"""Monte Carlo studies (`napkin/engine/uncertainty.py`) on tiny models with closed forms.

Each model's value has a closed form in the draws of its run, which each sample's trace holds, so every
sample must equal its own closed form: the test covers the seeds, the draws, the runs, the reads and the
summaries together, with no statistical tolerance. A tank that fills at a drawn rate r for 4 h holds 4 r;
a tank that drains at a drawn fraction k of its water an hour holds 100 L exp(-k t). The percentiles of a
summary are the type-7 percentiles of those closed forms (Hyndman and Fan), and the rank correlation of
two samples without ties is 1 - 6 sum(d^2) / (n (n^2 - 1)).
"""

from __future__ import annotations

import math
import textwrap
import threading
from dataclasses import replace

import pytest

from napkin.engine.sampling import SamplingSettings, sample_seed
from napkin.engine.study import Cancelled
from napkin.engine.timeline import read, run
from napkin.engine.uncertainty import monte_carlo
from napkin.model.compile import compile_text
from napkin.program.config import MEDIAN, SAMPLED
from tests.program.examples import UNITS

TANK = textwrap.dedent("""\
    scenario "Tank"
        horizon 4 h
    tank:
        input rate: L/h = uniform(1 L/h, 3 L/h).draw()  @measured
            "Inflow"
        water: L = 0 L in [0 L,]
            "Water in the tank"
        full = formula(this.water >= 10 L)
        ratio = formula(1 L / this.water)
        flow fill: SOURCE -> this.water
            request = this.rate
    record measured: source "A gauge reading."
    """)
RATE = 'tank.rate.draw[0]'


def noisy():
    """The tank with a noise that a flow of its own reads, so that each run draws it and the water does
    not depend on it."""
    return TANK.replace(
        '    flow fill:',
        '    input noise: L/h = uniform(0 L/h, 1 L/h).draw()\n'
        '    spill: L = 0 L in [0 L,]\n'
        '    flow trickle: SOURCE -> this.spill\n'
        '        request = this.noise\n'
        '    flow fill:',
    )


def compiled(text=TANK):
    return compile_text(text, UNITS)


def study(model, paths=('tank.water',), times=(4,), samples=24, seed=7, **options):
    return monte_carlo(
        model.program,
        model.configuration,
        paths,
        times,
        SamplingSettings(samples, seed),
        model=model.declared,
        **options,
    )


def drawn(sample, site=RATE, owner='tank'):
    """The value that a sample drew at a site, by an owner, from its trace."""
    (value,) = [value for found, by, value in sample.draws if (found, by) == (site, owner)]
    return value


def type7(values, p):
    x = sorted(values)
    h = (len(x) - 1) * p / 100
    low = math.floor(h)
    return x[low] + (h - low) * (x[min(low + 1, len(x) - 1)] - x[low])


def ranked(values):
    order = sorted(range(len(values)), key=values.__getitem__)
    ranks = [0] * len(values)
    for rank, place in enumerate(order, 1):
        ranks[place] = rank
    return ranks


def spearman_without_ties(x, y):
    n = len(x)
    d = sum((a - b) ** 2 for a, b in zip(ranked(x), ranked(y)))
    return 1 - 6 * d / (n * (n * n - 1))


def test_each_sample_of_a_tally_equals_its_rate_times_the_time_and_the_summary_is_theirs():
    found = study(compiled(), times=(0, 2, 4))
    assert found.refused is None and len(found.samples) == 24
    for sample in found.samples:
        rate = drawn(sample)
        assert 1 <= rate <= 3 and sample.values[0] == pytest.approx((0, 2 * rate, 4 * rate), rel=1e-12)
    closed = [4 * drawn(sample) for sample in found.samples]
    summary = found.spread('tank.water', 4).summary
    assert summary.estimated and summary.central == pytest.approx(8)  # the median rate, 2 L/h
    assert summary.mean.value == pytest.approx(sum(closed) / 24, rel=1e-12)
    assert (summary.least, summary.greatest) == pytest.approx((min(closed), max(closed)), rel=1e-12)
    assert summary.sd == pytest.approx(
        math.sqrt(sum((x - sum(closed) / 24) ** 2 for x in closed) / 23), rel=1e-9
    )
    assert summary.sem == pytest.approx(summary.sd / math.sqrt(24), rel=1e-12)
    assert [p for p, _ in summary.percentiles] == [5, 25, 50, 75, 95]
    assert [value for _, value in summary.percentiles] == pytest.approx(
        [type7(closed, p) for p in (5, 25, 50, 75, 95)], rel=1e-12
    )
    spread = found.spread('tank.water', 4)
    assert (spread.unit, spread.label) == ('L', 'Water in the tank')


