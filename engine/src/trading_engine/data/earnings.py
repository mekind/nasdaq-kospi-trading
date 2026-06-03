"""실적 이벤트 모델 + YoY 계산 + point-in-time(접수일) 정렬.

DART 재무제표(fnlttSinglAcntAll) 계정 행에서 매출·영업이익·순이익·EPS를 추출하고,
전년동기 대비(YoY) 성장률을 계산한다. 공시 접수일(rcept_dt)을 거래일 캘린더에 정렬해
**신호 가용일 = 접수일 다음 거래일**로 만든다(룩어헤드 차단).

재무 필드 semantics(전기동분기 등)는 라이브 검증 대상 — 07-dart-data-availability.md 참조.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import pandas as pd

# ── 계정 식별: XBRL account_id 우선, account_nm(한글) 폴백 ────────────────────
# DART/IFRS 표준 태그. 회사별로 account_id가 비거나 변형될 수 있어 이름 폴백을 둔다.
ACCOUNT_SPECS = {
    "revenue": {
        "ids": ("ifrs-full_Revenue", "ifrs_Revenue"),
        "names": ("매출액", "수익(매출액)", "영업수익"),
    },
    "operating_income": {
        "ids": ("dart_OperatingIncomeLoss", "ifrs-full_OperatingIncomeLoss"),
        "names": ("영업이익", "영업이익(손실)"),
    },
    "net_income": {
        "ids": ("ifrs-full_ProfitLoss", "ifrs_ProfitLoss"),
        "names": ("당기순이익", "당기순이익(손실)", "분기순이익", "반기순이익"),
    },
    "eps": {
        "ids": ("ifrs-full_BasicEarningsLossPerShare", "ifrs_BasicEarningsLossPerShare"),
        "names": ("기본주당이익", "기본주당순이익", "기본주당이익(손실)"),
    },
}


def _to_float(value) -> float | None:
    """DART 금액 문자열('1,234', '-', '', None)을 float로. 변환 불가 시 None."""
    if value is None:
        return None
    s = str(value).strip().replace(",", "")
    if s in ("", "-", "—"):
        return None
    # 괄호 음수 표기 (1,234) → -1234
    neg = s.startswith("(") and s.endswith(")")
    if neg:
        s = s[1:-1]
    try:
        f = float(s)
    except ValueError:
        return None
    return -f if neg else f


def _match_row(fs_df: pd.DataFrame, ids: tuple[str, ...], names: tuple[str, ...]) -> pd.Series | None:
    """account_id 우선, 없으면 account_nm 부분일치로 계정 행 1개를 찾는다."""
    if fs_df.empty:
        return None
    if "account_id" in fs_df.columns:
        for aid in ids:
            hit = fs_df[fs_df["account_id"] == aid]
            if not hit.empty:
                return hit.iloc[0]
    if "account_nm" in fs_df.columns:
        nm = fs_df["account_nm"].fillna("")
        for name in names:
            hit = fs_df[nm.str.contains(name, regex=False)]
            if not hit.empty:
                return hit.iloc[0]
    return None


@dataclass
class FinancialFigures:
    """한 보고서에서 추출한 핵심 재무 수치 (당기 + 전년동기)."""

    revenue: float | None = None
    operating_income: float | None = None
    net_income: float | None = None
    eps: float | None = None
    # 전년동기(전기동분기) 값 — YoY 계산용
    prior_revenue: float | None = None
    prior_operating_income: float | None = None
    prior_net_income: float | None = None
    prior_eps: float | None = None


def prior_field_for(reprt_code: str) -> str:
    """보고서 코드에 맞는 전년동기 금액 컬럼명.

    분기/반기 보고서는 ``frmtrm_q_amount``(전기 동기 3개월), 사업보고서(연간)는
    분기 컬럼이 없으므로 ``frmtrm_amount``(전기 연간)를 쓴다.
    (라이브 검증: 삼성전자 2023 반기 thstrm=당기3개월, frmtrm_q=전년동기3개월으로 동일기간 YoY 성립)
    """
    from trading_engine.data.dart_provider import REPRT_ANNUAL

    return "frmtrm_amount" if reprt_code == REPRT_ANNUAL else "frmtrm_q_amount"


def extract_figures(fs_df: pd.DataFrame, prior_field: str = "frmtrm_q_amount") -> FinancialFigures:
    """fnlttSinglAcntAll 계정 행 DataFrame에서 핵심 수치를 추출.

    ``thstrm_amount`` 는 손익계산서 기준 **당기 3개월**(분기/반기 보고서) 금액이며,
    누적은 ``thstrm_add_amount`` 에 별도로 있다. YoY는 동일 기간(3개월) 비교를 위해
    ``thstrm_amount`` vs ``prior_field`` 를 사용한다.

    Parameters
    ----------
    prior_field:
        전년동기 금액 컬럼. 분기/반기는 ``"frmtrm_q_amount"``(전기 동기 3개월),
        사업보고서는 ``"frmtrm_amount"``(전기 연간). ``prior_field_for()`` 참조.
    """
    fig = FinancialFigures()
    for key, spec in ACCOUNT_SPECS.items():
        row = _match_row(fs_df, spec["ids"], spec["names"])
        if row is None:
            continue
        setattr(fig, key, _to_float(row.get("thstrm_amount")))
        prior = row.get(prior_field) if prior_field in row else None
        if prior is None and "frmtrm_amount" in row:
            prior = row.get("frmtrm_amount")  # 폴백
        setattr(fig, f"prior_{key}", _to_float(prior))
    return fig


def yoy(current: float | None, prior: float | None) -> float | None:
    """전년동기 대비 성장률. 분모가 0/None이거나 부호가 바뀌면 None(정의 곤란).

    부호 전환(적자→흑자 등)은 비율 의미가 왜곡되므로 None으로 두고 신호단에서 별도 처리.
    """
    if current is None or prior is None:
        return None
    if prior == 0:
        return None
    if prior < 0:
        return None  # 전년 적자 → 성장률 비율 의미 없음
    return (current - prior) / prior


@dataclass
class EarningsEvent:
    """point-in-time 실적 이벤트 하나.

    ``avail_date`` 는 신호가 유효해지는 거래일(접수일 다음 거래일). 백테스트 엔진은
    이 시점 시그널을 받아 다시 다음 봉 시가에 체결하므로 룩어헤드가 발생하지 않는다.
    """

    stock_code: str
    corp_code: str
    rcept_no: str
    rcept_dt: str  # YYYYMMDD (접수일)
    bsns_year: int
    reprt_code: str
    is_amendment: bool
    figures: FinancialFigures
    avail_date: pd.Timestamp | None = None  # 접수일 다음 거래일 (PIT 가용일)
    yoy: dict[str, float | None] = field(default_factory=dict)

    def __post_init__(self) -> None:
        f = self.figures
        self.yoy = {
            "revenue": yoy(f.revenue, f.prior_revenue),
            "operating_income": yoy(f.operating_income, f.prior_operating_income),
            "net_income": yoy(f.net_income, f.prior_net_income),
            "eps": yoy(f.eps, f.prior_eps),
        }


def availability_date(rcept_dt: str, trading_index: pd.DatetimeIndex) -> pd.Timestamp | None:
    """접수일(YYYYMMDD) 다음 거래일을 거래일 인덱스에서 찾는다.

    접수일 당일은 장중/장후 발표 시각이 불명확하므로 보수적으로 **접수일 다음 거래일**을
    신호 가용일로 삼는다(접수일이 휴장/주말이면 그 이후 첫 거래일). 범위를 벗어나면 None.
    """
    if trading_index is None or len(trading_index) == 0:
        return None
    rcept_ts = pd.Timestamp(f"{rcept_dt[:4]}-{rcept_dt[4:6]}-{rcept_dt[6:8]}")
    # 접수일보다 '엄격히 큰' 첫 거래일
    later = trading_index[trading_index > rcept_ts]
    return None if len(later) == 0 else later[0]


def first_filings_only(disclosures: pd.DataFrame) -> pd.DataFrame:
    """정정 이력 중 **최초 접수 보고서만** 남긴다(룩어헤드 차단).

    같은 (bsns_year, reprt_code)에 대해 최초 접수분만 신호에 써야 하므로,
    보고서명에서 정정 표기를 제거하고 접수일이 가장 이른 행을 택한다.
    실무에선 report_nm 정규화로 그룹핑하지만, 여기선 보수적으로 is_amendment=False 중
    가장 이른 접수분을 우선한다.
    """
    if disclosures.empty:
        return disclosures
    df = disclosures.sort_values("rcept_dt")
    originals = df[~df["is_amendment"]]
    # 최초 정식 보고서가 있으면 그것, 없으면(전부 정정뿐) 가장 이른 것
    return (originals if not originals.empty else df).reset_index(drop=True)
