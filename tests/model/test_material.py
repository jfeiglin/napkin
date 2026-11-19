"""Material: a flow whose legs move together, flows from or to outside the model, a store that two
flows draw on and that shares its capacity among them, and an assertion of a sum. Every expectation is
a closed form of the inputs, worked by hand.

The fixture is a service from t = 0: `users` people wait and are served at `k` times the number still
waiting, so `served(t) = users (1 - exp(-k t))` (spec, "Flows and algebraic solvers"). A flow with legs
serves its legs at one fraction (spec, "Shared resources and competing invocations"), so when one
leg's store is empty both stop. `SOURCE` and `SINK` are the outside: a direct `SOURCE -> SINK` flow
takes its unit from its rate. An endpoint's capacity is shared by its allocation (`proportional()`
by default, or `priority(...)`); the rules at one moment are in `tests/engine/test_rationing.py`, and
a name that a priority lists twice in `tests/language/test_endpoints.py`.
"""

from __future__ import annotations

import math

import pytest

from napkin.engine import read, run
from napkin.model.compile import compile_text
from napkin.model.language.problems import LanguageError
from tests.program.examples import UNITS

USERS, K = 1000, 0.05

SERVICE = """\
scenario "Service"
    horizon 120 h

service:
    "A service that serves the users who wait."
    input users: person = 1000 person
    input k = 0.05
    waiting: person = this.users in [0 person,]
    served: person = 0 person in [0 person,]
{parts}
"""
SERVE = """\
    flow serve: this.waiting -> this.served
        request = formula(this.k * this.waiting / 1 h)
"""


def served(t):
    return USERS * (1 - math.exp(-K * t))


def time_to_serve(amount):
    """The time at which the service has served `amount` users."""
    return -math.log(1 - amount / USERS) / K


def values(parts, names, times):
    """The values of `names` at `times` in a run of the service with `parts`."""
    model = compile_text(SERVICE.format(parts=parts), UNITS)
    record = run(model.program, model.configuration)
    assert record.failure is None, record.failure.detail('message')
    return [reading.values for reading in read(record, model.program, names, list(times))]


# ---- a flow with legs -----------------------------------------------------------------------------


def with_tokens(per_user):
    """Each user served uses `per_user` tokens of a store of 400: the legs move together."""
    return f"""\
    tokens: work_unit = 400 work_unit in [0 work_unit,]
    used: work_unit = 0 work_unit in [0 work_unit,]
    flow serve:
        flow users: this.waiting -> this.served
            request = formula(this.k * this.waiting / 1 h)
        flow tokens: this.tokens -> this.used
            request = formula({per_user} work_unit / 1 person * this.k * this.waiting / 1 h)
"""


@pytest.mark.parametrize('per_user', [1, 2])
def test_legs_that_move_together_stop_together_when_one_runs_short(per_user):
    """The tokens run out once 400 / per_user users are served; the users' leg stops with them."""
    limit = 400 / per_user
    out_of_tokens = time_to_serve(limit)
    times = (out_of_tokens - 2, out_of_tokens + 5, 120)
    names = ['service.served', 'service.used', 'service.waiting', 'service.serve.served_fraction']
    found_served, used, waiting, fraction = values(with_tokens(per_user), names, times)
    expected = [min(served(t), limit) for t in times]
    assert found_served == pytest.approx(expected, rel=1e-6, abs=1e-6)
    assert used == pytest.approx([per_user * x for x in expected], rel=1e-6, abs=1e-6)
    assert [w + s for w, s in zip(waiting, found_served)] == pytest.approx([USERS] * 3)
    assert fraction == pytest.approx((1, 0, 0), abs=1e-9)
    # Without the second leg the service would have served far more by the end.
    assert served(120) > limit + 100


# ---- outside the model ---------------------------------------------------------------------------

OUTSIDE = (
    SERVE
    + """\
    counted: person = 0 person in [0 person,]
    spare: person = 100 person in [0 person,]
    flow count_served: SOURCE -> this.counted
        request = formula(this.k * this.waiting / 1 h)
    flow discard: this.spare -> SINK
        request = formula(0.1 * this.spare / 1 h)
"""
)


def test_flows_from_and_to_outside_the_model():
    """A counter filled from outside at the rate of the service counts every user served, and the
    spare store that drains to outside at a tenth of itself an hour holds 100 exp(-t / 10)."""
    times = (20, 45, 120)
    counted, spare = values(OUTSIDE, ['service.counted', 'service.spare'], times)
    assert counted == pytest.approx([served(t) for t in times], rel=1e-6)
    assert spare == pytest.approx([100 * math.exp(-0.1 * t) for t in times], rel=1e-6, abs=1e-6)


