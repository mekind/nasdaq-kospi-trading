# nasdaq-kospi-trading

나스닥(NASDAQ) / 코스피(KOSPI) 퀀트 전략 **연구·백테스트 모노레포**.

공개·학술 전략을 **편향 없이(룩어헤드·생존편향·비용 교정)** 백테스트해 "실제로 통하는가"를 정직하게 검증하는 것이 목표입니다. 절대 수익 숫자가 아니라 **검증 방법론**이 이 레포의 핵심 자산입니다.

> ⚠️ 지금까지 검증한 전략은 대부분 **"엣지 없음"으로 종료**되었습니다. 그게 정상이고, 그 과정과 근거가 자산입니다. (아래 [검증 이력](#검증-이력) 참고)

## 구조

```
nasdaq-kospi-trading/
├── engine/        # Python 매매·백테스트 엔진 (실질적 핵심)
│   └── src/trading_engine/
│       ├── data/        # FDR·DART·pykrx 시세/재무/시총 데이터 계층 + 캐시
│       ├── indicators.py# 순수 함수 지표 (SMA, RSI ...)
│       ├── strategy/    # 전략 (시그널/목표비중 산출)
│       ├── backtest/    # 백테스트 엔진 · 러너 · 성과지표 · 이벤트스터디
│       ├── broker/      # 증권사 주문 어댑터 (KIS / Alpaca, 스캐폴드)
│       └── api/         # 대시보드용 REST API (FastAPI, 스캐폴드)
├── dashboard/     # TypeScript 웹 대시보드 (Vite + React, 스캐폴드)
└── docs/          # 계획 · 리서치 · 실패기록 · 용어 (방법론의 보고)
```

## 백테스트 엔진

두 종류의 엔진이 있다. 둘 다 **룩어헤드 차단**(시그널은 종가로 계산, 체결은 익봉 시가)과 **현실 비용**(수수료·슬리피지·세금)을 강제한다.

| 엔진 | 대상 | 포지션 모델 |
|------|------|-------------|
| `BacktestEngine` | 단일 종목 | 롱/플랫 단일 포지션, 전액 투입(all-in) |
| `PortfolioBacktestEngine` | 다자산 | 리밸런싱일 **목표비중 벡터** → 체결·현금흐름·회전율 |

`CostModel`은 두 엔진이 공유한다 (편도 수수료 0.015% · 슬리피지 5bp · 매도세: ETF 0% / 개별주 0.18%).

## 구현된 전략

| 전략 | 파일 | 유형 | 시장 | 판정 |
|------|------|------|------|------|
| RSI(2) 평균회귀 | `strategy/mean_reversion.py` | 단일종목 추세필터+평균회귀 | KOSPI | ❌ 엣지 없음 |
| PEAD (실적 드리프트) | `backtest/event_study.py` | 이벤트 스터디 | KOSPI 대형주 | ❌ 엣지 없음 |
| Faber 자산군 추세추종 | `strategy/trend_following.py` | 다자산 시계열 모멘텀 | 미국 ETF | 🔬 검증 중 |

## 검증 이력

각 전략의 **계획·실행 결과**는 `docs/plan/`, **실패 원인**은 `docs/failure/`에 기록한다.

- **RSI(2) 평균회귀** — 코스피 시총 상위 200, 시점별 멤버십(생존편향 교정), 2014~2026. 편향 교정 후 수익종목 ≈50%(동전던지기), 누적 중앙 +1.3% vs 단순보유 +25.2%. → 체계적 엣지 없음. ([plan](docs/plan/2026-06-03-kospi-universe-backtest.md))
- **PEAD** — 대형주는 정보 효율이 높아 발표 후 드리프트가 거의 없고 큰 서프라이즈는 오히려 되돌림. ([failure](docs/failure/2026-06-03-pead-large-cap.md))
- **Faber 추세추종** — Mebane Faber TAA를 미국 자산군 ETF 5종에 재현. ([plan](docs/plan/2026-06-05-faber-trend-following.md))

## 빠른 시작

### engine (Python)

```bash
cd engine
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
pytest                                                   # 단위 테스트

# Faber 자산군 추세추종 백테스트 (미국 ETF, FDR 데이터)
python -m trading_engine.backtest.run_trend_following --start 2008-01-01

# 코스피 시총 유니버스 RSI(2) breadth 백테스트 (pykrx 로그인 필요: .env)
python -m trading_engine.backtest.run_universe --sample 30
```

### dashboard (TypeScript)

```bash
cd dashboard
npm install
npm run dev
```

## 작업 규칙 (WORKFLOW.md)

이 레포의 모든 작업은 [`WORKFLOW.md`](WORKFLOW.md)를 **예외 없이** 따른다. 요약:

1. **계획 우선** — 구현 전 `docs/plan/`에 계획 문서 작성, 외부 데이터는 스파이크로 선검증.
2. **브랜치 + 워크트리에서만** 작업 — `main` 직접 커밋 금지.
3. **완료 전 검증** — "됐을 것이다"가 아니라 "실행해서 확인했다".
4. **백테스트 무결성** — 룩어헤드·생존편향·수정주가·현실비용·벤치마크·정직한 음의 결과.
5. **실패도 기록** — 엣지가 없으면 `docs/failure/`에 원인을 남긴다.

## 대상 시장 / 브로커 (실거래는 미구현)

| 시장 | 브로커 후보 |
|------|-------------|
| KOSPI | 한국투자증권 (KIS) Open API |
| NASDAQ | Alpaca / Interactive Brokers |

## 면책

본 프로젝트는 **학습/연구 목적**입니다. 어떤 전략도 실거래 수익을 보장하지 않으며, 실거래 사용 시 발생하는 손실에 대해 책임지지 않습니다.
