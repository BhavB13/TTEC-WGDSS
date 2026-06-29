from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from sqlalchemy import func, select
from sqlalchemy.exc import SQLAlchemyError

from app.database.session import SessionLocal
from app.models.calibration import CalibrationScenarioProfile, ScadaTemperatureSample
from app.schemas.calibration import (
    CalibrationPointResponse,
    CalibrationScenarioResponse,
    CalibrationSnapshotResponse,
)

TRINIDAD_TZ = ZoneInfo("America/Port_of_Spain")


class CalibrationService:
    def __init__(self, session_factory=SessionLocal) -> None:
        self.session_factory = session_factory

    def get_snapshot(self, weather: dict[str, Any] | None = None) -> CalibrationSnapshotResponse | None:
        try:
            with self.session_factory() as session:
                scenario_rows = session.scalars(
                    select(CalibrationScenarioProfile).order_by(
                        CalibrationScenarioProfile.scenario_key,
                        CalibrationScenarioProfile.hour_of_day,
                    )
                ).all()
                scada_rows = session.scalars(
                    select(ScadaTemperatureSample).order_by(
                        ScadaTemperatureSample.scenario_key,
                        ScadaTemperatureSample.sample_timestamp,
                    )
                ).all()
        except SQLAlchemyError:
            # Calibration enriches the live snapshot but must never prevent it.
            return None

        if not scenario_rows and not scada_rows:
            return None

        scenarios = self._build_scenarios(scenario_rows, scada_rows)
        selected_key, scenario_scores, selection_confidence = self._select_scenario(
            weather,
            scenarios,
            self._current_hour(),
        )
        selected_scenario = scenarios.get(selected_key) if selected_key else None
        selected_hour = self._current_hour()

        selected_profile = None
        selected_next_profile = None
        if selected_scenario is not None:
            selected_profile = self._find_profile(selected_scenario, selected_hour)
            selected_next_profile = self._find_profile(selected_scenario, selected_hour + 1)

        selected_temperature = self._selected_temperature(
            selected_key=selected_key,
            scada_rows=scada_rows,
            selected_hour=selected_hour,
        )

        selected_demand = selected_profile.demand_mw if selected_profile is not None else None
        selected_spin = selected_profile.spin_mw if selected_profile is not None else None

        return CalibrationSnapshotResponse(
            source_archive=scenario_rows[0].source_archive if scenario_rows else scada_rows[0].source_archive,
            imported_at=scenario_rows[0].created_at if scenario_rows else scada_rows[0].created_at,
            selected_scenario_key=selected_key,
            selected_scenario_label=selected_scenario.scenario_label if selected_scenario else None,
            selected_hour=selected_hour,
            selected_temperature_c=selected_temperature,
            selected_demand_mw=selected_demand,
            selected_next_demand_mw=selected_next_profile.demand_mw if selected_next_profile else None,
            selected_spin_mw=selected_spin,
            selected_next_spin_mw=selected_next_profile.spin_mw if selected_next_profile else None,
            selection_reason=self._selection_reason(weather, selected_key),
            selection_confidence=selection_confidence,
            scenario_scores=scenario_scores,
            scenarios=list(scenarios.values()),
        )

    def _build_scenarios(
        self,
        scenario_rows: list[CalibrationScenarioProfile],
        scada_rows: list[ScadaTemperatureSample],
    ) -> dict[str, CalibrationScenarioResponse]:
        scenario_points: dict[str, list[CalibrationPointResponse]] = defaultdict(list)
        scenario_meta: dict[str, CalibrationScenarioProfile] = {}
        for row in scenario_rows:
            scenario_meta[row.scenario_key] = row
            scenario_points[row.scenario_key].append(
                CalibrationPointResponse(
                    hour=row.hour_of_day,
                    demand_mw=row.demand_mw,
                    spin_mw=row.spin_mw,
                    temperature_c=row.temperature_c,
                    quality_status=row.quality_status,
                )
            )

        temperature_points: dict[str, list[CalibrationPointResponse]] = defaultdict(list)
        for row in scada_rows:
            if row.quality_status.strip().lower() != "good":
                continue
            temperature_points[row.scenario_key].append(
                CalibrationPointResponse(
                    hour=self._hour_from_timestamp(row.sample_timestamp),
                    temperature_c=row.avg_value_c,
                    quality_status=row.quality_status,
                )
            )

        bundles: dict[str, CalibrationScenarioResponse] = {}
        for scenario_key, meta in scenario_meta.items():
            bundles[scenario_key] = CalibrationScenarioResponse(
                scenario_key=scenario_key,
                scenario_label=meta.scenario_label,
                operating_regime=meta.operating_regime,
                source_workbook=meta.source_workbook,
                source_sheet=meta.source_sheet,
                demand_curve=sorted(scenario_points[scenario_key], key=lambda point: point.hour),
                scada_temperature_trace=self._compress_temperature_trace(
                    temperature_points.get(scenario_key, [])
                ),
            )

        order = {"hot": 0, "typical": 1, "rainy": 2}
        return dict(sorted(bundles.items(), key=lambda item: order.get(item[0], 99)))

    def _compress_temperature_trace(
        self,
        points: list[CalibrationPointResponse],
    ) -> list[CalibrationPointResponse]:
        if not points:
            return []

        grouped: dict[int, list[CalibrationPointResponse]] = defaultdict(list)
        for point in points:
            grouped[point.hour].append(point)

        compressed: list[CalibrationPointResponse] = []
        for hour in sorted(grouped):
            hour_points = grouped[hour]
            temperatures = [point.temperature_c for point in hour_points if point.temperature_c is not None]
            if not temperatures:
                continue
            compressed.append(
                CalibrationPointResponse(
                    hour=hour,
                    temperature_c=round(sum(temperatures) / len(temperatures), 2),
                    quality_status=hour_points[0].quality_status or "Aggregated",
                )
            )
        return compressed

    def _select_scenario(
        self,
        weather: dict[str, Any] | None,
        scenarios: dict[str, CalibrationScenarioResponse],
        selected_hour: int,
    ) -> tuple[str | None, dict[str, float], float | None]:
        if not scenarios:
            return None, {}, None
        if not weather:
            key = "typical" if "typical" in scenarios else next(iter(scenarios))
            return key, {key: 1.0}, 1.0

        temperature_c = float(weather.get("temperature_c", 0.0) or 0.0)
        humidity = float(weather.get("humidity_percent", 0.0) or 0.0)
        rainfall = float(weather.get("rainfall_mm_hr", 0.0) or 0.0)
        cloud = float(weather.get("cloud_cover_percent", 0.0) or 0.0)
        condition = str(weather.get("weather_condition", "")).lower()

        scores: dict[str, float] = {}
        for key, scenario in scenarios.items():
            reference_temperature = self._scenario_temperature_at_hour(scenario, selected_hour)
            temperature_similarity = (
                max(0.0, 1.0 - abs(temperature_c - reference_temperature) / 8.0)
                if reference_temperature is not None
                else 0.5
            )

            if key == "rainy":
                weather_fit = (
                    min(rainfall / 8.0, 1.0) * 0.45
                    + min(cloud / 100.0, 1.0) * 0.20
                    + min(humidity / 100.0, 1.0) * 0.10
                    + (0.25 if any(token in condition for token in ("rain", "drizzle", "shower")) else 0.0)
                )
            elif key == "hot":
                weather_fit = (
                    min(max(temperature_c - 27.0, 0.0) / 7.0, 1.0) * 0.55
                    + min(max(humidity - 60.0, 0.0) / 40.0, 1.0) * 0.20
                    + max(0.0, 1.0 - min(rainfall / 3.0, 1.0)) * 0.15
                )
            else:
                weather_fit = (
                    max(0.0, 1.0 - abs(temperature_c - 28.0) / 6.0) * 0.35
                    + max(0.0, 1.0 - min(rainfall / 4.0, 1.0)) * 0.25
                    + max(0.0, 1.0 - abs(cloud - 45.0) / 70.0) * 0.15
                )

            scores[key] = round(weather_fit * 0.75 + temperature_similarity * 0.25, 4)

        ranked = sorted(scores.items(), key=lambda item: item[1], reverse=True)
        selected_key = ranked[0][0]
        margin = ranked[0][1] - ranked[1][1] if len(ranked) > 1 else ranked[0][1]
        confidence = round(max(0.0, min(1.0, 0.5 + margin)), 2)
        return selected_key, scores, confidence

    @staticmethod
    def _scenario_temperature_at_hour(
        scenario: CalibrationScenarioResponse,
        selected_hour: int,
    ) -> float | None:
        target_hour = selected_hour % 24 or 24
        candidates = [
            point for point in scenario.scada_temperature_trace if point.temperature_c is not None
        ]
        if not candidates:
            return None
        nearest = min(candidates, key=lambda point: abs(point.hour - target_hour))
        return nearest.temperature_c

    def _selected_temperature(
        self,
        selected_key: str | None,
        scada_rows: list[ScadaTemperatureSample],
        selected_hour: int,
    ) -> float | None:
        if not selected_key or not scada_rows:
            return None

        filtered = [
            row
            for row in scada_rows
            if row.scenario_key == selected_key and row.quality_status.lower() == "good"
        ]
        if not filtered:
            filtered = [row for row in scada_rows if row.scenario_key == selected_key]

        if not filtered:
            return None

        target_hour = selected_hour % 24 or 24
        best = min(
            filtered,
            key=lambda row: abs(self._hour_from_timestamp(row.sample_timestamp) - target_hour),
        )
        return round(best.avg_value_c, 2)

    def _find_profile(
        self,
        scenario: CalibrationScenarioResponse,
        selected_hour: int,
    ) -> CalibrationPointResponse | None:
        target_hour = selected_hour % 24 or 24
        for point in scenario.demand_curve:
            if point.hour == target_hour:
                return point
        if scenario.demand_curve:
            return min(scenario.demand_curve, key=lambda point: abs(point.hour - target_hour))
        return None

    def _selection_reason(self, weather: dict[str, Any] | None, selected_key: str | None) -> str:
        if not weather:
            return "Imported calibration data available"
        if selected_key == "rainy":
            return "Rain and cloud cover indicate the rainy operating regime"
        if selected_key == "hot":
            return "Higher ambient temperature and humidity indicate the hot operating regime"
        return "Weather conditions align with the typical operating regime"

    @staticmethod
    def _current_hour() -> int:
        return datetime.now(TRINIDAD_TZ).hour or 24

    @staticmethod
    def _hour_from_timestamp(timestamp: datetime) -> int:
        localized = (
            timestamp.replace(tzinfo=TRINIDAD_TZ)
            if timestamp.tzinfo is None
            else timestamp.astimezone(TRINIDAD_TZ)
        )
        return localized.hour or 24
