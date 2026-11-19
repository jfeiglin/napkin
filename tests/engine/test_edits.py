"""Edits at a checkpoint (PLAN, change 15; `napkin/program/checkpoint.py`, `timeline/checkpoints.py`).

An edit gives a live stored value a new value at a stop: at a stop before a stage it commits at once,
and at a stop before a statement it joins the writes of the stage, which sees it, and commits with
the stage. Each edit is one entry `edit` of the trace; a stage that runs again from its start takes
the edits made at its stops again, at their places, and commits each once. An edited run goes on the
same way in place and in a fresh process (a subprocess, which builds the program from the Python code
of `test_checkpoints.py`). The acceptance example of change 15: the dispatch, resumed untouched and
resumed with its order changed from WAIT to SEND. The expected values are worked by hand.
"""

from __future__ import annotations

import pytest

from napkin.engine.report import Lag, report
from napkin.engine.timeline import Plan, Run, read, resume, run
from napkin.program.build import (
    SOURCE,
    Builder,
    flow,
    input_,
    named,
    q,
    start,
    this,
    value,
)
from napkin.program.checkpoint import Checkpoint, CheckpointError, dumps, loads
from napkin.program.config import Configuration, Request
from napkin.program.record import Key
from tests.engine.test_checkpoints import SCENARIOS, UNITS, in_a_fresh_process, ticks
from tests.reference.from_program import run_of, value_at


def edited(case, edits):
    """A run stopped at each hit, edited there by `edits` ({stop: ((target, value), ...)}) and
    resumed in place: (each checkpoint as it stopped, as it was edited, the final record)."""
    made = Run(Plan.of(case.program, case.configuration), case.breakpoints)
    found, stopped, edits_made = made.run(), [], []
    while isinstance(found, Checkpoint):
        stopped.append(found)
        for target, value_ in edits.get(len(stopped) - 1, ()):
            found = made.edit(target, value_)
        edits_made.append(found)
        found = made.resume()
    return stopped, edits_made, found


def test_an_edit_at_a_stop_before_a_stage_commits_at_once(tmp_path):
    """The family's tank holds 6 L at the tick of 2 h; edited to 9 L, it drains at 2 L/h to 3 L at
    5 h, when the alarm starts, and is empty at 6.5 h."""
    case = SCENARIOS['family']()
    stopped, made, final = edited(case, {1: (('tank.water', 9),)})
    assert stopped[1].stop.t == 2 and stopped[1].state.value('tank.water') == 6
    (entry,) = final.entries('edit')
    assert (entry.t, entry.part, entry.owner) == (2, 'tank.tick.step[1]', 'tank.tick#0')
    assert dict(entry.details) == {'breakpoint': 'tank.tick', 'target': 'tank.water', 'old': 6, 'new': 9}
    assert [entry.t for entry in final.entries('start', 'tank.alarm')] == [pytest.approx(5, abs=1e-12)]
    (water,) = read(final, case.program, ['tank.water'], [2, 3, 5, 6.5, 7])
    assert water.values == pytest.approx([9, 7, 3, 0, 0], abs=1e-12)
    assert in_a_fresh_process('family', made, tmp_path) == [*stopped[1:], final]


def test_edits_in_a_stage_join_its_writes_and_commit_once_across_two_stops(tmp_path):
    """Stopped after its draw, the order stage gets 10 orders; stopped before its note, a demand of
    2 L. Run again from its start each time, it adds its order to the 10 and notes the 2 L: 11 orders,
    a note of 2, then 3 once the child adds one at 2 h. Each edit is traced once, at the commit."""
    case = SCENARIOS['ordering']()
    edits = {0: (('depot.orders', 10),), 1: (('depot.demand', 2),)}
    stopped, made, final = edited(case, edits)
    assert [stop.stop.at for stop in stopped] == ['depot.order.step[0].do[1]', 'depot.order.step[0].do[3]']
    # The stage that ran again to its second stop saw the first edit, and nothing of it is visible.
    assert stopped[1].state.value('depot.orders') == 0
    assert [(edit.hit, edit.target) for edit in made[1].edits] == [(1, 'depot.orders'), (2, 'depot.demand')]
    # The old value of an edit in a stage is what the stage sees there: the demand that it drew.
    (drawn,) = final.entries('draw')
    entries = final.entries('edit')
    assert [
        (entry.t, entry.detail('target'), entry.detail('old'), entry.detail('new')) for entry in entries
    ] == [
        (1, 'depot.orders', 0, 10),
        (1, 'depot.demand', drawn.detail('value'), 2),
    ]
    kinds = [entry.kind for entry in final.trace if entry.t == 1]
    assert kinds.index('commit') < kinds.index('edit')
    orders, noted, demand = read(final, case.program, ['depot.orders', 'depot.noted', 'depot.demand'], [1, 2])
    assert (orders.values, noted.values, demand.values) == ((11, 11), (2, 3), (2, 2))
    assert in_a_fresh_process('ordering', made, tmp_path) == [*stopped[1:], final]


