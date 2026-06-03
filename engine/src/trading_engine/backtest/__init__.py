"""Backtesting engine."""

from .costs import CostModel
from .engine import BacktestEngine, BacktestResult
from .metrics import compute_metrics, crash_period_analysis
from .event_study import (
    CaarStat,
    abnormal_returns,
    caar,
    car_for_event,
    eps_yoy_signal,
    run_event_study,
)

__all__ = [
    "BacktestEngine",
    "BacktestResult",
    "CostModel",
    "compute_metrics",
    "crash_period_analysis",
    "CaarStat",
    "abnormal_returns",
    "caar",
    "car_for_event",
    "eps_yoy_signal",
    "run_event_study",
]
