"""The session (`napkin/session.py`): one run played through the engine's checkpoints. It stops at
breakpoints, shows the stop (where, which occurrence, what runs next, the values asked for in their
declared units with their labels), takes edits of live stored values, saves the stop and goes on
from it in a fresh process, and keeps the log of its stops and edits, which plays the same run again.

The acceptance example of change 15 (`examples.pump_dispatch`): a depot asks for a pump at 0 h, the
dispatcher's forecast (SEND 0, WAIT 1) is drawn into the occurrence's `order`, and a switch sends a
spare or counts a wait. Unattended it waits once; paused before its switch, saved, reopened in a
fresh process and resumed untouched it is the same run; with `order` changed to SEND the send branch
runs once, the drawn WAIT stays in the trace and the edit says why the run differs. A battery of
4 h, which drains at 1 kW and takes 3 kWh at 1 h, gives the units and the labels: it holds
2 - t kWh before the recharge and 5 - t kWh after it, and edited to 5 kWh at 1 h, 9 - t kWh after it.
A clock whose stages come due at 1, 2 and 3 h gives stops at three times. Each expected value is
worked by hand from these rules. No test reads the catalogue.

The rules of the removed resolver's tests (`tests/engine/test_decision_resolver.py`) that still hold
are here: a stop shows nothing of its stage, its view is read-only and reads formulas; an edit that
does not hold is refused with no fallback; a log plays the same draws again in a sampled run; a log
played again goes on to the stops after it; a save that fails changes nothing.
"""

from __future__ import annotations

import os
import re
import subprocess
import sys
import textwrap
from dataclasses import FrozenInstanceError, replace
from pathlib import Path

import pytest

from napkin import session as session_module
from napkin import store
from napkin.engine.timeline import read, run
from napkin.model.compile import compile_text
from napkin.program.artifact import Artifact
from napkin.program.build import Builder, add, after, event, named, q, start, this, value
from napkin.program.checkpoint import Breakpoint, CheckpointError, Edit, decode, dumps
from napkin.program.config import Configuration, Request
from napkin.program.record import Key, Unavailable
from napkin.session import Log, Session, play
from napkin.store import fingerprint
from tests.engine.test_checkpoints import SCENARIOS
from tests.program.examples import DISPATCH, DISPATCH_SWITCH, UNITS, pump_dispatch

ROOT = Path(__file__).resolve().parents[1]
DISPATCH_DRAW = 'depot.request_pump.step[0].do[0].draw[0]'
ORDER = f'{DISPATCH}.order'
BEFORE_SWITCH = Breakpoint(DISPATCH_SWITCH, DISPATCH)
BEFORE_DRAW = Breakpoint('depot.request_pump.step[0].do[0]', DISPATCH)
ONE_HOUR = Configuration(Request(1))

BATTERY = textwrap.dedent("""\
    scenario "Battery"
        horizon 4 h
    battery:
        charge: kWh = 2 kWh in [0 kWh, 10 kWh]
            "Charge of the battery"
        share = formula(this.charge / 10 kWh)
            "Share of a full charge"
        input reserve: kWh = 1 kWh
        recharge = event(amount: kWh):
            mode: enum[SLOW, FAST] = SLOW
                "Mode of the recharge"
            after 1 h:
                this.charge += amount
        flow use: this.charge -> SINK
            request = 1 kW
    battery.recharge.start(3 kWh)
    """)
RECHARGE = 'battery.recharge.step[0]'


def battery():
    return compile_text(BATTERY, UNITS)


def clock(horizon=4):
    """A clock whose stages come due at 1, 2 and 3 h, each adding one to `ticks`, and a breakpoint at
    each stage."""
    b = Builder(UNITS)
    b.entity(
        'clock',
        value('ticks', '', 0),
        event('tick', *(after(q(1, 'h'), add(this.ticks, 1)) for _ in range(3))),
    )
    b.setup(start(named('clock').tick))
    breakpoints = [Breakpoint(f'clock.tick.step[{k}]') for k in range(3)]
    return b.finish(), Configuration(Request(horizon)), breakpoints


def values_at(record, program, path, times):
    return read(record, program, [path], times)[0].values


def finished(session):
    """The record of a session gone on to its end from where it is."""
    while session.advance() is not None:
        pass
    return session.record


# ---- the acceptance example ---------------------------------------------------------------------


