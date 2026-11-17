"""Combinations of options that no run makes, asked for one at a time (`Model.combination`).

The fixture is the analytic transfer (tests/build.py), which serves min(n, rate * end) people by the
horizon, with the rate a day over 24 hours. Its runs are `a` (Default), `b` (Default and Half rate)
and `c` (Fast, which stops the service later). Every option is in a run, so the build checks only the
runs. The Fast response with the half rate is a combination that no run makes. A check of the inputs
that the test can add forbids a slow rate in a service that stops late, and that combination breaks
it. Every expectation comes from the closed form, with values that the test reads from the model or
edits itself.
"""

import pytest

from napkin.engine import edits_for, evaluate_study, sample_result
from napkin.model import ModelError
from napkin.model.runs import Runs
from tests.build import (
    BASIS,
    RATE_OPTIONS,
    RATE_RUNS,
    check,
    compiled,
    edit,
    option,
    options,
    replace,
    runs,
    scenario,
)

SLOW = check('service.rate >= 18 people/day or service.end <= 12 h', 'A slow service stops early.')


def fixture(*steps, checked=False):
    """The transfer with the Response options Default and Fast, the Rate option Half rate and the runs
    a, b and c; with `checked`, also the check that a slow rate breaks when the service stops late."""
    responses = options(
        'Response',
        option('Default', 'The defaults.'),
        option('Fast', 'The service stops later.', f'service.end = 20 h  {BASIS}'),
    )
    rates = options(
        'Rate', option('Half rate', 'Half the delivery rate.', f'service.rate = 12 people/day  {BASIS}')
    )
    text = edit(
        scenario(),
        replace('\n\n'.join(RATE_OPTIONS), f'{responses}\n\n{rates}'),
        replace(RATE_RUNS, runs(a=['Default'], b=['Default', 'Half rate'], c=['Fast'])),
        *([replace('\noutput delivered', f'\n{SLOW}\n\noutput delivered')] if checked else []),
    )
    return edit(text, *steps)


def served(values):
    """The closed form of the people served by the horizon: min(n, rate * end)."""
    return min(values['service.n'], values['service.rate'] / 24 * values['service.end'])


def final(study, run):
    return sample_result(study)['runs'][run]['reporting_points']['final']


def option_value(model, name, option):
    return model.inputs[name]['options'][option]['value']


def test_a_combination_is_checked_only_when_it_is_asked_for():
    """The Fast response with the half rate breaks the check, and no run makes it: the model builds,
    and its study admits every run. Asked for, the combination is rejected with the check, and its
    diagnostics give its options."""
    model = compiled(fixture(checked=True))
    assert evaluate_study(model).admissible
    with pytest.raises(ModelError) as caught:
        model.combination('c', ['Half rate'])
    checks = next(iter(model.structures.values())).input_checks
    (slow,) = (cid for cid, item in checks.items() if 'service.rate' in str(item.expr))
    assert [(d['code'], d['options']) for d in caught.value.diagnostics] == [
        (f'check:{slow}', ['Fast', 'Half rate'])
    ]


def test_a_combination_takes_the_edits_of_every_run_of_its_options_and_of_its_run():
    """The combination of run `b` with Fast is b's Half rate with Fast in place of Default. An edit
    document gives it its values as it gives them to a run: an edit of every run, then of each of its
    options, then of the run, by its name, wins. An edit of an option that it does not take reaches
    it not."""
    model = compiled(fixture())
    combined = model.combination('b', ['Fast'])
    assert list(combined.runs) == ['b'] and combined.runs['b']['options'] == ('Fast', 'Half rate')
    edits = edits_for(
        model,
        {
            'set': {'service.n': 4, 'service.rate': 30},
            'options': {
                'Half rate': {'service.rate': 6},
                'Fast': {'service.end': 16},
                'Default': {'service.end': 2},
            },
            'runs': {'b': {'service.n': 8}},
        },
    )
    study = evaluate_study(combined, edits)
    assert study.admissible, study.diagnostics
    values = study.runs['b']['resolved'].parameter_values
    assert (values['service.n'], values['service.rate'], values['service.end']) == (8, 6, 16)
    origins = Runs.from_table(combined.run_table).values_of(('Fast', 'Half rate'), edits, 'b').origins
    assert [origins[name] for name in ('service.n', 'service.rate', 'service.end')] == [
        ('runs', 'b'),
        ('options', 'Half rate'),
        ('options', 'Fast'),
    ]
    assert final(study, 'b')['values']['delivered'] == pytest.approx(served(values), rel=1e-9)
    # Without edits, the combination takes the values of its options.
    plain = evaluate_study(combined)
    values = {
        **model.run_values('b'),
        'service.end': option_value(model, 'service.end', 'Fast'),
    }
    assert final(plain, 'b')['values']['delivered'] == pytest.approx(served(values), rel=1e-9)


