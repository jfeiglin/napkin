"""A package's models, and one run of a model with options in place of its own.

`load_package` builds every model of a package (docs/language.md, §2.12): the package's own model when
it has no variants, else the model of each variant, whose main file is part of it. `combined` gives
the model of one run with other options (`Model.combination`) under an edit document, which it checks
on the whole model first, so that an edit document is one transaction over every run.

Import time reads only `napkin.paths`; the compiler and the engine load when a function runs.
"""

from __future__ import annotations

from pathlib import Path

from . import paths


def name_of(entry):
    """The name of the model of an entry file, by its folders (`napkin.paths.names_of`): `package`, or
    `package:variant` for a variant. A relative path is named by the folders that it stands for."""
    package, variant = paths.names_of(Path(entry).absolute())
    return f'{package}:{variant}' if variant else package


def entries(path):
    """{name: entry file} of the models of the package at `path`, a package's folder or its main file
    (`model.scn`): each variant, in name order, when the package has variants; else the main file. It
    reads no file."""
    path = Path(path)
    folder = path.parent if path.name == paths.ENTRY else path
    found = paths.variants(folder) or {None: paths.entry(folder)}
    return {name_of(entry): entry for entry in found.values()}


def load_package(path, library=None, *, admission_runs=None):
    """{name: model} of every model of the package at `path` (`entries`), each built as `load_scenario`
    builds it, with `library` and `admission_runs`: `{package: model}` for a package without variants,
    else `{package:variant: model}` for each variant, in name order.

    Raises one ModelError with the diagnostics of every model that fails, each with the name of its
    model (`model`). A file that is not valid source text (`SourceError`) is a diagnostic `source`, with
    its file and, when it has one, its line."""
    from .model import ModelError, SourceError, load_scenario

    models, problems = {}, []
    for name, entry in entries(path).items():
        try:
            models[name] = load_scenario(entry, library, admission_runs=admission_runs)
        except ModelError as exc:
            problems.extend({**item, 'model': name} for item in exc.diagnostics)
        except SourceError as exc:
            problems.append({**source_problem(exc), 'model': name})
    if problems:
        raise ModelError(problems)
    return models


def source_problem(exc):
    """The diagnostic of a `SourceError`: its message, its file and its line (none when it has no
    line)."""
    from .model.ir import diagnostic

    text = str(exc)
    prefix = f'{exc.path}:{exc.line}: ' if exc.line else f'{exc.path}: '
    message = text.removeprefix(prefix)
    return diagnostic('source', '', message, file=exc.path, **({'line': exc.line} if exc.line else {}))


def combined(model, run, options, edits=None):
    """(the model of `run` with `options` in place of its options of their groups, the edit document
    for it) under the edit document `edits` (None for none).

    The whole document is checked first, on `model`, in every run that the model admits, with the
    engine's own check (`engine.study.resolve_edits`): an edit of any run, also one that does not reach
    the combination, must hold, so the document stays one transaction. Then the derived model
    (`Model.combination`, which checks the combination) keeps the run's name, and the document keeps
    only what reaches that run: `set`, the edits of the options of the combination, and the edits of
    the run itself, with the rest of its envelope. The study of the derived model checks that document
    again, as every study does. Raises the engine's ModelError unchanged."""
    from .engine.study import resolve_edits

    if edits:
        resolve_edits(model, edits, runs=model.admission_runs)
    derived = model.combination(run, options)
    return derived, reduced(edits, run, derived.runs[run]['options'])


def reduced(edits, run, options):
    """The edit document `edits` with only what reaches the run `run` of the options `options`: its
    envelope (`schema_version`, `model_hash`, `reason`), `set`, the edits of those options and the
    edits of that run. A level with nothing left goes. None, or anything that is not a mapping, is
    returned as it is: the study refuses a document of another shape."""
    from .engine.study import EDIT_LEVELS

    if not isinstance(edits, dict):
        return edits
    out = {key: value for key, value in edits.items() if key not in EDIT_LEVELS}
    if edits.get('set'):
        out['set'] = edits['set']
    kept = {option: values for option, values in (edits.get('options') or {}).items() if option in options}
    if kept:
        out['options'] = kept
    if run in (edits.get('runs') or {}):
        out['runs'] = {run: edits['runs'][run]}
    return out


__all__ = ['combined', 'entries', 'load_package', 'name_of', 'reduced', 'source_problem']
