# S4b-E state: the engine, part two of S4 (chance, choices and checks) — done

Brief: `briefs/s4.md` (S4b-E) with `COMMON-B.md`, `s0-engine.md`; part one in `b1/s4a-engine/STATE.md`.
Baseline: part one committed (8d5ae95); 3,472 live tests.

## Design (decided; docstrings of chance.py, plan.py, run.py, moment.py, triggers.py hold it)
- chance.py (new): draws and choices. Engine name `owner|site` (owner = occurrence id, trigger key,
  member id, '' root/setup); uniform number = first 64 bits of SHA-256 of `seed|site|owner`, as the
  oracle (sampled runs equal the oracle's); a firing's owner is `key!n` (n from 1). Median:
  numeric median, categorical most likely eligible (first on tie); weights are scaled, any sum.
  Lazy env in `Run.truth` (`_Reads`): an untaken branch of `a if c else b` draws nothing.
- switch on a bare draw/choice: guards first, barred outcomes out, none eligible -> else, no draw.
- choices: forecast = keyed draw; player = pick (site, owner); missing -> `Paused` -> record whose
  trace ends with a `pause` entry (details: site, actor, options, sees, weights, kept, starts);
  `Run.resume(*picks)` goes on in place (Moment.held) and equals a replay with the picks.
  A player's choice outside a stage/setup (entry, delay, firing) fails the run.
- `elapsed(x)` = node `t - x|changed` (kind CHANGED, from `Run.changes`, tx rule of R-A2-08);
  `delayed(x, d)` kind DELAYED: past of x from the recorder's pieces; d = 0 committed; held x with
  fixed d changes at c + d (moments via `Run.delayed_at`); a condition or a rate that reads the
  past of a moving value (or a delay not fixed) is a diagnostic. Reader derives both from x's history.
- `.mean`/`.std` (kind DESCRIBED, closed forms `chance.described`), recorded under their path.
- assertions over state (`plan.checks`): after each round, just after each moment, watched.
- distribution assignment in a stage; a distribution value copied from another through a path.
- allocation assignment in a stage (`Plan.allocate`); endpoints of an occurrence's own store
  (were silently ignored before; the oracle ignores them too).

## Done
- 9 examples in SUBSET with the oracle; engine+core+program+reference passed (see final run).
- new: test_assertions (7), test_random_draws (200; 1000 deep), 2 tests in test_occurrences.
- ported in place (dormant-listed): test_chance, test_availability, test_firing_values, test_pause,
  test_play, test_settled_decisions, test_timeline_outcomes, test_timeline_play (102 passed).
  test_decision_resolver stays dormant (resolver of napkin/session.py: stage C).
- deleted timeline/choices.py, state.py, reports.py (reports.py was already broken).

## Found (reported, not mine to fix)
- oracle `read_past` reads `view.t - D` (the run's end) for a formula read after the run, and fails
  ("no record at t = 0 h") for a trigger on `delayed` at the setup; the engine follows the spec.
- oracle keys a draw in a trigger body or `reset after` by the member, not the firing (R-A2-17).
- oracle demands categorical weights that add up to one; the checker admits any nonnegative weights.
- part one: a rate that reads `since(e)` is held between moments; its actual rate is not recorded.

## Fixes after the join (fcbf97a; coordinator's two bugs) — done
- `since(e)` is the node `t - latest` (Dynamic op `latest`: the newest start, fails before the
  first): its set moves, its contact is predicted as one on `t`, its rate is recorded.
- Every evaluation reads lazily (`timeline/reads.py`, `Reads`/`lazily`): run (stage, formula,
  delay; the start retries on `_Unknown`), triggers' sides, collections' tests and keys, recorder
  and reader, family/lines `Columns` (lazy columns; per-row fallback), sparse `Vector` (lazy
  columns and reads, NaN for constants with none, per-row fallback), component (a parameter with
  none is left out with its reason; `continuous/system.Formulas` evaluates formulas where read;
  the zero proof and the closed forms fall back where a fixed part has none).
- Fixed in passing: `plan._bound` crashed when a read with no shape preceded a path or `t`.
- tests: test_lazy_reads.py (11; each way; oracle where it can); random event programs now guard
  stages and triggers with `count(e) > 0 and since(e) >= d` (300, 2000 deep, all pass).
- oracle departure seen: it does not move a store whose rate reads `t` (holds the rate of the moment).

## Not done
- assignment of a formula or a collection in a stage (refused "(S4)"); keyed reads of moving values
  and keys (part one's refusals, "(S4)").
