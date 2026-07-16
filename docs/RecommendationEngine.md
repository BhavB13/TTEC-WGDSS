# Operating Risk And Recommendation Engine

## Purpose

WGDSS estimates the probability that forecast demand will leave insufficient
online capability to carry the configured operating reserve during the next six
hours. It then turns that evidence into read-only decision support. It does not
issue a SCADA command, dispatch a unit, or replace operator judgement.

All tag meanings, units, reserve policy, risk thresholds, unit blocks, and lead
times remain configurable prototype assumptions pending the confirmations in
`SCADA_OSI_CONFIRMATION_REGISTER.md`. `SCADA_OSI_CONTEXT.md` is authoritative
for the supplied June 2026 trend exports.

## Inputs

For each forecast horizon up to six hours, the engine consumes:

- forecast demand mean and residual standard deviation;
- a calibrated confidence interval when available;
- forecast issuance/target time and weather demand effect;
- the current generation/load proxy;
- Total Running/Online Available Capacity (TRA);
- corrected System Spin;
- Total Available Capacity (TA), with a verification flag;
- data-quality warnings; and
- configurable reserve, probability, unit-capacity, and startup-time policy.

The June `PTL132 GENERATION TOTALS` tag is only a demand proxy pending utility
confirmation. Corrected spin is never redefined as `TRA - demand`.

## Capacity Model

Corrected spin and TRA constrain immediate capability independently. When both
are available:

```text
immediate_online_capacity_h = min(
    TRA,
    current_demand + corrected_spin
)
required_reserve_h = reserve_fraction * max(current_demand, forecast_demand_h)
safe_online_capacity_h = immediate_online_capacity_h - required_reserve_h
```

This is equivalent to testing whether forecast demand plus required reserve
exceeds immediate capability. If corrected spin is missing, the engine uses TRA
alone and emits a data-quality warning. TA is not immediate capacity. Verified
`TA - TRA` can only limit how much startable capacity the guidance may claim.

## Continuous Probability

For each horizon, forecast demand is approximated as a normal distribution:

```text
D_h ~ Normal(forecast_demand_h, sigma_h)
z_h = (safe_online_capacity_h - forecast_demand_h) / sigma_h
p_h = P(D_h > safe_online_capacity_h) = 1 - NormalCDF(z_h)
```

`sigma_h` comes from chronological holdout residuals or a valid prediction
interval. A configured nonzero floor prevents a tiny or zero uncertainty from
turning a small boundary crossing into a false 0% or 100% result. The API
returns unrounded probabilities. The dashboard rounds only for display.

The headline probability is the maximum valid horizon probability:

```text
overall_probability = max(p_h for h in valid_horizons_through_6h)
```

This conservative aggregation does not pretend that correlated horizons are
independent.

## Shortfall Evidence

The engine returns two distinct quantities:

```text
expected_shortfall_h = E[max(D_h - safe_online_capacity_h, 0)]
conservative_shortfall_h = max(
    confidence_upper_h - safe_online_capacity_h,
    0
)
```

Expected shortfall integrates both event probability and magnitude under the
normal approximation. Conservative shortfall uses the configured confidence
upper bound. Neither value is a dispatch instruction.

## Risk And Startup Guidance

Default prototype probability bands are:

- LOW: below 0.30;
- MEDIUM: 0.30 through 0.65; and
- HIGH: above 0.65.

The selected horizon is the one with the highest probability, with
conservative shortfall as a tie-breaker. Startup guidance uses configurable
prototype blocks:

- up to two 15 MW fast-start units with a 20-minute lead time; and
- a 60-120 MW heavy unit block with a 60-minute lead time.

The API separately reports probability, physical severity, urgency, forecast
confidence, recommended capacity, target time, and decision deadline. High
probability does not by itself prove a large MW deficit, and forecast confidence
does not alter the physical exceedance probability.

## Failure And Quality Rules

- Missing or invalid demand, TRA, or uncertainty returns `UNAVAILABLE`.
- Missing corrected spin degrades the capacity basis and is disclosed.
- Invalid confidence bounds are rejected and rebuilt from residual uncertainty.
- Unverified TA cannot be presented as startable capacity.
- Utility policy and source-quality warnings are returned as structured drivers.
- Weather affects risk through the demand forecast; it is not added again as an
  arbitrary probability score.
- Historical replay, simulation, and live/read-only source modes remain visibly
  distinct.

## Validation

Tests cover exact intermediate probabilities near 20%, 50%, and 80%, a one-MW
boundary crossing, monotonic response to demand and spin, per-horizon evidence,
startup deadlines, malformed intervals, missing inputs, and chronological
backtesting with a no-future-leakage guard and Brier score.

The normal residual approximation and one-month June archive are prototype
limitations. Production use requires longer representative history, residual
calibration by horizon and operating regime, and T&TEC engineering approval.
