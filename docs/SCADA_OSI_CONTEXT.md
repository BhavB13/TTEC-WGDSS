# WGDSS SCADA and AspenTech OSI Context

## How to use this file

Place this document in the WGDSS repository, preferably under `docs/SCADA_OSI_CONTEXT.md`. It is a technical context and implementation specification, not an instruction to replace the existing application blindly. Codex must first inspect the repository, current schemas, forecast pipeline, tests, and documentation, then produce a plan that preserves working functionality.

---

# Master Codex Instruction

You are working on **WGDSS — the Trinidad and Tobago Weather Grid Decision Support System**. Build a deep, accurate understanding of electric-utility SCADA, AspenTech/Open Systems International (OSI) Digital Grid Management, and the supplied June 2026 OSI-style trend exports before changing the application.

WGDSS is an **operator decision-support and forecasting application**, not a SCADA replacement and not an autonomous control system. It combines grid telemetry, generation availability, operating reserve, weather, and historical relationships to forecast demand and estimate the risk that additional generation will be needed. It must remain read-only with respect to operational technology unless a future, separately authorized control project explicitly adds protected control functions.

Perform a repository audit first. Identify the current frontend, backend, data ingestion, database, forecast models, feature definitions, demo playback, APIs, tests, and documentation. Then produce a phased implementation plan. Do not invent proprietary OSI interfaces, tag formulas, units, reserve rules, or control permissions. Mark every uncertain utility-specific assumption and make it configurable.

---

# 1. What SCADA, EMS, GMS, Historian, and WGDSS Each Do

## 1.1 SCADA

A utility SCADA system provides centralized, near-real-time monitoring and supervisory control of geographically dispersed grid assets. Typical components include:

- Field sensors and transducers measuring MW, Mvar, voltage, current, frequency, temperature, equipment status, and other values.
- Intelligent Electronic Devices (IEDs), protective relays, Remote Terminal Units (RTUs), PLCs, and station gateways.
- Telecommunication links and front-end processors that collect telemetry and deliver commands.
- Real-time databases, HMIs, alarm/event processing, trending, engineering workstations, and operator consoles.
- Primary and backup control centers, redundancy, heartbeat/status monitoring, and failover mechanisms.
- A historian that retains time-series values, quality, timestamps, events, and operational context.

SCADA is optimized for availability, deterministic operations, operator awareness, alarms, and safe supervisory action. It is not merely a generic web API or a collection of CSV files.

## 1.2 AspenTech OSI monarch

Here, **OSI means Open Systems International/AspenTech Digital Grid Management**, not the seven-layer networking model and not OSIsoft PI. AspenTech OSI monarch is a utility platform for real-time monitoring, control, and situational awareness. Its surrounding suite can include SCADA, historian, EMS, GMS, forecasting, outage planning, network analysis, and other applications.

Relevant OSI concepts include:

- **monarch SCADA/HMI:** real-time telemetry, alarms, displays, supervisory control, and operational awareness.
- **CHRONUS/OpenHIS historian:** historical storage, trends, context, analytics, and retrieval of operational measurements.
- **OpenCalc or equivalent calculated points:** configured calculations that can create system totals, corrected values, margins, or derived tags.
- **OSI EMS:** transmission network analysis such as state estimation, contingency analysis, power flow, optimal power flow, short-circuit analysis, available transfer capability, stability analysis, and operator training simulation.
- **OSI GMS:** generation forecasting, scheduling, optimization, real-time operation, market/operational workflows, and management of generation assets.
- **OSI Forecast:** short-term load and renewable forecasting with machine-learning methods, configurable hierarchies, and configurable forecast intervals.

The exact OSI products, versions, point definitions, historian query interfaces, APIs, and custom calculations installed at T&TEC are not known from the supplied export. Codex must not assume that every public AspenTech capability is installed or licensed.

## 1.3 WGDSS

WGDSS should sit outside the safety-critical control path and consume approved replicated/exported data:

```text
Sensors / IEDs / RTUs / Plant DCS
              |
              v
     OSI SCADA real-time system
              |
      +-------+------------------+
      |                          |
      v                          v
 Historian / trends          EMS / GMS / OpenCalc
      |                          |
      +-----------+--------------+
                  |
          Approved OT-to-IT path
      (historian replica, DMZ service,
       data diode, ICCP/API, or files)
                  |
                  v
       WGDSS read-only ingestion
                  |
       Canonical telemetry storage
                  |
      Quality + feature processing
                  |
      Forecast + risk calculations
                  |
          Operator web interface
```

