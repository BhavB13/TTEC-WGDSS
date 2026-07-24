# WGDSS Technical Handover

## Scope

This handover describes the implementation present in the repository on:

- Branch: `experiment/live-scada-snapshot`
- Commit inspected: `6d8ef48972022291962946a8bdba087edb91508a`
- Inspection date: 2026-07-23

It must be read with [HANDOVER_STATUS.md](HANDOVER_STATUS.md). That file records
the gaps that prevent a production or live-SCADA claim.

WGDSS is currently a read-only weather and grid decision-support
demonstration. The normal dashboard runs a June simulated-present/historical
replay. The branch also contains an isolated July static SCADA snapshot
experiment. Neither is a continuously updating T&TEC SCADA feed, and WGDSS has
no command path to generation equipment.

## Status Vocabulary

| Label | Meaning in this handover |
|---|---|
| **Implemented** | Code exists in the inspected repository. |
| **Simulated** | Deterministic demonstration or replay behavior, not live telemetry. |
| **Experimental** | Isolated branch functionality intended for engineering tests. |
| **Configured option** | Code/configuration supports an option, but deployment has not been proven. |
| **Planned** | Documentation or an interface anticipates the feature; implementation is absent. |
| **Requires confirmation** | T&TEC, OSI, control engineering, security, or infrastructure approval is required. |

## Document Set

| Document | Purpose |
|---|---|
| [SYSTEM_CONTEXT.md](SYSTEM_CONTEXT.md) | System purpose, operating boundaries, modes, and operator workflow. |
| [ARCHITECTURE.md](ARCHITECTURE.md) | Frontend, backend, provider, data-flow, and component architecture. |
| [DATA_AND_ANALYTICS.md](DATA_AND_ANALYTICS.md) | Weather, SCADA, June replay, July experiment, forecasting, preprocessing, and risk mathematics. |
| [API_AND_DATABASE.md](API_AND_DATABASE.md) | HTTP API, snapshot contract, database tables, and migration ownership. |
| [INSTALL_CONFIG_DEPLOY.md](INSTALL_CONFIG_DEPLOY.md) | Installation, environment variables, local launch, PostgreSQL migration, deployment, backup, and recovery templates. |
| [CONFIGURATION_REFERENCE.md](CONFIGURATION_REFERENCE.md) | Complete current environment-variable contract and defaults. |
| [OPERATIONS_RUNBOOK.md](OPERATIONS_RUNBOOK.md) | Operator and administrator workflows, troubleshooting, replay, imports, and recovery. |
| [SECURITY_AND_GOVERNANCE.md](SECURITY_AND_GOVERNANCE.md) | Current safeguards, authentication/TLS/secrets gaps, OT boundary, and governance. |
| [TESTING_AND_RELEASE.md](TESTING_AND_RELEASE.md) | Test strategy, CI, model validation, release, rollback, and acceptance gates. |
| [FILE_AND_COMPONENT_MAP.md](FILE_AND_COMPONENT_MAP.md) | System-to-file ownership map for maintainers. |
| [HANDOVER_STATUS.md](HANDOVER_STATUS.md) | Completed work, gaps, suggested owners, next actions, and handoff checklists. |

## Source Precedence

When documents disagree, use this order:

1. Current code and migrations.
2. `CURRENT_STATUS.md` for dated validation results.
3. `RUNBOOK.md` for current local commands.
4. `docs/SCADA_OSI_CONTEXT.md` for SCADA/OSI constraints and source semantics.
5. This handover.
6. Older design documents.

Older files may describe intended architecture or superseded terminology. In
particular, the repository contains no XGBoost dependency or implementation,
no production historian connector, and no frozen fitted model artifact for the
July experiment.

## Quick Local Start

From the repository root in Windows PowerShell:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\scripts\Start-WGDSS.ps1
```

Then open:

- Dashboard: `http://localhost:5173`
- API documentation: `http://localhost:8000/docs`
- Health: `http://localhost:8000/api/v1/health`

This launcher starts development servers. It is not a production deployment.
