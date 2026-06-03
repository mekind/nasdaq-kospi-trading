"""FinanceDataReader 기반 일봉 OHLCV 로더 + 로컬 parquet 캐시."""

from __future__ import annotations

import os

import FinanceDataReader as fdr
import pandas as pd


class FdrProvider:
    """FinanceDataReader 기반 일봉 로더 + 로컬 parquet 캐시.

    Parameters
    ----------
    cache_dir:
        parquet 캐시 파일을 저장할 디렉터리 경로. 기본값은 ``"data/cache"``.
    """

    def __init__(self, cache_dir: str = "data/cache") -> None:
        self.cache_dir = cache_dir

    def load_daily(
        self,
        symbol: str,
        start: str | None = None,
        end: str | None = None,
        use_cache: bool = True,
    ) -> pd.DataFrame:
        """일봉 OHLCV를 반환. 표준 스키마(DatetimeIndex + open/high/low/close/volume).

        Parameters
        ----------
        symbol:
            종목 코드 또는 티커 (예: ``"069500"``, ``"AAPL"``).
        start:
            조회 시작일 문자열 (예: ``"2023-01-01"``). ``None`` 이면 FDR 기본값 사용.
        end:
            조회 종료일 문자열 (예: ``"2023-12-31"``). ``None`` 이면 FDR 기본값 사용.
        use_cache:
            ``True`` 이면 parquet 캐시를 우선 사용. 캐시가 없으면 FDR에서 fetch 후 저장.

        Returns
        -------
        pd.DataFrame
            DatetimeIndex(오름차순) + float 컬럼 ``open, high, low, close, volume``.
            ``close`` 가 NaN인 행은 제거됨.
        """
        # 캐시 파일 경로 결정
        cache_path = os.path.join(self.cache_dir, f"{symbol}_{start}_{end}.parquet")

        # 캐시 히트: 파일이 존재하면 바로 반환
        if use_cache and os.path.isfile(cache_path):
            return pd.read_parquet(cache_path)

        # FDR에서 데이터 fetch
        raw: pd.DataFrame = fdr.DataReader(symbol, start, end)

        # 컬럼 정규화: 대문자 → 소문자
        raw.columns = [c.lower() for c in raw.columns]

        # 필요한 컬럼만 선택 (Volume 없으면 0.0으로 채움)
        if "volume" not in raw.columns:
            raw["volume"] = 0.0

        df = raw[["open", "high", "low", "close", "volume"]].copy()

        # dtype 강제 float 변환
        df = df.astype(float)

        # 거래량 결측은 0으로 채움 (체결 시뮬레이션에 영향 없음).
        df["volume"] = df["volume"].fillna(0.0)

        # OHLC 중 하나라도 결측인 봉은 제거.
        # 백테스트 엔진은 next-bar 시가(open)로 체결하므로 open/high/low/close가 모두 필요하다.
        # 장기 지수(예: KS200) 선두 구간은 '종가만' 존재하는 경우가 있어, 이를 남겨두면
        # 체결가가 NaN이 되어 포지션·자산곡선 전체가 NaN으로 오염된다(룩어헤드 아닌 데이터 결측 버그).
        df = df.dropna(subset=["open", "high", "low", "close"])

        # 인덱스를 DatetimeIndex로 보장 후 오름차순 정렬
        df.index = pd.to_datetime(df.index)
        df = df.sort_index(ascending=True)

        # 캐시 저장 — 단, **빈 데이터는 저장하지 않는다**(불완전 캐시 오염 방지).
        # 다수 종목 일괄 수집 시, 실패/상폐로 0행이 나온 종목을 캐시에 남기면
        # 이후 실행이 그 빈 캐시를 무비용 재사용하며 조용히 잘못된 결과를 낸다.
        if use_cache and len(df) > 0:
            os.makedirs(self.cache_dir, exist_ok=True)
            df.to_parquet(cache_path, engine="pyarrow")

        return df


if __name__ == "__main__":
    # 수동 확인용: KODEX 200 ETF (069500) 최근 데이터 출력
    provider = FdrProvider(cache_dir="data/cache")
    df = provider.load_daily("069500", start="2024-01-01")
    print(df.tail())
