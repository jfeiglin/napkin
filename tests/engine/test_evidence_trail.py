"""The evidence trail reads the named state that an event tests for its memory, in its `when`, as
any other test there, and it follows an output into the outputs that it reads, into
the delay of its lag and into what limits a flow. A flow that is asked to move and delivers nothing is
not exercised.

The fixture is the analytic transfer of tests/build.py with a lock on the service. Only the event
`arm` arms the lock, at the input `arm_time`, and its record cites an assumption. Each test runs
the fixture with `arm_time` before and after the stop time `end`. An input whose edit changes an
output must be in that output's trail; a part that no route from the output reads must not be. The
last test gives the transfer outputs that read other outputs.

The trail is the engine's (`evidence_trail`) over the run's structure. No part of these structures is
left out (`model.left_out` is empty), so the run's structure is the whole structure that a report's
trail reads.
"""

from __future__ import annotations

import copy
import math

import pytest

from napkin.engine.report import evaluate_outputs, evidence_trail
from napkin.expressions import UnitSystem
from tests.build import (
    BASIS,
    append,
    compiled,
    edit,
    event,
    evidence_library,
    flow,
    in_place,
    member,
    named,
    output,
    parameter,
    replace,
    run,
    scenario,
    share,
    stock,
    system,
)

# The assumption that supports the event that arms the lock, and its record.
ARMED_BY = 'RT-FIXTURE'
ARMED_RECORD = f'record armed_by: assumption {ARMED_BY} "Fixture: the lock arms the stop."'
LOCK_PARTS = {'service.arm', 'service.lock', 'service.arm_time'}
# More people than the service can serve before the horizon: the stop time sets the served total.
MOST_PEOPLE = replace('input n: people = 10 people', 'input n: people = 100 people')


def locked_stop(tested):
    """The transfer, whose stop turns the service off at `end` and moves the lock to spent.

    tested: the stop leaves the lock only from armed (its condition tests the lock, which it changes:
    the lock is its memory); the rest of its condition names only the clock, so that test is the only
    route from the stop to `arm`. Otherwise the stop happens once and sets the lock to spent at `end`,
    whatever the lock holds. Either stop sets the state to off, as the transfer's stop does.
    """
    stop = (
        replace(
            'event stop when state is "on" and t >= end:',
            'event stop when lock is "armed" and t >= end:' if tested else 'event stop once when t >= end:',
        ),
        member('service/stop', 'lock = "spent"'),
    )
    return edit(
        scenario(),
        MOST_PEOPLE,
        member(
            'service',
            parameter('arm_time', 1, 'h', 1, 48),
            named('lock', 'open', 'armed', 'spent'),
            event(
                'arm',
                't >= arm_time',
                once=False,
                transition='lock "open" -> "armed"',
                doc='Arm',
                records='@armed_by',
            ),
        ),
        *stop,
        append(ARMED_RECORD),
    )


def runs(source):
    """(served total at the horizon, evidence trail) of run `a`, with the lock armed halfway to
    `end` and halfway from `end` to the horizon."""
    lib = evidence_library()
    model = compiled(source, lib)
    assert not any(model.left_out[model.runs['a']['starts']].values())
    end = model.run_values('a')['service.end']
    horizon = model.time['horizon']
    out = []
    for arm_time in (end / 2, (end + horizon) / 2):
        rs, trajectory = run(source, 'a', lib, values={'service.arm_time': arm_time})
        final = evaluate_outputs({'resolved': rs, 'trajectory': trajectory}, lib, [horizon])[0]
        out.append(
            (final['values']['delivered'], evidence_trail(rs, trajectory, lib, UnitSystem(lib['units'])))
        )
    return out


def test_a_trigger_reads_the_state_that_gives_it_its_memory():
    (early, early_trail), (late, late_trail) = runs(locked_stop(tested=True))
    # The stop waits for the lock: armed after `end`, the service runs longer and serves more.
    assert late > early
    for trail in (early_trail, late_trail):
        delivered = trail['outcomes']['delivered']
        assert set(delivered['exercised']) >= LOCK_PARTS
        assert 'service.stop' in delivered['exercised']
        assert ARMED_BY in trail['records']


def test_a_trigger_that_sets_a_state_without_testing_it_does_not_read_it():
    (early, early_trail), (late, late_trail) = runs(locked_stop(tested=False))
    # The stop comes at `end` whatever the lock holds: when the lock is armed changes nothing.
    assert math.isclose(late, early, rel_tol=1e-9, abs_tol=1e-9)
    for trail in (early_trail, late_trail):
        delivered = trail['outcomes']['delivered']
        assert 'service.stop' in delivered['exercised']
        assert not LOCK_PARTS & (set(delivered['exercised']) | set(delivered['possible']))
        assert not LOCK_PARTS & set(trail['parts'])
        assert ARMED_BY not in trail['records']


# The assumption that supports the output `delivered`, in a record written in place under it.
SERVED_BY = 'RT-FIXTURE'
SERVED_RECORD = in_place(
    'assumption', 'Fixture: the service counts the people it serves.', assumption=SERVED_BY
)


