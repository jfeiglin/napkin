# Values that the engine finds, for networks

**Status:** draft. The owner took the decisions of [the last section](#the-decisions) on 2026-11-17.

This page plans four engine features that let napkin model networks: places joined by routes, with
amounts on the routes that must balance and a best allocation within limits. Nothing in the features
knows what a place or a route is: the author writes them as things, and the physics of a route as
plain formulas.

A first draft planned five features. This draft follows a measurement of the solver paths and two
trials of the engine ([What was measured](#what-was-measured)). They changed the plan, and each
change says why. The references to files and lines were checked against the code on 2026-11-17.

## The need

### Networks need two calculations that napkin cannot make

Many systems are networks: water between utilities, medical supply, patients moved between
hospitals, evacuation, electricity, fuel, a market, repair crews and their sites. Two calculations
recur in them:

- **A balance.** The amounts on all routes depend on one another, and they must balance at each
  place. They are simultaneous equations.
- **A best allocation within limits.** Serve the most need, or cut the least, within the capacity of
  each route and each source. This is an optimization over the whole network at once.

napkin cannot make either today. Each value comes from values that are already known, in a fixed
order, and the compiler refuses a circle of formulas (the code `cycle`). `assert` checks a
condition and cannot make it true. A share splits one stock among its flows
([language.md](../language.md), §2.5) and does not balance a network.

### A large network does not fit the engine of today

- **Two links into one table.** A route has two ends in the table of places. A row with two links
  into one class of rows is a class of one (`napkin/model/hybrid.py:229-235`), so the compiler
  writes each route out. A sum over more than 150 routes is then refused: a model of 200 such routes
  does not compile.
- **No list of the routes that end at a place.** A cell of a table names one entity, never a list
  (`napkin/model/language/resolve.py:435`). And a template cannot read a list over the rows of a
  table in a line of its own (`lists_in_templates`, `hybrid.py:116`).
- **Two paths around one engine.** One engine runs every model, but a model has two compiled forms,
  each with its own study and its own report. The flat form writes each row of a table out. The
  hybrid core holds a table as columns. Edits, options, samples, play and the run store are on the
  flat side only, so a large table cannot use them (`napkin/commands/run.py:104-121`).

The design aims at a network of about 30,000 places, 35,000 routes and 15,000 sources, solved at
each hour of a week, with failures that spread from route to route (a cascade). The sizes are
targets of the plan, not measurements of a model.

## The scope

| Feature | What it adds |
| --- | --- |
| A. Found values | `find`, `make` and `goal`: values that the engine finds so that linear conditions hold, with the best values by a linear goal |
| B. Links between the rows of tables | Two links of a row into one table, a link of a row into its own table, a list in a line of a template, and `let routes_in: [Route] by destination` |
| C. One path for every model | Each public function reads the hybrid core. A model with no table is a core with no table. An edit can set an input of any row |
| D. Reports and the run store for large tables | The rows with events, the rows that a reader names, exact peaks, a stored report, and a process that keeps a compiled model |

Not in the first version:

- conditions or goals that are not linear in the found values, and found values that must be whole
  numbers;
- `make` with `<=` or `>=`;
- a derivative through a solve, and the analysis of the dynamics (`napkin/dynamics/`) of a model
  with found values;
- updates of a factorization, a memo of problems, islands in parallel and a native tier for
  formulas: the measurements do not call for them;
- any one model of a network: each use case is a model of its own, written with these features.

## The design

### A. Found values

An example: towns that share water through pipes. Only `find`, `make` and `goal` are new, and the
two reverse lists are feature B:

```
Town:
    let pipes_in: [Pipe] by destination     # Feature B: every Pipe whose `destination` is this town
    let pipes_out: [Pipe] by origin
    input supply: Mgal/day = 10 Mgal/day in 0 Mgal/day to 50 Mgal/day  @r
    input need: Mgal/day = 8 Mgal/day in 0 Mgal/day to 50 Mgal/day  @r
    find used: Mgal/day in 0 Mgal/day to supply  @r
    find served: Mgal/day in 0 Mgal/day to need  @r
    make used + sum(pipes_in.carried) is served + sum(pipes_out.carried)  @r
Pipe:
    let origin: Town
    let destination: Town
    input capacity: Mgal/day = 5 Mgal/day in 0 Mgal/day to 20 Mgal/day  @r
    find carried: Mgal/day in 0 Mgal/day to capacity  @r
goal most sum(Town.served)  @r
```

A network with physics on its routes is the same model. The author writes the physics as a plain
`let`. For example, the power on a line in the usual linear approximation of a power grid, where
`angle` is a found value of each end:

```
let carried: MW = (origin.angle - destination.angle) * susceptance if up else 0 MW
```

**The lines.**

- `find x: U in lo to hi [near n]`. The type and the range are necessary, and the engine keeps the
  value in the range. `near` is 0 when the line does not give it, clipped into the range. A range
  of no width makes the value a constant.
- `make L is R`, with an optional `when K`, under a thing or at the top level. When `K` is false
  the condition is dropped: for example, a route that is down.
- `goal least E` or `goal most E`: at most one in a model.
- Each of the three cites a record, as an input does. A formula of found values is a plain `let`.
- **No `<=` and no `>=` in the first version.** A limit on one found value is its range. A limit on
  a sum is a found value for what is left: `find idle: h in 0 h to hours` and
  `make sum(work) + idle is hours`. So each part of the rule of the one answer is in the file, and
  the engine solves one kind of condition. The two signs can come later, and they break no model.
- **The words.** `find`, `make` and `goal` start a line. `near`, `by`, `least` and `most` are words
  in their own lines only, so a model that has one as a name keeps its meaning (a test names an
  outcome `most`). `to` and `from` are reserved words of today (`language/lex.py:37`), so no link
  has one of them as its name.

**One answer.** Among the best answers, the engine takes the one nearest to `near`: the answer with
the least Σ((x − near)/(hi − lo))². That answer is unique, and it does not depend on the units. So:

- a source moves as little as it must from its normal output, when `near` is that output;
- a cut that is necessary goes to every place that can take it. The shares are not equal: the cut
  of a place grows with the square of its range. A model that needs equal shares has one found value
  for the share;
- a network whose values are fixed only up to a constant, such as the angles of a power grid, needs
  no reference place. Such a value takes part in the rule too, and a narrow range pulls the answer
  toward its `near`. The author gives it a wide range, and the modelling guide says so.

**Limits of the first version, checked from the structure.** Conditions and the goal are linear in
the found values. Coefficients, ranges, `near` and `when` read only values that change at moments:
inputs, lets of inputs, named states, and number states that only steps change. They read no stock,
no `t`, no found value in a range, and no output.

#### When the engine solves

The engine solves at the start of a run. At a moment, the rules that are due go one at a time, as
today, and the found values keep the values of the last solve. When no rule is due, the engine
solves again if a step wrote a value that a solve reads. It then reads the rules that read found
values, and their steps go. The moment ends when no rule is due. `max_steps` limits a moment, as
today.

- **Why.** Take 1,000 routes that fail at one moment. With a solve after each step, a route can trip
  on the amounts of a network with 400 of them down. That network never exists, and it depends on
  the order of the rows. And the cost follows the steps. In the trial of a cascade, 3,910 trips
  took 14 solves in this way. A solve after each step takes about 4,900.
- **What it means for a model.** The steps that go between two solves read the found values of the
  first of them. A model whose routes must trip one at a time gives each trip a delay.
- **No new class of crossing.** Found values are constant between moments. So a condition on a
  found value is a discrete trigger, a flow at a found rate is a straight line, and an output that
  reads only such values has an exact peak, read at the moments.

#### How the engine solves

An island is a set of found values and conditions that no condition joins to another set. The plan
finds the islands once, from the structure. A solve takes only the islands whose inputs a step
wrote. For one island:

1. **A first try.** Each value of the goal is put at the best end of its range, and the nearest
   step (below) runs. When the conditions hold, that is the answer: no cut is necessary. The engine
   leaves this try out when the last solve of the island needed a cut.
2. **The goal.** The HiGHS solver that SciPy bundles solves the linear program of the goal. The run
   keeps one solver for each island, so a program starts from the last basis. The binding of today
   (`napkin/engine/continuous/highs.py`) reads the same private interface of SciPy.
3. **The best answers.** A value whose reduced cost is not zero is at one end of its range in every
   best answer, and each answer that has those values there is a best one. The engine holds them
   there. So the number of the goal does not go into the next step, and neither does its roundoff.
4. **The nearest step.** A Newton method on the sparse system of the conditions finds the answer
   nearest to `near`, with an exact line search. It is new code of about 150 lines. Each of its
   trial answers is in the ranges, so the engine checks one thing: the residual of each condition.
   It also compares the goal of the answer with the goal of step 2.

What the first draft planned, and the measurements do not call for:

- **A quadratic program in HiGHS.** It took 73 s at one tenth of the scale.
- **Updates of a factorization (Woodbury), a memo of problems, islands in parallel.** A
  factorization at the scale takes 65 ms to 140 ms, and a cascade takes tens of solves.
- **highspy as a new dependency.** The bundled solver gives the warm start.

**The same result again.** The same build, computer and inputs give the same bits, as for every run
([engine.md](../engine.md#the-same-result-again)). What a solver keeps belongs to one run, never to
a plan or a process. The first draft also promised the same bits for one state of the network at
two times of a run. This draft does not: two such answers agree within the tolerance.

**Failures.** Two new codes stop a run: `infeasible`, which names the island and its worst
conditions, and `solve`, a residual above the tolerance. A problem cannot be unbounded, because each
range is finite.

**Derivatives and evidence.** A derivative through a solve is unsupported in the first version.
`napkin/engine/timeline/influence.py` adds conservative edges from each value that a solve reads to
each found value of its island, and `napkin/dynamics/` refuses a model with `find`, by name. The
records of `find`, `make` and `goal` count as used in the evidence trail.

### B. Links between the rows of tables

The hybrid core lowers one row of each class, its representative. The engine reads a name of another
class as the row that the link names. With two links into one class, both links give the same name,
so the engine cannot say which link a read came through.

- **A stand-in for each link.** In the parts of a representative, the first link into a class names
  the first row of that class, the second link names its second row, and so on. A stand-in is never
  the row that reads it. So the name says which link a read came through. The checks and the proofs
  of the compiler read two rows, as they read any two things: a difference of two ends is no zero.
- **In the plan.** `Space.links` is keyed by the name of the link. The plan writes each read through
  a link with its link (`plan.py`, `how`), and it makes no part of a row that only stands in.
- **The same rule lifts three limits:** two links into one table, a link of a row into its own
  table, and a list over a table in a line of its template. The trial made the first of them, in
  about 150 lines.
- **Reverse lists.** `let routes_in: [Route] by destination` lists every `Route` whose link
  `destination` names this thing, in the order of the model. The compiler binds it. In the engine,
  a sum over it is one sum for each row, over the rows that link to it (`Space.linked_from`).

### C. One path for every model

A model with no table is a hybrid core with no family (`hybrid.py`, `Hybrid`). So the core can
serve every model, and one compiled form needs one study and one report. The first draft kept the
two forms and gave six commands and tools a choice between them. This draft takes the choice away.

- **What reads the core:** `evaluate_study`, `evaluate_uncertainty`, `Session`, the run store, each
  command that reads a model, `tools.check`, `tools.publish` and the tests of the catalogue. A model
  with no table still gives its whole record (`Trajectory`).
- **Edits.** An edit sets an input of any row (`set.k.member`). A `Run` takes an array for each
  input already (`napkin/engine/timeline/run.py:724-737`), and `Run.admit` proves the run again over
  the ranges that it was given (`run.py:3390`). The values are checked once, on arrays, as one
  transaction over the declared runs.
- **What is left of the flat form.** It writes a small table out, as the definition in the tests
  (`hybrid.problems`).
- **What the table side lacks today:** edits, options, samples, play and the run store; an output
  that reads an output with a lag; and a report that reads its peaks as fast as the flat one.

### D. Reports and the run store for large tables

- `table_run.affected`: the rows with any event, up to a cap, with a count of the others.
- `table_run.rows`: the outputs of the rows that `--rows` names. It can name a whole small table,
  such as a table of regions.
- An output that changes only at moments is recorded at each moment, as the run goes. Its peak is
  exact, and `PEAK_WORK` (`reports.peaks`) never thins it.
- The run store keeps the report of a run of a large table, not its full record: the full record of
  a run at the scale is estimated at about 100 MB.
- A process that keeps a compiled model: an extension of `napkin.Session` that holds the core and
  runs many edit documents.

## What was measured

Measured on 2026-11-17, on one machine with 4 processors, with SciPy 1.18.1 (HiGHS 1.12.0), each
workload once. The network is synthetic: 30,000 random places, 35,000 routes between near places and
15,000 sources. The numbers of the solver and of the trials are those of prototypes, which are no
part of the package. No published test network was used.

| Question | Result |
| --- | --- |
| The engine of today at the scale, with no found value | 65,000 rows compile in 2.3 s; 1,000 steps run in 0.13 s |
| Routes with two ends in one table, today | A model of 200 routes is refused |
| The same, with a stand-in for each link (a trial in a copy of the package) | 30,000 places and 35,000 routes are two families; the compile takes 2.3 s; a run of 6,748 events takes 0.7 s. The events are those of the flat model at 20 and at 100 routes. 224 of 226 tests of the timeline, the hybrid core and the table command pass; the other two fail for a reason of the trial |
| The linear program of the goal, in the bundled HiGHS | 1.1 s to 1.7 s cold; 30 ms to 240 ms from the last basis of one kept solver |
| A quadratic program in the bundled HiGHS | 73 s for 3,000 places |
| One sparse factorization, and one solve with it | 65 ms and 1.4 ms for the normal equations (residual 3e-10); 141 ms and 5 ms for the whole system (residual 7e-14) |
| The nearest step, when no cut is necessary | One factorization |
| The nearest step, when a cut is necessary | 7 to 26 factorizations, 1.2 s to 2.6 s; after one more route fails, 1 to 3 factorizations, 0.16 s to 0.34 s |
| The nearest step after every need changes, in a network that is short at each hour | 3 to 29 factorizations, 0.4 s to 2.7 s; one case took 5.9 s |
| A cascade after 1,000 routes fail, with a solve when the steps of a moment are done | 3,910 trips in 14 solves, 82 s in the prototype (each program cold, and a rule to stop that is too strict) |
| Each run of each model with no table, through the table side of today | 113 runs of 21 models. 106 runs give the same outcomes (the largest difference is 2e-14 of a value) and the same steps in the same order. The table side refuses the 7 runs of one model, in which an output reads an output with a lag. On the largest model a run takes about 5 s on both sides; the report takes 4.4 s, where the flat one takes 0.1 s |

**The speed.** The targets of the first draft were illustrative, and this page sets no minimum. A
week of hourly solves costs seconds for a network that needs no cut on a normal day. It costs
minutes for a network that is short at each hour. The tests assert counts, never times.

## The changes

**Compiler (`napkin/model/`):**

- Lexer and parser: `find` as a kind of field (`language/parse.py:51`); `make` and `goal` read as
  `assert` is read; `near` in `NOT_UNITS` (`language/lex.py`); `by` in the line of a link.
- Identity: `identity` in `language/evidence.py` leaves out the new fields of a file that does not
  write them, so the `model_hash` of each model of today stays the same.
- Linearity in one place: a new `napkin/core/linear.py`, `linear(node, found) -> (constant, {name:
  coefficient})`, which the compiler and the engine both use.
- Builder, checks and proofs: the new parts `found`, `conditions` and `goals`; `discrete_names`
  (`analysis/structure.py:103`) adds the found names; a new `_solve_errors` checks the units, the
  linearity and the limits of the first version; the interval of a found value is its range.
- Hybrid core (`hybrid.py`, `language/resolve.py`): the stand-ins of feature B in `classes`,
  `compile` and `Kept`; reverse lists in `Resolver.links`; no refusal of `lists_in_templates`.

**Engine (`napkin/engine/`):**

- A new `timeline/solve.py`: the islands, the terms of each condition as sparse arrays, the nearest
  step and its check. `continuous/highs.py` gets a solver that keeps its program.
- `timeline/plan.py`: links by name and reads through a link; each value that a coefficient, a
  range or `near` reads gets a reader of the kind `solve`.
- `timeline/run.py`: a solve in `start`, and in `settle` when no rule is due. `apply` takes one
  place for each write today: it gets a write of a whole column, which the record of the past keeps
  as an array.
- One study and one report over the core: `study.py`, `report.py`, `timeline/reports.py`,
  `session.py`, `store.py`.

**Schemas and docs:** `report.schema.json` gets `solves` (the counts by path, the moments with a
linear program, the largest residual) and the two codes. `edits.schema.json` needs no change. Each
page of `docs/` gets its part, and [design.md](../design.md) records the measurements and each
decision with its reason.

## The order of the work

1. **B**, the links between the rows of tables. Each later part needs it.
2. **C**, one path. It can go beside B, and it ends when the comparison of the catalogue shows no
   difference.
3. **A**, in two parts. First the solve as a module of its own, tested with exact fractions. Then
   its place in a moment, once, in the timeline engine: a model with no table is the case of no
   family.
4. **D.**

## The checks

The tests follow [CONTRIBUTING.md](../../CONTRIBUTING.md#testing): independent mathematics,
properties and counterexamples, and synthetic models in `tests/` with generic names.

- **A, exact answers.** Closed forms with `Fraction`: the flows of networks of two places and of a
  triangle, and the projection of the one answer, x = n − W⁻¹Aᵀ(AW⁻¹Aᵀ)⁻¹(An − b). The best value
  of the towns equals the minimum cut, found by enumerating every cut of small random graphs. Small
  linear programs have their optima by exact enumeration of the vertices.
- **A, properties.** The residuals and the ranges hold; the goal is monotone in a capacity; two
  parts that do not connect give the results of two models; the order of the rows does not matter;
  a run equals its repeat, bit for bit.
- **A, counts.** Many steps of one moment make one solve. An island whose inputs no step wrote is
  not solved again.
- **A, refusals by name.** A condition that is not linear, `<=`, a range that reads a stock, `t` in
  a condition, a problem that is infeasible.
- **B.** A model written out and its table form give the same sums and the same events. A network
  of 30,000 rows stays a few classes. A difference of the two ends of a route is no zero in the
  proofs.
- **C.** On small tables, the flat study of the same edits is the definition: each outcome, status
  and time. A transaction is refused when one run fails. For the catalogue, `tools.compare` shows no
  difference, and each committed summary matches a fresh render.
- **Mutations.** Drop a term, flip a sign, skip a solve, merge islands, hold no value at its end,
  and the like for B and C. Each mutation must fail a test.
- **Acceptance, at the scale.** A synthetic model with `find`, `make` with `when` and `goal least`
  on two tables with reverse lists; a cascade of routes that trip on a found value; a flow at a
  found rate into a tally; edits of any rows; and the outputs of the rows of a small table.

## The risks and the open questions

**Risks:**

- The nearest step is new numerical code. In the prototype a problem with many equal answers took
  up to 29 factorizations, and its rule to stop was too strict for values with a wide range.
- A network that is short at each hour is slow at the scale: up to seconds for each solve.
- `highs.py` reads a private interface of SciPy, which a new version of SciPy can change.
- Feature C goes through every public function. The comparison of the two sides read the outcomes
  and the steps of each run, not its health or its evidence.
- A model can make steps without end at one moment. `max_steps` stops such a run.
- The identity of the models of today must not move: `tools.compare` over the whole catalogue shows
  it before the language changes land.

**Open questions:**

- The tolerance of a condition, and the rule to stop the nearest step. A proposal: the residual of a
  condition against the sizes of its terms.
- How `infeasible` names the worst conditions. The bundled interface of HiGHS has tools for it; they
  are not yet tried.
- Whether a `goal` can sit under a thing, or only at the top level.
- The cap of `table_run.affected`.
- Which published test networks the checks use, and on what terms.

## The decisions

Taken by the owner on 2026-11-17:

- The engine solves when the steps of a moment are done, not after each step.
- `make` has `is` only in the first version.
- A run gives the same bits again. The page promises no more of two equal states in one run.
- One path for every model, before feature A.
- The targets of speed were illustrative: the page sets no minimum.

Still for the owner, each recorded in [design.md](../design.md) before its part is built:

- the new words of the language, and the rule of the one answer nearest to `near`;
- the run store keeps the reports of runs of large tables, not their full records.
