"""Edits at a checkpoint (docs/design/decisions.md, change 15; `napkin/program/checkpoint.py`, `timeline/checkpoints.py`).

An edit gives a live stored value a new value at a stop: at a stop before a stage it commits at once,
and at a stop before a statement it joins the writes of the stage, which sees it, and commits with
the stage. Each edit is one entry `edit` of the trace; a stage that runs again from its start takes
the edits made at its stops again, at their places, and commits each once. An edited run goes on the
same way in place and in a fresh process (a subprocess, which loads the program from its artifact). The acceptance example of change 15: the dispatch, resumed untouched and
resumed with its order changed from WAIT to SEND. The expected values are worked by hand.
"""

from __future__ import annotations

import pytest

from napkin.engine.report import Lag, report
from napkin.engine.timeline import Plan, Run, read, resume, run
from napkin.program.build import (
    BOOL,
    SINK,
    SOURCE,
    Builder,
    after,
    event,
    flow,
    input_,
    move,
    named,
    q,
    reset_when,
    start,
    t,
    this,
    value,
    when,
)
from napkin.program.checkpoint import Breakpoint, Checkpoint, CheckpointError, dumps, loads
from napkin.program.config import Configuration, Request
from napkin.program.record import Key
from tests.engine.resume_parity import assert_resume_parity
from tests.engine.test_checkpoints import SCENARIOS, UNITS, in_a_fresh_process, ticks
from tests.program.examples import DISPATCH_SWITCH, PAUSES, At, pump_dispatch
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
    assert dict(entry.details) == {
        'breakpoint': 'tank.tick.step[1]',
        'target': 'tank.water',
        'old': 6,
        'new': 9,
    }
    assert [entry.t for entry in final.entries('start', 'tank.alarm')] == [pytest.approx(5, abs=1e-12)]
    (water,) = read(final, case.program, ['tank.water'], [2, 3, 5, 6.5, 7])
    assert water.values == pytest.approx([9, 7, 3, 0, 0], abs=1e-12)
    results = in_a_fresh_process(case.program, made, tmp_path)
    for expected, actual in zip([*stopped[1:], final], results, strict=True):
        assert_resume_parity(case.program, case.configuration, expected, actual)


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
    results = in_a_fresh_process(case.program, made, tmp_path)
    for expected, actual in zip([*stopped[1:], final], results, strict=True):
        assert_resume_parity(case.program, case.configuration, expected, actual)


def held(record, program, item):
    """Whether a record holds an expectation of `examples.py`: a value at a time, in its declared
    unit, or the times of the entries of a kind and a part."""
    if isinstance(item, At):
        (found,) = read(record, program, [item.key], [float(item.t)])
        return found.values[0] == pytest.approx(item.value)
    return [entry.t for entry in record.entries(item.kind, item.part)] == pytest.approx(item.times)


@pytest.mark.parametrize('name', sorted(PAUSES))
def test_the_acceptance_example_of_change_15(name, tmp_path):
    """`examples.PAUSES`: the dispatch stopped before its switch (and before its draw), edited there,
    resumed in place and in a fresh process: untouched it is the unattended run; with `order` changed
    from WAIT to SEND the send branch runs once and the drawn WAIT stays in the trace; with no spare
    SEND is not eligible; two stops in the stage keep both edits once. The oracle agrees."""
    spares, stops, expected = PAUSES[name]
    program, configuration = pump_dispatch(spares), Configuration(Request(1))
    breakpoints = tuple(Breakpoint(stop.at, stop.occurrence or '') for stop in stops)
    made = Run(Plan.of(program, configuration), breakpoints)
    found, stopped, edits_made = made.run(), [], []
    for stop in stops:
        assert isinstance(found, Checkpoint) and (found.stop.at, found.stop.owner) == (
            stop.at,
            stop.occurrence,
        )
        stopped.append(found)
        for key, value_ in stop.edits:  # the oracle's form: a record key, a value in its declared unit
            found = made.edit(key, value_)
        edits_made.append(found)
        found = made.resume()
    assert not isinstance(found, Checkpoint) and found.failure is None
    assert all(held(found, program, item) for item in expected)
    if not any(stop.edits for stop in stops):
        assert_resume_parity(program, configuration, run(program, configuration), found)
    oracle, failed = run_of(
        program, configuration, [(stop.at, stop.occurrence, stop.edits) for stop in stops]
    )
    assert failed is None
    for item in expected:
        if isinstance(item, At):
            assert value_at(oracle, program, item.key, item.t) == item.value
    (drawn,) = found.entries('draw')
    assert drawn.detail('value') == 'WAIT'
    edits = [entry for entry in found.entries('edit') if entry.detail('target').endswith('order')]
    assert [(entry.detail('old'), entry.detail('new')) for entry in edits] == [
        ('WAIT', 'SEND') for stop in stops if stop.edits and stop.at == DISPATCH_SWITCH
    ]
    results = in_a_fresh_process(program, edits_made, tmp_path)
    for expected, actual in zip([*stopped[1:], found], results, strict=True):
        assert_resume_parity(program, configuration, expected, actual)


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
    with pytest.raises(CheckpointError, match='a parameter or a built-in field of its occurrence'):
        made.edit('depot.request_pump#0.active', False)
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
    made = Run(Plan.of(program, Configuration(Request(3))), (Breakpoint('tank.tick.step[0]'),))
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
    made = Run(Plan.of(program, configuration), (Breakpoint('tank.tick.step[0]'),))
    made.run()
    made.edit('tank.served', 1)
    record = made.resume()
    (found,) = report(record, program, configuration, ['tank.served'], [4], lags).values
    assert found.lag is None
    assert 'can fall: an edit at 2 h, at tank.tick.step[0], lowered tank.served from 2 to 1 L' in found.note
    assert found.values == (pytest.approx(3),)