def chained_outputs():
    """The transfer with outputs that read outputs: `reported` reads only `delivered`, `reported_again`
    reads only `reported`, and `kept` reads `delivered` and the input `kept_share`, which no other
    output reads. More people wait than the service can serve before it stops, so the served total
    is `rate * end`."""
    outputs = (
        output(
            'delivered', 'service.served', 'people', doc='Delivered', records=None, under=(SERVED_RECORD,)
        ),
        output('reported', 'delivered', 'people', doc='Reported'),
        output('reported_again', 'reported', 'people', doc='Reported again'),
        output('kept', 'delivered * service.kept_share', 'people', doc='Kept'),
    )
    return edit(
        scenario(),
        MOST_PEOPLE,
        member('service', parameter('kept_share', 0.5, 'fraction', 0, 1, doc='Share kept')),
        replace(output('delivered', 'service.served', 'people', doc='Delivered'), '\n'.join(outputs)),
    )


def test_an_output_that_reads_outputs_carries_their_evidence():
    source = chained_outputs()
    lib = evidence_library()
    model = compiled(source, lib)
    assert not any(model.left_out[model.runs['a']['starts']].values())
    values = model.run_values('a')
    horizon = model.time['horizon']
    end, share = values['service.end'], values['service.kept_share']
    # People an hour: the rate in its own unit, times the scale of that unit.
    unit = model.inputs['service.rate']['unit']
    rate = values['service.rate'] * lib['units'][unit]['scale']

    def final(**edits):
        rs, trajectory = run(source, 'a', lib, values=edits)
        row = evaluate_outputs({'resolved': rs, 'trajectory': trajectory}, lib, [horizon])[0]['values']
        return row, evidence_trail(rs, trajectory, lib, UnitSystem(lib['units']))

    (row, trail), (shorter, _), (other_share, _) = (
        final(),
        final(**{'service.end': end / 2}),
        final(**{'service.kept_share': share / 2}),
    )
    # The served total is rate * end: halving the stop time halves every output that reads it.
    for name in ('delivered', 'reported', 'reported_again'):
        assert math.isclose(row[name], rate * end, rel_tol=1e-9)
        assert math.isclose(shorter[name], rate * end / 2, rel_tol=1e-9)
        # The share kept changes no output that only reads what was delivered.
        assert other_share[name] == row[name]
    assert math.isclose(other_share['kept'], row['kept'] / 2, rel_tol=1e-9)

    outcomes = trail['outcomes']
    delivered = set(outcomes['delivered']['exercised'])
    assert {'service.end', 'service.rate', 'service.served', 'service.stop'} <= delivered
    for name, reads in (('reported', {'delivered'}), ('reported_again', {'reported', 'delivered'})):
        # Each output that it reads, directly or through another output, is a part of its trail with
        # everything that output's trail exercised.
        assert set(outcomes[name]['exercised']) == delivered | reads
        assert set(outcomes[name]['possible']) == set(outcomes['delivered']['possible'])
        assert 'service.kept_share' not in set(outcomes[name]['exercised']) | set(outcomes[name]['possible'])
    assert set(outcomes['kept']['exercised']) == delivered | {'delivered', 'service.kept_share'}
    # The basis of an output that another output reads is the basis of that part: the record written
    # in place under `delivered`, and `@fixture`, the named identity record that `reported` cites.
    assert trail['parts']['delivered'] == {'kind': 'assumption', 'assumption': SERVED_BY}
    assert trail['parts']['reported'] == {'name': BASIS.removeprefix('@'), 'kind': 'identity'}
    assert 'kept' not in trail['parts'] and 'reported_again' not in trail['parts']
    assert SERVED_BY in trail['records']


# ---- what limits a flow, and the delay of a lag -------------------------------------------------
# A source stock that starts at the input `amount` pours into a sink at 2 people an hour, so the sink
# holds min(amount, 2 t). `reported` reports the sink `delay` hours late, and `again` reads
# `reported`. The inputs `amount` and `delay` each rest on an assumption record that no other part
# cites.

AMOUNT, DELAY = 'RT-AMOUNT', 'RT-DELAY'
AMOUNT_RECORD = f'record amount: assumption {AMOUNT} "Fixture: the source holds it."'
DELAY_RECORD = f'record delay: assumption {DELAY} "Fixture: reports come late."'
RATE = 2  # people an hour


def library_with(*identifiers):
    """The evidence library with one more assumption record for each identifier."""
    lib = evidence_library()
    record = next(a for a in lib['assumptions'] if a['id'] == 'RT-FIXTURE')
    for identifier in identifiers:
        lib['assumptions'].append({**copy.deepcopy(record), 'id': identifier, 'statement': identifier})
    return lib