def test_the_dispatch_unattended_waits_once_and_sends_nothing():
    program = pump_dispatch()
    session = Session(program, ONE_HOUR)
    assert session.advance() is None and session.checkpoint is None and session.stops == []
    record = session.record
    assert record == run(program, ONE_HOUR)
    assert values_at(record, program, 'depot.waits', [0, 1]) == (1, 1)
    assert values_at(record, program, 'sent', [1]) == (0,)
    (drawn,) = record.entries('draw')
    assert (drawn.t, drawn.part, drawn.detail('value')) == (0, DISPATCH_DRAW, 'WAIT')
    assert session.log == Log()


def test_the_dispatch_stops_before_its_switch_and_shows_the_stop():
    """The stop is before the switch, inside the stage: the stage has drawn WAIT into `order`, which
    no one sees yet, and it runs again from its start when the run goes on."""
    session = Session(pump_dispatch(), ONE_HOUR, [BEFORE_SWITCH])
    checkpoint = session.advance()
    assert checkpoint is session.checkpoint
    view = session.view()
    stop = view.stop
    assert (stop.hit, stop.at, stop.owner, stop.member, stop.t) == (1, DISPATCH_SWITCH, DISPATCH, 'depot', 0)
    assert stop.next == 'depot.request_pump.step[0]' and view.next == ((DISPATCH, stop.next),)
    assert view.where is None  # a program built by hand has no side table
    shown = {item.path: item for item in view.values}
    assert list(shown) == ['depot.spares', 'depot.waits', ORDER]
    assert (shown['depot.spares'].value, shown['depot.waits'].value) == (1, 0)
    assert (shown[ORDER].value, shown[ORDER].choices, shown[ORDER].editable) == (
        'WAIT',
        ('SEND', 'WAIT'),
        True,
    )
    assert [(entry.part, entry.detail('value')) for entry in view.drawn] == [(DISPATCH_DRAW, 'WAIT')]
    # Nothing of the stage is in the record: no commit, no wait counted.
    assert checkpoint.record.entries('commit') == ()
    # A value that the caller asks for: a formula, a built-in field and a distribution, none editable.
    sent, started, forecast = session.view(['sent', f'{DISPATCH}.started', 'dispatcher.forecast']).values
    assert (sent.value, started.value) == (0, 0)
    assert (forecast.value.family, forecast.value.params, forecast.value.outcomes) == (
        'categorical',
        (0, 1),
        ('SEND', 'WAIT'),
    )
    assert not any(item.editable for item in (sent, started, forecast))
    with pytest.raises(FrozenInstanceError):
        view.values[0].value = 3


def test_the_dispatch_resumed_untouched_is_the_unattended_run():
    program = pump_dispatch()
    session = Session(program, ONE_HOUR, [BEFORE_SWITCH])
    session.advance()
    assert session.advance() is None
    assert session.record == run(program, ONE_HOUR)
    assert fingerprint(session.record) == fingerprint(run(program, ONE_HOUR))


def test_the_dispatch_with_its_order_changed_to_send_sends_once_and_keeps_its_draw():
    """SEND is eligible with one spare: the send branch starts `send_pump` once, at 0 h, which takes
    the spare; no wait is counted. The drawn WAIT stays in the trace, and the edit is traced with
    its old and new value."""
    program = pump_dispatch()
    session = Session(program, ONE_HOUR, [BEFORE_SWITCH])
    session.advance()
    checkpoint = session.edit(ORDER, 'SEND')
    assert [(edit.hit, edit.target, edit.value) for edit in checkpoint.edits] == [
        (1, Key(DISPATCH, ('order',)), 'SEND')
    ]
    assert session.view().edits == checkpoint.edits
    assert session.advance() is None
    record = session.record
    assert values_at(record, program, 'depot.waits', [1]) == (0,)
    assert values_at(record, program, 'depot.spares', [1]) == (0,)
    assert values_at(record, program, 'sent', [1]) == (1,)
    assert [entry.t for entry in record.entries('start', 'depot.send_pump')] == [0]
    assert [entry.detail('value') for entry in record.entries('draw')] == ['WAIT']
    (edit,) = record.entries('edit')
    assert dict(edit.details) == {
        'breakpoint': DISPATCH_SWITCH,
        'target': ORDER,
        'old': 'WAIT',
        'new': 'SEND',
    }


# A fresh process: it loads the program from its artifact and goes on from a saved stop to the end.
FRESH = """
import sys
from napkin.program.artifact import load
from napkin.program.checkpoint import encode
from napkin.session import Session

session = Session.load(sys.argv[2], load(sys.argv[1]).program)
while session.advance() is not None:
    pass
print(encode(session.record))
"""


