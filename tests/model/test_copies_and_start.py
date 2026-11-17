"""Copies of an entity, a start that changes nothing and an operation that waits on it, time scales,
units that name a text value, and texts with one text for each time an event happens.

They use MODELTEST (tests/model/modeltest.py): the attacker switches a service off, the service is
repaired `repair_time` after it goes down and then serves waiting users at `service_rate` times the
number still waiting. Every expectation is a closed form of inputs read from the model.
"""

from __future__ import annotations

import math

import pytest

from napkin.core.expr import text as written
from napkin.engine.runtime import simulate
from napkin.model import ModelError
from tests.build import block, drop, member, replace
from tests.model.modeltest import LIB, build, run, times
from tools.publish.pages import pages
from tools.publish.texts import cards_for


def things(*blocks):
    """An edit step: things and templates after those of the fixture, before its options."""
    return replace('options "Response":', '\n\n'.join(blocks) + '\n\noptions "Response":')


def top(*blocks):
    """An edit step: checks and outputs at the top level, before the options."""
    return replace('options "Response":', '\n\n'.join(blocks) + '\n\noptions "Response":')


def env_at(model, t, name='slow', whole=False):
    """The values of a run at time t: of the run's structure, or of the whole structure of its start
    states, with every part (`whole`)."""
    if not whole:
        _, trajectory = run(model, name)
        return trajectory.env_at(t)
    numbers, errors = model.numbers(model.run_values(name))
    assert not errors
    every_part = model.whole[model.runs[name]['starts']]
    rs = model.resolve_in(every_part, numbers, f'whole {name}')
    return simulate(rs, LIB).env_at(t)


# ---- copies of an entity ------------------------------------------------------------------------
# Three couriers, copies of one template, numbered from 1. Copy k collects once, at k * 10 h, and
# adds k people, twice that if the service is back by then. A depot lists the set of copies. The
# structure names copy k `couriers_k`. The couriers' lines come after the service's, so at the moment
# of the repair the repair goes first.

COPIES = 3
STEP = 10.0


def with_couriers():
    return (
        things(
            block(
                'Courier:  @ident',
                '"A courier that collects once, at its own hour."',
                'role operator',
                'var stage: "idle" | "collected" = "idle"',
                'var amount: people = 0  @ident',
                block(
                    f'event collection when stage is "idle" and t >= copy * {STEP:g} h:  @ident',
                    '"The courier collects."',
                    'stage = "collected"',
                    'amount += copy * (1 people if service.status is "down" else 2 people)',
                ),
            ),
            f'couriers: Courier * {COPIES}',
            # A link has a name of its own, which no thing has.
            block(
                'depot:  @ident',
                '"Counts what the couriers collect."',
                'role operator',
                'let fleet = couriers',
                block('let total: people = sum(fleet.amount)  @ident', '"People collected"'),
            ),
        ),
        top(
            block(
                'output collected: people = sum(couriers.amount)  @ident',
                '"People collected by every courier"',
                'level',
                'distinct  @ident',
            )
        ),
    )


COPY_NUMBERS = range(1, COPIES + 1)


def amount(k, repair):
    """What copy k adds: k people, twice that once the service is back. A copy that collects as the
    repair ends finds the service back: the repair's line comes first."""
    return k * (2 if k * STEP >= repair else 1)


def test_each_copy_reads_its_own_number(tmp_path):
    model = build(tmp_path, *with_couriers())
    _, trajectory = run(model, 'slow')
    for k in COPY_NUMBERS:
        assert times(trajectory, model.events[f'couriers.{k}.collection.done']) == pytest.approx([k * STEP])
    repair = model.run_values('slow')['service.repair_time']
    env = env_at(model, COPIES * STEP + 5)
    expected = [amount(k, repair) for k in COPY_NUMBERS]
    assert [env[f'couriers_{k}.amount'] for k in COPY_NUMBERS] == pytest.approx(expected)
    # A set of copies fills a list link, and the top level adds a value over the set. Nothing reads
    # the depot's total, so the run's structure leaves the depot out; the whole structure keeps it.
    assert 'depot' in model.left_out[()]['entities']
    assert env_at(model, COPIES * STEP + 5, whole=True)['depot.total'] == pytest.approx(sum(expected))