def test_each_sample_of_a_decay_equals_its_exponential():
    text = textwrap.dedent("""\
        scenario "Drain"
            horizon 3 h
        tank:
            input k: 1/h = uniform(0.1, 0.5).draw()
            water: L = 100 L in [0 L,]
            flow drain: this.water -> SINK
                request = formula(this.k * this.water)
        """)
    model = compiled(text)
    found = monte_carlo(model.program, model.configuration, ['tank.water'], [1, 3], SamplingSettings(12, 3))
    for sample in found.samples:
        k = drawn(sample, 'tank.k.draw[0]')
        assert sample.values[0] == pytest.approx((100 * math.exp(-k), 100 * math.exp(-3 * k)), rel=1e-6)


def test_an_enum_draw_picks_a_rate_and_each_member_of_a_template_draws_its_own():
    """Each pump fills at 3 L/h when its plan is HIGH (three times in ten), else at its own drawn rate."""
    text = textwrap.dedent("""\
        scenario "Pumps"
            horizon 4 h
        Pump:
            input rate: L/h = uniform(1 L/h, 3 L/h).draw()
            input plan = categorical(HIGH: 0.3, LOW: 0.7).draw()
            water: L = 0 L in [0 L,]
            flow fill: SOURCE -> this.water
                request = formula(3 L/h if this.plan == HIGH else this.rate)
        east: Pump
        west: Pump
        """)
    found = study(compiled(text), paths=('east.water', 'west.water', 'east.plan'), samples=40)
    for sample in found.samples:
        for place, pump in enumerate(('east', 'west')):
            rate, plan = drawn(sample, 'Pump.rate.draw[0]', pump), drawn(sample, 'Pump.plan.draw[0]', pump)
            assert sample.values[place][0] == pytest.approx(4 * (3 if plan == 'HIGH' else rate), rel=1e-12)
        assert sample.values[2][0] == drawn(sample, 'Pump.plan.draw[0]', 'east')
    assert {drawn(sample, 'Pump.plan.draw[0]', 'east') for sample in found.samples} == {'HIGH', 'LOW'}
    rates = [
        (drawn(sample, 'Pump.rate.draw[0]', 'east'), drawn(sample, 'Pump.rate.draw[0]', 'west'))
        for sample in found.samples
    ]
    assert all(east != west for east, west in rates)
    plan = found.spread('east.plan', 4).summary
    assert not plan.estimated and plan.reason == 'a text has no mean' and plan.central == 'LOW'


def test_a_draw_in_a_stage_comes_from_the_seed_of_its_sample():
    text = TANK + textwrap.dedent("""\
        crew:
            duration: h = 0 h
            wait = event():
                after 1 h:
                    this.duration = uniform(1 h, 3 h).draw()
        crew.wait.start()
        """)
    found = study(compiled(text), paths=('crew.duration',), times=(0, 2), samples=12)
    durations = [drawn(sample, 'crew.wait.step[0].do[0].draw[0]', 'crew.wait#0') for sample in found.samples]
    assert [sample.values[0] for sample in found.samples] == [(0, d) for d in durations]
    assert len(set(durations)) == 12 and all(1 <= d <= 3 for d in durations)
    assert found.spread('crew.duration', 2).summary.central == pytest.approx(2)


def test_a_seed_gives_the_same_study_and_sample_k_does_not_depend_on_their_number():
    model = compiled()
    first, again, more = study(model, samples=10), study(model, samples=10), study(model, samples=20)
    assert first == again
    assert more.samples[:10] == first.samples
    assert [sample.seed for sample in first.samples] == [sample_seed(7, k) for k in range(10)]
    assert study(model, samples=10, seed=8).samples[0] != first.samples[0]


def test_an_unrelated_uncertain_input_leaves_the_other_draws_alone():
    model = compiled()
    other = compiled(noisy())
    plain, both = study(model, samples=10), study(other, samples=10)
    assert all(len(sample.draws) == 2 for sample in both.samples)
    assert [drawn(sample) for sample in both.samples] == [drawn(sample) for sample in plain.samples]


def test_the_central_run_is_the_median_run_whatever_the_mode_of_the_configuration():
    model = compiled()
    given = replace(model.configuration, mode=SAMPLED, seed=11)
    found = monte_carlo(model.program, given, ['tank.water'], [4], SamplingSettings(4, 7))
    median = run(model.program, replace(model.configuration, mode=MEDIAN))
    assert median.entries('draw')[0].detail('value') == 2
    assert found.central.values[0].values == pytest.approx((8,)) and found.central.stopped is None
    assert [sample.seed for sample in found.samples] == [sample_seed(7, k) for k in range(4)]


