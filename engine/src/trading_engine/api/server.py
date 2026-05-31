"""FastAPI server exposing engine state to the dashboard.

스캐폴드: health/version 엔드포인트와 포트폴리오 placeholder만 제공.
"""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from trading_engine import __version__

app = FastAPI(title="trading-engine API", version=__version__)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/version")
def version() -> dict[str, str]:
    return {"version": __version__}


@app.get("/portfolio")
def portfolio() -> dict[str, object]:
    """대시보드용 포트폴리오 요약 (placeholder)."""
    return {"cash": 0.0, "positions": [], "total_value": 0.0}
