# Recommendation Rules

## Decision-Support Boundary

WGDSS is read-only decision support. A recommendation is evidence for a Control
Engineer, not an automatic start command. All policy values below are
configurable and `PROTOTYPE_UNCONFIRMED` until T&TEC confirms them.

## Decision Matrix

| Probability | Default recommendation | Interpretation |
|---|---|---|
| Below 0.30 | `NO ACTION REQUIRED` | Reserve-adjusted shortfall is unlikely under the forecast distribution. |
| 0.30 through 0.65 | `MONITOR CONDITIONS` | The forecast or its uncertainty materially approaches the reserve boundary. |
| Above 0.65 | Capacity and lead-time evaluation | A reserve-adjusted shortfall is more likely than the configured high-risk threshold. |

For HIGH risk, the engine also checks conservative shortfall, verified startable
TA headroom, and time to the selected forecast horizon:

| Conservative shortfall and timing | Prototype guidance |
|---|---|
| Up to 15 MW, inside 20 minutes | Start one available 15 MW fast-start unit. |
| Above 15 MW through 30 MW, inside 20 minutes | Start both available 15 MW fast-start units. |
| Up to 30 MW, outside 20 minutes | Monitor the small-unit start window. |
| Above 30 MW, inside 60 minutes | Start a verified 60-120 MW heavy unit block. |
| Above 30 MW, outside 60 minutes | Monitor the heavy-unit start window. |
| Required block is not verified in TA | Escalate capacity availability; do not claim an unavailable start. |

## Structured Evidence

The result keeps these concepts separate:

- `probability_score`: statistical chance of crossing safe online capacity;
- `severity_level`: MW scale of the conservative shortfall;
- `decision_confidence`: forecast/data confidence, not event probability;
- `urgency`: whether startup lead time is available or action is due;
- `expected_shortfall_mw`: probability-weighted positive deficit;
- `projected_shortfall_mw`: confidence-upper-bound deficit;
- `drivers`: increasing, reducing, context, and quality factors.

The UI shows the top structured drivers and makes the complete list available.
It must not show contradictory statements such as both “mean exceeds capacity”
and “mean remains below capacity” for the same selected horizon.

## Inputs That Do Not Add Arbitrary Points

Temperature, humidity, rainfall, cloud cover, and wind influence the load model
and its uncertainty. They do not add fixed increments to the probability.
Likewise, reserve margin, outages, and derates affect capacity evidence rather
than adding arbitrary score weights.

## Required Confirmation

Before operational use, T&TEC/OSI owners must confirm:

- source tag semantics and engineering units;
- whether `PTL132 GENERATION TOTALS` is an acceptable demand target;
- corrected-spin calculation and response eligibility;
- reserve requirement and risk thresholds;
- unit availability, block sizes, ramp/start times, outages, and derates; and
- approved read-only historian/provider interface and quality-code mapping.

The confirmation register is `SCADA_OSI_CONFIRMATION_REGISTER.md`.
