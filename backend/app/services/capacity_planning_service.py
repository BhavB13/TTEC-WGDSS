from __future__ import annotations

import math
import threading
import time
from collections import OrderedDict
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from itertools import product
from statistics import NormalDist

from app.core.config import settings
from app.schemas.capacity_plan import (
    CapacityActionSource,
    CapacityActionStatus,
    CapacityPlanEvaluateRequest,
    CapacityPlanHorizonResponse,
    CapacityPlanResponse,
    CapacityPlanStatus,
    CapacityStartActionRequest,
    CapacityStartActionResponse,
    GenerationBlockDefinitionResponse,
)
from app.schemas.grid import GridStatusResponse
from app.schemas.probability import ProbabilityResponse, RiskHorizonResponse


ADVISORY_NOTICE = "ADVISORY ONLY - MANUAL OPERATOR ACTION REQUIRED"
BASELINE_TRA_BASIS = "CURRENT_TRA_HELD_NO_ACTION"
PLANNED_TRA_BASIS = "CURRENT_TRA_PLUS_PROPOSED_START_BLOCKS"


class CapacityPlanContextNotFound(LookupError):
    pass


class CapacityPlanContextExpired(LookupError):
    pass


class InvalidCapacityPlan(ValueError):
    pass


@dataclass(frozen=True)
class _PlanningContext:
    snapshot_id: str
    issue_time: datetime
    current_tra_mw: float
    current_tra_observed_at: datetime | None
    current_tra_source: str
    current_tra_quality_status: str
    current_tra_missing_fields: tuple[str, ...]
    total_available_capacity_mw: float | None
    baseline_probability: ProbabilityResponse
    registered_monotonic: float


