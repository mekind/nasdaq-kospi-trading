# 07. DART OpenAPI 데이터 가용성 조사 (PEAD Phase 0 Spike)

- **작성일**: 2026-06-03
- **목적**: KOSPI PEAD(실적발표 후 주가 표류) 전략의 데이터 소스로 DART OpenAPI(opendart.fss.or.kr)가 적합한지 평가
- **방식**: 공식 개발가이드·이용약관 + 신뢰 출처(R 퀀트쿡북, dart-fss/OpenDartReader 문서) 문서 조사 (라이브 호출 아님 — API 키 미보유)
- **관련 계획**: `docs/plan/2026-06-03-earnings-pead.md`
- **판정**: **조건부 GO** (제약 2가지 수용 시)

---

## 결론 요약

DART OpenAPI는 **무료**로 분기 재무(매출·영업이익·순이익·EPS)와 공시 접수일(PIT 기준)을 제공해 PEAD 백테스트의 주 데이터 소스로 **사용 가능**하다. 단 두 가지 제약을 반드시 수용해야 한다:

1. **🔴 데이터 2015년 이후만** — 재무제표 API는 `bsns_year` 2015년부터 제공. **2008 금융위기·2011 유럽위기 포함 장기 백테스트 불가.** PEAD 검증은 ~10년(2015~2026) 구간으로 한정된다.
2. **🟡 생존편향 수동 처리** — 상폐 기업의 `corp_code`는 존재하나, 파이썬 래퍼(dart-fss `include_delisting=False`, OpenDartReader)가 기본적으로 상폐 종목을 제외한다. corpCode.xml 전체를 직접 쓰고 상폐 종목을 명시 포함해야 편향을 막을 수 있다.

→ 이 두 제약을 계획에 반영하고 **GO**로 진행 권고. (단 라이브 검증 2건은 아래 "남은 블로커" 참조)

---

## 항목별 조사 결과 (10항)

| # | 항목 | 판정 | 근거 (엔드포인트·필드) |
|---|------|------|------------------------|
| 1 | 재무제표(매출·영업이익·순이익·EPS) | ✅ 가능 | `fnlttSinglAcntAll`(전체재무제표) / `fnlttSinglAcnt`(주요계정). EPS는 손익계산서 행 "기본주당이익(원)"으로 포함(전용필드 아님, account_id 필터) |
| 2 | 공시 접수일(rcept_dt, PIT 핵심) | ⚠️ 조건부 | 공시검색 `list.json`이 `rcept_dt`·`rcept_no` 제공. **재무제표 API 자체는 접수일 미제공** → list.json↔재무 API **2단계 매핑 필수** |
| 3 | 정정공시 구분 | ⚠️ 조건부 | `report_nm`에 "[정정]" 텍스트 파싱 + `last_reprt_at=N`으로 이력 전체. 단 "어느 보고서를 정정했는지" 연결 필드 없음 |
| 4 | 잠정실적 공시 | ⚠️ 조건부 | 거래소공시 수시(`I001`)/공정공시(`I002`)로 목록 조회 가능. **수치는 공시 원문(PDF/HTML) 파싱 필요** — 정형 필드 없음 |
| 5 | 연결(CFS)/별도(OFS) | ✅ 가능 | `fs_div=CFS\|OFS` 파라미터. PEAD엔 연결(CFS) 권장 |
| 6 | 전년동기/reprt_code | ✅ 가능 | 응답에 당기/전기/전전기 + 분기 `frmtrm_q_amount`(전기동분기) → YoY 가능. reprt_code: 11013(1Q)/11012(반기)/11014(3Q)/11011(사업) |
| 7 | corp_code↔종목코드 | ✅ 가능 | `corpCode.xml`(ZIP) 다운로드: corp_code(8)·corp_name·stock_code(6). **우선주 자동 구분 안 됨**(보통주 코드 위주) |
| 8 | 상폐 종목 과거 데이터 | ⚠️ 주의 | corp_code는 존재 → 직접 조회 시 폐지 전 재무 취득 가능. **단 래퍼 기본값이 상폐 제외 → 수동 포함 필수** |
| 9 | 인증·rate limit | ✅ 가능 | 무료. 이메일 인증 후 키 발급. **일 10,000건** 한도(이용약관·R쿡북). 분당 제한 명시 없음 |
| 10 | 과거 시작 연도 | 🔴 제약 | **2015년 이후만.** 2014 이전·2008 위기 불가. 이전 데이터는 XBRL 원문/KRX/유료벤더 |

---

## 핵심 구현 함의 (계획에 반영할 것)

