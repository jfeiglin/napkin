"""Material: flows that move several pairs, flows from or to outside the model, allocation of a stock
that several flows draw on, and sum checks across entities.

They use MODELTEST (tests/model/modeltest.py), a service that an attacker switches off at t = 0 and
that serves waiting users after its repair, and small additions to it. Every expectation is a closed
form of the inputs, read from the model.
"""

from __future__ import annotations

import math
import re

import pytest

from napkin.core.expr import text as written
from napkin.model import ModelError
from tests.build import block, member, replace
from tests.model.modeltest import build, run
from tests.model.test_parts import things, top, with_queues

# The fixture's flow of waiting users, with its text.
SERVE = 'flow serve: waiting -> served at service_rate * waiting while status is not "down"  @ident'
SERVE_TEXT = '        "Waiting users are served."'


def env_at(model, t, name='slow'):
    _, trajectory = run(model, name)
    return trajectory.env_at(t)


def fixture_inputs(model, name='slow'):
    values = model.run_values(name)
    return values['service.users'], values['service.service_rate'], values['service.repair_time']


def served(model, t, name='slow'):
    """Users served by time t in the fixture: none while the service is down, then
    users * (1 - exp(-k (t - repair)))."""
    users, k, repair = fixture_inputs(model, name)
    return 0.0 if t <= repair else users * (1 - math.exp(-k * (t - repair)))


def time_to_serve(model, amount, name='slow'):
    """The time at which the fixture has served `amount` users."""
    users, k, repair = fixture_inputs(model, name)
    return repair - math.log(1 - amount / users) / k


# ---- flows that move several pairs -------------------------------------------------------------


def with_tokens(per_user=None, together='  @ident'):
    """Each user served uses a token from a fixed stock: the serve flow moves both pairs together.
    `per_user` gives the token pair its own rate, that many tokens for each user. `together` ends
    the line of the flow, whose pairs are under it: its records, which say why they move together."""
    pair = 'tokens -> used'
    if per_user is not None:
        pair = f'tokens -> used at {per_user} * service_rate * waiting  @ident'
    head = 'flow serve at service_rate * waiting while status is not "down":' + together
    pairs = '\n'.join(f'        {line}' for line in ('waiting -> served', pair))
    return (
        member('service', 'var tokens = 400 people  @ident', 'var used: people = 0  @ident'),
        replace(f'{SERVE}\n{SERVE_TEXT}', f'{head}\n{SERVE_TEXT}\n{pairs}'),
    )


@pytest.mark.parametrize('per_user', [None, 2])
def test_pairs_that_move_together_stop_together_when_one_runs_short(tmp_path, per_user):
    model = build(tmp_path, *with_tokens(per_user))
    tokens_per_user = per_user or 1
    # Tokens run out once 400 / tokens_per_user users are served; the users' pair stops with them.
    limit = 400 / tokens_per_user
    out_of_tokens = time_to_serve(model, limit)
    users = model.run_values('slow')['service.users']
    for t in (out_of_tokens - 2, out_of_tokens + 5, 120.0):
        env = env_at(model, t)
        expected = min(served(model, t), limit)
        assert env['service.served'] == pytest.approx(expected, rel=1e-6, abs=1e-6), t
        assert env['service.used'] == pytest.approx(tokens_per_user * expected, rel=1e-6, abs=1e-6), t
        assert env['service.waiting'] + env['service.served'] == pytest.approx(users)
    # Without the second pair the service would have served far more by the end.
    assert served(model, 120.0) > limit + 100


def test_pairs_are_the_engine_s_coupled_flows(tmp_path):
    s = build(tmp_path, *with_tokens(2)).structure_of('slow')
    (group,) = s.coupling.values()
    assert list(group.flows) == ['service.serve.0', 'service.serve.1']
    flows = s.flows
    assert (flows['service.serve.0'].source, flows['service.serve.0'].target) == (
        'service.waiting',
        'service.served',
    )
    assert (flows['service.serve.1'].source, flows['service.serve.1'].target) == (
        'service.tokens',
        'service.used',
    )
    # The pair's own rate, under the flow's `while`.
    assert written(flows['service.serve.1'].rate).startswith('2 * service.service_rate * service.waiting if ')


def test_a_flow_of_several_pairs_says_why_they_move_together(tmp_path):
    # The line of a flow of several pairs with no record.
    with pytest.raises(ModelError, match='together'):
        build(tmp_path, *with_tokens(together=''))


# ---- outside the model -------------------------------------------------------------------------


WITH_OUTSIDE = member(
    'service',
    'var counted: people = 0  @ident',
    'var spare = 100 people  @ident',
    'flow count_served: -> counted at service_rate * waiting while status is not "down"  @ident',
    'flow discard: spare -> at 0.1 per_h * spare  @ident',
)


def test_flows_from_and_to_outside_the_model(tmp_path):
    model = build(tmp_path, WITH_OUTSIDE)
    s = model.structure_of('slow')
    flows = s.flows
    # The flow from outside into the tally `counted` is the engine's rate of that tally: it has no
    # source.
    assert 'service.count_served' not in flows
    assert s.rates['service.counted'].path == 'service/count_served'
    assert flows['service.discard'].source == 'service.spare' and flows['service.discard'].target is None
    for t in (20.0, 45.0, 120.0):
        env = env_at(model, t)
        # A counter from outside takes the serve flow's rate, so it counts every user served.
        assert env['service.counted'] == pytest.approx(served(model, t), rel=1e-6, abs=1e-6)
        assert env['service.spare'] == pytest.approx(100 * math.exp(-0.1 * t), rel=1e-6)


