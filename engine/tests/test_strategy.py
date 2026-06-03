"""MeanReversionStrategy 시그널 생성 테스트.

작은 합성 시계열과 짧은 trend_window를 사용해 200봉 없이 검증한다.
지표(RSI(2), SMA) 수치는 실제 indicators 모듈로 사전 계산해 확인하였다.
"""

from __future__ import annotations

import pandas as pd

from trading_engine.strategy import (
    MeanReversionStrategy,
    Signal,
    SignalType,
    Strategy,
)


def _make_df(prices: list[float]) -> pd.DataFrame:
    """가격 리스트로 DatetimeIndex OHLCV DataFrame 생성 (close 기준)."""
    idx = pd.date_range("2024-01-01", periods=len(prices), freq="D")
    return pd.DataFrame(
        {
            "open": prices,
            "high": prices,
            "low": prices,
            "close": prices,
            "volume": [1.0] * len(prices),
        },
        index=idx,
    )


def test_strategy_exports_and_contract():
    """공개 API 및 기본 파라미터 계약 검증."""
    assert issubclass(MeanReversionStrategy, Strategy)
    strat = MeanReversionStrategy()
    assert strat.name == "mean_reversion_rsi2"
    assert strat.rsi_period == 2
    assert strat.rsi_entry == 10.0
    assert strat.rsi_exit == 70.0
    assert strat.trend_window == 200
    assert strat.max_hold_days == 5
    # Signal / SignalType 도 strategy 패키지에서 export 되어야 한다.
    assert SignalType.BUY == "buy"
    sig = Signal(symbol="TEST", type=SignalType.BUY)
    assert sig.strength == 1.0


def test_buy_then_sell_on_oversold_above_ma():
    """추세(장기 MA) 위에서 과매도로 진입(buy) 후 RSI 회복으로 청산(sell)."""
    # 완만한 상승추세로 MA(10)를 충분히 아래로 lag 시킨 뒤,
    # 얕은 풀백으로 RSI(2)를 entry(30) 아래로 떨어뜨리되 종가는 MA 위를 유지.
    # idx14에서 buy, idx16의 급등(RSI≈94 > exit 70)에서 sell.
    prices = [
        100, 102, 104, 106, 108, 110, 112, 114, 116, 118, 120, 122, 124,
        121, 120, 120, 130, 145,
    ]
    df = _make_df(prices)
    strat = MeanReversionStrategy(
        trend_window=10, rsi_period=2, rsi_entry=30.0, rsi_exit=70.0, max_hold_days=5
    )
    sig = strat.generate_signals(df)

    assert list(sig.index) == list(df.index)
    assert sig.dtype == object

    sig_list = list(sig)
    assert "buy" in sig_list, "추세 위 과매도에서 buy 가 발생해야 한다"
    buy_idx = sig_list.index("buy")
    assert "sell" in sig_list[buy_idx + 1:], "buy 이후 sell 이 발생해야 한다"

    # 구체적 위치도 고정 (실제 지표값 기반 사전 계산).
    assert buy_idx == 14
    assert sig_list[16] == "sell"


def test_downtrend_blocks_buy_via_regime_filter():
    """하락추세에서는 종가가 MA 아래라 과매도여도 buy 가 차단되어야 한다."""
    # 단조 하락: RSI(2)=0 으로 과매도지만 close < MA 이므로 진입 불가.
    prices = [120, 118, 116, 114, 112, 110, 108, 106, 104, 102, 100, 98, 96, 94, 92]
    df = _make_df(prices)
    strat = MeanReversionStrategy(
        trend_window=10, rsi_period=2, rsi_entry=35.0, rsi_exit=70.0, max_hold_days=5
    )
    sig = strat.generate_signals(df)

    assert "buy" not in list(sig), "레짐 필터가 하락추세 진입을 막아야 한다"


def test_time_stop_exits_at_max_hold_days():
    """진입 후 RSI 청산이 발생하지 않는 횡보에서 max_hold_days 도달 시 sell."""
    # idx14 buy 이후 가격이 횡보하여 RSI 가 exit(70)을 넘지 않음.
    # days_held: idx15=1, idx16=2, idx17=3, idx18=4 -> max_hold_days=4 에서 sell.
    prices = [
        100, 102, 104, 106, 108, 110, 112, 114, 116, 118, 120, 122, 124,
        121, 120, 120, 120.2, 120.1, 120.3, 120.2, 120.4, 120.3,
    ]
    df = _make_df(prices)
    max_hold = 4
    strat = MeanReversionStrategy(
        trend_window=10,
        rsi_period=2,
        rsi_entry=30.0,
        rsi_exit=70.0,
        max_hold_days=max_hold,
    )
    sig = strat.generate_signals(df)
    sig_list = list(sig)

    assert "buy" in sig_list
    buy_idx = sig_list.index("buy")
    assert buy_idx == 14

    # sell 은 정확히 days_held == max_hold_days 인 봉에서 발생해야 한다.
    expected_sell_idx = buy_idx + max_hold
    assert sig_list[expected_sell_idx] == "sell"
    # 그 사이 봉은 모두 hold (조기 청산 없음).
    for i in range(buy_idx + 1, expected_sell_idx):
        assert sig_list[i] == "hold"
