# The rulings of the owner

This page states each ruling of the owner of napkin as it applies today. Code comments cite a
ruling by its number, for example `docs/design/decisions.md, change 15` or `D5`. The numbers stay
as the owner gave them. A ruling that a later change replaced keeps its number and its entry, and
the entry says what replaced it.

| Numbers | Source | Date |
| --- | --- | --- |
| D0 to D17 | The rulings of gate G0 (`scratch/rewrite/g0-decisions.md` at commit `ARCHIVE_SHA`) | 2026-11-18 |
| Changes 1 to 29 | "Changes after G0" in `scratch/rewrite/PLAN.md` at commit `ARCHIVE_SHA` | 2026-11-18 to 2026-11-21 |
| Changes 30 to 33 | The decisions of the last round of the owner | after 2026-11-21 |

An identifier such as `R-A5-05` names a ruling of a prototype. These rulings are in
`scratch/rewrite/rulings.md` and in the `FINDINGS.md` file of each prototype, at commit
`ARCHIVE_SHA` ([the archive](README.md#archive)). The words in **bold** type have the meanings
that [the terms](../language/README.md#terms) give. [docs/language/changes.md](../language/changes.md)
gives what replaced each word of the old language.

## The rulings of gate G0

### D0

**The selection order of a solver, and its cost.**

A declared **solver** selects its answer in one order, at every model size:

1. It applies the domains, the **capacities**, the balance of each **stock** and each declared
   hard constraint.
2. It optimizes the written objectives in their written order. It keeps each optimum that it
   reaches.
3. It applies the inherited service preferences and the preferences of the endpoints: fair sharing in
   each priority tier.
4. It selects the flow rates nearest their **requests**.
5. It selects the other unknowns nearest their declared references.

The fair-sharing step and the final distance step have budgets. If a step cannot give an answer
within its budget and its tolerances, the **run** stops with a diagnostic that names the step. The
engine never gives a different allocation in place of the answer, because a change of who is served
would change the model.

The measurements behind this ruling are in [measurements.md](measurements.md#the-solver). They show
specific capabilities and costs. They do not show that each network of 30,000 places finishes in a
given time.

**Later changes.** [Change 4](#change-4) counts each budget in deterministic work, not in seconds.
[Change 10](#change-10) makes "never a different allocation" a rule of defensibility.
[Change 18](#change-18) adds three speedups that change no answer. [Change 19](#change-19) limits a
solver to the rates that it names in `solve_for`.

### D1

**Chance is an ordinary value. The actor choice is removed.**

- A model branches on an ordinary value. For a random outcome, write
  `switch categorical(FIXED: 0.7, FAILED: 0.3).draw():`. There is no separate `chance(...)`.
- In the mode `sampled`, each draw that the run executes samples. In the mode `median`, a numeric
  distribution gives its median. A categorical distribution gives its most likely eligible outcome,
  and the first declared of them on a tie.
- The default run of a model is a `median` run.
- A read of a distribution uses no draw. A branch that the run does not take uses no draw.
- Eligibility and probability are independent. Eligibility is an ordinary guard.

At G0, this ruling also made an actor choice a second source of a value for a branch, and gave
`sees` to human playback.

**Later changes.** [Change 15](#change-15) removed the actor half of this ruling: the actor choice,
`sees` and the controllers. A caller who wants a different value stops the run at a **breakpoint**
and changes the value with an **edit**. [Change 1](#change-1) replaced the prototype translations
that used a separate `chance(...)`.

### D2

**An override of an input follows the declared type.**

- An override of an **input** has the type of the input, and it is in the admitted range of the
  input. A duration input takes a duration.
- A number that overrides an input skips the default draw of the input. For example,
  `input repair_time: h = uniform(1 h, 3 h).draw() in [1 h, 12 h]` admits an override of 5 h, and
  keeps its default distribution for a run with no override.
- To make the distribution itself configurable, declare a distribution-valued input. Override it
  with a compatible distribution, and call `.draw()` where the model needs the number.

**Later changes.** [Change 8](#change-8) states this ruling again for the build.

### D3

**Moving rates are valid at any model size.**

A rate formula can read a quantity that changes between **moments**. The language has no size
limit for this. A large model can take longer, or stop with an explicit failure of time, memory or
accuracy. Its size never changes its equations, and never freezes a moving rate. The limit of about
150 stocks in a prototype was a measurement of one implementation, not a rule of the language.

**Later changes.** [Change 3](#change-3) gives such a set the Sparse **method**.

### D4

**The language has no `none`.**

- There is no `none` value. The parser refuses `none` by name. If a model cannot estimate a value,
  leave the declaration out, and give the reason in the documentation or the evidence.
- An empty reduction has its ordinary meaning: `sum` is zero in its unit, `count` is zero, `any` is
  false and `all` is true. A read of `min` or `max` of an empty collection fails.
- A report can show that a **reading** is unavailable, with its reason. That reason is not a value
  of the model.

**Later changes.** [Change 1](#change-1) replaced the prototype translations that used `none`.

### D5

**Stages commit in a fixed order.**

- At one time, the **stages** that are due in one round commit one after the other. The stage of the
  **occurrence** that started first goes first. Occurrences that started together go in the order
  of their `.start` statements.
- A later stage sees the direct writes of an earlier stage. A value starts at 20 g. A stage sets it
  to 8 g, and a later stage adds 4 g. The result is 12 g.
- After the stages of a round, the engine shares the flows again. It solves each affected solver
  once, in dependency order, and publishes the results of each solve together. Then it reads the
  **triggers**. New consequences can make a further round at the same time.

At G0, this ruling also made a read of a solver result an error when its inputs changed before the
solver settled again.

**Later changes.** [Change 25](#change-25) extended that error to the rate of every flow.
[Change 26](#change-26) extended it to the changes that a moment makes by itself.
[Change 27](#change-27) replaced the error of D5, of change 25 and of change 26. Each reader now
gets the rates and the results of the last new share.

### D6

**The limits of a runaway run are configurable.**

| Limit | Default | What it counts |
| --- | --- | --- |
| `max_occurrences` | 1,000,000 | The starts of one event in a run |
| `max_active` | 100,000 | The occurrences of one event that are active at one time |
| `max_rounds` | 1,000 | The rounds at one time |

A **configuration** can change each limit (`Limits`, `napkin/program/config.py`). When a run reaches
a limit, it stops with a diagnostic. The diagnostic names the limit and the event. For
`max_active`, it also names the oldest occurrence and the step at which that occurrence waits. For
`max_rounds`, it names the events that started at that time.

### D7

**A finished occurrence does not change.**

- A finished occurrence keeps its identity, its parameters, its locals and the final results of its
  formulas. A formula that read 14 at the finish reads 14 later.
- If a formula cannot give a value at the finish, the occurrence keeps the reason and finishes
  normally. A report shows the reason as `Unavailable`. A read of that frozen value in the model
  fails with the kept reason.
- A later event cannot change what a finished occurrence holds.

**Later changes.** [Change 24](#change-24) (b) makes an actual write to a finished occurrence an
error. [Change 29](#change-29) adds a conservation allowance for the computed transfers at a stock
of a finished occurrence.

### D8

**A range can have one side, and `scale` replaces `size`.**

- Either bound of a range can be empty: `in [0,]` has no upper bound, and `in [, 10 L]` has no
  lower bound. A finite end is in the range.
- A quantity with no range has no bound. A stock that must not go below zero writes its lower bound.
- The numerical hint `size` has the new name `scale`. A **scale** helps the numerical calculation. It
  is not a physical bound.

**Later changes.** [Change 29](#change-29) makes the scale of a quantity the floor of its
**comparison band**. [Change 33](#change-33) states the only things that a scale can change.

### D9

**The caller owns comparisons and publication.**

- One start of the engine gives one record, from one configuration, one mode and, in the mode
  `sampled`, one seed.
- **Named runs** can stay in the model (`runs:`).
- To compare two runs, the wrapper of a **package** starts the engine two times and compares the two
  records. The language has no `versus`.
- The repository requires no publisher, no comparison manifest, no featured pair and no shared
  convention for reports.
- To give two policies the same weather, the wrapper gives the same draws of the weather to both
  runs. Equal seeds alone do not keep later draws aligned after the two runs take different
  branches.

At G0, a run also had one set of controller choices.

**Later changes.** [Change 5](#change-5) and [change 13](#change-13) decide the place of the
publisher. [Change 11](#change-11) states what "the same run" means. [Change 15](#change-15)
removed the controller choices. [Change 28](#change-28) gives the rule of reuse of the run store.

### D10

**A caller can report any named value.**

- The caller selects the paths and the times. The language has no `output`, no output flags, no
  `cumulative` markers and no `report:` block.
- A live total is an ordinary formula, for example
  `unserved_volume = formula(sum(Utility.instances.unserved))`.
- Labels, descriptions, evidence and the texts of status cases stay with the model. A status display
  has a text for each case, because two cases can share one rating and need different texts.
- A reporting lag is a transformation that the caller selects. It is valid only for a value that a
  proof says never falls.
- The measurement clauses `distinct`, `unestimated`, `level` and `signed` are removed. Evidence,
  documentation, ranges and the proofs of the compiler do their work.

**Later changes.** [Change 7](#change-7) states this ruling again for the build.
[Change 12](#change-12) removed `delayed`: a delayed observation is an event that waits and then
writes. [Change 19](#change-19) adds a `title` for a member. [Change 22](#change-22) makes a lag
window before 0 h unavailable.

### D11

**A stage can have `if` and `else`.**

A stage can do several actions, and it can do one of them only under a condition. `after D when C:`
still puts a guard on the whole stage. An ordinary Boolean branch does not need a `switch` of two
cases.

**Later changes.** [Change 19](#change-19) lets a case of a `switch` be empty.

### D12

**Units use ordinary multiplication and division.**

- `48 h/2` and `48 h / 2` both equal `24 h`. There is no unit `h/2`.
- Write a compound unit with `*` and `/`. For example, `(3 person) * (2 year)` gives
  `6 person * year`.
- The compiler derives the dimension of each product and quotient, and checks it.
- An old product with a hyphen (`person-years`) becomes `person * year`.

### D13

**Pass a quantity for an amount, and an entity for access to its values.**

- An event parameter `amount: L` receives a number. If the caller passes the 8 L of a tank, a
  withdrawal from the parameter does not debit the tank.
- An event that must withdraw from one tank takes a typed tank **entity** as its parameter, and uses
  its `.water`.
- There is no `stock` type and no `ref` keyword. A value becomes a stock by its use.

**Later changes.** [Change 14](#change-14) applies "by use" to tallies and to the ends of a
**route**. [Change 31](#change-31) states which values are stocks.

### D14

**The initializers of an event run in written order.**

- The plain initializers of the locals of an event, and of the flow that an occurrence declares,
  run in written order. A plain `request = left / (2 h)` needs `left` above it.
- A `formula(left / (2 h))` can refer to a later declaration, because the engine calculates it when
  it reads it.
- The setup of the model keeps its dependency order: a value is initialized after the values that
  it reads, whatever the order of the file.

### D15

**A request is soft, and a capacity is hard.**

- A request is a service preference. An objective of a higher rank can make an allocation above the
  request useful, within each hard constraint.
- If a consumer cannot physically accept more than it asks for, set its capacity to its request
  too. When the request changes, use a live formula for the capacity. A plain assignment keeps only
  the number at the start.
- Each example keeps the requested rate, the permitted rate (the capacity) and the **actual rate**
  apart.

### D16

**Retire the old machinery, and keep the useful proofs.**

- The old second pass over the rules and the pickles of whole runs are removed. The **record**
  holds the histories and the traces.
- A model writes the old numeric checks of `Partition` as ordinary assertions.
- The old comparison tool keeps only the checks of names, values and traces that a migration needs
  (`tools/compare.py`).
- The compiler keeps a conservative account of what can happen under a configuration, including
  conclusions from the finite transitions of events and enum states. "This event cannot fire with
  the plant closed" and "this event could fire, and did not fire in this run" answer different
  questions. A trace gives only the second.
- The proof information is for callers and evidence displays. To prune work by a proof is a
  separate optimization, with a value that a measurement can show.

**Later changes.** [Change 6](#change-6) keeps the analysis of what can start
(`napkin/program/reach.py`).

### D17

**The correction of the water example.**

`unserved_rate` can fall to zero when service returns. `unserved_volume` accumulates the unmet rate,
and keeps the loss that occurred. If service returns at hour 5, the volume at hour 6 still includes
the water that the run did not deliver through hour 5. This corrects one example. Another model can
define an instantaneous shortfall when that is its meaning.

## Flows, solvers and events at G0

The decision record of G0 also gives these rules without numbers. Later changes cite them.

- **A rule goes on the value that has the information for it.** A flow sees its source and its sink
  and gives its `actual_rate`. The source gains `outflow`, and the sink gains `inflow`. The capacity
  of a pipe is on the pipe. The shared outlet limit of a tank is on the `outflow` of the tank.
  `SOURCE` supplies a resource from outside the model, and `SINK` absorbs it.
- **Each endpoint shares locally by default.** 1 L/h reaches a junction. Two pipes each request 1 L/h.
  One serves A, and the other feeds a second junction with equal requests from B and C. A gets
  1/2 L/h, B gets 1/4 L/h and C gets 1/4 L/h. Equal service to all three needs a solver of the
  provider ([change 2](#change-2), [change 19](#change-19)).
- **One owner makes a coordinated decision.** A `solver` has `inputs`, `solve_for`, `constraints`
  and an optional `objective`. When two solvers would compete for one hard limit, one solver owns
  the joint decision.
- **The example with two bottlenecks.** Three consumers each request 6 W, with `a + b <= 4 W` and
  `b + c <= 5 W`. Fair sharing at equal priority gives `(2, 2, 3) W`. With `minimize(sum(unmet))`
  first, the answer is `(4, 0, 5) W`. A later fairness preference cannot undo an earlier objective.
- **Three forms of flow.** A directed flow has one actual rate. A route has one signed actual rate
  and two **legs**, which `priority(...)` names. A flow with several legs serves all legs at one
  `served_fraction`. Legs that request 4 L/h and 8 Wh/h at half service deliver 2 L/h and 4 Wh/h. A
  junction held at `[0, 0]` balances its inflow and its outflow at each instant. Both ends of a route
  must supply and receive, so `SOURCE` and `SINK` cannot be the end of a route. G0 also refused a
  tally there; [change 14](#change-14) removed that rule.
- **The ends of a flow show the present, and occurrences keep the history.** A flow of an occurrence
  joins the collections of its ends at the start, and leaves them at the finish. After the finish,
  it keeps its ends and its last request and capacity, and its actual rate reads zero.
- **One collection type for all members.** Instances, rows of a table, flows and occurrences share
  `where`, `by(field)`, projections and `.at(x)`.
- **A stage can write to a live occurrence.** `readonly` forbids a direct assignment, `+=` and `-=`
  included. A flow or a `move` can still transfer material into or out of a `readonly` stock.
- **A trigger fires when its condition first becomes true.** A tank starts at 11 L and drains at
  1 L/h. It reaches `water <= 10 L` at hour 1. If the engine cannot certify the first crossing, it
  stops the run by name. [Change 20](#change-20) extends this rule to a value that turns.
- **A human prompt pauses one atomic stage.** [Change 15](#change-15) removed this rule with the
  player machinery.

## Changes after G0

### Change 1

**The spec is the proposal of G0.** The prototypes and the reference interpreter used spellings that
G0 replaced: a separate `chance(...)`, `none`, a report block, `size` and `^` in units. The build made
their translations again in the language of G0 ([D1](#d1), [D4](#d4), [D8](#d8), [D10](#d10),
[D12](#d12)).

### Change 2

**Each endpoint shares locally.** Each endpoint shares among its own flows by its own allocation.
Fair sharing across several endpoints happens only inside a declared solver. The solve library
(`napkin/engine/solve/`) serves only the declared solvers. Local sharing also holds where junctions
at `[0, 0]` or full or empty stocks make several rates depend on one another
(`napkin/engine/timeline/network.py`). [docs/language/flows-and-solvers.md](../language/flows-and-solvers.md)
gives the rules of local allocation.

### Change 3

**Moving rates at any size ([D3](#d3)).** A large connected set whose rates read moving values runs
on the Sparse method (`napkin/engine/timeline/sparse.py`). A prototype moved 60,000 stocks to 48 h in
32 s while no stock rested at a bound. To hold the rates between moments is an optimization for a
set in which nothing moves (the Lines and Family methods). The engine refuses nothing for its size.

### Change 4

**A budget counts work, not seconds ([D0](#d0)).** A budget counts deterministic work, so a run that
succeeds on one machine succeeds on another.

| Budget | Default | What it counts |
| --- | --- | --- |
| `fair_programs` | 1,000 | The linear programs of one fair-sharing step, over all its tiers |
| `newton_steps` | 500 | The Newton steps of each distance stage |
| `qp_iterations` | 100,000 | The iterations of the exact QP fallback of a distance stage |

The defaults are in `Budgets`, `napkin/program/config.py`.

### Change 5

**The repository requires no publisher ([D9](#d9)).** [Change 13](#change-13) gives the place of
`tools/publish`.

### Change 6

**The analysis of what can start is kept ([D16](#d16)).** `napkin/program/reach.py` gives which
events can start, and which values each named state can take, under a configuration. Each
conclusion has its reason. It is proof information, and nothing prunes a run by it. The analysis
came from `napkin/model/lower/starts.py` at commit `81b367b`.

### Change 7

**Reports ([D10](#d10)).** A model has no `output` and no report block. The caller selects the paths
and the times. A lag needs the proof that the value never falls.

### Change 8

**Inputs ([D2](#d2)).** An override follows the declared type. A distribution-valued input exists.

### Change 9

**Worktrees.** This rule was for the work of the rewrite: each track of stage B1 worked in the main
checkout, in its own new folders. It has no effect on the code.

### Change 10

**The priorities: defensibility, then speed, then precision.** The owner, 2026-11-19. A choice
between algorithms, tolerances and budgets follows this order.

- **Defensibility.** Each number comes from a stated rule and its evidence. The same run gives the
  same result again. A run that cannot answer stops with a named failure, and never gives a
  different answer without a word. The rule "never a different allocation" of [D0](#d0) is a rule
  of defensibility.
- **Speed.** People explore a model, run it again, sample it and change its assumptions. A run of
  20 minutes is not used.
- **Precision.** Inputs are uncertain by tens of percent, so 1e-7 against 1e-10 means nothing. The
  tolerances of the solve library and of the integration can be looser. These stay exact:
  - conservation: the books of each stock balance;
  - equal treatment: two equal claims get equal shares;
  - bounds and proofs: a stock stays in its range, and a value that a proof says never falls does
    not fall;
  - discrete outcomes: where a small difference changes a trigger, a branch or who is served, the
    engine does not calculate more precisely. It finds the near-tie and reports it, for example
    "this trigger fired within tolerance of its threshold".

### Change 11

**Reproducibility.** The owner, 2026-11-19. This states what "one run" of [D9](#d9) gives again.

- The same run is deterministic: the same code, configuration, seed and thread settings on one
  machine give the same record.
- Each other case agrees within the stated tolerances, not bit for bit: a sample alone or in a
  batch, another solver, another platform.
- A threshold at the edge of a tolerance can fire differently across those cases.
- A test of the same run tests identity. A test across those cases compares within the
  tolerances.
- The run store does not put the thread settings in the key of a run (`napkin/store.py`).

This replaced the bitwise requirements of prototype A3, of the solve library and of `R-A4b-05`. An
exact sum at an endpoint stays as a way to be deterministic.

### Change 12

**The language has no `delayed`.** The owner, 2026-11-19. `delayed(x, D)` is removed. The parser
refuses it by name. A delayed observation is an event that waits (`after D:`) and then writes.
`elapsed` and the reporting lag of the caller ([D10](#d10)) stay.

### Change 13

**The publisher is an optional tool.** The owner, 2026-11-19. `tools/publish` stays in the
repository as an optional tool. The migration of the catalogue (stage M) ported it to the new
record, and made its committed outputs again. No drift check is required ([D9](#d9), [change 5](#change-5)).

### Change 14

**A tally is known by its use.** The owner, 2026-11-19. A tally is a stock that nothing drains. It
has no mark. A stock at the end of a route is a stock by its use. Thus, only `SOURCE` and `SINK` are
refused at the end of a route. This revises the G0 rule that also refused a tally there
([G0](#flows-solvers-and-events-at-g0)). See also [D13](#d13) and [change 31](#change-31).

### Change 15

**Breakpoints, checkpoints and edits replace the player machinery.** The owner, 2026-11-19.

- The compiler gives a versioned program that a fresh process loads and runs without the parser
  (`napkin/program/artifact.py`). Its side table maps each location where a run can stop to its
  event, stage, statement and place in the source. It maps each value to its name, its label and
  its evidence.
- A caller sets a breakpoint at a location of the program: an event, an occurrence, a stage or a
  statement. The engine stops there and gives a **checkpoint**: why and where it stopped, which
  entity and occurrence, and what runs next. A fresh process can load the checkpoint, show it,
  apply edits and resume (`napkin/program/checkpoint.py`, `napkin/engine/timeline/checkpoints.py`).
- The edit is the action. There is no answer channel. `choose(...)`, `sees`, the controllers of
  actors and picks are removed from the language, the program, the engine and the reference. This
  revises the actor half of [D1](#d1) and the controller choices of a run in [D9](#d9). It also
  revises the G0 rule "A human prompt pauses one atomic stage" and `R-A5-14`. Eligibility is an
  ordinary guard. `readonly` applies only to the assignments of the model.
- **Exact resume is a rule.** The conditions are one supported platform and the same compiled
  program, engine version, numerical settings and seed. Under these conditions, a run that stops and
  resumes with no edit matches a run with no stop. Both give the same recorded values, draws, event
  times and event order. A breakpoint alone never changes which branch fires. The tests check three
  cases: no breakpoint, a stop resumed in one process, and a stop saved and resumed in a fresh
  process.
- **Edits.** An edit changes a live stored value. Types and bounds hold, and the engine calculates
  the derived rates again. A finished occurrence stays frozen. The record holds an edit of a stock
  as an external transfer. An edit that breaks a proof that a value never falls withdraws that
  proof for the edited run. The trace holds each edit: its time, its breakpoint, its target, and the
  old and the new value. Two stops in one stage do not lose the first edit and do not apply it two
  times.
- **Acceptance.** The pump dispatch case runs with no stop. It also stops before its branch. A
  fresh process loads the saved checkpoint and resumes with no edit, with the same values, draws and
  events. It also resumes with `order` changed from `WAIT` to `SEND`. The send branch then runs one
  time, the first draw stays in the history, and the edit explains the difference.
- `napkin play` and `napkin.Session` (`napkin/session.py`) are clients of these checkpoints.
  [docs/language/events.md](../language/events.md) gives breakpoints, checkpoints and edits as a
  model author uses them.

### Change 16

**Evidence.** The owner, 2026-11-19. The compiler warns about each part without evidence, of the
kinds for which the compiler before the rewrite refused a model (`napkin/model/support.py`). A model
under exploration still runs. `tools.check` and the publisher refuse a package with such a warning.
A number, a Boolean or a distribution that an option or a `change` sets needs evidence. Its absence
is an error (`R-A5-05`). [docs/language/evidence.md](../language/evidence.md) gives the rule as a model
author sees it.

### Change 17

**The session of the rewrite stopped at gate G2.** The owner, 2026-11-19. The migration of the
catalogue (stage M) came after G2, in a later session. This rule has no effect on the code. The
compiler before the rewrite is at commit `8488047`.

### Change 18

**Speedups that change no answer.** The owner, 2026-11-19. Three speedups of the selection order of
[D0](#d0) give the same answers up to roundoff:

1. A stock held at `[0, 0]` is one equality row.
2. The exact distance step uses the LDL' factorization of `qdldl`.
3. Fair sharing solves independent parts together.

What trades precision or robustness for speed is deferred, with its plan, to
[docs/scoping/solver-speed.md](../scoping/solver-speed.md):

- a looser tolerance of fair sharing
- a path by an interior-point algorithm
- the precision profiles `default` and `fast`.

### Change 19

**The audit after G2.** The owner, 2026-11-19.

- **The scope of a solver.** A solver decides only the rates that it names in `solve_for`. A flow
  that it does not name keeps the local sharing of its endpoints. The solver sees that flow only through
  the limits of the flow, so that the books still balance. To decide who is served, the provider
  names those rates. In the two junctions of G0, a solver that names only the upstream feed leaves
  1/2, 1/4 and 1/4. This reverses the rule of stage S5 that put such a flow in the calculation of
  the solver. It also limits the selection order of [D0](#d0) to the rates that the solver names.
- **An empty case.** A case of a `switch` can be empty, with or without a text ([D11](#d11)).
- **Titles.** An entity, a **template** and an **instance** that the model writes out can have a
  `title`. The title is a label outside the identity of the program: no hash covers it. Reports and
  playback show it, beside the labels that [D10](#d10) keeps with the model.
- **Roles.** The model refuses the `role` of an event by name, and says where it goes: the wrapper of
  the package. [Change 23](#change-23) extends this to every part.
- **Timescales.** `timescales` is removed. The parser refuses it by name. The engine selects its own
  steps, and a run that needs finer steps sets `max_step` in its configuration.
- **Cycles.** The compiler checks cycles on the actual links of the instances. The links are fixed
  when the model compiles (`R-A1-30`). The compiler reports a real cycle as its chain.
- **Bugs.** Each bug that the audit found has its failing example as a test. The migration checker
  (`scratch/rewrite/a5/check.py` at commit `ARCHIVE_SHA`) runs the old and the new model to the
  horizon. It fails on a difference that the `changed.md` file of the package does not list.

### Change 20

**A trigger on a value that turns.** The owner, 2026-11-19. This extends the G0 rule that a trigger
fires when its condition first becomes true ([G0](#flows-solvers-and-events-at-g0)). The engine
certifies a continuous condition step by step when its value can rise and fall between moments. An example is the
`water >= level` of a reservoir that a storm fills and that a spill drains. In each integration step:

1. Far from the boundary, one comparison of the distance with the largest possible movement in the
   step clears the step.
2. Near the boundary, a step in which the rate of the value keeps one sign is certain from its ends.
   The engine finds a crossing by bracketed root search on the dense output of the integrator.
3. Where the value can turn near the boundary, the engine divides the step into halves. It reads the
   same output, with no new integration and no new rates. It continues until each part is certain or
   shorter than the time tolerance.

A value that comes within tolerance of the boundary and does not cross it is a near-tie
([change 10](#change-10)). A condition that the engine still cannot certify stops the run by name.
The engine never polls at fixed times.

### Change 21

**Fix causes, not cases.** The owner, 2026-11-19. A second audit of commit `0f78c65` found that 7 of
the 12 cases that passed had a close variant that failed. Each fix goes to the module that owns its
cause. Each fix has a test of its rule: a property test or a metamorphic test that does not depend
on the reference. [docs/engine/owners.md](../engine/owners.md) names the owner of each decision.

### Change 22

**A lag before the run.** The owner, 2026-11-19. A reporting lag shows a value as a report gives it
some hours later. A lag window that starts before 0 h has no history to read. The report gives
`Unavailable` there, with the reason, and fills in nothing (`napkin/engine/report.py`). Before this
change, the report gave the value at 0 h, and the engine before the rewrite gave 0 ([D10](#d10)).

### Change 23

**No part of a model has a role.** The owner, 2026-11-19. An entity, a template and an event have no
`role`. The model refuses `role` by name, and says where it goes. The wrapper says who plays a part,
in `roles.toml`, which the publisher and the interface read. For the pictures, `style.toml` has a
`[role]` table beside its `[icon]`, for example `operator = ["pump", "Utility"]`. `napkin draw` takes
from it the icon of each card that `[icon]` does not name. It also takes from it the words "who
acts" and the group of the card ([change 19](#change-19)).

### Change 24

**Three answers during the readiness fixes.** The owner, 2026-11-20.

- (a) [Change 28](#change-28) replaces the rule for a shorter request from a stored record.
- (b) **A finished occurrence is frozen.** The error is an actual write to it. An actual write is an
  assignment to its value, or a `move` of an amount that is not zero. It can also be a flow that
  carries a rate that is not zero into or out of its stock. A connected flow at a zero rate writes
  nothing, and the run continues ([D7](#d7)). [Change 29](#change-29) adds the allowance for
  computed transfers.
- (c) `napkin new` writes two files: `model.scn` and `style.toml`. The `[role]` of `style.toml`
  gives the picture of the starter its icon.

### Change 25

**A stale rate is an error, for every flow.** The owner, 2026-11-20. [Change 27](#change-27) replaced
this rule. Change 25 made a stage stop the run by name in one case. In that case, an earlier stage
of the same round changed what the rate of a flow depends on. The stage then read that rate before
the engine shared the flows again. It extended the read error of [D5](#d5) from the results of a
solver to local sharing.

### Change 26

**What a moment changes by itself.** The main session of the rewrite, 2026-11-20, from the answer of
the owner to change 25. [Change 27](#change-27) replaced this rule. Change 26 extended change 25, and
so the read error of [D5](#d5), to each change that no stage made and that the next share takes:

- a stock at its bound
- a keyed read by the time at its key time
- a branch on the time or on a stored value whose condition changes at the time of the moment.

### Change 27

**Rates and results read as the round began.** The owner, 2026-11-20. This replaces the read errors
of [change 25](#change-25), [change 26](#change-26) and [D5](#d5).

- Each reader gets the rates and the solver results of the last new share, also through a formula.
- Only the first round at a new time reads the incoming rate at that time.
- Writes, moves, allocations, edits, starts, finishes, bounds, switches and keyed steps reach the
  rates at the new share after the stages. A flow that joined reads zero until then. A flow that
  left keeps its share until then.
- Ordinary writes stay sequential, as D5 says.
- A firing reads the new share before it. A stage after `after 0 h:` reads the new share of the
  round before it, at the same time.
- Example: in the clinic and garden case, the stage gets 4 L/h, and the next round gets 2.4 L/h.
  The record gives 2.4 L/h from 2 h.
- The setup has no rate or result to give, and a read of one stops the setup by name.
- A delay that needs a result uses the new share. A delay that a condition reaches waits for the
  next new share.

**The amendment of the owner, 2026-11-21.** A contact of a stock joins a nearby moment only when
both distances qualify:

1. Its located time is within the crossing tolerance (in hours) of the moment.
2. At the time of the moment, the stock is within its own comparison band of the threshold or the
   bound.

Otherwise the engine processes the contact as its own moment, at its located time. An earlier
contact runs before the scheduled stages. A later contact stays pending across those stages if
their writes keep it. A run that ends before that contact ends at its horizon. An empty event, a
selection of what to record, or a checkpoint and resume must give the same decision. For a stock
that a comparison reads against another moving operand, each directly watched stock and the whole
expression must qualify. A reported rate can supply a threshold, but a read of it gives the
comparison no claim on the stock under it. A stage with its own schedule still reads its authored
guard at that time. A firing with the default reset needs a false condition before it can fire again.

Example: a request of 1 L/h and a cap of `(2 − t/h) L/h` bring the stock to 1 L at 1 h. Its
threshold of 1.000000005 L is 5 × 10⁻⁹ L away at the scheduled stage, outside its comparison band.
The engine keeps the stage at 1 h and processes the contact later, at its own located time. A
shorter run can end at 1 h. The engine adds no transfer at 1 h.

### Change 28

**The run store reuses an identical request.** The owner, 2026-11-20.

- The run store keeps each horizon, selection of recorded values and budget of pieces under its own
  key.
- The order of the selected keys can differ: the result gives them in the order of the caller.
- An identical request that reached its budget of pieces gives the same stored failure.
- A different request runs again, also a shorter horizon or a smaller selection.
- The program, the inputs and the seed stay in the identity of a run. The numerical settings, the
  processor, the engine and the log of edits also stay in it (`napkin/store.py`).

This replaces (a) of [change 24](#change-24). It applies "one record for one run" of [D9](#d9) to the
run store.

### Change 29

**Comparisons and crossings.** The owner, 2026-11-20, with amendments to 2026-11-21. The engine and
the reference interpreter apply the same rules. [docs/language/numerics.md](../language/numerics.md)
gives them as a model author sees them.

- Two numeric operands compare equal within `max(rtol, atol_factor) × max(scale, |a|, |b|)`. A
  quantity gives its declared scale ([D8](#d8)), or the size of one declared unit. The defaults are
  `rtol = 1e-9` and `atol_factor = 1e-10` (`Numerics`, `napkin/program/config.py`).
- A literal written by the author is exact (the ruling of language 0.2.3). It adds zero to the floor
  of the band, whatever its unit. This also applies to an expression of literals only, and to a
  formula that names one. The relative term of the band still applies.
- A literal threshold uses the scale of the compared quantity on either side. A formula keeps its
  comparison scale apart from its result unit. An explicit result scale wins. A literal offset
  keeps the scale.
- A sum or a difference adds the signed contributions of each quantity through its aliases, and
  takes the largest absolute contribution among independent quantities. A literal factor scales the
  contribution by its value in canonical units.
- Products, quotients, powers and square roots transform the floor in the units of the result. An
  absolute value and a dimensionless function of one argument keep the floor of the input. `min`,
  `max` and `clip` take the largest floor. A conditional takes the scale of its selected side. A
  keyed read takes the scale of its selected member. A frozen formula keeps its floor from its
  finish. Two independently compared quantities use the larger floor.
- An interval is reversed only when its lower end exceeds its upper end by more than their band.
  Two hard bounds that are inverted within the band admit one point: their midpoint.
- Authored evidence stays exact.
- For a crossing of a stock, the clock applies the time tolerance in hours. It also applies the
  comparison band of the stock in its unit. It applies both before it groups the contact
  ([change 27](#change-27)).
- A stage that writes a move of an amount that is not zero writes. The computed transfers at a
  frozen stock accumulate in each direction from its finish, against the conservation allowance of
  that stock ([D7](#d7), [change 24](#change-24)).

**The ruling on physical balances, placement and status, 2026-11-21.** This principle replaces the
separate rulings for residuals at bounds, thresholds and frozen lots.

1. **The books always balance.** Each accepted transfer posts equally at both ends. The balance of a
   stock changes only through posted transfers. A read, a group of events or the location of a
   crossing cannot move material.
2. **Exact placement is a preference.** The test of time and value of change 27 comes first. Then,
   when the flows can put a stock exactly on a bound or a threshold, the engine posts the signed
   correction. The correction goes to the legs that move the stock toward that value, in proportion
   to their rates just before the contact. If no leg moved toward the value, the legs keep the
   amounts that they carried. A connected placement applies as one. A correction can break a hard
   equation, a frozen allowance, a capacity or the limit of another stock. In that case, the engine
   keeps the amounts that the trajectories gave.
3. **The band decides the status.** This holds for comparisons, triggers and sharing. A stock within
   its own comparison band of a bound or a threshold counts as on it. The residual in its books does
   not change this. A stock on a bound leaves it only when the net flow away from it is more than a
   limit. The limit is 10⁻¹² times the sum of its incoming and outgoing traffic. Each method refines
   a decision that is numerically uncertain. When it still cannot decide, it holds and records a
   near-tie. Example: an inlet fixed at 1 L/h and an outlet fixed at 0.999999999999 L/h post 2 L and
   1.999999999998 L over two hours. The stock, empty at the start, holds the difference of
   0.000000000002 L, and stays on its bound while its balance is within its band.
4. **A failure needs a material breach.** The run fails only when it breaks a hard rule by more
   than the band of that rule. A placement can exceed a frozen allowance while the stock stays
   within its band. In that case, the engine skips the placement, keeps the accepted part and
   continues. A stock outside its target band at a nearby scheduled time keeps its located contact.
   The engine checks each affected stock and each shared allowance or cap before it posts a
   connected group of corrections.
5. **Report each tie in a fixed order.** The record keeps each affected stock, leg, direction and
   target.

The engine groups the violations of a frozen allowance at the first moment of failure within the
crossing tolerance. It lists each contributing leg by the name of its stock, outflow before inflow,
then in the order of declaration. The text names the first five and counts the rest. JSON and Python
keep the full ordered list, and the tests compare it with the independent interpreter.

### Change 30

**Entity and flow numbers start at 0.** The owner. The natural key of an instance is its creation
number in its template, from 0. The natural key of a flow is its creation number, from 0
(`Plan.number`, `napkin/engine/timeline/plan.py`). The reference interpreter (`tests/reference/`)
changed to match. The number of an occurrence also counts from 0: `tank.receive#0` is the first
start of `receive` on `tank`.

### Change 31

**An assignment to a stock is exact.** The owner.

- A stock is each value that is an end of a flow or of a `move` anywhere in the program. This
  includes the slots of occurrences that have not started. The engine fixes the set of stocks when
  it plans the program (`_stock_targets`, `napkin/engine/timeline/plan.py`).
- `=`, `+=` and `-=` on a stock calculate on the exact balance of the stock, the same as `move`.
- A value that only assignments change stays an ordinary value. It has no exact balance.
- An assignment that misses a bound of the stock by less than the tolerance of the stock puts the
  stock on the bound. An assignment that misses it by more stops the run
  (`napkin/engine/timeline/moment.py`).

This applies "a stock by its use" of [D13](#d13) and [change 14](#change-14).

### Change 32

**A move moves exactly what it writes.** The owner.

- A `move` debits and credits exactly the amount that it writes. If the result is outside the range
  of either stock, the move fails, and it moves nothing.
- A move whose amount is the source stock itself, directly or through a live formula, moves the full
  balance of that stock.
- The engine no longer sweeps a leftover smaller than the tolerance into a move.

This applies rule 1 of the ruling on physical balances in [change 29](#change-29).

### Change 33

**What a scale can change.** The owner. A declared `scale` can change only these:

- the outcome of a comparison inside the comparison band;
- the accuracy of the integration;
- the choice among answers of a solver that are equally optimal for the unknowns that are not
  flows.

A change of the units of display changes nothing. This limits [D8](#d8) and
[change 29](#change-29).
