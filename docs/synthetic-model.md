# Synthetic model specification v1

This original demonstration model is authorized by the project request. It has **not**
been reviewed by an equipment engineer. All diagnostic rules use `synthetic_demo`.
No real station measurements or restricted product information were used.

## Conditions common to every rule

One fault is active at a time. The nominal stimulus is a constant 5 V DC across an
opaque external load. The station is at a stable voltage-verification step. Check
outcomes describe an unchanged state. A missing observation does not mean normal.
Manual observations are reports, not verified facts. No numerical confidence is used.

## Modeled mechanisms

| Fault | Required condition | Intermediate condition | Symptom |
|---|---|---|---|
| F_SUPPLY | Output disabled, or setpoint zero, in this model | No modeled stimulus | Near-zero reading |
| F_ROUTE | Measurement route selects the synthetic grounded spare channel | Wrong measurement point | Near-zero reading |
| F_LEAD | Measurement lead open or misconnected; synthetic input bias is defined to pull the reading to zero | Invalid measurement path | Near-zero reading |
| F_DMM | AC mode selected for the steady DC stimulus; this idealized model ignores transients and noise | DC quantity rejected by modeled mode | Near-zero reading |
| F_RESOURCE | Resource name does not resolve in the synthetic resource table | No fresh instrument response | Timeout / no reading |
| F_SEQUENCE | Sequence expects the loaded 5 V profile but runs the zero-stimulus step | Wrong active step | Near-zero reading |

An open circuit does **not** universally read zero on a real meter. The imposed bias,
grounded spare route and ideal AC/DC behavior are synthetic assumptions solely for
demonstrating ambiguity. Communication failure returns missing data, never a fabricated
zero. Incorrect supply configurations other than zero setpoint are not modeled.

## Checks and observations

Checks inspect synthetic state or record a user's categorical report: output/setpoint,
selected route, lead path, measurement mode, resource response and sequence revision.
Their expected outcomes are stored in `data/runtime/graph.json`. The simulator's
independent state mapping is in `data/simulator/station.json`. No check operates hardware.
Outcomes are `normal`, an explicit abnormal state, or `unknown`. Two different known
outcomes for one check cause abstention. Two abnormal checks also cause abstention
when no single modeled fault explains both.

## Evidence status

`SRC_MODEL` covers the original mechanism definitions and conditional paths.
`SRC_CHECKS` covers the original logical check predictions.
`SRC_REFERENCE` covers one designated development example. It is not historical data.
All await engineering review. Public source candidates are quarantined separately.

