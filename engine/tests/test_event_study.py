"""모드 A 이벤트 스터디(CAAR) 단위 테스트 — 합성 데이터, 룩어헤드 검증 포함."""

from __future__ import annotations

import math

import pandas as pd
import pytest

from trading_engine.backtest.event_study import (
    abnormal_returns,
    caar,
    car_for_event,
    eps_yoy_signal,
    run_event_study,
)
from trading_engine.data.earnings import EarningsEvent, FinancialFigures


def _dates(n: int) -> pd.DatetimeIndex:
    return pd.bdate_range("2023-01-02", periods=n)


# ── abnormal_returns ────────────────────────────────────────────────────────
def test_abnormal_returns_subtracts_market():
    idx = _dates(4)
    stock = pd.Series([100, 110, 121, 133.1], index=idx)  # +10%/day
    market = pd.Series([100, 105, 110.25, 115.7625], index=idx)  # +5%/day
    abn = abnormal_returns(stock, market)
    # 초과수익 ≈ 5%/day
    assert abn.iloc[0] == pytest.approx(0.05, abs=1e-6)
    assert len(abn) == 3  # 첫 NaN 제거


# ── car_for_event: 룩어헤드 차단 ────────────────────────────────────────────
def test_car_excludes_event_day_jump():
    idx = _dates(30)
    abn = pd.Series([0.01] * 30, index=idx)
    entry = idx[10]
    abn.loc[entry] = 99.0  # 이벤트 당일 거대한 점프
    car = car_for_event(abn, entry, horizons=(1, 5))
    # 당일 점프(99)는 제외하고 다음날부터 누적 → CAR_1 = 0.01
    assert car[1] == pytest.approx(0.01)
    assert car[5] == pytest.approx(0.05)


def test_car_known_values():
    idx = _dates(30)
    abn = pd.Series([0.02] * 30, index=idx)
    car = car_for_event(abn, idx[5], horizons=(1, 10))
    assert car[1] == pytest.approx(0.02)
    assert car[10] == pytest.approx(0.20)


def test_car_insufficient_data_is_none():
    idx = _dates(10)
    abn = pd.Series([0.01] * 10, index=idx)
    car = car_for_event(abn, idx[8], horizons=(1, 5))
    assert car[1] == pytest.approx(0.01)  # pos8 → iloc[9:10] ok
    assert car[5] is None  # 데이터 부족


def test_car_entry_not_in_index():
    idx = _dates(10)
    abn = pd.Series([0.01] * 10, index=idx)
    car = car_for_event(abn, pd.Timestamp("2099-01-01"), horizons=(1, 5))
    assert car == {1: None, 5: None}


# ── caar: 평균 + t값 ────────────────────────────────────────────────────────
def test_caar_mean_and_tstat():
    event_cars = [{5: 0.10}, {5: 0.20}, {5: 0.30}]
    out = caar(event_cars, horizons=(5,))
    s = out[5]
    assert s.n == 3
    assert s.caar == pytest.approx(0.20)
    # std=0.1, t = 0.20 / (0.1/sqrt(3)) ≈ 3.464
    assert s.t_stat == pytest.approx(0.20 / (0.1 / math.sqrt(3)), rel=1e-6)


def test_caar_skips_none_and_single_sample():
    out = caar([{5: 0.1}, {5: None}], horizons=(5,))
    assert out[5].n == 1
    assert out[5].caar == pytest.approx(0.1)
    assert out[5].t_stat == 0.0  # n<2


def test_caar_empty():
    out = caar([], horizons=(5,))
    assert out[5].n == 0 and out[5].caar == 0.0


# ── eps_yoy_signal ──────────────────────────────────────────────────────────
def _event(stock_code, eps_yoy_val, avail):
    fig = FinancialFigures(eps=1.0, prior_eps=1.0)
    ev = EarningsEvent(
        stock_code=stock_code,
        corp_code="C",
        rcept_no="R",
        rcept_dt="20230814",
        bsns_year=2023,
        reprt_code="11012",
        is_amendment=False,
        figures=fig,
        avail_date=avail,
    )
    ev.yoy["eps"] = eps_yoy_val  # 직접 주입
    return ev


def test_eps_yoy_signal_threshold():
    sig = eps_yoy_signal(0.20)
    assert sig(_event("A", 0.25, None)) is True
    assert sig(_event("A", 0.10, None)) is False
    assert sig(_event("A", None, None)) is False


# ── run_event_study: 시그널 필터 + 집계 ─────────────────────────────────────
def test_run_event_study_filters_and_aggregates():
    idx = _dates(80)
    # 평탄한 시장(수익률 0) 대비 종목은 매일 +0.5% → 명확한 양의 초과수익 드리프트
    market = pd.Series(100.0, index=idx)
    stock_a = pd.Series((1.005 ** pd.Series(range(80))).values * 100, index=idx)
    stock_b = pd.Series((1.005 ** pd.Series(range(80))).values * 100, index=idx)

    entry = idx[10]
    events = [
        _event("A", 0.30, entry),  # 시그널 통과
        _event("B", 0.05, entry),  # 시그널 미달 → 제외
    ]
    out = run_event_study(
        events,
        price_map={"A": stock_a, "B": stock_b},
        market_close=market,
        signal_fn=eps_yoy_signal(0.20),
        horizons=(5, 20),
    )
    # A만 집계 → n=1
    assert out[5].n == 1
    # 양의 초과수익 → 양의 CAAR
    assert out[5].caar > 0
    assert out[20].caar > out[5].caar  # 드리프트 지속 → 더 긴 지평선이 더 큼


def test_run_event_study_skips_missing_price_and_no_avail():
    idx = _dates(40)
    market = pd.Series(100.0, index=idx)
    events = [
        _event("A", 0.30, None),  # avail 없음 → 제외
        _event("Z", 0.30, idx[5]),  # price_map에 없음 → 제외
    ]
    out = run_event_study(events, {}, market, eps_yoy_signal(0.20), horizons=(5,))
    assert out[5].n == 0
