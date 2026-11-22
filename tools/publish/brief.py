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
| `[[comparison]]` | A named run and the named run it is compared against | No authored pairs |
| `[[sweep]]` | A row of the run table: one run with other values of some inputs (`Sweep`) | No run table |
| `[[spread]]` | A spread that the brief shows: runs sampled under the edit document `spreads/<id>.json` (`Spread`) | No spread |

The pages read only `brief.toml`, and the map of the system reads only `style.toml`
(`draw/style.py`). The model and its runs read neither: a sweep is an edit document that the
publisher can give to a study of the model, and a spread's edit document gives the
distributions of its inputs to `--sample-spreads`.
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass

from napkin.draw.style import StyleError, beside, checked, lookup, names_of, problem, table, unknown
from napkin.engine.sampling import SamplingSettings
from napkin.engine.timeline.record import declaration, key_of, named
from napkin.model import semantic
from napkin.model.language.nodes import Text
from napkin.program import parts

from .. import catalogue

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
class Comparison:
    """A named run compared against another named run in the same study."""

    run: str
    against: str


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
        return SamplingSettings(self.samples, self.seed)


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
    comparisons: tuple[Comparison, ...] = ()


def read_brief(text, origin=BRIEF_FILE):
    """The brief settings of `text` (`Brief`): `show`, `drivers` and `featured`, each a list of
    names, `featured` of one run or two; `attack` and `choice_group`, each a nonempty text; each
    `[[comparison]]`, each `[[sweep]]` (`read_sweeps`) and each `[[spread]]` (`read_spreads`). Another key, a value of
    another shape and a name written twice raise `StyleError`."""
    found, problems, settings = table(text, origin), [], {}
    unknown(found, (*BRIEF_KEYS, *TEXT_KEYS, 'comparison', SWEEP, SPREAD), origin, problems)
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
    comparisons = []
    for where, entry in _entries(found.get('comparison'), 'comparison', ('run', 'against'), origin, problems):
        run = _text(entry, 'run', where, origin, problems)
        against = _text(entry, 'against', where, origin, problems)
        if run is None or against is None:
            continue
        pair = Comparison(run, against)
        if run == against:
            problems.append(problem(origin, where, 'a comparison requires two different runs'))
        elif pair in comparisons:
            problems.append(problem(origin, where, 'this comparison appears more than once'))
        else:
            comparisons.append(pair)
    settings['comparisons'] = tuple(comparisons)
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
    them. It may have a `description` and `outputs`, a nonempty list of names. Each problem goes to
    `problems`, and an entry with a problem gives no spread."""
    entries = _entries(value, SPREAD, SPREAD_KEYS, origin, problems)
    out = []
    for (where, entry), identifier in zip(entries, _identifiers(entries, origin, problems), strict=True):
        before = len(problems)
        description = _text(entry, 'description', where, origin, problems, required=False)
        runs = _listed(entry, 'runs', where, origin, problems)
        outputs = _listed(entry, 'outputs', where, origin, problems, required=False)
        settings = {'samples': entry.get('samples'), 'seed': entry.get('seed')}
        method = entry.get('method', 'random')
        if method != 'random':
            problems.append(
                problem(origin, f'{where}.method', f'the engine supports random sampling, got {method!r}')
            )
        valid = SamplingSettings().record()
        for key, given in settings.items():
            try:
                SamplingSettings(**{**valid, key: given})
                valid[key] = given
            except ValueError as exc:
                problems.append(problem(origin, f'{where}.{key}', str(exc)))
        if len(problems) == before and identifier is not None:
            out.append(
                Spread(identifier, description, runs, **settings, method=method, outputs=outputs or ())
            )
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


def comparisons_of(brief, model):
    """Authored pairs in order, including the comparison notes used by earlier packages."""
    if brief.comparisons:
        return brief.comparisons
    return tuple(
        Comparison(run.name, against)
        for run in model.declared.runs
        if (against := note_value(model, 'comparisons', run.name)) is not None
    )


def check_brief(brief, model):
    """The problems of brief settings against their model: `show` names outputs, `drivers` names
    inputs, `featured` names runs, the second the comparison of the first when it names two,
    `choice_group` names a group of the model's options, each sweep names a run, inputs, and an id
    that no run has, because the run table names each of its rows once, and each spread names runs and
    outputs, and has its edit document beside the brief settings. The engine checks the edit document
    when the spread runs, as it checks every edit document."""
    out = []
    runs = {item.name for item in model.declared.runs}
    if brief.choice_group is not None and brief.choice_group not in {
        item.group for item in model.declared.options
    }:
        out.append(problem(brief.origin, 'choice_group', f'{brief.choice_group} is not a group of options'))
    for name in brief.show or ():
        if output_name(name, model) is None:
            out.append(problem(brief.origin, 'show', f'{name} is not an output'))
    for name in brief.drivers or ():
        if not is_input(name, model):
            out.append(problem(brief.origin, 'drivers', f'{name} is not an input'))
    featured = brief.featured or ()
    for name in featured:
        if name not in runs:
            out.append(problem(brief.origin, 'featured', f'{name} is not a run'))
    pairs = comparisons_of(brief, model)
    for index, pair in enumerate(pairs):
        for key, name in (('run', pair.run), ('against', pair.against)):
            if name not in runs:
                out.append(problem(brief.origin, f'comparison[{index}].{key}', f'{name} is not a run'))
    if len(featured) == 2 and all(name in runs for name in featured):
        against, run = featured
        if Comparison(run, against) not in pairs:
            message = f'[{against}, {run}] must name a declared comparison of {run} against {against}'
            out.append(problem(brief.origin, 'featured', message))
    for position, sweep in enumerate(brief.sweeps):
        where = f'{SWEEP}[{position}]'
        if sweep.id in runs:
            message = f'{sweep.id} is the name of a run, and the run table names each row once'
            out.append(problem(brief.origin, f'{where}.id', message))
        if sweep.run not in runs:
            out.append(problem(brief.origin, f'{where}.run', f'{sweep.run} is not a run'))
        for name, _ in sweep.values:
            if not is_input(name, model):
                out.append(problem(brief.origin, f'{where}.set', f'{name} is not an input'))
    for position, spread in enumerate(brief.spreads):
        where = f'{SPREAD}[{position}]'
        for name in spread.runs:
            if name not in runs:
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


def note_value(model, first, *path):
    """The authored value of a note such as `comparisons.other` or `not_estimated.total.reason`."""
    notes = model.declared.notes
    for key in (first, *path):
        note = next((item for item in notes if item.key == key), None)
        if note is None:
            return None
        notes = note.notes
    return note.value.value if isinstance(note.value, Text) else note.value


def value_note(model, section, name, field):
    """A reporting note about a value, including a member's note inherited from its template."""
    value = note_value(model, section, *name.split('.'), field)
    if value is not None:
        return value
    key = key_of(model.program, name)
    if key.owner and '#' not in key.owner:
        template, _ = model.program.member(key.owner)
        return note_value(model, section, template.name, *key.steps, field)
    return None


