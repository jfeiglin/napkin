# Values that the engine finds, for networks

**Status:** draft.

This page plans five engine features that let napkin model networks: places joined by routes, with
amounts on the routes that must balance and a best allocation within limits. The first feature is a
new kind of value, which the engine finds so that stated conditions hold together. The other four let
such a model run at a large size, with its places and routes in tables, and let a reader edit it and
read its report as for any other model. Nothing in the features knows what a place or a route is: the
author writes them as things, and the physics of a route as plain formulas. The references to files
and lines were checked against the code on 2026-11-17.

## The need

### Networks need two calculations that napkin cannot make

Many systems are networks. Two calculations recur in them:

- **A balance.** The amounts on all routes depend on one another, and they must balance at each
  place. They are simultaneous equations.
- **A best allocation within limits.** Serve the most need, or cut the least, within the capacity of
  each route and each source. This is an optimization over the whole network at once.

Some use cases:

| Use case | Places | Routes | What the engine finds | A goal |
| --- | --- | --- | --- | --- |
| Water between utilities (the ties between the systems of a place in `water_controls_wipe`) | Utilities | Ties and pipes | The water on each tie, and the need served | Serve the most need |
| Medical supply (`iv_fluid_shortage`) | Makers, distributors, hospitals | Shipments | The amount on each route | Serve the most courses of care |
| Patients moved between hospitals | Hospitals | Transfers | The patients moved on each route | Leave the fewest patients without a bed |
| Evacuation | Zones and shelters | Roads | The people on each road | Move the most people in time |
| Electricity | Substations | Lines | The power on each line, from the physics that the author writes | Cut the least load |
| Fuel and gas | Terminals, stations, users | Pipelines and trucks | The amount on each route | Cut the least supply |
| A market | Sellers and buyers | Trades | The amount of each trade, so that supply equals demand | Clear the market at the least cost |
| Repair work | Crews and sites | Assignments | The work of each crew at each site, as a rate | Restore the most service |

napkin cannot make either calculation today:

