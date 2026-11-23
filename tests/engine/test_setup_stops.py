"""A stop at a statement of the setup resumes as the run straight through goes, in place, from the
saved state and in a fresh process (docs/design/decisions.md, change 15: "Exact resume is a rule ... stopping and resuming
an untouched run gives the same recorded values ... as running straight through", tested three ways).

The rule test: a tank of 10 L of [0, 20] drained at 2 L/h, and a setup that marks a value and then
sets the tank to 8 L; a stop at each statement of the setup, resumed untouched and with an edit of the
mark at the stop. Worked by hand: the tank holds 8 - 2 t L, empty at 4 h; the mark is 1, or the edit's
value where the stop is after the statement that marks it (an edit at a stop before it is the mark's
value until the statement writes it: 1). Before, a run restored from its saved state at a stop in the
setup could not go on (`moment.resume` tested its marker of the setup by identity).
"""

from __future__ import annotations

import pytest

from napkin.engine import read, run
from napkin.engine.timeline import Plan, Run, resume
from napkin.program.build import SINK, Builder, assign, flow, named, q, this, value
from napkin.program.checkpoint import Breakpoint, Checkpoint, dumps, loads
from napkin.program.config import Configuration, Request
from napkin.program.record import Key
from tests.engine.test_checkpoints import in_a_fresh_process

UNITS = {'h': {'time': 1}, 'L': {'volume': 1}}
TIMES = [0, 1, 2, 3, 4]


def tank():
    b = Builder(UNITS)
    b.entity(
        'tank',
        value('water', 'L', 10, lower=0, upper=20),
        flow('pipe', this.water, SINK, request=q(2, 'L/h')),
    )
    b.entity('ops', value('mark', '', 0))
    b.setup(assign(named('ops').mark, 1), assign(named('tank').water, q(8, 'L')))
    return b.finish()


def values(program, record):
    found = read(record, program, [Key('tank', ('water',)), Key('ops', ('mark',))], TIMES)
    return [list(each.values) for each in found]


@pytest.mark.parametrize('at', ['setup[0]', 'setup[1]'])
@pytest.mark.parametrize('mark', [None, 5])
def test_a_stop_in_the_setup_resumes_as_the_run_goes_three_ways(at, mark, tmp_path):
    program, configuration = tank(), Configuration(Request(4))
    straight = values(program, run(program, configuration))
    assert straight == [[8, 6, 4, 2, 0], [1, 1, 1, 1, 1]]
    made = Run(Plan.of(program, configuration), (Breakpoint(at),))
    stopped = made.run()
    assert isinstance(stopped, Checkpoint)
    if mark is not None:
        stopped = made.edit(Key('ops', ('mark',)), mark)
    expected = [[8, 6, 4, 2, 0], [mark if mark is not None and at == 'setup[1]' else 1] * 5]
    records = [
        made.resume(),
        resume(program, loads(dumps(stopped))),
        *in_a_fresh_process(program, [stopped], tmp_path),
    ]
    for record in records:
        assert record.failure is None, record.failure.detail('message')
        for found, wanted in zip(values(program, record), expected, strict=True):
            assert found == pytest.approx(wanted, abs=1e-12)