def test_a_combination_that_a_run_makes_is_that_run_bit_for_bit():
    """Run `a` with Half rate is the combination of run `b`: the same values, in the same structure, give
    the same report, bit for bit, with and without edits."""
    model = compiled(fixture())
    combined = model.combination('a', ['Half rate'])
    assert combined.runs['a']['options'] == model.runs['b']['options']
    for body in ({}, {'set': {'service.n': 5}, 'options': {'Half rate': {'service.rate': 9}}}):
        edits = edits_for(model, body)
        mine, theirs = evaluate_study(combined, edits), evaluate_study(model, edits, runs=['b'])
        assert mine.runs['a']['resolved'].parameter_values == theirs.runs['b']['resolved'].parameter_values
        assert final(mine, 'a') == final(theirs, 'b')
        assert mine.runs['a']['trajectory'].trace == theirs.runs['b']['trajectory'].trace


def test_a_start_state_option_without_a_built_structure_is_a_diagnostic():
    """An option that sets a start state, which no run takes, has no structure in the model: the build
    checks it in a structure of its own that it does not keep, and a combination with it is a
    diagnostic."""
    started = options(
        'Start', option('Started off', 'The service starts off.', f'service.state = "off"  {BASIS}')
    )
    model = compiled(fixture(replace('\nruns:', f'\n{started}\n\nruns:')))
    assert 'Started off' in model.start_options
    assert all('Started off' not in starts for starts in model.structures)
    with pytest.raises(ModelError) as caught:
        model.combination('a', ['Started off'])
    assert [(d['code'], d['options']) for d in caught.value.diagnostics] == [
        ('combination', ['Default', 'Started off'])
    ]


@pytest.mark.parametrize(
    'run, chosen, code',
    [
        ('nothing', [], 'run'),
        ('a', ['Quick'], 'reference'),
        ('a', ['Default', 'Fast'], 'combination'),
        ('a', 'Fast', 'combination'),
    ],
    ids=['unknown run', 'unknown option', 'two options of one group', 'a text'],
)
def test_a_combination_names_a_run_and_one_option_of_each_group(run, chosen, code):
    model = compiled(fixture())
    with pytest.raises(ModelError) as caught:
        model.combination(run, chosen)
    assert {d['code'] for d in caught.value.diagnostics} == {code}


def test_the_derived_model_is_one_run_of_the_same_model():
    """The derived model has the model's identity and the one run, under its name, with no comparison.
    An edit of another run is no edit of the derived model. The model itself does not change."""
    model = compiled(fixture())
    runs_before = {run: dict(info) for run, info in model.runs.items()}
    combined = model.combination('c', ['Half rate'])
    assert (combined.model_hash, combined.implementation_hash) == (
        model.model_hash,
        model.implementation_hash,
    )
    assert combined.runs['c']['comparison_of'] is None
    assert combined.runs['c']['name'] == ' · '.join(combined.runs['c']['options'])
    # A combination with the run's own options keeps the run's name on the pages.
    assert model.combination('a', ['Default']).runs['a']['name'] == model.runs['a']['name']
    rejected = evaluate_study(combined, edits_for(model, {'runs': {'a': {'service.n': 5}}}))
    assert not rejected.admissible and {d['code'] for d in rejected.diagnostics} == {'reference'}
    assert {run: dict(info) for run, info in model.runs.items()} == runs_before
    assert set(model.defaults) == set(model.runs) and combined.proven is not model.proven
