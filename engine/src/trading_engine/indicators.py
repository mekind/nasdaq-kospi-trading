"""기술적 지표 계산 모듈.

순수 함수로 구현되며 부작용 없음.
"""

import pandas as pd


def sma(series: pd.Series, window: int) -> pd.Series:
    """단순이동평균 = rolling mean.

    Args:
        series: 가격 시계열 데이터.
        window: 이동평균 기간.

    Returns:
        rolling mean pd.Series (입력과 동일 인덱스).
    """
    return series.rolling(window).mean()


def rsi(series: pd.Series, period: int = 14) -> pd.Series:
    """Wilder's RSI (0~100).

    Wilder 스무딩(EWM alpha=1/period)을 사용한 RSI 계산.
    warmup 기간(period 미만) 구간은 NaN 유지.
    avg_loss == 0 이고 avg_gain > 0 인 경우 RSI = 100.

    Args:
        series: 가격 시계열 데이터.
        period: RSI 계산 기간 (기본값 14).

    Returns:
        RSI pd.Series (0~100 범위, 입력과 동일 인덱스).
    """
    delta = series.diff()

    # 상승분과 하락분 분리
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)

    # Wilder 스무딩: EWM alpha=1/period, adjust=False
    avg_gain = gain.ewm(alpha=1 / period, adjust=False, min_periods=period).mean()
    avg_loss = loss.ewm(alpha=1 / period, adjust=False, min_periods=period).mean()

    rs = avg_gain / avg_loss

    # RSI 계산: avg_loss==0 이고 avg_gain>0 → RSI=100
    out = 100 - 100 / (1 + rs)

    # avg_loss == 0, avg_gain > 0 인 경우 RSI = 100 (division by zero 처리)
    overbought_mask = (avg_loss == 0) & (avg_gain > 0)
    out = out.where(~overbought_mask, other=100.0)

    return out
