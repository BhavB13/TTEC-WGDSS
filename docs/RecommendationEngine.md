# Capacity Risk And Recommendation Engine

## Purpose

WGDSS estimates the probability that forecast demand will leave less than the
required operating reserve during the next six hours. The result is read-only
decision support. It does not issue a SCADA command, dispatch a unit, or replace
Control Engineer judgement.

The Version 1 project target is 30 MW. It is configurable through
`CAPACITY_RISK_REQUIRED_RESERVE_MW` and remains
`PROTOTYPE_UNCONFIRMED` until T&TEC approves the operating policy.

## Data Semantics

For each forecast horizon the engine uses:

- forecast demand and its calibrated uncertainty;
- the latest quality-accepted current SCADA TRA as the no-action baseline;
- proposed aggregate start blocks only in a separately labelled hypothetical
  post-plan calculation;
- current corrected System Spin as separate observed context;
- Total Available Capacity (TA) only to bound verified startable capacity; and
- source quality, forecast confidence, and policy status.

The supplied `PTL132 GENERATION TOTALS` series is the prototype demand/load
proxy. `GSYS SYSTEM_ONLN_TOTAL` is treated as TRA. Corrected System Spin is not
redefined as `TRA - demand`.

## Projected Reserve

For horizon `h`, the headline/no-action calculation is:

```text
baseline_TRA_h = current_observed_TRA
projected_reserve_h = baseline_TRA_h - forecast_demand_h
reserve_surplus_h = projected_reserve_h - required_reserve
reserve_deficit_h = max(0, required_reserve - projected_reserve_h)
```

The current requirement is:

```text
required_reserve = 30 MW
```

A mean projected reserve of 30 MW or less is marked as expected to be
insufficient. The API reports the earliest such forecast horizon and timestamp.

Current TRA is held at every horizon and returned as
`CURRENT_TRA_HELD_NO_ACTION`. Statistical models do not forecast operator
dispatch. A hypothetical post-plan trajectory is computed only from explicit
aggregate starts after their configured lead times.

## Continuous Probability

Demand forecast error is approximated as normally distributed:

```text
actual_demand_h ~ Normal(forecast_demand_h, sigma_h)
safe_demand_h = current_TRA - required_reserve
z_h = (safe_demand_h - forecast_demand_h) / sigma_h
risk_h = P(actual_demand_h > safe_demand_h)
       = 1 - NormalCDF(z_h)
       = P(forecast_TRA_h - actual_demand_h < required_reserve)
```

This produces a continuous value from 0 to 1. The API also returns the same
value as `capacity_risk_percent` from 0 to 100. No weather points, reserve
percentages, or arbitrary score increments are added to this probability.
Weather affects risk only through the demand forecast and its uncertainty.

The headline result is always the maximum valid no-action horizon probability
through six hours.
Every headline evidence field comes from that same selected horizon: forecast
demand, forecast TRA, projected reserve, target, surplus or deficit, status,
and uncertainty.

## Uncertainty Sources

The engine resolves `sigma_h` in this order:

1. calibrated per-horizon residual standard deviation;
2. a valid prediction interval converted to a normal-equivalent sigma;
3. a validated fallback residual standard deviation;
4. chronological validation RMSE, used as sigma under a near-zero-bias
   assumption; or
5. chronological validation MAE converted under a zero-mean normal assumption:

```text
sigma = MAE * sqrt(pi / 2)
```

The chosen source is returned as `uncertainty_source`. If no positive validated
uncertainty is available, capacity risk is `UNAVAILABLE`; the service does not
invent a probability. A valid rule-based demand forecast may still be returned.

## Capacity Status

Default configurable prototype bands are:

| Capacity risk | Status | Default posture |
|---|---|---|
| Below 20% | `Normal` | `NO ACTION REQUIRED` |
| 20% to below 50% | `Watch` | `MONITOR CONDITIONS` |
| 50% to below 80% | `Prepare Generation` | `PREPARE ADDITIONAL GENERATION` |
| 80% or above | `Add Generation` | Evaluate available unit block and startup lead time |

