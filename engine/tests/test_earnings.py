"""PEAD 데이터 계층 단위 테스트 (라이브 DART 호출 없이 mock/합성으로 검증).

핵심 검증:
- 재무 수치 추출 (account_id 우선 + account_nm 폴백)
- YoY 계산 (정상/0/음수/None 처리)
- point-in-time 가용일 (접수일 다음 거래일, 주말/휴장, 범위초과)
- 정정공시 최초보고서 선택 (룩어헤드 차단)
- DART 응답 파싱 (corpCode.xml, list.json)
"""

from __future__ import annotations

import io
import zipfile

import pandas as pd
import pytest

from trading_engine.data import dart_provider as dp
from trading_engine.data.earnings import (
    EarningsEvent,
    availability_date,
    extract_figures,
    first_filings_only,
    prior_field_for,
    trailing_return,
    yoy,
)


# ── 합성 재무제표 행 (fnlttSinglAcntAll 응답 형태) ───────────────────────────
def _fs_rows_by_id() -> pd.DataFrame:
    """account_id 기반 손익계산서 일부 (당기 thstrm, 전기동분기 frmtrm_q)."""
    return pd.DataFrame(
        [
            {
                "sj_div": "IS",
                "account_id": "ifrs-full_Revenue",
                "account_nm": "매출액",
                "thstrm_amount": "1,200",
                "frmtrm_q_amount": "1,000",
                "frmtrm_amount": "900",
            },
            {
                "sj_div": "IS",
                "account_id": "dart_OperatingIncomeLoss",
                "account_nm": "영업이익",
                "thstrm_amount": "300",
                "frmtrm_q_amount": "200",
                "frmtrm_amount": "150",
            },
            {
                "sj_div": "IS",
                "account_id": "ifrs-full_ProfitLoss",
                "account_nm": "당기순이익",
                "thstrm_amount": "240",
                "frmtrm_q_amount": "150",
                "frmtrm_amount": "120",
            },
            {
                "sj_div": "IS",
                "account_id": "ifrs-full_BasicEarningsLossPerShare",
                "account_nm": "기본주당이익(손실)(원)",
                "thstrm_amount": "1,500",
                "frmtrm_q_amount": "1,000",
                "frmtrm_amount": "800",
            },
        ]
    )


def _fs_rows_by_name_only() -> pd.DataFrame:
    """account_id가 비어 있어 account_nm 폴백으로 매칭해야 하는 경우."""
    return pd.DataFrame(
        [
            {"account_id": "", "account_nm": "수익(매출액)", "thstrm_amount": "500", "frmtrm_q_amount": "400"},
            {"account_id": "", "account_nm": "영업이익", "thstrm_amount": "50", "frmtrm_q_amount": "40"},
            {"account_id": "", "account_nm": "당기순이익", "thstrm_amount": "30", "frmtrm_q_amount": "20"},
        ]
    )


# ── extract_figures ─────────────────────────────────────────────────────────
def test_extract_figures_by_account_id():
    fig = extract_figures(_fs_rows_by_id())
    assert fig.revenue == 1200.0
    assert fig.operating_income == 300.0
    assert fig.net_income == 240.0
    assert fig.eps == 1500.0
    assert fig.prior_revenue == 1000.0
    assert fig.prior_eps == 1000.0


def test_extract_figures_name_fallback():
    fig = extract_figures(_fs_rows_by_name_only())
    assert fig.revenue == 500.0
    assert fig.operating_income == 50.0
    assert fig.net_income == 30.0
    assert fig.prior_revenue == 400.0


def test_extract_figures_empty():
    fig = extract_figures(pd.DataFrame())
    assert fig.revenue is None and fig.eps is None


def test_extract_figures_annual_prior_field():
    # 사업보고서는 frmtrm_amount(전기) 사용
    fig = extract_figures(_fs_rows_by_id(), prior_field="frmtrm_amount")
    assert fig.prior_revenue == 900.0
    assert fig.prior_eps == 800.0


def test_trailing_return_pit():
    idx = pd.bdate_range("2022-01-03", periods=300)
    close = pd.Series(range(100, 400), index=idx, dtype=float)  # 단조 증가
    asof = idx[260]
    r = trailing_return(close, asof, lookback=252)
    end = float(close.iloc[260])
    start = float(close.iloc[260 - 252])
    assert r == pytest.approx(end / start - 1.0)


def test_trailing_return_ignores_future():
    idx = pd.bdate_range("2022-01-03", periods=300)
    close = pd.Series(range(100, 400), index=idx, dtype=float)
    asof = idx[260]
    # asof 이후 값을 바꿔도 결과 불변(룩어헤드 없음)
    r1 = trailing_return(close, asof, 252)
    close.iloc[261:] = 99999.0
    r2 = trailing_return(close, asof, 252)
    assert r1 == r2


def test_trailing_return_insufficient():
    idx = pd.bdate_range("2022-01-03", periods=100)
    close = pd.Series(range(100, 200), index=idx, dtype=float)
    assert trailing_return(close, idx[50], lookback=252) is None


