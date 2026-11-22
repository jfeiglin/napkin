"""Citations of a solver result follow the branch used for the reported solve."""

from dataclasses import replace

import pytest

from napkin.engine import run
from napkin.engine.report import report
from napkin.engine.timeline.record import key_of
from napkin.model.compile import compile_text

MODEL = '''scenario "Two measured limits"
    horizon 2 h
yard:
    input low: L/h = 2 L/h @low_reading
    input high: L/h = 9 L/h @high_reading
    use_low: bool = true
    water: L = 0 L
    flow tap: SOURCE -> this.water
        request = 20 L/h
    value = formula(this.tap.actual_rate)
    choose = solver:
        inputs:
            pipe = this.tap
            use_low = this.use_low
            small = this.low
            large = this.high
        solve_for:
            pipe.actual_rate
        constraints:
            pipe.actual_rate <= (small if use_low else large)
        objective:
            maximize(pipe.actual_rate)
    flip = event():
        after 1 h:
            this.use_low = false
yard.flip.start()
record low_reading: source "Low measured limit."
record high_reading: source "High measured limit."
'''


@pytest.mark.parametrize('selective', [False, True])
def test_each_solver_answer_credits_the_limit_read_by_its_own_constraint(selective):
    model = compile_text(MODEL, {'h': {'time': 1}, 'L': {'volume': 1}})
    program, cfg = model.program, model.configuration
    path = 'yard.value'
    if selective:
        cfg = replace(cfg, request=replace(cfg.request, everything=False, keys=(key_of(program, path),)))
    record = run(program, cfg)
    assert record.failure is None
    observed = []
    for when in (1.5, 0.5):
        row = report(record, program, cfg, [path], [when], table=model.artifact().table).values[0]
        used = {citation for step in row.trail if step.exercised for citation in step.records}
        observed.append((row.values[0], used))
    assert observed == [(9, {'high_reading'}), (2, {'low_reading'})]
