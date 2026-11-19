"""What the commands of `napkin` share (napkin/cli.py): the model that a command names, its compiled
form, its times, and how a command prints diagnostics, numbers, tables and JSON.

At import time this module reads only the standard library, so `napkin --help` loads no compiler and
no engine: each function imports what it needs when it runs. Two exceptions end a command, and
`cli.main` catches both:

- `UsageError`: the command line is wrong (exit 2), such as a MODEL that does not exist or a time
  outside the run;
- `Failed`: the model or its run gives diagnostics (exit 1), such as a model that does not compile.
  Each diagnostic is a `Problem` of the front end (`napkin/model/language/problems.py`): its code,
  its message, and its file, line and column where it has them.
"""

from __future__ import annotations

import difflib
import json
import os
import re
import sys
from fractions import Fraction
from pathlib import Path

# The main file of a package, and the suffix of a model file.
ENTRY = 'model.scn'
SUFFIX = '.scn'
# A time of `--at`: a number, then its unit.
TIME = re.compile(r'([+-]?(?:[0-9]+(?:\.[0-9]*)?|\.[0-9]+)(?:[eE][+-]?[0-9]+)?)\s*(.*)', re.DOTALL)
TIME_DIMENSION = (('time', 1),)


class UsageError(Exception):
    """The command line is wrong: `cli.main` prints the command's usage and the message, and exits 2."""


class Failed(Exception):
    """Diagnostics end the command: `cli.main` prints each one (`located`) and exits 1. `problems`
    are `Problem`s of the front end."""

    def __init__(self, problems):
        self.problems = tuple(problems)
        super().__init__('\n'.join(located(problem) for problem in self.problems))


# ---- the model --------------------------------------------------------------------------------------


def add_model(parser):
    """Give a command's parser the positional MODEL (`args.model`)."""
    parser.add_argument(
        'model', metavar='MODEL', help='a package folder (its model.scn starts with `scenario`) or that file'
    )


def entry_of(text):
    """The main file that a MODEL names: the `model.scn` of a folder, or a `.scn` file. A MODEL that
    does not exist, a folder without `model.scn` and any other file are a UsageError."""
    path = Path(text)
    if path.is_dir():
        if not (path / ENTRY).is_file():
            raise UsageError(f'{text} holds no {ENTRY}: a MODEL is a package folder or its main file')
        return path / ENTRY
    if path.is_file():
        if path.suffix != SUFFIX:
            raise UsageError(f'{text} is no {SUFFIX} file: a MODEL is a package folder or its main file')
        return path
    raise UsageError(f'{text} does not exist')


def problem(code, message, file='', line=0, column=0):
    """A diagnostic of a command, as the front end writes one."""
    from ..model.language.problems import Problem

    return Problem(code, str(message), line, column, str(file))


def compiled(entry):
    """The compiled model of a main file (`napkin.model.compile.load_scenario`): its declared model,
    its program and the configuration of its default run. Raises Failed with the problems of the
    front end, or with the file of the model or of its library that cannot be read."""
    from ..model.compile import load_scenario
    from ..model.ir import ModelError
    from ..model.language.problems import LanguageError
    from ..model.load import SourceError

    try:
        found = load_scenario(entry)
    except LanguageError as error:
        raise Failed(error.problems) from None
    except SourceError as error:
        text, prefix = str(error), f'{error.path}:{error.line}: ' if error.line else f'{error.path}: '
        raise Failed([problem('source', text.removeprefix(prefix), error.path, error.line)]) from None
    except ModelError as error:
        # A problem of the units or the records of the library names its place in them, not a file.
        found = []
        for item in error.diagnostics:
            where = f'{item["path"]}: ' if item.get('path') else ''
            found.append(
                problem(item.get('code') or 'library', f'the library: {where}{item["message"]}', entry)
            )
        raise Failed(found) from None
    except (json.JSONDecodeError, UnicodeDecodeError) as error:
        raise Failed([unreadable(entry, error)]) from None
    except OSError as error:
        raise Failed([problem('file', error.strerror or str(error), error.filename or entry)]) from None
    # The reports of the setup refuse nothing: each is a warning on the error stream, so that what a
    # command writes on its output stays as it is.
    for item in found.reports:
        sys.stderr.write(located(item, 'warning') + '\n')
    return found


