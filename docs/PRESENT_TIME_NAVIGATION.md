# Present Timeline and June Day Navigation

## Purpose

WGDSS exposes one operational view: **Present**. In the current prototype,
Present is backed by the June 2026 SCADA export replay. It is read-only decision
support and is not a live control feed.

Operators may inspect the active simulated-present day or select an earlier
available June day. An earlier day is still a replay of Present, not a separate
dashboard mode.

## API Contract

`GET /api/v1/dashboard/snapshot`

Optional query parameter:

- `selected_date=YYYY-MM-DD`

Omitting `selected_date` returns the active simulated-present day. Explicit
dates must exist in the available June archive and must not be later than the
active replay day. Invalid or unavailable dates return HTTP 422.

Every public snapshot supplies `time_context`:

- `selected_date`
- `active_date`
- `is_active_day`
- `displayed_at`
- `source`
- `value_classification`
- `available_start`, `available_end`, and exact `available_dates`
- hourly record count, completeness, and quality notice
- cutoff-safe hourly `series`

The removed `mode`, `start_date`, `end_date`, and `granularity` parameters are
not part of the current dashboard API.

## Frontend State

`DashboardTimeProvider` owns one persisted optional selected date. A null
selection means “follow the active simulated-present day.” It is mounted above
all tabs, so navigation does not reset the selected day.

`DayNavigationBar` provides:

- an exact June date picker;
- previous and next available-day buttons;
- a Return to Active Day command;
- active-day versus previous-day classification;
- selected date, source, hourly record count, and status notice.

The browser sends the same `selected_date` to the single snapshot endpoint for
every tab. There are no tab-local date modes.

## Data Classification

### Active simulated-present day

- Classification: `SIMULATED_LIVE`
- Grid and weather observations are revealed only through the active replay
  cursor.
- Replay controls are available.
- Actual demand and TRA stop at the present boundary.
- ML demand and weather forecasts continue beyond the boundary.

### Previous June day

- Classification: `SIMULATED_REPLAY_DAY`
- The selected day is shown as a completed hourly replay.
- Replay controls are hidden because the global active cursor is not mutated.
- Charts show recorded demand, TRA, system spin, quality, and gaps.
- Current-provider weather is never substituted into the selected prior day.
- Live sampling points and current cloud/rain/wind imagery are off by default.
  Operators may enable the clearly labelled current imagery layers as spatial
  context, but those layers are not presented as selected-day observations.

## Forecast Boundary

The active load chart keeps a continuous full-day forecast demand line for
comparison. Recorded demand remains a separate solid green series. A dashed
vertical `PRESENT | FORECAST` marker identifies the cutoff, while badges,
tooltips, line styles, and the legend identify observed, comparison, and
forecast values.

Previous-day charts contain recorded observations only and do not append future
forecasts.

## ML Isolation

The dashboard navigation policy does not change model training:

- Training: 2025-10-01 through 2026-05-31
- Simulated-present/out-of-sample replay: 2026-06-01 through 2026-06-30

June remains excluded from feature scaling, candidate selection, model fitting,
hyperparameter selection, and validation. Dashboard day selection is a query
and replay concern only.

## Files

Backend:

- `backend/app/api/dashboard.py`
- `backend/app/core/config.py`
- `backend/app/schemas/dashboard.py`
- `backend/app/schemas/dashboard_time.py`
- `backend/app/services/data_period_policy.py`
- `backend/app/services/present_day_service.py`
- `backend/app/services/dashboard_service.py`

Frontend:

- `frontend/src/context/DashboardTimeContext.tsx`
- `frontend/src/components/DayNavigationBar.tsx`
- `frontend/src/components/SelectedDayChart.tsx`
- `frontend/src/components/ReplayLoadChart.tsx`
- `frontend/src/pages/Dashboard.tsx`
- `frontend/src/services/api.ts`
- `frontend/src/types/dashboard.ts`
- `frontend/src/index.css`

Tests:

- `backend/tests/test_present_day_service.py`
- `frontend/src/pages/Dashboard.test.tsx`
- `frontend/src/components/ReplayLoadChart.test.tsx`

## Future SCADA/OSI Integration

The future live provider should replace the active Present source behind the
existing snapshot service. The UI contract remains:

- no selected date means follow the latest quality-accepted live timestamp;
- a selected archived date loads a read-only replay;
- provider provenance and freshness remain explicit;
- no UI action sends commands to SCADA or generation equipment.

Confirmed OSI endpoint details, credentials, units, tag definitions, and
production archive-query policy remain T&TEC-owned integration items.

## Limitations

- Present currently uses June exports, not a live historian connection.
- Prior-day humidity, rainfall, cloud, and wind depend on archived weather
  coverage; absent fields remain visibly unavailable.
- Previous-day operational recommendations are replay-time calculations, not
  records of decisions actually made by operators.
