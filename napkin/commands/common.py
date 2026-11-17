"""What the commands of `napkin` share (napkin/cli.py): the target of a command, the model it loads,
its runs, the values of its options, the run store, how it prints diagnostics and numbers, and its
JSON.

At import time this module reads only the standard library and `napkin.paths`, so `napkin --help`
loads no engine. Each function imports the engine when it runs. The engine does every check: these
functions read the command line and give the engine what it reads, and a model that the engine
refuses is a `Failed` with the engine's own diagnostics.

Two exceptions end a command, and `cli.main` catches both:

- `UsageError`: the command line is wrong (exit 2), such as an unknown variant or option;
- `Failed`: the engine gives diagnostics (exit 1), such as a model that does not compile.
"""

from __future__ import annotations

import json
import math
import os
import re
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path

from .. import paths

# What a TARGET is, for the messages that refuse one.
WHAT = (
    'a TARGET is a scenario folder (its model.scn starts with `scenario`) or that file, '
    'or a variant folder (variants/NAME/) or its model.scn'
)
# A value of `--set` that is not JSON: a bare word, which is text.
WORD = re.compile(r'[A-Za-z][A-Za-z0-9_-]*')
# A time of `--at`: a number, then its unit.
TIME = re.compile(r'([+-]?(?:[0-9]+(?:\.[0-9]*)?|\.[0-9]+)(?:[eE][+-]?[0-9]+)?)\s*(.*)', re.DOTALL)
# The parts of a report that each study gives for itself; every other part of its envelope names the
# model and the engine, which one command keeps for each of its studies (`merged`).
PER_STUDY = ('admissible', 'status', 'effective_edits', 'diagnostics', 'runs')


class UsageError(Exception):
    """The command line is wrong: `cli.main` prints the command's usage and the message, and exits 2."""


class Failed(Exception):
    """The engine gives diagnostics: `cli.main` prints `message`, if any, then each diagnostic
    (`show_diagnostics`), and exits 1. `diagnostics` is a list of the engine's diagnostics: dicts with
    a `message` and, where known, `severity`, `file`, `line`, `column`, `path` and `run`."""

    def __init__(self, diagnostics, message=None):
        self.diagnostics = list(diagnostics)
        self.message = message
        super().__init__(message or f'{len(self.diagnostics)} diagnostics')


# --- The target of a command ------------------------------------------------------------------


@dataclass(frozen=True)
class Target:
    """One model that a TARGET names.

    - `package`: the folder of the package;
    - `entry`: the model's entry file, the package's `model.scn` or the variant's;
    - `name`: the model's name, as its folders give it (`paths.names_of`): `package`, or
      `package:variant` for a variant;
    - `variant`: the variant's name, or None for the package's own model;
    - `variants`: the names of every variant of the package, sorted.
    """

    package: Path
    entry: Path
    name: str
    variant: str | None
    variants: tuple[str, ...]


def add_variant(parser, text='the variant of the package (needed when the package has several)'):
    """Give a command's parser `--variant NAME` (`args.variant`, None when not given)."""
    parser.add_argument('--variant', metavar='NAME', help=text)


def add_target(parser):
    """Give a command's parser the positional TARGET (`args.target`, `.` when not given)."""
    parser.add_argument(
        'target',
        nargs='?',
        default='.',
        metavar='TARGET',
        help="a scenario folder or its model.scn, or a variant's (default: .)",
    )


