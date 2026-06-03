"""백테스트 엔진 검증 테스트.

손으로 만든 시그널 + 손계산한 정답으로 산술을 검증한다.
전략 모듈은 사용하지 않고, 시그널을 직접 구성한다.
"""

from __future__ import annotations

import pandas as pd
import pytest

from trading_engine.backtest.costs import CostModel
from trading_engine.backtest.engine import TRADE_COLUMNS, BacktestEngine


def _make_df(opens: list[float], closes: list[float]) -> pd.DataFrame:
    """주어진 시가/종가 배열로 일봉 DataFrame을 만든다 (high/low/volume은 더미)."""
    n = len(opens)
    idx = pd.date_range("2020-01-01", periods=n, freq="D")
    return pd.DataFrame(
        {
            "open": opens,
            "high": [max(o, c) for o, c in zip(opens, closes)],
            "low": [min(o, c) for o, c in zip(opens, closes)],
            "close": closes,
            "volume": [1_000.0] * n,
        },
        index=idx,
    )


def test_no_cost_known_answer() -> None:
    """비용 0 — 손계산한 final_equity와 거래 pnl을 검증."""
    # 5일 봉. buy@day0(→ open[day1] 체결), sell@day2(→ open[day3] 체결).
    opens = [90.0, 100.0, 110.0, 120.0, 130.0]
    closes = [95.0, 105.0, 115.0, 125.0, 135.0]
    df = _make_df(opens, closes)
    signals = pd.Series(
        ["buy", "hold", "sell", "hold", "hold"], index=df.index
    )

    cost = CostModel(commission_rate=0.0, slippage_bps=0.0, sell_tax_rate=0.0)
    engine = BacktestEngine(initial_cash=1_000_000.0, cost_model=cost)
    result = engine.run(df, signals, symbol="TEST", strategy_name="manual")

    # 매수: open[day1]=100, qty=1_000_000/100=10_000, entry_notional=1_000_000.
    # 매도: open[day3]=120, exit_notional=10_000*120=1_200_000.
    # pnl = 1_200_000 - 1_000_000 = 200_000, return_pct = 0.20.
    assert len(result.trades) == 1
    trade = result.trades.iloc[0]
    assert trade["entry_price"] == pytest.approx(100.0)
    assert trade["exit_price"] == pytest.approx(120.0)
    assert trade["qty"] == pytest.approx(10_000.0)
    assert trade["pnl"] == pytest.approx(200_000.0)
    assert trade["return_pct"] == pytest.approx(0.20)
    # hold_days = day3 - day1 = 2일.
    assert trade["hold_days"] == 2

    # 매도 후 현금화 → 마지막 평가금 = 1_200_000.
    assert result.final_equity == pytest.approx(1_200_000.0)
    assert result.equity_curve.iloc[-1] == pytest.approx(1_200_000.0)
    assert len(result.equity_curve) == len(df)


def test_with_cost_lowers_pnl() -> None:
    """비용 적용 시 pnl이 무비용 대비 낮아지고, 그 차이가 예상 수수료/슬리피지 규모."""
    opens = [90.0, 100.0, 110.0, 120.0, 130.0]
    closes = [95.0, 105.0, 115.0, 125.0, 135.0]
    df = _make_df(opens, closes)
    signals = pd.Series(
        ["buy", "hold", "sell", "hold", "hold"], index=df.index
    )

    no_cost = CostModel(commission_rate=0.0, slippage_bps=0.0, sell_tax_rate=0.0)
    base = BacktestEngine(initial_cash=1_000_000.0, cost_model=no_cost).run(
        df, signals
    )
    base_pnl = base.trades.iloc[0]["pnl"]

    commission_rate = 0.001  # 0.1% 편도
    slippage_bps = 10.0      # 10bp
    cost = CostModel(
        commission_rate=commission_rate,
        slippage_bps=slippage_bps,
        sell_tax_rate=0.0,
    )
    res = BacktestEngine(initial_cash=1_000_000.0, cost_model=cost).run(df, signals)

    assert len(res.trades) == 1
    cost_pnl = res.trades.iloc[0]["pnl"]

    # 방향: 비용 적용 pnl < 무비용 pnl.
    assert cost_pnl < base_pnl

    # 매수 체결가 = 100 * (1 + 10/10000) = 100.10 → qty = 1_000_000/100.10.
    buy_price = 100.0 * (1 + slippage_bps / 10_000)
    qty = 1_000_000.0 / buy_price
    entry_notional = qty * buy_price  # = 1_000_000
    entry_fee = entry_notional * commission_rate
    # 매도 체결가 = 120 * (1 - 10/10000) = 119.88.
    sell_price = 120.0 * (1 - slippage_bps / 10_000)
    exit_notional = qty * sell_price
    exit_fee = exit_notional * commission_rate
    expected_pnl = (exit_notional - exit_fee) - (entry_notional + entry_fee)

    assert cost_pnl == pytest.approx(expected_pnl)

    # 슬리피지/수수료로 인한 손실 규모가 base 대비 충분히 큰지(근사) 확인.
    assert (base_pnl - cost_pnl) == pytest.approx(base_pnl - expected_pnl)
    assert (base_pnl - cost_pnl) > 0


def test_no_lookahead_on_last_bar() -> None:
    """마지막 봉의 buy 시그널은 체결할 다음 봉이 없으므로 거래가 발생하지 않는다."""
    opens = [90.0, 100.0, 110.0]
    closes = [95.0, 105.0, 115.0]
    df = _make_df(opens, closes)
    # 마지막 봉에서만 buy.
    signals = pd.Series(["hold", "hold", "buy"], index=df.index)

    cost = CostModel(commission_rate=0.0, slippage_bps=0.0, sell_tax_rate=0.0)
    res = BacktestEngine(initial_cash=1_000_000.0, cost_model=cost).run(df, signals)

    assert res.trades.empty
    assert list(res.trades.columns) == TRADE_COLUMNS
    # 포지션을 잡지 못했으므로 자산은 초기 현금 그대로 유지.
    assert res.final_equity == pytest.approx(1_000_000.0)


def test_force_close_at_end() -> None:
    """매도 시그널이 없으면 마지막 봉 종가로 강제 청산되고 거래 1건이 기록된다."""
    opens = [90.0, 100.0, 110.0, 120.0]
    closes = [95.0, 105.0, 115.0, 125.0]
    df = _make_df(opens, closes)
    # buy@day0(→ open[day1] 체결), 이후 매도 없음.
    signals = pd.Series(["buy", "hold", "hold", "hold"], index=df.index)

    cost = CostModel(commission_rate=0.0, slippage_bps=0.0, sell_tax_rate=0.0)
    res = BacktestEngine(initial_cash=1_000_000.0, cost_model=cost).run(df, signals)

    assert len(res.trades) == 1
    trade = res.trades.iloc[0]
    # 매수: open[day1]=100, qty=10_000.
    assert trade["entry_price"] == pytest.approx(100.0)
    assert trade["qty"] == pytest.approx(10_000.0)
    # 강제 청산: 마지막 봉 종가 close[day3]=125.
    assert trade["exit_price"] == pytest.approx(125.0)
    assert pd.Timestamp(trade["exit_date"]) == df.index[-1]
    # pnl = 10_000*125 - 1_000_000 = 250_000.
    assert trade["pnl"] == pytest.approx(250_000.0)
    assert res.final_equity == pytest.approx(1_250_000.0)
