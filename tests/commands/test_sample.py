"""`napkin sample`: the spread of named values over samples of one run, through the engine's Monte Carlo
study (`napkin.spread`).

The tank fills from outside at a rate drawn from uniform(1 L/h, 3 L/h) for 10 h, so each sample fills
10 h times its own draw, and the central run, which draws the median 2 L/h, fills 20 L. Each
expectation is computed from those closed forms and from the samples that the document lists: the
type-7 quantiles of numpy, the mean, the share above a value, and its Clopper-Pearson interval from
the beta distribution of scipy.
"""

from __future__ import annotations

import json
from decimal import Decimal

import numpy as np
import pytest
from scipy.stats import beta

from napkin.commands.sample import shown_tails
from tests.commands.call import UNITS, napkin, package

FILL = """\
scenario "Fill"
    horizon 10 h

tank:
    input rate: L/h = uniform(1 L/h, 3 L/h).draw() in [0 L/h, 10 L/h]
        "Rate of the fill"
    filled: L = 0 L in [0 L,]
        "Water filled"
    flow fill: SOURCE -> this.filled
        request = formula(this.rate)
"""


def sampled(capsys, model, *argv):
    found = napkin(capsys, 'sample', model, '--json', '--jobs', '1', *argv)
    assert found.code == 0, found.err
    return found.doc


def test_each_sample_fills_ten_hours_of_its_draw_and_the_central_run_the_median(tmp_path, capsys):
    model = package(tmp_path / 'fill', FILL, UNITS)
    doc = sampled(capsys, model, '--value', 'tank.filled', '--samples', '200')
    filled = doc['values']['tank.filled']
    assert (filled['unit'], filled['label'], filled['central']) == ('L', 'Water filled', pytest.approx(20))
    values = np.array([sample['values']['tank.filled'] for sample in doc['draws']])
    rates = np.array([sample['draws'][0]['value'] for sample in doc['draws']])
    assert len(values) == 200 and np.all((rates >= 1) & (rates <= 3))
    assert values == pytest.approx(10 * rates, rel=1e-9)
    assert filled['mean']['value'] == pytest.approx(values.mean(), rel=1e-12)
    for p in (5, 25, 50, 75, 95):
        assert filled['percentiles'][f'p{p}'] == pytest.approx(np.percentile(values, p), rel=1e-12)
    # The draw that moves it is the rate's, and the fill follows it exactly: a rank correlation of 1.
    (driver,) = filled['drivers']
    assert (driver['owner'], driver['rho']) == ('tank', pytest.approx(1))
    assert filled['tails'] == {}


def test_the_text_gives_the_central_value_the_mean_and_the_middle_of_the_samples(tmp_path, capsys):
    model = package(tmp_path / 'fill', FILL, UNITS)
    doc = sampled(capsys, model, '--value', 'tank.filled', '--samples', '40', '--seed', '3')
    found = napkin(
        capsys, 'sample', model, '--jobs', '1', '--value', 'tank.filled', '--samples', '40', '--seed', '3'
    )
    assert found.code == 0, found.err
    lines = found.out.splitlines()
    assert lines[0] == 'Fill: the default run, 40 samples from the seed 3, at 10 h'
    assert lines[1].split() == ['unit', 'central', 'mean', 'p5', 'p25', 'p50', 'p75', 'p95']
    filled = doc['values']['tank.filled']
    expected = [filled['mean']['value'], *(filled['percentiles'][f'p{p}'] for p in (5, 25, 50, 75, 95))]
    assert lines[2].split() == ['tank.filled', 'L', '20', *(f'{value:.6g}' for value in expected)]
    assert lines[3].startswith('tank.filled: moved most by ')


