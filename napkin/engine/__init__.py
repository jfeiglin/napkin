"""Run programs: the timeline engine and its solvers (`run`, and `read` of the record of a run),
and, until a later stage replaces them, the studies of runs under edits, Monte Carlo studies of
uncertain values, and reports of the old compiled form.

Each name of the package loads its module on first use, as the names of `napkin` do
(`napkin/__init__.py`). So the import of one module of the engine loads no report, no study and no
compiler. This file names each module as text and never imports it.
"""

from importlib import import_module as _import_module

# The names of the package: {name: the module of the package that defines it}.
_EXPORTS = {
    'NumericalSettings': 'runtime',
    'SamplingSettings': 'sampling',
    'SimulationError': 'errors',
    'analyze_bounds': 'study',
    'edits_for': 'study',
    'evaluate_study': 'study',
    'evaluate_uncertainty': 'uncertainty',
    'read': 'timeline',
    'resolve_edits': 'study',
    'run': 'timeline',
    'sample_result': 'report',
    'uncertainty_report': 'uncertainty',
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
