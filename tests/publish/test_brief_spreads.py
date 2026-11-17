"""A brief's spreads (`[[spread]]` in brief.toml): each samples its runs under its edit document
(`spreads/<id>.json`, which gives inputs their distributions), in the engine's Monte Carlo study through
napkin/spread.py, and the brief shows the mean and the middle 90% of each outcome at the end of each
run. Each sample of a tiny model holds its closed form, so each figure follows from the draws. A spread
that the engine rejects stops the brief, and a brief without a spread calculates none.

As in the catalogue, the models hold point values only: the distributions come from the edit
documents.
"""

import json
from types import SimpleNamespace

import numpy as np
import pytest
from jsonschema import Draft202012Validator

from napkin import spread as sampling
from napkin.draw.style import StyleError
from napkin.engine import (
    SamplingSettings,
    edits_for,
    evaluate_study,
    evaluate_uncertainty,
    sample_result,
    uncertainty_report,
)
from napkin.engine.sampling import LIMIT
from napkin.model import load_json
from napkin.model.load import SCHEMA_BYTES
from napkin.model.model import build_model
from tests.build import block, edit, library, named, once_at, output, replace, stock, system, timer, uncertain
from tests.helpers import ROOT
from tests.owned import write_scenario
from tests.publish.test_briefs import story_scenario
from tools.publish import brief as settings
from tools.publish import briefs

# The timer's own values, and the distributions that the edit document of a spread gives them.
POINT = ('2 people/h', '6 h')
DRAWN = {'s.rate': 'uniform(1 people/h, 3 people/h)', 's.end': 'pert(2 h, 6 h, 20 h)'}


def entry(ident='spread', runs=('a',), samples=8, seed=3, **keys):
    """The TOML of one `[[spread]]`, with its other keys (`method`, `description`, `outputs`)."""
    lines = [
        '[[spread]]',
        f'id = {json.dumps(ident)}',
        f'runs = {json.dumps(list(runs))}',
        f'samples = {samples}',
        f'seed = {seed}',
        *(f'{key} = {json.dumps(value)}' for key, value in keys.items()),
    ]
    return '\n'.join(lines) + '\n'


def documents(model, brief, edits):
    """Write the edit document of each spread of `brief` beside the model's file: `edits` for the model's
    revision."""
    for spread in settings.read_brief(brief).spreads:
        path = settings.spread_document(model, spread)
        path.parent.mkdir(exist_ok=True)
        path.write_text(json.dumps(edits_for(model, edits)), encoding='utf-8')


def written(tmp_path, text, brief, edits=None):
    """The model of `text` in a folder of the catalogue, with its brief settings `brief` and the edit
    document of each spread."""
    _, model = write_scenario(tmp_path, text, brief=brief)
    documents(model, brief, edits)
    return model


def the_spread(model, ident='spread'):
    return next(spread for spread in settings.brief_of(model).spreads if spread.id == ident)


def spread_rows(lines):
    """The rows of the pathways of a brief's spread table."""
    return [line for line in lines if line.startswith('| ') and not line.startswith(('| Pathway', '| ---'))]


def mean_and_band(values, unit):
    """What the brief shows of the samples of an outcome: their mean, then their middle 90% (type 7
    percentiles) in brackets, written as the brief writes a figure."""
    low, high = (briefs.amount(value, unit) for value in np.percentile(values, [5, 95]))
    return f'{briefs.amount(sum(values) / len(values), unit)} ({low if low == high else f"{low} to {high}"})'


# ---- the brief settings of a spread ---------------------------------------------------------------


