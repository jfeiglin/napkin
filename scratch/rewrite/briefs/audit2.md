# Brief: fix the causes, not the cases (the re-audit of `0f78c65`)

Read `briefs/COMMON-B.md` first (its rules hold), then `PLAN.md`, "Changes after G0", items 10, 11,
15, 16, 19 and 20. The re-audit is `scratch/rewrite/audit/reaudit-0f78c65.csv`: 22 entries, 12 of
which pass their first reproduction while 7 of those fail a close variant. The fixes after G2 cured
the cases the audit named and left the causes that produce them. This brief names the causes. Each
agent fixes its causes **at the level where they live**, and the audit's rows are test cases of a
cause, not its definition.

## What every agent does

1. For each cause: find **every** place in your files where it acts, not only the audit's line.
   List them in your state file before you change one.
2. Fix the cause once, in one mechanism that all those places use. A fix that adds a special case
   for one example is not a fix.
3. Write a test that states the **rule**, so that it would have caught every instance: a property
   over random or many inputs, or a metamorphic test (the same model under a change that must not
   change the answer). Then the audit's rows and the variants you find, as plain tests.
4. The oracle (`tests/reference/`) and the engine were changed together after G2, and both carried
   the solver-scope error: the oracle is not independent where one agent wrote both. A rule-level
   test checks a property from the spec directly, and does not compare with the oracle.
5. Tests lean, as the owner asked: while working, the files you change; your final command and the
   deep set that covers your change, once each, at the end. No benchmark unless your part says so.
6. If a fix changes a number that a test or an example expects, trace it to the spec before you
   change the expectation, and list it.

## The causes, and who owns them

### A. The selection order and every change to an answer after it (agent A)

Files: `napkin/engine/timeline/declared.py`, `network.py`, `selection.py`, `family.py`,
`napkin/engine/solve/`, `tests/reference/network.py` and its tests, new tests in `tests/engine/`.

- **A solver's named claims are put ahead of every unnamed claim** (re-audit 07). The owner's rule:
  a flow the solver does not name keeps its endpoint's local sharing, so an endpoint's rule ranks
  all its flows, named or not. With `priority(hospital, garden)` and a solver naming only the
  garden, the hospital is still served first. Build the claims' order from the endpoints' rules,
  with the solver's own sharing acting only among claims that those rules leave equal. Rule test:
  on random networks with priorities and a solver naming a random subset of flows, a claim an
  endpoint ranks above another is never served less because of which flows are named.
- **The polish changes the solver's answer without checking it** (06): it snapped a delivery split
  across two pipes to zero and published a top objective of 1 where the solver found 0. Make every
  change to an answer after the solve, the polish and any snap, a candidate that must pass the same
  end checks as the answer it replaces: each kept optimum, each fair level, each claim's served
  fraction, every row and bound, each to its stated tolerance. A candidate that fails is dropped
  and the solver's checked answer is published. Rule tests: on random solver programs, the
  published answer is never worse than the solver's on any rank; the same model in L, mL and kL
  gives the same physical answer.
- **Structure is analysed on the declared network, not the one that can carry flow** (05): a return
  pipe with zero capacity made a ring of full stores and refused a feasible run. Rings and depths
  read the edges that can carry flow at that moment, and are made again when a capacity changes.

### B. Time, and evaluation that recurses (agent B)

Files: `napkin/engine/timeline/triggers.py`, `moment.py`, `occurrences.py`, `run.py`, `chance.py`,
`plan.py`, new tests in `tests/engine/`.

- **Time is added up in floats along several paths, each with its own tolerance** (04): stages now
  meet the 0.3 h horizon, but a trigger that resets after 0.1 h fires its third time at
  0.30000000000000004 h. Give the engine one rule for when something is due, used by stages,
  delays, gates, triggers' resets, `.at(t)` ties between occurrences started together, `since`,
  `elapsed` and the horizon: scheduled times built from the model's durations in exact arithmetic,
  or one function that every path calls. Choose, and say why. Rule test: a schedule reached by any
  sum of delays behaves as the same schedule written directly, on random sums.
- **Long chains recurse in Python** (15): a total read through 100 acyclic child links raised a
  RecursionError in the reader. Make every evaluation over the dependency graph iterative, in the
  engine (`plan.py`, `collections.py`, `run.py`) and with agent C in the record's reader.
- **Moments of a truncated distribution are computed in a form that underflows** (13):
  `normal(0, 1, 9, 10)` draws 9.07578 but its `.mean` and `.std` divide by zero. Compute the moments
  of every bounded distribution in a stable form; check them against mpmath across the tails.

