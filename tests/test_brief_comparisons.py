"""A package compares named runs in its brief, using completed study readings."""

import pytest

from napkin.model import load_scenario
from tests.test_record_publication import SOURCE, package
from tools.publish import briefs
from tools.publish.brief import Comparison, StyleError, brief_of, read_brief

SENSOR_MODEL = SOURCE.replace('    nearby = "Local"', '    nearby = "Local"\n    reference = "Reference"')
PAIRS = """
[[comparison]]
run = "reference"
against = "standard"

[[comparison]]
run = "nearby"
against = "standard"
"""


def example(tmp_path, settings, source=SENSOR_MODEL):
    path = package(tmp_path, source)
    path.with_name('brief.toml').write_text('show = ["level", "forecast"]\n' + settings)
    return load_scenario(path)


def test_featured_pair_leads_then_others_in_declaration_order(tmp_path):
    model = example(tmp_path, 'featured = ["standard", "nearby"]\n' + PAIRS)
    assert brief_of(model).comparisons == (
        Comparison('reference', 'standard'),
        Comparison('nearby', 'standard'),
    )
    text = briefs.render(model)
    assert [line for line in text.splitlines() if line.startswith('## ')] == [
        '## nearby against standard',
        '## reference against standard',
    ]
    assert '| Reading | Unit | standard | nearby |' in text
    assert '| level | 1 | 5 | 7 |' in text
    assert '| level | 1 | 5 | 5 |' in text
    assert 'Not estimated (The field gauge measures only the present.)' in text


def test_unfeatured_pairs_keep_author_order(tmp_path):
    text = briefs.render(example(tmp_path, PAIRS))
    assert [line for line in text.splitlines() if line.startswith('## ')] == [
        '## reference against standard',
        '## nearby against standard',
    ]


def test_without_comparisons_the_featured_run_gets_a_summary(tmp_path):
    text = briefs.render(example(tmp_path, 'featured = ["nearby"]'))
    assert '## nearby\n' in text and '| level | 1 | 7 |' in text


def test_legacy_comparison_notes_still_work_but_authored_pairs_take_precedence(tmp_path):
    source = SENSOR_MODEL.replace('notes:\n', 'notes:\n    comparisons:\n        nearby: standard\n')
    model = example(tmp_path, 'featured = ["standard", "nearby"]', source)
    assert '## nearby against standard' in briefs.render(model)
    model = example(tmp_path, '[[comparison]]\nrun="reference"\nagainst="standard"', source)
    assert '## nearby against standard' not in briefs.render(model)


@pytest.mark.parametrize(
    ('settings', 'problem'),
    [
        ('comparison = "standard"', 'holds tables'),
        ('[[comparison]]\nrun="standard"', 'against'),
        ('[[comparison]]\nrun="standard"\nagainst=7', 'nonempty text'),
        ('[[comparison]]\nrun="standard"\nagainst="standard"', 'different runs'),
        (PAIRS + PAIRS, 'more than once'),
    ],
)
def test_invalid_comparison_tables(settings, problem):
    with pytest.raises(StyleError, match=problem):
        read_brief(settings)


@pytest.mark.parametrize(
    ('settings', 'problem'),
    [
        ('[[comparison]]\nrun="absent"\nagainst="standard"', 'absent is not a run'),
        ('[[comparison]]\nrun="nearby"\nagainst="absent"', 'absent is not a run'),
        ('featured=["nearby","standard"]\n' + PAIRS, 'declared comparison'),
    ],
)
def test_invalid_pairs_fail_before_publication(tmp_path, settings, problem):
    with pytest.raises(StyleError, match=problem):
        briefs.render(example(tmp_path, settings))


def test_briefs_and_readings_share_one_completed_study(tmp_path, monkeypatch):
    from tools import catalogue, publish

    folder = tmp_path / 'scenarios' / 'gauges'
    folder.mkdir(parents=True)
    example(folder, 'featured = ["standard", "nearby"]\n' + PAIRS)
    evaluate = catalogue.completed_study
    calls = []

    def counted(model, **kwargs):
        calls.append(model.model_hash)
        return evaluate(model, **kwargs)

    monkeypatch.setattr(catalogue, 'completed_study', counted)
    ctx = publish.Context(tmp_path, scenario_ids=['gauges'])
    outputs = publish.build(ctx, ['briefs', 'readings'])
    assert len(calls) == 1
    assert '## nearby against standard' in outputs[catalogue.result('gauges', 'brief.md')]
    reading = outputs[catalogue.result('gauges', 'readings.md')]
    assert reading.index('## standard') < reading.index('## nearby') < reading.index('## reference')
