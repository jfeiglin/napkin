"""The scenarios that a test session checks: every scenario, or those that `pytest --scenario ID` or
`check --scenario ID` names.

The selection travels in an environment variable, so the test workers and the modules that read it
at import (`tests/helpers.py`) all see it. An empty value selects no scenario: only the tests outside
the scenario folders run, without the cases of each scenario. The selection holds no scenario ID of
its own: it comes from the command line or from the changed files (`tools/check.py`).
"""

import os
from functools import cache
from pathlib import Path

VARIABLE = 'NAPKIN_TEST_SCENARIOS'
FOCUSED_VARIABLE = 'NAPKIN_TEST_FOCUSED'


def focused():
    """Whether pytest configured the focused suite before importing test modules."""
    return os.environ.get(FOCUSED_VARIABLE) == '1'


def chosen():
    """The selected scenario IDs, or None when every scenario is checked."""
    value = os.environ.get(VARIABLE)
    if value is None:
        return None
    return frozenset(name for name in value.split(',') if name)


def selected(ids):
    """The IDs of `ids` that this session checks, in their order."""
    names = chosen()
    return tuple(ids) if names is None else tuple(sid for sid in ids if sid in names)


def encode(ids):
    """The value of the variable that selects `ids` (none when empty)."""
    return ','.join(sorted(set(ids)))


def scenario_path_selected(path, root, names):
    """Whether a path in the folder of an owner of the catalogue belongs to the selection; None outside
    those folders.

    A path belongs to the owner of its folder (`tools.catalogue.owner_of`). The folder of an owner that
    other owners' models read, such as a family's folder of modules, holds the tests that they share: it
    belongs to the selection when one of its readers does (`tools.catalogue.readers`), and a folder that
    no selected model reads does not, whatever its name.
    """
    from tools import catalogue

    owner = catalogue.owner_of(path, root)
    if owner is None:
        return None
    return (
        names is None
        or owner in names
        or not set(names).isdisjoint(_readers(Path(root).resolve()).get(owner, ()))
    )


@cache
def _readers(root):
    """The readers of the catalogue at `root`, read once in a session."""
    from tools import catalogue

    return catalogue.readers(root)


# The list of the dormant tests: the test files that the rewrite of the language has not reached yet
# (scratch/rewrite/PLAN.md). A session does not collect them, so a run of a folder runs live tests only.
# The list is empty when the rewrite is done, and then this goes.
DORMANT = 'tests/dormant.txt'


def dormant_paths(text):
    """The paths that a dormant list names: one on each line, relative to the checkout, a file or a
    folder. An empty line and a line that starts with `#` name nothing."""
    return frozenset(
        line.strip().rstrip('/') for line in text.splitlines() if line.strip() and not line.startswith('#')
    )


@cache
def _dormant(root):
    try:
        return dormant_paths((root / DORMANT).read_text(encoding='utf-8'))
    except FileNotFoundError:
        return frozenset()


def dormant(path, root):
    """Whether the dormant list of the checkout at `root` names `path`, or a folder that holds it."""
    listed = _dormant(Path(root).resolve())
    if not listed:
        return False
    try:
        relative = Path(path).resolve().relative_to(Path(root).resolve())
    except ValueError:
        return False
    return any(part.as_posix() in listed for part in (relative, *relative.parents))
