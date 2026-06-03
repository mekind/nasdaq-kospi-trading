"""평균회귀(Mean Reversion) 전략 — RSI(2) 기반.

추세 필터(장기 SMA 위) 하에서 단기 과매도(RSI) 진입,
RSI 회복 또는 시간 손절(time-stop)로 청산하는 단일 롱 포지션 전략.
"""

from __future__ import annotations

import pandas as pd

from trading_engine.indicators import rsi, sma

from .base import Strategy


class MeanReversionStrategy(Strategy):
    """RSI(2) 평균회귀 전략 (단일 롱 포지션, 상태 기반 루프)."""

    name = "mean_reversion_rsi2"

    def __init__(
        self,
        rsi_period: int = 2,
        rsi_entry: float = 10.0,
        rsi_exit: float = 70.0,
        trend_window: int = 200,
        max_hold_days: int = 5,
    ) -> None:
        self.rsi_period = rsi_period
        self.rsi_entry = rsi_entry
        self.rsi_exit = rsi_exit
        self.trend_window = trend_window
        self.max_hold_days = max_hold_days

    def generate_signals(self, df: pd.DataFrame) -> pd.Series:
        """OHLCV df로부터 'buy'/'sell'/'hold' 시그널 Series를 생성한다."""
        close = df["close"]
        r = rsi(close, self.rsi_period)
        ma = sma(close, self.trend_window)

        signals: list[str] = []
        in_position = False
        days_held = 0

        for idx in df.index:
            r_i = r.loc[idx]
            ma_i = ma.loc[idx]
            close_i = close.loc[idx]

            if not in_position:
                # 진입: RSI 과매도 + 추세 필터(종가 > 장기 MA)
                if (
                    pd.notna(r_i)
                    and pd.notna(ma_i)
                    and r_i < self.rsi_entry
                    and close_i > ma_i
                ):
                    signals.append("buy")
                    in_position = True
                    days_held = 0
                else:
                    signals.append("hold")
            else:
                # 청산: RSI 회복 또는 시간 손절
                days_held += 1
                if (pd.notna(r_i) and r_i > self.rsi_exit) or (
                    days_held >= self.max_hold_days
                ):
                    signals.append("sell")
                    in_position = False
                else:
                    signals.append("hold")

        return pd.Series(signals, index=df.index, dtype=object)
