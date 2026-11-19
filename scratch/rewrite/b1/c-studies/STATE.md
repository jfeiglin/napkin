# C-S: studies and runs — state (in progress)

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
- store.py rewritten (records; one entry per key; `covers`/`served`/`_widened`; programs kept once
  by digest; locks; LRU limit; `verify` runs an entry again). tests/test_store.py (16) passes.
- sampling.py (`SamplingSettings(samples, seed)`, `sample_seed`, `sampled`, `stream`), study.py
  (`edits_for`, `configurations`, `run_all` with a spawn pool, `study`, `Cancelled`),
  expectations.py (`Estimate`, `Summary`, `mean`, `quantile`, `exceedance`, `summary`, `spearman`),
  uncertainty.py (`monte_carlo` -> `MonteCarlo`, `Sample`, `Spread`, `stopped`), spread.py
  (`spread(model, paths, times, run=, edits=, samples=, seed=, jobs=)`).
  tests/engine/test_monte_carlo_study.py (16) passes.
- Next: test_expectations, test_sampling (drop latin/sobol tests), test_public_engine (study),
  test_spread; delete test_admission_scope; engine/__init__.py exports; delete model/analysis.

## Decisions
- Reuse rule: one entry per key holds one record; it serves a request with a horizon at or before
  its own and values it holds, cut to the request (`served`); a miss runs again with a request wide
  enough for both, which replaces the entry. Failed runs are stored; paused runs are not.
- Thread settings are not in the key (a run under other threads agrees within tolerances).

## For C-K
- (to come)