def test_a_spread_is_read_as_written():
    """A spread keeps its runs in the order of the file, its settings and its outputs; its method is
    random unless it names one, and without outputs or a description it has none."""
    text = (
        entry(runs=('b', 'a'), samples=4, seed=1)
        + entry('other', method='latin', outputs=['served'], description='The other spread.')
        + entry('blocks', samples=32, method='sobol')
    )
    found = settings.read_brief(text, 'brief.toml').spreads
    assert [(s.id, s.runs, s.settings.record(), s.outputs, s.description) for s in found] == [
        ('spread', ('b', 'a'), {'samples': 4, 'seed': 1, 'method': 'random'}, (), None),
        ('other', ('a',), {'samples': 8, 'seed': 3, 'method': 'latin'}, ('served',), 'The other spread.'),
        # 32 samples with `sobol` are the 8 blocks of the engine, of 4 points each.
        ('blocks', ('a',), {'samples': 32, 'seed': 3, 'method': 'sobol', 'replicates': 8}, (), None),
    ]


@pytest.mark.parametrize(
    ('text', 'key', 'match'),
    [
        ('spread = 1\n', 'spread', 'holds tables'),
        (entry() + 'kind = "uncertainty"\n', 'spread[0].kind', 'not a key'),
        (entry().replace('id = "spread"\n', ''), 'spread[0].id', 'lowercase letters'),
        (entry() + entry(), 'spread[1].id', 'entry above'),
        (entry().replace('runs = ["a"]\n', ''), 'spread[0].runs', 'names one or more'),
        (entry(runs=()), 'spread[0].runs', 'names one or more'),
        (entry(runs=('a', 'a')), 'spread[0].runs', 'twice'),
        (entry().replace('["a"]', '["a", 3]'), 'spread[0].runs', 'list of names'),
        (entry().replace('samples = 8\n', ''), 'spread[0].samples', 'samples'),
        (entry(samples=0), 'spread[0].samples', 'samples'),
        (entry().replace('samples = 8', 'samples = true'), 'spread[0].samples', 'samples'),
        (entry(samples=LIMIT + 1), 'spread[0].samples', 'samples'),
        (entry().replace('seed = 3\n', ''), 'spread[0].seed', 'seed'),
        (entry(seed=-1), 'spread[0].seed', 'seed'),
        (entry(method='halton'), 'spread[0].method', 'method'),
        # `sobol` sampling takes its samples in 8 blocks of a power of two each.
        (entry(method='sobol', samples=12), 'spread[0].method', 'blocks of a power of two'),
        (entry(description=' '), 'spread[0].description', 'nonempty text'),
        (entry(outputs=[]), 'spread[0].outputs', 'names one or more'),
    ],
)
def test_a_spread_names_its_runs_and_its_samples(text, key, match):
    with pytest.raises(StyleError, match=match) as caught:
        settings.read_brief(text, 'brief.toml')
    assert [(d['file'], d['key'], d.get('line')) for d in caught.value.diagnostics] == [
        ('brief.toml', key, None)
    ]


@pytest.mark.parametrize(
    ('brief', 'key', 'match'),
    [
        (entry(runs=('a', 'nowhere')), 'spread[0].runs', 'not a run'),
        (entry(outputs=['served', 'unknown']), 'spread[0].outputs', 'not an output'),
    ],
)
def test_a_spread_names_what_its_model_declares(tmp_path, brief, key, match):
    model = written(tmp_path, timer(*POINT), brief, {'set': DRAWN})
    with pytest.raises(StyleError, match=match) as caught:
        settings.brief_of(model)
    assert [d['key'] for d in caught.value.diagnostics] == [key]


def test_a_spread_has_its_edit_document_beside_the_model_file(tmp_path):
    model = written(tmp_path, timer(*POINT), entry(), {'set': DRAWN})
    settings.spread_document(model, settings.read_brief(entry()).spreads[0]).unlink()
    with pytest.raises(StyleError, match='edit document') as caught:
        settings.brief_of(model)
    assert [d['key'] for d in caught.value.diagnostics] == ['spread[0].id']


# ---- the calculation ------------------------------------------------------------------------------


