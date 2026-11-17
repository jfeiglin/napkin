"""Options, runs and the edits of a study, with closed forms.

A synthetic service delivers people from outside at `rate * share`, and at half that pace in its
`half` state, which the option Halved sets at the start: the runs that name Halved have a structure
of their own. The Response options set `rate`, Impaired sets `share`, and a check of the inputs forbids a rate above LIMIT with an
impaired share. Every expectation comes from values that the test
reads from the model or edits itself, and from the closed form of the delivery,
delivered(T) = rate * share * factor * T, with factor 1/2 in the `half` state. None comes from a run
of a scenario.
"""

from __future__ import annotations

import copy
import textwrap

import pytest

import napkin.engine.study as study_module
from napkin.engine import analyze_bounds, edits_for, evaluate_study, resolve_edits, sample_result
from napkin.model import ModelError
from napkin.model.ir import thaw
from napkin.model.language import front
from napkin.model.model import build_model
from tests.build import (
    BASIS,
    check,
    compiled,
    edit,
    event,
    formula,
    library,
    member,
    output,
    parameter,
    replace,
)

LIBRARY = library()
LIMIT = 24  # people/day: the fastest rate that the check allows with an impaired share

FIXTURE = textwrap.dedent(
    """\
    scenario "Options fixture"
        summary "A synthetic service that options and edits change. A fixture for tests only."
        horizon 12 h
        scope "Synthetic people."

    service:  @fixture
        "A service that delivers people at a rate."
        role operator
        input rate = 18 people/day in 1 people/day to 48 people/day  @fixture
            "Delivery rate"
        input share: fraction = 1 in 0.1 to 1  @fixture
            "Share delivered"
        let capacity = 100 people  @fixture
            "Capacity"
        var mode: "full" | "half" = "full"
        var delivered: people = 0  @fixture
            "People delivered"
        output delivered
        flow deliver: -> delivered at rate * share * (0.5 if mode is "half" else 1)  @fixture
            "People are delivered."
        assert rate <= LIMIT people/day or share >= 1  @fixture
            "An impaired service cannot use a fast rate."

    options "Response":
        "Fast":
            "Fast delivery."
            service.rate = 24 people/day  @fixture
        "Slow":
            "Slow delivery."
            service.rate = 12 people/day  @fixture
        "Unused":
            "A response that no run takes."
            service.rate = 20 people/day  @fixture

    options "Delivery":
        "Full":
            "The defaults."
        "Impaired":
            "Half of the people are delivered."
            service.share = 0.5  @fixture
        "Halved":
            "The service starts at half pace."
            service.mode = "half"  @fixture

    options "Crew":
        "Day crew":
            "The defaults."
        "Night crew":
            "A crew that changes nothing."
        "Spare crew":
            "A crew that no run takes."

    runs:
        fast = "Fast" + "Full"
        slow = "Slow" + "Full"
        fast_impaired = "Fast" + "Impaired"
        fast_halved = "Fast" + "Halved"
        slow_halved = "Slow" + "Halved"
        slow_night = "Slow" + "Full" + "Night crew"

    record fixture: identity "Synthetic test fixture."
"""
).replace('LIMIT', str(LIMIT))


def build(*steps, text=FIXTURE, library=LIBRARY):
    """The model of the fixture `text` with the steps of an edit (tests/build.py, `edit`)."""
    return compiled(edit(text, *steps), library, 'options.scn')


@pytest.fixture(scope='module')
def model():
    return build()


def errors(study):
    return [d for d in study.diagnostics if d.get('severity') == 'error']


def option_value(model, name, option):
    return model.inputs[name]['options'][option]['value']


def setting(model, profile, target):
    """What the profile `profile` sets `target` to, as the model's run table holds it."""
    return model.run_table.data['inputs'][target]['options'][profile]


def check_code(model, index=0):
    """The code of the diagnostic of the service's check at `index`."""
    checks = next(iter(model.structures.values())).input_checks
    return 'check:' + next(cid for cid, c in checks.items() if c.path == f'service/assert:/{index}')


