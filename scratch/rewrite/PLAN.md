# Plan: implement the napkin language rewrite

## Progress

Each session starts by reading this file and `spec.md`, and ends by updating this list.

The current engine refactor starts from `6202824` on `engine_finalized_simple`. Its handoff follows a transfer from the authored request through allocation, interval acceptance, physical posting and recorded evidence. The handoff includes the duplicate-rule register, each benchmark script and size, the regular and deep corpus rules, and the order of the settlement and port-readiness gates. [Engine responsibilities and gates](audit/engine-finalized-simple.md) · [Measured results](audit/engine-finalized-results.md)

- [x] Step 0: the spec and the plan in `scratch/rewrite/`, the environment, the base worktree
- [x] A1 notation and types (`a1/FINDINGS.md`, 32 rulings)
- [x] A2 reference semantics (`a2/FINDINGS.md`, 23 rulings; 96 tests)
- [x] A3 solver numerics (`a3/FINDINGS.md`, 9 rulings; fair sharing and the last distance step are a no-go at 30,000 places)
- [x] A4 engine at scale, as two prototypes: A4a (`a4a/FINDINGS.md`, 8 rulings; its `measure.py` is not yet run end to end) and A4b (`a4b/FINDINGS.md`, 8 rulings; `a4b/LAYOUT.md`)
- [x] A5 catalogue fit (`a5/FINDINGS.md`, 15 rulings)
- [x] B0 keel, beside Phase A
  - [x] 1 imports that survive
  - [x] 2 `tests/units.py`
  - [x] 3 the dormant list
  - [x] 4 the test triage: `tests-triage.csv` (the parts are in `triage/`)
  - [x] 5 the derivative code deleted (`cf5c8d3`; proved bit for bit on 370 cases, `b0/bitwise.py`)
  - [x] 6 `timeline/run.py` split by moves into ten modules (`a4b/split_run.py`, `a4b/LAYOUT.md`)
  - [x] the last run of the old suite, with durations: 5,485 passed, 3 skipped, 5 min 52 s (`b0/last-old-suite.txt`)
- [x] Gate G0 (2026-11-18): the owner's decisions are `g0-decisions.md`; `spec.md` is the settled proposal. See "Changes after G0" below
- [x] B1 contract, oracle and solve library: three tracks (`briefs/b1-*.md`)
  - [x] the program (`napkin/program/`, `tests/program/`: 421 tests, 65 examples for the 32 acceptance rows)
  - [x] the oracle, phase 1: the semantics of G0 (`tests/reference/`, 127 tests)
  - [x] the solve library (`napkin/engine/solve/`, `tests/engine/solve/`: 173 tests; the four cases at 3,000 places run the whole order in 4 to 10 s)
  - [x] the oracle, phase 2: it runs all 65 programs of `tests/program/examples.py`, and each gives its expected results
- [x] S0 skeleton (`briefs/s0-front.md`, `briefs/s0-engine.md`); the dormant list is filled (6 folders, 110 files)
  - [x] the front end: the whole notation parses and formats; the subset of S0 lowers (`tests/language/`, 197 tests); `examples/piano_tuners` in the new language
  - [x] the engine: it reads programs only; `napkin.engine.run` and `read`; the key of a stored run; five engine test files ported (`b1/s0-engine/STATE.md`)
  - [x] the switch: `napkin run`, `fmt` and `compile` on the new path; the old compiler deleted (6,097 lines); the contract changes of both tracks (`b1/s0-switch/STATE.md`). 2,044 live tests pass
- [x] S1 templates, tables and collections (`briefs/s1.md`)
  - [x] the front end: templates, links, tables with ids, collections, reductions, `where`, `by`, `.at`, assertions over inputs (`tests/language/`, 294 tests)
  - [x] the engine: pools of members, the reverse index, the index of keys with its key times, the reductions; a connected set of one flow whose rate reads nothing that moves runs on arrays at any size. Benchmark: 30,000 rows, plan 4.7 s, run 7.2 s with the record of everything (`b1/s1-engine/STATE.md`)
  - [ ] for S2: the checker refuses `count(this.pumps)` (a path that ends on a collection value); a field named `start`, `draw`, `where`, `by`, `at` or `choose` cannot be read through a handle of `build.py`; per-row formulas of a large table are fitted row by row (slow); a failure inside a long numerical segment is timed at the segment's start; the setup reports for equal keys under `.at` and for coverage at a lower bound
  - [ ] contract and examples, for S5: the worked network's flows carry `W` where a source gets `Wh/h`, and its readings are fractions where a table gives floats, so its bytes differ from its source
- [x] S2 the flow network and sharing (`briefs/s2.md`); the carry-over of S1 is in it
  - [x] the front end: endpoints, priority over flows and ranked projections, flows across entities, junctions; the three contract fixes; the setup reports print as warnings
  - [x] the engine (its agent stopped at a restart of the container after step 8 of 9; the main session finished it): one sparse network, local sharing settled in the direction of supply, lines for rates held between moments, a sparse integrator for moving sets; 300 random networks agree with the oracle (2,000 under `deep`)
  - [x] carried into S3 and done there: the moving benchmark at 30,000 places that stopped at 41.94 h; the ports of `test_chattering.py`, `test_closed_form_short.py`, `test_roundoff_properties.py`; the speed of lines (87 s)
- [x] S3 reversible flows and flows with legs (`briefs/s3.md`), with the carry-over of S2. 2,979 live tests pass
  - [x] the front end: `<->` with its legs, flows with legs and one `served_fraction`, `.source` and `.sink` typed as the store at that end (`tests/language/`, 378 tests). A tally is known by use: a store at a route's end is a stock, so only `SOURCE` and `SINK` are refused there
  - [x] the engine (`b1/s3-engine/STATE.md`): a route is one signed rate with two leg views, a flow with legs one fraction, both through local sharing; routes and legs run as lines or on the sparse integrator, never as arrays or one component; an endpoint request that a route meets stops the run by name (the oracle has no answer either). 300 random networks with routes and legs agree with the oracle (2,000 under `deep`). Ported: `test_coupled_queue_boundaries.py`, `test_chattering.py`, `test_closed_form_short.py`, `test_roundoff_properties.py` (moves, timers and stock faces dropped: S4)
  - [x] the carry-over of S2: local sharing at scale solves each part in its own units, with claim rows as served fractions and a distance step from a feasible vertex or by the dual method; the moving benchmark at 30,000 places runs to 48 h (build 3.6 s, plan 22.2 s, run 299 s). Lines re-solve only what lies downstream of a changed store: held at 30,000 places, run 8.1 s (was 87 s); equal to the whole-part path up to roundoff (5.7e-14)
  - [x] the join: `napkin run` lists a route's legs and a flow with legs' fields in file order, each leg in its own unit, and a link as the name of its member
  - [ ] performance, for later: about 3/4 of the moving benchmark's 299 s goes to 2,948 two-store components, each run and fitted alone
- [x] S4 occurrences and time (`briefs/s4.md`). The largest slice: its engine comes in two parts, one after the other; the front end does the whole slice beside the first part
  - [x] the front end, the whole slice (`b1/s4-front/STATE.md`): the 32 examples that need no solver lower to their bytes; a write through `.source` or `.sink` is refused (`fixed_write`); reachability under a configuration (D16) is proof metadata in `napkin/program/reach.py`, ported from `81b367b`, each template's members merged into one state. An enum is named by its spelling. A distribution whose parameters are values is refused (`distribution`): the program holds numbers. Draws and choices stand only where a value is captured once. An event local holds no entity; occurrences are read through `.at(t)` (a local may keep one). Ported and deleted: the five front-end files of `tests/model/` for S4; `test_initiation.py` deleted (the old start of an incident)
  - [ ] for C: `napkin/model/views.py` is rewritten on the compiled model; `draw/` and `commands/play.py` still call the old API
  - [x] the engine, part one (`b1/s4a-engine/STATE.md`): occurrences, stages, gates, triggers, moves, retirement, history, limits. The 23 examples equal their values and the oracle; 300 random event programs agree with the oracle (2,000 under `deep`). New `moment.py`, `occurrences.py`, `triggers.py`, `ways.py`; the dead modules of the old engine deleted but `state.py` (part two). A moment rebuilds each connected set that it touches, in its own way of running. A contact on a curve is certified only for one store that only rises or only falls; else, and for a strict threshold on a moving value, a diagnostic. A setting that reads a rate of a set whose rates move is refused "(S5)". Ported: `test_finite_face_kernel.py`, `test_finite_stock_boundaries.py`, `test_monotone_crossing.py`, `test_rearm.py`, `test_switch_at_segment_start.py`, `test_timeline_row_facts.py`; the event cases of `test_runtime.py` and `test_timeline.py` (new files; the old ones stay dormant for the rest) and the trigger classes of `tests/model/` as `test_trigger_classes.py`; deleted `test_ai_layer.py`, `test_moment.py`, `test_windows.py`. Benchmark at 30,000 places with 482,500 starts over 48 h: build 0.7 s, plan 1.9 s, run 866 s, mostly reading every trigger at each moment. 3,472 live tests pass
  - [x] the join: `napkin run` lists no occurrence by default; `--value tank.deliver#1.pipe.request` reads one, `unavailable` before its start
  - [ ] for later: read again only the triggers whose inputs changed; free the caches of finished occurrences (memory grows with the starts); in stages, assign a formula, an allocation or a collection (refused "(S4)"); endpoint settings on an occurrence's own store
  - [x] the engine, part two (`b1/s4b-engine/STATE.md`): draws keyed by their site and their owner (the occurrence, the member, `''` for the root and the setup, `key!n` for the n-th firing of a trigger), each uniform number the first 64 bits of SHA-256 of `seed|site|owner`, as in the oracle; a median categorical draw is the most likely eligible outcome (the first on a tie), weights scaled to their sum. A stage reads lazily, so a branch not taken draws nothing. A choice is a keyed draw for a forecast and a pick for a player; a missing pick pauses the run: its record's trace ends with a `pause` entry and `Run.resume(*picks)` gives the record of a replay with the picks. A player's choice at an entry, a delay or a firing fails the run. `elapsed`, `delayed` (a condition or a rate that reads the past of a moving value is a diagnostic), `.mean` and `.std`; assertions after each round; a distribution or an allocation assigned in a stage; endpoint settings on an occurrence's own store. The 9 examples equal their values and the oracle; 200 random programs with draws agree with the oracle (1,000 more under `deep`). Ported: `test_chance.py`, `test_availability.py`, `test_firing_values.py`, `test_pause.py`, `test_play.py`, `test_settled_decisions.py`, `test_timeline_outcomes.py`, `test_timeline_play.py`; dropped with them: control by event, filters of decision events, opt-in settled windows, chances that must add up to 1. Deleted `timeline/choices.py`, `state.py` and `reports.py` (it no longer imported; C writes the report over the record)
  - [ ] for C: `test_decision_resolver.py` and the two resolver cases of the old `test_timeline_play.py` (`git show 8d5ae95:tests/engine/test_timeline_play.py`) test the resolver of `napkin/session.py`
  - [x] found at the join of part two, and fixed: the oracle's four departures from the spec (a `delayed` formula read after the run reads its delay before the time of the read; a draw in a trigger's captures, body or `reset after` belongs to the firing, `key!n`; categorical weights are scaled by their sum; endpoint settings under an occurrence's own store apply). In the engine, `since(e)` moves with the time as `t` does, so a rate that reads it is followed through the interval and recorded; every evaluation reads lazily (`timeline/reads.py`), so `and`, `or` and a conditional read only what they need, as the spec says, in stages, formulas, conditions, collection tests and keys, the recorder and the reader; the ways that evaluate many rows at once build a column only when it is read
  - [x] settled: `delayed` leaves the language (change 12). In the oracle, a followed request that falls below zero is caught only at the next moment. (Fixed: the oracle did not follow a moving request that was zero at the moment, such as `t * 1 L/h/h` at 0 h.)
  - [ ] carried into S5: in a stage, the assignment of a formula or a collection; keyed reads of moving values and keys (still refused "(S4)")
