"""유니버스 백테스트 결과 집계 — 멤버십 마스킹 + 분포 통계.

per-stock 독립 실행 결과(:class:`PerStockResult`)를 받아:
1. **멤버십 마스킹**: 각 종목의 거래 중 "그 종목이 시총 상위 유니버스 멤버였던 시점에 진입한"
   거래만 인정한다(룩어헤드 없는 시점별 멤버십). 지표는 전체 이력으로 계산하되 거래만 거른다.
2. **분포 집계**: 종목별 수익률·승률을 모아 중앙값/사분위, 수익 종목 비율(거래종목 중 / 전체 중 양쪽),
   상폐/생존 분리, buy&hold 벤치마크, 폭락구간(2018/2020/2022) 횡단을 산출한다.

설계 원칙(analyst 반영):
- 종목별 1,000만원 독립이므로 **원화 손익 횡단 합산은 무의미** → 출력하지 않고 수익률(%) 기반.
- 극단 CAGR 오염을 피해 **중앙값/사분위 우선**.
- 매매 미발생(n_trades=0) 종목 때문에 분모가 흔들리므로 **두 분모를 모두** 보고.
- per-stock 독립은 운용수익이 아니라 **전략 일반성 측정**이다.
"""

from __future__ import annotations

from typing import Callable

import numpy as np
import pandas as pd

# 데이터 범위(2014~) 내 스트레스/폭락 구간. entry_date 기준 횡단 집계.
DEFAULT_CRASH_PERIODS: dict[str, tuple[str, str]] = {
    "2018_Q4": ("2018-10-01", "2018-12-31"),
    "2020_COVID": ("2020-02-19", "2020-04-30"),
    "2022_BEAR": ("2022-01-01", "2022-12-31"),
}

CSV_GUARD_HEADER = (
    "# 주의: 종목별 1,000만원 독립 백테스트(동시보유 아님). 원화 손익 합산은 무의미. "
    "이것은 전략 일반성(breadth) 측정이지 운용수익이 아님."
)


def _mask_trades(symbol: str, trades: pd.DataFrame, is_member: Callable[[str, object], bool]) -> pd.DataFrame:
    """entry_date가 멤버십 구간에 든 거래만 남긴다."""
    if trades is None or trades.empty or "entry_date" not in trades.columns:
        return trades.iloc[0:0] if trades is not None else pd.DataFrame()
    mask = trades["entry_date"].apply(lambda d: is_member(symbol, d))
    return trades[mask]


def _per_stock_stats(masked: pd.DataFrame) -> dict:
    """마스킹된 거래로부터 종목 1개 요약(수익률 기반)."""
    n = len(masked)
    if n == 0:
        return {
            "n_trades": 0, "win_rate": np.nan, "mean_return": np.nan,
            "median_return": np.nan, "compound_return": np.nan,
        }
    r = masked["return_pct"].astype(float)
    return {
        "n_trades": n,
        "win_rate": float((r > 0).mean()),
        "mean_return": float(r.mean()),          # 거래당 기대값(%)
        "median_return": float(r.median()),
        "compound_return": float((1.0 + r).prod() - 1.0),  # 멤버십 구간만 순차 복리
    }


def _quartiles(vals: list[float]) -> dict:
    arr = np.array([v for v in vals if v == v], dtype=float)  # NaN 제외
    if len(arr) == 0:
        return {"n": 0, "median": np.nan, "q1": np.nan, "q3": np.nan, "mean": np.nan}
    return {
        "n": int(len(arr)),
        "median": float(np.median(arr)),
        "q1": float(np.percentile(arr, 25)),
        "q3": float(np.percentile(arr, 75)),
        "mean": float(arr.mean()),
    }


