"""The entry point of the front end: a model file, or a text, as its declared model, its program, the
configuration of one of its runs and its hash.

`compile_text` reads a text with a table of units, and the tables that it names when they are given
with it: it parses it (`language.parse`), declares it (`semantic.declare`) and lowers it
(`lowering.lower`). `load_scenario` reads the main file or a variant of a package with the modules
that it uses (`language.modules.files`): each file is parsed alone, with its lines numbered after
those of the file before it, and the files are declared as one model, so a problem is placed at its
own file and line (`semantic.Files`). A variant's scenario line is its package's with each line that
the variant writes in its place, and its title follows its package's (`Pumps: East`); a variant
reads the library of its package. Its units are those of the prelude, of the library that the main
file's scenario line names and of the folders of the package (`library.load_library`), its tables
are files of the folder of the package.

The configuration is that of the model's default run, a median run to the horizon of its scenario
line with its `resolution` as the longest step, or of the named run `run`, under the edit document
`edits` (`runs.configuration`). Each refusal is a `LanguageError` with every problem, each with its
code and its place: a file and a line, the file and the line of a table, or the place in the edit
document.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from fractions import Fraction
from pathlib import Path

from ..program.config import Configuration, Numerics, Request
from ..program.parts import Program
from . import runs
from .identity import model_hash
from .language import nodes as n
from .language.evidence import document
from .language.modules import files as package_files
from .language.parse import parse
from .language.problems import LanguageError, Problem, SyntaxProblem
from .language.tables import in_folder, in_memory
from .lowering import lower, reports
from .semantic import DeclaredModel, Files, declare

HORIZON = 'the scenario line gives the horizon of the default run: horizon 30 days'
LIBRARY = 'a variant reads the library of its package: the main file names it'


@dataclass(frozen=True)
class Compiled:
    """A model as the front end gives it: its declared model, its program, the configuration of one
    of its runs (None for a text with no horizon), the setup's reports (`lowering.reports`), each a
    `Problem` at its place that refuses nothing (equal keys in a keyed view that `.at(...)` reads, and a
    lookup below its first key at a known lower bound), and its hash (`identity.model_hash`). `base` is
    the configuration of its default run, from which `configure` makes another run's."""

    declared: DeclaredModel
    program: Program
    configuration: Configuration | None
    reports: tuple[Problem, ...] = ()
    model_hash: str = ''
    base: Configuration | None = None

    def configure(self, run=None, edits=None, options=None):
        """The configuration of the run `run` (None for the default run), or of a combination of
        `options`, under the edit document `edits`, which is checked against this model's hash
        (`runs.configuration`). Raises `LanguageError`."""
        if self.base is None:
            raise LanguageError([Problem('scenario', HORIZON)])
        return runs.configuration(self.declared, self.base, run, edits, options, self.model_hash)


def compile_text(text, units, file='', tables=None, *, run=None, edits=None):
    """The compiled model of a text, with a table of units as `napkin.program.build.Builder` takes it
    (a spelling and its dimension, or its dimension and its scale). `tables` gives the tables that
    the text names: a mapping of the name that it writes to the text of the file, or a reader
    (`language.tables.in_folder`). `run` and `edits` choose the configuration (`Compiled.configure`)."""
    reader = in_memory(tables) if isinstance(tables, dict) else tables
    try:
        tree = parse(text)
    except SyntaxProblem as problem:
        raise LanguageError([problem.problem], file) from None
    return _compiled(tree, units, reader, (), file, run, edits)


