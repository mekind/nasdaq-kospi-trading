"""Market data provider interface.

실제 구현(KIS / Alpaca / yfinance)은 이 추상 인터페이스를 따른다.
현재는 스캐폴드 단계로 인터페이스와 데이터 모델만 정의한다.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import datetime

from pydantic import BaseModel


class Bar(BaseModel):
    """OHLCV 봉 하나."""

    symbol: str
    timestamp: datetime
    open: float
    high: float
    low: float
    close: float
    volume: float


class MarketDataProvider(ABC):
    """시세 데이터 소스 추상화."""

    @abstractmethod
    def get_history(
        self,
        symbol: str,
        start: datetime,
        end: datetime,
        interval: str = "1d",
    ) -> list[Bar]:
        """기간별 과거 시세를 조회한다."""
        raise NotImplementedError

    @abstractmethod
    def get_latest(self, symbol: str) -> Bar:
        """최신 시세 한 건을 조회한다."""
        raise NotImplementedError
