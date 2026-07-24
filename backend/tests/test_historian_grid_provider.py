import pytest

from app.providers.grid_provider_factory import create_grid_provider


def test_historian_provider_fails_closed_when_disabled(monkeypatch):
    monkeypatch.setattr(
        "app.providers.historian_grid_provider.settings.HISTORIAN_READ_ONLY_ENABLED",
        False,
    )

    with pytest.raises(RuntimeError, match="disabled"):
        create_grid_provider("historian")


def test_historian_provider_exposes_no_control_methods():
    from app.providers.historian_grid_provider import HistorianGridProvider

    forbidden = {"write", "command", "acknowledge", "start_unit", "stop_unit"}
    assert not forbidden.intersection(dir(HistorianGridProvider))
