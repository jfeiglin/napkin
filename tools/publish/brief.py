"""The brief settings of the pages: `brief.toml`, an optional TOML file of the package.

A model's brief settings are found as its stylesheet is (`draw/style.py`, `lookup`): the file in the
folder of the model's file, which is a variant's own folder for a variant, else the one in the folder of
its package. The file that is found replaces the other whole, with its sweeps and its spreads, and the
edit documents of its spreads are in the folder `spreads/` beside it.

| Key | What it gives | Without it |
| --- | --- | --- |
| `show = [o, …]` | The outputs that the pages list, in order | Every output, in the order of the model file |
| `drivers = [e.f, …]` | The inputs that the brief lists | The inputs that the options set, in menu order (`controls`) |
| `featured = [r]` or `[r, c]` | The runs that the pages show first | The first run |
| `attack = "…"` | The name of the attack on the pages | No name: the pages describe the first move |
| `choice_group = "…"` | The group of options that holds the responses of the defenders; the pages name it | No group of responses |
| `[[sweep]]` | A row of the run table: one run with other values of some inputs (`Sweep`) | No run table |
| `[[spread]]` | A spread that the brief shows: runs sampled under the edit document `spreads/<id>.json` (`Spread`) | No spread |

The pages read only `brief.toml`, and the map of the system reads only `style.toml`
(`draw/style.py`). The model and its runs read neither: a sweep is an edit document that the run
tables (`publish/runs.py`) give to a study of the model, and a spread's edit document gives the
distributions of its inputs to the samples that the briefs calculate (`publish/briefs.py`).
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass

from napkin.draw.style import StyleError, beside, checked, lookup, names_of, problem, table, unknown
from napkin.engine.sampling import SamplingSettings
from napkin.model.ir import thaw
from napkin.model.model import input_name

BRIEF_FILE = 'brief.toml'
# The keys of `brief.toml` that hold a list of names, and those that hold a text.
BRIEF_KEYS = ('show', 'drivers', 'featured')
TEXT_KEYS = ('attack', 'choice_group')
# The key of the entries of the run table, `[[sweep]]`, and the keys of an entry, each required.
SWEEP = 'sweep'
SWEEP_KEYS = ('id', 'description', 'run', 'set')
# The key of the spreads that the brief shows, `[[spread]]`, and the keys of an entry: `id`, `runs`,
# `samples` and `seed` are required.
SPREAD = 'spread'
SPREAD_KEYS = ('id', 'description', 'runs', 'samples', 'seed', 'method', 'outputs')
# The folder beside the brief settings that holds the edit document of each spread: `spreads/<id>.json`.
SPREADS = 'spreads'
# The id of an entry: a word of lowercase letters, digits and `_` that starts with a letter.
IDENTIFIER = r'[a-z][a-z0-9_]*'


# ---- the brief settings: brief.toml --------------------------------------------------------------


@dataclass(frozen=True)
class Sweep:
    """A row of the run table (`[[sweep]]`): the run `run` with the values of the inputs that `set`
    gives (`values`, pairs of an input's name as edits write it and its value, in the order of the
    file), named `id` and described by `description`."""

    id: str
    description: str
    run: str
    values: tuple

    @property
    def edits(self):
        """The body of the sweep's edit document: its values, for every run (`set`)."""
        return {'set': dict(self.values)}


@dataclass(frozen=True)
class Spread:
    """A spread that the brief shows (`[[spread]]`): its runs (`runs`), sampled `samples` times with the
    seed `seed` by the method `method` (`settings`), under the edit document `spreads/<id>.json` beside
    the model file, which gives inputs their distributions. `outputs` names the outputs that the brief
    shows for the spread, or none for the brief's measures; `description` says what it is, or is None."""

    id: str
    description: str | None
    runs: tuple
    samples: int
    seed: int
    method: str
    outputs: tuple

    @property
    def settings(self):
        """The sampling settings of the spread (`SamplingSettings`)."""
        return SamplingSettings(self.samples, self.seed, self.method)


