"""The entry point of the front end: a model file, or a text, as its declared model, its program and
the configuration of its default run.

`compile_text` reads a text with a table of units: it parses it (`language.parse`), declares it
(`semantic.declare`) and lowers it (`lowering.lower`). `load_scenario` reads the main file of a
package: its units are those of the prelude, of the library that its scenario line names and of the
folder of the package (`library.load_library`), and its default run is a median run to the horizon of
its scenario line, with its `resolution` as the longest step. Each refusal is a `LanguageError` with
every problem, each with its code and its place in the file.
"""

from __future__ import annotations

from dataclasses import dataclass
from fractions import Fraction
from pathlib import Path

from ..program.config import Configuration, Numerics, Request
from ..program.parts import Program
from .language.evidence import document
from .language.parse import parse
from .language.problems import LanguageError, Problem, SyntaxProblem
from .lowering import lower
from .semantic import DeclaredModel, declare

MAIN = 'the main file of a package starts with its scenario line: scenario "Title"'
HORIZON = 'the scenario line gives the horizon of the default run: horizon 30 days'


@dataclass(frozen=True)
class Compiled:
    """A model as the front end gives it: its declared model, its program, and the configuration of
    its default run (None for a text with no horizon)."""

    declared: DeclaredModel
    program: Program
    configuration: Configuration | None


def compile_text(text, units, file=''):
    """The compiled model of a text, with a table of units as `napkin.program.build.Builder` takes it
    (a spelling and its dimension, or its dimension and its scale)."""
    try:
        tree = parse(text)
        declared = declare(tree, units)
        program = lower(declared)
    except SyntaxProblem as problem:
        raise LanguageError([problem.problem], file) from None
    except LanguageError as error:
        raise LanguageError(error.problems, file) from None
    return Compiled(declared, program, default_run(declared))


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


def load_scenario(path):
    """The compiled model of the main file of a package (`Compiled`). A missing file raises
    FileNotFoundError; a file that is no main file, or whose scenario line has no horizon, a
    LanguageError."""
    from .library import load_library

    path = Path(path)
    text = path.read_text(encoding='utf-8')
    file = path.as_posix()
    try:
        tree = parse(text)
    except SyntaxProblem as problem:
        raise LanguageError([problem.problem], file) from None
    if tree.scenario is None or tree.scenario.role != 'scenario':
        raise LanguageError([Problem('scenario', MAIN, 1)], file)
    library = load_library(path, document=document(tree))
    compiled = compile_text(text, library_units(library), file)
    if compiled.configuration is None:
        raise LanguageError([Problem('scenario', HORIZON, tree.scenario.line)], file)
    return compiled