def targets(text='.', variant=None):
    """The models that a TARGET and `--variant` name, in order: a list of `Target`.

    TARGET (`text`) is a package's folder or its `model.scn`, or a variant's folder or its
    `model.scn`. A package without variants is one model. A package with variants runs as its
    variants (its main file is part of each one), so it gives each variant, by name, unless `variant`
    names one. A variant's folder gives that variant. Raises UsageError for a path that is no TARGET
    (a missing path, a folder without `model.scn`, a module file or any other file), for an unknown
    variant (with the closest names) and for a `variant` that a variant's TARGET contradicts."""
    path = Path(os.path.abspath(text))
    if path.is_dir():
        entry = paths.entry(path)
        if not entry.is_file():
            raise UsageError(f'{text} holds no {paths.ENTRY}: {WHAT}')
    elif path.is_file():
        if path.name != paths.ENTRY:
            kind = 'a module of a package' if path.suffix == '.scn' else 'not a model file'
            raise UsageError(f'{text} is {kind}: {WHAT}')
        entry = path
    else:
        raise UsageError(f'{text} does not exist: {WHAT}')
    package = paths.package_of(entry)
    scenario, own = paths.names_of(entry)
    found = paths.variants(package)
    names = tuple(found)

    def target(entry, name):
        return Target(package, entry, scenario if name is None else f'{scenario}:{name}', name, names)

    if own is not None:
        if variant is not None and variant != own:
            raise UsageError(f'{text} is the variant {own} of {scenario}, not {variant}')
        return [target(entry, own)]
    if variant is not None:
        if variant not in found:
            if not found:
                raise UsageError(f'{scenario} has no variants, so --variant {variant} names none')
            raise UsageError(f'{variant} is not a variant of {scenario}' + _close(variant, found))
        return [target(found[variant], variant)]
    if found:
        return [target(file, name) for name, file in found.items()]
    return [target(entry, None)]


def one_target(text='.', variant=None):
    """The one model that a TARGET and `--variant` name (`targets`). For a package with several
    variants and no `variant`, raises UsageError with each variant's name and title, so the command
    lists the variants and stops."""
    found = targets(text, variant)
    if len(found) == 1:
        return found[0]
    width = max(len(item.variant) for item in found)
    rows = [f'  {item.variant:<{width}}  {_variant_title(item.entry) or ""}'.rstrip() for item in found]
    head = f'{found[0].name.partition(":")[0]} has {len(found)} variants: pick one with --variant NAME'
    raise UsageError('\n'.join([head, *rows]))


def _variant_title(entry):
    """The title of a variant: the text of its first declaration, `variant "Title"`, which can run over
    several lines; None when the file starts with no such line."""
    try:
        text = Path(entry).read_text(encoding='utf-8')
    except (OSError, UnicodeDecodeError):
        return None
    rows = text.split('\n')
    for k, row in enumerate(rows):
        if not row.strip() or row.lstrip().startswith('#'):
            continue
        found = re.match(r'variant +"([^"]*)"', '\n'.join(rows[k:]))
        return ' '.join(found.group(1).split()) if found else None
    return None


def _close(name, names):
    """`; did you mean …?` with the names of `names` closest to `name`, or ''."""
    from ..model.ir import close_names

    return close_names(name, names)


def listed(names):
    """Names in a sentence: `a`, `a and b`, `a, b and c`."""
    names = [str(name) for name in names]
    return names[0] if len(names) == 1 else f'{", ".join(names[:-1])} and {names[-1]}'


# --- The model ----------------------------------------------------------------------------------


def load(target, runs=None):
    """The model of a `Target`: `load_scenario(target.entry, admission_runs=runs)`. With `runs`, only
    those runs are checked numerically (D-30; `scope_note`). Raises Failed with the engine's
    diagnostics for a model that does not compile, and with a diagnostic that keeps the file (and the
    line, where known) for a file that cannot be read: a missing file, a JSON file that is not valid,
    or a file that is not UTF-8 text."""
    from ..model import load_scenario

    with _read(target):
        return load_scenario(target.entry, admission_runs=runs)


def table_core(target):
    """The hybrid core of the model of a `Target` that has instances from a table
    (`model/hybrid.py`): what `napkin run` runs of such a model. None for a model with no table.
    None also for a model with a table that the hybrid core does not hold; the second value then
    says why, and the model runs with each row written out. Raises Failed as `load` does."""
    from ..model import ModelError, hybrid
    from ..model.language import front

    with _read(target):
        file, _ = front.load(Path(target.entry))
        if not hybrid.classes(file):
            return None, None
        try:
            return hybrid.compile(target.entry), None
        except ModelError as exc:
            if exc.diagnostics and all(item.get('code') == 'hybrid' for item in exc.diagnostics):
                return None, exc.diagnostics[0]['message']
            raise


@contextmanager
def _read(target):
    """Read or build the model of a `Target` in the block: what the engine raises becomes Failed, with
    its diagnostics (`load`)."""
    from ..model import ModelError, SourceError

    try:
        yield
    except ModelError as exc:
        raise Failed(exc.diagnostics) from None
    except SourceError as exc:
        raise Failed([source_diagnostic(exc)]) from None
    except OSError as exc:
        raise Failed([os_diagnostic(exc, target.entry)]) from None
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise Failed([_unreadable(target, exc)]) from None