@dataclass(frozen=True)
class Brief:
    """The brief settings that `brief.toml` gives: the names of each list key, in order, and the text
    of each text key, or None for a key that the file leaves out; the sweeps (`[[sweep]]`) and the
    spreads (`[[spread]]`), in order; and the file (`origin`). Without a file, each key takes its
    default."""

    show: tuple | None = None
    drivers: tuple | None = None
    featured: tuple | None = None
    attack: str | None = None
    choice_group: str | None = None
    sweeps: tuple = ()
    spreads: tuple = ()
    origin: str | None = None


def read_brief(text, origin=BRIEF_FILE):
    """The brief settings of `text` (`Brief`): `show`, `drivers` and `featured`, each a list of
    names, `featured` of one run or two; `attack` and `choice_group`, each a nonempty text; each
    `[[sweep]]` (`read_sweeps`) and each `[[spread]]` (`read_spreads`). Another key, a value of
    another shape and a name written twice raise `StyleError`."""
    found, problems, settings = table(text, origin), [], {}
    unknown(found, (*BRIEF_KEYS, *TEXT_KEYS, SWEEP, SPREAD), origin, problems)
    for key in BRIEF_KEYS:
        listed = names_of(found[key], key, origin, problems) if key in found else None
        if key == 'featured' and listed is not None and not 1 <= len(listed) <= 2:
            problems.append(problem(origin, key, 'names one run, or a run and its comparison: ["r", "c"]'))
        settings[key] = listed
    for key in TEXT_KEYS:
        value = found.get(key)
        if value is not None and not (isinstance(value, str) and value.strip()):
            problems.append(problem(origin, key, f'holds a nonempty text, such as {key} = "…"'))
            value = None
        settings[key] = value
    settings['sweeps'] = read_sweeps(found.get(SWEEP), origin, problems)
    settings['spreads'] = read_spreads(found.get(SPREAD), origin, problems)
    if problems:
        raise StyleError(problems)
    return Brief(**settings, origin=origin)


def _entries(value, key, keys, origin, problems):
    """The entries of the array of tables `[[key]]`, each with its place (`key[i]`, from 0), or none
    with its problem: a value that is not a list of tables. An entry's key that is not in `keys` is a
    problem."""
    if value is None:
        return []
    if not isinstance(value, list) or not all(isinstance(entry, dict) for entry in value):
        problems.append(problem(origin, key, f'holds tables, each [[{key}]] with its keys'))
        return []
    out = []
    for position, entry in enumerate(value):
        where = f'{key}[{position}]'
        unknown(entry, keys, origin, problems, prefix=f'{where}.')
        out.append((where, entry))
    return out


def _text(entry, key, where, origin, problems, *, required=True):
    """The nonempty text of an entry's key, or None with its problem."""
    value = entry.get(key)
    if value is None and not required:
        return None
    if not (isinstance(value, str) and value.strip()):
        problems.append(problem(origin, f'{where}.{key}', f'holds a nonempty text, such as {key} = "…"'))
        return None
    return value


def _identifiers(entries, origin, problems):
    """The id of each entry (`IDENTIFIER`), or None with its problem; an id that two entries give is a
    problem of the second."""
    ids, seen = [], set()
    for where, entry in entries:
        value = entry.get('id')
        if not (isinstance(value, str) and re.fullmatch(IDENTIFIER, value, re.ASCII)):
            message = (
                'is a word of lowercase letters, digits and _ that starts with a letter, such as id = "a_1"'
            )
            problems.append(problem(origin, f'{where}.id', message))
            value = None
        elif value in seen:
            problems.append(problem(origin, f'{where}.id', f'{value} is the id of an entry above'))
        seen.add(value)
        ids.append(value)
    return ids


