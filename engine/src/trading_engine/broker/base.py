"""Broker interface and order/position models."""

from __future__ import annotations

from abc import ABC, abstractmethod
from enum import Enum

from pydantic import BaseModel


class OrderSide(str, Enum):
    BUY = "buy"
    SELL = "sell"


class OrderType(str, Enum):
    MARKET = "market"
    LIMIT = "limit"


class Order(BaseModel):
    symbol: str
    side: OrderSide
    quantity: float
    type: OrderType = OrderType.MARKET
    limit_price: float | None = None
    broker_order_id: str | None = None


class Position(BaseModel):
    symbol: str
    quantity: float
    avg_price: float


class Broker(ABC):
    """증권사 주문 추상화. KIS(KOSPI), Alpaca(NASDAQ) 등이 구현한다."""

    @abstractmethod
    def submit_order(self, order: Order) -> Order:
        """주문을 제출하고 broker_order_id가 채워진 주문을 반환한다."""
        raise NotImplementedError

    @abstractmethod
    def get_positions(self) -> list[Position]:
        """현재 보유 포지션을 조회한다."""
        raise NotImplementedError
