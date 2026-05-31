"""한국투자증권 (KIS) Open API 브로커 (KOSPI) — scaffold."""

from __future__ import annotations

from trading_engine.broker.base import Broker, Order, Position


class KISBroker(Broker):
    """한국투자증권 Open API 연동 브로커.

    TODO: OAuth 토큰 발급, 주문/잔고 REST 호출 구현.
    https://apiportal.koreainvestment.com/
    """

    def __init__(self, app_key: str, app_secret: str, account_no: str, paper: bool = True) -> None:
        self.app_key = app_key
        self.app_secret = app_secret
        self.account_no = account_no
        self.paper = paper

    def submit_order(self, order: Order) -> Order:
        raise NotImplementedError("KIS 주문 연동 미구현")

    def get_positions(self) -> list[Position]:
        raise NotImplementedError("KIS 잔고 조회 미구현")
