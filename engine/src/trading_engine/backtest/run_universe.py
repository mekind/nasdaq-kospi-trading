"""코스피 시총 상위 유니버스 멀티심볼 백테스트 러너.

분기별 시총 상위 N 유니버스(룩어헤드/생존편향 교정)를 받아, **종목마다 기존 단일종목 엔진을
독립 실행**한다(포트폴리오 아님). 결과는 aggregate 단계에서 멤버십 마스킹 후 분포로 집계한다.

per-symbol try/except로 한 종목 실패가 전체를 멈추지 않게 하고, 실패/스킵 사유를 분류해 센다
(network / empty / short / exception). 최소 이력(min_bars) 미만 종목은 스킵한다.

사용:
    python -m trading_engine.backtest.run_universe --n 200 --sample 30
"""

from __future__ import annotations

import argparse
import os
from collections import Counter
from dataclasses import dataclass

import pandas as pd

from trading_engine.backtest.aggregate import print_report, summarize, to_csv
from trading_engine.backtest.engine import BacktestEngine
from trading_engine.backtest.costs import CostModel
from trading_engine.data.fdr_provider import FdrProvider
from trading_engine.strategy.mean_reversion import MeanReversionStrategy


@dataclass
class PerStockResult:
    """종목 1개 백테스트 결과 + 집계에 필요한 메타."""

    symbol: str
    trades: pd.DataFrame      # entry_date/exit_date/return_pct/pnl/hold_days
    equity_curve: pd.Series
    first_date: pd.Timestamp
    last_date: pd.Timestamp
    first_close: float
    last_close: float
    n_bars: int
    n_jumps_30: int           # 일일 |수익률|>30% 횟수 (분할/권리락 의심 스캐너)


def _count_jumps(close: pd.Series, threshold: float = 0.30) -> int:
    """일일 수익률 절대값이 threshold 초과인 봉 수 (수정주가 미반영 점프 탐지)."""
    r = close.pct_change().abs()
    return int((r > threshold).sum())


def run_one(
    symbol: str,
    provider: FdrProvider,
    strategy: MeanReversionStrategy,
    engine: BacktestEngine,
    start: str | None,
    end: str | None,
    min_bars: int = 250,
) -> tuple[str, PerStockResult | None]:
    """종목 1개를 백테스트한다. 상태 문자열과 결과(or None)를 반환.

    상태: ``"ok"`` / ``"empty"`` / ``"short"``.
    """
    df = provider.load_daily(symbol, start, end)
    if df is None or len(df) == 0:
        return ("empty", None)
    if len(df) < min_bars:
        return ("short", None)

    signals = strategy.generate_signals(df)
    result = engine.run(df, signals, symbol=symbol, strategy_name=strategy.name)
    close = df["close"]
    rec = PerStockResult(
        symbol=symbol,
        trades=result.trades,
        equity_curve=result.equity_curve,
        first_date=df.index[0],
        last_date=df.index[-1],
        first_close=float(close.iloc[0]),
        last_close=float(close.iloc[-1]),
        n_bars=len(df),
        n_jumps_30=_count_jumps(close),
    )
    return ("ok", rec)


def run_universe(
    symbols: list[str],
    provider: FdrProvider,
    strategy: MeanReversionStrategy,
    engine: BacktestEngine,
    start: str | None = None,
    end: str | None = None,
    min_bars: int = 250,
) -> tuple[list[PerStockResult], dict[str, int]]:
    """종목 리스트를 순회하며 독립 백테스트. (결과 리스트, 스킵 사유별 카운트) 반환.

    한 종목의 예외는 삼켜서 사유별로 센다 — 전체 러너가 멈추지 않게.
    """
    results: list[PerStockResult] = []
    skips: Counter = Counter()
    for sym in symbols:
        try:
            status, rec = run_one(sym, provider, strategy, engine, start, end, min_bars)
            if status == "ok" and rec is not None:
                results.append(rec)
            else:
                skips[status] += 1
        except Exception as e:  # noqa: BLE001 — 한 종목 실패 격리
            name = type(e).__name__.lower()
            msg = str(e).lower()
            if any(k in name or k in msg for k in ("connection", "timeout", "http", "url", "ssl")):
                skips["network"] += 1
            else:
                skips["exception"] += 1
    return results, dict(skips)


def _select_symbols(args):
    """(종목 리스트, 멤버십 판정 함수)를 만든다. KRX 로그인(pykrx) 필요.

    - 전체: 분기별 시총 상위 N 유니버스 → all_members + universe.is_member(룩어헤드 없는 마스킹).
    - 표본(--sample): 최근 분기 시총 상위 N개. 파이프라인 검증용이라 마스킹 없이(항상 멤버) 본다.
    """
    from dotenv import load_dotenv

    load_dotenv()  # KRX_ID/KRX_PW (.env)
    from trading_engine.data.market_cap import KrxMarketCap
    from trading_engine.data.universe import QuarterlyUniverse

    mc = KrxMarketCap()
    if args.sample > 0:
        now = pd.Timestamp.now().normalize()
        past = [q for q in QuarterlyUniverse.quarter_ends(args.start, args.end) if pd.Timestamp(q) < now]
        symbols = mc.top_n_at(past[-1], args.sample, args.market)
        return symbols, (lambda s, d: True)  # 표본 스모크: 마스킹 없음
    universe = QuarterlyUniverse(mc, n=args.n, market=args.market).build(args.start, args.end)
    return universe.all_members, universe.is_member


def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="코스피 시총 상위 유니버스 멀티심볼 백테스트")
    p.add_argument("--n", type=int, default=200, help="시총 상위 N (유니버스 크기)")
    p.add_argument("--sample", type=int, default=0, help=">0이면 최근 시총 상위 N 표본만(검증용)")
    p.add_argument("--market", default="KOSPI")
    p.add_argument("--start", default="2014-01-01")
    p.add_argument("--end", default="2026-06-30")
    p.add_argument("--min-bars", type=int, default=250, help="최소 이력 봉 수(미만 스킵)")
    p.add_argument("--sell-tax", type=float, default=0.0018, help="개별주 매도 증권거래세")
    p.add_argument("--commission", type=float, default=0.00015)
    p.add_argument("--slippage-bps", type=float, default=5.0)
    p.add_argument("--cash", type=float, default=10_000_000.0)
    p.add_argument("--outdir", default="output")
    return p.parse_args()


def main() -> None:
    args = _parse_args()

    print(f"[1/3] 유니버스 구성 (시총 상위 {args.sample or args.n}, {args.market})")
    symbols, is_member = _select_symbols(args)
    print(f"      대상 {len(symbols)}종목")

    print("[2/3] 종목별 독립 백테스트")
    provider = FdrProvider()
    strategy = MeanReversionStrategy()
    cost = CostModel(
        commission_rate=args.commission,
        slippage_bps=args.slippage_bps,
        sell_tax_rate=args.sell_tax,  # 개별주 0.18%
    )
    engine = BacktestEngine(initial_cash=args.cash, cost_model=cost)
    results, skips = run_universe(
        symbols, provider, strategy, engine, args.start, args.end, args.min_bars
    )
    print(f"      성공 {len(results)} / 스킵 {sum(skips.values())} {skips}")

    print("[3/3] 분포 집계\n")
    summary = summarize(results, is_member)
    print_report(summary)

    os.makedirs(args.outdir, exist_ok=True)
    csv_path = os.path.join(args.outdir, "universe_per_stock.csv")
    to_csv(summary, csv_path)
    print(f"\n저장: {csv_path}")


if __name__ == "__main__":
    main()
