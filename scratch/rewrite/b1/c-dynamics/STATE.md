# C-Y state: dynamics over the component of a program — in progress

Brief: `briefs/c.md` (C-Y) with `COMMON-B.md`; PLAN "Changes after G0" 10-14. Owner:
`napkin/dynamics/`, `tests/dynamics/`. Engine read only (`timeline/component.py`, `sparse.py`,
`ways.py`, `plan.py`, `run.py`); old code at `8488047`.

## Plan
- field.py: `VectorField(program, configuration)` from the engine's own instances at the start of
  a run (`Run(Plan.of(...)).prepare()`): each moving set (way COMPONENT or SPARSE) gives its rates.
- equilibria.py: unchanged math. continuation.py: `Family` over a program, an input or `t`.
- basins.py, sensitivity.py: over `napkin.engine.run` and `read`.
- tests/dynamics/: models with `napkin.program.build.Builder`, closed forms.

## Done
(nothing yet)