def test_prior_field_for():
    # 분기/반기는 전기동분기, 사업보고서(연간)는 전기
    assert prior_field_for(dp.REPRT_Q1) == "frmtrm_q_amount"
    assert prior_field_for(dp.REPRT_HALF) == "frmtrm_q_amount"
    assert prior_field_for(dp.REPRT_Q3) == "frmtrm_q_amount"
    assert prior_field_for(dp.REPRT_ANNUAL) == "frmtrm_amount"


# ── _to_float 엣지 ──────────────────────────────────────────────────────────
@pytest.mark.parametrize(
    "raw,expected",
    [
        ("1,234", 1234.0),
        ("-", None),
        ("", None),
        (None, None),
        ("(500)", -500.0),  # 괄호 음수
        ("-300", -300.0),
        ("1,234,567", 1234567.0),
    ],
)
def test_to_float(raw, expected):
    assert dp_to_float(raw) == expected if expected is not None else dp_to_float(raw) is None


def dp_to_float(raw):
    from trading_engine.data.earnings import _to_float

    return _to_float(raw)


# ── yoy ─────────────────────────────────────────────────────────────────────
def test_yoy_normal():
    assert yoy(120, 100) == pytest.approx(0.2)


def test_yoy_zero_and_negative_prior_is_none():
    assert yoy(120, 0) is None
    assert yoy(120, -50) is None  # 전년 적자 → 비율 의미 없음


def test_yoy_none_inputs():
    assert yoy(None, 100) is None
    assert yoy(100, None) is None


# ── EarningsEvent.yoy dict ──────────────────────────────────────────────────
def test_earnings_event_computes_yoy():
    fig = extract_figures(_fs_rows_by_id())
    ev = EarningsEvent(
        stock_code="005930",
        corp_code="00126380",
        rcept_no="20230814000001",
        rcept_dt="20230814",
        bsns_year=2023,
        reprt_code=dp.REPRT_HALF,
        is_amendment=False,
        figures=fig,
    )
    assert ev.yoy["revenue"] == pytest.approx(0.2)  # 1200 vs 1000
    assert ev.yoy["eps"] == pytest.approx(0.5)  # 1500 vs 1000
    assert ev.yoy["net_income"] == pytest.approx(0.6)  # 240 vs 150


# ── availability_date (PIT) ─────────────────────────────────────────────────
def test_availability_date_next_trading_day():
    idx = pd.to_datetime(["2023-08-14", "2023-08-15", "2023-08-16", "2023-08-17"])
    # 접수일 당일(08-14)이 아니라 다음 거래일(08-15)이어야 함
    assert availability_date("20230814", idx) == pd.Timestamp("2023-08-15")


def test_availability_date_skips_weekend():
    # 금요일(08-11) 접수 → 다음 거래일은 월요일(08-14)
    idx = pd.to_datetime(["2023-08-10", "2023-08-11", "2023-08-14", "2023-08-15"])
    assert availability_date("20230811", idx) == pd.Timestamp("2023-08-14")


def test_availability_date_out_of_range():
    idx = pd.to_datetime(["2023-08-14", "2023-08-15"])
    assert availability_date("20231231", idx) is None  # 인덱스 끝 이후


def test_availability_date_strictly_after_disclosure():
    # 접수일이 마지막 거래일과 같으면 그 이후가 없으므로 None (당일 체결 금지)
    idx = pd.to_datetime(["2023-08-14"])
    assert availability_date("20230814", idx) is None


# ── first_filings_only (정정공시 룩어헤드 차단) ──────────────────────────────
def test_first_filings_only_prefers_original():
    df = pd.DataFrame(
        [
            {"rcept_no": "2", "rcept_dt": "20230820", "report_nm": "[정정]반기보고서", "is_amendment": True},
            {"rcept_no": "1", "rcept_dt": "20230814", "report_nm": "반기보고서", "is_amendment": False},
        ]
    )
    out = first_filings_only(df)
    # 정정(08-20)이 아니라 최초 정식 보고서(08-14)를 선택
    assert list(out["rcept_no"]) == ["1"]
    assert out.iloc[0]["rcept_dt"] == "20230814"


def test_first_filings_only_all_amendments_takes_earliest():
    df = pd.DataFrame(
        [
            {"rcept_no": "2", "rcept_dt": "20230820", "report_nm": "[정정]분기보고서", "is_amendment": True},
            {"rcept_no": "3", "rcept_dt": "20230825", "report_nm": "[정정]분기보고서", "is_amendment": True},
        ]
    )
    out = first_filings_only(df)
    assert out.iloc[0]["rcept_no"] == "2"  # 가장 이른 접수


