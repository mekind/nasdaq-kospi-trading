"""CostModel 단위 테스트."""

import importlib.util
import pathlib
import sys

import pytest

# backtest/__init__.py 가 아직 완성되지 않은 data.providers 모듈을 임포트하므로
# 패키지 초기화를 우회하여 costs 모듈만 직접 로드한다.
_costs_path = (
    pathlib.Path(__file__).parent.parent
    / "src" / "trading_engine" / "backtest" / "costs.py"
)
_spec = importlib.util.spec_from_file_location("trading_engine.backtest.costs", _costs_path)
_module = importlib.util.module_from_spec(_spec)
sys.modules.setdefault("trading_engine.backtest.costs", _module)
_spec.loader.exec_module(_module)
CostModel = _module.CostModel


def test_effective_buy_price_default_slippage():
    """슬리피지 5bp 기준 매수 체결가: 100 → 100.05."""
    model = CostModel()
    assert model.effective_buy_price(100.0) == pytest.approx(100.05)


def test_effective_sell_price_default_slippage():
    """슬리피지 5bp 기준 매도 체결가: 100 → 99.95."""
    model = CostModel()
    assert model.effective_sell_price(100.0) == pytest.approx(99.95)


def test_commission_default_rate():
    """기본 수수료율 0.015%: 1,000,000 → 150.0."""
    model = CostModel()
    assert model.commission(1_000_000) == pytest.approx(150.0)


def test_commission_negative_notional():
    """음수 명목금액도 절댓값 기준으로 계산."""
    model = CostModel()
    assert model.commission(-1_000_000) == pytest.approx(150.0)


def test_sell_tax_individual_stock():
    """개별주 거래세율 0.0018: 1,000,000 → 1800.0."""
    model = CostModel(sell_tax_rate=0.0018)
    assert model.sell_tax(1_000_000) == pytest.approx(1800.0)


def test_sell_tax_etf_default_zero():
    """ETF 기본 거래세율 0.0: 1,000,000 → 0.0."""
    model = CostModel()
    assert model.sell_tax(1_000_000) == pytest.approx(0.0)


def test_sell_tax_negative_notional():
    """음수 명목금액도 절댓값 기준으로 계산."""
    model = CostModel(sell_tax_rate=0.0018)
    assert model.sell_tax(-1_000_000) == pytest.approx(1800.0)
