"""모드 A — '이익 성장률 − 주가 상승률' 갭 신호 검증 (IS→OOS).

가설: 이익은 늘었는데(YoY>0) 주가가 그만큼 못 따라온 종목은, 이후 시장 대비 따라잡기
(catch-up) 초과수익을 낸다. 절대 성장률(EPS YoY 수준)이 아니라 **성장 대비 저평가 갭**을 본다.

PIT: 갭 = 이익YoY − (접수일까지 과거 1년 주가수익률). 둘 다 접수일에 알 수 있는 정보.
CAAR은 접수일 다음날부터 측정 → 따라잡기만 본다(룩어헤드 차단).

사용 예:
    python -m trading_engine.backtest.run_earnings_gap --split-year 2020 --sel-horizon 20
"""

from __future__ import annotations

import argparse

import pandas as pd

from trading_engine.backtest.event_study import (
    DEFAULT_HORIZONS,
    caar_for_signal,
    compute_event_cars,
    growth_gap_signal,
)
from trading_engine.backtest.run_earnings import DEFAULT_SYMBOLS, build_events_for_stock
from trading_engine.data import DartProvider, EarningsEvent, FdrProvider, trailing_return

_GAP_THRESHOLDS = (0.0, 0.20, 0.50, 1.0)  # 이익YoY가 주가YoY보다 0/20/50/100%p 이상 높음
_MIN_N = 20


def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="이익-주가 갭 신호 (IS→OOS)")
    p.add_argument("--symbols", default=",".join(DEFAULT_SYMBOLS))
    p.add_argument("--start-year", type=int, default=2016)
    p.add_argument("--end-year", type=int, default=2024)
    p.add_argument("--split-year", type=int, default=2020)
    p.add_argument("--sel-horizon", type=int, default=20)
    p.add_argument("--growth-field", default="eps", help="eps|net_income|revenue")
    p.add_argument("--market", default="KS11")
    return p.parse_args()


def main() -> None:
    args = _parse_args()
    symbols = [s.strip() for s in args.symbols.split(",") if s.strip()]
    dart = DartProvider()
    fdr = FdrProvider()
    start = f"{args.start_year - 1}-01-01"
    end = f"{args.end_year}-12-31"

    market = fdr.load_daily(args.market, start, end)["close"]
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
        # PIT 과거 1년 주가수익률 채우기 (접수일 다음 거래일=가용일 기준)
        for ev in evs:
            if ev.avail_date is not None:
                ev.price_yoy = trailing_return(close, ev.avail_date, lookback=252)
        all_events.extend(evs)

    event_cars = compute_event_cars(all_events, price_map, market, DEFAULT_HORIZONS)
    is_pairs = [(e, c) for e, c in event_cars if e.avail_date.year <= args.split_year]
    oos_pairs = [(e, c) for e, c in event_cars if e.avail_date.year > args.split_year]
    h = args.sel_horizon
    gf = args.growth_field
    print(f"이벤트: 전체 {len(event_cars)} | IS {len(is_pairs)} | OOS {len(oos_pairs)} | 성장지표={gf}")

    # 참고: 갭 분포 (가용일 기준 이익YoY−주가YoY)
    gaps = [
        (e.yoy.get(gf) - e.price_yoy)
        for e, _ in event_cars
        if e.yoy.get(gf) is not None and e.price_yoy is not None and e.yoy.get(gf) > 0
    ]
    if gaps:
        s = pd.Series(gaps)
        print(f"갭 분포(이익YoY>0, n={len(gaps)}): 중앙값 {s.median():.0%}, 25~75% {s.quantile(.25):.0%}~{s.quantile(.75):.0%}")

    print("\n" + "=" * 64)
    print(f"  [IS {args.start_year}~{args.split_year}] 갭 임계 스윕 (지평선 {h}일)")
    print("-" * 64)
    print(f"  {'갭 임계':<14} {'n':>4} {'CAAR':>9} {'t값':>7}")
    is_rows = []
    for th in _GAP_THRESHOLDS:
        sig = growth_gap_signal(th, gf)
        st = caar_for_signal(is_pairs, sig, (h,))[h]
        is_rows.append((th, sig, st))
        mark = " *" if st.n >= _MIN_N and abs(st.t_stat) > 2 else ""
        print(f"  {gf}−가격 ≥{th:>4.0%} {st.n:>4} {st.caar * 100:>8.2f}% {st.t_stat:>7.2f}{mark}")

    eligible = [r for r in is_rows if r[2].n >= _MIN_N and r[2].caar > 0]
    if not eligible:
        print("\n  IS에서 표본 충분한 양의 갭 신호 없음 → 알파 근거 약함.")
        print("=" * 64)
        return
    eligible.sort(key=lambda r: abs(r[2].t_stat), reverse=True)
    best_th, best_sig, best_is = eligible[0]
    oos = caar_for_signal(oos_pairs, best_sig, DEFAULT_HORIZONS)

    print("\n" + "=" * 64)
    print(f"  [OOS {args.split_year + 1}~{args.end_year}] IS best 갭≥{best_th:.0%} 확인")
    print(f"    (IS {h}일: CAAR {best_is.caar * 100:.2f}%, t {best_is.t_stat:.2f}, n {best_is.n})")
    print("-" * 64)
    print(f"  {'지평선(일)':>10} {'n':>5} {'CAAR':>10} {'t값':>8}")
    for hz in DEFAULT_HORIZONS:
        st = oos[hz]
        print(f"  {hz:>10} {st.n:>5} {st.caar * 100:>9.2f}% {st.t_stat:>8.2f}")
    print("=" * 64)
    print("  판정: OOS CAAR>0 & |t|>2 & 비용 차감 후 양수여야 모드 B 가치.")


if __name__ == "__main__":
    main()
