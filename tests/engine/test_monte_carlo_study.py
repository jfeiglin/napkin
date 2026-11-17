"""Monte Carlo studies (napkin/engine/uncertainty.py) on tiny models with closed forms.

Each model's outcome has a closed form in the drawn inputs, so every one of its 8 to 64 samples
must equal its own closed form: the test covers the draw, the resolution, the run, the report and
the summary together, with no statistical tolerance. Latin samples give deterministic bounds on the
summaries of a monotone model. The structural properties are exact.
"""

from __future__ import annotations

import json
import math

import numpy as np
import pytest
from jsonschema import Draft202012Validator

from napkin.engine import SamplingSettings, edits_for, evaluate_study, evaluate_uncertainty
from napkin.engine.report import evaluate_outputs
from napkin.engine.uncertainty import StudyCancelled, check_sample, run_sample, uncertainty_report
from napkin.schema import FOLDER as SCHEMAS
from tests.build import (
    block,
    check,
    compiled,
    document,
    edit,
    entity,
    event,
    flow,
    indent,
    library,
    move,
    once_at,
    output,
    parameter,
    replace,
    stock,
    system,
    template,
    timer,
    uncertain,
    value,
)
from tests.engine import distribution_oracles as oracle
from tests.owned import block_at

SCHEMA = json.loads((SCHEMAS / 'report.schema.json').read_text(encoding='utf-8'))


def study(source, samples=16, seed=1, method='random', edits=None):
    model = compiled(source)
    result = evaluate_uncertainty(
        model, edits_for(model, edits) if edits else None, SamplingSettings(samples, seed, method)
    )
    assert result.admissible, [d for d in result.diagnostics if d.get('severity', 'error') == 'error']
    return model, result


def final(model, completed, name):
    """The value of output `name` at the end of one completed run."""
    (row,) = evaluate_outputs(completed, library(), [completed['trajectory'].horizon])
    return row['values'][model.outputs[name]]


def test_each_sample_of_a_tally_equals_rate_times_end():
    model, result = study(timer())
    sampled = result.samples['a']
    assert len(sampled['runs']) == 16
    closed = [values['s.rate'] * values['s.end'] for values in sampled['values']]
    for completed, expected in zip(sampled['runs'], closed):
        assert final(model, completed, 'served') == pytest.approx(expected, rel=1e-9)
    report = uncertainty_report(result)
    assert not list(Draft202012Validator(SCHEMA).iter_errors(report))
    summary = report['uncertainty']['runs']['a']['outcomes'][model.outputs['served']]['points']['final']
    # The summary is the statistics of the closed forms, and the central run is the run at the
    # central values that the model gives.
    assert summary['mean'] == pytest.approx(np.mean(closed), rel=1e-9)
    assert summary['sd'] == pytest.approx(np.std(closed, ddof=1), rel=1e-9)
    assert summary['p50'] == pytest.approx(np.percentile(closed, 50), rel=1e-9)
    assert (summary['min'], summary['max']) == pytest.approx((min(closed), max(closed)), rel=1e-9)
    central = model.run_values('a')
    assert summary['central'] == pytest.approx(central['s.rate'] * central['s.end'], rel=1e-9)
    assert report['runs']['a']['reporting_points']['final']['values'][
        model.outputs['served']
    ] == pytest.approx(summary['central'], rel=1e-12)


def test_each_sample_of_a_decay_equals_its_exponential():
    source = system(
        uncertain('k', 'per_h', 0.001, 1, 'loguniform(0.01 per_h, 0.1 per_h)'),
        uncertain('size', 'people', 1, 1000, 'uniform(100 people, 200 people)'),
        stock('alive', 'size', size=1000),
        stock('dead', 0, kind='tally', size=1000),
        flow('death', move('alive', 'dead'), 'k * alive'),
        horizon=10,
        outputs=(output('alive', 's.alive', 'people', 'level'),),
    )
    model, result = study(source, samples=8)
    sampled = result.samples['a']
    for values, completed in zip(sampled['values'], sampled['runs']):
        expected = values['s.size'] * math.exp(-10 * values['s.k'])
        assert final(model, completed, 'alive') == pytest.approx(expected, rel=1e-7)


