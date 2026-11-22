## S3 switch-side baseline

On macOS, all 1,200 cases ran against clean engine and reference sources at `9c8188b1a3d67743a2962936a1a65ad99fc23841`. The [complete ledger](baseline.jsonl.gz) records every case ID, generator digest, outcome, and unsuccessful assertion or traceback. Each family used seeds 0–299. The regular tier continues to rotate one transformation for each of 300 seeds.

| Family | Passed | Failed |
| --- | ---: | ---: |
| Component | 152 | 148 |
| Sparse | 157 | 143 |
| MovingDeclared | 161 | 139 |
| Clock, trigger and keyed selection | 0 | 300 |
| Total | 470 | 730 |

All three methods passed the genuine physical crossing and immediate departure controls. Across the other trajectories, failures were wrong delivered volumes, wrong rates, or exhausted integration budgets. Each method failed all 48 cases of exiting a wide comparison band without crossing physical zero. Synthetic input and exact integral are defined in [the trajectory generator](../../../../../tests/engine/switch_side_cases.py).

Every selection seed compared both interpreters with a hand calculation on three paths and two trajectories. Both interpreters chose the wrong ranked member in all 300 ties. The reference also chose the wrong strict clock branch in all 300 ties, and the engine did so in four. All 300 genuine exits and both inclusive-trigger controls per seed passed. The [selection generator](../../../../../tests/engine/switch_selection_cases.py) records each mismatched observation independently.

[Reference reduction](reference-clock-tie.scn) delivers 3/4 L in the reference and 0 L in the engine. [Second reduction](engine-clock-tie.scn) delivers 1/2 L in the reference and about 0.499999836 L in the engine. Both exact answers are zero because the operands stay inside the equality band throughout the hour.