def source_diagnostic(exc):
    """The diagnostic of a `SourceError`: its message, its file and its line (none for line 0)."""
    text, line = str(exc), exc.line or None
    prefix = f'{exc.path}:{line}: ' if line else f'{exc.path}: '
    item = _diagnostic('source', text[len(prefix) :] if text.startswith(prefix) else text, file=exc.path)
    return {**item, 'line': line} if line else item


def os_diagnostic(exc, file):
    """The diagnostic of an OSError on `file`: the reason, and the file that it names."""
    return _diagnostic('file', exc.strerror or str(exc), file=str(exc.filename or file))


def _diagnostic(code, message, **extra):
    return {'code': code, 'path': '', 'message': str(message), 'severity': 'error', **extra}


def _unreadable(target, exc):
    """The diagnostic of a JSON or text error that the engine gives without its file: the first file of
    the model that is not UTF-8 text, or, of its JSON files, not valid JSON. The files of the model are
    its entry file and what `library.source_files` finds; when a file stops that search, the `.scn`
    files of the package."""
    from ..model.library import source_files

    files = [target.entry]
    try:
        files += source_files(target.entry)
    except (OSError, ValueError):
        files += sorted(Path(target.package).rglob('*.scn'))
    for file in dict.fromkeys(Path(file) for file in files):
        try:
            text = Path(file).read_bytes().decode('utf-8')
            if Path(file).suffix == '.json':
                json.loads(text)
        except UnicodeDecodeError as found:
            return _diagnostic(
                'source', f'not UTF-8 text: {found.reason} at byte {found.start}', file=str(file)
            )
        except json.JSONDecodeError as found:
            return _diagnostic('source', found.msg, file=str(file), line=found.lineno, column=found.colno)
        except OSError:
            continue
    return _diagnostic('source', str(exc))


def scope_note(model):
    """The note of a model that was checked for some runs only (D-30): `checked for run X only;
    `napkin compile` checks every run`. None for a model that was checked for every run."""
    runs = getattr(model, 'admission_runs', None)
    if runs is None:
        return None
    return f'checked for {"run" if len(runs) == 1 else "runs"} {listed(runs)} only; `napkin compile` checks every run'


# --- The runs -----------------------------------------------------------------------------------
#
# `run`, `play` and `sample` find their runs in the files of the model, before it compiles: the
# names, a run's comparisons (D-42) and the usage errors of `--run` need no proof, and a model that
# is checked for some runs only (D-30) compiles faster. The files are read as the language reads them
# (`language.front.load`: the files of the model merged in their order), so a variant has the runs of
# its main file and its modules, then its own. The engine still checks each run when the model loads.


def declared_runs(target):
    """{run: the runs that it is compared with} of the model of a `Target`, each in the order of the
    files, from its files and without compiling them. The runs are the lines of `runs:` of every file
    of the model. The runs that a run is compared with are the run that its `versus` names and each
    run whose `versus` names it: the runs that a spread of the run samples on the same draws
    (`spread.sampled_runs`). A model with no runs and no options has the one run `base`
    (docs/language.md, §2.9); one with options and no runs has none, and the engine refuses it.
    Raises Failed, as `load` does, for files that cannot be read or that do not parse."""
    return {name: compared for name, (_, compared) in _runs_of(target).items()}


def _runs_of(target):
    """{run: (its label, the runs that it is compared with)} of the files of a `Target`
    (`declared_runs`). The label is the run's text, or else its options joined by " · ", as the model
    names it (docs/python-api.md, `runs`)."""
    from ..model.language import front
    from ..model.semantic import BASE_RUN

    with _read(target):
        file, _ = front.load(target.entry)
    if not file.runs:
        return {} if file.profiles else {BASE_RUN: (BASE_RUN, ())}
    versus = {run.name: run.versus for run in file.runs}
    found = {}
    for run in file.runs:
        compared = tuple(
            other
            for other in versus
            if other != run.name and (other == run.versus or versus[other] == run.name)
        )
        text = run.text.value if run.text is not None else None
        label = text if isinstance(text, str) else ' · '.join(run.profiles)
        found[run.name] = (' '.join(label.split()), compared)
    return found


