# Plan: implement the napkin language rewrite

## Progress

Each session starts by reading this file and `spec.md`, and ends by updating this list.

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
- [ ] S4 occurrences and time (`briefs/s4.md`). The largest slice: its engine comes in two parts, one after the other; the front end does the whole slice beside the first part
  - [x] the front end, the whole slice (`b1/s4-front/STATE.md`): the 32 examples that need no solver lower to their bytes; a write through `.source` or `.sink` is refused (`fixed_write`); reachability under a configuration (D16) is proof metadata in `napkin/program/reach.py`, ported from `81b367b`, each template's members merged into one state. An enum is named by its spelling. A distribution whose parameters are values is refused (`distribution`): the program holds numbers. Draws and choices stand only where a value is captured once. An event local holds no entity; occurrences are read through `.at(t)` (a local may keep one). Ported and deleted: the five front-end files of `tests/model/` for S4; `test_initiation.py` deleted (the old start of an incident)
  - [ ] for C: `napkin/model/views.py` is rewritten on the compiled model; `draw/` and `commands/play.py` still call the old API
  - [x] the engine, part one (`b1/s4a-engine/STATE.md`): occurrences, stages, gates, triggers, moves, retirement, history, limits. The 23 examples equal their values and the oracle; 300 random event programs agree with the oracle (2,000 under `deep`). New `moment.py`, `occurrences.py`, `triggers.py`, `ways.py`; the dead modules of the old engine deleted but `state.py` (part two). A moment rebuilds each connected set that it touches, in its own way of running. A contact on a curve is certified only for one store that only rises or only falls; else, and for a strict threshold on a moving value, a diagnostic. A setting that reads a rate of a set whose rates move is refused "(S5)". Ported: `test_finite_face_kernel.py`, `test_finite_stock_boundaries.py`, `test_monotone_crossing.py`, `test_rearm.py`, `test_switch_at_segment_start.py`, `test_timeline_row_facts.py`; the event cases of `test_runtime.py` and `test_timeline.py` (new files; the old ones stay dormant for the rest) and the trigger classes of `tests/model/` as `test_trigger_classes.py`; deleted `test_ai_layer.py`, `test_moment.py`, `test_windows.py`. Benchmark at 30,000 places with 482,500 starts over 48 h: build 0.7 s, plan 1.9 s, run 866 s, mostly reading every trigger at each moment. 3,472 live tests pass
  - [x] the join: `napkin run` lists no occurrence by default; `--value tank.deliver#1.pipe.request` reads one, `unavailable` before its start
  - [ ] for later: read again only the triggers whose inputs changed; free the caches of finished occurrences (memory grows with the starts); in stages, assign a formula, an allocation or a collection (refused "(S4)"); endpoint settings on an occurrence's own store
  - [ ] the engine, part two: draws and run modes in stages, inputs that are distributions, choices and the pause, assertions over state, `elapsed` and `delayed` (9 examples)
- [ ] S5 solvers
- [ ] S6 packages and configurations
- [ ] Gate G1
- [ ] C results and consumers
- [ ] Gate G2
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
  batch.
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
