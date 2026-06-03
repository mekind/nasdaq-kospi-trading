"""Backtesting engine."""

from .costs import CostModel
from .engine import BacktestEngine, BacktestResult
from .metrics import compute_metrics, crash_period_analysis
from .event_study import (
    CaarStat,
    abnormal_returns,
    caar,
    caar_for_signal,
    car_for_event,
    composite_yoy_signal,
    compute_event_cars,
    eps_yoy_signal,
    growth_gap_signal,
    run_event_study,
    sue_signal,
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
    "caar_for_signal",
    "car_for_event",
    "composite_yoy_signal",
    "compute_event_cars",
    "eps_yoy_signal",
    "growth_gap_signal",
    "run_event_study",
    "sue_signal",
]
