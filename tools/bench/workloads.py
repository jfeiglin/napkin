"""The workloads of the benchmark: which models it measures, and which run of each.

A workload is one model file and the run that the harness measures in it. `workloads` lists them and
reads no model: the catalogue's packages by the names of their folders (`tools.catalogue.entries`), the
examples by their folders, and the synthetic families by their names and sizes. The catalogue is found
and never listed: no name of a package is written here.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from tools import catalogue
from tools.catalogue import ROOT

from .families import FAMILIES

# The value of `Workload.run` that asks for every run of the model. No run has this name: a name is
# a word of letters, digits and `_`.
ALL = '*'
# The folder of the examples in the checkout; the owner of an example is `examples.<name>`.
EXAMPLES = 'examples'
RUNS = ('first', 'all')


@dataclass(frozen=True)
class Workload:
    """One workload: its kind (`catalogue`, `example` or `family`), its name, its model file and its
    run. The run is a name, None for the first run of the model, or `ALL` for every run: the names of
    the runs are known only after the compile. A workload of a family also has the name of its family
    and its size, and its file is written just before it is measured (`families.write`)."""

    kind: str
    name: str
    path: Path
    run: str | None = None
    family: str | None = None
    size: int | None = None


def _run(runs):
    if runs not in RUNS:
        raise ValueError(f'runs is one of {", ".join(RUNS)}: {runs!r}')
    return ALL if runs == 'all' else None


def catalogue_workloads(root, scenarios, runs='first'):
    """The workloads of the named owners of the catalogue at `root`, in the catalogue's order, each
    once. A name is an owner with an entry file (`package` or `package:variant`), or a package with
    variants, which gives each of its variants. A name that gives no owner raises ValueError."""
    entries = catalogue.entries(root)
    chosen = set()
    for name in scenarios:
        found = [owner for owner in entries if owner == name or owner.startswith(f'{name}:')]
        if not found:
            raise ValueError(f'no scenario {name!r} in the catalogue')
        chosen.update(found)
    return [
        Workload('catalogue', owner, path, _run(runs)) for owner, path in entries.items() if owner in chosen
    ]


def example_workloads(root, runs='first'):
    """The workloads of the examples at `root`: each `examples/<name>/model.scn`, by name."""
    found = sorted((Path(root) / EXAMPLES).glob('*/model.scn'))
    return [Workload('example', f'{EXAMPLES}.{path.parent.name}', path, _run(runs)) for path in found]


def family_workloads(names, sizes, folder):
    """The workloads of the families `names` at each size of `sizes`: `<family>_<n>`, whose model file
    will be `<folder>/<family>_<n>/model.scn`. A family has one run. An unknown family or a size below
    1 raises ValueError."""
    unknown = [name for name in names if name not in FAMILIES]
    if unknown:
        raise ValueError(f'no family {", ".join(unknown)}: the families are {", ".join(FAMILIES)}')
    wrong = [n for n in sizes if isinstance(n, bool) or not isinstance(n, int) or n < 1]
    if wrong:
        raise ValueError(f'the size of a family is a whole number from 1: {wrong[0]!r}')
    return [
        Workload('family', f'{name}_{n}', Path(folder) / f'{name}_{n}' / 'model.scn', None, name, n)
        for name in dict.fromkeys(names)
        for n in dict.fromkeys(sizes)
    ]


def workloads(
    root=ROOT, *, scenarios=(), examples=False, families=(), sizes=(10, 40), runs='first', folder='.'
):
    """The workloads that a selection gives, in this order: the named scenarios of the catalogue, the
    examples, the families at each size. It runs nothing and writes nothing.

    The catalogue is opt-in, because its models are slow: without `scenarios`, no model of the
    catalogue is a workload. `runs` is `first` (the first run of each model) or `all`; `folder` is where
    the models of the families will be written."""
    return [
        *catalogue_workloads(root, scenarios, runs),
        *(example_workloads(root, runs) if examples else ()),
        *family_workloads(families, sizes, folder),
    ]