WGDSS must not poll field devices directly, bypass the OSI system, or write commands/setpoints into SCADA. The preferred production integration is an approved historian replica, export service, ICCP feed, or vendor-supported interface located behind the utility's OT security boundary.

---

# 2. Protocol and Integration Context

Design provider interfaces without hard-coding one transport. Candidate utility protocols and integration methods include:

- **ICCP/TASE.2:** control-center-to-control-center exchange of real-time and historical system values, schedules, accounting data, and operator messages.
- **DNP3:** telemetry/control communication among master stations, RTUs, substation computers, and IEDs.
- **IEC 60870-5-104:** TCP/IP telecontrol protocol used in SCADA and substation/control-center communication.
- **OPC UA:** platform-independent information exchange with values, timestamps, quality/status, alarms/events, and historical access where supported.
- **CIM/IEC 61970:** vendor-neutral representation of utility network objects and relationships; useful for topology/model exchange rather than replacing high-rate telemetry transport.
- **Historian query/export:** a common and safer WGDSS source for historical and replicated near-real-time data.
- **CSV/Excel files:** acceptable for demonstration and offline validation, but not proof of a live production interface.

Implement an abstraction such as:

```python
class ScadaProvider(Protocol):
    async def fetch_latest(self, tags: list[str]) -> list[TelemetryPoint]: ...
    async def fetch_range(
        self,
        tags: list[str],
        start: datetime,
        end: datetime,
        aggregation: AggregationSpec | None,
    ) -> list[TelemetryInterval]: ...
    async def health(self) -> ProviderHealth: ...
```

Potential implementations:

- `CsvTrendExportProvider` for the supplied demonstration data.
- `HistorianProvider` placeholder with no invented endpoints.
- `OpcUaProvider` only after official endpoint, namespace, certificates, security policy, and tag mapping are supplied.
- `IccpProvider` only through an approved utility interface and configured bilateral tables.
- `MockScadaProvider` for tests, clearly labeled as simulation.

Never infer credentials, server addresses, OSI API paths, or proprietary schemas.

---

# 3. Supplied June 2026 Dataset: What It Actually Contains

The uploaded archive contains five OSI-style trend export CSV files:

| File | Source tag in export | Intended WGDSS concept |
|---|---|---|
| `June Load demand 2026.csv` | `PTL132 GENERATION TOTALS` | System generation total used as a load/demand proxy, pending utility confirmation |
| `June Temperature 2026.csv` | `MHO132 AVERAGE AMBIENT TEMPERATURE` | Ambient temperature |
| `June System Spin 2026.csv` | `GSYS SYSTEM_CORRECTED_SPIN_TOTAL` | Corrected system spinning reserve |
| `System TA June.csv` | `GSYS SYSTEM_AVAIL_TOTAL` | Total Available Capacity (TA) |
| `Total Online TRA JUne.csv` | `GSYS SYSTEM_ONLN_TOTAL` | Total Running/Online Available Capacity (TRA) |

Every file uses this export schema:

```text
Pen Index
Name
Start Time
End Time
Min Time
Min Value
Max Time
Max Value
Avg Value
Quality
```

These rows are **interval summaries**, not raw telemetry samples. Each row describes an interval and gives its minimum, maximum, average, corresponding extrema timestamps, and a quality label. Preserve this semantic distinction throughout ingestion and modeling.

## 3.1 Verified profile after removing exact duplicate rows

| Variable | Unique rows | Coverage | Typical interval | Average-value range | Raw quality |
|---|---:|---|---|---|---|
| Generation/load proxy | 550 | Jun 1 00:00 to Jul 1 01:15:50 | exactly 78m 41s | 924.83–1335.96 | all `Other` |
| Temperature | 550 | Jun 1 00:00 to Jul 1 00:00 | 78–79m; final 3m | 25.56–34.05 | 543 Good, 2 Questionable, 5 Other |
| Corrected spin | 550 | Jun 1 00:00 to Jul 1 00:00 | 78–79m; final 3m | 23.31–194.89 | all `Other` |
| TA | 550 | Jun 2 23:49 to Jun 27 00:51 | 62–63m | 1585.80–1840.75 | 544 Good, 2 Questionable, 4 Other |
| TRA | 550 | Jun 2 23:49 to Jun 27 00:51 | 62–63m | 1015.80–1469.50 | 544 Good, 2 Questionable, 4 Other |

