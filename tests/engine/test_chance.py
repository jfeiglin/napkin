"""Draws under the run's mode (spec, "Distributions and explicit draws"; D1; `chance.py`).

A median run takes the median of a numeric distribution and the most likely outcome of a categorical
one, the first declared of them on a tie; a sampled run draws each outcome with its weight. A draw is
keyed by the seed, its site and the member, the occurrence or the firing that executes it (R-A2-17):
a sampled run replays exactly from its seed, and a branch that is not taken, an extra read or a step
size of the integrator moves no draw. The expected values are medians and moments worked by hand, a
binomial share, and the oracle's own draws (`tests/reference/`), which key a draw the same way.
"""

from __future__ import annotations

import math
from dataclasses import replace

import pytest
from scipy import integrate, stats

from napkin.engine import read, run
from napkin.engine.errors import SimulationError
from napkin.engine.timeline.chance import described, numeric, outcome, uniform
from napkin.expressions import UnitSystem
from napkin.program import parts as p
from napkin.program.build import (
    BOOL,
    SOURCE,
    Builder,
    add,
    after,
    assign,
    case,
    categorical,
    draw,
    event,
    flow,
    formula,
    if_,
    ifelse,
    input_,
    local,
    lognormal,
    loguniform,
    named,
    normal,
    pert,
    q,
    start,
    switch,
    this,
    triangular,
    value,
)
from napkin.program.build import uniform as uniform_of
from napkin.program.config import SAMPLED, Configuration, InputValue, Numerics, Request
from napkin.program.record import Key
from napkin.program.refs import Distribution, Named, Path, This
from tests.reference.from_program import run_of, value_at

UNITS = {'h': {'time': 1}, 'L': {'volume': 1}, 'min': ({'time': 1}, '1/60')}


def decision(weights, guarded=False):
    """A machine that draws `categorical(weights)` at 2 h and records the outcome as its state."""
    b = Builder(UNITS)
    names = tuple(weights)
    kind = b.enum(f'enum[{", ".join(names)}]', *names)
    b.entity(
        'machine',
        value('state', kind, getattr(kind, names[0])),
        value('drawn', BOOL, False),
        event(
            'check',
            after(
                q(2, 'h'),
                assign(this.drawn, True),
                switch(
                    draw(categorical(kind, **weights)),
                    *(case(getattr(kind, name), assign(this.state, getattr(kind, name))) for name in names),
                ),
            ),
        ),
    )
    b.setup(start(named('machine').check))
    return b.finish()


def state_of(program, configuration):
    (reading,) = read(run(program, configuration), program, ['machine.state'], [3])
    return reading.values[0]


@pytest.mark.parametrize(
    ('weights', 'expected'),
    [
        ({'SHUT': 0.3, 'MANUAL': 0.7}, 'MANUAL'),  # the likeliest
        ({'SHUT': 0.7, 'MANUAL': 0.3}, 'SHUT'),
        ({'SHUT': 0.5, 'MANUAL': 0.5}, 'SHUT'),  # a tie: the first declared
        ({'MANUAL': 0.5, 'SHUT': 0.5}, 'MANUAL'),
        ({'SHUT': 1, 'MANUAL': 2, 'WAIT': 2}, 'MANUAL'),
    ],
)
def test_a_median_run_takes_the_likeliest_outcome_and_the_first_declared_on_a_tie(weights, expected):
    assert state_of(decision(weights), Configuration(Request(3))) == expected


def test_a_sampled_run_draws_each_outcome_with_its_weight():
    """Over 400 seeds the share of SHUT is 0.3 within three standard deviations of a binomial share."""
    program = decision({'SHUT': 0.3, 'MANUAL': 0.7})
    found = [state_of(program, Configuration(Request(3), mode=SAMPLED, seed=seed)) for seed in range(400)]
    spread = 3 * math.sqrt(0.3 * 0.7 / 400)
    assert abs(found.count('SHUT') / 400 - 0.3) <= spread
    assert set(found) == {'SHUT', 'MANUAL'}


def test_the_outcome_of_a_uniform_number_is_the_one_whose_share_holds_it():
    """Weights 1, 2 and 1 cut (0, 1) at 1/4 and 3/4, in declared order; with SHUT barred, MANUAL and
    WAIT share it 2 to 1, cut at 2/3."""
    d = Distribution('categorical', (1, 2, 1), enum='E', outcomes=('SHUT', 'MANUAL', 'WAIT'))
    shares = {u: outcome(d, None, u) for u in (0.01, 0.2499, 0.2501, 0.7499, 0.7501, 0.99)}
    assert list(shares.values()) == ['SHUT', 'SHUT', 'MANUAL', 'MANUAL', 'WAIT', 'WAIT']
    assert [outcome(d, ('MANUAL', 'WAIT'), u) for u in (0.66, 0.67)] == ['MANUAL', 'WAIT']
    assert outcome(d, ('MANUAL', 'WAIT'), None) == 'MANUAL'