def the_run(target, run=None):
    """The one run of a command (`play`, `sample`) on the model of a `Target`: the run that `--run`
    names (`run`), or without it the only run of the model, from its files (`declared_runs`). Raises
    UsageError for a run that the files do not declare, with the closest names, and for a model of
    several runs and no `run`, with each run's name and label, so the command lists the runs and
    stops."""
    found = _runs_of(target)
    if run is not None:
        return _declared(target, run, found)
    if len(found) == 1:
        return next(iter(found))
    if not found:
        _no_runs(target)
    width = max(len(name) for name in found)
    rows = [f'  {name:<{width}}  {label}'.rstrip() for name, (label, _) in found.items()]
    head = f'{target.name} has {len(found)} runs: pick one with --run NAME'
    raise UsageError('\n'.join([head, *rows]))


def check_runs(target, runs):
    """The runs that the `--run` items of `napkin run` name (`runs`), each once, in the order given,
    when the files of the model of a `Target` declare each one (`declared_runs`). No item gives ()
    and reads no file. Raises UsageError, with the closest names, for the first run that the files
    do not declare."""
    runs = tuple(dict.fromkeys(runs or ()))
    if runs:
        found = _runs_of(target)
        for run in runs:
            _declared(target, run, found)
    return runs


def _declared(target, run, found):
    """`run`, when it is one of the runs `found` (`_runs_of`); else a UsageError with the closest
    names."""
    if not found:
        _no_runs(target)
    if run not in found:
        raise UsageError(f'{run} is not a run of {target.name}' + _close(run, found))
    return run


def _no_runs(target):
    """Stop a command on a model whose files declare no run: one with options and no `runs:`. The
    engine refuses it, and `load` gives its diagnostics (Failed)."""
    load(target)
    raise UsageError(f'{target.name} declares no runs: a model with options names its runs (runs:)')


# --- The values of the options ------------------------------------------------------------------


class _Refused(ValueError):
    """A JSON value that is not finite, or an object with a key twice."""


def strict_json(text):
    """The value of a JSON text, read strictly: no NaN or infinity, no number beyond a float, and no
    key twice in an object. Raises ValueError: json.JSONDecodeError for a text that is not JSON."""

    def pairs(items):
        found = {}
        for key, value in items:
            if key in found:
                raise _Refused(f'the key {key!r} is there twice')
            found[key] = value
        return found

    def constant(text):
        raise _Refused(f'{text} is not a finite number')

    def real(text):
        value = float(text)
        if not math.isfinite(value):
            raise _Refused(f'{text} is not a finite number')
        return value

    def whole(text):
        value = int(text)
        try:
            float(value)
        except OverflowError:
            raise _Refused(f'{text} is not a finite number') from None
        return value

    return json.loads(
        text, object_pairs_hook=pairs, parse_constant=constant, parse_float=real, parse_int=whole
    )


def parse_set(items):
    """{NAME: value} of `--set NAME=VALUE` items, the `set` entries of an edit document. A VALUE is
    strict JSON (no NaN or infinity, no number beyond a float, no key twice); otherwise a bare word
    (`[A-Za-z][A-Za-z0-9_-]*`) is text, so `--set plan=fast` is `"fast"`. Raises UsageError for any
    other VALUE, a missing `=` or NAME, and a NAME given twice. The engine checks each name and value."""
    found = {}
    for item in items or ():
        name, separator, text = item.partition('=')
        name, text = name.strip(), text.strip()
        if not separator or not name or not text:
            raise UsageError(f'--set takes NAME=VALUE, not {item!r}')
        if name in found:
            raise UsageError(f'--set gives {name} twice')
        try:
            found[name] = strict_json(text)
        except _Refused as exc:
            raise UsageError(f'--set {name}={text}: {exc}') from None
        except json.JSONDecodeError:
            if not WORD.fullmatch(text):
                raise UsageError(
                    f'--set {name}={text}: give a JSON value, or a word of letters, digits, _ and - '
                    'that starts with a letter, which is text'
                ) from None
            found[name] = text
    return found


