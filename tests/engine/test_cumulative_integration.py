"""Roundoff at bounds in the dense values of a run, bound violations that stop a run, and cash-control
integrals across a kink, against closed forms.

Accounts are in USD2025 with a scale of 1e9, so the absolute tolerance of each is 0.1, and the lower
slack of an account that flows only fill (a tally: it never falls) is 0.1 + 1e-9 * 1e9 = 1.1.
"""

import math

import numpy as np
import pytest

import napkin.engine.continuous.integrate as integrate
from napkin.engine import read, run
from napkin.engine.timeline import Plan, Run
from napkin.program import build
from napkin.program.build import SINK, SOURCE, Builder, flow, fmax, fmin, formula, q, t, this, value
from napkin.program.config import Configuration, Request

UNITS = {'USD2025': {'money': 1}, 'person': {'people': 1}, 'h': {'time': 1}}
SCALE = 1e9
NOTHING = q(0, 'USD2025/h')


def usd(name, initial=0, **bounds):
    """An account in USD2025 with a scale of 1e9, never negative unless its bounds say otherwise."""
    return value(name, 'USD2025', initial, scale=SCALE, **{'lower': 0, **bounds})


def exp(x):
    return build.call('exp', x)


def recovery(hours):
    """20 pending that recover at pending / (4 hours) * exp(-t / hours): pending is
    20 exp(-0.25 (1 - exp(-t / hours))) and pending + recovered stays 20."""
    rate = this.pending / q(4 * hours, 'h') * exp(-t / q(hours, 'h'))
    return (
        value('pending', 'person', 20, lower=0, scale=20),
        value('recovered', 'person', 0, lower=0, scale=20),
        flow('recover', this.pending, this.recovered, request=formula(rate)),
    )


def pending(at, hours):
    return 20 * math.exp(-0.25 * (-math.expm1(-at / hours)))


def configured(program, horizon):
    return program, Configuration(Request(horizon))


def dense_fixture():
    """The recovery beside three accounts at 0.5 USD2025 that flows of nothing touch: a tally that
    a flow fills (at most 1), an account that a flow drains (at most 1), and a signed account in
    [-2, 2] that a flow fills. Each flow reads the pending count, times zero: so their stores have
    dense values in the recovery's component (a set whose rates hold between moments runs on arrays
    or on lines, with exact lines)."""
    nothing = formula(NOTHING * this.pending / q(1, 'person'))
    b = Builder(UNITS)
    b.entity(
        's',
        *recovery(1),
        usd('ledger', 0.5, upper=1),
        usd('account', 0.5, upper=1),
        usd('signed', 0.5, lower=-2, upper=2),
        flow('fill', SOURCE, this.ledger, request=nothing),
        flow('draw', this.account, SINK, request=nothing),
        flow('rise', SOURCE, this.signed, request=nothing),
    )
    return configured(b.finish(), 2)


@pytest.mark.parametrize(
    'coordinate,raw,reported',
    [
        ('ledger', -0.10985851323228443, 0),
        ('ledger', -0.5, 0),
        ('ledger', -1.2, -1.2),
        ('account', -0.5, -0.5),
        ('account', -0.05, 0),
        ('ledger', 1.5, 1.5),
        ('ledger', 1.05, 1),
        ('ledger', 1e-28, 1e-28),
        ('signed', -0.5, -0.5),
    ],
)
def test_a_dense_value_takes_the_roundoff_of_each_authored_bound_onto_it(coordinate, raw, reported):
    """A dense value within the slack of a bound is put on it: the lower slack of the tally is 1.1,
    that of the drained account its tolerance 0.1, and an upper bound's is the tolerance. A larger
    excursion stays, for the checks to see."""
    _, _, ways = Run(Plan.of(*dense_fixture())).prepare()
    name = f's.{coordinate}'
    component = next(way.component for way in ways if name in way.component.system.index)
    state = component.state.y.copy()
    state[component.system.index[name]] = raw
    assert component.context.project(state)[component.system.index[name]] == reported


