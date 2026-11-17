"""Independent reporting witnesses for admitted cumulative lower roundoff.

The nonlinear population has a closed-form solution. Injected interior samples
exercise the public reporting boundary on an account of size 1e9 USD2025:
absolute accuracy is 0.1 and cumulative lower accuracy is 1.1.

Independent finite-cash kink and bounded numerical-retry witnesses.

Independent cash-control integrals across the first expenditure shortfall.
"""

import copy
import math

import numpy as np
import pytest

import napkin.engine.continuous.integrate as integrate
from napkin.engine.report import evaluate_outputs
from napkin.engine.runtime import NumericalSettings, SimulationError, simulate
from tests.build import (
    edit,
    flow,
    formula,
    library,
    member,
    move,
    output,
    resolved,
    stock,
    system,
)

LIBRARY = library()
# The spending under 24 h cash control, and the spending that it forgoes, in USD2025 an hour.
SPENDING = 'min(1000000 USD2025/h, cash / 24 h + 500000 USD2025/h)'
FOREGONE = 'max(0 USD2025/h, 1000000 USD2025/h - spending)'


def usd(name, initial=0, *, kind='stock', **lines):
    """An account in USD2025 of size 1e9."""
    return stock(name, initial, 'USD2025', kind=kind, size=1e9, **lines)


def outcome(name, expr, *, measure='level', nonnegative=True):
    return output(
        name, expr, 'USD2025', measure, doc='Reported account', under=() if nonnegative else ('signed',)
    )


def with_timescale(text, timescale):
    """A text whose solver keeps its steps shorter than `timescale`."""
    return edit(text, member('scenario:', f'timescales {timescale}'))


def dense_fixture():
    # The accounts start with a balance. A run leaves out a stock, tally or number state that starts
    # at zero and that nothing changes or reads, and the test injects values into these accounts as
    # solver states. The expected values do not depend on the balance. A flow of nothing makes the
    # ledger a tally (it fills it) and the account a stock (it takes from it).
    return with_timescale(
        system(
            stock('pending', 20, size=20),
            stock('recovered', size=20, kind='tally'),
            usd('ledger', 0.5, kind='tally', maximum=1, rate='0 USD2025/h'),
            usd('account', 0.5, maximum=1),
            usd('signed', 0.5, kind='state', minimum=-2, maximum=2),
            flow('recover', move('pending', 'recovered'), 'pending / 4 h * exp(-t / 1 h)'),
            flow('draw', move('account', None), '0 USD2025/h'),
            horizon=2,
            outputs=tuple(
                outcome(f'reported_{name}', f's.{name}', nonnegative=name != 'signed')
                for name in ('ledger', 'account', 'signed')
            ),
        ),
        '1 h',
    )


@pytest.mark.parametrize(
    'coordinate,raw,reported,rejected',
    [
        ('ledger', -0.10985851323228443, 0, False),
        ('ledger', -0.5, 0, False),
        ('ledger', -1.2, -1.2, True),
        ('account', -0.5, -0.5, True),
        ('account', -0.05, 0, False),
        ('ledger', 1.5, 1.5, False),
        ('ledger', 1.05, 1, False),
        ('ledger', 1e-28, 1e-28, False),
        ('signed', -0.5, -0.5, False),
    ],
)
def test_dense_reporting_respects_each_authored_bound_accuracy(coordinate, raw, reported, rejected):
    rs = resolved(dense_fixture())
    trajectory = simulate(rs, LIBRARY, NumericalSettings())
    assert trajectory.settings['integration_segments']
    at = 0.5
    assert not any(snapshot[0] == at for snapshot in trajectory._snapshots)
    segment = next(item for item in trajectory._segments if item.start <= at <= item.end)
    original_solution = segment.solution
    name = f's.{coordinate}'
    position = trajectory._states.index(name)

    def interior_roundoff(time):
        values = np.array(original_solution(time), copy=True)
        if time == at:
            values[position] = raw
        return values

    segment.solution = interior_roundoff
    trace_before = copy.deepcopy(trajectory.trace)
    snapshots_before = [
        (t, values.copy(), copy.deepcopy(store)) for t, values, store in trajectory._snapshots
    ]
    evaluations_before = trajectory.evaluations
    assert segment.solution(at)[position] == raw
    assert trajectory.env_at(at)[name] == reported
    expected_pending = 20 * math.exp(-0.25 * (-math.expm1(-at)))
    assert trajectory.env_at(at)['s.pending'] == pytest.approx(expected_pending, rel=1e-8)
    assert trajectory.env_at(at)['s.pending'] + trajectory.env_at(at)['s.recovered'] == pytest.approx(
        20, abs=1e-10
    )
    result = {'resolved': rs, 'trajectory': trajectory}
    if rejected:
        with pytest.raises(ValueError, match=f'Negative nonnegative outcome reported_{coordinate}'):
            evaluate_outputs(result, LIBRARY, [at])
    else:
        assert evaluate_outputs(result, LIBRARY, [at])[0]['values'][f'reported_{coordinate}'] == reported
    assert trajectory.trace == trace_before
    assert trajectory.evaluations == evaluations_before
    for actual, prior in zip(trajectory._snapshots, snapshots_before, strict=True):
        assert actual[0] == prior[0] and actual[2] == prior[2]
        np.testing.assert_array_equal(actual[1], prior[1])
    assert segment.solution(at)[position] == raw


