#!/usr/bin/env python3
"""Gemini 기반 다중 역할(persona) PR 자동 리뷰.

PR diff를 읽어 역할별(버그/보안/성능/유지보수)로 Gemini를 각각 호출하고,
각 역할의 리뷰를 PR에 '스티키 코멘트'(역할당 하나, 매 실행마다 갱신)로 게시한다.
표준 라이브러리만 사용한다(외부 의존성 없음).

환경변수:
  GEMINI_API_KEY     (필수) 없으면 전체 스킵(exit 0).
  GEMINI_MODEL       (선택) 기본 'gemini-2.5-flash-lite'.
  GITHUB_TOKEN       (필수, 게시용) GitHub Actions가 자동 제공.
  GITHUB_REPOSITORY  (필수) "owner/repo". Actions가 자동 제공.
  PR_NUMBER          (필수) 대상 PR 번호.

인자:
  argv[1]  diff 파일 경로
"""

from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.request

MAX_DIFF_CHARS = 120_000
GEMINI_MODEL_DEFAULT = "gemini-2.5-flash-lite"
GH_API = "https://api.github.com"

# 모든 역할에 공통 적용되는 규칙 — 오탐(false positive)을 줄이는 것이 핵심.
COMMON_RULES = """\
공통 규칙(반드시 준수):
- diff에 실제로 보이는 코드에만 근거하라. 보이지 않는 파일/코드는 추측하거나 지적하지 마라.
- GitHub 호스티드 러너에는 `gh` CLI와 표준 유닉스 도구가 기본 설치돼 있다고 가정하라(설치 관련 지적 금지).
- 커밋 날짜/타임스탬프/시점에 대해서는 지적하지 마라.
- 확신이 없으면 지적하지 마라. (오탐보다 누락이 낫다)
- 각 지적은 [심각도] + 위치(파일·대략 위치) + 구체적 수정안을 포함하라.
  심각도 표기: 🔴높음 / 🟡중간 / 🟢낮음.
- 이 역할 관점에서 중대한 문제가 없으면 정확히 `LGTM` 한 단어만 출력하라(부연 설명 없이)."""

# 역할(persona) 정의. 각 역할이 별도 코멘트를 단다.
ROLES = [
    {
        "key": "correctness",
        "emoji": "🐛",
        "title": "버그·정확성",
        "persona": "당신은 버그와 논리 결함을 잡는 데 집중하는 시니어 엔지니어입니다.",
        "focus": "정확성, 경계 조건, off-by-one, None/예외 처리, 경쟁 상태, 잘못된 분기, 회귀 가능성.",
    },
    {
        "key": "security",
        "emoji": "🔒",
        "title": "보안",
        "persona": "당신은 보안 리뷰어입니다.",
        "focus": "비밀정보 노출, 인젝션, 권한/토큰 범위, 신뢰 경계, 안전하지 않은 입력/역직렬화, 공급망 위험.",
    },
    {
        "key": "performance",
        "emoji": "⚡",
        "title": "성능",
        "persona": "당신은 성능 리뷰어입니다.",
        "focus": "불필요한 연산/할당, O(n^2) 이상 패턴, I/O·네트워크 호출, 캐싱 기회, 큰 입력에서의 확장성.",
    },
    {
        "key": "maintainability",
        "emoji": "🧹",
        "title": "가독성·유지보수",
        "persona": "당신은 가독성과 유지보수성에 집중하는 리뷰어입니다.",
        "focus": "명명, 중복, 복잡도, 응집/결합, 죽은 코드, 문서화. 린터가 잡는 단순 포매팅은 언급하지 마라.",
    },
]


def _skip(msg: str) -> int:
    print(msg)
    return 0


