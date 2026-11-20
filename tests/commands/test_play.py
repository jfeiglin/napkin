"""`napkin play` (`napkin/commands/play.py`): the acceptance example of change 15 at the command line.

The dispatch (`examples.pump_dispatch`, written as a package): a depot asks for a pump at 0 h, the
dispatcher's forecast (SEND 0, WAIT 1) is drawn into the order, and a switch sends a spare or counts
a wait. Stopped before its switch, the command shows the stop with each value's label and what an
edit can give it; resumed untouched, its table is `napkin run`'s, a wait and no pump sent; with the
order changed to SEND, the spare is sent and the wait is not counted; saved, the stop goes on in a
fresh process. The expected values are worked by hand from these rules.
"""

from __future__ import annotations

import io
import os
import re
import subprocess
import sys
from pathlib import Path

from tests.commands.call import napkin, package

ROOT = Path(__file__).resolve().parents[2]

DISPATCH = """\
scenario "Pump dispatch"
    horizon 1 h

record depot_count: assumption "A depot of a test holds one spare pump."

dispatcher:
    forecast = categorical(SEND: 0, WAIT: 1)  @depot_count
        "What the dispatcher does when left alone"

depot:
    spares = 1 in [0,]  @depot_count
        "Spare pumps at the depot"
    waits = 0  @depot_count
        "Requests that waited"
    request_pump = event():  @depot_count
        order: enum[SEND, WAIT] = WAIT
            "The dispatcher's order"
        after 0 h:
            order = dispatcher.forecast.draw()
            switch order:
                SEND when this.spares >= 1:
                    this.send_pump.start()
                WAIT:
                    this.waits += 1
    send_pump = event():  @depot_count
        after 0 h:
            this.spares -= 1

depot.request_pump.start()
sent = formula(count(depot.send_pump.occurrences))
    "Pumps sent"
"""
SWITCH = 'depot.request_pump.step[0].do[1]'
ORDER = 'depot.request_pump#0.order'
SWITCH_LINE = DISPATCH.splitlines().index('            switch order:') + 1


def played(capsys, monkeypatch, *argv, typed=''):
    """`napkin play ARGV` in this process, reading the lines of `typed`."""
    monkeypatch.setattr(sys, 'stdin', io.StringIO(typed))
    return napkin(capsys, 'play', *argv)


def ending(out):
    """The table and the lines under it that end the output of `napkin play`."""
    return re.split(r'The run ends at \S+ h\.\n', out, maxsplit=1)[1].splitlines()


def assert_unattended(capsys, model, table):
    """Play and run give the same table and summary, each pointing to its own full list."""
    found = napkin(capsys, 'run', model)
    assert found.code == 0, found.err
    lines = found.out.splitlines()[1:]
    assert table[:-1] == lines[:-1]
    assert lines[-1] == 'See near_ties in napkin run --json for every entry.'
    assert table[-1] == (
        'For every entry, replay the same stops and edits in Python and read session.record.near_ties().'
    )


def cells(line):
    """The cells of a line of a table, split at two spaces or more."""
    return re.split(r'\s{2,}', line.strip())


def test_play_stops_before_the_switch_shows_the_stop_and_goes_on_as_the_unattended_run(
    tmp_path, capsys, monkeypatch
):
    model = package(tmp_path / 'dispatch', DISPATCH)
    found = played(capsys, monkeypatch, model, '--break', f'{SWITCH}@depot.request_pump#0', typed='go\n')
    assert found.code == 0, found.err
    lines = found.out.splitlines()
    assert lines[0] == 'Pump dispatch: a median run to 1 h'
    stop = lines.index(
        f'Stop 1 at 0 h: before {SWITCH} (switch at {model / "model.scn"}:{SWITCH_LINE}), '
        'in depot.request_pump#0 of depot.'
    )
    assert lines[stop + 1] == 'Next: depot.request_pump.step[0] of depot.request_pump#0, from its start.'
    assert (
        lines[stop + 2]
        == 'Drawn in this stage before the stop: depot.request_pump.step[0].do[0].draw[0] = WAIT.'
    )
    assert [cells(line) for line in lines[stop + 3 : stop + 6]] == [
        ['depot.spares', '1', 'edit: a number', 'Spare pumps at the depot'],
        ['depot.waits', '0', 'edit: a number', 'Requests that waited'],
        [ORDER, 'WAIT', 'edit: SEND or WAIT', "The dispatcher's order"],
    ]
    assert lines[stop + 6 : stop + 8] == ['Edit with PATH = VALUE, or: save FILE, go, quit.', '> go']
    # A wait and no pump sent, as in the run with no breakpoint.
    table = ending(found.out)
    assert_unattended(capsys, model, table)
    assert [cells(line) for line in table[1:4]] == [
        ['depot.spares', '1', '1'],
        ['depot.waits', '1', '1'],
        ['sent', '0', '0'],
    ]