def delivered(model, report, run):
    return report['runs'][run]['reporting_points']['final']['values'][model.outputs['service.delivered']]


def closed_form(model, values, starts):
    """delivered(T) = rate * share * factor * T, with the rate in people/h."""
    scale = LIBRARY['units'][model.inputs['service.rate']['unit']]['scale']
    factor = 0.5 if 'Halved' in starts else 1
    return values['service.rate'] * scale * values['service.share'] * factor * model.time['horizon']


# ---- the model --------------------------------------------------------------------------------


def test_a_model_builds_from_a_file_with_a_library_of_the_current_schema(tmp_path):
    """A model builds from a model file with a library of the current schema."""
    path = tmp_path / 'options.scn'
    path.write_text(FIXTURE, encoding='utf-8')
    assert set(build_model(path, LIBRARY).runs) == {
        run.name for run in front.read(FIXTURE, 'options.scn').runs
    }

    # The scenario line takes no schema version.
    with pytest.raises(ModelError):
        build(member('scenario:', 'schema_version "3.0.0"'))
    # A run that names no option of a group is a run like any other.
    assert build(member('runs:', 'odd = "Full"')).runs['odd']['options'] == ('Full',)
    old = copy.deepcopy(LIBRARY)
    old['schema_version'] = '1.0.0'
    with pytest.raises(ModelError):
        build(library=old)


@pytest.mark.parametrize(
    'change',
    [
        replace('service.rate = 24 people/day', 'service.rate = 100 people/day'),
        # 1e999 is too large for a number of the machine: it reads as infinity.
        replace('service.rate = 12 people/day', 'service.rate = 1e999 people/day'),
        member('options:/Delivery/Impaired', f'service.rate = 12 people/day  {BASIS}'),
        member('runs:', 'odd = "Fast" + "Quick"'),
    ],
    ids=['out of range', 'not finite', 'two groups set one field', 'unknown option'],
)
def test_the_model_rejects_a_bad_option(change):
    with pytest.raises(ModelError):
        build(change)


def test_a_response_option_that_no_run_names_is_checked_when_the_model_is_built():
    """A Response option that no run names combines with the other options of every run, as an option
    of any other group that no run names does, so the model checks its values when it is built: one
    out of its range, or one that breaks a check of the inputs in such a combination, rejects the
    file."""

    def rate(value):
        return replace('service.rate = 20 people/day', f'service.rate = {value} people/day')

    with pytest.raises(ModelError) as caught:
        build(rate(100))
    assert {d['code'] for d in caught.value.diagnostics} == {'bounds'}
    model = build()
    with pytest.raises(ModelError) as caught:
        build(rate(LIMIT + 12))
    assert [(d['code'], d.get('run'), d.get('options')) for d in caught.value.diagnostics] == [
        (check_code(model), None, ['Unused', 'Impaired'])
    ]
    assert evaluate_study(build(rate(LIMIT))).admissible


def test_a_response_option_that_no_run_names_is_proved_with_the_other_options_of_every_run():
    """A formula divides by a pause that a Response option that no run names sets to zero: the model is
    rejected for that option's combinations only when it is built, and admitted once its pause is
    positive."""

    def paced(pause):
        return (
            member(
                'service',
                parameter('pause', 2, 'h', 0, 10, doc='Pause'),
                formula('paced', 'rate * 1 h / pause', 'people/h', doc='Paced delivery rate'),
            ),
            replace('at rate * share', 'at paced * share'),
            member('options:/Response/Unused', f'service.pause = {pause} h  {BASIS}'),
        )

    with pytest.raises(ModelError) as caught:
        build(*paced(0))
    found = caught.value.diagnostics
    assert found
    for d in found:
        assert d.get('run') is None and d['options'][0] == 'Unused', d
    assert any(d['code'] == 'dynamic_domain' for d in found)
    assert evaluate_study(build(*paced(1))).admissible


# ---- one option, every run that names it --------------------------------------------------------