The probability remains continuous at every boundary. A one-MW change around
the 30 MW reserve target therefore changes risk gradually instead of jumping
from near 0% to near 100%.

## Aggregate Capacity Planner

The capacity planner is deterministic, read-only, and separate from the demand
model. For a proposed action set:

```text
planned_TRA_h =
  current_TRA + sum(block_capacity for blocks online by horizon h)
post_plan_risk_h =
  P(planned_TRA_h - actual_demand_h < required_reserve)
```

The planner searches configured aggregate block combinations and selects the
smallest feasible capacity that reduces every protectable horizon below the
`Watch` threshold. It also reports interim exposure, unresolved MW, start-by
time, and expected-online time.

Every response includes a machine-generated `system_suggestion` and
`system_suggestion_basis`. This is a deterministic recommendation from the
validated demand forecast, residual uncertainty, observed current TRA, reserve
target, block roster, and startup timing. It is not generative AI and cannot
execute an action. The system suggestion remains unchanged while an operator
evaluates a different what-if selection, allowing a clear comparison with the
machine baseline.

Current prototype configuration:

- up to three small blocks;
- 20-minute startup lead;
- 15 MW per small block, explicitly `UNCONFIRMED`;
- 60-minute heavy-block startup lead; and
- no heavy-block MW guidance until approved capacities are configured.

TA bounds the total proposed startable headroom but is never counted as online
TRA. An action whose expected-online time has passed is excluded until a newer
SCADA observation confirms increased TRA. Proposed starts never lower the
headline no-action risk.

## API Evidence

The probability and recommendation objects expose:

- `capacity_risk_percent` and `capacity_status`;
- `forecast_demand_mw` and `forecast_tra_mw`;
- `projected_reserve_mw` and `required_reserve_mw`;
- `reserve_surplus_mw` and `reserve_deficit_mw`;
- `reserve_insufficient_horizon_minutes` and `reserve_insufficient_at`;
- `forecast_uncertainty_mw` and `uncertainty_source`;
- `tra_projection_basis`; and
- a per-horizon `risk_profile` containing the same calculation.

Legacy `risk_level` remains for compatibility and maps `Normal` to LOW, `Watch`
to MEDIUM, and both generation states to HIGH.

The dashboard snapshot also exposes `capacity_plan`, including:

- current TRA value, timestamp, quality, source, and age;
- the machine-generated suggestion and its auditable mathematical basis;
- no-action and post-plan risk profiles;
- configured block definitions;
- recommended and operator-evaluated starts;
- action deadlines and expected-online times;
- unresolved/interim exposure and configuration warnings; and
- the permanent `ADVISORY ONLY - MANUAL OPERATOR ACTION REQUIRED` notice.

`POST /api/v1/capacity-plan/evaluate` performs a stateless-looking, app-local
what-if evaluation against a recent snapshot ID. The underlying context is
bounded and expires after 15 minutes by default. It neither persists a dispatch
instruction nor communicates with SCADA.

## Safety And Limitations

- Missing demand, TRA, or validated uncertainty returns `UNAVAILABLE`.
- Bad, stale, missing, or non-fresh current TRA evidence inhibits the capacity
  planner.
- Invalid prediction intervals are ignored and rebuilt from valid residual
  uncertainty when possible.
- Corrected spin remains separate context and does not silently alter TRA.
- A missing future TRA schedule is disclosed rather than inferred.
- Unverified TA cannot be presented as startable capacity.
- Replay, simulation, and live/read-only source modes remain visibly distinct.
- Shutdown advice is excluded until ramp-down, minimum-run/down-time, and
  operator restrictions are approved.
- App-local snapshot contexts are not a production distributed state store;
  multi-worker deployment requires a shared, expiring context repository.
- The normal residual approximation and limited June archive require validation
  against longer, seasonally representative history before operational use.

Tests cover reserve above, exactly at, and below 30 MW; continuous probabilities
at 20%, 50%, and 80%; a one-MW boundary crossing; demand/TRA monotonicity;
corrected-spin independence; uncertainty fallbacks; per-horizon consistency;
earliest insufficiency; malformed inputs; and chronological backtesting.
