"""A resolved run that a caller makes by hand, whose triggers have no class (`timeline/plan.py`,
`Plan._rules`): the plan classifies each trigger itself.

The model has one event of each of two kinds, which the test names from the file: an event at a
written time is a timer, and an event at the level of a tally that only rises is a crossing.
"""

import pytest

from napkin.engine import timeline
from napkin.model.structure import Resolved
from tests.build import block, compiled, library, output, stock, system


def source():
    """A tally that rises by 2 people an hour. One event at 3 h, and one when the tally holds 10
    people, which is at 5 h; each adds 1 to a number of events seen."""
    return system(
        stock('served', 0, kind='tally', size=100, rate='2 people/h'),
        stock('seen', 0, 'people', size=10),
        block('event late once when t >= 3 h:  @fixture', '"At a time."', 'seen += 1 people'),
        block('event full once when served >= 10 people:  @fixture', '"At a level."', 'seen += 1 people'),
        horizon=8,
        outputs=(output('seen', 's.seen', 'people'),),
    )


def test_a_run_made_by_hand_with_no_class_of_its_triggers_gets_them_from_the_plan():
    """The run of the model has the class of each trigger from the checks of its structure. The
    same run written as plain data, with the class of each trigger taken away and read again, has
    none. The plan of each has the timer and the crossing, and the two runs have the same events:
    the timer at 3 h and the crossing at 5 h."""
    run = compiled(source()).resolve('a')
    plain = run.plain()
    for rule in plain['rules'].values():
        rule['trigger'] = {key: rule['trigger'][key] for key in ('when', 'path') if key in rule['trigger']}
    bare = Resolved.of(plain)
    assert {rule.trigger.kind for rule in bare.rules.values()} == {None}
    kinds = {'s.late': 'timer', 's.full': 'crossing'}
    for made in (run, bare):
        plan = timeline.Plan.flat(made, library())
        assert {rule.name: rule.kind for rule in plan.rules} == kinds
        result = timeline.run(plan)
        assert [(time, rule) for time, rule, _ in result.trace] == [
            (pytest.approx(3.0), 's.late'),
            (pytest.approx(5.0, abs=1e-9), 's.full'),
        ]
        assert result.outputs['seen'] == 2.0
