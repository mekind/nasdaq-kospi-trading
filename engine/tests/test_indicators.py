"""indicators 모듈 단위 테스트."""

import math
import pandas as pd
import pytest

from trading_engine.indicators import sma, rsi


# ---------------------------------------------------------------------------
# SMA 테스트
# ---------------------------------------------------------------------------

class TestSma:
    def test_known_values(self):
        """소규모 시리즈로 정확한 rolling mean 값 검증."""
        data = pd.Series([1.0, 2.0, 3.0, 4.0, 5.0])
        result = sma(data, window=3)

        # 처음 두 값은 NaN (warmup)
        assert math.isnan(result.iloc[0])
        assert math.isnan(result.iloc[1])

        # window=3 rolling mean
        assert result.iloc[2] == pytest.approx((1 + 2 + 3) / 3)  # 2.0
        assert result.iloc[3] == pytest.approx((2 + 3 + 4) / 3)  # 3.0
        assert result.iloc[4] == pytest.approx((3 + 4 + 5) / 3)  # 4.0

    def test_output_length_equals_input(self):
        """출력 길이 == 입력 길이."""
        data = pd.Series(range(10), dtype=float)
        result = sma(data, window=3)
        assert len(result) == len(data)

    def test_index_preserved(self):
        """인덱스가 입력과 동일하게 유지되어야 함."""
        idx = pd.date_range("2024-01-01", periods=5, freq="D")
        data = pd.Series([10.0, 20.0, 30.0, 40.0, 50.0], index=idx)
        result = sma(data, window=2)
        assert list(result.index) == list(idx)

    def test_window_1_equals_series(self):
        """window=1 이면 원래 시리즈와 동일해야 함."""
        data = pd.Series([3.0, 1.0, 4.0, 1.0, 5.0])
        result = sma(data, window=1)
        pd.testing.assert_series_equal(result, data)


# ---------------------------------------------------------------------------
# RSI 테스트
# ---------------------------------------------------------------------------

class TestRsi:
    def test_strictly_increasing_rsi_near_100(self):
        """단조 증가 시리즈의 마지막 RSI는 100에 근접해야 함."""
        data = pd.Series([float(i) for i in range(1, 51)])  # 50개 데이터
        result = rsi(data, period=14)
        last_valid = result.dropna().iloc[-1]
        assert last_valid > 90.0, f"strictly increasing RSI should be near 100, got {last_valid}"

    def test_strictly_decreasing_rsi_near_0(self):
        """단조 감소 시리즈의 마지막 RSI는 0에 근접해야 함."""
        data = pd.Series([float(50 - i) for i in range(50)])  # 50, 49, ..., 1
        result = rsi(data, period=14)
        last_valid = result.dropna().iloc[-1]
        assert last_valid < 10.0, f"strictly decreasing RSI should be near 0, got {last_valid}"

    def test_all_values_in_range(self):
        """non-NaN RSI 값 전체가 [0, 100] 범위 내에 있어야 함."""
        import numpy as np
        rng = np.random.default_rng(42)
        prices = pd.Series(100.0 + rng.standard_normal(100).cumsum())
        result = rsi(prices, period=14)
        valid = result.dropna()
        assert (valid >= 0.0).all(), "RSI 값 중 0 미만이 존재함"
        assert (valid <= 100.0).all(), "RSI 값 중 100 초과가 존재함"

    def test_output_length_equals_input(self):
        """출력 길이 == 입력 길이."""
        data = pd.Series(range(30), dtype=float)
        result = rsi(data, period=14)
        assert len(result) == len(data)

    def test_warmup_is_nan(self):
        """period 미만 구간은 NaN이어야 함 (warmup)."""
        data = pd.Series(range(30), dtype=float)
        result = rsi(data, period=14)
        # 첫 번째 값은 diff() 로 인해 NaN, warmup 포함해 일정 기간 NaN
        # non-NaN 개수가 전체보다 작아야 함
        non_nan_count = result.notna().sum()
        assert non_nan_count < len(data), "warmup 기간 NaN이 없음"

    def test_constant_series_rsi_nan_or_neutral(self):
        """일정한 시리즈 (변동 없음): gain=0, loss=0 → RS=NaN, RSI=NaN or 특수처리."""
        data = pd.Series([100.0] * 30)
        result = rsi(data, period=14)
        # gain=0, loss=0 → avg_loss==0 & avg_gain==0 → overbought_mask False → NaN
        # 모든 값이 NaN 이거나, 일부 non-NaN 은 범위 내
        valid = result.dropna()
        if len(valid) > 0:
            assert (valid >= 0.0).all()
            assert (valid <= 100.0).all()

    def test_index_preserved(self):
        """인덱스가 입력과 동일하게 유지되어야 함."""
        idx = pd.date_range("2024-01-01", periods=30, freq="D")
        data = pd.Series(range(30), dtype=float, index=idx)
        result = rsi(data, period=14)
        assert list(result.index) == list(idx)