def test_a_bool_and_a_named_value_gate_and_pick_a_rate():
    """A bernoulli draw switches a flow on, and a categorical draw picks its rate: served(24 h) is
    24 h times 2 or 1 people/h when the flow is on, else 0."""
    source = system(
        value('input', 'backup', 'bernoulli(0.4)', 'bool', doc='Backup'),
        value('input', 'curve', 'categorical(slow=0.5, fast=0.5)', '"slow" | "fast"', doc='Curve'),
        stock('served', 0, kind='tally', size=100),
        flow(
            'serve',
            move(None, 'served'),
            '(2 people/h if curve is "fast" else 1 people/h) if backup else 0 people/h',
        ),
        horizon=24,
        outputs=(output('served', 's.served', 'people'),),
    )
    model, result = study(source, samples=32, seed=8)
    sampled = result.samples['a']
    seen = set()
    for values, completed in zip(sampled['values'], sampled['runs']):
        rate = (2 if values['s.curve'] == 'fast' else 1) if values['s.backup'] else 0
        seen.add((values['s.backup'], values['s.curve']))
        assert final(model, completed, 'served') == pytest.approx(24 * rate, rel=1e-9, abs=1e-9)
    assert len(seen) == 4  # 32 samples reach every pair of values


def test_a_distribution_that_reads_another_input_reads_its_draw():
    """d2 ~ uniform(d1, d1 + 10 h) reads the draw of d1 in the same sample, so the event at d2 never
    comes before the event at d1."""
    source = system(
        uncertain('d1', 'h', 1, 5, 'uniform(1 h, 5 h)'),
        uncertain('d2', 'h', 1, 15, 'uniform(d1, d1 + 10 h)'),
        event('first', 't >= d1'),
        event('second', 't >= d2'),
        horizon=24,
    )
    model, result = study(source, samples=16, seed=3)
    # The central run takes the median of d1, and d2 at the median of d1.
    central = model.run_values('a')
    assert (central['s.d1'], central['s.d2']) == (3.0, 8.0)
    sampled = result.samples['a']
    for values, completed in zip(sampled['values'], sampled['runs']):
        assert values['s.d1'] <= values['s.d2'] <= values['s.d1'] + 10
        times = {e['event']: e['t'] for e in completed['trajectory'].trace}
        assert times['s.first.done'] == pytest.approx(values['s.d1'], rel=1e-12)
        assert times['s.second.done'] == pytest.approx(values['s.d2'], rel=1e-12)


def test_latin_samples_bound_the_mean_and_the_median_of_a_monotone_outcome():
    """With one sample in each of 64 strata, the outcome end (the rate is 1 people/h) is a monotone
    image of the draw: its mean is within 1/64 of the width of the support of the true mean, and the
    median of the samples lies within one stratum of the true median."""
    model, result = study(timer(rate='1 people/h'), samples=64, method='latin')
    values = np.array([final(model, completed, 'served') for completed in result.samples['a']['runs']])
    args = {'min': 2, 'mode': 6, 'max': 20}
    mean, _ = oracle.moments('pert', args)
    assert abs(values.mean() - float(mean)) <= (20 - 2) / 64
    lower, _ = oracle.tails('pert', args, np.median(values))
    assert 31 / 64 - 1e-12 <= lower <= 33 / 64 + 1e-12
    strata = sorted(int(64 * float(oracle.tails('pert', args, v)[0])) for v in values)
    assert strata == list(range(64))


def test_a_sobol_study_has_the_mean_of_the_closed_form_with_the_error_of_its_blocks():
    """The tally is rate times end, with the rate uniform from 1 to 3 and the end PERT from 2 to
    20 around 6: its mean is the product of the two means. A study of 8 blocks of 64 Sobol' points
    has that mean within four of its standard errors; its standard error is that of the means of
    its 8 blocks, and is less than a fifth of the standard error of a random study of as many
    samples. The settings of the report say the blocks."""
    model, result = study(timer(), samples=8 * 64, seed=3, method='sobol')
    values = np.array([final(model, completed, 'served') for completed in result.samples['a']['runs']])
    drawn = result.samples['a']['values']
    assert values == pytest.approx([point['s.rate'] * point['s.end'] for point in drawn], rel=1e-9)
    report = uncertainty_report(result)
    assert not list(Draft202012Validator(SCHEMA).iter_errors(report))
    assert report['uncertainty']['settings'] == {
        'samples': 512,
        'seed': 3,
        'method': 'sobol',
        'replicates': 8,
    }
    summary = report['uncertainty']['runs']['a']['outcomes'][model.outputs['served']]['points']['final']
    means = [block.mean() for block in np.split(values, 8)]
    assert summary['mean'] == pytest.approx(values.mean(), rel=1e-12)
    assert summary['sem'] == pytest.approx(np.std(means, ddof=1) / math.sqrt(8), rel=1e-9)
    mean_of_end, _ = oracle.moments('pert', {'min': 2, 'mode': 6, 'max': 20})
    assert abs(summary['mean'] - 2.0 * float(mean_of_end)) <= 4 * summary['sem']
    _, random = study(timer(), samples=8 * 64, seed=3)
    by_chance = uncertainty_report(random)['uncertainty']['runs']['a']['outcomes'][model.outputs['served']]
    assert summary['sem'] < by_chance['points']['final']['sem'] / 5
    # Each block has one sample in each of 64 strata of each input: here, of the rate.
    for rates in np.split(np.array([point['s.rate'] for point in drawn]), 8):
        assert sorted(np.floor((rates - 1.0) / 2.0 * 64).astype(int)) == list(range(64))