def read_sweeps(value, origin, problems):
    """The sweeps of the value of `[[sweep]]` (`Sweep`), in order: each has an `id` (`IDENTIFIER`,
    once), a `description`, the `run` that it changes and a nonempty table `set` of input names, each in
    quotes as an edit writes it (`"entity.value"`), and their values, each a finite number or true or
    false. Each problem goes to `problems`, and an entry with a problem gives no sweep."""
    entries = _entries(value, SWEEP, SWEEP_KEYS, origin, problems)
    out = []
    for (where, entry), identifier in zip(entries, _identifiers(entries, origin, problems), strict=True):
        before = len(problems)
        description = _text(entry, 'description', where, origin, problems)
        run = _text(entry, 'run', where, origin, problems)
        values = entry.get('set')
        if not isinstance(values, dict) or not values:
            problems.append(
                problem(origin, f'{where}.set', 'holds a table of inputs, such as set = {"a.b" = 1}')
            )
            values = {}
        for name, item in values.items():
            if isinstance(item, dict):
                message = (
                    f'writes the name of an input in quotes, such as "{name}.{next(iter(item), "b")}" = 1'
                )
                problems.append(problem(origin, f'{where}.set', message))
            elif not isinstance(item, (int, float)) or not math.isfinite(item):
                message = f'{name}: a sweep gives an input a finite number, or true or false, not {item!r}'
                problems.append(problem(origin, f'{where}.set', message))
        if len(problems) == before and identifier is not None:
            out.append(Sweep(identifier, description, run, tuple(values.items())))
    return tuple(out)


def _listed(entry, key, where, origin, problems, *, required=True):
    """The names of an entry's key, a nonempty list of names, or None with its problem."""
    if key not in entry and not required:
        return None
    listed = names_of(entry[key], f'{where}.{key}', origin, problems) if key in entry else ()
    if listed == ():
        problems.append(problem(origin, f'{where}.{key}', f'names one or more, such as {key} = ["a"]'))
        return None
    return listed


def read_spreads(value, origin, problems):
    """The spreads of the value of `[[spread]]` (`Spread`), in order: each has an `id` (`IDENTIFIER`,
    once), which names its edit document `spreads/<id>.json`; the `runs` that it samples, a nonempty
    list of names; and `samples`, `seed` and `method`, `random` by default, as `SamplingSettings` takes
    them (a `sobol` spread has the 8 blocks that the engine has by default). It may have a `description` and `outputs`, a nonempty list of names. Each problem goes to
    `problems`, and an entry with a problem gives no spread."""
    entries = _entries(value, SPREAD, SPREAD_KEYS, origin, problems)
    out = []
    for (where, entry), identifier in zip(entries, _identifiers(entries, origin, problems), strict=True):
        before = len(problems)
        description = _text(entry, 'description', where, origin, problems, required=False)
        runs = _listed(entry, 'runs', where, origin, problems)
        outputs = _listed(entry, 'outputs', where, origin, problems, required=False)
        settings = {'samples': entry.get('samples'), 'seed': entry.get('seed'), 'method': entry.get('method')}
        settings['method'] = 'random' if settings['method'] is None else settings['method']
        valid = SamplingSettings().record()
        for key, given in settings.items():
            # The engine checks each setting, one at a time, so that a problem names its key. The
            # method is last, with the samples of the entry when they are valid: `sobol` sampling
            # takes its samples in blocks.
            try:
                SamplingSettings(**{**valid, key: given})
                valid[key] = given
            except ValueError as exc:
                problems.append(problem(origin, f'{where}.{key}', str(exc)))
        if len(problems) == before and identifier is not None:
            out.append(Spread(identifier, description, runs, **settings, outputs=outputs or ()))
    return tuple(out)


def spread_document(model, spread):
    """The path of the edit document of a spread, `spreads/<id>.json` in the folder of the model's brief
    settings (`beside`), so that a spread and its edit document come from one folder; None for a model
    that has no file."""
    settings = beside(model, BRIEF_FILE)
    return None if settings is None else settings.parent / SPREADS / f'{spread.id}.json'


def brief_file(path):
    """The brief settings of the model file `path`, found without the model (`lookup`), or None."""
    return lookup(path, BRIEF_FILE)