1. **PIT 2단계 파이프라인 (항목 2)**: `list.json`으로 (기업, 보고서유형 A001/A002/A003) 검색 → `rcept_dt`·`rcept_no` 확보 → 같은 `bsns_year`+`reprt_code`로 `fnlttSinglAcntAll` 호출. **신호 가용일 = rcept_dt + 1 거래일.** 분기말 기준 인덱싱 금지.
2. **정정 처리 (항목 3)**: `last_reprt_at=N`으로 정정 이력 전체 수집 후, **최초 접수(rcept_no 최소/최초 rcept_dt) 숫자를 신호에 사용**. 정정 후 확정치 사용은 룩어헤드.
3. **연결 고정 (항목 5)**: `fs_div=CFS`로 통일.
4. **YoY (항목 6)**: 분기 응답의 전기동분기 금액으로 EPS/순이익/매출 YoY 계산. 전년동기 부재(신규상장/분할) 종목은 명시 제외 + 건수 로깅.
5. **생존편향 (항목 8) — 가장 중요**: 래퍼 기본값을 믿지 말고 corpCode.xml 전체 corp_code 사용 + 상폐 종목 명시 포함. 불가 구간은 결과에 "낙관 편향" 한계 명시.
6. **수집량 관리 (항목 9)**: KOSPI ~800종목 × 40분기 ≈ 32,000건 > 일 10,000건 → **수일 분산 수집 + parquet 캐시 영속화** 필요. `dart_provider.py` 캐시 설계에 반영.
7. **백테스트 기간 한정 (항목 10)**: 2015~2026. 폭락 표본은 2018·2020(코로나)·2022 하락장으로 한정. 2008 꼬리검증은 불가 → 한계 명시.

## 파이썬 래퍼

| 라이브러리 | 장점 | 주의 |
|-----------|------|------|
| **OpenDartReader** | `dart.list()`/`dart.finstate()` pandas 반환, 간편 | 상폐 자동 포함 아님 |
| **dart-fss** | `include_delisting` 파라미터 존재, 공시유형 문서화 | **기본값 False → 반드시 True 또는 수동** |

→ 1차는 직접 `httpx`로 `list.json`+`fnlttSinglAcntAll` 호출(`pyproject.toml`에 httpx 이미 존재)하거나 OpenDartReader 채택. 생존편향 때문에 corp_code 목록은 수동 관리 권장.

---

## 남은 블로커 (라이브 검증 미완)

문서 조사는 완료했으나, **실제 응답 스키마·상폐 종목 실데이터 확인은 라이브 호출이 필요**하며 현재 막혀 있다:

1. **DART API 키 없음** — 무료 발급 필요: opendart.fss.or.kr 회원가입 → 이메일 인증 → 인증키 신청. (사용자 조치 필요)
2. **Python 엔진 환경 미설치** — `engine/`에서 `python -m venv .venv && pip install -e ".[dev]"` 필요. (Phase 1 착수 시 셋업)

**라이브로 확정해야 할 잔여 질문** (키 확보 후 Phase 1 초입에):
- [ ] 상폐 종목 1개(예: 과거 상폐기업)의 `fnlttSinglAcntAll`이 폐지 전 분기재무를 실제 반환하는가
- [ ] `frmtrm_q_amount`(전기동분기)가 분기보고서에서 일관 채워지는가
- [ ] EPS account_id의 정확한 XBRL 태그명(기본주당이익) 확인

---

## 출처

- [OpenDART 개발가이드 — 단일회사 전체재무제표 fnlttSinglAcntAll](https://opendart.fss.or.kr/guide/detail.do?apiGrpCd=DS003&apiId=2019020)
- [OpenDART 개발가이드 — 공시검색 list.json](https://opendart.fss.or.kr/guide/detail.do?apiGrpCd=DS001&apiId=2019001)
- [OpenDART 개발가이드 — 고유번호 corpCode.xml](https://opendart.fss.or.kr/guide/detail.do?apiGrpCd=DE002&apiId=AE00009)
- [OpenDART 이용약관 (무료·rate limit)](https://opendart.fss.or.kr/intro/terms.do)
- [dart-fss 공시유형 코드](https://dart-fss.readthedocs.io/en/latest/dart_types.html)
- [dart-fss 기업정보 include_delisting](https://dart-fss.readthedocs.io/en/latest/dart_corp.html)
- [OpenDartReader GitHub](https://github.com/FinanceData/OpenDartReader)
- [R 퀀트쿡북 — DART API (10,000건/일)](https://hyunyulhenry.github.io/quant_cookbook/금융-데이터-수집하기-심화.html)