class CapacityPlanningService:
    """Evaluate advisory aggregate start scenarios against one dashboard snapshot."""

    def __init__(
        self,
        context_ttl_seconds: int | None = None,
        max_contexts: int | None = None,
    ) -> None:
        self.context_ttl_seconds = max(
            1,
            context_ttl_seconds or settings.CAPACITY_PLAN_CONTEXT_TTL_SECONDS,
        )
        self.max_contexts = max(
            1,
            max_contexts or settings.CAPACITY_PLAN_MAX_CONTEXTS,
        )
        self._contexts: OrderedDict[str, _PlanningContext] = OrderedDict()
        self._lock = threading.Lock()

    def build_snapshot_plan(
        self,
        snapshot_id: str,
        grid: GridStatusResponse,
        probability: ProbabilityResponse,
    ) -> CapacityPlanResponse:
        observed_at = _aware_datetime(grid.timestamp)
        issue_time = (
            observed_at
            if _uses_replay_clock(grid.source_provider) and observed_at is not None
            else datetime.now(observed_at.tzinfo if observed_at is not None else timezone.utc)
        )
        source = _tra_source_label(grid.source_provider)
        context = _PlanningContext(
            snapshot_id=snapshot_id,
            issue_time=issue_time,
            current_tra_mw=float(grid.current_generation_mw),
            current_tra_observed_at=observed_at,
            current_tra_source=source,
            current_tra_quality_status=str(grid.quality_status),
            current_tra_missing_fields=tuple(grid.missing_fields),
            total_available_capacity_mw=float(grid.total_available_capacity_mw),
            baseline_probability=probability,
            registered_monotonic=time.monotonic(),
        )
        self._register(context)
        recommended = self._recommend_actions(context)
        source_kind = (
            CapacityActionSource.SYSTEM_RECOMMENDED
            if recommended
            else CapacityActionSource.NONE
        )
        return self._response(
            context,
            evaluated_actions=recommended,
            recommended_actions=recommended,
            action_source=source_kind,
        )

    def evaluate_what_if(
        self,
        request: CapacityPlanEvaluateRequest,
    ) -> CapacityPlanResponse:
        context = self._get_context(request.snapshot_id)
        recommended = self._recommend_actions(context)
        evaluated = self._materialize_actions(
            context,
            request.actions,
            automatic=False,
        )
        return self._response(
            context,
            evaluated_actions=evaluated,
            recommended_actions=recommended,
            action_source=CapacityActionSource.OPERATOR_WHAT_IF,
        )

    def block_definitions(self) -> tuple[GenerationBlockDefinitionResponse, ...]:
        definitions: list[GenerationBlockDefinitionResponse] = [
            GenerationBlockDefinitionResponse(
                block_id=settings.CAPACITY_PLAN_SMALL_BLOCK_ID,
                label=settings.CAPACITY_PLAN_SMALL_BLOCK_LABEL,
                block_class="SMALL",
                unit_capacity_mw=settings.CAPACITY_PLAN_SMALL_BLOCK_CAPACITY_MW,
                startable_count=settings.CAPACITY_PLAN_SMALL_STARTABLE_COUNT,
                startup_lead_time_minutes=(
                    settings.CAPACITY_PLAN_SMALL_STARTUP_LEAD_MINUTES
                ),
                enabled=(
                    settings.CAPACITY_PLAN_SMALL_STARTABLE_COUNT > 0
                    and settings.CAPACITY_PLAN_SMALL_BLOCK_CAPACITY_MW > 0
                ),
                provenance="CONFIGURABLE_PROTOTYPE_ROSTER",
                verification_status=(
                    settings.CAPACITY_PLAN_SMALL_VERIFICATION_STATUS
                ),
            )
        ]
        for index, capacity in enumerate(_heavy_block_capacities(), start=1):
            definitions.append(
                GenerationBlockDefinitionResponse(
                    block_id=f"heavy-start-{index}",
                    label=f"Heavy start block {index}",
                    block_class="HEAVY",
                    unit_capacity_mw=capacity,
                    startable_count=1,
                    startup_lead_time_minutes=(
                        settings.CAPACITY_PLAN_HEAVY_STARTUP_LEAD_MINUTES
                    ),
                    enabled=True,
                    provenance="CONFIGURABLE_OPERATOR_ROSTER",
                    verification_status=(
                        settings.CAPACITY_PLAN_HEAVY_VERIFICATION_STATUS
                    ),
                )
            )
        if not any(item.block_class == "HEAVY" for item in definitions):
            definitions.append(
                GenerationBlockDefinitionResponse(
                    block_id="heavy-start-unconfigured",
                    label="Heavy start capacity",
                    block_class="HEAVY",
                    unit_capacity_mw=None,
                    startable_count=0,
                    startup_lead_time_minutes=(
                        settings.CAPACITY_PLAN_HEAVY_STARTUP_LEAD_MINUTES
                    ),
                    enabled=False,
                    provenance="CAPACITY_NOT_CONFIGURED",
                    verification_status="UNCONFIGURED",
                )
            )
        return tuple(definitions)

    def _register(self, context: _PlanningContext) -> None:
        with self._lock:
            self._evict_expired_locked()
            self._contexts[context.snapshot_id] = context
            self._contexts.move_to_end(context.snapshot_id)
            while len(self._contexts) > self.max_contexts:
                self._contexts.popitem(last=False)

    def _get_context(self, snapshot_id: str) -> _PlanningContext:
        with self._lock:
            context = self._contexts.get(snapshot_id)
            if context is None:
                raise CapacityPlanContextNotFound(
                    "Capacity-plan snapshot is unknown; refresh the dashboard"
                )
            if self._is_expired(context):
                self._contexts.pop(snapshot_id, None)
                raise CapacityPlanContextExpired(
                    "Capacity-plan snapshot has expired; refresh the dashboard"
                )
            self._contexts.move_to_end(snapshot_id)
            return context

    def _evict_expired_locked(self) -> None:
        expired = [
            snapshot_id
            for snapshot_id, context in self._contexts.items()
            if self._is_expired(context)
        ]
        for snapshot_id in expired:
            self._contexts.pop(snapshot_id, None)

    def _is_expired(self, context: _PlanningContext) -> bool:
        return (
            time.monotonic() - context.registered_monotonic
            > self.context_ttl_seconds
        )

    def _recommend_actions(
        self,
        context: _PlanningContext,
    ) -> list[CapacityStartActionResponse]:
        baseline = self._baseline_profile(context)
        target = settings.CAPACITY_RISK_WATCH_PROBABILITY_THRESHOLD
        first_at_risk = next(
            (
                point
                for point in baseline
                if point.baseline_capacity_risk_percent / 100.0 >= target
            ),
            None,
        )
        if first_at_risk is None:
            return []

        definitions = [
            item
            for item in self.block_definitions()
            if item.enabled
            and item.unit_capacity_mw is not None
            and item.startable_count > 0
        ]
        if not definitions:
            return []

        baseline_area = sum(
            point.baseline_capacity_risk_percent for point in baseline
        )
        candidates: list[
            tuple[
                tuple[int, float, float, int, int],
                list[CapacityStartActionResponse],
            ]
        ] = []
        ranges = [range(item.startable_count + 1) for item in definitions]
        for counts in product(*ranges):
            if not any(counts):
                continue
            requests = [
                CapacityStartActionRequest(block_id=definition.block_id, count=count)
                for definition, count in zip(definitions, counts)
                if count > 0
            ]
            try:
                actions = self._materialize_actions(
                    context,
                    requests,
                    automatic=True,
                    first_at_risk=first_at_risk,
                )
            except InvalidCapacityPlan:
                continue
            profile = self._planned_profile(context, actions)
            violations = sum(
                point.planned_capacity_risk_percent / 100.0 >= target
                for point in profile
            )
            risk_area = sum(point.planned_capacity_risk_percent for point in profile)
            total_capacity = sum(action.total_capacity_mw for action in actions)
            unit_count = sum(action.count for action in actions)
            max_lead = max(action.startup_lead_time_minutes for action in actions)
            score = (
                (0, round(total_capacity, 10), round(risk_area, 10), unit_count, max_lead)
                if violations == 0
                else (
                    1,
                    float(violations),
                    round(risk_area, 10),
                    round(total_capacity, 10),
                    unit_count,
                )
            )
            candidates.append((score, actions))

        if not candidates:
            return []
        _, selected = min(candidates, key=lambda item: item[0])
        selected_area = sum(
            point.planned_capacity_risk_percent
            for point in self._planned_profile(context, selected)
        )
        return selected if selected_area < baseline_area - 1e-9 else []

    def _materialize_actions(
        self,
        context: _PlanningContext,
        requests: list[CapacityStartActionRequest],
        automatic: bool,
        first_at_risk: CapacityPlanHorizonResponse | None = None,
    ) -> list[CapacityStartActionResponse]:
        definitions = {item.block_id: item for item in self.block_definitions()}
        seen: set[str] = set()
        actions: list[CapacityStartActionResponse] = []
        for request in requests:
            if request.block_id in seen:
                raise InvalidCapacityPlan(
                    f"Duplicate capacity block {request.block_id!r}"
                )
            seen.add(request.block_id)
            definition = definitions.get(request.block_id)
            if definition is None:
                raise InvalidCapacityPlan(
                    f"Unknown capacity block {request.block_id!r}"
                )
            if not definition.enabled or definition.unit_capacity_mw is None:
                raise InvalidCapacityPlan(
                    f"Capacity block {request.block_id!r} is not configured"
                )
            if request.count > definition.startable_count:
                raise InvalidCapacityPlan(
                    f"{request.block_id!r} allows at most "
                    f"{definition.startable_count} startable block(s)"
                )

            start_by = self._start_by(
                context,
                definition.startup_lead_time_minutes,
                first_at_risk,
            )
            if automatic:
                start_at = max(context.issue_time, start_by or context.issue_time)
            else:
                start_at = _aware_datetime(request.start_at) or _evaluation_time(
                    context
                )
            expected_online_at = start_at + timedelta(
                minutes=definition.startup_lead_time_minutes
            )
            expired_without_telemetry = expected_online_at <= context.issue_time
            actions.append(
                CapacityStartActionResponse(
                    block_id=definition.block_id,
                    block_label=definition.label,
                    block_class=definition.block_class,
                    count=request.count,
                    unit_capacity_mw=definition.unit_capacity_mw,
                    total_capacity_mw=(
                        definition.unit_capacity_mw * request.count
                    ),
                    startup_lead_time_minutes=(
                        definition.startup_lead_time_minutes
                    ),
                    start_at=start_at,
                    start_by=start_by,
                    expected_online_at=expected_online_at,
                    verification_status=definition.verification_status,
                    action_status=(
                        CapacityActionStatus.VERIFICATION_REQUIRED
                        if expired_without_telemetry
                        else CapacityActionStatus.PROPOSED
                    ),
                    applied_to_projection=not expired_without_telemetry,
                )
            )

        self._validate_startable_headroom(context, actions)
        return sorted(actions, key=lambda action: action.expected_online_at)

    @staticmethod
    def _start_by(
        context: _PlanningContext,
        lead_minutes: int,
        first_at_risk: CapacityPlanHorizonResponse | None,
    ) -> datetime | None:
        if first_at_risk is None:
            return None
        target_at = _aware_datetime(first_at_risk.forecast_timestamp) or (
            context.issue_time
            + timedelta(minutes=first_at_risk.horizon_minutes)
        )
        return target_at - timedelta(minutes=lead_minutes)

    @staticmethod
    def _validate_startable_headroom(
        context: _PlanningContext,
        actions: list[CapacityStartActionResponse],
    ) -> None:
        available = context.total_available_capacity_mw
        if available is None or available < context.current_tra_mw:
            return
        configured_headroom = available - context.current_tra_mw
        requested = sum(
            action.total_capacity_mw
            for action in actions
            if action.applied_to_projection
        )
        if requested > configured_headroom + 1e-9:
            raise InvalidCapacityPlan(
                f"Requested {requested:.1f} MW exceeds the current "
                f"TA-minus-TRA startable margin of {configured_headroom:.1f} MW"
            )

    def _response(
        self,
        context: _PlanningContext,
        evaluated_actions: list[CapacityStartActionResponse],
        recommended_actions: list[CapacityStartActionResponse],
        action_source: CapacityActionSource,
    ) -> CapacityPlanResponse:
        warnings = self._configuration_warnings(context, evaluated_actions)
        if not self._context_is_usable(context):
            return CapacityPlanResponse(
                snapshot_id=context.snapshot_id,
                status=CapacityPlanStatus.UNAVAILABLE,
                action_source=CapacityActionSource.NONE,
                system_suggestion=(
                    "VERIFY CURRENT TRA AND FORECAST INPUTS BEFORE PLANNING"
                ),
                system_suggestion_basis=[
                    "No machine capacity suggestion is issued without fresh, "
                    "quality-accepted TRA and a cutoff-safe demand-risk profile"
                ],
                issue_time=context.issue_time,
                current_tra_mw=(
                    context.current_tra_mw
                    if context.current_tra_mw > 0
                    else None
                ),
                current_tra_observed_at=context.current_tra_observed_at,
                current_tra_age_seconds=self._tra_age_seconds(context),
                current_tra_source=context.current_tra_source,
                current_tra_quality_status=context.current_tra_quality_status,
                required_reserve_mw=(
                    context.baseline_probability.required_reserve_mw
                    or settings.CAPACITY_RISK_REQUIRED_RESERVE_MW
                ),
                target_risk_probability=(
                    settings.CAPACITY_RISK_WATCH_PROBABILITY_THRESHOLD
                ),
                baseline_peak_risk_percent=0,
                post_plan_peak_risk_percent=0,
                risk_reduction_percentage_points=0,
                block_definitions=list(self.block_definitions()),
                configuration_status=settings.OPERATING_POLICY_STATUS,
                warnings=[
                    *warnings,
                    "Capacity planning is unavailable because current TRA or "
                    "the cutoff-safe demand-risk profile is unavailable",
                ],
            )

        profile = self._planned_profile(context, evaluated_actions)
        baseline_peak = max(
            point.baseline_capacity_risk_percent for point in profile
        )
        post_peak = max(point.planned_capacity_risk_percent for point in profile)
        target = settings.CAPACITY_RISK_WATCH_PROBABILITY_THRESHOLD
        first_unprotected = next(
            (
                point
                for point in profile
                if point.planned_capacity_risk_percent / 100.0 >= target
            ),
            None,
        )
        unresolved = max(
            (
                self._required_additional_capacity(point, target)
                for point in profile
            ),
            default=0.0,
        )
        interim = bool(evaluated_actions) and any(
            point.baseline_capacity_risk_percent / 100.0 >= target
            and point.applied_start_capacity_mw <= 0
            for point in profile
        )
        if interim:
            warnings.append(
                "Risk exists before the proposed capacity can be online"
            )
        if first_unprotected is not None:
            warnings.append(
                "The evaluated start plan does not reduce every horizon below "
                "the Watch threshold"
            )
        recommended_profile = self._planned_profile(
            context,
            recommended_actions,
        )
        system_suggestion, suggestion_basis = self._system_suggestion(
            context=context,
            baseline_peak_risk_percent=baseline_peak,
            recommended_actions=recommended_actions,
            recommended_profile=recommended_profile,
            target_risk_probability=target,
        )
        return CapacityPlanResponse(
            snapshot_id=context.snapshot_id,
            status=CapacityPlanStatus.AVAILABLE,
            action_source=action_source,
            advisory_notice=ADVISORY_NOTICE,
            system_suggestion=system_suggestion,
            system_suggestion_basis=suggestion_basis,
            issue_time=context.issue_time,
            current_tra_mw=context.current_tra_mw,
            current_tra_observed_at=context.current_tra_observed_at,
            current_tra_age_seconds=self._tra_age_seconds(context),
            current_tra_source=context.current_tra_source,
            current_tra_quality_status=context.current_tra_quality_status,
            current_tra_projection_basis=BASELINE_TRA_BASIS,
            required_reserve_mw=(
                context.baseline_probability.required_reserve_mw
                or settings.CAPACITY_RISK_REQUIRED_RESERVE_MW
            ),
            target_risk_probability=target,
            baseline_peak_risk_percent=baseline_peak,
            post_plan_peak_risk_percent=post_peak,
            risk_reduction_percentage_points=max(0.0, baseline_peak - post_peak),
            first_unprotected_horizon_minutes=(
                first_unprotected.horizon_minutes
                if first_unprotected is not None
                else None
            ),
            first_unprotected_at=(
                first_unprotected.forecast_timestamp
                if first_unprotected is not None
                else None
            ),
            interim_unmitigated_risk=interim,
            unresolved_capacity_mw=unresolved,
            block_definitions=list(self.block_definitions()),
            recommended_actions=recommended_actions,
            evaluated_actions=evaluated_actions,
            profile=profile,
            configuration_status=settings.OPERATING_POLICY_STATUS,
            warnings=list(dict.fromkeys(warnings)),
        )

    def _system_suggestion(
        self,
        context: _PlanningContext,
        baseline_peak_risk_percent: float,
        recommended_actions: list[CapacityStartActionResponse],
        recommended_profile: list[CapacityPlanHorizonResponse],
        target_risk_probability: float,
    ) -> tuple[str, list[str]]:
        target_percent = target_risk_probability * 100.0
        peak_point = max(
            recommended_profile,
            key=lambda point: point.baseline_capacity_risk_percent,
        )
        basis = [
            (
                f"No-action peak risk is {baseline_peak_risk_percent:.1f}% "
                f"against the {target_percent:.1f}% Watch threshold"
            ),
            (
                f"Peak modeled demand is {peak_point.forecast_demand_mw:.1f} MW "
                f"at +{peak_point.horizon_minutes} minutes with current TRA "
                f"held at {context.current_tra_mw:.1f} MW"
            ),
        ]
        if baseline_peak_risk_percent < target_percent:
            basis.append(
                "No configured start block is needed to keep modeled risk "
                "below the Watch threshold"
            )
            return (
                "MAINTAIN CURRENT TRA AND MONITOR FORECAST CONDITIONS",
                basis,
            )

        if not recommended_actions:
            basis.append(
                "No configured and quality-eligible block combination can "
                "reduce the modeled exposure below the Watch threshold"
            )
            return "ESCALATE CAPACITY AVAILABILITY REVIEW", basis

        total_capacity = sum(
            action.total_capacity_mw for action in recommended_actions
        )
        action_summary = " + ".join(
            f"{action.count} x {action.block_label}"
            for action in recommended_actions
        )
        recommended_peak = max(
            point.planned_capacity_risk_percent
            for point in recommended_profile
        )
        maximum_lead = max(
            action.startup_lead_time_minutes
            for action in recommended_actions
        )
        basis.extend(
            [
                (
                    f"The selected configured plan is {action_summary}, "
                    f"adding {total_capacity:.1f} MW after its lead time"
                ),
                (
                    f"Modeled post-plan peak risk is {recommended_peak:.1f}% "
                    f"with a maximum startup lead of {maximum_lead} minutes"
                ),
            ]
        )
        residual_suffix = (
            "; ESCALATE RESIDUAL EXPOSURE"
            if recommended_peak >= target_percent
            else ""
        )
        return (
            f"REVIEW START OF {action_summary.upper()} "
            f"({total_capacity:.1f} MW TOTAL){residual_suffix}",
            basis,
        )

    def _baseline_profile(
        self,
        context: _PlanningContext,
    ) -> list[CapacityPlanHorizonResponse]:
        return self._planned_profile(context, [])

    def _planned_profile(
        self,
        context: _PlanningContext,
        actions: list[CapacityStartActionResponse],
    ) -> list[CapacityPlanHorizonResponse]:
        required_reserve = (
            context.baseline_probability.required_reserve_mw
            or settings.CAPACITY_RISK_REQUIRED_RESERVE_MW
        )
        profile: list[CapacityPlanHorizonResponse] = []
        for point in sorted(
            context.baseline_probability.risk_profile,
            key=lambda item: item.horizon_minutes,
        ):
            target_at = _point_timestamp(context.issue_time, point)
            applied_capacity = sum(
                action.total_capacity_mw
                for action in actions
                if action.applied_to_projection
                and target_at >= action.expected_online_at
            )
            baseline_tra = context.current_tra_mw
            planned_tra = baseline_tra + applied_capacity
            baseline_risk = _capacity_risk(
                point.forecast_demand_mw,
                point.forecast_uncertainty_mw,
                baseline_tra,
                required_reserve,
            )
            planned_risk = _capacity_risk(
                point.forecast_demand_mw,
                point.forecast_uncertainty_mw,
                planned_tra,
                required_reserve,
            )
            baseline_reserve = baseline_tra - point.forecast_demand_mw
            planned_reserve = planned_tra - point.forecast_demand_mw
            balance = planned_reserve - required_reserve
            profile.append(
                CapacityPlanHorizonResponse(
                    horizon_minutes=point.horizon_minutes,
                    forecast_timestamp=point.forecast_timestamp,
                    forecast_demand_mw=point.forecast_demand_mw,
                    forecast_uncertainty_mw=point.forecast_uncertainty_mw,
                    baseline_tra_mw=baseline_tra,
                    baseline_reserve_mw=baseline_reserve,
                    baseline_capacity_risk_percent=baseline_risk * 100.0,
                    baseline_capacity_status=_capacity_status(baseline_risk),
                    planned_tra_mw=planned_tra,
                    applied_start_capacity_mw=applied_capacity,
                    planned_reserve_mw=planned_reserve,
                    planned_reserve_surplus_mw=max(0.0, balance),
                    planned_reserve_deficit_mw=max(0.0, -balance),
                    planned_capacity_risk_percent=planned_risk * 100.0,
                    planned_capacity_status=_capacity_status(planned_risk),
                    required_reserve_mw=required_reserve,
                )
            )
        return profile

    @staticmethod
    def _required_additional_capacity(
        point: CapacityPlanHorizonResponse,
        target_risk_probability: float,
    ) -> float:
        if not 0 < target_risk_probability < 1:
            return 0.0
        quantile = NormalDist().inv_cdf(1.0 - target_risk_probability)
        required_tra = (
            point.required_reserve_mw
            + point.forecast_demand_mw
            + quantile * point.forecast_uncertainty_mw
        )
        return max(0.0, required_tra - point.planned_tra_mw)

    @staticmethod
    def _context_is_usable(context: _PlanningContext) -> bool:
        probability = context.baseline_probability
        quality = context.current_tra_quality_status.upper()
        return (
            context.current_tra_mw > 0
            and quality not in {"BAD", "STALE"}
            and not _tra_is_missing(context.current_tra_missing_fields)
            and (
                _uses_replay_clock(context.current_tra_source)
                or (context.current_tra_observed_at is not None
                    and (CapacityPlanningService._tra_age_seconds(context) or 0)
                    <= settings.GRID_STALE_AFTER_SECONDS)
            )
            and probability.risk_level != "UNAVAILABLE"
            and probability.capacity_status != "Unavailable"
            and bool(probability.risk_profile)
        )

    @staticmethod
    def _tra_age_seconds(context: _PlanningContext) -> float | None:
        if context.current_tra_observed_at is None:
            return None
        return max(
            0.0,
            (
                context.issue_time - context.current_tra_observed_at
            ).total_seconds(),
        )

    def _configuration_warnings(
        self,
        context: _PlanningContext,
        actions: list[CapacityStartActionResponse],
    ) -> list[str]:
        warnings: list[str] = []
        if "Mock" in context.current_tra_source or "Synthetic" in context.current_tra_source:
            warnings.append(
                "Current TRA is simulated; this plan is for replay or training only"
            )
        if context.current_tra_quality_status.upper() == "UNCERTAIN":
            warnings.append(
                "Current TRA quality is UNCERTAIN and requires operator verification"
            )
        if _tra_is_missing(context.current_tra_missing_fields):
            warnings.append(
                "Current TRA evidence is marked missing in the grid snapshot"
            )
        if any(
            definition.block_class == "HEAVY" and not definition.enabled
            for definition in self.block_definitions()
        ):
            warnings.append(
                "Heavy-set capacity is unconfigured; no MW-specific heavy start is proposed"
            )
        if any(
            action.verification_status != "VERIFIED" for action in actions
        ):
            warnings.append(
                "One or more proposed block capacities are unconfirmed and must be verified"
            )
        if any(
            action.action_status == CapacityActionStatus.VERIFICATION_REQUIRED
            for action in actions
        ):
            warnings.append(
                "An action expected online by the snapshot time was excluded until TRA confirms it"
            )
        return warnings


