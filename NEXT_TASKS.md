# Next Tasks

## Recommended Order

1. Obtain historical CSV exports for all five required SCADA tags, with `Avg
   Value`, `Quality`, and overlapping timestamps.
2. Run the SCADA replay pipeline and review its preflight warnings, normalized
   snapshot coverage, baseline comparison, uncertainty, and risk-readiness
   report. Do not treat a short replay as production validation.
3. Configure an external supervised refresh schedule only after replay data is
   adequate and the active model has been reviewed by engineering.
4. Add a real grid provider only through a controlled historian/API/OPC-UA/CSV
   export integration. Keep `MockGridProvider` available for demo and testing.
5. Add operational observability before production: structured logs, import and
   refresh job monitoring, alert routing, backup/restore checks, and access
   control.
6. Expand model validation with multiple seasons, public holidays, outages,
   dispatch constraints, and more weather regimes before relying on ML output.

## Do Not Do Yet

- Do not label simulated grid data as live SCADA.
- Do not auto-train inside the FastAPI request process.
- Do not activate ML merely because it runs; it must beat chronological
  baselines and be reviewed with enough representative data.
- Do not import the calibration Excel archive as raw SCADA CSV telemetry.