def in_a_fresh_process(program, session, folder):
    """The record that a fresh process gives for the stop at which `session` waits, saved."""
    Artifact(program).save(folder / 'program')
    session.save(folder / 'stop.checkpoint')
    environment = {**os.environ, 'PYTHONHASHSEED': '4321', 'NAPKIN_STORE': 'off'}
    done = subprocess.run(
        [sys.executable, '-c', FRESH, str(folder / 'program'), str(folder / 'stop.checkpoint')],
        cwd=ROOT,
        env=environment,
        capture_output=True,
        text=True,
        check=False,
        timeout=120,
    )
    assert done.returncode == 0, done.stderr
    return decode(done.stdout)


def test_the_dispatch_saved_at_its_stop_goes_on_in_a_fresh_process_as_the_run_straight_through(tmp_path):
    program = pump_dispatch()
    session = Session(program, ONE_HOUR, [BEFORE_SWITCH])
    session.advance()
    assert in_a_fresh_process(program, session, tmp_path) == run(program, ONE_HOUR)
    # The edited stop, saved, goes on there as here.
    session.edit(ORDER, 'SEND')
    fresh = in_a_fresh_process(program, session, tmp_path)
    assert fresh == finished(session)
    assert values_at(fresh, program, 'sent', [1]) == (1,)


def test_a_session_goes_on_from_a_saved_stop_in_this_process_and_its_log_starts_there(tmp_path):
    program = pump_dispatch()
    session = Session(program, ONE_HOUR, [BEFORE_SWITCH])
    session.advance()
    session.edit(ORDER, 'SEND')
    session.save(tmp_path / 'stop.checkpoint')
    again = Session.load(tmp_path / 'stop.checkpoint', program, configuration=ONE_HOUR)
    assert again.checkpoint == session.checkpoint and again.view().edits == session.view().edits
    assert again.log == session.log
    assert finished(again) == finished(session)


# ---- the log --------------------------------------------------------------------------------------


def test_the_log_of_two_stops_in_one_stage_plays_the_same_run_again():
    """`examples.PAUSES['two_stops']`: 5 waits given before the draw and SEND before the switch. The
    stage runs again from its start at each stop and keeps both edits once: 5 waits (the send
    branch adds none) and one pump sent."""
    program = pump_dispatch()
    session = Session(program, ONE_HOUR, [BEFORE_DRAW, BEFORE_SWITCH])
    session.advance()
    session.edit('depot.waits', 5)
    assert session.advance().stop.at == DISPATCH_SWITCH
    session.edit(ORDER, 'SEND')
    record = finished(session)
    assert values_at(record, program, 'depot.waits', [1]) == (5,)
    assert values_at(record, program, 'sent', [1]) == (1,)
    log = session.log
    assert [stop.hit for stop in log.stops] == [1, 2] and [edit.hit for edit in log.edits] == [1, 2]
    assert fingerprint(play(program, ONE_HOUR, log)) == fingerprint(record)
    # Played again, the session waits at the log's last stop with its edits made, as it did.
    replay = Session(program, ONE_HOUR, log=log)
    checkpoint = replay.advance()
    assert checkpoint.stop == log.stops[-1]
    assert checkpoint.edits == log.edits and replay.stops == list(log.stops)
    assert finished(replay) == record


@pytest.mark.parametrize('seed', [2, 17])
def test_the_log_of_a_sampled_run_plays_its_draws_again(seed):
    """The engine's `ordering` case: at 1 h a stage draws a demand from uniform(1 L, 3 L), then stops
    before it queues a child and before it notes the demand. Given 10 orders at the first stop and a
    demand of 2 L at the second, the stage counts 11 orders and notes 2, and the child adds one at
    2 h. The draw is made once, with the value that the stops showed, and the log plays the same run."""
    case = SCENARIOS['ordering']()
    configuration = replace(case.configuration, seed=seed)
    session = Session(case.program, configuration, case.breakpoints)
    session.advance()
    (shown,) = session.view().drawn
    session.edit('depot.orders', 10)
    session.advance()
    assert session.view().drawn == (shown,)
    session.edit('depot.demand', 2)
    record = finished(session)
    (drawn,) = record.entries('draw')
    assert drawn == shown and 1 <= drawn.detail('value') <= 3
    assert record.entries('edit')[1].detail('old') == drawn.detail('value')
    assert values_at(record, case.program, 'depot.orders', [3]) == (11,)
    assert values_at(record, case.program, 'depot.noted', [1, 2]) == (2, 3)
    assert fingerprint(play(case.program, configuration, session.log)) == fingerprint(record)


