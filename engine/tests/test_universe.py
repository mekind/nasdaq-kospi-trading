"""QuarterlyUniverse 멤버십·룩어헤드 방지·생존편향 교정 단위 테스트.

가짜 시총 provider를 주입해 네트워크/KRX 로그인 없이 멤버십 로직만 검증한다.
"""

from __future__ import annotations

import pandas as pd

from trading_engine.data.universe import QuarterlyUniverse


class FakeMC:
    """date(YYYYMMDD) -> 시총 내림차순 종목 리스트 매핑을 돌려주는 가짜 provider."""

    def __init__(self, mapping: dict[str, list[str]]) -> None:
        self.mapping = mapping
        self.calls: list[str] = []

    def top_n_at(self, date: str, n: int, market: str = "KOSPI") -> list[str]:
        self.calls.append(date)
        return self.mapping[date][:n]


# 2014년 4개 분기. C는 Q2에 탈락(상폐 가정), D는 Q2 진입, B는 Q4 탈락, E는 Q4 진입.
MAPPING = {
    "20140331": ["A", "B", "C"],
    "20140630": ["A", "B", "D"],
    "20140930": ["A", "B", "D"],
    "20141231": ["A", "E", "D"],
}


def _built(n: int = 3) -> QuarterlyUniverse:
    return QuarterlyUniverse(FakeMC(MAPPING), n=n).build("2014-01-01", "2014-12-31")


def test_quarter_ends():
    qe = QuarterlyUniverse.quarter_ends("2014-01-01", "2014-12-31")
    assert qe == ["20140331", "20140630", "20140930", "20141231"]


def test_all_members_is_union():
    u = _built()
    assert u.all_members == ["A", "B", "C", "D", "E"]


def test_membership_applies_after_snapshot_no_lookahead():
    u = _built()
    # 첫 스냅샷(03-31) 이전 → 아무도 멤버 아님
    assert u.is_member("A", "2014-02-15") is False
    # Q2 구간(03-31 이후 ~ 06-30 전): 03-31 스냅샷[A,B,C] 적용
    assert u.is_member("C", "2014-04-15") is True
    assert u.is_member("D", "2014-04-15") is False  # D는 아직 미진입(미래정보 미사용)
    # Q3 구간(06-30 이후): 06-30 스냅샷[A,B,D] 적용
    assert u.is_member("D", "2014-07-15") is True
    assert u.is_member("C", "2014-07-15") is False  # C는 이미 탈락


def test_survivorship_delisted_member_only_while_listed():
    u = _built()
    # C(상폐 가정)는 Q2 구간에만 멤버. 이후엔 영구 비멤버.
    assert u.is_member("C", "2014-04-15") is True
    assert u.is_member("C", "2014-08-15") is False
    assert u.is_member("C", "2014-12-31") is False


def test_top_n_cut_passed_through():
    # n=2 면 각 분기 상위 2개만 → C/D 등 3번째는 제외
    u = QuarterlyUniverse(FakeMC(MAPPING), n=2).build("2014-01-01", "2014-12-31")
    assert "C" not in u.all_members  # 03-31 상위2 = [A,B]
    assert u.is_member("B", "2014-04-15") is True
    assert u.is_member("C", "2014-04-15") is False


def test_members_at_matches_is_member():
    u = _built()
    assert u.members_at("2014-04-15") == {"A", "B", "C"}
    assert u.members_at("2014-07-15") == {"A", "B", "D"}
    assert u.members_at("2014-02-15") == set()


def test_snapshot_boundary_inclusive():
    u = _built()
    # 스냅샷 당일(06-30)은 그 스냅샷 적용(<=)
    assert u.is_member("D", pd.Timestamp("2014-06-30")) is True
