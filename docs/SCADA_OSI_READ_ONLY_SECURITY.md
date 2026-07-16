# SCADA and OSI Read-Only Security Boundary

## Scope

WGDSS is decision-support software. It may ingest approved historical exports
or, in a future production phase, read approved telemetry through a utility
controlled interface. It must not issue commands, setpoints, acknowledgements,
switching actions, or writes to AspenTech OSI, SCADA, EMS, GMS, or plant
systems.

No production AspenTech OSI endpoint, protocol, credential, certificate,
network path, or account has been supplied or implemented. Provider selections
for `scada` and `historian` therefore fail closed.

## Required Production Controls

These are integration requirements, not claims about T&TEC's current network:

- T&TEC/OSI owners must approve the source interface, network zone, data tags,
  units, quality mapping, scan/export rates, stale limits, and failover policy.
- Prefer an approved replicated historian, export service, or other read-only
  boundary rather than direct control-system access.
- Use a dedicated least-privilege read identity. It must have no write,
  command, acknowledgement, or configuration permission.
- Terminate and protect credentials outside source control. Load secrets from
  the approved deployment secret store or runtime environment.
- Restrict network routes and allowlists to the approved source and consumer.
  Do not expose OT services to the public internet.
- Validate server identity and certificate trust according to T&TEC policy.
  Do not disable TLS verification to make an integration work.
- Log connector health, authentication events, import hashes, source age,
  quality, completeness, and failures without logging secrets.
- Keep replay, simulation, and live read-only data stores and labels distinct.
- Fail to `DATA UNAVAILABLE` or the approved degraded state when telemetry is
  stale, incomplete, contradictory, or unavailable. Never fabricate live
  values from replay or mock data.
- Security review, backup/restore testing, patching, monitoring, incident
  response, and rollback ownership must be approved before deployment.

## Secrets and Repository Hygiene

- Keep `.env` files and private keys out of Git.
- Commit only `.env.example` placeholders.
- Rotate any credential that is accidentally committed or displayed.
- Do not place credentials in URLs, browser code, logs, screenshots, fixtures,
  or import provenance.
- OpenWeather browser overlay keys are unrelated to SCADA credentials and must
  never be reused for operational systems.

## Required T&TEC / OSI Decisions

Before a production connector is implemented, complete
`docs/SCADA_OSI_CONFIRMATION_REGISTER.md`, including interface type, product
and version, endpoint ownership, certificate/authentication model, network
zone, exact tag metadata, quality meanings, stale limits, audit retention,
high-availability behavior, and named approvers.