# ── DART 응답 파싱 ───────────────────────────────────────────────────────────
def test_parse_corp_code_xml_includes_delisted():
    xml_str = (
        "<?xml version='1.0' encoding='utf-8'?><result>"
        "<list><corp_code>00126380</corp_code><corp_name>삼성전자</corp_name>"
        "<stock_code>005930</stock_code><modify_date>20230101</modify_date></list>"
        "<list><corp_code>00999999</corp_code><corp_name>상폐기업</corp_name>"
        "<stock_code> </stock_code><modify_date>20180101</modify_date></list>"
        "</result>"
    )
    df = dp._parse_corp_code_xml(xml_str.encode("utf-8"))
    assert len(df) == 2
    # 상장사
    assert df.loc[df["stock_code"] == "005930", "corp_code"].iloc[0] == "00126380"
    # 비상장/상폐(주식코드 공백)도 corp_code는 보존됨 (생존편향 방지 핵심)
    assert (df["stock_code"] == "").any()


def test_parse_corp_code_zip_roundtrip():
    xml = (
        b"<result><list><corp_code>00126380</corp_code>"
        b"<corp_name>X</corp_name><stock_code>005930</stock_code>"
        b"<modify_date>20230101</modify_date></list></result>"
    )
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("CORPCODE.xml", xml)
    df = dp._parse_corp_code_zip(buf.getvalue())
    assert df.iloc[0]["corp_code"] == "00126380"


def test_normalize_disclosure_list_detects_amendment():
    rows = [
        {"rcept_no": "1", "rcept_dt": "20230814", "report_nm": "반기보고서", "corp_code": "C", "corp_name": "X"},
        {"rcept_no": "2", "rcept_dt": "20230820", "report_nm": "[정정]반기보고서", "corp_code": "C", "corp_name": "X"},
    ]
    df = dp._normalize_disclosure_list(rows)
    assert list(df["is_amendment"]) == [False, True]  # 접수일 정렬됨
    assert list(df.columns) == dp.DISCLOSURE_COLUMNS


def test_normalize_disclosure_list_empty():
    df = dp._normalize_disclosure_list([])
    assert df.empty and list(df.columns) == dp.DISCLOSURE_COLUMNS


# ── DartProvider HTTP mock (라이브 키 불필요) ────────────────────────────────
def test_financial_statement_mocked(monkeypatch):
    prov = dp.DartProvider(api_key="DUMMY", cache_dir="/tmp/_dart_test_cache")

    def fake_get_json(endpoint, params):
        assert endpoint == "fnlttSinglAcntAll"
        assert params["fs_div"] == "CFS"
        return {"status": "000", "list": _fs_rows_by_id().to_dict("records")}

    monkeypatch.setattr(prov, "_get_json", fake_get_json)
    df = prov.financial_statement("00126380", 2023, dp.REPRT_HALF, use_cache=False)
    fig = extract_figures(df)
    assert fig.revenue == 1200.0


def test_financial_statement_no_data(monkeypatch):
    prov = dp.DartProvider(api_key="DUMMY")
    monkeypatch.setattr(prov, "_get_json", lambda e, p: {"status": "013", "message": "no data"})
    df = prov.financial_statement("00126380", 2014, dp.REPRT_ANNUAL, use_cache=False)
    assert df.empty


def test_list_disclosures_paginates(monkeypatch):
    prov = dp.DartProvider(api_key="DUMMY")
    calls = {"n": 0}

    def fake_get_json(endpoint, params):
        calls["n"] += 1
        page = params["page_no"]
        return {
            "status": "000",
            "total_page": 2,
            "list": [
                {
                    "rcept_no": f"p{page}",
                    "rcept_dt": f"2023081{page}",
                    "report_nm": "분기보고서",
                    "corp_code": "C",
                    "corp_name": "X",
                }
            ],
        }

    monkeypatch.setattr(prov, "_get_json", fake_get_json)
    df = prov.list_disclosures("C", "20230101", "20231231", use_cache=False)
    assert calls["n"] == 2  # 2페이지 순회
    assert len(df) == 2


def test_corp_code_for_mocked(monkeypatch):
    prov = dp.DartProvider(api_key="DUMMY")
    mapping = pd.DataFrame(
        [{"corp_code": "00126380", "corp_name": "삼성전자", "stock_code": "005930", "modify_date": "x"}]
    )
    monkeypatch.setattr(prov, "corp_codes", lambda use_cache=True: mapping)
    assert prov.corp_code_for("005930") == "00126380"
    assert prov.corp_code_for("000000") is None


def test_dart_error_on_bad_status(monkeypatch):
    prov = dp.DartProvider(api_key="DUMMY")

    def boom(endpoint, params):
        # 실제 _get_json 로직을 흉내내되 020(한도초과)에서 raise
        data = {"status": "020", "message": "사용한도 초과"}
        if data["status"] not in ("000", "013"):
            raise dp.DartError(data["status"], data["message"])
        return data

    monkeypatch.setattr(prov, "_get_json", boom)
    with pytest.raises(dp.DartError):
        prov.financial_statement("C", 2023, dp.REPRT_Q1, use_cache=False)