def test_a_response_option_edit_reaches_every_run_that_names_it(model):
    """An edit of one option changes the runs that name it and no other; the model does not change."""
    fast = option_value(model, 'service.rate', 'Fast')
    before = model.resolve('fast_impaired')
    assert list(before.options) == ['Fast', 'Impaired']
    assert before.parameter_values['service.rate'] == fast
    scale = LIBRARY['units'][model.inputs['service.rate']['unit']]['scale']
    assert before.values['service.rate'] == pytest.approx(fast * scale, rel=1e-12)
    edited = fast / 2
    study = evaluate_study(model, edits_for(model, {'options': {'Fast': {'service.rate': edited}}}))
    assert study.admissible, errors(study)
    report = sample_result(study)
    for run, info in model.runs.items():
        values = dict(model.run_values(run))
        if 'Fast' in info['options']:
            values['service.rate'] = edited
        assert report['runs'][run]['effective_inputs']['service.rate'] == values['service.rate']
        assert delivered(model, report, run) == pytest.approx(
            closed_form(model, values, info['starts']), rel=1e-9
        )
    assert model.resolve('fast').parameter_values['service.rate'] == fast
    with pytest.raises(TypeError):
        setting(model, 'Fast', 'service.rate')['value'] = 99


def test_a_response_option_edit_changes_every_structure_and_keeps_the_other_options(model):
    """The runs that name Fast have two structures (with and without Halved); one edit of Fast
    changes both, and the runs of Slow keep every reported value."""
    baseline = sample_result(evaluate_study(model))
    slow = option_value(model, 'service.rate', 'Slow')
    study = evaluate_study(model, edits_for(model, {'options': {'Fast': {'service.rate': slow}}}))
    assert study.admissible, errors(study)
    report = sample_result(study)
    for run, info in model.runs.items():
        values = dict(model.run_values(run))
        if 'Fast' in info['options']:
            values['service.rate'] = slow
        else:
            assert report['runs'][run]['reporting_points'] == baseline['runs'][run]['reporting_points']
        assert delivered(model, report, run) == pytest.approx(
            closed_form(model, values, info['starts']), rel=1e-9
        )
    fast, halved = study.runs['fast']['resolved'], study.runs['fast_halved']['resolved']
    assert fast.starts != halved.starts
    assert fast.parameter_values['service.rate'] == halved.parameter_values['service.rate'] == slow


def test_a_reversed_response_edit_is_admitted(model):
    """No study checks an order of the Response options: the orders of the results of the
    standard runs are acceptance tests."""
    slow = option_value(model, 'service.rate', 'Slow')
    study = evaluate_study(model, edits_for(model, {'options': {'Fast': {'service.rate': slow / 2}}}))
    assert study.admissible, errors(study)
    assert not [d for d in study.diagnostics if d['code'] in ('tier_order', 'outcome_order')]
    report = sample_result(study)
    assert delivered(model, report, 'fast') < delivered(model, report, 'slow')


def test_an_edit_of_one_run_wins_over_the_value_of_its_response_option(model):
    slow, fast = (option_value(model, 'service.rate', p) for p in ('Slow', 'Fast'))
    study = evaluate_study(model, edits_for(model, {'runs': {'fast_halved': {'service.rate': slow}}}))
    assert study.admissible, errors(study)
    rate = {
        run: completed['resolved'].parameter_values['service.rate'] for run, completed in study.runs.items()
    }
    assert rate['fast_halved'] == slow and rate['fast'] == rate['fast_impaired'] == fast


