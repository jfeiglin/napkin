# Declared solvers in the engine

A declared solver is a `solver` that an entity owns. It sets the rates and values that it names in
`solve_for`. This page tells how the engine forms its problem, how the solve library selects the
answer, and how a solve fails. The [flows and solvers page](../language/flows-and-solvers.md) tells how
a model writes a solver.

The code:

| File | What it does |
| --- | --- |
| `napkin/engine/timeline/declared.py` | Forms the problem of the set at an instant (`Former.problem`), runs the set between moments (`DeclaredWay`, `MovingDeclared`) and publishes the answer. |
| `napkin/engine/solve/problem.py` | The problem: unknowns, affine rows, ranked objectives and claims, in the author's units. |
| `napkin/engine/solve/solver.py` | The selection order on one kept HiGHS instance, and the end checks of the answer. |
| `napkin/engine/solve/scaled.py` | The working units of the problem. |
| `napkin/engine/solve/ranked.py` | The hard constraints and the written objectives, each optimum kept by pinning. |
| `napkin/engine/solve/fair.py` | Fair sharing, tier by tier. |
| `napkin/engine/solve/distance.py` | The two distance steps. |
| `napkin/engine/solve/kept.py` | The HiGHS instance that a run keeps, and the QP of HiGHS. |
| `napkin/engine/solve/failures.py` | The named failures. |

## What a solver decides

