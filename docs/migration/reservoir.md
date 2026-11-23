# Reservoir package migration

The checker compared the shipped `examples/reservoir/model.scn` with the same path at legacy commit `8488047dbb7eafee1f5582cf59839c6bea0cf8cd`. It matched the model's 22 authored numbers, 26 texts, 14 names, three flows and two cumulative outputs. Both default runs finished at 120 h. The observation times were 0, 24, 40, 60, 80, 96 and 120 h. [Shipped model](../../../examples/reservoir/model.scn) · [Migration checker](../a5/check.py)

Separate processes ran both versions with storm inflow of 0.03 or 0.06 fraction/day, spillway discharge of 0.06 or 0.15 fraction/day and a risk threshold of 0.6, 0.7 or 0.8 fraction. At each time the comparison checked water, cumulative spill and hours at risk, for 252 paired readings. Another 21 readings cover the operator choosing WAIT with the default inputs. The largest differences were 3.331 × 10⁻¹⁶ fraction of water, 7.216 × 10⁻¹⁶ fraction spilled and 5.544 × 10⁻⁸ hours at risk. All 273 readings met the established tolerance, the larger of 10⁻⁸ in the stated unit and 10⁻⁶ times the magnitude of the legacy value. [Exact input settings and paired readings](reservoir-package-migration.csv.gz)

On the default public CLI run, the gate opened at 40 h with water at 0.7 fraction. It ended with 0.4 fraction of water, 0.5 fraction spilled and zero hours at risk. The public play command stopped at 40 h before the operator's switch. Choosing WAIT ended with 0.9 fraction of water, zero spill and 40 hours at risk. The example tests also check the physical balances and analytical risk duration at each observation for all twelve configurations and two additional storm/operator settings. [CLI commands](../../../examples/reservoir/README.md) · [Example tests](../../../tests/test_examples.py)

With `NAPKIN_BASE` set to the absolute path of a worktree at the legacy commit, run these commands from the candidate checkout.

```sh
PYTHONPATH=. python scratch/rewrite/a5/check.py "$NAPKIN_BASE/examples/reservoir/model.scn" \
    examples/reservoir/model.scn --at 24 --at 40 --at 60 --at 80 --at 96
python -m pytest -q --no-focused tests/test_examples.py
```
