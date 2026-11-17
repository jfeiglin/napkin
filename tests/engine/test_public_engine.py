"""Independent acceptance cases for the public numerical and reporting contract.

The tests that read a study or a report use `evaluate_study(model, edits, numerical_settings,
runs=...)` and `sample_result(study, times)` with `report['runs']`. The others run each run
directly.
"""

import json
import math
import threading

import pytest
from jsonschema import Draft202012Validator

import napkin.engine.report as report_module
import napkin.model.model as model_module
from napkin import SCHEMA_VERSION
from napkin.engine import analyze_bounds, evaluate_study, sample_result
from napkin.model import ModelError
from napkin.model.runs import Runs
from napkin.schema import FOLDER as SCHEMAS
from tests.build import (
    BASIS,
    RATE_OPTIONS,
    RATE_RUNS,
    check,
    compiled,
    drop,
    edit,
    entity,
    event,
    formula,
    indent,
    library,
    member,
    named,
    option,
    options,
    parameter,
    replace,
    run,
    runs,
    scenario,
    stock,
    with_horizon,
)
from tests.owned import block_at


def edits_of(model, edits=None):
    return {'schema_version': SCHEMA_VERSION, 'model_hash': model.model_hash, **(edits or {})}


def lines_at(text, place):
    """The rows of the line at `place` and of the lines under it."""
    return block_at(text, place).rstrip('\n')


def forcing_fixture(expression):
    """The served count integrates a forcing of time, with nothing else moving."""
    text = with_horizon(scenario(), 1)
    tally = stock('served', 0, minimum=None, size=10, kind='tally', rate='forcing')
    return edit(
        text,
        member('scenario:', 'timescales 0.01 h'),
        replace('input end: h = 12 h', 'input end: h = 1 h'),
        replace(lines_at(text, 'service/served'), indent(tally)),
        drop('service/stock', 'service/delivery', 'service/serve', 'service/assert:/0', 'assert:/0'),
        member('service', formula('forcing', expression, 'people/h')),
    )


def test_smooth_narrow_forcing_matches_gaussian_integral():
    sc = forcing_fixture('1 people/h + 1000 people/h * exp(- ((t - 0.45 h) / 0.01 h) ** 2)')
    expected = 1 + 10 * math.sqrt(math.pi) / 2 * (math.erf(55) - math.erf(-45))
    for name in compiled(sc).runs:
        _, trajectory = run(sc, name)
        assert trajectory.env_at(1)['service.served'] == pytest.approx(expected, rel=1e-8, abs=1e-8)
        assert trajectory.settings['resolution_policy'] == 'physical_resolution_cap'
        assert trajectory.settings['actual_max_step_h'] == pytest.approx(0.00125)
        assert all(
            segment['max_step_h'] == pytest.approx(0.00125)
            for segment in trajectory.settings['integration_segments']
        )


def test_chained_time_window_matches_rectangle_integral():
    sc = forcing_fixture('100 people/h if 0.4 h < t < 0.5 h else 0')
    for name in compiled(sc).runs:
        _, trajectory = run(sc, name)
        assert trajectory.env_at(1)['service.served'] == pytest.approx(100 * (0.5 - 0.4), abs=1e-6)


def option_fixture(factor=1):
    """The stock starts at n * factor; an option that no run takes sets the factor."""
    menu = options(
        'Option', option('Unused option', 'No run takes it.', f'service.factor = {factor}  {BASIS}')
    )
    return edit(
        scenario(),
        member('service', parameter('factor', 1, 'fraction', -1, 1)),
        replace('var stock: people = n', 'var stock: people = n * factor'),
        replace('\nruns:', f'\n{menu}\n\nruns:'),
    )


def test_an_option_that_no_run_takes_receives_start_value_validation():
    sc = option_fixture(-1)
    with pytest.raises(ModelError) as raised:
        compiled(sc, library())
    assert any(item['code'] == 'initial_bound' for item in raised.value.diagnostics)


def test_an_edit_is_validated_in_every_run_as_one_transaction():
    sc = option_fixture()
    model = compiled(sc, library())
    edits = edits_of(model, {'set': {'service.factor': -1}})
    for name, item in Runs.from_table(model.run_table).resolve(edits).items():
        with pytest.raises(ModelError) as raised:
            model.resolve(name, item.values)
        assert any(d['code'] == 'initial_bound' for d in raised.value.diagnostics)


def test_a_study_validates_an_edit_in_every_run_as_one_transaction():
    model = compiled(option_fixture(), library())
    result = evaluate_study(model, edits_of(model, {'set': {'service.factor': -1}}))
    assert not result.admissible
    assert result.runs == {}
    assert any(item['code'] == 'initial_bound' for item in result.diagnostics)


