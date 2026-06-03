# Gemini 기반 PR 자동 리뷰

- **Status**: 구현 완료 (2026-06-03) — 스크립트/YAML 검증 통과. 실 호출은 시크릿 등록 후 PR에서 검증.
- **브랜치**: `feature/gemini-pr-review`

## 목표

PR이 열리거나 갱신될 때 **Google Gemini(무료 티어)** 로 변경분을 자동 리뷰하고, 결과를 PR 코멘트로 남긴다.
공개 레포라 GitHub Actions 실행 비용은 0원, LLM도 Gemini 무료 티어를 사용해 **완전 무료**를 목표로 한다.

## 구조

```
PR opened/synchronize
  → GitHub Actions 트리거
  → gh pr diff 로 변경분 추출
  → gemini_review.py 가 Gemini API 호출 → 리뷰 마크다운 생성
  → gh pr comment 로 PR에 코멘트 게시
```

## 파일

| 파일 | 역할 |
|------|------|
| `.github/workflows/gemini-review.yml` | PR 이벤트 트리거 + 단계 오케스트레이션 |
| `.github/scripts/gemini_review.py` | diff → Gemini 호출 → 리뷰 마크다운 저장 (Python 표준 라이브러리만 사용) |

## 핵심 설계 결정

1. **자작 스크립트** (서드파티 액션 미사용): 공급망 위험을 줄이고 동작을 완전히 감사 가능하게. 의존성 없이 `urllib`만 사용 → CI에서 pip 설치 불필요.
2. **트리거**: `opened`, `synchronize`, `reopened`. 푸시마다 새 리뷰 코멘트를 남긴다(v1은 단순; 추후 sticky 코멘트로 갱신 가능).
3. **모델**: 기본 `gemini-2.5-flash-lite`(무료 티어). `GEMINI_MODEL` 환경변수로 교체 가능. (구 `gemini-2.0-flash`는 2026-06-01 종료되어 교체함)
4. **안전한 스킵**: `GEMINI_API_KEY` 시크릿이 없거나 diff가 비면 조용히 스킵(exit 0) → 시크릿 등록 전에도 CI가 깨지지 않음. Gemini 오류도 CI를 실패시키지 않음(리뷰는 보조 기능).
5. **diff 크기 제한**: 120k자 초과 시 잘라서 호출(토큰/무료 한도 보호), 잘렸음을 코멘트에 명시.
6. **권한 최소화**: `contents: read`, `pull-requests: write` 만.

## 비용 / 한도

- GitHub Actions: 공개 레포 무료.
- Gemini 무료 티어: 분당/일당 요청 제한 존재(리뷰 용도엔 충분). API 키는 Google AI Studio에서 무료 발급.

## 사용자 작업 (1회)

1. Google AI Studio(aistudio.google.com)에서 API 키 무료 발급.
2. 레포 시크릿 등록: `gh secret set GEMINI_API_KEY` (또는 GitHub 웹 Settings → Secrets).

## 검증 방법

- 스크립트 `py_compile` + 키 미설정 시 graceful skip 동작 확인.
- 워크플로우 YAML 파싱 검증.
- 실제 Gemini 호출 + 코멘트 게시는 **시크릿 등록 후 실제 PR에서만** 검증 가능(로컬에선 키가 없어 불가) → 한계 명시.

## 추후

- sticky 코멘트(기존 리뷰 갱신)로 푸시마다 코멘트 누적 방지.
- 인라인(라인별) 리뷰 코멘트로 고도화.
- 라벨/슬래시 커맨드로 온디맨드 리뷰.