- [x] S5 solvers (`briefs/s5.md`). 4,070 live tests pass
  - [x] the front end (`b1/s5-front/STATE.md`): `solver:` with `inputs`, `solve_for`, `constraints` and `objective` resolves, checks and lowers, and the 17 examples with a solver lower to their bytes; no change to the contract. The worked network's flows and the pump's power read `Wh/h` and `kWh/h`, as their sources give, and readings are floats. Refusals by code: `solver_form` (strict relations, `!=`, a disjunction, a relation under a condition, an unknown in a test or a key), `nonlinear` (products, quotients and functions of unknowns; a yes-or-no problem is left out), `participant` (a solver reads only rates that it determines, stricter than the oracle, which reads other rates as known), `two_solvers` (two solvers whose flows meet in one connected set, whether or not a bound binds), `solver_input`. A read of a result before it settles is left to the run. `test_binary_controls.py`: its front-end cases are in `tests/language/test_yes_no.py`, its edits wait for S6
  - [x] the engine (`b1/s5-engine/STATE.md`): declared solvers on the solve library (`timeline/declared.py`). Each affected solver is solved once in a round, in dependency order, and published before conditions are read; a read before it settles is an error; members join and leave; answers are polished onto the bounds and rows they hold, so the examples come out exact. A flow that shares a store with a solver's flow is in that solver's problem, as in the oracle. A solver whose inputs move is integrated with Radau and a full solve at each trial state, for at most 20 stores; above, a diagnostic names the solver and the limit (never held: D3). A setting that reads a rate of its own set fails the run: it needs a declared solver, as the oracle says. The 17 examples equal their values and the oracle; 100 random programs with a solver agree with the oracle (900 more under `deep`). Ported: `test_erf.py`, `test_continuous_domains.py`
  - [x] the join: `napkin run` from source gives the two bottlenecks (2, 2, 3) W with 11 W unmet, and (4, 0, 5) W with 9 W unmet under `minimize(sum(consumers.unmet))`
  - [ ] the benchmark (A3's network as a program, 48 h, supply times 0.8 at 24 h): 3,000 places build 0.4 s, plan 2.1 s, run 31.7 s, 2 solves, 0.5 GB; 30,000 places build 5.8 s, plan 26.5 s, then the run stops at 0 h after 132 s: "numerical in fair sharing, tier 0: HiGHS ended with the status kUnknown" (3.2 GB). The solve library's own bench with `--share 1.0` fails the same way
  - [ ] left, with no stage yet: in a stage, the assignment of a formula or a collection, and keyed reads of moving values and keys (refused "(S4)"); a setting that reads a moving rate of another connected set; a priority endpoint with a request inside a declared solver; the cases of `test_runtime.py` and `test_timeline.py` that are not events. The oracle applies the stale-read rule to the rates of local sharing too, where the spec and D5 speak of solver results; the engine applies it to solvers only
- [x] S6 packages and configurations (`briefs/s6.md`), with what earlier slices left (S6-E) and fair sharing at full scale (S6-S)
  - [x] the front end (`b1/s6-front/STATE.md`): `use`, `variant`, `change`, options, named runs and the edit document give one program and one `Configuration` (`load_scenario(path, run=, edits=)`, `Compiled.configure`), with the precedence of R-A5-03; a package's files read as one model, each problem at its own file and line. `Configuration` holds no start values: only inputs are configured (R-A5-04, D2). `model_hash` covers the program, options and runs, the default configuration and `LANGUAGE_VERSION` (0.1.0), and no label, note, record or place, so evidence no longer moves it. A record is needed for a number, a yes/no or a distribution that an option or a `change` sets. `runs:` stays in the model (R-A5-04, R-A5-06, D9). Ported and deleted: eight files of `tests/model/` and four of `tests/engine/` (options and runs, combinations, yes/no controls); `tests/acceptance/test_every_construct.py` runs from source (a status display waits for C; captures, an entity parameter, `.at(t)` and a start on each member are in `tests/language/test_events.py`)
  - [x] mended at the join: `path = expression` in the setup scope initializes that path as the indented line under its declaration does (the same program bytes), as the spec says; a second initializer is a `property` error naming both lines; a `change`, an option and an edit still win; a `readonly` value may be initialized so (it bars assignment, not initialization). Templates, table rows and settings of a member's parts stay refused
  - [x] the engine, what was left (`b1/s6-engine/STATE.md`): a formula assigned in a stage (readers follow it from the commit; the trace keeps each definition); keyed reads whose key, keys or members move (on the sparse integrator, a segment ends where the selection changes); a setting that reads a moving rate of another set (the sets integrate together, level by level); a priority endpoint with a request inside a solver ("a preferred route has first access to useful requested work"). Fixed on the way: a number written to a request that was a formula was ignored; a key written in a stage did not rebuild what reads the keyed read; a trigger on `any(...)` of moving flags fired at the horizon; an enum formula of a moving value crashed the recorder; per-member keyed reads were quadratic (30,000 x 30,000: plan 7.2 s, run 12.9 s). A status display runs and computes nothing (its reading is C's). No refusal names a slice. Ported in place: `test_runtime.py` (20), `test_timeline.py` (7)
  - [ ] refused with the spec's reason: a collection assigned in a stage (R-A1-30); a lookup keyed by a solver unknown; a watched condition on a moving keyed read whose first crossing is not certified; an endpoint request at a route inside a solver (not convex); `where` over plain values; a link at the root. Refused as engine limits: a set that follows a moving solver, or that one follows; a starting value that reads an actual rate fails the run ("read before its flows first settle"), as in the oracle. A gap against the spec: `where` over an endpoint's flows, which the spec describes and both halves refuse
  - [x] fair sharing at full scale (`b1/solve/STATE.md`): two numerical failures of the kept HiGHS instance, not of the programs. At need x1.45 a fair program at the primal tolerance 1e-10 ended `kUnknown` when HiGHS's cleanup met a taboo basis change (a fresh instance answers it in 0 iterations); at x1.7 the kept factorization drifted over 5,000 updates, so an answer reported optimal missed a balance row by 1.1e-4, a fair level came out 3.4e-7 high, and the held claims emptied the face. Mended: `Kept.run` checks each answer against its own copy of the matrix and, on a status it does not state or a miss above 10 times the tolerance, solves the same program on a fresh instance (warm, then cold by the dual simplex), else fails 'numerical' naming the cause and size; `fair.UPDATES` 100. At 30,000 places with a budget of 5,000 programs, objective + fair: normal 4.2 + 152 s (459 programs), x1.45 6.1 + 396 s (1,287), damaged 3.8 + 175 s (693), x1.7 6.3 + 587 s (1,779); the whole order at normal need adds 350 s of distance step. The default budget of 1,000 stops x1.45 and x1.7 by name. The reproducibility rule (change 11) is applied in the library and its tests
  - [ ] the engine's benchmark at 30,000 places did not finish its first solve within 45 minutes (stopped by the owner's cap): at 0 h, past fair sharing, in the distance step of the flows (SuperLU in `distance.nearest`). The problem that the engine forms is harder than the library bench's; P1 (`briefs/p1-solvers.md`) measures why, with interior-point solvers, fewer fair programs and looser tolerances
  - [ ] for C: studies and admission, reuse of pages, the library hash and the closure of evidence (from the ported files); whether the publisher needs a hash that moves with texts and evidence, as the old `model_hash` did. For M: the three catalogue cases of `test_runs.py`. Not done: an instance value needs no record yet, though the spec says it does ("as an instance value does"); the dead `LANGUAGE_VERSION` of `ir.py`; `tests/model/test_build.py`, `test_diagnostic_places.py`, `test_library.py` still dormant; `tests/test_package.py`, `test_nested_packages.py` and `tests/evidence/test_adopt.py` import fixtures of deleted files
- [x] Gate G1 (2026-11-19; the owner asked to go on past it, into C). The wide run, `tests/core`, `tests/program`, `tests/reference`, `tests/language`, `tests/model`, `tests/engine` and `tests/acceptance` with 4 workers: 4,049 passed in 99 s; ruff clean (but `napkin/draw/` and `napkin/dynamics/`, being ported). Every worked example of the spec runs from source: the 65 programs equal their values and the oracle, and each source lowers to its program. The file with every construct runs from source (a status display waits for C). `napkin run` on the worked network gives the levels (8/3, -4/3, -4/3) and, once the garden route closes, (3, -3, 0); its tables reversed change nothing; in kW each delivery is 0.004 kW. Shown on the way: a solver leaves residues such as 4e-26 where it means 0, and a rate prints `Wh/h` where the spec writes `W`
- [x] C results and consumers (`briefs/c.md`); the publisher waits for M (change 13)
  - [x] commands, API and tools (`b1/c-commands/STATE.md`): `napkin run` prints through the report, with `--run NAME`, `--edits FILE` and `--lag PATH=FROM..TO`; status displays and near-ties under the table; the evidence trail in its JSON; runs kept in the run store. `napkin sample` on `spread` (central value, mean, percentiles, p99 and p99.5 with enough samples, drivers, `--exceed`). `napkin draw` reads `Things(compiled).runs`; `napkin compile` checks `style.toml` and lists the runs and the model hash. `napkin new` and `tools/new.py` write the new language; `tools/compare.py` is small, over the record; `tools/bench/` over programs. The text shows 0 for a number within 1e-10 of the largest magnitude of its history (the JSON keeps the record's number), and a composed unit as the named unit of its dimension and scale (`Wh/h` as `W`). The Python API: `load_scenario`, `load_package`, `run`, `read`, `report`, `Lag`, `study`, `monte_carlo`, `spread`, `instances`, `dynamics`; `sample_result`, `evaluate_*`, `uncertainty_report` are gone. Live: `tests/commands/`, `test_api.py`, `test_bench.py`, `test_compare.py`, `test_nested_packages.py`, `test_package.py`, `test_tools_new.py`; `test_cli.py` and `test_cli_tables.py` ported and deleted; `test_tools_new_catalogue.py` and `tests/release/` wait for M
  - [ ] for S7: `napkin play`, `Session`, `actors`; `CLOSURE` of `tests/test_api.py` again once S7 lands. Engine bugs found: a solver's residue makes `rate_follows_levels` (an equality of a flow and the levels) false at 3 h in the worked network, where R-A3-02 compares a formula that reads an enforced equality to 1e-7 relative; `sparse.py`'s `compiled` crashes on an enum read in a moving rate; a linear chain of three compartments takes 9 s
  - [x] studies and runs (`b1/c-studies/STATE.md`): `store.py`, `engine/sampling.py`, `study.py`, `uncertainty.py`, `expectations.py`, `spread.py` over programs and records. The run store keeps one record for each key (the program, the configuration without its request, the code and the machine; no label, no thread setting); a request that the record covers is cut from it (an equal or earlier horizon, values that it holds), else the run is made again with a request wide enough for both and replaces the entry; a failed run is stored, a paused one is not. A Monte Carlo study runs the median run first, then samples with the seed SHA-256 of `seed|k`; a sample that stops refuses the study and is named. Parallel samples: `jobs=N` fresh processes, ordered chunks, only values and draws come back; the same study gives the same bits, other process counts agree within tolerance. Only the plain estimators stay: latin, Sobol' and the weighted estimator went, because a draw is keyed by its seed, site and owner and cannot be handed a number. Ported: `test_store.py`, `test_spread.py`, and `test_monte_carlo_study.py`, `test_public_engine.py`, `test_expectations.py` of `tests/engine/`; `test_admission_scope.py` deleted (the admission scope left in S6)
  - [ ] for S7: `napkin/session.py`, `tests/test_session.py` (also the catalogue, M) and `tests/engine/test_decision_resolver.py`; a store key over an edit log (`key` digests the log, `_save` keeps it, `run` resumes through S7's entry). `napkin/model/analysis/` stays while the old `session.py` imports `values.py`; `napkin/schema/report.schema.json` while `napkin/model/load.py` loads it
  - [x] evidence tools (`b1/c-evidence/STATE.md`): `tools/evidence/trail.py` reads each use of a record in the declared model and what a value rests on, resolves a report's trail in the library (each claim's verification, each assumption's review; parts not exercised kept apart as possible), and gives disclosures (`python -m tools.evidence.trail MODEL PATH... [--run NAME]`); `integrate.py --coverage` over it; `manifest.py` keeps the publisher's interface for M. `tests/evidence/` and `tests/model/test_pages.py` are live (164 tests); `test_catalogue.py` and `test_scientific_spec.py` wait for M. Found, for the front end: `model_document` parses only the entry file and misses a package's modules' records (worked around in `trail.py`); `proofs.reads` misses a stage that assigns a flow's request; the report's trail leaves out a member's own records and those of the options of the run; no value is checked against the datum that it cites; an error for a missing record has no line, and some places read as list indexes (`service.members[7]`)
  - [x] the report (`b1/c-report/STATE.md`): `report(record, program, configuration, paths, times, lags=None, model=None)` in `napkin/engine/report.py` gives each value with its unit and its label; a status display as `Shown(rating, text, case)` (its cases lower and run; `later_slice` is gone); a lag `Lag(shortest, longest)` in hours as the mean of the history over its window (before 0 h, the 0 h value), or "the lag is refused: X can fall: <reason>"; the evidence trail, each part with why (it cannot start under this configuration, it did not start, it moved nothing); the near-ties; and after a pause or a failure, `Unavailable` values and when and why it stopped. The never-falls proof is `napkin/program/proofs.py` (`Proofs(program, configuration).never_falls(key)` with its reason), the old cumulative rules member by member over every flow, stage, move and solver; it skips events that cannot start, does not count setup writes, and takes a sign only from a stored number's bounds (not an input's: conservative). Near-ties: a firing, a stage guard, an `if` or a case guard decided within the tolerance of what it reads carries `near` in its trace entry (for a trigger, if its sides still agree 1e-6 h later, so a crossing is not marked); `Record.near_ties()`. Ported and deleted: the five report files of `tests/engine/` and `tests/model/test_categories.py`; the old peaks, group summaries and report schema retired
  - [x] near-ties marked since (`b1/near/STATE.md`): four trace kinds, each written only with `near`: `miss` ("this trigger came within tolerance of its threshold and did not fire", once for each arming unless its near-ties change, a memory rebuilt from the trace so that a resumed run agrees), `skip` ("this guard was false within tolerance of its boundary, and the stage ran nothing"), `release` ("this gate released its occurrence within tolerance of its threshold"), `settle` ("this split of who is served was decided within tolerance of its boundary", at each settling and in round zero); only a term that decides is marked; a gate that stays shut is not. Left: a split decided inside a way between moments (a hook in `run.py`). Before: For C-S: `napkin/model/analysis/values.py` goes once `study.py` and `session.py` stop importing it. For C-K: the `sample_result` export of `napkin/__init__.py` and `engine/__init__.py` names nothing
  - [x] draw (`b1/c-draw/STATE.md`): `napkin/draw/` reads the compiled model through one module, `things.py`; `model_map`, `triggers`, `notation`, `symbols`, `equations`, `style` and `panels` are rewritten on it, their TOML reading and LaTeX output kept. A diagram now shows: a table's rows as one card marked xn, a member written by hand as its own card, no card for the top level; stocks and tallies by use, a stored value that nothing writes as fixed; events that reachability proves cannot start left out of `--run` and of the picture of all runs; a flow's `request(f) = r` with `f <= c` (`|f| <= c` for a route), an endpoint's `outflow(S) <= c` and `priority(...)`; event lines such as "when C, once", "again after T", "the setup starts it", "never: nothing starts it"; a solver's unknowns as "solves"; no "compared with". `tests/draw/` is live (804 tests; one needs TeX); its new `test_catalogue.py` waits for M. For C-K: `commands/draw.py` still reads the old `model.runs`, and four tests of `napkin compile` and `napkin draw` stopping on stylesheet problems were dropped and need writing again. For M: `tools/publish` imports `filled`, which is gone. Optional: a `Compiled.library`, so that draw need not read the library again from the entry file
  - [x] dynamics (`b1/c-dynamics/STATE.md`): `VectorField(program, configuration)` reads the rates of each moving set from the instance that the engine builds for it, a component or the sparse integrator; continuation over an input or `t`, thresholds on `engine.run`, sensitivity over inputs. Another start value is another program (a configuration sets inputs only). `tests/dynamics/` is live (55 tests; two cusp thresholds `deep`); the six tests of `scenarios/cyber_learning_loop` that use dynamics wait for M. For later: the recorder fits every flow's rate in a segment even when its request holds one value, most of a cusp run's time
  - [x] near-ties (change 10): firings, guards, branches, case guards, misses, skips, releases and the splits of a settling are marked, and the report shows each one; `where` over an endpoint's flows runs in both halves (entity flows, occurrence flows as they join and leave, the legs of a route; `source` and `sink` compare by identity with a stored number; rates are refused, and such a `where` in a solver whose endpoint's members change), which the oracle does not cover (it reads an end as its stored amount and crashes on a flow to SINK). The five bugs of the cleanup fixed: the expression parser rewritten (nesting deeper than 150 refused as `deep`; a sum of more than 150 terms becomes one `sum(...)` with the same bits; a longer product refused), two `record` lines of one name refused, a note's missing record refused, `duplicate_name` for a value and an event or flow of one name, and the spec's assertion over the sum of two moving stores runs on held rates and on curves
  - [x] P1, other solvers (`p1/FINDINGS.md`, `briefs/p1-solvers.md`): the engine's distance problem was harder because a store held at [0, 0] is two `<=` rows (Newton system 316k against 233k unknowns, each factorization 2.79 s against 0.69 s); merged into one equality, 377 s with SuperLU and 81 s with qdldl at 30,000 places, where before it did not finish in 15 minutes. qdldl (Apache-2.0, wheels for CPython 3.8 to 3.14 on Linux, macOS and Windows, x86-64 and ARM) in the library's exact method: 827 of 827 exact cases, 4.6x faster at 30,000, answers within 6e-7. Fair sharing in connected parts: exact, damaged 693 programs to 22 (174 s to 67 s). Kept: SciPy's HiGHS, the primal simplex, tolerance 1e-10 with renewals, FIX 1e-7, UPDATES 100. Not adopted: Clarabel, PIQP, OSQP, qpsolvers (an IPM stops about the square root of its tolerance off a bound that holds with no multiplier: the pump serves 6.00017 for 6; they fail on the engine's faces and on x1.45 and x1.7). Tolerance 1e-7 removes the renewals but stops one of 60 small networks by name; FIX 1e-6 moves levels by up to 1.5e-3. All methods repeat bit for bit with one thread
  - [x] the three pure speedups adopted (change 18): a store held at both bounds is one row `== 0` (`declared.py`); qdldl LDL' in `distance.py` (pattern analysed once a stage, two refinement steps), a stage going on by SuperLU at its first solve whose backward error is above 1e-10 or a factorization qdldl refuses, and run again by SuperLU alone if LDL' leaves it unconverged; connected parts in one fair program, one level variable each (`fair.py`). `qdldl>=0.1.9,<0.2` in `pyproject.toml`, `qdldl==0.1.9.post1` in `requirements.lock`. Exact resume holds three ways with held stores and parts. Times: the distance step after fair sharing at 3,000 places 2.1-5.3 s to 0.7-1.5 s; 30,000 normal, the whole order about 500 s to 205 s (fair 155, distance 45); 30,000 damaged 65 s for the whole order (22 programs, not 693); the engine's bench at 3,000 31.7 s to 18.2 s; at 30,000 its first solve 166 s, where it did not finish in 45 minutes. Under shortage at 30,000 (need x1.45, x1.7, and the bench's second solve) the distance step still does not finish in 15 minutes. The plan for the rest: `docs/scoping/solver-speed.md`, with a row in `docs/known-issues.md`
