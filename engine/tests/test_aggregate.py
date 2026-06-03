"""aggregate.summarize 의 멤버십 마스킹·분모·분포·분리·crash·스캐너 단위 테스트."""

from __future__ import annotations

import pandas as pd
import pytest

from trading_engine.backtest.aggregate import summarize, to_csv, CSV_GUARD_HEADER
from trading_engine.backtest.run_universe import PerStockResult


def _trades(entries: list[tuple[str, float]]) -> pd.DataFrame:
    return pd.DataFrame({
        "entry_date": [pd.Timestamp(d) for d, _ in entries],
        "exit_date": [pd.Timestamp(d) + pd.Timedelta(days=3) for d, _ in entries],
        "return_pct": [r for _, r in entries],
        "pnl": [r * 1e6 for _, r in entries],
        "hold_days": [3] * len(entries),
    })


def _rec(symbol, entries, last_date="2026-06-01", first_close=100.0, last_close=150.0, jumps=0):
    return PerStockResult(
        symbol=symbol,
        trades=_trades(entries),
        equity_curve=pd.Series(dtype="float64"),
        first_date=pd.Timestamp("2014-03-11"),
        last_date=pd.Timestamp(last_date),
        first_close=first_close,
        last_close=last_close,
        n_bars=3000,
        n_jumps_30=jumps,
    )


# 멤버십: 2018-01-01 이후 진입만 멤버로 인정
def _is_member(symbol, d):
    return pd.Timestamp(d) >= pd.Timestamp("2018-01-01")


@pytest.fixture
def summary():
    results = [
        # A: 2017 거래(+0.50)는 멤버십 밖 → 제외, 2019 거래(+0.10)만 인정 → 수익
        _rec("A", [("2017-06-01", 0.50), ("2019-06-01", 0.10)]),
        # B: COVID(-0.20) + 2021(+0.05) 둘 다 멤버 → 누적 음수
        _rec("B", [("2020-03-01", -0.20), ("2021-01-01", 0.05)]),
        # C: 2016 거래만(+0.30) → 멤버십 밖 → 마스킹 후 무거래
        _rec("C", [("2016-01-01", 0.30)]),
        # D: 비활성(상폐추정, last_date 옛날) + 멤버십 내 손실(-0.30), 점프 2회
        _rec("D", [("2018-06-01", -0.30)], last_date="2019-01-01", jumps=2),
    ]
    return summarize(results, _is_member)


def test_counts(summary):
    assert summary["n_universe"] == 4
    assert summary["n_traded"] == 3        # A, B, D (C는 마스킹 후 무거래)
    assert summary["n_no_trade"] == 1      # C
    assert summary["n_inactive"] == 1      # D


def test_membership_masking_excludes_outside_trades(summary):
    # A의 2017 +0.50이 제외됐으면 누적은 0.10 (0.65 아님)
    a = next(r for r in summary["rows"] if r["symbol"] == "A")
    assert a["n_trades"] == 1
    assert a["compound_return"] == pytest.approx(0.10)


def test_profit_denominators(summary):
    # 수익난 종목: A만 (B 누적 -0.16, D -0.30)
    assert summary["pct_profit_among_traded"] == pytest.approx(1 / 3)
    assert summary["pct_profit_among_all"] == pytest.approx(1 / 4)


def test_survivor_inactive_split(summary):
    sv = summary["survivor_vs_inactive"]
    assert sv["survivor"]["n"] == 2        # A, B
    assert sv["inactive"]["n"] == 1        # D
    assert sv["inactive"]["median"] == pytest.approx(-0.30)


def test_crash_cross_section_is_return_based(summary):
    covid = summary["crash"]["2020_COVID"]
    assert covid["n_trades"] == 1          # B의 2020-03-01
    assert covid["median"] == pytest.approx(-0.20)
    assert covid["win_rate"] == pytest.approx(0.0)


def test_jump_scanner(summary):
    jo = summary["jump_offenders"]
    assert [d["symbol"] for d in jo] == ["D"]


def test_csv_has_guard_and_no_won_pnl(summary, tmp_path):
    path = tmp_path / "per_stock.csv"
    to_csv(summary, str(path))
    text = path.read_text(encoding="utf-8")
    assert text.startswith(CSV_GUARD_HEADER)
    # 원화 손익 합산 오해 방지 — pnl 컬럼은 출력하지 않음
    header_line = text.splitlines()[1]
    assert "pnl" not in header_line
    assert "compound_return" in header_line


def test_empty_results():
    assert summarize([], _is_member)["n_universe"] == 0