def call_gemini(prompt: str, api_key: str, model: str) -> str | None:
    """Gemini를 호출해 리뷰 텍스트를 반환. 실패 시 None(해당 역할 스킵)."""
    url = (
        f"https://generativelanguage.googleapis.com/v1beta/models/"
        f"{model}:generateContent?key={api_key}"
    )
    payload = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {"temperature": 0.2, "maxOutputTokens": 2048},
    }
    req = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        return data["candidates"][0]["content"]["parts"][0]["text"].strip()
    except urllib.error.HTTPError as e:
        detail = e.read().decode("utf-8", "replace")[:300]
        print(f"  Gemini API 오류 {e.code}: {detail}", file=sys.stderr)
    except Exception as e:  # noqa: BLE001 - 리뷰 실패가 CI를 깨면 안 됨
        print(f"  Gemini 호출 실패: {e}", file=sys.stderr)
    return None


def _gh_request(method: str, path: str, token: str, data: dict | None = None):
    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
        "User-Agent": "gemini-review-bot",
    }
    body = None
    if data is not None:
        body = json.dumps(data).encode("utf-8")
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(GH_API + path, data=body, headers=headers, method=method)
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read().decode("utf-8"))


def upsert_comment(repo: str, pr: str, token: str, marker: str, body: str) -> None:
    """marker가 포함된 기존 코멘트를 찾아 갱신(PATCH), 없으면 새로 생성(POST). 스티키."""
    existing = _gh_request("GET", f"/repos/{repo}/issues/{pr}/comments?per_page=100", token)
    cid = next((c["id"] for c in existing if marker in (c.get("body") or "")), None)
    if cid:
        _gh_request("PATCH", f"/repos/{repo}/issues/comments/{cid}", token, {"body": body})
    else:
        _gh_request("POST", f"/repos/{repo}/issues/{pr}/comments", token, {"body": body})


def build_prompt(role: dict, diff: str) -> str:
    return (
        f"{role['persona']}\n"
        f"아래 GitHub PR의 diff를 '{role['title']}' 관점에서만 리뷰하세요. 다른 관점은 무시합니다.\n"
        f"집중 영역: {role['focus']}\n\n"
        f"{COMMON_RULES}\n\n"
        f"한국어로 간결하게, 마크다운 불릿으로 답하세요.\n\n"
        f"--- DIFF ---\n{diff}"
    )


def main() -> int:
    api_key = os.environ.get("GEMINI_API_KEY", "").strip()
    if not api_key:
        return _skip("GEMINI_API_KEY 미설정 → 리뷰 스킵 (시크릿 등록 후 동작).")

    if len(sys.argv) < 2:
        print("usage: gemini_review.py <diff_file>", file=sys.stderr)
        return 1
    try:
        with open(sys.argv[1], encoding="utf-8", errors="replace") as f:
            diff = f.read().strip()
    except OSError as e:
        return _skip(f"diff 읽기 실패 → 스킵: {e}")
    if not diff:
        return _skip("diff 비어있음 → 스킵.")

    truncated = len(diff) > MAX_DIFF_CHARS
    if truncated:
        diff = diff[:MAX_DIFF_CHARS]

    token = os.environ.get("GITHUB_TOKEN", "").strip()
    repo = os.environ.get("GITHUB_REPOSITORY", "").strip()
    pr = os.environ.get("PR_NUMBER", "").strip()
    if not (token and repo and pr):
        return _skip("GITHUB_TOKEN/REPOSITORY/PR_NUMBER 누락 → 게시 불가, 스킵.")

    model = os.environ.get("GEMINI_MODEL", "").strip() or GEMINI_MODEL_DEFAULT
    posted = 0
    for role in ROLES:
        review = call_gemini(build_prompt(role, diff), api_key, model)
        if review is None:
            continue
        marker = f"<!-- gemini-review:{role['key']} -->"
        body = f"{marker}\n## {role['emoji']} {role['title']} 리뷰 (Gemini)\n\n{review}"
        if truncated:
            body += "\n\n> ⚠️ diff가 커서 앞부분만 검토했습니다."
        try:
            upsert_comment(repo, pr, token, marker, body)
            posted += 1
            print(f"[{role['key']}] 코멘트 게시/갱신 완료")
        except Exception as e:  # noqa: BLE001
            print(f"[{role['key']}] 코멘트 게시 실패: {e}", file=sys.stderr)

    print(f"완료: {posted}/{len(ROLES)} 역할 게시")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
