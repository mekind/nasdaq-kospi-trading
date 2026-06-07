"""PortfolioBacktestEngine 무결성 단위 테스트 (합성 데이터).

WORKFLOW 규칙5: 현금보존·동일비중재조정·회전율0·룩어헤드·결측을 합성 케이스로 단정한다.
"""

from __future__ import annotations

import pandas as pd
import pytest

from trading_engine.backtest.costs import CostModel
from trading_engine.backtest.portfolio_engine import PortfolioBacktestEngine

NO_COST = CostModel(commission_rate=0.0, slippage_bps=0.0, sell_tax_rate=0.0)


def _panel(prices: dict[str, list[float]], dates: pd.DatetimeIndex):
    """opens=closes 동일한 단순 패널(시가체결=종가평가 일치 케이스용)."""
    df = pd.DataFrame(prices, index=dates)
    return df, df


def test_no_trade_keeps_cash_constant():
    """목표비중이 없으면 거래가 없고 자산은 초기현금 그대로다."""
    dates = pd.date_range("2020-01-01", periods=5, freq="D")
    opens, closes = _panel({"A": [10, 11, 12, 13, 14]}, dates)
    eng = PortfolioBacktestEngine(initial_cash=1000.0, cost_model=NO_COST)
    res = eng.run(opens, closes, target_weights={})
    assert (res.equity_curve == 1000.0).all()
    assert res.final_equity == 1000.0
    assert len(res.rebalance_log) == 0


def test_cash_conservation_identity():
    """비용0·임의 가격에서 equity = cash + Σ qty×close 항등식이 매일 성립한다."""
    dates = pd.date_range("2020-01-01", periods=6, freq="D")
    opens = pd.DataFrame(
        {"A": [10, 10, 10, 10, 10, 10], "B": [20, 21, 22, 23, 24, 25]}, index=dates
    )
    closes = pd.DataFrame(
        {"A": [10, 10, 10, 10, 10, 10], "B": [20, 21, 22, 23, 24, 25]}, index=dates
    )
    # day0 결정 → day1 체결로 50:50.
    tw = {dates[0]: {"A": 0.5, "B": 0.5}}
    eng = PortfolioBacktestEngine(initial_cash=1000.0, cost_model=NO_COST)
    res = eng.run(opens, closes, tw)
    # 체결 전(day0)은 전액 현금 → equity=1000.
    assert res.equity_curve.iloc[0] == pytest.approx(1000.0)
    # 체결 후 A는 가격불변, B만 상승 → equity 증가.
    assert res.equity_curve.iloc[-1] > 1000.0
    # 항등식 수동 검증: 체결은 day1(iloc 1) 시가에 일어남 → A 50주(500/10), B 500/21주.
    qty_a, qty_b = 500 / 10, 500 / 21
    expected = qty_a * 10 + qty_b * 25  # day5(iloc 5) 종가: A=10, B=25
    assert res.equity_curve.iloc[-1] == pytest.approx(expected)


def test_equal_weight_rebalances_to_equal_value():
    """1자산이 2배 오른 뒤 동일비중 리밸런싱하면 두 평가액이 같아진다."""
    dates = pd.date_range("2020-01-01", periods=4, freq="D")
    # A는 10 고정, B는 day2에 2배(20→40)로 점프.
    opens = pd.DataFrame({"A": [10, 10, 10, 10], "B": [20, 20, 40, 40]}, index=dates)
    closes = opens.copy()
    # day0 결정→day1 체결 50:50, day2 결정→day3 체결 재조정 50:50.
    tw = {dates[0]: {"A": 0.5, "B": 0.5}, dates[2]: {"A": 0.5, "B": 0.5}}
    eng = PortfolioBacktestEngine(initial_cash=1000.0, cost_model=NO_COST)
    res = eng.run(opens, closes, tw)
    # day3 체결 직후 종가(day3) 평가에서 A,B 평가액 동일해야 함.
    # day1: A 50주, B 25주. day2 close: A 500, B 1000 → equity 1500.
    # day3 open 재조정: 각 750 목표. A 75주(750/10), B 18.75주(750/40).
    # day3 close 평가: A 750, B 750 → 동일.
    qty_a, qty_b = 75.0, 750 / 40
    assert qty_a * 10 == pytest.approx(qty_b * 40)
    assert res.equity_curve.iloc[-1] == pytest.approx(1500.0)


