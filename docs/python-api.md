# The Python API

The public Python API is the list of names in `_EXPORTS` of `napkin/__init__.py`. Each name loads
its module when a script first uses it, so `import napkin` loads no compiler, no engine, and no
numpy or scipy. Every other name of the package is internal and can change in a minor version. The
words **model**, **package**, **variant**, **input**, **run**, **named run**, **configuration**,
**record**, **reading**, **path**, **edit**, **breakpoint**, **checkpoint** and **study** have the
meanings of [the terms](language/README.md#terms).

| Name | Module | What it gives |
| --- | --- | --- |
| [`load_scenario`](#load_scenario) | `napkin.model.compile` | The compiled model of a package, of a variant or of a model file |
| [`load_package`](#load_package) | `napkin.package` | The compiled model of each variant of a package |
| [`run`](#run) | `napkin.engine.timeline` | The record of one run, or a checkpoint |
| [`read`](#read) | `napkin.engine.timeline.record` | The values of paths at times, from a record |
| [`report`](#report-and-lag) | `napkin.engine.report` | The values of paths at times, with units, labels, lags, evidence trails and near-ties |
| [`Lag`](#report-and-lag) | `napkin.engine.report` | A reporting lag |
| [`Session`](#session) | `napkin.session` | One run, stopped at breakpoints, edited, saved and resumed |
| [`study`](#study) | `napkin.engine.study` | The records of the named runs of a model |
| [`monte_carlo`](#monte_carlo) | `napkin.engine.uncertainty` | A Monte Carlo study of one run of a program |
| [`spread`](#spread) | `napkin.spread` | The module of the Monte Carlo study of one run of a model |
| [`instances`](#instances) | `napkin.model.views` | The members of a template, with their links |
| [`dynamics`](#dynamics) | `napkin.dynamics` | The module of the field, the equilibria, the branches, the thresholds and the sensitivity of a run |

`napkin.__version__` is the version of the package. `napkin.SCHEMA_VERSION` (`"0.0.1"`) is the
version of the edit document.

The examples on this page ran in a folder that holds the `examples/` folder of this repository. Each
example shows the output that it printed.

## load_scenario

```text
napkin.load_scenario(path, *, run=None, edits=None)
```

`path` is a package folder, its `model.scn`, the folder or the `model.scn` of a variant, or another
model file. `run` names a named run, and `edits` is an edit document
([cli.md](cli.md#the-edit-document)). The result is a `Compiled`
([compiler.md](compiler.md#the-two-entry-points)):

| Field or function | What it gives |
| --- | --- |
| `declared` | The declared model: its scenario line, entities, members, values, options, named runs and records |
| `program` | The program that the engine runs |
| `configuration` | The configuration of the run that `run` and `edits` chose: the default run when both are None |
| `reports` | The warnings, each a `Problem` that refuses nothing |
| `model_hash` | The model hash, which an edit document names |
| `table` | The side table: the place, the label, the evidence and the title of each part |
| `configure(run=None, edits=None, options=None)` | The configuration of another run of this model |
| `artifact()` | The program with its side table, as a file keeps it |

A file that does not exist raises `FileNotFoundError`. A model that does not compile raises
`napkin.model.LanguageError`, whose `problems` hold each problem with its code and its place.

```python
import napkin

model = napkin.load_scenario('examples/incident_response_tempo')
print(model.declared.scenario.title, [item.name for item in model.declared.runs][:2])
print(model.configure('rapid_response').inputs[1])
```

```text
Attack tempo and incident response ['standard', 'rapid_response']
InputValue(member='response', name='containment_delay', value=Quantity(number=2, unit='h'))
```

## load_package

```text
napkin.load_package(path)
```

`path` is a package folder or its `model.scn`. The result is `{name: Compiled}`: `{package: model}`
for a package with no variants, else `{package:variant: model}` for each variant, in name order. One
`LanguageError` holds the problems of every model that fails. A problem of the main file shows once.

The package `demo` comes from `napkin new demo --variants east,west` ([cli.md](cli.md#napkin-new)):

```python
import napkin

for name, model in napkin.load_package('demo').items():
    record = napkin.run(model.program, model.configuration)
    (served,) = napkin.read(record, model.program, ['people_served'], [720])
    print(name, served.values, served.unit)
```

```text
demo:east (600.0,) people
demo:west (900.0,) people
```

## run

```text
napkin.run(program, configuration, breakpoints=())
```

The function runs a program under a configuration to the horizon of its request, and gives the
`Record` of the run (`napkin/program/record.py`). A run that fails gives the record up to the time at
which it stopped, with its failure. A run that one of `breakpoints` stops gives a `Checkpoint`
(`napkin/program/checkpoint.py`); [`Session`](#session) is the simple way to use breakpoints.

The engine refuses a part that it does not run with `napkin.engine.timeline.Outside`, and a
configuration that the program cannot take with `napkin.program.config.ConfigurationError`.

A `Record` has its `manifest`, its `histories`, its `trace` and its `failure`. `record.entries(kind)`
gives the entries of the trace, and `record.near_ties()` gives the decisions within the tolerance of
their boundary.

```python
import napkin

model = napkin.load_scenario('examples/reservoir')
record = napkin.run(model.program, model.configuration)
print(record.manifest.horizon, record.failure)
print([(entry.t, entry.kind, entry.part) for entry in record.entries('commit')])
```

```text
120.0 None
[(40.0, 'commit', 'operator.decide.step[0]')]
```

## read

```text
napkin.read(record, program, paths, times)
```

The function gives one `Reading` for each path, in order. A `Reading` has its `path`, its `key`, its
`unit` (the declared unit) and its `values`, one for each time, in order. Times are in hours.

A value comes only from what the record holds. Any other value is `Unavailable` with its reason: a
time before the run, after its horizon or after its stop, a value that the record does not hold, or
a value of an occurrence before its start. A path that names no value of the program raises
`KeyError`.

```python
import napkin

model = napkin.load_scenario('examples/piano_tuners')
record = napkin.run(model.program, model.configuration)
for reading in napkin.read(record, model.program, ['tunings_done', 'tuners.due'], [0, 4380, 8760]):
    print(reading.path, reading.unit, reading.values)
```

```text
tunings_done tunings (0.0, 1461.768743696291, 2923.537487392582)
tuners.due tunings (5000.0, 3538.231256303709, 2076.462512607418)
```

## report and Lag

```text
napkin.report(record, program, configuration, paths, times, lags=None, model=None, options=(), *, table=None)
napkin.Lag(shortest, longest)
```

`report` reads the values of `paths` at `times` from one record, as `napkin run` shows them
([cli.md](cli.md#napkin-run)). Give the side table in `table` (`Compiled.table`) for the labels, the
titles and the evidence. `lags` maps a path to its `Lag`. `options` names the options of the run,
whose settings the evidence trails cite. A time outside the run raises `ValueError`.

`Lag(shortest, longest)` is a uniform reporting lag, in hours. The value at a time t is the mean of
its history from t − `longest` to t − `shortest`. Equal ends are a fixed delay. A lag is valid only
for a number that a proof says never falls over the run. Without that proof, the value keeps its
plain read, and its `note` gives the reason. A window that starts before 0 h is `Unavailable`.

The result is a `Report`:

| Field | What it holds |
| --- | --- |
| `times` | The times of the report |
| `values` | One `Reported` for each path: its `path`, `unit`, `label`, `title`, `values`, `lag`, `note` and evidence `trail` |
| `near_ties` | Each decision within the tolerance of its boundary (`NearTie`) |
| `end`, `stopped` | The time to which the record reaches, and why it stopped there (None for a run to its horizon) |
| `records` | Each evidence record that a trail cites: its name, its kind and its text |

```python
import napkin

model = napkin.load_scenario('examples/piano_tuners')
record = napkin.run(model.program, model.configuration)
found = napkin.report(
    record, model.program, model.configuration, ['tunings_done'], [0, 4380, 8760],
    {'tunings_done': napkin.Lag(730, 1460)}, table=model.table,
)
(value,) = found.values
print(value.label, value.unit, value.values[1:])
print(value.note)
print(value.values[0].reason)
```

```text
Tunings done in the year tunings (1096.3265577722182, 2558.0953014685088)
what changes it adds to what it counts or moves within it: tuners.tune of tuners
the lag of tunings_done at 0 h reads it from -1460 h, before the run starts at 0 h: the record holds no value then
```

## Session

```text
napkin.Session(program, configuration, breakpoints=(), *, table=None, log=None)
napkin.Session.load(path, program, *, configuration=None, table=None)
```

A session plays one run and stops at its breakpoints. A breakpoint is a
`napkin.program.checkpoint.Breakpoint(at, owner='')`. `at` is the origin of an event, a stage or a
statement (`operator.decide.step[0].do[1]`), and `owner` limits it to one member or one occurrence.
`Compiled.table.executable()` lists the locations of a model. `napkin play` is one client of a
session ([cli.md](cli.md#napkin-play)).

| Call or field | What it does |
| --- | --- |
| `advance()` | Go on to the next stop and give its checkpoint, or None at the end of the run |
| `view(paths=None)` | The stop as a `View`: the stop, its place in the source, what runs next, the values (each a `Shown`: `path`, `value`, `unit`, `label`, `editable`, `choices`), the edits and the draws of the stage before the stop |
| `edit(path, value)` | Give a live stored value a new value at the stop, in its declared unit. The engine checks the type and the bounds |
| `save(path)` | Write the checkpoint, with its edits, to a file |
| `Session.load(path, program, ...)` | Go on from a saved checkpoint, in this process or a fresh one |
| `checkpoint`, `record`, `stops`, `log` | The present checkpoint, the record at the end, the stops so far, and the log of the session |

A session refuses an unknown location and a location in the body of a trigger with
`napkin.program.checkpoint.CheckpointError`. It refuses a checkpoint of another program, another
engine or another configuration by name.

```python
import napkin
from napkin.program.checkpoint import Breakpoint

model = napkin.load_scenario('examples/reservoir')
stop = Breakpoint('operator.decide.step[0].do[1]')
session = napkin.Session(model.program, model.configuration, [stop], table=model.table)
session.advance()
for shown in session.view(['reservoir.water', 'operator.decide#0.order']).values:
    print(shown.path, shown.value, shown.choices)
session.edit('operator.decide#0.order', 'WAIT')
session.save('stop.checkpoint')
while session.advance() is not None:
    pass
print(napkin.read(session.record, model.program, ['reservoir.gate'], [120])[0].values)
```

```text
reservoir.water 0.7 None
operator.decide#0.order OPEN ('OPEN', 'WAIT')
('CLOSED',)
```

## study

```text
napkin.study(model, runs=None, edits=None, *, jobs=1, progress=None, cancel=None)
```

`model` is a `Compiled`. The result is `{name: record}` for each named run of `runs`, or for each
named run of the model, or `{None: record}` of the default run when the model has none. The study
checks the edit document whole, in every run, before any run starts. Each run goes through the run
store when a store is active ([cli.md](cli.md#the-run-store)).

- `jobs` above 1 runs the runs on that many new processes. The results come in the order of the runs.
- `progress(done, total)` is called as runs finish.
- `cancel`, an event such as a `threading.Event`, stops the study between runs with
  `napkin.engine.study.Cancelled`.

`napkin.engine.study.edits_for(model, edits)` gives an edit document for the model's revision: the
schema version and the model hash, with the keys `set`, `options`, `runs` and `reason` of `edits`.

```python
import napkin
from napkin.engine.study import edits_for

model = napkin.load_scenario('examples/incident_response_tempo')
for name, record in napkin.study(model, ['standard', 'rapid_response']).items():
    print(name, napkin.read(record, model.program, ['attack.blocked'], [24])[0].values)
edits = edits_for(model, {'set': {'response.detection_delay': '5 h'}})
slower = napkin.study(model, ['rapid_response'], edits)
print(napkin.read(slower['rapid_response'], model.program, ['attack.blocked'], [24])[0].values)
```

```text
standard (4.0,)
rapid_response (6.0,)
(5.0,)
```

## monte_carlo

```text
napkin.monte_carlo(program, configuration, paths, times, settings=None, *, model=None,
                   confidence=0.95, with_scales=False, jobs=1, progress=None, cancel=None)
```

The function reads the values of `paths` at `times` in a central run and in each sample of a run.

1. The central run is the configuration in `median` mode. It gives each value's unit, label and
   central value. A central run that stops refuses the study before any sample runs.
2. Each sample is the configuration in `sampled` mode, with its own seed.
   `napkin.engine.sampling.SamplingSettings(samples=200, seed=0)` gives the number of samples and
   the seed of the study.
3. A sample that stops before its horizon refuses the study. `refused` names each such sample, and
   the study has no summary.

Give the side table in `model` (`Compiled.table`) for the labels. A path that the program does not
have raises `KeyError`. A time outside the run raises `ValueError`. The result is a `MonteCarlo`:

| Field or function | What it holds |
| --- | --- |
| `settings`, `paths`, `times` | The settings and the selection of the study |
| `central` | The report of the central run |
| `samples` | Each `Sample`: its seed, its values, its draws, its number of near-ties and why it stopped |
| `spread(path, t)` | The `Spread` of a path at a time: its `unit`, its `label`, its `summary` and its `drivers` |
| `refused` | Why the study has no summary, or None |

A `summary` has `central`, `mean` (an estimate with `value`, `low` and `high`), `sd`, `sem`, `least`,
`greatest` and `percentiles`. A value that is no number in every sample has no summary, and
`reason` says why. The `drivers` are the draws in the order of their rank correlation with the value.

```python
import napkin
from napkin.engine.sampling import SamplingSettings

model = napkin.load_scenario('examples/piano_tuners')
study = napkin.monte_carlo(
    model.program, model.configuration, ['tunings_done'], [8760],
    SamplingSettings(samples=50, seed=1), model=model.table,
)
found = study.spread('tunings_done', 8760)
print(found.unit, found.summary.central, round(found.summary.mean.value, 1))
print(found.drivers)
```

```text
tunings 2923.537487392582 2900.9
(('tuners.rate.draw[0]', 'tuners', 0.9999999999999999),)
```

## spread

```text
napkin.spread.spread(model, paths, times=None, *, run=None, edits=None, samples=200, seed=0,
                     with_scales=False, jobs=1, progress=None, cancel=None)
```

`napkin.spread` is a module. Its function `spread` is the Monte Carlo study of one run of a model, as
`napkin sample` asks for it ([cli.md](cli.md#napkin-sample)).

- `model` is a path that `load_scenario` reads, or a `Compiled`.
- `run` names a named run, and `edits` is an edit document. The function checks the document first,
  and a problem raises `LanguageError` before any run starts.
- `times` are in hours. Without them, the study reads at the horizon of the run.
- `samples` and `seed` are the settings of the study. `jobs` is the number of processes.

The result is a `MonteCarlo` ([monte_carlo](#monte_carlo)). A pool starts its processes with `spawn`,
and each process imports the main module of the script. So a script with `jobs` above 1 calls
`spread` under `if __name__ == '__main__':`.

```python
from napkin.spread import spread


def main():
    found = spread('examples/piano_tuners', ['tunings_done'], samples=100, seed=0, jobs=2)
    if found.refused is None:
        mean = found.spread('tunings_done', 8760).summary.mean
        print(round(mean.value, 1), round(mean.low, 1), round(mean.high, 1))


if __name__ == '__main__':
    main()
```

```text
2918.0 2853.5 2982.4
```

## instances

```text
napkin.instances(compiled, template)
```

The function gives `[{name, links}]` for each member of a template, in the order of creation. `links`
maps each link to the id of the member that it names.

The package `pumps` holds this model and a table `tanks.csv` with the rows `north,100` and
`south,20` under the header `id,water: L @guess`. Its `units.json` gives the unit `L`.

```scn
scenario "Pumps between tanks"
    horizon 1 day

Tank:
    "A tank."
    water: L = 100 L in [0 L,] scale 100 L @guess
        "Water in the tank"

Pump:
    "A pump that moves water from one tank to another."
    origin: Tank
    destination: Tank
    input rate: L/h = 2 L/h in [0 L/h, 10 L/h] @guess
        "Water that the pump moves in an hour"
    flow pump: this.origin.water -> this.destination.water @guess
        request = formula(this.rate)

tanks: Tank from "tanks.csv"

lift: Pump
    origin = tanks.north
    destination = tanks.south

record guess: assumption "An example value."
```

```python
import napkin

model = napkin.load_scenario('pumps')
print(napkin.instances(model, 'Tank'))
print(napkin.instances(model, 'Pump'))
```

```text
[{'name': 'tanks.north', 'links': {}}, {'name': 'tanks.south', 'links': {}}]
[{'name': 'lift', 'links': {'origin': 'tanks.north', 'destination': 'tanks.south'}}]
```

## dynamics

`napkin.dynamics` is a module. It reads the engine's own field of a run, so it analyses the equations
that the engine runs. It gives data, and it changes no program and no record.

```text
napkin.dynamics.vector_field(program, configuration, values=None)
```

`vector_field` gives the `VectorField` of a run at its start. `values` gives inputs other values:
`{path of an input: value}`, a number in the input's declared unit, a yes/no, the name of an enum
member, a text or a distribution.

- The state is the stocks of the connected sets whose rates move (`names`), in canonical units.
- `field(x, t=0.0)` gives the rates of those stocks, per hour, at the state `x` and the time `t`.
- `field.start` is the state at the start, and `field.values(x)` gives each stock in its own unit.
- The values that do not move between moments keep their values at the start. No stage runs, and no
  trigger fires.

| Function | What it gives |
| --- | --- |
| `equilibria(field, *, t=0.0, starts=32, seed=0, box=None, tol=1e-10, include=())` | Each distinct equilibrium (`Equilibrium`: `state`, `eigenvalues`, `stability`, `value(name)`) |
| `equilibrium_at(field, x, t=0.0)` | The equilibrium at `x`, with its derivative and its stability |
| `continue_equilibrium(program, configuration, parameter, span, ...)` | A branch of equilibria as an input or the time `t` moves, with its folds and Hopf points |
| `fold_curve(program, configuration, parameter, span, second, grid, ...)` | The folds of the branch for each value of a second input |
| `input_threshold(program, configuration, name, low, high, classify, *, tol)` | The value of an input where the class of the run's end changes |
| `state_threshold(program, configuration, path, low, high, classify, *, tol)` | The start value of a stored value where the class of the run's end changes |
| `input_factors(program, configuration, names)`, `run_function(program, configuration, path, *, time=None)` | The ranges of inputs, and a function of their values: the value of a path at a time |
| `morris(f, factors, ...)`, `sobol(f, factors, *, samples, ...)` | Morris screening and Sobol indices of such a function |

The model `room` is a waiting room. People come at a fixed rate, and a share of them leaves each hour:

```scn
scenario "A waiting room"
    horizon 2 days

room:
    "A waiting room that people enter and leave."
    input arrivals: people/h = 4 people/h in [0 people/h, 10 people/h] @guess
        "People who come in an hour"
    input leave: fraction/h = 0.1 fraction/h in [0.01 fraction/h, 1 fraction/h] @guess
        "Share of the people who leave in an hour"
    waiting: people = 10 people in [0 people,] scale 100 people @guess
        "People who wait"
    flow come: SOURCE -> this.waiting @guess
        request = formula(this.arrivals)
    flow go: this.waiting -> SINK @guess
        request = formula(this.leave * this.waiting)

record guess: assumption "An example value."
```

```python
import napkin

model = napkin.load_scenario('room')
field = napkin.dynamics.vector_field(model.program, model.configuration, {'room.arrivals': 5})
print(field.names, field(field.start))
for found in napkin.dynamics.equilibria(field):
    print(round(found.value('room.waiting'), 6), found.stability, found.eigenvalues)
```

```text
('room.waiting',) [4.]
50.0 stable [-0.1+0.j]
```

With 5 people in each hour and a share of 0.1 that leaves each hour, the room holds 50 people at
rest. The eigenvalue −0.1 per hour makes the rest state stable.