def unreadable(entry, error):
    """The diagnostic of a JSON or text error that the library gives without its file: the first file
    of the model that is not UTF-8 text or, of its JSON files, not valid JSON, with its place."""
    from ..model.library import source_files

    try:
        files = source_files(entry)
    except (OSError, ValueError):
        files = (entry,)
    for file in files:
        try:
            text = Path(file).read_bytes().decode('utf-8')
            if Path(file).suffix == '.json':
                json.loads(text)
        except UnicodeDecodeError as found:
            return problem('source', f'not UTF-8 text: {found.reason} at byte {found.start}', file)
        except json.JSONDecodeError as found:
            return problem('source', found.msg, file, found.lineno, found.colno)
        except OSError:
            continue
    return problem('source', error, entry)


def hours(model, item, flag):
    """(the text as the command shows it, the hours) of one time of a command line, `2h` or `3 days`:
    a number and a unit of time of the model (`model.declared.units`). A time that is not one is a
    UsageError that names `flag`, with the closest units of time."""
    units = model.declared.units
    match = TIME.fullmatch(item)
    if match is None:
        raise UsageError(f'{flag} {item!r}: give a number and a unit of time, such as 2h or 3 days')
    written, unit = match.group(1), match.group(2).replace(' ', '')
    if not unit:
        raise UsageError(f'{flag} {item}: give the unit of time, such as {written}h')
    dimension, scale = units.of(unit) or (None, None)
    if dimension != TIME_DIMENSION:
        times = [name for name, (kind, _) in units.base.items() if kind == TIME_DIMENSION]
        raise UsageError(f'{flag} {item}: {unit} is not a unit of time of the model' + close(unit, times))
    return f'{written} {unit}', float(Fraction(written) * scale)


def times_of(model, items, horizon):
    """[(text, hours)] of the `--at` items (each a list such as `2h,160min`), each time once, in time
    order: a number and a unit of time of the model (`hours`), from 0 to `horizon` (h). With no item,
    the start and the horizon. A time that is not one is a UsageError."""
    if not items:
        return [('0 h', 0.0), (f'{number(horizon)} h', horizon)]
    found = {}
    for item in (piece.strip() for text in items for piece in text.split(',')):
        text, t = hours(model, item, '--at')
        if not 0 <= t <= horizon:
            raise UsageError(f'--at {item}: the run goes from 0 h to {number(horizon)} h')
        found.setdefault(t, text)
    return [(text, t) for t, text in sorted(found.items())]


def edits_of(model, path):
    """The edit document of `--edits FILE`, or None without a FILE: a JSON object, read as the front
    end reads JSON (`napkin.model.load.load_json`: no key twice, no number that is not finite), with
    the `schema_version` and the `model_hash` of this model where it gives none, so that a document
    made for another revision keeps its hash and is refused. Raises Failed, with the file, for a file
    that cannot be read or that is no JSON object."""
    if path is None:
        return None
    from .. import SCHEMA_VERSION
    from ..model.load import SourceError, load_json

    try:
        body = load_json(path)
    except SourceError as error:
        text, prefix = str(error), f'{error.path}: '
        raise Failed([problem('edits', text.removeprefix(prefix), path)]) from None
    except json.JSONDecodeError as error:
        raise Failed([problem('edits', error.msg, path, error.lineno, error.colno)]) from None
    except UnicodeDecodeError as error:
        raise Failed(
            [problem('edits', f'not UTF-8 text: {error.reason} at byte {error.start}', path)]
        ) from None
    except OSError as error:
        raise Failed([problem('file', error.strerror or str(error), path)]) from None
    if not isinstance(body, dict):
        raise Failed([problem('edits', 'an edit document is a JSON object', path)])
    return {'schema_version': SCHEMA_VERSION, 'model_hash': model.model_hash, **body}