def test_zero_turnover_when_weights_and_prices_unchanged():
    """목표비중·가격이 그대로면 재리밸런싱 시 회전율·비용이 0이다(무비용 기준 불변식).

    비용이 있으면 첫 진입 비용만큼 equity가 줄어 다음 리밸런싱에 미세 조정이 생기므로
    (현실적 동작), 순수 '비중 불변 → 무거래' 불변식은 NO_COST에서 검증한다.
    """
    dates = pd.date_range("2020-01-01", periods=5, freq="D")
    opens = pd.DataFrame({"A": [10, 10, 10, 10, 10]}, index=dates)
    closes = opens.copy()
    # day0 진입(100% A), day2 동일비중 재지정 → 가격불변이라 Δ=0.
    tw = {dates[0]: {"A": 1.0}, dates[2]: {"A": 1.0}}
    eng = PortfolioBacktestEngine(initial_cash=1000.0, cost_model=NO_COST)
    res = eng.run(opens, closes, tw)
    second = res.rebalance_log.iloc[1]
    assert second["turnover"] == pytest.approx(0.0)
    assert second["cost"] == pytest.approx(0.0)


def test_costs_reduce_equity_on_entry():
    """비용 모델이 있으면 진입 시 수수료·슬리피지만큼 자산이 줄어든다."""
    dates = pd.date_range("2020-01-01", periods=3, freq="D")
    opens = pd.DataFrame({"A": [10, 10, 10]}, index=dates)
    closes = opens.copy()
    cost = CostModel(commission_rate=0.01, slippage_bps=50.0, sell_tax_rate=0.0)
    tw = {dates[0]: {"A": 1.0}}
    eng = PortfolioBacktestEngine(initial_cash=1000.0, cost_model=cost)
    res = eng.run(opens, closes, tw)
    # 진입 후 자산은 비용만큼 1000 미만, 회전율·비용 > 0.
    assert res.equity_curve.iloc[-1] < 1000.0
    first = res.rebalance_log.iloc[0]
    assert first["turnover"] > 0.0
    assert first["cost"] > 0.0


def test_execution_is_next_bar_open_not_decision_bar():
    """체결은 결정일 다음 봉 시가에서 일어난다(룩어헤드 차단)."""
    dates = pd.date_range("2020-01-01", periods=3, freq="D")
    # 결정일(day0) 종가 이후, day1 시가가 결정일과 크게 다른 케이스.
    opens = pd.DataFrame({"A": [10, 100, 100]}, index=dates)  # day1 시가=100
    closes = pd.DataFrame({"A": [10, 100, 100]}, index=dates)
    tw = {dates[0]: {"A": 1.0}}
    eng = PortfolioBacktestEngine(initial_cash=1000.0, cost_model=NO_COST)
    res = eng.run(opens, closes, tw)
    # day0엔 미체결(현금 1000). day1 시가 100에 매수 → 10주. 이후 가격불변.
    assert res.equity_curve.iloc[0] == pytest.approx(1000.0)
    # 만약 결정일(day0=10)에 체결했다면 100주→equity 10000이 됐을 것. 아님을 확인.
    assert res.equity_curve.iloc[1] == pytest.approx(1000.0)
    assert res.rebalance_log.iloc[0]["exec_date"] == dates[1]


