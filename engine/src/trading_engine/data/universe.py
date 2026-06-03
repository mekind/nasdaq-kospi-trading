"""분기별 시총 상위 N 유니버스(멤버십) 빌더.

룩어헤드/생존편향을 피하기 위해:
- 매 **분기말 시총 스냅샷**으로 상위 N 종목을 정한다(그 시점 당시 순위).
- 어떤 분기의 유니버스는 **직전 분기말 스냅샷**으로 결정해 적용한다(결정 후 적용 → 미래정보 미사용).
- 각 분기 스냅샷은 그 시점에 상장돼 있던 종목만 담으므로, 상폐 종목도 살아있던 분기엔 포함되고
  폐지 후 자동 이탈한다(생존편향 교정).

시총 데이터 소스는 ``mc_provider``(``top_n_at(date, n, market)`` 메서드)로 주입받는다.
실제로는 :class:`trading_engine.data.market_cap.KrxMarketCap`, 테스트에서는 가짜 provider.
"""

from __future__ import annotations

from bisect import bisect_right
from typing import Protocol

import pandas as pd


class MarketCapProvider(Protocol):
    """시총 상위 N 조회 인터페이스."""

    def top_n_at(self, date: str, n: int, market: str = ...) -> list[str]: ...


class QuarterlyUniverse:
    """분기 리밸런싱 시총 상위 N 멤버십.

    사용:
        u = QuarterlyUniverse(KrxMarketCap(), n=200).build("2014-01-01", "2026-06-30")
        u.all_members              # fetch 대상(전 분기 멤버 합집합)
        u.is_member("005930", ts)  # ts 시점 멤버 여부(거래 마스킹용)
    """

    def __init__(
        self,
        mc_provider: MarketCapProvider,
        n: int = 200,
        market: str = "KOSPI",
    ) -> None:
        self.mc = mc_provider
        self.n = n
        self.market = market
        # build() 후 채워짐
        self.snapshot_dates: list[pd.Timestamp] = []
        self.members: list[set[str]] = []
        self.all_members: list[str] = []

    @staticmethod
    def quarter_ends(start: str, end: str) -> list[str]:
        """[start, end] 사이 분기말 달력일 목록(``YYYYMMDD``)."""
        qe = pd.date_range(start=start, end=end, freq="QE")
        return [d.strftime("%Y%m%d") for d in qe]

    def build(self, start: str = "2014-01-01", end: str = "2026-06-30") -> "QuarterlyUniverse":
        """분기말마다 시총 상위 N을 받아 멤버십을 구성한다.

        멤버십 경계 키는 분기말 달력일(Timestamp)을 쓴다. 거래 ``entry_date`` d 에 대해
        **d 직전(<=)의 가장 최근 분기말** 스냅샷의 멤버를 적용한다(직전 분기 결정 → 당분기 적용).
        """
        now = pd.Timestamp.now().normalize()
        snaps = self.quarter_ends(start, end)
        self.snapshot_dates = []
        self.members = []
        for s in snaps:
            # 미래 분기말은 시총 스냅샷을 받을 수 없으므로 건너뛴다.
            if pd.Timestamp(s) >= now:
                continue
            tickers = self.mc.top_n_at(s, self.n, self.market)
            self.snapshot_dates.append(pd.Timestamp(s))
            self.members.append(set(tickers))

        union: set[str] = set()
        for m in self.members:
            union |= m
        self.all_members = sorted(union)
        return self

    def is_member(self, ticker: str, date) -> bool:
        """``date`` 시점에 ``ticker`` 가 유니버스 멤버였는지.

        date 직전(<=)의 가장 최근 분기말 스냅샷 멤버십을 적용한다.
        첫 스냅샷 이전 시점은 멤버 아님(False).
        """
        if not self.snapshot_dates:
            return False
        ts = pd.Timestamp(date)
        # snapshot_dates 는 오름차순. ts 이하인 가장 큰 스냅샷 인덱스.
        idx = bisect_right(self.snapshot_dates, ts) - 1
        if idx < 0:
            return False
        return ticker in self.members[idx]

    def members_at(self, date) -> set[str]:
        """``date`` 시점 적용 멤버 집합(없으면 빈 집합)."""
        if not self.snapshot_dates:
            return set()
        ts = pd.Timestamp(date)
        idx = bisect_right(self.snapshot_dates, ts) - 1
        if idx < 0:
            return set()
        return self.members[idx]