def test_a_copy_writes_its_number_into_its_expressions(tmp_path):
    model = build(tmp_path, *with_couriers())
    s = model.structure_of('slow')
    assert 't >= 3 * ' in written(s.rules[model.events['couriers.3.collection']].trigger.when)
    assert written(s.outcomes[model.outputs['collected']].expr) == (
        'couriers_1.amount + couriers_2.amount + couriers_3.amount'
    )


@pytest.mark.parametrize(
    ('steps', 'match'),
    [
        ((replace(f'couriers: Courier * {COPIES}', 'couriers: Courier * true'),), 'k is a whole number'),
        # A set has one copy or more.
        (
            (replace(f'couriers: Courier * {COPIES}', 'couriers: Courier * 0'),),
            'k is a whole number, 1 or more',
        ),
        # `copy` is the number of a copy, a word that names nothing else.
        ((member('Courier', 'var copy: people = 0  @ident'),), 'not a usable name'),
        (
            (
                replace(
                    'elapsed(status) >= repair_time:  @ident',
                    'elapsed(status) >= repair_time + copy * 1 h:  @ident',
                ),
            ),
            'not one of a set of copies',
        ),
    ],
    ids=[
        '<lambda>-copies is a whole number1',
        'none',
        '<lambda>-not a usable name',
        '<lambda>-not one of a set of copies',
    ],
)
def test_copies_are_checked(tmp_path, steps, match):
    with pytest.raises(ModelError, match=match):
        build(tmp_path, *with_couriers(), *steps)


# ---- an operation that waits on the start ----------------------------------------------------------
# The attacker prepares for `prepare_time` from t = 0 and then switches the service off: the start
# changes nothing, and the strike fires `prepare_time` after it, unless the attacker is removed by
# then.


def with_operation():
    return (
        member(
            'attacker',
            block('let prepare_time = 5 h  @ident', '"Time to prepare"'),
            block(
                'event strike_when_ready once after prepare_time when count(start) > 0:  @ident',
                block(
                    'done access is not "removed":  @attack',
                    '"{actor} switches the service off."',
                    'switch.position = "off"',
                ),
                block('stopped else:', '"The attacker is removed first."'),
            ),
        ),
        drop('attacker/start/done/0'),
    )


def test_an_operation_starts_at_zero_and_its_first_effect_comes_after_the_preparation(tmp_path):
    model = build(tmp_path, *with_operation())
    values = model.run_values('slow')
    prepare, repair = values['attacker.prepare_time'], values['service.repair_time']
    _, trajectory = run(model, 'slow')
    assert times(trajectory, model.events['attacker.start.done']) == pytest.approx([0])
    assert times(trajectory, model.events['attacker.strike_when_ready.done']) == pytest.approx([prepare])
    assert times(trajectory, model.events['service.repaired.done']) == pytest.approx([prepare + repair])
    users, k = values['service.users'], values['service.service_rate']
    for t in (prepare / 2, prepare + repair + 10, 150.0):
        # Users are served before the strike and again after the repair.
        down = min(t, prepare)
        after = max(0.0, t - prepare - repair)
        expected = users * (1 - math.exp(-k * (down + after)))
        assert trajectory.env_at(t)['service.served'] == pytest.approx(expected, rel=1e-6)


def test_the_attacker_times_from_the_start_of_an_operation(tmp_path):
    model = build(tmp_path, *with_operation())
    removal = 3.0
    prepare = model.run_values('slow_kept')['attacker.prepare_time']
    assert removal < prepare
    _, trajectory = run(model, 'slow_kept', {'responders.removal_time': removal})
    # The responders time their removal from the start, so the strike, which fires when the
    # preparation ends, finds the attacker removed: it is stopped, and the service never fails.
    assert times(trajectory, model.events['responders.clean_up.done']) == pytest.approx([removal])
    assert times(trajectory, model.events['attacker.strike_when_ready.stopped']) == pytest.approx([prepare])
    assert not times(trajectory, model.events['service.fails.done'])


