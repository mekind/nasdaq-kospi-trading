"""DART OpenAPI(금융감독원 전자공시) 클라이언트 + 로컬 캐시.

PEAD 전략의 실적/재무 데이터 소스. point-in-time(공시 접수일) 정합성을 위해
재무제표(fnlttSinglAcntAll)와 공시검색(list.json)을 **분리해서** 제공한다.

데이터 가용성·제약은 docs/research/07-dart-data-availability.md 참조:
- 재무제표는 2015년(bsns_year) 이후만 제공
- 일 10,000건 호출 한도 → parquet 캐시로 재호출 최소화
- 상장폐지 종목은 corp_code가 존재하면 폐지 전 재무를 받을 수 있음(생존편향 수동 처리)
"""

from __future__ import annotations

import io
import os
import zipfile
from xml.etree import ElementTree as ET

import httpx
import pandas as pd

from trading_engine.config import settings

# 분기/사업보고서 보고서 코드
REPRT_Q1 = "11013"  # 1분기보고서
REPRT_HALF = "11012"  # 반기보고서
REPRT_Q3 = "11014"  # 3분기보고서
REPRT_ANNUAL = "11011"  # 사업보고서(연간)
QUARTERLY_REPRT_CODES = (REPRT_Q1, REPRT_HALF, REPRT_Q3, REPRT_ANNUAL)

# 정기공시 상세유형: A001 사업보고서, A002 반기보고서, A003 분기보고서
PERIODIC_REPORT_TYPE = "A"  # pblntf_ty (정기공시)


class DartError(RuntimeError):
    """DART API가 비정상 status를 반환했을 때."""

    def __init__(self, status: str, message: str) -> None:
        self.status = status
        self.message = message
        super().__init__(f"DART status={status}: {message}")


class DartProvider:
    """DART OpenAPI 로더 + parquet 캐시.

    Parameters
    ----------
    api_key:
        DART 인증키. None이면 ``settings.dart_api_key``(.env의 DART_API_KEY) 사용.
    cache_dir:
        parquet/zip 캐시 디렉터리. 기본 ``"data/dart_cache"``.
    timeout:
        HTTP 타임아웃(초).
    """

    BASE = "https://opendart.fss.or.kr/api"

    def __init__(
        self,
        api_key: str | None = None,
        cache_dir: str = "data/dart_cache",
        timeout: float = 30.0,
    ) -> None:
        self.api_key = api_key if api_key is not None else settings.dart_api_key
        self.cache_dir = cache_dir
        self.timeout = timeout

    # ── 저수준 HTTP (테스트에서 monkeypatch 지점) ────────────────────────────
    def _get_json(self, endpoint: str, params: dict) -> dict:
        """``{endpoint}.json`` 을 호출해 dict를 반환. status 검증 포함."""
        p = {"crtfc_key": self.api_key, **params}
        url = f"{self.BASE}/{endpoint}.json"
        resp = httpx.get(url, params=p, timeout=self.timeout)
        resp.raise_for_status()
        data = resp.json()
        status = data.get("status", "000")
        # 013 = 조회된 데이터 없음 (정상 흐름에서 발생 가능 → 빈 결과로 처리)
        if status not in ("000", "013"):
            raise DartError(status, data.get("message", ""))
        return data

    def _get_bytes(self, endpoint: str, params: dict) -> bytes:
        """``{endpoint}.xml`` 등 바이너리 응답(zip)을 반환."""
        p = {"crtfc_key": self.api_key, **params}
        url = f"{self.BASE}/{endpoint}.xml"
        resp = httpx.get(url, params=p, timeout=self.timeout)
        resp.raise_for_status()
        return resp.content

    # ── corp_code ↔ 종목코드 매핑 ────────────────────────────────────────────
    def corp_codes(self, use_cache: bool = True) -> pd.DataFrame:
        """전체 공시대상 법인의 corp_code 매핑 테이블.

        Returns
        -------
        pd.DataFrame
            컬럼 ``corp_code``(8자리), ``corp_name``, ``stock_code``(6자리, 비상장은 빈값),
            ``modify_date``. 상장폐지 법인도 corp_code가 있으면 포함된다(생존편향 방지).
        """
        cache_path = os.path.join(self.cache_dir, "corp_codes.parquet")
        if use_cache and os.path.isfile(cache_path):
            return pd.read_parquet(cache_path)

        raw = self._get_bytes("corpCode", {})
        df = _parse_corp_code_zip(raw)

        if use_cache:
            os.makedirs(self.cache_dir, exist_ok=True)
            df.to_parquet(cache_path, engine="pyarrow")
        return df

    def corp_code_for(self, stock_code: str, use_cache: bool = True) -> str | None:
        """6자리 종목코드 → 8자리 corp_code. 없으면 None.

        주의: corpCode.xml의 stock_code는 보통주 기준이라 우선주는 매핑되지 않을 수 있다.
        """
        codes = self.corp_codes(use_cache=use_cache)
        hit = codes.loc[codes["stock_code"] == str(stock_code).zfill(6), "corp_code"]
        return None if hit.empty else str(hit.iloc[0])

    # ── 공시검색 (접수일 = PIT 기준일) ───────────────────────────────────────
    def list_disclosures(
        self,
        corp_code: str,
        bgn_de: str,
        end_de: str,
        pblntf_ty: str = PERIODIC_REPORT_TYPE,
        last_reprt_at: str = "N",
        use_cache: bool = True,
    ) -> pd.DataFrame:
        """기업의 공시 목록을 접수일과 함께 반환.

        point-in-time의 핵심: ``rcept_dt``(접수일자)는 시장이 실제로 정보를 안 날이다.
        ``last_reprt_at="N"`` 이면 정정 이력을 포함(최초 보고서 식별 가능).

        Parameters
        ----------
        bgn_de, end_de:
            검색 시작/종료 접수일 ``YYYYMMDD``.
        pblntf_ty:
            공시유형. ``"A"`` 정기공시(사업/반기/분기보고서).

        Returns
        -------
        pd.DataFrame
            컬럼 ``rcept_no, rcept_dt, report_nm, corp_code, corp_name, is_amendment``.
            결과 없으면 동일 스키마의 빈 DataFrame.
        """
        cache_path = os.path.join(
            self.cache_dir, f"list_{corp_code}_{bgn_de}_{end_de}_{pblntf_ty}_{last_reprt_at}.parquet"
        )
        if use_cache and os.path.isfile(cache_path):
            return pd.read_parquet(cache_path)

        rows: list[dict] = []
        page_no = 1
        while True:
            data = self._get_json(
                "list",
                {
                    "corp_code": corp_code,
                    "bgn_de": bgn_de,
                    "end_de": end_de,
                    "pblntf_ty": pblntf_ty,
                    "last_reprt_at": last_reprt_at,
                    "page_no": page_no,
                    "page_count": 100,
                },
            )
            if data.get("status") == "013":  # 데이터 없음
                break
            rows.extend(data.get("list", []))
            total_page = int(data.get("total_page", 1) or 1)
            if page_no >= total_page:
                break
            page_no += 1

        df = _normalize_disclosure_list(rows)
        if use_cache:
            os.makedirs(self.cache_dir, exist_ok=True)
            df.to_parquet(cache_path, engine="pyarrow")
        return df

    # ── 재무제표 ─────────────────────────────────────────────────────────────
    def financial_statement(
        self,
        corp_code: str,
        bsns_year: int | str,
        reprt_code: str,
        fs_div: str = "CFS",
        use_cache: bool = True,
    ) -> pd.DataFrame:
        """단일회사 전체재무제표(fnlttSinglAcntAll) 계정 행을 반환.

        Parameters
        ----------
        fs_div:
            ``"CFS"`` 연결 / ``"OFS"`` 별도. PEAD는 연결(CFS) 권장.

        Returns
        -------
        pd.DataFrame
            DART 응답 계정 행(``sj_div, account_id, account_nm, thstrm_amount,
            frmtrm_q_amount, ...``). 결과 없으면 빈 DataFrame.

        Notes
        -----
        ``bsns_year`` 2015 미만은 DART가 데이터를 제공하지 않는다.
        """
        bsns_year = str(bsns_year)
        cache_path = os.path.join(
            self.cache_dir, f"fs_{corp_code}_{bsns_year}_{reprt_code}_{fs_div}.parquet"
        )
        if use_cache and os.path.isfile(cache_path):
            return pd.read_parquet(cache_path)

        data = self._get_json(
            "fnlttSinglAcntAll",
            {
                "corp_code": corp_code,
                "bsns_year": bsns_year,
                "reprt_code": reprt_code,
                "fs_div": fs_div,
            },
        )
        rows = [] if data.get("status") == "013" else data.get("list", [])
        df = pd.DataFrame(rows)

        if use_cache:
            os.makedirs(self.cache_dir, exist_ok=True)
            df.to_parquet(cache_path, engine="pyarrow")
        return df


