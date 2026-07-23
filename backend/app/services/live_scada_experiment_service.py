from __future__ import annotations

import hashlib
import json
import math
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any
from uuid import uuid4

from app.core.config import settings
from app.providers.excel_snapshot_scada_provider import (
    ExcelSnapshotScadaProvider,
    TRINIDAD_TZ,
)
from app.schemas.live_scada_experiment import (
    ExperimentWeatherSnapshot,
    ExperimentalForecastPoint,
    ExperimentalRiskPoint,
    ExperimentalSessionArtifacts,
    LiveScadaExperimentStatus,
    LiveScadaTestSession,
)
from app.services.frozen_snapshot_model_service import FrozenSnapshotModelService
from app.services.weather_service import WeatherService


class LiveScadaSessionRepository:
    def __init__(self, root: str | Path | None = None) -> None:
        configured = root or settings.LIVE_SCADA_SESSION_ROOT
        path = Path(configured)
        self.root = path if path.is_absolute() else Path.cwd() / path

    def save(
        self,
        session: LiveScadaTestSession,
        raw_rows: list[dict[str, object]],
        cleaned_rows: list[dict[str, object]],
    ) -> LiveScadaTestSession:
        session_dir = self.root / session.session_id
        session_dir.mkdir(parents=True, exist_ok=False)
        paths = ExperimentalSessionArtifacts(
            manifest_path=str(session_dir / "manifest.json"),
            raw_audit_path=str(session_dir / "raw_records.jsonl"),
            cleaned_audit_path=str(session_dir / "cleaned_records.jsonl"),
            weather_snapshot_path=str(session_dir / "weather_snapshot.json"),
            test_report_path=str(session_dir / "TEST_REPORT.md"),
        )
        session.artifacts = paths
        _write_jsonl(Path(paths.raw_audit_path), raw_rows)
        _write_jsonl(Path(paths.cleaned_audit_path), cleaned_rows)
        _write_json(Path(paths.weather_snapshot_path), session.weather.model_dump(mode="json"))
        _write_json(Path(paths.manifest_path), session.model_dump(mode="json"))
        Path(paths.test_report_path).write_text(_report(session), encoding="utf-8")
        (self.root / "latest").write_text(session.session_id, encoding="ascii")
        return session

    def latest(self) -> LiveScadaTestSession | None:
        marker = self.root / "latest"
        if not marker.is_file():
            return None
        manifest = self.root / marker.read_text(encoding="ascii").strip() / "manifest.json"
        if not manifest.is_file():
            return None
        return LiveScadaTestSession.model_validate_json(
            manifest.read_text(encoding="utf-8")
        )


