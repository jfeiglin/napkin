# C-S: studies and runs — state (in progress)

Brief: `briefs/c.md` (C-S) with `COMMON-B.md`; PLAN "Changes after G0" 10-13; `b1/c-report/STATE.md`.
Coordinator (2026-11-19): do the choices last (session resolver, picks, controllers, `Run.resume`,
`test_decision_resolver.py`); if reached before a new word, stop and list them as not done.

## Order
1. `napkin/store.py`: records, key, reuse rule, locks, size limit, verify. tests/test_store.py.
2. `napkin/engine/sampling.py` (seeds of samples; `stream` kept), `study.py` (configurations of
   named runs, runs in processes), `uncertainty.py` (Monte Carlo), `expectations.py` (plain
   estimators), `napkin/spread.py`. Tests: test_monte_carlo_study, test_public_engine,
   test_expectations, test_spread, test_sampling; delete test_admission_scope.
3. Last: `napkin/session.py`, tests/test_session.py, test_decision_resolver.py (choices).

## Done
- (nothing yet)

## Decisions
- (to come)

## For C-K
- (to come)