def test_play_with_the_order_changed_to_send_sends_the_spare_and_counts_no_wait(
    tmp_path, capsys, monkeypatch
):
    model = package(tmp_path / 'dispatch', DISPATCH)
    found = played(capsys, monkeypatch, model, '--break', SWITCH, typed=f'{ORDER} = SEND\ngo\n')
    assert found.code == 0, found.err
    assert f'  {ORDER}: WAIT -> SEND' in found.out.splitlines()
    table = ending(found.out)
    assert [cells(line) for line in table[1:4]] == [
        ['depot.spares', '0', '0'],
        ['depot.waits', '0', '0'],
        ['sent', '1', '1'],
    ]
    assert table[-1] == f'edit at 0 h, before {SWITCH}: {ORDER} WAIT -> SEND'


def test_play_gives_the_title_of_each_member_that_a_line_names(tmp_path, capsys, monkeypatch):
    """A member's title follows its name, in brackets, in the stop's line, in the rows of the values,
    and in the lines of an edit (PLAN, change 19)."""
    titled = DISPATCH.replace('depot:\n', 'depot:\n    title "North depot"\n')
    model = package(tmp_path / 'dispatch', titled)
    found = played(capsys, monkeypatch, model, '--break', SWITCH, typed=f'{ORDER} = SEND\ngo\n')
    assert found.code == 0, found.err
    lines = found.out.splitlines()
    stop = next(k for k, line in enumerate(lines) if line.startswith('Stop 1 at 0 h: '))
    assert lines[stop].endswith(', in depot.request_pump#0 of depot (North depot).')
    rows = [cells(line) for line in lines[stop + 3 : stop + 6]]
    assert [row[0] for row in rows] == [
        'depot.spares (North depot)',
        'depot.waits (North depot)',
        f'{ORDER} (North depot)',
    ]
    assert f'  {ORDER} (North depot): WAIT -> SEND' in lines
    assert lines[-1] == f'edit at 0 h, before {SWITCH}: {ORDER} (North depot) WAIT -> SEND'


def in_a_fresh_process(model, path, typed):
    """`python -m napkin play MODEL --from PATH` in a fresh process, reading the lines of `typed`."""
    environment = {**os.environ, 'PYTHONHASHSEED': '4321', 'NAPKIN_STORE': 'off'}
    return subprocess.run(
        [sys.executable, '-m', 'napkin', 'play', str(model), '--from', str(path)],
        cwd=ROOT,
        env=environment,
        input=typed,
        capture_output=True,
        text=True,
        check=False,
        timeout=120,
    )


def test_play_saves_the_stop_and_a_fresh_process_goes_on_from_it(tmp_path, capsys, monkeypatch):
    """Saved untouched and resumed in a fresh process, the run is the unattended one; saved with its
    order changed to SEND, it sends the spare there."""
    model = package(tmp_path / 'dispatch', DISPATCH)
    path = tmp_path / 'stop.checkpoint'
    found = played(capsys, monkeypatch, model, '--break', SWITCH, typed=f'save {path}\n')
    assert found.code == 3, found.err
    assert f'  saved; go on with: napkin play {model} --from {path}' in found.out.splitlines()
    assert found.out.splitlines()[-1] == 'The run stops at its stop 1, before its end.'
    done = in_a_fresh_process(model, path, 'go\n')
    assert done.returncode == 0, done.stderr
    assert_unattended(capsys, model, ending(done.stdout))
    found = played(
        capsys, monkeypatch, model, '--break', SWITCH, typed=f'{ORDER} = SEND\nsave {path}\nquit\n'
    )
    assert found.code == 3, found.err
    done = in_a_fresh_process(model, path, 'go\n')
    assert done.returncode == 0, done.stderr
    assert f'  edited here: {ORDER} = SEND' in done.stdout.splitlines()
    assert [cells(line) for line in ending(done.stdout)[1:4]] == [
        ['depot.spares', '0', '0'],
        ['depot.waits', '0', '0'],
        ['sent', '1', '1'],
    ]


