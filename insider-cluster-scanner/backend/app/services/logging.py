from __future__ import annotations

from datetime import datetime, timezone

from backend.app.config import get_settings


def log_api_call(provider: str, endpoint: str) -> None:
    settings = get_settings()
    timestamp = datetime.now(timezone.utc).isoformat()
    with open(settings.api_log_file, "a", encoding="utf-8") as handle:
        handle.write(f"{timestamp}\t{provider}\t{endpoint}\n")
