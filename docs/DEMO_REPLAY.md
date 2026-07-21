# WGDSS Production-System Demonstration Replay

## Purpose And Data Provenance

The demonstration mode presents the proposed production workflow without
claiming that a live T&TEC SCADA connection exists. It seeds one deterministic
hourly dataset for calendar year 2025 (8,760 observations). The values are
synthetic but operationally shaped for Trinidad and Tobago: daily and weekly
load cycles, wet/dry-season weather, temperature/humidity cooling demand,
rainfall effects, reserve variation, and periodic capacity derating.

June 2025 is the simulation-replay source month. The other eleven months remain an
immutable historical archive. The UI and API label the source as
`WGDSS 12-Month Synthetic SCADA/Weather Demonstration` and all decisions remain
`SIMULATION` only.

## Separation Of Responsibilities

```text
demo_observations (immutable 12-month archive)
        |
        +--> analytics: all 12 months, June marked REPLAY_SOURCE
        |
        +--> forecast training: observations strictly before replay cursor
        |
        +--> June source rows
                  |
          demo_replay_state (mutable cursor/control only)
                  |
          DemoReplayService
                  |
          dashboard snapshot DTO
                  |
          React control-room presentation
```

- `DemoObservation` stores SCADA-like grid measurements and colocated weather.
- `DemoReplayState` stores only replay configuration and the current cursor.
- `DemoReplayService` advances the cursor, reveals records, creates forecast
  features, and assembles replay DTOs.
- `DashboardService` consumes replay DTOs through the same grid/weather/
  probability boundary used by the normal dashboard.
- React owns presentation and controls; it never invents or advances records.

## Forecast Integrity

The full-day load forecast uses only demand observations available before the
current replay cursor. It combines the target-hour profile with exact
1/2/3/6/24/48/168-hour demand lags, trailing 3/6/12/24-hour moving averages,
short-term ramps, a median recent-profile residual, current grid context, and the
target-hour weather outlook. Ridge penalty and blend weight are selected on a
chronological tuning block. The selected load-state/weather challenger is then
activated only when it improves on the strongest statistical method on a
separate newest chronological holdout.
Future hours recurse on prior forecasts rather than reading future June demand.
When a provider outlook is missing, the model uses its learned hourly weather
profile instead of holding the last weather observation indefinitely. The chart
distinguishes:

- forecast demand;
- historical hourly average;
- revealed simulation-replay demand;
- revealed TRA where the source archive provides it;
- residual-calibrated per-hour uncertainty.

Model inputs and residual corrections are clipped to bounds learned from the
fit partition. A six-hour median profile correction follows a sustained load
shift while limiting the effect of one abnormal current reading.

The complete archive is available for retrospective analytics, but records
after the cursor are excluded from forecast fitting to prevent future leakage.

Forecast training also stays within one provenance regime. On a SCADA-backed
replay day, only SCADA intervals finalized by the model issue time are eligible;
synthetic rows never fill unavailable SCADA gaps. The chart may reveal later
source values while retaining the earlier model issue time. Outside complete
SCADA coverage, the entire forecast, weather context, risk input, and UI status
switch to the synthetic simulation regime instead of carrying the last SCADA
state forward.

## Playback

The dashboard has persistent Play, Pause, Step, and Sync Now controls. On first
startup after migration, the replay maps Trinidad's current day and hour into
June and advances at real-time speed. Step size is configurable as one hour, six
hours, or one day. Automatic playback also supports one simulated minute, ten
simulated minutes, one simulated hour, or one simulated day per real second.

Synthetic replay weather is derived only from rows revealed by the replay
cursor. When the historical June SCADA archive is present, Open-Meteo Archive
observations provide humidity, rainfall, cloud, wind, and pressure; SCADA
temperature remains authoritative. Future weather first uses the Open-Meteo
Single Runs archive to retrieve ECMWF IFS, NOAA GFS, and DWD ICON model output
issued early enough to be available at the source cursor. Model values are
reconciled by source timestamp and mapped onto the display clock by lead time.
They drive the weather-sensitive demand and operating-risk forecast. If that
archive is unavailable, the system uses a one-source same-hour baseline built
only from observations at or before the cursor.

The offline pipeline may store exact-cursor 1h-through-6h forecast artifacts. The
dashboard uses them when the archived issued-weather ensemble is unavailable,
and only when `source_cursor_at` matches the simulated SCADA cursor and all
feature/target timestamps are valid. Otherwise it falls back to the cutoff-safe
replay forecast; it never uses a later artifact. See
`docs/JUNE_SCADA_FORECAST_ASSESSMENT.md` for the evidence and limitations.

API:

```text
GET  /api/v1/replay/status
POST /api/v1/replay/control
```

Example control body:

```json
{
  "action": "configure",
  "step_minutes": 1440,
  "speed_multiplier": 86400
}
```

Seed or reset from the command line:

```powershell
cd backend
venv\Scripts\python.exe -m alembic upgrade head
venv\Scripts\python.exe scripts\seed_demo_replay.py --force
```

## Production Replacement Path

The immutable demonstration store is an adapter boundary, not a substitute for
production telemetry. A production implementation should replace the seeder and
replay cursor with a read-only historian, PI/OSIsoft, OPC-UA, approved SCADA API,
or controlled export pipeline. The dashboard contract can remain stable while
`GridProvider` and weather/history repositories change underneath it.
