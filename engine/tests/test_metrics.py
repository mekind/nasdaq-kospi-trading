"""metrics.py 단위 테스트."""

from __future__ import annotations

import math

import pandas as pd
import pytest

from trading_engine.backtest.metrics import compute_metrics, crash_period_analysis


# ── 공통 픽스처 ──────────────────────────────────────────────────────────────

@pytest.fixture
def equity_curve() -> pd.Series:
    """[100, 110, 99, 120] 4일치 자산 곡선."""
    dates = pd.date_range("2023-01-02", periods=4, freq="B")
    return pd.Series([100.0, 110.0, 99.0, 120.0], index=dates, name="equity")


@pytest.fixture
def trades() -> pd.DataFrame:
    """손익이 명확한 샘플 거래 4건."""
    return pd.DataFrame(
        {
            "entry_date": pd.to_datetime(
                ["2023-01-02", "2023-01-03", "2023-01-04", "2023-01-05"]
            ),
            "exit_date": pd.to_datetime(
                ["2023-01-03", "2023-01-04", "2023-01-05", "2023-01-06"]
            ),
            "entry_price": [100.0, 110.0, 99.0, 105.0],
            "exit_price": [110.0, 99.0, 120.0, 100.0],
            "qty": [1, 1, 1, 1],
            "pnl": [10.0, -11.0, 21.0, -5.0],
            "return_pct": [0.10, -0.10, 0.212, -0.0476],
            "hold_days": [1, 1, 1, 1],
        }
    )


@pytest.fixture
def empty_trades() -> pd.DataFrame:
    """빈 거래 DataFrame (올바른 컬럼 포함)."""
    return pd.DataFrame(
        columns=[
            "entry_date", "exit_date", "entry_price", "exit_price",
            "qty", "pnl", "return_pct", "hold_days",
        ]
    )


# ── compute_metrics 기본 검증 ─────────────────────────────────────────────────

class TestComputeMetrics:
    def test_total_return(self, equity_curve, trades):
        # (120 / 100) - 1 = 0.20
        m = compute_metrics(equity_curve, trades, initial_cash=100.0)
        assert m["total_return"] == pytest.approx(0.20)

    def test_max_drawdown(self, equity_curve, trades):
        # cummax: [100, 110, 110, 120]
        # drawdown: [0, 0, (99-110)/110, 0] → min = -11/110
        expected_dd = (99.0 / 110.0) - 1.0  # ≈ -0.10
        m = compute_metrics(equity_curve, trades, initial_cash=100.0)
        assert m["max_drawdown"] == pytest.approx(expected_dd)

    def test_win_rate(self, equity_curve, trades):
        # pnl = [10, -11, 21, -5] → 승리 2건 / 4건 = 0.5
        m = compute_metrics(equity_curve, trades, initial_cash=100.0)
        assert m["win_rate"] == pytest.approx(0.5)

    def test_expectancy(self, equity_curve, trades):
        # avg_win = (10 + 21) / 2 = 15.5
        # avg_loss = (-11 + -5) / 2 = -8.0
        # expectancy = 0.5 * 15.5 + 0.5 * (-8.0) = 3.75
        m = compute_metrics(equity_curve, trades, initial_cash=100.0)
        assert m["avg_win"] == pytest.approx(15.5)
        assert m["avg_loss"] == pytest.approx(-8.0)
        assert m["expectancy"] == pytest.approx(3.75)

    def test_payoff_ratio(self, equity_curve, trades):
        # 15.5 / 8.0 = 1.9375
        m = compute_metrics(equity_curve, trades, initial_cash=100.0)
        assert m["payoff_ratio"] == pytest.approx(1.9375)

    def test_n_trades(self, equity_curve, trades):
        m = compute_metrics(equity_curve, trades, initial_cash=100.0)
        assert m["n_trades"] == 4

    def test_cagr(self, equity_curve, trades):
        # (1.20) ** (252/4) - 1
        expected_cagr = (1.20 ** (252 / 4)) - 1.0
        m = compute_metrics(equity_curve, trades, initial_cash=100.0)
        assert m["cagr"] == pytest.approx(expected_cagr)

    def test_sharpe_is_finite(self, equity_curve, trades):
        m = compute_metrics(equity_curve, trades, initial_cash=100.0)
        assert math.isfinite(m["sharpe"])

    def test_sharpe_value(self, equity_curve, trades):
        """샤프 비율 수동 검증."""
        daily_ret = equity_curve.pct_change().dropna()
        expected = daily_ret.mean() / daily_ret.std() * math.sqrt(252)
        m = compute_metrics(equity_curve, trades, initial_cash=100.0)
        assert m["sharpe"] == pytest.approx(expected)

    def test_all_keys_present(self, equity_curve, trades):
        required = {
            "total_return", "cagr", "n_trades", "win_rate",
            "avg_win", "avg_loss", "payoff_ratio", "expectancy",
            "max_drawdown", "sharpe",
        }
        m = compute_metrics(equity_curve, trades, initial_cash=100.0)
        assert required == set(m.keys())


# ── 빈 거래 방어 로직 ─────────────────────────────────────────────────────────