@pytest.mark.parametrize('seed', range(8))
@pytest.mark.parametrize(
    ('weights', 'large'),
    [
        ((1, 1), (1e308, 1e308)),
        ((1, 2, 1), (5e307, 1e308, 5e307)),
    ],
    ids=['equal', 'unequal'],
)
def test_rescaling_categorical_weights_preserves_each_seeded_draw(seed, weights, large):
    names = ('FIRST', 'SECOND', 'THIRD')[: len(weights)]
    configuration = Configuration(Request(3), mode=SAMPLED, seed=seed)
    answers = []
    for scale in (weights, large):
        program = decision(dict(zip(names, scale, strict=True)))
        oracle, failed = run_of(program, configuration)
        assert failed is None
        expected = value_at(oracle, program, Key('machine', ('state',)), 3)
        answers.append((state_of(program, configuration), expected))
    ordinary, huge = answers
    assert ordinary[0] == ordinary[1] == huge[1]
    assert huge[0] == huge[1]


def test_categorical_overflow_preserves_eligible_boundaries_and_median_ties():
    dist = Distribution('categorical', (1e308, 0, 1e308, 1e308), enum='E', outcomes=('A', 'Z', 'B', 'C'))
    eligible = ('C', 'Z', 'A')
    assert outcome(dist, eligible, None) == 'A'
    for u, expected in ((math.nextafter(0.5, 0), 'A'), (0.5, 'C'), (math.nextafter(0.5, 1), 'C')):
        assert outcome(dist, eligible, u) == expected


@pytest.mark.parametrize('u', [None, 0.5])
@pytest.mark.parametrize('eligible', [(), ('Z',)])
def test_categorical_without_an_eligible_positive_weight_still_fails(eligible, u):
    dist = Distribution('categorical', (1e308, 0, 1e308), enum='E', outcomes=('A', 'Z', 'B'))
    with pytest.raises(SimulationError, match='no eligible outcome has a weight to draw'):
        outcome(dist, eligible, u)


def test_the_uniform_number_of_a_draw_is_open_and_keyed():
    found = [uniform(seed, 'site|owner') for seed in range(200)]
    assert all(0 < u < 1 for u in found) and len(set(found)) == 200
    assert uniform(7, 'a|b') == uniform(7, 'a|b') != uniform(7, 'a|c')


@pytest.mark.parametrize(
    ('distribution', 'median'),
    [
        (uniform_of(1, 3, 'h'), 2),
        (triangular(1, 2, 4, 'h'), 4 - math.sqrt(3)),  # 1 - F(x) = (4 - x)^2 / 6 = 1/2
        (loguniform(1, 4, 'h'), 2),  # the geometric mean of the ends
        (normal(2, 0.5, 'h'), 2),
        (lognormal(2, 1.5, 'h'), 2),
        (triangular(60, 120, 240, 'min'), 4 - math.sqrt(3)),  # the same, in minutes
    ],
)
def test_a_median_run_draws_the_median_of_a_numeric_distribution(distribution, median):
    assert numeric(distribution, UnitSystem(_scales()), 0.5) == pytest.approx(median, rel=1e-12)


def _scales():
    return {
        'h': {'dimensions': {'time': 1}, 'scale': 1.0},
        'min': {'dimensions': {'time': 1}, 'scale': 1 / 60},
    }


def _truncated_lognormal(median, gsd, low, high, k):
    """The k-th moment of a lognormal truncated to [low, high], by quadrature of its density."""
    shape, scale = math.log(gsd), median
    density = stats.lognorm(shape, scale=scale).pdf
    mass = integrate.quad(density, low, high)[0]
    return integrate.quad(lambda x: x**k * density(x), low, high)[0] / mass