- Each value comes from values that are already known, in a fixed order. The compiler refuses a
  circle of formulas (the code `cycle`, [compiler.md](../compiler.md), "What is known for a
  structure"). This is deliberate: it makes each value traceable and provable.
- `assert` checks a condition. It cannot make a condition true.
- A share splits one stock among the flows that take from it ([language.md](../language.md), §2.5).
  It does not balance a network.

The cases of the catalogue needed no more until now.

### A large network does not fit the paths of today

A model with a table runs in the hybrid core: one class of rows is one family, and the engine runs a
family on arrays ([engine.md](../engine.md), "Tables and tiers"). Four limits stop a network of tens
of thousands of routes:

- **Two links into one class.** A row with two links into one class is a class of one
  (`napkin/model/hybrid.py:229-235`), and the plan refuses two links of a space into one class
  (`napkin/engine/timeline/plan.py:497`). A route has two ends in the same class of places, so each
  route would be a class of its own, and the fast path would fall back to the flat build.
- **No list of the routes that end at a place.** A cell of a table names one entity, never a list
  (`napkin/model/language/resolve.py:435`). A place cannot find the routes that end at it without a
  list that the author writes by hand.
- **No edit of a row.** With `--set`, `--edits` or `--option`, `napkin run` writes each row of the
  table out ([cli.md](../cli.md), "A model with a table"; `napkin/commands/run.py:104-121`). A sum
  over more rows than the limit of 150 operations one inside the other is then refused.
- **The flat path elsewhere.** `evaluate_study`, `napkin compile`, `napkin draw`, the catalogue's
  check, its tests (`tests/helpers.py:30`, `scenarios/tests/test_catalogue.py:45`) and the publisher
  all build the flat structure, which a model of 80,000 rows cannot use.

### The scale to reach

The design aims at a network of about 30,000 places, 35,000 routes and 15,000 sources, solved at
each hour of a week, with failures that spread from route to route (a cascade). The national power
grid of a large country is one network of this size, and other use cases of the table above can
reach it too. These sizes are targets of the plan, not measurements of a model.

## The scope

The five features:

| Feature | What it adds |
| --- | --- |
| A. Found values | `find`, `make` and `goal`: values that the engine finds so that linear conditions hold, with the best values by a linear goal |
| B. Reverse lists | `let routes_in: [Route] by to`, and two links of a row into one class without a class of one |
| C. Edits on the rows of a table | An edit document that sets an input of any row, checked once on arrays |
| D. Models with a table everywhere | Each public path runs a large model with a table through the hybrid core |
| E. Reports and the run store for table runs | The rows with events, the rows that a reader names, exact peaks, a stored report, and a process that keeps a compiled model |

Not in the first version:

- conditions or goals that are not linear in the found values, and found values that must be whole
  numbers;
- a derivative through a solve, and the analysis of the dynamics (`napkin/dynamics/`) of a model
  with found values;
- `--option` combinations of a model with a table, which stay on the flat path;
- a native tier for formulas, unless the speed gates need it;
- any one model of a network: each use case is a model of its own, written with these features.

## The design

### A. Found values

An example: towns that share water through pipes, in the syntax of today. Only `find`, `make` and
`goal` are new, and the two reverse lists are feature B:

```
Town:
    let pipes_in: [Pipe] by to          # Feature B: every Pipe whose `to` is this town
    let pipes_out: [Pipe] by from
    input supply: Mgal/day = 10 Mgal/day in 0 Mgal/day to 50 Mgal/day  @r
    input need: Mgal/day = 8 Mgal/day in 0 Mgal/day to 50 Mgal/day  @r
    find used: Mgal/day in 0 Mgal/day to supply  @r
    find served: Mgal/day in 0 Mgal/day to need  @r
    make used + sum(pipes_in.carried) is served + sum(pipes_out.carried)  @r
Pipe:
    let from: Town
    let to: Town
    input capacity: Mgal/day = 5 Mgal/day in 0 Mgal/day to 20 Mgal/day  @r
    find carried: Mgal/day in 0 Mgal/day to capacity  @r
goal most sum(Town.served)  @r
```

A network with physics on its routes is the same model. The author writes the physics as a plain
`let`, and the engine knows nothing of it. For example, the power on a line in the usual linear
approximation of a power grid, where `angle` is a found value of each end:

```
let carried: MW = (from.angle - to.angle) * susceptance if up else 0 MW
```

**The lines.**

- `find x: U in lo to hi [near n]`. The type and the range are necessary, and the engine keeps the
  value in the range. `lo`, `hi` and `n` read only values that change at moments. `near` is 0 when
  the line does not give it, clipped into the range.
- `make L is R`, `make L <= R` or `make L >= R`, each with an optional `when K`. The condition is
  linear in the found values; `<`, `>`, `and`, `or` and `not` are refused. `K` reads only values that
  change at moments, and when `K` is false the condition is dropped: for example, a route that is
  down.
- A `make` can be under a thing or at the top level.
- `goal least E` or `goal most E`: at most one in a model, linear in the found values.
- Each of the three cites a record, as an input does.
- A formula of found values is a plain `let`.
- The words: `find` and `make` are verbs of ASD-STE100. `holds` is not used, because the docs use it
  for `assert`. `least` and `most` are not `min` and `max`, which are functions.

**One answer.** Among the best answers, the engine takes the one nearest to `near`: the answer with
the least Σ((x − near)/(hi − lo))². That answer is unique, and it does not depend on the units. So:

- a cut that is necessary spreads evenly over the places that can take it;
- a source moves as little as it must from its normal output, when `near` is that output;
- a network whose values are fixed only up to a constant, such as the angles of a power grid or the
  heads of a water system with no fixed level, needs no reference place.

**Limits of the first version, checked from the structure.** Conditions and the goal are linear in
the found values. Coefficients, ranges, `near` and `when` read only inputs, lets of inputs, named
states, and number states that only steps change. They read no stock, no `t`, no found value in a
range, and no output.

**No new class of crossing.** A found value is a function of values that change only at moments, and
the engine solves again after each step that writes one of them. So found values are constant between
moments. A condition on a found value is a discrete trigger; a flow at a found rate is a straight
line, exact between moments; and an output that reads only such values has an exact peak, read at the
moments.

**Failures.** Two new codes stop a run: `infeasible`, which names the island and its worst
conditions, and `solve`, a residual above the tolerance after the polish. A problem cannot be
unbounded, because each range is finite. A numerical failure invalidates the run, as every
numerical failure does.

**Derivatives.** A derivative through a solve is unsupported in the first version.
`napkin/engine/timeline/influence.py` adds conservative edges from each value that a solve reads to
each found value of its island, so a derivative that it calls structurally zero stays zero.
`napkin/dynamics/` refuses a model with `find`, by name.

**Evidence.** The records of `find`, `make` and `goal` count as used in the evidence trail.

### B. Reverse lists, and two links into one class

`let routes_in: [Route] by to` lists every `Route` whose link `to` names this thing, in the order of
the model. The compiler binds it, and no instance binds it. It works on things written out and on
tables.

- `Space.links` is keyed by the pair (space, link), not by the target space. This changes `Plan.how`
  (`plan.py:531`) and lifts the refusal of two links into one class (`plan.py:497`).
- A reverse list reads the index of the rows that link to each row, which the plan already builds
  (`Space.linked_from`, `plan.py:498-502`).
- `classes` in `napkin/model/hybrid.py` no longer makes a row with two links into one class a class
  of one (`:229-235`). It keeps that rule for a link into its own class. The representative records
  which link a read came through.

### C. Edits on the rows of a table

An edit can set an input of any row. The engine is mostly ready for it: a `Run` takes an array for
each input (`napkin/engine/timeline/run.py:724-737`), and `Run.admit` proves the run again over the
ranges that it was given (`run.py:3390`).

- **One check.** A new `Hybrid.rows()` gives `{set: {row: representative}}`. (`rows_of`, at
  `hybrid.py:546`, gives the ranges of the rows of each class, which is another job.)
  `napkin/model/runs.py` resolves `set.k.member` to the `Input` of the representative, with the
  row's cell as its default, so the same checks of the values run. `values_of` gives an array over
  the rows.
- **One transaction.** In each declared run: `Plan.of(core, run, values)` and `Run.admit`, with the
  checks of the inputs of each row and the proofs again over the given ranges. `timeline.admit`
  takes the arrays of the families.
- **Diagnostics.** The `ValueError` of `bound_reads` (`run.py:729`) becomes a diagnostic, and an
  error names `set.k.member`.
- **Classes stay.** A class records no value of an input (the module docstring of `hybrid.py`), so
  an edit moves no row to another class.
- **Entry points.** `reports.study_of(…, edits=None)`, and `napkin run --set` and `--edits` through
  `run_table`, which no longer write the rows out. `--option` combinations stay on the flat path.

### D. Models with a table everywhere

`evaluate_study`, `napkin compile`, `napkin draw`, `tools.check`, the catalogue's tests and
`tools.publish` route a model through `hybrid.compile` and `study_of` when it has a table, or when its
flat build is refused for its size. The structure of the model decides, never its name. The envelope
of the report stays the same.

### E. Reports and the run store for table runs

- `table_run.affected`: the rows with any event, up to a cap, with a count of the others.
- `table_run.rows`: the outputs of the rows that `--rows` names. It can name a whole small table,
  such as a table of regions.
- An output that changes only at moments is recorded at each moment. Its peak is exact, and
  `PEAK_WORK` (`reports.peaks`) never thins it.
- The run store keeps table runs. The full record of a run at the scale above is estimated at about
  100 MB, so the store keeps its report.
- A process that keeps a compiled model: a Python object, an extension of `napkin.Session`, that holds
  the hybrid core and runs many edit documents.

### Speed

| What is slow at scale | The fix |
| --- | --- |
| Each command compiles 80,000 rows | The process of feature E keeps the compiled model |
| Each edit is checked in each run, for each row | One check on arrays; only the classes that an edit touches are proved again (feature C) |
| The public paths write the rows out | Feature D |
| Each route would be a class | Feature B |
| A solve at each hour over a large network | The fast path: solve the least-squares (KKT) system of the equalities toward `near`. Take that answer when the ranges and the inequalities hold and the goal is at its best over the box of the ranges, which is the usual case, with no cut. Keep the factorization of each island; an hourly step changes only the right-hand side, so it costs one back-substitution |
| A route that fails changes a few coefficients | A Woodbury update from the rows that change; a new factorization after K updates, or when the update is ill-conditioned |
| A cut is necessary | A linear program, warm-started from the island's last basis; then a quadratic program for the one answer nearest to `near`; then one polish solve of the final active set, in a canonical order. The polish makes the result the same bit for bit, whatever the history |
| Every island at every moment | Only the islands whose inputs change. A memo by the digest of a problem reuses the answers of a normal day. Islands run in parallel, each with a solver of one thread |
| A family falls to the general tier (Python for each row) | The families of a network model stay in the fast tier, and a test fails if one falls |
| The peaks of every row | Exact peaks at moments (feature E) |
| A report of 80,000 rows | Only the rows with events (feature E) |
| The same study again | The run store (feature E) |
| Formulas in Python | A native tier, later, and only if the gates need it |

**The solver.** First choice: the HiGHS solver that SciPy bundles, through the binding of
`napkin/engine/continuous/highs.py`. That binding gives the results of `linprog`, bit for bit
(`tests/engine/test_highs.py`), but it reads SciPy's private interface (`scipy.optimize._highspy`)
and makes a new solver for each program, so it has no warm start today. If it cannot give a warm
start or a quadratic program, use highspy (MIT licence). highspy is a new dependency: it needs a
wheel for aarch64 and the owner's approval.

## The changes

**Compiler (`napkin/model/`):**

- Lexer and parser: `find`, `make`, `goal`, `least`, `most`, `near` and `by` in `NOT_UNITS`
  (`language/lex.py`); `find` in `FIELD_KINDS` (`language/parse.py:51`); `make` and `goal` read as
  `assert` is read, under a thing (`thing()`, `parse.py:756`) and at the top level (`parse.py:584`);
  new nodes in `language/nodes.py`; the words in `KEYWORDS` of `language/format.py`.
- Identity: `identity` in `language/evidence.py` leaves out the new fields of a file that does not
  write them, so the `model_hash` of each model of today stays the same ([extending.md](../extending.md),
  "The identity of a model").
- Resolution: `language/resolve.py`, `semantic.py` and `resolved.py`.
- Linearity in one place: a new `napkin/core/linear.py`, `linear(node, found) -> (constant, {name:
  coefficient})`. It goes through `+`, `−`, `*` and `/` by a side that reads no found value,
  `if`/`else` whose test reads none, lets and `sum`. Anything else is the code `solve`. The compiler
  and the engine both use it.
- Builder: `lower/builder.py` writes the new parts `found`, `conditions` and `goals` (`SECTIONS` of
  `structure.py`). `lower/starts.py` keeps what the conditions read.
- Checks (`analysis/structure.py`): `discrete_names` (`:103`) adds the found names, and a new
  `_solve_errors` checks the units, the linearity and the limits of the first version.
- Proofs (`analysis/values.py`): the interval of a found value is its range, so the asserts and the
  outputs that read it are proved. A tally fed at a found rate gets its sign proved. Feasibility is
  checked when the model runs.
- Hybrid core (`hybrid.py`): feature B in `classes`, and `Hybrid.rows()` for feature C.

**Engine (`napkin/engine/timeline/`):**

- A new `solve.py`, with a `SolvePlan` that `Plan.made` builds. For each condition it keeps its space
  and its terms. Each value that a coefficient, a range or `near` reads gets a reader of the kind
  `solve`, so `Run.closure` reaches it.
- In `Run.apply` (`run.py:2222`), after the writes and before `closure` (`run.py:2189`), the islands
  whose inputs changed are solved again. The found values that change are written as values, and
  events read them as they read any value. `Run.start` solves once.
- Islands are the connected parts of the bipartite graph of the conditions and the found values, with
  nonzero coefficients only (`scipy.sparse.csgraph`). Nothing in the engine knows what a place or a
  route is.
- `plan.py`: `Space.links` by (space, link) for feature B.
- `reports.py`: `study_of` with edits, `table_run.affected`, `table_run.rows` and the exact peaks.

**Schemas and identity:** `report.schema.json` gets `solves` (the counts by path, the moments with a
linear program, the largest residual) and the new codes. `edits.schema.json` needs no change. The
implementation hash covers the new modules, and `CLOSURE` in `tests/test_api.py` names them.

**Commands and tools:** `napkin run --set` and `--edits` on a table model (feature C); the paths of
feature D in `napkin compile`, `napkin draw`, `tools.check` and `tools.publish`; the run store
(`napkin/store.py`) for table runs.

**Docs:**

- [language.md](../language.md): reverse lists in §2.3; a new section "Values that the engine finds";
  the refusals; the reserved words.
- [compiler.md](../compiler.md): the new parts, linearity, the proofs, the changes of the hybrid core.
- [engine.md](../engine.md): "One moment", a new section "The solve", "When a run stops", "Tables and
  tiers", "The run store".
- [python-api.md](../python-api.md): the new parts, edits of rows, the process that keeps a model.
- [cli.md](../cli.md): "A model with a table".
- [extending.md](../extending.md): "A declaration that the engine solves".
- [design.md](../design.md): the measurements, the limits that remain, and each decision with its
  reason (the words, the rule of the one answer, the solver and any dependency, reverse lists, the
  edits of a table model, the run store, the minimums of speed).

## The order of the work

1. **S0, measure first.** On a synthetic network of 30,000 places and 35,000 routes, and on
   published test networks of a similar size where their terms allow (for example benchmark cases
   of power grids or of water systems): a KKT factorization and its Woodbury update, and warm linear
   and quadratic programs through each binding.
2. **B, C and D**, in parallel.
3. **A on the flat path.**
4. **A in the hybrid core**, with the speed work.
5. **E.**

## The checks

The tests follow [CONTRIBUTING.md](../../CONTRIBUTING.md#testing): independent mathematics,
properties and counterexamples, and synthetic models in `tests/` with generic names.

**Feature A:**

- Exact closed forms with `Fraction`: the flows of networks of two places and of a triangle, and the
  projection of the one answer, x = n − W⁻¹Aᵀ(AW⁻¹Aᵀ)⁻¹(An − b).
- The towns of the example, written out by hand: the best value equals the minimum cut, found by
  enumerating every cut of small random graphs.
- Small linear programs: the optima by exact enumeration of the vertices.
- Properties: the residuals and the ranges hold; the goal is monotone in a capacity; two parts that do
  not connect give the results of two models; the order of the rows does not matter; a run equals its
  repeat, and equals a run that reaches the same problem by another history, bit for bit.
- Refusals by name: a condition that is not linear, `<`, a range that reads a stock, `t` in a
  condition, a problem that is infeasible.

**Feature B:** a model written out and its table form give the same sums; a network of 30,000 rows
stays a few classes; the flat build and the hybrid build of a small file agree.

**Feature C:** on small tables, the flat study of the same edits is the definition: each outcome,
status and time. A transaction is refused when one run fails.

**Mutations.** As the ledger records for other features: drop a term, flip a sign, skip a solve,
merge islands, skip the polish, and the like for B and C. Each mutation must fail a test.

**Gates.** The tests assert counts, never times, so that they do not depend on the machine:
one factorization for each structure of an island, none for a step that changes only the right-hand
side, and the rows evaluated after a step. The times are measured and recorded in
[design.md](../design.md), "What was measured". Proposed minimums for a network at the scale above,
for the owner to set:

| Measure | Proposed minimum |
| --- | --- |
| Compile of the network | 30 s or less |
| A week of hourly solves with no failure | 60 s or less |
| 1,000 places or routes down, with a cascade | 120 s or less from a cold start; 60 s or less in the process that keeps the model |
| Memory | 4 GB or less |
| Growth of the time with the size, from about a third of the scale to the full scale | a power of 1.3 or less |

**Acceptance.** A network model at the scale above needs each of these, and each has a synthetic test
model:

- `find`, `make` with `when`, and `goal least` on tables of 30,000 places, 35,000 routes and 15,000
  sources, with two links into one class and reverse lists;
- an event that reads a found value, such as a route that trips when the amount on it passes a share
  of its rating: `abs(carried) >= margin * rating`;
- a flow at a found rate, such as need that is not served, into a tally;
- edits of the inputs of any rows through `napkin run --edits`, `evaluate_study` and the process that
  keeps a model;
- a model with a table through `tools.check`, `tools.publish`, `napkin compile` and `napkin draw`;
- the outputs of the rows of a small table, such as regions, in the report;
- the speed gates, met or reported.

## The risks and the open questions

**Decisions for the owner**, each recorded in [design.md](../design.md) before its part is built:

- the new words of the language, and the rule of the one answer nearest to `near`;
- the minimums of speed above;
- highspy as a new dependency, if S0 shows that the binding of today cannot give a warm start or a
  quadratic program;
- `--set` and `--edits` on a table model no longer write the rows out, as they do today;
- the run store keeps the reports of table runs, not their full records.

**Risks:**

- `highs.py` reads a private interface of SciPy, which a new version of SciPy can change. A warm
  start through it is not yet tried.
- The fast path assumes that a cut is rare. A network that often needs a linear program is slower,
  and S0 must show by how much.
- A Woodbury update can lose accuracy; the rule to factorize again must be tested on ill-conditioned
  cases.
- Results that are the same bit for bit, whatever the history, rest on the polish solve. A test must
  try histories that reach the same problem by other paths.
- Some use cases want whole numbers, such as crews or beds. The first version finds rates and shares,
  not whole numbers, and a model must say so where it matters.
- The identity of the models of today must not move: `tools.compare` over the whole catalogue shows
  it before the language changes land.

**Open questions:**

- Which published test networks S0 uses, and on what terms.
- The cap of `table_run.affected`.
- Whether a `goal` can sit under a thing, or only at the top level.
