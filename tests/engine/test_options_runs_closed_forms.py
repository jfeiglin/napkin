"""Options, runs and the precedence of edits, through the engine, with independent outcomes.

The fixture is the analytic transfer (tests/build.py) with two defender responses, Fast response and
Slow response, that set the delivery rate, and an option, Impaired delivery, that halves it. The
served total at the horizon is min(n, rate * attenuation * end): the expectations below come from that
closed form, on values that the options and the edits of each test set. A run's values come from the
edit document (`napkin/model/runs.py`); `model.resolve` checks them and gives the engine
what it runs.
"""

import pytest

from napkin import SCHEMA_VERSION
from napkin.engine import analyze_bounds, evaluate_study, sample_result
from napkin.engine.report import evaluate_outputs
from napkin.engine.runtime import simulate
from napkin.model import ModelError
from napkin.model.language import front
from napkin.model.language.resolve import resolve
from napkin.model.runs import Runs
from tests.build import (
    BASIS,
    RATE_OPTIONS,
    RATE_RUNS,
    block,
    check,
    compiled,
    drop,
    edit,
    indent,
    library,
    member,
    option,
    options,
    output,
    parameter,
    q,
    rejected,
    replace,
    runs,
    scenario,
)
from tests.owned import block_at

DAY = 24  # the rates are people a day, the times hours


def lines_at(text, place):
    """The rows of the line at `place` and of the lines under it."""
    return block_at(text, place).rstrip('\n')


def table_of(text, lib=None):
    """The runs' table of a text (`Runs`), read from its semantic model, without building its model."""
    lib = lib or library()
    scenario_model, _ = resolve(front.read(text, 'test.scn'), lib)
    return Runs.from_scenario(scenario_model, lib)


def transfer(*members, groups, named_runs, delivery):
    """The transfer with more `members` of the service, the delivery rate `delivery`, the groups of
    profiles `groups` in place of its own, and `named_runs`."""
    return edit(
        scenario(),
        member('service', *members),
        replace('rate if state is "on"', f'{delivery} if state is "on"'),
        replace('\n\n'.join(RATE_OPTIONS), '\n\n'.join(groups)),
        replace(RATE_RUNS, runs(**named_runs)),
    )


def response_model(*steps):
    """The rate is the response's, and the attenuation the option's."""
    responses = options(
        'Response',
        option('Fast response', 'Delivery at full pace.', f'service.rate = {q(24, "people/day")}  {BASIS}'),
        option('Slow response', 'Delivery at half pace.', f'service.rate = {q(12, "people/day")}  {BASIS}'),
    )
    delivery = options(
        'Delivery',
        option(
            'Impaired delivery',
            'An attack halves what the service delivers.',
            f'service.attenuation = 0.5  {BASIS}',
        ),
    )
    text = transfer(
        parameter('attenuation', 1, 'fraction', 0.1, 1),
        groups=(responses, delivery),
        named_runs={
            'fast_base': ['Fast response'],
            'fast_impaired': ['Fast response', 'Impaired delivery'],
            'slow_base': ['Slow response'],
        },
        delivery='rate * attenuation',
    )
    return edit(text, *steps)


def edit_document(model, edits=None):
    return {'schema_version': SCHEMA_VERSION, 'model_hash': model.model_hash, **(edits or {})}


def delivered(sc, edits=None, lib=None):
    """{run: the served total at the horizon} of every run under an edit document, and the values
    that each run resolved."""
    lib = lib or library()
    model = compiled(sc, lib)
    resolved = table_of(sc, lib).resolve(edit_document(model, edits), model_hash=model.model_hash)
    totals, values = {}, {}
    for name, item in resolved.items():
        rs = model.resolve(name, item.values)
        trajectory = simulate(rs, lib)
        row = evaluate_outputs({'resolved': rs, 'trajectory': trajectory}, lib, [model.time['horizon']])[0]
        totals[name] = row['values']['delivered']
        values[name] = rs.parameter_values
    return totals, values


def served(values):
    """The closed form of the served total: min(n, rate * attenuation * end)."""
    rate = values['service.rate'] / DAY * values.get('service.attenuation', 1)
    return min(values['service.n'], rate * values['service.end'])


def setting(model, profile_name, target):
    """What a profile writes for `target` (`entity.value`), as the model holds it: the value and its
    records."""
    entity, _, member = target.rpartition('.')
    for item in model.scenario.entity(entity).settings:
        if item.profile == profile_name and item.target == member:
            assert set(item.written) == {'value', 'basis'}
            return item.written
    raise KeyError((profile_name, target))


