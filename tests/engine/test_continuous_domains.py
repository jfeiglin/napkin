"""Continuous domains, capacities and output limits are proved between reporting samples.

The transient queue oracle is the closed form for two sequential exponential
stages, not a replay of the engine or an exported reference trajectory.
"""

import math

import pytest

from napkin.engine import evaluate_study, sample_result
from napkin.model import ModelError
from tests.build import (
    append,
    check,
    compiled,
    edit,
    flow,
    formula,
    library,
    member,
    move,
    output,
    replace,
    scenario,
    share,
    status,
    stock,
)

# A narrow peak at 5 h whose exponential overflows there.
PEAK = 'exp(1000 - ((t - 5 h) / 0.01 h) ** 2)'


def test_health_domain_failure_cannot_hide_between_report_endpoints():
    sc = edit(
        scenario(),
        member(
            'service',
            status(('ok', '1 h / (t - 5 h) > 0', 'Available'), ('inactive', None, 'Not available')),
        ),
    )
    try:
        model = compiled(sc)
    except ModelError:
        return  # A conservative domain rejection is an acceptable contract.
    assert not evaluate_study(model).admissible, (
        'An admitted study must be reportable at every in-horizon time, including t=5.'
    )


def test_transient_capacity_violation_cannot_hide_inside_exact_segment():
    sc = edit(
        scenario(),
        replace('flow serve: stock -> served at delivery', 'flow serve: stock -> waiting at stock / 1 h'),
        replace('assert stock + served is n', 'assert abs(stock + waiting + served - n) <= 1e-8 people'),
        member(
            'service',
            stock('waiting', 0, size=10),
            flow('leave', 'waiting -> served', 'waiting / 1 h'),
            check('waiting <= 3 people', 'Waiting occupancy cannot exceed three places'),
        ),
    )
    # A'=−A, W'=A−W, A(0)=10, W(0)=0: W(t)=10*t*exp(−t).
    # Both 0h and 12h are safe; the interior peak at 1h breaches capacity.
    assert 10 / math.e > 3 > 120 * math.exp(-12)
    try:
        model = compiled(sc)
    except ModelError:
        return  # Unsupported continuous invariants may fail closed at compile.
    assert not evaluate_study(model).admissible, (
        'The 1h waiting stock is 10/e people, exceeding the declared capacity of three.'
    )


def test_transient_output_overflow_cannot_depend_on_reporting_grid():
    sc = edit(
        scenario(),
        append(output('transient', f'1 people * {PEAK}', 'people', 'instantaneous', doc='Transient stress')),
    )
    try:
        model = compiled(sc)
    except ModelError:
        return
    assert not evaluate_study(model).admissible, (
        'The output overflows near 5h although the 0h and 24h samples are finite.'
    )


@pytest.mark.parametrize(
    'collection,path',
    [
        ('computed', 'service/hidden_peak'),
        ('rates', 'service/add_unused_counter'),
        ('flows', 'service/unused_inflow'),
        ('allocation', 'service/share_stock'),
    ],
)
def test_unreferenced_continuous_expressions_require_global_domains(collection, path):
    rate = f'1 people/h * {PEAK}'
    if collection == 'computed':
        added = [formula('hidden_peak', PEAK, 'fraction')]
    elif collection == 'rates':
        # A flow from outside into a var makes it a tally, and its rate is the tally's rate.
        added = [stock('unused_counter', 0, minimum=None, size=1, kind='state', rate=rate)]
    elif collection == 'flows':
        # A flow between two vars of the model is a flow.
        added = [
            stock('unused_counter', 0, minimum=None, size=1, kind='state'),
            stock('unused_source', 0, minimum=None, size=1, kind='state'),
            flow('unused_inflow', move('unused_source', 'unused_counter'), rate),
        ]
    else:
        # A share shares a stock that two or more flows draw on: a second flow, which moves nothing,
        # draws on the stock beside `serve`.
        added = [flow('spill', 'stock -> served', '0 people/h'), share('stock', rate)]
    with pytest.raises(ModelError) as raised:
        compiled(edit(scenario(), member('service', *added)))
    assert any(d['code'] == 'dynamic_domain' and d['path'] == path for d in raised.value.diagnostics), (
        raised.value.diagnostics
    )


def test_continuous_domain_checks_preserve_lazy_guards_and_event_only_expressions():
    sc = edit(
        scenario(),
        member(
            'service',
            formula('safe_ratio', 'n / stock if stock > 0 else 0', 'fraction'),
            stock('checkpoint_ratio', 0, 'fraction', minimum=None, size=1, kind='state'),
        ),
        # This division is meaningful at its sole scheduled evaluation, t=12h. It
        # need not be defined at every other instant, particularly the unused t=5h.
        member('service/stop', 'checkpoint_ratio = 7 h / (t - 5 h)'),
    )
    result = evaluate_study(compiled(sc, library()))
    assert result.admissible, result.diagnostics
    report = sample_result(result, [5, 12])
    assert report['admissible']
    assert result.runs['a']['trajectory'].env_at(12)['service.checkpoint_ratio'] == 1
