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
        return load_scenario(entry)
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


def times_of(model, items):
    """[(text, hours)] of the `--at` items (each a list such as `2h,160min`), each time once, in time
    order: a number and a unit of time of the model (`model.declared.units`), from 0 to the horizon
    of its default run. With no item, the start and the horizon. A time that is not one is a
    UsageError, with the closest units of time."""
    units = model.declared.units
    horizon = float(model.configuration.request.horizon)
    if not items:
        return [('0 h', 0.0), (f'{number(horizon)} h', horizon)]
    found = {}
    for item in (piece.strip() for text in items for piece in text.split(',')):
        match = TIME.fullmatch(item)
        if match is None:
            raise UsageError(f'--at {item!r}: give a number and a unit of time, such as 2h or 3 days')
        written, unit = match.group(1), match.group(2).replace(' ', '')
        if not unit:
            raise UsageError(f'--at {item}: give the unit of time, such as {written}h')
        dimension, scale = units.of(unit) or (None, None)
        if dimension != TIME_DIMENSION:
            times = [name for name, (kind, _) in units.base.items() if kind == TIME_DIMENSION]
            raise UsageError(f'--at {item}: {unit} is not a unit of time of the model' + close(unit, times))
        t = float(Fraction(written) * scale)
        if not 0 <= t <= horizon:
            raise UsageError(f'--at {item}: the run goes from 0 h to {number(horizon)} h')
        found.setdefault(t, f'{written} {unit}')
    return [(text, t) for t, text in sorted(found.items())]


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


def located(item):
    """One diagnostic on one line, as a compiler writes it: `file:line:column: error: message
    [code]`, with the file relative to the current folder when it is inside it."""
    where = shown(item.file) if item.file else ''
    if where and item.line:
        where += f':{item.line}' + (f':{item.column}' if item.column else '')
    message = ' '.join(item.message.split('\n'))
    return f'{where + ": " if where else ""}error: {message} [{item.code}]'


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