def test_the_recovery_follows_its_closed_form_in_the_dense_values():
    program, configuration = dense_fixture()
    record = run(program, configuration)
    found, recovered = read(record, program, ['s.pending', 's.recovered'], [0.5, 1.3])
    assert found.values == pytest.approx([pending(0.5, 1), pending(1.3, 1)], rel=1e-8)
    assert np.add(found.values, recovered.values) == pytest.approx([20, 20], abs=1e-10)


def spending(b, cash):
    """Spending under 24 h cash control: min(1,000,000 USD2025 an hour, cash / 24 h + 500,000)."""
    return fmin(q(1_000_000, 'USD2025/h'), cash / q(24, 'h') + q(500_000, 'USD2025/h'))


def spending_fixture(foregone_max=None):
    """The recovery of the dense fixture, slower, beside a cash account that receives 500,000 USD2025
    an hour and spends under 24 h cash control. `foregone_max` is an upper bound of the foregone
    spending (None: it has none)."""
    b = Builder(UNITS)
    b.entity(
        's',
        *recovery(24),
        usd('cash', 100_000_000),
        usd('burned'),
        usd('foregone', **({} if foregone_max is None else {'upper': foregone_max})),
        value('spending', 'USD2025/h', formula(spending(b, this.cash))),
        flow('receipts', SOURCE, this.cash, request=q(500_000, 'USD2025/h')),
        flow('spend', this.cash, this.burned, request=formula(this.spending)),
        flow(
            'forgo',
            SOURCE,
            this.foregone,
            request=formula(fmax(NOTHING, q(1_000_000, 'USD2025/h') - this.spending)),
        ),
    )
    return configured(b.finish(), 200)


def independent_spending(at):
    if at <= 176:
        return {'s.cash': 100_000_000 - 500_000 * at, 's.foregone': 0, 's.burned': 1_000_000 * at}
    elapsed = at - 176
    cash = 12_000_000 * math.exp(-elapsed / 24)
    return {
        's.cash': cash,
        's.burned': 100_000_000 + 500_000 * at - cash,
        's.foregone': 500_000 * (elapsed - 24 * (-math.expm1(-elapsed / 24))),
    }


def test_piecewise_spending_matches_independent_cash_and_foregone_integral():
    program, configuration = spending_fixture()
    record = run(program, configuration)
    assert record.failure is None
    times = (0, 24, 168, 175, 176, 177, 192, 200)
    names = ['s.cash', 's.foregone', 's.burned', 's.pending', 's.recovered']
    found = {reading.path: reading.values for reading in read(record, program, names, times)}
    for k, at in enumerate(times):
        for name, expected in independent_spending(at).items():
            assert found[name][k] == pytest.approx(expected, abs=2.2), (at, name)
        assert found['s.cash'][k] + found['s.burned'][k] == pytest.approx(100_000_000 + 500_000 * at, abs=2.2)
        assert found['s.pending'][k] + found['s.recovered'][k] == pytest.approx(20, abs=1e-10)
        assert found['s.pending'][k] == pytest.approx(pending(at, 24), rel=1e-8)
    assert found['s.foregone'][times.index(176)] == pytest.approx(0, abs=1.1)


def injected_solver(
    monkeypatch,
    plan,
    *,
    coordinate='foregone',
    persistent=False,
    switching=True,
    value_=None,
    failed=False,
    kink=176,
):
    """A solver that writes `value_` into the account `coordinate` at the last accepted state of
    the segment that ends at the kink of the cash control (or, not `switching`, at the horizon)."""
    original = integrate.radau
    stores = next(connected.stores for connected in plan.sets if f's.{coordinate}' in connected.stores)
    index = stores.index(f's.{coordinate}')
    injections = []

    def inject(fun, interval, initial, **kwargs):
        solution = original(fun, interval, initial, **kwargs)
        if len(initial) != len(stores):
            return solution  # the solver of the recovery
        is_kink = solution.success and abs(solution.t[-1] - kink) < 1e-3
        is_final = solution.success and solution.t[-1] == 200
        if (is_kink if switching else is_final) and (persistent or not injections):
            solution.y[index, -1] = (
                value_ if value_ is not None else (-1.73 if coordinate == 'foregone' else -0.2)
            )
            if failed:
                solution.success = False
                solution.message = 'Injected solver failure'
            injections.append(solution)
        return solution

    monkeypatch.setattr(integrate, 'radau', inject)
    return injections


