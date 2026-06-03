"""거래 비용 모델 - 수수료, 슬리피지, 증권거래세를 캡슐화."""

from dataclasses import dataclass


@dataclass
class CostModel:
    """매매 비용 모델.

    Attributes:
        commission_rate: 위탁수수료 편도 비율 (기본 0.015%).
        slippage_bps: 슬리피지 (basis points 단위, 기본 5bp).
        sell_tax_rate: 매도 증권거래세율 (ETF는 0%, 개별주 약 0.0018).
    """

    commission_rate: float = 0.00015  # 위탁수수료 편도 0.015%
    slippage_bps: float = 5.0         # 슬리피지 (basis points)
    sell_tax_rate: float = 0.0        # 증권거래세: ETF는 0%, 개별주 약 0.0018

    def effective_buy_price(self, price: float) -> float:
        """슬리피지 반영 매수 체결가 = price * (1 + slippage_bps/10000).

        Args:
            price: 기준가격.

        Returns:
            슬리피지가 가산된 실제 매수 체결가.
        """
        return price * (1 + self.slippage_bps / 10_000)

    def effective_sell_price(self, price: float) -> float:
        """슬리피지 반영 매도 체결가 = price * (1 - slippage_bps/10000).

        Args:
            price: 기준가격.

        Returns:
            슬리피지가 차감된 실제 매도 체결가.
        """
        return price * (1 - self.slippage_bps / 10_000)

    def commission(self, notional: float) -> float:
        """수수료 = abs(notional) * commission_rate.

        Args:
            notional: 거래 명목금액 (양수 또는 음수).

        Returns:
            편도 위탁수수료 금액.
        """
        return abs(notional) * self.commission_rate

    def sell_tax(self, notional: float) -> float:
        """매도 거래세 = abs(notional) * sell_tax_rate.

        Args:
            notional: 거래 명목금액 (양수 또는 음수).

        Returns:
            증권거래세 금액.
        """
        return abs(notional) * self.sell_tax_rate