def parse_options(model, items):
    """The options of `--option [GROUP=]OPTION` items, in the order given, each once: each is an option
    of the model's menu (`model.menu`), and at most one comes from each group. An OPTION that more than
    one group holds needs its GROUP. Raises UsageError, with the closest names for a name that names
    nothing. `model.combination` checks the combination of these options with a run."""
    menu = model.menu
    groups_of = {}
    for group, options in menu.items():
        for option in options:
            groups_of.setdefault(option, []).append(group)
    chosen = {}
    for item in items or ():
        group, separator, option = item.partition('=')
        if separator and group in menu:
            if option not in menu[group]:
                raise UsageError(
                    f'{option} is not an option of the group {group}' + _close(option, menu[group])
                )
        elif item in groups_of:
            option, holders = item, groups_of[item]
            if len(holders) > 1:
                raise UsageError(
                    f'{option} is an option of the groups {listed(holders)}: write GROUP={option}'
                )
            group = holders[0]
        elif separator and option in groups_of:
            raise UsageError(f'{group} is not a group of options' + _close(group, menu))
        else:
            raise UsageError(f'{item} is not an option' + _close(item, groups_of))
        if chosen.get(group, option) != option:
            raise UsageError(f'{chosen[group]} and {option} are two options of the group {group}: give one')
        chosen[group] = option
    return tuple(chosen.values())


def read_edits(model, path, settings):
    """The edit document of `--edits FILE` and `--set` settings ({NAME: value}, `parse_set`), or None
    when there are neither. The file is read as the engine reads JSON (`napkin.model.load_json`: no key
    twice, no NaN) and is a JSON object. Each setting takes the place of the file's `set` entry of the
    same name. `schema_version` and `model_hash` come from the model only where the document has none
    (`engine.edits_for`), so a document for another revision of the model keeps its hash and the
    engine refuses it. Raises Failed, with the file, for a file that cannot be read or is no object."""
    if path is None and not settings:
        return None
    from ..engine import edits_for
    from ..model import SourceError, load_json

    body = {}
    if path is not None:
        try:
            body = load_json(path)
        except SourceError as exc:
            raise Failed([source_diagnostic(exc)]) from None
        except json.JSONDecodeError as exc:
            raise Failed(
                [_diagnostic('edits', exc.msg, file=str(path), line=exc.lineno, column=exc.colno)]
            ) from None
        except UnicodeDecodeError as exc:
            raise Failed([_diagnostic('edits', f'not UTF-8 text: {exc.reason}', file=str(path))]) from None
        except OSError as exc:
            raise Failed([os_diagnostic(exc, path)]) from None
        if not isinstance(body, dict):
            raise Failed([_diagnostic('edits', 'An edit document is a JSON object', file=str(path))])
    if settings:
        given = body.get('set', {})
        if not isinstance(given, dict):
            raise Failed(
                [_diagnostic('edits', 'The edit document\'s "set" is not an object', file=str(path))]
            )
        body = {**body, 'set': {**given, **settings}}
    return edits_for(model, body)


def _is_time(unit):
    return dict(unit.dimensions) == {'time': 1}


def parse_times(model, text, *, many=True):
    """[(point, t)] of `--at` times (`24h,7days`), each once, in time order. Each item is a number and a
    unit of time of the model, converted to the model's execution unit (hours) by its unit system, and
    lies from 0 to the end of the run (`model.time['horizon']`). `point` is the name that a report
    gives the time (`sample_result(…, reporting_times=…)`). With `many=False`, `text` is one time.
    Raises UsageError for a number with no unit, an unknown unit (with the closest units of time), a
    unit that is not of time, and a time outside the run."""
    from ..expressions import ExpressionError, UnitSystem
    from ..model.ir import thaw

    units = UnitSystem(thaw(model.library['units']))
    horizon = float(model.time['horizon'])
    items = [item.strip() for item in str(text).split(',')]
    if not many and len(items) > 1:
        raise UsageError(f'--at takes one time, not {text!r}')
    found = {}
    for item in items:
        match = TIME.fullmatch(item)
        if match is None:
            raise UsageError(f'--at {item!r}: give a number and a unit of time, such as 24h or 7days')
        value, unit = match.group(1), match.group(2).strip()
        if not unit:
            raise UsageError(f'--at {item}: give the unit of time, such as {value}h or {value}days')
        try:
            parsed = units.parse_unit(unit)
        except (ExpressionError, OverflowError, ValueError):
            parsed = None
        if parsed is None or not _is_time(parsed):
            times = [name for name in units.names if _is_time(units.parse_unit(name))]
            raise UsageError(f'--at {item}: {unit} is not a unit of time of the model' + _close(unit, times))
        t = float(value) * parsed.scale
        if not (math.isfinite(t) and 0 <= t <= horizon):
            raise UsageError(f'--at {item}: the run goes from 0 h to {number(horizon)} h')
        found.setdefault(repr(t), t)
    return sorted(found.items(), key=lambda point: point[1])