def test_the_dispatch_resumes_untouched_and_with_its_order_changed(tmp_path):
    """Unattended, the forecast waits: one wait, no send. Paused before its branch, saved and resumed in
    a fresh process untouched, the same. Resumed with `order` changed from WAIT to SEND, the send branch
    runs once (no spare left, one sent, no wait); the draw of WAIT stays in the trace, and the edit
    explains the change."""
    case = SCENARIOS['dispatch']()
    alone = run(case.program, case.configuration)
    names = ['depot.waits', 'depot.spares', 'sent', 'depot.request_pump#0.order']
    unattended = [reading.values[0] for reading in read(alone, case.program, names, [1])]
    assert unattended == [1, 1, 0, 'WAIT']
    oracle, failed = run_of(case.program, case.configuration)
    assert failed is None
    keys = [Key('depot', ('waits',)), Key('depot', ('spares',)), Key('', ('sent',))]
    assert [value_at(oracle, case.program, key, 1) for key in keys] == unattended[:3]
    checkpoint = run(case.program, case.configuration, case.breakpoints)
    assert checkpoint.state.value('depot.request_pump#0.order') == 'WAIT'
    assert in_a_fresh_process('dispatch', [checkpoint], tmp_path) == [alone]
    sending = checkpoint.edit('depot.request_pump#0.order', 'SEND')
    (sent,) = in_a_fresh_process('dispatch', [sending], tmp_path)
    made = Run(Plan.of(case.program, case.configuration), case.breakpoints)
    made.run()
    made.edit('depot.request_pump#0.order', 'SEND')
    assert made.resume() == sent
    assert [reading.values[0] for reading in read(sent, case.program, names, [1])] == [0, 0, 1, 'SEND']
    assert [entry.owner for entry in sent.entries('start')] == ['depot.request_pump#0', 'depot.send_pump#0']
    (drawn,) = sent.entries('draw')
    assert drawn.detail('value') == 'WAIT' and drawn.owner == 'depot.request_pump#0'
    (entry,) = sent.entries('edit')
    assert (entry.detail('target'), entry.detail('old'), entry.detail('new')) == (
        'depot.request_pump#0.order',
        'WAIT',
        'SEND',
    )


def test_an_edit_that_breaks_a_rule_of_the_run_is_refused_by_name():
    case = SCENARIOS['ordering']()
    made = Run(Plan.of(case.program, case.configuration), case.breakpoints)
    checkpoint = made.run()
    for target, value_, message in (
        ('depot.nowhere', 1, 'no value of the state'),
        ('depot.orders', True, 'holds a number'),
        ('depot.orders', float('inf'), 'a finite number'),
    ):
        with pytest.raises(CheckpointError, match=message):
            made.edit(target, value_)
    dispatch = SCENARIOS['dispatch']()
    made = Run(Plan.of(dispatch.program, dispatch.configuration), dispatch.breakpoints)
    made.run()
    with pytest.raises(CheckpointError, match='takes a member of SEND, WAIT'):
        made.edit('depot.request_pump#0.order', 'MAYBE')
    with pytest.raises(CheckpointError, match='outside its range'):
        made.edit('depot.spares', -1)
    family = SCENARIOS['family']()
    made = Run(Plan.of(family.program, family.configuration), family.breakpoints)
    found = made.run()
    while found.stop.t < 4:
        found = made.resume()
    with pytest.raises(CheckpointError, match=r'finished occurrence tank\.alarm#0, which is frozen'):
        made.edit('tank.alarm#0.done', False)
    with pytest.raises(CheckpointError, match='at no stop'):
        Run(Plan.of(family.program, family.configuration)).edit('tank.water', 1)
    assert checkpoint.edits == ()


def test_an_edit_of_an_input_is_refused_when_the_run_goes_on():
    """An input is fixed for the run: the state holds it, and the engine refuses the edit."""
    b = Builder(UNITS)
    b.entity('tank', input_('size', 'L', 5), value('ticks', '', 0), ticks(1, 2))
    b.setup(start(named('tank').tick))
    program = b.finish()
    made = Run(Plan.of(program, Configuration(Request(3))), SCENARIOS['family']().breakpoints)
    made.run()
    with pytest.raises(CheckpointError, match=r'tank\.size: an edit changes a stored value'):
        made.edit('tank.size', 6)


def test_an_edit_that_lowers_a_tally_withdraws_its_never_falls_proof_for_the_run():
    """A tally filled at 1 L/h never falls, so a lag of it holds; lowered from 2 L to 1 L at the tick of
    2 h, it can fall in this run, and the report says which edit withdrew the proof."""
    b = Builder(UNITS)
    b.entity(
        'tank',
        value('served', 'L', 0, lower=0),
        value('ticks', '', 0),
        flow('fill', SOURCE, this.served, request=q(1, 'L/h')),
        ticks(2),
    )
    b.setup(start(named('tank').tick))
    program = b.finish()
    configuration = Configuration(Request(4))
    lags = {'tank.served': Lag(0.5, 1)}
    plain = report(run(program, configuration), program, configuration, ['tank.served'], [4], lags)
    assert plain.values[0].lag == Lag(0.5, 1)
    made = Run(Plan.of(program, configuration), SCENARIOS['family']().breakpoints)
    made.run()
    made.edit('tank.served', 1)
    record = made.resume()
    (found,) = report(record, program, configuration, ['tank.served'], [4], lags).values
    assert found.lag is None
    assert 'can fall: an edit at 2 h, at tank.tick.step[0], lowered it from 2 to 1 L' in found.note
    assert found.values == (pytest.approx(3),)


def test_a_saved_edited_checkpoint_reads_back_with_its_edits():
    case = SCENARIOS['family']()
    checkpoint = run(case.program, case.configuration, case.breakpoints).edit('tank.water', 9)
    assert loads(dumps(checkpoint)).edits == checkpoint.edits
    assert resume(case.program, loads(dumps(checkpoint))).edits == checkpoint.edits
