# WGDSS Production-System Demonstration Replay

## Purpose And Data Provenance

The demonstration mode presents the proposed production workflow without
claiming that a live T&TEC SCADA connection exists. It seeds one deterministic
hourly dataset for calendar year 2025 (8,760 observations). The values are
synthetic but operationally shaped for Trinidad and Tobago: daily and weekly
load cycles, wet/dry-season weather, temperature/humidity cooling demand,
rainfall effects, reserve variation, and periodic capacity derating.

June 2025 is the simulated-live source month. The other eleven months remain an
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

The full-day load forecast uses demand observations before the current replay
cursor, grouped by target hour, plus the target-hour weather outlook. It applies
temperature, humidity, and rainfall adjustments to that historical baseline.
Future June demand is never exposed as an actual value before its timestamp is
revealed. The chart distinguishes:

- forecast demand;
- historical hourly average;
- revealed simulated-live actual demand;
- per-hour uncertainty.

The complete archive is available for retrospective analytics, but records
after the cursor are excluded from forecast fitting to prevent future leakage.

## Playback

The dashboard has persistent Play, Pause, Step, and Reset controls. Step size is
configurable as one hour, six hours, or one day. Automatic playback supports one
simulated minute, ten simulated minutes, one simulated hour, or one simulated
day per real second.

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
