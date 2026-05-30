from __future__ import annotations

import os
from functools import lru_cache

from pydantic import BaseModel


class Settings(BaseModel):
    scanner_api_key: str | None = os.getenv("SCANNER_API_KEY")
    fmp_api_key: str | None = os.getenv("FMP_API_KEY")
    sec_user_agent: str = os.getenv("SEC_USER_AGENT", "InsiderClusterScanner/0.1 contact@example.com")
    scan_tickers: list[str] = [
        ticker.strip().upper()
        for ticker in os.getenv("SCAN_TICKERS", "AAPL,MSFT,NVDA,TSLA,JPM,HLNE,AAT").split(",")
        if ticker.strip()
    ]
    cache_ttl_seconds: int = int(os.getenv("CACHE_TTL_SECONDS", "21600"))
    api_log_file: str = os.getenv("API_LOG_FILE", "api_calls.log")


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