def spending_fixture(foregone_max=None):
    """The recovery of the dense fixture, slower, beside a cash account that receives 500,000 USD2025
    an hour and spends under 24 h cash control. `foregone_max` is an upper bound of the foregone
    spending (None: it has none)."""
    return with_timescale(
        system(
            stock('pending', 20, size=20),
            stock('recovered', size=20, kind='tally'),
            usd('cash', 100_000_000),
            usd('burned', kind='tally'),
            usd('foregone', kind='tally', maximum=foregone_max, rate=FOREGONE),
            formula('spending', SPENDING, 'USD2025/h'),
            flow('recover', move('pending', 'recovered'), 'pending / 96 h * exp(-t / 24 h)'),
            flow('receipts', move(None, 'cash'), '500000 USD2025/h'),
            flow('spend', move('cash', 'burned'), 'spending'),
            horizon=200,
            outputs=(outcome('foregone_output', 's.foregone', measure=None),),
        ),
        '24 h',
    )


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


def assert_independent_spending(trajectory):
    for at in (0, 24, 168, 175, 176, 177, 192, 200):
        observed = trajectory.env_at(at)
        for name, value in independent_spending(at).items():
            assert observed[name] == pytest.approx(value, abs=2.2), (at, name)
        assert observed['s.cash'] + observed['s.burned'] == pytest.approx(100_000_000 + 500_000 * at, abs=2.2)
        assert observed['s.pending'] + observed['s.recovered'] == pytest.approx(20, abs=1e-10)
        expected_pending = 20 * math.exp(-0.25 * (-math.expm1(-at / 24)))
        assert observed['s.pending'] == pytest.approx(expected_pending, rel=1e-8)


def test_piecewise_spending_matches_independent_cash_and_foregone_integral():
    rs = resolved(spending_fixture())
    trajectory = simulate(rs, LIBRARY, NumericalSettings())
    assert_independent_spending(trajectory)
    assert evaluate_outputs({'resolved': rs, 'trajectory': trajectory}, LIBRARY, [176])[0]['values'][
        'foregone_output'
    ] == pytest.approx(0, abs=1.1)


def injected_solver(
    monkeypatch,
    rs,
    *,
    coordinate='foregone',
    persistent=False,
    switching=True,
    value=None,
    failed=False,
    kink=176,
):
    original = integrate.radau
    index = list(rs.quantities).index(f's.{coordinate}')
    calls, injections = [], []

    def inject(fun, interval, initial, **kwargs):
        solution = original(fun, interval, initial, **kwargs)
        calls.append(
            {
                'interval': interval,
                'initial': initial.copy(),
                'max_step': kwargs['max_step'],
                'atol': np.array(kwargs['atol']).copy(),
                'rtol': kwargs['rtol'],
            }
        )
        is_kink = solution.success and abs(solution.t[-1] - kink) < 1e-3
        is_final = solution.success and solution.t[-1] == 200
        if (is_kink if switching else is_final) and (persistent or not injections):
            solution.y[index, -1] = (
                value if value is not None else (-1.73 if coordinate == 'foregone' else -0.2)
            )
            if failed:
                solution.success = False
                solution.message = 'Injected solver failure'
            injections.append(calls[-1])
        return solution

    monkeypatch.setattr(integrate, 'radau', inject)
    return calls, injections


