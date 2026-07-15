# June SCADA Forecast Assessment

## Purpose

This assessment records the evidence used to redesign WGDSS around the supplied
June 2026 SCADA export. The files are historical exports, not a live SCADA
connection. They support prototype model development, replay, and validation.
They do not authorize live dispatch.

## Supplied Dataset

The two supplied `junescadadata` ZIP files have different archive hashes but
contain byte-identical CSV members. Deduplication must therefore occur at the
member-content level as well as the archive level.

| CSV | Normalized field | Rows | Source interval | Time coverage | Quality |
|---|---|---:|---|---|---|
| `June Load demand 2026.csv` | Demand | 551 | 78m 41s | Jun 1 00:00 to Jul 1 01:15 | 551 Other |
| `June Temperature 2026.csv` | Temperature | 550 | 78-79m | Jun 1 00:00 to Jul 1 00:00 | 543 Good, 5 Other, 2 Questionable |
| `June System Spin 2026.csv` | Spin/reserve power | 550 | 78-79m | Jun 1 00:00 to Jul 1 00:00 | 550 Other |
| `System TA June.csv` | Total Available (TA) | 551 | 62-63m | Jun 2 23:49 to Jun 27 00:51 | 545 Good, 4 Other, 2 Questionable |
| `Total Online TRA JUne.csv` | Total Running Availability (TRA) | 551 | 62-63m | Jun 2 23:49 to Jun 27 00:51 | 545 Good, 4 Other, 2 Questionable |

All files use the existing ten-column SCADA schema and `Avg Value` is the
interval value. The demand file uses two-digit years and extra whitespace, which
the pre-upgrade parser does not accept. Tag names also contain trailing spaces.

### Data Quality Findings

- No required `Avg Value` or timestamp is missing.
- Demand, TA, and TRA each contain one exact duplicate final interval.
- The five series are not row-aligned and do not share a cadence. Joining by row
  number or start-hour would be mathematically wrong.
- Interval-overlap resampling at a 90% hourly coverage threshold produces 577
  complete hours from Jun 3 00:00 through Jun 27 00:00. Excluding
  `Questionable` portions leaves 571 model-eligible hours through Jun 26 23:00.
- `Other` cannot be silently presented as `Good`. It is conditionally usable
  for this export with a warning because all demand and spin rows carry that
  label; `Questionable` remains excluded.
- Observed ranges are plausible for this prototype: demand 924.83-1335.96 MW,
  temperature 25.56-34.05 C, spin 23.31-194.89 MW, TA 1585.8-1840.75 MW, and
  TRA 1015.8-1469.5 MW.
- In the complete window, TA never falls below TRA, TRA never falls below
  demand, and spin is never negative.
- Mean TA margin is 613.65 MW and mean TRA spare is 105.05 MW.
- Piarco Open-Meteo historical temperature is strongly aligned with SCADA
  temperature (correlation 0.921), but averages 1.91 C lower. SCADA ambient
  temperature remains authoritative for the measured grid site.

## Predictor Availability And Leakage Policy

For a forecast generated at time `t` for target `t+h`, only values observed or
issued at or before `t` are eligible.

| Variable | Demand model | Risk engine | Rule |
|---|---|---|---|
| Demand at `t` and earlier | Yes | Yes | Lags, rolling means, and rates use timestamps no later than `t` |
| SCADA temperature at `t` and earlier | Yes | Weather effect | Never use actual temperature at `t+h` |
| External weather observed by `t` | Yes | Weather effect | Current humidity/rain/cloud/wind/pressure are valid |
| Provider forecast issued by `t` | Yes | Yes | Target-hour weather is valid only when issuance/creation time is proven |
| TA, TRA, and Spin at `t` and earlier | Challenger only | Yes | Future operating values are forbidden |
| TA, TRA, Spin, demand, or actual weather at `t+h` | No | No | Target leakage |

TRA has a 0.959 correlation with demand in this archive because online plant is
dispatched in response to load. Although current TRA is technically known, it
can teach a demand model an operational response rather than a causal demand
driver. TA, TRA, and Spin are therefore retained as timestamped context and as
explicit risk inputs, but are not in the default demand feature profile.

Historical Open-Meteo observations may enrich current-time features. They must
not be relabelled as archived forecasts. If no provider forecast with
`created_at <= t` exists, target-weather features remain missing and the model
uses missingness indicators. This avoids perfect-weather leakage.