def test_the_file_takes_no_schema_version_and_a_run_takes_no_default_option():
    # A schema version line in the file and a library of another schema version are rejected.
    sc = response_model(member('scenario:', 'schema_version "3.0.0"'))
    with pytest.raises(ModelError) as raised:
        compiled(sc, library())
    assert [(d['code'], d['line']) for d in raised.value.diagnostics] == [
        ('syntax', sc.split('\n').index('    schema_version "3.0.0"') + 1)
    ]
    # A run without an option of a group is a run like any other.
    sc = response_model(replace('slow_base = "Slow response"', 'slow_base = "Impaired delivery"'))
    assert compiled(sc, library()).runs['slow_base']['options'] == ('Impaired delivery',)
    old = library()
    old['schema_version'] = '1.0.0'
    with pytest.raises(ModelError):
        compiled(response_model(), old)


def bare_transfer():
    """The analytic transfer without its options and its runs."""
    return edit(scenario(), drop('options:/Response', 'options:/Rate', 'runs:'))


def test_a_model_without_runs_and_options_has_one_run_base():
    """The transfer without options and runs has one run, `base`, which takes the values as the file
    writes them. Edits of every run and of the run, by its name, reach it, and the report gives the
    run with no options."""
    sc = bare_transfer()
    model = compiled(sc)
    assert model.menu == {} and list(model.runs) == ['base']
    assert (model.runs['base']['options'], model.runs['base']['name']) == ((), 'base')
    totals, values = delivered(sc)
    assert values['base'] == model.run_values('base')
    assert totals['base'] == pytest.approx(served(values['base']))
    totals, values = delivered(sc, {'set': {'service.n': 4}, 'runs': {'base': {'service.end': 2}}})
    assert (values['base']['service.n'], values['base']['service.end']) == (4, 2)
    assert totals['base'] == pytest.approx(served(values['base']))
    report = sample_result(evaluate_study(model))
    assert (report['runs']['base']['options'], report['runs']['base']['label']) == ([], 'base')


def test_a_model_with_options_names_its_runs():
    """Only a model without options has the run `base`: a model with options and no runs is refused at
    its menu, before anything is built."""
    sc = edit(scenario(), drop('runs:'))
    assert rejected(sc, library()) == {('structure', 'options:/Response')}


def test_a_response_option_edit_follows_every_run_that_names_the_option():
    model = compiled(response_model())
    before = model.resolve('fast_impaired')
    assert list(before.options) == ['Fast response', 'Impaired delivery']
    # 24 people a day is one person an hour in execution units.
    assert before.parameter_values['service.rate'] == 24 and before.values['service.rate'] == 1
    totals, values = delivered(response_model(), {'options': {'Fast response': {'service.rate': 12}}})
    for name in ('fast_base', 'fast_impaired', 'slow_base'):
        assert totals[name] == pytest.approx(served(values[name]))
    # 12 h at 12 people a day is six people; the impaired run delivers half.
    assert totals == pytest.approx({'fast_base': 6, 'fast_impaired': 3, 'slow_base': 6})
    assert values['slow_base']['service.rate'] == 12 == values['fast_impaired']['service.rate']
    # The edit changed no value of the model.
    assert model.resolve('fast_base').parameter_values['service.rate'] == 24
    with pytest.raises(TypeError):
        setting(model, 'Fast response', 'service.rate')['value'] = 99


def test_the_narrower_edit_wins_in_every_run():
    edits = {
        'set': {'service.rate': 30, 'service.n': 100},
        'options': {'Slow response': {'service.rate': 18}},
        'runs': {'fast_impaired': {'service.rate': 48}},
    }
    totals, values = delivered(response_model(), edits)
    # One run, then one option, then every run.
    assert {name: v['service.rate'] for name, v in values.items()} == {
        'fast_base': 30,
        'fast_impaired': 48,
        'slow_base': 18,
    }
    for name, total in totals.items():
        assert total == pytest.approx(served(values[name]))
    assert totals == pytest.approx({'fast_base': 15, 'fast_impaired': 12, 'slow_base': 9})


def fixed_n(text):
    """Make the people served a fixed value, which no option and no edit can change."""
    return edit(
        text, replace(lines_at(text, 'service/n'), indent(parameter('n', 10, 'people', doc='People')))
    )


