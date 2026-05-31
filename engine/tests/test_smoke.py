"""Smoke tests — 스캐폴드가 정상 import/동작하는지 확인."""

from datetime import datetime

from trading_engine import __version__
from trading_engine.backtest import BacktestEngine
from trading_engine.data import Bar
from trading_engine.strategy import Signal, SignalType, Strategy


class _NoopStrategy(Strategy):
    name = "noop"

    def on_bars(self, bars):
        return Signal(symbol="TEST", type=SignalType.HOLD)


def _make_bars(n: int) -> list[Bar]:
    return [
        Bar(
            symbol="TEST",
            timestamp=datetime(2024, 1, 1),
            open=1.0,
            high=1.0,
            low=1.0,
            close=1.0,
            volume=1.0,
        )
        for _ in range(n)
    ]


def test_version():
    assert __version__ == "0.1.0"


def test_backtest_runs():
    engine = BacktestEngine()
    result = engine.run(_NoopStrategy(), "TEST", _make_bars(5))
    assert result.n_bars == 5
    assert result.strategy == "noop"


def test_strategy_signal():
    sig = _NoopStrategy().on_bars(_make_bars(1))
    assert sig.type == SignalType.HOLD