def unused_response_fixture(factor=1):
    return edit(
        scenario(),
        member('service', parameter('factor', 1, 'fraction', 0, 1)),
        replace('rate if state is "on"', 'rate / factor if state is "on"'),
        member('options:/Response/Default', f'service.factor = 1  {BASIS}'),
        member(
            'options:/Response', option('Unused', 'No run takes it.', f'service.factor = {factor}  {BASIS}')
        ),
    )


def test_an_unused_response_receives_arithmetic_domain_validation():
    sc = unused_response_fixture(0)
    with pytest.raises(ModelError):
        compiled(sc, library())


def test_an_edit_of_an_unused_response_is_validated_in_each_combination_that_takes_it():
    """No run takes Unused, so an edit of it changes no run of the model. Each run with Unused in place
    of its response is a combination that takes the edit, and there a zero factor divides by zero."""
    sc = unused_response_fixture()
    model = compiled(sc, library())
    edits = edits_of(model, {'options': {'Unused': {'service.factor': 0}}})
    table = Runs.from_table(model.run_table)
    assert table.resolve(edits) == table.resolve()
    for name in model.runs:
        combined = model.combination(name, ['Unused'])
        (resolved,) = Runs.from_table(combined.run_table).resolve(edits).values()
        assert resolved.values['service.factor'] == 0
        with pytest.raises(ModelError) as caught:
            combined.resolve(name, resolved.values)
        assert 'dynamic_domain' in {d['code'] for d in caught.value.diagnostics}


def test_a_study_validates_an_unused_response_atomically_where_it_is_asked_for():
    """A study of the runs admits the edit of Unused, which reaches none of them. A study of a
    combination that takes Unused rejects it as one transaction, and keeps no run."""
    model = compiled(unused_response_fixture(), library())
    edits = edits_of(model, {'options': {'Unused': {'service.factor': 0}}})
    assert evaluate_study(model, edits).admissible
    result = evaluate_study(model.combination('a', ['Unused']), edits)
    assert not result.admissible
    assert result.runs == {}


def test_one_transaction_validates_each_run_once_and_preserves_admission(monkeypatch):
    sc = edit(scenario(), replace(RATE_RUNS, runs(**{f'v{i}': ['Default'] for i in range(6)})))
    model = compiled(sc, library())
    calls = []
    original = model_module.resolve_structure

    def record_validation(structure, source, lib, values, context, **options):
        calls.append(context)
        return original(structure, source, lib, values, context, **options)

    monkeypatch.setattr(model_module, 'resolve_structure', record_validation)
    result = evaluate_study(model, edits_of(model, {'set': {'service.n': 20}}))
    assert result.admissible, result.diagnostics
    assert sorted(calls) == [f'runs/{name}' for name in sorted(model.runs)]
    rejected = evaluate_study(model, edits_of(model, {'runs': {'v5': {'service.rate': 100}}}))
    assert not rejected.admissible and rejected.runs == {}


def validate_report(report):
    schema = json.loads((SCHEMAS / 'report.schema.json').read_text())
    Draft202012Validator(schema).validate(json.loads(json.dumps(report, allow_nan=False)))


def test_reports_share_one_envelope_across_admission_and_failure(monkeypatch):
    model = compiled(scenario(), library())
    accepted = evaluate_study(model)
    report = sample_result(accepted)
    validate_report(report)
    rejected = sample_result(evaluate_study(model, {'schema_version': SCHEMA_VERSION, 'model_hash': 'stale'}))
    validate_report(rejected)

    def fail_health(*args, **kwargs):
        raise report_module.ReportingError('Injected reporting failure')

    monkeypatch.setattr(report_module, 'health', fail_health)
    failed = sample_result(accepted)
    validate_report(failed)
    assert set(report) == set(rejected) == set(failed)
    assert rejected['runs'] == failed['runs'] == {}
    assert failed['diagnostics'][-1]['code'] == 'reporting_failure'
    failed['diagnostics'].append({'severity': 'error', 'message': 'Caller edit'})
    assert accepted.diagnostics == []


@pytest.mark.parametrize('value', [float('nan'), float('inf'), 10**500, object()])
def test_rejected_python_edits_produce_serializable_reports(value):
    model = compiled(scenario(), library())
    report = sample_result(evaluate_study(model, edits_of(model, {'set': {'service.n': value}})))
    assert not report['admissible'] and report['runs'] == {}
    assert report['effective_edits']['set']['service.n'] is None
    validate_report(report)