def test_a_spread_is_the_engines_study_of_its_runs_under_its_edit_document(tmp_path):
    """The brief's spread is the engine's Monte Carlo study of the edit document in one process, bit for
    bit: the same rows, draws and outcomes of the events that go by chance, for this model and this
    implementation. The draws are those of the document's distributions."""
    source = timer(
        *POINT,
        named('answer', 'none', 'yes', 'no'),
        block(
            'event choose once when t >= 1 h:  @fixture',
            block('yes 0.5:', 'answer = "yes"'),
            block('no else:', 'answer = "no"'),
        ),
    )
    model = written(tmp_path, source, entry(samples=8, seed=17), {'set': DRAWN})
    report = briefs.calculated_spread(model, the_spread(model))
    retained = evaluate_uncertainty(
        model, edits_for(model, {'set': DRAWN}), SamplingSettings(8, seed=17), runs=['a']
    )
    assert retained.admissible, retained.diagnostics
    assert json.dumps(report, sort_keys=True) == json.dumps(uncertainty_report(retained), sort_keys=True)
    assert (report['model_hash'], report['implementation_hash']) == (
        model.model_hash,
        model.implementation_hash,
    )
    sampled = report['uncertainty']['runs']['a']
    assert {name: item['distribution']['text'] for name, item in sampled['inputs'].items()} == DRAWN
    events = sampled['events']['s.choose']
    assert sum(events.values()) == 8
    assert all(count > 0 for count in events.values())


def test_the_spread_is_the_spread_of_the_closed_forms_of_its_draws(tmp_path):
    """served(24 h) = rate * end in each sample: the percentiles that the spread gives at the end are
    those of the closed forms of its draws, the brief keeps the engine's summary of each outcome, and
    the report keeps the report schema."""
    model = written(tmp_path, timer(*POINT), entry(samples=8, seed=3), {'set': DRAWN})
    spread = the_spread(model)
    report = briefs.calculated_spread(model, spread)
    # The report schema as the compiler imported it.
    Draft202012Validator(json.loads(SCHEMA_BYTES['report'])).validate(report)
    section = report['uncertainty']
    assert section['settings'] == {'samples': 8, 'seed': 3, 'method': 'random'}
    data = section['runs']['a']
    draws = {name: item['draws'] for name, item in data['inputs'].items()}
    served = [rate * end for rate, end in zip(draws['s.rate'], draws['s.end'], strict=True)]
    final = data['outcomes'][model.outputs['served']]['points']['final']
    assert [final[f'p{p}'] for p in (5, 50, 95)] == pytest.approx(
        list(np.percentile(served, [5, 50, 95])), rel=1e-9
    )
    kept = briefs.spread_of(model, spread, report)
    assert kept['runs']['a']['inputs'] == DRAWN
    assert kept['runs']['a']['outcomes'][model.outputs['served']]['final'] == final
    assert json.loads(json.dumps(kept)) == kept


def test_a_sample_whose_run_fails_stops_the_brief(tmp_path):
    """A sample that moves more people than the source holds fails its run, so the engine rejects the
    spread, and the brief shows no part of it."""
    source = system(
        uncertain('amount', 'people', 0, 20, '5 people'),
        stock('source', 10),
        stock('out'),
        once_at('takes', '1 h', 'move amount from source to out'),
        horizon=3,
    )
    drawn = {'set': {'s.amount': 'uniform(5 people, 15 people)'}}
    model = written(tmp_path, source, entry(samples=8, seed=6), drawn)
    assert not evaluate_uncertainty(
        model, edits_for(model, drawn), SamplingSettings(8, seed=6), runs=['a']
    ).admissible
    with pytest.raises(ValueError, match='rejected'):
        briefs.calculated_spread(model, the_spread(model))


def test_a_reporting_failure_of_a_sample_stops_the_brief(tmp_path, monkeypatch):
    """A sample's outcomes fail to report at the end of the run, after its run checks held: an outcome
    is never estimated from it, and the brief shows no part of the spread."""
    from napkin.engine import uncertainty
    from napkin.engine.report import ReportingError

    model = written(tmp_path, timer(*POINT), entry(samples=2, seed=17), {'set': DRAWN})
    evaluate = uncertainty.evaluate_outputs
    horizon = model.time['horizon']

    def fail_at_the_end(completed, library, times):
        if completed['resolved'].luck and horizon in times:
            raise ReportingError('Injected reporting failure of a sample')
        return evaluate(completed, library, times)

    monkeypatch.setattr(uncertainty, 'evaluate_outputs', fail_at_the_end)
    with pytest.raises(ValueError, match='Injected reporting failure of a sample'):
        briefs.calculated_spread(model, the_spread(model))


