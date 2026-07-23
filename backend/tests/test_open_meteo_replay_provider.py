from datetime import datetime
from zoneinfo import ZoneInfo

import pytest

from app.data.temperature_sampling import TRINIDAD_TEMPERATURE_SAMPLING_POINTS
from app.providers.open_meteo_replay_provider import OpenMeteoReplayProvider


TRINIDAD_TZ = ZoneInfo("America/Port_of_Spain")


def test_replay_provider_selects_available_run_and_parses_three_models(monkeypatch):
    provider = OpenMeteoReplayProvider()
    models = provider.models
    timestamps = [
        "2026-06-16T09:00",
        "2026-06-16T10:00",
        "2026-06-16T11:00",
        "2026-06-16T12:00",
    ]
    payload: dict[str, object] = {"hourly": {"time": timestamps}}
    hourly = payload["hourly"]
    assert isinstance(hourly, dict)
    for model_index, model in enumerate(models):
        hourly[f"temperature_2m_{model}"] = [
            27 + model_index,
            28 + model_index,
            29 + model_index,
            30 + model_index,
        ]
        hourly[f"relative_humidity_2m_{model}"] = [80, 78, 76, 74]
        hourly[f"precipitation_{model}"] = [0.0, 0.1, 0.2, 0.3]
        hourly[f"cloud_cover_{model}"] = [40, 50, 60, 70]
        hourly[f"wind_speed_10m_{model}"] = [12, 13, 14, 15]
        hourly[f"surface_pressure_{model}"] = [1012, 1011, 1010, 1009]
        hourly[f"weather_code_{model}"] = [1, 2, 3, 61]

    captured: dict[str, object] = {}

    def fake_request(params):
        captured.update(params)
        return payload

    monkeypatch.setattr(provider, "_request_json", fake_request)
    result = provider.get_forecast_sources(
        latitude=10.5953,
        longitude=-61.3372,
        source_cursor=datetime(2026, 6, 16, 10, tzinfo=TRINIDAD_TZ),
        hours=2,
    )

    assert captured["run"] == "2026-06-16T06:00"
    assert captured["models"] == ",".join(models)
    assert result.expected_source_count == 3
    assert len(result.source_payloads) == 3
    assert all(len(source) == 2 for source in result.source_payloads)
    assert result.source_payloads[0][0]["forecast_timestamp"] == (
        "2026-06-16T11:00:00-04:00"
    )
    assert [source[0]["provider_name"] for source in result.source_payloads] == [
        "Open-Meteo ECMWF IFS",
        "Open-Meteo NOAA GFS",
        "Open-Meteo DWD ICON",
    ]
    assert result.assumed_available_at <= datetime(
        2026,
        6,
        16,
        10,
        tzinfo=TRINIDAD_TZ,
    ).astimezone(result.assumed_available_at.tzinfo)


def test_replay_provider_weights_all_weather_fields_across_sampling_network(
    monkeypatch,
):
    provider = OpenMeteoReplayProvider()
    timestamps = ["2026-06-16T10:00", "2026-06-16T11:00"]
    payloads = []
    for point_index, point in enumerate(TRINIDAD_TEMPERATURE_SAMPLING_POINTS):
        hourly: dict[str, object] = {"time": timestamps}
        for model in provider.models:
            hourly[f"temperature_2m_{model}"] = [
                26.0 + point_index,
                27.0 + point_index,
            ]
            hourly[f"relative_humidity_2m_{model}"] = [
                60.0 + point_index,
                61.0 + point_index,
            ]
            hourly[f"precipitation_{model}"] = [
                point_index / 10.0,
                point_index / 10.0 + 0.1,
            ]
            hourly[f"cloud_cover_{model}"] = [
                20.0 + point_index,
                21.0 + point_index,
            ]
            hourly[f"wind_speed_10m_{model}"] = [
                10.0 + point_index,
                11.0 + point_index,
            ]
            hourly[f"wind_direction_10m_{model}"] = [350.0, 10.0]
            hourly[f"surface_pressure_{model}"] = [
                1008.0 + point_index,
                1009.0 + point_index,
            ]
            hourly[f"weather_code_{model}"] = [1, 2]
        payloads.append(
            {
                "latitude": point.latitude,
                "longitude": point.longitude,
                "hourly": hourly,
            }
        )

    monkeypatch.setattr(provider, "_request_json", lambda params: payloads)
    result = provider.get_forecast_sources(
        latitude=10.5953,
        longitude=-61.3372,
        source_cursor=datetime(2026, 6, 16, 10, tzinfo=TRINIDAD_TZ),
        hours=1,
    )

    period = result.source_payloads[0][0]
    total_weight = sum(
        point.demand_weight for point in TRINIDAD_TEMPERATURE_SAMPLING_POINTS
    )
    expected_humidity = sum(
        (61.0 + index) * point.demand_weight
        for index, point in enumerate(TRINIDAD_TEMPERATURE_SAMPLING_POINTS)
    ) / total_weight
    assert period["humidity_percent"] == pytest.approx(
        expected_humidity,
        abs=0.1,
    )
    assert period["rainfall_mm_hr"] > 0.1
    assert period["cloud_cover_percent"] > 21.0
    assert period["wind_speed_kmh"] > 11.0
    assert period["wind_direction_deg"] == pytest.approx(10.0, abs=0.1)
    assert period["weather_aggregation"]["sample_count"] == 11
