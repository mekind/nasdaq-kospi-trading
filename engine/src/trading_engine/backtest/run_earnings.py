"""모드 A 이벤트 스터디(CAAR) 실행 CLI — PEAD 알파 존재 게이트.

DART 실적 이벤트를 수집해 가용일(접수일 다음 거래일) 정렬 후, EPS YoY 시그널 통과 건의
시장(KOSPI) 대비 누적초과수익(CAAR)을 집계한다.

사용 예:
    python -m trading_engine.backtest.run_earnings --start-year 2016 --end-year 2024 \
        --symbols 005930,000660,005380,051910,035420 --eps-yoy 0.20

주의(정직성):
- 명시적 유니버스(--symbols)만 검증하면 현재 생존 종목 위주 → **생존편향**. 결과는 상한 추정.
- CAR은 발표 당일 점프 제외, 가용일 다음날부터 누적(룩어헤드 차단).
- DART 2015년 이후만 → 2008/2011 위기 미포함.
"""

from __future__ import annotations

import argparse

import pandas as pd

from trading_engine.backtest.event_study import (
    DEFAULT_HORIZONS,
    eps_yoy_signal,
    run_event_study,
)
from trading_engine.data import (
    DartProvider,
    EarningsEvent,
    FdrProvider,
    availability_date,
    extract_figures,
    first_filings_only,
    prior_field_for,
)
from trading_engine.data.dart_provider import QUARTERLY_REPRT_CODES

# KOSPI 대형주 샘플 (생존편향 있음 — PIT 유니버스는 Phase 2 과제)
DEFAULT_SYMBOLS = [
    "005930",  # 삼성전자
    "000660",  # SK하이닉스
    "005380",  # 현대차
    "051910",  # LG화학
    "035420",  # NAVER
    "005490",  # POSCO홀딩스
    "012330",  # 현대모비스
    "055550",  # 신한지주
    "105560",  # KB금융
    "096770",  # SK이노베이션
]


def build_events_for_stock(
    dart: DartProvider,
    stock_code: str,
    price_index: pd.DatetimeIndex,
    start_year: int,
    end_year: int,
) -> list[EarningsEvent]:
    """한 종목의 정기보고서 실적 이벤트를 point-in-time으로 구성."""
    corp = dart.corp_code_for(stock_code)
    if corp is None:
        return []

    # 공시검색(정기보고서)으로 접수일 확보 → 최초 보고서만
    disclosures = dart.list_disclosures(
        corp, f"{start_year}0101", f"{end_year}1231", pblntf_ty="A", last_reprt_at="N"
    )
    disclosures = first_filings_only(disclosures)
    # 접수일 → (bsns_year, reprt_code) 추정용 매핑: 보고서명에서 분기/연도 파싱
    rcept_by_period: dict[tuple[int, str], str] = {}
    for _, d in disclosures.iterrows():
        period = _infer_period(d["report_nm"])
        if period is not None:
            rcept_by_period.setdefault(period, d["rcept_dt"])

    events: list[EarningsEvent] = []
    for year in range(start_year, end_year + 1):
        for reprt in QUARTERLY_REPRT_CODES:
            rcept_dt = rcept_by_period.get((year, reprt))
            if rcept_dt is None:
                continue
            fs = dart.financial_statement(corp, year, reprt, fs_div="CFS")
            if fs.empty:
                continue
            fig = extract_figures(fs, prior_field=prior_field_for(reprt))
            ev = EarningsEvent(
                stock_code=stock_code,
                corp_code=corp,
                rcept_no="",
                rcept_dt=rcept_dt,
                bsns_year=year,
                reprt_code=reprt,
                is_amendment=False,
                figures=fig,
                avail_date=availability_date(rcept_dt, price_index),
            )
            events.append(ev)
    return events


# 보고서명 → (연도, reprt_code). 예: "분기보고서 (2023.09)" → (2023, 11014)
_MONTH_TO_REPRT = {"03": "11013", "06": "11012", "09": "11014", "12": "11011"}


def _infer_period(report_nm: str) -> tuple[int, str] | None:
    """보고서명 괄호의 'YYYY.MM' 으로 (연도, reprt_code)를 추정."""
    import re

    m = re.search(r"\((\d{4})\.(\d{2})\)", report_nm)
    if not m:
        return None
    year = int(m.group(1))
    reprt = _MONTH_TO_REPRT.get(m.group(2))
    return None if reprt is None else (year, reprt)


def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="PEAD 이벤트 스터디(CAAR)")
    p.add_argument("--symbols", default=",".join(DEFAULT_SYMBOLS), help="쉼표구분 종목코드")
    p.add_argument("--start-year", type=int, default=2016)
    p.add_argument("--end-year", type=int, default=2024)
    p.add_argument("--eps-yoy", type=float, default=0.20, help="EPS YoY 진입 임계")
    p.add_argument("--market", default="KS11", help="시장지수 심볼 (기본 KOSPI)")
    return p.parse_args()


def main() -> None:
    args = _parse_args()
    symbols = [s.strip() for s in args.symbols.split(",") if s.strip()]
    dart = DartProvider()
    fdr = FdrProvider()

    start = f"{args.start_year - 1}-01-01"  # 전년 데이터 여유
    end = f"{args.end_year}-12-31"

    print(f"[1/3] 시장지수 로드: {args.market}")
    market = fdr.load_daily(args.market, start, end)["close"]

    print(f"[2/3] 이벤트 수집: {len(symbols)}종목 ({args.start_year}~{args.end_year})")
    all_events: list[EarningsEvent] = []
    price_map: dict[str, pd.Series] = {}
    for sym in symbols:
        try:
            close = fdr.load_daily(sym, start, end)["close"]
        except Exception as e:  # noqa: BLE001
            print(f"    {sym}: 가격 로드 실패 {e}")
            continue
        price_map[sym] = close
        evs = build_events_for_stock(dart, sym, close.index, args.start_year, args.end_year)
        all_events.extend(evs)
        n_sig = sum(1 for e in evs if (e.yoy.get("eps") or -9) >= args.eps_yoy)
        print(f"    {sym}: 이벤트 {len(evs)}건, EPS YoY≥{args.eps_yoy} {n_sig}건")

    print("[3/3] CAAR 집계 (EPS YoY 시그널, 시장조정)\n")
    result = run_event_study(
        all_events, price_map, market, eps_yoy_signal(args.eps_yoy), DEFAULT_HORIZONS
    )

    print("=" * 52)
    print(f"  PEAD 이벤트 스터디 — EPS YoY ≥ {args.eps_yoy:.0%}")
    print(f"  유니버스 {len(symbols)}종목, {args.start_year}~{args.end_year} (생존편향 주의)")
    print("-" * 52)
    print(f"  {'지평선(일)':>10} {'n':>5} {'CAAR':>10} {'t값':>8}")
    for h in DEFAULT_HORIZONS:
        s = result[h]
        print(f"  {h:>10} {s.n:>5} {s.caar * 100:>9.2f}% {s.t_stat:>8.2f}")
    print("=" * 52)
    print("  해석: CAAR>0 & |t|>2 면 비용 차감 전 드리프트 알파 시사.")
    print("        비용(왕복≈0.21%+슬리피지) 차감 후에도 양수여야 모드 B 진행 가치.")


if __name__ == "__main__":
    main()