@pytest.mark.parametrize(
    ('distribution', 'mean', 'sd'),
    [
        (uniform_of(1, 3, 'h'), 2, 2 / math.sqrt(12)),
        (triangular(1, 2, 4, 'h'), 7 / 3, math.sqrt((1 + 4 + 16 - 2 - 4 - 8) / 18)),
        # PERT(1, 2, 4): a beta(7/3, 11/3) on [1, 4]
        (pert(1, 2, 4, 'h'), 1 + 3 * (7 / 3) / 6, 3 * math.sqrt((7 / 3) * (11 / 3) / (36 * 7))),
        (loguniform(1, 4, 'h'), 3 / math.log(4), math.sqrt(15 / (2 * math.log(4)) - (3 / math.log(4)) ** 2)),
        (normal(2, 0.5, 'h'), 2, 0.5),
        (
            normal(2, 1, 'h', lower=1, upper=4),
            stats.truncnorm(-1, 2, loc=2, scale=1).mean(),
            stats.truncnorm(-1, 2, loc=2, scale=1).std(),
        ),
        (lognormal(2, 1.5, 'h'), 2 * math.exp(math.log(1.5) ** 2 / 2), None),
        (
            lognormal(2, 1.5, 'h', lower=1, upper=5),
            _truncated_lognormal(2, 1.5, 1, 5, 1),
            math.sqrt(_truncated_lognormal(2, 1.5, 1, 5, 2) - _truncated_lognormal(2, 1.5, 1, 5, 1) ** 2),
        ),
    ],
)
def test_the_mean_and_the_standard_deviation_of_a_distribution_are_its_closed_forms(distribution, mean, sd):
    units = UnitSystem(_scales())
    assert described(distribution, units, 'mean') == pytest.approx(mean, rel=1e-9)
    if sd is not None:
        assert described(distribution, units, 'std') == pytest.approx(sd, rel=1e-9)


# ---- keyed draws -------------------------------------------------------------------------------------


def keyed(early=False, mean=False, fill=False):
    """A pump that draws its speed at 1 h; `early` (an input) makes another stage draw at 0 h in a branch;
    `mean` adds a formula that reads the distribution; `fill` adds a tank that fills on a curve, which an
    integrator steps through."""
    b = Builder(UNITS)
    parts = [
        input_('early', BOOL, early),
        value('speeds', None, uniform_of(1, 3, 'L/h')),
        value('first', 'L/h', 0),
        value('speed', 'L/h', 0),
        value('choice', 'L/h', 0),
        event(
            'work',
            after(q(0, 'h'), if_(this.early, [assign(this.first, draw(this.speeds))])),
            after(
                q(1, 'h'),
                assign(this.speed, draw(this.speeds)),
                assign(this.choice, ifelse(this.early, draw(uniform_of(5, 6, 'L/h')), q(0, 'L/h'))),
            ),
        ),
    ]
    if mean:
        parts.append(value('typical', 'L/h', formula(this.speeds.mean)))
    if fill:
        parts += [
            value('tank', 'L', 1, lower=0, upper=100),
            flow('fill', SOURCE, this.tank, request=formula(q(1, 'L/h') * this.tank / q(1, 'L'))),
        ]
    b.entity('pump', *parts)
    b.setup(start(named('pump').work))
    return b.finish()


def drawn(record):
    return {(entry.part, entry.owner): entry.detail('value') for entry in record.entries('draw')}


def sampled(seed=7, **settings):
    return Configuration(Request(2), mode=SAMPLED, seed=seed, **settings)


def test_a_sampled_run_replays_exactly_from_its_seed():
    program = keyed(fill=True)
    first, again = run(program, sampled()), run(program, sampled())
    assert first == again
    assert drawn(first) != drawn(run(program, sampled(8)))


def test_a_branch_that_is_not_taken_draws_nothing_and_moves_no_other_draw():
    late = ('pump.work.step[1].do[0].draw[0]', 'pump.work#0')
    without = drawn(run(keyed(early=False), sampled()))
    taken = run(keyed(early=False), replace(sampled(), inputs=(InputValue('pump', 'early', True),)))
    with_branch = drawn(taken)
    assert late in without and without[late] == with_branch[late]
    assert len(without) == 1 and len(with_branch) == 3  # the stage at 0 h and the `if` expression


def test_an_extra_read_of_a_distribution_draws_nothing_and_moves_no_draw():
    plain, read_too = run(keyed(), sampled()), run(keyed(mean=True), sampled())
    assert drawn(plain) == drawn(read_too)
    (typical,) = read(read_too, keyed(mean=True), ['pump.typical'], [2])
    assert typical.values == (pytest.approx(2.0),)


def test_another_step_size_moves_no_draw():
    """The tank fills on a curve (dx/dt = x), which the integrator steps through: a longest step of
    1/100 h makes many more steps than one of 1 h, and the draws are the same."""
    program = keyed(fill=True)
    coarse = run(program, sampled())
    fine = run(program, sampled(numerics=Numerics(max_step=0.01)))
    assert drawn(coarse) == drawn(fine)
    tank = [read(record, program, ['pump.tank'], [2])[0].values[0] for record in (coarse, fine)]
    assert tank == pytest.approx([math.exp(2)] * 2, rel=1e-6)