- [x] S7 breakpoints, checkpoints and edits (`briefs/s7.md`, change 15)
  - [x] the front end, M1 and part of M2 (`b1/s7-front/STATE.md`): `canonical.decode` reads canonical bytes back; `napkin/program/artifact.py`, a versioned file (a header `napkin program 1` and `language 0.1.0`, then the program's section with its size and SHA-256, then the side table's section), whose loader refuses by name what is no program (`not_a_program`), another format (`format_version`), another language (`language_version`) or a damaged file (`damaged`, also a record whose fields differ from this napkin's); `Artifact.digest` names a program. The compiler gives the side table (`Compiled.table`, `Compiled.artifact()`): each part with an origin, its kind and source place (columns counted from 1), each value's name, label and evidence. A fresh process loads a program without `napkin.model` and gives the same bytes and the same record; a label, a record or a moved line changes neither the program nor the model hash. `choose(...)` and `sees` are refused by name (`choose`, `sees`) with the idiom; the acceptance example `pump_dispatch` and its stops (`PAUSES`: untouched, sends, no spare, two stops) are in `examples.py`; the oracle has breakpoints and edits (resume reruns the paused stage with its draws, then applies the edits in order). Draw's choice cases, its actor badge and "Decides" mark are gone; three test models now draw a field `order` and switch on it
  - [x] M3 of the contract: `refs.Choice`, `Template.sees`, the controllers and picks of `config.py`, `build.choose`/`sees`, `views.actors`, the four `dispatcher_*` examples and the oracle's choices are gone; `FORMAT_VERSION` 2. The evidence rule (change 16): `napkin/model/support.py` adds a `no_record` warning for each part without a record; `napkin compile` lists each with its place, the other commands print `warning: N values have no record (napkin compile lists them) [no_record]`, their `--json` keeps them all. The evidence gaps: `model_document` reads every file of a package; `proofs.reads` follows a stage that assigns a flow's request or capacity; unnamed parts are named as the model names them (`status.case[0]`, `assert[0]`); `DeclaredModel.evidence(origin, member, options)` for the trail. Left: checking a value against the datum that it cites; `napkin/commands/play.py` still imports `views.actors` (no live test calls it)
  - [x] the engine, M1 to M3 (`b1/s7-engine/STATE.md`): `run(..., breakpoints)`, `Run.resume()`, `resume(program, checkpoint)`; `Checkpoint.edit` and `Run.edit`, and the trace kind `edit`; the report refuses a lag when an edit lowered the value. Choices, controllers, picks, `sees`, `Paused` and `resume(*picks)` are gone from the engine; the four player-only test files deleted (`test_pause`, `test_play`, `test_timeline_play`, `test_settled_decisions`), five ported. Exact resume holds bit for bit on 11 cases run three ways and the four edited acceptance cases, among them a tank that crosses its threshold at 10 - sqrt(50) h between stops at 2.92893 h and 2.929 h, on the continuous engine and on the sparse integrator; the fresh process is a subprocess under another hash seed that loads S7-F's artifact. What carried numerical state across a moment: the sparse integrator's Radau steps (when a moment falls at the end of a step), the kept HiGHS instance and its last problem, the line anchors of the family, the lines and a solver's lines, values captured when an instance is built, the order in which plan values are named. Resume in a fresh process replays the run to the stop and checks the stop, the state and the record against the checkpoint (in one process the stopped stage reruns in place). The checkpoint: text, `napkin checkpoint 1` then JSON of named records; the program named by `Artifact.digest`, the engine by the SHA-256 of its code. At 3,000 places, stopping at 22 h of 24: 28 s to the stop, 43 MB (written in 4.3 s, read in 3.7 s), resume 37.7 s (straight through 27 to 33 s); breakpoints cost nothing on an uninterrupted run
  - [x] restore, as the owner chose (`napkin/engine/timeline/saved.py`): a fresh process rebuilds the run from the checkpoint's saved state and goes on, running nothing before the stop again. Saved as data: the order of the plan's names, the values and the record so far, the line anchors, what each instance captured when it was built, each solver's program, basis and last problem. Restarted at every moment on every path: the sparse integrator's Radau solver and a moving solver's segment; HiGHS solves after each round's stages on a fresh instance with its basis (about 6% on S5's network at 3,000 places). The guard refuses by name a checkpoint whose restored state differs from its saved state. Exact bit for bit on the 11 cases and the four edited acceptance cases, three ways, the crossing at 10 - sqrt(50) h included. At 3,000 places stopping at 22 h of 24: 72.3 MB (written in 6.9 s, read in 5.0 s), restored and run on in 7.1 s (the replay took 37.7 s; straight through 26.9 s). Edits by record key in the declared unit or by engine name in canonical units; an edit of a store enters its record as `<store>.external`, the running total from outside. Fixed: a reader of an equality that a solver enforces compares to 1e-7 relative (a floor of one canonical unit); an enum, text or yes/no in a moving rate stays as it is; `expm` in numpy (Padé 13 with scaling and squaring), a chain of three compartments 12 s to 0.16 s. The trail calls `DeclaredModel.evidence` through `report(..., options=)`; an edit withdraws reachability's "cannot start"; `choice` and `LEFT` removed. Left: `commands/run.py` passes no options to the report yet
  - [x] the session and `napkin play` as clients of the checkpoints (`b1/s7-play/STATE.md`): `napkin/session.py` stops at breakpoints and shows the stop (where, which occurrence, what runs next, the values asked for with units and labels), takes edits, saves and reloads a checkpoint, and keeps a log of stops and edits that `play` plays again to the same run (a log that does not fit is refused by name). `napkin play` prints each stop ("Stop 1 at 0 h: before ... (switch at model.scn:21), in depot.request_pump#0 of depot."), what runs next and what the stage drew, and a table of values with their units, what an edit can give them (`edit: SEND or WAIT`) and labels; the user types `PATH = VALUE`, `save FILE`, `go` or `quit`, and sees `napkin run`'s table and one line for each edit at the end. The run store keys a run with edits by its breakpoints and edits, keeps the log, and resumes through the engine. `napkin run` passes the run's options to the report. `tests/test_session.py` and `tests/commands/test_play.py` run `pump_dispatch` unattended, saved and resumed untouched in a fresh process, and with `order` set to `SEND`; `tests/engine/test_decision_resolver.py` deleted, its rules that still hold in the session's tests. `napkin/model/analysis/` deleted (nothing imported it); `pyproject.toml`'s packages no longer list it, nor `napkin.model.lower`. Left: the play fixtures of `tests/build.py` serve no test; `docs/cli.md` (F)
- [x] the dormant list cleaned (`b1/cleanup/STATE.md`): of 26 old files, 18 ported and live (`tests/model/` and `tests/test_check.py`: 279 tests and 14 strict xfails that hold the bugs found), 6 deleted (`test_desugar`, `test_kept_parts`, `test_resolved`, `test_start_states`, `test_structure`, and `test_list_reductions`, whose cases were live elsewhere), 2 wait for M (`test_scenario_ownership.py` imports `tools.publish`; `test_scenario_scope.py` reads the catalogue). The list now holds only tests that read the catalogue, and the session's two. Bugs found, each a strict xfail: a deep expression ends in a `RecursionError` (about 150 nested brackets, calls or choices in `parse.py`, a sum of 700 terms in `semantic.py`); two `record shared:` lines are accepted, the second replacing the first; a note may cite a record that does not exist; `go: L = 1 L` then `go = event():` crashes with an `AttributeError` instead of `duplicate_name`; the spec's assertion over the sum of two moving stores compiles, then the run stops at 0 h as not certified
- [x] M made ready (change 17; `b1/m-prep/STATE.md`, handover `briefs/m.md`): `a5/translate.py` writes the language of now into `a5/translated/now/` (`--compile` compiles each entry file); 6,918 of 6,960 lines mechanical (99.4%); the reservoir 47 of 49 lines and compiles with no warning; the water model's jamestown 1,216 of 1,220 lines, refused with 7 problems; 32 library units cannot be spelled from their parts. `a5/check.py OLD NEW` compares meaning (compile, number, text, kind, flow, cumulative proved never to fall by `proofs.py`), passes on `examples/piano_tuners` against `8488047`, refuses four wrong copies each in its group. `tools/check.py` has a stage `Evidence` that refuses a package with a `no_record` warning (with `--scenario` and `--all`); `tests/test_check_evidence.py`. Things that have no place in the language go to `notes:` under what they were. For the owner, at M: 21 empty outcomes cannot become a `switch` case (a case needs an action); members have no `title`, events no `role`; `timescales` that name values are refused; a template-level cycle on `Utility.tie_asks`
- [x] Gate G2 (2026-11-19): `pytest -n 4 --no-focused --scenario-selection '' -m 'not deep' tests` gives 5,979 passed and 2 skipped (TeX and Ghostscript are not installed) in 126 s; ruff check and format are clean on `napkin/`, `tests/` and `tools/` (the prototypes of `scratch/` are not linted, and go in F); `tests/dormant.txt` holds only tests that read the catalogue (11 entries). This session stops here (change 17). M starts from `briefs/m.md`.
  - Open at G2, for later stages (each named above where it was found): the questions for the owner that M raised (an empty `switch` case; `title` of members and `role` of events; `timescales` that name values; the template-level cycle on `Utility.tie_asks`); distance answers under shortage at 30,000 places, and fair sharing's one program per level (`docs/scoping/solver-speed.md`); a split of who is served decided inside a way between moments is not marked as a near-tie; every trigger is read at every moment and finished occurrences' caches are kept (the event bench at 30,000 places: 866 s, 2.9 GB); 2,948 two-store components run alone (S3's moving bench); a value is not checked against the datum that it cites; the oracle does not cover `where` over flows, and catches a followed request below zero only at the next moment; three tests take 12 to 13 s without the mark `deep`; `docs/` describe the old language (F)
- [x] After G2, the audit (changes 19 and 20): a solver decides only what it names (the worked junctions with an upstream-only solver keep 1/2, 1/4, 1/4, in the engine and the oracle); two full tanks in series pass room; a small request survives the polish; an idle pipe stays idle; a vanishing request no longer crashes the sparse integrator; a self-move leaves its store; a stage whose commit fails is discarded whole; a replaced distribution is drawn new; an action at a horizon reached by two waits runs; an unrecorded flow reads "not recorded"; an edit withdraws the never-falls proof for what rests on it; nothing reads past a pause; an empty case, a member's `title`, roles refused for the wrapper, `timescales` retired, cycles checked on the members' connections, ranges compared in one unit, impossible distribution parameters refused; triggers on values that rise and fall certified step by step (`napkin/engine/continuous/dense.py`), so the reservoir runs. The migration checker runs both models (its group `run`), and the translator writes the owner's decisions (99.7% of the catalogue's lines). The central suite: 6,088 passed, 2 skipped; every deep set of the engine passed once on the final code. Handoff for M: `HANDOFF.md`
- [ ] After the re-audit of `0f78c65` (change 21, `briefs/audit2.md`, `audit/reaudit-0f78c65.csv`): five causes behind its 22 rows, each fixed in one mechanism, with a test of the rule that would have caught every instance
  - [x] K, the migration checker compares how each run ended (finished, failed or paused; where and why) before its values; a new failure or pause passes only when `changed.md` lists it (`a5/test_outcomes.py`)
  - [x] D, the front end: a quantity is its dimension and an exact scale however it is spelled (rows 12, 22 and the cyber draft's `sqrt`); an occurrence reference is a typed local and a formula reads only what lives as long as it does (14); a fixed key selects its member (15); a value that cites a datum equals it exactly, else a `datum` warning that `tools.check` refuses (17). At merge the datum's tolerance of half a digit went: a datum states no precision, and the docs and the old compiler require equality
  - [x] A, the selection order (rows 05, 06, 07): an endpoint's rule ranks all its flows, named by a solver or not (`network.claim_order`, for local sharing and every solver); a change to an answer after the solve (the polish, every snap) is kept only if it passes the solve's end checks and is no worse on any rank (`solve.Answer.admits`); structure is read from what can carry flow at the instant (`network.carrying`). New stop by name: a ring of empty stores reached by a flow the solver does not name (4 of 1,000 random solver programs); 9 random programs change values, engine and oracle agree. Rule tests `test_claim_order.py`, `test_published_answers.py`, `test_closed_connections.py`. Found on the way: `Kept.set_bounds` sent a column twice, and HiGHS refused it silently
  - [x] B, time and evaluation (rows 04, 13, 15): one clock (`moment.Clock`) for every time built or compared, durations summed exactly and rounded once, what is due fixed as a moment begins; one driver on an explicit stack (`plan.walked`) for every walk of the graph; bounded distributions' moments by quadrature in the tail and closed forms without cancellation, against mpmath. With D's engine half: exact scales, occurrence references bound at entry, a constant key reads its entry alone. Rule tests `test_clock.py`, `test_deep_graphs.py`, `test_bounded_moments.py`, `test_references_and_keys.py`
  - [x] C, records and reports (rows 09, 10, 11, 15, 16, 18, 21): one rule of what a record holds (`Record.unavailable`), followed by the reader, the trail, the store and the report, `Unavailable` with the reason for anything else, every edited store's ledger kept; each value read at its own time; an edited run's proofs derived again with each edit as one more writer (`Proofs(program, configuration, changes)`); exercised is what an evaluation read; only a number is lagged, a window before 0 h is unavailable (change 22); the history budget enforced; the reader iterative. `commands/run.py held()` offers only what the manifest names. Rule tests `test_record_claims.py` (230)
  - [x] The merge: the central suite on the combined code, 7,252 passed and 2 skipped; its one failure, the pinned list of files that the run store digests (`test_api.CLOSURE`, which gained `program/check.py`, `proofs.py` and `reach.py` because the record's reader imports `proofs.always`), updated. Every deep test, 14,984, passed once on the combined code (4 min 26 s)
  - [x] An independent check of the fixes, by variants of the re-audit's rows run from source that no agent's test uses (three ranked consumers with each subset named by a solver; a ring of three full tanks closed, then opened at 2 h; an enum edit that enables a drain; an edited store under four requests; a failed run read at permuted times; a history budget; lags of a yes/no and a text; a far-tail normal and lognormal against mpmath; a formula's untaken branch in the trail; respelled units and horizons). Each held, but two that showed a cause still acting where two fixes met, each fixed in one place with a rule test that fails without it: a request's horizon is held as the clock holds a time, its exact value rounded once (`Request`), where the record had compared a caller's float 7.2 with the exact 36/5 and found the horizon passed; and a units file's float is read as the number that rounds to it written with the fewest digits (`core.units.scale_of`), so the library's 1/24, 1/8760 and a minute's 1/60, written out as floats, are their ratios again (the respelling property now runs with the units as a file holds them). The central suite after them: 7,263 passed, 2 skipped; every deep test, 14,984, passed again (4 min 31 s); the migration checker's own check (`a5/run_all.sh`) passes. Dead code noted for F: `napkin/model/types.py` (`time_units`, `hours`) and `uncertain.py` are the old language's, and nothing in a run calls them. Left open, optional: the engine's own evaluations (a trigger's condition, a stage's guard) record no read set, so the trail gives no exercised mark for a part read only there (C's state file, "For B")
- [x] After the readiness audit of `8b3a01a` (`audit/readiness-8b3a01a.csv`, `briefs/audit3.md`): 8 of its 22 rows partial. The main session's reproductions (`audit/repro-8b3a01a/repro.py`) showed 7, worse in one (300 chained formulas did not compile), and row 16 only by a property. Why they got through: each agent listed the places of its cause in its own files, each rule test ran one path, and a departure from the spec was merged (an interval that only a run knows tested as written). This round each agent searched the whole repository first and wrote each rule test first, failing, across every path that the rule governs, combined with edits, budgets, store cuts, resumes, lags and trails
  - [x] F, the front end (rows 12, 14, 15, 17, and change 23): a membership is one checked operation of the program (`within`, `ops.REVERSED`) in every evaluator; a formula's lifetime is its resolved target's owner, whatever spells it; a cited value is compared as the compiler folds it, a value only the run computes warns, a number token is its exact decimal; names resolve on an explicit stack, arrays and faces walk in loops, chains of 5,000 links compile at a recursion limit of 400; a named collection may name another; the parser refuses `role` everywhere
  - [x] E, the engine (rows 14, 15): a finished occurrence fails the run on an actual write (change 24 b: an assignment, a move or a flow beyond its store's tolerance), in one check, the oracle too; a named collection is the collection that it names in every reduction and lookup; the run on chains of 5,000 links; a rate read at the horizon of a run is the rate a longer run reads there (`ways.finish`), but a curve's jump within the crossing tolerance of a horizon where nothing else is due
  - [x] R, records, reports, solves (rows 06, 11, 15, 16, 18): every rank is checked when an answer replaces the solver's, the distance to the targets included, in the solver and in local sharing (`solver.farther`); the budget is applied as the run goes (`OverBudget`: no checkpoint past it) and one rule decides what a record holds (`record.requested`), so a cut of a stored record equals a fresh run of the shorter request, histories included, and a shorter request on moving values runs fresh (change 24 a); a trail follows (name, time) pairs; proofs, lags, the reader, `declared` and `family` walk on stacks; a reversed membership in a solver's constraint fails by name; a restored component keeps its bounds and faces; near-tied rows of a solve rerun tight
  - [x] S, pictures (change 23): `napkin draw` takes roles from `style.toml`'s `[role]`, each of 13 test pictures as before; `napkin new` writes the stylesheet (change 24 c); the translator moves the catalogue's 59 roles to `style.toml` and `roles.toml`
  - [x] N, pictures: a membership is drawn `x \in [lo, hi]`, in the equations and on the cards
  - [x] The main session: `napkin compile` summarized four of the six kinds of value and raised a KeyError on a link (every kind has its group now); every property test draws the same examples on every run (a seed from the test and no database of earlier examples: 7 of the 36 had no seed, and the database replayed examples of other code); `tests/acceptance/test_rules_across_paths.py`, written apart from the agents: long chains on every path at a recursion limit of 300, a trail independent of its report on 200 random models, one outcome cold and warm with a later edit, no checkpoint past a budget, each failing on `8b3a01a` and passing now
  - [x] T: change 25 (`e529a1f`): a rate that the settling decides, read in a stage after something it depends on changed since the flows last settled, stops the run by name, for every flow, through every set whose rates its settings read, also with a stop and an edit resumed in place and from the saved state; 235 of 413 random cases against the oracle failed before. The main session: a range test in a solver's constraint stays a membership (`8282d72`), so ends that a stage reverses stop the run by name
  - [x] C (`13b06cc`, change 26): a moment's own changes (a key time, a switch that a way's state reaches there) make the rates that depend on them stale in its stages, judged for each part of a set that shares stores; the check covers firings too; a segment that starts at a switch starts on its far side (`integrate.far_sides`). From the review: formula locals of an occurrence have no value until read (R03), the oracle checks parameter ranges (R06), one writer of a value in a message in its declared unit (R08), a moving solver unknown in a trigger is refused by name (R09)
  - [x] L (`1564ac7`): the rates after a moment are those of the state just after it, in the engine and the oracle, or a named failure; zeros stay at a [0, 0] junction; rings refused after the setup; an endpoint that only a stage names. From the review: a moving declared set reads trial states within bounds and fails at its time, record kept (R10, R12)
  - [x] A fresh review of `2cd1751` (`audit/review-2cd1751/findings.csv`): 12 findings, each reproduced by the main session, given to C, L and V
  - [x] L, continued, and V (`4d78f92`, `147ddc5`): the sparse integrator at a switch; a route's fulfilled fraction within [0, 1] (spec.md:246, 546); a solver with no answer just after a moment stops by name; formula locals at their source; a capacity left out that a stage sets; a stop at a setup statement resumes in a fresh process; a set whose endpoint a stage configures. V: a solver's unknown read in its unit, every named value reportable, `napkin compile` on legs, the key fields of a keyed read in a selective record, messages in the model's notation
  - [x] The merge (`678df65`): the central suite on Linux (one stale closure list fixed); the deep sets of the round's rule tests failed in C's clock test (13 of 2,000 on macOS): missed stops, small switch-timing differences, and results that depended on the machine
  - [x] Change 27 (owner): rates and results read as the round began, `after 0 h:` to read them after a round's changes, replacing the stops of changes 25 and 26; then one rule for a contact at a moment's time in every engine, reported as a near-tie (change 10), switches located on the arriving trajectory, change 28 (the store reuses an identical request), the planner's quadratic walk fixed (planning at 3,000 places 4.2 s to 1.2 s), and a refactor that writes each shared rule once (`codex/freeze-rates`, reviewed and fast-forwarded to `6bfc700`). Central suite green on Linux and macOS, the deep selection green on macOS (6,631) and its clock and switch cases on Linux (2,044); the near-tie inventory unchanged by the refactor, entry for entry; the benchmark within 1 % of the baseline; the engine +1,169 lines against `678df65`

- [x] After the readiness audit of `6f297e5` (`audit/readiness-6f297e5.md`): change 29 (tolerant comparisons, with the floor of the larger declared scale that the two sides read; a single store put on its threshold at a located crossing), the frozen store's cumulative allowance, an idle route carrying exactly zero, every named value reportable, the run store keyed on its stops and edits, exact JSON evidence, language `0.2.1`; then the fitter owning the history budget (a run stops at the first excess piece of its complete record), one departure decision after a crossing in every engine, comparison scales through expressions (`codex/readiness-audit-6f297e5`, reviewed and fast-forwarded to `ad690c3`). Central suite green on Linux and macOS, the whole deep set green on macOS (23,547) and its timing, budget and cross-engine cases on Linux (2,094); the engine +1,953 lines against `678df65`. The auditor reruns the bundle next
- [x] After the audit of `8e422da` (the reservoir accepted as the first port; six findings): a switch that leaves its threshold at rest, settings of event-local declarations, mixed-magnitude transfers conserved, a frozen allowance counted the same however the run is split, proofs and folding by resolved values, the evidence gate refusing what it cannot compare, evidence through sums, filters and lookups; language `0.2.2` (`codex/readiness-audit-8e422da`, reviewed and fast-forwarded to `8735cb0`, then two lagged values in the spelling tests compared within roundoff after they failed on Linux only). The engine +225 lines this round
- [ ] M catalogue migration
- [ ] Gate G3
- [ ] F finish

### Changes after G0

These override the text of this plan below, wherever the two differ. The owner's record
(`g0-decisions.md`) overrides both.

1. **The spec.** `spec.md` is the proposal settled at G0. The prototypes' translations and the oracle
   used spellings that G0 replaced (a separate `chance(...)`, `none`, a report block, `size`, `^`
   in units); they are made again where they are used.
2. **Local sharing.** Each endpoint shares among its own flows by its own rule, by default. Fair
   sharing across endpoints happens only inside a declared solver. The solve library serves the
   declared solvers. The network of S2 computes local sharing, also when [0, 0] junctions and full
   or empty stores make several rates depend on one another.
3. **Moving rates at any size (D3).** Choice 2 below changes. A large connected set whose rates read
   moving quantities runs on a sparse integrator (A4a: 60,000 stores to 48 h in 32 s while no store
   rests at a bound). Holding rates between moments is an optimization for a set in which nothing
   moves. Nothing is refused for its size: a large model may stop with an explicit failure of
   time, memory or accuracy, and its size never changes its equations.
4. **Solver budgets (D0)** count deterministic work (linear programs, iterations), never seconds,
   so that a run that succeeds on one machine succeeds on another.
5. **No required publisher (D9).** Stage C does not port `tools/publish` as a requirement of the
   repository. What happens to it and to its committed outputs is asked of the owner at stage C.
6. **Reachability is kept (D16).** The analysis of `napkin/model/lower/starts.py` (what can fire
   under an effective configuration) is ported as proof metadata, not retired. Pruning work by it
   is a separate optimization. The old file went with `lower/` at the switch of S0; port it from
   commit `81b367b` in S4, when events and named states exist.
7. **Reports (D10).** No `output`, no report block in a model. The caller selects paths and times.
   A lag needs the never-falls proof.
8. **Inputs (D2).** An override follows the declared type; a distribution-valued input exists.
9. **Worktrees.** The tracks of B1 work in the main checkout, each in new directories that no other
   track touches, because the harness makes an agent's worktree from `main`, not from this branch.
10. **Priorities (owner, 2026-11-19).** Defensibility first, then speed, then precision; choices
   between methods, tolerances and budgets are weighed in that order.
   - Defensibility: every number traces to a stated rule and its evidence; the same run gives the
     same result again; a run that cannot answer stops with a named failure instead of a quietly
     different answer (D0's "never another allocation" is a rule of defensibility).
   - Speed: people explore a Fermi model, rerun it, sample it and change assumptions, so a run of
     20 minutes is not used. This argues for interior-point solvers, fewer fair-sharing programs
     and parallel samples.
   - Precision: inputs are uncertain by tens of percent, so 1e-7 against 1e-10 means nothing. The
     tolerances of R-A3-02 (1e-7, and 1e-10 in fair sharing, which is part of why HiGHS failed at
     scale) and of integration may be loosened, keeping exact the precision that is defensibility:
     - conservation: the books of each store balance;
     - equal treatment: two equal claims get equal shares;
     - bounds and never-falls proofs: a store stays in its range, a cumulative value never drops;
     - discrete outcomes: where a tiny difference flips a trigger, a branch or who is served, the
       engine does not compute more precisely; it detects the near-tie and reports it ("this
       trigger fired within tolerance of its threshold").
11. **Reproducibility (owner, 2026-11-19).** The same run (the same code, configuration, seed and
   thread settings on one machine) is deterministic. Anything else (a sample alone or in a batch,
   another solver, another platform) agrees within the stated tolerances, not bit for bit. A
   threshold that sits at a tolerance boundary may fire differently across those settings; the docs
   say so where they state the tolerances (stage F). This replaces the bitwise requirements of A3
   ("sample k alone and in a batch"), of the solve library (`briefs/b1-solve.md`,
   `b1/solve/STATE.md`, `tests/engine/solve/`) and of R-A4b-05: an endpoint's exact sum stays as a
   way to be deterministic, not as a promise of bits equal to a problem formed fresh. Tests compare
   across settings within the tolerances and test the same run for identity. Stage C applies it to
   the tests that it ports which compare a sample alone with one in a batch, or one process with
   several (`test_spread.py`, `test_monte_carlo_study.py`); a test of the same run, or of a pure
   refactor, keeps its bits.
12. **No `delayed` (owner, 2026-11-19).** `delayed(x, D)` leaves the language: an unnecessary
   complication. No model of the catalogue and no worked example uses it. The front end refuses it
   by name, the program, the engine and the oracle lose it, and R-A2-09 (`delayed(x, 0 h)` reads the
   committed value) is moot. A delayed observation is modeled by an event that waits and then
   writes. `elapsed` and the caller's reporting lag (D10) stay.
13. **The publisher (owner, 2026-11-19).** `tools/publish` stays as an optional tool and is ported in
   stage M, over the new record, once the catalogue is migrated; its 110 committed outputs (each
   scenario's and variant's `brief.md`, `methods.md`, `runs.csv`, `runs.json` and two review files)
   are made again then. No drift check is required. Stage C does not port it.
14. **Tallies (owner, 2026-11-19).** A tally is known by use: a store that nothing drains. No mark.
   A store at a route's end is a stock by use, so only `SOURCE` and `SINK` are refused there.
15. **Breakpoints, checkpoints and edits replace player machinery (owner, 2026-11-19).** The compiler
   gives a versioned, loadable program that the engine runs without the parser, with a side table
   that maps each executable location to its event, stage, statement and source place, and values to
   names, labels and evidence. A caller sets a breakpoint at a location of that compiled program
   (event, occurrence, stage, statement); the engine stops there and gives a resumable checkpoint
   (why, where, which entity and occurrence, what runs next) that a fresh process can load, inspect,
   edit through a documented representation, and resume. The edit is the action: no answer channel.
   `choose(...)`, `sees`, actor controllers and picks leave the language, the program, the engine and
   the oracle; this revises the actor half of D1, the G0 part "A human prompt pauses one atomic
   stage", and R-A5-14. Ordinary events, branches, guards, distributions and draws stay; eligibility
   is an ordinary guard; `readonly` keeps its meaning for the model's own assignments only.
   - Exact resume is a rule: on one supported platform, with the same compiled program, engine
     version, numerical settings and seed, stopping and resuming an untouched run gives the same
     recorded values, draw results, event times and event order as running straight through; a
     breakpoint alone never changes which branch fires. Tested three ways (no breakpoint; pause and
     resume in one process; save and resume in a fresh process), with a continuously changing value
     near a trigger threshold. No numerical state may be restarted only on the resume path.
   - Edits in v1 are to live stored values. Types and bounds hold, derived rates are recomputed, a
     finished occurrence stays frozen. An edit of a store is recorded as an external transfer; an
     edit that breaks a never-falls proof withdraws that proof for the edited run. Each edit is in
     the trace (time, breakpoint, target, old and new value). Resuming by replaying a stage's prefix
     keeps earlier edits: two pauses in one stage neither lose the first edit nor apply it twice.
   - Acceptance: the pump dispatch run unattended; paused before its branch, saved, reopened in a
     fresh process and resumed untouched, with the same values, draws and events; and resumed with
     `order` changed from `WAIT` to `SEND`, where the send branch runs once, the original draw stays
     in the history and the edit explains the divergence. "About one slice" is provisional until
     the numerical resume case passes. A wrapper such as `napkin play` is a client of this.
16. **Evidence (owner, 2026-11-19).** The compiler warns about each value without a record of the
   kinds that the old compiler required one for (`docs/language.md` 2.10 at `8488047`: an input but
   a text, a stored value, a timed event, a status, an assert, an instance value, a column of a
   table); the report marks each in its evidence trail; `tools.check` and the publisher refuse a
   scenario package with any. A model being explored still runs. A number, a yes/no or a
   distribution that an option or a `change` sets needs a record, an error as now (R-A5-05).
17. **This session stops at G2 (owner, 2026-11-19).** M, the migration of the catalogue, is a later
   session. Everything up to G2 is done here, and M is made ready: A5's translator and check script
   brought to the language as it now is, the steps to rebuild the old compiler's worktree
   (`git worktree add /home/user/napkin-base 8488047`), and a handover in `briefs/m.md`.
18. **Speedups (owner, 2026-11-19).** Once P1 reports, the speedups that change no answer go in
   before G2: those that give the same answers up to roundoff, such as merging a store held at
   [0, 0] into one equality row, `qdldl` in the exact distance method (a new dependency, if its
   license is permissive and it has wheels for the platforms), and fair sharing split into
   independent pieces. What trades precision or robustness for speed (a looser fair tolerance, an
   interior-point path) and precision profiles (`default`, `fast`) are deferred to a written plan
   that outlives `scratch/` (`docs/scoping/solver-speed.md`): P1's measured tables, what was
   adopted and why, the profile design (named profiles in the run's identity, invariants exact in
   every profile, fallback by name, published runs on `default`), the open case (need x1.7 at
   30,000 places), and the commit that holds P1's scripts.
19. **The audit after G2 (owner, 2026-11-19).** An audit of the branch raised five questions and a
   list of bugs whose answer the spec already gives. The owner's answers:
   - **Solver scope.** A solver decides only the rates that it names in `solve_for`. A flow that it
     does not name keeps its endpoints' local sharing; the solver sees it only through the limits
     that it imposes, so that it still conserves; to take over who is served, the provider names
     those rates. In the worked junctions (spec, "Local allocation") a solver that names only the
     upstream feed leaves 1/2, 1/4, 1/4. This reverses S5's "a flow that shares a store with a
     solver's flow is in that solver's calculation", in the engine and the oracle, as the spec says:
     "Flows that no solver determines follow their own endpoints".
   - **An empty case.** A `switch` case may be empty, with or without a text.
   - **Titles and roles.** A member may have a `title`, model text kept with the labels outside the
     program's identity, which reports and playback show. An event's `role` belongs to the
     scenario's wrapper (its UI or `brief.toml`); the model refuses it with that hint. Neither is
     lost silently.
   - **Timescales** are retired: refused, with the message that the engine chooses its own steps and
     a run that needs finer ones sets `max_step`. M confirms on the heat-wave and cyber models that
     their results meet their accuracy without the hint.
   - **Cycles** are checked on the members' actual connections (links are fixed when a model
     compiles: R-A1-30); a real cycle is reported as its chain.
   - **Before the migration branch starts**, the bugs are fixed on this branch, each with its failing
     example as a test, and the migration checker gains a step that runs the old and the new model to
     the horizon and fails on a difference that the package's `changed.md` does not list.
20. **Triggers on values that turn (owner, 2026-11-19).** A continuous condition whose value can
   rise and fall between moments (the reservoir's `water >= level`, filled by a storm and drained by
   a spill that grows with the water) is certified step by step, not refused. In each integration
   step: far from the boundary, one comparison of the distance with the most the value can move in
   the step skips it; near it, a step in which the value's rate keeps one sign is certain from its
   ends, and a crossing is found by bracketed root-finding on the integrator's own dense output;
   where the value may turn near the boundary, the step is halved, reading the same output (no
   extra integration and no new rates), until each piece is certain or shorter than the time
   tolerance. A value that comes within tolerance of the boundary without crossing is a near-tie
   (change 10). What still cannot be certified stops the run by name; nothing polls at fixed times.
21. **Causes, not cases (owner, 2026-11-19).** A re-audit of `0f78c65`
   (`scratch/rewrite/audit/reaudit-0f78c65.csv`) found that the fixes after G2 cured the cases the
   first audit named and left their causes: 7 of the 12 entries that pass have a close variant that
   fails. The owner asked that each cause be fixed where it lives, not each case. The causes and
   their owners are in `briefs/audit2.md`: the selection order and every change to an answer after
   it; time and recursive evaluation; what a record holds and what a report claims from it; units
   and lifetimes in the front end; the checker's run outcomes. Each fix comes with a test of its
   rule, a property or a metamorphic test that does not lean on the oracle, beside the audit's
   rows.
22. **A lag before the run (owner, 2026-11-19).** A reporting lag shows a value as it would be
   reported some hours after it happens. A window that reaches before 0 h has no history to read,
   so the report gives `Unavailable` there, with the reason, and fills in nothing: not the value at
   0 h (the rule from C until this change), nor 0 (the engine before the rewrite). In the
   catalogue it touches only the first hours of `iv_fluid_shortage`, whose lagged values are 0 at
   the start.

23. **No roles in the model (owner, 2026-11-19).** An entity and a template take no `role` either,
   so no part of a model has one: the model refuses `role` anywhere, by name, and says where it goes.
   Who plays a part is the wrapper's (`roles.toml`, read by the publisher and the UI) and, for the
   pictures, the stylesheet's: `style.toml` has a `[role]` table beside its `[icon]`
   (`operator = ["pump", "Utility"]`), from which `napkin draw` takes each card's icon when `[icon]`
   names none, its "who acts" words and its group, so a picture is as it was. The translator moves
   each old role to both.

24. **Three answers during the readiness fixes (owner, 2026-11-20).** (a) Change 28 supersedes the
   rule for serving shorter requests from stored records. (b) A finished occurrence is frozen, and
   the error is an actual write to it: an assignment to
   its field, a `move` of a nonzero amount, a flow carrying a nonzero rate into or out of its store;
   a connected flow at zero rate writes nothing, and the run goes on. (c) `napkin new` writes two
   files, `model.scn` and `style.toml`, whose `[role]` gives the starter's picture its icon.

25. **A stale rate is an error, for every flow (owner, 2026-11-20).** In a moment, stages commit
   first and the flows are shared again after. A stage that reads a flow's rate (`actual_rate`, a
   leg's rate, a `served_fraction`) after something in the same round changed what that rate
   depends on (a store at its bound, a request, a capacity or an allocation that an earlier stage
   set, a flow that joined or left), and before the network settles again, stops the run by name:
   the stage, the flow and why, with the advice to read it in a later stage or after a wait. The spec
   made this an error for a declared solver's result ("a stale answer is a wrong one", spec.md:544);
   it holds for local sharing's rates too, as the reference interpreter already has it. Before, the
   engine gave the stage the earlier rate without a word.

26. **What a moment changes by itself (main session, 2026-11-20, from change 25).** The owner
   answered change 25 with "its store just hit a bound" among its examples. The same answer holds
   for every change that the next settling takes up and that no stage made: a keyed read by the
   time at its key time, and a branch on the time or on a stored value whose condition changes at
   the moment's time. A rate that depends on one of them is stale in that moment's stages, and a
   read stops the run by name. It holds for every reader, a firing's capture or start argument
   read after an earlier firing changed what the rate depends on as well as a stage. The other
   answer, to settle a moment's own changes before its stages, would also change the answer that
   the owner gave for a store at its bound.

27. **Rates and results read as the round began (owner, 2026-11-20).** This replaces the read
   errors of changes 25 and 26 and of G0 D5. Every reader sees the last re-share’s rates and solver
   results, including through formulas. Only the first round at a new time reads the incoming rate
   at that time. Writes, moves, allocations, edits, starts, finishes, bounds, switches and keyed
   steps reach the rates at the re-share after the stages. A flow that joined reads zero until
   then. A flow that left keeps its share until then. Ordinary writes stay sequential. Firings
   read the re-share before them. A stage after `after 0 h:` reads the preceding round’s new share
   at the same time. In the clinic and garden example the stage gets 4 L/h, the next round gets
   2.4 L/h, and the record gives 2.4 L/h from 2 h. Setup still has no rate or result to give.
   A result-dependent delay uses the new share and a delay reached during conditions waits for
   the next re-share (spec, “Reading a result” and “Time, waiting and completion”).

   **Owner’s amendment to change 27, 2026-11-21.** A stock contact joins a nearby
   moment only when both distances qualify. Its located time must be within the crossing
   tolerance in hours, and the stock at the proposed moment’s time must be within its
   own comparison band of the threshold or bound. Otherwise process the contact as its
   own moment at its located time. An earlier contact runs before the scheduled stages.
   A later contact remains pending across those stages if their writes preserve it.
   A run ending before that contact finishes at its horizon. An empty event, recording
   selection, or checkpoint and resume must give the same decision. Once a contact is
   admitted, the posting, placement and hard-constraint checks below apply.

   With a 1 L/h request and a cap of `(2 − t/h) L/h`, the stock reaches 1 L at 1 h.
   Its threshold of 1.000000005 L is 5 × 10⁻⁹ L away at the scheduled stage, outside
   its comparison band. Keep the 1 h stage and process the later contact at its own
   located time. A shorter run can finish at 1 h. No transfer is added at 1 h.

28. **The run store reuses an identical request (owner, 2026-11-20).** Store each horizon,
   selection of recorded values and piece budget under its own key. The order of the selected keys
   can differ. The returned manifest gives them in the caller's order. An identical request that
   reached its piece budget gives the same stored failure. A different request runs fresh, including
   a shorter horizon or a smaller selection. The program, inputs, seed, numerical settings,
   processor, engine and edit log still contribute to the run's identity.

29. **Comparisons and crossings (owner, 2026-11-20).** In every evaluator and in the reference
    interpreter, two numeric operands within `max(rtol, atol_factor) × max(scale, |a|, |b|)`
    compare equal. A quantity supplies its declared scale, or the size of one declared unit. A literal
    threshold uses the compared quantity's scale on either side. The owner's language 0.2.3 ruling
    makes an authored literal exact: it contributes zero comparison floor, regardless of its unit.
    This also applies to literal-only expressions and formulas naming them. The relative term in
    the band still applies. Inline and named formulas keep
    the comparison scale separate from the result unit. An explicit result scale wins. A literal
    offset leaves the scale unchanged. Add or subtract each quantity's signed contributions
    through its aliases and take the largest absolute contribution among independent quantities.
    A literal factor scales the contribution by its value in canonical units. Products,
    quotients, powers and square roots transform the floor in the result's units. A unary
    dimensionless function and an absolute value keep the input floor. Min, max and clip take
    the largest contributing floor. A conditional takes its selected arm's scale. A keyed
    read takes its selected member's scale. A frozen formula keeps its floor at retirement. Two
    independently compared quantities use the larger floor. This amendment is language 0.2.1. An interval is reversed only
    when its lower end exceeds its upper end by more than their band. Inverted hard bounds within
    the band admit one point, their midpoint. Authored evidence stays exact.
    For a stock crossing, the clock applies the time tolerance in hours and the stock’s
    comparison band in its physical unit before grouping the contact (amended change 27). A stage that
    authors a nonzero move writes. Computed transfers at a frozen store accumulate in each
    direction since retirement against that store's conservation allowance.

    **Owner’s ruling on physical balances, placement and status, 2026-11-21.** This principle
    supersedes the separate rulings for residuals at bounds, thresholds and frozen lots.

    1. The books always balance. Post each accepted transfer equally at both ends. A stock
       balance changes through posted transfers. Reading, grouping events or locating a
       numerical crossing cannot move material.
    2. After the time-and-value test in change 27, exact placement is a preference. When the flows can put a stock exactly on a bound
       or threshold, post the signed correction to the legs moving it toward that value,
       in proportion to their rates just before contact. If none approached the value,
       keep the amounts the legs carried. Apply a connected placement together. Preserve an author’s hard equations,
       frozen allowances, capacities and other stocks’ limits. If the correction would
       violate one of them, retain the amounts the trajectories delivered. Independent,
       feasible placements in the same clock group can still commit.
    3. The band decides status for comparisons, triggers and sharing. An inventory inside
       its own comparison band of a bound or threshold counts as being on it regardless of
       the residual on its books. A stock on a bound is released only when the net flow away
       from it strictly exceeds 10⁻¹² times gross incoming plus outgoing traffic. Equality
       retains the bound. Every method refines a numerically uncertain decision, and holds
       and records a near-tie when it still cannot decide. An inlet fixed at 1 L/h and an
       outlet fixed at 0.999999999999 L/h post 2 L and 1.999999999998 L over two hours.
       The initially empty stock holds the 0.000000000002 L difference and retains its
       bound status while its balance remains within its band.
    4. Fail only when a hard rule is broken by more than its applicable band. If a proposed
       placement would exceed a frozen allowance while the stock remains within its band,
       skip the placement, keep the accepted prefix and continue. A stock outside its
       target band at a nearby scheduled time keeps its located contact. Failure requires
       a material breach of an applicable hard rule. Check every affected stock and each
       shared allowance or cap before posting a connected group of corrections.
    5. Report all tied decisions in a fixed order. Keep every affected stock, leg, direction
       and target in the structured record. Questions that this principle does not decide
       are collected for the owner while independent work continues.

    Group frozen-stock allowance violations at the first failure moment within the crossing
    tolerance. List every contributing leg by stock name, outflow before inflow, then declaration
    order. Name the first five in the text and count the rest. Retain the entire ordered list in
    JSON and Python and compare it against the independent interpreter.

### If the session is cut off

Everything that matters is in the repository, pushed. The working memory of an agent is not: it
lives in the session's container, which is reclaimed after a time with no activity.

- Each prototype keeps `scratch/rewrite/aN/STATE.md`: what is done, each decision and why, what is
  in progress, the steps that remain. A fresh agent, on any model, continues from the brief
  (`briefs/aN.md`), that file and the other files of the folder.
- A worktree of an agent is not pushed, and it starts at `origin/main`, not at this branch: its
  first step is a fast-forward to this branch. When an agent works in a worktree, save its diff
  here as a patch from time to time.
- A subagent may be refused when it writes a new report file. It then gives the text in its last
  message, and the main session saves it, from the transcript of the agent, with a script.
- From 2026-11-18 the agents run on another model, to save usage.
- `g0-notes.md` holds what the main session learned beside the prototypes. `open-items.md` is the
  checklist for `rulings.md`. `tests-triage.csv` is the finished test triage.

### To set up a session

```bash
python3 -m venv .venv && .venv/bin/python -m pip install -q -r requirements.lock && .venv/bin/python -m pip install -q --no-deps -e .
```

```bash
git worktree add --detach ../napkin-base 8488047
```

The second command gives the old compiler at the base commit, outside the checkout. The migration
scripts of A5 and the checks of B0 read old model files with it. Run a test or a script of a
worktree with `PYTHONPATH=$PWD`, so that it loads its own copy of the package.

## Context

The rewrite proposal is agreed as a design to prototype against. It gives each value a type, an
owner and a lifetime. Each start of an event is a separate occurrence. A flow has a `capacity`, a
`request` and an `actual_rate`. There is one keyed collection type, an entity can own a solver, and
a run is `sampled` or `median`. Today's compiler and engine cannot express it:

- The engine keeps one pending firing for each event (`RuleState`, `napkin/engine/timeline/run.py:253`).
- A flow has one source, one target and a rate that is never negative. No flow joins two tables
  (`timeline/plan.py:497`, `:707`, `:925`).
- A model has two compiled forms. The public API runs the flat one, in which each row is written
  out and the whole model is one part. Studies, samples, edits and the whole record of a run exist
  only there (`docs/engine.md:1061`, `:1280`).
- The spec leaves many details open, and lists them.

Decisions the owner has taken:

| Decision | Choice |
| --- | --- |
| Old language | Replace in place. No old and new side by side |
| Scope | Through catalogue migration: 23 model files, publisher, notebook, docs |
| Parity with today's results | Not required |
| Execution | One stream, with parallel subagents where a step allows it |
| Whole-run derivatives | Take out. Rebuild in a later plan |
| Existing tests | Port the tests of code we keep. Delete tests of replaced features |
| Stops for approval | After the prototypes (G0), then at three gates (G1 to G3) |
| Testing | Only the tests a step needs. Full checks only at gates |
| Spec | The last version pasted in the session, with four gaps added as open items |
| Spec and plan location | `scratch/rewrite/`, deleted before merge |
| `CONTRIBUTING.md` | Not binding during the rewrite. Rewritten at the end |

Outcome: one language, one compiled form, every model migrated, the docs rewritten, the old
language gone, and `tools.check --all --deep` green.

## The approach in six choices

1. **Two boundaries, each with one form.**
   - The *declared model* is what the author wrote, with names resolved and types checked. It keeps
     texts, records, options and places in the file. It is `napkin/model/semantic.py`, rewritten in
     place. Draw, the publisher, the evidence tools and the labels of a report read it, as they
     read `semantic.Scenario` today.
   - The *program* is what runs: templates, members, values, formulas, collections, flows, events
     and solvers. It has no text and no place in a file. It is a new package, `napkin/program/`,
     which imports only `napkin/core`. The engine and the proofs read it. Each part carries the id
     of its declared part, so a report or a trace finds the label, the record and the line.
   - The program replaces `Structure`, `Resolved`, the hybrid core and the flat form. `model_hash`
     reads the declared model and the key of the run store reads the program. So a change to the
     parser moves no hash, and a change to a label makes no run again.
2. **One compiled form. The planner chooses how each part of it runs.** Today's flat run is "the
   whole model is one component". That way of running must stay: it is the only one that runs
   flows with legs in a shared pool and rates that read a stock
   (`scenarios/water_controls_wipe/water.scn:375`). Only the second compiled form goes. The planner
   cuts a program into connected sets of members and gives each set to one of three ways:
   - a small connected set goes to the continuous engine as one component (today's general tier);
   - a large family of like rows runs on arrays (today's fast tier);
   - a large connected network gets its rates from the sparse solver at each moment and holds them
     between moments. This is new. It is allowed only when nothing that the rates read moves
     between moments.

   Nothing in the language names the choice. What a run cannot do at scale stops with the name of
   the part, as the spec asks.
3. **Keep the numerical core. Rebuild the planner and the event half of the run. Add one solve
   library.** Kept: `napkin/core/` (also `core/derivatives.py`, which the planner uses to find
   linear blocks), `engine/continuous/`, `engine/solvers.py`, sampling, estimators, sum trees.
   Rebuilt: `timeline/plan.py` and the rule, trigger and moment parts of `timeline/run.py`. New:
   `napkin/engine/solve/`, on sparse arrays. The spec makes fair sharing a rank of the solver's
   selection order, so the sharing of endpoints and a declared solver are one calculation.
   `Allocation.linear_program` (`engine/allocation.py:500`) is that calculation in dense form, with
   one program for each pending member. It cannot serve 35,000 routes.
4. **Build in slices, not in halves.** A thin model runs from source to report first. Then each
   slice adds one group of constructs: the change to the program first, then the engine and the
   front end side by side, then a join on the slice's worked examples.
5. **Tests that do not overlap, an oracle, and a list of dormant tests.**
   - Front-end tests go from source to a program. They never simulate.
   - Engine tests build a program in Python. They never parse.
   - A *reference interpreter* is small and slow and follows the spec line by line. The tables of
     the spec check it. It then checks the engine on small programs, also generated ones. It
     replaces most hand-worked expectations.
   - A few acceptance tests go from source to results. They run at joins and gates only.
   - `tests/dormant.txt` names each test file that still needs the old language. `conftest.py`
     skips those files, so a run of a folder runs live tests only. The list is empty at the end.
6. **Prototype what is uncertain, and rule on every open item at one stop.** Five prototypes. Each
   item that the spec calls open gets a rule with an example, or "not in the first version" with
   the message that a model gets.

## Step 0: before anything else

- Put the spec at `scratch/rewrite/spec.md` and this plan, with a progress list, at
  `scratch/rewrite/PLAN.md`. The spec is the owner's last pasted version (870 lines); its exact
  text is recovered from the session transcript. Four gaps join its list of open items: `none` in
  arithmetic, a flow with legs that two endpoints rank differently, occurrences that never finish,
  and the caveat on the fair-sharing measurement.
- Environment: build the venv from `requirements.lock` with the dev extra, and propose it as the
  setup script of the cloud environment, so that each session starts ready.
- Keep a worktree of the base commit `8488047` outside the checkout. The old parser there reads
  the old model files for the migration scripts after the branch has lost it.
- Commit and push. The work spans many sessions: each one starts by reading these two files and
  ends by updating the progress list.

## Phase A: prototypes

All code lives in `scratch/rewrite/`: not linted, not tested, deleted before merge. No repo test
runs in this phase. The five prototypes are independent and run as five parallel subagents. Each
ends with a findings note and its proposed rulings in one form: the rule, a ten-line example on
which the rule and its alternative give different results, and a recommendation.

**A1. Notation and types.** Does the notation parse without ambiguity, and can a model be checked?
- Method: collect every code block of the spec as a corpus. Write a precedence parser for
  expressions that gives `napkin/core/expr.py` nodes. Today's route writes an expression as Python
  text and calls `ast` (`napkin/model/language/expressions.py`); it cannot read `<a, b>`, `<->` or
  a trailing `in [lo, hi]`. Lines and blocks reuse the rules of `lex.py`.
- Exit: the corpus parses. Rulings on: unit arithmetic (`48 h / 2`, `^`, `**`); `<...>` beside
  comparisons; wraps, escapes and comments; reserved words and shadowing; enum names with no
  expected type; the type of "a rate or a live formula"; assignment and copy of a formula;
  reference parameters; the names of triggers; whether `.start` gives a handle; distribution
  constructors and the range of a draw.

**A2. Reference semantics.** The same-time rules that the spec leaves open.
- Method: a small, slow interpreter over model objects built in Python, in exact fractions:
  rounds, stages, occurrences, triggers, sharing and the selection order. Linear ranks use
  `scipy.optimize.linprog`. A linear program cannot give the last rank, the least squared
  distance: for `x + y == 1` with both targets zero the answer is (1/2, 1/2), and a linear solver
  may return (1, 0). So the interpreter has its own exact calculation for that rank: for a small
  problem it tries each set of active inequality rows, solves the conditions of the least distance
  in fractions, and keeps the one feasible answer. It shares nothing with A3's method. The answers
  proved by hand stay as tests of both: (1/2, 1/2), (2, 2) and (3, 3), and the levels of the worked
  network.
- Exit: every table of the spec reproduces. Rulings on: the order of simultaneous starts and of the
  members of a broadcast; conflicting writes from two stages; reset cycles; setup order; `none` in
  arithmetic; `min` and `max` over nothing; `elapsed` after several writes in one stage; what stays
  readable on a finished occurrence; a flow with legs ranked differently at two endpoints; the
  budget for occurrences that never finish; where a human choice pauses; where an `assert` on state
  is checked; an invalid history read that a report asks for; the key of each draw.
- The interpreter is kept: it becomes the test oracle (choice 5).

**A3. Solver numerics.** Which algorithms, and what they cost.
- Method: standalone, on arrays, from `scratch/networks/` (`net.py`, `hs.py`, `nearest.py`,
  `e7_warm.py`, `e8_cascade.py`). Ranked objectives on one kept HiGHS instance. The fair-sharing
  rank on the 30,000-place route-and-level network, with the fixed members found from duals and not
  by one program for each member. The squared-distance step with `<=` and `>=` rows and a corrected
  stop rule. Unknowns that join and leave: does SciPy's HiGHS binding add and delete columns? The
  same answer under another spelling of the units. The same answer for sample k alone and in a
  batch (within the stated tolerances, not bit for bit: change 11 under "Changes after G0").
- Exit: chosen algorithms and tolerances, and a measured table at full scale. The expected answers
  reproduce: (2, 2) and (3, 3); 2, then 1.5 each, then 2; (2, 2, 3) and (4, 0, 5); the worked
  network with levels (8/3, -4/3, -4/3) and (3, -3, 0). A go or a no-go for fair sharing at scale.
  A fallback may be a slower exact method, or a refusal by name above a measured size. It may
  never give another answer: a change in who is served is a change to the language, and goes to the
  owner as one. The closed forms of `allocation.py` that stay as fast paths under the new sharing
  rules.

**A4. Engine at scale.** How the planner cuts a model, and how the engine holds members that come
and go.
- Method: a spike in a copy of the package.
  - First, a tiny model with a real transfer across rows. One route row has an origin and a
    destination that resolve into the same table, and moves a known quantity between two place
    rows. The debit and the credit are on the right stocks, also after the place rows are
    reordered. The earlier trial did not show this: it read inputs through two links by stand-in
    rows, and ran no transfer (`scratch/networks/two_links_trial.py`). Then the same at 30,000
    places, for the cost.
  - A pool of rows whose members join and leave: occurrences, their flows and stores, the totals
    of each receiver.
  - The rule for connected sets (choice 2). A request that moves continuously, inside a small set
    and inside a large one.
  - What a run records (below, under G0), and what that costs with 30,000 rows.
- Exit: a layout note (arrays, indexes, the reader graph, and the proofs over a program whose
  members come and go). The measured limits, and the message for each thing refused at scale. For
  `timeline/run.py` and `plan.py`: what is kept, moved or rewritten, and the module layout.

**A5. Catalogue fit.** Does the language cover real models, and how much of the migration is
mechanical?
- Method: translate by hand both `examples/`, `water_controls_wipe/water.scn` with one variant, the
  options and runs of `heat_wave_blackout`, and one actor with a choice and status cases. Count
  each old form in the catalogue with the old parser, not with a pattern.
- Exit: each old form has a new form or a decision. A proposed spelling for what the spec gives
  none: the scenario line; options and named runs, and where a comparison lives now that `versus`
  goes; `use`, `variant` and `change` with their precedence; records and claims; notes; `sees`; the
  chance and choice producers; the report selection; scale hints. A migration table. Two scripts
  that use the old compiler: one translates the mechanical lines, with its measured share; one
  checks a translation against its old file. The check covers meaning, not only words: each number
  with its unit and each text is present; each name keeps its kind (a store, an accumulated tally,
  a rate, a formula, an input, a state); and each output that the old compiler proved cumulative is
  proved never to fall by the new one.

**Gate G0 (stop for the owner).** One document, `scratch/rewrite/rulings.md`, in two parts.
Rulings that change what an author writes or sees need the owner's word. Technical rulings stand
unless the owner objects. It also holds:

- the scope of the first version, with the message for each thing it refuses;
- a go or a no-go for the three numerical risks: fair sharing at scale, inequalities in the
  distance step, and membership that changes;
- the limit for a request that moves continuously in a large connected set;
- what a run records, settled before S0 builds it. A reporting lag averages a value over a window,
  and two histories with the same readings at the chosen times can have different averages
  (`napkin/engine/report.py:164`). So the record holds histories, not readings: for each recorded
  value, its exact pieces over the run. Proposed: a small model records every named value, as
  today, so a later report or chart needs no new run; a large model records what the request
  names. The key of a stored run covers the program, the effective configuration, the mode, the
  seed, the choices, the numerical settings and the code. It covers no label. A stored run serves
  a request that it covers; a request for a value or a window that it lacks runs again;
- one error of the spec, for the owner to correct: its `unserved_volume` example calls an
  accumulated volume a current one that "can fall when service returns". In the water model the
  rate falls to zero and the volume keeps the loss (`water_controls_wipe/water.scn:264`, `:374`,
  `:701`);
- candidates to retire and not port: the pruning of idle parts for each set of start-state options
  (`napkin/model/lower/starts.py`), the second reading of the rules (`reading='every'`,
  `timeline.check`), whole-record pickles in the run store, `tools/compare.py` at its present size;
- the staging and the module layout of Phase B, confirmed or changed.

The spec is then edited to hold the rulings.

## Phase B: build in place

### Working rules

- B0 and B1 change nothing that an old test can see. The old language stops at S0. From S0 until
  G3 the whole suite is never run; the dormant list makes each folder run safe.
- Old modules are deleted when their replacement lands. Nothing new imports an old module.
- Each step ends with a commit and a push to `claude/blissful-heisenberg-5me2hn`. No pull request
  unless asked.
- Three tracks, with directories that do not overlap:
  - **Engine track**: the main session, which hands a self-contained module with its tests to a
    subagent where it can. It owns `napkin/program/`, `napkin/engine/`, `tests/program/` and
    `tests/engine/`.
  - **Front-end track**: a chain of subagent tasks. It owns `napkin/model/`, `tests/language/`,
    `tests/model/` and the new `tests/build.py`. It owns the lowering from the declared model to a
    program too. Its target in each slice is exact: the source of each example lowers to the
    program that the engine tests already run.
  - **Oracle track**: one subagent for each slice. It extends the reference interpreter and writes
    the slice's acceptance files, from the spec only and never from the engine.
- A subagent works in its own git worktree. The change to the program is committed before the
  tracks start. The main session merges. Worktree branches stay local.
- Each subagent gets a written brief, kept in `scratch/rewrite/briefs/`: the spec sections, the
  files it owns, the tests it may run, and its exit criterion.

### Stages at a glance

| Stage | Delivers | Old suite |
| --- | --- | --- |
| B0 Keel | Imports that survive, the dormant list, the test triage, derivative code gone, `run.py` split | Runs once at the end, for the last time |
| B1 Contract | `napkin/program/`, the reference interpreter, `napkin/engine/solve/` | Not touched |
| S0 Skeleton | Values, a store and a flow run from source through `napkin run` | Old language gone |
| S1 | Templates, tables, collections, keyed reads | |
| S2 | The flow network and sharing | |
| S3 | Reversible flows and flows with legs | |
| S4 | Occurrences, stages, triggers, draws, run modes, choices | |
| S5 | Solvers | |
| S6 | Packages, options and edits as one run configuration; **gate G1** | |
| C | The report, then studies, commands, draw, dynamics, publisher; **gate G2** | |
| M | The catalogue; **gate G3** | Whole suite again |
| F | Clean-up, docs, final checks | |

### B0. Keel

It needs no ruling and keeps behaviour, so it runs beside Phase A.

1. Imports that survive the rewrite. `napkin/engine/__init__.py` and `napkin/model/__init__.py`
   load their names on first use, as `napkin/__init__.py:44` does. Today an import of
   `napkin.engine.allocation` loads the report, the study and the whole front end.
2. `tests/units.py`, from the units of `tests/build.py:30-81`. Four files of `tests/core` import
   `tests/build.py` for its units only (`reference.py`, `test_ops.py`, `test_units.py`,
   `test_derivatives.py`); they change to the new file. `tests/core` then needs no front end.
3. The dormant list: `tests/dormant.txt`, read by `pytest_ignore_collect` in `conftest.py`. It is
   empty for now.
4. Triage each test file into a class (table under "Existing tests") as
   `scratch/rewrite/tests-triage.csv`. Parallel subagents, one for each test folder. The file is
   the work list for porting, and it fills the dormant list at S0.
5. Delete the whole-run derivative code: `timeline/derivatives.py`, `influence.py`, `smooth.py`,
   the tangent arrays in `run.py` (about 160 lines touch them), `Plan.fast()` and `plan.optional`,
   `commands/derivatives.py`, the derivative estimators of `engine/expectations.py`, their tests
   and their doc sections. Keep `napkin/core/derivatives.py`.
6. Split `timeline/run.py` (one class, 3,490 lines) by pure moves into one module for each
   concern, so that a later slice deletes whole modules. Replaced later: `RuleState`, `read_rule`,
   `_trigger`, `_fire`, `settle`, play. Kept: `Solution`, `field` and `decide`, lines and floors,
   `read` and `read_past`, `closure` and `apply`. The split follows A4's layout note.

Tests: while working, three engine files (`test_timeline.py`, `test_moment.py`,
`test_closed_form_short.py`). At the end, once: the whole test suite,
`pytest -n 4 --no-focused -m 'not deep' tests scenarios`, with its durations recorded. This one run
proves that the keel changed nothing, gives the list of what was green before the rewrite, and is
the last run of the old suite. A failure is checked alone against the base commit. The publication
comparison and its drift test are left out: each code change moves the hashes that committed files
hold. The run waits until A3 and A4 have made their timing runs.

### B1. Contract, oracle and solve library

Three tracks side by side. All three only add files.

- **The program**, `napkin/program/` (main session):
  - `parts.py`: frozen records for templates, members (ids, columns, link columns), fields, stores,
    flows with legs and endpoints, events (parameters, locals, steps, statements), triggers and
    solvers.
  - `refs.py`: a reference is a template, a field and a path of links. Today the engine infers the
    space of a part from the prefix of a flat name (`plan.py:505-541`); that is why two links into
    one table are refused.
  - Expressions stay scalar nodes of `napkin/core/expr.py`. A reduction, a keyed read and a field
    of an occurrence are named parts that an expression reads by reference, as `Aggregate` is today
    (`plan.py:621`). So `napkin/core` and its tests do not change.
  - `build.py`: builders. The lowering of the front end and the tests both make programs with
    them, and `finish` runs the checker (one writer for each value, endpoints are stores, units as
    explicit fields).
  - `canonical.py`: the bytes that the key of the run store reads.
  - A second small record, the *run configuration*: inputs, start values, the chosen options, the
    mode, the seed and the choices. The engine also reads `model.runs.Runs`, `model.uncertain`,
    `model.evidence` and `input_name` today; all of these move behind the two records.
  - The *request* and the *record* of a run, as G0 settled them: which values a run keeps, the
    exact pieces of each over the run, and the trace. The report, the store and the oracle all
    read this one form.
  - The proofs (`napkin/model/analysis/`) move to `napkin/program/` slice by slice, because the
    front end and the engine both call them: zero faces with S2, crossing classes with S4, the
    never-falls proof with the report.
- **Examples as programs**: `tests/program/examples.py` holds each worked example of the spec.
- **The oracle**, `tests/reference/` (oracle track): A2's interpreter, made to read a program and
  checked by the tables of the spec.
- **The solve library**, `napkin/engine/solve/` (a subagent, from A3): a persistent HiGHS instance
  that belongs to one run and never to a plan; the affine form of an expression; a problem and its
  independent parts; ranked objectives that keep each attained optimum; max-min tiers; the
  squared-distance step; failures by name. Its tests use arrays and exact fractions.
- Register the new packages: `packages` in `pyproject.toml`, `CLOSURE` in `tests/test_api.py:34`.
- Tests: `tests/program/`, `tests/reference/`, `tests/engine/solve/`. Nothing else.

### The slices

Each slice has four steps. (1) The main session commits the change to the program and the slice's
examples. (2) The three tracks work in parallel. (3) The join: the slice's acceptance files run
from source. (4) The test files of the triage that belong to the slice are ported or deleted, and
leave the dormant list.

**S0. Skeleton.** The old language stops here.
- Language: the scenario line, entities, values, units, ranges, `input`, `readonly`, `formula`,
  stores, a one-way flow with `capacity` and `request`, texts, `@record`, a median run, the
  selection of values to report.
- Front end: the lexer and the new expression parser, the declared model, the checks of types and
  units, the lowering, `napkin fmt`. Reused: lines and texts of `lex.py`, the cursor and the
  parsing of records and notes in `parse.py`, `modules.py`, `tables.py`, `library.py`.
- Engine: `Plan.of(program)`, with each connected set as one component. The record of a run: the
  history of each recorded value, and the trace. A first report from `timeline/reports.py`. Deleted:
  `hybrid.py`, `structure.py`, `lower/`, `Plan.flat` and the flat entry points of
  `timeline/__init__.py`. `conftest.py:9` imports `napkin.store`, which digests the code from
  `engine/runtime.py` at import (`store.py:70`): the start of that digest moves in the same commit
  as the file, or no test collects.
- Join: the tank that empties at 2 h 40 min, through `napkin run`. `examples/piano_tuners`
  migrated. The owner gets a note with the command to try. This is no stop.

**S1. Templates, tables and collections.**
- Language: templates, links, `this`, tables with an `id` column, `instances`, literals,
  projection, the six reductions, `where`, `by`, `at`, `none`, `assert` on inputs, initializers in
  the order of their dependencies.
- Engine: pools of members, link columns, the reverse index for `where(link == this)`, the sorted
  key index, key times on the timeline, sum trees (`timeline/trees.py`), arrays for a large family.
- Join: keyed reads; row names that survive a reordered CSV. Once, as a benchmark: the two-link
  model with 30,000 places and 35,000 routes compiles and runs.

**S2. The flow network and sharing.**
- Language: the scopes of an endpoint, `priority(...)` and `proportional()`, ranks with ties,
  junctions, `SOURCE` and `SINK`, flows across templates, the `.flows` collections.
- Engine: one sparse network across spaces. It replaces the dense matrix of
  `continuous/system.py:152` and the refusals of `plan.py:497`, `:707`, `:782`, `:925` and `:974`.
  Sharing comes from the solve library; `allocation.py` keeps only the closed forms that A3
  confirmed. Bounds, faces, floors and the roundoff rules are reused as they are.
- Join: 8 and 2; 4 and 6; the common sink; one pipe and three requests; the junction that carries
  8 W; the flows of one water variant.

**S3. Reversible flows and flows with legs.**
- Language: `<->` with `forward` and `backward`; nested legs with one `served_fraction`.
- Engine: one signed coordinate with two leg views; one fraction for a flow with legs, from the
  coupling of `Allocation.ration`. One rule of that code is reversed. Today a flow with one leg
  that asks and one that asks nothing is an error of the run (`engine/allocation.py:165`,
  `tests/engine/test_rationing.py:116`); the spec allows it.
- Join: the leg reads at -3 L/h; a leg in `priority(...)`; the fraction 0.5 that gives 2 and 4; the
  refused ends. Leg requests (0, 8) with ample capacity give rates (0, 8) and a fraction of 1;
  (0, 0) gives a fraction of 0; a live request that crosses zero during a run stops no run.

**S4. Occurrences and time.**
- Language: `event(...)`, `.start`, locals, `after`, guards, `until`, triggers with both resets,
  `switch`, the chance and choice producers, `sees`, a start on each member of a collection,
  `move`, the flows and stores of an occurrence, history, `since`, `elapsed`, `delayed`, explicit
  draws, `sampled` and `median`, `assert` on state.
- Engine: `moment.py` (rounds: due stages commit, sharing and solvers settle, conditions are read);
  `occurrences.py` (frames in a pool that grows; their flows and stores join and leave the network;
  the retirement rule); `triggers.py`, on the crossing classes that the engine has today;
  `choices.py` with the pause; draws keyed by their site and their occurrence. These replace
  `RuleState`, `read_rule`, `_trigger`, `_fire` and `settle`.
- Join: the grinder at 108 g; overlapping deliveries; `inspect` at 3 h and 5 h; the clock at 3, 6
  and 9 h; the history table; two starts at one time; the flows table 0, 1, 0, 1; a failed
  retirement; the horizon case with 7.5 L and 12.5 L; one median run and one sampled replay.
- Join, on time: a flow that joins must move the time of a crossing. A tank starts at 10 L and
  fills at 1 L/h. An occurrence drains 2 L/h more from 2 h to 4 h. A trigger on `>= 16 L` fires at
  10 h. A prediction that was not made again fires at 6 h, when the tank holds 12 L.

**S5. Solvers.**
- Language: `solver:` with its four sections, projected unknowns, the refusals by name.
- Engine: the lowering of constraints and objectives; one solve for each affected solver in a
  round; members that join and leave; the diagnostic for a dirty read; an infeasible solve stops
  the run before a trigger reads; a solve inside a small component at trial states; the refusal at
  scale.
- Join: the worked network (four rows, both sets of levels, inputs in kW, reordered CSVs); two
  bottlenecks; staffing; the pump; the provider; the inequality case; the membership case. Both
  halves of "once in a round": two writes in one round make one solve, and a trigger that reacts
  to that result starts a second round with a second solve at the same time. Once: `tools.bench`
  at 30,000 places.

**S6. Packages and configurations.**
- Language: `use`, `variant`, `change`, options, named runs, the edit document.
- Both halves: one run configuration over one program (`napkin/model/runs.py`,
  `napkin/schema/edits.schema.json`, `Model.combination`), with the precedence and the conflicts
  that G0 ruled. `model_hash` from the declared model. `LANGUAGE_VERSION` goes up.
- Join: one package with a variant, two options and an edit.

**Gate G1 (stop).** Every worked example of the spec runs from source, and so does one file with
every construct. This is the first wide run: `tests/core`, `tests/program`, `tests/reference`,
`tests/language`, `tests/model`, `tests/engine` and `tests/acceptance`, with `--test-jobs 4`.

### C. Results and consumers

First, alone: one report over the record. It merges `engine/report.py` and `timeline/reports.py`,
and holds the status display, the texts, the lag with its never-falls proof, `none` and the
evidence trail.

Then parallel subagents, each with its own tests only:

| Part | Code | Tests |
| --- | --- | --- |
| Studies and runs | `engine/study.py`, `uncertainty.py`, `sampling.py`, `expectations.py` (plain estimators), `napkin/spread.py`, `session.py`, `store.py` (the key and the reuse rule that G0 settled; the record replaces the `Trajectory` pickles), `napkin/schema/` | The matching top-level and engine files. New: a label edit reuses a stored run; another seed, and a window that the stored run lacks, do not |
| Commands and API | `napkin/commands/*`, `napkin/__init__.py`, `package.py`, the templates of `commands/new.py` and `tools/new.py` | `tests/test_cli*.py`, `tests/test_api.py` |
| Draw | `napkin/draw/**`, over the new declared model | `tests/draw` |
| Dynamics | `napkin/dynamics/**`, over the component of a small model (`dynamics/field.py:52` builds its system from the flat form today) | `tests/dynamics` |
| Publisher and tools | `tools/publish/**`, `tools/evidence/**`, `tools/bench/families.py`, and `tools/compare.py` rewritten small over the record unless G0 retired it | `tests/publish`, `tests/evidence`, the tool tests |

**Gate G2 (stop).** Every central test is green with no catalogue:
`pytest -n 4 --no-focused --scenario-selection '' -m 'not deep' tests`, then ruff. The dormant list
holds only tests that read the catalogue.

### M. Catalogue migration

- The main session migrates `examples/reservoir` and writes the migration guide from A5's table.
- Then one subagent for each package, in parallel: `iv_fluid_shortage`, `heat_wave_blackout` with
  its notebook, `cyber_learning_loop` (3,200 lines in one file, done in sections; its tests use
  `napkin.dynamics`), and `water_controls_wipe` with its 16 variants and its UI (`ui/server.py`,
  `ui/view.py`, two test files).
- For each package: translate, with A5's script for the mechanical lines and then by hand. Run
  A5's check script, so that no number, unit or text is lost, no name changes its kind, and each
  cumulative output is still proved never to fall. Compile. Run in `median` mode. Port its tests
  with `oracle-inputs.json` and `expected-orders.json`, its evidence index, its `style.toml` and
  its spread files.
- Each package also gets one behaviour test for each headline quantity, which shows what kind of
  quantity it is. For the water model: when service returns, the unserved rate is zero and the
  unserved volume keeps its value.
- Parity is not required, but no change is silent. A scenario test that fails after the migration
  is traced to its cause. A translation error is fixed. A change that follows from the new
  semantics goes on a list for the owner at G3, with the old and the new numbers. No expected value
  is edited to pass.
- For each package: `tools.check --scenario ID --skip-summaries`. Nothing wider.
- Once, at the end: `tools.publish --write` for all, then a read of every changed brief.

**Gate G3 (stop).** `python -B -m tools.check --all`. The dormant list is empty, and its mechanism
is deleted.

### F. Finish

- Delete what is dead: old modules, old tests, `scratch/`, the superseded scoping page
  (`docs/scoping/networks-and-found-values.md`) and its row in `known-issues.md`.
- Among the old modules: `napkin/model/types.py` and `napkin/model/uncertain.py`, whose last user is
  the old publisher (`tools/publish/runs.py`, ported in M); `napkin/engine/runtime.py`, the old
  trajectory, which only dormant test helpers import; and `napkin/expressions.py` with
  `napkin/core/intervals.py`, which the old runtime reaches and, for `ExpressionError` and
  `UnitSystem` only, `napkin/model/evidence.py` and `tools/evidence/adopt.py`: move those two first.
- Rewrite the docs, one subagent for each file: `language.md`, `compiler.md`, `engine.md`,
  `modeling-guide.md`, `python-api.md`, `cli.md`, `draw.md`, `extending.md`. Record the rulings and
  the new measurements in `design.md`. Update `known-issues.md` and `CHANGELOG.md`.
- Rewrite `CONTRIBUTING.md`. Its rules on tests, comparisons, identity and structures describe the
  old system.
- Versions and lists: the schema versions, `_SOURCES` in `model/compile.py:24`, `packages` in
  `pyproject.toml`, `CLOSURE`.
- Final checks, once: `tools.check --all --deep`, the committed spreads, `tools.bench`.

## Test policy

| When | What runs | Command |
| --- | --- | --- |
| While writing | The one test or file in hand, with the run store off | `NAPKIN_STORE=off python -m pytest -q -p no:cacheprovider PATH::TEST` |
| Before a commit | The test files that the commit touched, and ruff on the changed files | as above |
| End of a slice | The slice's folders with lint, and the tests of any kept module that it changed | `python -B -m tools.check --tests FOLDER --tests FOLDER` |
| Joins | The slice's acceptance files | as above |
| Gates G1 to G3 | As written at each gate | |
| Final | `--all --deep`, spreads, bench | |

- A failing test is run again alone. The set of a slice runs again once, when it is believed green.
- `tools.check` cannot find the changes on this branch, which has no merge base with main. So every
  call names `--tests`, `--scenario` or `--all`.
- The run store is off in the inner loop, because every edit of the engine changes its digest.
- New tests take their expected values from closed forms, from the reference interpreter or from
  properties, and never from a run of the engine. Their models are synthetic, with generic names. A
  test that needs more than about 10 seconds is marked `deep`.
- From S2 on, a generator of small programs compares the engine with the reference interpreter: a
  few hundred cases in a normal run, more under `deep`.

What must not run early, and why:

| Not before | What | Why |
| --- | --- | --- |
| G3 | The whole suite and `tools.check --all`, after the one run of B0 | The catalogue is in the old language until M |
| The one `--write` in M | `tools.publish --check`, `tests/publish/test_publish_drift.py` | Each code change moves the hashes in committed files |
| M | Each test that reads the catalogue: `scenarios/*/tests`, `tests/test_examples.py`, what imports `tests/helpers.py` | The models are in the old language |
| Their part of C | `tests/draw` (heavy property tests), `tests/publish`, `tests/evidence`, the tests that start processes | Their code is not ported yet, and they are slow |
| The end of a stage | `tests/test_api.py` | Its `CLOSURE` list changes with each new module |
| Final | `deep` tests, and the spreads (the longest takes about 25 minutes) | Cost |
| The end of S5, and final | The run with 30,000 places | It is a benchmark. Tests assert counts, never times |

### Existing tests

A first count by what each test file imports: 28 files need no language (5,200 lines), 141 compile
source text (53,800 lines), and 33 read the catalogue (10,900 lines). The triage of B0 splits the
141 into "port" and "delete". 210 tests pin the text of a message; they are rewritten with the new
messages, not adapted one by one.

| Class | Which | Treatment |
| --- | --- | --- |
| Keep | `tests/core`, and the engine tests of modules whose behaviour stays (HiGHS, solver adapters, sampling, estimators, distributions, sum trees) | Unchanged. Run when their module changes |
| Change with the rules | `tests/engine/test_rationing.py`. It needs no language, but the sharing rules change, and one of its cases is now the opposite (S3) | Rewritten in S2 and S3, with the new rules |
| Port, engine | Tests of bounds, faces, roundoff, integration, switching, crossings and sizes, whose expected values are closed forms | Written again on the builders of `napkin/program/build.py`, in S0 to S4 |
| Port, front end | Units, modules, packages, tables, identity, diagnostics | In the slice that brings the construct |
| Port, consumer | CLI, API, session, store, spread, draw, dynamics, publish, evidence | In C, each with its consumer. Mostly a change of fixtures to the new `tests/build.py` |
| Dormant until M | Each test that reads the catalogue | In M, with its package |
| Delete | Moments and rearming of the old events, windows, the cancel on `while`, outcomes in their old form, `versus`, `output` settings, derivatives, the flat structure, the hybrid core | With the feature |

## Not in this plan

- Whole-run derivatives and the estimators built on them: removed, rebuilt later.
- What the spec defers: `where` on state, reads of an occurrence at an earlier time, lists of
  values, cancellation and interruption, interpolation in a keyed read, nonlinear or yes-or-no
  solver problems, `at T:`, `assert initially`, a type for a resource that is held and released,
  correlated draws.
- `formula.diff(...)`, which the spec marks optional.
- Whatever G0 rules out of the first version.

## Risks, in the order they are retired

1. Whether the language covers real models, with their options, runs and comparisons (A5).
2. How the planner cuts a model, and what runs at scale (A4).
3. The same-time rules (A2).
4. Fair sharing at scale, and inequality rows in the distance step (A3).
5. Members that come and go, in the engine and in the proofs (A4). What a run records, on which
   the report, the store and the oracle all depend (G0, B1).
6. The parser, and the tests that pin message text (A1, S0).
7. The join of the two halves. The slices, the examples as programs and the oracle limit it.
8. Draw: 12,700 lines over the declared model (C).
9. The catalogue: 10,000 lines translated mostly by hand. The check script and the rule against
   silent changes limit it (M).
10. Edge cases lost while tests are ported. The triage limits it, and the dormant list must end
    empty.

## Verification

- S0: `napkin run` on the tank example reports the tank empty at 2 h 40 min.
- G1: `napkin run` on the worked network gives the four rows and both sets of levels of the spec.
  A reordered CSV changes no named result. Inputs in kW give 0.004 kW for each delivery.
- G2: the central tests are green with an empty catalogue selection, and ruff is clean.
- G3: `python -B -m tools.check --all` is green, `napkin fmt --check` passes on every model, and
  the dormant list is gone.
- Final: `python -B -m tools.check --all --deep`; `tools.publish --check` after the one `--write`;
  the numbers of `tools.bench` recorded in `docs/design.md`.

## Critical files

- Spec, rulings and progress: `scratch/rewrite/spec.md`, `rulings.md`, `PLAN.md`, `briefs/`.
- Contract: `napkin/program/` (new), `tests/program/examples.py` (new), `tests/reference/` (new).
- Front end: `napkin/model/language/{lex,parse,nodes,format,expressions,resolve,modules,tables,evidence}.py`,
  `napkin/model/{semantic,model,runs,identity,ir,compile}.py`, `napkin/model/analysis/`.
- Engine: `napkin/engine/timeline/{plan,run,reports,trees,__init__}.py`,
  `napkin/engine/allocation.py`, `napkin/engine/continuous/{system,highs,integrate}.py`,
  `napkin/engine/solve/` (new), `napkin/engine/runtime.py`, `napkin/store.py`.
- Results: `napkin/engine/{report,study,uncertainty,expectations}.py`.
- Check tooling: `tools/check.py`, `conftest.py`, `tests/selection.py`, `tests/dormant.txt` (new).
- Prototypes to reuse: `scratch/networks/` (`hs.py`, `nearest.py`, `net.py`, `e7_warm.py`,
  `e8_cascade.py`).
