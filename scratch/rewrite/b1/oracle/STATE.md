# B1-O state: the oracle, phase 1 (`tests/reference/`) — DONE

## Done
- Package `tests/reference/`: `model.py` (the description: E nodes, records, `Config`, units
  `q()`), and the code that runs it: `run.py`, `evaluate.py`, `network.py`, `order.py` (A2's
  select.py), `exact.py`, `poly.py`, `errors.py`. Imports nothing from napkin (scipy for LPs).
- Tests, one file per topic (flows, solvers, events, rounds, branches, values, limits, rulings:
  each A2 ruling as settled). Run them with
  `NAPKIN_STORE=off .venv/bin/python -m pytest -q -p no:cacheprovider -n 2 tests/reference`.

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

## Phase 2 — DONE
- `from_program.py`: Program and Configuration -> the oracle's Model and Config (reads records,
  walks `napkin.core.expr` nodes as data; no napkin evaluation code). `value_at` reads a record
  Key in its declared unit; `traced` maps record kinds (commit, finish, ...) to oracle entries.
- `test_programs.py`: all 65 examples of `tests/program/examples.py` pass, no xfail, no edit to
  examples.py. tests/reference 192 passed (~5.5 s); with tests/program and tests/core: 1008.
- Oracle changes for it (no semantic rule changed): occurrences numbered from 0 (`#0`, as record
  keys); trace entries carry round and origin, with draws, choices (at commit) and moves; a stage
  whose guard is false is 'skip', not a commit; the retirement message states its unit ("8 L");
  a read of a stopped run at its stop time gives the committed state; new read nodes (member by
  id, n-th occurrence, `where` with an item); Model keeps the program's units and sites.

## Fixes after the join — DONE (tests/reference 204 passed; the engine's 3 comparison files 626)
- `delayed(x, D)` reads D before the time of the state read (`ev.view.t`, D = 0 too): a formula
  read after the run at 5 h reads 3 h. OPEN, not chosen: before the start it reads the record at
  0 h, which the first moment lacks, so a trigger on `delayed` fails at the setup; the spec
  ("documented domains"), R-A2-09 (D = 0) and G0 do not say what such a read gives.
- R-A2-17: a firing owns the draws of its captures, body and `reset after` (`key!n`, n from 1, as
  the engine spells it); the setup's belong to the root `''` (was 'model').
- Categorical weights: nonnegative, scaled by their sum. All zero stay zero: a draw fails in both
  modes (as eligible outcomes of total zero); a person may still pick.
- An occurrence's store has endpoint settings as a member's (`Run._endpoints`): plain ones in
  written order (D14, `_forward`), frozen at the finish (D7, `_holder`). 12 new tests.

## Remaining
- Rows only partly covered: `48 h/2` vs `48 h / 2` (no parser: one expression; value checked);
  `6 person * year` (number checked, dimension is the compiler's).
