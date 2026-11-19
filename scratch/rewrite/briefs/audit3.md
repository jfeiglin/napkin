# Brief: the causes that the readiness audit of `8b3a01a` found still acting

Read `briefs/COMMON-B.md` first (its rules hold), then `PLAN.md`, "Changes after G0", items 10, 16 and
19 to 22, then `briefs/audit2.md`, the causes that the last round fixed. The audit is
`scratch/rewrite/audit/readiness-8b3a01a.csv`: of its 22 rows, 14 hold and 8 are partial. The main
session reproduced each, independently of the auditor:
`NAPKIN_STORE=off .venv/bin/python scratch/rewrite/audit/repro-8b3a01a/repro.py [06 12 14 15 17]`.
Each prints the defect on `8b3a01a`. Row 16 did not reproduce in a simple form: find it with the
property below.

## Why these got through, which is what this round changes

The last round fixed each cause where its agent looked. Three things let these through:

1. **Each agent listed the places where its cause acts in its own files.** The causes also acted in
   other files and in other forms: recursion in the front end's resolution of names and in the
   never-falls proof, not only in the engine; a formula's lifetime at a target spelled through a
   parameter, not only through `this`; writes to a finished occurrence, not only reads; the last rank
   of the selection order, not only the ranks before it; constant forms of a value other than
   arithmetic.
2. **Each rule test exercised one path.** A rule holds on every path that reads it: compile, run,
   read, report (with lags and trails), the run store (cold and warm), breakpoints, edits and resume,
   and the command line.
3. **A decision that departs from the spec was taken and merged**: an interval whose ends only a run
   knows was tested as written, where `spec.md:80` says that reversed bounds are an error.

## What every agent does, this time

1. **Search the whole repository** (`napkin/`, `tools/`, not only your files) for every place where
   your cause acts, and list them in your state file before you change one. A place in another
   agent's files goes under "For the main session" in your state file, which forwards it.
2. **Write the rule test first**, over every path that the rule governs (each item names them), and
   run it on the code as it is: it must fail. Note the failure in your state file. Then fix the
   mechanism, once, until it passes. The test states the rule from the spec; it does not compare with
   the oracle, and its expected values come from the spec, closed forms or hand work.
3. **Combine.** Each rule test runs the feature with what it can meet: an edit at a stop, a history
   budget, a record cut from the run store, a resume from a checkpoint, a lag and a trail, a member of
   a table and an occurrence.
4. **Check each decision against the text of the spec** and of the changes after G0. A decision that
   departs from it is not yours to take: follow the spec, and write the question under "For the
   owner" in your state file.
5. Tests lean, as before: while working, the files you change; your final command and the deep set
   that covers your change, once each, at the end.

The three of you share one working tree. Edit only the files that you own; ask for any other through
your state file. `scratch/rewrite/b1/audit3-<agent>/STATE.md` is yours.

## F, the front end

Owns `napkin/core/`, `napkin/model/`, `napkin/program/{parts,refs,build,check,canonical}.py`,
`napkin/engine/continuous/fields.py` and `napkin/engine/timeline/sparse.py` (for the operation
below only), `tests/core/`, `tests/language/`, `tests/model/`, and `tests/reference/` for that
operation only.

- **Row 12, a reversed interval.** The rule (`spec.md:80`): `x in [lo, hi]` with `lo > hi` is an
  error, when the model compiles if its ends are fixed then, and when the run evaluates it otherwise:
  a formula read, a stage's statement, a guard, a trigger's or a gate's condition. One mechanism: a
  membership operation of the program that checks its ends whenever it is evaluated, with the same
  failure by name in every evaluator of the program (core's, the compiled ones, the oracle's). A
  trigger's condition is E's file (`triggers.py`): list what it needs for E.
- **Row 14, a lifetime by the target, not its spelling.** The rule (`spec.md:640`): a formula or a
  flow's setting installed on a place that outlives the occurrence, and that reads one of the
  occurrence's own names (a parameter, a local, a flow of it), is refused (`lifetime`), whatever the
  spelling of the target: `this.x`, a link, an event's parameter, a saved occurrence reference, a
  member of a collection. One mechanism: the place's lifetime is the lifetime of the resolved
  target's owner.
