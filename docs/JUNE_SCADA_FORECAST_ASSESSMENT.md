# June SCADA Forecast Assessment

## Purpose

This assessment records the evidence used to redesign WGDSS around the supplied
June 2026 SCADA export. The files are historical exports, not a live SCADA
connection. They support prototype model development, replay, and validation.
They do not authorize live dispatch.

## Supplied Dataset

The inspected `junescadadata.zip` contains five independent CSV members. The
pipeline hashes each member payload, so repackaging or renaming the ZIP does not
duplicate previously imported measurements.

| CSV | Normalized field | Rows | Source interval | Time coverage | Quality |
|---|---|---:|---|---|---|
| `June Load demand 2026.csv` | Demand | 551 | 78m 41s | Jun 1 00:00 to Jul 1 01:15 | 551 Other |
| `June Temperature 2026.csv` | Temperature | 550 | 78-79m | Jun 1 00:00 to Jul 1 00:00 | 543 Good, 5 Other, 2 Questionable |
| `June System Spin 2026.csv` | Spin/reserve power | 550 | 78-79m | Jun 1 00:00 to Jul 1 00:00 | 550 Other |
| `System TA June.csv` | Total Available (TA) | 551 | 62-63m | Jun 2 23:49 to Jun 27 00:51 | 545 Good, 4 Other, 2 Questionable |
| `Total Online TRA JUne.csv` | Total Running Availability (TRA) | 551 | 62-63m | Jun 2 23:49 to Jun 27 00:51 | 545 Good, 4 Other, 2 Questionable |

In the historical replay UI, demand remains sourced from `PTL132 GENERATION
TOTALS`, while the displayed generation value and generation graph are sourced
from Total Running Availability (TRA). TA remains the separate available
capacity value.

All files use the existing ten-column SCADA schema and `Avg Value` is the
interval value. The demand file uses two-digit years and extra whitespace, which
the pre-upgrade parser does not accept. Tag names also contain trailing spaces.

### Data Quality Findings

- No required `Avg Value` or timestamp is missing.
- Demand, TA, and TRA each contain one exact duplicate final interval.
- The five series are not row-aligned and do not share a cadence. Joining by row
  number or start-hour would be mathematically wrong.
- The implemented interval-overlap resampler emits 722 hourly buckets across
  the union of all source ranges. Of these, 569 have all five required fields
  at or above 90% coverage and are conditionally usable; 153 are degraded by
  missing coverage, excluded `Questionable` portions, or boundary mismatch.
- `Other` cannot be silently presented as `Good`. It is conditionally usable
  for this export with a warning because all demand and spin rows carry that
  label; `Questionable` remains excluded.
- Observed ranges are plausible for this prototype: demand 924.83-1335.96 MW,
  temperature 25.56-34.05 C, spin 23.31-194.89 MW, TA 1585.8-1840.75 MW, and
  TRA 1015.8-1469.5 MW.
- In the complete window, TA never falls below TRA, TRA never falls below
  demand, and spin is never negative.
- Mean TA margin is 613.65 MW and mean TRA spare is 105.05 MW.
- Corrected System Spin averages 97.30 MW. It differs from the raw
  `TRA - demand` gap by 11.47 MW mean absolute error, so the corrected SCADA tag
  is authoritative and the raw gap is diagnostic only.
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

All three horizons use the same availability-safe source fields but train and
select independently. The target clock and target-weather baseline are computed
for each horizon. The vector includes short/long demand lags and rates,
current/forecast cooling degree, temperature-humidity interaction, explicit
cooling-degree x current-load interaction, and temperature-rate x demand-rate
interaction. At 1h the recent trajectory can dominate; at 2h/6h each separate
model can rely more on target-hour cycle and weather. No feature is accepted
merely from correlation, and future TA/TRA/Spin remain forbidden.

Historical Open-Meteo observations enrich current-time features. They are never
relabelled as archived provider forecasts. If no provider forecast with
`created_at <= t` exists, target-weather fields use an explicitly labelled
same-hour historical baseline built only from observations at or before `t`.
Those rows are down-weighted and retain a distinct quality code. Future observed
weather is never copied into a forecast feature.

## Exploratory Chronological Benchmark

The implemented pipeline performs nested expanding-window candidate selection
inside the training partition and evaluates the selected candidate once on an
untouched chronological 20% holdout. The July 16, 2026 v3 build produced:

