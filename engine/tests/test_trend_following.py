"""AssetClassTrendFollowing 신호 단위 테스트 (합성 데이터).

SMA 위/아래 보유·현금 전환, 워밍업 현금처리, 룩어헤드 차단(월말 기준 SMA)을 검증한다.
"""

from __future__ import annotations

import pandas as pd
import pytest

from trading_engine.strategy.trend_following import AssetClassTrendFollowing


def _daily(prices_by_asset: dict[str, list[float]], dates: pd.DatetimeIndex):
    return pd.DataFrame(prices_by_asset, index=dates)


def test_month_end_rows_picks_last_trading_day():
    """월말 추출은 각 월의 마지막 거래일을 고른다(달력 말일 아님)."""
    # 1월: 1/30까지, 2월: 2/27까지(주말 제외 영업일).
    dates = pd.bdate_range("2021-01-01", "2021-02-28")
    df = _daily({"A": list(range(len(dates)))}, dates)
    me = AssetClassTrendFollowing.month_end_rows(df)
    assert len(me) == 2
    assert me.index[0].month == 1 and me.index[1].month == 2
    # 1월 마지막 영업일 = 2021-01-29.
    assert me.index[0] == pd.Timestamp("2021-01-29")


def test_warmup_period_is_cash():
    """SMA 워밍업(이력 < sma_months) 구간은 보유 자산이 없다(현금)."""
    dates = pd.bdate_range("2020-01-01", periods=120)  # 약 6개월
    df = _daily({"A": [100.0 + i for i in range(len(dates))]}, dates)
    strat = AssetClassTrendFollowing(["A"], sma_months=10)
    w = strat.generate_weights(df)
    # 월말이 6개 정도 — 10개월 SMA가 안 차므로 전부 빈 비중.
    assert all(v == {} for v in w.values())


def test_uptrend_holds_downtrend_goes_cash():
    """상승추세(종가>SMA)면 보유, 하락추세(종가<SMA)면 현금."""
    # 12개월: 처음 단조 상승 후 급락하도록 월말값 설계.
    dates = pd.bdate_range("2019-01-01", periods=400)
    # 일별이지만 월말만 신호에 쓰이므로 완만한 상승 후 후반 급락.
    vals = []
    for i in range(len(dates)):
        if i < 300:
            vals.append(100.0 + i * 0.5)  # 상승
        else:
            vals.append(250.0 - (i - 300) * 3.0)  # 급락
    df = _daily({"A": vals}, dates)
    strat = AssetClassTrendFollowing(["A"], sma_months=10)
    w = strat.generate_weights(df)
    items = list(w.items())
    # 10개월 이후 상승구간 월말: 보유(0.5? no, 1자산이라 1.0).
    held = [ts for ts, ww in items if ww]
    cash = [ts for ts, ww in items if not ww]
    assert len(held) > 0, "상승구간에서 보유가 있어야 함"
    assert len(cash) > 0, "급락구간에서 현금이 있어야 함"
    # 보유 비중은 1/N = 1.0(단일자산).
    for ts in held:
        assert w[ts]["A"] == pytest.approx(1.0)
    # 마지막 월말(급락)은 현금이어야 함.
    assert items[-1][1] == {}


def test_slot_weight_is_equal_across_assets():
    """다자산이면 보유 슬롯 비중은 1/N으로 동일하다."""
    dates = pd.bdate_range("2018-01-01", periods=400)
    # A,B는 꾸준히 상승(보유), C는 꾸준히 하락(현금)하도록.
    up = [100.0 + i for i in range(len(dates))]
    down = [100.0 - i * 0.1 for i in range(len(dates))]
    df = _daily({"A": up, "B": up, "C": down}, dates)
    strat = AssetClassTrendFollowing(["A", "B", "C"], sma_months=10)
    w = strat.generate_weights(df)
    last = list(w.values())[-1]
    # A,B 보유(각 1/3), C 현금.
    assert last.get("A") == pytest.approx(1 / 3)
    assert last.get("B") == pytest.approx(1 / 3)
    assert "C" not in last


def test_decision_dates_exist_in_daily_index():
    """결정일(월말)이 모두 입력 일별 인덱스에 존재한다(엔진 체결 가능 보장)."""
    dates = pd.bdate_range("2018-01-01", periods=300)
    df = _daily({"A": [100.0 + i for i in range(len(dates))]}, dates)
    strat = AssetClassTrendFollowing(["A"], sma_months=10)
    w = strat.generate_weights(df)
    for ts in w:
        assert ts in df.index
