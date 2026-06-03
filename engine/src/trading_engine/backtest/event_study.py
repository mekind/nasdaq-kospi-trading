"""모드 A — 실적 이벤트 스터디 (CAAR).

백테스트 엔진(단일 포지션)을 거치지 않고, 실적 발표 이벤트 후 **시장조정 누적초과수익
(Cumulative Average Abnormal Return)** 을 집계해 PEAD 알파의 존재 여부를 편향 최소로 본다.
이것이 본격 전략 구현(모드 B) 전의 GO/NO-GO 게이트다 (계획 docs/plan/2026-06-03-earnings-pead.md).

룩어헤드 차단: CAR은 이벤트 가용일(접수일 다음 거래일) **다음 날부터** 누적한다.
발표 당일 점프는 실거래로 잡을 수 없으므로 제외하고, "공개 후에도 남는 드리프트"만 측정한다.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import pandas as pd

from trading_engine.data.earnings import EarningsEvent

DEFAULT_HORIZONS = (1, 5, 10, 20, 40, 60)


def daily_returns(close: pd.Series) -> pd.Series:
    """종가 시계열의 일간 단순수익률."""
    return close.pct_change()


def abnormal_returns(stock_close: pd.Series, market_close: pd.Series) -> pd.Series:
    """시장조정 초과수익 = 종목 수익률 − 시장(지수) 수익률.

    공통 거래일에 정렬해 계산한다(market-adjusted model: beta=1 가정, 단순·견고).
    """
    common = stock_close.index.intersection(market_close.index)
    rs = daily_returns(stock_close.loc[common])
    rm = daily_returns(market_close.loc[common])
    return (rs - rm).dropna()


def car_for_event(
    abn_ret: pd.Series,
    entry_date: pd.Timestamp,
    horizons: tuple[int, ...] = DEFAULT_HORIZONS,
) -> dict[int, float | None]:
    """단일 이벤트의 누적초과수익(CAR)을 지평선별로 계산.

    ``entry_date`` 가용일(접수일 다음 거래일) 기준, **다음 거래일부터 h일** 초과수익 합.
    데이터가 부족하면 해당 지평선은 None.
    """
    idx = abn_ret.index
    pos_arr = idx.get_indexer([entry_date])
    pos = int(pos_arr[0])
    out: dict[int, float | None] = {}
    if pos < 0:  # 가용일이 초과수익 인덱스에 없음
        return {h: None for h in horizons}
    for h in horizons:
        start = pos + 1
        end = pos + 1 + h
        if end > len(abn_ret):
            out[h] = None
        else:
            out[h] = float(abn_ret.iloc[start:end].sum())
    return out


@dataclass
class CaarStat:
    """한 지평선의 CAAR 통계."""

    horizon: int
    n: int
    caar: float  # 평균 누적초과수익
    t_stat: float  # caar / (std/sqrt(n))


def caar(
    event_cars: list[dict[int, float | None]],
    horizons: tuple[int, ...] = DEFAULT_HORIZONS,
) -> dict[int, CaarStat]:
    """이벤트별 CAR들을 지평선별로 평균내어 CAAR + t값 산출.

    t값 = 평균 / (표본표준편차 / sqrt(n)). n<2면 t=0.
    """
    out: dict[int, CaarStat] = {}
    for h in horizons:
        vals = [c[h] for c in event_cars if c.get(h) is not None]
        n = len(vals)
        if n == 0:
            out[h] = CaarStat(h, 0, 0.0, 0.0)
            continue
        mean = sum(vals) / n
        if n < 2:
            out[h] = CaarStat(h, n, mean, 0.0)
            continue
        var = sum((v - mean) ** 2 for v in vals) / (n - 1)
        std = math.sqrt(var)
        t = 0.0 if std == 0 else mean / (std / math.sqrt(n))
        out[h] = CaarStat(h, n, mean, t)
    return out


def compute_event_cars(
    events: list[EarningsEvent],
    price_map: dict[str, pd.Series],
    market_close: pd.Series,
    horizons: tuple[int, ...] = DEFAULT_HORIZONS,
) -> list[tuple[EarningsEvent, dict[int, float | None]]]:
    """신호와 무관하게 **모든 유효 이벤트의 CAR을 한 번** 계산해 둔다.

    스윕(여러 신호 설정 비교) 시 이벤트별 CAR을 재계산하지 않도록 분리한 함수.
    종목별 초과수익 시계열은 1회만 계산해 캐시한다.
    """
    abn_cache: dict[str, pd.Series] = {}
    out: list[tuple[EarningsEvent, dict[int, float | None]]] = []
    for ev in events:
        if ev.avail_date is None:
            continue
        close = price_map.get(ev.stock_code)
        if close is None:
            continue
        if ev.stock_code not in abn_cache:
            abn_cache[ev.stock_code] = abnormal_returns(close, market_close)
        out.append((ev, car_for_event(abn_cache[ev.stock_code], ev.avail_date, horizons)))
    return out


def caar_for_signal(
    event_cars: list[tuple[EarningsEvent, dict[int, float | None]]],
    signal_fn,
    horizons: tuple[int, ...] = DEFAULT_HORIZONS,
) -> dict[int, CaarStat]:
    """사전 계산된 (event, CAR) 목록에서 signal 통과분만 모아 CAAR 산출."""
    cars = [c for ev, c in event_cars if signal_fn(ev)]
    return caar(cars, horizons)


def run_event_study(
    events: list[EarningsEvent],
    price_map: dict[str, pd.Series],
    market_close: pd.Series,
    signal_fn,
    horizons: tuple[int, ...] = DEFAULT_HORIZONS,
) -> dict[int, CaarStat]:
    """이벤트 집합에 대해 시그널 통과 건만 모아 CAAR을 계산.

    Parameters
    ----------
    events:
        ``avail_date`` 가 설정된 EarningsEvent 목록.
    price_map:
        ``{stock_code: 종가 Series}`` (DatetimeIndex).
    market_close:
        시장지수(예: KOSPI) 종가 Series.
    signal_fn:
        ``EarningsEvent -> bool``. 진입 대상(예: EPS YoY ≥ 임계)만 True.
    """
    event_cars: list[dict[int, float | None]] = []
    for ev in events:
        if ev.avail_date is None or not signal_fn(ev):
            continue
        close = price_map.get(ev.stock_code)
        if close is None:
            continue
        abn = abnormal_returns(close, market_close)
        event_cars.append(car_for_event(abn, ev.avail_date, horizons))
    return caar(event_cars, horizons)


# ── 기본 시그널 (계획 기본 파라미터) ─────────────────────────────────────────
def eps_yoy_signal(threshold: float = 0.20):
    """EPS YoY ≥ threshold 인 이벤트만 통과시키는 signal_fn 팩토리."""

    def _fn(ev: EarningsEvent) -> bool:
        v = ev.yoy.get("eps")
        return v is not None and v >= threshold

    return _fn


def composite_yoy_signal(specs: tuple[tuple[str, float], ...], mode: str = "all"):
    """복합 YoY 신호 팩토리.

    Parameters
    ----------
    specs:
        ``((field, threshold), ...)`` 예: ``(("eps", 0.2), ("revenue", 0.0))``.
        field ∈ {revenue, operating_income, net_income, eps}.
    mode:
        ``"all"`` 모든 조건 충족 / ``"any"`` 하나라도 충족. None 값은 미충족 취급.
    """
    if mode not in ("all", "any"):
        raise ValueError("mode must be 'all' or 'any'")

    def _fn(ev: EarningsEvent) -> bool:
        results = []
        for field, th in specs:
            v = ev.yoy.get(field)
            results.append(v is not None and v >= th)
        return all(results) if mode == "all" else any(results)

    return _fn