def test_the_study_takes_each_value_from_the_narrowest_edit_that_reaches_its_run(model):
    """Every level of an edit document edits one input with its own value: each run takes the value
    of the narrowest level that reaches it (one run, one option, every run), and the report gives the
    edits as given, the run's name, options and start-state options."""
    low, high = model.inputs['service.share']['range']
    level_values = dict(zip(('set', 'options', 'runs'), (low + (high - low) * f for f in (0, 1 / 2, 1))))
    single = 'slow_night'
    body = {
        'reason': 'Precedence of the levels',
        'set': {'service.share': level_values['set']},
        'options': {'Impaired': {'service.share': level_values['options']}},
        'runs': {single: {'service.share': level_values['runs']}},
    }
    study = evaluate_study(model, edits_for(model, body))
    assert study.admissible, errors(study)
    report = sample_result(study)
    assert report['effective_edits'] == edits_for(model, body)
    for run, info in model.runs.items():
        level = 'runs' if run == single else 'options' if 'Impaired' in info['options'] else 'set'
        result = report['runs'][run]
        assert (result['label'], result['options'], result['starts']) == (
            info['name'],
            list(info['options']),
            list(info['starts']),
        )
        assert result['effective_inputs']['service.share'] == level_values[level], run
        values = {**model.run_values(run), 'service.share': level_values[level]}
        assert delivered(model, report, run) == pytest.approx(
            closed_form(model, values, info['starts']), rel=1e-9
        )


# ---- one edit document, one transaction ---------------------------------------------------------


@pytest.mark.parametrize(
    ('body', 'code'),
    [
        ({'options': {'Quick': {'service.rate': 12}}}, 'reference'),
        ({'runs': {'fastest': {'service.rate': 12}}}, 'reference'),
        ({'options': {'Fast': {'service.nothing': 12}}}, 'input'),
        ({'options': {'Fast': {'service.rate': 100}}}, 'bounds'),
        ({'options': {'Fast': {'service.rate': True}}}, 'value'),
        ({'options': {'Fast': {'service.rate': 12}, 'Impaired': {'service.rate': 12}}}, 'meeting'),
        ({'set': {'service.capacity': 100}}, 'locked'),
        # A named state takes its start value from the options, never from an edit.
        ({'set': {'service.mode': 'half'}}, 'input'),
        # A key of the edit format before version 2 is no key.
        ({'response_set': {'fast': {'rate': 12}}}, 'schema'),
        ({'model_hash': 'another revision'}, 'model_hash'),
    ],
)
def test_an_edit_document_has_one_validator_for_every_level(model, body, code, monkeypatch):
    """Each document breaks one rule: resolve_edits and the study reject it with that rule, and
    nothing runs. A fixed value takes no edit, even of its own value."""
    ran = []
    monkeypatch.setattr(study_module, 'simulate', lambda rs, *args: ran.append(rs.run))
    edits = edits_for(model, body)
    with pytest.raises(ModelError) as rejected:
        resolve_edits(model, edits)
    assert {d['code'] for d in rejected.value.diagnostics} == {code}
    study = evaluate_study(model, edits)
    assert not study.admissible and study.runs == {} and ran == []
    assert {d['code'] for d in errors(study)} == {code}


def test_an_edit_of_a_response_option_that_no_run_names_is_checked(model):
    """No run names Unused: an edit of it is checked against its input, and one that holds is
    admitted. It changes no run."""
    rejected = evaluate_study(model, edits_for(model, {'options': {'Unused': {'service.rate': 100}}}))
    assert not rejected.admissible and {d['code'] for d in errors(rejected)} == {'bounds'}
    admitted = evaluate_study(model, edits_for(model, {'options': {'Unused': {'service.rate': LIMIT}}}))
    assert admitted.admissible
    plain = evaluate_study(model)
    assert {run: item['resolved'] for run, item in admitted.runs.items()} == {
        run: item['resolved'] for run, item in plain.runs.items()
    }


