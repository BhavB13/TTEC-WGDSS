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
- forecast TRA when an approved future TRA schedule is supplied;
- otherwise, current SCADA TRA held as an explicitly labelled scenario;
- current corrected System Spin as separate observed context;
- Total Available Capacity (TA) only to bound verified startable capacity; and
- source quality, forecast confidence, and policy status.

The supplied `PTL132 GENERATION TOTALS` series is the prototype demand/load
proxy. `GSYS SYSTEM_ONLN_TOTAL` is treated as TRA. Corrected System Spin is not
redefined as `TRA - demand`.

## Projected Reserve

For horizon `h`:

```text
projected_reserve_h = forecast_TRA_h - forecast_demand_h
reserve_surplus_h = projected_reserve_h - required_reserve
reserve_deficit_h = max(0, required_reserve - projected_reserve_h)
```

The current requirement is:

```text
required_reserve = 30 MW
```

A mean projected reserve of 30 MW or less is marked as expected to be
insufficient. The API reports the earliest such forecast horizon and timestamp.

When no future TRA schedule exists, the engine uses current TRA at each horizon
and returns `CURRENT_TRA_HELD_SCENARIO_NO_DISPATCH_PLAN`. This is a scenario,
not a claim that future generation is known.

## Continuous Probability

Demand forecast error is approximated as normally distributed:

```text
actual_demand_h ~ Normal(forecast_demand_h, sigma_h)
safe_demand_h = forecast_TRA_h - required_reserve
z_h = (safe_demand_h - forecast_demand_h) / sigma_h
risk_h = P(actual_demand_h > safe_demand_h)
       = 1 - NormalCDF(z_h)
       = P(forecast_TRA_h - actual_demand_h < required_reserve)
```

This produces a continuous value from 0 to 1. The API also returns the same
value as `capacity_risk_percent` from 0 to 100. No weather points, reserve
percentages, or arbitrary score increments are added to this probability.
Weather affects risk only through the demand forecast and its uncertainty.

The headline result is the maximum valid horizon probability through six hours.
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

For `Add Generation`, existing configurable prototype unit blocks and startup
lead times are used to produce guidance. These values remain unconfirmed. TA is
not counted as online reserve and can only limit a start recommendation when its
mapping to startable capacity is verified.

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

## Safety And Limitations

- Missing demand, TRA, or validated uncertainty returns `UNAVAILABLE`.
- Invalid prediction intervals are ignored and rebuilt from valid residual
  uncertainty when possible.
- Corrected spin remains separate context and does not silently alter TRA.
- A missing future TRA schedule is disclosed rather than inferred.
- Unverified TA cannot be presented as startable capacity.
- Replay, simulation, and live/read-only source modes remain visibly distinct.
- The normal residual approximation and limited June archive require validation
  against longer, seasonally representative history before operational use.

Tests cover reserve above, exactly at, and below 30 MW; continuous probabilities
at 20%, 50%, and 80%; a one-MW boundary crossing; demand/TRA monotonicity;
corrected-spin independence; uncertainty fallbacks; per-horizon consistency;
earliest insufficiency; malformed inputs; and chronological backtesting.
