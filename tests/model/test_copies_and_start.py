"""The setup's starts, a stage that waits and then acts only if its guard holds, and the retired time
scales of the scenario line. Every expectation is a closed form of the inputs.

The setup starts an attacker's operation and the responders' clean-up at t = 0 (spec, "Time, waiting
and completion"). The operation prepares for `prepare` hours, and its stage then switches the service
off and starts its repair only if the attacker has not been removed: the guard is read once, when the
stage comes due. The repair takes `repair` hours. While the service is up it serves the users who wait
at `k` times their number, so the users served are `users (1 - exp(-k u))`, with `u` the hours that
the service has been up.

The engine chooses its own steps: `timescales` left the scenario line (PLAN, change 19).

Copies of a template (`* k` and `copy`) and units that name a text left the language (spec, "What
the first version leaves out"): a template's members are written by hand or are the rows of a table.
The texts of an event for each of its occurrences went with the old pages.
"""

from __future__ import annotations

import math

import pytest

from napkin import SCHEMA_VERSION
from napkin.engine import read, run
from napkin.model.compile import compile_text
from napkin.model.language.problems import LanguageError
from tests.program.examples import UNITS

USERS, K, PREPARE, REPAIR = 1000, 0.05, 5, 10

OPERATION = """\
scenario "Operation"
    horizon 150 h

service:
    "A service that serves the users who wait while it is up."
    input users: person = 1000 person
    input k = 0.05
    input repair: h = 10 h
    up: bool = true
    waiting: person = this.users in [0 person,]
    served: person = 0 person in [0 person,]
    flow serve: this.waiting -> this.served
        request = formula(this.k * this.waiting / 1 h if this.up else 0 person/h)
    fix = event():
        after this.repair:
            this.up = true

attacker:
    "An attacker that prepares, then switches the service off unless it was removed first."
    input prepare: h = 5 h
    removed: bool = false
    operation = event():
        after this.prepare when not this.removed:
            service.up = false
            service.fix.start()

responders:
    "Responders that remove the attacker."
    input removal: h = 8 h
    clean_up = event():
        after this.removal:
            attacker.removed = true

attacker.operation.start()
responders.clean_up.start()
"""


def run_with(**inputs):
    model = compile_text(OPERATION, UNITS)
    configuration = model.configuration
    if inputs:
        edits = {'schema_version': SCHEMA_VERSION, 'model_hash': model.model_hash, 'set': inputs}
        configuration = model.configure(edits=edits)
    record = run(model.program, configuration)
    assert record.failure is None, record.failure.detail('message')
    return model, record


def starts(record, part):
    return [entry.t for entry in record.trace if entry.kind == 'start' and entry.part == part]


def test_the_setup_starts_at_zero_and_the_first_effect_comes_after_the_preparation():
    model, record = run_with()
    assert starts(record, 'attacker.operation') == starts(record, 'responders.clean_up') == [0]
    assert starts(record, 'service.fix') == [PREPARE]
    times = (PREPARE / 2, PREPARE + REPAIR / 2, PREPARE + REPAIR + 10, 150)
    (found,) = read(record, model.program, ['service.served'], list(times))
    # The service is up until the strike at 5 h and again from the end of the repair at 15 h.
    up = [min(t, PREPARE) + max(0.0, t - PREPARE - REPAIR) for t in times]
    assert found.values == pytest.approx([USERS * (1 - math.exp(-K * u)) for u in up], rel=1e-6)


def test_a_guard_read_when_the_stage_comes_due_skips_its_body():
    """The responders remove the attacker at 3 h, before the preparation ends: the stage at 5 h skips
    its body, so the service never goes down and is never repaired."""
    model, record = run_with(**{'responders.removal': 3})
    assert starts(record, 'service.fix') == []
    times = (2, 20, 150)
    (found,) = read(record, model.program, ['service.served'], list(times))
    assert found.values == pytest.approx([USERS * (1 - math.exp(-K * t)) for t in times], rel=1e-6)


# ---- time scales ---------------------------------------------------------------------------------


@pytest.mark.parametrize('written', ['2 h', '2 h, 3 h', 'service.repair'])
def test_timescales_are_retired_with_the_steps_that_the_engine_chooses(written):
    """The engine chooses its own steps (PLAN, change 19): `timescales` is refused by name, whatever it
    lists, with the configuration's `max_step` for a run that needs finer steps."""
    text = OPERATION.replace('    horizon 150 h\n', f'    horizon 150 h\n    timescales {written}\n')
    with pytest.raises(LanguageError) as raised:
        compile_text(text, UNITS)
    (problem,) = raised.value.problems
    assert (problem.code, problem.line) == ('retired', 3)
    assert 'the engine chooses its own steps' in problem.message and 'max_step' in problem.message