Probable units are degrees Celsius for temperature and MW for the power/capacity variables, but units are absent from the exports. Units must be confirmed from the OSI point definitions, engineering-unit metadata, or T&TEC documentation before production use.

## 3.2 Critical sampling conclusion

Each series contains approximately 550 unique output buckets even though the coverage differs:

- A full 30-day month divided into 550 buckets produces about 78.5-minute intervals.
- The approximately 24-day TA/TRA range divided into 550 buckets produces about 63-minute intervals.

This strongly indicates a **trend-export display/bucket limit or configured aggregate count**, not native hourly or raw SCADA sampling. Therefore:

- Do not claim these rows are hourly measurements.
- Do not treat each average as an instantaneous point.
- Do not upsample them into minute-level “live SCADA” values.
- Do not create synthetic precision that was not present in the source.
- Preserve `start_time`, `end_time`, interval duration, min/max/average, and raw quality.
- Request a fixed aggregation configuration or raw historian export for production model training.

## 3.3 Data anomalies that must be flagged

1. Exact duplicates exist in the generation/load, TA, and TRA files. Ingestion must be idempotent and deduplicate exact rows.
2. The generation/load export extends to **July 1 at 01:15:50**, beyond the intended June window. Flag or clip by an explicit requested reporting window; never silently discard without lineage.
3. The last temperature interval is `Jun 30 23:57–Jul 1 00:00`, but its Min/Max Time fields are `Jul 1 00:58` and `Jul 1 00:26`, outside the interval.
4. The last spinning-reserve interval is `Jun 30 23:57–Jul 1 00:00`, but its Min/Max Time fields are `Jul 1 00:06` and `Jul 1 00:03`, outside the interval.
5. TA and TRA cover only Jun 2 23:49 through Jun 27 00:51. Do not forward-fill them outside that range and present the result as observed data.
6. All generation/load and spin rows are labeled `Other`. This does **not** prove that all values are invalid. Preserve the raw value and set normalized quality to `unknown` until the OSI export's quality-code meaning is confirmed.

## 3.4 Non-Good quality windows

Temperature:

- Jun 16 13:44–15:03 — Questionable
- Jun 25 10:11–11:30 — Other
- Jun 25 11:30–12:48 — Other
- Jun 25 12:48–14:07 — Other
- Jun 25 14:07–15:26 — Other
- Jun 26 12:25–13:43 — Other
- Jun 27 00:13–01:31 — Questionable

TA and TRA share these windows:

- Jun 11 09:15–10:18 — Questionable
- Jun 21 18:57–20:00 — Questionable
- Jun 25 10:02–11:05 — Other
- Jun 25 12:08–13:11 — Other
- Jun 25 13:11–14:14 — Other
- Jun 26 13:19–14:22 — Other

These windows should remain visible in the UI and excluded, down-weighted, or separately modeled according to a configurable policy.

---

# 4. Variable Semantics and How SCADA/OSI Use Them

## 4.1 `PTL132 GENERATION TOTALS`

The tag name says **generation total**, although the filename says load demand. Do not silently rename it to measured demand.

In a balanced islanded system, aggregate real-power generation is often close to customer demand plus system losses and station service, but the relationship can differ if imports/exports, embedded generation, storage, unmetered generation, or accounting adjustments exist. Use a canonical name such as:

```text
system_generation_total_mw
```

and add metadata:

```text
business_alias: demand_proxy
semantic_status: pending_utility_confirmation
```

Questions for T&TEC/OSI administrators:

- Is this gross or net generation?
- Does it include all plants and independent power producers?
- Does it include station service, losses, embedded generation, imports, or exports?
- Is it a raw sum or an OpenCalc/custom calculated point?
- What are its source tags, scan rates, and quality aggregation rules?

Forecasting implication: it may be a valid target or proxy for system demand, but the target definition must remain explicit and versioned.

## 4.2 `MHO132 AVERAGE AMBIENT TEMPERATURE`

Temperature is an exogenous weather/load driver. In WGDSS it should support:

- Current condition display and data-quality monitoring.
- Load-forecast features: current temperature, lags, rolling values, forecast temperature, and non-linear transformations.
- Similar-day selection based on temperature profile, time of day, weekday/weekend, and season.
- Detection of unusually hot conditions that increase cooling demand.
- Potential future dynamic equipment-rating context, only if approved engineering models and additional weather variables are available.