def check_brief(brief, model):
    """The problems of brief settings against their model: `show` names outputs, `drivers` names
    inputs, `featured` names runs, the second the comparison of the first when it names two,
    `choice_group` names a group of the model's options, each sweep names a run, inputs, and an id
    that no run has, because the run table names each of its rows once, and each spread names runs and
    outputs, and has its edit document beside the brief settings. The engine checks the edit document
    when the spread runs, as it checks every edit document."""
    out = []
    if brief.choice_group is not None and brief.choice_group not in model.menu:
        out.append(problem(brief.origin, 'choice_group', f'{brief.choice_group} is not a group of options'))
    for name in brief.show or ():
        if output_name(name, model) is None:
            out.append(problem(brief.origin, 'show', f'{name} is not an output'))
    for name in brief.drivers or ():
        if input_name(name) not in model.inputs:
            out.append(problem(brief.origin, 'drivers', f'{name} is not an input'))
    featured = brief.featured or ()
    for name in featured:
        if name not in model.runs:
            out.append(problem(brief.origin, 'featured', f'{name} is not a run'))
    if len(featured) == 2 and all(name in model.runs for name in featured):
        run, other = featured
        if model.runs[other]['comparison_of'] != run:
            message = f'[{run}, {other}] names a run and its comparison, so {other} says versus {run}'
            out.append(problem(brief.origin, 'featured', message))
    for position, sweep in enumerate(brief.sweeps):
        where = f'{SWEEP}[{position}]'
        if sweep.id in model.runs:
            message = f'{sweep.id} is the name of a run, and the run table names each row once'
            out.append(problem(brief.origin, f'{where}.id', message))
        if sweep.run not in model.runs:
            out.append(problem(brief.origin, f'{where}.run', f'{sweep.run} is not a run'))
        for name, _ in sweep.values:
            if input_name(name) not in model.inputs:
                out.append(problem(brief.origin, f'{where}.set', f'{name} is not an input'))
    for position, spread in enumerate(brief.spreads):
        where = f'{SPREAD}[{position}]'
        for name in spread.runs:
            if name not in model.runs:
                out.append(problem(brief.origin, f'{where}.runs', f'{name} is not a run'))
        for name in spread.outputs:
            if output_name(name, model) is None:
                out.append(problem(brief.origin, f'{where}.outputs', f'{name} is not an output'))
        document = spread_document(model, spread)
        if document is not None and not document.is_file():
            message = (
                f'the edit document of the spread, {SPREADS}/{spread.id}.json beside this file, is missing'
            )
            out.append(problem(brief.origin, f'{where}.id', message))
    return out


def brief_of(model):
    """The brief settings of a model, read and checked: its `brief.toml` (`beside`: a variant's own, else
    its package's), or settings that each take their default when there is none. A file with a problem
    raises `StyleError`."""
    return checked(model, BRIEF_FILE, read_brief, check_brief, Brief())


def output_name(name, model):
    """The model's name of the output that the brief names, or None."""
    for candidate in (name, input_name(name)):
        if candidate in model.outputs:
            return candidate
    return None


def shown(brief, model):
    """The outputs that the pages list, by the model's names: `show`, or every output in the order of
    the model file."""
    return list(model.outputs) if brief.show is None else [output_name(name, model) for name in brief.show]


def controls(model):
    """The inputs that the options set, by the model's names, in menu order."""
    flat = {name: key for key, name in thaw(model.entities).items()}
    out = []
    for options in thaw(model.menu).values():
        for option in options:
            for entity in model.scenario.entities:
                for setting in entity.settings:
                    name = f'{flat.get(entity.name, entity.name)}.{setting.target}'
                    if setting.profile == option and name in model.inputs and name not in out:
                        out.append(name)
    return out


def drivers(brief, model):
    """The inputs that the brief lists: `drivers`, or the inputs that the options set (`controls`)."""
    return controls(model) if brief.drivers is None else [input_name(name) for name in brief.drivers]


def featured(brief, model):
    """The runs that the pages show first: `featured`, or the first run."""
    return list(brief.featured) if brief.featured is not None else list(model.runs)[:1]


__all__ = [
    'BRIEF_FILE',
    'BRIEF_KEYS',
    'IDENTIFIER',
    'SPREAD',
    'SPREADS',
    'SPREAD_KEYS',
    'SWEEP',
    'SWEEP_KEYS',
    'TEXT_KEYS',
    'Brief',
    'Spread',
    'StyleError',
    'Sweep',
    'brief_file',
    'brief_of',
    'check_brief',
    'controls',
    'drivers',
    'featured',
    'output_name',
    'read_brief',
    'read_spreads',
    'read_sweeps',
    'shown',
    'spread_document',
]
