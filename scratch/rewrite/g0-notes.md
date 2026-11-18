# Notes for gate G0, kept by the main session

Facts that came up beside the prototypes and that `rulings.md` must not lose. Each has its source.

## Rules of today's engine that the spec reverses or changes

| # | Today | The spec | Source | Slice |
| --- | --- | --- | --- | --- |
| 1 | A flow with legs where one leg asks and one asks nothing is an error of the run | Allowed: the leg that asks nothing moves nothing, and the fraction follows the other legs | `napkin/engine/allocation.py:165`, `tests/engine/test_rationing.py:116`; the fast tier has a second copy of the rule at `timeline/run.py:1289` (A4b) | S3 |
| 2 | Two outflows of one stock with no share are a compile error | The default is `proportional()` | `tests/engine/test_runtime.py` (triage, engine part 2) | S2 |
| 3 | Two flows with legs that share a resource at an empty stock split it "upstream first": 0.5, 0.25, 0.25 | Max-min sharing would give 1/3 each. Not run: A2 or A3 must confirm | `tests/engine/test_coupled_queue_boundaries.py` (triage, engine part 1) | S3 |
| 4 | Events that are due at one moment go in the order of their lines in the file | The order of simultaneous starts is an open item (A2) | `tests/engine/test_moment.py`; one test each in `test_public_engine.py` and `test_finite_face_kernel.py` | S4 |
| 5 | `event start`: an initiating event with its own rules at build and at t = 0 | No counterpart is named | `tests/engine/test_initiation.py` | A5 must say |
| 6 | Outcome rules: `sight`, and the chances of the outcomes of a firing sum to one | Eligibility stays; the rest is the chance producer, which has no spelling yet | `tests/engine/test_availability.py` | S4 |
| 7 | What an actor does not see is refused in its choices and conditions | `sees` only chooses what a human player is shown | `tests/model/test_sight.py` (triage: 45% of its tests are such refusals) | S4 |

## Candidates to retire and not port: what uses each today

| Candidate | Size | Used by |
| --- | --- | --- |
| The pruning of idle parts for each set of start-state options | `napkin/model/lower/starts.py`, 621 lines | `lower/builder.py:1444` fills `left_out`; the evidence trail of a report reads it (`engine/report.py:476`), and `model.py:624` |
| The second reading of the rules: `reading='every'`, `timeline.check` | About 15 lines in `run.py`, one function in `timeline/__init__.py:249` | `tests/engine/test_timeline.py` only |
| Whole-record pickles in the run store | `napkin/store.py` (entries are compressed pickles of a trajectory) | Every stored run; replaced by the record of a run in any case |
| `tools/compare.py` at its present size | 1,689 lines | A manual tool (`CONTRIBUTING.md`, `scenarios/docs/conventions.md`), `tests/test_compare.py`, and `tools/bench/measure.py:815` |
| `Partition` checks (the parts add up to the total) | `plan.py:113-136`, `run.py:2336-2368` | An `assert` with an interval can say the same (map of the engine code, A4b) |

## From the test triage

- `tests/acceptance/helpers.py` is imported by 14 test files in 7 folders (`LIBRARY`, `fixture`,
  `model_of`). Its replacement must exist at S0.
- `tests/engine/test_radau.py`: 16 of its 18 tests need no language. Split off the two that
  compile source and the rest is kept.
- `tests/engine/test_release.py` tests version strings and needs no model, but it imports
  `tests/helpers.py` for `ROOT` only, which would hold it until M. Give it its own `ROOT`.
- `tests/engine/test_erf.py`, `test_bound_balance.py` and `test_distributions_deep.py` are mostly
  free of the language, with one test each that is not.
- `tests/engine/test_expectations.py`: 28 of 38 tests go with the derivative code; 8 on `weighted`
  are ported in C. `control_variate` of `estimators.py` then has no caller in the package.
- `tests/engine/test_timeline.py`, `test_timeline_play.py` and `test_timeline_reports.py` use the
  run of the flat structure as their second oracle. It goes at S0; the reference interpreter
  takes its place.
- Tests of `napkin/core` alone sit in `tests/model/`: 15 in `test_contracts.py`, 6 in `test_units.py`, 3 in
  `test_shared_formulas.py`. Move them to `tests/core/` when their files are ported.
- `tests/test_scenario_scope.py` and `tests/test_scenario_ownership.py` are kept, but they import
  consumer code that may not import between S0 and C.
- `tests/model/test_hybrid.py` goes with the hybrid core, but five of its checks of rows deserve
  tests in S1.
- `tests/test_compare.py`: 36 of its 45 tests use made-up records. G0 decides the tool.
- `needs.csv` gives `catalogue` too often, as its header says: the two engine parts corrected
  six files to `source` or `none`.

## From the prototypes, before their findings

- A4a: the present table path cannot make a transfer between two rows of one table by a small
  change. With its two refusals removed it runs and gives a wrong answer: the debit and the credit
  land on one stock. A layout of its own (pools, links by id, one sparse network) gives the right
  stocks, also with the rows reordered, and runs 30,000 places and 35,000 routes to 48 h in 1.4 s.
- A4a: a set that runs as one component has a practical limit. 30, 100 and 300 places take 0.08,
  0.86 and 12.3 s; with rings, 300 places gave no result in 10 minutes.
- A4b: today a prediction that comes due makes its crossing hold with no look at the value
  (`timeline/run.py:2447`); only the version of the rule protects it. A flow that joins is in no
  list of the plan (`plan.py:690-709`), so the new engine must count a join and a leave as a write.
- A5: the mechanical translator handles 6,691 of 6,960 logical lines of the catalogue (96%). Left
  for a person: 172 flows with several pairs, 75 events with several outcomes, 11 `versus`, 11
  `since(e.outcome)`.
- A5: the catalogue never uses tables, copies, `change`, `each`, `while` on an event, `delayed`,
  `any` or `all`. Every crossing that the old compiler classified uses `<=` or `>=`.