def _capacity_risk(
    forecast_demand_mw: float,
    uncertainty_mw: float,
    tra_mw: float,
    required_reserve_mw: float,
) -> float:
    if uncertainty_mw <= 0:
        return 0.0
    z_score = (
        tra_mw - required_reserve_mw - forecast_demand_mw
    ) / uncertainty_mw
    return max(0.0, min(1.0, 0.5 * math.erfc(z_score / math.sqrt(2.0))))


def _capacity_status(probability: float) -> str:
    rounded = round(probability, 12)
    if rounded >= settings.CAPACITY_RISK_ADD_GENERATION_PROBABILITY_THRESHOLD:
        return "Add Generation"
    if rounded >= settings.CAPACITY_RISK_PREPARE_PROBABILITY_THRESHOLD:
        return "Prepare Generation"
    if rounded >= settings.CAPACITY_RISK_WATCH_PROBABILITY_THRESHOLD:
        return "Watch"
    return "Normal"


def _point_timestamp(
    issue_time: datetime,
    point: RiskHorizonResponse,
) -> datetime:
    return _aware_datetime(point.forecast_timestamp) or (
        issue_time + timedelta(minutes=point.horizon_minutes)
    )


def _aware_datetime(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value


def _tra_source_label(source_provider: str) -> str:
    if source_provider in {
        "HistoricalScadaReplay",
        "HistoricalScadaSimulatedReplay",
    }:
        return f"GSYS SYSTEM_ONLN_TOTAL via {source_provider}"
    return f"{source_provider} aggregate online capacity"


def _uses_replay_clock(source: str) -> bool:
    return "Replay" in source or "Synthetic" in source


def _evaluation_time(context: _PlanningContext) -> datetime:
    if _uses_replay_clock(context.current_tra_source):
        return context.issue_time
    return datetime.now(context.issue_time.tzinfo or timezone.utc)


def _tra_is_missing(missing_fields: tuple[str, ...]) -> bool:
    aliases = {
        "current_generation_mw",
        "online_capacity_mw",
        "system_onln_total",
        "gsys system_onln_total",
        "tra",
    }
    return any(field.strip().lower() in aliases for field in missing_fields)


def _heavy_block_capacities() -> tuple[float, ...]:
    values: list[float] = []
    for raw in settings.CAPACITY_PLAN_HEAVY_BLOCKS_MW.split(","):
        text = raw.strip()
        if not text:
            continue
        try:
            capacity = float(text)
        except ValueError:
            continue
        if math.isfinite(capacity) and capacity > 0:
            values.append(capacity)
    return tuple(values)


capacity_planning_service = CapacityPlanningService()
