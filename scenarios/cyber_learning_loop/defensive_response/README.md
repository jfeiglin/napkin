# Defensive attention and remediation

This standalone entry follows a security team's response to aggregate observed incident volume. A volume of 1 represents its reference period. A workload surge raises the attention level the team can sustain. Actual attention approaches that level over time and recovers when volume falls. The horizon is 25 years.

```sh
python -m napkin run scenarios/cyber_learning_loop/defensive_response --value observations.pressure,defender_attention,defenders.hardening,defenders.closing --at 0h,1year,2years,25years
```

The reference run holds workload at 1 and attention at 0.05. Use the three inputs `observations.initial`, `during` and `later` on the `observations` entity to replay a change in volume. `observations.change_at` and `duration` give the start and length of the middle period in years. `observations.uptake` holds the supplied fraction of defensive tooling adoption for the run. Inputs and their ranges are declared in the model. [Model](model.scn) · [Selected readings](brief.toml)

## Historical coverage

| Retained quantity | Meaning |
|---|---|
| `observations.pressure` | External input at the boundary formerly named `defenders.threat`, normalized to the same reference period |
| `defenders.attention_target` | Saturating response to observed workload, with the historical baseline level and cap |
| `defenders.alertness`, also reported as `defender_attention` | Balance of the flows drawing and releasing attention at the historical adjustment rate |
| `defenders.hardening` | Index summing a yearly improvement and the contribution from measured defensive tooling adoption |
| `defenders.closing` | Multiplier for discovery and remediation pace given defensive tooling adoption |

The historical model generated workload, assigned staff across missions and used their results to change later decisions. This entry takes workload and uptake as observations and stops at the defensive readings above. The historical staffing, assessment, mission outcomes and doctrine are outside its scope. Its calibrated attention index and multiplier are model assumptions. The historical package retains the evidence and published results for the larger model. [Original defensive declarations](https://github.com/jfeiglin/napkin/blob/8488047/scenarios/cyber_learning_loop/model.scn#L530-L602) · [Historical package](../README.md)

## Verification

The historical interpreter at `8488047` evaluated the retained declarations in isolation under the same supplied observations. Four replays cover reference, zero, sustained elevated and pulsed workloads. Five quantities sampled at ten times give **200 matched readings**. The largest absolute difference was **5.09 × 10⁻¹¹** in the attention index. Both interpreters finished at 219,000 h with a seven-day maximum step. The replay receipt records the full legacy commit, source and extracted fixture hashes, inputs, times and values. [Historical readings](tests/legacy-readings.json) · [Reproduction script](../../../scratch/rewrite/a5/compare_defensive_response.py)

In the pulse replay, volume is 1 for the first year, 5 for the next year and 0.5 afterward. With an adjustment rate of three per year, attention is 0.05 at year 1, 0.145021293 at year 2 and 0.033135083 at year 3. A separate closed-form check tests the transitions and recovery at seven-day and one-day maximum steps. [Regression tests](tests/test_observations.py)

```sh
python -m pytest -q scenarios/cyber_learning_loop/defensive_response/tests/test_observations.py
python scratch/rewrite/a5/compare_defensive_response.py /path/to/napkin-at-8488047
```