@pytest.mark.parametrize('field', ['rtol', 'atol_factor', 'max_step'])
def test_boolean_numerical_settings_are_rejected(field):
    model = compiled(scenario(), library())
    result = evaluate_study(model, numerical_settings={field: True})
    assert not result.admissible and result.runs == {}
    validate_report(sample_result(result))


def test_boolean_reporting_time_is_rejected():
    result = evaluate_study(compiled(scenario(), library()))
    with pytest.raises(ValueError):
        sample_result(result, [True])


def test_expression_cache_releases_old_trees_and_preserves_lazy_semantics(monkeypatch):
    import napkin.expressions as expressions
    from napkin.core import evaluation, expr

    monkeypatch.setattr(evaluation, 'LIMIT', 8)
    for number in range(32):
        source = f'{number} if ok else 1/zero'
        expression = expressions.compile_expression(
            expr.read(source),
            {'ok': expressions.BOOLEAN, 'zero': expressions.NUMBER},
            expressions.UnitSystem(library()['units']),
        )
        assert expression.evaluate({'ok': True, 'zero': 0}) == number
    assert len(evaluation._FUNCTIONS) <= 8
    assert (
        expressions.evaluate(expr.read('0 if ok else 1/zero'), {'ok': True, 'zero': 0}, library()['units'])
        == 0
    )


def autonomous_pulse_model():
    """The pulse of the forcing fixture, driven by an evolving clock number instead of `t`."""
    pulse = '1 people/h + 1000 people/h * exp(- ((clock - 0.45 h) / 0.01 h) ** 2)'
    clock = stock('clock', 0, 'h', minimum=None, size=1, kind='state', rate='1 fraction')
    return edit(
        forcing_fixture('0'),
        drop('service/forcing'),
        replace('-> served at forcing', f'-> served at {pulse}'),
        member('service', clock),
    )


def test_autonomous_clock_preserves_narrow_gaussian_mass():
    # clock'=1, clock(0)=0 gives clock(t)=t. Substitution u=(t-.45)/.01
    # gives 1+5*sqrt(pi)*(erf(55)-erf(-45)), independently of the solver.
    sc = autonomous_pulse_model()
    expected = 1 + 5 * math.sqrt(math.pi) * (math.erf(55) - math.erf(-45))
    for name in compiled(sc).runs:
        _, trajectory = run(sc, name)
        assert trajectory.env_at(1)['service.served'] == pytest.approx(expected, abs=1e-8)


def test_the_effective_edits_resolve_the_values_the_study_ran():
    model = compiled(scenario(), library())
    study = evaluate_study(model, edits_of(model, {'set': {'service.n': 20}}))
    assert study.admissible, study.diagnostics
    values = Runs.from_table(model.run_table).resolve(study.effective_edits)['a'].values
    assert model.resolve('a', values).parameter_values['service.n'] == 20


@pytest.mark.parametrize('kind', ['opaque', 'cycle'])
def test_rejected_python_inputs_always_produce_json_envelope(kind):
    model = compiled(scenario(), library())
    edits = edits_of(model, {'set': {'service.n': threading.Lock() if kind == 'opaque' else None}})
    if kind == 'cycle':
        edits['set']['service.n'] = edits
    study = evaluate_study(model, edits)
    assert not study.admissible
    assert study.diagnostics[0]['path'] == 'edits/set/service.n'
    report = sample_result(study)
    assert report['admissible'] is False and report['runs'] == {}
    assert report['effective_edits']['set']['service.n'] is None
    json.dumps(report, allow_nan=False)


@pytest.mark.parametrize('time', [-1, 25])
def test_rejected_study_checks_requested_reporting_time_bounds(time):
    model = compiled(scenario(), library())
    rejected = evaluate_study(model, {'schema_version': SCHEMA_VERSION, 'model_hash': 'stale'})
    assert not rejected.admissible and rejected.runs == {}
    with pytest.raises(ValueError):
        sample_result(rejected, [time])


def layered_fixture():
    """Three defender responses, each run with and without hidden access, with one input that the
    responses set and one that they do not: the shape of a catalogue case's runs."""
    responses = options(
        'Response',
        option('Near ideal', 'Early.', f'service.act_h = 4 h  {BASIS}'),
        option('Subpar', 'Delayed.', f'service.act_h = 18 h  {BASIS}'),
        option('Minimal', 'Limited.', f'service.act_h = 36 h  {BASIS}'),
    )
    access = options(
        'Access',
        option('Keeps access', 'The attacker keeps its access.', f'service.access = "kept"  {BASIS}'),
    )
    named_runs = {
        response.lower().replace(' ', '_') + suffix: [response, *extra]
        for response in ('Near ideal', 'Subpar', 'Minimal')
        for suffix, extra in (('', []), ('_persistent', ['Keeps access']))
    }
    return edit(
        scenario(),
        member(
            'service',
            parameter('act_h', 4, 'h', 2, 48),
            parameter('places', 230000, 'people', 25000, 400000),
            named('access', 'none', 'kept'),
        ),
        replace('\n\n'.join(RATE_OPTIONS), f'{responses}\n\n{access}'),
        replace(RATE_RUNS, runs(**named_runs)),
    )


