# C-S: studies and runs — state (done, but for S7's part)

Brief: `briefs/c.md` (C-S) with `COMMON-B.md`; PLAN "Changes after G0" 10-13 and 15; `b1/c-report/STATE.md`.
Owner (2026-11-19, PLAN item 15): breakpoints, checkpoints and edits replace the player machinery.
NOT ported, waiting for S7: `napkin/session.py` (resolver, picks, controllers, `Run.resume`),
`tests/test_session.py`, `tests/engine/test_decision_resolver.py`; a store key over an edit log.

## Order
1. `napkin/store.py`: records, key, reuse rule, locks, size limit, verify. tests/test_store.py.
2. `napkin/engine/sampling.py` (seeds of samples; `stream` kept), `study.py` (configurations of
   named runs, runs in processes), `uncertainty.py` (Monte Carlo), `expectations.py` (plain
   estimators), `napkin/spread.py`. Tests: test_monte_carlo_study, test_public_engine,
   test_expectations, test_spread, test_sampling; delete test_admission_scope.

## Done
- store.py, sampling.py, study.py, expectations.py, uncertainty.py, spread.py rewritten (API below);
  engine/__init__.py exports updated (no `study` export: it is a submodule's name).
- Tests (all pass alone): tests/test_store.py (16), tests/test_spread.py (7),
  tests/engine/test_monte_carlo_study.py (16), test_public_engine.py (14), test_expectations.py (6),
  test_sampling.py (14, latin/Sobol' tests gone with the methods). Deleted
  tests/engine/test_admission_scope.py (no admission scope since S6; the transaction is in
  test_public_engine).
- Not ported (S7): session.py, tests/test_session.py, tests/engine/test_decision_resolver.py;
  `expectations.weighted` and `mean_of` dropped (no given outcomes in the engine; no caller).
- model/analysis/ stays: session.py (S7) imports values.py; report.schema.json stays: model/load.py
  loads it at import (old report; nothing writes it now).
- Final: my 6 files 73 passed; with tests/core, tests/engine, tests/program: 3176 passed (-n 2).
- Can leave dormant.txt: tests/test_store.py, tests/test_spread.py, tests/engine/test_monte_carlo_study.py,
  test_public_engine.py, test_expectations.py (test_admission_scope.py deleted).

## Decisions
- Reuse rule: one entry per key holds one record; it serves a request with a horizon at or before
  its own and values it holds, cut to the request (`served`); a miss runs again with a request wide
  enough for both, which replaces the entry. Failed runs are stored; paused runs are not.
- Thread settings are not in the key (a run under other threads agrees within tolerances).

## For C-K (public names; keep current)
- Runs through the store: `napkin.store.run(program, configuration)` -> Record (reuse rule above);
  turn it on with `store.activate(store.default_directory())` / `store.use(dir)`; `store.counts`,
  `store.verify(dir, n)` (prints, gives differing paths), `store.default_directory()`, `store.cores()`,
  `store.pool_options()` (no `helpers` any more), `store.ENVIRONMENT`, `store.fingerprint`.
  Gone: `simulate`, `simulate_all`, `helpers`, `canonical`, `_StoredLibrary`.
- `napkin.spread.spread(model, paths, times=None, *, run=None, edits=None, samples=200, seed=0,
  jobs=1, progress=None, cancel=None)` -> `MonteCarlo` (`napkin.engine.uncertainty`): `.central`
  (a `report.Report`), `.samples` (`Sample(seed, values[path][time], draws, near_ties, stopped)`),
  `.spreads` (`Spread(path, t, unit, label, summary, drivers)`), `.spread(path, t)`, `.refused`.
- `napkin.engine.expectations`: `summary`, `mean`, `quantile(values, p)`, `exceedance(values, v)`
  -> `Estimate(value, low, high, confidence, n)`; `Summary(estimated, central, mean, sd, sem, least,
  greatest, percentiles, reason)`; `spearman`.
- `napkin.engine.study`: `edits_for(model, edits)`, `configurations(model, runs, edits)`,
  `run_all(program, configurations, work, jobs=)`, `study(model, runs, edits, jobs=)`, `Cancelled`.
  `package.py`: `EDIT_LEVELS` -> `napkin.model.runs.LEVELS`; `resolve_edits` -> `configurations`.
- `napkin.engine.sampling`: `SamplingSettings(samples, seed)` (no `method`), `sample_seed`, `sampled`.
- For `napkin/__init__.py`: export `spread` ('napkin.spread'), `study` and `monte_carlo`; drop
  `evaluate_study`, `evaluate_uncertainty`, `uncertainty_report`, `sample_result`; `Session` waits
  for S7.
