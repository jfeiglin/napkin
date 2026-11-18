"""The scenario language: read a model file and build its model (docs/language.md, docs/python-api.md).

The front end (`language/`) reads a file into its semantic model (`semantic`), `lower` writes the engine's
flat structures from it, `runs` gives the values of its runs under an edit document, and `model`
builds, checks and proves the model that the engine runs.

Each name of the package loads its module on first use, as the names of `napkin` do
(`napkin/__init__.py`). So the import of one module of the compiler loads no other part of it. This
file names each module as text and never imports it.
"""

from importlib import import_module as _import_module

# The names of the package: {name: the module of the package that defines it}.
_EXPORTS = {
    'Model': 'model',
    'ModelError': 'ir',
    'SourceError': 'load',
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