def test_an_edit_document_of_another_model_revision_stops_the_brief(tmp_path):
    """The engine checks a spread's edit document as every edit document: one written for another
    revision of the model is not this calculation's."""
    model = written(tmp_path, timer(*POINT), entry(), {'set': DRAWN})
    path = settings.spread_document(model, the_spread(model))
    path.write_text(json.dumps({**load_json(path), 'model_hash': '0' * 64}), encoding='utf-8')
    with pytest.raises(ValueError, match='different model revision'):
        briefs.calculated_spread(model, the_spread(model))


# ---- what the brief shows -------------------------------------------------------------------------


def test_the_brief_shows_the_mean_and_the_middle_90_percent_of_each_outcome_of_each_sampled_run():
    """Only a sampled pathway has a row: the mean, with the words of its unit once, then the middle 90%;
    an outcome that is not estimated is never a figure. The text counts the calculations."""
    model = SimpleNamespace(
        inputs={'s.rate': {'doc': 'Rate'}},
        runs={'a': {'name': 'First pathway'}, 'b': {'name': 'Second pathway'}},
    )
    point = {'estimated': True, 'mean': 3.0, 'p5': 1.2345, 'p95': 5.678}
    study = {
        'description': None,
        'settings': {'samples': 8, 'seed': 3, 'method': 'random'},
        'outcomes': [],
        'runs': {
            'a': {
                'inputs': {'s.rate': 'uniform(1 people/h, 3 people/h)'},
                'chance': False,
                'outcomes': {
                    'o.served': {'final': point},
                    'o.open': {'final': {'estimated': False}},
                    'o.fuel': {'final': {'estimated': True, 'mean': 2000.0, 'p5': 1000.0, 'p95': 3000.0}},
                },
            }
        },
    }
    served = briefs.Metric('o.served', 'Served', 'people', '', '')
    unknown = briefs.Metric('o.open', 'Open', 'people', '', '')
    fuel = briefs.Metric('o.fuel', 'Fuel', 'L', 'litres', '')
    lines = briefs.spread_lines(model, {'studies': {'spread': study}}, [served, unknown, fuel])
    amount = briefs.amount
    assert spread_rows(lines) == [
        f'| First pathway | {amount(3.0, "people")} ({amount(1.2345, "people")} to {amount(5.678, "people")})'
        f' | not estimated | {amount(2000.0, "L")} litres ({amount(1000.0, "L")} to {amount(3000.0, "L")}) |',
    ]
    assert any(line.startswith('8 calculations draw each input') and 'Rate' in line for line in lines)
    study['settings']['samples'] = 1
    lines = briefs.spread_lines(model, {'studies': {'spread': study}}, [])
    assert any(line.startswith('1 calculation draws each input') for line in lines)


