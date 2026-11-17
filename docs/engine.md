# The engine

The engine runs one **resolved structure** at a time: the flat structure of one run
([python-api.md](python-api.md#the-structure)), with the run's input values, that
`Model.resolve(run, values)` gives. It knows nothing of templates, options or files. One timeline
holds the times at which something can happen. At each moment, the engine takes everything that
happens, one event at a time. Between moments, one solver moves the quantities of the model
together. The reports read the finished run and never change it. The rows of a table run in another
form, which gives the same results at a lower cost ([Tables and tiers](#tables-and-tiers)).

This page is the contract of the engine: what a run does with each part of the structure.
[python-api.md](python-api.md#names) names the parts, and [language.md](language.md) says how a
scenario's model file writes them. [compiler.md](compiler.md) says how the compiler makes the
structure. The structure is a record of typed parts ([python-api.md](python-api.md#the-structure)).
Words in `code` are its sections and the fields of its parts. A key of the model file is written as
the file writes it, such as `when` or `after`.

```python
import napkin
from napkin.engine.report import evaluate_outputs
from napkin.engine.runtime import simulate
from napkin.model.ir import thaw

model = napkin.load_scenario('scenarios/iv_fluid_shortage/model.scn')
library = thaw(model.library)
rs = model.resolve('subpar_persistent')               # the resolved structure of one run
trajectory = simulate(rs, library)                    # every step and every segment, to the horizon
rows = evaluate_outputs({'resolved': rs, 'trajectory': trajectory}, library, [24, 168])
```

These functions are internal. `Model.resolve(run, values)` takes `values` for some inputs: a number
in the input's unit, True or False, a name, or a distribution, which takes its central value. Every
other input takes the run's value. It checks the values, normalizes them to execution units, applies
the blocking checks of the inputs and proves the run's bounds and domains. A failure raises
`ModelError`. The resolved structure is a `Resolved` record (`napkin/model/structure.py`). It is the
structure of the run's start-state options with
`values` (the input values in execution units), `parameter_values` (the values in the inputs' own
units), `time`, `initiation`, the `run`, its `options` and `starts`, the `model_hash` and the results
of the proofs. A sample of a Monte Carlo study has `luck`, the seed and number of its draws. A run
can take the outcomes of its chance events from its caller
([The outcomes of a run, given](#the-outcomes-of-a-run-given)). What a
played run asks (who picks, and the picks; [Play](#play)) is no part of the resolved structure: it is
an argument of the run, `simulate(rs, library, settings, play={'control': …, 'picks': …})`.

The public functions do this for each run of a study ([python-api.md](python-api.md)):
`napkin.evaluate_study` and `napkin.sample_result` give the report of
`napkin/schema/report.schema.json` ([The study](#the-study)). `napkin.evaluate_uncertainty` also runs
samples of each run whose values hold distributions ([Monte Carlo studies](#monte-carlo-studies)).

The study takes its table of inputs and options from `model.run_table`. It does not read the
file's values or resolve units again. Edit admission remains one transaction: the shared table
checks names, values, precedence and collisions, then the model checks the resolved structure's
bounds and domains. `Runs.from_scenario(scenario, library)` reads the same table from a semantic
model, for analysis before compilation.

## What the engine reads

| Section | What the engine does with it |
| --- | --- |
| `values` | The input values in execution units, by `entity.value`. They never change during a run. |
| `quantities` | The numbers that the run holds: stocks, tallies, number states and yes/no states (0 or 1). Each has a `kind` (`stock`, `cumulative` for a tally, or `variable`), a `unit`, an `initial` expression, its bounds `minimum` and `maximum`, and the `size` that the file gives it (`size:`), if any. The builder gives a stock and a tally the `minimum` 0 unless the file sets one. A yes/no state has the bounds 0 and 1, and a number state has no bounds unless the file sets them. |
| `rates` | The rate of change of a tally, `{expr}`, per hour: a flow of the file whose one pair runs from outside into a tally (`flow f: -> x at R`). |
| `flows`, `allocation`, `coupling` | Material that moves between quantities all the time, and how flows share a capacity or move together ([Flows](#flows-allocation-and-coupling)). |
| `modes` | The named states: `{values, initial}`. |
| `computed`, `labels` | Formulas and statuses: functions of the present values, calculated again whenever they are read. A label takes the value of its first case whose `when` holds, or its `default`. Each `status` line with a condition is a case, and the last line, which has none, is the default. |
| `rules` | The only parts that change the state at a moment ([Rules](#rules)). |
| `events` | The events that the run counts, `{event: {sources}}`. |
| `input_checks`, `state_checks`, `partitions` | The checks before and during a run: the file's `assert` lines ([Checks](#checks)). |
| `outcomes` | What the report gives: the outputs of the file ([Outcomes and reports](#outcomes-and-reports)). |
| `entities` | The status of each entity (`health`) and whether the report lists it (`metadata.internal`). |
| `parameters` | The input definitions: their records (`basis`) for the evidence trail. |
| `time` | The `horizon`, in hours; the `timescales`: expressions of inputs that cap the solver's step; and the scenario's `resolution` in hours, when its file gives one. |
| `proven_zero_stock_faces`, `proven_monotone_crossings`, `proven_cumulative_outcomes` | What the build proved: the stocks of each closed network in which a crossing rule watches a stock reach zero, the crossing rules that watch a quantity that only rises or only falls ([Triggers](#triggers)), and the outcomes that never fall. |
| `initiation` | The start: `{rule, effect, entity, basis}`, the rule of the event `start` of one thing, which fires first at t = 0, and its outcome's event. The study checks that it fires first ([The study](#the-study)). |

The engine does not read `links`: the model's evidence index reads them.

A moment takes rules in the order of their `rank` ([One moment](#one-moment)). The solver keeps
the order of the structure's quantities, rates and flows, and a residue at zero can depend on it. The
builder sets this order: the entities by name, each with its stocks, tallies and states in the order
of the file (an instance takes the order of its template), and the flows by name.

### The store and the environment

Beside the quantities, a run keeps a store of discrete values:

- `m` and `m__entered`: the value of each mode, and the time when it took that value (a step that
  sets the value that it already has does not change the time);
- `e__count` and `e__time`: how many times the event `e` has happened, and the time of the last
  occurrence (valid when the count is positive).

The builder rewrites the file's `count(e)` as `e__count`, a comparison with `since(e)` as
`(e__count > 0 and t - e__time OP x)`, and `elapsed(s)` as `(t - s__entered)`, for any named state
`s` (`napkin/model/lower/expressions.py`;
[compiler.md](compiler.md#the-forms-that-are-no-operation-of-the-engine)). `t` is the time in hours
since the run started. A clock that runs from the entry time of a mode
other than its rule's own runs from that mode's last entry, and a step that changes that mode starts
it again; the search for the next time of a clock reads both kinds of anchor.

Every expression reads one environment: the input values, the quantities, the store, `t`, and the
formulas and labels, which the engine calculates in the order of their dependencies. The expression
language is typed and has a closed list of functions
([language.md](language.md#24-fields)). The build checks the
units of every expression, and values run in execution units. The structure holds each expression as
its typed node ([compiler.md](compiler.md#typed-expressions)).

A run calculates its expressions with generated programs (`expressions.compile_program`): one for
the rates, the flow rates and the capacities, one for the formulas of an environment, one for the
checks on the state, and one for the roots of each numerical segment. An input that no quantity,
entry of the store, formula or `t` hides is a literal in a program. The program calculates each part
of an expression that reads only such inputs once, when the program is made. A program gives what
each expression gives on its own, bit for bit. When a program fails, the engine evaluates each
expression on its own, in order, so the first one that fails names itself.

A program checks each value: a number must be finite. The program of the rates, the flow rates and
the capacities runs at each evaluation of the field, so it checks a value only where a value that is
not finite could be hidden (`evaluation.program`, `lean`): where a comparison, a test, `min`, `max`,
`clip`, a divisor, a power, `exp`, `expm1`, `erf` or a quantity reads it, where a formula is
assigned and at each output. A sum, a difference, a product or a quotient of a value that is not
finite is not finite, so the next check finds it. The values are the same, and a program that fails
with every check fails with these. The engine keeps the code of the last programs by their text, so
the segments of a run and the runs of a study share it.

## Rules

Each event of the file is a rule `entity.event`; the start is the rule of the event `start` of its
thing.

| Field | Meaning |
| --- | --- |
| `trigger` | `when`, the condition (an event's `when`, or `False` for an event that only a line that names it fires), and how the build classified it (below). |
| `once` | The rule triggers at most once in a run (`event e once`). |
| `named` | The event has no `when`: only a line that names it triggers it. |
| `delay` | The time, in hours, from the trigger to the firing (`after D`), read when the rule triggers; None to fire at once. |
| `extras` | The values that the rule reads at a firing, each with its placeholder `name` and its `stage` (`trigger` for the delay, else `fire`): a draw (`family`, `args`), which the central run takes at its median and a sample draws from the stream `rule/draw/sample`, in order; a delayed value (`expr`, `delay`), read from the run's own trajectory at `t − delay` (after every step of the first moment, when that is before the start). |
| `each`, `keep` | The values of the rule's window (`each W`): it triggers at most once for each of their combinations, which the run keeps when it triggers. The condition under which a firing that waits still happens (`while K`): the run cancels it at the first moment that `K` fails. Both read only values that change at moments. |
| `rank` | Its place in the order of one moment: the line of its event in the file, then the instance and the copy (`(-1,)` for the start). |
| `outcomes` | `[{name, chance, label, basis, path, do, emits}]`: one of them happens at each firing. `chance` is an expression, None (1) or `else` (1 less the others). `do` is the outcome's step: `set`, `transfer` and `fire` (below). |
| `emits` | The rule's own event, `entity.event`, which its trigger adds; each outcome adds its own, `entity.event.outcome`. |
| `choice` | True on an actor's event marked `choice`: a run can give it to a person or an agent. The build has checked that it reads only what its actor sees. |

**Memory.** A rule triggers when its condition becomes true: it is armed while the condition is
false, and a trigger disarms it. A `once` rule triggers once. A rule that waits to fire does not
trigger again. The build rejects a rule that can trigger again on a crossing, when an outcome sets
none of the names that its gate reads: the crossing would hold again at the same moment.

### Triggers

The build reads each `when` as an `and` of conditions (`analysis.structure.classify`). The conditions that read
only names that change at moments make the `gate`. At most one other kind of condition remains, and
it gives the trigger its `kind`; only a crossing can also have clocks:

| `kind` | The other conditions | The rule is due |
| --- | --- | --- |
| `discrete` | None. | At any step at which `when` holds. |
| `timer` | `t >= X`, or `t - S >= d` with `S` an event time or a mode's entry time (`times`: each `X` or `S + d`). | When the gate holds and `t` has reached every time in `times`, within 1e-8 h. |
| `crossing` | One quantity that moves between moments, compared by `>=` or `<=` with a value that changes only at moments (`var`, `op`, `value`), and any clocks (`times`, as for a timer). | When the gate holds and `t` has reached every time in `times`: at the crossing's own time, which is the time at which the quantity reaches the value ([When a crossing is due](#when-a-crossing-is-due)). |
| `face` | Stocks of `proven_zero_stock_faces` compared with zero (`face`). | At any step at which `when` holds. |

The build rejects any other condition, with its path. A crossing belongs to one of three classes:

- the rate of the quantity changes only at moments, and so do the rates of the flows that move it, of
  the flows that share an allocation or coupling group with one of them, and the capacities of those
  allocation groups; or
- the rule watches `stock <= 0` and changes only named states, and the stock lies in a closed network:
  every flow of the network runs between two quantities of the model and draws on a stock whose
  minimum is 0, no quantity of the network has a rate of its own, and the rates and capacities of the
  network never fall below zero and read its stocks only by comparing them with zero. The stocks of
  these networks are `proven_zero_stock_faces`; or
- the quantity only rises, or only falls, between moments (`analysis.values.monotone_quantity`): it is a
  tally, or every flow that moves it goes the same way (all into it, or all out of it) and its own
  rate has that sign, or is zero, on the declared ranges. Its rates can read the state. These rules
  are `proven_monotone_crossings`.

Where a face condition holds, it must still hold when any stock that it reads falls to zero, for
every combination of the modes and the stocks that it reads (at most 2,048). So the solver always
ends a segment where a rule becomes due: at the next timer whose gate holds, at the crossing of each
crossing rule whose gate holds, and where a stock reaches zero. A condition is never checked only at
sample times.

**A crossing with clocks.** Between two moments, every gate, clock anchor, duration and threshold is
constant, so the clocks together are false before one time T, the latest of their times, and true
from T until the next moment. The crossing can change only where the quantity minus the value
changes sign, and the quantity is continuous between moments. So the condition first holds at T, when
the crossing holds there, or else at the first root after T in the direction that makes the
crossing true. The engine ends a segment at T, as for a timer, reads the rule there, and watches
the crossing's root only from T. A moment before T can change an anchor, a threshold or a gate; the
engine reads a rule again after each step that writes a value that the rule reads, so no change is
missed. Two crossings, a crossing with a face, and a clock with a face stay out: no such argument
holds for them.

**A crossing of a quantity that only rises or only falls.** A flow rate is never negative (a negative
rate stops the run), and allocation and coupling scale a flow by a share from 0 to 1, so a flow into
the quantity can only raise it and a flow out of it can only lower it. A bound stops the quantity
without reversing it, and transfers and boundary corrections happen at moments. So between two moments
the quantity is monotone, the value is constant, and the quantity minus the value changes sign at most
once. The solver tests that sign at each accepted step, so the step that holds the crossing brackets
it and no step can hide two. Such a quantity can approach its value without reaching it, as a stock
that drains in proportion to itself approaches zero. So the solver watches the root half a tolerance
inside the band of the quantity's absolute tolerance around the value: the rule is due where the
quantity comes that near, and a root found by Brent's method lies inside the band. A quantity whose
limit lies in the outer half of the band never comes that near: its rule does not become due. The
two tiers watch the same root: a block of the fast tier that a solver integrates has the crossing
of such a quantity half a tolerance inside its band too.

#### When a crossing is due

A crossing is due at its own time: the time at which its quantity reaches its value (for a solver,
the root above). At a moment that another rule caused, it is due in two cases only: when that moment
is within 1e-8 h of its own time, as a clock within 1e-8 h is; or when a step of that moment wrote a
value that the crossing reads, and the quantity is then at or past the value. It is not due only
because its quantity is inside its tolerance band at a moment of another rule. A crossing that was
reached stays reached until its rule triggers or a step writes its quantity.

### The step

A firing takes one outcome by its chances: the central run takes the likeliest, the first in the file
on a tie; a sample of a study draws one, with one uniform number from the stream of its event. The
chances must be from 0 to 1 and add up to 1 within 1e-9, or the run stops (`chances`).

In a played run (`simulate(…, play={'control': …, 'picks': …})`; [Play](#play)), a
`choice` rule that `control` gives to a reader or an agent (by the rule, or by its actor) takes
the next pick of the log instead. The pick must name this decision
and an outcome that can happen: one with no `when`, or whose `when` holds (its chance is the model's
estimate, which the pick replaces), or the run stops (`pick`). An outcome whose `when` fails must have
no chance, or the run stops (`chances`). The first decision with no
pick left takes the central choice; the run keeps it, with what the actor sees, as the run's
`decision`. The trace entry of a picked firing has `picked`, who picked it. This is the default
behavior, and the same log gives the same run.

`simulate(..., pause_at_decision=True, decision_events=None)` instead stops before committing the
first unanswered controlled outcome. An optional set of rule IDs limits control to strategic
decisions; other rules retain their normal seeded behavior. The returned trajectory has `paused`
true and `end_time` at that exact boundary, while `horizon` retains the scenario's planned end.
Earlier committed steps at the same time remain visible; later steps and the unanswered outcome
are absent. Sampling beyond `end_time` is rejected. A pause at the horizon is still a pause.
Completed-run reports and the run store reject paused trajectories. Continuing replays the saved
pick log with the same inputs, numerical settings and seed; no live solver checkpoint is required.
`Session.advance()` simulates in this mode ([python-api.md](python-api.md#session)).

`simulate(..., pause_at_decision=True, decision_resolver=callback)` lets a trusted controller
authorize an unanswered choice at its exact boundary. The callback receives `(decision, env, trace)`:
the decision includes the zero-based `pick_index`, the environment is a read-only snapshot, and
the trace is a tuple of read-only entry mappings. Nested trace values are borrowed and must not be
changed. These are internal execution views, not player-facing permissions. The controller must
project permitted observations before showing information to a player.

Return a pick mapping with `event` and `outcome`, or `None` to pause normally. The controller must
save an authorized action durably before returning it. The engine validates the pick against the
current event and available outcomes, then commits it within the same simulation invocation.
Already saved picks bypass the callback. Invalid picks and callback exceptions stop execution;
they never select a fallback action. A resolver requires pause mode; ordinary callers are unchanged.
A `Session` with a `resolver` is such a controller. It gives its resolver the decision without
`pick_index`, and never the environment or the trace. It logs each answer before it gives the pick to
the engine.

`simulate(..., settled_decisions=True)` opts a played run into decision windows. Independent
non-controlled rules already due at the current timestamp settle before a controlled outcome.
Their cascades can make further current rules due. This does not advance time or execute any
outcome that needs an unanswered choice. Delayed controlled rules may record their deterministic
trigger before their outcome is due. Within each phase the run retains file order.

A named controlled call holds its later siblings in a continuation. Earlier parent and sibling
steps remain committed; independent current work can settle before the question, but later
siblings cannot pass that unanswered call. After its chosen outcome commits, its continuation
resumes and newly enabled current updates settle before the next question. The default leaves
both the original recursive named calls and file-ordered scheduling unchanged. Replay must use
the same decision-window option as the original played run.

Every expression of the outcome's step reads the values from before the step. Two sets of one value
in one step are an error when the model is built. A step can set a quantity and also move it: the
set applies first.

| Field | Meaning |
| --- | --- |
| `set` | New values: those of the lines `x = v`, `x += v` and `x -= v`. A mode takes one of its values: `{mode}`, or `{expr, values}`, an expression that must give one of `values`. A quantity takes a finite number (`{expr}`). |
| `transfer` | `{source, target, amount}`: moves a finite, nonnegative amount from one quantity to another, from a line `move A from S to D`. |
| `fire` | The rules that the step names, which trigger after it, in order. |

A step commits when every quantity that it sets or moves stays within its bounds; else the run stops
(`transaction_failed`). Its quantities take their new values, its transfers move one after another,
its modes take their new values, and its events follow. A transfer that would leave its source
within the source's absolute tolerance of its minimum, above it or below it, moves everything that
is above the minimum, so that the arithmetic never leaves a residue in a stock
([Roundoff at bounds](#roundoff-at-bounds-the-arguments)). A value that misses a bound by less than
the solver can resolve is set on the bound. Then every quantity must be within its bounds (`joint_feasibility`).

Each event adds one occurrence: its count rises by one, and its time is now.

## One moment

One timeline holds the times at which a rule can become due: the time of a clock, the end of a
delay, the time at which a crossing reaches its value, and the end of a segment. A moment takes the
times within 1e-8 h of the earliest. At each moment the engine fires the rules that are due, one at
a time:

1. A rule is due when its condition has become true and it can trigger, or when its delay ends now.
2. The first due rule in the order of `rank` goes: it triggers (and fires at once, or waits its
   delay), or it fires. After its step, each condition that reads a value that the step wrote is read
   again, and the next to go is again the first due rule in that order. A condition that reads nothing
   that the step wrote has the answer that it had, so the engine does not read it again; no model can
   tell. The rules that a step names trigger at once, after the step, in the order of its lines.
3. After each step, no tally can have fallen, and every check on the state and every sum check must
   hold ([Checks](#checks)).
4. The moment ends when no rule is due.

So a rule reads what the rules before it in the file wrote at the same moment. A moment that takes
more than `max_steps` steps stops the run (`step_budget`), with the rule due next.

The trace has an entry for each step: `{t, step, rule, entity, event, outcome, label, changes,
before, transfers, path, basis, fires, semantic}`. A firing's `event` is its outcome's event and
`outcome` its name. A rule with a delay also has an entry when it triggers, with its own event and no
outcome. `semantic` is true for an entry with a label: an outcome's text, or the event's text for a
trigger and for a firing of an event that fires at once.

## Between moments: the solver

`NumericalSettings` (`napkin.engine.runtime`) holds the settings of a run. A caller can give
other values to `simulate` or `evaluate_study`; an unknown or invalid setting rejects the study
(`numerical_settings`).

| Setting | Default | Meaning |
| --- | --- | --- |
| `rtol` | 1e-9 | The solver's relative tolerance. |
| `atol_factor` | 1e-10 | Each quantity's absolute tolerance is this factor times its size in execution units (below). |
| `max_step` | 1 h | The step cap of a scenario without a `resolution`: the interval at which the engine reads a numerical segment (below, "Steps"). It scales a scenario's resolution: the cap is the resolution times `max_step` / 1 h. |
| `max_evaluations` | 2,000,000 | The most evaluations of the rates in one run. For the rows of a table it is a limit for each row ([Tables and tiers](#tables-and-tiers)). |
| `max_events` | 10,000 | The most trace entries in one run. With a table, the limit is this number times the rows of the largest table. |
| `max_steps` | 1,000 | The most steps at one moment. With a table, the limit is this number times the rows of the largest table: each row can take its steps at the same moment. |

- **Sizes.** Each quantity's size is the `size:` that the file gives it, or else the largest of one of
  its unit, its start value, its finite bounds, the largest start value of the quantities that flows
  and transfers connect it to, and the capacity of an allocation group that rations one of its flows,
  over the horizon (`System.sizes_of`, from the run's own values). A quantity that fills from empty to
  far beyond its start needs a `size:`: with the size of one unit, a roundoff on a large value can
  exceed its tolerance at a bound and stop the run, and a tiny tolerance makes the solver slow.
- **Steps.** The step cap is the smaller of the requested step and one eighth of the shortest timescale.
  The requested step is `max_step`, or for a scenario with a `resolution` the resolution times
  `max_step` / 1 h, so one setting refines every run by the same factor. A timescale reads inputs only,
  and it must be finite and positive. A scenario without the line keeps its structure, its settings
  and its model hash, so its stored runs stay valid.

  The cap is the interval at which the engine reads a numerical segment: its roots, its field and
  its hidden excursions. It is not the longest step of the solver. The solver's own control of the
  error decides its steps, and one eighth of the shortest timescale that the scenario declares
  limits them. So a quiet part of a run costs few steps. Inside a step that is longer than the cap,
  on the dense solution of the step (`integrate.radau`):
  - At each half of the cap, the engine evaluates the field and compares it with the rate of the
    dense solution. The difference, times the length of the step, must be within the solver's
    tolerance (`integrate.departure`): the error of the dense solution in the step is no more than
    that. The largest difference of a step also sets the longest next step. When the difference is
    too large, the step is not used, and the solver goes on from the start of that step with a
    shorter limit, down to the cap. So a pulse of a rate, or a switch, inside a long step is found
    when it is there at one of the times at which the engine reads the field: one that lasts for
    half a cap or more. A shorter pulse between two such times can be missed, where a solver held
    at the cap can find it at a point of one of its steps or miss it too: for a pulse of 0.05 h
    in a run of 1,000 h with a cap of 1 h, the engine gives a total of 1.0 where the closed form is
    1.089. A model with such a pulse states a `resolution` shorter than the pulse, or a timescale.
  - At each cap, the engine reads the roots.

  A limit at the cap does not stay: after one step of the cap the solver can take two caps again,
  and then what its steps show. In a part of a run where a longer step fails each time, that
  would lose each second step. So the wait doubles with each fall to the cap in a row, to 32
  steps of the cap at the most, and it is one step again when a longer step is used and allows a
  longer step after it (`integrate.Limit`).

  A numerical block of the fast tier ([Tables and tiers](#tables-and-tiers)) is read in the same
  way (`Solution.advance` of `napkin/engine/timeline/run.py`), with the same limit and through
  each solver adapter: the field at each half of the cap inside a long step, and at each whole cap
  the value of a crossing and the state of the block (its bounds, and the signs of its flows).

  **A stalled segment.** A surface that is at its switch when a segment starts does not end the
  segment (below, "Switches"). When each branch of it takes the state back across it, the steps of
  the solver get shorter and shorter: for example, a stock whose outflows are written
  `rate if stock > 0 else 0` and ask for more than comes in. After 1,000 accepted steps in a row
  that are each shorter than the event time tolerance (1e-8 h), the run stops with the code
  `chattering` (`integrate.STALLED_STEPS`, `Limit.accepted`). A step that is not used does not
  change that count, and a longer step starts it again. When the solver itself fails there (its step
  is less than the spacing of the doubles at that time), the run stops with the same code. The
  diagnostic gives the time, the surfaces at their switch in the last state and the quantities that
  they read. Without the condition, the engine gives the outflows of the empty stock what comes in.
- **Segments.** A segment runs from one moment to the earliest of: the horizon; the next timer whose
  gate holds; the crossing of a crossing rule whose gate holds; a quantity that reaches a finite bound,
  or leaves by twice its tolerance a bound that it rests on; and, in a numerical segment, a switch of a
  rate (below). The end of the segment is a moment of the timeline.
- **Exact segments.** When no stock leaves a zero face at the start of a segment, and every rate, flow
  rate and capacity stays constant through it, the engine solves the segment exactly as a straight
  line. When no stock leaves a zero face and the moving quantities form a positive linear system of
  compartments, it solves the segment exactly with a matrix exponential. The exponential is of the
  quantities whose rates read quantities, and of the quantities that they read. A quantity whose rate
  reads no quantity moves on a straight line. Otherwise the Radau method, an implicit solver,
  integrates the segment, with dense output.
- **Roots.** The engine takes the Radau steps itself (`integrate.radau`). With no step longer than
  the cap, they are the steps, the roots and the result of SciPy's `solve_ivp`, bit for bit. After
  each step, and at each cap inside a longer step, it evaluates all the roots of the segment
  together (`integrate.Roots`): the crossing rules, the bounds, the releases from bounds, the
  repayment surfaces and the switches. Brent's method finds the time of each root that changes sign
  between two such times, on the dense solution, and the first in time ends the segment. At the two
  ends of the step, it takes a root's values at the accepted states: the dense solution there can
  miss them by roundoff. A root that changes sign and back between two such times is not seen; a
  shorter timescale or resolution sees it.
- **Values that only rules set.** A quantity with no rate and no flow stays constant between moments.
  The solver's trial stages keep it at its value.
- **Switches.** Each pair of arguments of `min`, `max`, `clip` or `abs`, and each comparison other
  than `==` and `!=`, in a rate, a flow rate, a capacity or a formula that they read, is a switching
  surface. A numerical segment ends where one switches, so that one solver step never mixes two
  branches. A surface that is at its switch when the segment starts does not end the segment.
- **A segment that starts on a switch.** A rate can compare a quantity with a value, for example
  `1 if released > 0 else 0`. When a segment starts with a nondecreasing quantity on its lower bound,
  a rate compares it with that bound, and the quantity starts to increase, the solver uses the rate
  from just above the bound for the whole segment. The quantity is above the bound at every later time
  of the segment, so this is the rate that applies there.
- **Hidden excursions.** After a numerical segment, the engine samples the dense solution once per step
  cap from the start of the segment. A sample beyond a bound by more than its tolerance stops the run,
  and so does a sample past the value of a crossing rule (a value fixed in the segment) when no root
  ended the segment. An excursion between two samples is not seen. A shorter timescale resolves it. A
  coarse `resolution` makes the samples coarse too, so it suits a model whose fastest change is slower
  than the resolution.
- **Stock faces.** A stock of `proven_zero_stock_faces` reaches zero exactly: the segment ends at the
  time when the stock runs out, the stock stays on zero while its net rate there is zero (an inflow
  that flows straight out does not lift it), and it leaves zero when its net rate is positive. A field
  that does not point up just above zero (its rate there is zero or less) would bring it straight
  back: the run stops.
- **Roundoff at a bound.** When the solver leaves a quantity a little beyond a bound, within its
  tolerance, the engine puts the quantity on the bound and moves the difference to a quantity that its
  flows connect, or to the outside. It records each correction as a `boundary_roundoff` diagnostic
  (severity `info`). A larger excursion stops the run.

## Flows, allocation and coupling

- **Flows.** A flow moves material from its `source` to its `target` at its `rate` per hour: a
  `flow name: A -> B` of the file, with its `rate:`. Its `while:` makes the rate zero while it fails.
  Either end can be outside the model: the flow then has no `source`, or no `target`. A negative rate
  stops the run.
- **Allocation.** The flows of an `allocation` group `{policy, capacity, order}` share its `capacity`,
  the most that the group gives out per hour. With `proportional`, requests share capacity in
  proportion to their original rates. A member capped by its own source or destination keeps that
  cap while the remaining members share the unused capacity with their original weights.
  With `priority`, the flows take their requests in `order`, each in full before the next. A flow that
  a bound holds back leaves its share of the capacity to the other flows of the group. A `share` of
  the file makes the group of the flows that take from its stock. Its `limit` is the `capacity`;
  without `order`, the policy is `proportional`, and `order f, g` gives the policy `priority` with
  that `order`.
- **Coupling.** The flows of a `coupling` group move by one fraction: when one flow is cut, every flow
  of the group is cut by the same fraction. The pairs of a flow of several pairs (the pairs under its
  line) make one group. A flow of the group that requests nothing while another requests something stops the
  run.
- **At a bound.** Where a quantity rests on a bound (a stock on its minimum, a quantity at its
  maximum), the engine serves the largest share of every request that keeps the bound, priority groups
  upstream first: a group decides after every group whose flows feed the stocks that it draws on, and
  groups that feed each other keep the order of the file. Material that cannot move is limited, never
  lost: a flow out of an empty stock gets only what flows in, and a flow into a full stock is cut.
  Flows that compete for one stock at its bound must share one allocation group, or the run stops.
  Proportional groups linked by one coupled transaction are allocated together at these bounds.
  Separate proportional groups decide upstream first, so downstream demand does not change the
  shares of its upstream supply.
- **A stock that rests on a bound.** When what flows into a stock on a bound equals what flows out,
  its rate is zero. The sum of its flows keeps the roundoff of its terms, of either sign: a few
  units in the last place of those flows. Where such a residual would carry the stock past its
  bound, the engine does not read it as a rate: for a stock that is exactly on its upper bound, for
  a proven zero face, and for an empty stock whose flows ask for more than comes in, a residual
  within 32 times the machine epsilon of the size of its flows becomes exactly zero, and one leg of
  the stock takes it (a flow out of it, a flow into it, or its flow from or to outside the model),
  so the total does not change. A tally takes no residual that would make it fall. A larger
  residual stays a rate. So does a residual above zero of any other empty stock: its inflow is
  more than its outflows in the numbers of the run, and it rises by that
  ([Roundoff at bounds](#roundoff-at-bounds-the-arguments)).
- **Tallies.** A quantity of kind `cumulative` never falls: a negative rate, or a step that lowers it,
  stops the run.

### Roundoff at bounds: the arguments

Five parts of the engine remove roundoff at a bound. Each one rests on an argument about the
arithmetic. The arithmetic is of IEEE doubles, rounded to the nearest. `eps` is the machine
epsilon, 2.2e-16. A tolerance is the absolute tolerance of the quantity (above, "Sizes").
`tests/engine/test_roundoff_properties.py` tries to break each argument with many cases.

1. **A transfer leaves no residue** (`_fire` in `napkin/engine/timeline/run.py`). A move computes
   what it leaves in its source, the value less the amount. When that is not on the minimum of
   the source, but within its tolerance of the minimum, above or below, the move takes the
   difference too: the source is set exactly on its minimum, and the target gets the value less
   the minimum. When the source already holds less than its minimum, nothing moves. The amounts
   that a model writes, such as three thirds of a stock, do not add up to the stock in doubles;
   this rule makes the last move empty the stock. The target takes one rounding of its sum, so the
   total changes by at most that. A difference larger than the tolerance stays in the source.
2. **A residual on a bound goes to a leg** (`Allocation.balance` in `napkin/engine/allocation.py`).
   The rate of a stock is the sum of its flows, and NumPy chooses the order of that sum. So the
   argument reads only the size of the residual, not the order of its terms: a residual is
   roundoff when it is at most 32 `eps` times the size of the terms, which is the absolute value of
   the rate of the stock without its flows and the sum of the requests of its flows. A flow that the
   allocation cuts delivers a part of its request, which is computed from the request, so the
   roundoff of the sum is of the size of the requests. On the
   upper bound, the stock must be exactly on it, and its upper bound active. On the lower bound,
   the stock must have its lower bound active, be exactly on it or on a zero face, and be a
   proven zero face, or an empty stock whose flows asked for more than comes in. The rate of the
   stock becomes exactly zero, and the first leg that can take the residual takes it: the first
   flow out of the stock, in the order of the flows of the file, that moves something into a
   quantity (a tally only when it does not fall); else the first flow into the stock that moves
   something from a quantity above its minimum by more than its tolerance; else a flow from or to
   outside the model that moves something. With no such leg, the residual stays. A larger residual
   stays a rate: the bound allocation, the roots of the segment and the checks of the state
   answer for it.
3. **The short path of the closed form** (`Allocation.served_in_full`, which `closed_form`
   calls). When every unit is one flow, and no product of a request with a coefficient is zero,
   the short path computes the same fractions as the closed form: the same products
   (`0.0 + a * request`), the same sums from the left, in the same order, and the same
   `min(1.0, available / need)`, on the same doubles. It says that every unit is served in full only
   when each fraction is exactly 1.0. Then the closed form gives the request back, which is what
   its own work gives, in each bit. The argument holds because a Python float and a NumPy double
   use the same correctly rounded operations. In any other case the short path says no, and the
   closed form does all of its work.
4. **A face that runs out within the ulp of the time** (`rounded_faces` in
   `napkin/engine/continuous/bounds.py`). The time of a depletion is a double, so a stock that
   runs out at a constant rate can keep a small remainder at the end of its segment. Before each
   segment, a proven zero face that holds more than its minimum, but not more than its tolerance
   above it, and whose rate is below zero, is settled when its remainder runs out within one ulp
   of the time: no later double is the time of its depletion. The engine puts it on its minimum
   and gives the remainder to a leg (`boundary_roundoff`, above, "Roundoff at a bound"). That is
   a moment for the rules and the checks; the segment comes after it. A remainder that runs out
   later has a segment of its own, and one that is larger than the tolerance is not settled here.
5. **A face that departs is probed one ulp above zero** (`depart_faces` in
   `napkin/engine/continuous/bounds.py`). A proven zero face that is exactly on its minimum, with a
   rate above zero there, departs. The engine computes the field again with the stock at the next
   double above its minimum and its lower bound released, so that a comparison such as
   `stock > 0` reads the stock as above zero. A proven face that this field lifts from its minimum
   departs too, and the field is computed again. When the rate of a departing stock in this field
   is zero or less, the run stops: the face would chatter. Else the segment uses this field. The
   probe sees a switch at the minimum itself, not a switch at a level above the next double: the
   switches of the segment find such a switch.

## Checks

| Part | When | A failure |
| --- | --- | --- |
| `input_checks` (an `assert` that reads only inputs and named states) | Before a run, on the input values, the formulas of inputs and the start values of the named states. | A failure is an error and the run does not start. The model tests these checks before its proofs, so an edit that breaks one is rejected with the check's own message. |
| `state_checks` (any other `assert`) | At every solver point and after every step. | Stops the run (`check_failed`), with the values that the check read. |
| `partitions` (`assert a + b is T within d`) | At every solver point and after every step. | The `parts` must add up to `total` within `tolerance` (`within`), or one part in 10⁹ without one; else the run stops (`partition_failed`). |
| Bounds | At every solver point and after every step. | A quantity below `minimum` or above `maximum` by more than its tolerance stops the run. |

The build admits a check on the state only when it cannot fail and hold again between two solver
points: a comparison that the bounds decide, a balanced sum, a monotone comparison, `abs(x) <= c` when
`x <= c` and `-x <= c` each qualify, or an `and` of these.

## Outcomes and reports

- **Values.** `evaluate_outputs(run, library, times)` gives each outcome at each time, in its own unit,
  with its status: `estimated`, `unestimated` (an output with `unestimated:`) or `not_applicable`. An
  outcome that is not estimated has no value (null), never zero. An outcome that reads one that is not
  estimated is not estimated either. A value that is not finite, or a `nonnegative` outcome below
  zero, is a reporting failure. Every output without `signed: true` is `nonnegative`.
- **Lags** (`lag:`) delay a cumulative count as the report gives it, not as it happens. `fixed` reads
  the count at `delay` earlier; `uniform` takes its mean over the times from `maximum` to `minimum`
  earlier;
  `mixture` adds fixed delays with their weights. A lag acts on the whole history, jumps included, and
  includes the value at the exact delayed jump. Before time zero, a lagged count is zero when the
  outcome is estimated at the start. For a `uniform` lag, a report cuts the history at the ends of the
  windows of all its times and at the times of the trace. It integrates each piece once (`quad`), and
  each window adds its pieces.
- **Reporting points.** A report gives each outcome at `final`, the horizon, and at each time that
  the report asks for, by its number of hours (`'24.0'`). The model names no reporting times.
- **Peaks** are candidates: the largest value at the ends and middles of the segments. The times
  that a report asks for are not candidates, so a peak is the same in every report of the run. An
  outcome of `proven_cumulative_outcomes` peaks at the horizon, and its peak is certified.
- **Health.** The status of each entity at each time, and its text: those of the first case of its
  label that holds, or of its default. An entity with no status lines reads `inactive`, with no text
  (`label` is null). The report does not list an entity with `metadata.internal`.

The engine writes no text for readers: each text in a report comes from the model or the library,
except the messages of the diagnostics.

### The trace

Each step adds one entry ([One moment](#one-moment)):

| Field | Meaning |
| --- | --- |
| `t`, `step` | The time, and the number of the step within its moment. |
| `rule`, `entity`, `label`, `path` | The rule, its entity, its label and the place of the line of the file that it comes from, such as `service/repaired/done`. |
| `basis` | The identity of each record of the outcome or the rule: its `name`, `kind` and `assumption`, and the claims that it cites. |
| `event`, `outcome` | The outcome's event and its name; for the trigger of a rule with a delay, the rule's own event and no outcome. |
| `changes`, `before` | The values that the step set, and the value of each changed mode before the step. |
| `transfers` | `[from, to, amount]`, with the amounts that moved. |
| `fires` | The rules that the step named. |
| `semantic` | True for the steps that the story tells: the entries with a label. |

The trajectory also keeps each entry's step number across the run (`layers`), the state after each
step, and the flows that delivered material (`moved`): each flow whose rate at the middle of a
segment, after capacities, couplings and bounds, is above zero.

## The evidence trail

`evidence_trail(rs, trajectory, library, units, left_out)` gives, for each outcome, the parts that it
can depend on and the parts of them that the run exercised.

- **Parts.** Every input, quantity, formula, label, flow, mode and rule is a part, with its records
  (`basis`). So is every outcome, with the records of its output.
- **Dependencies.** An outcome depends on the parts that its expression and the delays of its lag
  name, and on what those parts depend on. A quantity depends on its initial value, its bounds, its
  rate, the flows that move it and the rules that set or move it. A formula or a label depends on what
  it reads. A flow depends on what limits what it delivers: its rate, its source stock, its destination
  when the destination has a maximum, its allocation group's capacity, and the other flows of a
  transaction that moves together. A mode depends on the rules whose steps set it. An outcome that another
  outcome's expression names depends on what its own expression and lag name, so an output that reads
  other outputs carries their evidence.
- **What a rule reads.** A rule depends on its `when`, its delay, the chances of its outcomes, the
  expressions of its sets and the amounts of its transfers. An event's count or time that a rule reads is a read of the
  rules that add the event; a mode's entry time is a read of the mode.
- **Rules that cannot fire.** A named state takes its start value and every value that a rule that can
  fire gives it. A rule can fire unless a condition of its trigger that it needs asks a named state
  for a value that the state never takes. Every other condition counts as possible, so the set of rules that can fire is never too
  small.
- **Exercised and possible.** The run exercised each part that the outcome reaches without passing
  through a rule that cannot fire, except a rule that did not fire and a flow that delivered no
  material (`moved`): a flow that is asked to move but gets nothing from an empty stock, a limit or a
  transaction that runs short moves nothing. An input that kept a rule or a flow idle is exercised: it
  decided that nothing happened. Every other part that the outcome depends on is possible.
- **Parts that the run's structure left out.** `run_evidence` reads the run's resolved structure with
  the sections of its whole structure (`model.whole[starts]`), and gives the parts that the structure
  left out (`model.left_out[starts]`). The run exercised nothing through such a part: each rule that
  it left out cannot fire, and the flows that moved material are among the run's own flows. So the
  evidence of a part left out shows as possible, not exercised
  ([python-api.md](python-api.md#the-parts-that-cannot-act)).
- **Records.** The trail gives the digest of the library and the digest of each claim and assumption
  that the records of its parts cite.

## The study

`evaluate_study(model, edits=None, numerical_settings=None, *, runs=None, play=None)` checks one edit
document as one transaction and runs the study's runs ([python-api.md](python-api.md#studies)):

1. It checks the document and resolves every run, or the named `runs`: their values, the blocking
   input checks and the proofs of each run's structure. One failure rejects the study, and no run
   starts. With `play`, it then checks the play request ([Play](#play)).
2. For each run, it reports the input checks that warn.
3. It simulates each run that no blocking check stops, after the checks of every run. When a caller
   turns on the run store ([The run store](#the-run-store)), a run that the store holds is read, not
   simulated again, and helper processes can simulate the runs that it does not hold.
4. It checks each simulated run with one function, `run_checks(rs, trajectory, library, run)`,
   which a sample of a Monte Carlo study uses too: the diagnostics of the simulation; when the model
   has a start, the first entry of the trace that the story tells must be the start's firing, at
   t = 0 (`initiation`); and, when neither has an error, every outcome at time zero and at the end
   of the run must be reportable. It reads a run that paused at a decision up to its pause.

The study is admissible when no diagnostic is an error. A model, expression, numerical or reporting
failure is an error: an outcome is never estimated from a run that failed. A rejected study gives no
run. `sample_result(study, times)` gives the report of an admissible study: for each run, its samples,
its reporting points, its trace, the health of its entities, its evidence trail, its numerical
diagnostics and its peaks. A `Session` runs the same checks, in the same order, for its one run.

## Monte Carlo studies

```python
import napkin
from napkin.engine import SamplingSettings

model = napkin.load_scenario('examples/piano_tuners/model.scn')
result = napkin.evaluate_uncertainty(model, None, SamplingSettings(samples=200, seed=0, method='random'))
report = napkin.uncertainty_report(result, [4380])  # the report of the study, with `uncertainty`
```

A Monte Carlo study runs the same deterministic engine many times. A run's values can hold
distributions ([language.md](language.md#24-fields)):

1. **The central study.** `evaluate_study` runs each run with each distribution at its central
   value, with every check of a study. One failure rejects the study.
2. **The draws.** Each sample of each run with uncertain values draws every uncertain value once,
   before the run; a run whose events go by chance (an event with two outcomes or more, or one that
   draws a distribution when it fires) is sampled too, at its central values, so that its chances and
   draws vary by sample. A value is drawn as the quantile of a uniform number in (0, 1) (`engine/sampling.py`). Each value
   has a stream of numbers of its own, named by the input and seeded by the study's seed: sample k
   does not depend on the number of samples, adding or removing an uncertain value never changes the
   draws of the others, and every run of the study reads the same numbers, so two runs compare
   sample by sample. `latin` sampling puts one sample in each of N equal strata of each value.
   `sobol` sampling takes the numbers from scrambled Sobol' points, in independent blocks
   ([Sobol' points](#sobol-points)). A distribution that reads other values reads their draws in
   the same sample.
3. **The resolution.** Every sample resolves through `Model.resolve`, with the checks of any run,
   before any sample runs. A sample that fails rejects the study; its diagnostics name the run, the
   sample, the seed and the drawn values (`sample`, `seed`, `drawn`).
4. **The runs.** The engine runs each sample. A sample whose run fails rejects the study too. No
   sample is left out, because leaving one out biases the results, and a rejected study keeps no
   sample.
5. **The summaries.** For each outcome at each report point, `uncertainty_report` gives the central
   run's value, the mean, the standard deviation and its standard error, the minimum and maximum, and
   the 5th, 25th, 50th, 75th and 95th percentiles (Hyndman and Fan type 7). The standard error is
   that of independent samples; with `sobol` sampling it is that of the means of the blocks. A
   summary is estimated
   only when the outcome is estimated in the central run and in every sample; otherwise it has no
   value, never zero, and gives the statuses that it met. Each summary gives the rank correlation
   (Spearman) of each uncertain input with the outcome: the drivers. Each outcome names the uncertain
   inputs that it can depend on; one that depends on none has the central value in every sample.
   With reporting times, `uncertainty_report(result, times)` also gives each outcome's `series`: its
   percentiles at each of those times, for the bands of a chart.

**The samples in other processes.** `evaluate_uncertainty(model, edits, settings, runs=…,
times=…, check_samples=…, run_samples=…)` gives the samples to the caller after the central study
and the draws. `check_samples(tasks)` gets `[(run, k, values)]` and gives back the diagnostics of each
sample's resolution in order, as `check_sample(model, run, values)` gives them; when none fails,
`run_samples(tasks)` gets `[(run, k, values, times, luck)]` and gives back the result of each in
order, as `run_sample(model, run, values, None, times, luck)` gives it: its rows, its failures and
`events`, the outcome that each firing of an event with several outcomes took. `luck` is `{seed,
sample}`, the streams of the sample's outcomes. The caller can do this work in other processes, and
stop the study with `StudyCancelled`. `times` can be a function
of the admitted central study, such as the times of its charts; each sample then gives its outcome
rows at those times only, which cross a process boundary as JSON, and the summaries are the ones of
the same study in one process, bit for bit. `napkin/spread.py` runs the samples in this way,
in a pool of processes ([The spread](#the-spread)).

N admitted samples are not a proof for every draw: a value that no sample draws can still fail, as
the points that `analyze_bounds` checks are not a proof for the whole range. The spread of a result
is the spread of the inputs that the scenario assumes, carried through the model; it is not a
measured interval. The sampling settings are part of the report, not of the model's identity.

## Estimators

A Monte Carlo study gives the mean of an outcome with the error of independent samples. The
functions of this section are other estimators. A caller asks for each by name, and no study uses
one unless it is asked. Each estimator is a claim of its own: it says what it assumes, and it gives
the interval that belongs to it. `napkin/engine/estimators.py` has the mathematics, on plain
numbers; `napkin/engine/expectations.py` runs the model ([python-api.md](python-api.md#estimators)).

### Sobol' points

`SamplingSettings(samples, seed, 'sobol', replicates=8)` draws the uncertain values from scrambled
Sobol' points (`scipy.stats.qmc.Sobol`). The points of one block fill the space of the inputs more
evenly than random numbers do, so the mean of a result that is smooth in its inputs has a smaller
error.

- A study has `replicates` blocks (8 by default), each of a power of two of points, so the samples
  are 8, 16, 32, … for 8 blocks. Each block has a scramble of its own, from the seed and the number
  of the block.
- The points of one block are not independent. The blocks are. So the standard error of a mean is
  that of the means of the blocks (`estimators.replicate_interval`), and `uncertainty_report` gives
  that number as the standard error of each summary. The percentiles are those of all samples.
- Each input has one dimension of the points for good: its place among the inputs of the model. To
  make another input uncertain changes no number of this one. Sample k depends on the size of a
  block.
- The points are for the draws at the start of a run. The outcomes of the events and the values
  that an event draws keep their own streams, as with `latin`.

### The interval of a quantile, and a rule to stop

- `estimators.quantile_interval(values, p, confidence)` gives two of the sorted samples between
  which the quantile `p` is with at least that confidence. It holds for every continuous
  distribution, because the number of samples below the quantile is binomial. The function gives
  the ranks and the coverage that the binomial sum gives; with too few samples it gives nothing.
- `estimators.until_narrow(sample, p, width, confidence)` makes a study larger until that interval
  is narrow enough. It looks at 64, 128, 256, … samples. A rule that looks many times and stops
  when it likes what it sees would make an interval too narrow. So look number j uses the
  confidence `1 - alpha / 2^(j + 1)`: all looks together spend less than `alpha`, and the interval
  that the rule stops with has at least the confidence that was asked.

### The outcomes of a run, given

A run takes `outcomes`: the place of the outcome of each firing that goes by chance, in the order
of the run (`timeline.Run(outcomes=…)`, `run_sample(…, outcomes=…)`). Such a firing takes the
given outcome and draws nothing; a firing after the last given place takes its likeliest outcome.
The run keeps each such firing (`Result.firings`): the event, the chance with which a sample takes
each outcome, the place that it took, and, in a run with directions, the derivative of each chance.
A given outcome that no sample takes (its chance is 0) is an error. A value that an event draws
still comes from the stream of the sample.

`estimators.every_path(run)` runs every path of the outcomes in this way. A run with the places `p`
has one child for each later firing and each other outcome with a chance. Each path is run once,
its weight is the product of the chances of its outcomes, and the weights add up to 1. The paths
grow fast with the number of firings: more than the limit (4,096 by default) stops the work before
the limit is passed. Each path is a run from the start.

### Weighted outcomes

`expectations.weighted(model, run, edits, settings)` gives the mean of each outcome at the horizon
with the outcomes of the events weighted and not drawn. For each sample of the uncertain values
(the samples of a Monte Carlo study with the same settings), it runs every path and adds the paths
with their weights: the exact mean over the outcomes, given the values of the sample. The estimate
is the mean of those sums, with the interval of the sampling method.

- The error that is left is that of the uncertain values and of the values that the events draw.
  The part of the variance that the outcomes make is gone.
- A run with no uncertain value and no drawn value has one sample. Its estimate has no sampling
  error (`se` is `None`); the numerical error of the runs stays.
- `sd` is the standard deviation of the outcome itself. The percentiles of the outcome are not
  given: the sums of the samples are means, and their spread is not that of the outcome.
- An outcome that one path does not estimate has no value. A path whose run fails refuses the
  estimate, as a failed sample refuses a study.

### A control

`expectations.controlled(result, run)` gives the mean of each outcome of a finished Monte Carlo
study with a control. The control of a sample is the linear form of the uncertain inputs at the
central run, `c = sum g (x - x0)`: `g` is the derivative of the outcome by each input there
([Tables and tiers](#tables-and-tiers), "Derivatives"), and `x0` the central values. The mean of
`c` is known from the distributions (`expectations.mean_of`: the integral of the quantile
function). The estimate is the mean of `y - (c - E[c])`.

- It has no bias, whatever `g` is and however far the outcome is from a line. Its error is that of
  what the line does not explain: small for an outcome that is near a line over the range of its
  inputs, and larger than that of the plain mean for an outcome that is far from one. The result
  has the plain mean and its interval beside it.
- An input has no part in the control when its values are no numbers, when its distribution reads
  other values, or when the engine gives no derivative by it. `left_out` names each with its
  reason. The engine gives no derivative through the general tier, so there the caller gives the
  coefficients (`coefficients`): any numbers that do not come from the samples keep the estimate
  without bias, such as the differences of two runs.
- With `sobol` sampling each interval is that of the blocks.

### The derivative of an expectation

`expectations.derivatives(model, run, inputs, edits, settings)` gives the derivative of the mean of
each outcome at the horizon by each input.

The mean of the derivatives of the samples is the derivative of the mean only where the outcome of
a sample is continuous in the input. Take a uniform number U from 0 to 1 and the outcome
`1 if U < x else 0`. Its mean is x, so the derivative of the mean is 1. But each sample has the
derivative 0, because no sample has U = x. What the mean of the derivatives misses is the part of
the samples that crosses the edge when x moves. Such an edge needs no chance event: a condition on
a drawn value, an event that comes into the horizon, and a chance that reads the input all make
one.

So each pair of an outcome and an input has a **label**, which follows from the structure of the
model (`expectations.labels`, on the graph of influence):

| Label | What it says | The estimate |
| --- | --- | --- |
| `zero by the structure` | No read leads from the input to the outcome, and no distribution of an uncertain value that reaches the outcome reads the input. | 0. |
| `sample mean` | With the outcomes of the events given, the outcome is continuous in the input: on each way from the input to the outcome there is no event that the input can move or stop, no comparison that it can change, and no store that can rest on its bound. `min`, `max`, `clip` and `abs` have a bend and no jump, and they are allowed. No chance that reaches the outcome reads the input. | The mean of the derivatives of the samples. |
| `branch weighting` | As above, but the input changes the chance of an outcome of an event that reaches the outcome. | Every path of the outcomes is run. A path gives the derivative of its value times its weight, and the derivative of its weight times its value. |
| `unsupported` | One of the conditions fails. `why` has each reason. | None. |

- A sample mean is never given without its label, and a pair that is `unsupported` has no value:
  above all not the mean of the derivatives of the samples.
- The outcomes of the events are weighted in every case (`every_path`), so the estimate has the
  error of the uncertain values only. With no uncertain value it has no sampling error.
- For this question the graph of influence is finer than for a single run
  (`Influence(plan, paths=True)`): the value of a `set` or of a move changes what a step writes
  and not when the step happens, and the chance of an outcome decides nothing when the outcomes
  are given.
- These are also `unsupported`: an input that is uncertain itself; an input that the draw of an
  uncertain value follows, because its distribution reads the input or reads a value that does
  (a sample holds its draw, so its derivative misses that way); a
  chance that the input changes and that is 0 or 1 (a change of the input opens a path that has no
  weight now); a run through which the engine carries no derivative (the general tier, a drawn
  value, a value of the past); and a run that meets a change of kind that the structure did not
  show.
- `one_sided` says that a sample sat on a bend: there the value is the derivative of one side.

Not built: an estimator for a distribution whose arguments read the input (a score function, or
the derivative of the quantile function), and an estimator for an edge that an event or a
comparison makes. Such a pair is `unsupported`.

### The derivative of a tail

With `exceed={outcome: value}` and `quantiles={outcome: p}`, `expectations.derivatives` also gives
the derivative of the chance that the outcome is above a value, and of a quantile of the outcome
(`estimators.tail_slopes`), for each pair that has an estimate.

- The distribution of the outcome changes in two ways. The paths whose weight changes give a mean
  like any other. The paths whose value moves pass a given value at the rate of the density of the
  outcome there, and the density is not known: a normal kernel estimates it, with the width
  `1.06 sd n^(-1/5)`.
- So where a value moves, and for every quantile, the estimate is **slower** (`slower` is true):
  its bias falls with the square of the width, and its error falls as `n^(-2/5)` and not as
  `n^(-1/2)`. The interval is that of the samples at this width; for a quantile it has the error
  of the quantile of the samples too. It does not hold the bias.
- Where only weights change, the derivative of the chance to pass a value has no bias and the
  error of a mean (`slower` is false).
- They need independent samples (`random` sampling), and a density: an outcome with one sample, or
  whose values are all the same, has none.

## The edit document

An edit document gives the inputs of a model's runs other values, as one transaction. It follows
`napkin/schema/edits.schema.json`. `napkin run`, `napkin play` and `napkin sample` read one with
`--edits FILE`, and each `--set NAME=VALUE` goes into its `set` ([cli.md](cli.md)). In Python,
`evaluate_study`, `evaluate_uncertainty` and `Session` take it as `edits`
([python-api.md](python-api.md#studies)). This document is for the catalogue's Juneau model
(`water_controls_wipe:juneau`):

```json
{
  "schema_version": "0.0.1",
  "model_hash": "<the model_hash of the model>",
  "reason": "Slower removal of the credential, and more emergency water for each person",
  "set": {"relief.ration": 2},
  "options": {"Delayed response": {"responders.removal_time": "pert(120 h, 240 h, 480 h)"}},
  "runs": {"delayed_kept_human": {"attacker.reaction_time": 72}}
}
```

- `schema_version` is `0.0.1`: `napkin.SCHEMA_VERSION`. The schema accepts no other version.
- `model_hash` names the revision of the model. The engine refuses a document for another revision
  (`model_hash`). The commands fill in each of the two keys that a file leaves out, from the model.
  A key that the file gives stays as it is, so the engine refuses a file for another revision.
- `reason` is an optional text that says why. The engine does not read it.

A value is a number in the unit of the input, true or false for a bool input, a name for a named
input, or a distribution written as in the file, with its units (`"pert(120 h, 240 h, 480 h)"`). A
study runs a distribution at its central value, and a Monte Carlo study draws it. An edit is for
every run (`set`), for one option (`options`), or for one run (`runs`), and the narrower edit wins:
one run, then one option, then every run. Every edit wins over the value that an option gives, and
that value wins over the input's own value. Two edits of one input by two options that meet in one run
are an error, because neither is narrower. `model/runs.py` checks the document as one transaction
over the declared runs. An edit of an option that no run names changes no run.

A combination of options that no run makes is checked only when a caller asks for it:
`model.combination(run, options)` puts each option into the run in place of the run's option of
its group, checks the combination as the build checks a run, and gives a model whose one run is the
combination, under the run's name. The same edits apply to it: those of every run, of each of its
options and of the run. A combination whose start-state options start no run of the model is a
diagnostic (`combination`). `--option` and a `Session` with `options` check the whole document on the
model first, in every run that the model admits, and then give the combination the edits that reach
its run.

A saved document depends on the model's identity only. So a change to the engine's code that keeps
the language's version keeps the document valid. A change to a record changes the identity of each
model that reaches the record, and of no other model. A change to `style.toml` or `brief.toml` keeps
every document valid, because the model hash does not cover them. The catalogue's spreads are
documents of this kind, in the `spreads/` folders of its packages and variants
([catalogue.md](../scenarios/docs/catalogue.md)).

## The spread

`napkin sample` runs a Monte Carlo study of one run and prints the spread of each outcome
([cli.md](cli.md)). The work is the engine's ([Monte Carlo studies](#monte-carlo-studies)), in a pool
of processes (`napkin/spread.py`):

- **The runs.** It samples the run with the runs that it is compared with: the run that its `versus`
  names, and each run whose `versus` names it. All of them read the same draws, so two runs compare
  sample by sample. With `--option`, it samples the combination (`model.combination`), which has no
  comparison: each run with the options takes a spread of its own, and with the same seed the spreads
  draw the same values.
- **The draws.** It draws each input that has a distribution, in the model or in the edit document,
  with `--samples` samples (200 by default), from `--seed` (0 by default), with the method `random`.
  A model whose runs have no input with a distribution has no spread, and the command says so.
- **The pool.** `--jobs` processes (by default the number of processors, and never more than the
  samples) do the work in two phases. Each process builds the model once. First the pool checks each
  sample, with the checks of any run: a sample that fails rejects the spread before any sample runs,
  and its diagnostics have `sample` (from 0), `seed` and `drawn`. Then it runs the samples. A sample
  whose run fails rejects the spread too. The result is the one of the same study in one process, bit
  for bit. With one job, the samples run in the command's own process.
- **The cost.** A spread takes about the samples times the runs, times the time of one run, shared
  among the processes. The 200 samples of `examples/piano_tuners` take a few seconds. In the
  catalogue, 20 samples of the runs `delayed_kept` and `delayed_kept_human` of
  `water_controls_wipe:washington_dc`, with its spread document, took 9.5 minutes of processor time:
  about 13 seconds a run.

For each outcome, `napkin sample` prints the engine's summary at the end of the run, or at `--at`:
the mean, the middle 50% (p25 to p75), the middle 90% (p5 to p95) and the inputs that move it most.
It adds the 1-in-100 value (p99) from 1000 samples, and the 1-in-200 value (p99.5) from 2000 samples,
type-7 quantiles of the samples. `--exceed NAME=VALUE` adds the share of the samples above the value.

The report of a Monte Carlo study (`uncertainty_report`) is the report of its central study with an
`uncertainty` section:

| Key | What it holds |
| --- | --- |
| `settings` | `{samples, seed, method}`. |
| `runs` | `{run: …}`: each run of the study that has uncertain values or events by chance. A rejected study has none. |

| Key of a run | What it holds |
| --- | --- |
| `samples` | The number of samples. |
| `events` | `{event: {outcome: count}}`: how many times each outcome of an event that goes by chance happened, over the samples. |
| `inputs` | `{input: {distribution, draws}}`: the distribution as written, and the value of each sample. |
| `outcomes` | `{outcome: {uncertain_inputs, points, series}}`: the uncertain inputs that the outcome can depend on; its summary at each report point (`central`, `mean`, `sd`, `sem`, `min`, `max`, `p5` to `p95` and `drivers`, or `estimated: false` with the `statuses` that it met); and, with reporting times, its percentiles at each of them (`series`). |

`drivers` gives the rank correlation (Spearman) of each uncertain input that the outcome can depend
on with the outcome: null when the input or the outcome takes one value only. The spread is the
spread of the inputs that the model assumes, carried through the model: it is not a measured
interval.

## Play

A person or a program can play the actors of a run ([language.md §2.7](language.md#27-actors)): they
pick the outcomes of the actors' decisions in place of the model. `napkin.actors(model)` lists the
actors and their choices ([python-api.md](python-api.md#views)). There are three ways to give the
picks, and they give the same run, bit for bit:

- `napkin play`, at the terminal, or with `--json` for a program that reads each decision and writes
  each pick ([cli.md](cli.md));
- a `Session` in Python, live with a resolver or step by step ([python-api.md](python-api.md#session));
- `evaluate_study(model, runs=[run], play=…)` with a log.

A play request names the run, who controls what, and the log:

```json
{"run": "base", "control": {"operator": "reader"}, "picks": [{"event": "operator.decide", "outcome": "wait"}]}
```

- `control` gives a method to actors and to their choices (events marked `choice`): `chance` (the
  model's chances), `reader` (a person) or `agent` (an AI agent). A key is an actor (all its choices),
  a set of copies, or one choice, `actor.event` (or the event of a set of copies). A choice's own key
  comes before its actor's, and chance takes every choice that nothing names. A key that names
  neither an actor nor a choice of the run is refused (`play`).
- `picks` is the log so far: `[{event, outcome, t, by, reason}]`. The calculation reads `event` and
  `outcome` only; the log keeps when, by whom and why.

Each decision of a played actor takes the next pick of the log, in order ([The step](#the-step)). A
pick must answer that decision with an outcome that can happen, or the study is rejected with the code
`pick`. At the first decision with no pick left, a study takes the model's choice and goes on: the
decision is the study's `decision`. A `Session` stops there instead, and waits for a pick. The engine
keeps no paused run. To go on after a pause, a session simulates the run again from t = 0 with the
longer log, and the same log gives the same run, bit for bit. In the report, the trace entry of each
outcome that a pick took has `picked: "reader"` (or `"agent"`).

A decision that waits for a pick, as `Session.advance()` gives it for `examples/reservoir`:

```json
{
  "t": 40.00000000000081, "thing": "operator", "event": "operator.decide",
  "text": "The water reaches the level at which the operator opens the spillway.",
  "outcomes": [{"name": "open", "text": "The operator opens the spillway.", "available": true},
               {"name": "wait", "text": "The operator waits, and the spillway stays closed.", "available": true}],
  "view": {"reservoir.water": 0.7},
  "units": {"reservoir.water": "fraction"},
  "seen": [],
  "pick": 0, "by": "reader"
}
```

- `t` is the time of the decision, in hours, `thing` the actor, `event` the choice, and `text` the
  choice's text.
- An outcome can happen (`available`) unless its `when` condition does not hold
  ([language.md](language.md), §2.8). Its chance is the model's estimate of what the actor does: a
  pick replaces it.
- `view` has each fact of the actor's `sees`, and no other: a field's value, a number in the field's
  own unit (`units` names it), or the number of times an event has happened.
- `seen` lists the times that the events among the facts happened, in order: `{t, event, text}`.
- `pick` counts the picks before this decision, and `by` says who picks it.

`napkin play --json` writes the same fields in each decision line, with `type` and
`schema_version`. `--save FILE` writes the play log, and `--picks FILE` goes on from a saved log
([cli.md](cli.md)). The play log holds the context of the play: the hashes of the model and of the
engine, the run, the options, the control, the edits and the numerical settings. A log goes on only in
the same context, so it replays exactly ([python-api.md](python-api.md#session)).

## When a run stops

| Code | Cause |
| --- | --- |
| `transaction_failed` | A step's transfer does not fit. |
| `chances` | The chances of a firing's outcomes are not each from 0 to 1, or do not add up to 1 within 1e-9. |
| `delay` | A rule's delay is not a finite time from 0. |
| `step_budget` | A moment takes more than `max_steps` steps. |
| `joint_feasibility` | A step leaves a quantity outside its bounds. |
| `check_failed` | A check on the state fails. |
| `partition_failed` | The parts of a sum check do not add up to its total. |

A run also stops when a quantity leaves its bounds, a value is not finite, an expression cannot be
evaluated, a flow rate, a transfer amount or an allocation capacity is negative, a tally falls, the
evaluation or event budget runs out, or the solver fails. Each of these failures makes the run
invalid, and the study that holds it is rejected.

## Tables and tiers

The engine is `napkin/engine/timeline/`. `simulate` gives it the flat structure of a run, in which
each row of a table is written out as an instance: the whole model is then one part, and the
sections above say what the engine does with it. The engine also reads the hybrid core of a model
([compiler.md](compiler.md)), which does not write the rows out: `timeline.run(Plan.of(core))`.
`napkin run` reads the hybrid core of a model with a table
([cli.md](cli.md#a-model-with-a-table)), and `napkin derivatives` reads the hybrid core of every
model. `evaluate_study` and the other functions of the public API
([python-api.md](python-api.md#studies)) use the flat structure. This section says how the engine
runs the rows of a table from the hybrid core.

**Two tiers.** The things that no table makes are one space of one instance, and each family of a
table is a space with one instance for each row. A space is in one of two tiers.

- The *general tier* gives each instance of the space to the continuous engine
  ([Between moments: the solver](#between-moments-the-solver)): the allocated field, the bounds and
  the stock faces, the exact segments and the numerical segment. The things outside the tables are
  in this tier, and so is the one space of a flat structure. The instance makes its segments one
  after the other between two moments that write something that it reads. The end of each segment
  is a moment for the rules and the checks that read the instance, and the time at which a crossing
  that a rule watches reaches its value is the time of that rule.
- The *fast tier* holds the quantities of all instances of the space as arrays, as the next
  paragraphs say. A family is in this tier. A family with a part that this tier does not run (flows
  that move by one fraction of which one is of an allocation group; a ring of stocks that can rest
  on a bound) is in the general tier. When a run in the fast tier meets a state that the tier does
  not run (a quantity at a bound that is no stock resting on zero; a flow that would ask a rate
  below zero), the run is made again with that family in the general tier: the tier of a run
  follows from its own values alone. A run that carries derivatives has the things outside the
  tables in the fast tier, because the general tier carries none; such a run is not made again, and
  the state that the fast tier does not run stops it by name.

In both tiers the size of a quantity, which sets its tolerance, and the longest step of a numerical
segment are those of [Between moments: the solver](#between-moments-the-solver).

**A plan for each structure.** `Plan.of(core)` makes, once, what follows from the structure alone:
each expression as one node, each list over the instances of a family as one part that keeps its
value, what each quantity is between two moments, the kind of each rule, and the readers of each
name. Each run of the structure reads the plan: each sample of a batch, each edit of a number.
`simulate` keeps the plans of the last flat structures that it ran.

**What a quantity is between two moments, in the fast tier.**

- A value that only a step changes.
- A line: its rate reads nothing that moves, so it is `y0 + rate * (t - t0)`, exactly.
- A member of a block: quantities whose rates read one another. The instances of a block that read
  no other instance are each a problem of its own. A block whose rates are linear, with factors that
  only steps change, has a closed form (the exponential of its matrix). The engine takes it when no
  state can leave its bounds without the timeline knowing, and when no flow of the block can ask a
  rate below zero while each quantity is within its bounds. Any other block goes to a solver through
  an adapter (`napkin/engine/solvers.py`), and it is integrated only as far as a reader asks. A
  step of the solver can be longer than the step cap
  ([Between moments: the solver](#between-moments-the-solver), "Steps"). The engine reads the
  solution at the end of each step, and at each whole cap inside a longer step. Each of these
  states is a state of the run when a reader comes to it: its bounds and the signs of its flows
  are checked then. A step can end far after the time that a reader asks for, and an event before
  its end starts the block again: the states of the step after that event are no states of the
  run, and are not checked.

**After a step.** Only the parts that read what the step wrote are brought up to date: those rules
are read again, and those lines and blocks start again from the moment. So a step of one instance
costs nothing for the other instances.

**The two readings of the rules.** `timeline.run(plan, reading='every')` reads every rule at every
moment and after every step, and has a crossing due inside its tolerance band at any moment, as the
engine before this one did. `timeline.check` makes a run with each reading and gives the differences
of their traces. They differ in two cases only
([When a crossing is due](#when-a-crossing-is-due)): a crossing whose quantity is inside its band at
a moment of another rule, which the reading of every rule fires there (a shift of at most the time
that the quantity takes to cross its band); and a crossing whose own time is within 1e-8 h after a
moment while its quantity is outside its band, to which that reading gives a moment of its own (a
shift of less than 1e-8 h).

**A played run.** `timeline.run(plan, play={'control': …, 'picks': …}, pause_at_decision=…)` is the
played run of [Play](#play), with `decision_events`, `settled_decisions` and `decision_resolver` as
`simulate` takes them. The result has the decision, whether the run stopped there, the time to which
it went, and each step of the trace (`entries`). A resolver is asked once for each decision, also
when the run is made again in the general tier.

**A sum over a list.** A list that only steps change keeps a tree of pairwise sums of a fixed shape.
A change of one member costs log2(n) additions, and the total depends on the present values only.
The order of the additions is not the order of the list; the language promises no order of a sum over
a list.

**Derivatives.** With `directions` (names of inputs), a run carries the derivative of every value by
each input, for one unit of the input as the file writes it. The time of an event has a derivative
too, and a part that starts again at an event takes the jump that the moving time gives. The result
has the derivative of each output at the horizon. It is the derivative on the path of the events of
the run.

**The class of a derivative.** `derivatives.report(plan, values, inputs)` gives each derivative
with its class (`napkin/engine/timeline/derivatives.py`). Each derivative is that of one run, and
the other inputs keep their values: also an uncertain input whose distribution reads this input,
which has its central value in the run. The derivative of a mean over samples is another question
([The derivative of an expectation](#the-derivative-of-an-expectation)).

- **structurally zero.** No read of the plan leads from the input to the output: the graph of
  influence (`timeline/influence.py`) has each read of the engine as an edge: from what a rate, a
  start, a rule or an output reads (also through the members of a list) to what it gives, from a
  rule to what its steps write, and from a stock to what its flows deliver when it rests on its
  bound. The derivative is 0 for every value. A derivative that the run finds to be
  other than 0 for such a pair stops the report: the graph would lack a read.
- **smooth.** The run met nothing of the kinds below for this input and this output.
- **one-sided.** The run met a place where a small change of the input changes the path, and the
  value is the derivative on the side of the path of the run. The run notes (`Run.note`):
  - two pieces of an expression that meet (`timeline/smooth.py`: the two sides of a comparison,
    two arguments of `min` or `max`, the value of `clip` and a limit, the argument of `abs` and
    zero), where the derivative of their difference by the input is not zero. The engine looks at
    each state of the run at which it makes a tangent: a start, a step, the rate of a line that
    starts again, an output at the horizon, and, for a block that a solver integrates, each
    state at which it reads the solution (so a state that comes to the edge of a piece and stays
    within the tolerance of it is seen);
  - the same in the condition of a rule that is read at a moment;
  - two steps of one moment whose times move apart with the input: the file decides their order
    here, and a small change puts one before the other;
  - two clocks of one rule at one time, with different derivatives;
  - a value that a step sets within the tolerance of its bound, which is taken as the bound;
  - two outcomes of a firing with one chance, where the input moves the two chances apart (the
    central run takes the first of the file).

  A tie that no input can break is no note: a stock that a step emptied compared with zero, two
  values that the input does not move. The class is the safe one: a tie that holds at one time
  only, through which the value passes, leaves the derivative of both sides the same.
- **undefined.** The time of a crossing is not decided by its value, and the input moves the
  value or the mark there: the value has no rate at its mark, or it is within its tolerance of
  the mark for a step cap or longer (the tolerance over the rate). That is the crossing of a
  value that comes near its mark and never passes it. A derivative that is no finite number is
  undefined too. No value is given.
- **unsupported.** The engine carries no derivative through a part of the run, and names it
  (below, "What the engine names as outside"). No value is given; the pairs that are zero by the
  structure keep their zeros. A rate of a numeric block that jumps at a time that the input moves
  is such a part (`Run.jumps`): a comparison in the rate (`x if a < b else y`, a flow with
  `while`) whose two sides change their order between two readings of the block, where the
  derivative of their difference by the input is not zero. The tangents of the block are those of
  each side of the jump, and carry no term for the jump itself: `1 if t < x h else 0` an hour
  fills `x` until `t = x h`, whose derivative by `x` is 1, and the tangents give 0. A jump at a
  time that no input moves, and a kink of `min`, `max`, `clip` or `abs`, change no derivative.

The result of a run with directions has the notes and three margins: the longest time in which a
crossing is decided only within the tolerance of its value, the least time between two moments
with a step, and the least distance between the two likeliest outcomes of a firing.

**The budgets.** `max_steps` counts the steps of one moment. `max_events` counts the events of a run
for each instance of the largest table: the limit is `max_events` times that number of instances.
`max_evaluations` counts the evaluations of the rates of one instance of a space in the general
tier over the run, and of one block of the fast tier between two moments that start it again.

**The checks of the inputs.** The model of the representatives has each check of the inputs for
one row of each class. A run from the hybrid core reads them for every row when it starts, and is
refused (`ModelError`, with the check of each failing row under its flat name) when a blocking one
fails, as `Model.resolve` refuses a run of a flat structure. `timeline.input_failures` lists them,
warnings included.

**The proofs.** The compiler proves each declared run for every row of each table
([compiler.md](compiler.md#what-is-known-for-every-row-of-a-table)). An input of a class of more
than one row whose distribution reads a column has no value of its own for each row in the hybrid
core, so the core refuses such a model by the name of the input, and `napkin run` runs it with each
row written out. The plan of a run reads
the facts of that proof: the stocks with a proved zero face, the crossings of a quantity that moves
one way, and the cumulative outcomes. A run that is given values (`timeline.run(plan, values)`, each
sample of a batch) has values that nothing proved. Before it starts, it checks each given value
against the range of its input and makes the proofs again over the rows with those values. A
failure refuses the run (`ModelError`), and so does a proof that gives other facts than those of
the plan. That costs one pass over the model of the representatives for each such run, whatever the
number of rows; a run with no values costs nothing more.

**A bound that is an expression.** A quantity of a table can have a bound that reads inputs
(`in 0 to cap`). The plan holds the number that the values of its own run give
(`Plan.of(core, run, values)`). A run that gives one of those inputs another value would have
another bound than its plan: it is refused, and the message names the input. The rows of one
class have one bound, so a bound that reads a column of the table is refused when the model
compiles.

**The checks of the state.** In the general tier a check that reads a quantity of an instance is
read at the end of each segment, at each state that a solver accepts, and at the horizon. In the
fast tier a check is read at the moments that write what it reads, and at the horizon. The compiler
admits a check on a value that moves only with a proof that it holds, so a model that it admits has
no check that fails between two such readings.

**The reports of a run of a table.** A report of a flat structure reads a trajectory, which holds
every quantity at every time. A run of a table has none; `napkin/engine/timeline/reports.py` gives
the rows from the result of the run.

- `reports.outputs(result, times)` gives the rows of
  [Outcomes and reports](#outcomes-and-reports): the value of each output in its own unit and its
  status at each time, with the lag of each output. The run must keep the record of its past
  (`timeline.run(plan, record=True)`): a value at a time is read from that record. `Result.outputs`
  is another thing: the expression of each output at the horizon, with no lag.
- `reports.evidence(result)` gives the evidence trail of [The evidence trail](#the-evidence-trail)
  over the parts of the model of the representatives: one name for the rows of a class. A rule of a
  class fired when it fired for one of its rows, and a flow of a class moved material when it did
  for one of its rows.
- **When a flow moved material.** In the general tier, as in a flat structure: its delivered rate
  is above zero at the middle of a segment. In the fast tier the engine looks where it reads the
  rates: at the start of each segment of the quantities of the flow, at each state that a solver
  accepts, and at the end of the run. A flow that is at zero at all of these counts as not moved.

- `reports.report_of(result, times, rows)` gives the report of the run, with the parts of the report
  of a run of a study ([python-api.md](python-api.md)). A table can have very many rows, so what the
  report says of the things of a table is by group. A group is one class of rows: the rows that the
  engine runs as one family.
  - `groups`: each group with its table, the number of its rows, and the least and the greatest
    value of each input over its rows.
  - `health`: at each time, for each group, how many of its rows are in each status and in each
    value of each named state, with the text of each status (`groups`); and the health of each thing
    outside a table and of each row that `rows` names (`entities`).
  - `events`: for each group, each event and each outcome: how many times it happened, in how many
    rows, and the first and the last time.
  - `trace`: the steps of the things outside a table and of the rows that `rows` names.
  - `samples`, `reporting_points`, `peaks`, `evidence`, `outcomes`: as in the report of a study.
    The candidates of a peak are the start, the horizon, each moment of the run, the time just
    before it, and the middle between two moments. An outcome of `proven_cumulative_outcomes` that
    is estimated is read at the horizon only: its peak is there, certified. Each other output is
    read at the candidates. A reading of one time reads every row, and a large table has a moment
    for each event of each row. So when the candidates times the rows of the largest table are more
    than `reports.PEAK_WORK` (1,000,000), the output is read at fewer candidates, evenly spread over
    their order, with the first and the last (`reports.thinned`; 200 at the least). Such a peak has
    `candidates: {read, of}`, the count of the times that were read and of the candidates. Its value
    is the largest that was read; a peak that is not certified is always such a value. The
    expression of an output is written with one member of a list for each group: the name of the
    row that stands for the group.
- `reports.study_of(core, runs, times, rows, settings)` runs the runs of a hybrid core and gives
  their report with the envelope of the report of a study: `napkin run` prints it for a model with a
  table ([cli.md](cli.md#a-model-with-a-table)). Each run has the shape `table_run` of
  `napkin/schema/report.schema.json`. A run that the engine stops rejects the report, and the report
  then has no run.

Not there yet: a study of a table with edits or samples. An output that reads an output with a lag
is named as outside.

**What the engine names as outside.** The engine stops with the name of a part that it does not run
(`timeline.Outside`). From a flat structure no model that the compiler admits has such a part; if
one had, `simulate` would stop the run with that name. From the hybrid core, the parts are these.

- Of the model: start-state options.
- Of a family and its links: a partition with a part that is no quantity, or with a part of another
  family; a link whose rows go into more than one class, or two links into one class; a part that
  reads a value of a family outside a list and outside a link; a list in a part of a family, or a
  member of a list that names two families; a flow, a transfer or an allocation group that joins
  two spaces; a step of a family that writes a value of another family; a condition of an event of
  a family that reads a list.
- Of the general tier: an instance whose rates read a value that moves outside it (a line of
  another space, or a list over a family that moves); flows that move by one fraction and share a
  limit, in a thing whose rates read another instance or another family.
- Of what a run is asked: the whole record of a run (`Result.trajectory`) of a model with a table,
  or with the things outside the tables in the fast tier; the derivative of a played run, of a run
  with a part that only the general tier runs, of a run with a draw or a value of the past, of a `min` or a `max`
  over a list, of the start of a quantity that each row writes, of a flow of an allocation group at
  its limit, and of a run in which a stock comes to rest on its bound.

## The same result again

What the engine promises of a result, and what it does not:

- **The same build, the same computer and the same inputs give the same result, bit for bit.** The
  build is the package, its dependencies and the interpreter. The result does not depend on the
  number of processes of a study, on the samples that run beside a sample, on whether a run is
  read from the run store or made again, or on the order in which a set or a dictionary gives its
  members. Sample k of a study with `random` sampling does not depend on the number of samples.
- **Another computer can give other last digits.** The run store keys a run by the machine and
  the processor for that reason.
- **Another build is judged by classes of difference, not by bits.** A change of the numerical
  core is compared with the build before it by the contract of `CONTRIBUTING.md` ("Comparisons of
  a change of the numerical core"): a difference within the tolerance of its value, a moment whose
  time a root can give and that moved within the tolerance of a time, or a discrete difference
  (another event, another order, another outcome) and a value beyond its tolerance, each of which
  is explained by something that depends on neither build alone. A refactor that changes no
  arithmetic keeps the bits ("Refactor comparisons").
- **Agreement of two builds is no proof of the mathematics.** The tests of correctness are
  independent: closed forms, sums with exact fractions, high precision, properties and
  counterexamples.

## The run store

A simulation (`simulate`) reads only its resolved run, the units of the library, the numerical
settings and, for a played run, what the run asks (`play`: who picks, and the picks). Its result
depends only on these and on the engine code. The run store (`napkin/store.py`) keeps each simulated
run on disk, keyed by:

- the canonical bytes of the resolved run, in its compiled order, of the units, of the settings and
  of what a played run asks;
- a digest of the engine code: each file of the package that `engine/runtime.py` imports, directly or
  through other files of the package, with each parent package's `__init__.py`, and
  `expressions.py` and `distributions.py`;
- the Python, numpy and scipy versions, the machine, the processor and numpy's CPU features.

A change to any of these is a miss: the run is simulated again. A change to the language's front end,
the build, the commands or the publisher simulates nothing again when every resolved run stays the
same. A resolved run names its claims by ID and holds no text, quote or digest of a claim or an
assumption, so an evidence change through `tools.evidence.integrate` that keeps the IDs simulates
nothing either. A simulation
that the store runs gets only the units of the library, so it cannot read an input that its key
leaves out, and a test checks that a simulation calls code only from the files that the key
digests. The store keeps only what `simulate` returns: every check of a study still runs, and a
failed run is never stored.

The store is off until a caller turns it on. These turn it on: `napkin run` (unless `--no-store`),
`napkin play` and `napkin sample`, with the processes of a spread; the tests outside `tests/engine`,
`tests/acceptance` and `tests/model` (the root `conftest.py`); and the maintainer tools' publisher
and comparison, with their worker processes. The engine, language and acceptance unit tests always
simulate, and so does a program that calls the Python API. Processes share the store: each run has a
lock, and a process that needs a run that another process is simulating first simulates the next run
of its study that no process holds, then waits.

A command that runs one study at a time also lets the store start helper processes: `napkin run`,
`napkin play` and `napkin sample` one fewer than the processors, and the publisher `--jobs` processes
in all, its workers and their helpers. When a study needs two or more runs that the store does not hold, the helpers take
them in order through the same locks, beside the process of the study, which simulates too. A run
that fails in a helper is not stored, so the process of the study simulates it again and reports the
failure. The tests start no helpers. A cold study of seven runs of ten seconds each takes about 25
seconds on four processors, where one process takes 70.

The store is in `.cache/runs` of a source checkout, or in `~/.cache/napkin/runs` (under
`XDG_CACHE_HOME` when it is set) for an installed package. `NAPKIN_STORE` names another directory, or
turns the store off with `off`. When the store passes `NAPKIN_STORE_LIMIT` gigabytes (4 by default), the runs used
least recently go. Deleting the store's folder clears it. In a source checkout,
`python -B -m tools.check --all --deep` also simulates three stored runs again and compares each
with the store, bit for bit. The last digits of a result depend on the processor, so a store
serves only the computer that wrote it.
