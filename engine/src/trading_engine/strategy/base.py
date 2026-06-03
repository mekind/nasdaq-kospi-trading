"""Strategy base class and signal definitions."""

from __future__ import annotations

from abc import ABC, abstractmethod
from enum import Enum

import pandas as pd
from pydantic import BaseModel


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
    """모든 전략의 베이스. OHLCV DataFrame을 받아 시그널 Series를 산출한다."""

    name: str = "base"

    @abstractmethod
    def generate_signals(self, df: pd.DataFrame) -> pd.Series:
        """df(OHLCV)를 받아 index 정렬된 시그널 Series를 반환.

        값은 'buy'(진입 의도) / 'sell'(청산 의도) / 'hold' 문자열."""
        raise NotImplementedError