A solver decides only what it names ([change 19](../design/decisions.md#change-19)): the rates in its
`solve_for`, the stored numbers in its `solve_for`, and its own unknowns.

- A flow that shares a stock with one of its flows is in the same connected set, so that the books
  of the stock balance. The solver sees that flow only through its bounds and the rows that it meets.
  Its claim keeps its place in local sharing.
- A relation or an objective that reads a flow that the solver does not name stops the run by name.
  To decide who is served, the solver names those rates.
- Two solvers that meet in one connected set stop the run, with both names. One solver must own the
  joint decision.

In this package, a supply of 1 L/h reaches a junction. One outflow serves A, and the other feeds a
second junction that serves B and C. The package's `units.json` declares `L`:

```json
{"L": {"kind": "volume", "dimensions": {"volume": 1}, "scale": 1}}
```

```scn
scenario "Fair sharing"
    horizon 2 h

site:
    water: L = 0 in [0, 0]
    flow feed: SOURCE -> this.water
        capacity = 1 L/h
    flow to_a: this.water -> SINK
        request = 1 L/h
    flow onward: this.water -> other.water
        request = 1 L/h

other:
    water: L = 0 in [0, 0]
    flow to_b: this.water -> SINK
        request = 1 L/h
    flow to_c: this.water -> SINK
        request = 1 L/h

provider:
    share = solver:
        solve_for:
            site.feed.actual_rate
            site.to_a.actual_rate
            site.onward.actual_rate
            other.to_b.actual_rate
            other.to_c.actual_rate
```

| Version of the model | A (L/h) | B (L/h) | C (L/h) |
| --- | --- | --- | --- |
| As written: the solver names all five rates | 0.333333 | 0.333333 | 0.333333 |
| The solver names only `site.feed.actual_rate` | 0.5 | 0.25 | 0.25 |
| No solver: local sharing at each endpoint | 0.5 | 0.25 | 0.25 |

With no objective, the solver's fair sharing acts across all its claims. A solver that names only the
feed leaves the other flows to local sharing.

## The problem

`Former.problem` forms the problem of the set at an instant from the program:

- **Unknowns.** Each flow of the set: a directed flow's rate within 0 and its capacity, a route's
  signed rate within its capacity, or a flow with legs' served fraction within 0 and 1. Each other
  result within its domain.
- **Targets.** A flow's target is its request. A served fraction's target is one when a leg asks, else
  zero. Another result's target is its reference: its initializer, or zero without one.
- **Rows.** Each stock that rests on a bound: what leaves a stock at its lower bound must also arrive,
  and what arrives at a stock at its upper bound must also leave. A stock at both bounds, such as one
  held at `[0, 0]`, is one `==` row. Each endpoint's capacity. Each relation of `constraints`.
- **Objectives**, in written order. A `maximize` is a negated minimum.
- **Claims.** Each positive request of a flow and of an endpoint, in tiers. The endpoints' rules
  rank every claim (`network.claim_order`). The solver's own sharing acts only among the claims that
  they leave equal.

The solver reads its unknowns as symbols (`Affine`). The engine accepts these forms: affine `==`, `<=`
and `>=`, their conjunction, `all(...)`, sums, products and quotients by known numbers, a membership
`x in [lo, hi]`, and positive parts (`max` of an unknown) where they are convex. These forms stop the
run with a diagnostic that names the solver and the form: a strict relation, `!=`, `or`, `any`, `not`
of a relation, a relation under a condition, `min` of an unknown, a product of two unknowns, a division
by an unknown, another function of an unknown, and a request or a capacity of the set that reads an
unknown.

## The ranks

The solve library selects the answer by the selection order of the language (`napkin/engine/solve/solver.py`;
[flows and solvers](../language/flows-and-solvers.md)). Each rank keeps what the ranks before it
attained.

1. **The hard constraints**: the bounds and the rows of the problem. With no objective, one linear
   program with no cost checks that they have an answer.
2. **The written objectives**, in order (`ranked.optimize`). After each objective, the engine pins its
   optimal face (next section).
3. **Fair sharing**, one priority tier after another, tier 0 first (`fair.py`). In a tier, the
   smallest served fraction rises as far as the face allows, then the next smallest, until no claim
   can rise without lowering one that is no higher. A served fraction counts from 0 up to 1.
4. **The final distance** (`distance.select`), in two stages:
   1. the flows nearest their targets;
   2. with the flows fixed, the other unknowns nearest their references.

Ranks 1 to 3 are linear programs on the kept HiGHS instance. The final distance is a convex quadratic
problem. Its criterion is strictly convex in the coordinates of each stage, so the answer is unique.

**Fair sharing in parts.** The claims of a tier often fall into parts that share no row through the
columns that the face leaves free. Each part gets its own level in one linear program. So the number
of programs is that of the part with the most levels, not the sum over the parts.

**The distance method** is a dual semismooth Newton method. It factorizes its Newton system by
`qdldl` (LDL'). When a solve by LDL' is not accurate (backward error above 1e-10), or when LDL' refuses
a factorization, the stage continues by SuperLU. A stage that does not converge so runs again by SuperLU alone. A stage that still does not
converge within its Newton steps goes to the QP of HiGHS, the exact fallback.

## Pinning and tolerances

After objective k, a column whose reduced cost is not zero goes to the bound that it rests on. A row
whose dual is not zero becomes an equality on the side that it rests on (`ranked.pin`). With an optimal
dual, this is the optimal face itself, and it adds no row.

Pinning is exact only with an optimal dual. So `ranked.exact` decides, for each objective and each fair
program, whether an answer is exact enough to pin. It runs the program again at HiGHS's tightest
tolerance (`kept.TIGHT`, 1e-10) in two cases:

- a dual has the wrong sign by more than `TAU`;
- the answer misses a row or a bound by more than `TIGHT`, in the working units of the program
  (`missed_by`).

A held fair claim gets a lower bound `FIX` below its level, never an equality, because HiGHS knows the
level only to its feasibility tolerance.

| Constant | Value | Where | What it decides |
| --- | --- | --- | --- |
| `ranked.TAU` | 1e-9 | `napkin/engine/solve/ranked.py` | A reduced cost or a dual above this is not zero. |
| `ranked.KEPT` | 1e-7 | `napkin/engine/solve/ranked.py` | An optimum is kept to this, relative to the magnitude of its terms. |
| `ranked.NEAR` | 1e-9 | `napkin/engine/solve/ranked.py` | A value this near its bound, relative to the bound, rests on it. |
| `kept.TIGHT` | 1e-10 | `napkin/engine/solve/kept.py` | The tight primal tolerance of HiGHS. |
| `kept.MISS` | 10 | `napkin/engine/solve/kept.py` | A run that misses its program by more than this times the primal tolerance, relative to the magnitude of its terms, runs again on a fresh instance. |
| `fair.TAU` | 1e-9 | `napkin/engine/solve/fair.py` | A claim whose dual is above this is held at its level. |
| `fair.FIX` | 1e-7 | `napkin/engine/solve/fair.py` | A held claim keeps its level to this. |
| `fair.FULL` | 1e-9 | `napkin/engine/solve/fair.py` | A level within this of one serves every pending claim in full. |
| `fair.UPDATES` | 100 | `napkin/engine/solve/fair.py` | HiGHS factorizes its basis again after this many updates. |
| `distance.TOL` | 1e-9 | `napkin/engine/solve/distance.py` | A row is met when its residual is below this times one plus the magnitude of its terms. |
| `distance.FEASIBLE` | 1e-7 | `napkin/engine/solve/distance.py` | A stalled method counts a row as met to this. |
| `distance.ACCURATE` | 1e-10 | `napkin/engine/solve/distance.py` | An LDL' solve with a backward error above this goes to SuperLU. |
| `solver.CHECK` | 1e-6 | `napkin/engine/solve/solver.py` | The end checks of a row, a bound and a fair level, relative to the magnitude of the terms. |

**The kept instance.** One `solve.Solver` serves each declared solver for the whole run
(`Ways.kept`). Its HiGHS instance follows each new problem by the keys of its unknowns and rows: what
left is deleted, what joined is added, a row that changed is replaced. A run of HiGHS whose status says
nothing of the program, or whose answer misses the program, runs again on a fresh instance with the
same basis, then on one with no basis (`Kept.run`).

**The end checks.** Before the solver gives an answer, it checks each kept optimum, each claim's
served fraction against its level, and every bound and row. The engine then polishes the answer onto
the bounds and rows that it holds, and clips it to its bounds (`declared.polished`, `published`). A
polished answer replaces the solver's answer only where it passes the same checks and is no worse on
any rank (`Answer.admits`).

## Scales

The ranks and the distance use the scales differently (`napkin/engine/solve/scaled.py`):

- **The physical ranks do not depend on a declared scale.** The hard constraints, the written
  objectives and fair sharing use physical coordinates. A flow is in its physical rate unit. A nonflow
  unknown is in its physical unit.
- **Rows and objectives are normalized** after the engine chooses these coordinates: each row by its
  largest coefficient, and each objective to a largest coefficient of one.
- **The flow distance** divides each flow by one canonical unit of its dimension. A served fraction
  uses the scale one. So the answer does not depend on the units in which a model writes its rates.
- **The nonflow distance uses the declared scale.** The reference scale of a nonflow unknown is its
  declared `scale`, else its finite width, else one canonical unit. Only the second distance stage
  reads it, as its metric (`distance.select`).

A value declared `level = 0 in [-30, 30]` has the reference zero in every solve. A feasible level can
differ from zero when the route equations require it.

## When a solver solves

- **Once in a round.** The engine forms the problem after the stages of a round commit, and solves each
  affected solver once, in the order of the levels of the sets. The results publish together. A
  problem equal to the one that the solver answered last is not solved again.
- **Between moments.** For Declared, the answer holds until a stock meets a bound or leaves one. For
  MovingDeclared, the engine solves at each trial state of its integrator. These trial solves are not
  in the trace ([methods.md](methods.md#movingdeclared)).
- **In the trace.** Each solve that publishes is a `solve` entry, at its time and its round.
- **After a failure.** A failed solve publishes nothing. The run stops before a trigger or a report can
  read a partial answer.

## Budgets

The budgets count deterministic work, never seconds ([change 4](../design/decisions.md#change-4)). So
a run that succeeds on one machine succeeds on another. `Configuration.budgets` (`napkin.program.config.Budgets`)
holds them:

| Budget | Default | What it counts | Diagnostic when it runs out |
| --- | --- | --- | --- |
| `fair_programs` | 1,000 | The linear programs of the fair-sharing step of one solve, over all its tiers. | `fair-sharing budget exceeded`, with the levels and the programs that it reached and the claims still pending. |
| `newton_steps` | 500 | The Newton steps of each distance stage, for each of its two runs (LDL', then SuperLU). | None: the stage goes to the QP of HiGHS. |
| `qp_iterations` | 100,000 | The iterations of the QP of HiGHS in the fallback of a distance stage. | `distance budget exceeded`, with the Newton steps, the residual and the iterations. |

The engine never gives another allocation when a budget runs out: a change in who is served would
change the model. With `Budgets(fair_programs=1)`, the fair sharing package above stops at 0 h with
this message:

```text
the solver provider.share cannot answer at t = 0 h: fair-sharing budget exceeded in fair sharing, tier 0: 1 levels in 1 programs, 1 claims pending (budget: 1 programs)
```

The message names the solver, the time, the failure, the step and what the step reached.

## Failure names

A solve gives the answer of the selection order, or raises a `SolveFailure` with one of these names
(`napkin/engine/solve/failures.py`). The engine stops the run with the message
`the solver <id> cannot answer at t = <T> h: <name> in <step>: <detail>`.

| Name | Cause |
| --- | --- |
| `infeasible` | The hard constraints have no answer: the bounds, the rows or both contradict one another. |
| `unbounded` | A written objective has no finite optimum over the answers that keep the earlier optima. |
| `fair-sharing budget exceeded` | Fair sharing used its budget of linear programs, with claims pending. |
| `distance budget exceeded` | The distance method did not converge within its Newton steps, and the QP of HiGHS did not finish within its iterations. |
| `numerical` | A contradiction that the problem does not hold: a later rank found no answer on a face that an earlier rank found feasible, the answer lost a kept optimum, or HiGHS gave a status that is no answer. |

The step names are `the hard constraints`, `objective k`, `fair sharing, tier k`,
`distance of the flows` and `distance of the others`.

Other stops of a solver set are not `SolveFailure` names: an unsupported form, two solvers in one set,
a relation that reads a flow that the solver does not name, and a MovingDeclared set of more than 20
stocks. Each stops the run with a message that names the solver.

## Reproducibility

The same run, with the same code, configuration, seed and thread settings on one machine, gives the
same answers bit for bit. One `Solver` for each declared solver of a run, and no state outside it,
make sure of this. Anything else agrees within the tolerances of the steps
([change 11](../design/decisions.md#change-11)): a sample alone or in a batch, a problem formed fresh
against a kept one, another platform. A threshold at a tolerance boundary can decide differently there: a dual
against `TAU`, a level against `FULL`, a miss against `MISS`, a residual against the stall rule. Then
the work differs and the answers agree within the tolerances. A solve near a budget can pass in one
setting and stop by name in another.

## Speed

[The solver speed plan](../scoping/solver-speed.md) holds the measurements of the solve library, the
three speedups that change no answer (one `==` row for a stock at both bounds, LDL' by `qdldl`, fair
sharing in parts), and the work that is deferred.