def test_an_outcome_that_reads_no_uncertain_input_is_the_same_in_every_sample():
    model, result = study(timer())
    report = uncertainty_report(result)
    outcomes = report['uncertainty']['runs']['a']['outcomes']
    assert outcomes[model.outputs['served']]['uncertain_inputs'] == ['s.end', 's.rate']
    elapsed = outcomes[model.outputs['elapsed_time']]
    assert elapsed['uncertain_inputs'] == []
    points = elapsed['points']['final']
    assert points['min'] == points['max'] == points['central'] == 24


def test_a_central_run_at_the_old_point_values_is_the_point_run_bit_for_bit():
    """uniform(1, 3) and a symmetric triangular(2, 6, 10) have the medians 2 and 6: the central run of
    the uncertain model is the run of the point model, bit for bit."""
    point = compiled(timer(rate='2 people/h', end='6 h'))
    model = compiled(timer(end='triangular(2 h, 6 h, 10 h)'))
    assert model.run_values('a') == point.run_values('a')
    a, b = (evaluate_study(m).runs['a']['trajectory'] for m in (point, model))
    assert a.trace == b.trace
    assert all(a.env_at(t) == b.env_at(t) for t in (0, 3, 6, 6.5, 24))


def test_a_seed_gives_the_same_study_and_sample_k_does_not_depend_on_n():
    _, first = study(timer(), samples=16, seed=21)
    _, again = study(timer(), samples=16, seed=21)
    assert json.dumps(uncertainty_report(first), sort_keys=True) == json.dumps(
        uncertainty_report(again), sort_keys=True
    )
    _, few = study(timer(), samples=4, seed=21)
    assert few.samples['a']['values'] == first.samples['a']['values'][:4]


def test_an_unrelated_uncertain_input_leaves_the_other_draws_alone():
    _, alone = study(timer(), seed=5)
    other = uncertain('other', 'h', 1, 10, 'uniform(1 h, 10 h)')
    # The timer's own rate and stop time, then the other input.
    _, more = study(timer(*timer.__defaults__, other), seed=5)
    for a, b in zip(alone.samples['a']['values'], more.samples['a']['values']):
        assert (a['s.rate'], a['s.end']) == (b['s.rate'], b['s.end'])


def test_with_sobol_sampling_an_input_keeps_its_numbers_when_another_becomes_certain():
    """Each input has the dimension of its place among the inputs of the model. With the stop
    time set to one value by an edit, the rate alone is uncertain, and it has the draws that it
    has in the study with the two."""
    _, both = study(timer(), samples=32, seed=5, method='sobol')
    _, alone = study(timer(), samples=32, seed=5, method='sobol', edits={'set': {'s.end': 6}})
    assert [point['s.end'] for point in alone.samples['a']['values']] == [6] * 32
    assert [point['s.rate'] for point in alone.samples['a']['values']] == [
        point['s.rate'] for point in both.samples['a']['values']
    ]


