# Historical Data Import Extension Guide

## Entry Point

All new historical files should enter through:

```powershell
cd backend
venv\Scripts\python.exe scripts\import_historical_dataset.py PATH_TO_DATASET
```

The command uses `HistoricalDataImportService`, which selects a registered
adapter, validates before persistence, records a SHA-256 source identity, maps
source fields to canonical WGDSS fields, and returns required downstream steps.

Current adapters:

- `scada_csv_v1`: raw SCADA interval CSV exports;
- `calibration_archive_v1`: the existing XLSX calibration ZIP.

## Adding A Dataset

1. Preserve the original file unchanged outside generated application output.
2. Document its owner, timezone, units, quality codes, interval, and date range.
3. Implement `HistoricalDatasetAdapter` with `can_handle`, `validate`, and
   `import_dataset` methods.
4. Map source columns to canonical timestamps, MW, degrees Celsius, percent,
   mm/hour, km/hour, hPa, and quality values.
5. Reject missing required fields, invalid timestamps, non-finite numbers, and
   impossible ranges before database mutation.
6. Deduplicate by SHA-256 content hash; never rely only on a filename.
7. Align SCADA and weather by timestamp and timezone, never row number.
8. Add adapter tests covering valid data, malformed data, duplicate data, and
   quality preservation.
9. Rebuild normalized snapshots and chronological forecast rows.
10. Retrain only through the supervised refresh path. Activate a model only if
    it beats the chronological baseline and passes uncertainty/risk checks.

## Adapter Contract

An import returns `HistoricalImportReport` with adapter and filename, SHA-256
provenance, imported/duplicate state, accepted row count, validation status,
schema mapping, warnings, and recalibration or retraining actions.

Registration is intentionally open: tests demonstrate a future adapter can be
added without changing either existing importer.

## Safety Rules

- Historical exports are not a live SCADA stream.
- Preserve source quality and exclude bad/inactive rows from model training.
- Do not use records created after a feature timestamp to train that forecast.
- Use chronological validation only.
- Keep replay, historical analysis, and live-provider tables separate.
- Review model and dispatch changes with Control Engineering before production.