@pytest.mark.parametrize(
    'change, path',
    [
        # An option value outside its input's range.
        (
            lambda s: edit(
                s, replace('service.rate = 24 people/day', f'service.rate = {q(100, "people/day")}')
            ),
            'values/service.rate',
        ),
        # An option of another group that sets the input of the defender responses.
        (
            lambda s: edit(
                s,
                member(
                    'options:/Delivery/Impaired delivery', f'service.rate = {q(12, "people/day")}  {BASIS}'
                ),
            ),
            'options:/Response/Fast response/service.rate',
        ),
        # A run that names an option that is not in the menu.
        (
            lambda s: edit(s, replace('slow_base = "Slow response"', 'slow_base = "Missing response"')),
            'runs:/slow_base',
        ),
        # An option that sets a fixed value.
        (
            lambda s: edit(
                fixed_n(s),
                member('options:/Response/Fast response', f'service.n = {q(20, "people")}  {BASIS}'),
            ),
            'options:/Response/Fast response/service.n',
        ),
    ],
    ids=[
        '<lambda>-values/service.rate',
        '<lambda>-classes/Service/options/Fast response/rate',
        '<lambda>-simulate/runs/slow_base',
        '<lambda>-classes/Service/options/Fast response/n',
    ],
)
def test_the_options_of_a_run_are_checked_when_the_model_is_built(change, path):
    sc = change(response_model())
    assert path in {where for _, where in rejected(sc, library())}


def test_a_non_finite_option_value_is_a_model_error():
    # 1e999 is too large for a number of the machine: it reads as infinity.
    sc = response_model(replace('service.rate = 12 people/day', 'service.rate = 1e999 people/day'))
    with pytest.raises(ModelError):
        compiled(sc)


def test_an_option_that_no_run_names_is_still_checked():
    """A defender response that no run names is a choice that the pages offer with the other options of
    each run: its values are checked with the document, and the model is not built."""
    unused = option('Unused', 'An unused response outside the range.', f'service.rate = 0  {BASIS}')
    sc = response_model(member('options:/Response', unused))
    found = table_of(sc).problems
    assert [(d['code'], d['path']) for d in found] == [
        ('bounds', 'options:/Response/Unused/service.rate/value')
    ]
    with pytest.raises(ModelError):
        compiled(sc)


def paced_model(unused_pause=0):
    """A delivery that divides by a reaction time, which an unused response sets to zero."""
    responses = options(
        'Response',
        option('Selected reaction', 'A positive reaction time.', f'service.pause = {q(2, "h")}  {BASIS}'),
        option(
            'Unused zero reaction', 'No run takes it.', f'service.pause = {q(unused_pause, "h")}  {BASIS}'
        ),
    )
    return transfer(
        parameter('pause', 2, 'h', 0, 10),
        groups=(responses,),
        named_runs={'a': ['Selected reaction']},
        delivery='rate * 1 h / pause',
    )


def test_every_option_that_no_run_names_is_checked_with_the_other_options_of_each_run():
    sc = paced_model()
    assert table_of(sc).unnamed_choices() == [('Unused zero reaction',)]
    # That choice divides by zero: the model of the file is not built, and the fault names the choice.
    with pytest.raises(ModelError) as caught:
        compiled(sc)
    found = [d for d in caught.value.diagnostics if d['code'] == 'dynamic_domain']
    assert found and all('Unused zero reaction' in str(d.get('context', '')) for d in found)
    # With a positive pause, the model builds, and the combination, asked for, runs.
    combined = compiled(paced_model(1)).combination('a', ['Unused zero reaction'])
    assert combined.runs['a']['options'] == ('Unused zero reaction',)
    assert evaluate_study(combined).admissible


def offset_model():
    """A delivery that divides by the pause less an offset that the option Offset sets. Run `a` takes
    the selected reaction alone, run `b` the other reaction with the offset: the selected reaction with
    the offset is a combination that no run makes. Built as authored, every pause less offset is
    positive (2 - 0, 3 - 1, 2 - 1, 3 - 0)."""
    responses = options(
        'Response',
        option('Selected reaction', 'A positive reaction time.', f'service.pause = {q(2, "h")}  {BASIS}'),
        option('Other reaction', 'A slower one.', f'service.pause = {q(3, "h")}  {BASIS}'),
    )
    timing = options(
        'Timing',
        option('Offset', 'The reaction starts one hour early.', f'service.offset = {q(1, "h")}  {BASIS}'),
    )
    return transfer(
        parameter('pause', 2, 'h', 0, 10),
        parameter('offset', 0, 'h', 0, 5),
        groups=(responses, timing),
        named_runs={'a': ['Selected reaction'], 'b': ['Other reaction', 'Offset']},
        delivery='rate * 1 h / (pause - offset)',
    )


