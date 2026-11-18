# B1-P state: the program (napkin/program/, tests/program/)

## Done
- napkin/program/: refs.py (reads: Path with start + steps, Reduce, Draw, Choice, Since, Elapsed,
  Delayed, EnumValue, TIME; Expr = core node + reads by name; Formula), parts.py (Unit, Enum,
  types, Value, Endpoint, Priority/Proportional, Flow, Assign/Move/Start/If/Switch/Case,
  After/Until, Reset, Trigger, Event, Binding/Constraint/Objective/Solver, Status, Assert, Member,
  Template, Program), config.py, record.py, check.py (Resolver + 30 codes), build.py (handles X,
  part constructors, Builder.finish), canonical.py.
- tests/program/: examples.py (65 examples, ROWS maps all 32 acceptance rows), test_examples,
  test_check (58 malformed cases, one per code or more), test_canonical, test_record, test_config.
- `NAPKIN_STORE=off .venv/bin/python -m pytest -q -p no:cacheprovider tests/program`: 421 passed.
  tests/core: 395 passed. ruff check + format clean.

## Decisions (and why)
- A path through a collection is a projection (the language's own rule); collections, `where`,
  `by`, `.at` are starts of a path, so one Path record covers members, rows, occurrences, flows.
- Names in a node are spellings of their reads, made canonical at finish (deterministic bytes).
- Members named by id in paths (`Named`), links of members as row numbers; rows with ids sorted by
  id (R-A4a-02), so reordered tables give equal bytes.
- Unit table of spellings with dimension + exact Fraction scale; builder composes `*` `/` (D12).
- Setup statements = round zero (R-A2-05); later starts use `when t >= T` triggers.
- Tally: no mark in the program (D10 removed `cumulative`); route_end refuses SOURCE/SINK only.
- Expected values in the value's declared unit; trace rounds 0 (setup), then 1, 2, ...
- Budgets default 10,000 LPs (fair sharing) and 100,000 iterations (distance).
- An ineligible pick fails the run (dispatcher_player_no_spare).
- two_junctions_solver: solver over the four requested rates, feed left local (spec's "four").
- network_kw writes every power in kW/kWh (strength 0.001 kW).
- A status display ends with its one unconditional case; a where tests fixed fields only
  (where_live); a start passes one argument per parameter (arguments).
- Trace kind `solve` added (row 20 needs it); draw site = holder origin + `.draw[k]`.

## Remaining
- Not mine: register napkin.program in pyproject `packages` and tests/test_api.py CLOSURE.
- Not checked: full expression units (front end's type checker); two solvers competing for one
  binding resource; a receive-only tally at a route end (no mark exists).
