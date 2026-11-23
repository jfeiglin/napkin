"""Breakpoints and edits on the oracle, written from docs/design/decisions.md, change 15.

The acceptance example (`tests/program/examples.py`, `pump_dispatch`): a depot draws its dispatcher's
forecast, which never sends, into the occurrence's field `order` and switches on it. Stopped before
the switch and resumed untouched, the run is the unattended run; resumed with `order` edited from
WAIT to SEND, the send branch runs once and the drawn WAIT stays in the history. The rules of an
edit: of a live stored value only, of its type and in its range, never of a finished occurrence; in
the trace and in the edit log (time, breakpoint, target, old, new); an edit of a store a transfer in
the books; inside a stage it joins the stage's writes, before a stage it commits at once. Each
expected value is worked by hand from the example's text.
"""

from fractions import Fraction

import pytest

from napkin.program.build import SINK, Builder, after, assign, event, flow, q, start, this, value
from napkin.program.config import Configuration, Request
from napkin.program.record import Key
from tests.program.examples import DISPATCH, DISPATCH_SWITCH, PAUSES, UNITS, At, Traced, pump_dispatch
from tests.reference.errors import RunFailed
from tests.reference.from_program import config_of, model_of, run_of, traced, value_at
from tests.reference.run import Run

MEDIAN = Configuration(Request(1))


def stopped(program, stops):
    run, failure = run_of(program, MEDIAN, [(stop.at, stop.occurrence, stop.edits) for stop in stops])
    assert failure is None, failure
    assert run.paused is None
    return run


@pytest.mark.parametrize('name', sorted(PAUSES))
def test_the_acceptance_example_after_its_stops(name):
    spares, stops, expected = PAUSES[name]
    program = pump_dispatch(spares)
    run = stopped(program, stops)
    for each in expected:
        if isinstance(each, At):
            assert value_at(run, program, each.key, each.t) == each.value, each
        elif isinstance(each, Traced):
            assert tuple(t for t, _ in traced(run, each.kind, each.part)) == tuple(each.times), each


def entries(run):
    return [(entry.kind, entry.t, entry.label, entry.step, entry.round, entry.origin) for entry in run.trace]


def test_a_stop_resumed_untouched_is_the_unattended_run():
    program = pump_dispatch()
    alone, failure = run_of(program, MEDIAN)
    assert failure is None
    run = stopped(program, PAUSES['untouched'][1])
    assert entries(run) == entries(alone)
    assert (
        run.draws
        == alone.draws
        == [('depot.request_pump.step[0].do[0].draw[0]|depot.request_pump#0', 'WAIT')]
    )
    for key in (Key('depot', ('waits',)), Key('depot', ('spares',)), Key('', ('sent',))):
        assert value_at(run, program, key, 1) == value_at(alone, program, key, 1)


def test_the_edit_explains_the_divergence():
    """Resumed with SEND: the stage runs again from its start, so it draws WAIT again from the draw
    that it kept, and the edit then takes the place of the draw in `order`."""
    run = stopped(pump_dispatch(), PAUSES['sends'][1])
    assert run.draws == [('depot.request_pump.step[0].do[0].draw[0]|depot.request_pump#0', 'WAIT')]
    assert run.edit_log == [
        {
            'time': 0,
            'breakpoint': DISPATCH_SWITCH,
            'owner': DISPATCH,
            'name': 'order',
            'old': 'WAIT',
            'new': 'SEND',
        }
    ]
    kinds = [entry.kind for entry in run.trace if entry.label == DISPATCH]
    assert kinds == ['start', 'draw', 'edit', 'stage', 'done']


def paused_at(program, origin, occurrence=None):
    run = Run(model_of(program), config_of(program, MEDIAN))
    run.breakpoints = [(origin, occurrence)]
    run.run()
    assert run.paused is not None and run.paused['why'] == 'breakpoint'
    return run


def test_a_stop_says_where_it_is_and_what_runs_next():
    run = paused_at(pump_dispatch(), DISPATCH_SWITCH)
    found = {name: run.paused[name] for name in ('at', 'time', 'member', 'occurrence', 'next', 'inside')}
    assert found == {
        'at': DISPATCH_SWITCH,
        'time': 0,
        'member': 'depot',
        'occurrence': DISPATCH,
        'next': DISPATCH_SWITCH,
        'inside': True,
    }
    event = paused_at(pump_dispatch(), 'depot.request_pump')
    found = {name: event.paused[name] for name in ('at', 'occurrence', 'next', 'inside')}
    assert found == {
        'at': 'depot.request_pump',
        'occurrence': DISPATCH,
        'next': 'depot.request_pump.step[0]',
        'inside': False,
    }


def refused(run, owner, name, value):
    with pytest.raises(RunFailed) as caught:
        run.edit(owner, name, value)
    return str(caught.value)


def test_an_edit_keeps_the_type_and_the_range_and_changes_only_live_stored_values():
    run = paused_at(pump_dispatch(), DISPATCH_SWITCH)
    assert 'the type' in refused(run, DISPATCH, 'order', 3)
    assert 'outside its range' in refused(run, 'depot', 'spares', -1)
    assert 'formula' in refused(run, '', 'sent', 2)
    assert 'no stored value' in refused(run, DISPATCH, 'started', 1)
    assert 'no member' in refused(run, 'depot.request_pump#7', 'order', 'SEND')


def test_an_occurrence_that_finished_stays_frozen():
    """The request finishes in round 1 at 0 h; its child `send_pump` runs in round 2, and a stop at
    the child's stage finds the request finished."""
    program = pump_dispatch()
    run = Run(model_of(program), config_of(program, MEDIAN))
    run.breakpoints = [(DISPATCH_SWITCH, DISPATCH), ('depot.send_pump.step[0]', None)]
    run.run()
    run.edit(DISPATCH, 'order', 'SEND')
    run.breakpoints.remove((DISPATCH_SWITCH, DISPATCH))
    run.resume()
    assert run.paused['occurrence'] == 'depot.send_pump#0'
    assert 'frozen' in refused(run, DISPATCH, 'order', 'WAIT')


def tank():
    """A tank of 10 L that delivers 1 L/h to the outside, and an event that at 1 h copies the water
    into `seen`."""
    b = Builder(UNITS)
    store = b.entity(
        'tank',
        value('water', 'L', 10, lower=0, upper=20),
        value('seen', 'L', 0),
        event('look', after(q(1, 'h'), assign(this.seen, this.water))),
        flow('delivery', this.water, SINK, request=q(1, 'L/h')),
    )
    b.setup(start(store.look))
    return b.finish()


def test_an_edit_of_a_store_before_a_stage_commits_at_once_as_a_transfer():
    """Stopped before the stage at 1 h, the water is 10 - 1 = 9 L; edited to 12 L, the stage sees
    12 L, and at 3 h the tank holds 12 - 2 = 10 L. The books hold the edit as 3 L from outside."""
    program = tank()
    run = paused_at(program, 'tank.look.step[0]')
    assert run.paused['inside'] is False
    assert run.edit('tank', 'water', Fraction(12)) == 9
    run.resume()
    run.run(until=3)
    assert value_at(run, program, Key('tank', ('seen',)), 1) == 12
    assert value_at(run, program, Key('tank', ('water',)), 3) == 10
    edits = [entry for entry in run.ledger if entry[0] == 'edit']
    assert [(entry[1], entry[3]) for entry in edits] == [(1, 3)]
    assert not [entry for entry in run.ledger if entry[0] == 'write']
