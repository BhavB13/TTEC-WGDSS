# Three-Source Forecast And Generator Dispatch Upgrade

> Dispatch capacities, lead times, the 30 MW reserve target, and status bands
> in this design note are configurable prototype assumptions. They are not approved
> T&TEC policy; see `docs/SCADA_OSI_CONFIRMATION_REGISTER.md`.

## Recommended Forecast Approach

WGDSS uses a hybrid architecture because no single model is reliable in every
data regime:

1. The live six-hour weather outlook concurrently requests Open-Meteo Best
   Match, MET Norway, and Open-Meteo NOAA GFS.
2. Provider timestamps are converted to UTC and matched to the nearest hourly
   boundary. A source more than 30 minutes from that boundary is not merged.
3. Each field is merged independently. Missing or non-numeric values never
   become zero; valid peers supply that field. An hour is omitted if no source
   supplies temperature, humidity, rainfall, cloud, or wind.
4. Historical hourly average, a transparent weather-adjusted baseline, and a
   regularized weather-feature regression are evaluated with a chronological
   80/20 split. The stronger model is activated only when it improves MAE and
   RMSE by at least two percent. The existing offline SCADA trainer retains its
   HistGradientBoosting candidate and the same baseline gate.
5. Forecast uncertainty comes from held-out residual error and is widened when
   weather-source confidence falls.

This is preferable to forcing a complex model into service: it makes weather a
direct demand feature while retaining a measured fallback when data is short or
the model does not improve future-period accuracy.

## Replay Weather Sources

External providers cannot issue forecasts for a past June. The replay therefore
stores deterministic archived forecast snapshots under the same three provider
identities. Small source-specific errors are applied around the archived weather
observation, then the normal timestamp and per-field merge logic is used. This
tests the production consensus path without claiming the external APIs supplied
historical forecasts.

## Simulated Time

On first startup after migration, the selected June replay maps the current
Trinidad day and hour to the archive. For example, July 15 at 10:42 maps to June
15 at 10:00. The cursor starts in real-time playback. `Sync Now` repeats this
mapping; manual Step and accelerated rates remain available. All API and UI
surfaces use explicit `historical_replay`, `simulation`, or `live_read_only`
labels and never present replay data as live SCADA.

## Dispatch Mathematics

For each forecast horizon up to six hours:

```text
required_reserve_mw = 30 MW
projected_reserve_mw = forecast_TRA_mw - forecast_demand_mw
safe_demand_mw = forecast_TRA_mw - required_reserve_mw
z = (safe_demand_mw - forecast_demand_mw) / uncertainty_mw
risk_probability = P(Normal(0,1) > z)
conservative_shortfall_mw = max(0,
  confidence_upper_mw - safe_demand_mw)
```

The default 90% central interval uses the 95th-percentile upper endpoint
(`forecast + 1.64485 * sigma`) when the model has not supplied valid bounds.
The reserve target is configurable and unconfirmed. Corrected System Spin is
separate SCADA context. The engine selects the
highest-probability horizon and applies configurable, unconfirmed lead-time
rules:

| Condition | Decision |
|---|---|
| Probability below 0.20 | Normal / no action |
| Probability 0.20 to below 0.50 | Watch / monitor |
| Probability 0.50 to below 0.80 | Prepare generation |
| Probability 0.80 or above | Add-generation capacity and lead-time evaluation |

The dashboard response includes action, generator set, recommended MW,
conservative and expected shortfall, expected rise and lead time, startup time,
weather demand effect, confidence, and calculation factors. These are decision
support outputs, not autonomous dispatch commands.

## Failure Behavior

- One failed weather provider produces a degraded two-source forecast.
- A missing field from one provider is ignored for that field only.
- A forecast hour with no valid source for an operational field is omitted.
- Reduced weather confidence widens load uncertainty.
- Missing or inconsistent grid capacity inhibits dispatch guidance.
- Future replay demand remains hidden until the cursor reaches its timestamp.
