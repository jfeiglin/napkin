"""The pipeline of a model file: it reads the file and the modules that it uses as one file (`parse`,
`modules`), gives the evidence walkers its projection (`evidence`), resolves its semantic model
(`resolve`) and builds its model with the rest of the pipeline, which reads only the semantic model
(`model.finish`)."""

from __future__ import annotations

from pathlib import Path

from ..ir import ModelError, diagnostic
from ..meaning import flat_clashes, meaning_errors
from ..semantic import MAIN
from . import parse
from .evidence import Evidence, identity, notes_of
from .lex import SyntaxProblem
from .resolve import Problems, arguments, resolve


def read(text, origin):
    """The parts of a model file (`nodes.File`). Raises ModelError with the line of a problem of
    its form."""
    try:
        return parse.parse(text)
    except SyntaxProblem as exc:
        raise ModelError([syntax_problem(exc, origin)]) from None


def syntax_problem(exc, origin):
    """The diagnostic of a `SyntaxProblem` of the file `origin`: its line and, when it has one, its
    column."""
    item = {**diagnostic('syntax', '', exc.message), 'line': exc.line, 'file': origin}
    return {**item, 'column': exc.column} if exc.column else item


def load(path):
    """(the `nodes.File` of the model of the file `path`: the file and the modules that it uses, merged
    in their order; {place: file} of each line of a model of several files, else {})."""
    from .modules import read as read_files

    return read_files(Path(path))


def evidence_of(file):
    """The evidence of a parsed file: each line's records, the records of its notes among them."""
    evidence = Evidence(file).collect()
    notes_of(file.notes, evidence)
    return evidence


def projection(file):
    """What the evidence walkers read of a file (`evidence.Evidence.projection`)."""
    evidence = evidence_of(file)
    return evidence.projection(evidence.units)


def compile_file(file, origin, library, *, files=None, admission_runs=None, only=None):
    """The model of a parsed model file (`model.finish`): one file, or the merged file of a model of
    several files (`load`), with the file of each line (`files`). With `only` (`resolve.Kept`), each
    table makes only the instances of the rows that it keeps: the model of the representatives of
    `model/hybrid.py`."""
    from ..model import Source, finish

    lines, columns, files = file.lines, file.columns, dict(files or {})
    evidence = evidence_of(file)
    errors = []
    if file.uses or file.changes:
        errors.append(
            diagnostic(
                'modules', '', 'a file with use lines or change blocks is built from its path (front.build)'
            )
        )
    errors += [
        diagnostic(
            'table',
            '/'.join(map(str, thing.table.place)),
            f'{thing.table.file!r} is not read: a table is a file of a package, and the model is built '
            'from its path (front.build)',
        )
        for thing in file.things
        if thing.table is not None and thing.table.rows is None
    ]
    errors += [
        diagnostic('basis', '/'.join(map(str, where)), message) for where, message in evidence.problems
    ]
    payload = identity(file)
    source = Source(
        lines=lines,
        origin=origin,
        evidence=evidence.projection(evidence.units),
        identity=payload,
        files=files,
        columns=columns,
    )

    declare = _declare(file, origin, library, files, only)
    return finish(source, declare, library, errors=errors, admission_runs=admission_runs)


def _declare(file, origin, library, files, only):
    """The function that gives the semantic model of a parsed file and its run table (`model.built`)."""
    from ..model import located
    from ..runs import Runs

    lines, columns = file.lines, file.columns

    def declare():
        try:
            scenario, resolver = resolve(file, library, files, only)
        except Problems as exc:
            raise ModelError(located(exc.diagnostics, lines, origin, files, columns)) from None
        clashes = flat_clashes([entity.name for entity in scenario.entities], MAIN)
        problems = meaning_errors(scenario)
        if clashes:
            problems.append(diagnostic('structure', '', f'{clashes} name two entities of the structure'))
        if problems:
            raise ModelError(located(problems, lines, origin, files, columns))
        run_table = Runs.from_scenario(scenario, library).table
        return arguments(scenario, run_table, resolver), run_table

    return declare


def listed_structures(file, origin, library, *, files=None, only=None):
    """{start-state options: the structure} of a parsed model file with each reduction over a list as
    one node (`sum(a, b)`), as the hybrid core reads it (`model/hybrid.py`). Each structure is its
    typed parts (`model.typed_of`). These structures are lowered and not checked: the checks are those
    of the model of the same file (`compile_file`), which writes a list as its chain."""
    from ..model import built

    files = dict(files or {})
    _, structures = built(
        _declare(file, origin, library, files, only),
        file.lines,
        origin,
        library,
        files,
        columns=file.columns,
        listed=True,
    )
    return structures


def build(path, library=None, *, admission_runs=None):
    """Read, build, check and prove one model file."""
    from ..ir import thaw
    from ..library import load_library

    path = Path(path)
    file, files = load(path)
    if library is None:
        library = load_library(path, document=projection(file))
    return compile_file(file, path.as_posix(), thaw(library), files=files, admission_runs=admission_runs)