def test_a_brief_gives_the_mean_of_each_outcome_and_so_the_share_of_an_outcome_of_one_or_zero(tmp_path):
    """served(24 h) = rate * end, and early = 1 when the service stops before 6 h, else 0, in each sample.
    The spread names the two outcomes for the brief, which gives the mean of each over the samples and
    then their middle 90%, as the closed forms of the draws give them: the mean of `early` is the share
    of the samples that stop early, which its band of 0 to 1 does not show."""
    early = output('early', '(1 if s.end < 6 h else 0)', 'fraction', 'level', doc='The service stops early')
    anchor = 'output elapsed_time: h = t  @fixture'
    source = edit(timer(*POINT), replace(anchor, f'{early}\n\n{anchor}'))
    brief = entry(samples=16, seed=3, description='The spread of the service.', outputs=['served', 'early'])
    model = written(tmp_path, source, brief, {'set': DRAWN})
    spread = the_spread(model)
    report = briefs.calculated_spread(model, spread)
    draws = {name: item['draws'] for name, item in report['uncertainty']['runs']['a']['inputs'].items()}
    served = [rate * end for rate, end in zip(draws['s.rate'], draws['s.end'], strict=True)]
    stops_early = [1.0 if end < 6 else 0.0 for end in draws['s.end']]
    # The seed gives samples of both kinds, so the share is neither 0 nor 1.
    assert 0 < sum(stops_early) < len(stops_early)
    kept = briefs.spread_of(model, spread, report)
    assert kept['outcomes'] == [model.outputs['served'], model.outputs['early']]
    # The timer has no event that goes by chance: each sample draws its inputs only.
    assert kept['runs']['a']['chance'] is False
    lines = briefs.spread_lines(model, {'studies': {spread.id: kept}}, [])
    outcomes = next(iter(model.structures.values())).outcomes
    labels = [outcomes[name].label for name in kept['outcomes']]
    assert f'| Pathway | {labels[0]} | {labels[1]} |' in lines
    assert spread_rows(lines) == [
        f'| {model.runs["a"]["name"]} | {mean_and_band(served, "people")} | '
        f'{mean_and_band(stops_early, "fraction")} |'
    ]
    assert spread.description in lines
    assert any(model.inputs['s.rate']['doc'] in line and 'by chance' not in line for line in lines)


def test_the_spread_of_chance_alone_gives_the_share_of_each_outcome_of_the_events(tmp_path):
    """An event at 1 h shuts the plant with the chance 0.3, else the operators run it by hand, and no
    input has a distribution: the edit document has no edits. Each sample draws the event's outcome;
    the brief says so, and the mean of `shut` is the share of the samples whose plant is shut at the
    end."""
    source = system(
        named('x', 'a', 'shut', 'manual'),
        block(
            'event decide once when t >= 1 h:  @fixture',
            block('shut 0.3:', 'x = "shut"'),
            block('manual else:', 'x = "manual"'),
        ),
        outputs=(output('shut', '(1 if s.x is "shut" else 0)', 'fraction', 'level', doc='Plant shut'),),
    )
    model = written(tmp_path, source, entry(samples=16, seed=11, outputs=['shut']))
    spread = the_spread(model)
    report = briefs.calculated_spread(model, spread)
    result = evaluate_uncertainty(model, settings=SamplingSettings(16, seed=11), runs=['a'])
    assert result.admissible, result.diagnostics
    ends = [run['trajectory'].env_at(run['trajectory'].horizon)['s.x'] for run in result.samples['a']['runs']]
    shut = [1.0 if x == 'shut' else 0.0 for x in ends]
    assert 0 < sum(shut) < len(shut)
    kept = briefs.spread_of(model, spread, report)
    assert kept['runs']['a']['chance'] is True
    assert kept['runs']['a']['inputs'] == {}
    lines = briefs.spread_lines(model, {'studies': {spread.id: kept}}, [])
    assert any(
        line.startswith('16 calculations draw the outcome of each event that goes by chance.')
        for line in lines
    )
    assert not any('has a distribution:' in line for line in lines)
    assert spread_rows(lines) == [f'| {model.runs["a"]["name"]} | {mean_and_band(shut, "fraction")} |']


def test_a_brief_calculates_no_spread_that_its_settings_do_not_define(tmp_path, monkeypatch):
    model = written(tmp_path, timer(*POINT), '# No spread.\n')

    def unexpected(*arguments, **keywords):
        pytest.fail('calculated a spread that no brief settings define')

    monkeypatch.setattr(sampling, 'spread', unexpected)
    assert briefs.scenario_spread(SimpleNamespace(), 'SC99', model) is None


