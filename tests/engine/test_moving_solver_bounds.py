"""A declared solver whose problem reads a store that moves to its bound (the review of `2cd1751`,
R10 and R12; spec, D0 and "Selection order", "A rate can follow a moving quantity", "Time, waiting
and completion").

The rules:

- **A feasible problem has its answer** (D0; spec.md:19). The integrator of a moving solver's set
  evaluates the solver at trial states (spec, "Rounds": evaluations apart from the once-in-a-round
  rule); a store that reaches its bound in a step is at its bound there, as a store's interval is an
  inventory bound, so a trial state that the integrator puts a tolerance past a bound is read at the
  bound, and the problem, feasible there, answers.
- **A run fails at the time it fails, with its record to then** (spec, "Time, waiting and
  completion"; the record ends at its failure). A problem that has no answer from some time on stops
  the run at that time, to the crossing tolerance of the run, and every value before it reads as the
  run made it.
- **A bound met at a moment settles there under the same rules** (spec.md:662: the work due at the
  horizon settles as at any moment): a store that reaches its bound at the time of a stage, or at the
  horizon, gives the same values as one that reaches it between moments.

The rule test: random stores drained or filled at a constant rate toward a bound, read by a solver
whose answer has a closed form there, with horizons and stages placed at the time of the bound as
often as near it, straight and stopped at the stage and resumed in place and from the saved state.
The expected values are the closed forms (the reference interpreter does not run a solver whose
problem moves).
"""

from __future__ import annotations

import random
from fractions import Fraction

import pytest

from napkin.engine import read, run
from napkin.engine.timeline import Plan, Run, resume
from napkin.model.compile import compile_text
from napkin.program.checkpoint import Breakpoint, Checkpoint, dumps, loads
from tests.program.examples import UNITS

DRAIN = """scenario "A solver whose input drains"
    horizon {horizon} h

clinic:
    staff: h = {start} h in [0 h,]
    mark: h = 0 h
    floor: h = {floor} h
    flow attrition: this.staff -> SINK
        request = {rate} h/h
    least = formula({share} * this.staff)
    staffing = solver:
        inputs:
            available = this.staff
            least = this.{least}
        solve_for:
            care: h in [0 h, available]
            outreach: h in [least, available]
        constraints:
            care + outreach == available
        objective:
            maximize(care)
{tick}"""

FILL = """scenario "A solver whose input fills"
    horizon {horizon} h

clinic:
    staff: h = 0 h in [0 h, {upper} h]
    flow hire: SOURCE -> this.staff
        request = {rate} h/h
    cap: h = {cap} h
    staffing = solver:
        inputs:
            available = this.staff
            cap = this.cap
        solve_for:
            care: h in [0 h, cap]
        constraints:
            care <= available
        objective:
            maximize(care)
{tick}"""

# A stage due at a time: it writes a value that the solver reads (its cap, unchanged), or one that
# nothing reads.
TICK = """    tick = event():
        after {at} h:
            this.{target} = {value}

clinic.tick.start()
"""
TOLERANCE = 1e-6  # of the closed forms: the integrator's tolerances on a straight line are far below


def compiled(text):
    return compile_text(text, UNITS)


def values(record, program, path, times):
    return list(read(record, program, [path], [float(time) for time in times])[0].values)


