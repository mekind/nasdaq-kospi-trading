"""Alpaca 브로커 (NASDAQ) — scaffold."""

from __future__ import annotations

from trading_engine.broker.base import Broker, Order, Position


class AlpacaBroker(Broker):
    """Alpaca 연동 브로커.

    TODO: alpaca-py SDK 또는 REST 호출로 주문/잔고 구현.
    https://docs.alpaca.markets/
    """

    def __init__(self, api_key: str, api_secret: str, base_url: str) -> None:
        self.api_key = api_key
        self.api_secret = api_secret
        self.base_url = base_url

    def submit_order(self, order: Order) -> Order:
        raise NotImplementedError("Alpaca 주문 연동 미구현")

    def get_positions(self) -> list[Position]:
        raise NotImplementedError("Alpaca 잔고 조회 미구현")
