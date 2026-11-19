"""A membership test and its interval (spec, "Units, comparisons and layout"): `x in [lo, hi]` holds
when `lo <= x <= hi`, `[x, x]` contains exactly `x`, and reversed bounds are an error. The audit's row
12: an interval whose ends only a run knows was tested as written, so a stage that made `lo` 3 h and
`hi` 2 h left a membership that read false and a run that finished.

The rule holds on every path that evaluates a membership: when the model compiles, if its ends are
fixed then (`range`); otherwise when the run evaluates it, in a formula read (by the record's reader
and by a report), a stage's statement, a stage's guard, a trigger's condition, a gate's condition,
an assertion over state and a rate that a flow reads (on lines, and between moments on the sparse
integrator), after an edit at a stop and after a resume in a fresh process, and on the oracle. Each
fails by the one name of the failure (`NAME`), at the time at which it evaluates the membership. The
expected times and values are worked by hand from the model.
"""

import textwrap

import pytest

from napkin.engine import read, run
from napkin.engine.report import report
from napkin.engine.timeline import Plan, Run
from napkin.model.compile import compile_text
from napkin.model.language.problems import LanguageError
from napkin.program.checkpoint import Breakpoint, Checkpoint
from napkin.program.record import Unavailable
from tests.engine.test_checkpoints import in_a_fresh_process
from tests.program.examples import UNITS
from tests.reference.from_program import run_of

# The name of the failure, in every evaluator.
NAME = 'the interval of a membership test is reversed'

# A plant whose interval [lo, hi] = [1 h, 3 h] holds x = 2.5 h until a stage reverses it at 1 h to
# [3 h, 2 h]; `{event}` and `{top}` place a membership on a path.
PLANT = """
    scenario "Interval"
        horizon 4 h

    plant:
        lo: h = 1 h
        hi: h = 3 h
        x: h = 2.5 h
        low: L = 0 L
        high: L = 10 L
        seen: bool = false
        ok = formula(this.x in [this.lo, this.hi])
        water: L = 1 L in [0,]
        flow fill: SOURCE -> this.water
            request = {request}
        flow drain: this.water -> SINK
            request = 1 L/h
        swap = event():
            after 1 h:
                this.lo = 3 h
                this.hi = 2 h
                this.low = 10 L
                this.high = 0 L
{event}
    plant.swap.start()
{top}
    """

# Each path that evaluates a membership at run time: (the event that holds it, the setup and top
# level lines, the fill's request), and the time at which the run evaluates it reversed.
PATHS = {
    'stage': (
        """
        go = event():
            after 2 h:
                this.seen = (this.x in [this.lo, this.hi])""",
        '    plant.go.start()',
        '1 L/h',
        2.0,
    ),
    'guard': (
        """
        go = event():
            after 2 h when this.x in [this.lo, this.hi]:
                this.seen = true""",
        '    plant.go.start()',
        '1 L/h',
        2.0,
    ),
    'trigger': (
        """
        go = event():
            when not (this.x in [this.lo, this.hi]):
                this.go.start()
            after 0 h:
                this.seen = true""",
        '',
        '1 L/h',
        1.0,
    ),
    'gate': (
        """
        go = event():
            until not (this.x in [this.lo, this.hi])
            after 0 h:
                this.seen = true""",
        '    plant.go.start()',
        '1 L/h',
        1.0,
    ),
    'assertion': ('', '    assert plant.x in [plant.lo, plant.hi]', '1 L/h', 1.0),
    # A rate that reads no store that moves: the set runs on lines, and reads the rate at 1 h.
    'rate': ('', '', 'formula(2 L/h if this.x in [this.lo, this.hi] else 3 L/h)', 1.0),
    # A rate that reads the store that it fills, which two flows share: the sparse integrator reads
    # it between moments, and at 1 h after the stage.
    'moving rate': ('', '', 'formula(2 L/h if this.water in [this.low, this.high] else 3 L/h)', 1.0),
}


def plant(event='', top='', request='1 L/h'):
    """The plant's text, with an event under it, lines at the top level and the fill's request."""
    return textwrap.dedent(PLANT.format(event=event, top=top, request=request))


def compiled(text):
    return compile_text(text, UNITS)


def failure(record):
    """(the time of the failure, its message), or None for a run that finished."""
    if record.failure is None:
        return None
    return record.failure.t, dict(record.failure.details)['message']


@pytest.mark.parametrize('path', sorted(PATHS))
def test_a_reversed_interval_fails_the_run_by_name_where_the_run_evaluates_it(path):
    event, top, request, at = PATHS[path]
    model = compiled(plant(event, top, request))
    found = failure(run(model.program, model.configuration))
    assert found is not None and found[0] == at and NAME in found[1], found


@pytest.mark.parametrize('path', sorted(PATHS))
def test_the_oracle_fails_by_the_same_name(path):
    event, top, request, _ = PATHS[path]
    model = compiled(plant(event, top, request))
    _, failed = run_of(model.program, model.configuration)
    assert failed is not None and NAME in str(failed), failed


