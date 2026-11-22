# Defensive attention and remediation

How quickly does a security team’s attention respond to changes in observed workload?

Aggregate defensive monitoring and remediation over 25 years.

Model revision `0d0a56e7d0539fea1b2f111135a0e12dcdd42837c7561c0476335bca7be3abea`. Readings are instantaneous, without reporting lags. All times are in hours.

## Default run

| Reading | Time (h) | Value | Unit | Evidence |
|---|---:|---|---|---|
| observations.pressure | 0 | 1 | ratio | observation |
| defenders.attention_target | 0 | 0.05 | ratio | attention_today, saturation, observation |
| defender_attention | 0 | 0.05 | ratio | attention_balance, attention_today, saturation, attention_fades, observation |
| defenders.hardening | 0 | 0 | ratio | hardening_basis, observation |
| defenders.closing | 0 | 1 | ratio | remediation_basis, observation |
| observations.pressure | 219000 | 1 | ratio | observation |
| defenders.attention_target | 219000 | 0.05 | ratio | attention_today, saturation, observation |
| defender_attention | 219000 | 0.05 | ratio | attention_balance, attention_today, saturation, attention_fades, observation |
| defenders.hardening | 219000 | 0 | ratio | hardening_basis, observation |
| defenders.closing | 219000 | 1 | ratio | remediation_basis, observation |

## Evidence

- **attention_balance** (identity). The rate drawing attention is the adjustment rate times the sustained level. The rate releasing attention is the same rate times current attention.
- **attention_fades** (assumption). The historical alertness_fades assumption sets the reference adjustment rate to two per year.
- **attention_today** (assumption). The historical model starts the attention index at 0.05. Its units are an index, not a share of staff.
- **hardening_basis** (assumption). The historical hardening and defender_ai assumptions add a yearly improvement and a gain proportional to measured uptake; both gains default to zero.
- **observation** (assumption). The caller supplies aggregate incident volume and defensive tooling uptake. A volume of one is the reference workload. The two observation boundaries are replay settings.
- **remediation_basis** (assumption). The historical rediscovery assumption lets discovery and patching rise with uptake of defensive tools; the reference pace is one.
- **saturation** (assumption). The historical attention_cap assumption sets today's workload to today's attention and limits the sustained level to six times today's by default.