# ── 순수 파싱 헬퍼 (HTTP 비의존 → 단위테스트 용이) ────────────────────────────
def _parse_corp_code_zip(raw: bytes) -> pd.DataFrame:
    """corpCode.xml ZIP 바이트를 corp_code 매핑 DataFrame으로 파싱."""
    with zipfile.ZipFile(io.BytesIO(raw)) as zf:
        xml_name = zf.namelist()[0]
        xml_bytes = zf.read(xml_name)
    return _parse_corp_code_xml(xml_bytes)


def _parse_corp_code_xml(xml_bytes: bytes) -> pd.DataFrame:
    """corpCode.xml 본문을 DataFrame으로 파싱 (stock_code 공백은 빈 문자열로)."""
    root = ET.fromstring(xml_bytes)
    rows: list[dict] = []
    for item in root.iter("list"):
        rows.append(
            {
                "corp_code": (item.findtext("corp_code") or "").strip(),
                "corp_name": (item.findtext("corp_name") or "").strip(),
                "stock_code": (item.findtext("stock_code") or "").strip(),
                "modify_date": (item.findtext("modify_date") or "").strip(),
            }
        )
    df = pd.DataFrame(rows, columns=["corp_code", "corp_name", "stock_code", "modify_date"])
    return df


DISCLOSURE_COLUMNS = [
    "rcept_no",
    "rcept_dt",
    "report_nm",
    "corp_code",
    "corp_name",
    "is_amendment",
]


def _normalize_disclosure_list(rows: list[dict]) -> pd.DataFrame:
    """list.json 의 list 항목들을 표준 스키마로 정규화.

    ``is_amendment`` 는 보고서명에 '정정'이 포함되는지로 판정(DART는 부모 보고서를
    명시 연결하지 않으므로 텍스트 기반).
    """
    if not rows:
        return pd.DataFrame(columns=DISCLOSURE_COLUMNS)
    out: list[dict] = []
    for r in rows:
        report_nm = r.get("report_nm", "")
        out.append(
            {
                "rcept_no": r.get("rcept_no", ""),
                "rcept_dt": r.get("rcept_dt", ""),
                "report_nm": report_nm,
                "corp_code": r.get("corp_code", ""),
                "corp_name": r.get("corp_name", ""),
                "is_amendment": "정정" in report_nm,
            }
        )
    df = pd.DataFrame(out, columns=DISCLOSURE_COLUMNS)
    # 접수일 오름차순 정렬 (최초 보고서 식별 용이)
    return df.sort_values("rcept_dt").reset_index(drop=True)
