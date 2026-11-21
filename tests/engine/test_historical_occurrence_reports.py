"""A historical occurrence key selects the same writable field, comparison scale and report evidence."""

from dataclasses import replace

from napkin.engine.report import report
from napkin.engine.timeline import Plan, Run
from napkin.engine.timeline.record import key_of
from napkin.model.compile import compile_text
from napkin.program.artifact import loads
from napkin.program.checkpoint import Breakpoint, Checkpoint, dumps
from napkin.program.checkpoint import loads as load_checkpoint

UNITS = {'h': {'time': 1}, 'L': {'volume': 1}}


SCENARIO = """scenario "Which shift's meter was read?"
    horizon 2.5 h
plant:
    input anchor: h = 0 h @schedule
    input slow: L/h = 1 L/h @slow_meter
    input fast: L/h = 2 L/h @fast_meter
    input calibrated: L/h = 3 L/h @calibration
    input spare: L/h = 4 L/h @spare_meter
    spare_log: L/h = 0 L/h
    stock: L = 20 L
    shift = event(quick: bool):
        zero: L = 0 L scale (1000000000 L if quick else 1 L)
        flow pipe: this.stock -> SINK
            request = formula(this.fast if quick else this.slow)
        after 4 h
    schedule = event():
        after 1 h:
            this.shift.start(false)
        after 1 h:
            this.shift.occurrences.at(this.anchor).pipe.request = formula(this.calibrated)
            this.spare_log = this.spare
    older = formula(this.shift.occurrences.at(this.anchor).pipe.request)
    latest = formula(this.shift.occurrences.at(t).pipe.request)
    old_guard = formula(this.shift.occurrences.at(this.anchor).zero == 0.001 L)
plant.shift.start(false)
plant.shift.start(true)
plant.schedule.start()
record schedule: source "Shift register."
record slow_meter: source "Slow meter."
record fast_meter: source "Fast meter."
record calibration: source "Calibrated meter."
record spare_meter: source "Spare meter."
"""


def test_an_older_occurrence_selected_at_a_tied_start_keeps_its_own_reads_after_a_write():
    source_model = compile_text(SCENARIO, UNITS)
    paths = ['plant.older', 'plant.latest', 'plant.old_guard']
    request = replace(
        source_model.configuration.request,
        everything=False,
        keys=tuple(key_of(source_model.program, name) for name in paths),
    )
    config = replace(source_model.configuration, request=request)
    machine = Run(Plan.of(source_model.program, config), (Breakpoint('plant.schedule.step[1]'),))
    stop = machine.run()
    assert isinstance(stop, Checkpoint) and stop.stop.t == 2
    saved = load_checkpoint(dumps(stop))
    physical = Run.restored(Plan.of(source_model.program, config), saved).resume()
    assert physical == machine.resume()
    assert physical.failure is None

    # Freshly decoded program objects force historical plan replay even in the source-backed case.
    # Return to the same instant after querying the future and reverse the requested path order.
    for artifact_only in (False, True):
        artifact = loads(source_model.artifact().data())
        evidence = {'table': artifact.table} if artifact_only else {'model': source_model.declared}
        for at, old, current, selected, recent in [
            (2.5, 3, 1, 'calibration', 'slow_meter'),
            (0.5, 2, 2, 'fast_meter', 'fast_meter'),
            (1, 2, 1, 'fast_meter', 'slow_meter'),
            (2, 3, 1, 'calibration', 'slow_meter'),
        ]:
            rows = report(
                physical, artifact.program, config, paths[::-1] if artifact_only else paths, [at], **evidence
            )
            values = {r.path: r for r in rows.values}
            assert [values[path].values for path in paths] == [(old,), (current,), (True,)]
            for path, expected in [(paths[0], {'schedule', selected}), (paths[1], {recent})]:
                cited = {c for part in values[path].trail if part.exercised for c in part.records}
                assert cited == expected, (artifact_only, at, path)


def test_a_stage_assigned_request_credits_only_the_inputs_read_by_that_definition():
    model = compile_text(SCENARIO.replace('.at(this.anchor)', '.at(t)'), UNITS)
    path = 'plant.latest'
    cfg = replace(
        model.configuration,
        request=replace(model.configuration.request, everything=False, keys=(key_of(model.program, path),)),
    )
    result = Run(Plan.of(model.program, cfg)).run()
    assert result.failure is None
    for original in (False, True):
        artifact = loads(model.artifact().data())
        evidence = {'model': model.declared} if original else {'table': artifact.table}
        for at, amount, citation in [(2, 3, 'calibration'), (0.5, 2, 'fast_meter'), (1, 1, 'slow_meter')]:
            (row,) = report(result, artifact.program, cfg, [path], [at], **evidence).values
            assert row.values == (amount,)
            assert {r for part in row.trail if part.exercised for r in part.records} == {citation}
            if at == 2:
                assert any(p.origin == 'plant.schedule.step[1]' and p.exercised for p in row.trail)


def test_a_frozen_formula_credits_the_defining_stage_before_a_later_same_time_commit():
    model = compile_text(
        """scenario "Two definitions at the finish"
    horizon 3 h
plant:
    input first: L = 1 L @first
    input second: L = 2 L @second
    chosen = formula(this.first)
    sample = event():
        saved = formula(this.chosen)
        after 2 h
    writer = event():
        after 1 h:
            this.chosen = formula(this.second)
        after 1 h:
            this.chosen = formula(this.first)
plant.sample.start()
plant.writer.start()
record first: source "First reading."
record second: source "Second reading."
""",
        UNITS,
    )
    result = Run(Plan.of(model.program, model.configuration)).run()
    assert result.failure is None
    for original in (True, False):
        artifact = loads(model.artifact().data())
        evidence = {'model': model.declared} if original else {'table': artifact.table}
        paths = ['plant.sample#0.saved', 'plant.chosen']
        rows = report(result, artifact.program, model.configuration, paths, [2], **evidence).values
        for row, amount, citation, stage in zip(rows, (2, 1), ('second', 'first'), (0, 1), strict=True):
            assert row.values == (amount,)
            assert {r for p in row.trail if p.exercised for r in p.records} == {citation}
            assert any(p.origin == f'plant.writer.step[{stage}]' and p.exercised for p in row.trail)
