"""The public Python API (`napkin/__init__.py`): the spec's names and `uncertainty_report` (D-44), each
the object of the module that defines it, loaded on first use (D-24).

`import napkin` loads no other module of the package, nor numpy, scipy or jsonschema: a property of a
fresh interpreter, not a timing. The file names each export's module as text and imports none, so the
run store's digest of the engine (`store.closure`) reads the same files as before the API.
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

# The files of the run store's closure at 742d3f2b, before the public API, relative to the package,
# and `model/structure.py`: the engine reads the typed parts of a run from it (A3);
# and the typed core that the expression evaluator reads (`core/`, A4); and `engine/allocation.py`,
# which holds the allocation that `engine/continuous/fields.py` held, and
# `engine/continuous/segment.py`, which holds the step between two moments that `engine/runtime.py`
# held (B2.4); and the timeline engine with what it reads (`engine/timeline/`, `engine/solvers.py`,
# `core/arrays.py`, `core/derivatives.py`), which `simulate` runs (B2.7); and `engine/errors.py`,
# which holds the error of a run that `engine/scheduler.py` held with the rule engine before the
# timeline engine took its place (CP-B2). The engine names no module of the compiler.
CLOSURE = (
    '__init__.py',
    'core/__init__.py',
    'core/arrays.py',
    'core/derivatives.py',
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
    'engine/runtime.py',
    'engine/sampling.py',
    'engine/solvers.py',
    'engine/timeline/__init__.py',
    'engine/timeline/component.py',
    'engine/timeline/plan.py',
    'engine/timeline/run.py',
    'engine/timeline/trees.py',
    'expressions.py',
    'model/__init__.py',
    'model/analysis/__init__.py',
    'model/analysis/structure.py',
    'model/ir.py',
    'model/structure.py',
    'model/types.py',
    'model/uncertain.py',
)

# The public API: the spec's list (Phase 4) and `uncertainty_report` (D-44), each with the module that
# defines it. `dynamics` is the package itself.
SPEC = {
    'load_scenario': 'napkin.model.compile',
    'load_package': 'napkin.package',
    'evaluate_study': 'napkin.engine.study',
    'sample_result': 'napkin.engine.report',
    'evaluate_uncertainty': 'napkin.engine.uncertainty',
    'Session': 'napkin.session',
    'actors': 'napkin.model.views',
    'instances': 'napkin.model.views',
    'dynamics': 'napkin.dynamics',
}
ADDED = {'uncertainty_report': 'napkin.engine.uncertainty'}

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


def test_the_exports_are_the_spec_s_list_and_uncertainty_report():
    assert napkin._EXPORTS == {**SPEC, **ADDED}
    assert sorted(napkin.__all__) == sorted({**SPEC, **ADDED})
    assert set(napkin.__all__) <= set(dir(napkin))


@pytest.mark.parametrize('name', list({**SPEC, **ADDED}))
def test_each_export_is_the_object_of_its_module(name):
    module = importlib.import_module({**SPEC, **ADDED}[name])
    value = getattr(napkin, name)
    if name == 'dynamics':
        assert value is module
    else:
        assert value is getattr(module, name) and value.__module__ == module.__name__
    # The value is kept, so the next use asks the module no more.
    assert vars(napkin)[name] is value


def test_the_version_and_the_schema_version_are_plain_attributes():
    """The hashed engine imports both by name (`engine/study.py`, `engine/report.py`)."""
    assert {'__version__', 'SCHEMA_VERSION'} <= set(vars(napkin))
    assert napkin.SCHEMA_VERSION == '0.0.1' and isinstance(napkin.__version__, str)
