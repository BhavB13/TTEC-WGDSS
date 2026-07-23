# July 23 Static SCADA Snapshot Test

## Result

- Source: `20260723.zip`
- SHA-256: `1c4802aedbda50848bf3a3f0c4b3b3c6ad52dc083891cabd7b091ebbc22cf8f7`
- Available range: July 23, 2026 00:00-11:30 AST
- Common valid boundary: July 23, 2026 11:30 AST
- Raw / accepted records: 2,486 / 2,486
- Duplicate, malformed, future, or impossible records: 0
- Latest demand: 1,274.98 MW
- Latest TRA: 1,408.6 MW
- Latest corrected spin: 72.76 MW
- Latest SCADA ambient temperature: 32.7 C
- Missing required variable: available generation capacity / TA
- Weather snapshot: 48 post-boundary hourly periods from the configured
  Open-Meteo/MET Norway ensemble; the exact response and hash are stored in the
  generated session.
- Registered model version: `demand-forecast-v5.0` (metadata only)
- Model status: `NO_FROZEN_MODEL_ARTIFACT`
- Training/preprocessing changes: none

The supplied interval records align cleanly using timestamp overlap rather than
row number or nearest-row matching. The source archive is hashed before and
after parsing and is never modified.

## Limitation

A static snapshot can test parsing, input construction, model behavior, and
risk plumbing. It cannot establish forecast accuracy until later actual SCADA
values are supplied for an out-of-sample comparison. Generation-need
probability remains unavailable when a validated frozen model artifact and
uncertainty estimate are unavailable.
