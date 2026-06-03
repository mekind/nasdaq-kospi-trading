"""Smoke tests — 스캐폴드/엔진이 정상 import·동작하는지 확인."""

import pandas as pd

from trading_engine import __version__
from trading_engine.backtest import BacktestEngine, CostModel, compute_metrics
from trading_engine.strategy import MeanReversionStrategy


def _toy_df(n: int = 30) -> pd.DataFrame:
    idx = pd.date_range("2020-01-01", periods=n, freq="D")
    # 완만한 상승 + 중간에 한 번 급락했다 회복하는 합성 가격
    close = [100.0 + i for i in range(n)]
    close[15] = close[15] - 12  # 급락
    close[16] = close[16] - 6
    return pd.DataFrame(
        {
            "open": close,
            "high": [c + 1 for c in close],
            "low": [c - 1 for c in close],
            "close": close,
            "volume": [1_000.0] * n,
        },
        index=idx,
    )


def test_version():
    assert __version__ == "0.1.0"


def test_end_to_end_runs():
    df = _toy_df()
    strat = MeanReversionStrategy(trend_window=10)  # 합성 데이터라 짧은 추세창 사용
    signals = strat.generate_signals(df)
    assert len(signals) == len(df)
    assert set(signals.unique()) <= {"buy", "sell", "hold"}

    engine = BacktestEngine(initial_cash=10_000_000.0, cost_model=CostModel())
    result = engine.run(df, signals, symbol="TOY", strategy_name=strat.name)
    assert len(result.equity_curve) == len(df)
    assert result.final_equity > 0

    metrics = compute_metrics(result.equity_curve, result.trades, 10_000_000.0)
    assert "total_return" in metrics
    assert "max_drawdown" in metrics