def test_a_saved_edited_checkpoint_reads_back_with_its_edits():
    case = SCENARIOS['family']()
    checkpoint = run(case.program, case.configuration, case.breakpoints).edit('tank.water', 9)
    assert loads(dumps(checkpoint)).edits == checkpoint.edits
    assert resume(case.program, loads(dumps(checkpoint))).edits == checkpoint.edits


def scaled():
    """A tank of 2 kL that drains at 1 kL/h, and a tick at 1 h."""
    b = Builder({'h': {'time': 1}, 'L': {'volume': 1}, 'kL': ({'volume': 1}, 1000)})
    b.entity(
        'tank',
        value('water', 'kL', 2, lower=0),
        value('ticks', '', 0),
        flow('drain', this.water, SINK, request=q(1, 'kL/h')),
        ticks(1),
    )
    b.setup(start(named('tank').tick))
    return b.finish(), Configuration(Request(3))


@pytest.mark.parametrize('target', [Key('tank', ('water',)), 'tank.water'], ids=['key', 'engine'])
def test_an_edit_names_a_value_as_the_model_does_in_its_unit_or_by_its_engine_name(target, tmp_path):
    """At 1 h the tank holds 1 kL; edited to 1.5 kL (by its key, in kL) or to 1,500 L (by its engine
    name, in canonical litres), it is empty at 2.5 h; its books hold 0.5 kL brought in from outside."""
    program, configuration = scaled()
    made = Run(Plan.of(program, configuration), (Breakpoint('tank.tick.step[0]'),))
    checkpoint = made.run()
    edited = made.edit(target, 1.5 if isinstance(target, Key) else 1500)
    final = made.resume()
    water, external = read(final, program, ['tank.water', 'tank.water.external'], [1, 2, 2.5, 3])
    assert water.values == pytest.approx([1.5, 0.5, 0, 0], abs=1e-12)
    assert external.values == pytest.approx([0.5, 0.5, 0.5, 0.5])
    (entry,) = final.entries('edit')
    assert (entry.detail('target'), entry.detail('old'), entry.detail('new')) == ('tank.water', 1000, 1500)
    assert checkpoint.edit(target, 1.5 if isinstance(target, Key) else 1500) == edited
    (fresh,) = in_a_fresh_process(program, [edited], tmp_path)
    assert_resume_parity(program, configuration, final, fresh)
    with pytest.raises(CheckpointError, match='outside its range'):
        made_again = Run(Plan.of(program, configuration), (Breakpoint('tank.tick.step[0]'),))
        made_again.run()
        made_again.edit(Key('tank', ('water',)), -0.5)


def test_an_edit_of_a_store_is_a_transfer_from_or_to_outside_in_its_books():
    """The family's tank: 6 L at 2 h edited to 9 L (3 L in), then at 4 h, holding 5 L, to 1 L (4 L out):
    its books hold +3 L from 2 h and -1 L from 4 h, and it is empty at 4.5 h."""
    case = SCENARIOS['family']()
    _, _, final = edited(case, {1: (('tank.water', 9),), 4: (('tank.water', 1),)})
    water, external = read(final, case.program, ['tank.water', 'tank.water.external'], [1, 2, 3, 4, 4.5])
    assert water.values == pytest.approx([8, 9, 7, 1, 0], abs=1e-12)
    assert external.values == pytest.approx([0, 3, 3, -1, -1])


def test_an_edit_withdraws_the_proof_that_an_event_cannot_start():
    """A repair starts when the road is open, which nothing writes: it cannot start (a proof). Opened
    by an edit at 0.5 h, it starts at 1 h, and the trail says that the edit withdrew the proof."""
    b = Builder(UNITS)
    b.entity(
        'plant',
        value('open', BOOL, False),
        value('used', 'L', 0, lower=0),
        value('stock', 'L', 10, lower=0),
        value('ticks', '', 0),
        flow('idle', this.stock, SINK, request=q(0, 'L/h')),
        event(
            'repair',
            when(this.open & (t >= q(1, 'h')), start(this.repair), reset=reset_when(False)),
            after(q(1, 'h'), move(q(2, 'L'), this.stock, this.used)),
        ),
        ticks(0.5),
    )
    b.setup(start(named('plant').tick))
    program, configuration = b.finish(), Configuration(Request(4))

    def repair(record):
        (found,) = report(record, program, configuration, ['plant.used'], [4]).values
        return next(used for used in found.trail if (used.kind, used.origin) == ('event', 'plant.repair'))

    alone = repair(run(program, configuration))
    assert not alone.exercised and alone.why.startswith('it cannot start under this configuration: ')
    made = Run(Plan.of(program, configuration), (Breakpoint('plant.tick.step[0]'),))
    made.run()
    made.edit(Key('plant', ('open',)), True)
    record = made.resume()
    found = repair(record)
    assert found.exercised and found.why.startswith(
        'it started at 1 h (an edit at 0.5 h, at plant.tick.step[0], set plant.open from false to true: '
    )
    assert 'withdrew for this run the proof that it cannot start' in found.why
    assert read(record, program, ['plant.used'], [4])[0].values == (pytest.approx(2),)
