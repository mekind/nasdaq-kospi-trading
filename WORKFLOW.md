# WORKFLOW

이 레포의 모든 작업은 아래 규칙을 따른다. **예외 없이 적용한다.**

## 1. 계획 우선 (Plan First) — 필수

**어떤 구현도 계획 없이 시작하지 않는다.**

- 새 기능/변경을 시작하기 전에 **반드시 `docs/plan/` 아래에 계획 문서를 먼저 작성**한다.
- 계획 문서는 다음을 포함한다: 목표, 모듈/파일 구조, 데이터 흐름, 핵심 설계 결정과 이유, 비용/리스크 고려사항, 검증 방법, 작업 순서.
- 계획을 사람이 검토·승인한 뒤에 구현에 들어간다. (문서 상단 `Status` 갱신)
- 구현 중 계획이 바뀌면 코드보다 **계획 문서를 먼저 갱신**한다.

### 계획 문서 규칙
- 경로: `docs/plan/`
- 파일명: `YYYY-MM-DD-<short-slug>.md` (예: `2026-06-02-daily-backtest.md`)
- 상단에 `Status: 제안됨 | 승인됨 | 진행중 | 완료 | 보류` 를 명시한다.

## 2. 브랜치 + 워크트리에서만 작업 — 필수

**`main`에서 직접 커밋하지 않는다.**

- 모든 작업은 `main`에서 분기한 **브랜치 + git worktree** 안에서 수행한다.
- 워크트리 생성:
  ```bash
  git worktree add ../worktrees/<repo>--<slug> -b <type>/<slug> main
  ```
- 작업 완료 후 PR로 `main`에 병합한다. 병합 후 워크트리는 정리한다:
  ```bash
  git worktree remove <path>
  git branch -d <branch>
  ```

### 브랜치 네이밍 규칙

형식: **`<type>/<slug>`** (선택적으로 이슈 번호: `<type>/<issue>-<slug>`)

**type (목적별 접두사)**

| type | 용도 |
|------|------|
| `feature/` | 새 기능 추가 |
| `fix/` | 버그 수정 |
| `chore/` | 빌드·설정·의존성 등 잡무 |
| `docs/` | 문서 변경 |
| `refactor/` | 동작 변경 없는 구조 개선 |
| `test/` | 테스트 추가·수정 |
| `exp/` | 실험·전략 리서치 (병합 안 할 수도 있음) |

**slug 규칙**
- 영어 **kebab-case** (소문자 + 하이픈). 예: `daily-backtest`, `kis-data-collector`
- 간결하게 2~4단어. 무엇을 하는지 한눈에 드러나게.
- 공백·대문자·언더스코어·한글 금지.

**예시**
- `feature/daily-backtest`
- `feature/kis-realtime-collector`
- `fix/lookahead-bias-in-engine`
- `exp/rsi2-threshold-sweep`
- `docs/12-update-workflow` (이슈 #12)

**금지**
- `main`, `master`, `develop` 등 보호/공용 브랜치명 재사용 금지
- `temp`, `test1`, `mybranch`처럼 목적 불명한 이름 금지

## 3. 완료 전 검증 — 필수

- 완료를 선언하기 전에 테스트/실행으로 동작을 검증하고 증거를 남긴다.
- "됐을 것이다"가 아니라 "실행해서 확인했다"로 보고한다.

## 4. 커밋

- 작은 단위로 자주 커밋한다. 메시지는 무엇을/왜를 명확히.
- 비밀키·`.env`·데이터 파일은 커밋하지 않는다 (`.gitignore` 준수).

---

요약: **계획 문서 작성 → 승인 → main에서 브랜치+워크트리 생성 → 거기서만 구현 → 검증 → PR 병합.**