Do not use one sensor as a universal Trinidad-wide temperature truth without documenting location and representativeness. Future work may combine station sensors with Open-Meteo/WeatherAPI forecasts and multiple geographic zones.

## 4.3 `GSYS SYSTEM_CORRECTED_SPIN_TOTAL`

Spinning reserve generally represents synchronized, online capability able to increase output quickly following a contingency or unexpected load increase. The word **corrected** indicates that the exported value may be adjusted by utility-specific rules, eligibility, derates, ramp capability, telemetry quality, unit constraints, or custom calculations.

Do not implement:

```text
spin = TRA - generation
```

as a definition. The dataset shows that spin is related to online headroom but is not identical to it. The exact formula must be obtained from OSI point/OpenCalc configuration or T&TEC operating documentation.

Use it in WGDSS for:

- Current reserve status and trend.
- Forecasted reserve-risk assessment.
- Comparison against a configurable operating-reserve requirement.
- Lead-time-aware generation recommendations.
- Data-quality and consistency checks against online capacity and output.

Reserve thresholds and response-time requirements must be utility-configurable. Do not hard-code a North American ten-minute market rule as T&TEC policy. A public FERC definition is useful background, not T&TEC's official operating criterion.

## 4.4 `GSYS SYSTEM_AVAIL_TOTAL` — TA

TA likely represents the total capacity currently declared or calculated as available, including online capability and some offline available units. It may reflect outages, derates, fuel restrictions, start capability, maintenance states, or declarations.

Use canonical name:

```text
total_available_capacity_mw
```

Do not assume every MW of TA can respond within the same time. Future unit-level data should include:

- Unit status and availability.
- Current output and operating limit.
- Maximum available output.
- Minimum stable generation.
- Ramp rate.
- Start time and synchronization time.
- Fuel type/constraint.
- Planned and forced outage state.
- Dispatch priority and operator restrictions.

## 4.5 `GSYS SYSTEM_ONLN_TOTAL` — TRA

TRA likely represents total online/running available capability, not actual generation output. Use canonical name:

```text
total_running_available_capacity_mw
```

It should normally be greater than or equal to current generation and less than or equal to TA, subject to data quality, timestamp alignment, and utility definitions.

## 4.6 Derived metrics

Only compute these when source intervals overlap sufficiently and quality is acceptable:

```text
online_headroom_mw = TRA - generation_or_demand_proxy
offline_available_capacity_mw = TA - TRA
total_available_headroom_mw = TA - generation_or_demand_proxy
online_margin_pct = online_headroom_mw / generation_or_demand_proxy * 100
available_margin_pct = total_available_headroom_mw / generation_or_demand_proxy * 100
spin_to_online_headroom_ratio = corrected_spin / online_headroom_mw
```

These are WGDSS analytical metrics, not automatically official T&TEC reserve-margin definitions. Give each derived metric a formula version, unit, source lineage, quality result, and calculation timestamp.

Expected soft invariants:

```text
0 <= generation_or_demand_proxy <= TRA <= TA
corrected_spin >= 0
temperature is within configured physical/engineering limits
```

An invariant violation should create an anomaly flag, not crash ingestion or silently alter the value.

---

# 5. Exploratory Relationships in the Supplied Data

The following are exploratory results after exact deduplication. TA/TRA midpoints were used as the common timeline, and the other interval-average series were linearly interpolated to those midpoints only for exploratory analysis. These findings are not a production validation and must not be treated as causal laws.

- Generation/load proxy vs temperature: correlation approximately **0.73**.
- Generation/load proxy vs TRA: correlation approximately **0.96**.
- Corrected spin vs generation/load proxy: correlation approximately **-0.11**.
- Corrected spin vs online headroom `(TRA - generation)`: correlation approximately **0.86**.
- Exploratory linear fit: `spin ≈ 0.744 × online_headroom + 19.10`, with `R² ≈ 0.74`.
- Spin minus online headroom has median approximately **-1.09 MW**, mean approximately **-7.85 MW**, and a wide range, confirming that the two concepts are not identical.
- Mean offline available capacity `(TA - TRA)` is approximately **508.6 MW**.
- Mean total available headroom `(TA - generation)` is approximately **613.7 MW**.
- Exploratory online margin averages approximately **9.33%**.
- Exploratory available margin averages approximately **55.75%**.
- No interpolated samples violated generation > TRA, generation > TA, or TRA > TA in the overlapping period.
- Temperature leading generation/load by one export bucket had a stronger correlation (~**0.82**) than the same-bucket relationship. One bucket is about 78–79 minutes, suggesting a possible thermal/load lag of roughly 1.3–2.6 hours across one to two buckets. This is also confounded by the daily cycle and must be validated with higher-resolution, longer-duration data.