def test_a_combination_that_no_run_makes_is_checked_when_it_is_asked_for():
    """Every option is in a run, and the model builds. An edit of the selected reaction, which run `a`
    takes without the offset, divides by zero only with the offset (1 - 1), a combination that no run
    makes: the study of the runs admits it, and the combination, asked for, rejects it under the same
    edit. With a longer pause, it admits it."""
    model = compiled(offset_model())
    edits = edit_document(model, {'options': {'Selected reaction': {'service.pause': 1}}})
    assert evaluate_study(model, edits).admissible
    combined = model.combination('a', ['Offset'])
    assert combined.runs['a']['options'] == ('Selected reaction', 'Offset')
    result = evaluate_study(combined, edits)
    assert not result.admissible and result.runs == {}
    found = [d for d in result.diagnostics if d['code'] == 'dynamic_domain']
    assert found and all(d['run'] == 'a' for d in found)
    edits = edit_document(model, {'options': {'Selected reaction': {'service.pause': 1.5}}})
    assert evaluate_study(combined, edits).admissible


@pytest.mark.parametrize(
    'edits, code',
    [
        ({'options': {'Unknown response': {'service.rate': 12}}}, 'reference'),
        ({'options': {'Fast response': {'service.rate': 100}}}, 'bounds'),
        ({'options': {'Fast response': {'service.rate': True}}}, 'value'),
        ({'set': {'service.ghost': 12}}, 'input'),
        ({'runs': {'ghost': {'service.rate': 12}}}, 'reference'),
        ({'runs': {'fast_base': {'service.rate': 0}}}, 'bounds'),
    ],
)
def test_one_validator_checks_every_level_of_an_edit_document(edits, code):
    sc = response_model()
    model = compiled(sc)
    document = edit_document(model, edits)
    assert code in {d['code'] for d in table_of(sc).errors(document, model.model_hash)}
    with pytest.raises(ModelError):
        table_of(sc).resolve(document, model_hash=model.model_hash)


def test_an_edit_document_of_another_model_or_shape_is_rejected():
    sc = response_model()
    model = compiled(sc)
    stale = {'schema_version': SCHEMA_VERSION, 'model_hash': 'stale'}
    assert {d['code'] for d in table_of(sc).errors(stale, model.model_hash)} == {'model_hash'}
    # An option that no run takes takes an edit, which changes no run; a fixed value takes none, not
    # even its own value.
    unused = option('Unused option', 'No run takes it.', f'service.attenuation = 0.25  {BASIS}')
    sc = response_model(member('options:/Delivery', unused))
    edits = edit_document(model, {'options': {'Unused option': {'service.n': 20}}})
    assert table_of(sc).errors(edits) == []
    assert table_of(sc).resolve(edits) == table_of(sc).resolve()
    sc = fixed_n(response_model())
    table = table_of(sc)
    value = table.inputs['service.n'].value
    found = table.errors(edit_document(model, {'set': {'service.n': value}}))
    assert {(d['code'], d['path']) for d in found} == {('locked', 'edits/set/service.n')}


@pytest.mark.parametrize('edits', [[], [1], False, 42, 'invalid'])
def test_an_edit_document_that_is_not_an_object_has_a_shape_error(edits):
    result = evaluate_study(compiled(response_model()), edits)
    assert not result.admissible and result.runs == {}
    assert result.diagnostics and result.diagnostics[0]['code'] == 'edits_shape'


def capped_model():
    cap = check(
        'service.rate <= 24 people/day if service.attenuation < 1 else true',
        'An impaired delivery cannot take a higher nominal response.',
    )
    return response_model(replace('\noutput delivered', f'\n{cap}\n\noutput delivered'))


def test_one_option_edit_that_breaks_a_check_in_one_run_breaks_it_only_there():
    sc = capped_model()
    model = compiled(sc)
    resolved = table_of(sc).resolve(
        edit_document(model, {'options': {'Fast response': {'service.rate': 36}}})
    )
    with pytest.raises(ModelError) as caught:
        model.resolve('fast_impaired', resolved['fast_impaired'].values)
    assert {d['code'] for d in caught.value.diagnostics} == {'check:simulate.1'}
    for name in ('fast_base', 'slow_base'):
        model.resolve(name, resolved[name].values)


