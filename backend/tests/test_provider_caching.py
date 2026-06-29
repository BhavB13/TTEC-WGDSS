from datetime import datetime, timedelta, timezone
from email.utils import format_datetime

from app.providers.met_norway_provider import MetNorwayProvider
from app.providers.open_meteo_provider import OpenMeteoProvider
from app.providers.weatherapi_provider import WeatherAPIProvider


class _Response:
    def __init__(
        self,
        payload,
        *,
        status_code=200,
        headers=None,
    ):
        self._payload = payload
        self.status_code = status_code
        self.headers = headers or {}

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")

    def json(self):
        return self._payload


def test_open_meteo_provider_cache_prevents_duplicate_requests(monkeypatch):
    provider = OpenMeteoProvider(
        retry_attempts=1,
        cache_ttl_seconds=300,
    )
    calls = []

    def fake_get(url, params, timeout):
        calls.append((url, params, timeout))
        return _Response({"current": {"temperature_2m": 29}})

    monkeypatch.setattr(provider.session, "get", fake_get)

    first = provider._request_json({"latitude": 10.5953})
    second = provider._request_json({"latitude": 10.5953})

    assert first == second
    assert len(calls) == 1


def test_met_norway_cache_honors_expiry_and_conditional_requests(monkeypatch):
    provider = MetNorwayProvider(
        user_agent="WGDSS-Test/1.0 (+https://example.com/)",
        retry_attempts=1,
    )
    last_modified = format_datetime(
        datetime.now(timezone.utc) - timedelta(minutes=30),
        usegmt=True,
    )
    expires = format_datetime(
        datetime.now(timezone.utc) + timedelta(minutes=10),
        usegmt=True,
    )
    responses = [
        _Response(
            {"properties": {"timeseries": []}},
            headers={"Expires": expires, "Last-Modified": last_modified},
        ),
        _Response({}, status_code=304, headers={"Expires": expires}),
    ]
    request_headers = []

    def fake_get(url, params, headers, timeout):
        request_headers.append(headers)
        return responses.pop(0)

    monkeypatch.setattr(provider.session, "get", fake_get)
    params = {"lat": 10.5953, "lon": -61.3372}

    first = provider._request_json(params)
    second = provider._request_json(params)
    assert first == second
    assert len(request_headers) == 1

    cache_entry = next(iter(provider._response_cache.values()))
    cache_entry.expires_at = datetime.now(timezone.utc) - timedelta(seconds=1)
    third = provider._request_json(params)

    assert third == first
    assert len(request_headers) == 2
    assert request_headers[1]["If-Modified-Since"] == last_modified


def test_weatherapi_provider_cache_prevents_duplicate_free_plan_requests(monkeypatch):
    provider = WeatherAPIProvider(
        api_key="free-plan-test-key",
        retry_attempts=1,
        cache_ttl_seconds=300,
    )
    calls = []

    def fake_get(url, params, timeout):
        calls.append((url, params, timeout))
        return _Response({"current": {"temp_c": 29}})

    monkeypatch.setattr(provider.session, "get", fake_get)

    first = provider._request_json("current.json", {"q": "10.5953,-61.3372"})
    second = provider._request_json("current.json", {"q": "10.5953,-61.3372"})

    assert first == second
    assert len(calls) == 1
