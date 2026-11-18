"""The scenario language: read a model file and lower it to its program (docs/language.md).

The front end (`language/`) parses a file, `semantic` declares it (names, types and units),
`lowering` writes it as a program (`napkin/program`), and `compile` is the entry of all three
(`load_scenario`, `compile_text`). `library` gives a model its units and its records. The modules
`ir`, `runs`, `views`, `uncertain` and `analysis/` hold work of the old compiler that a later stage
ports; nothing on the path from a file to a run loads `runs`, `views` or `analysis/`.

Each name of the package loads its module on first use, as the names of `napkin` do
(`napkin/__init__.py`). So the import of one module of the compiler loads no other part of it. This
file names each module as text and never imports it.
"""

from importlib import import_module as _import_module

# The names of the package: {name: the module of the package that defines it}.
_EXPORTS = {
    'LanguageError': 'language.problems',
    'ModelError': 'ir',
    'SourceError': 'load',
    'compile_text': 'compile',
    'load_json': 'load',
    'load_library': 'library',
    'load_scenario': 'compile',
}
__all__ = list(_EXPORTS)


def __getattr__(name):
    """A name of the package, from its module, which loads on first use; the value is then kept in
    this module. Any other name is a module of the package, or no attribute."""
    module = _EXPORTS.get(name)
    if module is not None:
        value = getattr(_import_module(f'{__name__}.{module}'), name)
    elif name.startswith('_'):
        raise AttributeError(f'module {__name__!r} has no attribute {name!r}')
    else:
        try:
            value = _import_module(f'{__name__}.{name}')
        except ModuleNotFoundError as missing:
            if missing.name != f'{__name__}.{name}':
                raise
            raise AttributeError(f'module {__name__!r} has no attribute {name!r}') from None
    globals()[name] = value
    return value


def __dir__():
    return sorted({*globals(), *_EXPORTS})