def test_a_study_resolves_no_run_that_the_build_resolved(model, monkeypatch):
    """The build resolved and checked every run, so a study without edits resolves none of them
    again, and neither does a study with an edit of an option that no run names, which changes no run.
    An edit that changes a run's values resolves that run, and only it."""
    resolved = []
    real = type(model).resolve_in

    def resolve_in(self, *args, **kwargs):
        resolved.append(args[2])
        return real(self, *args, **kwargs)

    monkeypatch.setattr(type(model), 'resolve_in', resolve_in)
    resolve_edits(model)
    assert resolved == []
    # A rate that no option sets: an edit of Unused changes no run; one of Night crew changes one.
    rate = LIMIT - 2
    assert rate not in {option_value(model, 'service.rate', p) for p in ('Fast', 'Slow', 'Unused')}
    resolve_edits(model, edits_for(model, {'options': {'Unused': {'service.rate': rate}}}))
    assert resolved == []
    resolve_edits(model, edits_for(model, {'options': {'Night crew': {'service.rate': rate}}}))
    named = [run for run, info in model.runs.items() if 'Night crew' in info['options']]
    assert resolved == [f'runs/{run}' for run in named] and named


def test_one_option_edit_rejects_the_whole_study_if_one_run_fails(model, monkeypatch):
    """A fast rate breaks the check in the one run that names Fast with Impaired: the whole edit is
    rejected with that check, before any run."""
    ran = []
    real = study_module.simulate

    def simulate(rs, *args):
        ran.append(rs.run)
        return real(rs, *args)

    monkeypatch.setattr(study_module, 'simulate', simulate)
    study = evaluate_study(model, edits_for(model, {'options': {'Fast': {'service.rate': LIMIT + 12}}}))
    assert not study.admissible and study.runs == {} and ran == []
    assert [(d['code'], d.get('run')) for d in errors(study)] == [(check_code(model), 'fast_impaired')]


def test_an_edit_that_breaks_a_check_only_where_no_run_goes_is_checked_when_that_is_asked_for(model):
    """No run names Slow with Impaired. An edit of Slow that breaks the check only there holds in every
    run, so the study admits it. Fast_impaired with Slow in place of Fast, asked for, is the one run of
    its own model, which takes the same edit and rejects it with the check before anything runs.
    Without the edit, the combination delivers the closed form."""
    assert not any({'Slow', 'Impaired'} <= set(info['options']) for info in model.runs.values())
    edits = edits_for(model, {'options': {'Slow': {'service.rate': LIMIT + 12}}})
    study = evaluate_study(model, edits)
    assert study.admissible, errors(study)
    combined = model.combination('fast_impaired', ['Slow'])
    assert list(combined.runs) == ['fast_impaired']
    assert combined.runs['fast_impaired']['options'] == ('Slow', 'Impaired')
    rejected = evaluate_study(combined, edits)
    assert not rejected.admissible and rejected.runs == {}
    assert [(d['code'], d.get('run')) for d in errors(rejected)] == [(check_code(model), 'fast_impaired')]
    report = sample_result(evaluate_study(combined))
    values = {
        **model.run_values('fast_impaired'),
        'service.rate': option_value(model, 'service.rate', 'Slow'),
    }
    assert report['runs']['fast_impaired']['options'] == ['Slow', 'Impaired']
    assert delivered(combined, report, 'fast_impaired') == pytest.approx(
        closed_form(model, values, model.runs['fast_impaired']['starts']), rel=1e-9
    )


def group_named(name):
    """The steps of a change of the fixture: the group Response, under another name."""
    return (replace('options "Response":', f'options "{name}":'),)


def decided(model, edits):
    """What a study under `edits` decides: its admission, each error with its run or options, and the
    final values of each run that it admits."""
    study = evaluate_study(model, edits_for(model, edits))
    finals = {}
    if study.admissible:
        finals = {
            run: r['reporting_points']['final']['values'] for run, r in sample_result(study)['runs'].items()
        }
    return study.admissible, [(d['code'], d.get('run'), d.get('options')) for d in errors(study)], finals


EDITS = (
    {},
    {'options': {'Slow': {'service.rate': LIMIT + 12}}},
    {'options': {'Unused': {'service.rate': LIMIT}}},
    {'options': {'Unused': {'service.rate': LIMIT + 12}}},
)