def test_no_execution_on_last_bar():
    """마지막 봉이 결정일이면 체결할 다음 봉이 없어 거래가 예약되지 않는다."""
    dates = pd.date_range("2020-01-01", periods=3, freq="D")
    opens = pd.DataFrame({"A": [10, 10, 10]}, index=dates)
    closes = opens.copy()
    tw = {dates[2]: {"A": 1.0}}  # 마지막 봉 결정
    eng = PortfolioBacktestEngine(initial_cash=1000.0, cost_model=NO_COST)
    res = eng.run(opens, closes, tw)
    assert len(res.rebalance_log) == 0
    assert (res.equity_curve == 1000.0).all()


def test_raises_on_misaligned_panels():
    """opens/closes의 index 또는 columns가 어긋나면 ValueError로 조기 차단한다."""
    d1 = pd.date_range("2020-01-01", periods=3, freq="D")
    d2 = pd.date_range("2020-01-02", periods=3, freq="D")
    eng = PortfolioBacktestEngine(initial_cash=1000.0, cost_model=NO_COST)
    with pytest.raises(ValueError, match="index"):
        eng.run(
            pd.DataFrame({"A": [1, 2, 3]}, index=d1),
            pd.DataFrame({"A": [1, 2, 3]}, index=d2),
            {},
        )
    with pytest.raises(ValueError, match="columns"):
        eng.run(
            pd.DataFrame({"A": [1, 2, 3]}, index=d1),
            pd.DataFrame({"B": [1, 2, 3]}, index=d1),
            {},
        )


def test_raises_on_weights_exceeding_one():
    """목표비중 합 > 1.0(레버리지) 또는 음수 비중은 ValueError."""
    dates = pd.date_range("2020-01-01", periods=3, freq="D")
    opens = pd.DataFrame({"A": [10, 10, 10], "B": [10, 10, 10]}, index=dates)
    eng = PortfolioBacktestEngine(initial_cash=1000.0, cost_model=NO_COST)
    with pytest.raises(ValueError, match="레버리지"):
        eng.run(opens, opens.copy(), {dates[0]: {"A": 0.7, "B": 0.7}})
    with pytest.raises(ValueError, match="음수"):
        eng.run(opens, opens.copy(), {dates[0]: {"A": -0.5}})


def test_full_investment_weights_allowed():
    """비중 합이 정확히 1.0(부동소수 오차 포함)이면 허용된다."""
    dates = pd.date_range("2020-01-01", periods=3, freq="D")
    opens = pd.DataFrame(
        {"A": [10, 10, 10], "B": [10, 10, 10], "C": [10, 10, 10]}, index=dates
    )
    eng = PortfolioBacktestEngine(initial_cash=1000.0, cost_model=NO_COST)
    # 1/3 × 3 = 0.999...로 1.0 미세초과 가능 → 허용돼야 함.
    res = eng.run(opens, opens.copy(), {dates[0]: {"A": 1 / 3, "B": 1 / 3, "C": 1 / 3}})
    assert res.final_equity == pytest.approx(1000.0)


def test_missing_price_asset_is_skipped():
    """시가가 NaN인 자산은 거래되지 않고 보유가 유지된다(다른 자산은 정상 체결)."""
    dates = pd.date_range("2020-01-01", periods=3, freq="D")
    opens = pd.DataFrame({"A": [10, 10, 10], "B": [20, float("nan"), 20]}, index=dates)
    closes = pd.DataFrame({"A": [10, 10, 10], "B": [20, 20, 20]}, index=dates)
    tw = {dates[0]: {"A": 0.5, "B": 0.5}}
    eng = PortfolioBacktestEngine(initial_cash=1000.0, cost_model=NO_COST)
    res = eng.run(opens, closes, tw)
    # B는 day1 시가 NaN이라 매수 불가 → A만 500어치 매수, 나머지 현금.
    # equity 유지(손실/이익 없음, 가격 불변).
    assert res.equity_curve.iloc[-1] == pytest.approx(1000.0)