def summarize(
    results: list,
    is_member: Callable[[str, object], bool],
    crash_periods: dict[str, tuple[str, str]] | None = None,
    inactive_gap_days: int = 60,
) -> dict:
    """유니버스 결과를 분포로 집계한다.

    Parameters
    ----------
    results: PerStockResult 리스트.
    is_member: ``(symbol, entry_date) -> bool`` 멤버십 판정(룩어헤드 없는 시점별).
    crash_periods: 폭락구간 {라벨: (시작, 끝)}. None이면 기본값.
    inactive_gap_days: 마지막 거래일이 전체 최신일보다 이만큼 이전이면 '상폐/비활성'으로 분류.
    """
    crash_periods = crash_periods or DEFAULT_CRASH_PERIODS
    if not results:
        return {"n_universe": 0, "rows": [], "note": "결과 없음"}

    latest_last = max(r.last_date for r in results)
    inactive_cut = pd.Timestamp(latest_last) - pd.Timedelta(days=inactive_gap_days)

    rows: list[dict] = []
    masked_by_symbol: dict[str, pd.DataFrame] = {}
    for r in results:
        masked = _mask_trades(r.symbol, r.trades, is_member)
        masked_by_symbol[r.symbol] = masked
        stats = _per_stock_stats(masked)
        rows.append({
            "symbol": r.symbol,
            **stats,
            "buy_hold_return": float(r.last_close / r.first_close - 1.0) if r.first_close else np.nan,
            "n_bars": r.n_bars,
            "n_jumps_30": r.n_jumps_30,
            "inactive": bool(pd.Timestamp(r.last_date) < inactive_cut),  # 상폐/거래정지 추정
        })

    traded = [x for x in rows if x["n_trades"] > 0]
    n_all = len(rows)
    n_traded = len(traded)

    # 수익 종목 비율 — 두 분모 (analyst 결정)
    prof_compound = [x for x in traded if x["compound_return"] > 0]
    pct_profit_among_traded = (len(prof_compound) / n_traded) if n_traded else np.nan
    pct_profit_among_all = (len(prof_compound) / n_all) if n_all else np.nan

    # 분포 (중앙값/사분위 우선)
    dist_compound = _quartiles([x["compound_return"] for x in traded])
    dist_expectancy = _quartiles([x["mean_return"] for x in traded])
    dist_winrate = _quartiles([x["win_rate"] for x in traded])
    dist_buyhold = _quartiles([x["buy_hold_return"] for x in rows])

    # 상폐/생존 분리
    survivors = [x for x in traded if not x["inactive"]]
    inactives = [x for x in traded if x["inactive"]]
    split = {
        "survivor": _quartiles([x["compound_return"] for x in survivors]),
        "inactive": _quartiles([x["compound_return"] for x in inactives]),
    }

    # 폭락구간 횡단 (% 기반, 원화 합산 아님)
    crash = {}
    for label, (s, e) in crash_periods.items():
        s_ts, e_ts = pd.Timestamp(s), pd.Timestamp(e)
        rets: list[float] = []
        for sym, m in masked_by_symbol.items():
            if m is None or m.empty:
                continue
            sel = m[(m["entry_date"] >= s_ts) & (m["entry_date"] <= e_ts)]
            rets.extend(sel["return_pct"].astype(float).tolist())
        q = _quartiles(rets)
        q["win_rate"] = float(np.mean([1.0 if x > 0 else 0.0 for x in rets])) if rets else np.nan
        q["n_trades"] = len(rets)
        crash[label] = q

    # 분할/권리락 의심 스캐너
    jump_offenders = sorted(
        [{"symbol": x["symbol"], "n_jumps_30": x["n_jumps_30"]} for x in rows if x["n_jumps_30"] > 0],
        key=lambda d: d["n_jumps_30"], reverse=True,
    )

    return {
        "n_universe": n_all,
        "n_traded": n_traded,
        "n_no_trade": n_all - n_traded,
        "n_inactive": sum(1 for x in rows if x["inactive"]),
        "pct_profit_among_traded": pct_profit_among_traded,
        "pct_profit_among_all": pct_profit_among_all,
        "dist_compound_return": dist_compound,
        "dist_expectancy_per_trade": dist_expectancy,
        "dist_win_rate": dist_winrate,
        "dist_buy_hold": dist_buyhold,
        "survivor_vs_inactive": split,
        "crash": crash,
        "jump_offenders": jump_offenders,
        "rows": rows,
    }


def _pct(x: float) -> str:
    return "n/a" if x != x else f"{x * 100:.1f}%"


def print_report(summary: dict) -> None:
    """집계 결과를 콘솔 요약으로 출력."""
    if summary.get("n_universe", 0) == 0:
        print("(집계할 결과 없음)")
        return
    s = summary
    print("=" * 60)
    print("  코스피 시총 상위 유니버스 — RSI(2) breadth 검증")
    print("  ⚠ 종목별 독립 백테스트(동시보유 아님). 전략 일반성 측정, 운용수익 아님.")
    print("-" * 60)
    print(f"  유니버스 종목   : {s['n_universe']}  (거래발생 {s['n_traded']}, 무거래 {s['n_no_trade']}, 비활성/상폐추정 {s['n_inactive']})")
    print(f"  수익 종목 비율  : 거래종목중 {_pct(s['pct_profit_among_traded'])} / 전체중 {_pct(s['pct_profit_among_all'])}")
    print("-" * 60)
    dc = s["dist_compound_return"]
    print(f"  종목 누적수익(멤버십구간) 분포 (n={dc['n']}):")
    print(f"    중앙값 {_pct(dc['median'])}  Q1 {_pct(dc['q1'])}  Q3 {_pct(dc['q3'])}")
    de = s["dist_expectancy_per_trade"]
    print(f"  거래당 기대값 중앙값 : {_pct(de['median'])}")
    dw = s["dist_win_rate"]
    print(f"  승률 중앙값          : {_pct(dw['median'])}")
    bh = s["dist_buy_hold"]
    print(f"  [벤치마크] 단순보유 수익 중앙값 : {_pct(bh['median'])}  (전략 중앙값 {_pct(dc['median'])}와 비교)")
    print("-" * 60)
    sv = s["survivor_vs_inactive"]
    print(f"  생존 종목 누적 중앙값 : {_pct(sv['survivor']['median'])} (n={sv['survivor']['n']})")
    print(f"  비활성/상폐 누적 중앙값: {_pct(sv['inactive']['median'])} (n={sv['inactive']['n']})")
    print("-" * 60)
    print("  [폭락구간 횡단] (수익률 분포, 원화 합산 아님)")
    for label, c in s["crash"].items():
        print(f"    {label}: {c['n_trades']}거래 중앙수익 {_pct(c['median'])} 승률 {_pct(c.get('win_rate', float('nan')))}")
    print("-" * 60)
    jo = s["jump_offenders"]
    print(f"  분할/권리락 의심(일일 |Δ|>30%) 종목 : {len(jo)}개"
          + (f"  상위: {[d['symbol'] for d in jo[:5]]}" if jo else ""))
    print("=" * 60)


def to_csv(summary: dict, path: str) -> None:
    """종목별 결과를 가드 헤더와 함께 CSV로 저장(원화 손익 컬럼 없음)."""
    rows = summary.get("rows", [])
    df = pd.DataFrame(rows)
    with open(path, "w", encoding="utf-8") as f:
        f.write(CSV_GUARD_HEADER + "\n")
        df.to_csv(f, index=False)
