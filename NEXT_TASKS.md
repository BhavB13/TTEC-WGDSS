# Next Tasks

## Recommended Order

1. Obtain at least twelve months of exports for the same five tags, including
   seasonal demand, holidays, outages, maintenance, and dispatch changes.
2. Have SCADA/control engineering define the operational meaning of `Other`,
   `Questionable`, and any future quality codes before changing quality gates.
3. Obtain archived weather forecast runs with genuine issuance timestamps if
   available; until then retain the explicitly degraded past-observation
   weather baseline.
4. Obtain an engineering-approved Trinidad and Tobago holiday/event calendar,
   including Divali, Eid, one-off public holidays, major industrial shutdowns,
   and system events. Supply approved variable dates through
   `FORECAST_EXTRA_HOLIDAY_DATES` until a maintained calendar feed exists.
5. Re-run the ZIP replay pipeline, compare every horizon to chronological
   baselines, inspect residual calibration by horizon/regime, and require an
   engineering model-approval record before promoting `PROTOTYPE` results.
6. Configure an external supervised refresh schedule only after replay data is
   adequate and the active model has been reviewed by engineering.
7. Add a real grid provider only through a controlled historian/API/OPC-UA/CSV
   export integration. Keep `MockGridProvider` available for demo and testing.
8. Add operational observability before production: structured logs, import and
   refresh job monitoring, alert routing, backup/restore checks, and access
   control.
9. Complete `docs/SCADA_OSI_CONFIRMATION_REGISTER.md` with T&TEC control
   engineering and the OSI system owner before changing tag semantics, units,
   quality gates, reserve policy, start recommendations, or provider settings.
10. Select a production read-only integration pattern and complete the controls
    in `docs/SCADA_OSI_READ_ONLY_SECURITY.md`; do not implement a connector
    until its interface and OT boundary are approved.

## Do Not Do Yet

- Do not label simulated grid data as live SCADA.
- Do not auto-train inside the FastAPI request process.
- Do not activate ML merely because it runs; it must beat chronological
  baselines and be reviewed with enough representative data.
- Do not treat the June historical exports as a live feed or a production model.
- Do not substitute future actual weather, TA, TRA, Spin, or demand for data
  that would have been known at forecast issuance time.
