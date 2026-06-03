"""KrxMarketCap.top_n_at 의 정렬·상위 N 컷·양수 필터 검증 (pykrx 미사용).

market_cap_at 를 패치해 네트워크/KRX 로그인 없이 순수 로직만 테스트한다.
"""

from __future__ import annotations

import pandas as pd

from trading_engine.data.market_cap import KrxMarketCap


def test_top_n_sorts_desc_and_cuts(monkeypatch):
    mc = KrxMarketCap()
    series = pd.Series(
        {"A": 100.0, "B": 300.0, "C": 200.0, "D": 50.0}, name="시가총액"
    )
    monkeypatch.setattr(mc, "market_cap_at", lambda *a, **k: series)

    # 시총 내림차순 상위 2 = [B(300), C(200)]
    assert mc.top_n_at("20200630", 2) == ["B", "C"]
    # n이 종목 수보다 크면 가능한 만큼
    assert mc.top_n_at("20200630", 10) == ["B", "C", "A", "D"]


def test_top_n_filters_nonpositive(monkeypatch):
    mc = KrxMarketCap()
    # 시총 0/결측 종목은 제외(상장폐지 직전 등)
    series = pd.Series(
        {"A": 100.0, "Z": 0.0, "B": 300.0, "N": float("nan")}, name="시가총액"
    )
    monkeypatch.setattr(mc, "market_cap_at", lambda *a, **k: series)

    assert mc.top_n_at("20200630", 10) == ["B", "A"]