def test_a_start_that_changes_nothing_is_an_event_at_zero(tmp_path):
    model = build(tmp_path, *with_operation())
    # The start is the event `start` of the attacker, and acts as the attacker.
    assert model.initiation['rule'] == model.events['attacker.start']
    assert model.initiation['entity'] == 'attacker'
    # The start is an event at t = 0 that changes nothing.
    for structure in model.structures.values():
        rule = structure.rules[model.events['attacker.start']]
        assert written(rule.trigger.when) == "t >= q(0, 'h')"
        assert not any(part for step in rule.steps() for part in (step.set, step.transfer, step.fire))


# ---- time scales, units that name a text and texts for each occurrence ----------------------------


def with_timescales(*names):
    """An edit step: the time scales of the scenario block."""
    return replace('    horizon 200 h', f'    horizon 200 h\n    timescales {", ".join(names)}')


def test_time_scales_name_the_inputs_that_set_the_shortest_times(tmp_path):
    model = build(tmp_path, with_timescales('service.repair_time', 'service.settle_time / 2'))
    assert list(model.time['timescales']) == ['service.repair_time', 'service.settle_time / 2']
    with pytest.raises(ModelError, match='timescale'):
        build(tmp_path, with_timescales('service.users'))


# The service names the unit of its waiting users in a text value.
WITH_ITEM = (
    member('service', 'input item = "people"'),
    replace('var waiting: people = users', 'var waiting: {item} = users'),
)


def test_a_unit_can_name_a_text_field_of_its_entity(tmp_path):
    plain, model = build(tmp_path), build(tmp_path, *WITH_ITEM)
    assert model.structure_of('slow').quantities['service.waiting'].unit == 'people'
    # The braces change nothing else: the runs are the same.
    for t in (20.0, 60.0):
        assert env_at(model, t)['service.served'] == pytest.approx(env_at(plain, t)['service.served'])


@pytest.mark.parametrize(
    ('steps', 'match'),
    [
        ((replace('var waiting: {item} = users', 'var waiting: {users} = users'),), 'not a text value'),
        ((replace('at service_rate * waiting while', 'at item * waiting while'),), 'is a text'),
        # A number is no text, as an option's value.
        ((member('options:/Access/Keeps access', 'service.item = 3'),), 'a text value is a text in quotes'),
    ],
    ids=['<lambda>-not a text field', '<lambda>-is a text', 'profile'],
)
def test_a_text_field_only_names_a_unit_or_fills_a_doc(tmp_path, steps, match):
    with pytest.raises(ModelError, match=match):
        build(tmp_path, *WITH_ITEM, *steps)


def test_a_doc_can_give_one_text_for_each_time_its_event_happens(tmp_path):
    texts = ['The service is repaired.', 'The service is repaired again.']
    listed = '[' + ', '.join(f'"{text}"' for text in texts) + ']'
    model = build(tmp_path, replace('"The service is repaired."', listed))
    cards = pages(model)['cards'][model.events['service.repaired.done']]
    assert [(c['text'], c['occurrence']) for c in cards] == [(texts[0], 1), (texts[1], 2)]
    assert model.structure_of('slow').rules[model.events['service.repaired']].label == texts[0]


def test_each_occurrence_shows_its_own_card():
    cards = [{'label': 'first', 'occurrence': 1}, {'label': 'second', 'occurrence': 2}, {'label': 'always'}]
    assert [c['label'] for c in cards_for(cards, 1)] == ['first', 'always']
    assert [c['label'] for c in cards_for(cards, 2)] == ['second', 'always']
    # The last text covers every later time.
    assert [c['label'] for c in cards_for(cards, 5)] == ['second', 'always']
    plain = [{'label': 'one'}, {'label': 'two'}]
    assert cards_for(plain, 3) == plain
