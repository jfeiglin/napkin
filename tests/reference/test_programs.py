"""The programs of `tests/program/examples.py` on the oracle: one test for each example, which runs
its program under its configuration and checks every result that it expects, exactly.

An `At` is a value at a key, after the last round at its time, in the declared unit of the value; a
`Traced` the times (and rounds) of the trace entries of a kind for a part; a `Fails` a failure whose
message holds a text, at a time. A run that expects no failure must not fail."""

import pytest

from tests.program.examples import EXAMPLES, At, Fails, Traced
from tests.reference.from_program import run_of, traced, value_at


@pytest.mark.parametrize('name', sorted(EXAMPLES))
def test_program(name):
    example = EXAMPLES[name]()
    run, failure = run_of(example.program, example.configuration)
    expected_failures = [each for each in example.expected if isinstance(each, Fails)]
    if expected_failures:
        assert failure is not None, f'{name}: the run was expected to fail'
        for each in expected_failures:
            assert each.message in str(failure), f'{name}: {failure}'
            assert each.t is None or run.view.t == each.t, f'{name}: failed at {run.view.t} h'
    else:
        assert failure is None, f'{name}: {failure}'
        assert run.paused is None, f'{name}: the run waits for {run.paused}'
    for each in example.expected:
        if isinstance(each, At):
            got = value_at(run, example.program, each.key, each.t)
            assert got == each.value, f'{name}: {each.key} at {each.t} h is {got}, not {each.value}'
        elif isinstance(each, Traced):
            found = traced(run, each.kind, each.part)
            assert tuple(t for t, _ in found) == tuple(each.times), (
                f'{name}: {each.kind} {each.part} at {found}'
            )
            if each.rounds is not None:
                assert tuple(r for _, r in found) == tuple(each.rounds), (
                    f'{name}: {each.kind} {each.part} {found}'
                )
