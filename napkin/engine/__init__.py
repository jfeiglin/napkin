"""Run programs: the timeline engine and its solvers (`run`, `read` of the record of a run, and the
checkpoint of a run that a breakpoint stops: `paused`, the entry that ends its record so far, and
`resume`, which goes on with a checkpoint in this process or another); the studies of a
program under several configurations (`configurations`, `run_all`, `edits_for`, and the module
`study`); and Monte Carlo studies (`monte_carlo`, `SamplingSettings`).

Each name of the package loads its module on first use, as the names of `napkin` do
(`napkin/__init__.py`). So the import of one module of the engine loads no report, no study and no
compiler. This file names each module as text and never imports it.
"""

from importlib import import_module as _import_module

# The names of the package: {name: the module of the package that defines it}.
_EXPORTS = {
    'Cancelled': 'study',
    'SamplingSettings': 'sampling',
    'SimulationError': 'errors',
    'configurations': 'study',
    'edits_for': 'study',
    'monte_carlo': 'uncertainty',
    'paused': 'timeline',
    'read': 'timeline',
    'resume': 'timeline',
    'run': 'timeline',
    'run_all': 'study',
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