def parse_exceed(model, items):
    """[(outcome, value)] of `--exceed NAME=VALUE` items, in the order given: NAME is an output of the
    model, as the file names it or as the report does (`model.outputs`), and `outcome` is its name in
    the report; VALUE is a finite number in the output's own unit. Raises UsageError, with the closest
    names for an unknown output."""
    found = []
    for item in items or ():
        name, separator, text = item.partition('=')
        name, text = name.strip(), text.strip()
        if not separator or not name or not text:
            raise UsageError(f'--exceed takes NAME=VALUE, not {item!r}')
        if name in model.outputs:
            outcome = model.outputs[name]
        elif name in model.outputs.values():
            outcome = name
        else:
            raise UsageError(f'{name} is not an output of the model' + _close(name, model.outputs))
        try:
            value = float(text)
        except ValueError:
            value = math.nan
        if not math.isfinite(value):
            raise UsageError(f'--exceed {name}={text}: give a finite number in the unit of the output')
        found.append((outcome, value))
    return found


# --- The run store ------------------------------------------------------------------------------


def use_store(enabled=True):
    """Use the run store (`napkin/store.py`) from now on, as the commands do: its directory
    (`store.default_directory()`, which `NAPKIN_STORE` names or turns off), with helper processes for
    the runs that it does not hold. `enabled=False` (`--no-store`) uses no store. Gives the store's
    directory, or None."""
    from .. import store

    directory = store.default_directory() if enabled else None
    store.activate(directory, helpers=store.cores() - 1 if directory is not None else 0)
    return directory


# --- Text -----------------------------------------------------------------------------------------


def located(item, cwd=None):
    """One diagnostic in one line, as a compiler writes it: `file:line:column: severity: message
    (path)`. The file is relative to `cwd` (by default the current folder) when it is inside it. A
    diagnostic without a file is `severity: message (path)`. The parentheses also name the run of a
    diagnostic that has one, and are left out when there is neither a path nor a run."""
    where = ''
    if item.get('file'):
        file = Path(item['file'])
        base = Path.cwd() if cwd is None else Path(os.path.abspath(cwd))
        if file.is_absolute() and file.is_relative_to(base):
            file = file.relative_to(base)
        where = str(file)
        if item.get('line'):
            where += f':{item["line"]}' + (f':{item["column"]}' if item.get('column') else '')
    message = ' '.join(str(item.get('message', '')).split('\n'))
    places = [str(item['path'])] if item.get('path') else []
    places += [f'run {item["run"]}'] if item.get('run') else []
    place = f' ({"; ".join(places)})' if places else ''
    return f'{where + ": " if where else ""}{item.get("severity") or "error"}: {message}{place}'


def show_diagnostics(items, stream, *, cwd=None):
    """Write each diagnostic to `stream`, one line each (`located`)."""
    for item in items:
        stream.write(located(item, cwd) + '\n')
    stream.flush()


def number(value):
    """A value with four significant figures, as the summaries show it: plain digits from 0.0001 to a
    trillion, and a power of ten beyond. Any other value is its text."""
    if value is None or isinstance(value, bool) or not isinstance(value, (int, float)):
        return str(value)
    if value == 0 or not math.isfinite(value):
        return f'{value:g}'
    if 1e-4 <= abs(value) < 1e12:
        import numpy as np

        return np.format_float_positional(value, precision=4, unique=False, fractional=False, trim='-')
    return f'{value:.4g}'


def table(rows):
    """The rows of a table as lines, each column as wide as its widest cell."""
    if not rows:
        return []
    widths = [max(len(row[k]) for row in rows) for k in range(len(rows[0]))]
    return ['   '.join(cell.ljust(width) for cell, width in zip(row, widths)) for row in rows]


# --- JSON ---------------------------------------------------------------------------------------


