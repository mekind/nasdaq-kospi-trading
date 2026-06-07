"""Faber 자산군 추세추종(Asset Class Trend-Following) — 시계열 모멘텀 TAA.

Mebane Faber, "A Quantitative Approach to Tactical Asset Allocation"의 단순 규칙을 재현한다:
각 자산을 동일비중 슬롯(기본 1/N)으로 두되, **수정종가가 10개월 단순이동평균 위일 때만 보유**,
아니면 그 슬롯은 현금으로 둔다. 매월말 결정한다.

이 모듈은 신호→**목표비중 dict**만 산출한다(엔진 바깥). 체결·비용은 PortfolioBacktestEngine 담당.
"""

from __future__ import annotations

import pandas as pd


class AssetClassTrendFollowing:
    """자산군 추세추종 전략 (월별 10개월 SMA 필터, 동일비중 슬롯)."""

    name = "faber_asset_class_trend"

    def __init__(self, assets: list[str], sma_months: int = 10) -> None:
        """전략 초기화.

        Args:
            assets: 대상 자산 심볼 리스트. 슬롯 비중 = 1/len(assets).
            sma_months: 추세필터 이동평균 개월 수(기본 10).
        """
        if not assets:
            raise ValueError("assets must be non-empty")
        self.assets = list(assets)
        self.sma_months = sma_months
        self.slot_weight = 1.0 / len(assets)

    @staticmethod
    def month_end_rows(daily_close: pd.DataFrame) -> pd.DataFrame:
        """일별 종가 패널에서 **각 월의 마지막 거래일** 행만 추출한다.

        달력 월말이 아니라 실제 거래일을 쓰므로 결정일이 daily index에 존재하게 된다
        (엔진이 그 다음 거래일 시가에 체결할 수 있도록).

        Args:
            daily_close: index=거래일(오름차순 DatetimeIndex), columns=자산.

        Returns:
            월말 거래일만 남긴 종가 패널.
        """
        idx = daily_close.index
        # (연, 월)이 다음 행에서 바뀌는 지점 = 그 달의 마지막 거래일.
        ym = pd.Series(idx.year * 100 + idx.month, index=idx)
        is_month_end = ym != ym.shift(-1)
        return daily_close.loc[is_month_end.to_numpy()]

    def generate_weights(
        self, daily_close: pd.DataFrame
    ) -> dict[pd.Timestamp, dict[str, float]]:
        """월말마다 자산별 목표비중 dict를 산출한다.

        규칙: 월말 수정종가 > 10개월 SMA(월말 종가 기준) → 슬롯 비중(1/N), 아니면 0(현금).
        SMA 워밍업(이력 < sma_months) 구간은 NaN → 미보유(현금).

        룩어헤드 차단: 각 월말의 SMA는 그 월말까지의 월말 종가만 사용한다.

        Args:
            daily_close: 수정종가 일별 패널. columns에 self.assets가 포함되어야 한다.

        Returns:
            {월말 거래일: {심볼: 목표비중}}. 보유 자산이 없는 달도 빈 dict로 포함.
        """
        monthly = self.month_end_rows(daily_close[self.assets])
        sma = monthly.rolling(self.sma_months).mean()
        # 워밍업 구간(이력 < sma_months)은 SMA가 NaN → 비교 결과 False(의도된 동작).
        # pandas에서 `값 > NaN`은 항상 False이므로 해당 월은 자동으로 미보유(현금)가 된다.
        above = monthly > sma

        weights: dict[pd.Timestamp, dict[str, float]] = {}
        for ts in monthly.index:
            row = above.loc[ts]
            w = {a: self.slot_weight for a in self.assets if bool(row[a])}
            weights[ts] = w
        return weights
