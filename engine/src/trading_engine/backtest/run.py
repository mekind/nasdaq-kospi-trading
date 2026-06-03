"""일봉 평균회귀 백테스트 실행 CLI.

provider → strategy → engine → metrics 를 연결하는 오케스트레이터.

사용 예:
    python -m trading_engine.backtest.run --symbol 069500 --start 2002-01-01
"""

from __future__ import annotations

import argparse
import os

from trading_engine.backtest import (
    BacktestEngine,
    CostModel,
    compute_metrics,
    crash_period_analysis,
)
from trading_engine.data import FdrProvider
from trading_engine.strategy import MeanReversionStrategy


def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="일봉 평균회귀 백테스트")
    p.add_argument("--symbol", default="069500", help="종목 코드 (기본: KODEX 200)")
    p.add_argument("--start", default=None, help="시작일 YYYY-MM-DD")
    p.add_argument("--end", default=None, help="종료일 YYYY-MM-DD")
    p.add_argument("--cash", type=float, default=10_000_000.0, help="초기 자본")
    # 전략 파라미터
    p.add_argument("--rsi-period", type=int, default=2)
    p.add_argument("--rsi-entry", type=float, default=10.0)
    p.add_argument("--rsi-exit", type=float, default=70.0)
    p.add_argument("--trend-window", type=int, default=200)
    p.add_argument("--max-hold", type=int, default=5)
    # 비용
    p.add_argument("--commission", type=float, default=0.00015)
    p.add_argument("--slippage-bps", type=float, default=5.0)
    p.add_argument("--sell-tax", type=float, default=0.0, help="ETF는 0, 개별주 약 0.0018")
    p.add_argument("--outdir", default="output")
    return p.parse_args()


def _fmt_pct(x: float) -> str:
    return f"{x * 100:.2f}%"


def main() -> None:
    args = _parse_args()

    print(f"[1/4] 데이터 로드: {args.symbol} ({args.start or '상장후'} ~ {args.end or '최근'})")
    provider = FdrProvider()
    df = provider.load_daily(args.symbol, args.start, args.end)
    print(f"      {len(df)} 봉, {df.index[0].date()} ~ {df.index[-1].date()}")

    print("[2/4] 시그널 생성")
    strat = MeanReversionStrategy(
        rsi_period=args.rsi_period,
        rsi_entry=args.rsi_entry,
        rsi_exit=args.rsi_exit,
        trend_window=args.trend_window,
        max_hold_days=args.max_hold,
    )
    signals = strat.generate_signals(df)
    n_buy = int((signals == "buy").sum())
    print(f"      진입 신호 {n_buy}회")

    print("[3/4] 백테스트 실행")
    cost = CostModel(
        commission_rate=args.commission,
        slippage_bps=args.slippage_bps,
        sell_tax_rate=args.sell_tax,
    )
    engine = BacktestEngine(initial_cash=args.cash, cost_model=cost)
    result = engine.run(df, signals, symbol=args.symbol, strategy_name=strat.name)

    print("[4/4] 성과 분석\n")
    m = compute_metrics(result.equity_curve, result.trades, args.cash)
    crash = crash_period_analysis(result.trades)

    print("=" * 48)
    print(f"  전략         : {result.strategy}")
    print(f"  종목         : {result.symbol}")
    print(f"  기간         : {df.index[0].date()} ~ {df.index[-1].date()} ({len(df)} 봉)")
    print(f"  초기자본     : {args.cash:,.0f}")
    print(f"  최종자본     : {result.final_equity:,.0f}")
    print("-" * 48)
    print(f"  총수익률     : {_fmt_pct(m['total_return'])}")
    print(f"  CAGR         : {_fmt_pct(m['cagr'])}")
    print(f"  MDD          : {_fmt_pct(m['max_drawdown'])}")
    print(f"  샤프         : {m['sharpe']:.2f}")
    print("-" * 48)
    print(f"  거래 횟수    : {m['n_trades']}")
    print(f"  승률         : {_fmt_pct(m['win_rate'])}")
    print(f"  평균이익     : {m['avg_win']:,.0f}")
    print(f"  평균손실     : {m['avg_loss']:,.0f}")
    print(f"  손익비       : {m['payoff_ratio']:.2f}")
    print(f"  기대값/거래  : {m['expectancy']:,.0f}")
    print("-" * 48)
    print("  [폭락 구간 분석] (꼬리 위험 점검)")
    for label, info in crash.items():
        print(
            f"    {label}: {info['n_trades']}거래 "
            f"손익 {info['total_pnl']:,.0f} 승률 {_fmt_pct(info['win_rate'])}"
        )
    print("=" * 48)

    os.makedirs(args.outdir, exist_ok=True)
    eq_path = os.path.join(args.outdir, f"equity_curve_{args.symbol}.csv")
    tr_path = os.path.join(args.outdir, f"trades_{args.symbol}.csv")
    result.equity_curve.to_csv(eq_path, header=["equity"])
    result.trades.to_csv(tr_path, index=False)
    print(f"\n저장: {eq_path}, {tr_path}")


if __name__ == "__main__":
    main()