def test_the_far_tails_show_once_ten_samples_lie_beyond_them(tmp_path, capsys):
    """p99 from 1000 samples, p99.5 from 2000: N (100 - p) / 100 >= 10."""
    assert shown_tails(999) == [] and [float(p) for p in shown_tails(1000)] == [99]
    assert [float(p) for p in shown_tails(2000)] == [99, 99.5]
    model = package(tmp_path / 'fill', FILL, UNITS)
    doc = sampled(capsys, model, '--value', 'tank.filled', '--samples', '1000')
    values = [sample['values']['tank.filled'] for sample in doc['draws']]
    assert doc['values']['tank.filled']['tails'] == {
        'p99': pytest.approx(np.percentile(values, 99), rel=1e-12)
    }


def test_an_exceedance_is_the_share_of_the_samples_above_the_value(tmp_path, capsys):
    """P(filled > 25 L) = k / n, near 1/4 for a uniform fill from 10 L to 30 L, with the Clopper-Pearson
    interval of k in n."""
    model = package(tmp_path / 'fill', FILL, UNITS)
    doc = sampled(capsys, model, '--samples', '200', '--exceed', 'tank.filled=25')
    values = np.array([sample['values']['tank.filled'] for sample in doc['draws']])
    k, n = int(np.count_nonzero(values > 25)), 200
    (item,) = doc['exceed']
    assert (item['path'], item['threshold'], item['above'], item['samples']) == ('tank.filled', 25, k, n)
    assert item['share'] == {
        'value': k / n,
        'low': pytest.approx(beta.ppf(0.025, k, n - k + 1)),
        'high': pytest.approx(beta.ppf(0.975, k + 1, n - k)),
    }
    text = napkin(capsys, 'sample', model, '--jobs', '1', '--samples', '200', '--exceed', 'tank.filled=25')
    assert f'P(tank.filled > 25) = {k}/{n} = {k / n:.6g} (95% from ' in text.out


def test_exceedance_uses_the_exact_threshold_it_prints_as_a_json_number(tmp_path, capsys):
    model = package(tmp_path / 'fixed', 'scenario "Fixed"\n    horizon 1 h\nbox:\n    n = 1\n', UNITS)
    below = '0.99999999999999999999'
    found = napkin(
        capsys,
        'sample',
        model,
        '--json',
        '--jobs',
        '1',
        '--samples',
        '3',
        '--exceed',
        f'box.n={below}',
        '--exceed',
        'box.n=1',
    )
    assert found.code == 0, found.err
    first, second = json.loads(found.out, parse_float=Decimal)['exceed']
    assert (first['threshold'], first['above'], first['samples']) == (Decimal(below), 3, 3)
    assert (second['threshold'], second['above']) == (1, 0)


def test_the_same_seed_gives_the_same_samples_and_another_seed_others(tmp_path, capsys):
    model = package(tmp_path / 'fill', FILL, UNITS)
    first, again = (sampled(capsys, model, '--value', 'tank.filled', '--samples', '20') for _ in range(2))
    other = sampled(capsys, model, '--value', 'tank.filled', '--samples', '20', '--seed', '1')
    assert first['draws'] == again['draws']
    assert [sample['seed'] for sample in other['draws']] != [sample['seed'] for sample in first['draws']]


def test_samples_in_two_processes_agree_with_samples_in_one(tmp_path, capsys):
    """Change 11: a sample in another process agrees within the stated tolerances."""
    model = package(tmp_path / 'fill', FILL, UNITS)
    one = sampled(capsys, model, '--value', 'tank.filled', '--samples', '8')
    two = napkin(
        capsys, 'sample', model, '--json', '--jobs', '2', '--value', 'tank.filled', '--samples', '8'
    ).doc
    assert [sample['seed'] for sample in two['draws']] == [sample['seed'] for sample in one['draws']]
    assert [sample['values']['tank.filled'] for sample in two['draws']] == pytest.approx(
        [sample['values']['tank.filled'] for sample in one['draws']], rel=1e-9
    )