def test_a_blocking_check_rejects_an_edit_before_any_run(monkeypatch):
    """The edit breaks the check in the impaired run, so the whole edit is rejected with that check, before any run and before any proof that the edit makes fail."""
    import napkin.engine.study as study

    model = compiled(capped_model())
    ran = []
    real = study.simulate

    def counted(rs, *args):
        ran.append(rs.run)
        return real(rs, *args)

    monkeypatch.setattr(study, 'simulate', counted)
    result = evaluate_study(model, edit_document(model, {'options': {'Fast response': {'service.rate': 36}}}))
    assert not result.admissible and ran == [] and result.runs == {}
    errors = [d for d in result.diagnostics if d.get('severity') == 'error']
    assert {d['code'] for d in errors} == {'check:simulate.1'}


def test_a_blocking_check_is_reported_instead_of_a_proof_the_edit_breaks():
    kept = output('kept', 'service.served * service.share', 'people', 'instantaneous', doc='Kept')
    share = check('service.share >= 0', 'A share cannot be negative')
    sc = edit(
        scenario(),
        member('service', parameter('share', 0.5, 'fraction', -1, 1)),
        replace('\noutput delivered', f'\n{share}\n\noutput delivered'),
        replace('\noptions "Response":', f'\n{kept}\n\noptions "Response":'),
    )
    model = compiled(sc)
    # A negative share breaks the check and, with it, the claim that `kept` is never negative.
    for name in model.runs:
        with pytest.raises(ModelError) as caught:
            model.resolve(name, {'service.share': -0.5})
        assert {d['code'] for d in caught.value.diagnostics} == {'check:simulate.1'}


def test_the_bounds_of_a_response_input_are_candidates_that_probe_every_run():
    model = compiled(response_model())
    bounds = analyze_bounds(
        model, None, {'input': 'service.rate', 'level': 'options', 'name': 'Fast response'}
    )
    assert bounds['certified'] is False and bounds['status'] == 'unresolved'
    assert bounds['candidates'][0]['min'] == 1 and bounds['candidates'][0]['max'] == 48
    assert bounds['checked_points']


def test_malformed_waiting_methods_fail_the_reader_before_the_build():
    change = 'state = "off"'

    def with_event(*lines):
        shut_down = block(f'event shut_down once when t >= {q(1, "h")}:  {BASIS}', *lines)
        return edit(scenario(), member('service', shut_down))

    compiled(with_event(change))
    invalid = [
        # A line of no event.
        ((change, 'execute_python: pass'), 'syntax'),
    ]
    for lines, code in invalid:
        assert {found for found, _ in rejected(with_event(*lines), library())} == {code}


def paired_response_fixture():
    """A transparent rate x time oracle: two responses, each run with and without half delivery."""
    responses = options(
        'Response',
        option('Fast', 'Full pace.', f'service.rate = {q(24, "people/day")}  {BASIS}'),
        option('Slow', 'Half pace.', f'service.rate = {q(12, "people/day")}  {BASIS}'),
    )
    delivery = options(
        'Delivery',
        option('Half delivery', 'Half of each delivery arrives.', f'service.share = 0.5  {BASIS}'),
    )
    return transfer(
        parameter('share', 1, 'fraction', 0.1, 1),
        groups=(responses, delivery),
        named_runs={
            'a': ['Fast'],
            'b': ['Slow'],
            'c': ['Fast', 'Half delivery'],
            'd': ['Slow', 'Half delivery'],
        },
        delivery='rate * share',
    )


def test_a_response_edit_changes_every_run_of_the_response_and_no_other():
    baseline, _ = delivered(paired_response_fixture())
    totals, values = delivered(paired_response_fixture(), {'options': {'Fast': {'service.rate': 12}}})
    # Twelve hours at 12 people a day give six people; the half delivery gives three. Neither result is
    # taken from a run of the authored values.
    assert totals == pytest.approx({'a': 6, 'b': 6, 'c': 3, 'd': 3})
    for name in ('b', 'd'):
        assert totals[name] == baseline[name]
    assert values['a']['service.rate'] == values['c']['service.rate'] == 12
    # An edit of one run is narrower than the edit of its response, and reaches that run only.
    totals, values = delivered(
        paired_response_fixture(),
        {'options': {'Fast': {'service.rate': 12}}, 'runs': {'c': {'service.rate': 6}}},
    )
    assert (values['a']['service.rate'], values['c']['service.rate']) == (12, 6)
    assert totals == pytest.approx({'a': 6, 'b': 6, 'c': 1.5, 'd': 3})
