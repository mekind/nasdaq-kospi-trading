# nasdaq-kospi-trading

나스닥(NASDAQ) / 코스피(KOSPI) 매매 트레이딩 시스템.

데이터 수집 → 전략 백테스트 → (검증 후) 실거래 → 웹 대시보드 모니터링을 목표로 하는 모노레포입니다.
현재 단계는 **스캐폴드(뼈대)**이며, 각 모듈은 인터페이스와 placeholder 구현만 가지고 있습니다.

## 구조

```
nasdaq-kospi-trading/
├── engine/        # Python 매매 엔진 (데이터 · 전략 · 백테스트 · 브로커 · API)
└── dashboard/     # TypeScript 웹 대시보드 (Vite + React)
```

| 모듈 | 언어 | 역할 |
|------|------|------|
| `engine` | Python 3.11+ | 시세 수집, 전략, 백테스트, 증권사 주문, 대시보드용 REST API |
| `dashboard` | TypeScript | 포트폴리오/전략/주문 현황 시각화 웹 UI |

## 대상 시장 / 브로커

| 시장 | 브로커 후보 |
|------|-------------|
| KOSPI | 한국투자증권 (KIS) Open API |
| NASDAQ | Alpaca / Interactive Brokers |

## 빠른 시작

### engine (Python)

```bash
cd engine
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
pytest                       # 스모크 테스트
uvicorn trading_engine.api.server:app --reload   # 대시보드용 API
```

### dashboard (TypeScript)

```bash
cd dashboard
npm install
npm run dev
```

## 로드맵

- [x] 모노레포 스캐폴드
- [ ] 시세 데이터 프로바이더 구현 (KIS / Alpaca / yfinance)
- [ ] 전략 인터페이스 + 샘플 전략 (이동평균 교차 등)
- [ ] 백테스트 엔진
- [ ] 페이퍼 트레이딩 → 실거래
- [ ] 대시보드 실데이터 연동

## 면책

본 프로젝트는 학습/연구 목적입니다. 실거래에 사용 시 발생하는 손실에 대해 책임지지 않습니다.