def test_a_formula_read_after_the_interval_is_reversed_is_unavailable_by_name():
    """The record's reader and a report read `ok` as the closed interval before 1 h (1 h <= 2.5 h
    <= 3 h) and as no value after it, with the reason; the run itself never reads `ok`, and
    finishes."""
    model = compiled(plant())
    record = run(model.program, model.configuration)
    assert record.failure is None
    for found in (
        read(record, model.program, ['plant.ok'], [0, 0.5, 2])[0].values,
        report(record, model.program, model.configuration, ['plant.ok'], [0, 0.5, 2]).values[0].values,
    ):
        assert found[:2] == (True, True)
        assert isinstance(found[2], Unavailable) and NAME in found[2].reason, found


def test_an_interval_of_equal_ends_holds_its_one_value_only():
    """`[x, x]` contains exactly x: 2.5 h lies in [2.5 h, 2.5 h], and 2.5 h lies in no [lo, lo]
    whose end the run makes 2.4 h or 2.6 h."""
    text = plant(
        """
        go = event():
            after 2 h:
                this.lo = 2.4 h
                this.hi = 2.4 h
            after 1 h:
                this.lo = 2.6 h
                this.hi = 2.6 h""",
        '    plant.go.start()',
    ).replace('this.lo = 3 h', 'this.lo = 2.5 h').replace('this.hi = 2 h', 'this.hi = 2.5 h')
    model = compiled(text)
    record = run(model.program, model.configuration)
    assert record.failure is None
    assert read(record, model.program, ['plant.ok'], [0, 1, 2, 3])[0].values == (True, True, False, False)


def test_an_edit_that_reverses_the_interval_at_a_stop_fails_by_name_in_place_and_in_a_fresh_process(tmp_path):
    """No stage reverses the interval: a stop before the stage at 2 h edits lo to 3 h and hi to 2 h,
    and the stage's membership then fails at 2 h, resumed in place and in a fresh process."""
    text = plant(
        """
        go = event():
            after 2 h:
                this.seen = (this.x in [this.lo, this.hi])""",
        '    plant.go.start()',
    ).replace('plant.swap.start()', '')
    model = compiled(text)
    made = Run(Plan.of(model.program, model.configuration), (Breakpoint('plant.go.step[0]'),))
    stopped = made.run()
    assert isinstance(stopped, Checkpoint) and stopped.stop.t == 2.0
    made.edit('plant.lo', 3)
    edited = made.edit('plant.hi', 2)
    found = failure(made.resume())
    assert found is not None and found[0] == 2.0 and NAME in found[1], found
    (fresh,) = in_a_fresh_process(model.program, [edited], tmp_path)
    found = failure(fresh)
    assert found is not None and found[0] == 2.0 and NAME in found[1], found


@pytest.mark.parametrize('ends', ['[3 h, 2 h]', '[1 year, 6 h]', '[2 h + 3 h, 1 h]', '[this.x + 1 h, 2 h]'])
def test_a_reversed_interval_whose_ends_are_fixed_when_the_model_compiles_is_refused(ends):
    """The ends of `[this.x + 1 h, 2 h]` read x, a stored value: only a run knows them, so the model
    compiles and the run fails at 2 h; the others are fixed, and the model is refused (`range`)."""
    text = plant(
        f"""
        go = event():
            after 2 h:
                this.seen = (this.x in {ends})""",
        '    plant.go.start()',
    ).replace('plant.swap.start()', '')
    if 'this.x' in ends:
        model = compiled(text)
        found = failure(run(model.program, model.configuration))
        assert found is not None and found[0] == 2.0 and NAME in found[1], found
        return
    with pytest.raises(LanguageError) as caught:
        compiled(text)
    assert [problem.code for problem in caught.value.problems] == ['range']


# A store that rises at 1 L/h from 1 L, into [low, high] = [3 L, 10 L] at 2 h.
RISING = """
    scenario "Rising"
        horizon 4 h

    plant:
        low: L = 3 L
        high: L = 10 L
        seen: bool = false
        at: h = 0 h
        water: L = 1 L in [0,]
        flow fill: SOURCE -> this.water
            request = 1 L/h
        go = event():
{event}
            after 0 h:
                this.seen = true
                this.at = t
{top}
    """


# Where a trigger's or a gate's condition changes between moments is the engine's (`triggers.py`):
# it reads the comparisons of a condition, and a membership's are those of its chain
# (`napkin.core.expr.membership`), which agent E reads there in this round.
PENDING = pytest.mark.xfail(strict=True, reason='E: triggers.py reads a membership as its chain')


@pytest.mark.parametrize(
    'form',
    [
        pytest.param(
            ('            when this.water in [this.low, this.high]:\n                this.go.start()', ''),
            id='trigger',
            marks=PENDING,
        ),
        pytest.param(
            ('            until this.water in [this.low, this.high]', '    plant.go.start()'),
            id='gate',
            marks=PENDING,
        ),
        pytest.param(
            ('            when this.low <= this.water <= this.high:\n                this.go.start()', ''),
            id='chain',
        ),
    ],
)
def test_a_membership_of_a_moving_value_holds_from_where_the_value_reaches_an_end(form):
    """Between moments a membership changes where its value crosses an end of its interval, as the
    chain of its two comparisons does: the store reaches 3 L at 2 h (1 L + 1 L/h x 2 h, worked by
    hand), and the trigger fires, or the gate releases, then."""
    event, top = form
    model = compiled(textwrap.dedent(RISING.format(event=event, top=top)))
    record = run(model.program, model.configuration)
    assert record.failure is None
    (at,) = read(record, model.program, ['plant.at'], [4])[0].values
    assert at == pytest.approx(2.0, abs=1e-6)
