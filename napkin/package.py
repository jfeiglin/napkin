"""A package's models: the main file of a package with no variants, else each of its variants.

`load_package` compiles every model of a package as `napkin.model.compile.load_scenario` compiles
one (docs/language/README.md): the package's own model when it has no variants, else the model of each
variant, whose files read the main file's (spec, "How templates compose into a run"). A run of one of
them, under its options and an edit document, is that model's configuration
(`Compiled.configure`), so nothing here makes a model of a run.

Import time reads only `napkin.paths`; the compiler loads when a function runs.
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


def load_package(path):
    """{name: compiled model} of every model of the package at `path` (`entries`), each as
    `load_scenario` gives it: `{package: model}` for a package without variants, else
    `{package:variant: model}` for each variant, in name order.

    Raises one `LanguageError` with the problems of every model that fails, each once: a problem of
    the main file, which each variant reads, is not repeated for each variant. A file that is not
    there raises FileNotFoundError."""
    from .model.compile import load_scenario
    from .model.language.problems import LanguageError

    models, problems = {}, []
    for name, entry in entries(path).items():
        try:
            models[name] = load_scenario(entry)
        except LanguageError as error:
            problems.extend(item for item in error.problems if item not in problems)
    if problems:
        raise LanguageError(problems)
    return models


__all__ = ['entries', 'load_package', 'name_of']