def compact(report, *, full=False, index=None, admitted=None):
    """The `--json` document of `napkin run`: the CLI's projection of a report (`sample_result`), with
    the report's own names. The report's schema stays as it is.

    - The report's envelope: every part but `runs` (`schema_version`, the hashes, the scenario and the
      variant, the edits, the diagnostics, …).
    - For each run: its `label`, `options`, `horizon` and `outcomes` (their definitions); each
      reporting point's `t`, `values` and `statuses`; and its `events`, each entry of the trace with
      an outcome, as `{t, thing, event, outcome, text}`, with `picked` when a pick decided it.
    - `admitted_runs`: the runs that the model was checked for (`admitted`, `model.admission_runs`),
      or None for every run.
    - With `full`: each run's `trace` and `evidence` too, and the model's evidence index (`index`,
      `model.index`).
    """
    from ..model.ir import thaw

    doc = {key: thaw(value) for key, value in report.items() if key != 'runs'}
    doc['runs'] = {}
    for name, run in report.get('runs', {}).items():
        shown = {
            'label': run['label'],
            'options': thaw(run['options']),
            'horizon': run['horizon'],
            'outcomes': thaw(run['outcomes']),
            'reporting_points': {
                point: {'t': row['t'], 'values': thaw(row['values']), 'statuses': thaw(row['statuses'])}
                for point, row in run['reporting_points'].items()
            },
            'events': [_event(entry) for entry in run['trace'] if entry.get('outcome') is not None],
        }
        if full:
            shown['trace'] = thaw(run['trace'])
            shown['evidence'] = thaw(run['evidence'])
        doc['runs'][name] = shown
    doc['admitted_runs'] = None if admitted is None else list(admitted)
    if full:
        doc['index'] = thaw(index)
    return doc


def _event(entry):
    """An event of the compact document: one entry of the trace with an outcome."""
    event = {
        't': entry['t'],
        'thing': entry['entity'],
        'event': entry['event'],
        'outcome': entry['outcome'],
        'text': entry['label'],
    }
    return {**event, 'picked': entry['picked']} if entry.get('picked') is not None else event


def merged(reports, *, edits=None):
    """One report of several studies of one model, each of other runs (`--option` runs one study for
    each run): the envelope of the first, whose parts that name the model and the engine every report
    must share; every run of each, in order; every diagnostic of each, each once; admitted when every
    study is. A report that is not admitted rejects the whole: the result then has no run, as a
    rejected study has none. `effective_edits` is `edits`, the document that the command applied,
    when given; otherwise the reports' own, which must then be the same. Raises ValueError for reports
    of other models or engines, for a run in two reports and for edits that differ."""
    from ..model.ir import thaw

    reports = list(reports)
    if not reports:
        raise ValueError('merged takes at least one report')
    first = reports[0]
    for report in reports[1:]:
        for key in {*first, *report} - set(PER_STUDY):
            if report.get(key) != first.get(key):
                raise ValueError(f'The reports differ in {key}: they are not of one model and one engine')
    if edits is None:
        if any(report['effective_edits'] != first['effective_edits'] for report in reports):
            raise ValueError('The reports have other edits: give the edit document that the command applied')
        edits = first['effective_edits']
    doc = {key: thaw(value) for key, value in first.items()}
    doc['effective_edits'] = thaw(edits)
    seen, doc['diagnostics'], doc['runs'] = set(), [], {}
    for report in reports:
        for item in report['diagnostics']:
            key = json.dumps(item, sort_keys=True, default=str)
            if key not in seen:
                seen.add(key)
                doc['diagnostics'].append(thaw(item))
        for name, run in report['runs'].items():
            if name in doc['runs']:
                raise ValueError(f'The run {name} is in two reports')
            doc['runs'][name] = thaw(run)
    doc['admissible'] = all(report['admissible'] for report in reports)
    doc['status'] = next(
        (report['status'] for report in reports if report['status'] != 'accepted'), 'accepted'
    )
    if not doc['admissible']:
        doc['runs'] = {}
    return doc


def write_json(doc, stream):
    """Write `doc` to `stream` as one line of compact JSON, and flush it. A number that is not finite is
    a ValueError: JSON has none."""
    stream.write(json.dumps(doc, allow_nan=False, separators=(',', ':')) + '\n')
    stream.flush()