Modeling implications:

- Temperature is useful, but non-linear and lagged relationships are likely more informative than a simple contemporaneous linear feature.
- TRA is highly correlated with generation because operators commit capacity to expected load. This can introduce **target leakage or operational-policy leakage** if future observed TRA is used to predict future demand.
- For a forecast issued at time `t`, only use variables known or legitimately forecast/scheduled at `t`. Never train with future realized TA, TRA, spin, or generation values that were unavailable at the forecast issue time.
- Separate load forecasting from generation-risk/commitment logic. First forecast demand; then assess capacity and reserve risk using the latest available and scheduled/forecast capacity information.

---

# 6. Canonical Data Model

Implement or align the existing schema with an interval-aware model. Example:

```python
class TelemetryInterval(BaseModel):
    source_system: str                 # e.g. "OSI trend export"
    source_provider: str               # e.g. "csv_trend_export"
    source_file: str | None
    source_tag: str
    pen_index: int | None
    variable_key: str                  # canonical WGDSS key

    start_time_utc: datetime
    end_time_utc: datetime
    source_timezone: str               # America/Port_of_Spain
    interval_seconds: int

    min_time_utc: datetime | None
    min_value: float | None
    max_time_utc: datetime | None
    max_value: float | None
    avg_value: float | None

    engineering_unit: str | None
    raw_quality: str | None
    normalized_quality: Literal[
        "good", "uncertain", "bad", "unknown"
    ]

    aggregation: Literal["interval_summary", "raw_sample"]
    anomaly_flags: list[str]
    ingested_at_utc: datetime
    record_hash: str                   # idempotency/deduplication
    source_metadata: dict[str, Any]
```

Recommended canonical variables:

```text
system_generation_total_mw
ambient_temperature_c
corrected_spinning_reserve_mw
total_available_capacity_mw
total_running_available_capacity_mw
```

Recommended metadata tables/configuration:

- `scada_tag_registry`
- `data_source_registry`
- `quality_mapping`
- `engineering_unit_mapping`
- `calculation_definition`
- `forecast_feature_version`
- `model_version`
- `data_quality_event`
- `provider_health_event`

The tag registry should hold:

```text
source_tag
canonical_variable
business_description
unit
source_system
source_type (raw/calculated/aggregate)
scan_or_export_interval
owner
criticality
stale_after_seconds
valid_min
valid_max
quality_policy
formula_reference
active_from / active_to
```

---

# 7. Time Alignment and Resampling Rules

1. Persist timestamps as timezone-aware UTC and retain `America/Port_of_Spain` as source timezone metadata.
2. Preserve both interval start and end. Do not reduce intervals to a point without recording whether the representative timestamp is start, end, or midpoint.
3. Deduplicate by a stable hash of source, tag, interval boundaries, values, and quality.
4. For interval-to-interval joins, prefer overlap-weighted aggregation when feasible.
5. If nearest/midpoint matching is used, make the tolerance explicit and emit match-quality metadata.
6. Never join the supplied files by row number.
7. Do not require exact timestamp equality: generation boundaries differ from temperature/spin by seconds, and TA/TRA have a different bucket size.
8. Never forward-fill beyond a configured maximum staleness window.
9. Do not interpolate across a known bad/unknown-quality gap without marking the result as imputed.
10. Do not upsample an interval summary into fake high-frequency raw telemetry.
11. Downsampling is allowed only with documented aggregation, quality propagation, and interval coverage.
12. Record data completeness for every model input window.

---

# 8. Quality, Timestamps, and Provenance

Quality is a first-class field. OPC UA publicly demonstrates the general industry pattern of `Good`, `Uncertain`, and `Bad` severities, with timestamps required to detect stale data. The OSI export's exact `Good`, `Questionable`, and `Other` meanings are vendor/configuration specific.

Default normalization until verified:

```yaml
Good: good
Questionable: uncertain
Other: unknown
missing: unknown
```

