"""FdrProvider 정규화 로직 단위 테스트 (네트워크 없이 fdr.DataReader 모킹).

핵심 검증: 장기 지수 데이터처럼 '선두 구간 OHLC 결측(종가만 존재)'이 섞여 있어도
체결 불가능한 봉을 제거해 NaN 오염을 차단하는지.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from trading_engine.data import fdr_provider
from trading_engine.data import FdrProvider


def _raw_with_leading_ohlc_nan() -> pd.DataFrame:
    """선두 2봉은 종가만 존재(open/high/low NaN), 이후 3봉은 정상 OHLCV.

    KS200 같은 장기 지수의 초기 구간(종가만 제공)을 모사한다.
    컬럼은 대문자로 두어 FDR 원본(대문자) → 소문자 정규화도 함께 검증.
    """
    idx = pd.to_datetime(
        ["1990-01-03", "1990-01-04", "1995-01-03", "1995-01-04", "1995-01-05"]
    )
    return pd.DataFrame(
        {
            "Open": [np.nan, np.nan, 100.0, 101.0, 102.0],
            "High": [np.nan, np.nan, 101.0, 102.0, 103.0],
            "Low": [np.nan, np.nan, 99.0, 100.0, 101.0],
            "Close": [50.0, 51.0, 100.5, 101.5, 102.5],
            "Volume": [10.0, np.nan, 1000.0, 1100.0, 1200.0],
        },
        index=idx,
    )


def test_drops_rows_with_missing_ohlc(monkeypatch):
    """OHLC 중 하나라도 결측인 봉(선두 2봉)은 제거되어야 한다."""
    monkeypatch.setattr(
        fdr_provider.fdr, "DataReader", lambda *a, **k: _raw_with_leading_ohlc_nan()
    )

    df = FdrProvider().load_daily("KS200", start="1990-01-01", use_cache=False)

    # 선두 결측 2봉 제거 → 정상 3봉만 남는다.
    assert len(df) == 3
    assert df.index[0] == pd.Timestamp("1995-01-03")
    # 남은 봉에는 OHLC 결측이 없어야 한다(체결가 NaN 오염 차단).
    assert not df[["open", "high", "low", "close"]].isna().any().any()


def test_columns_normalized_and_float(monkeypatch):
    """컬럼은 소문자 표준 스키마 + float dtype 이어야 한다."""
    monkeypatch.setattr(
        fdr_provider.fdr, "DataReader", lambda *a, **k: _raw_with_leading_ohlc_nan()
    )

    df = FdrProvider().load_daily("KS200", start="1990-01-01", use_cache=False)

    assert list(df.columns) == ["open", "high", "low", "close", "volume"]
    assert all(str(dt) == "float64" for dt in df.dtypes)


def test_missing_volume_filled_with_zero(monkeypatch):
    """거래량 결측은 0으로 채워지되, 그 봉의 OHLC가 정상이면 제거되지 않는다."""
    # 1995-01-04 봉은 Volume이 NaN이지만 OHLC는 정상 → 유지 + volume 0.
    raw = _raw_with_leading_ohlc_nan()
    raw.loc["1995-01-04", "Volume"] = np.nan
    monkeypatch.setattr(fdr_provider.fdr, "DataReader", lambda *a, **k: raw)

    df = FdrProvider().load_daily("KS200", start="1990-01-01", use_cache=False)

    assert pd.Timestamp("1995-01-04") in df.index
    assert df.loc["1995-01-04", "volume"] == 0.0
    assert int(df["volume"].isna().sum()) == 0


def test_index_sorted_ascending(monkeypatch):
    """반환 인덱스는 DatetimeIndex 오름차순이어야 한다."""
    raw = _raw_with_leading_ohlc_nan().iloc[::-1]  # 역순 입력
    monkeypatch.setattr(fdr_provider.fdr, "DataReader", lambda *a, **k: raw)

    df = FdrProvider().load_daily("KS200", start="1990-01-01", use_cache=False)

    assert isinstance(df.index, pd.DatetimeIndex)
    assert df.index.is_monotonic_increasing