@pytest.mark.parametrize(
    'case', ['cumulative', 'noncumulative', 'nonswitching', 'upper', 'nonfinite', 'failed']
)
def test_a_material_bound_violation_rejects_the_run_at_once(monkeypatch, case):
    rs = resolved(spending_fixture(1e9 if case == 'upper' else None))
    _calls, injections = injected_solver(
        monkeypatch,
        rs,
        coordinate='cash' if case == 'noncumulative' else 'foregone',
        persistent=True,
        switching=case != 'nonswitching',
        value=1e9 + 0.2 if case == 'upper' else (math.nan if case == 'nonfinite' else None),
        failed=case == 'failed',
    )
    name = 'cash' if case == 'noncumulative' else 'foregone'
    message = (
        'Nonfinite continuous state'
        if case == 'nonfinite'
        else 'Integrator failed: Injected solver failure'
        if case == 'failed'
        else rf'Material state-bound violation for s\.{name}'
    )
    with pytest.raises(SimulationError, match=message):
        simulate(rs, LIBRARY, NumericalSettings())
    assert len(injections) == 1


def cash_control_model():
    # Receipts are 500,000 USD/h. Normal expenditure is 1,000,000 USD/h.
    # With 24 h cash control the first shortfall occurs at 176 h, when cash = 12m.
    return system(
        usd('cash', 100_000_000),
        usd('receipts', kind='tally'),
        usd('spent', kind='tally'),
        usd('foregone', kind='tally', rate=FOREGONE),
        # The patients leave at patients * patients / 20 people an hour, so patients = 20 / (1 + t).
        stock('patients', 20, size=20, kind='state'),
        flow('leave', move('patients', None), 'patients * patients / 20 people / 1 h'),
        formula('spending', SPENDING, 'USD2025/h'),
        flow('receipt', move(None, 'cash'), '500000 USD2025/h'),
        flow('receipt_ledger', move(None, 'receipts'), '500000 USD2025/h'),
        flow('expense', move('cash', 'spent'), 'spending'),
        horizon=240,
    )


def test_positive_piecewise_cumulative_integral_matches_independent_closed_form():
    trajectory = simulate(resolved(cash_control_model()), LIBRARY, None)
    previous = 0
    for time in (0, 24, 120, 175.9999, 176, 176.0001, 180, 192, 216, 240):
        elapsed = max(0, time - 176)
        cash = 100_000_000 - 500_000 * time if time <= 176 else 12_000_000 * math.exp(-elapsed / 24)
        foregone = 500_000 * (elapsed + 24 * math.expm1(-elapsed / 24))
        env = trajectory.env_at(time)
        assert env['s.cash'] == pytest.approx(cash, abs=1.1)
        assert env['s.foregone'] == pytest.approx(foregone, abs=1.1)
        assert env['s.foregone'] >= 0
        assert env['s.foregone'] >= previous - 1.1
        previous = env['s.foregone']
        assert env['s.cash'] + env['s.spent'] - env['s.receipts'] == pytest.approx(100_000_000, abs=1.1)
        assert env['s.spent'] + env['s.foregone'] == pytest.approx(1_000_000 * time, abs=1.1)
        assert env['s.patients'] == pytest.approx(20 / (1 + time), rel=1e-8)
    assert trajectory.settings['rtol'] == 1e-9
    assert trajectory.settings['atol_factor'] == 1e-10
    assert trajectory.settings['max_step'] == 1
    assert all(0 < segment['max_step_h'] <= 1 for segment in trajectory.settings['integration_segments'])
