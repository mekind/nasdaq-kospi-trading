"""Backtest engine (scaffold).

전략 + 과거 봉 데이터를 받아 손익을 시뮬레이션한다.
현재는 인터페이스와 결과 모델만 정의하며, 실제 체결/수수료/슬리피지 로직은 추후 구현한다.
"""

from __future__ import annotations

from pydantic import BaseModel

from trading_engine.data import Bar
from trading_engine.strategy import Strategy


class BacktestResult(BaseModel):
    strategy: str
    symbol: str
    n_bars: int
    total_return: float = 0.0
    n_trades: int = 0


class BacktestEngine:
    def __init__(self, initial_cash: float = 10_000_000.0) -> None:
        self.initial_cash = initial_cash

    def run(self, strategy: Strategy, symbol: str, bars: list[Bar]) -> BacktestResult:
        """전략을 봉 데이터에 대해 실행한다. (placeholder)"""
        # TODO: 시그널 기반 체결 시뮬레이션, 수수료/슬리피지, 포지션 추적 구현
        return BacktestResult(
            strategy=strategy.name,
            symbol=symbol,
            n_bars=len(bars),
        )
