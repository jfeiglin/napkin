# The Python API

`import napkin` gives the public core of the engine. With it, a program builds the models of a
package and runs their studies. It samples their distributions, plays a run one decision at a time,
and analyses the dynamics of a run. These names are the public API:

| Name | What it does |
| --- | --- |
| `load_scenario(path, …)` | Builds, checks and proves the model of one model file ([Build a model](#build-a-model)). |
| `load_package(path, …)` | Builds each model of a package: its own model, or the model of each variant. |
| `evaluate_study(model, …)` | Checks an edit document and simulates the runs ([Studies](#studies)). |
| `sample_result(study, …)` | Gives the report of a study. |
| `evaluate_uncertainty(model, …)` | Runs the runs many times with their distributions drawn ([Uncertainty](#uncertainty)). |
| `uncertainty_report(result, …)` | Gives the report of such a study, with a summary of each outcome. |
| `Session(model, run, …)` | Plays one run, one decision at a time ([Session](#session)). |
| `actors(model)`, `instances(model, template)` | List the actors with their choices, and the instances of a template ([Views](#views)). |
| `napkin.dynamics` | Finds rest states, branches of rest states and thresholds, and ranks the inputs ([Dynamics](#dynamics)). |

Everything else is internal and may change in a minor version. This page also names the classes that
these functions take or raise: `ModelError` (`napkin.model`), `SamplingSettings` (`napkin.engine`) and
`OtherContext` (`napkin.session`). A program uses them as this page shows. `napkin.__version__` is the
version of the package, and `napkin.SCHEMA_VERSION` is the version of the documents that the engine
reads and writes (`0.0.1`).

`import napkin` loads no other module. Each name loads its module when a program uses it first. The
examples on this page run from the root of a checkout, because the wheel does not ship `examples/` or
`scenarios/`. A program that uses this API simulates each run that it asks for: the run store is for
the `napkin` command ([engine.md](engine.md#the-run-store)). The command line is in
[cli.md](cli.md), and the language of the model files is in [language.md](language.md). The steps of
the compiler that builds a model are in [compiler.md](compiler.md).

## Build a model

`load_scenario(path, library=None, *, admission_runs=None)` reads one model file, builds its model,
checks it and proves it. `path` is a `model.scn`: the main file of a package, or the file of a
variant. The model of a variant also holds its package's main file and the modules that they use
([language.md §2.12](language.md#212-packages-variants-and-modules)).

```python
import napkin

model = napkin.load_scenario('examples/piano_tuners/model.scn')
print(list(model.runs))
print(list(model.inputs))
staff = model.inputs['tuners.staff']
print(staff['unit'], staff['value'], staff['range'], staff['doc'])
print(dict(model.outputs))
```

```
['base']
['tuners.rate', 'tuners.staff', 'tuners.need']
tuner 3 (1, 10) Tuners in the town
{'tunings_done': 'tunings_done'}
```

A model that is built is valid. The build checks each of these once:

- the files: the form of each line, the modules and their uses, and the names that two files declare;
- the rules of the language: names, units, ranges, bools, named values, options and runs;
- the library, and each record that a line cites;
- one flat structure for each set of start-state options that a run uses, with the compiler's checks
  and proofs of its bounds and domains; and each whole structure, so a part that every run leaves out
  is still checked ([The parts that cannot act](#the-parts-that-cannot-act));
- the start, when the model has one: one thing has the event `start`, with no `after` and one
  outcome, and it fires first, at t = 0, in every run;
- the values of every run, with the blocking checks of the inputs, so each run of the model as its
  files write it resolves;
- the options that no run names: their values, and each of them with the other options of each run.

The build does not check any other combination of options. A caller asks for one with
`model.combination` ([The model](#the-model)).

The library of a model is the prelude's units (`napkin/std/units.json`), the library that the main
file's `library "PATH"` line names, and the units and evidence of the package's folder and of the
variant's folder. Leave `library` out: then the build reads all of these. A library that a caller
gives is the whole library, the prelude included.

A model that fails raises `ModelError`. Its `diagnostics` are a list of dicts, each with its `code`,
`path`, `message` and `severity`, and with the `file`, `line` and `column` of the part that it is
about. A diagnostic of a name that names nothing ends with the closest names of the model, when one
is close. A JSON file of the model that writes a key twice, or a number that is not finite, raises
`SourceError` (`napkin.model`). A model file that is not UTF-8 text raises Python's
`UnicodeDecodeError`.

```python
import shutil
import tempfile
from pathlib import Path

import napkin
from napkin.model import ModelError

folder = Path(tempfile.mkdtemp()) / 'piano_tuners'
shutil.copytree('examples/piano_tuners', folder)
entry = folder / 'model.scn'
entry.write_text(entry.read_text().replace('to 10 tuner', 'to 10 tunr'))
try:
    napkin.load_scenario(entry)
except ModelError as error:
    for item in error.diagnostics:
        print(item)
```

```
{'code': 'build', 'path': 'tuners/staff/max:', 'message': "Unregistered unit 'tunr'", 'severity': 'error', 'line': 14, 'column': 5, 'file': '/tmp/tmp4ljt288d/piano_tuners/model.scn'}
```

`load_package(path, library=None, *, admission_runs=None)` builds each model of a package, as
`load_scenario` builds it. `path` is the package's folder or its main file. It gives `{name: model}`:
`{package: model}` for a package without variants, else `{package:variant: model}` for each variant,
in name order. When models fail, it raises one `ModelError` with the diagnostics of each, and each
diagnostic names its model (`model`).

```python
import napkin

models = napkin.load_package('examples/reservoir')
print({name: model.scenario.title for name, model in models.items()})
```

```
{'reservoir': 'A reservoir in a storm'}
```

### Admission scope

`admission_runs` is a collection of the names of runs. With it, the build keeps every check of the
files, the evidence, the units, the tables and the structures. It resolves and proves the values of
the named runs only, and it skips the options that no run names. So a model of a large package builds
faster. `napkin run --run` and `napkin play` build the model for their run only, and `napkin sample
--run` for the run and the runs that it is compared with. `napkin compile` checks every run.

`model.admission_runs` is None for a full build, or the tuple of the admitted runs. The model hash does
not change with the scope. A model with a scope runs only the admitted runs, and a study of it must
name its runs:

```python
import napkin

model = napkin.load_scenario('examples/reservoir/model.scn', admission_runs=['base'])
print(model.admission_runs)
print(napkin.evaluate_study(model).diagnostics)
print(napkin.evaluate_study(model, runs=['base']).admissible)
```

```
('base',)
[{'code': 'admission_scope', 'severity': 'error', 'message': 'A scoped model requires an explicit selection of admitted runs'}]
True
```

A model with a scope is not a model that passed every check. Do not show it as one.

### The model

`Model` is a frozen dataclass. Its mappings are read-only. A program may read these fields, and the
others are internal:

| Field | What it holds |
| --- | --- |
| `origin` | The path of the model file. |
| `scenario` | The model as the file writes it. Its `title`, `summary` and `scope` are the texts of the scenario line (a variant's title follows its package's). |
| `menu` | The options: `{group: {option: its text}}`, in the order of the file. |
| `runs` | `{run: {options, name, comparison_of, starts}}`: the options of the run in the order written; the name that a report shows (its text, or its options joined by " · "); the run that its `versus` names, or None; and its start-state options. |
| `start_options` | The options that set a start state: a named state, or the start value of a stock, tally or number state, in the order of the menu. |
| `inputs` | `{input: …}` for each input and fixed value, with its `entity`, `field`, `doc`, `type` (`number`, `bool` or `names`, with its `values`), `unit`, `value`, `distribution` (the record of its distribution, or None), `fixed`, `range`, `basis` (the record of its value), `options` (the value that each option gives it) and `groups`. The `value` of an input with a distribution is its central value. |
| `outputs` | `{output in the file: its outcome in a report}` ([Names](#names)). |
| `events` | `{event in the file: its event in the structure}`, for each event and each of its outcomes. |
| `time` | `{horizon}` in hours, with `timescales` and `resolution` when the file gives them. |
| `initiation` | The start, `{rule, effect, entity, basis}`, or None for a model without one. |
| `structures` | `{starts: structure}`: one flat structure for each set of start-state options that a run uses, as a `Structure` of typed records ([The structure](#the-structure)). |
| `left_out`, `whole` | For each structure, the parts that it leaves out and why, and the structure before it leaves out a part, which is a `Structure` too ([The parts that cannot act](#the-parts-that-cannot-act)). |
| `admission_runs` | None, or the admitted runs ([Admission scope](#admission-scope)). |
| `model_hash` | The SHA-256 of the meaning of the model, of the units that it uses, of the records that it reaches and of the language's version. It covers no name or path: not the names of the package and the variant, nor the folder of the library. It covers no unit or record that the model does not reach, not the list of variants and not the package's version. So a rename keeps it, a new variant does not change its siblings' hashes, and a unit that a later prelude adds changes no hash. An edit document and a play log name it. |
| `implementation_hash` | The digest of the code of the engine, of the model and of the expressions, and of the compiler's schemas, comments included. A report and a play log keep it; an edit document does not. |
| `library_hash` | The digest of the units that the model uses and of the records that it reaches. |

`combination(run, options)` gives the model of one run with other options. Its one run is `run`, with
each of `options` in place of the run's option of its group, or added when the run names none of
that group. The build does not check a combination that no run makes, so this call checks it as the
build checks a run: its values, the blocking checks of its inputs and the proofs of its structure.
The derived model keeps the model's identity, its structures and its evidence. Its run keeps its name,
so an edit document of the model applies to it as to the run.

```python
import napkin
from napkin.model import ModelError

model = napkin.load_scenario('scenarios/water_controls_wipe/variants/juneau/model.scn')
print({group: list(options) for group, options in model.menu.items()})
print(list(model.runs))
print(dict(model.runs['early_kept']))
derived = model.combination('early_kept', ['Delayed response'])
print(dict(derived.runs['early_kept']))
try:
    model.combination('early_kept', ['Late response'])
except ModelError as error:
    print(error.diagnostics)
```

```
{'Response': ['Early response', 'Standard response', 'Delayed response'], 'Access': ['No hidden access', 'Keeps hidden access'], 'Attacker': ['AI agent', 'Human team'], 'Reach': ['Every system of the place']}
['early_kept', 'standard_kept', 'delayed_kept', 'delayed_none', 'delayed_kept_human']
{'options': ('Early response', 'Keeps hidden access'), 'name': 'Early response · Keeps hidden access', 'comparison_of': None, 'starts': ('Keeps hidden access',)}
{'options': ('Delayed response', 'Keeps hidden access'), 'name': 'Delayed response · Keeps hidden access', 'comparison_of': None, 'starts': ('Keeps hidden access',)}
[{'code': 'reference', 'path': 'options/Late response', 'message': 'Late response is not an option; did you mean Early response, Delayed response or Standard response?', 'severity': 'error'}]
```

An option that is not in the menu is a diagnostic (`reference`), and so are two options of one group
(`combination`). The combination runs in the structure of its start-state options. When no run of the
model starts from them, it is a diagnostic too (`combination`).

### The structure

The engine runs a flat structure: the model with its templates, copies and files made into one set of
named parts. `model.structures` holds one for each set of start-state options that a run uses. The key
is the sorted tuple of those options, `()` for runs that have none, and `model.structure_of(run)`
gives the structure of a run. [engine.md](engine.md#what-the-engine-reads) lists its sections and what
the engine does with each one.

A structure is a `Structure` (`napkin.model.structure`): a frozen record of typed parts. A program
reads a part as an attribute, such as `structure.flows[name].rate`, and never as a key of a nested
mapping. These rules hold for each record:

- **Sections.** Each section is a read-only mapping from the name of a part to its record, in the
  compiled order: `structure.quantities`, `structure.flows`, `structure.rules`.
- **Fields.** [engine.md](engine.md) names the fields of each part. The ends of a flow and of a move
  are `source` and `target`, not `from` and `to`. The bounds of a quantity are `minimum` and
  `maximum`, not `min` and `max`. Those four short words are words of Python.
- **No value.** A field that a part does not have is None. A flow from outside the model has the
  `source` None, and a rule with no window has the `each` None.
- **Lists.** Each list is a tuple, and no record can change.
- **Expressions.** An expression is its typed node (`napkin.core.expr`), or the number or the yes/no
  that it is. `str(node)` is the text of the expression, and `napkin.core.expr.names(node)` gives the
  names that it reads.
- **Records.** The evidence of a part (`basis`) and its `metadata` are plain read-only data.

`model.whole[starts]` is a `Structure` too. `model.resolve(run, values)` gives a `Resolved`: a
`Structure` with the values of one run ([engine.md](engine.md)). The `resolved` of each run of a study
is a `Resolved` ([Studies](#studies)). A resolved run shares the parts of its structure, which cannot
change: `model.resolve(run).flows` is the `flows` of the structure of the run, the same object.

```python
import napkin

model = napkin.load_scenario('examples/reservoir/model.scn')
structure = model.structure_of('base')
print(list(model.structures), structure is model.structures[()])
spill = structure.flows['reservoir.spill']
print(spill.source, spill.target, spill.rate)
print(structure.flows['reservoir.storm'].source)
water = structure.quantities['reservoir.water']
print(water.kind, water.initial, water.minimum, water.maximum)
rule = structure.rules['operator.decide']
print(rule.trigger.kind, rule.trigger.var, rule.trigger.op, rule.trigger.value)
print([outcome.name for outcome in rule.outcomes], rule.each)

resolved = model.resolve('base', {'reservoir.inflow': 0.04})
print(type(resolved).__name__, resolved.run, resolved.parameter_values['reservoir.inflow'])
study = napkin.evaluate_study(model)
print(type(study.runs['base']['resolved']).__name__)
```

```
[()] True
reservoir.water reservoir.spilled reservoir.spillway if reservoir.gate == 'open' else 0
None
stock q(0.6, 'fraction') 0 None
crossing reservoir.water >= operator.level
['open', 'wait'] None
Resolved base 0.04
Resolved
```

These rules hold for every section:

- **Names.** Each part has the name of [Names](#names).
- **Paths.** Each part has its `path`: the place of its line in the file, such as `reservoir/spill`
  for a flow and `operator/decide/open` for an outcome. A report and a diagnostic name a part by it.
  A part of an instance that its template writes has the template's place.
- **Owners.** A stock, tally, flow and share belongs to the entity that declares it.
- **Copies.** The entity record of a copy has `origin`, its set, and `copy`, its number.
- **Actors.** An entity has `sees`: the facts that the actor sees, or None for a thing of the world. A
  played run shows them at each decision ([engine.md](engine.md#play)).
- **Links** are keyed by the part that they reach, under the entity that reaches it.
- **Outputs** read zero for a stock or tally that the structure leaves out.

Every structure has every input. So a run accepts an edit of any input, also of an input that only a
part that the run leaves out reads.

### The queries of a structure

A `Structure` answers the questions that the engine, the reports and the pictures ask of a model.

| Query | What it gives |
| --- | --- |
| `section(name)` | `{name: record}` of one kind of part, by the name of its section. |
| `moment_order()` | The rules in the order in which one moment reads them: by `rank`. |
| `flows_from(quantity)`, `flows_into(quantity)` | The names of the flows that drain a quantity, or fill it, in the order of the flows. |
| `owner(name)` | The entity that a part belongs to, or None for a part of no entity, such as an output of the scenario. |
| `names(source)` | The names that one expression reads itself. It reads nothing through a formula. |
| `reads(rule, roles=None)` | The names that a rule reads itself: in all its expressions, or in those of the `roles` that the caller names. |
| `writes(rule)` | What a rule can change: each value that an outcome sets, and the two ends of each move. |
| `expanded(source, labels=False, keep=False)` | The names that an expression reads through the formulas. With `labels`, it also reads through the statuses. With `keep`, the result has the names of the formulas on the way. |
| `left(section)` | `{name: why}` of the parts of one section that the structure leaves out ([The parts that cannot act](#the-parts-that-cannot-act)). |

A rule answers three more questions. `rule.sources()` gives each expression that the rule reads, with
its role: `when`, `delay`, `each`, `keep`, `extra`, `chance`, `available`, `set` or `amount`.
`rule.events()` gives each event that the rule can make happen. `rule.steps()` gives what each outcome
does.

```python
import napkin

model = napkin.load_scenario('examples/reservoir/model.scn')
structure = model.structure_of('base')
rule = structure.rules['operator.decide']
print(structure.flows_from('reservoir.water'), structure.flows_into('reservoir.water'))
print(sorted(structure.reads(rule)), sorted(structure.writes(rule)))
print(rule.sources())
print(rule.events())
print(structure.owner('reservoir.spill'), [item.id for item in structure.moment_order()])
print(sorted(structure.expanded(structure.rates['reservoir.risk_time'].expr)))
print(dict(structure.left('rules')))
```

```
('reservoir.spill',) ('reservoir.storm',)
['operator.level', 'reservoir.water'] ['reservoir.gate']
(('when', 'reservoir.water >= operator.level'), ('chance', '1'))
('operator.decide', 'operator.decide.open', 'operator.decide.wait')
reservoir ['operator.decide']
['reservoir.risk', 'reservoir.water']
{}
```

### The parts that cannot act

A structure leaves out the parts that cannot act in any of its runs, from its start values. The
analysis follows what the runs can reach:

- each named state takes its start value, and each value that an outcome that can happen gives it;
- for two named states that a condition tests together, the values that they can take at once;
- an event can happen only when a rule that emits it can fire;
- a condition on a stock, a time or anything else counts as possible.

A rule can fire where its `when` can hold, or where the step of an outcome that can happen names it.
An outcome can happen where its chance can be above 0. A condition that the runs never reach makes it
impossible; a number, an expression and `else` count as possible.

The structure then leaves out:

- each rule that cannot fire, and each event of those rules only;
- a stock or tally that starts at zero and that no part that stays changes or reads: outputs and
  checks read zero for it;
- a named state that no part that stays changes or reads;
- an entity none of whose parts can act and that no part of another entity reads, with its states,
  stocks, flows, formulas, status and checks.

Each part that stays keeps the parts that it names, so each name of a structure resolves:

- a rule keeps what its `when`, `after`, `each`, `while`, its chances, its draws, its delayed values
  and the conditions of its outcomes read, and what the step of each of its outcomes reads and
  changes, also for an outcome that can never happen; it keeps the rules that its steps name;
- a flow keeps its two ends and what its rate reads, also when its rate is zero in every state that
  the runs reach;
- a stock, tally or number state keeps what its start value, its bounds and its rate read;
- a formula and a status keep what they read, and a share what its limit reads; its stock is an end
  of its flows;
- a sum check keeps its number states, and what its total and its tolerance read;
- outputs and checks keep the named states, formulas and statuses that they read;
- an actor keeps what it sees: a decision shows it.

An event that a part that stays counts or times stays too. When the structure leaves out each rule
that emits it, the event stays with no rule. It never happens in these runs, so its count stays 0:
`count(x) == 0` holds, and `since(x)` never does.

These parts always stay: each input, and each state, stock or tally that an option sets; a flow whose
rate is zero in every state that the runs reach, unless its entity goes; and each rule that the step
of an outcome that can happen names. `model.left_out[starts]` gives each part that a structure leaves
out, with the reason: `{section: {part: why}}`. `model.whole[starts]` keeps every part. The build
checks it, with the values of a run that starts from its start states, so a part that every run leaves
out is still checked.

A part that is left out never acts: it changes no number, event or status. Its evidence still shows in
the run's evidence trail, as possible but not exercised ([engine.md](engine.md#the-evidence-trail)).

## Studies

`evaluate_study(model, edits=None, numerical_settings=None, *, runs=None, play=None)` checks one edit
document as one transaction, then simulates the runs:

- `edits` is an edit document ([engine.md](engine.md#the-edit-document)), or None for the model as
  its files write it. It names `schema_version` (`napkin.SCHEMA_VERSION`) and the `model_hash` of the
  model.
- `numerical_settings` is a mapping of the solver's settings, such as `{'max_step': 0.5}`
  ([engine.md](engine.md#between-moments-the-solver)), or None for the defaults.
- `runs` names the runs to check and simulate. Without it, the study checks the edits on every run
  of the model, and simulates every run. With it, the study resolves the named runs only: an edit that
  holds in those runs is admitted. The checks of the document itself still apply.
- `play` (`{run, control, picks}`) plays one run of the study ([engine.md](engine.md#play)).

The result is a `StudyResult`. `admissible` is True when no diagnostic is an error, and `diagnostics`
lists every diagnostic, the warnings too. `runs` holds the simulated runs; a rejected study holds
none, and no run starts when one check fails. Each run is `{'resolved': …, 'trajectory': …}`: the
`Resolved` record of the run ([The structure](#the-structure)) and its trajectory. `decision` is the
decision that waits in a played run, or None. `model_hash`, `implementation_hash` and
`effective_edits` name what the study ran.

`sample_result(study, reporting_times=None)` gives the report of a study, as plain data
(`napkin/schema/report.schema.json`). Each run gives its outcomes at `final`, the end of the run, and
at each of the `reporting_times`, in hours. A report point is named by its number of hours, such as
`'4380.0'`.

```python
import napkin

model = napkin.load_scenario('examples/piano_tuners/model.scn')
edits = {
    'schema_version': napkin.SCHEMA_VERSION,
    'model_hash': model.model_hash,
    'set': {'tuners.staff': 4},
}
study = napkin.evaluate_study(model, edits)
print(study.admissible, study.diagnostics)
report = napkin.sample_result(study, reporting_times=[4380])
for point, row in report['runs']['base']['reporting_points'].items():
    print(point, row['values'], row['statuses'])

bad = {**edits, 'set': {'tuners.staff': 40}}
rejected = napkin.evaluate_study(model, bad)
print(rejected.admissible, rejected.runs, rejected.diagnostics)
print(napkin.sample_result(rejected)['status'])
```

```
True []
4380.0 {'tunings_done': 1949.0249915950546} {'tunings_done': 'estimated'}
final {'tunings_done': 3898.0499831901093} {'tunings_done': 'estimated'}
False {} [{'code': 'bounds', 'path': 'edits/set/tuners.staff', 'message': 'tuners.staff: 40 is outside [1, 10]', 'severity': 'error'}]
rejected
```

The report has `model_hash`, `implementation_hash`, `library_hash`, `schema_version`,
`engine_version`, `admissible`, `status` (`accepted`, `rejected` or `reporting_failure`), `scenario`
and `variant` (the names of the model's folders), `title`, `effective_edits`, `diagnostics` and
`runs`. Each run has:

| Key | What it holds |
| --- | --- |
| `label`, `options`, `starts`, `horizon` | The run's name, its options, its start-state options and its end, in hours. |
| `outcomes` | Each outcome's `label`, `unit`, `kind`, `status`, `scope` and `basis`. |
| `effective_inputs`, `numerical_settings` | The input values of the run, in their own units, and the solver's settings. |
| `reporting_points`, `samples` | Each outcome's value and status at each report point, by its name and by time. |
| `trace` | Each step of the run ([engine.md](engine.md#the-trace)). |
| `health` | The status of each entity at each report time. |
| `evidence` | The evidence trail of each outcome ([engine.md](engine.md#the-evidence-trail)). |
| `numerical_diagnostics`, `peaks` | The solver's diagnostics, and the largest value of each outcome. |

The status of an outcome is `estimated`, `unestimated` or `not_applicable`. An outcome that is not
estimated has no value (None), never zero. A numerical failure rejects the study: a report never
gives an outcome of a run that failed. In the evidence of a run, a part that the run's structure
leaves out shows as possible, not exercised ([The parts that cannot act](#the-parts-that-cannot-act)).

A study of a combination of options is a study of the derived model of `model.combination`. An edit
document is one transaction over the runs of the model. So `napkin run --option` and a `Session` with
`options` check the document on the whole model first, then give the derived model only the edits that
reach its run.

```python
import napkin

model = napkin.load_scenario('scenarios/water_controls_wipe/variants/juneau/model.scn')
derived = model.combination('early_kept', ['Delayed response'])
report = napkin.sample_result(napkin.evaluate_study(derived))
final = report['runs']['early_kept']['reporting_points']['final']
print(final['values']['deaths'], final['statuses']['deaths'], final['values']['economic_loss'])
```

```
None unestimated 0.003652344316725998
```

This model does not estimate deaths, so the report gives no value for them, never zero. Its economic
loss is in billions of US dollars at 2025 prices (`USD2025_bn`).

### A model with a table

A model with a table ([language.md](language.md)) builds and runs as every model does:
`load_scenario` writes each row out as a thing of its own. For a table of very many rows, the hybrid
core of the model keeps each class of rows as one family, and the engine runs a family without
writing its rows out ([engine.md](engine.md#tables-and-tiers)).

```python
from napkin.engine.timeline import reports
from napkin.model import hybrid

core = hybrid.compile('demo/model.scn')
report = reports.study_of(core, runs=None, times=[30.0], rows=['cells_4'], settings=None)
```

- `hybrid.compile(path)` gives the hybrid core, a `Hybrid`. It raises `ModelError` as
  `load_scenario` does. A diagnostic with the code `hybrid` names a model that the hybrid core does
  not hold; such a model runs from `load_scenario` only.
- `reports.study_of(core, runs, times, rows, settings)` runs the runs that `runs` names (default:
  every run) and gives their report, as plain data. `times` are the reporting times in hours, `rows`
  names rows of tables for their own detail, and `settings` is the numerical settings.
- The report has the envelope of `sample_result`. Each run has the shape `table_run` of
  `napkin/schema/report.schema.json`: the parts of the report of a run, with what the report says
  of the rows of a table by group (`groups`, `events`, and the `groups` of each entry of `health`).
  A group is one class of rows. `trace` has the steps of the things that no table makes and of the
  rows that `rows` names.
- A run that the engine stops rejects the report: `admissible` is False, `diagnostics` says why,
  and `runs` is empty.
- `study_of` takes no edit document and plays no run.

### Derivatives

```python
from napkin.engine import timeline
from napkin.engine.timeline import derivatives
from napkin.model import hybrid

core = hybrid.compile('examples/reservoir/model.scn')
plan = timeline.Plan.of(core, 'base')
report = derivatives.report(plan, values=None, inputs=['reservoir.inflow'])
item = report['derivatives']['reservoir.spilled.output']['reservoir.inflow']
```

- `derivatives.report(plan, values, inputs, settings=None, error=True)` gives the report of the
  derivatives of one run of a plan, as plain data: the document of `napkin derivatives --json`
  ([cli.md](cli.md#napkin-derivatives---json)) without the name of the run. A model with no table
  is its own hybrid core, so `hybrid.compile` and `Plan.of` take every model. `values` are values
  of inputs for this run, `inputs` names the inputs (default: every input), and `settings` is the
  numerical settings.
- Each derivative has its `value`, `unit`, `class`, `why` and `error`. The classes are `smooth`,
  `one-sided`, `undefined`, `unsupported` and `structurally zero`
  ([engine.md](engine.md#tables-and-tiers), "Derivatives"). A value is the derivative of the
  outcome in its own unit for one unit of the input, as the file writes the two.
- `error` is the distance of the value from that of a second run with tolerances a hundred times
  tighter. With `error=False` that run is not made, and each error is `None`.
- `timeline.run(plan, values, directions=inputs)` is the run itself: its `tangents` have the
  derivative of each output in execution units, its `notes` what it met that decides a class, and
  its `margins` the least margins of the run.

## Uncertainty

`evaluate_uncertainty(model, edits=None, settings=None, numerical_settings=None, *, runs=None,
times=None, run_samples=None, check_samples=None)` runs a Monte Carlo study
([engine.md](engine.md#monte-carlo-studies)). The central study comes first, with every check of a
study, and each distribution at its central value. Then each run that has a distribution, or an event
whose outcome goes by chance, draws its samples. Each sample is checked before any sample runs. A
sample that fails, in its check or in its run, rejects the whole study, and the result keeps no
sample.

- `settings` is a `SamplingSettings(samples=200, seed=0, method='random')` (`napkin.engine`):
  `samples` from 1 to 100,000, `seed` from 0 to 2^63 − 1, and `method` `random`, `latin` or
  `sobol` ([Estimators](#estimators)).
- An edit document can give an input a distribution, written as in a model file.
- `times` asks each sample for its outcomes at those times, in hours.
- `check_samples` and `run_samples` let a caller check and run the samples in other processes, or stop
  the study with `StudyCancelled`. `napkin sample` runs its samples in a pool of processes in this way
  ([engine.md](engine.md#the-spread)).

The result is an `UncertaintyResult`: `study` (the central study), `settings`, `admissible`,
`diagnostics`, and `samples` (`{run: {values, runs, rows, events}}`, each a list with one item for
each sample).

`uncertainty_report(result, reporting_times=None)` gives the report of the central study, as
`sample_result` gives it, with an `uncertainty` section: `settings`, and for each sampled run its
number of `samples`, the `events` (how many times each outcome of an event that goes by chance
happened), the `inputs` (each drawn input's `distribution` and its `draws`) and the `outcomes`.

```python
import napkin
from napkin.engine import SamplingSettings

model = napkin.load_scenario('examples/piano_tuners/model.scn')
result = napkin.evaluate_uncertainty(model, settings=SamplingSettings(samples=200, seed=0))
report = napkin.uncertainty_report(result)
spread = report['uncertainty']['runs']['base']
outcome = spread['outcomes']['tunings_done']
print(outcome['uncertain_inputs'])
final = outcome['points']['final']
print({key: round(value) for key, value in final.items() if isinstance(value, float)})
print(final['drivers'])
```

```
['tuners.rate']
{'central': 2924, 'mean': 2864, 'sd': 313, 'sem': 22, 'min': 2023, 'max': 3517, 'p5': 2316, 'p25': 2644, 'p50': 2874, 'p75': 3111, 'p95': 3355}
{'tuners.rate': 1.0}
```

These are the numbers that `napkin sample examples/piano_tuners` prints. Each outcome has its
`uncertain_inputs`, the drawn inputs that it can depend on, and its `points`: at each report point,
the central run's value (`central`), the mean, the standard deviation (`sd`) and its standard error
(`sem`), the minimum and maximum, the 5th, 25th, 50th, 75th and 95th percentiles, and the `drivers`,
the rank correlation of each uncertain input with the outcome. A summary is estimated only when the
outcome is estimated in the central run and in each sample. Otherwise it is
`{'estimated': False, 'statuses': […]}`. With `reporting_times`, each outcome also has its `series`:
its percentiles at each of those times.

The spread of a result is the spread of the inputs that the model assumes, carried through the model.
It is not a measured interval.

### Estimators

`napkin.engine.estimators` and `napkin.engine.expectations` have other estimators of a study
([engine.md](engine.md#estimators) says what each assumes). A caller asks for each by name.

```python
import napkin
from napkin.engine import SamplingSettings, evaluate_uncertainty, estimators, expectations

model = napkin.load_scenario('examples/piano_tuners/model.scn')
settings = SamplingSettings(samples=64, seed=0, method='sobol')  # 8 blocks of 8 points
result = evaluate_uncertainty(model, None, settings)
controlled = expectations.controlled(result, 'base')
weighted = expectations.weighted(model, 'base', None, settings)
slopes = expectations.derivatives(model, 'base', ['tuners.staff'], None, settings)
```

- `SamplingSettings(samples, seed, 'sobol', replicates=8)`: scrambled Sobol' points in independent
  blocks. The samples are `replicates` blocks of a power of two each, and the standard error of
  each summary of the report is that of the means of the blocks.
- `estimators.mean_interval(values, confidence=0.95)`, `estimators.replicate_interval(blocks)` and
  `estimators.quantile_interval(values, p)` give an interval from plain numbers:
  `{mean, se, low, high, n}`, and for a quantile `{low, high, ranks, coverage}` or `None` with too
  few samples. `estimators.until_narrow(sample, p, width)` makes a study larger until the interval
  of a quantile is narrow enough, and keeps its confidence.
- `expectations.weighted(model, run, edits=None, settings=None, numerical_settings=None, *,
  limit=4096, confidence=0.95)` gives the mean of each outcome at the horizon with the outcomes of
  the chance events weighted: `{admissible, run, samples, paths, settings, confidence, outcomes,
  events}`. `outcomes[name]` is `{estimated, mean, se, low, high, sd, unit}`; `se`, `low` and
  `high` are `None` when nothing but the outcomes is drawn. A study that is refused has
  `admissible` false and its `diagnostics`.
- `expectations.controlled(result, run, *, coefficients=None, numerical_settings=None,
  confidence=0.95)` gives the mean of each outcome of a finished Monte Carlo study with the linear
  control: `{run, samples, confidence, outcomes, left_out}`. `outcomes[name]` is `{estimated,
  mean, se, low, high, n, plain, coefficients}`, `plain` being the mean with no control.
- `expectations.derivatives(model, run, inputs=None, edits=None, settings=None,
  numerical_settings=None, *, exceed=None, quantiles=None, limit=4096, confidence=0.95)` gives the
  derivative of the mean of each outcome by each input: `{admissible, run, samples, paths,
  settings, confidence, inputs, outcomes, derivatives}`. `derivatives[outcome][input]` is `{label,
  why, value, se, low, high, unit, one_sided}`; the labels are `zero by the structure`, `sample
  mean`, `branch weighting` and `unsupported`. With `exceed` and `quantiles` a pair that has an
  estimate also has `exceedance` and `quantile`: `{value, se, low, high, n, at, density,
  bandwidth, slower}`.
- `timeline.run(plan, values, outcomes=places)` and `run_sample(model, run, values, None, times,
  luck, outcomes=places)` are a run with given outcomes; `estimators.every_path(run)` runs every
  path.

## Session

`Session(model, run, *, control, options=(), edits=None, picks=(), settings=None, resolver=None)`
plays one run of a model. The decisions of the actors that `control` names wait for a pick, and the
model takes every other decision ([engine.md](engine.md#play)). `napkin play` uses a session.

- `control`: who picks the decisions of each actor or choice, `{THING: 'reader' | 'agent' |
  'chance'}`. A key is an actor, a set of copies or one choice, `actor.event`.
- `options`: options in place of the run's own of their groups. The session plays the model of that
  combination (`model.combination`). It checks the edit document on the whole model first, then keeps
  what reaches the run.
- `edits`: an edit document, or None.
- `picks`: a log to go on from, `[{event, outcome, t, by, reason}]`.
- `settings`: the solver's settings, as for `evaluate_study`.
- `resolver`: a function `resolver(decision) -> (outcome, reason)`, which answers each decision while
  the run is simulated, or gives None to stop the run there.

A session has `base` (the model as given), `model` (the model of the run), `run`, `options`,
`control`, `edits`, `settings`, `picks` (the log), `decision` (the decision that waits, or None),
`trajectory` (the simulated run of the last `advance()`) and `warnings` (the diagnostics of the last
`advance()` that are not errors).

- `advance()` simulates the run from t = 0 with the log, to the first decision that neither the log
  nor the resolver answers, or to the end of the run. It gives that decision (also `decision`), or None
  when the run is finished.
- `pick(outcome, reason=None)` answers the decision that waits. The log takes the pick, and the next
  `advance()` goes on from it.
- `result(times=None)` gives the report of the finished run, as `sample_result(evaluate_study(model,
  edits, settings, runs=[run], play=…), reporting_times=times)` gives it.
- `log()` gives the play log: `schema_version`, `kind` (`play`), the context of the play, `scenario`,
  `variant` and `picks`. The context is `model_hash`, `implementation_hash`, `run`, `options`,
  `control`, `edits` and `numerical_settings`.
- `save(path)` writes the log as JSON. It replaces the file whole or not at all.
- `Session.load(path, model, run, *, control, options=(), edits=None, settings=None, resolver=None)`
  gives the session that goes on from a saved log. The log must have the same context.

Step by step, each pick simulates the run again from t = 0. The engine keeps no paused run, so the
same log gives the same run, bit for bit:

```python
import napkin

model = napkin.load_scenario('examples/reservoir/model.scn', admission_runs=['base'])
session = napkin.Session(model, 'base', control={'operator': 'reader'})
decision = session.advance()
print(decision['t'], decision['event'], decision['view'], decision['units'])
print([(item['name'], item['available']) for item in decision['outcomes']])
try:
    session.result()
except ValueError as error:
    print(error)
try:
    session.pick('close')
except ValueError as error:
    print(error)
session.pick('wait', 'The storm ends soon.')
print(session.advance())
final = session.result()['runs']['base']['reporting_points']['final']
print(final['values'])
print(session.picks)
```

```
40.00000000000081 operator.decide {'reservoir.water': 0.7} {'reservoir.water': 'fraction'}
[('open', True), ('wait', True)]
The log has no pick for operator.decide at t = 40 h: the run is not finished
'close' is not an outcome of operator.decide that can happen now: pick one of open, wait
None
{'reservoir.spilled.output': 0.0, 'reservoir.risk_time.output': 40.00000000328194}
[{'event': 'operator.decide', 'outcome': 'wait', 't': 40.00000000000081, 'by': 'reader', 'reason': 'The storm ends soon.'}]
```

Live, a resolver answers each decision while the run is simulated, in one simulation. The session
logs each answer before the engine takes it. `save` and `load` keep the log with its context:

```python
import tempfile
from pathlib import Path

import napkin
from napkin.session import OtherContext


def operator(decision):
    """The reader's rule: wait while the water is below 80% of the capacity."""
    if decision['view']['reservoir.water'] < 0.8:
        return 'wait', 'The water is below the risk level.'
    return 'open', 'The water is at the risk level.'


model = napkin.load_scenario('examples/reservoir/model.scn', admission_runs=['base'])
live = napkin.Session(model, 'base', control={'operator': 'reader'}, resolver=operator)
print(live.advance())
print([(item['outcome'], item['reason']) for item in live.picks])

log = Path(tempfile.mkdtemp()) / 'play.json'
live.save(log)
again = napkin.Session.load(log, model, 'base', control={'operator': 'reader'})
print(again.advance(), again.result() == live.result())
try:
    napkin.Session.load(log, model, 'base', control={'operator': 'agent'})
except OtherContext as error:
    print(error.fields)
```

```
None
[('wait', 'The water is below the risk level.')]
None True
('control',)
```

A session refuses what a study refuses, with the same diagnostics:

| Call | Refuses | With |
| --- | --- | --- |
| `Session(…)` | Numerical settings that are not valid; options that the model does not have or cannot combine; with options, an edit document that fails on the whole model. | `ModelError` |
| `advance()` | An edit document that fails; a run that is not in the model or not admitted (`run`, `admission_scope`); a `control` that names no actor or choice of the run, or a log that is not a list of picks (`play`); a pick that does not answer its decision (`pick`); a blocking check of the inputs; a run that fails. | `ModelError` |
| `advance()` with a resolver | An answer that is not `(outcome, reason)` or None, or an outcome that cannot happen now. An exception of the resolver goes up as it is, and the log keeps each pick before it. | `ValueError` |
| `pick(…)` | A pick when no decision waits, or an outcome that cannot happen now. | `ValueError` |
| `result()` | A log that leaves a decision without a pick. | `ValueError` |
| `Session.load(…)` | A file that is not a play log of schema `0.0.1`, or whose picks are not a list of objects; a log of another context. | `ValueError`; `OtherContext` names each field that differs (`fields`) |

So a log replays only with the same model, engine, run, options, control, edits and numerical
settings. A log of another version of the engine has another `implementation_hash`, and `load`
refuses it.

## Names

The structure uses the names of the file. A name in an expression is an identifier, so a copy of a
set has a name of its own. The examples are from `examples/reservoir`, `examples/piano_tuners` and the
catalogue's `iv_fluid_shortage` and `water_controls_wipe:juneau`.

| Part | Name | Example |
| --- | --- | --- |
| Entity (a thing of the file) | its name in the file | `reservoir` |
| Copy k of a set, from 1 | `set_k`: the file writes `set.k` | `pumps_2`, for `pumps.2` of a set `pumps: Pump * 3` |
| Input, fixed value, stock, tally, number state, named state, formula | `entity.value` | `reservoir.inflow`, `reservoir.water`, `reservoir.gate` |
| Status of an entity | `entity.health` | `juneau.health` |
| Rule of an event, and the event of its trigger | `entity.event`; `set_k.event` for an event of a copy | `operator.decide` |
| The start | `entity.start`: the rule of the event `start`, which fires first at t = 0 | `attacker.start` |
| Outcome of an event | `entity.event.outcome`; an event whose lines are under it directly has the one outcome `done` | `operator.decide.open`, `manufacturer.stops_shipping.done` |
| Flow | `entity.flow`, of the entity that declares it | `reservoir.spill` |
| Pair k of a flow of several pairs | `entity.flow.k`, from 0; the pairs' coupling group is `entity.flow` | `juneau.repair.0` |
| Share | `entity.share_<stock>`: the group of the flows that take from the stock | `parts.share_spares` |
| Check of an entity (`assert`) | `Name.i`: its position among the checks of its template, or of the entity made without one, from 0; `Name.i.entity` when the template has more than one entity | `parts.0`, `Hospitals.0`, `CrewPool.0.controls_crew` |
| Check of the top level | `simulate.i` | `simulate.0` |
| Output of a value | `entity.value`; `entity.value.output` when the value is also a stock, tally or number state, because the run holds that value as `entity.value` | `manufacturer.output_loss`, `reservoir.spilled.output` |
| Top-level output | its name | `tunings_done` |
| Link | the part that it reaches, under the entity that reaches it | `links['attacker']['platform.access']` |
| Run | as written | `base`, `early_kept` |

An edit document names an input as `entity.value`. A copy's input can also be written
`set.k.value`.

## Views

The views give what a program needs to show the actors and the instances of a model, so that it
never retypes the model's names. `napkin compile` and `napkin play` list the actors with `actors`,
and `napkin draw` reads both views.

- `actors(model)` gives each thing that sees, in the order of the file: `{name, title, role,
  template, copy, sees, choices}`. `sees` lists its facts as the file writes them. Each choice, an
  event marked `choice` ([language.md §2.7](language.md#27-actors)), is `{event, label, outcomes:
  [{name, label}]}`, and `event` is the event of the structure (`entity.event`).
- `instances(model, template)` gives each instance of a template, copies included, in the order of the
  file: `{name, title, copy, links}`. Each link maps to the entity, or the list of entities, that the
  instance binds.

```python
import napkin

model = napkin.load_scenario('examples/reservoir/model.scn')
(operator,) = napkin.actors(model)
print({key: value for key, value in operator.items() if key != 'choices'})
(choice,) = operator['choices']
print(choice['event'], [item['name'] for item in choice['outcomes']])

juneau = napkin.load_scenario('scenarios/water_controls_wipe/variants/juneau/model.scn')
for item in napkin.instances(juneau, 'CrewPool'):
    print(item)
```

```
{'name': 'operator', 'title': 'Operator', 'role': 'operator', 'template': None, 'copy': None, 'sees': ['reservoir.water']}
operator.decide ['open', 'wait']
{'name': 'controls_crew', 'title': 'Controls crew', 'copy': None, 'links': {'utilities': ['juneau']}}
{'name': 'field_crew', 'title': 'Field crew', 'copy': None, 'links': {'utilities': ['juneau']}}
```

## Dynamics

`napkin.dynamics` analyses the continuous dynamics of one run: where its quantities come to rest,
whether they stay there, how the rest states move as an input or the time changes, from which states
a run reaches each one, and which inputs move a result most. It reads the engine's own field, so it
analyses the equations that the engine runs. It gives data only. It changes no model and no result.

### The field

`vector_field(model, run, values=None, *, state=None, store=None)` gives the field of a run at its
start: the rates of its active quantities, in execution units per hour. `values` gives inputs other
values, in their own units. `state` gives the quantities other start values, and `store` the
discrete values, in execution units.

- The active quantities (`names`) are those that a flow or a tally changes and that a rate, a flow
  rate or a capacity reads. The others that change, such as a tally that counts, are `passive`: no
  rate reads them, so they have no rest state.
- The named states, event counts and times, and the number states that only rules set, keep their
  values. No rule fires.
- The field is the field inside the bounds: no bound acts. The capacities of shares and the couplings
  still apply. `at_bound(x)` names each quantity within its tolerance of a bound.
- `field(x, t)` gives the rates at the active values `x` and the time `t`, in hours. `jacobian(x, t)`
  gives the derivative by central differences. `one_sided(x, t)` gives the forward and the backward
  derivatives, with the columns where the field has a kink. A state where a rate is negative or not
  finite raises `OutsideDomain`.

### Equilibria and stability

`equilibria(field, *, t=0, starts=32, seed=0, box=None)` looks for rest states from the run's start
and from `starts` points that it draws with the seed. It gives each distinct `Equilibrium` once, with
its `state`, its `eigenvalues` and its class. `newton(field, x0)` is the search from one point, and
`equilibrium_at(field, x)` classifies one state.

- **The search.** Newton's method comes first, with a line search. Where it stalls, at a kink of
  `min()` or `max()` or at a local minimum of the residual, implicit steps of the flow follow its path
  (pseudo-transient continuation; Kelley and Keyes, 1998). These steps lead to the stable equilibria,
  so the search finds a saddle or an unstable equilibrium mainly from starts where Newton's method
  converges.
- **Stability.** The eigenvalues of the derivative, per hour, give the class: `stable` when every real
  part is below zero, `unstable` when every one is above zero, and `saddle` for both. A real part
  within 1e-7 of the largest eigenvalue's size makes it `nonhyperbolic`: the linear part does not
  decide.
- **Neutral modes.** Where the rest states make a line or a surface, as where the field fixes only a
  total of some quantities, each direction along it is a neutral mode (`neutral`, `neutral_modes`).
  The class comes from the other directions (`transverse`).
- **Kinks.** At a kink of `min()` or `max()`, `sides` holds the forward and the backward side, each with
  its eigenvalues and its class. The equilibrium takes the class of its least stable side. Across a
  kink the linear part is a guide only, and a run of the engine decides ([Basins](#basins)).

A rate per year is 8,760 times a rate per hour.

### Branches, folds and Hopf points

`continue_equilibrium(model, run, parameter, span, *, start=None)` follows one branch of rest states
as `parameter` moves from `span[0]` to `span[1]`. The parameter is an input, in its own unit, or
`'t'`, the time at which the field is read. The method is pseudo-arclength continuation, so the
branch goes through a fold and turns back. The `Branch` has its `points`, each with its state, its
eigenvalues and its class, its `folds`, its `hopf` points, and `end`, the reason that it stops.

- **A fold** is where the branch turns back in the parameter. On one side two rest states exist; on the
  other side none. Where a stable branch ends at a fold, a run that follows it jumps to another rest
  state: a threshold that comes from the dynamics.
- **A Hopf point** is where a pair of complex eigenvalues crosses zero: the rest state gives its
  stability to an oscillation, of `frequency` per hour.
- **A corner** is a kink of the field where no direction moves the parameter. The branch steps over it
  in the parameter alone, and it looks for no fold or Hopf point across it.
- **The end** is one of `span`, `bound` (a quantity reaches a bound), `inadmissible` (the model rejects
  a value), `step`, `points` or `kink`.

`fold_curve(model, run, parameter, span, second, grid)` follows a branch for each value of a second
input. The folds of each row are the edges of the region where the run has several rest states.

### Basins

`threshold(evaluate, classify, low, high, *, tol)` finds, by bisection, the value at which the class
of a result changes. `input_threshold(model, run, name, low, high, classify, *, tol)` changes an
input of a run, and `classify` reads the completed run of a study, `{resolved, trajectory}`.
`state_threshold(model, run, quantity, low, high, classify, *, tol)` changes the start value of a
quantity, and `classify` reads the trajectory. Each evaluation is a real run of the engine, with
every check of a study. So a threshold rests on the dynamics as they run, not on the linear part at a
rest state.

```python
from napkin import dynamics, load_scenario

model = load_scenario('examples/reservoir/model.scn')
field = dynamics.vector_field(model, 'base')
print(field.names, field.passive, field.start, field(field.start))
print(dynamics.equilibria(field, starts=8, seed=0))


def at_risk(run):
    """Whether the water was above the risk level at some time of the run."""
    trajectory = run['trajectory']
    return trajectory.env_at(trajectory.horizon)['reservoir.risk_time'] > 0


found = dynamics.input_threshold(model, 'base', 'operator.level', 0.5, 1, at_risk, tol=1e-4)
print(round(found.value, 4), found.below, found.above, found.evaluations)
```

```
('reservoir.water',) ('reservoir.spilled', 'reservoir.risk_time') [0.6] [0.0025]
[]
0.8 False True 15
```

The storm fills the reservoir at a constant rate, 0.06 of its capacity in a day (0.0025 in an hour),
so the water has no rest state. An operator who opens the spillway below 0.8 of the capacity keeps the
water below the risk level. From 0.8, the valley is at risk.

### Global sensitivity

`morris(f, factors, *, trajectories=20, levels=4, seed=0)` and `sobol(f, factors, *, samples, seed=0,
bootstrap=1000)` take any function `f({input: value}) -> number`. `model_function(model, run, output,
*, time=None)` makes one from an output of a run, at the end of the run by default.
`factors_from_model(model, names)` gives each input its range in the model.

- **Morris screening** moves one input at a time along random paths through a grid of the ranges.
  `mu_star`, the mean of the absolute effects, ranks the inputs (`ranking()`). `sigma`, their spread,
  shows effects that change along the ranges: curvature or interactions.
- **Sobol indices** split the variance of the result over the ranges. The `first` index of an input
  is the share that it causes alone (Saltelli et al., 2010). Its `total` index adds each interaction
  that it takes part in (Jansen, 1999). They cost N (k + 2) evaluations for k inputs and N rows. The
  intervals (`first_interval`, `total_interval`) and the standard errors come from a bootstrap over
  the rows.
- **The draws.** Each input draws from a stream of its own, named by the input and seeded by the seed.
  So one seed gives one result, and an extra input changes no index of the others.

```python
from napkin import dynamics, load_scenario

model = load_scenario('examples/piano_tuners/model.scn')
f = dynamics.model_function(model, 'base', 'tunings_done')
factors = dynamics.factors_from_model(model, ['tuners.rate', 'tuners.staff', 'tuners.need'])
screen = dynamics.morris(f, factors, trajectories=10, levels=4, seed=0)
print(screen.ranking(), screen.mu_star.round(), screen.evaluations)
indices = dynamics.sobol(f, factors, samples=256, seed=0, bootstrap=200)
for name, total, (low, high) in zip(indices.names, indices.total, indices.total_interval):
    print(f'{name}: total {total:.2f} ({low:.2f} to {high:.2f})')
print(indices.evaluations)
```

```
['tuners.staff', 'tuners.rate', 'tuners.need'] [4500. 6850. 4225.] 40
tuners.rate: total 0.23 (0.18 to 0.30)
tuners.staff: total 0.53 (0.42 to 0.65)
tuners.need: total 0.37 (0.27 to 0.50)
1280
```

The total indices add up to more than 1, because the tunings that the tuners do are the smaller of
the need and of what they can do: the inputs interact. The ranges are uniform, and a range that a
reader can explore is not a measured interval. So the indices say how a result depends on the ranges
that the model assumes, not how likely a result is. A study that rejects a sample raises an error: no
sample is left out.