def configured(model, run=None, edits=None, path=None):
    """The configuration of the run `run` (None for the default run) of a compiled model under the
    edit document `edits` of the file `path` (`Compiled.configure`, which checks the document whole).
    A run that the model does not have is a UsageError, with the closest names; a problem of the
    document is a Failed, at its file."""
    from ..model.language.problems import LanguageError

    if run is not None and model.declared.run(run) is None:
        names = [item.name for item in model.declared.runs]
        known = f'; its runs are {listed(names)}' if names else '; it has no named run'
        raise UsageError(f'--run {run}: no run of the model' + (close(run, names) or known))
    if run is None and edits is None:
        return model.configuration
    try:
        return model.configure(run, edits)
    except LanguageError as error:
        raise Failed(
            [item if item.file else problem(item.code, item.message, path or '') for item in error.problems]
        ) from None


def stored():
    """Turn on the run store of this checkout or installation for this process
    (`napkin.store.default_directory`; none when `NAPKIN_STORE` is `off`), so that the runs of a
    command are read from it when it holds them, and kept in it."""
    from .. import store

    store.activate(store.default_directory())


def listed(names):
    """Names as a text lists them: `a`, `a and b`, `a, b and c`."""
    names = list(names)
    return ', '.join(names[:-1]) + (' and ' if len(names) > 1 else '') + (names[-1] if names else '')


def unit_shown(units, spelling):
    """A unit as the commands show it: a spelling that composes names (`Wh/h`) is the first name of
    the model's table of units (`model.declared.units`) with the same dimension and the same scale
    (`W`), when there is one, so that a number is the same in either; any other spelling as it is. A
    plain number stays plain: no name of a ratio stands for it."""
    if not any(sign in spelling for sign in '*/'):
        return spelling
    found = units.of(spelling)
    if found is None or not found[0]:
        return spelling
    return next((name for name, base in units.base.items() if base == found), spelling)


def close(name, names):
    """`; did you mean …?` with the names of `names` closest to `name`, or ''."""
    found = difflib.get_close_matches(name, sorted(set(names) - {name}), n=3)
    return f'; did you mean {" or ".join(found)}?' if found else ''


# ---- text and JSON ----------------------------------------------------------------------------------


def shown(path):
    """A path as a command shows it: relative to the current folder when it is inside it."""
    absolute = Path(os.path.abspath(path))
    try:
        return str(absolute.relative_to(Path.cwd()))
    except ValueError:
        return str(absolute)


def located(item, kind='error'):
    """One diagnostic on one line, as a compiler writes it: `file:line:column: error: message
    [code]`, with the file relative to the current folder when it is inside it. A report of the
    setup, which refuses nothing, is a `warning`."""
    where = shown(item.file) if item.file else ''
    if where and item.line:
        where += f':{item.line}' + (f':{item.column}' if item.column else '')
    message = ' '.join(item.message.split('\n'))
    return f'{where + ": " if where else ""}{kind}: {message} [{item.code}]'


def show(problems, stream):
    """Write each diagnostic to `stream`, one line each (`located`)."""
    for item in problems:
        stream.write(located(item) + '\n')
    stream.flush()


def problem_json(item):
    """A diagnostic as JSON: its code, its message, its file (or None), its line and its column (0
    when it has none)."""
    return {
        'code': item.code,
        'message': item.message,
        'file': shown(item.file) if item.file else None,
        'line': item.line,
        'column': item.column,
    }


def number(value):
    """A number as the commands print it: six significant figures (`2923.54`, `0.333737`)."""
    return f'{value:.6g}'


def table(rows):
    """The rows of a table as lines, each column as wide as its widest cell."""
    widths = [max(len(row[k]) for row in rows) for k in range(len(rows[0]))]
    return ['   '.join(cell.ljust(width) for cell, width in zip(row, widths)).rstrip() for row in rows]


def write_json(doc, stream):
    """Write `doc` to `stream` as one line of JSON, and flush it. A number that is not finite is a
    ValueError: JSON has none."""
    stream.write(json.dumps(doc, allow_nan=False, separators=(',', ':')) + '\n')
    stream.flush()
