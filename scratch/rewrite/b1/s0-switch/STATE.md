# S0-S: the switch of the first slice — state (done)

Brief: `scratch/rewrite/briefs/s0-switch.md` (with `COMMON-B.md`).

## Done

1. Deleted (6,097 lines): model/hybrid.py 1144, structure.py 1008, lower/ 2723 (builder 1555,
   starts 621, expressions 534, __init__ 13), model.py 896, resolved.py 204, meaning.py 122.
   Proof: the static import closure (every import, also in functions) from engine/timeline,
   model/compile.py, conftest.py and every live test reaches them only through tests/owned.py,
   which only dormant tests import; a run of the piano tuners loads none; 1979 live tests collect
   before and after. model/__init__: no `Model`; adds `LanguageError`, `compile_text`.
2. Contract: `build.call` (closed list of core FUNCTIONS, ValueError otherwise; `X(node, reads)`
   documented); a plain store's flow is `1/h` in the builder (was `/h`, refused); refs.py notes
   (temporary draw site, lognormal gsd plain); `record.Curve` + `Piece.curve` + `Piece.at` (pure
   Python Clenshaw); `Quantity.unit` may be a `parts.Unit` (a library unit, whole); the engine reads
   `Numerics.crossing` (kernels, integrate: `Limit(moment=)`, `radau(moment=)`, chattering message;
   record's yes/no bisection); `EVENT_TIME_TOLERANCE_H` gone from continuous/system.py.
   `read` evaluates formulas from the recorded values of what they read (`_Values`); a record with
   `keys` keeps what its formulas read. Test files mended: engine/test_record.py (curve field),
   test_switching_surfaces.py and test_cumulative_integration.py (`build.call`).
3. CLI: cli.py (parse_known_args; LATER commands refused, exit 2), commands/__init__ (NAMES, LATER,
   STAGE), common.py (rewritten small), run.py, fmt.py, compile.py.
4. tests/commands/ (65 tests): call.py (in-process CLI, the tank text), test_run, test_fmt,
   test_compile, test_cli, test_contract.
5. Checks: commands+language+program+reference+core 1270 passed; tests/engine (live) 535 passed;
   ruff check and format clean on napkin tools tests scenarios conftest.py; whole tests 2044 passed.

## Findings

- The fit of a formula can lose more than its tolerance: a yes/no true only between two check points
  (`water <= 5.3 L and water >= 5.29 L` on the draining tank) is fitted false throughout. Hence
  `read` evaluates.
- Pre-existing (reproduced on HEAD via git archive): in one process, scipy `linprog` (tests/reference
  order.py) before the solve library sets HiGHS's global scheduler to the default thread count, and
  solve/kept.py's `threads = 1` then ends with kSolveError ("numerical"). With -n 3 this hits
  tests/engine/solve when a worker ran a reference file first (159 failures once, 0 in another run).
  Mend in napkin/engine/solve/kept.py (`_Highs.resetGlobalScheduler`, or no threads option).
- Broken by the deletion (old path, later stages): draw/*, dynamics/field,
  engine/{report,study,uncertainty,timeline/reports}, model/analysis/*, store._typed_bytes (lazy),
  tests/build.py, tools/{bench/measure,compare,evidence/integrate,publish/*}. Already broken:
  model/runs.py, views.py. commands/{play,sample,draw,new}.py kept, unimported (stage C).

## Decisions

- D-S1 A library unit in a Quantity is a whole `parts.Unit` (no lookup table in the configuration).
- D-S2 `Limit` and `radau` default `moment` to `Numerics.crossing`; the engine passes the run's.
- D-S3 `read` builds the plan of the program with a bare request to evaluate formulas.
- D-S4 New tests of the contract changes are in tests/commands/test_contract.py (my folder).
- D-S5 lower/starts.py (reachability, D16) is deleted with lower/; git history keeps it (81b367b).
- D-S6 `napkin run` uses no run store; `fmt` needs FILEs; values print with 6 significant figures.

## Not done (outside the brief)

- tests/test_api.py CLOSURE (dormant); the oracle's `_input` does not read a `Unit` quantity;
  lowering still passes `unit='1/h'` (now redundant); docs/cli.md and the example README.
