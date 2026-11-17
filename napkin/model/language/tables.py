"""The table of a set of instances (docs/language.md, §2.3): `name: Template from "file.csv"`.

The table is a file of the package: UTF-8 text with commas between its cells and double quotes around
a cell that holds a comma, a quote or a line break (RFC 4180). Its first row is the header, and each
row after it is one instance of the template, in the order of the file.

A header is `name`, or `name: unit` for a column of numbers, and then the records that support the
values of the column, `@record`. The name is a member of the template, a link of the template or
`title`. This module reads only the form of the table: which names a column can have and what a cell
can hold is the resolver's (`resolve.Resolver.rows`).

`fill` gives each table of a parsed file its columns and its rows, and each column and each row its
place and its line. The place of a column is `(thing, 'table:', name)`, at line 1 of the table; the
place of row k is `(thing, 'table:', k)`. A cell has the place `(thing, 'table:', k, name)`, which no
map holds: a diagnostic about a cell gets the line of its row (`model.located`).
"""

from __future__ import annotations

import csv
import io
from pathlib import Path, PurePosixPath

from ..ir import diagnostic
from ..semantic import path_text
from . import lex
from .lex import SyntaxProblem
from .nodes import Cite, Column, Row

HEADER = 'a header is `name`, or `name: unit`, and then its records: `population: people @census`'


def problem(origin, message, line=None, place=()):
    """The diagnostic of a problem of a table: its file, and its line when it has one."""
    item = {**diagnostic('table', path_text(place) if place else '', message), 'file': origin}
    return {**item, 'line': line} if line else item


def table_path(written, package):
    """The file of a table that a model names `written`, in the folder of the package; or the reason
    that the name is no file of the package."""
    name = PurePosixPath(written)
    if (
        not written
        or name.is_absolute()
        or '..' in name.parts
        or '\\' in written
        or Path(written).is_absolute()
    ):
        return None, 'is not a path inside the package: a table is a file of the folder of the package'
    if name.suffix != '.csv':
        return None, 'is not a .csv file'
    path = Path(package, *name.parts)
    if not path.is_file():
        return None, 'is not a file of the package'
    return path, None


def header(text, place, number):
    """The column of one header cell, or raises SyntaxProblem."""
    from .parse import Cursor

    lines = [line for line in lex.lines(text) if line.kind == 'line']
    if len(lines) != 1 or lines[0].depth:
        raise SyntaxProblem(HEADER, number)
    cursor = Cursor(lines[0])
    name = cursor.name(HEADER)
    unit = None
    if cursor.at_op(':'):
        cursor.i += 1
        unit = cursor.word(HEADER)
    if not cursor.done() and cursor.peek().kind != 'at':
        cursor.fail(HEADER)
    names = cursor.cites()
    where = (*place, name)
    return Column(where, number, name, unit, [Cite(where, number, cited) for cited, _ in names])


def read(path, table, origin):
    """(the columns of the table in the file `path`, its rows, the problems of its form)."""
    place = table.place
    try:
        text = path.read_bytes().decode('utf-8-sig')
    except UnicodeDecodeError:
        return None, None, [problem(origin, 'the table is not UTF-8 text', place=place)]
    reader = csv.reader(io.StringIO(text, newline=''), strict=True)
    columns, rows, problems = None, [], []
    before = 0
    while True:
        try:
            cells = next(reader)
        except StopIteration:
            break
        except csv.Error as exc:
            problems.append(problem(origin, f'the table is not read: {exc}', reader.line_num, place))
            break
        number, before = before + 1, reader.line_num
        cells = [cell.strip() for cell in cells]
        if columns is None:
            columns = []
            for cell in cells:
                try:
                    columns.append(header(cell, place, number))
                except SyntaxProblem as exc:
                    problems.append(problem(origin, f'the header {cell!r}: {exc.message}', number, place))
            names = [column.name for column in columns]
            for name in sorted({name for name in names if names.count(name) > 1}):
                problems.append(problem(origin, f'two columns give {name}', number, place))
            if problems:
                return None, None, problems
            continue
        k = len(rows) + 1
        if len(cells) != len(columns):
            problems.append(
                problem(
                    origin,
                    f'row {k} has {len(cells)} cells, and the header has {len(columns)}',
                    number,
                    place,
                )
            )
        rows.append(Row((*place, k), number, cells))
    if columns is None:
        problems.append(problem(origin, 'the table has no header', place=place))
    elif not rows:
        problems.append(problem(origin, 'the table has no row: a set has one instance or more', 1, place))
    return columns, rows, problems


def fill(file, package, origin):
    """Give each table of the parsed file `file` (of the path `origin`) its columns and its rows from
    its file in the folder `package`, and each column and row its line in `file.lines`.
    ({place: the path of its table} of each of those places, the problems of the tables)."""
    files, problems = {}, []
    for thing in file.things:
        table = thing.table
        if table is None:
            continue
        line = file.lines.get(table.place)
        if package is None:
            path, why = None, 'is not read: the model has no folder of a package'
        else:
            path, why = table_path(table.file, package)
        if path is None:
            item = diagnostic('table', path_text(table.place), f'{table.file!r} {why}')
            problems.append({**item, 'file': Path(origin).as_posix(), **({'line': line} if line else {})})
            continue
        columns, rows, wrong = read(path, table, path.as_posix())
        problems += wrong
        if wrong:
            continue
        table.columns, table.rows = columns, rows
        for part in (*columns, *rows):
            file.lines[part.place] = part.line
            files[part.place] = path.as_posix()
    return files, problems