## Exploratory Chronological Benchmark

The final pipeline must repeat model selection with nested walk-forward
validation. An initial 80/20 chronological holdout over the 571 eligible hours
showed the following direction:

| Horizon | Strongest demand/weather model | MAE | RMSE | Persistence MAE | Ops-context result |
|---:|---|---:|---:|---:|---|
| 1h | Ridge | 14.04 MW | 20.06 MW | 30.72 MW | Worse than demand/weather-only |
| 2h | HistGradientBoosting | 22.16 MW | 27.83 MW | 57.33 MW | Worse than demand/weather-only |
| 6h | RandomForest | 33.33 MW | 42.16 MW | 130.14 MW | Worse than demand/weather-only |

This is a prototype result from less than one month, not a production claim.
The active model for each horizon must beat the selected chronological baseline
on both MAE and RMSE before replacing it.

## Recommended Architecture

### 1. Reusable Ingestion

- Accept a ZIP or one or more CSV exports without depending on filenames or
  fixed row positions.
- Normalize headers, tags, whitespace, timestamps, and Trinidad timezone.
- Validate intervals and numeric ranges before database mutation.
- Hash each CSV payload so repackaged archives cannot duplicate measurements.
- Preserve raw quality and source provenance.
- Detect exact duplicates and report skipped rows.
- Resample by interval overlap into hourly bins; require configurable coverage.
- Mark conditional quality and excluded quality explicitly.
- Emit a structured dataset-quality report with ranges, cadence, coverage,
  missing fields, duplicates, and next actions.

### 2. Leakage-Safe Feature Dataset

- Create direct 1h, 2h, and 6h target rows.
- Add demand lags (1h, 2h, 3h, 6h, 24h), rolling averages (3h, 6h, 24h), and
  demand rates (1h, 3h, 6h).
- Add SCADA-temperature lag, rolling mean, rate, cooling degree, and
  temperature-demand interaction.
- Retain current and lagged TA/TRA/Spin for audit and challenger evaluation, but
  keep them out of the default demand feature profile.
- Add current external humidity, rain, cloud, wind, and pressure.
- Add target-hour provider forecast fields only when their issuance timestamp
  proves availability at feature time.
- Store feature provenance and quality state.

### 3. Horizon Model Selection

- Keep persistence, trend-adjusted persistence, rolling trend,
  same-hour-yesterday, and hourly-average baselines.
- Compare Ridge, HistGradientBoostingRegressor, and RandomForestRegressor for
  each horizon.
- Select hyperparameters and model family with expanding-window validation on
  the training partition.
- Evaluate the selected challenger once on an untouched chronological holdout.
- Activate ML only when it improves both MAE and RMSE by at least 2%.
- Refit the accepted method on all eligible data for inference.
- Store model version, feature profile, sample span, candidate metrics, residual
  uncertainty, and prototype/trusted status.

### 4. Operational Risk

Demand prediction and dispatch risk remain separate. Risk uses the selected
forecast and uncertainty together with current TA, TRA, Spin, reserve margin,
weather effect, expected rise, and startup lead time.

- No shortfall: `NO ACTION`.
- Uncertain or distant exposure: `MONITOR`.
- Up to 15 MW within 20 minutes: start one 15 MW set.
- Above 15 MW and up to 30 MW within 20 minutes: start both 15 MW sets.
- Above 30 MW within 60 minutes: start a 60, 90, or 120 MW heavy set.
- If projected shortfall exceeds available startable capacity, escalate and
  report the residual shortfall rather than pretending it is covered.

### 5. Simulated-Live Replay

Map the current Trinidad day and hour to the same June day/hour. Use only rows
at or before that simulated cursor for model fitting and feature generation.
Future June demand, TA, TRA, Spin, and observed weather remain hidden. The
dashboard must label this source as historical SCADA replay/simulation.

## Limitations

- The common TA/TRA window is only about 24 days and has limited weekday and
  weather-regime diversity.
- No outage schedule, holiday calendar, unit commitment plan, or archived
  provider-issuance snapshots were supplied.
- `Other` quality requires engineering confirmation before production use.
- Model accuracy from this archive is prototype evidence only. A 12-month
  export is needed for seasonal, holiday, outage, and regime validation.
- Production integration still requires a read-only historian, automated CSV
  export, PI/OSIsoft connector, OPC-UA connection, or approved SCADA API.

