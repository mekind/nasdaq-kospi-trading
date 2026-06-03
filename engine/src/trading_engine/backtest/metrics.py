"""백테스트 성과 지표 계산 모듈."""

from __future__ import annotations

import math

import pandas as pd


def compute_metrics(
    equity_curve: pd.Series,
    trades: pd.DataFrame,
    initial_cash: float,
    periods_per_year: int = 252,
) -> dict:
    """일별 자산 곡선과 거래 내역으로 주요 성과 지표를 계산한다.

    Args:
        equity_curve: DatetimeIndex 기반 일별 총 자산 (현금 + 평가금).
        trades: entry_date, exit_date, entry_price, exit_price, qty,
                pnl, return_pct, hold_days 컬럼을 가진 거래 DataFrame.
        initial_cash: 초기 투자 원금.
        periods_per_year: 연간 거래일 수 (기본 252).

    Returns:
        성과 지표 딕셔너리.
    """
    n = len(equity_curve)

    # ── 수익률 지표 ──────────────────────────────────────────────────────────
    if n == 0 or initial_cash == 0:
        total_return = 0.0
        cagr = 0.0
    else:
        final_equity = float(equity_curve.iloc[-1])
        ratio = final_equity / initial_cash
        total_return = ratio - 1.0
        if n >= 2:
            cagr = ratio ** (periods_per_year / n) - 1.0
        else:
            cagr = 0.0

    # ── 거래 지표 ────────────────────────────────────────────────────────────
    n_trades = len(trades)

    if n_trades == 0:
        win_rate = 0.0
        avg_win = 0.0
        avg_loss = 0.0
        payoff_ratio = 0.0
        expectancy = 0.0
    else:
        pnl = trades["pnl"]
        wins = pnl[pnl > 0]
        losses = pnl[pnl <= 0]

        win_rate = float((pnl > 0).mean())
        avg_win = float(wins.mean()) if len(wins) > 0 else 0.0
        avg_loss = float(losses.mean()) if len(losses) > 0 else 0.0  # 음수

        if avg_loss == 0.0:
            payoff_ratio = 0.0
        else:
            payoff_ratio = avg_win / abs(avg_loss)

        expectancy = win_rate * avg_win + (1.0 - win_rate) * avg_loss

    # ── 최대 낙폭 ────────────────────────────────────────────────────────────
    if n == 0:
        max_drawdown = 0.0
    else:
        running_max = equity_curve.cummax()
        drawdown = (equity_curve / running_max) - 1.0
        max_drawdown = float(drawdown.min())

    # ── 샤프 지수 ────────────────────────────────────────────────────────────
    if n < 2:
        sharpe = 0.0
    else:
        daily_ret = equity_curve.pct_change().dropna()
        if len(daily_ret) == 0:
            sharpe = 0.0
        else:
            std = float(daily_ret.std())
            if std == 0.0:
                sharpe = 0.0
            else:
                sharpe = float(daily_ret.mean()) / std * math.sqrt(periods_per_year)

    return {
        "total_return": total_return,
        "cagr": cagr,
        "n_trades": n_trades,
        "win_rate": win_rate,
        "avg_win": avg_win,
        "avg_loss": avg_loss,
        "payoff_ratio": payoff_ratio,
        "expectancy": expectancy,
        "max_drawdown": max_drawdown,
        "sharpe": sharpe,
    }


def crash_period_analysis(
    trades: pd.DataFrame,
    periods: dict[str, tuple[str, str]] | None = None,
) -> dict:
    """특정 위기 기간 동안의 거래 성과를 분석한다.

    Args:
        trades: 거래 DataFrame (entry_date 컬럼 필요).
        periods: {"레이블": ("시작일", "종료일")} 형태의 딕셔너리.
                 None 이면 기본 위기 기간(2008 GFC, 2020 COVID)을 사용.

    Returns:
        레이블별 {"n_trades", "total_pnl", "win_rate"} 딕셔너리.
    """
    if periods is None:
        periods = {
            "2008_GFC": ("2008-09-01", "2009-03-31"),
            "2020_COVID": ("2020-02-19", "2020-04-30"),
        }

    result: dict = {}

    for label, (start_str, end_str) in periods.items():
        start = pd.Timestamp(start_str)
        end = pd.Timestamp(end_str)

        if trades.empty or "entry_date" not in trades.columns:
            result[label] = {"n_trades": 0, "total_pnl": 0.0, "win_rate": 0.0}
            continue

        # entry_date가 [start, end] 범위에 속하는 거래만 필터링
        mask = (trades["entry_date"] >= start) & (trades["entry_date"] <= end)
        subset = trades[mask]

        n = len(subset)
        if n == 0:
            result[label] = {"n_trades": 0, "total_pnl": 0.0, "win_rate": 0.0}
        else:
            total_pnl = float(subset["pnl"].sum())
            win_rate = float((subset["pnl"] > 0).mean())
            result[label] = {
                "n_trades": n,
                "total_pnl": total_pnl,
                "win_rate": win_rate,
            }

    return result
