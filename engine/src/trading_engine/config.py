"""Engine configuration loaded from environment / .env."""

from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # 한국투자증권 (KIS) — KOSPI
    kis_app_key: str = ""
    kis_app_secret: str = ""
    kis_account_no: str = ""
    kis_env: str = "paper"  # paper | real

    # Alpaca — NASDAQ
    alpaca_api_key: str = ""
    alpaca_api_secret: str = ""
    alpaca_base_url: str = "https://paper-api.alpaca.markets"

    # Engine API
    api_host: str = "0.0.0.0"
    api_port: int = 8000


settings = Settings()
