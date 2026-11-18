# A2 state (reference semantics). Updated at each milestone.

## Done, by file (all under scratch/rewrite/a2/)
- `ref/model.py`: the description only. `E` expression nodes with operators, statements, `Field`, `Flow`,
  `Event` (`After`, `Until`, `Trigger`), `Solver`, `Template`, `Instance`, `Model`, `Config`, and `Rules`
  (one switch for each ruling: default = proposed rule, other value = the alternative).
- `ref/poly.py`: polynomials in time, exact; first root after 0 (degree <= 2, rational roots only).
- `ref/exact.py`: fraction linear algebra, least squares on an affine set, simplest fraction in an interval.
- `ref/select.py`: the selection order. TESTED by hand: (1/2,1/2), (2,2), (3,3), (2,2,3), (4,0,5), 70/30.
- `ref/evaluate.py`: the evaluator (modes instant / germ / symbolic unknowns). Written, NOT yet run.
- `ref/network.py`: components, assembly of a problem, settle with cache, motion between moments. NOT yet run.
- `ref/run.py`: setup, moments, rounds, stages, occurrences, triggers, gates, ledger, record, reads. NOT yet run.
- `FINDINGS.md`: draft of the rulings (rules decided; examples and numbers TODO).

## Decisions taken (design)
- Expressions are data (`E(kind, args)`), never Python closures: the oracle must later read program records.
- No unit algebra: a model is in one set of working units. `Model.scales` gives one canonical unit per dimension.
- Linear ranks: `scipy linprog` (HiGHS) on float copies; each optimum is snapped to the simplest fraction
  within 1e-9, then kept as exact rows. A positive part `max(0, e)` in a row or objective is expanded to 2^k rows.
- Fair sharing in a tier: maximise t; then one LP per open claim to find which are stuck at t; repeat.
- Least distance (rank 4): float LPs sort rows (always tight -> equality; never tight -> dropped); then in
  fractions try each set of active rows up to the free dimension; the feasible candidate of least cost wins;
  flows first, then other unknowns (two-level least squares on the affine set). Empty set tried first.
- One calculation per connected set: flows that share a store, plus all unknowns of one declared solver.
  Two declared solvers in one set = diagnostic. "Affected" = the assembled problem differs from the cached one.
- Time: mode 'germ' reads `t`, moving stores and rates as polynomials in tau; a comparison answers for "just
  after" and records its first root as a stop. So contact times are exact. Irrational roots = NotCovered.
- A request that is a polynomial in time is followed only when nothing limits the flow; else NotCovered.
- A read by a report evaluates on recorded frames (state copy at each moment + level polynomials).

## Same-time rules settled (each is a switch in `Rules`)
- Round = stages (older occurrence first) -> settle once -> delays that read results -> read ALL conditions,
  then act (firings by receiver and declaration, then gates by age). Zero delay = next round, same time.
- Starts register in the order their statements ran; a broadcast goes in key order of the collection.
- Two stages of one round: sequential commits, the later sees the earlier; last write wins, `+=` adds up.
- Reset cycle: budget of rounds at one time (default 100), message names the triggers. Alt: second firing fails.
- Setup = round zero: setup statements commit as a stage, settle, then the first trigger check.
- `none`: propagates in arithmetic, ordering and reductions; `==`/`!=` test absence; a decision on none fails.
- `min`/`max` over nothing = none. `elapsed` restarts only on a net change at commit. `delayed(x, 0)` in a
  stage reads the committed value. Finished occurrence: everything frozen and readable, store reads 0.
- A saved occurrence reference pins the identity. Legs ranked differently: a claim waits for every claim that
  any endpoint ranks ahead of it ('waits'); alternatives 'latest' and 'earliest' position.
- Waiting for ever is legal; budget is on occurrences of one bound event running at once (default 1000).
- Human choice: pause inside the stage before commit; nothing of the stage is visible; resume = replay.
- `assert` on state: every round, plus "just after" each moment, plus stops at its boundaries.
- Draw key = site in the model | owner or occurrence label (not a stream position).
- Opening balance: recorded in the ledger when a cell first becomes a store ('opening', amount).
- Retirement: fail and name the amount. `move` may touch readonly. Flows of an event join after all locals.

## In the middle of
Nothing. (2nd agent) DONE: all 31 cases pass (`cases/test_NN_*.py`, 73 tests); `cases/test_rulings.py` has 23
rulings (R-A2-01..23), rule vs alternative differ; FINDINGS.md is complete (coverage, mended work, rulings,
not covered). Suite: 96 tests, best of 3 = 4.63 s at load 1.53 (`run_all.sh`).
Fixes made to ref/: setup round zero (run.py:313), node passed to draw/choose/chance (evaluate.py:236),
`Irrational` contact stops (poly.py, run.py:273), `Run.read` resolves projected collections.

## Remaining, in order
Optional only: cases for `switch`, `sees`, chance producers; resume of a pause in place.
Run tests with: `cd /home/user/napkin && .venv/bin/python -m pytest scratch/rewrite/a2 -q -p no:cacheprovider
--rootdir scratch/rewrite/a2 -c /dev/null` (the repo conftest imports napkin; keep it out).

## Facts not in files yet
- `open-items.md` gives A2 three more items than the brief: #1 move on readonly, #23 forward references of
  locals and flows, #27 the retirement rule. They need rulings too.
- Brute-force active-set enumeration over all rows is too slow (2^15 for the worked network); the float
  LP pre-sort of rows is what makes it small. An exact simplex was considered and not written.
- Current engine facts for rulings: `elapsed(s)` is `t - s__entered` and a write of the same value does not
  restart it; `delayed(x, D)` before the start reads the value after the first moment; today a pause stops
  "before committing the first unanswered controlled outcome" (napkin-base docs/engine.md:214-240, :86-98).
- The spec's flow scale is undefined when flows of two dimensions trade off in the distance step.
