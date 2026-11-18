# B1-O state: the oracle, phase 1 (`tests/reference/`) — DONE

## Done
- Package `tests/reference/`: `model.py` (the description: E nodes, records, `Config`, units
  `q()`), and the code that runs it: `run.py`, `evaluate.py`, `network.py`, `order.py` (A2's
  select.py), `exact.py`, `poly.py`, `errors.py`. Imports nothing from napkin (scipy for LPs).
- Tests (127, ~4 s): test_flows 26, test_solvers 14, test_events 22, test_rounds 11,
  test_branches 14, test_values 13, test_limits 4, test_rulings 23 (each A2 ruling, as settled).
  `NAPKIN_STORE=off .venv/bin/python -m pytest -q -p no:cacheprovider tests/reference tests/core -n 2`
  gives 522 passed. ruff check and format are clean.

## Decisions (and why)
- A2's `Rules` switches removed: G0 settled every ruling, an alternative would be dead code.
  Tests of an alternative became tests of the rule (disposal = a declared flow to SINK).
- Local sharing: claims settle level by level in the direction of supply ("upstream supply
  first", as today's engine tests say): level = supply depth of the claim's source stores
  (0 with stock; 1 + deepest feeder at the lower bound). Same level: the fair-sharing rank. A
  declared solver puts all its claims on one level. Room passed upstream through two full stores
  (not [0,0] junctions) is NotCovered; a ring of empty stores is NotCovered.
- Units: canonical numbers (L, h, g, W, Wh, person; year 8760 h as in the prelude). `q()` in,
  `read(unit=)` out; every flow scale in the distance step is 1. No dimension checking.
- D5 applies to every computed result (local rates too), in stages, guards and setup. Inputs
  include cells read by the assembly, flows joining/leaving, and a store meeting a bound by
  moving at that moment. A result never settled is an error.
- D4: a field without a value is unset; a read fails. A capacity left out sets no limit and has no
  value to read; a request left out reads 0.
- D1: in a switch an outcome is eligible unless its case's guard is false; none eligible: `else`,
  no draw. Eligible outcomes with zero total probability: error in both modes.
- Prompt: `Config.controllers` names actors a person controls; answers by decision key or actor
  id. Resume reruns the paused stage on the unchanged state with its kept draws (draws, decisions,
  starts, moves recorded once); equals a replay. A person's choice outside a stage: NotCovered.
- D7: formulas (and flow-setting formulas) freeze before the occurrence's flows leave; a failure
  is stored as `Failed(reason)`. Writes to a finished occurrence fail.

## Remaining
- Phase 2 (later message): read the programs of `tests/program/` instead of `model.py` records.
- Rows only partly covered: `48 h/2` vs `48 h / 2` (no parser: one expression; value checked);
  `6 person * year` (number checked, dimension is the compiler's).