def drained(seed):
    """A store of `start` h drained at `rate` h/h, empty at `start / rate`; the solver keeps outreach
    at least `share` of it (or at least a fixed `least` h, which has no answer once less remains),
    and the horizon and a stage fall on the time it empties, or near it."""
    rng = random.Random(seed)
    start, rate = rng.choice([40, 50, 100]), rng.choice([4, 5, 10])
    empty = Fraction(start, rate)
    share = rng.choice(['0.3', '0.5'])
    fixed = rng.random() < 0.3
    least = 'floor' if fixed else 'least'
    near = [empty, empty, empty + Fraction(1, 4), empty - Fraction(1, 4), empty + 2]
    horizon = rng.choice(near)
    ticks = rng.random() < 0.5
    tick = TICK.format(at=float(rng.choice(near[:-1])), target='mark', value='1 h') if ticks else ''
    text = DRAIN.format(
        horizon=float(horizon), start=start, rate=rate, share=share, least=least, floor=start // 2, tick=tick
    )
    return compiled(text), start, rate, Fraction(share), (start // 2 if fixed else None), horizon, ticks


def filled(seed, kink=True):
    """A store from 0 h filled at `rate` h/h to its upper bound `upper` h, full at `upper / rate`;
    the solver gives care up to `cap` within what is there (with `kink`, a cap below the bound now
    and then, where care stops following the store: the integrator takes many short steps there,
    each a solve); the horizon and a stage fall on the time it is full, or near it."""
    rng = random.Random(seed)
    upper, rate = rng.choice([20, 30]), rng.choice([10, 15])
    full = Fraction(upper, rate)
    cap = rng.choice([upper - 10, upper, upper + 10] if kink else [upper, upper + 10])
    near = [full, full, full + Fraction(1, 4), full - Fraction(1, 4), full + 2]
    horizon = rng.choice(near)
    ticks = rng.random() < 0.5
    tick = TICK.format(at=float(rng.choice(near[:-1])), target='cap', value=f'{cap} h') if ticks else ''
    text = FILL.format(horizon=float(horizon), upper=upper, rate=rate, cap=cap, tick=tick)
    return compiled(text), upper, rate, cap, horizon, ticks


def records(c, stop):
    """The record straight through, and with `stop` the records resumed in place and from the saved
    state of a stop at the stage."""
    found = [run(c.program, c.configuration)]
    if stop:
        made = Run(Plan.of(c.program, c.configuration), (Breakpoint('clinic.tick.step[0]'),))
        stopped = made.run()
        if isinstance(stopped, Checkpoint):
            found += [made.resume(), resume(c.program, loads(dumps(stopped)))]
    return found


def drain(seed):
    c, start, rate, share, least, horizon, ticks = drained(seed)
    times = [Fraction(k, 4) * horizon for k in range(5)]
    for record in records(c, ticks):
        staff = [max(Fraction(0), start - rate * time) for time in times]
        if least is None:  # outreach at least a share of what is there: care is the rest, to the end
            assert record.failure is None, record.failure.detail('message')
            care = [(1 - share) * level for level in staff]
        else:  # at least `least` h of outreach: no answer once less is there, at (start - least) / rate
            end = Fraction(start - least, rate)
            if horizon <= end:
                assert record.failure is None, record.failure.detail('message')
            else:
                assert record.failure is not None
                assert record.failure.t == pytest.approx(float(end), abs=1e-6)
                assert 'cannot answer' in record.failure.detail('message')
                times = [time for time in times if time < end]
                staff = staff[: len(times)]
            care = [level - least for level in staff]
        assert values(record, c.program, 'clinic.staff', times) == pytest.approx(
            [float(x) for x in staff], abs=TOLERANCE
        )
        assert values(record, c.program, 'clinic.staffing.care', times) == pytest.approx(
            [float(x) for x in care], abs=TOLERANCE
        )


def fill(seed, kink=True):
    c, upper, rate, cap, horizon, ticks = filled(seed, kink)
    times = [Fraction(k, 4) * horizon for k in range(5)]
    staff = [min(Fraction(upper), rate * time) for time in times]
    care = [min(Fraction(cap), level) for level in staff]
    for record in records(c, ticks):
        assert record.failure is None, record.failure.detail('message')
        assert values(record, c.program, 'clinic.staff', times) == pytest.approx(
            [float(x) for x in staff], abs=TOLERANCE
        )
        assert values(record, c.program, 'clinic.staffing.care', times) == pytest.approx(
            [float(x) for x in care], abs=TOLERANCE
        )


@pytest.mark.parametrize('seed', range(6))
def test_a_store_drained_to_its_bound_keeps_the_solver_answering_or_fails_at_its_time(seed):
    drain(seed)


@pytest.mark.parametrize('seed', range(8, 14))  # half of them met their bound where a run crashed
def test_a_store_filled_to_its_bound_at_a_moment_settles_as_between_moments(seed):
    fill(seed, kink=False)


@pytest.mark.deep
@pytest.mark.parametrize('seed', range(6, 40))
def test_more_stores_drained_and_filled_to_their_bounds(seed):
    drain(seed)
    fill(seed)
