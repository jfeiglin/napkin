"""Comparison receipts use joint draws and can be replayed through scoped publication."""

import json
from dataclasses import replace
from types import SimpleNamespace

import pytest

from napkin.engine.sampling import sample_seed
from napkin.engine.uncertainty import Sample
from tests.test_record_publication import SOURCE
from tools.publish import __main__ as cli
from tools.publish import paired


def author(folder):
    folder.mkdir(parents=True)
    source = SOURCE.replace(
        'level = formula(first if t < 1 h else second)',
        'input common = uniform(1, 20).draw() @early\n'
        'empty = formula(0) @late\n'
        'level = formula(common + (first if t < 1 h else second))',
    )
    (folder / 'model.scn').write_text(source)
    settings = folder / 'brief.toml'
    settings.write_text("""show = ["level", "empty"]
[[comparison]]
run = "nearby"
against = "standard"

[[spread]]
id = "level"
runs = ["nearby", "standard"]
outputs = ["level", "empty", "forecast"]
samples = 4
seed = 43
""")
    (folder / 'spreads').mkdir()
    (folder / 'spreads' / 'level.json').write_text('{"set":{}}')
    return settings


def test_receipt_replays_paired_draws_and_reports_finite_percentages(tmp_path, monkeypatch):
    monkeypatch.setattr(cli, 'ROOT', tmp_path)
    folder = tmp_path / 'scenarios' / 'gauges'
    settings = author(folder)
    receipt = folder / 'results' / paired.FILENAME
    flags = ['--scenario', 'gauges', '--jobs', '1', '--only', 'briefs']
    assert cli.main(['--write', *flags]) == 0
    assert not receipt.exists()
    assert cli.main(['--write', '--sample-spreads', *flags]) == 0
    first = receipt.read_bytes()
    record = json.loads(first)
    assert record['scenario'] == 'gauges'
    (spread,) = record['spreads']
    assert (spread['seed'], spread['samples_per_run']) == (43, 4)
    assert spread['unestimated_outputs'] == {'forecast': 'The field gauge measures only the present.'}
    (pair,) = spread['comparisons']
    assert (pair['run'], pair['against'], pair['paired_draws']) == ('nearby', 'standard', 4)
    level, empty = pair['readings']
    assert level['time_hours'] == 2 and level['unit'] == '1'
    assert level['difference'] == {'mean': 2, 'p05': 2, 'p95': 2}
    assert level['run']['p05'] < level['run']['p95']
    assert level['run']['p95'] - level['against']['p05'] > 2
    assert level['percent_change']['p95'] > level['percent_change']['p05'] > 0
    assert empty['percent_change'] is None
    assert empty['difference'] == {'mean': 0, 'p05': 0, 'p95': 0}
    assert '| empty | 1 | 0 | 0 | 0 | — |' in (folder / 'results' / 'brief.md').read_text()
    assert cli.main(['--check', '--sample-spreads', *flags]) == 0
    assert cli.main(['--write', '--sample-spreads', *flags]) == 0
    assert receipt.read_bytes() == first

    settings.write_text(settings.read_text().replace('seed = 43', 'seed = 44'))
    assert cli.main(['--check', *flags]) == 0
    assert cli.main(['--check', '--sample-spreads', *flags]) == 1
    assert receipt.read_bytes() == first
    settings.write_text('show = ["level", "empty"]\n')
    assert cli.main(['--write', '--sample-spreads', *flags]) == 0
    assert not receipt.exists()


def test_pairing_joins_on_seed_when_results_arrive_in_different_orders():
    spec = SimpleNamespace(samples=2, seed=3)
    a, b = [sample_seed(3, i) for i in range(2)]

    def study(rows):
        samples = [Sample(k, ((v,),), (), 0, None) for k, v in rows]
        return SimpleNamespace(
            refused=None,
            samples=samples,
            paths=('level',),
            times=(2,),
            spread=lambda *_: SimpleNamespace(unit='L'),
        )

    baseline = study([(a, 10), (b, 100)])
    compared = study([(b, 102), (a, 12)])
    studies = {
        name: (result, paired.keyed_samples(result, spec, name))
        for name, result in [('base', baseline), ('run', compared)]
    }
    pair = paired.comparison(SimpleNamespace(against='base', run='run'), studies)
    (row,) = pair['readings']
    assert row['unit'] == 'L' and row['difference'] == {'mean': 2, 'p05': 2, 'p95': 2}


def test_incomplete_refused_and_duplicate_studies_cannot_produce_receipts():
    spec = SimpleNamespace(samples=2, seed=4)
    first = Sample(sample_seed(4, 0), ((0,),), (), 0, None)
    for result, diagnostic in [
        (SimpleNamespace(refused='central run stopped'), 'central run stopped'),
        (SimpleNamespace(refused=None, samples=[first]), 'incomplete or unexpected'),
        (SimpleNamespace(refused=None, samples=[first, first]), 'duplicate sample seed'),
        (
            SimpleNamespace(
                refused=None,
                paths=('x', 'y'),
                times=(0,),
                samples=[first, replace(first, seed=sample_seed(4, 1))],
            ),
            'incomplete outcome readings',
        ),
        (SimpleNamespace(refused=None, samples=[replace(first, stopped='paused')]), 'paused'),
    ]:
        with pytest.raises(ValueError, match=diagnostic):
            paired.keyed_samples(result, spec, 'gauge')
