# The engine

The engine runs a compiled program under a configuration and gives a record. This page tells how one
run goes from the program to the record. The words that the language defines (model, stock, flow,
moment, stage, record and the others) have the meanings in
[the terms of the language](../language/README.md#terms).

| Page | What it tells |
| --- | --- |
| [methods.md](methods.md) | The six methods that calculate the stocks between moments, the bounds, the contacts and the stock ledger. |
| [solver.md](solver.md) | How a declared solver selects its answer: its ranks, tolerances, scales, budgets and failures. |
| [verification.md](verification.md) | The reference interpreter, the generated corpus, the test tiers and the speed benchmarks. |
| [owners.md](owners.md) | The one owner (file and function) of each decision of the engine, its readers and its tests. |

The code of the engine is in `napkin/engine/`. The timeline is in `timeline/`, the continuous
integration is in `continuous/`, and the solve library of declared solvers is in `solve/`.

## Engine terms

These words are the engine's own. Each has one meaning on the engine pages. The language defines
contact, near-tie, endpoint, leg and member ([terms](../language/README.md#terms)).

| Term | Meaning |
| --- | --- |
| program | The compiled form of a model (`napkin/program`). The engine reads the program and never the model text. |
| plan | What the engine makes of a program under one configuration (`Plan.of`): a name for each value, the connected sets, the events and the triggers. |
| connected set | The stocks and the flows that a flow joins: the stocks at its ends, and the moving stocks that its request or capacity reads. |
| round | One pass at one moment: the stages that are due, then the re-share, then the conditions. |
| re-share | The step of a round that calculates the rates and the solver results again, after the stages commit. |
| segment | The calculation of one connected set from one event of its method to the next. |
| switch | A time at which a rate or a formula changes its branch, because two of its operands change their order. |
| ledger | The exact balance of a stock, in rational numbers, which only posted transfers change. |
| piece | One part of the history of a value in the record. |
| trace | The list of entries in a record: starts, finishes, commits, firings, draws, moves, solves, edits, pauses and the failure. |
| crossing tolerance | `Numerics.crossing`, 1e-8 h by default: the shortest time between two moments that the engine tells apart. |
| integration size | The number that sets the absolute tolerance of a stock in Component: its declared `scale`, or else the largest of 1 in its unit, its start value, its finite bounds and the start values of the stocks that flows connect it to, directly or through other stocks. |

## From a program to a record

The engine does these steps in each run (`napkin/engine/timeline/run.py`):

1. It makes the plan (`Plan.of(program, configuration)`). A part that the engine does not run stops
   the plan with `Outside` and its reason.
2. It evaluates the start values once: each input, draw, link, stored value and captured request or
   capacity, in the order of what each value reads. An input outside its admitted range stops the
   run. Each assertion over inputs is checked once.
3. It finds the scale and the integration size of each stock. Each stock must start within its bounds.
4. It runs round zero at 0 h: the setup commits as one stage. Then each connected set starts, and the
   flows get their first rates.
5. It goes from moment to moment until the horizon. At each moment it runs rounds. Between two
   moments, each connected set runs on its method.
6. It gives the record of the run. A run that a breakpoint stops gives a checkpoint.

```python
import napkin

model = napkin.load_scenario('examples/piano_tuners')
record = napkin.run(model.program, model.configuration)
rows = napkin.read(record, model.program, ['tunings_done'], [0, 4380, 8760])
```

`rows[0].values` is `(0.0, 1461.768743696291, 2923.537487392582)`, in `tunings`. The
[Python API](../python-api.md) tells how to compile, run and read a model. The
[command line](../cli.md) runs the same engine.

## The configuration

A configuration (`napkin.program.config.Configuration`) holds all that one run needs beside its
program. The engine reads nothing else.

| Part | What it holds | Default |
| --- | --- | --- |
| `request` | The horizon in hours (an inclusive cutoff), every value or only the `keys`, and the budget of pieces. | every value, 10,000,000 pieces |
| `inputs` | The value of each input that the run sets. A value follows the declared type. A number overrides a default draw. | none |
| `mode`, `seed` | `median` (each draw is its median, or its most likely outcome), or `sampled` with a whole-number seed. | `median`, no seed |
| `limits` | `max_occurrences` starts of one event, `max_active` occurrences of one event at one time, `max_rounds` rounds at one time. | 1,000,000; 100,000; 1,000 |
| `budgets` | The work of one solve: `fair_programs`, `newton_steps`, `qp_iterations` ([solver.md](solver.md#budgets)). | 1,000; 500; 100,000 |
| `numerics` | `rtol`, `atol_factor`, `max_step` (h), `max_evaluations`, `crossing` (h). | 1e-9; 1e-10; 1 h; 2,000,000; 1e-8 h |

A compiled model gives the configuration of its default run (`model.configuration`).
`model.configure(run, edits)` gives the configuration of a named run under an edit document. A
`resolution` line of the scenario sets `max_step`. The first of these gives an input its value:

1. an edit of the run in the edit document (`runs`);
2. an edit of one of the run's options (`options`);
3. an edit of every run (`set`);
4. an option of the run;
5. the program itself.

The edit document is one transaction. It is checked whole, in every run of the model, before any run
takes its values. It names the revision of the model that it was made for (`model_hash`). The
[Python API](../python-api.md) and the [command line](../cli.md) tell how to give one.

## The plan

The plan (`napkin/engine/timeline/plan.py`) reads the program once for each configuration.

- **Names.** Each value has an engine name, which is its key in the record: `tank.water`,
  `clinic.delivery.actual_rate`. A path is resolved once for each member that reads it.
- **Kinds.** An input is fixed for the run. A stored value starts from its initializer. A formula,
  a reduction, a keyed read, and a request or a capacity written as `formula(...)`, is evaluated at
  each read.
- **Stocks.** A value is a stock when a flow or a `move` touches it anywhere in the program, also in an
  occurrence that did not start yet. The plan finds them from the ends of the flows and the targets of
  the moves (`Plan._declare_ends`, `Plan._stock_targets`).
- **Connected sets.** `Plan.connect` makes the connected sets and gives each one its method
  (next section). A set whose rates read the actual rates or results of another set settles after
  that set: it has a higher level.
- **Events and triggers.** Each trigger of each member is known from the start. An occurrence gets
  its values under its id, such as `tank.receive#0.remaining`.
- **Assertions.** An assertion that reads only inputs is checked once at the start. An assertion over
  state is checked after every round, just after every moment and between moments.

## Connected sets and methods

Each connected set runs on one method between moments. The plan chooses the method from the set
alone, at the start of the run and again at each moment that changes the set.

| Method | The plan uses it for |
| --- | --- |
| Family | One directed flow with no endpoint settings, whose rates read nothing that moves. All such sets run together on arrays. |
| Lines | Any other set whose rates read nothing that moves. |
| Component | A set whose rates move: directed flows only, no endpoint settings, no keyed read that moves, at most 150 stocks, and each stock meets at most one flow on each side. |
| Sparse | Any other set whose rates move. |
| Declared | The set of a declared solver whose problem reads nothing that moves. |
| MovingDeclared | The set of a declared solver whose problem reads a moving stock or the time. It has at most 20 stocks. |

An endpoint setting is a capacity or a request of an `outflow` or an `inflow`, or a stage that sets
one. [methods.md](methods.md) tells how each method calculates its stocks.

## Moments and rounds

A moment is a time at which the engine stops the continuous calculation. At each moment the engine
runs rounds (`napkin/engine/timeline/moment.py`). One round has three steps:

1. **Stages.** The stages that are due when the round begins commit one after the other. The stage of
   the occurrence that started first goes first. Each statement sees the writes before it. A stage
   commits only at its end: a failure discards the whole stage and stops the run.
2. **Re-share.** The engine builds again each connected set that the round touched, and calculates
   its rates. Each affected declared solver solves once, in the order of the levels, and publishes
   its results together.
3. **Conditions.** The engine reads the triggers, the resets and the gates on the new state, and
   checks each assertion over state. Then the firings start their events and the released gates
   continue. What they start belongs to the next round.

Another round follows at the same time while a stage is due there or a condition acted. Round zero is
the setup. More than `max_rounds` rounds at one time stop the run with the name of the limit.

**Rates read as the round began** ([change 27](../design/decisions.md#change-27)). A stage or a
firing reads the rates and the solver results of the last re-share, also through a formula. The
writes of a round reach the rates only at the re-share after its stages. A flow that joins reads zero
until then. A flow that leaves keeps its last rate until then. The setup has no rate to read. In this
package, a stage at 2 h raises the garden's request and reads the clinic's rate:

```json
{"L": {"kind": "volume", "dimensions": {"volume": 1}, "scale": 1}}
```

```scn
scenario "Rates read as the round began"
    horizon 3 h

tank:
    water: L = 100 in [0, 100]
        outflow.capacity = 6 L/h
    flow clinic: this.water -> SINK
        request = 4 L/h
    flow garden: this.water -> SINK
        request = 2 L/h
    first: L/h = 0 L/h
    second: L/h = 0 L/h
    raise = event():
        when t >= 2 h:
            this.raise.start()
        after 0 h:
            this.garden.request = 6 L/h
            this.first = this.clinic.actual_rate
        after 0 h:
            this.second = this.clinic.actual_rate
```

The first file is `units.json` and the second is `model.scn`. The run gives these readings:

| Path | 1 h | 2 h | 3 h |
| --- | --- | --- | --- |
| `tank.first` | 0 | 4 | 4 |
| `tank.second` | 0 | 2.4 | 2.4 |
| `tank.clinic.actual_rate` | 4 | 2.4 | 2.4 |

The first stage reads 4 L/h, the rate before the round. The stage after `after 0 h:` runs in the next
round and reads 2.4 L/h, the clinic's share of 6 L/h in the ratio 4 to 6.

**The clock** (`moment.Clock`) is the one rule for when something is due. A time that a duration
makes is exact: the engine adds each duration in exact arithmetic and rounds the sum once. So 0.1 h
three times from 0 h is the float of 0.3 h. A time at most the crossing tolerance after the moment's
time is due at that moment. A delay above zero that a moment reaches is due at a later moment.

## Between moments

Between two moments each connected set runs on its method. The next moment is the earliest of:

- a stage that is due, the end of a `reset after D`, or a key time of a keyed read by the time;
- the horizon;
- the first contact of a watched condition or assertion;
- an event of a method (a stock that reaches a bound, the end of a segment) that changes what a
  condition or another set reads.

A condition on a value that moves is watched step by step
([change 20](../design/decisions.md#change-20); `napkin/engine/timeline/triggers.py`). For a value on a line, the engine calculates the time of the
crossing exactly. For a value on a curve, it reads the form of the method's solution over each step:

- a piece that cannot reach the threshold costs no read;
- where the rate of the difference keeps one sign, the engine finds the crossing by bisection on the
  dense output, to the crossing tolerance;
- where the value can turn near the threshold, it halves the piece until each part is certain.

The engine never polls at fixed times. A strict comparison of a moving value has no first instant,
and a condition that the engine cannot certify stops the run with a diagnostic. A value that comes
inside the comparison band of its threshold without a crossing makes a near-tie. A trigger that fires
there, or misses there, has the detail `near` in its trace entry. The
[events page](../language/events.md) tells how a model writes triggers.

A contact joins a nearby moment only when its time and its stock both qualify (amended
[change 27](../design/decisions.md#change-27)). [methods.md](methods.md#contacts-and-moments) tells
the rule.

## The stock ledger

The engine keeps an exact balance for each stock (`napkin/engine/timeline/stocks.py`):

- The ledger opens when the stock comes into existence. The engine evaluates the opening value in
  exact arithmetic when its initializer has no draw.
- Each accepted transfer is posted at both ends of its leg. A stage's `move` debits and credits two
  stocks together, or fails whole.
- The method of a connected set gives the amount that each leg carried through an accepted time. The
  ledger posts the difference from its last post.
- A read of a balance does not post. Grouping of contacts and the search for a crossing do not move
  material.
- An edit of a stock at a stop is a transfer from or to outside. The record gives it as the
  history `external` of the stock, such as `tank.water.external`.

[methods.md](methods.md#the-exact-stock-ledger) tells how the methods supply the amounts.

## The record

A run gives one record (`napkin/program/record.py`). It holds:

- **Histories.** Each recorded value has a list of pieces in time order. A piece reads
  `value + rate * (time - t)` from its time until the next piece. A piece on a curve holds a Chebyshev
  series of degree 8 instead. A jump is a new piece at the same time.
- **The trace.** One entry for each start, finish, commit, firing, draw, move, solve, edit, pause and
  failure, in order. Each entry has its time, its round, its kind, its part and its owner.
- **Near-ties.** The detail `near` of an entry gives, for each comparison that decided within its
  band: the origin, the comparison, the difference and the tolerance. A `contact` entry gives a switch
  or a bound that joined a scheduled moment, with its located time and its signed difference in hours.
- **The manifest.** The horizon, the values that the record holds, and the comparison settings.
- **The failure,** when the run stopped. A value after the stop is `Unavailable`, with the reason.

**The budget of pieces.** The values that a record holds have at most `request.pieces` pieces. A
record that would hold more ends at the time of the first piece that does not fit. Its last entry is
a failure that names the budget.

## `read` and `report`

`napkin.read(record, program, paths, times)` gives one reading for each path, with a value for each
time, in the declared unit of the path. A value comes only from what the record holds. Any other
value is `Unavailable` with the reason: a time before 0 h or after the stop, a value that the record
does not hold. A formula is evaluated at each time from the recorded values of what it reads, never
from its fitted pieces.

`napkin.report(record, program, configuration, paths, times, lags=None, table=None)` reads the same
values and adds the unit, the label, the status display, the evidence trail and the near-ties of
each path. A report claims nothing that the record does not show.

**The evidence trail** of a value lists the parts that the value can read, with the records that
each part cites. It tells whether this run exercised each part. A part is exercised when it acted: a
flow moved material, an event started, a trigger fired, a stage committed, a solver solved, or a
value was read. A part whose use the record cannot show has no answer (`exercised` is `None`).

**A reporting lag** (`napkin.Lag(shortest, longest)`, in hours) shows the mean of the history of a
value from `longest` to `shortest` hours before each time. Equal ends make a fixed delay. A lag:

- reads the pieces of the history with five Gauss-Legendre points in each piece;
- is `Unavailable` where its window begins before 0 h ([change 22](../design/decisions.md#change-22));
- is valid only for a number that a proof says never falls. For another value, the report gives the
  plain reading and a note that tells why.

```python
found = napkin.report(record, model.program, model.configuration, ['tunings_done'], [0, 8760],
                      lags={'tunings_done': napkin.Lag(720, 1440)}, table=model.table)
```

At 0 h the lagged value is `Unavailable`, because the window starts at -1440 h. At 8760 h it is
`2563.101358809935`. On the command line, `--lag tunings_done=1month..2months` gives the same lag.

## Breakpoints, checkpoints and resume

A breakpoint names a location of the compiled program: an event, a stage or a statement
(`napkin.program.checkpoint.Breakpoint`). It applies to every occurrence, or to one member or
occurrence. The engine stops before that location and gives a checkpoint
([change 15](../design/decisions.md#change-15)).

A checkpoint holds these parts:

- the stop: why and where the run stopped, which occurrence, and what runs next;
- the logical state of the run, and the record so far;
- the edits so far, and the saved state of the engine.

Its text form starts with the line `napkin checkpoint 2`. To edit a run and resume it:

1. Run the program with the breakpoints. The result is a `Checkpoint`.
2. Call `checkpoint.edit(target, value)` for each change. An edit gives a live stored value a new value.
3. To resume in another process, save the checkpoint with `dumps`. Load it there with `loads`.
4. Call `resume(program, checkpoint)`. The result is the record, or the next checkpoint.

```python
import napkin
from napkin.engine.timeline import resume, run
from napkin.program.checkpoint import Breakpoint, dumps, loads

model = napkin.load_scenario('examples/reservoir')
stopped = run(model.program, model.configuration, [Breakpoint('operator.decide.step[0]')])
edited = stopped.edit('reservoir.gate', 'OPEN', key=True)
record = resume(model.program, loads(dumps(edited)))
```

This run stops at 40 h, before the stage of `operator.decide`.

**Exact resume.** On one platform, with the same program, engine version, numerical settings and
seed, a run that stops and resumes with no edit gives the same values, draws, event times and event
order as the run straight through. A breakpoint alone never changes which branch fires. A stage that
stopped runs again from its start. Its draws use the same keys, so they are the same. A checkpoint of
another program or another engine version is refused with `CheckpointError`.

A record over its budget of pieces at a stop ends there, and the run gives no checkpoint. The
[Python API](../python-api.md) tells how a `Session` uses checkpoints, and the
[command line](../cli.md) tells how `napkin play` uses them.

## The run store

The run store (`napkin/store.py`) keeps the record of each run on disk, so that a command does not run
the same run twice. It reuses only an identical request ([change 28](../design/decisions.md#change-28)):

- The key of an entry is a digest of the canonical program, the configuration with its request (the
  horizon, the selected keys and the budget of pieces), the engine code, the versions of Python, NumPy
  and SciPy, the machine, the processor and the NumPy CPU features.
- A run with edits also keys its edit log. A log with no edit keys as the run without it.
- The order of the selected keys can differ. The store gives the manifest in the caller's order.
- A different horizon, selection or budget runs again, also a shorter horizon or a smaller selection.
- An identical request that reached its budget of pieces gives the same stored failure.
- A run that raises an exception stores nothing.

The store is off until a caller turns it on. `napkin run` and `napkin sample` turn it on, and so do the
catalogue tests and the maintainer tools. The engine, language and acceptance unit tests never use
it. The processes of a study use the store of the process that made them.

| Setting | Effect |
| --- | --- |
| `NAPKIN_STORE` | A directory for the store, or `off`. The default is `.cache/runs` in a source checkout, and `~/.cache/napkin/runs` (or under `XDG_CACHE_HOME`) for an installed package. |
| `NAPKIN_STORE_LIMIT` | The limit of the store in gigabytes, 4 by default. The entries used least recently go first. |

Each entry has a lock. A process that needs a run that another process runs waits for it, then reads
it. The thread settings of the linear algebra are not in the key. The last digits of a result can
depend on the processor, so an entry serves only the machine that wrote it.
`python -B -m tools.check --all --deep` runs three stored runs again and compares each with the store,
bit for bit.

## Studies

A study runs one program under several configurations (`napkin/engine/study.py`). A Monte Carlo study
(`napkin.monte_carlo`, `napkin/engine/uncertainty.py`) does these steps:

1. It runs the configuration in `median` mode. A central run that stops refuses the study.
2. It runs each sample in `sampled` mode. Sample k takes its seed from the SHA-256 digest of the
   text `seed|k`, where `seed` is the seed of the study. So more samples leave the earlier seeds
   unchanged.
3. A sample that stops refuses the study, with its index, seed and reason.
4. It summarizes each value at each time. For each draw that every sample made once at one site, it
   gives the rank correlation (Spearman) of the value with the draw.

`napkin/engine/estimators.py` holds the estimators:

- the mean, with Student's interval;
- an interval of a quantile from two order statistics;
- a stopping rule that keeps its confidence over several looks;
- the expectation over every path of the outcomes of chance events.

The [Python API](../python-api.md) and the [command line](../cli.md) (`napkin sample`) tell how to
use them.

## Tolerances and reproducibility

The numerical settings of a run (`Numerics`) set every tolerance of the engine:

| Tolerance | Value | Where it applies |
| --- | --- | --- |
| Comparison band | `max(rtol, atol_factor) × max(scale, \|a\|, \|b\|)`: by default 1e-9 times the largest of the scale and the two operands | Every comparison of two numbers, in every evaluator ([change 29](../design/decisions.md#change-29)). |
| Conservation allowance | `atol_factor × scale` | The retirement of an occurrence's stock and the amounts of a frozen stock. At setup, a start value can miss a bound by `atol_factor × max(scale, \|value\|)`. |
| Integration accuracy | `rtol`, and `atol_factor` times the integration size (Component) or the scale (Sparse, MovingDeclared) of each stock | The numerical methods ([methods.md](methods.md#integration-tolerances)). |
| Crossing tolerance | `crossing`, 1e-8 h | The time of a contact or a crossing, and the time between two moments. |
| Step cap | `max_step`, 1 h, or the `resolution` of the scenario | The interval at which a numerical method reads its roots and its field inside a long step. |

A declared `scale` can change only three things ([change 33](../design/decisions.md#change-33)): the
outcome of a comparison inside its band, the accuracy of the integration, and the choice among answers
of a solver that are equally optimal for its nonflow unknowns. A change of the display units changes
nothing.

The scale of a value is its declared `scale`, or else 1 in its declared unit (1 mL for a value in mL). A
literal in the model is exact: it adds no floor to a comparison band, and the relative term of the
band still applies. The
[numerics page](../language/numerics.md) tells how a model declares a scale.

**Reproducibility** ([change 11](../design/decisions.md#change-11)):

- The same run is deterministic. The same code, configuration, seed and thread settings on one
  machine give the same record, bit for bit.
- Anything else agrees within the stated tolerances, not bit for bit: a sample alone or in a batch,
  another platform, other thread settings, a solver formed fresh against a kept one.
- A threshold that sits at a tolerance boundary can fire differently across those settings. The
  trace marks such a decision as a near-tie.
- A draw is keyed by the seed, its site and its owner (the first 64 bits of the SHA-256 of
  `seed|site|owner`), never by its place in a stream. So a branch that is not taken, an extra read, a
  report or the step length of an integrator moves no draw.
- A sum over a list adds in a pairwise tree of a fixed shape (`napkin/engine/timeline/trees.py`). Its bits depend on
  the present values only. The language promises no order of a sum over a list.

A change of the numerical core is compared with the build before it by classes of difference.
[CONTRIBUTING.md](../../CONTRIBUTING.md) gives the rules under "Comparisons of a change of the
numerical core". A refactor that changes no arithmetic keeps the bits ("Refactor comparisons" in the
same file).
Agreement of two builds is no proof of the mathematics: [verification.md](verification.md) tells how
the tests check it.

## When a run stops

A run that cannot continue stops with a named failure. Its record holds the histories to the time of
the stop and the failure as the last trace entry. The engine never gives a different answer in place
of one that it cannot calculate.

| Failure | Cause |
| --- | --- |
| A limit | `max_occurrences`, `max_active` or `max_rounds`. The message names the limit and the event, and for `max_active` the oldest occurrence and the step where it waits. |
| A budget of a solve | `fair-sharing budget exceeded` or `distance budget exceeded` ([solver.md](solver.md#failure-names)). |
| `Numerical evaluation budget exceeded` | A Component or Sparse instance evaluated its rates more than `max_evaluations` times. |
| The budget of pieces | The record would hold more pieces than `request.pieces`. |
| Chattering | The rates switch back and forth at a condition, or a segment takes 1,000 accepted steps in a row, each shorter than the crossing tolerance. |
| Retirement | An occurrence finishes with material in its stock, above its conservation allowance. |
| A write to a frozen occurrence | An assignment, a nonzero `move`, or a flow that carries more than the allowance into or out of a stock of a finished occurrence. |
| A bound | A write or a method puts a stock past a bound by more than its tolerance, or a `move` does not fit. |
| A solver failure | A declared solver cannot give the answer of its selection order ([solver.md](solver.md#failure-names)). |
| An assertion | An assertion over state does not hold. |
| A value | A value is not finite, an expression cannot be evaluated, or a rate is negative. |