# The fill, with the rate drawn from a distribution that is an input of its own (D2), which an edit
# document can replace.
SPREAD = FILL.replace(
    '    input rate: L/h = uniform(1 L/h, 3 L/h).draw() in [0 L/h, 10 L/h]\n',
    '    input spread = uniform(1 L/h, 3 L/h)\n        "Spread of the rate"\n'
    '    rate: L/h = this.spread.draw() in [0 L/h, 10 L/h]\n',
)


def test_an_edit_document_gives_a_distribution_valued_input_another_distribution(tmp_path, capsys):
    """uniform(2 L/h, 4 L/h): a median of 3 L/h, 30 L in 10 h, and each sample 10 h times its draw."""
    model = package(tmp_path / 'fill', SPREAD, UNITS)
    edits = tmp_path / 'edits.json'
    edits.write_text(json.dumps({'set': {'tank.spread': 'uniform(2 L/h, 4 L/h)'}}), encoding='utf-8')
    doc = sampled(capsys, model, '--edits', edits, '--value', 'tank.filled', '--samples', '30')
    assert doc['values']['tank.filled']['central'] == pytest.approx(30)
    rates = [sample['draws'][0]['value'] for sample in doc['draws']]
    assert all(2 <= rate <= 4 for rate in rates)
    assert [sample['values']['tank.filled'] for sample in doc['draws']] == pytest.approx(
        [10 * r for r in rates]
    )
    assert sampled(capsys, model, '--value', 'tank.filled', '--samples', '5')['values']['tank.filled'][
        'central'
    ] == pytest.approx(20)


def test_a_run_that_draws_nothing_has_no_spread(tmp_path, capsys):
    model = package(tmp_path / 'fixed', FILL.replace('uniform(1 L/h, 3 L/h).draw()', '2 L/h'), UNITS)
    found = napkin(capsys, 'sample', model, '--jobs', '1', '--samples', '5')
    assert found.code == 0, found.err
    assert (
        found.out.splitlines()[-1]
        == 'Its samples draw nothing: each sample is its central run, so it has no spread.'
    )
    assert napkin(capsys, 'sample', model, '--json', '--jobs', '1', '--samples', '5').doc['drawn'] is False


# A move of a drawn amount from 8 L: a sample that draws more than 8 L fails at 1 h.
MOVES = """\
scenario "Moves"
    horizon 4 h

tank:
    input amount: L = uniform(5 L, 10 L).draw() in [0 L, 20 L]
    water: L = 8 L in [0 L,]
    out: L = 0 L in [0 L,]
    take = event():
        after 1 h:
            move this.amount from this.water to this.out

tank.take.start()
"""


def test_a_sample_that_stops_refuses_the_study(tmp_path, capsys):
    """The median, 7.5 L, moves; a draw above 8 L cannot. No estimate leaves a sample out."""
    model = package(tmp_path / 'moves', MOVES, UNITS)
    found = napkin(capsys, 'sample', model, '--jobs', '1', '--samples', '20')
    assert found.code == 1 and found.out == ''
    assert found.err.rstrip().endswith('[sample]') and 'stops: the run failed at 1 h' in found.err


@pytest.mark.parametrize(
    'argv, message',
    [
        (('--value', 'tank.fild'), 'no named value of the model; did you mean tank.filled'),
        (('--at', '11h'), 'the run goes from 0 h to 10 h'),
        (('--exceed', 'tank.filled'), '--exceed takes PATH=VALUE'),
        (('--exceed', 'tank.filled=much'), 'give a number in the unit of tank.filled'),
        (('--run', 'fast'), 'it has no named run'),
        (('--samples', '0'), 'give a whole number of 1 or more'),
    ],
)
def test_a_command_line_that_names_nothing_of_the_model_is_a_usage_error(tmp_path, capsys, argv, message):
    model = package(tmp_path / 'fill', FILL, UNITS)
    found = napkin(capsys, 'sample', model, '--jobs', '1', *argv)
    assert found.code == 2
    assert message in found.err
