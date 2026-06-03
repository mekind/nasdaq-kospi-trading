# 참고문헌 (References)

이 프로젝트의 설계·전략·검증 원칙이 어디서 유래했는지 정리한다.

> **출처에 대한 정직한 고지**
> 아래 자료들은 설계의 **배경 지식**이다. 특정 레포/책 하나를 복제한 것이 아니라, 알고 트레이딩 분야의
> 정착된 관례를 종합한 것이며, 작성 시점에 각 문헌을 직접 조회해 인용한 것은 아니다.
> 따라서 **세부 수치(예: RSI(2) 임계값, 거래세율, 수수료율)는 반드시 1차 출처/실데이터로 재검증**해야 한다.
> 우리 전략 파라미터를 "검증용 baseline(strawman)"이라 부르는 이유다 — 최적값이 아니라 출발점이다.

---

## 1. 시스템 아키텍처 (모듈 분리 구조)

`data → strategy → backtest → broker → api` 의 층위 분리는 오픈소스 알고 트레이딩
프레임워크들이 공통으로 수렴한 표준 구조를 따른 것이다.

| 프레임워크 | 비고 |
|-----------|------|
| Backtrader | 파이썬 백테스트의 대표격, 전략/데이터/브로커 추상화 |
| Zipline (구 Quantopian) | 이벤트 기반 백테스트 |
| QuantConnect / LEAN | 백테스트~실거래 통합 엔진 |
| freqtrade | 전략 인터페이스 + 거래소 추상화 |
| NautilusTrader | 고성능 이벤트 기반 |
| vectorbt / bt | 벡터화 백테스트 |

→ 특정 코드 복제가 아니라 **공통 설계 패턴**을 반영.

## 2. 전략 — 단기 평균회귀 (Connors 계열)

우리 baseline 규칙(RSI(2) 과매도 + 200일선 레짐 필터 + 반등/시간 청산)의 직접적 계보.

- **Larry Connors & Cesar Alvarez**, *Short Term Trading Strategies That Work* — RSI(2)를 단기 과매도 매매에 대중화
- **Larry Connors**, *How Markets Really Work* — 과매도/과매수 통계
- **Werner De Bondt & Richard Thaler**, *Does the Stock Market Overreact?* (Journal of Finance, 1985) — 과민반응→평균회귀의 학술적 기반

> "공포 과매도 후 반등"이라는 가설 자체는 사용자가 제시했고, 위 문헌들은 그것을
> 검증 가능한 규칙으로 형식화하는 근거로 참고했다.

## 3. 백테스트 · 검증 원칙

룩어헤드 차단, 비용 모델, 생존편향, 과최적화 방지, 워크포워드 등.

- **Marcos López de Prado**, *Advances in Financial Machine Learning* (Wiley, 2018) — 백테스트 함정·과최적화
- **Ernest P. Chan**, *Quantitative Trading* (2008), *Algorithmic Trading* (2013)
- **Andreas F. Clenow**, *Trading Evolved* (2019), *Following the Trend* (2013)

## 4. 리스크 관리 · 손익 분포

음의 왜도·꼬리위험·포지션 사이징·파산위험·켈리 공식.

- **Nassim Nicholas Taleb**, *Fooled by Randomness*, *The Black Swan*, *Antifragile* — 꼬리위험·왜도
- **Edward O. Thorp** — 켈리 공식 응용 (*A Man for All Markets*)
- **Van K. Tharp**, *Trade Your Way to Financial Freedom* — 포지션 사이징
- **Ralph Vince**, *The Mathematics of Money Management*

## 5. 시장·가격 이론 ("주가가 오르는 본질")

- **Benjamin Graham**, *The Intelligent Investor* — "단기 투표기계 / 장기 저울"
- **Eugene Fama**, *Efficient Capital Markets* (1970) — 효율적 시장 가설(EMH)
- **John Maynard Keynes**, *The General Theory* (1936) — "미인대회" 비유

## 6. 기술적 지표 원전

- **J. Welles Wilder Jr.**, *New Concepts in Technical Trading Systems* (1978) — RSI·ATR·ADX·Parabolic SAR의 원전

## 7. 데이터 · API (실제 구현 시 1차 출처)

| 자료 | 용도 |
|------|------|
| FinanceDataReader (GitHub) | 한국/해외 일봉 무료 수집 — 우리 일봉 백테스트 데이터 소스 |
| pykrx | KRX 시세·종목 정보 |
| KIS Developers (apiportal.koreainvestment.com) | 한국투자증권 Open API 공식 문서 (KOSPI/해외주식, 모의투자) |
| Alpaca Docs (docs.alpaca.markets) | 나스닥 브로커 API 공식 문서 |

> 세금·수수료·API 스펙은 **반드시 위 1차 출처와 최신 고시로 확인**할 것. 본 문서의 수치는 참고용이다.

## 8. 소프트웨어 엔지니어링 관행

ABC 인터페이스, pydantic 모델, 모노레포, 계획 우선(WORKFLOW.md), 브랜치+워크트리 등은
트레이딩과 무관한 일반 SWE 관례를 따른 것이다.
