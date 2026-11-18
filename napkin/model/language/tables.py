"""The form of a table: `sites: Place from "places.csv"` names a file of the package whose rows are
members of the template.

A table is UTF-8 text with commas between its cells and double quotes around a cell that holds a
comma, a quote or a line break (RFC 4180). Its first row is the header; each row after it is one
member of the template. A header cell is `name`, or `name: unit` for a column of numbers, and then
the records that support the values of the column (`base_need: W @survey`): a column cites its
record in its header. The column `id` gives each row a stable name, the row `sites.clinic`, so a
reordered file names the same members.

This module reads only the form: which names a column may have and what a cell may hold is the
declared model's (`napkin/model/semantic.py`), which knows the template. Each problem of the form is
a `Problem` with the file of the table and the line of its row. A reader gives the text of the file
that a model names: `in_folder` from the folder of a package, `in_memory` from texts given with a
model that is a text.
"""

from __future__ import annotations

import csv
import io
import re
from dataclasses import dataclass
from pathlib import Path, PurePosixPath

from .problems import LanguageError, Problem

HEADER = 'a header is `name`, or `name: unit`, and then its records: `base_need: W @survey`'
_NAME = r'[A-Za-z_][A-Za-z0-9_]*'
_HEADER = re.compile(rf'^\s*(?P<name>{_NAME})\s*(?::\s*(?P<unit>[^@]*?))?\s*(?P<cites>(?:@{_NAME}\s*)*)$')
_UNIT = re.compile(rf'^(?:{_NAME}|1)(?:\s*[*/]\s*{_NAME})*$')


@dataclass(frozen=True)
class Column:
    """A column: the name of a part of the template (or `id`), the unit of its numbers as a spelling
    (`L/h`, `person*year`) or None, and the records that it cites."""

    name: str
    unit: str | None
    cites: tuple[str, ...]


@dataclass(frozen=True)
class Row:
    """A row: its cells, stripped, in the order of the columns, and its line in the file."""

    cells: tuple[str, ...]
    line: int


@dataclass(frozen=True)
class Data:
    """The form of a table: the file it was read from (`origin`), its columns and its rows."""

    origin: str
    columns: tuple[Column, ...]
    rows: tuple[Row, ...]


def header(cell):
    """The column of one header cell, or None when the cell is not written as a header is."""
    found = _HEADER.match(cell)
    if found is None:
        return None
    unit = found['unit']
    if unit is not None:
        unit = unit.strip()
        if not _UNIT.match(unit):
            return None
        unit = re.sub(r'\s+', '', unit)
    cites = tuple(re.findall(_NAME, found['cites'].replace('@', ' ')))
    return Column(found['name'], unit, cites)


def read(text, origin):
    """The form of the table in `text`, read from the file `origin`. Raises `LanguageError` with each
    problem of its form, at the file and the line of its row."""
    reader = csv.reader(io.StringIO(text, newline=''), strict=True)
    problems, columns, rows, line = [], None, [], 0

    def fail(message, at):
        problems.append(Problem('table', message, at, 0, origin))

    while True:
        try:
            cells = next(reader)
        except StopIteration:
            break
        except csv.Error as error:
            fail(f'the table is not read: {error}', reader.line_num)
            break
        # A cell may hold a line break, so a row starts on the line after the last one read.
        number, line = line + 1, reader.line_num
        cells = tuple(cell.strip() for cell in cells)
        if cells in ((), ('',)):
            continue  # a blank line
        if columns is None:
            columns = []
            for cell in cells:
                found = header(cell)
                if found is None:
                    fail(f'the header {cell!r}: {HEADER}', number)
                columns.append(found)
            names = [column.name for column in columns if column is not None]
            for name in sorted({name for name in names if names.count(name) > 1}):
                fail(f'two columns give {name}', number)
            if problems:
                break
            continue
        if len(cells) != len(columns):
            fail(f'row {len(rows) + 1} has {len(cells)} cells, and the header has {len(columns)}', number)
        rows.append(Row(cells, number))
    if not problems and columns is None:
        fail('the table has no header', 1)
    elif not problems and not rows:
        fail('the table has no row: a table gives one member or more', 1)
    if problems:
        raise LanguageError(problems, origin)
    return Data(origin, tuple(columns), tuple(rows))


def table_path(written, package):
    """The file of a table that a model names `written`, in the folder of its package, or None and
    the reason that the name is no file of the package."""
    name = PurePosixPath(written)
    if not written or name.is_absolute() or '..' in name.parts or '\\' in written:
        return None, 'is not a path inside the package: a table is a file of the folder of the package'
    if name.suffix != '.csv':
        return None, 'is not a .csv file'
    path = Path(package, *name.parts)
    if not path.is_file():
        return None, 'is not a file of the package'
    return path, None


def in_folder(package):
    """A reader of the tables of a package: `reader(written)` gives (text, origin) of the file in
    the folder `package`, or (None, the reason that it is no table)."""

    def reader(written):
        path, why = table_path(written, package)
        if path is None:
            return None, why
        try:
            return path.read_bytes().decode('utf-8-sig'), path.as_posix()
        except UnicodeDecodeError:
            return None, 'is not UTF-8 text'

    return reader


def in_memory(files):
    """A reader of tables given as texts by the names that the model writes (`{"places.csv": text}`),
    for a model that is a text."""

    def reader(written):
        if written not in files:
            return None, 'is not a table given with the text'
        return files[written], written

    return reader


def no_tables(written):
    """The reader of a text with no folder: it has no table."""
    return None, 'is not read: a table is a file of a package, and this text has no folder'
