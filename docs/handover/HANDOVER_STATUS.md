# WGDSS Handover Status

## Handover Baseline

| Item | Value |
|---|---|
| Repository branch inspected | `experiment/live-scada-snapshot` |
| Source commit inspected | `6d8ef48972022291962946a8bdba087edb91508a` |
| Stable pre-experiment tag | `pre-scada-baseline` |
| Current Alembic head | `4e1f2a3b5c84` |
| Handover generated | 2026-07-23 |
| Production readiness | **Not production ready** |
| Live SCADA status | **Not implemented** |
| SCADA command capability | **None; read-only decision support** |

Owners below are proposed accountable roles. They are unassigned until T&TEC
names and approves individuals or teams.

## Completed in the Repository

| Area | Evidence/status |
|---|---|
| React/Vite control-room dashboard | Implemented with typed snapshot integration |
| FastAPI service and OpenAPI | Implemented |
| Provider architecture | Weather and grid abstractions implemented |
| Weather ensemble/fallback | Open-Meteo, MET Norway, GFS cross-check; optional WeatherAPI |
| Weighted T&T weather | Implemented, policy unconfirmed |
| NASA/NHC/Leaflet map | Implemented external visualization |
| June replay | Persistent simulated-present and previous-day selection |
| SCADA historical import | Raw/provenance/quality/dedup/anomaly handling |
| Irregular time alignment | Duration-weighted interval overlap and reconciliation |
| Forecast dataset | 1h-6h leakage-gated feature rows |
| Forecast model evaluation | Baselines plus scikit-learn candidates and chronological gate |
| Generation-need probability | Normal residual approximation against current TRA and reserve target |
| Capacity what-if | Advisory aggregate start blocks, current-TRA anchored |
| July static experiment | Isolated immutable source/session path |
| SQL schema/migrations | SQLAlchemy models and single Alembic chain |
| CI | Backend/frontend tests and SQLite migration check |
| Local launch | PowerShell launcher and manual commands |
| Technical handover | `docs/handover/` document set |

## Handover Validation

The following checks were run from the current worktree on 2026-07-23:

| Check | Result |
|---|---|
| Backend pytest | `179 passed in 100.23s` |
| Alembic schema check | `No new upgrade operations detected` |
| Frontend Vitest | `4` files, `12` tests passed |
| Frontend TypeScript/Vite build | Passed |
| Local Markdown links in `docs/handover/` | All resolved |

No PostgreSQL instance, external provider live response, production deployment,
or live SCADA/OSI connection was exercised by these checks.

## Open Gaps and Owners

| Gap | Status | Proposed owner | Next action |
|---|---|---|---|
| Official five-tag semantics/units | Requires confirmation | T&TEC Control Engineering + OSI owner | Complete confirmation register |
| `Other`/`Questionable` quality policy | Requires confirmation | OSI owner + Data/ML owner | Approve mapping and model weights/exclusions |
| Twelve-plus months approved history | Missing | Data/OSI owner | Export matching tags across seasons/events |
| Genuine issued weather forecast archive | Missing | Data/Weather owner | Obtain issuance-timestamped archive or retain degraded label |
| Production reserve target/status bands | Unconfirmed | Control Engineering | Approve policy and contingencies |
| Generation block roster and constraints | Unconfirmed | Generation Operations | Approve MW, count, lead/ramp/outage constraints |
| Shutdown planning rules | Not implemented | Generation Operations | Define minimum run/down, ramps, lead, verification |
| Read-only OSI/historian connector | Not implemented | OT/OSI Integration | Select approved interface and boundary |
| Frozen fitted model artifact | Missing | ML owner | Implement reproducible packaging/signing/release |
| Model registry/approval workflow | Missing | ML Governance | Select registry and approval record |
| PostgreSQL deployment/data migration | Unverified | Database/Infrastructure | Build/test non-production PostgreSQL migration |
| Authentication/RBAC | Not implemented | Identity/Security + App team | Approve identity integration and enforce roles |
| TLS/reverse proxy | Not implemented | Infrastructure/Security | Approve DNS/PKI and deploy TLS |
| Secrets manager | Not implemented | Security/Infrastructure | Select runtime secret mechanism |
| Tracked empty `backend/.env` | Hygiene gap | Repository owner | Scan history, remove tracked file, rotate if needed |
| Central logging/metrics/alerts | Not implemented | Operations/SRE | Define stack, SLOs, routing, retention |
| Backup/restore automation | Not implemented | Database/Infrastructure | Set RPO/RTO, implement and test restores |
| Multi-worker capacity context | In-process only | Backend team | Move to shared expiring store |
| Production packaging | Not implemented | Platform team | Add reviewed frontend/API/container/service assets |
| End-to-end/accessibility/security tests | Missing | QA/Security | Add browser and security gates |
| Operator UAT and training | Not completed | Control Engineering | Approve terminology, workflow, and fail-safe states |

