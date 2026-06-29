from __future__ import annotations

from datetime import datetime, timezone
from threading import Lock

_lock = Lock()
_states: dict[str, dict[str, str | None]] = {}


def record_provider_success(role: str, provider_name: str) -> None:
    with _lock:
        _states[role] = {
            "status": "operational",
            "provider": provider_name,
            "last_success": datetime.now(timezone.utc).isoformat(),
            "last_error": None,
        }


def record_provider_failure(role: str, provider_name: str, error: Exception) -> None:
    with _lock:
        previous = _states.get(role, {})
        _states[role] = {
            "status": "degraded",
            "provider": provider_name,
            "last_success": previous.get("last_success"),
            "last_error": type(error).__name__,
        }


def get_provider_state(role: str) -> dict[str, str | None] | None:
    with _lock:
        state = _states.get(role)
        return dict(state) if state else None