def _compiled(tree, units, reader, files, file, run, edits):
    """The compiled model of a tree (of a text, or of a package's files with their `files`)."""
    place = Files(files)

    def placed(problems):
        out = []
        for item in problems:
            if item.file or not files or not item.line:
                out.append(item)
                continue
            name, line = place.place(item.line)
            out.append(replace(item, file=name, line=line))
        return out

    try:
        declared = declare(tree, units, reader, files)
        program = lower(declared)
    except LanguageError as error:
        raise LanguageError(placed(error.problems), file) from None
    base = default_run(declared)
    found = tuple(replace(item, file=item.file or file) for item in placed(reports(declared, program)))
    compiled = Compiled(declared, program, base, found, model_hash(declared, program, base), base)
    if run is not None or edits is not None:
        try:
            compiled = replace(compiled, configuration=compiled.configure(run, edits))
        except LanguageError as error:
            raise LanguageError(error.problems, file) from None
    return compiled


def default_run(declared):
    """The configuration of a model's default run: a median run to the horizon of its scenario line,
    recording every value, or None with no horizon."""
    scenario = declared.scenario
    if scenario is None or scenario.horizon is None:
        return None
    numerics = Numerics() if scenario.resolution is None else Numerics(max_step=float(scenario.resolution))
    return Configuration(Request(scenario.horizon), numerics=numerics)


def library_units(library):
    """The units of a library (`library.load_library`) as `Builder` takes them: each with its
    dimension and its exact scale (`0.01` is 1/100)."""
    out = {}
    for name, unit in library['units'].items():
        scale = unit.get('scale', 1)
        out[name] = (
            dict(unit.get('dimensions', {})),
            Fraction(str(scale)) if isinstance(scale, float) else Fraction(scale),
        )
    return out


def load_scenario(path, *, run=None, edits=None):
    """The compiled model of the main file or of a variant of a package (`Compiled`), with the
    configuration of its run `run` (None for its default run) under the edit document `edits`. A
    missing file raises FileNotFoundError; a file that is no model, a problem of its files or a
    scenario line with no horizon, a LanguageError."""
    from .library import load_library

    path = Path(path)
    found = package_files(path)
    problems, trees, files, offset = list(found.problems), [], [], 0
    for file, text in found.files:
        files.append((file.as_posix(), offset))
        try:
            # The lines of each file are numbered after those of the files before it.
            trees.append(parse('\n' * offset + text))
        except SyntaxProblem as problem:
            name, line = Files(tuple(files)).place(problem.problem.line)
            problems.append(replace(problem.problem, file=name, line=line))
        offset += text.count('\n') + 1
    if problems:
        raise LanguageError(problems)
    tree, scenario_problems = merged(trees)
    if scenario_problems:
        place = Files(tuple(files))
        raise LanguageError(
            [
                replace(item, file=place.place(item.line)[0], line=place.place(item.line)[1])
                for item in scenario_problems
            ]
        )
    library = load_library(path, document=document(tree))
    compiled = _compiled(
        tree, library_units(library), in_folder(found.package), tuple(files), path.as_posix(), run, edits
    )
    if compiled.base is None:
        line = Files(tuple(files)).place(tree.scenario.line)
        raise LanguageError([Problem('scenario', HORIZON, line[1], 0, line[0])])
    return compiled


def merged(trees):
    """(the tree of the files of a model in the order in which they are read, the problems of its
    scenario line): the files' lines with no `use`, under one scenario line, the main file's with
    each line of a variant's in its place."""
    items, scenario, problems = [], None, []
    for tree in trees:
        for item in tree.items:
            if isinstance(item, n.Use):
                continue
            if not isinstance(item, n.Scenario):
                items.append(item)
            elif scenario is None:
                scenario = item
            else:
                if item.library is not None:
                    problems.append(Problem('scenario', LIBRARY, item.line))
                written = {
                    key: getattr(item, key)
                    for key in ('summary', 'horizon', 'scope', 'timescales', 'resolution')
                    if getattr(item, key) not in (None, ())
                }
                scenario = replace(
                    scenario,
                    role='variant',
                    title=f'{scenario.title}: {item.title}',
                    line=item.line,
                    **written,
                )
    return n.File(((scenario,) if scenario is not None else ()) + tuple(items)), problems