def test_a_sampled_draw_equals_the_oracles_and_lies_in_its_support():
    """The oracle keys its draws by the same site and owner, and maps the same uniform number."""
    program = keyed(early=True)
    for seed in range(20):
        configuration = sampled(seed)
        record = run(program, configuration)
        oracle, failed = run_of(program, configuration)
        assert failed is None
        for name in ('first', 'speed', 'choice'):
            found = read(record, program, [f'pump.{name}'], [2])[0].values[0]
            assert found == pytest.approx(
                float(value_at(oracle, program, Key('pump', (name,)), 2)), rel=1e-12
            )
        speed = read(record, program, ['pump.speed'], [2])[0].values[0]
        assert 1 <= speed <= 3


def test_each_executed_draw_is_traced_with_its_owner_its_site_and_its_value():
    record = run(keyed(early=True), Configuration(Request(2), inputs=()))
    entries = [(entry.t, entry.part, entry.owner, entry.detail('value')) for entry in record.entries('draw')]
    assert entries == [
        (0, 'pump.work.step[0].do[0].then[0].draw[0]', 'pump.work#0', 2.0),
        (1, 'pump.work.step[1].do[0].draw[0]', 'pump.work#0', 2.0),
        (1, 'pump.work.step[1].do[1].draw[0]', 'pump.work#0', 5.5),
    ]


def test_a_counter_that_a_draw_feeds_adds_the_median_each_time():
    """Three occurrences each add a draw of uniform(1 L, 3 L): 3 times the median, 2 L."""
    b = Builder(UNITS)
    b.entity(
        'tank',
        value('water', 'L', 0),
        event('fill', after(q(1, 'h'), add(this.water, draw(uniform_of(1, 3, 'L'))))),
    )
    tank = named('tank')
    b.setup(start(tank.fill), start(tank.fill), start(tank.fill))
    program = b.finish()
    record = run(program, Configuration(Request(2)))
    assert read(record, program, ['tank.water'], [2])[0].values == (pytest.approx(6.0),)
    assert sorted(entry.owner for entry in record.entries('draw')) == [f'tank.fill#{k}' for k in range(3)]


def test_replacing_a_distribution_leaves_what_was_drawn_and_changes_the_draws_after_it():
    """Spec: "Replacing a descriptor leaves previously stored samples intact." A machine draws at its
    start from uniform(1 h, 3 h) (median 2 h); its stage at 1 h stores the draw and replaces the
    distribution with uniform(2 h, 6 h), and a draw at 2 h takes the new median, 4 h. The mean
    follows the distribution: 2 h, then 4 h from 1 h."""
    b = Builder(UNITS)
    b.entity(
        'machine',
        value('times', None, uniform_of(1, 3, 'h')),
        value('first', 'h', 0),
        value('later', 'h', 0),
        value('typical', 'h', formula(this.times.mean)),
        event(
            'go',
            value('drawn', 'h', draw(this.times)),
            after(q(1, 'h'), assign(this.first, local.drawn), assign(this.times, uniform_of(2, 6, 'h'))),
            after(q(1, 'h'), assign(this.later, draw(this.times))),
        ),
    )
    b.setup(start(named('machine').go))
    program = b.finish()
    record = run(program, Configuration(Request(3)))
    found = read(record, program, ['machine.first', 'machine.later', 'machine.typical'], [0, 1, 3])
    assert [reading.values for reading in found] == [(0, 2, 2), (0, 0, 4), (2, 4, 4)]


def test_a_distribution_can_be_the_distribution_of_another_at_the_start():
    """A value whose initializer names another distribution-valued value takes its distribution
    (the builder spells only a distribution written in place: the parts are written whole)."""
    b = Builder(UNITS)
    kind = p.DistributionType(p.Number('h'))
    b.entity('shop', value('times', None, uniform_of(2, 4, 'h')))
    b.entity(
        'machine',
        p.Value('mine', p.DISTRIBUTION, kind, Path(Named('shop'), ('times',))),
        value('ready', 'h', 0),
        event(
            'go',
            p.Value('own', p.DISTRIBUTION, kind, Path(This(), ('mine',))),
            after(q(0, 'h'), assign(this.ready, draw(named('machine').mine))),
        ),
    )
    b.setup(start(named('machine').go))
    program = b.finish()
    record = run(program, Configuration(Request(1)))
    assert read(record, program, ['machine.ready'], [1])[0].values == (3,)
