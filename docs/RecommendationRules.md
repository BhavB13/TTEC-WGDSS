# Recommendation Rules

## Decision-Support Boundary

WGDSS is read-only decision support. Recommendations are evidence for a Control
Engineer, not automatic start commands. Policy values are configurable and
`PROTOTYPE_UNCONFIRMED` until T&TEC approves them.

## Capacity Event

The engine evaluates one physical event at each forecast horizon:

```text
projected_reserve = forecast_TRA - forecast_demand
risk = P(forecast_TRA - actual_demand < 30 MW)
```

Corrected System Spin remains independent SCADA context. TA is potential
available capacity and is not substituted for TRA.

## Decision Matrix

| Capacity risk | Capacity status | Recommendation |
|---|---|---|
| Below 20% | `Normal` | `NO ACTION REQUIRED` |
| 20% to below 50% | `Watch` | `MONITOR CONDITIONS` |
| 50% to below 80% | `Prepare Generation` | `PREPARE ADDITIONAL GENERATION` |
| 80% or above | `Add Generation` | Evaluate unit block, capacity availability, and lead time |

At a mean projected reserve of exactly 30 MW, normally distributed zero-mean
forecast error gives 50% risk and `Prepare Generation`. As reserve moves below
the target, probability and guidance urgency increase continuously.

For `Add Generation`, the existing prototype dispatch guidance checks the
confidence-upper demand shortfall, target horizon, startup lead time, and
verified `TA - TRA` startable headroom. It must not claim an unavailable unit.

## Shared Evidence Invariant

The selected horizon is the horizon with the largest capacity-risk probability.
The following displayed values must all come from that same horizon:

- capacity-risk percentage and status;
- forecast demand and forecast TRA;
- projected reserve and 30 MW target;
- reserve surplus or deficit;
- forecast uncertainty and provenance; and
- selected horizon timestamp.

The first-insufficiency field is separate: it is the earliest chronological
horizon whose mean projected reserve is 30 MW or less.

## Inputs That Do Not Add Arbitrary Points

Temperature, humidity, rainfall, cloud cover, and wind influence the load model
and validation error. They do not add fixed increments to probability. Corrected
spin, reserve margin, outages, and derates are disclosed as capacity or quality
evidence rather than arbitrary risk-score weights.

## Required Confirmation

Before operational use, T&TEC/OSI owners must confirm:

- source tag semantics and engineering units;
- whether `PTL132 GENERATION TOTALS` is an acceptable demand target;
- TRA, TA, and corrected-spin meanings and quality-code handling;
- whether 30 MW is the approved operating reserve requirement;
- capacity-risk status thresholds and escalation workflow;
- unit availability, block sizes, ramp/start times, outages, and derates; and
- the approved read-only historian/provider interface.

See `SCADA_OSI_CONFIRMATION_REGISTER.md`.