def test_edits_layer_by_level_across_runs():
    sc = layered_fixture()
    model = compiled(sc, library())
    edits = edits_of(
        model,
        {
            'set': {'service.places': 250000},
            'options': {'Subpar': {'service.act_h': 24}, 'Minimal': {'service.act_h': 40}},
        },
    )
    resolved = Runs.from_table(model.run_table).resolve(edits, model_hash=model.model_hash)

    def values(name):
        return model.resolve(name, resolved[name].values).parameter_values

    # An option's edit follows the option into every run that names it.
    assert values('subpar')['service.act_h'] == values('subpar_persistent')['service.act_h'] == 24
    assert values('minimal')['service.act_h'] == values('minimal_persistent')['service.act_h'] == 40
    # An untouched response keeps its option's value; an edit of every run reaches every run.
    assert (
        values('near_ideal')['service.act_h']
        == model.inputs['service.act_h']['options']['Near ideal']['value']
    )
    assert {values(name)['service.places'] for name in model.runs} == {250000}


def test_disconnected_bounds_are_candidates_not_false_safe_interval():
    regions = check('service.n <= 20 people or service.n >= 80 people', 'Disconnected feasible regions')
    sc = edit(scenario(), replace('\noutput delivered', f'\n{regions}\n\noutput delivered'))
    model = compiled(sc, library())
    bounds = analyze_bounds(model, {}, {'input': 'service.n', 'level': 'set'})
    assert not bounds['certified'] and bounds['status'] == 'unresolved'
    assert any(p['admissible'] for p in bounds['checked_points'])
    assert any(not p['admissible'] for p in bounds['checked_points'])


def two_milestones(first, second):
    """Two entities, each with a milestone at its own input time."""
    things = [
        entity(
            name,
            parameter(field, value, 'h', 1, 10),
            named('state', *values),
            event(
                'milestone',
                f't >= {field}',
                once=False,
                transition=f'state "{values[0]}" -> "{values[1]}"',
                doc=name,
            ),
            doc=f'The entity {name}.',
            title=title,
        )
        for name, title, field, value, values in (
            (first, 'First', 't_first', 5, ['quiet', 'raised']),
            (second, 'Second', 't_second', 6, ['idle', 'sent']),
        )
    ]
    return edit(
        scenario(), replace('\nassert service.end', '\n' + '\n\n'.join(things) + '\n\nassert service.end')
    )


def test_events_of_one_moment_go_in_the_order_of_their_lines_whatever_their_names():
    """Events of one moment go one at a time, in the order of their lines, whatever their names."""

    def milestones(trajectory, first, second):
        """(entity, time, step within the moment) of each milestone, in trace order."""
        names = {f'{first}.milestone': first, f'{second}.milestone': second}
        return [(names[e['rule']], e['t'], e['step']) for e in trajectory.trace if e['rule'] in names]

    # The entity names order the two triggers one way, then the other.
    for first, second in (('alarm', 'crew'), ('zalarm', 'crew')):
        s = two_milestones(first, second)
        _, trajectory = run(s)
        assert [m[:2] for m in milestones(trajectory, first, second)] == [(first, 5), (second, 6)]
        _, trajectory = run(s, values={f'{first}.t_first': 6, f'{second}.t_second': 5})
        assert [m[:2] for m in milestones(trajectory, first, second)] == [(second, 5), (first, 6)]
        # Tied at 5 h: both at one moment, one step after the other, and the line of `first` comes
        # first in the file.
        _, trajectory = run(s, values={f'{first}.t_first': 5, f'{second}.t_second': 5})
        tied = milestones(trajectory, first, second)
        assert [m[:2] for m in tied] == [(first, 5), (second, 5)]
        assert tied[1][2] == tied[0][2] + 1


def test_bounds_for_an_option_no_run_takes_are_a_clear_error():
    spare = options('Spare option', option('Spare', 'Unused option.', f'service.end = 6 h  {BASIS}'))
    s = edit(scenario(), replace('\nruns:', f'\n{spare}\n\nruns:'))
    model = compiled(s, library())
    with pytest.raises(ValueError, match='No run'):
        analyze_bounds(model, None, {'input': 'service.end', 'level': 'options', 'name': 'Spare'})