def test_a_replayed_log_goes_on_to_the_stops_after_it():
    """A log of the first of three stops passes it with its edit (ticks 10 at 1 h, 11 after the
    stage) and waits there; the session then stops at 2 h and 3 h, and ends with 13 ticks."""
    program, configuration, breakpoints = clock()
    session = Session(program, configuration, breakpoints)
    session.advance()
    session.edit('clock.ticks', 10)
    replay = Session(program, configuration, log=session.log)
    assert replay.advance().stop.t == 1
    assert [replay.advance().stop.t, replay.advance().stop.t] == [2, 3]
    assert replay.advance() is None
    assert values_at(replay.record, program, 'clock.ticks', [1, 2, 3, 4]) == (11, 12, 13, 13)


def test_a_log_of_another_run_is_refused_by_name_and_plays_no_further():
    program, configuration, breakpoints = clock()
    session = Session(program, configuration, breakpoints)
    session.advance()
    session.edit('clock.ticks', 10)
    session.advance()
    log = session.log
    moved = replace(log, stops=(log.stops[0], replace(log.stops[1], t=2.5)))
    replay = Session(program, configuration, log=moved)
    with pytest.raises(CheckpointError, match='the log does not play again: its stop 2 is before'):
        replay.advance()
    with pytest.raises(CheckpointError, match='the log does not play again'):
        replay.advance()
    # Within the tolerance in time of a crossing, a stop is the same stop.
    near = replace(log, stops=(log.stops[0], replace(log.stops[1], t=2 + 1e-9)))
    assert play(program, configuration, near) == play(program, configuration, log)
    other = replace(log, breakpoints=(breakpoints[1], breakpoints[2]))
    with pytest.raises(CheckpointError, match=re.escape('its stop 1 is before clock.tick.step[0] in')):
        play(program, configuration, other)
    late = replace(log, stops=log.stops[:1], edits=(Edit(2, 'clock.ticks', 3.0),))
    with pytest.raises(CheckpointError, match='after its last stop'):
        Session(program, configuration, log=late)


def test_a_stop_of_the_log_after_the_horizon_need_not_come_and_one_before_it_must():
    """The log stops at 1 h and at 2 h, with 10 ticks given at 1 h. A run to 1.5 h reaches only the
    first stop: 11 ticks at 1.5 h. A log that holds a third stop at 2 h, which the run does not make,
    is refused."""
    program, configuration, breakpoints = clock()
    session = Session(program, configuration, breakpoints)
    session.advance()
    session.edit('clock.ticks', 10)
    session.advance()
    shorter = Configuration(Request(1.5))
    record = play(program, shorter, session.log)
    assert values_at(record, program, 'clock.ticks', [1.5]) == (11,)
    stops = session.log.stops
    one_more = replace(session.log, stops=(*stops, replace(stops[1], hit=3)))
    with pytest.raises(CheckpointError, match='the run ends before its stop 3'):
        play(program, Configuration(Request(2.5)), replace(one_more, breakpoints=breakpoints[:2]))


def test_a_stop_of_the_log_at_or_after_the_end_that_the_budget_gives_need_not_come(tmp_path):
    """The log stops at 1 h, 2 h and 3 h, with 10 ticks given at 1 h. A record of the ticks within
    two pieces holds their start, 0 at 0 h, and the edit and the stage's commit give two more at 1 h
    (10, then 11): by hand its budget ends it at 1 h, and the run stops there by its budget, at its
    stop at 2 h, before any checkpoint (`program/record.py`, "The budget"). So the log's stops at
    2 h and 3 h cannot come, as a stop after the horizon cannot: the log plays as that record, fresh
    and through the store, cold and warm under its own budget, and a
    record within three pieces, which ends at 2 h, reaches the stop at 2 h and not the one at 3 h. A
    stop before the end must come: a log whose third stop is at 1.5 h is refused."""
    program, configuration, breakpoints = clock()
    session = Session(program, configuration, breakpoints)
    session.advance()
    session.edit('clock.ticks', 10)
    log = finished(session) and session.log
    ticks = Key('clock', ('ticks',))
    for pieces, end in ((2, 1), (3, 2)):
        small = Configuration(Request(4, everything=False, keys=(ticks,), pieces=pieces))
        wide = Configuration(Request(4, everything=False, keys=(ticks,)))
        fresh = play(program, small, log)
        with store.use(tmp_path / str(pieces)):
            cold = store.run(program, small, log)
            store.run(program, wide, log)
            warm = store.run(program, small, log)
        assert cold == fresh == warm  # one record, its histories included
        for record in (fresh, cold, warm):
            assert record.failure.detail('budget') == pieces and record.end == end, record.failure
            found = values_at(record, program, 'clock.ticks', [0.5, end])
            assert found[0] == 0 and isinstance(found[1], Unavailable), found
    stops = log.stops
    early = replace(log, stops=(*stops[:2], replace(stops[2], t=1.5)))
    with pytest.raises(CheckpointError, match='the run ends before its stop 3'):
        play(program, Configuration(Request(4, everything=False, keys=(ticks,), pieces=3)), early)


