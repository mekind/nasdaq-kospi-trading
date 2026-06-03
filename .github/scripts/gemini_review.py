#!/usr/bin/env python3
"""Gemini 기반 PR 자동 리뷰.

PR diff를 읽어 Google Gemini API(무료 티어)로 리뷰를 생성하고,
리뷰 마크다운을 출력 파일로 저장한다. (코멘트 게시는 워크플로우의 gh가 담당)

표준 라이브러리만 사용한다(외부 의존성 없음).

환경변수:
  GEMINI_API_KEY  (필수) Google AI Studio 발급 키. 없으면 스킵(exit 0).
  GEMINI_MODEL    (선택) 기본 'gemini-2.0-flash'.
  REVIEW_OUT      (선택) 리뷰 마크다운 저장 경로. 기본 'gemini-review.md'.

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

PROMPT = """당신은 시니어 코드 리뷰어입니다. 아래 GitHub Pull Request의 diff를 리뷰하세요.
한국어로 간결하고 구체적으로 작성합니다. 다음 마크다운 형식으로 답하세요:

## 🤖 Gemini 자동 리뷰
**요약**: (1-2문장)

**주요 지적** (각 항목 심각도 🔴높음 / 🟡중간 / 🟢낮음 표기, 없으면 "없음"):
- ...

**개선 제안**:
- ...

확실하지 않은 추측은 피하고 diff에 실제로 보이는 것에 근거하세요.
변경이 사소하면 짧게 끝내도 됩니다.

--- DIFF ---
"""


def _skip(msg: str) -> int:
    print(msg)
    return 0


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

    model = os.environ.get("GEMINI_MODEL", "gemini-2.0-flash").strip()
    url = (
        "https://generativelanguage.googleapis.com/v1beta/models/"
        f"{model}:generateContent?key={api_key}"
    )
    payload = {
        "contents": [{"parts": [{"text": PROMPT + diff}]}],
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
    except urllib.error.HTTPError as e:
        detail = e.read().decode("utf-8", "replace")[:500]
        return _skip(f"Gemini API 오류 {e.code} → 리뷰 스킵: {detail}")
    except Exception as e:  # noqa: BLE001 - 리뷰 실패가 CI를 깨면 안 됨
        return _skip(f"Gemini 호출 실패 → 스킵: {e}")

    try:
        review = data["candidates"][0]["content"]["parts"][0]["text"].strip()
    except (KeyError, IndexError):
        return _skip(f"예상치 못한 응답 → 스킵: {json.dumps(data)[:500]}")

    if truncated:
        review += "\n\n> ⚠️ diff가 커서 앞부분만 리뷰했습니다."

    out = os.environ.get("REVIEW_OUT", "gemini-review.md").strip() or "gemini-review.md"
    with open(out, "w", encoding="utf-8") as f:
        f.write(review + "\n")
    print(f"리뷰 저장: {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
