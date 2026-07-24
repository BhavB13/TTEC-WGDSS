# System Context and Operator Workflow

## Purpose

The T&TEC Weather Grid Decision Support System (WGDSS) helps a control engineer
review weather-driven demand, grid capacity context, demand forecasts, and the
modeled probability that additional generation may be needed.

The application is advisory. It:

- displays weather, replayed grid measurements, forecasts, and provenance;
- forecasts demand and estimates forecast uncertainty;
- compares demand uncertainty with current online generation capacity (TRA);
- produces an aggregate, machine-generated capacity suggestion;
- supports manual what-if evaluation of proposed aggregate start blocks.

It does not:

- replace SCADA, EMS, GMS, AspenTech OSI, or an operator HMI;
- poll field devices;
- issue starts, stops, setpoints, acknowledgements, or switching commands;
- prove forecast accuracy from one static July snapshot;
- contain a production-approved reserve policy or generation roster.

## Current Operating Modes

| Mode | Status | Data | Intended use |
|---|---|---|---|
| June active day | **Simulated** | Persistent June replay, optionally overlaid with imported five-tag June historical exports | Demonstration, replay, and operator workflow testing |
| Previous June day | **Simulated historical replay** | Completed hourly June observations selected by date | Inspect a prior day without future-row leakage into the active cursor |
| Live weather test | **Implemented display aid** | Current provider response and short forecast | Weather display testing only; it does not make grid data live |
| July SCADA Test | **Experimental** | Immutable `20260723.zip`-style CSV/Excel trend snapshot | Parsing, provenance, static model-input, and UI testing |
| Mock grid | **Default provider** | `MockGridProvider` | Local operation and tests |
| Production live SCADA/OSI | **Planned** | No endpoint, credentials, protocol, or connector supplied | Requires approved read-only integration |

`GRID_PROVIDER=mock` is the default. Selecting an unimplemented SCADA or
historian provider fails closed; it does not silently create a live connection.

## Operator Workflow

1. Start WGDSS and verify the header labels the active source as simulated,
   replay, archived, or experimental.
2. Check `/api/v1/health` or the dashboard quality badges before using any
   forecast.
3. Confirm displayed time, source observation time, provider, quality, and
   freshness.
4. Use the map for weather and geographic context. Map imagery is external
   visualization and is not the source of SCADA values.
5. Use **Overview** for current demand, TRA, available capacity, corrected
   System Spin, weather, and the full-day load forecast.
6. Use **Grid Ops** for aggregate and demonstration generation information.
7. Use **Weather** for weighted Trinidad and Tobago weather and the six-hour
   weather/demand outlook. The optional live weather view changes weather only.
8. Use **Demand** for forecast, uncertainty, observed demand, TRA, temperature,
   and historical comparison.
9. Use **Risk** for the no-action generation-need probability. Confirm the
   selected highest-risk horizon and the current-TRA evidence.
10. Use **Guidance** to review the advisory block suggestion or evaluate a
    hypothetical plan. A proposed start changes only the hypothetical
    post-plan risk.
11. Use **Analytics** for replay/model evidence and calibration summaries.
12. Use **SCADA Test** only on the experiment branch for the isolated July
    static snapshot.

All start/stop decisions and physical actions remain the responsibility of the
authorized control engineer.

## June Time Navigation

The frontend stores the selected day in browser local storage under
`wgdss-dashboard-selected-day`. The selected date is sent as
`selected_date=YYYY-MM-DD` to `/api/v1/dashboard/snapshot`.

The backend:

- constrains selectable dates to available `scada_grid_snapshots` inside the
  configured June archive period;
- excludes dates after the active replay date;
- limits the active day to rows at or before the replay cursor;
- returns all available rows for a completed previous day;
- reports completeness, record count, source, classification, and a notice.

Classifications are:

- `SIMULATED_LIVE` for the active June replay day;
- `SIMULATED_REPLAY_DAY` for a selected previous June day.

The implementation provides single-day selection and previous/next/reset
navigation. General multi-day range selection is not implemented.

## July Static Snapshot Experiment

The July experiment is isolated from normal June tables and the stable baseline:

- source file is hashed before and after reading;
- source is never modified;
- raw and cleaned audit records are stored under
  `backend/var/live_scada_sessions/<session-id>/`;
- experiment data is not imported into the normal WGDSS database;
- timestamps use `America/Port_of_Spain`;
- the latest common boundary uses demand, temperature, corrected spin, and TRA;
- weather after the boundary is captured and hashed for reproducibility;
- the UI displays the observed/forecast boundary and warnings.

The repository does not contain a fitted frozen model artifact. The experiment
therefore reports `NO_FROZEN_MODEL_ARTIFACT` and may show a persistence
reference, not a validated six-hour model forecast. See
[DATA_AND_ANALYTICS.md](DATA_AND_ANALYTICS.md).

## Required Human Confirmations

The following are explicitly unverified:

- official meanings and units of all five OSI-exported tags;
- whether `PTL132 GENERATION TOTALS` is an approved demand target/proxy;
- quality meanings for `Other`, `Questionable`, and future OSI quality codes;
- reserve target and generation-need thresholds;
- small/heavy block capacities, availability, lead times, and constraints;
- approved live read-only OSI/historian interface and network boundary;
- production data-retention, audit, backup, recovery, and availability targets;
- model approval criteria and named approvers.

Track decisions in `docs/SCADA_OSI_CONFIRMATION_REGISTER.md`.

