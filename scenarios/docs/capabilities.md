# What a model can say today

This page tells what the napkin language, version 0.2.3, and its engine can model today, and what
they cannot. The [language reference](../../docs/language/README.md) gives the rules of each line,
and the [engine pages](../../docs/engine/README.md) tell how the engine calculates a run. This page
uses the terms of the language reference ([Terms](../../docs/language/README.md#terms)).

## The parts of a model

A model is a finite, deterministic hybrid system: values that change continuously through flows, and
values that change at moments through events.

| Part | What it models | Example |
| --- | --- | --- |
| Entities, templates and instances | The things of the scenario, and the things of one kind | `lumberton_homes: Households` |
| Tables | The instances of a template, one row each, from a `.csv` file | `sites: Place from "places.csv"`. No model of the catalogue has a table today. |
| Links and collections | A fixed connection to one member, and a group of members with a numeric key | `buys: <Tie>` in `water_controls_wipe` |
| Inputs | A value that a named run or an edit sets before the run. An input can hold a distribution. | `input interval_range = pert(2 h, 4 h, 6 h)` |
| Stored values | A stock, a tally, a Boolean or a member of an enum, which flows, moves and stages change | `controls: enum[INTACT, WIPED, RESTORED] = INTACT` |
| Formulas | A value that the engine calculates from other values each time that it reads it | `capacity = formula(this.people * (1 + 0.2 * ai_tools.progress))` |
| Flows and routes | A transfer per time in one direction (`->`), or in both directions (`<->`) | `flow deliver: SOURCE -> this.completed` |
| Flows with legs | One activity with several transfers, served at one common fraction | `flow dispatch:` of `support` in `water_controls_wipe` |
| Requests, capacities and allocation | The soft rate that a flow asks for, its hard limit, and how an endpoint shares a limit (`priority(…)`, `proportional()`) | `outflow.allocation = priority(this.deliver, this.export, this.sell, this.leak)` |
| Declared solvers | Affine constraints, and objectives in their order of rank, on the rates and values that the solver names | A provider that shares water and electricity in one decision. No model of the catalogue has a solver today. |
| Events, stages and triggers | Activities with stages at times (`after D:`), guards (`after D when C:`), gates (`until C`) and triggers (`when C:`) | `quality_review.notice` |
| Statements of a stage | Assignments, `move`, starts of events, `if` and `switch` | `this.inspection.start(this.hold_duration, this.repeat_work, false)` |
| Occurrences and history | Each start of an event, with its own parameters and locals; `count`, `since`, `elapsed` and `.at(t)` | `count(incident.reported.occurrences) > 0` |
| Draws | A value that `.draw()` takes once from a distribution | `this.interval_range.draw()` |
| Status displays | A rating (`ok`, `degraded`, `failed`, `inactive`) and a text, from the first case that holds | `responders.status` |
| Assertions | A condition that must hold at the start, or wherever it applies during the run | The balance checks of the work of each utility in `water_controls_wipe` |
| Packages | Modules (`use`), variants for each place (`variant`) and `change` lines | The 16 places of `water_controls_wipe` |
| Options and named runs | Groups of input settings, and the runs that take them | `acknowledged_stop = "Standard cooling" + "Calendar inspections" + "Acknowledge the stop order"` |
| Evidence and notes | The `record` declaration behind each value, and the notes of the reviewers | `record lumberton_storage: source "…"` |

## What the engine does with a model

- **One run gives one record.** A run is a median run or a sampled run with a seed. The caller
  selects the paths and the times to read. Any named value is a path that a caller can read.
- **The books balance.** The engine keeps an exact balance for each stock. Each transfer goes equally
  out of one stock and into the other.
- **Each endpoint shares by its own rule.** A declared solver sets only the rates and values that it
  names in `solve_for`. The other flows keep the rules of their endpoints.
- **The engine finds the time of a crossing.** A trigger on a value that changes continuously fires
  at the first contact with its boundary, between the scheduled times. The engine certifies each
  contact. It does not read the value at fixed times.
- **A decision inside the comparison band is a near-tie.** The engine marks it in the trace, and
  `napkin run` lists it.
- **A run can stop at a breakpoint.** At a breakpoint, a caller can read values and edit a stored
  value (`napkin play`). The caller can also save a checkpoint and go on later, also in a new process. A run that stops and goes
  on without an edit gives the same record as a run without a stop.
- **A study is a group of runs.** The named runs of a model, or the samples of a Monte Carlo
  calculation (`napkin sample`, and the spreads of `brief.toml`).
- **The run store keeps each run.** An identical request reads the stored record and does not run
  again.
- **A reporting lag is the choice of the caller.** It needs a proof that the value never falls. A
  window before 0 h gives "Unavailable", with the reason.
- **The same run gives the same result.** With the same code, configuration, seed and thread
  settings on one computer, a run gives the same record again. Other settings, another solver or
  another computer agree within the stated tolerances.
- **A run that cannot answer stops by name.** The failure names the part and the reason. An example
  is a strict threshold on a continuous value (`water < 10 L`), which has no first instant. The size
  of a model does not change its equations. A large model can stop with a named failure of time, memory
  or accuracy.
- **Limits protect a run.** By default, a run stops at one of these limits:
  - 1,000,000 starts of one event (`max_occurrences`);
  - 100,000 occurrences of one event alive at one time (`max_active`);
  - 1,000 rounds at one time (`max_rounds`).

  The budgets of a solver count work, not seconds.

## What the catalogue models today

| Entry | What the model follows | How the model receives the disruption |
| --- | --- | --- |
| `cyber_learning_loop` | One national workforce for 25 years: AI uptake, staff, shared review capacity, learning and defensive AI, in baseline-equivalent staff-years | No disruption. The options set the path of AI progress, funding and the allocation of work. |
| `heat_wave_blackout` | An electricity outage in a heat wave: crews, utility checks, the temperature in homes, cooling places, protection and health | An observed outage at the start. Options add a safety hold, inspections on a calendar or after clearance, and a stop order. |
| `iv_fluid_shortage` | The release and the supply of IV fluid: quality review, reserves of the hospitals, patients and cost | Options supply the records work, the condition of the first lot, and the schedule of quality notices. |
| `water_controls_wipe` (16 places) | A loss of the controls of water systems: crews and parts, stored water, advisories, relief water, hospitals and economic loss | An observed outage at the start. Options add batches of regional support requests at fixed intervals or after recovery. |

No model of the catalogue has an entity for the attacker today. Each model receives its disruption as
inputs and options. [ai-operations.md](ai-operations.md) tells how a model can show an attacker with
fixed rules. [deviations.md](deviations.md) tells how each package differs from the earlier catalogue.

## What a model cannot say

Each item below is refused, or has no form, in this version. The compiler or the engine refuses each
by name, with what to write instead. [changes.md](../../docs/language/changes.md) lists the words of
the old language and what replaced each.

| What a model cannot say | What to write instead |
| --- | --- |
| A part that observes the run and decides during it | Store the decision in a value, and branch on it (`switch`). A caller can stop the run before the branch and edit the value. |
| Who plays a part | `roles.toml` and the `[role]` of `style.toml` ([conventions.md](conventions.md#who-plays-each-part)) |
| What a report shows | Nothing in the model. The caller selects the paths, the times and the lags. |
| A read of a value as it was some time before | An event that waits (`after D:`) and then writes the value |
| A value that stands for "no estimate" | Do not declare the value. Say why in a note (`not_estimated`) or in the evidence. |
| A list of plain values | Put the value on a member, and reduce the field |
| A `where` filter on a value that changes in the run | Put a Boolean formula on the member, and reduce it |
| A past value of a field, read in a stage, or a member by its position | Keep the past value in a stored value. Select a member by its key with `.at(key)`. |
| A handle that `.start(…)` gives | Find the occurrence in `event.occurrences` |
| An interruption, a cancellation or a join of an occurrence | An occurrence runs to its end. Guard its later stages, or wait with `until`. |
| A stage at an absolute time | A trigger on `t >= T` |
| A name that a stage declares | Declare a local at the start of the event, and assign it in the stage |
| A resource that a part holds and then releases | A stock with a flow out and a flow back, or a flow with legs |
| One stored field as a parameter of an event | Give the entity as the parameter |
| Two draws that are correlated | Store one draw, and read it twice |
| The derivative of a formula | Not in this version |
| An assertion only at the start | An assertion over an input that gives the start |
| A citation of one cell of a table | One table for each source |
| A nonlinear or yes/no problem of a solver, or a lookup keyed by an unknown of a solver | Refused by name |
| An interpolation in a keyed read | `.at(x)` is a step |
| A change of the ends of a flow, or of a link, during a run | The ends and the links are fixed for the run |
| A way to clear a declared capacity during a run | Change the request, or give the capacity a rate |
| A strict threshold (`<`, `>`) on a value that changes continuously | An inclusive threshold (`<=`, `>=`) |

## Known issues and possible features

[known-issues.md](../../docs/known-issues.md) lists the known issues of the engine, the tools and the
notebook of the catalogue, and the features that could come next. The plan for faster declared solvers
is in [solver-speed.md](../../docs/scoping/solver-speed.md).
