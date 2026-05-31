# trading-engine

NASDAQ/KOSPI 매매 엔진 (Python).

## 모듈

| 패키지 | 역할 |
|--------|------|
| `trading_engine.config` | 환경설정 (pydantic-settings, `.env` 로드) |
| `trading_engine.data` | 시세 데이터 프로바이더 인터페이스 |
| `trading_engine.strategy` | 전략 베이스 클래스 + 시그널 정의 |
| `trading_engine.backtest` | 백테스트 엔진 (placeholder) |
| `trading_engine.broker` | 증권사 주문 추상화 (KIS / Alpaca) |
| `trading_engine.api` | 대시보드용 FastAPI 서버 |

## 개발

```bash
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
pytest
ruff check src
uvicorn trading_engine.api.server:app --reload
```
