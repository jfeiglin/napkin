# Audit 3, agent V: the fresh review of 2cd1751 (R01, R02, R04, R05, R07, R11, two small)

Brief: the main session's message; COMMON-B; audit3b "The fresh review", V; audit3 rules 1-5.
Worktree /home/user/napkin-V; round 1 committed as ec23708; round 2 (below) on it, uncommitted.

## Round 1 (ec23708): places, rule tests, what is done
Places: R01/R07 record.declared, session._declared, report._origin. R02 plan.end_of/_described (L),
a stage-named endpoint made mid-run, Reader.value (KeyError -> Unavailable), a loose declared, two
catalogues in the commands. R04 compile.summary. R05 record.needed. R11 checked_value, intervals,
proofs, C's occurrences/triggers/moment/integrate, L's plan. Small: run.py help, check.solve_for.
Tests (each failed first): tests/engine/test_named_values.py (R01/R02/R07, every path, commands),
test_keyed_records.py (R05), tests/core/test_notation.py (R11), commands/test_compile.py (R04),
test_run.py (help), program/test_check.py (alias). Done: record.declaration (one lookup),
declared, absent, named, Reader.checked, needed (Keyed.reads); plan: every endpoint a flow meets,
descriptions; session, report, uncertainty; run.Offered/listed, play, sample.shown_value,
compile.flow_json; expr.notation, evaluation.failure; one writer per solver.

## Decisions
- Records of every value hold every endpoint and description (spec 131, 221-227, 163); measured
  run times unchanged within the noise of a shared machine; pieces +19-66%.
- napkin run's default lists what the file names: an endpoint only where its store sets it.
- An evaluation failure quotes the run's expression (`plant.water / (plant.water - 2 L)`) with
  the stage beside it (spec 658).

## Tests whose expectation changed
test_intervals ('`1 / y`'); model/test_build:71; commands/test_compile (kind); test_run
deliveries (default rows); test_near_tie_kinds:70,114,150 and test_near_ties:68,82,155 (`0.3 L`).

## Round 2 (the main session's three, on ec23708)
1. R02's gaps: plan._reached (an event flow's end through an entity parameter: the store of each
   member that its type allows); occurrence(): `.mean`/`.std` of its distributions into `initial`;
   C occurrences._enter records a DESCRIBED. Test test_named_values `..._through_a_parameter_...`
   (failed: KeyError "no flow meets north.water").
2. Recorder.wanted is NOT dead: sparse.py:582 reaches it, and since b566f0f it raised
   AttributeError '_needed' for every request of some keys over a sparse set. Repaired on the one
   rule (`needed` under plan.defined; `defined` likewise); Plan.formula_reads (only the old wanted
   reached it) removed. Test test_keyed_records `..._sparse_integrator_...` (failed: AttributeError).
3. Ways: test_named_values `..._sets_nothing_changes_the_way_of_no_set` (8 bench families with
   empty endpoints, deep table_instances:5000, random models): same flows and way per set. The
   30,000-place bench program did not build in 2 min (not checked); at 3,000 places: one declared
   set before and after.

## For the main session / the owner
- (L) A stage that sets an endpoint's request that the model leaves out: the set stays FAMILY
  (Plan.settled reads the start node), so the flow keeps 3 L/h; the oracle gives 5.
- `refs.spelled` (a node name: identity) keeps `q(1, 'h')` in a where/key spelling.

## Final counts, round 1 (-n 2, not deep; test_clock_moments.py left out)
tests/engine 4589; commands, core, program, model, session, store, spread, reference, acceptance,
language 2947; deep set of the new tests 51; ruff clean.
Round 2 (-n 2, not deep): tests/engine 4599; reference + commands 373; deep set of the two engine
tests 52; ruff clean on its 5 files.
