# Balanced-throughflow capacity contact

Pinned revision 54284bd311158175d5c707e01da1a229e89a2393; tests/engine/test_declared_stock_faces.py on macOS: 1 failure, 5 passes.

| Integration | Ledger perturbation (ULPs) | Run | Last stock L | Old assertion | Physical invariant |
| --- | ---: | --- | ---: | --- | --- |
| held | 0 | direct | 9.3644688644688565e-18 | fail | pass |
| held | 0 | resumed | 9.3644688644688565e-18 | fail | pass |
| held | 0 | restored | 9.3644688644688565e-18 | fail | pass |
| held | -2 | direct | 0 | pass | pass |
| held | -2 | resumed | 0 | pass | pass |
| held | -2 | restored | 0 | pass | pass |
| held | 2 | direct | 2.686446886446887e-17 | fail | pass |
| held | 2 | resumed | 2.686446886446887e-17 | fail | pass |
| held | 2 | restored | 2.686446886446887e-17 | fail | pass |
| moving | 0 | direct | 0 | pass | pass |
| moving | 0 | resumed | 0 | pass | pass |
| moving | 0 | restored | 0 | pass | pass |
| moving | -2 | direct | 0 | pass | pass |
| moving | -2 | resumed | 0 | pass | pass |
| moving | -2 | restored | 0 | pass | pass |
| moving | 2 | direct | 0 | pass | pass |
| moving | 2 | resumed | 0 | pass | pass |
| moving | 2 | restored | 0 | pass | pass |

For seed 875, the exact depletion clock is 14471/4550 h. At the held solver’s located time 3.1804395604395603 h, the outlet already carries its full 1 L/h. The remaining 9.364468864468856e-18 L is inside the stock’s 1e-9 L band. Bringing the ledger to exactly zero would add that amount through the capped outlet. Settlement names the outlet and retains its actual balance. Running with a two-ULP downward probe reaches zero with no refusal for this stock. The oracle reads agree to 1e-10 across all 18 controls.

The only incorrect observation is the test’s unconditional equality to zero for held integration. Apply the same physical and diagnostic assertions to both integration modes. Preserve the uninterrupted, resumed and file-restored trajectory evidence.