def test_play_refuses_an_edit_that_does_not_hold_with_its_reason_and_keeps_waiting(
    tmp_path, capsys, monkeypatch
):
    model = package(tmp_path / 'dispatch', DISPATCH)
    typed = f'{ORDER} = HOLD\ndepot.spares = -1\ndepot.waits = many\nsent = 2\nnothing = 1\njump\ngo\n'
    found = played(capsys, monkeypatch, model, '--break', SWITCH, typed=typed)
    assert found.code == 0, found.err
    errors = [line for line in found.out.splitlines() if line.startswith('  error: ')]
    assert errors[0] == f"  error: {ORDER} takes a member of SEND, WAIT, not 'HOLD'"
    assert 'is outside its range' in errors[1]
    assert errors[2] == "  error: depot.waits takes a number in its unit, not 'many'"
    assert errors[3] == '  error: sent: no value of the state at the stop has this name'
    assert len(errors) == 5 and 'nothing' in errors[4]
    assert (
        "  'jump' is no command. Edit with PATH = VALUE, or: save FILE, go, quit." in found.out.splitlines()
    )
    assert_unattended(capsys, model, ending(found.out))


def test_play_shows_the_values_of_value_at_each_stop_and_at_the_end(tmp_path, capsys, monkeypatch):
    model = package(tmp_path / 'dispatch', DISPATCH)
    found = played(capsys, monkeypatch, model, '--break', SWITCH, '--value', 'depot.waits,sent', typed='go\n')
    assert found.code == 0, found.err
    lines = found.out.splitlines()
    first = next(k for k, line in enumerate(lines) if line.startswith('Drawn in this stage')) + 1
    assert [cells(line) for line in lines[first : first + 2]] == [
        ['depot.waits', '0', 'edit: a number', 'Requests that waited'],
        ['sent', '0', 'Pumps sent'],
    ]
    assert [cells(line)[0] for line in ending(found.out)[1:3]] == ['depot.waits', 'sent']
    assert ending(found.out)[3] == 'Near-ties (1 total, from 0 h to 0 h)'


def test_play_refuses_a_location_where_it_cannot_stop_and_a_checkpoint_that_is_not_one(
    tmp_path, capsys, monkeypatch
):
    model = package(tmp_path / 'dispatch', DISPATCH)
    found = played(capsys, monkeypatch, model, '--break', 'depot.request_pum')
    assert found.code == 2
    assert (
        '--break depot.request_pum: no event, stage or statement of the model; did you mean depot.request_pump or'
        in found.err
    )
    assert played(capsys, monkeypatch, model).code == 2
    path = tmp_path / 'stop.checkpoint'
    path.write_text('napkin checkpoint 1\n{}', encoding='utf-8')
    assert 'give no --break' in played(capsys, monkeypatch, model, '--from', path, '--break', SWITCH).err
    found = played(capsys, monkeypatch, model, '--from', path)
    assert found.code == 1
    assert found.err.rstrip().endswith('this napkin reads format 2 [checkpoint]')
    found = played(capsys, monkeypatch, model, '--break', SWITCH, '--value', 'depot.wait')
    assert (
        found.code == 2 and '--value depot.wait: no value of the model; did you mean depot.waits' in found.err
    )


# A tank of 2 kL drains at 1 kL/h and takes 3 kL at 1 h: 1 kL then; edited there to 5 kL, it holds
# 8 kL after the stage and 5 kL at 4 h.
TANK = """\
scenario "Tank"
    horizon 4 h

record size: assumption "A tank of a test."

tank:
    water: kL = 2 kL in [0 kL, 10 kL]  @size
        "Water in the tank"
    top_up = event():  @size
        after 1 h:
            this.water += 3 kL
    flow use: this.water -> SINK  @size
        request = 1 kL/h

tank.top_up.start()
"""
KILOLITRES = {
    'L': {'dimensions': {'volume': 1}, 'scale': 1, 'description': 'A litre.'},
    'kL': {'dimensions': {'volume': 1}, 'scale': 1000, 'description': 'A thousand litres.'},
}


def test_play_shows_and_edits_a_value_in_its_declared_unit(tmp_path, capsys, monkeypatch):
    model = package(tmp_path / 'tank', TANK, KILOLITRES)
    found = played(capsys, monkeypatch, model, '--break', 'tank.top_up.step[0]', typed='tank.water = 5\ngo\n')
    assert found.code == 0, found.err
    lines = found.out.splitlines()
    assert ['tank.water', '1 kL', 'edit: a number', 'Water in the tank'] in [cells(line) for line in lines]
    assert '  tank.water: 1 kL -> 5 kL' in lines
    # The edit is a transfer from outside in the tank's books: 4 kL came in.
    table = ending(found.out)
    assert [cells(line) for line in table[1:]] == [
        ['tank.water', 'kL', '2', '5'],
        ['tank.use.actual_rate', 'kL/h', '1', '1'],
        ['tank.use.request', 'kL/h', '1', '1'],
        ['tank.water.external', 'kL', '0', '4'],
        ['edit at 1 h, before tank.top_up.step[0]: tank.water 1 kL -> 5 kL'],
    ]
