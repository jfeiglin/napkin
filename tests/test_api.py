"""The public Python API (`napkin/__init__.py`): compile, run, read, report, study, the members of a
template and the dynamics, each the object of the module that defines it, loaded on first use (D-24).

`import napkin` loads no other module of the package, nor numpy, scipy or jsonschema: a property of a
fresh interpreter, not a timing. The file names each export's module as text and imports none, so the
run store's digest of the engine (`store.closure`) reads the engine's files and no more.
"""

from __future__ import annotations

import ast
import importlib
import os
import subprocess
import sys
from pathlib import Path

import pytest

import napkin
from napkin import store

ROOT = Path(__file__).resolve().parents[1]

# The files of the run store's closure, relative to the package: the files that the engine imports
# from its timeline (`engine/timeline/`), the expressions and the distributions, with the packages
# that hold them: the program that it runs, its record, its canonical bytes and its checkpoints
# (`program/`), the solve library of the declared solvers and of fair sharing (`engine/solve/`), the
# continuous engine and the typed core that the evaluator reads (`core/`). The engine names no module
# of the compiler, of the report or of the studies. A new module of the engine changes this list.
CLOSURE = (
    '__init__.py',
    'core/__init__.py',
    'core/arrays.py',
    'core/errors.py',
    'core/evaluation.py',
    'core/expr.py',
    'core/faces.py',
    'core/intervals.py',
    'core/ops.py',
    'core/units.py',
    'distributions.py',
    'engine/__init__.py',
    'engine/allocation.py',
    'engine/continuous/__init__.py',
    'engine/continuous/bounds.py',
    'engine/continuous/fields.py',
    'engine/continuous/highs.py',
    'engine/continuous/integrate.py',
    'engine/continuous/kernels.py',
    'engine/continuous/segment.py',
    'engine/continuous/system.py',
    'engine/errors.py',
    'engine/solve/__init__.py',
    'engine/solve/distance.py',
    'engine/solve/failures.py',
    'engine/solve/fair.py',
    'engine/solve/kept.py',
    'engine/solve/problem.py',
    'engine/solve/ranked.py',
    'engine/solve/scaled.py',
    'engine/solve/solver.py',
    'engine/solvers.py',
    'engine/timeline/__init__.py',
    'engine/timeline/chance.py',
    'engine/timeline/checkpoints.py',
    'engine/timeline/collections.py',
    'engine/timeline/component.py',
    'engine/timeline/declared.py',
    'engine/timeline/family.py',
    'engine/timeline/lines.py',
    'engine/timeline/moment.py',
    'engine/timeline/network.py',
    'engine/timeline/occurrences.py',
    'engine/timeline/plan.py',
    'engine/timeline/pools.py',
    'engine/timeline/reads.py',
    'engine/timeline/record.py',
    'engine/timeline/run.py',
    'engine/timeline/selection.py',
    'engine/timeline/sparse.py',
    'engine/timeline/trees.py',
    'engine/timeline/triggers.py',
    'engine/timeline/ways.py',
    'expressions.py',
    'program/__init__.py',
    'program/artifact.py',
    'program/canonical.py',
    'program/checkpoint.py',
    'program/config.py',
    'program/parts.py',
    'program/record.py',
    'program/refs.py',
)

# The public API, each with the module that defines it. `spread` and `dynamics` are modules.
API = {
    'load_scenario': 'napkin.model.compile',
    'load_package': 'napkin.package',
    'run': 'napkin.engine.timeline',
    'read': 'napkin.engine.timeline.record',
    'report': 'napkin.engine.report',
    'Lag': 'napkin.engine.report',
    'study': 'napkin.engine.study',
    'monte_carlo': 'napkin.engine.uncertainty',
    'spread': 'napkin.spread',
    'instances': 'napkin.model.views',
    'dynamics': 'napkin.dynamics',
}
# The names of the old API that are gone: the old report, the old studies, and the player's session
# and actors, which breakpoints and checkpoints replace (slice S7).
GONE = ('sample_result', 'evaluate_study', 'evaluate_uncertainty', 'uncertainty_report', 'Session', 'actors')

# The modules whose loading `import napkin` must not cause, by their top-level name.
HEAVY = ('numpy', 'scipy', 'jsonschema')


def fresh(code):
    """The standard output of `code` in a fresh interpreter that imports this checkout's package."""
    environment = {**os.environ, 'PYTHONPATH': str(ROOT)}
    done = subprocess.run(
        [sys.executable, '-B', '-c', code],
        cwd=ROOT,
        env=environment,
        capture_output=True,
        text=True,
        check=False,
    )
    assert done.returncode == 0, done.stderr
    return done.stdout.split()


LOADED = 'import sys; print(*sorted(m for m in sys.modules if m.partition(".")[0] in ("napkin", *{heavy})))'


def test_the_run_store_reads_the_same_engine_files_as_before_the_api():
    assert [path.relative_to(store.PACKAGE).as_posix() for path in store.closure()] == list(CLOSURE)


def test_the_package_file_imports_no_module_of_the_package():
    """An import statement anywhere in the file, a function body included, would bring its module into
    the store's closure (`store.closure` walks every node)."""
    tree = ast.parse((ROOT / 'napkin' / '__init__.py').read_bytes())
    named = [
        node
        for node in ast.walk(tree)
        if (isinstance(node, ast.ImportFrom) and (node.level or (node.module or '').startswith('napkin')))
        or (isinstance(node, ast.Import) and any(a.name.partition('.')[0] == 'napkin' for a in node.names))
    ]
    assert named == []


def test_import_napkin_loads_no_other_module_of_the_package_nor_numpy_or_scipy():
    found = fresh(f'import napkin; print(napkin.__file__); {LOADED.format(heavy=HEAVY)}')
    assert found[0] == str(ROOT / 'napkin' / '__init__.py')
    assert found[1:] == ['napkin']


def test_an_export_loads_its_module_on_first_use():
    """The laziness is real: the first use of an export loads the compiler, and only then."""
    found = fresh(f'import napkin; napkin.load_scenario; {LOADED.format(heavy=HEAVY)}')
    assert {'napkin.model.compile', 'napkin.model'} <= set(found)
    assert 'napkin.engine.study' not in found


def test_a_name_that_is_no_export_is_no_attribute_and_a_submodule_still_imports():
    with pytest.raises(AttributeError, match='no attribute'):
        napkin.load_everything  # noqa: B018
    assert fresh('from napkin import store, paths; print(store.__name__, paths.__name__)') == [
        'napkin.store',
        'napkin.paths',
    ]


def test_the_exports_are_the_api_and_the_old_names_are_gone():
    assert napkin._EXPORTS == API
    assert sorted(napkin.__all__) == sorted(API)
    assert set(napkin.__all__) <= set(dir(napkin))
    for name in GONE:
        with pytest.raises(AttributeError):
            getattr(napkin, name)


@pytest.mark.parametrize('name', list(API))
def test_each_export_is_the_object_of_its_module(name):
    module = importlib.import_module(API[name])
    value = getattr(napkin, name)
    if name in ('dynamics', 'spread'):
        assert value is module
    else:
        assert value is getattr(module, name) and value.__module__ == module.__name__
    # The value is kept, so the next use asks the module no more.
    assert vars(napkin)[name] is value


def test_the_version_and_the_schema_version_are_plain_attributes():
    """The studies import the schema version by name (`engine/study.py`)."""
    assert {'__version__', 'SCHEMA_VERSION'} <= set(vars(napkin))
    assert napkin.SCHEMA_VERSION == '0.0.1' and isinstance(napkin.__version__, str)
