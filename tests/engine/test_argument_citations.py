"""The source of an event argument survives capture, completion and record serialization."""

from dataclasses import replace

import pytest

from napkin.engine import run
from napkin.engine.report import report
from napkin.model.compile import compile_text
from napkin.program.artifact import value_of
from napkin.program.canonical import value_bytes
from napkin.program.config import InputValue

SOURCE = """scenario "Equal readings"
    horizon 3 h
yard:
    input left: L = 2 L @left_meter
    input right: L = 2 L @right_meter
    input use_left: bool = true @selection
    job = event(amount: L, spare: L):
        when t >= 1 h:
            chosen = this.left if this.use_left else this.right
            forwarded = chosen
            this.job.start(forwarded, this.right)
        after 1 h
yard.job.start(yard.right, yard.left)
record left_meter: source "Left meter."
record right_meter: source "Right meter."
record selection: source "Meter selector."
"""


@pytest.mark.parametrize('use_left', [False, True])
def test_a_trigger_start_credits_only_what_each_argument_read_after_reloading(use_left):
    model = compile_text(SOURCE, {'h': {'time': 1}, 'L': {'volume': 1}})
    cfg = replace(model.configuration, inputs=(InputValue('yard', 'use_left', use_left),))
    record = value_of(value_bytes(run(model.program, cfg)))
    assert record.failure is None
    expected = {
        'yard.job#0.amount': {'right_meter'},
        'yard.job#0.spare': {'left_meter'},
        'yard.job#1.amount': {'selection', 'left_meter' if use_left else 'right_meter'},
        'yard.job#1.spare': {'right_meter'},
    }
    for t in (1.5, 2.5):
        for row in report(record, model.program, cfg, list(expected), [t], table=model.table).values:
            cited = {cite for item in row.trail if item.exercised for cite in item.records}
            assert (row.values, cited) == ((2,), expected[row.path]), (t, row.path)


def test_an_overwritten_argument_credits_the_writing_stage_even_if_the_value_is_equal():
    source = """scenario "An overwritten argument"
    horizon 3 h
yard:
    input left: L = 2 L @left_meter
    input right: L = 2 L @right_meter
    job = event(amount: L):
        derived = formula(amount)
        after 1 h:
            amount = this.right
        after 1 h
yard.job.start(yard.left)
record left_meter: source "Original meter."
record right_meter: source "Replacement meter."
"""
    model = compile_text(source, {'h': {'time': 1}, 'L': {'volume': 1}})
    cfg = model.configuration
    record = value_of(value_bytes(run(model.program, cfg)))
    paths = ['yard.job#0.amount', 'yard.job#0.derived']
    actual = {}
    for t in (0.5, 1.5, 2.5):
        for row in report(record, model.program, cfg, paths, [t], table=model.table).values:
            assert row.values == (2,)
            actual[t, row.path] = {cite for item in row.trail if item.exercised for cite in item.records}
    assert actual == {
        (t, path): {'left_meter' if t < 1 else 'right_meter'} for t in (0.5, 1.5, 2.5) for path in paths
    }