| Horizon | Active method | MAE | RMSE | MAPE | Best baseline | Baseline MAE |
|---:|---|---:|---:|---:|---|---:|
| 1h | HistGradientBoosting + similar periods | 14.88 MW | 18.92 MW | 1.22% | Trend-adjusted persistence | 18.70 MW |
| 2h | Similar periods | 19.43 MW | 22.72 MW | 1.62% | Similar periods | 19.43 MW |
| 6h | Ridge + similar periods | 19.67 MW | 27.73 MW | 1.65% | Similar periods | 24.92 MW |

Compared with v2.1, v3 improves the full-history holdout MAE from 15.40 to
14.88 MW at 1h, 24.10 to 19.43 MW at 2h, and 30.75 to 19.67 MW at 6h. The 2h
result remains on the similarity baseline because no ML blend beat it by the
required MAE and RMSE margin. The 6h blend uses 75% similar-period evidence and
25% Ridge output.

At the mapped Jun 15 14:00 source cursor, the cutoff-only artifact selected
trend-adjusted persistence at 1h and RandomForest at both 2h and 6h. This
difference is expected: model selection is repeated using only the
history available at the simulated cursor rather than later June rows.

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
- Add demand lags (1h, 2h, 3h, 6h, 24h, 48h, 168h), rolling averages (3h, 6h,
  12h, 24h, 168h), same-hour seven-day history, six-hour volatility, and demand
  rates (1h, 3h, 6h).
- Add SCADA-temperature lag, rolling mean, rate, cooling degree, and
  temperature-demand interaction.
- Retain current and lagged TA/TRA/Spin for audit and challenger evaluation, but
  keep them out of the default demand feature profile.
- Add current external humidity, rain, cloud, wind, and pressure.
- Add target-hour provider forecast fields only when their issuance timestamp
  proves availability at feature time. Otherwise use the past-only weather
  baseline with explicit provenance and reduced quality weight.
- Store feature provenance and quality state.

### 3. Horizon Model Selection

- Keep persistence, trend-adjusted persistence, rolling trend,
  same-hour-yesterday, and hourly-average baselines.
- Compare Ridge, HistGradientBoostingRegressor, RandomForestRegressor, and
  ExtraTreesRegressor for each horizon.
- Compare pure similar-period forecasts and 25%, 50%, and 75% similarity blends
  of every ML family. Similarity uses only already-observed targets and weighs
  target hour, forecast temperature within a 4 C preferred band, weekday/
  weekend/holiday class, season, humidity, rain, cloud, load, and recent trend.
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

### 5. Historical Replay

Map the current Trinidad day and hour to the same June day/hour. Use only rows
at or before that replay cursor for model fitting and feature generation.
Future June demand, TA, TRA, Spin, and observed weather remain hidden. The
dashboard must label this source as historical SCADA replay/simulation.

The offline pipeline stores direct 1h, 2h, and 6h results keyed by
`source_cursor_at`. The dashboard mounts those results only on an exact cursor
match, maps their target times into the display replay year, and uses the same
profile for operating risk. A mismatched future artifact is ignored.

## Implemented Pipeline Evidence

Running:

```powershell
venv\Scripts\python.exe scripts\run_scada_replay_pipeline.py `
  --backfill-weather C:\path\to\junescadadata.zip
```

produced 2,157 direct-horizon training rows (721 at 1h, 720 at 2h, and
716 at 6h), 744 Open-Meteo historical weather rows, and three cutoff-safe replay
forecast artifacts. The validation report marked operating risk ready from
`CUTOFF_SAFE_REPLAY`, while retaining `PROTOTYPE` validation status.

Open-Meteo archive data is used under its CC BY 4.0 terms. Endpoint reference:
<https://open-meteo.com/en/docs/historical-weather-api>.

## Limitations

- The common TA/TRA window is only about 24 days and has limited weekday and
  weather-regime diversity.
- No outage schedule, unit commitment plan, approved variable-holiday calendar,
  or archived provider-issuance snapshots were supplied. The model includes
  fixed and Easter-relative Trinidad holidays plus configurable extra dates,
  but these cannot be validated adequately from one month.
- The past-only weather baseline is leakage-safe but is less informative than a
  genuine archived forecast run and must not be described as one.
- `Other` quality requires engineering confirmation before production use.
- Model accuracy from this archive is prototype evidence only. A 12-month
  export is needed for seasonal, holiday, outage, and regime validation.
- Production integration still requires a read-only historian, automated CSV
  export, PI/OSIsoft connector, OPC-UA connection, or approved SCADA API.