@pytest.mark.parametrize(
    'case', ['cumulative', 'noncumulative', 'nonswitching', 'upper', 'nonfinite', 'failed']
)
def test_a_material_bound_violation_stops_the_run_at_once(monkeypatch, case):
    program, configuration = spending_fixture(1e9 if case == 'upper' else None)
    plan = Plan.of(program, configuration)
    injections = injected_solver(
        monkeypatch,
        plan,
        coordinate='cash' if case == 'noncumulative' else 'foregone',
        persistent=True,
        switching=case != 'nonswitching',
        value_=1e9 + 0.2 if case == 'upper' else (math.nan if case == 'nonfinite' else None),
        failed=case == 'failed',
    )
    name = 'cash' if case == 'noncumulative' else 'foregone'
    message = (
        'Nonfinite continuous state'
        if case == 'nonfinite'
        else 'Integrator failed: Injected solver failure'
        if case == 'failed'
        else f'Material state-bound violation for s.{name}'
    )
    record = Run(plan).run()
    assert message in record.failure.detail('message')
    assert len(injections) == 1


def cash_control_model():
    """Receipts are 500,000 USD2025 an hour. Normal expenditure is 1,000,000 an hour. With 24 h cash
    control the first shortfall occurs at 176 h, when cash = 12m. The patients leave at
    patients * patients / 20 people an hour, so patients = 20 / (1 + t)."""
    b = Builder(UNITS)
    b.entity(
        's',
        usd('cash', 100_000_000),
        usd('receipts'),
        usd('spent'),
        usd('foregone'),
        value('patients', 'person', 20, scale=20),
        value('spending', 'USD2025/h', formula(spending(b, this.cash))),
        flow(
            'leave',
            this.patients,
            SINK,
            request=formula(this.patients * this.patients / q(20, 'person') / q(1, 'h')),
        ),
        flow('receipt', SOURCE, this.cash, request=q(500_000, 'USD2025/h')),
        flow('receipt_ledger', SOURCE, this.receipts, request=q(500_000, 'USD2025/h')),
        flow('expense', this.cash, this.spent, request=formula(this.spending)),
        flow(
            'forgo',
            SOURCE,
            this.foregone,
            request=formula(fmax(NOTHING, q(1_000_000, 'USD2025/h') - this.spending)),
        ),
    )
    return configured(b.finish(), 240)


def test_positive_piecewise_cumulative_integral_matches_independent_closed_form():
    program, configuration = cash_control_model()
    record = run(program, configuration)
    assert record.failure is None
    times = (0, 24, 120, 175.9999, 176, 176.0001, 180, 192, 216, 240)
    names = ['s.cash', 's.foregone', 's.spent', 's.receipts', 's.patients']
    found = {reading.path: reading.values for reading in read(record, program, names, times)}
    previous = 0
    for k, time in enumerate(times):
        elapsed = max(0, time - 176)
        cash = 100_000_000 - 500_000 * time if time <= 176 else 12_000_000 * math.exp(-elapsed / 24)
        foregone = 500_000 * (elapsed + 24 * math.expm1(-elapsed / 24))
        assert found['s.cash'][k] == pytest.approx(cash, abs=1.1)
        assert found['s.foregone'][k] == pytest.approx(foregone, abs=1.1)
        assert found['s.foregone'][k] >= 0
        assert found['s.foregone'][k] >= previous - 1.1
        previous = found['s.foregone'][k]
        assert found['s.cash'][k] + found['s.spent'][k] - found['s.receipts'][k] == pytest.approx(
            100_000_000, abs=1.1
        )
        assert found['s.spent'][k] + found['s.foregone'][k] == pytest.approx(1_000_000 * time, abs=1.1)
        assert found['s.patients'][k] == pytest.approx(20 / (1 + time), rel=1e-8)
