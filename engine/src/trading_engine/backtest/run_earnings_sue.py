"""모드 A — 정통 PEAD: SUE(표준화 기대외이익) 신호 (IS→OOS).

YoY '성장 수준'이 아니라 '기대를 깬 정도'를 본다. 기대 = 계절 랜덤워크(전년동기),
UE = 당분기 순이익 − 전년동기, SUE = UE / 과거 UE 표준편차. 모두 DART 무료 데이터로 계산.

PIT: SUE는 해당 분기 이전 UE만으로 표준화. CAAR은 접수일 다음날부터 측정(룩어헤드 차단).

사용 예:
    python -m trading_engine.backtest.run_earnings_sue --split-year 2020 --sel-horizon 60
"""

from __future__ import annotations

import argparse

import pandas as pd

from trading_engine.backtest.event_study import (
    DEFAULT_HORIZONS,
    caar_for_signal,
    compute_event_cars,
    sue_signal,
)
from trading_engine.backtest.run_earnings import DEFAULT_SYMBOLS, build_events_for_stock
from trading_engine.data import DartProvider, EarningsEvent, FdrProvider, attach_sue

_SUE_THRESHOLDS = (0.5, 1.0, 1.5, 2.0)
_MIN_N = 20


def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="SUE 기반 PEAD (IS→OOS)")
    p.add_argument("--symbols", default=",".join(DEFAULT_SYMBOLS))
    p.add_argument("--start-year", type=int, default=2016)
    p.add_argument("--end-year", type=int, default=2024)
    p.add_argument("--split-year", type=int, default=2020)
    p.add_argument("--sel-horizon", type=int, default=60)
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
        # SUE는 분기 시계열이 필요하므로 시작연도보다 더 과거부터 수집해 워밍업 확보
        evs = build_events_for_stock(dart, sym, close.index, args.start_year - 3, args.end_year)
        attach_sue(evs, lookback=8, min_obs=4)
        all_events.extend(evs)

    event_cars = compute_event_cars(all_events, price_map, market, DEFAULT_HORIZONS)
    # 분석 대상 기간만(워밍업 연도 제외)
    event_cars = [(e, c) for e, c in event_cars if e.avail_date.year >= args.start_year]
    is_pairs = [(e, c) for e, c in event_cars if e.avail_date.year <= args.split_year]
    oos_pairs = [(e, c) for e, c in event_cars if e.avail_date.year > args.split_year]
    h = args.sel_horizon
    n_sue = sum(1 for e, _ in event_cars if e.sue is not None)
    print(f"이벤트: 전체 {len(event_cars)} (SUE有 {n_sue}) | IS {len(is_pairs)} | OOS {len(oos_pairs)}")

    sue_vals = [e.sue for e, _ in event_cars if e.sue is not None]
    if sue_vals:
        s = pd.Series(sue_vals)
        print(f"SUE 분포: 중앙값 {s.median():.2f}, 25~75% {s.quantile(.25):.2f}~{s.quantile(.75):.2f}, max {s.max():.2f}")

    print("\n" + "=" * 64)
    print(f"  [IS {args.start_year}~{args.split_year}] SUE 임계 스윕 (지평선 {h}일)")
    print("-" * 64)
    print(f"  {'SUE 임계':<12} {'n':>4} {'CAAR':>9} {'t값':>7}")
    is_rows = []
    for th in _SUE_THRESHOLDS:
        sig = sue_signal(th)
        st = caar_for_signal(is_pairs, sig, (h,))[h]
        is_rows.append((th, sig, st))
        mark = " *" if st.n >= _MIN_N and abs(st.t_stat) > 2 else ""
        print(f"  SUE ≥{th:>4.1f}    {st.n:>4} {st.caar * 100:>8.2f}% {st.t_stat:>7.2f}{mark}")

    eligible = [r for r in is_rows if r[2].n >= _MIN_N and r[2].caar > 0]
    if not eligible:
        print("\n  IS에서 표본 충분한 양의 SUE 신호 없음 → 알파 근거 약함.")
        print("=" * 64)
        return
    eligible.sort(key=lambda r: abs(r[2].t_stat), reverse=True)
    best_th, best_sig, best_is = eligible[0]
    oos = caar_for_signal(oos_pairs, best_sig, DEFAULT_HORIZONS)

    print("\n" + "=" * 64)
    print(f"  [OOS {args.split_year + 1}~{args.end_year}] IS best SUE≥{best_th} 확인")
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