# ---- edits and views ----------------------------------------------------------------------------


def test_an_edit_that_does_not_hold_is_refused_by_name_and_changes_nothing():
    """No fallback: a member that is not one of the enum's, a number below its range, a formula, a
    built-in field (which its start gives, as an input) and a number for a text are refused, and the
    run goes on as the unattended one."""
    program = pump_dispatch()
    session = Session(program, ONE_HOUR, [BEFORE_SWITCH])
    session.advance()
    refused = {
        (ORDER, 'HOLD'): 'takes a member of SEND, WAIT',
        ('depot.spares', -1): 'outside its range',
        ('sent', 2): 'no value of the state',
        (f'{DISPATCH}.started', 0.5): 'a value of kind input',
        (ORDER, 3): 'holds a text',
    }
    for (path, given), message in refused.items():
        with pytest.raises(CheckpointError, match=message):
            session.edit(path, given)
    assert session.checkpoint.edits == ()
    assert finished(session) == run(program, ONE_HOUR)


def test_a_value_of_a_finished_occurrence_is_frozen():
    """Sent, the request finishes in the round of its switch, before the send's stage: its order is
    shown, and no edit changes it."""
    session = Session(pump_dispatch(), ONE_HOUR, [BEFORE_SWITCH, Breakpoint('depot.send_pump.step[0]')])
    session.advance()
    session.edit(ORDER, 'SEND')
    assert session.advance().stop.at == 'depot.send_pump.step[0]'
    (order,) = session.view([ORDER]).values
    assert (order.value, order.editable) == ('SEND', False)
    with pytest.raises(CheckpointError, match=f'finished occurrence {re.escape(DISPATCH)}, which is frozen'):
        session.edit(ORDER, 'WAIT')


def test_a_view_gives_each_value_in_its_declared_unit_with_its_label_and_an_edit_takes_that_unit():
    """At the recharge's stage, 1 h: 2 - 1 = 1 kWh, a share of 0.1, the parameter 3 kWh. Edited to
    5 kWh, the stage adds 3 kWh: 8 kWh at 1 h, then 1 kW less each hour, 5 kWh at 4 h."""
    model = battery()
    session = Session(model.program, model.configuration, [Breakpoint(RECHARGE)], table=model.table)
    session.advance()
    view = session.view()
    assert (view.where.kind, view.where.line) == ('stage', 12)
    shown = {item.path: item for item in view.values}
    assert list(shown) == [
        'battery.charge',
        'battery.share',
        'battery.reserve',
        'battery.recharge#0.amount',
        'battery.recharge#0.mode',
    ]
    charge, share, reserve = shown['battery.charge'], shown['battery.share'], shown['battery.reserve']
    assert (charge.value, charge.unit, charge.label, charge.editable) == (
        pytest.approx(1),
        'kWh',
        'Charge of the battery',
        True,
    )
    assert (share.value, share.label, share.editable) == (pytest.approx(0.1), 'Share of a full charge', False)
    assert (reserve.value, reserve.unit, reserve.editable) == (1, 'kWh', False)
    amount, mode = shown['battery.recharge#0.amount'], shown['battery.recharge#0.mode']
    assert (amount.value, amount.unit, amount.editable) == (3, 'kWh', False)
    assert (mode.value, mode.choices, mode.label, mode.editable) == (
        'SLOW',
        ('SLOW', 'FAST'),
        'Mode of the recharge',
        True,
    )
    with pytest.raises(CheckpointError, match='parameter'):
        session.edit('battery.recharge#0.amount', 4)
    with pytest.raises(CheckpointError, match='a value of kind input'):
        session.edit('battery.reserve', 2)
    session.edit('battery.charge', 5)
    record = finished(session)
    assert values_at(record, model.program, 'battery.charge', [1, 2, 4]) == pytest.approx((8, 7, 5))
    (edit,) = record.entries('edit')
    # The trace holds the edit in canonical units: Wh.
    assert (edit.detail('old'), edit.detail('new')) == (pytest.approx(1000), 5000)


