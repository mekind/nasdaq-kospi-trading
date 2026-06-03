# 기술적 지표 (Technical Indicators)

가격 데이터(OHLCV)를 전략이 판단에 쓰는 숫자로 변환한 것. 우리 코드에서는 `indicators.py`에 순수 함수로 구현한다.

## SMA (Simple Moving Average, 단순이동평균)
최근 N기간 종가의 산술평균. 추세 방향과 기준선을 파악하는 데 쓴다.
- 예: 200일선(장기 추세, 상승 레짐 필터), 5일선(단기 기준·청산)
- `sma(series, window) = series.rolling(window).mean()`
- **발명자 없음**: 통계학의 일반 개념(이동 구간 평균)으로, 금융 이전부터 시계열 분석에 쓰였다.

## RSI (Relative Strength Index, 상대강도지수)
일정 기간 상승폭과 하락폭의 비율로 계산하는 0~100 사이 지표. **과매수/과매도**를 수치화한다.
- 통상 70 이상이면 과매수, 30 이하면 과매도로 본다.
- **발명자: J. 웰스 와일더 주니어(J. Welles Wilder Jr.)**, 1978년 저서 《New Concepts in Technical Trading Systems》에서 발표. ATR·ADX·Parabolic SAR도 그가 만들었다. 표준 기본 기간은 14.

### RSI(2)
기간을 2로 줄인 단기 RSI. **래리 코너스(Larry Connors)**가 단기 평균회귀 전략에 대중화했다.
우리 전략의 진입 신호 `RSI(2) < 10`(단기 과매도 = 공포)에 사용한다.

---
관련: [strategy.md](./strategy.md)(지표를 매매 규칙으로), [market-data.md](./market-data.md)(입력 데이터)