### C. What a record holds, and what a report claims from it (agent C)

Files: `napkin/engine/timeline/record.py`, `napkin/engine/report.py`, `napkin/program/proofs.py`,
`napkin/program/record.py`, `napkin/program/config.py` (the history budget), `napkin/store.py`,
`napkin/engine/timeline/reads.py`, `tools/evidence/trail.py`, their tests.

- **A value the record does not hold is read as a default** (11): `record.py` reads a missing
  history as 0.0, so a -1 L edit showed as 0 with only the stock recorded, a LookupError with only
  the ledger, and -1 L once a cached full run served the same request. A reader gives a value only
  from what the record holds, and otherwise `Unavailable` with the reason. What the books need (a
  store's external total once it is edited) is kept whatever the request names. A cut of a stored
  record answers as a fresh run of the narrower request would. Rule test: for random programs and
  requests, a fresh narrow run, a narrow run cut from a full one, and a full run agree on every value
  that the narrow request holds, and none gives a value that it does not hold.
- **Results are paired with times by position** (10): asking a stopped run for hours [3, 1] put
  hour 1's value under hour 3. Carry each value with its time. Rule test: permuting the requested
  times permutes the results.
- **A proof is computed once and then patched by kind of edit** (09): an edit that turned on a
  withdrawal left the stock certified never to fall and the event "cannot start", although it ran.
  An edited run's proofs are derived again with each edited field free from the time of its edit,
  any value of its type and bounds, so every consequence follows from one premise. Rule test: on
  random edited runs, no proof the report gives is contradicted by the run's own values.
- **"Exercised" is read from what an expression can read, not from what it did read** (16): a
  number from branch B cites the untaken branch A, and both a status display's first case and its
  fallback show as reached. The lazy evaluator (`reads.py`) knows what each evaluation read and
  which branch, case or argument of `min`/`max` it took: record that, and let the trail say
  exercised for what was read and possible for the rest. Rule test: on random formulas with
  branches, the exercised set is exactly the set read at that time.
- **A lag accepts a value of any type** (21): `false` lags to 0.0 and a text raises a ValueError.
  The report checks the type of what it is asked for and refuses by name.
- **The history budget is declared and not enforced** (18): one piece budgeted, twelve kept. Enforce
  it, and stop by name when a run would exceed it.

### D. Units and lifetimes in the front end (agent D)

Files: `napkin/model/` (and `napkin/core/units*` if units live there), `tests/language/`,
`tests/model/`.

- **Quantities are compared by their spelling, not their dimension and scale** (12, 22, and the
  cyber model's `sqrt(luck + common)` of a dimensionless `ratio`): `0.1 day in [2.4 h, 2.4 h]`
  fails, `sqrt(24 h * 1 day)` fails where `sqrt(24 h * 24 h)` works, a reversed interval in a
  membership test gives false. Every unit check, comparison, range, bound, `sqrt` and power reads a
  quantity as its dimension and its scale, with literals and scales in exact rationals, so equal
  quantities are equal however they are spelled. Rule test: on random quantities, respelling a
  unit (h, min, day; L, mL, kL; a named dimensionless unit) never changes a check or a value.
- **A value's lifetime is not part of its type** (14): reading a field through a saved occurrence
  reference fails to compile, while an entity formula that captures an invocation's local compiles
  and is read after the invocation ends. Give each value an owner and a lifetime in the checker: an
  occurrence reference is a typed value whose fields resolve against its event (frozen once it
  finishes, D7); a formula may read only what lives at least as long as it does, or a copy.
- **A keyed read with a fixed key depends on every entry** (15): `<leaf, top>.at(0)` selects only
  `leaf` but makes `top` depend on itself. A key fixed when the model compiles selects its entry
  there, and the dependency graph reads only that entry.
- **A value is not checked against the datum it cites** (17): an input of 99 h citing a 34 h datum
  compiles silently. Compare in dimension and scale, within the record's stated precision, and
  report a difference as a warning with both numbers (an error in `tools.check`, as change 16
  does for a missing record).

### K. The migration checker (agent K)

File: `scratch/rewrite/a5/check.py` and its fixtures. **It compares values, not outcomes** (19): a
new run that fails at the final hour passes if its last values match. Compare each run's outcome
(finished, failed or paused, where and why) as part of the run step; a new failure or pause passes
only when `changed.md` lists it.