def poured(amount, delay):
    """(the values at 10 h, the evidence trail) of the pour with these inputs."""
    source = system(
        parameter('amount', 5, 'people', 1, 40, doc='Start amount', records='@amount'),
        parameter('delay', 1, 'h', 0, 8, doc='Report delay', records='@delay'),
        stock('source', 'amount', doc='Source'),
        stock('sink', 0, doc='Sink'),
        flow('pour', 'source -> sink', f'{RATE} people/h'),
        horizon=10,
        outputs=(
            output('poured', 's.sink', 'people', doc='Poured'),
            output('reported', 's.sink', 'people', doc='Reported', under=('lag s.delay',)),
            output('again', 'reported', 'people', doc='Reported again'),
        ),
        records=(AMOUNT_RECORD, DELAY_RECORD),
    )
    lib = library_with(AMOUNT, DELAY)
    rs, trajectory = run(source, 'a', lib, values={'s.amount': amount, 's.delay': delay})
    row = evaluate_outputs({'resolved': rs, 'trajectory': trajectory}, lib, [10])[0]['values']
    return row, evidence_trail(rs, trajectory, lib, UnitSystem(lib['units']))


def test_a_flow_depends_on_the_stock_that_it_draws_on():
    for amount in (5, 10):
        row, trail = poured(amount, 1)
        # The source runs dry before 10 h: the amount, through the source, sets what the flow delivers.
        assert row['poured'] == pytest.approx(min(amount, RATE * 10))
        assert {'s.pour', 's.source', 's.amount'} <= set(trail['outcomes']['poured']['exercised'])
        assert AMOUNT in trail['records']


def test_an_output_depends_on_the_delay_of_its_lag():
    rows = {}
    for delay in (1, 4):
        # More than the flow moves in 10 h: the sink holds 2 t, reported `delay` hours late.
        rows[delay], trail = poured(40, delay)
        assert rows[delay]['reported'] == pytest.approx(RATE * (10 - delay))
        outcomes = trail['outcomes']
        for name in ('reported', 'again'):
            assert 's.delay' in outcomes[name]['exercised']
        assert 's.delay' not in set(outcomes['poured']['exercised']) | set(outcomes['poured']['possible'])
        assert DELAY in trail['records']
    assert rows[1]['poured'] == rows[4]['poured']


# ---- a flow that is asked to move and delivers nothing ------------------------------------------
# Each fixture asks its flows for 2 people an hour, and none delivers: its source is empty and
# nothing fills it, a share's limit of 0 serves no one, or one pair of a flow that moves two pairs
# together draws on an empty stock. A flow that moves nothing is possible, not exercised, and what
# holds it back stays in the trail.

ASKED = f'{RATE} people/h'
STARVED = {
    'empty_source': (
        (stock('empty', 0, doc='Empty'), stock('x', 0, doc='X'), flow('drain', 'empty -> x', ASKED)),
        {'s.empty'},
    ),
    'zero_limit': (
        (
            stock('pool', 10, doc='Pool'),
            stock('x', 0, doc='X'),
            stock('y', 0, doc='Y'),
            parameter('limit', 0, 'people/h', doc='Limit'),
            flow('to_x', 'pool -> x', ASKED),
            flow('to_y', 'pool -> y', ASKED),
            share('pool', 'limit'),
        ),
        {'s.pool', 's.limit'},
    ),
    'blocked_pair': (
        (
            stock('full', 10, doc='Full'),
            stock('empty', 0, doc='Empty'),
            stock('x', 0, doc='X'),
            stock('y', 0, doc='Y'),
            flow('both', ['full -> x', 'empty -> y'], ASKED),
        ),
        {'s.full', 's.empty'},
    ),
}


@pytest.mark.parametrize('kind', sorted(STARVED))
def test_a_flow_that_delivers_nothing_is_not_exercised(kind):
    members, holders = STARVED[kind]
    source = system(*members, horizon=10, outputs=(output('got', 's.x', 'people', doc='Got'),))
    lib = evidence_library()
    rs, trajectory = run(source, 'a', lib)
    (row,) = evaluate_outputs({'resolved': rs, 'trajectory': trajectory}, lib, [10])
    assert row['values']['got'] == pytest.approx(0, abs=1e-9)
    got = evidence_trail(rs, trajectory, lib, UnitSystem(lib['units']))['outcomes']['got']
    assert set(rs.flows) <= set(got['possible'])
    assert not set(rs.flows) & set(got['exercised'])
    assert holders <= set(got['exercised'])


def test_an_output_that_counts_a_trigger_depends_on_the_trigger_and_its_time():
    # The output counts the times that `ping` happens: once, at the input `ping_time`.
    source = system(
        parameter('ping_time', 1, 'h', 0.5, 2, doc='Ping time'),
        named('flag', 'no', 'yes'),
        event('ping', 't >= ping_time', 'flag = "yes"'),
        horizon=4,
        outputs=(
            output(
                'pings',
                'count(s.ping) * 1 episodes',
                'episodes',
                'instantaneous',
                doc='Pings',
                under=('signed',),
            ),
        ),
    )
    lib = evidence_library()
    rs, trajectory = run(source, 'a', lib)
    (row,) = evaluate_outputs({'resolved': rs, 'trajectory': trajectory}, lib, [4])
    assert row['values']['pings'] == 1
    trail = evidence_trail(rs, trajectory, lib, UnitSystem(lib['units']))['outcomes']['pings']
    assert {'s.ping', 's.ping_time'} <= set(trail['exercised'])
