"""napkin: a small typed language for simulation models, and its engine.

The model package reads and compiles a model file into its declared model and its program; the engine
runs a program under a configuration and gives the record of the run, which the report reads; the
studies run a program under many configurations; the dynamics package finds its rest states; the draw
package gives its static picture; the run store keeps the records of runs between commands. The
repository's maintainer tools (the checks, the comparisons, the publisher and the evidence tools) are
in `tools/`, outside the package.

The public Python API is the names of `_EXPORTS`:

    import napkin

    model = napkin.load_scenario('examples/piano_tuners')
    record = napkin.run(model.program, model.configuration)
    found = napkin.report(record, model.program, model.configuration, ['tunings_done'], [0, 8760],
                          model=model.declared)

- compile: `load_scenario` (a model file or package folder, with its run and edits), `load_package`
  (every model of a package);
- run and read: `run`, `read` (values at times) and `report` (values with their units, labels, lags
  `Lag`, status displays, evidence trails and near-ties);
- play: `Session` (one run stopped at breakpoints, shown and edited at each stop, saved, and resumed
  in this process or another: `napkin/session.py`);
- study: `study` (the named runs of a model), `monte_carlo` (samples of one run) and the module
  `spread` (a Monte Carlo study as a command asks for it);
- read the model: `instances` (the members of a template); `dynamics` (its rest states).

Each one loads its module on first use, so `import napkin` loads no other module of the package, nor
numpy or scipy. This file names the module of each export as text and never imports it: the run
store's digest of the engine follows the import statements of the engine's files and of their
packages, this file included (`store.closure`). Everything else is internal and may change in a minor
version.
"""

from importlib import import_module as _import_module
from importlib import metadata as _metadata
from pathlib import Path as _Path


def _version():
    """The version of the installed distribution, `napkin-sim`, from its metadata. A source checkout
    that is not installed has no metadata: its version is the one that its `pyproject.toml` gives."""
    try:
        return _metadata.version('napkin-sim')
    except _metadata.PackageNotFoundError:
        pass
    import tomllib

    try:
        project = tomllib.loads(
            (_Path(__file__).resolve().parent.parent / 'pyproject.toml').read_text('utf-8')
        )
        return str(project['project']['version'])
    except (OSError, KeyError, TypeError, tomllib.TOMLDecodeError):
        return '0+unknown'


__version__ = _version()
# The version of the documents that the engine reads: the edit document (`napkin/schema/`).
SCHEMA_VERSION = '0.0.1'

# The public API: {name: the module that defines it}. A name that is its module's own last part is the
# module itself (`napkin.dynamics`, `napkin.spread`).
_EXPORTS = {
    'load_scenario': 'napkin.model.compile',
    'load_package': 'napkin.package',
    'run': 'napkin.engine.timeline',
    'read': 'napkin.engine.timeline.record',
    'report': 'napkin.engine.report',
    'Lag': 'napkin.engine.report',
    'Session': 'napkin.session',
    'study': 'napkin.engine.study',
    'monte_carlo': 'napkin.engine.uncertainty',
    'spread': 'napkin.spread',
    'instances': 'napkin.model.views',
    'dynamics': 'napkin.dynamics',
}
__all__ = list(_EXPORTS)


def __getattr__(name):
    """An export of the public API, from its module, which loads on first use; the value is then kept
    in this module. Any other name is no attribute, so `from napkin import store` still finds the
    module `napkin.store`."""
    path = _EXPORTS.get(name)
    if path is None:
        raise AttributeError(f'module {__name__!r} has no attribute {name!r}')
    module = _import_module(path)
    value = module if path == f'{__name__}.{name}' else getattr(module, name)
    globals()[name] = value
    return value


def __dir__():
    return sorted({*globals(), *_EXPORTS})