def test_a_view_gives_the_title_of_the_member_that_it_names():
    """A member's title (PLAN, change 19) comes from the side table: the stop's member's, and each
    value's member's, an occurrence's being its receiver's; the root's values have none."""
    model = compile_text(BATTERY.replace('\nbattery:\n', '\nbattery:\n    title "Main battery"\n'), UNITS)
    session = Session(model.program, model.configuration, [Breakpoint(RECHARGE)], table=model.table)
    session.advance()
    view = session.view()
    assert view.title == 'Main battery'
    assert {item.title for item in view.values} == {'Main battery'}
    assert (session.title('battery'), session.title('battery.recharge#0'), session.title('')) == (
        'Main battery',
        'Main battery',
        None,
    )
    untitled = Session(*battery_parts(), [Breakpoint(RECHARGE)])
    untitled.advance()
    assert untitled.view().title is None and {item.title for item in untitled.view().values} == {None}


def battery_parts():
    model = battery()
    return model.program, model.configuration


def test_a_stop_in_the_setup_shows_the_values_of_the_root_and_runs_the_setup_next():
    program = pump_dispatch()
    session = Session(program, ONE_HOUR, [Breakpoint('setup[0]')])
    session.advance()
    view = session.view()
    assert (view.stop.owner, view.stop.next, view.next) == ('', 'setup', (('', 'setup'),))
    assert [(item.path, item.value) for item in view.values] == [('sent', 0)]
    # The request has not started: its order has no value yet, and takes no edit.
    (order,) = session.view([ORDER]).values
    assert isinstance(order.value, Unavailable) and not order.editable
    with pytest.raises(CheckpointError, match='no value of the state'):
        session.edit(ORDER, 'SEND')


# ---- saving and going on --------------------------------------------------------------------------


def test_a_saved_stop_goes_on_only_with_its_program_its_engine_and_its_run(tmp_path, monkeypatch):
    program = pump_dispatch()
    session = Session(program, ONE_HOUR, [BEFORE_SWITCH])
    session.advance()
    path = tmp_path / 'stop.checkpoint'
    session.save(path)
    with pytest.raises(CheckpointError, match='of another program'):
        Session.load(path, pump_dispatch(spares=2))
    with pytest.raises(CheckpointError, match='another run: it differs in its request'):
        Session.load(path, program, configuration=Configuration(Request(2)))
    (tmp_path / 'other').write_bytes(b'napkin program 2\n')
    with pytest.raises(CheckpointError, match='not a napkin checkpoint'):
        Session.load(tmp_path / 'other', program)
    monkeypatch.setattr(session_module, 'engine_version', lambda: '0' * 64)
    with pytest.raises(CheckpointError, match='another version of the engine'):
        Session.load(path, program)


def test_a_save_writes_the_whole_file_or_none_and_the_session_still_waits(tmp_path):
    program = pump_dispatch()
    session = Session(program, ONE_HOUR, [BEFORE_SWITCH])
    with pytest.raises(CheckpointError, match='waits at no stop'):
        session.save(tmp_path / 'early.checkpoint')
    session.advance()
    with pytest.raises(OSError):
        session.save(tmp_path / 'missing' / 'stop.checkpoint')
    session.save(tmp_path / 'stop.checkpoint')
    assert sorted(path.name for path in tmp_path.iterdir()) == ['stop.checkpoint']
    assert (tmp_path / 'stop.checkpoint').read_bytes() == dumps(session.checkpoint)
    assert finished(session) == run(program, ONE_HOUR)
    with pytest.raises(CheckpointError, match='reached its end'):
        session.advance()


def test_a_location_where_a_run_cannot_stop_is_refused_when_the_session_is_made():
    with pytest.raises(CheckpointError, match='no event, stage or statement'):
        Session(pump_dispatch(), ONE_HOUR, [Breakpoint('depot.request_pump.step[7]')])
    with pytest.raises(ValueError, match='breakpoints of the log'):
        Session(pump_dispatch(), ONE_HOUR, [BEFORE_SWITCH], log=Log())