def test_a_flow_from_outside_to_outside_takes_its_unit_from_its_rate():
    passing = '    flow through: SOURCE -> SINK\n        request = 2 person/h\n    seen = formula(this.through.actual_rate)\n'
    assert values(SERVE + passing, ['service.seen'], [1]) == [(2,)]
    with pytest.raises(LanguageError) as raised:
        compile_text(SERVICE.format(parts=SERVE + '    flow through: SOURCE -> SINK\n'), UNITS)
    assert raised.value.codes == ['flow_units']


# ---- a store that two flows draw on -----------------------------------------------------------------

STORE = """\
scenario "Store"
    horizon 60 h

store:
    stock: person = 100 person in [0 person,]
        outflow.capacity = {limit} person/h{allocation}
    to_a: person = 0 person in [0 person,]
    to_b: person = 0 person in [0 person,]
    flow take_a: this.stock -> this.to_a
        request = 3 person/h
{second}"""
SECOND = '    flow take_b: this.stock -> this.to_b\n        request = 2 person/h\n'


def shared(limit, order=None, second=SECOND, times=None):
    allocation = (
        ''
        if order is None
        else '\n        outflow.allocation = priority(' + ', '.join(f'this.{name}' for name in order) + ')'
    )
    text = STORE.format(limit=limit, allocation=allocation, second=second)
    model = compile_text(text, UNITS)
    record = run(model.program, model.configuration)
    assert record.failure is None
    return read(record, model.program, ['store.to_a', 'store.to_b', 'store.stock'], list(times))


@pytest.mark.parametrize(
    ('order', 'limit', 'rate_a', 'rate_b'),
    [
        # The first flow gets what it asks for, the second what is left under the limit.
        (('take_a', 'take_b'), 4, 3.0, 1.0),
        (('take_b', 'take_a'), 4, 2.0, 2.0),
        # Each flow gets the same share of its request.
        (None, 4, 3.0 * 4 / 5, 2.0 * 4 / 5),
        # A limit above both requests does not bind.
        (None, 10, 3.0, 2.0),
    ],
)
def test_a_store_shares_its_capacity_by_its_allocation_until_it_is_empty(order, limit, rate_a, rate_b):
    empty = 100 / (rate_a + rate_b)
    times = (empty / 2, empty + 10)
    to_a, to_b, stock = (reading.values for reading in shared(limit, order, times=times))
    hours = [min(t, empty) for t in times]
    assert to_a == pytest.approx([rate_a * h for h in hours], rel=1e-6, abs=1e-6)
    assert to_b == pytest.approx([rate_b * h for h in hours], rel=1e-6, abs=1e-6)
    assert stock == pytest.approx([100 - (rate_a + rate_b) * h for h in hours], rel=1e-6, abs=1e-6)


@pytest.mark.parametrize(('limit', 'rate'), [(2, 2.0), (10, 3.0)])
def test_the_capacity_of_a_store_with_one_flow_caps_that_flow(limit, rate):
    empty = 100 / rate
    to_a, _, _ = shared(limit, second='', times=(empty / 2, empty + 10))
    assert to_a.values == pytest.approx([rate * empty / 2, 100], rel=1e-6, abs=1e-6)


# ---- an assertion of a sum ---------------------------------------------------------------------------

BOOKS = 'assert service.waiting + service.served in [service.users - 0.001 person, service.users + 0.001 person]\n'
# The spec writes a sum that must hold as such an assertion ("Assertions and their timing"), and says
# that the compiler rejects an assertion whose guarantee the engine cannot give.
UNCERTIFIED = pytest.mark.xfail(
    strict=True,
    raises=AssertionError,
    reason='bug: the front end accepts an assertion of the sum of two stores that move, and the engine '
    'stops its run at 0 h: "the first contact ... cannot be certified: it reads more than one store"',
)


@UNCERTIFIED
def test_an_assertion_of_a_sum_holds_while_the_flows_keep_their_stores():
    model = compile_text(SERVICE.format(parts=SERVE) + BOOKS, UNITS)
    assert run(model.program, model.configuration).failure is None


@UNCERTIFIED
def test_an_assertion_of_a_sum_fails_when_a_flow_takes_from_its_stores():
    """A leak of 1 person an hour from the waiting users leaves the books 0.001 person short at
    0.001 h."""
    leak = SERVE + '    flow leak: this.waiting -> SINK\n        request = 1 person/h\n'
    model = compile_text(SERVICE.format(parts=leak) + BOOKS, UNITS)
    record = run(model.program, model.configuration)
    assert record.failure is not None and record.failure.t == pytest.approx(0.001, rel=1e-6)
    assert 'assert[0]: the assertion does not hold' in record.failure.detail('message')