def test_a_group_works_the_same_under_any_name(model):
    """A group's name is the file's and has no meaning in the language: under another name, the model
    has the same runs, every run gives the closed form, and every study decides the same."""
    other = build(*group_named('Defence'))
    assert list(other.menu) == ['Defence', *list(model.menu)[1:]]
    assert thaw(other.runs) == thaw(model.runs)
    report = sample_result(evaluate_study(other))
    for run, info in other.runs.items():
        assert delivered(other, report, run) == pytest.approx(
            closed_form(other, other.run_values(run), info['starts']), rel=1e-9
        )
    for edits in EDITS:
        assert decided(other, edits) == decided(model, edits), edits


def test_a_study_of_some_runs_checks_the_edits_in_those_runs(model):
    """`runs` resolves, checks and simulates only the runs named: an edit that breaks the check in
    another run is admitted for a run where it holds."""
    edits = edits_for(model, {'options': {'Fast': {'service.rate': LIMIT + 12}}})
    assert not evaluate_study(model, edits).admissible
    study = evaluate_study(model, edits, runs=['fast'])
    assert study.admissible, errors(study)
    assert list(study.runs) == ['fast'] and list(sample_result(study)['runs']) == ['fast']
    values = {**model.run_values('fast'), 'service.rate': LIMIT + 12}
    report = sample_result(study)
    assert delivered(model, report, 'fast') == pytest.approx(
        closed_form(model, values, model.runs['fast']['starts']), rel=1e-9
    )
    study = evaluate_study(model, edits, runs=['fast', 'fast_impaired'])
    assert not study.admissible and study.runs == {}
    assert [(d['code'], d.get('run')) for d in errors(study)] == [(check_code(model), 'fast_impaired')]
    nothing = evaluate_study(model, edits, runs=[])
    assert nothing.admissible and nothing.runs == {}
    unknown = evaluate_study(model, runs=['nothing'])
    assert not unknown.admissible and [d['code'] for d in errors(unknown)] == ['run']
    # resolve_edits is the same admission without the runs.
    assert list(resolve_edits(model, edits, iter(['fast']))) == ['fast']
    with pytest.raises(ModelError):
        resolve_edits(model, edits)
    with pytest.raises(ModelError):
        resolve_edits(model, edits, ['fast_impaired'])
    with pytest.raises(ModelError):
        resolve_edits(model, None, ['nothing'])


@pytest.mark.parametrize(
    'body',
    [
        {'options': {'Fast': {'service.rate': 100}}},
        {'options': {'Fast': {'service.rate': 12}, 'Impaired': {'service.rate': 12}}},
        {'runs': {'fastest': {'service.rate': 12}}},
        {'model_hash': 'another revision'},
    ],
    ids=['bounds', 'meeting', 'reference', 'model_hash'],
)
def test_a_study_of_some_runs_still_checks_the_edit_document(model, body):
    """The checks of the document itself hold whatever runs a study names: here the edits never reach
    the run named, and the study still rejects them."""
    study = evaluate_study(model, edits_for(model, body), runs=['slow'])
    assert not study.admissible and study.runs == {}
    with pytest.raises(ModelError):
        resolve_edits(model, edits_for(model, body), ['slow'])


def test_a_blocking_check_is_reported_instead_of_a_proof_that_the_edit_breaks():
    """A negative share breaks a check of the inputs and, with it, the sign of an output that reads the
    share: the study reports the check, in every run."""

    model = build(
        replace('in 0.1 to 1', 'in -1 to 1'),
        member(
            'service',
            output('kept', 'delivered * share', 'people', doc='People kept'),
            check('share >= 0', 'A share is not negative.'),
        ),
    )
    study = evaluate_study(model, edits_for(model, {'set': {'service.share': -0.5}}))
    found = errors(study)
    assert {d['code'] for d in found} == {check_code(model, 1)}
    assert {d['run'] for d in found if 'run' in d} == set(model.runs)
    assert all('run' in d for d in found)


@pytest.mark.parametrize('edits', [[], [1], False, 42, 'invalid'])
def test_edits_that_are_not_an_object_are_a_shape_error(model, edits):
    study = evaluate_study(model, edits)
    assert not study.admissible and study.diagnostics[0]['code'] == 'edits_shape'