class TestEmptyTrades:
    def test_no_exception(self, equity_curve, empty_trades):
        m = compute_metrics(equity_curve, empty_trades, initial_cash=100.0)
        assert isinstance(m, dict)

    def test_n_trades_zero(self, equity_curve, empty_trades):
        m = compute_metrics(equity_curve, empty_trades, initial_cash=100.0)
        assert m["n_trades"] == 0

    def test_win_rate_zero(self, equity_curve, empty_trades):
        m = compute_metrics(equity_curve, empty_trades, initial_cash=100.0)
        assert m["win_rate"] == 0.0

    def test_avg_win_zero(self, equity_curve, empty_trades):
        m = compute_metrics(equity_curve, empty_trades, initial_cash=100.0)
        assert m["avg_win"] == 0.0

    def test_avg_loss_zero(self, equity_curve, empty_trades):
        m = compute_metrics(equity_curve, empty_trades, initial_cash=100.0)
        assert m["avg_loss"] == 0.0

    def test_payoff_ratio_zero(self, equity_curve, empty_trades):
        m = compute_metrics(equity_curve, empty_trades, initial_cash=100.0)
        assert m["payoff_ratio"] == 0.0

    def test_expectancy_zero(self, equity_curve, empty_trades):
        m = compute_metrics(equity_curve, empty_trades, initial_cash=100.0)
        assert m["expectancy"] == 0.0

    def test_total_return_still_computed(self, equity_curve, empty_trades):
        # 거래가 없어도 자산 곡선 지표는 정상 계산
        m = compute_metrics(equity_curve, empty_trades, initial_cash=100.0)
        assert m["total_return"] == pytest.approx(0.20)


# ── crash_period_analysis ─────────────────────────────────────────────────────

class TestCrashPeriodAnalysis:
    @pytest.fixture
    def crash_trades(self) -> pd.DataFrame:
        """GFC/COVID 기간 및 그 외 기간 거래 혼합."""
        return pd.DataFrame(
            {
                "entry_date": pd.to_datetime(
                    [
                        "2008-09-15",  # GFC 기간 내
                        "2008-10-01",  # GFC 기간 내
                        "2010-01-01",  # 기간 외
                        "2020-03-01",  # COVID 기간 내
                        "2020-04-15",  # COVID 기간 내
                        "2021-01-01",  # 기간 외
                    ]
                ),
                "exit_date": pd.to_datetime(
                    [
                        "2008-09-20",
                        "2008-10-05",
                        "2010-01-10",
                        "2020-03-10",
                        "2020-04-20",
                        "2021-01-10",
                    ]
                ),
                "entry_price": [100.0] * 6,
                "exit_price": [90.0, 85.0, 110.0, 80.0, 95.0, 115.0],
                "qty": [1] * 6,
                "pnl": [-10.0, -15.0, 10.0, -20.0, -5.0, 15.0],
                "return_pct": [-0.10, -0.15, 0.10, -0.20, -0.05, 0.15],
                "hold_days": [5, 5, 9, 9, 5, 9],
            }
        )

    def test_gfc_n_trades(self, crash_trades):
        r = crash_period_analysis(crash_trades)
        assert r["2008_GFC"]["n_trades"] == 2

    def test_gfc_total_pnl(self, crash_trades):
        r = crash_period_analysis(crash_trades)
        assert r["2008_GFC"]["total_pnl"] == pytest.approx(-25.0)

    def test_gfc_win_rate_zero(self, crash_trades):
        # GFC 거래 2건 모두 손실
        r = crash_period_analysis(crash_trades)
        assert r["2008_GFC"]["win_rate"] == pytest.approx(0.0)

    def test_covid_n_trades(self, crash_trades):
        r = crash_period_analysis(crash_trades)
        assert r["2020_COVID"]["n_trades"] == 2

    def test_covid_total_pnl(self, crash_trades):
        r = crash_period_analysis(crash_trades)
        assert r["2020_COVID"]["total_pnl"] == pytest.approx(-25.0)

    def test_default_periods_keys(self, crash_trades):
        r = crash_period_analysis(crash_trades)
        assert "2008_GFC" in r
        assert "2020_COVID" in r

    def test_custom_periods(self, crash_trades):
        custom = {"test_period": ("2010-01-01", "2010-01-31")}
        r = crash_period_analysis(crash_trades, periods=custom)
        assert "test_period" in r
        assert r["test_period"]["n_trades"] == 1
        assert r["test_period"]["total_pnl"] == pytest.approx(10.0)
        assert r["test_period"]["win_rate"] == pytest.approx(1.0)

    def test_empty_trades_no_exception(self, empty_trades):
        r = crash_period_analysis(empty_trades)
        assert r["2008_GFC"]["n_trades"] == 0
        assert r["2008_GFC"]["total_pnl"] == 0.0
        assert r["2008_GFC"]["win_rate"] == 0.0

    def test_period_outside_all_trades(self, crash_trades):
        custom = {"no_match": ("2000-01-01", "2000-12-31")}
        r = crash_period_analysis(crash_trades, periods=custom)
        assert r["no_match"]["n_trades"] == 0
        assert r["no_match"]["total_pnl"] == 0.0
        assert r["no_match"]["win_rate"] == 0.0

    def test_boundary_inclusive(self, crash_trades):
        # 2008-09-15 정확히 경계일 → 포함돼야 함
        custom = {"boundary": ("2008-09-15", "2008-09-15")}
        r = crash_period_analysis(crash_trades, periods=custom)
        assert r["boundary"]["n_trades"] == 1