## Priority Next Actions

1. Complete the SCADA/OSI confirmation register.
2. Obtain representative approved history and genuine forecast issuance data.
3. Reproduce the full import/train/validate pipeline from hashes.
4. Package a frozen model artifact with exact features, preprocessing, periods,
   metrics, code commit, and hash.
5. Select and approve the read-only OT/IT integration pattern.
6. Implement authentication, TLS, secrets, PostgreSQL, backup, and monitoring
   in a non-production environment.
7. Run shadow-mode live-read testing with no command path.
8. Evaluate predictions against later actuals and calibrate generation need.
9. Complete operator UAT and security/production readiness review.

## Repository Handoff Checklist

- [ ] Repository location and access approved.
- [ ] Default branch and branch protections confirmed.
- [ ] `pre-scada-baseline` tag verified and protected.
- [ ] Experimental branch disposition agreed.
- [ ] Working tree clean at handoff.
- [ ] Full Git history and large/source data ownership understood.
- [ ] Empty tracked `backend/.env` history scanned and corrected.
- [ ] No credentials, private source archives, databases, logs, or experiment
      sessions tracked.
- [ ] README/status/runbook/handover reviewed by maintainers.
- [ ] CI required on protected branches/PRs.
- [ ] Dependency update and vulnerability process assigned.
- [ ] Release/tag/changelog convention approved.

## Model Handoff Checklist

- [ ] Target definition (`PTL132` demand proxy) approved.
- [ ] Engineering units and quality mapping approved.
- [ ] Training source hashes recorded.
- [ ] October-May feature and target cutoff proven.
- [ ] June and July excluded from training, preprocessing, tuning, and model
      selection.
- [ ] Exact ordered feature contract recorded.
- [ ] Fill/clipping/temperature/calendar preprocessing frozen.
- [ ] Candidate/baseline comparison and chronological holdout reproduced.
- [ ] Per-horizon metrics and residual intervals approved.
- [ ] Frozen fitted artifact created.
- [ ] Artifact schema, model version, feature profile, commit, dependency set,
      and SHA-256 recorded.
- [ ] Artifact load and inference-only test passes.
- [ ] Drift, recalibration, retraining, approval, and rollback policy assigned.
- [ ] Later actuals available for June/July forecast evaluation.

## Deployment Handoff Checklist

- [ ] Target environments and network zones approved.
- [ ] PostgreSQL provisioned and restore tested.
- [ ] Alembic migration tested on target-like data.
- [ ] Authentication and server-side RBAC implemented.
- [ ] TLS, DNS, certificates, and renewal assigned.
- [ ] Secrets supplied only through approved runtime store.
- [ ] Explicit CORS origins configured.
- [ ] Backend/frontend production packaging implemented.
- [ ] Central logs, metrics, health, alerts, and on-call routing implemented.
- [ ] Backup retention, encryption, RPO/RTO, and restore drill approved.
- [ ] Read-only OSI/historian source and least-privilege identity approved.
- [ ] Failure/stale/missing-data behavior tested.
- [ ] Load, security, browser, and operator acceptance tests pass.
- [ ] Deployment manifest records commit, migration, environment, and model hash.
- [ ] Rollback application and matching database backup are available.
- [ ] `ADVISORY ONLY` and no-control boundary approved in UI/operator procedures.

## Known Limitations

- Current normal operation is a June replay, not a live source.
- The July package is a fixed snapshot and lacks TA.
- A fixed snapshot cannot establish forecast accuracy without later actuals.
- No frozen fitted artifact exists for July inference.
- Weather/map providers are external and can degrade independently.
- Available historical coverage is not sufficient for production seasonality,
  outage, holiday, or extreme-weather assurance.
- Probability assumes a normal residual approximation; calibration is
  prototype.
- Reserve and generation block policies are unconfirmed.
- Local state/cache behavior is not designed for multiple API workers.
- Authentication, TLS, PostgreSQL operations, production deployment, backup,
  and monitoring are incomplete.

## Acceptance Sign-Off Template

```text
Repository owner:
Application owner:
Control Engineering owner:
OSI/data owner:
ML owner:
Database/platform owner:
Security owner:
Operations/support owner:

Reviewed commit:
Alembic revision:
Model artifact hash:
Deployment artifact/image:
Database backup reference:
Open risks accepted:
Date:
```

Blank fields are intentional. This repository does not provide or infer named
owners, credentials, server details, OSI endpoints, or production approval.
