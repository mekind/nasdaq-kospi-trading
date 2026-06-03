"""멀티심볼 러너 run_universe 의 스킵 사유 카운트·예외 격리·상태 분기 단위 테스트.

가짜 provider를 주입해 네트워크 없이 검증한다. 전략·엔진은 순수하므로 실제 인스턴스를 쓴다.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from trading_engine.backtest.costs import CostModel
from trading_engine.backtest.engine import BacktestEngine
from trading_engine.backtest.run_universe import _count_jumps, run_one, run_universe
from trading_engine.strategy.mean_reversion import MeanReversionStrategy


def _ohlcv(n: int) -> pd.DataFrame:
    idx = pd.date_range("2015-01-01", periods=n, freq="B")
    close = pd.Series(100.0 + np.sin(np.arange(n) / 5.0) * 5.0, index=idx)
    return pd.DataFrame(
        {
            "open": close.values,
            "high": close.values + 1,
            "low": close.values - 1,
            "close": close.values,
            "volume": 1000.0,
        },
        index=idx,
    )


class FakeProvider:
    """symbol -> 거동('ok'|'short'|'empty'|'raise'|'network') 매핑 가짜 로더."""

    def __init__(self, behaviors: dict[str, str]) -> None:
        self.behaviors = behaviors

    def load_daily(self, symbol, start=None, end=None, use_cache=True):
        b = self.behaviors[symbol]
        if b == "raise":
            raise ValueError("boom")
        if b == "network":
            raise ConnectionError("connection reset by peer")
        if b == "empty":
            return _ohlcv(0)
        if b == "short":
            return _ohlcv(100)  # < min_bars 250
        return _ohlcv(300)


def _engine_bits():
    return (
        MeanReversionStrategy(),
        BacktestEngine(initial_cash=10_000_000.0, cost_model=CostModel(sell_tax_rate=0.0018)),
    )


def test_run_one_statuses():
    strat, engine = _engine_bits()
    p = FakeProvider({"OK": "ok", "SH": "short", "EM": "empty"})
    assert run_one("OK", p, strat, engine, None, None, min_bars=250)[0] == "ok"
    assert run_one("SH", p, strat, engine, None, None, min_bars=250)[0] == "short"
    assert run_one("EM", p, strat, engine, None, None, min_bars=250)[0] == "empty"


def test_run_universe_counts_skips_by_reason():
    strat, engine = _engine_bits()
    behaviors = {
        "A": "ok", "B": "ok",
        "C": "short", "D": "empty",
        "E": "raise", "F": "network",
    }
    results, skips = run_universe(
        list(behaviors), FakeProvider(behaviors), strat, engine, min_bars=250
    )
    assert len(results) == 2                      # A, B
    assert skips.get("short") == 1
    assert skips.get("empty") == 1
    assert skips.get("exception") == 1            # ValueError
    assert skips.get("network") == 1              # ConnectionError
    # 성공 + 스킵 = 전체
    assert len(results) + sum(skips.values()) == len(behaviors)


def test_one_failure_does_not_stop_others():
    strat, engine = _engine_bits()
    behaviors = {"X": "raise", "Y": "ok", "Z": "network"}
    results, skips = run_universe(
        list(behaviors), FakeProvider(behaviors), strat, engine, min_bars=250
    )
    assert [r.symbol for r in results] == ["Y"]   # 가운데 실패해도 Y는 처리됨


def test_count_jumps():
    close = pd.Series([100.0, 101.0, 60.0, 61.0, 200.0])  # -40%, +228% 점프 2회
    assert _count_jumps(close, threshold=0.30) == 2


def test_perstock_result_fields():
    strat, engine = _engine_bits()
    status, rec = run_one("OK", FakeProvider({"OK": "ok"}), strat, engine, None, None, 250)
    assert status == "ok"
    assert rec.symbol == "OK"
    assert rec.n_bars == 300
    assert rec.first_close > 0 and rec.last_close > 0
    assert isinstance(rec.trades, pd.DataFrame)
