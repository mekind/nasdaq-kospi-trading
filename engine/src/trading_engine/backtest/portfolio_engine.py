"""다자산 포트폴리오 백테스트 엔진 — 목표비중 기반 리밸런싱 시뮬레이션.

단일종목 ``BacktestEngine``(롱/플랫·스칼라 상태)과 달리, 자산별 **목표비중 벡터**를
입력받아 통합 자산곡선을 산출한다. 책임은 "목표비중 → 체결·현금흐름·회전율" 변환뿐이며,
신호→비중 결정은 엔진 바깥(strategy)에 둔다.

룩어헤드 차단: 비중 결정은 결정일(월말) 종가로 하되, **체결은 항상 다음 봉의 시가**에서
일어난다. 결정일 i에 예약된 리밸런싱은 i+1 시가에 일괄 집행한다(매도→현금→매수).
"""

from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

from trading_engine.backtest.costs import CostModel


@dataclass
class PortfolioBacktestResult:
    """포트폴리오 백테스트 결과.

    Attributes:
        initial_cash: 초기 원금.
        final_equity: 종료 시점 총자산(equity_curve 마지막 값).
        equity_curve: 일별 총자산(현금 + 평가금) 시계열.
        rebalance_log: 리밸런싱별 회전율·비용·목표비중 로그 DataFrame.
    """

    initial_cash: float
    final_equity: float
    equity_curve: pd.Series
    rebalance_log: pd.DataFrame


REBALANCE_LOG_COLUMNS = ["exec_date", "turnover", "cost", "n_positions"]


class PortfolioBacktestEngine:
    """목표비중 기반 다자산 롱온리 백테스트 엔진."""

    def __init__(
        self,
        initial_cash: float = 10_000_000.0,
        cost_model: CostModel | None = None,
    ) -> None:
        """엔진 초기화.

        Args:
            initial_cash: 초기 투자 원금.
            cost_model: 비용 모델. None이면 기본 CostModel(ETF 가정: 매도세 0).
        """
        self.initial_cash = initial_cash
        self.cost_model = cost_model if cost_model is not None else CostModel()

    def run(
        self,
        opens: pd.DataFrame,
        closes: pd.DataFrame,
        target_weights: dict[pd.Timestamp, dict[str, float]],
    ) -> PortfolioBacktestResult:
        """목표비중 스케줄을 가격 패널에 대해 시뮬레이션한다.

        체결 모델:
        - 결정일(target_weights의 키, 보통 월말 거래일)에 비중을 읽되, 체결은 **다음 거래일
          시가**에서 일어난다(룩어헤드 차단).
        - 리밸런싱은 현 보유를 목표비중으로 맞추는 것: 자산별 Δ수량을 다음 봉 시가에 체결하고
          슬리피지·수수료를 차감한다(ETF 매도세 0).
        - 일별 평가금은 그날 예약된 체결을 먼저 처리한 뒤 종가로 산정한다.

        Args:
            opens: 시가 패널. index=거래일(오름차순), columns=자산 심볼.
            closes: 종가 패널. opens와 동일 index/columns로 정렬되어 있어야 한다.
            target_weights: {결정일: {심볼: 목표비중}}. 비중 합 ≤ 1.0(잔여는 현금).
                            결정일은 opens.index에 존재하는 거래일이어야 한다.

        Returns:
            PortfolioBacktestResult.
        """
        cost = self.cost_model
        assets = list(opens.columns)
        index = opens.index
        n = len(index)

        cash = self.initial_cash
        qty: dict[str, float] = {a: 0.0 for a in assets}

        # 다음 봉에 집행할 예약 목표비중(없으면 None).
        pending: dict[str, float] | None = None

        equity_list: list[float] = []
        rebal_rows: list[dict] = []

        for i in range(n):
            # ── 1) 예약된 리밸런싱을 봉 i의 시가에 집행 ────────────────────────────
            if pending is not None:
                row_open = opens.iloc[i]
                # 집행 직전 평가금(원시 시가 기준) = 현금 + 보유 평가.
                equity_at_open = cash + sum(
                    qty[a] * float(row_open[a])
                    for a in assets
                    if not pd.isna(row_open[a])
                )

                turnover_notional = 0.0
                total_cost = 0.0
                n_pos = 0

                for a in assets:
                    raw_open = float(row_open[a])
                    if pd.isna(raw_open) or raw_open <= 0.0:
                        continue  # 가격 없는 자산은 거래 불가(보유 유지).
                    w = pending.get(a, 0.0)
                    if w > 0.0:
                        n_pos += 1
                    target_notional = w * equity_at_open
                    target_qty = target_notional / raw_open
                    delta_qty = target_qty - qty[a]
                    if delta_qty > 0:  # 매수
                        price = cost.effective_buy_price(raw_open)
                        notional = delta_qty * price
                        fee = cost.commission(delta_qty * raw_open)
                        cash -= notional + fee
                        total_cost += fee
                    elif delta_qty < 0:  # 매도
                        price = cost.effective_sell_price(raw_open)
                        notional = (-delta_qty) * price
                        fee = cost.commission((-delta_qty) * raw_open)
                        tax = cost.sell_tax((-delta_qty) * raw_open)
                        cash += notional - fee - tax
                        total_cost += fee + tax
                    qty[a] = target_qty
                    turnover_notional += abs(delta_qty) * raw_open

                turnover = (
                    turnover_notional / equity_at_open if equity_at_open > 0 else 0.0
                )
                rebal_rows.append(
                    {
                        "exec_date": index[i],
                        "turnover": turnover,
                        "cost": total_cost,
                        "n_positions": n_pos,
                    }
                )
                pending = None

            # ── 2) 봉 i 종가로 일별 평가금 산정 ───────────────────────────────────
            row_close = closes.iloc[i]
            equity_i = cash + sum(
                qty[a] * float(row_close[a])
                for a in assets
                if not pd.isna(row_close[a])
            )
            equity_list.append(equity_i)

            # ── 3) 봉 i가 결정일이면 다음 봉 집행을 예약 ──────────────────────────
            #     i+1 >= n 이면 집행할 다음 봉이 없으므로 예약하지 않는다(룩어헤드 방지).
            ts = index[i]
            if ts in target_weights and i + 1 < n:
                pending = target_weights[ts]

        equity_curve = pd.Series(equity_list, index=index, dtype="float64")
        final_equity = float(equity_curve.iloc[-1]) if n > 0 else self.initial_cash

        if rebal_rows:
            rebal_df = pd.DataFrame(rebal_rows, columns=REBALANCE_LOG_COLUMNS)
        else:
            rebal_df = pd.DataFrame(columns=REBALANCE_LOG_COLUMNS)

        return PortfolioBacktestResult(
            initial_cash=self.initial_cash,
            final_equity=final_equity,
            equity_curve=equity_curve,
            rebalance_log=rebal_df,
        )
