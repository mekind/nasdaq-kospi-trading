"""모드 A 신호 스윕 — In-Sample 탐색 → Out-of-Sample 1회 확인 (p-해킹 차단).

EPS 단독 신호로는 알파가 안 보였으므로(2026-06-03 모드 A), 매출·순이익·EPS YoY를
결합/임계 스윕한다. **다만 과적합을 막기 위해**:
1. 이벤트를 접수연도로 IS(예: 2016~2020) / OOS(2021~2024) 분할
2. IS에서만 신호 그리드를 탐색해 best 선정
3. 그 best를 OOS에 **단 한 번** 적용 — OOS 수치만 신뢰
4. IS에서 |t|>2가 몇 개 나왔는지 함께 보고(다중검정 맥락)

사용 예:
    python -m trading_engine.backtest.run_earnings_sweep --split-year 2020 --sel-horizon 10
"""

from __future__ import annotations

import argparse

import pandas as pd

from trading_engine.backtest.event_study import (
    DEFAULT_HORIZONS,
    caar_for_signal,
    composite_yoy_signal,
    compute_event_cars,
)
from trading_engine.backtest.run_earnings import DEFAULT_SYMBOLS, build_events_for_stock
from trading_engine.data import DartProvider, EarningsEvent, FdrProvider

# 사전 정의 그리드 (탐색 자유도를 의도적으로 제한 — 과적합 방지)
_COMBOS = [
    (("eps",), "all"),
    (("net_income",), "all"),
    (("revenue",), "all"),
    (("eps", "net_income"), "all"),
    (("eps", "revenue"), "all"),
    (("net_income", "revenue"), "all"),
    (("eps", "net_income", "revenue"), "all"),
    (("eps", "net_income", "revenue"), "any"),
]
_THRESHOLDS = (0.0, 0.10, 0.20, 0.30, 0.50)
_MIN_N = 20  # IS 최소 표본


def _grid():
    """(label, signal_fn, specs, mode, threshold) 그리드 생성."""
    for fields, mode in _COMBOS:
        for th in _THRESHOLDS:
            specs = tuple((f, th) for f in fields)
            label = f"{'&' if mode == 'all' else '|'}".join(fields) + f" ≥{th:.0%}"
            yield label, composite_yoy_signal(specs, mode)


def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="PEAD 신호 스윕 (IS→OOS)")
    p.add_argument("--symbols", default=",".join(DEFAULT_SYMBOLS))
    p.add_argument("--start-year", type=int, default=2016)
    p.add_argument("--end-year", type=int, default=2024)
    p.add_argument("--split-year", type=int, default=2020, help="이 연도까지 IS, 이후 OOS")
    p.add_argument("--sel-horizon", type=int, default=10, help="IS best 선정 기준 지평선(일)")
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
        all_events.extend(
            build_events_for_stock(dart, sym, close.index, args.start_year, args.end_year)
        )

    # 이벤트별 CAR 1회 계산 후 IS/OOS 분할
    event_cars = compute_event_cars(all_events, price_map, market, DEFAULT_HORIZONS)
    is_pairs = [(ev, c) for ev, c in event_cars if ev.avail_date.year <= args.split_year]
    oos_pairs = [(ev, c) for ev, c in event_cars if ev.avail_date.year > args.split_year]
    print(f"이벤트: 전체 {len(event_cars)} | IS(~{args.split_year}) {len(is_pairs)} | OOS {len(oos_pairs)}")
    h = args.sel_horizon

    # 1) IS 그리드 탐색
    rows = []
    for label, sig in _grid():
        st = caar_for_signal(is_pairs, sig, (h,))[h]
        rows.append((label, sig, st))
    rows.sort(key=lambda r: abs(r[2].t_stat), reverse=True)

    n_signif = sum(1 for _, _, st in rows if st.n >= _MIN_N and abs(st.t_stat) > 2)
    print("\n" + "=" * 64)
    print(f"  [IS {args.start_year}~{args.split_year}] 신호 그리드 (지평선 {h}일 기준 정렬)")
    print("-" * 64)
    print(f"  {'신호':<28} {'n':>4} {'CAAR':>9} {'t값':>7}")
    for label, _, st in rows:
        mark = " *" if st.n >= _MIN_N and abs(st.t_stat) > 2 else ""
        print(f"  {label:<28} {st.n:>4} {st.caar * 100:>8.2f}% {st.t_stat:>7.2f}{mark}")
    print("-" * 64)
    print(f"  IS에서 |t|>2 & n≥{_MIN_N} 신호 수: {n_signif} / {len(rows)}")
    print(f"  (다중검정: {len(rows)}개 시험 → 우연히 |t|>2 ~{len(rows) * 0.05:.1f}개 기대. 과신 금지)")

    # 2) IS best(표본 충분 & 양의 CAAR 중 |t| 최대) → OOS 1회 확인
    eligible = [r for r in rows if r[2].n >= _MIN_N and r[2].caar > 0]
    if not eligible:
        print("\n  IS에서 표본 충분한 양의 신호 없음 → OOS 확인 생략. 알파 근거 약함.")
        print("=" * 64)
        return
    best_label, best_sig, best_is = eligible[0]
    oos = caar_for_signal(oos_pairs, best_sig, DEFAULT_HORIZONS)
    print("\n" + "=" * 64)
    print(f"  [OOS {args.split_year + 1}~{args.end_year}] IS best 신호 '{best_label}' 확인")
    print(f"    (IS {h}일: CAAR {best_is.caar * 100:.2f}%, t {best_is.t_stat:.2f}, n {best_is.n})")
    print("-" * 64)
    print(f"  {'지평선(일)':>10} {'n':>5} {'CAAR':>10} {'t값':>8}")
    for hz in DEFAULT_HORIZONS:
        s = oos[hz]
        print(f"  {hz:>10} {s.n:>5} {s.caar * 100:>9.2f}% {s.t_stat:>8.2f}")
    print("=" * 64)
    print("  판정: OOS에서 CAAR>0 & |t|>2 & 비용(왕복≈0.21%+슬리피지) 차감 후 양수여야")
    print("        모드 B 진행 가치. IS만 좋고 OOS 무너지면 과적합 = 알파 아님.")


if __name__ == "__main__":
    main()
