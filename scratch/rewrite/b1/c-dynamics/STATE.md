# C-Y state: dynamics over the component of a program — done

Brief: `briefs/c.md` (C-Y) with `COMMON-B.md`; PLAN "Changes after G0" 10-14. Owner:
`napkin/dynamics/`, `tests/dynamics/`. Engine read only; old code at `8488047`.

## Done
- field.py: `VectorField(program, configuration)` runs `Run(Plan.of(...)).prepare()` (start values,
  sizes, bounds, ways at 0; no setup, no rule) and reads each moving instance's rates:
  `ComponentWay.component.field.rates` or `Sparse.field`, restoring their evaluation counters as
  `ComponentWay.delivered` does; a component's keyed reads by the time are refreshed at the time
  read. State = stores of every moving instance, program order; active = stores in
  `Connected.reads`; passive = the rest + stores of sets that do not move; `held` = stored values
  that the rates read and no flow meets. `configured` (inputs, by type), `started` (start values:
  a program of its own), `value_at`. Refused by name: a moving declared solver; a moving set that
  waits for the setup's solve.
- equilibria.py: math unchanged. continuation.py: `Family(program, configuration, parameter)`;
  `Inadmissible` = ConfigurationError, SimulationError or ExpressionError at the start; the stop
  'inadmissible' (documented before, never set) is now set.
- basins.py: thresholds over `engine.run`; a failed run raises. sensitivity.py: `input_factors`
  (an input's admitted range), `run_function` (a path at a time, D10).
- tests/dynamics: models.py with `Builder`; the six rows ported. New: sparse pond, keyed read by
  the time, time driver, 'inadmissible' stop, drain thresholds (closed form, fast), failed run,
  refusals. Cusp thresholds `deep` (13 s each: Radau near an unstable rest).
- Counts: the 5 test files 55 passed, 2 deselected (deep: 2 passed); tests/core 395 passed.
- `tests/dynamics/` can leave tests/dormant.txt whole: no file reads the catalogue.

## Decisions
- Several moving sets are one field (block derivative): ported tests have two components.
- Sparse sets too, by the engine's own field: cyber_learning_loop has legs and junctions.
- Start values change the program (`started`), not the run (S6-F C1: a configuration sets inputs).
- The field is taken before the setup (the old contract: no rule fires).

## For others (no change needed)
- `sensitivity.py` imports `engine.sampling.stream` (C-S owns sampling.py): keep it.
- docs/python-api.md "Dynamics" describes the old API (stage F); `engine/runtime.py` docstring
  still says napkin.dynamics reads it.
- M: the cyber tests read old field internals (`system`, `field.values_program`,
  `rs.parameter_values`); port them over `VectorField.plan`, `.run`, `.moving` and `engine.read`.
- Engine, optional: a budget-free `rates(t, y)` on ComponentWay and Sparse would replace the
  counter restore; `Recorder.segment` fits every flow of a component even when the request keeps
  only some keys (most of a cusp run's time).