def test_a_brief_shows_the_spread_of_its_pathways(tmp_path):
    """The story's spread samples its two featured runs under an edit document that draws the audit
    hours. Its brief gives, for each pathway, the mean and the middle 90% of the deliveries awaiting
    audit, served * audit_h / 1 h in each sample with the run's own people served, min(n, rate * end)
    with a rate a day; the pending audits are not estimated in any sample."""
    story = story_scenario()
    folder = tmp_path / 'story'
    folder.mkdir()
    brief = story.brief() + entry(runs=('ai', 'human'), samples=8, seed=5)
    (folder / 'model.scn').write_text(story.text, encoding='utf-8')
    (folder / settings.BRIEF_FILE).write_text(brief, encoding='utf-8')
    lib = library()
    model = build_model(folder / 'model.scn', lib)
    drawn = {'set': {'audit.audit_h': 'uniform(1 h, 3 h)'}}
    documents(model, brief, drawn)
    study = evaluate_study(model)
    assert study.admissible, study.diagnostics
    sid = 'story_fixture'
    ctx = SimpleNamespace(
        root=ROOT, models={sid: model}, studies={sid: study}, library=lib, scenario_ids=None
    )
    text = briefs.artifacts(ctx)[f'scenarios/{sid}/results/brief.md']
    lines = text.splitlines()
    section = lines[
        lines.index('## The spread of the outcomes') : lines.index('## The decisive defender choice')
    ]
    report = briefs.calculated_spread(model, the_spread(model))
    rows = []
    for run in ('ai', 'human'):
        values = model.run_values(run)
        served = min(values['service.n'], values['service.rate'] / 24 * values['service.end'])
        hours = report['uncertainty']['runs'][run]['inputs']['audit.audit_h']['draws']
        rows.append(
            f'| {model.runs[run]["name"]} | {mean_and_band([served * h for h in hours], "people")} | not estimated |'
        )
    assert spread_rows(section) == rows


def test_a_check_without_spreads_takes_the_committed_section_and_samples_none(tmp_path, monkeypatch):
    """D-39: with committed spreads (`tools.check` without `--spreads`), the brief's spread section is the
    committed brief's, line for line, no spread is sampled, and every other line is the brief without a
    spread. A committed brief without the section gives the placeholder, so that the check reports it."""
    story = story_scenario()
    folder = tmp_path / 'story'
    folder.mkdir()
    brief = story.brief() + entry(runs=('ai', 'human'), samples=8, seed=5)
    (folder / 'model.scn').write_text(story.text, encoding='utf-8')
    (folder / settings.BRIEF_FILE).write_text(brief, encoding='utf-8')
    lib = library()
    model = build_model(folder / 'model.scn', lib)
    documents(model, brief, {'set': {'audit.audit_h': 'uniform(1 h, 3 h)'}})
    study = evaluate_study(model)
    assert study.admissible, study.diagnostics

    def unexpected(*arguments, **keywords):
        pytest.fail('sampled a spread in a check without --spreads')

    monkeypatch.setattr(briefs, 'calculated_spread', unexpected)
    monkeypatch.setattr(sampling, 'spread', unexpected)
    sid = 'story_fixture'
    path = f'scenarios/{sid}/results/brief.md'
    section = [
        briefs.SPREAD_HEADING,
        '',
        'A committed line.',
        '',
        '### one',
        '',
        'Another committed line.',
        '',
    ]
    committed = tmp_path / path
    committed.parent.mkdir(parents=True)
    committed.write_text(
        '\n'.join(
            ['# A committed brief', '', '## Before', '', 'text', '', *section, '## After', '', 'more', '']
        ),
        encoding='utf-8',
    )
    ctx = SimpleNamespace(
        root=tmp_path,
        models={sid: model},
        studies={sid: study},
        library=lib,
        scenario_ids=None,
        committed_spreads=True,
    )
    lines = briefs.artifacts(ctx)[path].splitlines()
    start = lines.index(briefs.SPREAD_HEADING)
    assert lines[start : start + len(section)] == section
    without = briefs.brief(sid, model, study, sample_result(study), model.library).splitlines()
    assert lines[:start] + lines[start + len(section) :] == without
    committed.write_text('# A committed brief without a spread\n', encoding='utf-8')
    assert briefs.MISSING_SPREAD in briefs.artifacts(ctx)[path].splitlines()