- **Row 17, a cited datum.** The rule: a value whose record cites a datum is that number. One
  mechanism: the value compared is what the compiler's own folding of constants gives, every
  operation folded exactly where its result is rational (a conditional with a fixed condition, `min`,
  `max`, `sqrt` of an exact square, a whole power, a unit conversion); a value that cites a datum and
  that the compiler cannot fix is a `datum` warning as well ("it is computed when the model runs, and
  a datum names a number"), never a silent pass; and a number token is the exact decimal that it
  writes (`parse.py:538`), never read through a float.
- **Row 15, recursion in the front end.** 300 top-level formulas in a chain fail to compile with a
  RecursionError (`semantic.py`: `path`, `name`, `value`, `initializer`, `expression`). The rule: a
  model whose values form a chain of 5,000 links compiles with the recursion limit lowered to 400, in
  each form that the front end resolves: top-level formulas, entity formulas, links between members
  of a table, keyed reads, initializers in the order of their dependencies, and the lowering. One
  mechanism: names resolved in a dependency order made by a loop, or on an explicit stack.

## E, the engine

Owns `napkin/engine/timeline/{moment,occurrences,plan,collections,triggers,run,pools,chance}.py`,
`napkin/engine/continuous/` but `fields.py`, and new files in `tests/engine/`.

- **Row 14, a finished occurrence is frozen.** The rule (`spec.md:632`): every write to the field or
  the store of an occurrence after it finished fails the run by name at that moment, whatever makes
  it: an assignment through a saved reference, a `move`, a flow. One check, where every write and
  transfer of a run lands (`moment.py:512` is one of them).
- **Row 15, a named collection at the top level.** `tanks = Tank.instances` and then
  `sum(tanks.water)` is refused by the engine (`plan.py:1650`). The rule: a named collection is the
  collection that it names: every reduction, projection, keyed read and count over it equals the
  same over the collection written in its place, at the top level, in an entity and in an event.
- **Row 15, recursion in the engine.** The run, its reads and its triggers on F's chain of 5,000
  links with the recursion limit at 400: B's driver (`plan.walked`) covers the engine's walks; test
  the paths that it may not: a named collection, keyed reads, a trigger's condition, a solver's
  inputs, the sparse integrator.
- F's membership operation in a trigger's or a gate's condition, once F says what it needs.

## R, records, reports and solves

Owns `napkin/engine/solve/`, `napkin/engine/timeline/{record,reads,checkpoints,saved}.py`,
`napkin/engine/report.py`, `napkin/store.py`, `napkin/program/{record,proofs,reach,config,checkpoint}.py`,
`tools/evidence/`, and their tests.

- **Row 06, every rank, the last included.** `solve.Answer.admits` compares the objectives, the
  served fractions, the rows and the bounds, and not the final distance to the targets, which is a
  rank of the selection order (`spec.md:548-556`): a candidate that moves all of a delivery onto an
  idle pipe passes. The rule: an answer published in place of the solver's is no worse on any rank,
  the distance included, to its tolerance. Rule test: on random solver programs, a feasible
  alternative that is equal on every earlier rank and farther from the targets is never admitted, and
  the published answer's distance is the solver's to its tolerance.
- **Rows 11 and 18, the budget, the store and the stops.** The budget is applied once a record is
  built (`record.py:377`), so a run with a breakpoint gives a checkpoint at 2 h of a record that was
  over its budget at 0 h; and the store's cut of a longer record (`store.served`) keeps a history that
  a fresh run of the shorter request would not have (the ledger of a store edited after the cut), so
  the same request succeeds cold and fails warm. The rule: what a record holds, and whether a run
  within its budget succeeds, follows one rule as the run goes. A run whose record would exceed its
  budget stops then, before any later stop or checkpoint; and a cut of a longer record is the record
  of a fresh run of the shorter request, by the same rule. Rule test: random runs with edits at random
  stops, random budgets and horizons: fresh, cut from a stored longer run, and resumed from a
  checkpoint give the same outcome (finished or stopped, where and why) and the same values.
- **Row 15, recursion in records and reports.** The never-falls proof (`proofs.py:787`), the report's
  lag (`report.py:196`), the trail and the record's reader on F's chain of 5,000 links with the
  recursion limit at 400.
- **Row 16, a trail that depends on its report.** The rule: the trail of a value is the same whatever
  else its report holds, and in whatever order. Rule test: random models with nested formulas that
  depend on the time (branches on `t`, on stored values that a stage changes, on `since` and
  `elapsed`), random sets and orders of paths, times and lags: each path's trail equals its trail in
  a report of it alone. The auditor saw an unused source marked exercised for an outer value once the
  value between them was reported first; find the case with the property, then the cause.

## When you finish

Your report: for each item, the places where the cause acted (all of them, in any file), the
mechanism, the rule test and its failure before the fix, what you sent to the main session, each
decision with the spec's text that it follows, and your final counts.