class LiveScadaExperimentService:
    def __init__(
        self,
        *,
        source_path: str | Path | None = None,
        weather_service: WeatherService | None = None,
        repository: LiveScadaSessionRepository | None = None,
        model_service: FrozenSnapshotModelService | None = None,
    ) -> None:
        self.source_path = Path(source_path or settings.LIVE_SCADA_SNAPSHOT_PATH)
        self.weather_service = weather_service or WeatherService()
        self.repository = repository or LiveScadaSessionRepository()
        self.model_service = model_service or FrozenSnapshotModelService(
            settings.LIVE_SCADA_MODEL_ARTIFACT_PATH
        )

    def status(self) -> LiveScadaExperimentStatus:
        latest = self.repository.latest()
        configured = bool(str(self.source_path)) and self.source_path.is_file()
        return LiveScadaExperimentStatus(
            enabled=True,
            configured_source=configured,
            source_path=self.source_path.name if configured else None,
            latest_session_id=latest.session_id if latest else None,
            latest_available_timestamp=(
                latest.source.latest_valid_timestamp if latest else None
            ),
            message=(
                "Static SCADA snapshot is configured"
                if configured
                else "Set LIVE_SCADA_SNAPSHOT_PATH to run the experiment"
            ),
        )

    async def run(self) -> LiveScadaTestSession:
        provider = ExcelSnapshotScadaProvider(self.source_path)
        imported = provider.load_snapshot()
        boundary = imported.summary.latest_valid_timestamp
        if boundary is None:
            raise ValueError("Snapshot has no usable common timestamp boundary")
        weather = await self._weather_snapshot(boundary)
        model_inputs = self._model_inputs(imported.summary, weather)
        model, forecasts = self.model_service.predict(model_inputs)
        references = self._reference_forecasts(imported.summary, model_inputs)
        risk = self._risk(forecasts or references, imported.summary)
        warnings = list(imported.summary.warnings) + list(model.warnings)
        if not forecasts:
            warnings.append(
                "Generation-need probability is unavailable because no approved "
                "frozen fitted model artifact is configured."
            )
        session = LiveScadaTestSession(
            session_id=f"{boundary:%Y%m%dT%H%M}-{uuid4().hex[:10]}",
            created_at=datetime.now(TRINIDAD_TZ),
            source=imported.summary,
            model=model,
            weather=weather,
            model_inputs=model_inputs,
            forecasts=forecasts,
            reference_forecasts=references,
            risk=risk,
            validation_warnings=warnings,
            processing_metadata={
                "database_writes": 0,
                "source_mutated": False,
                "weather_boundary_policy": (
                    "SCADA temperature at/before boundary; provider forecast "
                    "targets strictly after boundary"
                ),
                "training_policy_verified": model.status in {
                    "READY",
                    "NO_FROZEN_MODEL_ARTIFACT",
                },
                "static_snapshot_accuracy_limitation": (
                    "Later actual SCADA values are required to measure forecast accuracy"
                ),
                "snapshot_age_seconds": max(
                    0.0,
                    (
                        datetime.now(TRINIDAD_TZ)
                        - imported.summary.latest_valid_timestamp
                    ).total_seconds(),
                ),
                "freshness_status": "STATIC_SNAPSHOT",
            },
        )
        return self.repository.save(
            session, imported.raw_audit_rows, imported.cleaned_audit_rows
        )

    async def _weather_snapshot(self, boundary: datetime) -> ExperimentWeatherSnapshot:
        warnings: list[str] = []
        current: dict[str, object] | None = None
        forecast: list[dict[str, object]] = []
        try:
            current = await self.weather_service.get_current_weather(
                settings.DEFAULT_LATITUDE, settings.DEFAULT_LONGITUDE, True
            )
            provider_forecast = await self.weather_service.get_forecast(
                settings.DEFAULT_LATITUDE, settings.DEFAULT_LONGITUDE, 2, True
            )
            for item in provider_forecast:
                timestamp = _item_timestamp(item)
                if timestamp is not None and timestamp > boundary:
                    forecast.append(item)
        except Exception as exc:
            warnings.append(f"Weather fetch failed: {type(exc).__name__}: {exc}")
        payload = {"current": current, "forecast": forecast}
        response_hash = hashlib.sha256(
            json.dumps(payload, sort_keys=True, default=str).encode("utf-8")
        ).hexdigest()
        providers = sorted(
            {
                str(item.get("provider_name"))
                for item in forecast
                if item.get("provider_name")
            }
        )
        return ExperimentWeatherSnapshot(
            fetched_at=datetime.now(TRINIDAD_TZ),
            boundary_timestamp=boundary,
            current=current,
            forecast=forecast,
            post_boundary_weather_source=", ".join(providers) or None,
            response_hash=response_hash,
            warnings=warnings,
        )

    @staticmethod
    def _model_inputs(summary, weather: ExperimentWeatherSnapshot) -> list[dict[str, object]]:
        points = [point for point in summary.hourly_series if point.available_at <= summary.latest_valid_timestamp]
        latest = points[-1] if points else None
        demands = [point.demand_mw for point in points if point.demand_mw is not None]
        inputs: list[dict[str, object]] = []
        for horizon in (1, 2, 6):
            target = summary.latest_valid_timestamp + timedelta(hours=horizon)
            forecast_weather = _nearest_forecast(weather.forecast, target)
            features = {
                "current_demand_mw": latest.demand_mw if latest else None,
                "lag_1h_demand_mw": demands[-2] if len(demands) > 1 else None,
                "rolling_3h_demand_mw": (
                    sum(demands[-3:]) / len(demands[-3:]) if demands else None
                ),
                "generation_tra_mw": latest.generation_tra_mw if latest else None,
                "spinning_reserve_mw": latest.spinning_reserve_mw if latest else None,
                "temperature_c": latest.temperature_c if latest else None,
                "forecast_temperature_c": _weather_value(forecast_weather, "temperature_c"),
                "forecast_humidity_percent": _weather_value(forecast_weather, "humidity_percent"),
                "forecast_rainfall_mm_hr": _weather_value(forecast_weather, "rainfall_mm_hr"),
                "forecast_cloud_cover_percent": _weather_value(forecast_weather, "cloud_cover_percent"),
                "forecast_wind_speed_kmh": _weather_value(forecast_weather, "wind_speed_kmh"),
                "hour_of_day": target.hour,
                "day_of_week": target.weekday(),
            }
            inputs.append(
                {
                    "horizon_hours": horizon,
                    "feature_timestamp": summary.latest_valid_timestamp,
                    "forecast_timestamp": target,
                    "features": features,
                    "input_quality": latest.quality_status if latest else "MISSING",
                    "leakage_guard": "all SCADA features available at/before boundary",
                }
            )
        return inputs

    @staticmethod
    def _reference_forecasts(summary, model_inputs) -> list[ExperimentalForecastPoint]:
        evidence = {item.field: item for item in summary.field_evidence}
        demand = evidence.get("current_demand_mw")
        if demand is None or demand.cleaned_value is None:
            return []
        return [
            ExperimentalForecastPoint(
                horizon_hours=int(item["horizon_hours"]),
                forecast_timestamp=item["forecast_timestamp"],
                forecast_demand_mw=round(demand.cleaned_value, 2),
                uncertainty_mw=0.0,
                lower_bound_mw=round(demand.cleaned_value, 2),
                upper_bound_mw=round(demand.cleaned_value, 2),
                model_name="Persistence reference",
                model_version="reference-v1",
                status="REFERENCE_ONLY",
                input_quality=str(item["input_quality"]),
                reasons=["Current demand held constant; not an ML forecast"],
            )
            for item in model_inputs
        ]

    @staticmethod
    def _risk(forecasts, summary) -> list[ExperimentalRiskPoint]:
        evidence = {item.field: item for item in summary.field_evidence}
        tra = evidence.get("generation_tra_mw")
        generation = tra.cleaned_value if tra and tra.cleaned_value is not None else None
        results: list[ExperimentalRiskPoint] = []
        for forecast in forecasts:
            probability = None
            if generation is not None and forecast.uncertainty_mw > 0:
                threshold = generation - settings.CAPACITY_RISK_REQUIRED_RESERVE_MW
                z = (threshold - forecast.forecast_demand_mw) / forecast.uncertainty_mw
                probability = 1.0 - 0.5 * (1.0 + math.erf(z / math.sqrt(2.0)))
            level = (
                "UNAVAILABLE"
                if probability is None
                else "HIGH" if probability > 0.65 else "MEDIUM" if probability >= 0.30 else "LOW"
            )
            results.append(
                ExperimentalRiskPoint(
                    horizon_hours=forecast.horizon_hours,
                    forecast_timestamp=forecast.forecast_timestamp,
                    generation_tra_mw=generation,
                    forecast_demand_mw=forecast.forecast_demand_mw,
                    projected_tra_minus_demand_mw=(
                        round(generation - forecast.forecast_demand_mw, 2)
                        if generation is not None
                        else None
                    ),
                    required_reserve_mw=settings.CAPACITY_RISK_REQUIRED_RESERVE_MW,
                    generation_need_probability=(
                        round(probability, 4) if probability is not None else None
                    ),
                    risk_level=level,
                    status="CALCULATED" if probability is not None else "UNAVAILABLE",
                    reasons=["TRA held at latest accepted snapshot value"],
                )
            )
        return results


