"""Flow turnover, the first over-budget piece, and the histories of retired occurrences."""

from dataclasses import replace

import pytest

from napkin.engine.timeline import Plan, Run, read, run
from napkin.engine.timeline.record import Recorder, key_of, requested
from napkin.model.compile import compile_text
from napkin.program.checkpoint import Breakpoint, Checkpoint
from tests.engine.record_history_oracle import check_history_rebuilds
from tests.engine.resume_parity import assert_resume_parity
from tests.engine.test_frozen_occurrences import in_a_fresh_process

UNITS = {'h': {'time': 1}, 'L': {'volume': 1}}

ENDPOINT_TURNOVER = """scenario "Equal-rate pump handoff"
    horizon 6 h
tank:
    stock: L = 20 L
    old_wish: L/h = 1 L/h
    new_wish: L/h = 1 L/h
    first = event():
        flow pump: this.stock -> SINK
            request = formula(this.old_wish)
        after 2 h:
            this.second.start()
    second = event():
        flow pump: this.stock -> SINK
            request = formula(this.new_wish)
        after 3 h
    controls = event():
        after 3 h:
            this.old_wish = 7 L/h
            this.new_wish = 2 L/h
        after 1 h:
            this.old_wish = 9 L/h
    members_total = formula(sum(this.stock.outflow.flows.actual_rate))
    replacements = formula(count(this.second.occurrences))
tank.first.start()
tank.controls.start()
"""
ENDPOINT = 'tank.stock.outflow.actual_rate'
ENDPOINT_PATHS = (ENDPOINT, 'tank.members_total', 'tank.replacements')
HANDOFF = Breakpoint('tank.first.step[0]')

FINISHED_FORMULAS = """scenario "Two readings of a changing level"
    horizon 7 h
yard:
    level = 2
    job = event():
        score = formula(this.level * (1 + t / 1 h))
        echo = formula(this.level)
        after 2 h
    controls = event():
        after 1 h:
            this.level = 3
        after 2 h:
            this.level = 7
            this.job.start()
        after 1 h:
            this.level = 11
        after 2 h:
            this.level = 13
yard.job.start()
yard.controls.start()
"""
FIRST_JOB = ('yard.job#0.score', 'yard.job#0.echo')
SECOND_JOB = ('yard.job#1.score', 'yard.job#1.echo')


def selected(source, paths):
    model = compile_text(source, UNITS)
    keys = tuple(key_of(model.program, path) for path in paths)
    request = replace(model.configuration.request, everything=False, keys=keys)
    return model.program, replace(model.configuration, request=request)


def test_equal_rate_handoff_adds_the_new_pump_to_the_endpoint_reads(monkeypatch):
    reference = check_history_rebuilds(monkeypatch)
    program, configuration = selected(ENDPOINT_TURNOVER, ENDPOINT_PATHS)
    live = Run(Plan.of(program, configuration), (HANDOFF,))
    checkpoint = live.run()
    assert isinstance(checkpoint, Checkpoint) and checkpoint.stop.t == 2
    before = live.plan.dynamic_reads(ENDPOINT)
    record = live.resume()
    assert record.failure is None
    after = live.plan.dynamic_reads(ENDPOINT)
    assert before < after
    assert 'tank.first#0.pump.actual_rate' in before
    assert 'tank.second#0.pump.actual_rate' in after - before

    times = (1, 2, 2.5, 3, 4, 5, 6)
    rates = (1, 1, 1, 2, 2, 0, 0)
    expected = (rates, rates, (0, 1, 1, 1, 1, 1, 1))
    assert tuple(r.values for r in read(record, program, ENDPOINT_PATHS, times)) == expected
    for path, readings in zip(ENDPOINT_PATHS, expected, strict=True):
        history = record.history(key_of(program, path))
        assert tuple(history.at(t) for t in times) == readings
    assert reference.updates and not reference.closed_spans