Never map `Other` to `bad` automatically. Preserve the raw text.

Quality propagation rules should consider:

- Source quality.
- Missing interval coverage.
- Staleness.
- Imputation/interpolation.
- Out-of-range values.
- Inconsistent min/max timestamps.
- Constraint violations.
- Provider health.
- Duplicate/conflicting records.

Every forecast and risk output should expose:

```text
input_data_end_time
forecast_issue_time
source_age
coverage/completeness
quality summary
imputed feature count
model version
feature version
```

---

# 9. Forecasting Architecture

Keep the existing trained XGBoost ensemble unless the repository audit proves a necessary migration. Improve the data and feature pipeline before changing algorithms.

## 9.1 Separate two problems

### A. Demand/generation forecast

Predict the canonical demand target or validated generation proxy for each future horizon.

Candidate features:

- Demand/generation lags: 1, 2, 3, 6, 12, 24 hours and horizon-appropriate equivalents.
- Rolling mean, min, max, standard deviation, trend, and ramp.
- Hour-of-day, day-of-week, weekend/holiday, month/season using cyclical encoding.
- Current and forecast temperature.
- Temperature lags, rolling temperature, cooling-degree style transforms, and non-linear interactions.
- Humidity, rainfall, cloud cover, and wind if data quality/history support them.
- Similar-day features using the whole hourly temperature profile, calendar type, and recent load shape.
- Known-at-issue-time outage, availability, and scheduled generation information where legitimately available.

### B. Capacity/reserve risk and generation-start decision

Use forecast demand plus current/scheduled capacity to estimate operational risk:

```text
forecast_online_headroom = forecast_TRA - forecast_demand
forecast_total_headroom = forecast_TA - forecast_demand
forecast_reserve_gap = required_reserve - forecast_corrected_spin
```

Where future TA/TRA/spin forecasts are not available, construct documented scenarios instead of pretending current values remain certain.

Account for WGDSS lead times:

- Quick/small generation block: approximately two 15 MW generators, around 20 minutes to start.
- Heavy generation units: approximately 60–120 MW, around one hour to start.

These values are project context and must still be configurable and confirmed. The risk engine should evaluate whether a projected margin/reserve shortfall occurs inside each resource's actionable lead-time window.

## 9.2 Avoid leakage

At every forecast issue time, assemble features from an **as-of snapshot**. Future realized spin, TA, TRA, weather observations, or revised historian values must not leak into training.

Store:

```text
observation_time
available_at_time / ingestion_time
forecast_issue_time
target_time
forecast_horizon
```

## 9.3 Validation

- Use chronological walk-forward validation or `TimeSeriesSplit`, never random train/test splitting.
- Compare against persistence and seasonal-naive baselines.
- Report MAE, RMSE, and a robust percentage metric; guard against division by very low targets.
- Report error by horizon, hour, day type, temperature band, and high-load periods.
- Evaluate forecast calibration or prediction intervals if uncertainty modeling is included.
- Track feature drift, missingness, and data-quality distribution.
- One month is insufficient to establish robust production accuracy; use the future 12-month or multi-year dataset for training and seasonal validation.

---

# 10. Demo Playback Versus Production Live Data

The June files may drive a realistic demonstration, but the UI and APIs must label the mode honestly.

Implement explicit modes:

```text
historical_replay
simulation
live_read_only
```

For historical replay:

- Map current wall-clock position to a June timestamp only in the demo clock service.
- Preserve the original source timestamp separately from display/simulation time.
- Display `Historical replay — June 2026`, not `Live SCADA`.
- Step through source intervals according to their actual boundaries.
- Do not fabricate minute-by-minute changes within an interval.
- Show playback speed and data-quality state.
- Provide pause, resume, jump, and reset controls without mutating source data.

For production:

- Show source/provider, last update, data age, quality, connection state, and fallback state.
- Degrade gracefully when the source becomes stale.
- Never hide fallback/mock data behind a live label.

---

# 11. Operator UI Requirements

The Real-Time Monitoring page should prioritize raw operational awareness:

- Current generation/load proxy, corrected spin, TA, TRA, temperature.
- Online headroom, offline available capacity, total headroom, and configurable reserve requirement.
- Synchronized multi-series trend chart with interval bands or clear aggregate markers.
- Quality badges and anomaly markers on points/intervals.
- Source tag, unit, last update, age, provider, and replay/live status.
- Forecast demand and projected margins for the next six hours.
- Lead-time markers for quick-start and heavy units.
- Clear distinction among measured, calculated, forecast, scheduled, and imputed values.
- No excessive prose replacing numerical operational data.
- Explainability panel that states the exact factors behind risk without claiming certainty.

