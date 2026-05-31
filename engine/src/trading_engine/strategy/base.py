"""Strategy base class and signal definitions."""

from __future__ import annotations

from abc import ABC, abstractmethod
from enum import Enum

from pydantic import BaseModel

from trading_engine.data import Bar


class SignalType(str, Enum):
    BUY = "buy"
    SELL = "sell"
    HOLD = "hold"


class Signal(BaseModel):
    symbol: str
    type: SignalType
    strength: float = 1.0  # 0.0 ~ 1.0
    reason: str = ""


class Strategy(ABC):
    """모든 전략의 베이스. 봉 시퀀스를 받아 시그널을 산출한다."""

    name: str = "base"

    @abstractmethod
    def on_bars(self, bars: list[Bar]) -> Signal:
        """가장 최근 봉까지 누적된 데이터를 보고 시그널을 반환한다."""
        raise NotImplementedError
