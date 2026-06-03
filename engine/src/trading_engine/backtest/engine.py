"""백테스트 엔진 - 시그널 기반 일봉 체결 시뮬레이션.

롱/플랫 단일 포지션, 전액 투입(all-in), 익일 시가(next-bar-open) 체결 모델.
look-ahead(미래 정보 참조) 방지를 위해 시그널은 항상 다음 봉의 시가에 체결된다.
"""

from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

from trading_engine.backtest.costs import CostModel

# 거래 내역 DataFrame 컬럼 정의 (거래가 없을 때도 동일 스키마 유지).
TRADE_COLUMNS = [
    "entry_date",
    "entry_price",
    "exit_date",
    "exit_price",
    "qty",
    "pnl",
    "return_pct",
    "hold_days",
]


@dataclass
class BacktestResult:
    """백테스트 실행 결과.

    Attributes:
        strategy: 전략 이름.
        symbol: 종목 코드/심볼.
        initial_cash: 초기 투자 원금.
        final_equity: 종료 시점 총 자산 (equity_curve의 마지막 값).
        equity_curve: df.index를 인덱스로 갖는 일별 총 자산 시계열.
        trades: 거래 내역 DataFrame (TRADE_COLUMNS 컬럼).
    """

    strategy: str
    symbol: str
    initial_cash: float
    final_equity: float
    equity_curve: pd.Series
    trades: pd.DataFrame


class BacktestEngine:
    """시그널 기반 롱/플랫 백테스트 엔진."""

    def __init__(
        self,
        initial_cash: float = 10_000_000.0,
        cost_model: CostModel | None = None,
    ) -> None:
        """엔진을 초기화한다.

        Args:
            initial_cash: 초기 투자 원금.
            cost_model: 비용 모델. None이면 기본 CostModel을 사용.
        """
        self.initial_cash = initial_cash
        self.cost_model = cost_model if cost_model is not None else CostModel()

    def run(
        self,
        df: pd.DataFrame,
        signals: pd.Series,
        symbol: str = "",
        strategy_name: str = "",
    ) -> BacktestResult:
        """시그널을 봉 데이터에 대해 시뮬레이션한다.

        체결 모델:
        - 매 봉 i에서 시그널을 읽되, 체결은 다음 봉 i+1의 시가에서 일어난다.
        - i+1 >= n 이면 체결 불가(시그널 무시) → 시리즈 끝단 look-ahead 방지.
        - 일별 평가금은 봉 i에 예약된 체결을 먼저 처리한 뒤 종가로 산정한다.

        Args:
            df: 오름차순 DatetimeIndex, open/high/low/close/volume 컬럼.
            signals: df.index와 정렬된 "buy"/"sell"/"hold" 시리즈.
            symbol: 종목 심볼.
            strategy_name: 전략 이름.

        Returns:
            BacktestResult.
        """
        cost = self.cost_model
        n = len(df)

        opens = df["open"]
        closes = df["close"]
        index = df.index

        cash = self.initial_cash
        in_position = False
        qty = 0.0
        entry_price = 0.0
        entry_date = None
        entry_notional = 0.0
        entry_fee = 0.0

        # 다음 봉에 체결할 예약 주문: None 또는 "buy"/"sell".
        pending: str | None = None

        equity_list: list[float] = []
        trades: list[dict] = []

        for i in range(n):
            # ── 1) 봉 i에 예약된 주문(직전 봉 시그널)을 봉 i의 시가에 체결 ──────
            if pending is not None:
                raw_open = float(opens.iloc[i])
                if pending == "buy" and not in_position:
                    price = cost.effective_buy_price(raw_open)
                    qty = cash / price
                    entry_notional = qty * price
                    entry_fee = cost.commission(entry_notional)
                    cash -= entry_notional + entry_fee
                    in_position = True
                    entry_price = price
                    entry_date = index[i]
                elif pending == "sell" and in_position:
                    price = cost.effective_sell_price(raw_open)
                    exit_notional = qty * price
                    fee = cost.commission(exit_notional)
                    tax = cost.sell_tax(exit_notional)
                    cash += exit_notional - fee - tax
                    pnl = (exit_notional - fee - tax) - (entry_notional + entry_fee)
                    return_pct = pnl / (entry_notional + entry_fee)
                    hold_days = (index[i] - entry_date).days
                    trades.append(
                        {
                            "entry_date": entry_date,
                            "entry_price": entry_price,
                            "exit_date": index[i],
                            "exit_price": price,
                            "qty": qty,
                            "pnl": pnl,
                            "return_pct": return_pct,
                            "hold_days": hold_days,
                        }
                    )
                    in_position = False
                    qty = 0.0
                pending = None

            # ── 2) 봉 i의 종가로 일별 평가금 산정 ───────────────────────────────
            equity_i = cash + (qty * float(closes.iloc[i]) if in_position else 0.0)
            equity_list.append(equity_i)

            # ── 3) 봉 i의 시그널을 읽어 다음 봉 체결을 예약 ─────────────────────
            #     i+1 >= n 이면 체결할 다음 봉이 없으므로 예약하지 않는다(look-ahead 방지).
            if i + 1 < n:
                action = signals.iloc[i]
                if action == "buy" and not in_position:
                    pending = "buy"
                elif action == "sell" and in_position:
                    pending = "sell"

        # ── 4) 루프 종료 후 잔여 포지션 강제 청산 (마지막 봉 종가 기준) ─────────
        if in_position and n > 0:
            last_i = n - 1
            raw_close = float(closes.iloc[last_i])
            price = cost.effective_sell_price(raw_close)
            exit_notional = qty * price
            fee = cost.commission(exit_notional)
            tax = cost.sell_tax(exit_notional)
            cash += exit_notional - fee - tax
            pnl = (exit_notional - fee - tax) - (entry_notional + entry_fee)
            return_pct = pnl / (entry_notional + entry_fee)
            hold_days = (index[last_i] - entry_date).days
            trades.append(
                {
                    "entry_date": entry_date,
                    "entry_price": entry_price,
                    "exit_date": index[last_i],
                    "exit_price": price,
                    "qty": qty,
                    "pnl": pnl,
                    "return_pct": return_pct,
                    "hold_days": hold_days,
                }
            )
            in_position = False
            qty = 0.0
            # 강제 청산은 마지막 봉 평가금을 현금화하므로 마지막 equity를 갱신.
            equity_list[last_i] = cash

        equity_curve = pd.Series(equity_list, index=index, dtype="float64")
        final_equity = float(equity_curve.iloc[-1]) if n > 0 else self.initial_cash

        if trades:
            trades_df = pd.DataFrame(trades, columns=TRADE_COLUMNS)
        else:
            trades_df = pd.DataFrame(columns=TRADE_COLUMNS)

        return BacktestResult(
            strategy=strategy_name,
            symbol=symbol,
            initial_cash=self.initial_cash,
            final_equity=final_equity,
            equity_curve=equity_curve,
            trades=trades_df,
        )
