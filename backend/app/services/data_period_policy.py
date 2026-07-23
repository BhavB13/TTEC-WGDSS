from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta

from app.core.config import settings


@dataclass(frozen=True)
class DataPeriodPolicy:
    training_start: date
    training_end: date
    simulated_live_start: date
    simulated_live_end: date
    replay_archive_start: date
    replay_archive_end: date

    @classmethod
    def from_settings(cls) -> "DataPeriodPolicy":
        policy = cls(
            training_start=date.fromisoformat(settings.MODEL_TRAINING_START_DATE),
            training_end=date.fromisoformat(settings.MODEL_TRAINING_END_DATE),
            simulated_live_start=date.fromisoformat(
                settings.SIMULATED_LIVE_START_DATE
            ),
            simulated_live_end=date.fromisoformat(settings.SIMULATED_LIVE_END_DATE),
            replay_archive_start=date.fromisoformat(
                settings.JUNE_REPLAY_ARCHIVE_START_DATE
            ),
            replay_archive_end=date.fromisoformat(
                settings.JUNE_REPLAY_ARCHIVE_END_DATE
            ),
        )
        if policy.training_start > policy.training_end:
            raise ValueError("Model training start must not be after its end")
        if policy.training_end >= policy.simulated_live_start:
            raise ValueError("Training and simulated-live periods must not overlap")
        if policy.replay_archive_start > policy.replay_archive_end:
            raise ValueError(
                "Replay archive start must not be after its end"
            )
        return policy

    def is_training_timestamp(self, value: datetime) -> bool:
        return self.training_start <= value.date() <= self.training_end

    def is_simulated_live_timestamp(self, value: datetime) -> bool:
        return self.simulated_live_start <= value.date() <= self.simulated_live_end

    @property
    def training_start_at(self) -> datetime:
        return datetime.combine(self.training_start, time.min)

    @property
    def training_end_exclusive(self) -> datetime:
        return datetime.combine(
            self.training_end + timedelta(days=1),
            time.min,
        )

    @property
    def replay_archive_start_at(self) -> datetime:
        return datetime.combine(self.replay_archive_start, time.min)

    @property
    def replay_archive_end_exclusive(self) -> datetime:
        return datetime.combine(
            self.replay_archive_end + timedelta(days=1),
            time.min,
        )