@pytest.mark.parametrize(('cutoff', 'budget'), [(2, 3), (3, 4)])
def test_first_excess_at_and_after_handoff_matches_both_continuations(cutoff, budget, tmp_path, monkeypatch):
    reference = check_history_rebuilds(monkeypatch)
    program, configuration = selected(ENDPOINT_TURNOVER, ENDPOINT_PATHS)
    full = run(program, configuration)
    assert full.failure is None
    starts = sorted(p.t for h in full.histories if full.manifest.names(h.key) for p in h.pieces)
    assert sum(t < cutoff for t in starts) == budget and starts[budget] == cutoff
    bounded = replace(configuration, request=replace(configuration.request, pieces=budget))
    straight = run(program, bounded)
    assert straight.failure is not None and straight.failure.t == cutoff
    assert straight.failure.detail('budget') == budget
    assert straight == requested(full.within(budget), program)

    live = Run(Plan.of(program, bounded), (HANDOFF,))
    checkpoint = live.run()
    assert isinstance(checkpoint, Checkpoint) and checkpoint.stop.t == 2
    assert_resume_parity(program, bounded, straight, live.resume())
    assert_resume_parity(program, bounded, straight, in_a_fresh_process(program, checkpoint, tmp_path))
    assert reference.updates and not reference.closed_spans


def test_two_jobs_freeze_their_own_score_and_echo(monkeypatch):
    reference = check_history_rebuilds(monkeypatch)
    paths = FIRST_JOB + SECOND_JOB
    program, configuration = selected(FINISHED_FORMULAS, paths)
    record = run(program, configuration)
    assert record.failure is None
    times = (3, 3.5, 4, 5, 6, 7)
    assert tuple(r.values for r in read(record, program, paths, times)) == (
        (9, 9, 9, 9, 9, 9),
        (3, 3, 3, 3, 3, 3),
        (28, 31.5, 55, 66, 66, 66),
        (7, 7, 11, 11, 11, 11),
    )
    assert reference.updates and not reference.closed_spans


def test_changes_at_three_five_and_seven_leave_the_finished_formula_alone(monkeypatch):
    # Add writes to the same input at hours 5 and 7; the original controls already write at 3.
    source = (
        FINISHED_FORMULAS.replace(
            'yard.job.start()',
            """    late = event():
        after 5 h:
            this.level = 17
        after 2 h:
            this.level = 19
yard.job.start()""",
        )
        + 'yard.late.start()\n'
    )
    paths = (*FIRST_JOB, 'yard.level')
    program, configuration = selected(source, paths)
    live = Run(Plan.of(program, configuration))
    reference = check_history_rebuilds(monkeypatch)
    advance, formula = Recorder._advance, Recorder.formula
    boundary = None
    live_calls, rebuilt_calls, frozen_pieces = [], [], []

    def observe_advance(recorder, end):
        nonlocal boundary
        boundary = end
        try:
            advance(recorder, end)
        finally:
            boundary = None
        if recorder is live.recorder and end in (2, 3, 5, 7) and FIRST_JOB[0] in live.frozen:
            frozen_pieces.append((end, tuple(tuple(recorder._histories[p].pieces) for p in FIRST_JOB)))

    def count_formula(recorder, name, *args, **kwargs):
        if name == FIRST_JOB[0] and boundary is not None:
            calls = live_calls if recorder is live.recorder else rebuilt_calls
            calls.append(boundary)
        return formula(recorder, name, *args, **kwargs)

    monkeypatch.setattr(Recorder, '_advance', observe_advance)
    monkeypatch.setattr(Recorder, 'formula', count_formula)
    record = live.run()
    assert record.failure is None
    assert tuple(r.values for r in read(record, program, paths, (3, 5, 7))) == (
        (9, 9, 9),
        (3, 3, 3),
        (7, 17, 19),
    )
    assert live_calls and max(live_calls) <= 2
    assert {3, 5, 7} <= set(rebuilt_calls)
    assert {end for end, _ in frozen_pieces} == {2, 3, 5, 7}
    final = tuple(record.history(key_of(program, p)).pieces for p in FIRST_JOB)
    assert all(pieces == final for _, pieces in frozen_pieces)
    assert reference.updates and not reference.closed_spans