def test_each_copy_draws_its_own_value_and_reads_the_one_value_of_a_linked_input():
    lane = template(
        'Lane',
        uncertain('cars', 'people', 0, 20, 'uniform(hub.level, hub.level + 5 people)'),
        doc='A lane.',
    )
    hub = entity(
        'hub',
        uncertain('level', 'people', 0, 10, 'uniform(1 people, 5 people)'),
        doc='A hub.',
    )
    source = document('Copies', lane, entity('lanes', template='Lane', records=None, copies=3), hub)
    _, result = study(source, samples=8, seed=2)
    for values in result.samples['a']['values']:
        cars = [values[f'lanes_{k}.cars'] for k in (1, 2, 3)]
        assert len(set(cars)) == 3
        assert all(values['hub.level'] <= c <= values['hub.level'] + 5 for c in cars)


def test_independent_shares_that_break_a_sum_check_reject_the_study_and_name_the_sample():
    """Two shares drawn alone rarely add up to 1: the central run holds the check (0.375 + 0.625),
    the samples do not, and the study is rejected with no sample kept."""
    source = system(
        uncertain('w1', 'fraction', 0, 1, 'uniform(0.25, 0.5)'),
        uncertain('w2', 'fraction', 0, 1, 'uniform(0.5, 0.75)'),
        horizon=2,
        checks=(check('abs(s.w1 + s.w2 - 1) <= 1e-12', 'The shares add up to 1.'),),
    )
    model = compiled(source)
    assert evaluate_study(model).admissible
    result = evaluate_uncertainty(model, None, SamplingSettings(8, seed=4))
    assert not result.admissible and result.samples == {}
    failed = [d for d in result.diagnostics if 'sample' in d]
    assert failed and {d['run'] for d in failed} == {'a'}
    assert all(d['seed'] == 4 and set(d['drawn']) == {'s.w1', 's.w2'} for d in failed)

    # Samples checked elsewhere give the same diagnostics, and none of them runs.
    def no_run(tasks):
        raise AssertionError('A rejected study runs no sample')

    remote = evaluate_uncertainty(
        model, None, SamplingSettings(8, seed=4), run_samples=no_run, check_samples=check_elsewhere(model)
    )
    assert json.dumps(remote.diagnostics, sort_keys=True) == json.dumps(result.diagnostics, sort_keys=True)
    report = uncertainty_report(result)
    assert report['runs'] == {} and report['uncertainty']['runs'] == {}
    assert not list(Draft202012Validator(SCHEMA).iter_errors(report))


def test_a_sample_whose_run_fails_rejects_the_study():
    """A move of more than the stock holds stops the run: the central run moves exactly 10 people,
    and a sample that draws more fails, so the study keeps no sample."""
    source = system(
        uncertain('amount', 'people', 0, 20, 'uniform(5 people, 15 people)'),
        stock('source', 10),
        stock('out'),
        once_at('takes', '1 h', 'move amount from source to out'),
        horizon=3,
    )
    model = compiled(source)
    assert evaluate_study(model).admissible
    result = evaluate_uncertainty(model, None, SamplingSettings(8, seed=6))
    assert not result.admissible and result.samples == {}
    assert any(d.get('sample') is not None and d['drawn']['s.amount'] > 10 for d in result.diagnostics)


def test_an_edit_gives_a_distribution_and_a_point_value_makes_an_input_certain():
    _, result = study(timer(), edits={'set': {'s.end': 'uniform(4 h, 8 h)', 's.rate': 2}})
    for values in result.samples['a']['values']:
        assert values['s.rate'] == 2 and 4 <= values['s.end'] <= 8
    # The central run of the study takes the median of the edit's distribution.
    assert result.study.runs['a']['resolved'].parameter_values['s.end'] == 6.0


def test_a_study_of_certain_values_has_no_samples():
    _, result = study(timer(rate='2 people/h', end='6 h'))
    assert result.samples == {}
    report = uncertainty_report(result)
    assert report['uncertainty']['runs'] == {} and report['runs']


def test_a_fixed_value_with_a_distribution_takes_a_draw_in_each_sample():
    """A fixed value cannot change by an edit, and its own distribution still gives each sample its
    draw: served(24 h) = rate * end with a fixed rate."""
    rate = 'uniform(1 people/h, 3 people/h)'
    source = timer(rate)
    fixed = indent(parameter('rate', rate, 'people/h', doc='Rate'))
    source = edit(source, replace(block_at(source, 's/rate').rstrip('\n'), fixed))
    model, result = study(source, samples=8, seed=13)
    rates = {values['s.rate'] for values in result.samples['a']['values']}
    assert len(rates) == 8 and all(1 <= rate <= 3 for rate in rates)
    for values, completed in zip(result.samples['a']['values'], result.samples['a']['runs']):
        assert final(model, completed, 'served') == pytest.approx(
            values['s.rate'] * values['s.end'], rel=1e-9
        )


