"""Faber 자산군 추세추종 백테스트 러너 (미국 ETF, FDR 수정주가).

데이터(수정주가 패널) → 월별 10개월 SMA 신호 → 목표비중 → PortfolioBacktestEngine →
성과지표 + 벤치마크(동일비중 buy&hold / SPY 단독) 대비 표.

사용:
    python -m trading_engine.backtest.run_trend_following --start 2008-01-01
"""

from __future__ import annotations

import argparse
import math
import os

import pandas as pd

from trading_engine.backtest.costs import CostModel
from trading_engine.backtest.metrics import compute_metrics
from trading_engine.backtest.portfolio_engine import PortfolioBacktestEngine
from trading_engine.data.adjusted_prices import load_adjusted_panel
from trading_engine.strategy.trend_following import AssetClassTrendFollowing

DEFAULT_ASSETS = ["SPY", "EFA", "BND", "VNQ", "GSG"]
_EMPTY_TRADES = pd.DataFrame(
    columns=["pnl", "return_pct"]
)  # compute_metrics의 거래지표는 미사용(포트폴리오).


def equity_stats(equity: pd.Series, initial_cash: float) -> dict:
    """자산곡선에서 CAGR·연변동성·Sharpe·MDD·총수익을 계산한다."""
    m = compute_metrics(equity, _EMPTY_TRADES, initial_cash, periods_per_year=252)
    daily = equity.pct_change().dropna()
    vol = float(daily.std() * math.sqrt(252)) if len(daily) > 1 else 0.0
    return {
        "total_return": m["total_return"],
        "cagr": m["cagr"],
        "vol": vol,
        "sharpe": m["sharpe"],
        "mdd": m["max_drawdown"],
    }


def _constant_weights(
    month_ends: pd.DatetimeIndex, weights: dict[str, float]
) -> dict[pd.Timestamp, dict[str, float]]:
    """모든 월말에 동일한 목표비중을 주는 스케줄(동일비중 buy&hold 벤치마크용)."""
    return {ts: dict(weights) for ts in month_ends}


def _buy_and_hold_once(
    month_ends: pd.DatetimeIndex, weights: dict[str, float]
) -> dict[pd.Timestamp, dict[str, float]]:
    """첫 월말에만 비중을 잡고 이후 보유(SPY 단독 buy&hold 벤치마크용)."""
    return {month_ends[0]: dict(weights)}


def run(
    assets: list[str],
    start: str | None,
    end: str | None,
    sma_months: int,
    cash: float,
    cost: CostModel,
    use_cache: bool = True,
) -> dict:
    """전략·벤치마크를 모두 실행하고 결과 dict를 반환한다."""
    opens, closes = load_adjusted_panel(assets, start, end, use_cache=use_cache)
    if len(opens) == 0:
        raise RuntimeError("데이터 없음 — 심볼/기간 확인")

    strat = AssetClassTrendFollowing(assets, sma_months=sma_months)
    weights = strat.generate_weights(closes)
    month_ends = pd.DatetimeIndex(list(weights.keys()))

    engine = PortfolioBacktestEngine(initial_cash=cash, cost_model=cost)

    # 전략
    strat_res = engine.run(opens, closes, weights)
    # 벤치마크 1: 동일비중 buy&hold (월 리밸런싱, 추세필터 OFF)
    ew = {a: 1.0 / len(assets) for a in assets}
    ew_res = engine.run(opens, closes, _constant_weights(month_ends, ew))
    # 벤치마크 2: SPY 단독 buy&hold
    spy_res = engine.run(opens, closes, _buy_and_hold_once(month_ends, {"SPY": 1.0}))

    return {
        "period": (opens.index[0], opens.index[-1]),
        "n_days": len(opens),
        "n_rebalances": len(strat_res.rebalance_log),
        "avg_turnover": float(strat_res.rebalance_log["turnover"].mean())
        if len(strat_res.rebalance_log)
        else 0.0,
        "total_cost": float(strat_res.rebalance_log["cost"].sum())
        if len(strat_res.rebalance_log)
        else 0.0,
        "strategy": equity_stats(strat_res.equity_curve, cash),
        "equal_weight_bh": equity_stats(ew_res.equity_curve, cash),
        "spy_bh": equity_stats(spy_res.equity_curve, cash),
        "equity_curves": {
            "strategy": strat_res.equity_curve,
            "equal_weight_bh": ew_res.equity_curve,
            "spy_bh": spy_res.equity_curve,
        },
    }


def _fmt_pct(x: float) -> str:
    return f"{x * 100:+.2f}%"


def print_report(res: dict) -> None:
    """결과를 콘솔 표로 출력한다."""
    p0, p1 = res["period"]
    print("\n=== Faber 자산군 추세추종 백테스트 ===")
    print(f"기간: {p0.date()} ~ {p1.date()} ({res['n_days']} 거래일)")
    print(
        f"리밸런싱: {res['n_rebalances']}회 · 평균 회전율 {res['avg_turnover'] * 100:.1f}%"
        f" · 누적 비용 {res['total_cost']:,.0f}"
    )
    print("\n지표             전략(추세)   동일비중B&H   SPY단독B&H")
    rows = [
        ("총수익", "total_return"),
        ("CAGR", "cagr"),
        ("변동성", "vol"),
        ("Sharpe", "sharpe"),
        ("MDD", "mdd"),
    ]
    s, e, p = res["strategy"], res["equal_weight_bh"], res["spy_bh"]
    for label, key in rows:
        if key == "sharpe":
            print(f"{label:12s} {s[key]:>11.2f} {e[key]:>12.2f} {p[key]:>12.2f}")
        else:
            print(
                f"{label:12s} {_fmt_pct(s[key]):>11s} {_fmt_pct(e[key]):>12s}"
                f" {_fmt_pct(p[key]):>12s}"
            )


def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Faber 자산군 추세추종 백테스트")
    p.add_argument("--assets", nargs="+", default=DEFAULT_ASSETS)
    p.add_argument("--start", default="2008-01-01")
    p.add_argument("--end", default=None)
    p.add_argument("--sma-months", type=int, default=10)
    p.add_argument("--cash", type=float, default=10_000_000.0)
    p.add_argument("--commission", type=float, default=0.00015)
    p.add_argument("--slippage-bps", type=float, default=5.0)
    p.add_argument("--no-cache", action="store_true")
    p.add_argument("--outdir", default="output")
    return p.parse_args()


def main() -> None:
    args = _parse_args()
    cost = CostModel(
        commission_rate=args.commission,
        slippage_bps=args.slippage_bps,
        sell_tax_rate=0.0,  # ETF는 매도세 없음
    )
    res = run(
        args.assets,
        args.start,
        args.end,
        args.sma_months,
        args.cash,
        cost,
        use_cache=not args.no_cache,
    )
    print_report(res)

    os.makedirs(args.outdir, exist_ok=True)
    curves = pd.DataFrame(res["equity_curves"])
    out = os.path.join(args.outdir, "trend_following_equity.csv")
    curves.to_csv(out)
    print(f"\n저장: {out}")


if __name__ == "__main__":
    main()
