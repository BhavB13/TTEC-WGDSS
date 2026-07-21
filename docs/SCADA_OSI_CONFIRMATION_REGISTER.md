# SCADA and OSI Confirmation Register

This register separates verified WGDSS implementation facts from utility-specific
items that require written confirmation from T&TEC control engineering or the
AspenTech OSI system owner. WGDSS remains read-only decision support while any
item below is unresolved.

## Confirmed From The June 2026 Exports

- The files are historical OSI-style trend exports, not a live SCADA stream.
- Each row is an interval summary containing minimum, maximum, average, extrema
  timestamps, and raw quality. It is not a raw instantaneous sample.
- The five exported source tags are preserved exactly by ingestion.
- `Good`, `Questionable`, and `Other` are raw source quality strings. Until the
  OSI quality mapping is supplied, WGDSS maps them to `good`, `uncertain`, and
  `unknown` respectively while retaining the raw value.
- Exact duplicate rows may occur and must be handled idempotently.
- TA and TRA have only partial June coverage and must not be forward-filled as
  observed data beyond their source intervals.

## Requires T&TEC / OSI Confirmation

| Item | Current prototype treatment | Production requirement |
|---|---|---|
| `PTL132 GENERATION TOTALS` semantics | Stored as `system_generation_total_mw`; used as a demand proxy only with `pending_utility_confirmation` provenance | Confirm gross/net definition, included plants, station service, losses, embedded generation, imports/exports, and whether it is calculated |
| Engineering units for all five tags | Display/model names retain the existing MW/C assumptions, but ingestion records the source unit as unconfirmed | Supply point engineering-unit metadata and approved display precision |
| `SYSTEM_CORRECTED_SPIN_TOTAL` formula | Used only as the reported corrected-spin value; never reconstructed from TRA minus generation | Supply the OSI/OpenCalc definition, eligible resources, correction rules, and quality aggregation |
| TA and TRA definitions | Treated as total available and total running/online available capacity according to current project terminology | Confirm included assets, outages, derates, response capability, and calculation ownership |
| Quality `Other` | Preserved and normalized to `unknown`; conditionally usable only in historical prototype workflows | Supply OSI export quality-code meanings and approved modeling policy |
| Trend bucket construction | Preserved as irregular interval summaries | Supply native scan rate, historian compression/deadband, and fixed export aggregation rules |
| Operating reserve requirement | Version 1 uses a configurable 30 MW project target and explicitly labels it unconfirmed | Supply approved reserve requirement, largest credible contingency, and time-dependent rules |
| Risk thresholds | Configurable Normal/Watch/Prepare Generation/Add Generation probability bands are demo policy | Approve operational bands and escalation workflow |
| Generator blocks and lead times | Existing 15 MW/20 minute and 60-120 MW/60 minute demo settings are configurable | Confirm unit sizes, start/synchronization times, ramp limits, availability, and operator restrictions |
| Production data interface | No live connector is implemented; `scada` and `historian` provider selections fail closed | Approve historian replica/export/API/ICCP/OPC UA path, OT zone, certificates, identities, allowlists, and failover behavior |
| Forecast target | Existing historical prototype predicts the generation-total demand proxy | Approve the operational target definition and model governance process |

## Read-Only Boundary

WGDSS has no command, setpoint, acknowledgement, or control endpoint. A future
historian or SCADA provider may only read approved replicated/exported data.
Any write/control capability requires a separate authorized project, hazard
analysis, interlocks, role separation, and formal OT testing; it is outside the
current WGDSS scope.

## Implemented Safeguards

- Raw imports retain the source tag text, interval boundaries, extrema,
  average, raw quality, normalized quality, source timezone, stable record
  hash, provenance, and anomaly flags.
- Hourly snapshots use overlap-weighted interval aggregation. Their
  `available_at` value is the latest contributing source interval end, not an
  assumed top-of-hour timestamp.
- Forecast rows record feature and target observation/availability timestamps
  and cannot use an interval before that interval was available.
- Corrected System Spin is never reconstructed from TRA minus the generation
  or demand proxy. Missing spin remains unavailable.
- `GRID_PROVIDER=scada` and `GRID_PROVIDER=historian` continue to fail closed;
  no AspenTech OSI endpoint or credential format has been invented.
- Replay responses distinguish `historical_replay`, `simulation`, and the
  reserved `live_read_only` mode.

## Repository Model Audit

The repository does not currently contain an XGBoost dependency or XGBoost
model implementation. Its tested candidate set is Ridge,
`HistGradientBoostingRegressor`, `RandomForestRegressor`,
`ExtraTreesRegressor`, time-series baselines, similar-period forecasts, and
validated blends. That existing ensemble was preserved. An XGBoost migration
must not be inferred from older documentation; it would require an explicit,
chronologically tested change that beats the active baseline and existing
candidate on untouched holdout data.