def is_input(path, model):
    """Whether an edit can name this input of the root, a member, or every instance of a template."""
    owner, mark, field = path.partition('.instances.')
    if mark:
        return (
            isinstance(model.declared.part(owner), semantic.DeclaredTemplate)
            and getattr(model.declared.part(f'{owner}.{field}'), 'kind', None) == parts.INPUT
        )
    try:
        found = declaration(model.program, key_of(model.program, path))
    except KeyError:
        return False
    return found.what in ('value', 'distribution') and getattr(found.part, 'kind', None) == parts.INPUT


def output_name(name, model):
    """A reportable path, or a value documented with a reason for having no estimate."""
    key = key_of(model.program, name)
    try:
        named(model.program, key)
    except KeyError:
        if value_note(model, 'not_estimated', name, 'reason') is None:
            return None
    return name


def reported_paths(model):
    """Paths identified by reporting or unestimated notes, expanding notes on a template to its members.

    A former output without any reporting metadata leaves no note. Only an authored `show` or a
    migration manifest can identify such a prior selection.
    """
    sections = [note for note in model.declared.notes if note.key in ('reporting', 'not_estimated')]
    if not sections:
        return None
    paths = {}
    for section in sections:
        fields = {'about', 'scope', 'category', 'lag'} if section.key == 'reporting' else {'reason', 'label'}
        for note in section.notes:
            if any(item.key in fields and item.value is not None for item in note.notes):
                paths[note.key] = None
                continue
            if isinstance(model.declared.part(note.key), semantic.DeclaredTemplate):
                owners = [member.id for member in model.program.template(note.key).members]
            else:
                owners = [note.key]
            for field in note.notes:
                for owner in owners:
                    paths[f'{owner}.{field.key}'] = None
    return list(paths)


def shown(brief, model, record=None):
    """Authored `show`, then reporting notes if present, then every public path of a completed record."""
    if brief.show is not None:
        return list(brief.show)
    paths = reported_paths(model)
    if paths is not None:
        return paths
    from napkin.commands.run import named as named_values

    if record is None:
        record = catalogue.completed_study(model, runs=[None])[None]
    return named_values(model, record)


def controls(model):
    """The declared input paths that the options set, in menu and setting order."""
    return list(
        dict.fromkeys(setting.path for option in model.declared.options for setting in option.settings)
    )


def drivers(brief, model):
    """The inputs that the brief lists: `drivers`, or the inputs that the options set (`controls`)."""
    return controls(model) if brief.drivers is None else list(brief.drivers)


def featured(brief, model):
    """The runs that the pages show first: `featured`, or the first run."""
    if brief.featured is not None:
        return list(brief.featured)
    return [model.declared.runs[0].name if model.declared.runs else None]


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
    'Comparison',
    'Spread',
    'StyleError',
    'Sweep',
    'brief_file',
    'brief_of',
    'check_brief',
    'comparisons_of',
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
