"""KRX 시점별 시가총액 조회 (pykrx) + parquet 캐시.

pykrx는 KRX 정보데이터시스템 로그인이 필요하다(환경변수 ``KRX_ID`` / ``KRX_PW``).
자격증명은 ``.env``(.gitignore 처리)에 두고, 진입점에서 ``load_dotenv()`` 로 로드한 뒤
이 모듈을 사용한다. pykrx는 import 시 로그인을 시도하므로, **env 로드 후 처음 호출**되도록
pykrx import 를 메서드 안으로 지연시킨다.

시점별 시총은 "그 시점 당시" 순위를 주므로(과거 대형주 ≠ 현재 대형주), 시총 상위 N 유니버스를
구성할 때 룩어헤드/생존편향을 피할 수 있다. 상폐 종목도 상장돼 있던 시점 스냅샷에는 포함된다.
"""

from __future__ import annotations

import os

import pandas as pd


class KrxMarketCap:
    """pykrx 기반 시점별 시가총액 로더 + parquet 캐시.

    Parameters
    ----------
    cache_dir:
        시총 스냅샷 캐시 디렉터리. 날짜·시장별 1파일.
    """

    def __init__(self, cache_dir: str = "data/cache/marketcap") -> None:
        self.cache_dir = cache_dir

    def market_cap_at(
        self, date: str, market: str = "KOSPI", use_cache: bool = True
    ) -> pd.Series:
        """``date`` 시점 종목별 시가총액 Series(index=종목코드, 값=시가총액).

        Parameters
        ----------
        date:
            조회 기준일 ``YYYYMMDD``. 휴장일이면 직전 영업일로 스냅된다.
        market:
            ``"KOSPI"`` / ``"KOSDAQ"`` 등.
        use_cache:
            True면 parquet 캐시 우선. 캐시 미스 시 pykrx fetch 후 저장.
            **빈 데이터/실패는 캐시에 저장하지 않는다**(오염 방지).
        """
        # 영업일 스냅(휴장일 방지)은 pykrx에 의존하므로 fetch 직전에 수행.
        from pykrx import stock  # 지연 import: env 로드 후 로그인되도록

        biz_date = stock.get_nearest_business_day_in_a_week(date, prev=True)

        cache_path = os.path.join(self.cache_dir, f"{market}_{biz_date}.parquet")
        if use_cache and os.path.isfile(cache_path):
            return pd.read_parquet(cache_path)["시가총액"]

        df = stock.get_market_cap_by_ticker(biz_date, market=market)
        if df is None or len(df) == 0 or "시가총액" not in df.columns:
            raise RuntimeError(f"KRX 시총 조회 실패/빈데이터: {market} {biz_date}")

        if use_cache:
            os.makedirs(self.cache_dir, exist_ok=True)
            df.to_parquet(cache_path, engine="pyarrow")

        return df["시가총액"]

    def top_n_at(
        self, date: str, n: int, market: str = "KOSPI", use_cache: bool = True
    ) -> list[str]:
        """``date`` 시점 시가총액 상위 ``n`` 종목코드 리스트(내림차순).

        시총 동률·결측은 정렬에서 자연 처리된다. 종목 수 < n 이면 가능한 만큼 반환.
        """
        mc = self.market_cap_at(date, market=market, use_cache=use_cache)
        mc = mc[mc > 0].sort_values(ascending=False)
        return mc.head(n).index.tolist()
