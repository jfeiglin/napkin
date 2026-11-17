"""Reductions over a list (docs/language.md, §2.4): `sum`, `count`, `any`, `all`, `min` and `max` of
one value of each member of a template's instances, a list link or a set of copies. The expected
values follow from the members' inputs."""

from __future__ import annotations

import pytest

from napkin.model import ModelError
from tests.build import compiled, document, entity, library, output, run, template

LOADS = {'north': 0.2, 'south': 0.7, 'west': 0.4}
DOWN = {'north': False, 'south': True, 'west': True}


def zones(*members):
    """Three zones with a load and a yes/no input, and a thing that reads them all."""
    parts = [
        template(
            'Zone',
            'input load: fraction = 0.1 in 0 to 1  @fixture\n    "Load"',
            'input down = false  @fixture\n    "Down"',
        )
    ]
    for name in LOADS:
        parts.append(
            entity(
                name,
                f'load = {LOADS[name]}  @fixture',
                f'down = {str(DOWN[name]).lower()}  @fixture',
                template='Zone',
            )
        )
    parts.append(entity('grid', *members))
    # An output reads the formula, so that the run keeps it.
    parts.append(output('found', 'grid.found', 'fraction', 'level', doc='Found', under=('signed',)))
    return document('List fixture', *parts, horizon=1)


def value(expression, unit):
    rs, trajectory = run(zones(f'let found: {unit} = {expression}  @fixture\n    "Found"'))
    env = trajectory.env_at(0)
    # A formula of inputs alone is a fixed value of the run.
    return env['grid.found'] if 'grid.found' in env else rs['values']['grid.found']


def test_count_any_and_all_of_a_yes_no():
    assert value('count(Zone.down)', 'fraction') == sum(DOWN.values())
    assert value('1 if any(Zone.down) else 0', 'fraction') == 1
    assert value('1 if all(Zone.down) else 0', 'fraction') == 0


def test_min_and_max_of_a_number_with_other_arguments():
    assert value('max(Zone.load)', 'fraction') == pytest.approx(max(LOADS.values()))
    assert value('min(Zone.load)', 'fraction') == pytest.approx(min(LOADS.values()))
    assert value('min(Zone.load, 0.1)', 'fraction') == pytest.approx(0.1)


def test_sum_is_unchanged():
    assert value('sum(Zone.load)', 'fraction') == pytest.approx(sum(LOADS.values()))


def test_count_of_a_number_is_refused():
    with pytest.raises(ModelError):
        compiled(zones('let found: fraction = count(Zone.load)  @fixture\n    "Found"'), library())
