from __future__ import annotations

from app.core.config import settings
from app.providers.grid_provider import GridProvider
from app.providers.mock_grid_provider import MockGridProvider


def create_grid_provider(provider_name: str | None = None) -> GridProvider:
    selected = (provider_name or settings.GRID_PROVIDER).strip().lower()
    if selected == "mock":
        return MockGridProvider()
    if selected in {"scada", "historian"}:
        raise RuntimeError(
            f"GRID_PROVIDER={selected!r} is reserved but no live connector is configured"
        )
    raise RuntimeError(f"Unsupported GRID_PROVIDER value: {selected!r}")
