from __future__ import annotations

import copy
import json
import logging
import threading
import time
from datetime import datetime, timezone
from typing import Any

import requests

from app.core.config import settings
from app.schemas.storm import (
    StormAdvisoryLinkResponse,
    StormSystemResponse,
    StormTrackingResponse,
)

logger = logging.getLogger(__name__)


class StormTrackingService:
    def __init__(
        self,
        source_url: str | None = None,
        timeout_seconds: float | None = None,
        cache_ttl_seconds: int | None = None,
        max_attempts: int = 3,
    ) -> None:
        self.source_url = source_url or settings.NHC_CURRENT_STORMS_URL
        self.timeout_seconds = timeout_seconds or settings.NHC_STORM_TRACKING_TIMEOUT_SECONDS
        self.cache_ttl_seconds = cache_ttl_seconds or settings.NHC_STORM_TRACKING_CACHE_TTL_SECONDS
        self.max_attempts = max(1, max_attempts)
        self.session = requests.Session()
        self.session.headers.update(
            {
                "User-Agent": settings.NHC_USER_AGENT,
                "Accept": "application/json",
            }
        )
        self._cache: StormTrackingResponse | None = None
        self._cache_expires_at = 0.0
        self._lock = threading.Lock()

    def get_storm_tracking(self, force_refresh: bool = False) -> StormTrackingResponse:
        cached = self._get_cached(force_refresh)
        if cached is not None:
            return cached

        try:
            payload = self._fetch_payload()
            normalized = self._normalize_payload(payload)
        except Exception as exc:  # pragma: no cover - external service resilience
            logger.warning("Storm tracking feed unavailable: %s", exc)
            normalized = StormTrackingResponse(
                source_url=self.source_url,
                status="unavailable",
                fetched_at=datetime.now(timezone.utc),
                message="Storm tracking feed is temporarily unavailable",
                active_storms=[],
            )

        self._set_cache(normalized)
        return copy.deepcopy(normalized)

    def _fetch_payload(self) -> dict[str, Any]:
        last_error: Exception | None = None

        for attempt in range(1, self.max_attempts + 1):
            try:
                response = self.session.get(self.source_url, timeout=self.timeout_seconds)
                response.raise_for_status()
                return response.json()
            except (requests.RequestException, json.JSONDecodeError, ValueError) as exc:
                last_error = exc
                logger.warning(
                    "Storm tracking fetch attempt %s failed: %s",
                    attempt,
                    exc,
                )
                if attempt < self.max_attempts:
                    time.sleep(0.35 * attempt)

        raise RuntimeError("Unable to retrieve storm tracking feed") from last_error

    def _normalize_payload(self, payload: dict[str, Any]) -> StormTrackingResponse:
        storms = payload.get("activeStorms") if isinstance(payload, dict) else []
        active_storms = [
            self._normalize_storm(storm)
            for storm in storms
            if isinstance(storm, dict)
        ]
        fetched_at = datetime.now(timezone.utc)
        message = (
            "No active tropical cyclones reported by NHC"
            if not active_storms
            else f"{len(active_storms)} active storm(s) reported by NHC"
        )
        return StormTrackingResponse(
            source_url=self.source_url,
            status="available",
            fetched_at=fetched_at,
            message=message,
            active_storms=active_storms,
        )

    def _normalize_storm(self, storm: dict[str, Any]) -> StormSystemResponse:
        public_advisory = self._normalize_link(storm.get("publicAdvisory"))
        forecast_advisory = self._normalize_link(storm.get("forecastAdvisory"))
        forecast_discussion = self._normalize_link(storm.get("forecastDiscussion"))
        forecast_graphics = self._normalize_link(storm.get("forecastGraphics"))

        return StormSystemResponse(
            id=str(storm.get("id") or storm.get("binNumber") or storm.get("name") or "unknown"),
            bin_number=self._coerce_optional_string(storm.get("binNumber")),
            name=self._coerce_optional_string(storm.get("name")),
            basin=self._coerce_optional_string(storm.get("basin")),
            classification=self._coerce_optional_string(storm.get("classification")),
            classification_label=self._classification_label(storm.get("classification")),
            intensity_knots=self._coerce_optional_float(storm.get("intensity")),
            pressure_mb=self._coerce_optional_float(storm.get("pressure")),
            latitude=self._coerce_optional_string(storm.get("latitude")),
            longitude=self._coerce_optional_string(storm.get("longitude")),
            latitude_numeric=self._coerce_optional_float(storm.get("latitudeNumeric")),
            longitude_numeric=self._coerce_optional_float(storm.get("longitudeNumeric")),
            movement_direction_deg=self._coerce_optional_float(storm.get("movementDir")),
            movement_speed_mph=self._coerce_optional_float(storm.get("movementSpeed")),
            last_update=self._coerce_datetime(storm.get("lastUpdate")),
            public_advisory=public_advisory,
            forecast_advisory=forecast_advisory,
            forecast_discussion=forecast_discussion,
            forecast_graphics=forecast_graphics,
            forecast_track_kmz_url=self._extract_nested_url(
                storm.get("forecastTrack"),
                ("kmzFile", "url"),
            ),
            wind_speed_probabilities_url=self._extract_nested_url(
                storm.get("windSpeedProbabilities"),
                ("url",),
            ),
        )

    @staticmethod
    def _normalize_link(value: Any) -> StormAdvisoryLinkResponse | None:
        if not isinstance(value, dict):
            return None
        return StormAdvisoryLinkResponse(
            advisory_number=StormTrackingService._coerce_optional_string(
                value.get("advNum") or value.get("advisoryNumber")
            ),
            issuance=StormTrackingService._coerce_datetime(value.get("issuance")),
            url=StormTrackingService._coerce_optional_string(value.get("url")),
        )

    @staticmethod
    def _classification_label(value: Any) -> str | None:
        classification = str(value or "").strip().upper()
        if not classification:
            return None

        labels = {
            "PTC": "Potential Tropical Cyclone",
            "TD": "Tropical Depression",
            "TS": "Tropical Storm",
            "STS": "Subtropical Storm",
            "HU": "Hurricane",
            "TY": "Typhoon",
        }
        return labels.get(classification, classification)

    @staticmethod
    def _coerce_optional_string(value: Any) -> str | None:
        if value is None:
            return None
        text = str(value).strip()
        return text or None

    @staticmethod
    def _coerce_optional_float(value: Any) -> float | None:
        if value in (None, ""):
            return None
        try:
            return float(value)
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _coerce_datetime(value: Any) -> datetime | None:
        if value in (None, ""):
            return None
        if isinstance(value, datetime):
            return value
        text = str(value).strip()
        for fmt in (
            "%Y-%m-%dT%H:%M:%SZ",
            "%Y-%m-%dT%H:%M:%S.%fZ",
            "%Y-%m-%d %H:%M:%S",
        ):
            try:
                parsed = datetime.strptime(text, fmt)
                return parsed.replace(tzinfo=timezone.utc)
            except ValueError:
                continue
        try:
            parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
            return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
        except ValueError:
            return None

    @staticmethod
    def _extract_nested_url(value: Any, keys: tuple[str, ...]) -> str | None:
        if not isinstance(value, dict):
            return None
        for key in keys:
            candidate = value.get(key)
            if isinstance(candidate, str) and candidate.strip():
                return candidate.strip()
        return None

    def _get_cached(self, force_refresh: bool) -> StormTrackingResponse | None:
        if force_refresh:
            return None
        with self._lock:
            if self._cache is None or time.time() >= self._cache_expires_at:
                return None
            return copy.deepcopy(self._cache)

    def _set_cache(self, payload: StormTrackingResponse) -> None:
        with self._lock:
            self._cache = copy.deepcopy(payload)
            self._cache_expires_at = time.time() + self.cache_ttl_seconds