def check_elsewhere(model):
    """A caller that checks the samples as another process does: their diagnostics through JSON."""
    return lambda tasks: [thaw_rows(check_sample(model, run, point)) for run, _, point in tasks]


def test_samples_that_run_elsewhere_give_the_same_report():
    """A caller can check and run the samples itself, as the spread does in other processes
    (`napkin/spread.py`): each sample, with its luck (the draws of the outcomes of its
    events), gives its diagnostics, its outcome rows and the counts of its outcomes by chance only, and
    the report is the sequential one, bit for bit."""
    model = compiled(timer())
    settings = SamplingSettings(8, seed=17)
    times = [0, 3, 6, 12, 24]
    reference = evaluate_uncertainty(model, None, settings, times=times)

    def elsewhere(tasks):
        out = []
        for run, _, point, at, luck in tasks:
            outcome = run_sample(model, run, point, None, at, luck)
            out.append(
                {
                    'completed': None,
                    'rows': thaw_rows(outcome['rows']),
                    'failures': outcome['failures'],
                    'events': thaw_rows(outcome['events']),
                }
            )
        return out

    remote = evaluate_uncertainty(
        model, None, settings, times=times, run_samples=elsewhere, check_samples=check_elsewhere(model)
    )
    assert remote.samples['a']['runs'] == [None] * 8
    a, b = (json.dumps(uncertainty_report(r, times), sort_keys=True) for r in (reference, remote))
    assert a == b


def thaw_rows(rows):
    """The rows of a sample as another process returns them: through JSON."""
    return json.loads(json.dumps(rows))


def test_the_series_of_an_outcome_is_the_percentiles_of_its_closed_forms_at_each_time():
    """served(t) = rate * min(t, end) for each sample; the series at each asked time holds the type-7
    percentiles of those closed forms."""
    model = compiled(timer())
    times = [1, 4, 9, 16, 24]
    result = evaluate_uncertainty(model, None, SamplingSettings(16, seed=23), times=times)
    report = uncertainty_report(result, times)
    series = report['uncertainty']['runs']['a']['outcomes'][model.outputs['served']]['series']
    assert [entry['t'] for entry in series] == times
    for entry in series:
        closed = [v['s.rate'] * min(entry['t'], v['s.end']) for v in result.samples['a']['values']]
        for p in (5, 25, 50, 75, 95):
            assert entry[f'p{p}'] == pytest.approx(np.percentile(closed, p), rel=1e-9, abs=1e-9)
    assert not list(Draft202012Validator(SCHEMA).iter_errors(report))


def test_a_caller_can_stop_a_study_while_it_checks_or_runs_its_samples():
    def stop(tasks):
        raise StudyCancelled

    for hook in ('check_samples', 'run_samples'):
        with pytest.raises(StudyCancelled):
            evaluate_uncertainty(compiled(timer()), None, SamplingSettings(4), **{hook: stop})


def test_a_run_whose_only_chance_is_a_draw_at_a_firing_is_sampled():
    """An event that draws a distribution when it fires makes the run vary by sample, with no uncertain
    input: the study samples it, and the samples differ."""
    source = document(
        'Draws fixture',
        entity(
            'clock',
            stock('next', 1, 'h', minimum=None, maximum=20, size=None, kind='state'),
            stock('total', 0, 'people', size=1000),
            block(
                'event tick when t >= next:  @fixture',
                '"A tick."',
                'next += 1 h',
                'total += uniform(1 people, 3 people)',
            ),
        ),
        output('total', 'clock.total', 'people'),
        horizon=6,
    )
    model, result = study(source, samples=8, seed=3)
    assert len(result.samples['a']['runs']) == 8
    totals = {round(final(model, completed, 'total'), 9) for completed in result.samples['a']['runs']}
    assert len(totals) > 1
    for completed in result.samples['a']['runs']:
        # Each firing adds a draw from (1, 3): the total lies between once and three times their number.
        firings = sum(
            1 for e in completed['trajectory'].trace if e['rule'] == 'clock.tick' and e.get('outcome')
        )
        assert firings >= 5
        assert firings <= final(model, completed, 'total') <= 3 * firings
