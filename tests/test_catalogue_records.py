"""The catalogue's shared readers use compiled models, named records and declared brief metadata."""

from decimal import Decimal

import pytest

from napkin.engine import read
from napkin.model import LanguageError, compile_text
from tests import helpers
from tools import catalogue, check, publish
from tools.publish import brief

SOURCE = """\
scenario "Rain gauges"
    horizon 2 h

Gauge:
    input rate = 1 in [0, 3] @observed

east: Gauge
west: Gauge
total = formula(east.rate + west.rate)

options "Gauges":
    "Low":
        Gauge.instances.rate = 1 @observed
    "High":
        east.rate = 3 @observed

runs:
    low = "Low"
    high = "High"

notes:
    comparisons:
        low: high
    not_estimated:
        future:
            reason: "The gauges observe the current period."

record observed: assumption "The rates used in this test."
"""


def write_model(root, sid, text=SOURCE):
    folder = root / 'scenarios' / sid
    folder.mkdir(parents=True)
    entry = folder / 'model.scn'
    entry.write_text(text)
    return entry


def test_selected_runs_edits_and_completed_records(tmp_path, monkeypatch):
    sid = 'gauge_record_test'
    path = write_model(tmp_path, sid)
    write_model(tmp_path, 'SC98', 'deliberately invalid')
    monkeypatch.setattr(helpers, 'ROOT', tmp_path)
    model = helpers.catalogue_model(sid)
    subset = helpers.catalogue_study(sid, runs=['low'])
    assert list(subset) == ['low']
    records = helpers.catalogue_default(sid)
    assert list(records) == ['low', 'high']
    assert read(records['high'], model.program, ['total'], [2])[0].values == (4,)
    edited = helpers.catalogue_study(sid, {'set': {'east.rate': 2}}, runs=['low'])
    assert read(edited['low'], model.program, ['total'], [2])[0].values == (3,)
    with pytest.raises(LanguageError):
        helpers.catalogue_study(sid, {'set': {'east.rate': Decimal('3.00000000000000001')}})
    monkeypatch.setattr(helpers, 'SCENARIO_IDS', (sid,))
    saved = path.parent / 'edits' / 'outside.json'
    saved.parent.mkdir()
    saved.write_text('{"scenario":"gauge_record_test","set":{"east.rate":3.00000000000000001}}')
    assert helpers.example_edit_sets()[saved.relative_to(tmp_path).as_posix()] == (
        sid,
        {'set': {'east.rate': Decimal('3.00000000000000001')}},
    )
    ctx = publish.Context(tmp_path, scenario_ids=[sid])
    assert list(ctx.studies) == [sid]
    assert ctx.studies[sid] == records
    assert publish.Context(tmp_path, studies={sid: (model, records)}).models == {sid: model}


def test_publisher_workers_keep_named_records_and_catalogue_order(tmp_path):
    for sid in ('SC98', 'SC97'):
        write_model(tmp_path, sid)
    serial = publish.Context(tmp_path)
    parallel = publish.Context(tmp_path, jobs=2)
    assert parallel.studies == serial.studies
    assert list(parallel.studies) == ['SC97', 'SC98']
    assert list(parallel.libraries) == ['SC97', 'SC98']


def test_a_failure_at_the_requested_horizon_refuses_a_completed_study():
    model = compile_text('scenario "Clock"\n    horizon 2 h\nassert t < 2 h\n', {'h': {'time': 1}})
    with pytest.raises(ValueError, match='2 h'):
        catalogue.completed_study(model)


def test_authored_paths_option_settings_and_comparisons(tmp_path):
    path = write_model(tmp_path, 'SC97')
    settings = path.with_name('brief.toml')
    settings.write_text(
        'show = ["total", "east.rate", "future"]\n'
        'drivers = ["west.rate"]\n'
        'featured = ["high", "low"]\n'
        'choice_group = "Gauges"\n'
        '[[sweep]]\nid = "central"\ndescription = "Change both gauges"\n'
        'run = "low"\nset = {"Gauge.instances.rate" = 2}\n'
    )
    model = publish.Context(tmp_path, scenario_ids=['SC97']).models['SC97']
    display = brief.brief_of(model)
    assert brief.shown(display, model) == ['total', 'east.rate', 'future']
    assert brief.controls(model) == ['Gauge.instances.rate', 'east.rate']
    assert brief.drivers(display, model) == ['west.rate']
    assert brief.featured(display, model) == ['high', 'low']
    assert display.sweeps[0].edits == {'set': {'Gauge.instances.rate': 2}}
    wrong = brief.read_brief('show = ["absent"]\ndrivers = ["total"]\nfeatured = ["low", "high"]')
    assert [p['key'] for p in brief.check_brief(wrong, model)] == ['show', 'drivers', 'featured']


def test_spreads_check_the_requested_sampling_method_and_settings():
    text = '[[spread]]\nid = "wide"\nruns = ["low"]\nsamples = 12\nseed = 1\n'
    spread = brief.read_brief(text).spreads[0]
    assert spread.settings.record() == {'samples': 12, 'seed': 1}
    with pytest.raises(brief.StyleError) as problem:
        brief.read_brief(text + 'method = "sobol"\n')
    assert [p['key'] for p in problem.value.diagnostics] == ['spread[0].method']


def test_missing_show_uses_authored_reporting_and_unestimated_notes_including_template_members():
    source = SOURCE.replace(
        '    comparisons:',
        '    reporting:\n        Gauge:\n            rate:\n                category: "Condition"\n'
        '        total:\n            scope: "Both gauges"\n    comparisons:',
    )
    model = compile_text(source, {'h': {'time': 1}})
    assert brief.shown(brief.Brief(), model) == ['east.rate', 'west.rate', 'total', 'future']
    # Without reporting notes a new package has the same default path listing as the public CLI.
    plain = compile_text('scenario "Gauge"\n    horizon 0 h\nvalue = 2\n', {'h': {'time': 1}})
    record = catalogue.completed_study(plain)[None]
    assert brief.shown(brief.Brief(), plain, record) == ['value']
    assert brief.featured(brief.Brief(), plain) == [None]
    assert [item['path'] for item in check.catalogue_problems(plain)] == ['value']
    empty = compile_text(
        'scenario "Gauge"\n    horizon 0 h\nvalue = 2\nnotes:\n    reporting:\n', {'h': {'time': 1}}
    )
    assert brief.shown(brief.Brief(), empty) == []


def test_catalogue_scope_comes_from_the_value_its_template_or_the_scenario():
    source = SOURCE.replace(
        '    comparisons:',
        '    reporting:\n        Gauge:\n            rate:\n                scope: "This gauge"\n'
        '        total:\n            category: "Quantity"\n    comparisons:',
    )
    model = compile_text(source, {'h': {'time': 1}})
    assert [p['path'] for p in check.catalogue_problems(model)] == ['total', 'future']
    scoped = compile_text(
        source.replace('    horizon', '    scope "This region"\n    horizon'), {'h': {'time': 1}}
    )
    assert check.catalogue_problems(scoped) == []