def test_a_sample_whose_run_fails_refuses_the_study_and_names_it():
    """The assertion holds at the median rate, 2 L/h, and fails at the start of each sample that draws
    more than 2.5 L/h: those samples, and only those, are named with their seeds."""
    found = study(compiled(TANK + 'assert tank.rate <= 2.5 L/h\n'), samples=24)
    failed = [k for k, sample in enumerate(found.samples) if drawn(sample) > 2.5]
    assert failed and found.spreads == () and found.refused is not None
    for k, sample in enumerate(found.samples):
        named = f'sample {k} (seed {sample.seed}) stops: the run failed at 0 h' in found.refused
        assert named == (k in failed)
    assert all((sample.stopped is not None) == (k in failed) for k, sample in enumerate(found.samples))


def test_a_central_run_that_stops_refuses_the_study_before_any_sample_runs():
    found = study(compiled(TANK + 'assert tank.rate <= 1.5 L/h\n'))
    assert found.samples == () and found.spreads == ()
    assert found.refused.startswith('the central run stops: the run failed at 0 h')


def test_samples_in_two_processes_agree_with_one_process_and_the_same_study_is_the_same_again():
    model = compiled()
    here = study(model, samples=16, times=(1, 4))
    pool = study(model, samples=16, times=(1, 4), jobs=2)
    assert [sample.seed for sample in pool.samples] == [sample.seed for sample in here.samples]
    for one, other in zip(here.samples, pool.samples):
        assert one.draws == other.draws and other.values[0] == pytest.approx(one.values[0], rel=1e-9)
    assert pool.spread('tank.water', 4).summary.mean.value == pytest.approx(
        here.spread('tank.water', 4).summary.mean.value, rel=1e-9
    )
    assert study(model, samples=16, times=(1, 4)) == here


@pytest.mark.parametrize('jobs', [1, 2])
def test_a_caller_can_stop_a_study_between_samples(jobs):
    cancel, seen = threading.Event(), []

    def progress(done, total):
        seen.append((done, total))
        if done >= 3:
            cancel.set()

    with pytest.raises(Cancelled):
        study(compiled(), samples=200, jobs=jobs, progress=progress, cancel=cancel)
    assert seen and seen[-1][1] == 200 and seen[-1][0] < 200
    if jobs == 1:
        assert seen == [(1, 200), (2, 200), (3, 200)]


def test_a_value_that_a_run_cannot_give_has_no_summary_and_says_why():
    """1 L / water has no value at the start, when the tank is empty; at 4 h it is 1 / (4 r)."""
    found = study(compiled(), paths=('tank.ratio',), times=(0, 4), samples=8)
    start = found.spread('tank.ratio', 0).summary
    assert not start.estimated and 'division by zero' in start.reason and start.mean is None
    end = found.spread('tank.ratio', 4).summary
    assert end.estimated and end.mean.value == pytest.approx(
        sum(1 / (4 * drawn(sample)) for sample in found.samples) / 8, rel=1e-12
    )


def test_a_yes_or_no_has_the_share_of_the_samples_in_which_it_holds():
    """The tank holds 10 L or more at 4 h when it draws 2.5 L/h or more."""
    found = study(compiled(), paths=('tank.full',), samples=40)
    share = sum(drawn(sample) >= 2.5 for sample in found.samples) / 40
    summary = found.spread('tank.full', 4).summary
    assert summary.estimated and summary.central is False and summary.mean.value == pytest.approx(share)


def test_the_drivers_of_a_value_are_the_rank_correlations_of_the_draws_with_it():
    """The water at 4 h rises with the drawn rate: its correlation is 1. A noise that nothing reads has
    the rank correlation of its draws with the water, and comes after."""
    model = compiled(noisy())
    found = study(model, samples=30)
    water = [sample.values[0][0] for sample in found.samples]
    noise = [drawn(sample, 'tank.noise.draw[0]') for sample in found.samples]
    (first, second) = found.spread('tank.water', 4).drivers
    assert first[:2] == (RATE, 'tank') and first[2] == pytest.approx(1)
    assert second[:2] == ('tank.noise.draw[0]', 'tank')
    assert second[2] == pytest.approx(spearman_without_ties(noise, water), abs=1e-12)


def test_a_sample_alone_is_the_sample_of_the_study():
    """Each sample is the study's configuration in sampled mode with the sample's seed: run alone, with
    every value recorded, that configuration draws what the sample drew and holds its values."""
    model = compiled()
    found = study(model, samples=3, times=(2, 4))
    for sample in found.samples:
        alone = run(model.program, replace(model.configuration, mode=SAMPLED, seed=sample.seed))
        assert drawn(sample) == alone.entries('draw')[0].detail('value')
        values = read(alone, model.program, ['tank.water'], [2, 4])[0].values
        assert values == pytest.approx(sample.values[0], rel=1e-12)
    with pytest.raises(ValueError, match='one path or more'):
        study(model, paths=())