def test_a_pair_has_an_end_inside_the_model(tmp_path):
    with pytest.raises(ModelError, match='at least one value of the model'):
        build(tmp_path, replace(SERVE, SERVE.replace('waiting -> served', '->')))


# ---- allocation ---------------------------------------------------------------------------------


def with_store(serve, limit, share=True, flows='ab'):
    """A store of 100 that two flows draw on at 3 and 2 an hour, shared up to `limit` an hour (with no
    share without `share`): `serve` is `proportional` or the flows in their order; `flows` names the
    flows that the store has."""
    order = '' if isinstance(serve, str) else ' order ' + ', '.join(serve)
    return things(
        block(
            'store:  @ident',
            '"A store that two flows draw on."',
            'role operator',
            'var stock = 100 people  @ident',
            'var to_a: people = 0  @ident',
            'var to_b: people = 0  @ident',
            'flow take_a: stock -> to_a at 3 people / 1 h  @ident' if 'a' in flows else None,
            'flow take_b: stock -> to_b at 2 people / 1 h  @ident' if 'b' in flows else None,
            f'share stock limit {limit} people / 1 h{order}  @ident' if share else None,
        )
    )


@pytest.mark.parametrize(
    ('serve', 'limit', 'rate_a', 'rate_b'),
    [
        # The first flow gets what it asks for, the second what is left under the limit.
        (['take_a', 'take_b'], 4, 3.0, 1.0),
        (['take_b', 'take_a'], 4, 2.0, 2.0),
        # Each flow gets the same share of its request.
        ('proportional', 4, 3.0 * 4 / 5, 2.0 * 4 / 5),
        # A limit above both requests does not bind.
        ('proportional', 10, 3.0, 2.0),
    ],
)
def test_a_rationing_entry_shares_its_stock_up_to_its_limit(tmp_path, serve, limit, rate_a, rate_b):
    model = build(tmp_path, with_store(serve, limit))
    empty = 100 / (rate_a + rate_b)
    for t in (empty / 2, empty + 10):
        env = env_at(model, t)
        hours = min(t, empty)
        assert env['store.to_a'] == pytest.approx(rate_a * hours, rel=1e-6, abs=1e-6), t
        assert env['store.to_b'] == pytest.approx(rate_b * hours, rel=1e-6, abs=1e-6), t
        assert env['store.stock'] == pytest.approx(100 - (rate_a + rate_b) * hours, rel=1e-6, abs=1e-6), t


@pytest.mark.parametrize(('limit', 'rate'), [(2, 2.0), (10, 3.0)])
def test_a_rationing_entry_of_one_flow_caps_it_at_its_limit(tmp_path, limit, rate):
    # A list of a template's instances can have one member: the entry then shares its stock with no
    # other flow, and its limit caps the one flow that draws on it.
    model = build(tmp_path, with_store('proportional', limit, flows='a'))
    empty = 100 / rate
    for t in (empty / 2, empty + 10):
        env = env_at(model, t)
        assert env['store.to_a'] == pytest.approx(rate * min(t, empty), rel=1e-6, abs=1e-6), t


def test_a_rationing_entry_needs_a_flow_that_draws_on_its_stock(tmp_path):
    # With no flow that takes from it, the var is no stock (docs/language.md, §2.4), so nothing shares it.
    with pytest.raises(ModelError, match='stock is not a stock'):
        build(tmp_path, with_store('proportional', 4, flows=''))


def test_rationing_is_the_engine_s_allocation_group(tmp_path):
    s = build(tmp_path, with_store(['take_b', 'take_a'], 4)).structure_of('slow')
    (name,) = s.allocation
    group = s.allocation[name]
    assert group.policy == 'priority'
    assert list(group.order) == ['store.take_b', 'store.take_a']
    assert {s.flows[f].allocation for f in ('store.take_a', 'store.take_b')} == {name}


def test_two_flows_out_of_one_stock_without_rationing_are_rejected(tmp_path):
    with pytest.raises(ModelError, match='Competing withdrawals require one explicit allocation policy'):
        build(tmp_path, with_store('proportional', 4, share=False))


@pytest.mark.parametrize(
    ('serve', 'match'),
    [
        (['take_a'], 'once'),
        (['take_a', 'take_a'], 'serve lists'),
        (['take_a', 'missing'], 'not a flow that draws on'),
    ],
)
def test_a_priority_lists_every_flow_that_draws_on_the_stock_once(tmp_path, serve, match):
    with pytest.raises(ModelError, match=match):
        build(tmp_path, with_store(serve, 4))


# ---- sum checks across entities ----------------------------------------------------------------


def with_main_sum(refs):
    return top(
        block(
            f'assert {" + ".join(refs)} is small.size + large.size within 0.001 people  @ident',
            '"Every user of the two queues is waiting or dealt with."',
        )
    )


def test_a_sum_check_of_the_main_lists_stocks_of_several_entities(tmp_path):
    refs = ['small.pending', 'small.handled', 'large.pending', 'large.handled']
    model = build(tmp_path, *with_queues(), with_main_sum(refs))
    (partition,) = [p for p in model.structure_of('slow').partitions.values() if len(p.parts) == 4]
    assert list(partition.parts) == refs
    env = env_at(model, 120.0)
    values = model.run_values('slow')
    assert sum(env[ref] for ref in refs) == pytest.approx(values['small.size'] + values['large.size'])


def test_a_sum_check_of_the_main_lists_stocks_and_tallies_only(tmp_path):
    with pytest.raises(ModelError, match=re.escape('dispatcher.total is not a number var')):
        build(tmp_path, *with_queues(), with_main_sum(['small.pending', 'dispatcher.total']))