Recommended visual status hierarchy:

```text
Normal -> Watch -> Elevated -> High -> Critical -> Data unavailable
```

Risk/status must consider both operational conditions and confidence in the input data. Poor data quality should produce `Data uncertain` rather than a falsely precise green/red decision.

---

# 12. OT Cybersecurity and Reliability Requirements

Follow defense-in-depth principles appropriate to OT:

- WGDSS is read-only by default.
- Place integration services in an approved OT DMZ or consume a replicated historian/data service.
- No direct internet or ordinary enterprise client connection into the SCADA control network.
- Consider unidirectional replication/data-diode architecture where required by utility policy.
- Use separate service identities, least privilege, certificate-based authentication where supported, network allowlists, and explicit outbound/inbound rules.
- Do not reuse operator credentials or place secrets in source code, `.env` committed files, logs, screenshots, prompts, or test fixtures.
- Maintain audit logs for ingestion, configuration changes, model deployment, recommendation generation, and operator acknowledgement.
- Support redundant providers/paths, health checks, stale-data detection, reconnect/backoff, buffering, and idempotent recovery.
- Never allow a model failure to block or degrade OSI SCADA operations.
- WGDSS outage/failure must leave grid control unaffected.
- Any future write/control integration requires a separate hazard analysis, authorization, interlocks, confirmation workflow, role separation, fail-safe design, and formal testing. It is outside the current scope.

---

# 13. Implementation Tasks for Codex

After the repository audit, implement in phases.

## Phase 1 — Documentation and data contract

1. Add `docs/SCADA_OSI_CONTEXT.md` from this file.
2. Add a variable dictionary with source tags, canonical names, tentative units, definitions, uncertainty, and questions requiring T&TEC confirmation.
3. Add an Architecture Decision Record establishing WGDSS as read-only decision support outside the OT control path.
4. Document historical replay versus live data.
5. Document all formulas and quality policies.

## Phase 2 — Robust ingestion

1. Build/repair `CsvTrendExportProvider` for the supplied schema.
2. Trim whitespace from headers and values.
3. Parse both timestamp formats present in the files.
4. Preserve interval summaries and raw quality.
5. Deduplicate exact rows using stable hashes.
6. Flag invalid extrema timestamps, partial coverage, unexpected month spillover, missing units, and unknown quality.
7. Generate a machine-readable ingestion/data-quality report.
8. Add provider health and source freshness.

## Phase 3 — Canonical storage and alignment

1. Add or migrate to an interval-aware schema.
2. Add tag registry and quality mapping configuration.
3. Implement overlap-aware alignment or a documented midpoint strategy.
4. Prevent forward-fill beyond configured staleness.
5. Store original source and simulated replay timestamps separately.

## Phase 4 — Derived operational metrics

1. Implement TA/TRA/headroom formulas with lineage.
2. Add soft invariants and anomaly events.
3. Do not derive corrected spin from TRA unless an official formula is supplied.
4. Add configurable reserve requirement and generator lead-time configuration.

## Phase 5 — Forecast feature pipeline

1. Create an as-of feature builder that prevents future leakage.
2. Combine demand history, weather, temperature lags, cyclical time features, and known-at-issue-time grid state.
3. Preserve the existing three-model XGBoost ensemble unless justified otherwise.
4. Version feature schemas and model artifacts.
5. Add time-series validation and baselines.

## Phase 6 — Risk engine

1. Forecast demand first.
2. Evaluate projected headroom/reserve under current, scheduled, and stress scenarios.
3. Tie risk to 20-minute and one-hour actionable windows.
4. Return reasons, confidence/data quality, and recommended review time.
5. Keep all operating thresholds configurable.

## Phase 7 — UI and demo fidelity

1. Update Real-Time Monitoring to show raw variables, quality, age, source, and derived margins.
2. Use honest historical-replay labeling.
3. Synchronize charts by real interval time.
4. Add anomaly/quality overlays.
5. Preserve the existing map unless a change is required for data integration.

## Phase 8 — Provider-ready production design