def test_bounds_are_candidates_and_probe_the_runs_that_an_option_reaches(model):
    bounds = analyze_bounds(model, None, {'input': 'service.rate', 'level': 'options', 'name': 'Fast'})
    assert bounds['certified'] is False and bounds['status'] == 'unresolved'
    low, high = model.inputs['service.rate']['range']
    assert (bounds['candidates'][0]['min'], bounds['candidates'][0]['max']) == (low, high)
    assert bounds['checked_points']
    # A run names Fast with Impaired: a rate above the limit breaks the check there.
    for point in bounds['checked_points']:
        assert point['admissible'] == (point['value'] <= LIMIT), point['value']
    locked = analyze_bounds(model, None, {'input': 'service.capacity', 'level': 'set'})
    assert locked['status'] == 'locked' and not locked['checked_points']
    with pytest.raises(ValueError, match='No run'):
        analyze_bounds(model, None, {'input': 'service.rate', 'level': 'options', 'name': 'Spare crew'})
    # The levels are those of an edit document: a list of runs is none.
    with pytest.raises(ValueError, match='Unknown edit level'):
        analyze_bounds(model, None, {'input': 'service.rate', 'level': 'lists', 'name': 0})


def test_bounds_take_each_option_that_an_edit_takes_with_the_same_meaning(model):
    """An edit of an option reaches the runs that name it, and the bounds take that level with the
    same meaning: the Response option Unused, which no run names, reaches no run, so its bounds are a
    clear error. With an edit of an option that runs name, the current value is the edit's."""
    assert not any('Unused' in run['options'] for run in model.runs.values())
    target = {'input': 'service.rate', 'level': 'options', 'name': 'Unused'}
    with pytest.raises(ValueError, match='No run names the option'):
        analyze_bounds(model, None, target)
    low, _ = model.inputs['service.rate']['range']
    edit = low + 1
    assert edit < LIMIT
    fast = {**target, 'name': 'Fast'}
    edited = analyze_bounds(model, edits_for(model, {'options': {'Fast': {'service.rate': edit}}}), fast)
    assert edit in [p['value'] for p in edited['checked_points']]
    # A name that is not an option of the menu is no level, as it is no edit.
    with pytest.raises(ValueError, match='Unknown option'):
        analyze_bounds(model, None, {**target, 'name': 'Unused response'})


# ---- methods -----------------------------------------------------------------------------------

ORDERS = textwrap.dedent(
    """\
    scenario "Orders fixture"
        summary "A synthetic service that stops. A fixture for tests only."
        horizon 12 h
        scope "Synthetic people."

    service:  @fixture
        "A service that stops."
        role operator
        input delay = 1 h in 0.5 h to 5 h  @fixture
            "Time before it stops"
        var state: "on" | "off" = "on"
        var served: people = 0  @fixture
            "People served"
        output served
        flow serve: -> served at 1 people/h while state is "on"  @fixture
            "People are served."
        event stop when state is "on" and t >= delay:  @fixture
            "The service stops."
            state = "off"

    options "Response":
        "Default":
            "The defaults."

    runs:
        a = "Default"

    record fixture: identity "Synthetic test fixture."
"""
)


def ordered(*members):
    """The orders fixture with more members of the service."""
    return build(member('service', *members), text=ORDERS)


def test_a_malformed_method_fails_the_reader():
    """An event that waits has the lines of the language; a line of its change is a statement."""

    def take_pause(*changes, after='2 * delay', keep=None, more=()):
        # It ends after `stop`, at another moment, so the two do not meet.
        lines = event(
            'take_pause',
            'state is "on"',
            *changes,
            after=after,
            keep=keep,
            doc='The service pauses.',
            do_records=BASIS,
        )
        return '\n'.join([lines, *(f'    {line}' for line in more)])

    assert evaluate_study(ordered(take_pause('state = "off"'))).admissible
    for method in (
        take_pause('state = "off"', more=('execute_python: pass',)),
        take_pause('state'),
    ):
        with pytest.raises(ModelError):
            ordered(method)
