"""A played sampled run (spec, "Actor decisions and observations", "A run produces one trajectory";
D1, D9, R-A2-17; `chance.py`).

One run is one trajectory of one configuration: its seed and its picks. It replays exactly from them;
a draw is keyed by its site and its owner, so a member that nobody plays draws the same whether or not
another member is played, and so does every draw that two policies both execute. A choice that the
picks answer differently takes another branch, and the draws of the branch that it leaves are not
made. The expected values are the rules themselves and the oracle's draws.
"""

from __future__ import annotations

import pytest

from napkin.engine import read, run
from napkin.program.build import (
    Builder,
    add,
    after,
    assign,
    case,
    categorical,
    choose,
    dist_of,
    draw,
    event,
    named,
    q,
    start,
    switch,
    this,
    uniform,
    value,
)
from napkin.program.config import PLAYER, SAMPLED, Configuration, Controller, Pick, Request
from napkin.program.record import Key
from tests.reference.from_program import run_of, value_at

UNITS = {'h': {'time': 1}, 'L': {'volume': 1}}
SITE = 'Crew.respond.step[0].do[1].choice[0]'


def crews():
    """Two crews of one template: at 1 h each draws a delay, then chooses to repair, which draws a
    cost, or to wait; at 3 h each draws the weather."""
    b = Builder(UNITS)
    action = b.enum('enum[REPAIR, WAIT]', 'REPAIR', 'WAIT')
    b.template(
        'Crew',
        value('forecast', dist_of(action), categorical(action, REPAIR=0.5, WAIT=0.5)),
        value('delay', 'h', 0),
        value('cost', 'L', 0),
        value('weather', 'L', 0),
        value('waits', '', 0),
        event(
            'respond',
            after(
                q(1, 'h'),
                assign(this.delay, draw(uniform(1, 3, 'h'))),
                switch(
                    choose(this, this.forecast),
                    case(action.REPAIR, assign(this.cost, draw(uniform(10, 20, 'L')))),
                    case(action.WAIT, add(this.waits, 1)),
                ),
            ),
            after(q(2, 'h'), assign(this.weather, draw(uniform(0, 1, 'L')))),
        ),
    )
    b.member('Crew', 'east')
    b.member('Crew', 'west')
    b.setup(start(named('east').respond), start(named('west').respond))
    return b.finish()


def configured(seed, *picks, played=('east',)):
    return Configuration(
        Request(4),
        mode=SAMPLED,
        seed=seed,
        controllers=tuple(Controller(actor, PLAYER) for actor in played),
        picks=tuple(Pick(SITE, f'{actor}.respond#0', answer) for actor, answer in picks),
    )


def drawn(record):
    return {(entry.part, entry.owner): entry.detail('value') for entry in record.entries('draw')}


@pytest.mark.parametrize('seed', [3, 4, 5])
def test_a_played_sampled_run_replays_exactly_from_its_seed_and_picks(seed):
    program = crews()
    configuration = configured(seed, ('east', 'REPAIR'))
    assert run(program, configuration) == run(program, configuration)


@pytest.mark.parametrize('seed', [3, 4, 5])
def test_a_member_that_nobody_plays_draws_the_same_whether_another_is_played(seed):
    program = crews()
    alone = drawn(run(program, configured(seed, played=())))
    played = drawn(run(program, configured(seed, ('east', 'REPAIR'))))
    west = {key: number for key, number in alone.items() if key[1].startswith('west')}
    assert west and all(played[key] == number for key, number in west.items())


@pytest.mark.parametrize('seed', [3, 4, 5])
def test_two_policies_draw_the_same_wherever_both_draw(seed):
    """Repairing draws a cost that waiting does not; the delay before the choice and the weather
    after it are the same draws in both, and agree with the oracle's."""
    program = crews()
    repair, wait = (configured(seed, ('east', answer)) for answer in ('REPAIR', 'WAIT'))
    repaired, waited = drawn(run(program, repair)), drawn(run(program, wait))
    cost = ('Crew.respond.step[0].do[1].REPAIR.do[0].draw[0]', 'east.respond#0')
    assert cost in repaired and cost not in waited
    shared = set(repaired) & set(waited)
    assert {part for part, owner in shared if owner == 'east.respond#0'} == {
        'Crew.respond.step[0].do[0].draw[0]',
        'Crew.respond.step[1].do[0].draw[0]',
    }
    assert all(repaired[key] == waited[key] for key in shared)
    oracle, failed = run_of(program, repair)
    assert failed is None
    record = run(program, repair)
    for name in ('delay', 'cost', 'weather'):
        found = read(record, program, [f'east.{name}'], [4])[0].values[0]
        expected = float(value_at(oracle, program, Key('east', (name,)), 4))
        assert found == pytest.approx(expected, rel=1e-12)
