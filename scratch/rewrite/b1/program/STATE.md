# B1-P state: the program (napkin/program/, tests/program/)

## Done
- Read the brief, COMMON-B, g0-decisions, spec, PLAN (G0 changes, choice 1, B1), a2/ref/model.py,
  a4a R-01/02/07/08 + 3.4, a4b R-01/02/04/07 + spike/program.py, a1/types.md, core expr/ops/units.

## Design (decided)
- Modules: refs.py (reads of an expression: Path with a start and steps, Reduce, Draw, Choice,
  Since, Elapsed, Delayed, EnumValue, TIME; Expr = core node + reads by name; Formula),
  parts.py (Unit, types, Value, Endpoint, allocations, Flow, statements, steps, Trigger, Event,
  Solver, Status, Assert, Member, Template, Program), config.py, record.py, check.py (resolver +
  checker, codes), build.py (handles X, part constructors, Builder.finish), canonical.py.
- A Path start: THIS, ROOT, ITEM, Named(member id), Local(bare name of the scope), Instances,
  Literal, Where, By, Lookup. A path through a collection is a projection (as in the language).
- Units: a table of spellings (L/h, person*year) with dimension and exact scale; `q(n, unit)` core
  call in expressions; the builder composes spellings with `*` and `/` over declared units.
- Table rows with ids are sorted by id (R-A4a-02), so a reordered table gives equal bytes.
- Setup statements of the root are round zero (R-A2-05); later starts use `when t >= T` triggers.
- Record: Key(owner, steps), pieces (t, value, rate), trace entries with round, manifest.
- Config canonical bytes leave out the request (R-A4a-08); seed only in sampled mode.

## Done (code)
- napkin/program/{__init__,refs,parts,config,record,check,build,canonical}.py written, linted;
  the docstring tank builds, finishes and gives equal bytes for two builds.

## In progress
- tests/program/examples.py: ~65 examples (each acceptance row; variants; pinned delivery
  experiments; keyed lookup; D2 overrides), with ROWS mapping each acceptance row to examples.

## Remaining
- tests/program/{__init__,test_examples,test_check,test_canonical,test_record}.py, lint, message.