1. Keep CSV working for demo.
2. Add interface stubs and configuration for an approved historian/OSI provider without inventing vendor endpoints.
3. Add a production integration checklist requesting endpoint type, network zone, certificates, tags, units, quality mapping, scan rates, and failover behavior.
4. Add OT security deployment documentation.

---

# 14. Required Tests

Add automated tests for at least:

- All five CSV files parse successfully.
- Whitespace in headers/tags is normalized while raw source text can be retained.
- Exact duplicate records are idempotently removed.
- Generation/load month spillover is flagged.
- Final temperature and spin extrema timestamps outside their intervals are flagged.
- TA/TRA partial coverage is detected and not filled outside the source range.
- `Other` remains raw and normalizes to `unknown` by default.
- Interval summaries are not labeled as raw samples.
- Joining does not depend on row number or exact timestamp equality.
- Derived metrics are calculated only where inputs overlap and pass policy.
- `generation <= TRA <= TA` anomalies are reported, not silently repaired.
- Historical replay preserves source timestamps.
- Forecast features contain no values newer than the issue-time cut-off.
- Random train/test split is not used for time-series evaluation.
- API responses expose data age, quality, provenance, model version, and feature version.
- Mock/replay data can never be shown as production live data.

---

# 15. Acceptance Criteria

The work is complete only when:

1. Codex has audited the current repository and explained what it changed and why.
2. All five supplied variables have explicit lineage, canonical names, units/status, and definitions.
3. The application treats exported rows as interval aggregates.
4. Duplicate, partial, unknown-quality, and invalid-timestamp conditions are visible and tested.
5. Forecast features are issue-time-correct and leakage-safe.
6. Demand forecasting is separated from reserve/capacity risk logic.
7. Corrected spin is not falsely equated with TRA minus generation.
8. All thresholds and generator lead times are configurable.
9. Historical replay is clearly distinguished from live SCADA.
10. WGDSS remains read-only and cannot issue operational commands.
11. Documentation identifies every utility-specific item still requiring T&TEC/OSI confirmation.
12. Existing working features and models are preserved unless a migration is tested and justified.

---

# 16. Questions That Must Be Answered Before Production Integration

Codex should create a checklist for the project owner/SCADA team:

1. Which AspenTech OSI products and versions are installed: monarch SCADA, CHRONUS/OpenHIS, EMS, GMS, Forecast, OpenCalc, or others?
2. Are the five tags raw telemetry, accumulated points, or calculated points?
3. What are the official engineering units and point descriptions?
4. What does `Quality = Other` mean in this export?
5. How does OSI aggregate quality for Min/Max/Avg trend buckets?
6. What is the exact formula for `SYSTEM_CORRECTED_SPIN_TOTAL`?
7. What assets and derates are included in `SYSTEM_AVAIL_TOTAL` and `SYSTEM_ONLN_TOTAL`?
8. Is `PTL132 GENERATION TOTALS` an accepted demand proxy, and what is excluded/included?
9. What is the native scan rate and historian compression/deadband configuration?
10. Can a fixed hourly, 15-minute, 5-minute, or raw historian export be obtained?
11. Which production interface is approved: historian replica, OSI export service, ICCP, OPC UA, database replica, or another mechanism?
12. What are T&TEC's operating-reserve requirement, largest credible contingency, unit start times, ramp limits, and escalation thresholds?
13. Which future availability/schedule data is known at forecast issue time?
14. What OT network zone, DMZ, authentication, certificate, firewall, audit, and failover requirements apply?
15. Who owns approval of tags, formulas, models, recommendations, and deployment?

---

# 17. Public Research Basis

This context is based on official and primary material, including:

- AspenTech product documentation for OSI monarch, OSI Energy Management System, OSI Generation Management System, OSI CHRONUS Historian, and OSI Forecast.
- NIST Special Publication 800-82 Revision 3, *Guide to Operational Technology Security*.
- NERC implementation guidance describing ICCP/TASE.2 control-center data exchange and redundancy.
- OPC Foundation OPC UA specifications for values, timestamps, and Good/Uncertain/Bad data-quality semantics.
- IEC/CIM, DNP3, and ICCP standards organization material.
- FERC background material describing operating, spinning, and non-spinning reserve concepts.
- The supplied June 2026 OSI-style trend export files.

Public product descriptions explain general capabilities but cannot reveal T&TEC's private OSI configuration, custom tag calculations, operating criteria, or network design. Treat those as unresolved until authoritative utility documentation is supplied.
