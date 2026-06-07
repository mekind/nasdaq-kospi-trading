"""배당·분할 수정주가(총수익) 패널 로더 — FinanceDataReader 기반.

기존 ``FdrProvider``는 수정 전 OHLCV만 반환한다(다른 전략과의 호환 유지). 추세추종 같은
장기 전략은 배당 재투자를 반영한 **총수익(수정주가)** 으로 신호·평가를 해야 채권·리츠의
추세가 왜곡되지 않으므로, 이 모듈은 ``Adj Close``를 활용한 수정 OHLC 패널을 별도 제공한다.

수정계수 ``adj = Adj Close / Close`` 를 일별로 구해 시가에도 적용한다
(``adj_open = Open × adj``). 이로써 신호(수정종가)와 체결(수정시가)이 같은 총수익
기준선 위에 놓이면서 next-bar-open 룩어헤드 차단 원칙도 유지된다.
"""

from __future__ import annotations

import os

import FinanceDataReader as fdr
import pandas as pd


def load_adjusted(
    symbol: str,
    start: str | None = None,
    end: str | None = None,
    cache_dir: str = "data/cache_adj",
    use_cache: bool = True,
) -> pd.DataFrame:
    """단일 심볼의 수정 OHLC(총수익) 일봉을 반환한다.

    Args:
        symbol: 티커(예: ``"SPY"``).
        start: 조회 시작일(예: ``"2008-01-01"``). None이면 FDR 기본값.
        end: 조회 종료일. None이면 FDR 기본값.
        cache_dir: parquet 캐시 디렉터리.
        use_cache: True면 캐시 우선, 없으면 fetch 후 저장(빈 데이터는 저장 안 함).

    Returns:
        DatetimeIndex(오름차순) + float 컬럼 ``open, high, low, close``(모두 수정가).
        ``Adj Close``가 없으면 원시 종가를 그대로 사용한다.
    """
    cache_path = os.path.join(cache_dir, f"{symbol}_{start}_{end}.parquet")
    if use_cache and os.path.isfile(cache_path):
        return pd.read_parquet(cache_path)

    raw: pd.DataFrame = fdr.DataReader(symbol, start, end)
    raw.columns = [c.lower() for c in raw.columns]

    close = raw["close"].astype(float)
    # 수정계수: Adj Close가 있으면 총수익 기준, 없으면 1.0(원시가 그대로).
    if "adj close" in raw.columns:
        adj_close = raw["adj close"].astype(float)
        factor = adj_close / close
    else:
        adj_close = close
        factor = pd.Series(1.0, index=raw.index)

    df = pd.DataFrame(
        {
            "open": raw["open"].astype(float) * factor,
            "high": raw["high"].astype(float) * factor,
            "low": raw["low"].astype(float) * factor,
            "close": adj_close,
        }
    )
    df = df.dropna(subset=["open", "high", "low", "close"])
    df.index = pd.to_datetime(df.index)
    df = df.sort_index(ascending=True)

    if use_cache and len(df) > 0:
        os.makedirs(cache_dir, exist_ok=True)
        df.to_parquet(cache_path, engine="pyarrow")

    return df


def load_adjusted_panel(
    symbols: list[str],
    start: str | None = None,
    end: str | None = None,
    cache_dir: str = "data/cache_adj",
    use_cache: bool = True,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """여러 심볼의 수정 시가/종가 패널을 **공통 거래일**로 정렬해 반환한다.

    모든 심볼이 데이터를 가진 구간(교집합)으로 잘라, 어떤 자산도 미상장/결측이 아닌
    상태에서 백테스트가 시작되도록 한다(부분기간 모드는 범위 밖 — plan 결정 6).

    .. warning::
        교집합(``dropna``) 방식이므로 **한 자산이라도 이력이 짧거나 중간 결측이 길면
        전체 백테스트 기간이 그만큼 단축**된다(예: BND 2007-04 상장 → 5자산 공통 시작이
        2007-12경으로 당겨짐). 자산을 추가할 때 가장 짧은 이력이 시작일을 좌우한다.
        또한 ``load_adjusted``는 ``Adj Close``가 없는 심볼에 대해 수정계수를 1.0으로 두므로
        (원시 종가 사용), 분배금이 큰 자산은 추세가 왜곡될 수 있다 — 총수익 가정이 필요한
        전략에는 ``Adj Close``를 제공하는 소스/심볼만 사용할 것.

    Args:
        symbols: 티커 리스트.
        start: 조회 시작일. end: 조회 종료일.
        cache_dir: 캐시 디렉터리. use_cache: 캐시 사용 여부.

    Returns:
        (opens, closes) 튜플. 각각 index=공통 거래일, columns=symbols 순서의 수정가 패널.
    """
    opens_cols: dict[str, pd.Series] = {}
    closes_cols: dict[str, pd.Series] = {}
    for sym in symbols:
        df = load_adjusted(sym, start, end, cache_dir, use_cache)
        opens_cols[sym] = df["open"]
        closes_cols[sym] = df["close"]

    # 모든 심볼이 값을 가진 거래일만(교집합) — how="inner".
    opens = pd.DataFrame(opens_cols).dropna()
    closes = pd.DataFrame(closes_cols).dropna()
    common = opens.index.intersection(closes.index)
    opens = opens.loc[common, symbols]
    closes = closes.loc[common, symbols]
    return opens, closes