def _item_timestamp(item: dict[str, Any]) -> datetime | None:
    value = item.get("forecast_timestamp") or item.get("timestamp") or item.get("time")
    if not isinstance(value, str):
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        return parsed.replace(tzinfo=TRINIDAD_TZ) if parsed.tzinfo is None else parsed.astimezone(TRINIDAD_TZ)
    except ValueError:
        return None


def _nearest_forecast(items: list[dict[str, object]], target: datetime) -> dict[str, object] | None:
    candidates = [(abs((timestamp - target).total_seconds()), item) for item in items if (timestamp := _item_timestamp(item)) is not None]
    return min(candidates, key=lambda pair: pair[0])[1] if candidates else None


def _weather_value(item: dict[str, object] | None, key: str) -> object:
    return item.get(key) if item else None


def _write_json(path: Path, value: object) -> None:
    path.write_text(json.dumps(value, indent=2, default=str), encoding="utf-8")


def _write_jsonl(path: Path, rows: list[dict[str, object]]) -> None:
    path.write_text(
        "".join(json.dumps(row, default=str) + "\n" for row in rows),
        encoding="utf-8",
    )


def _report(session: LiveScadaTestSession) -> str:
    source = session.source
    return f"""# Live SCADA Snapshot Test Report

## Scope

This is an experimental, read-only static snapshot test. It does not connect to
live SCADA and cannot control generation equipment.

## Import

- Session: `{session.session_id}`
- Source: `{source.source_filename}`
- SHA-256: `{source.source_file_hash}`
- Available range: `{source.available_start}` to `{source.available_end}`
- Common valid boundary: `{source.latest_valid_timestamp}`
- Raw / cleaned records: {source.raw_record_count} / {source.cleaned_record_count}
- Missing required variables: {", ".join(source.missing_required_variables) or "None"}

## Model

- Status: `{session.model.status}`
- Version: `{session.model.model_version or "Unavailable"}`
- Training policy: October-May only; June and this July snapshot excluded
- Preprocessing refit: `{session.model.preprocessing_refit}`
- Model forecasts: {len(session.forecasts)}
- Reference-only forecasts: {len(session.reference_forecasts)}

## Weather

- Fetched at: `{session.weather.fetched_at}`
- Response SHA-256: `{session.weather.response_hash}`
- Post-boundary source: `{session.weather.post_boundary_weather_source or "Unavailable"}`

## Quality and limitations

{chr(10).join(f"- {warning}" for warning in session.validation_warnings)}

A static snapshot can test parsing, model behavior, and operational calculations,
but it cannot establish forecast accuracy. Later actual SCADA values are required
for a valid out-of-sample comparison.
"""
