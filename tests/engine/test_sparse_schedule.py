"""A Sparse group computes its settings with one schedule, each value after what it reads
(`sparse.Vector.schedule`). A value that fails is held: only a taken side that reads it fails."""

import pytest

from napkin.engine import run
from tests.engine.test_threshold_transfer_placement import use_method

SOURCE = """scenario "A failure on one side"
    horizon 1 h
yard:
    stock: L = 1 L in [0,]
    drained: L = 0 L
    zero: formula(L) = formula(this.stock - this.stock)
    broken: formula(L/h) = formula(1 L/h * (1 L / this.zero))
    flow drain: this.stock -> this.drained
        request = formula({request})
"""


@pytest.mark.parametrize('taken', [False, True], ids=['untaken', 'taken'])
def test_a_failure_fails_the_run_only_where_a_taken_side_reads_it(taken, monkeypatch):
    request = (
        'this.broken if this.stock >= 0 L else 0.5 L/h'
        if taken
        else '0.5 L/h if this.stock >= 0 L else this.broken'
    )
    model = use_method(SOURCE.format(request=request), 'sparse', monkeypatch, 'drain')
    record = run(model.program, model.configuration)
    if taken:
        assert record.failure is not None
        assert 'a division by zero' in record.failure.detail('message')
    else:
        assert record.failure is None
