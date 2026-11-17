"""Distributions and named inputs in a file and in edits: what the build reads, and each fault at its
line. No case runs a simulation."""

from __future__ import annotations

import ast
import json
import pickle

import pytest

from napkin.core import expr as nodes
from napkin.core.expr import LARGEST, LONGEST, parse
from napkin.core.expr import text as written
from napkin.engine import edits_for
from napkin.expressions import ExpressionError, UnitRegistry, compile_expression
from napkin.model import ModelError
from napkin.model.language import expressions
from napkin.model.runs import Runs
from napkin.model.types import literal_quantities
from napkin.model.uncertain import DistributionProblem, read_distribution, written_arguments
from tests.acceptance.helpers import model_of
from tests.build import (
    UNITS,
    block,
    compiled,
    edit,
    in_place,
    indent,
    library,
    member,
    parameter,
    rejected,
    replace,
    scenario,
    value,
)
from tests.helpers import ROOT

END = 'service/end'
CURVE = 'service/curve'
# The lines of the analytic transfer that the cases change.
END_LINE = 'input end: h = 12 h in 1 h to 24 h  @fixture'
DELIVERY = 'let delivery: people/h = rate if state is "on" else 0 people/h  @fixture'
HALF_RATE = 'service.rate = 12 people/day  @fixture'


def with_end(written):
    """The analytic fixture with the stop time `end` (an input in h, from 1 h to 24 h) written as
    `written`."""
    return edit(scenario(), replace(END_LINE, f'input end: h = {written} in 1 h to 24 h  @fixture'))


def after_delivery(*blocks, delivery=DELIVERY):
    """An edit step: the formula `delivery` of the service, written as `delivery`, with `blocks`
    after it as members of the service."""
    return replace(DELIVERY, '\n'.join([delivery, *(indent(part) for part in blocks)]))


def with_curve(written='"slow"', test='curve is "fast"', *more):
    """The fixture with a named input that picks the delivery rate, and `more` members after it."""
    delivery = (
        f'let delivery: people/h = (rate * 2 if {test} else rate) if state is "on" else 0 people/h  @fixture'
    )
    curve = value('input', 'curve', written, '"slow" | "fast"', doc='Curve')
    return edit(scenario(), after_delivery(curve, *more, delivery=delivery))


@pytest.mark.parametrize(
    ('written', 'central'),
    [
        ('uniform(2 h, 10 h)', 6.0),
        # A unit of the dimension converts: 6 h to 12 h.
        ('uniform(0.25 days, 0.5 days)', 9.0),
        ('triangular(min=2 h, mode=6 h, max=10 h)', 6.0),
        ('normal(6 h, 1 h, min=2 h, max=10 h)', 6.0),
        ('lognormal(median=6 h, gsd=1.5, min=2 h, max=18 h)', 6.0),
        ('loguniform(2 h, 18 h)', 6.0),
    ],
)
def test_a_distribution_of_numbers_reads_its_units_and_takes_its_median(written, central):
    model = compiled(with_end(written), library())
    info = model.inputs['service.end']
    assert info['distribution']['text'] == written
    assert info['value'] == pytest.approx(central, rel=1e-12)
    assert model.run_values('a')['service.end'] == pytest.approx(central, rel=1e-12)


def test_a_distribution_in_another_unit_has_the_numbers_of_the_input_s_unit():
    days = compiled(with_end('pert(0.25 days, 0.5 days, 0.75 days)'), library())
    hours = compiled(with_end('pert(6 h, 12 h, 18 h)'), library())
    assert (
        days.inputs['service.end']['distribution']['args']
        == hours.inputs['service.end']['distribution']['args']
    )
    assert days.run_values('a') == hours.run_values('a')


@pytest.mark.parametrize(
    ('written', 'expected'),
    [
        ('uniform(10 h, 2 h)', ('distribution', END)),
        ('uniform(2, 10)', ('distribution', END)),
        ('uniform(2 people, 10 people)', ('distribution', END)),
        ('pert(2 h, 12 h, 10 h)', ('distribution', END)),
        ('normal(6 h, 1 h)', ('distribution', END)),
        ('normal(6 h, 1 h, min=2 h, max=10 h, mode=4 h)', ('distribution', END)),
        ('lognormal(6 h, 0.5, min=2 h, max=18 h)', ('distribution', END)),
        ('uniform(1 h, 30 h)', ('bounds', END)),
        # A beta gives a share from 0 to 1, not a number of hours.
        ('beta(2, 3)', ('distribution', END)),
        # The reader knows the kind of value that each family gives.
        ('bernoulli(0.3)', ('distribution', END)),
        ('categorical(a=1)', ('distribution', END)),
        ('gamma(2 h, 3 h)', ('build', END)),
    ],
)
def test_a_distribution_that_its_input_cannot_take_is_rejected_at_its_value(written, expected):
    assert expected in rejected(with_end(written), library())


def test_a_beta_gives_a_dimensionless_value_from_0_to_1():
    text = edit(scenario(), after_delivery(parameter('share', 'beta(2, 3)', 'fraction', 0, 1, doc='Share')))
    info = compiled(text, library()).inputs['service.share']
    assert info['distribution']['family'] == 'beta' and 0 < info['value'] < 1


def test_an_option_value_can_be_a_distribution_with_the_same_checks():
    def half_rate(written):
        return edit(scenario(), replace(HALF_RATE, f'service.rate = {written}  @fixture'))

    model = compiled(half_rate('uniform(6 people/day, 18 people/day)'), library())
    assert model.inputs['service.rate']['options']['Half rate']['value'] == pytest.approx(12)
    assert model.run_values('b')['service.rate'] == pytest.approx(12)
    assert ('bounds', 'options:/Rate/Half rate/service.rate/value') in rejected(
        half_rate('uniform(6 people/day, 60 people/day)'), library()
    )


def test_a_bool_and_a_named_input_take_their_own_families():
    spare = value('input', 'spare', 'bernoulli(0.6)', 'bool', doc='Spare')
    model = compiled(with_curve('categorical(slow=0.3, fast=0.7)', 'curve is "fast"', spare), library())
    assert (model.inputs['service.curve']['value'], model.inputs['service.spare']['value']) == ('fast', True)
    for bad in (
        'categorical(slow=0.3, fast=0.6)',
        'categorical(slow=0.3, quick=0.7)',
        'categorical(0.3, 0.7)',
    ):
        assert ('distribution', CURVE) in rejected(with_curve(bad), library())
    assert ('distribution', CURVE) in rejected(with_curve('bernoulli(0.5)'), library())


def test_distributions_that_read_each_other_are_rejected():
    wait = parameter('wait', 'uniform(end, end + 1 h)', 'h', 1, 24)
    text = edit(with_end('uniform(wait, wait + 2 h)'), after_delivery(wait))
    with pytest.raises(ModelError) as caught:
        compiled(text, library())
    assert any('read each other' in d['message'] for d in caught.value.diagnostics)


def test_a_distribution_reads_inputs_and_fixed_values_only():
    text = with_end('uniform(1 h, 1 h + stock / 1 people/h)')
    assert ('build', END) in rejected(text, library())


def test_an_argument_that_reads_an_input_has_the_unit_of_its_parameter():
    assert ('build', END) in rejected(with_end('uniform(1 h, n)'), library())


def test_a_linked_support_outside_the_range_is_found_when_the_values_are_known():
    """The support of uniform(n / 1 people * 1 h, ...) depends on n: with n = 10 people it reaches
    30 h, beyond the range of end."""
    text = with_end('uniform(n / 1 people * 1 h, n / 1 people * 3 h)')
    with pytest.raises(ModelError) as caught:
        compiled(text, library())
    assert any(d['code'] == 'build' and 'outside the range' in d['message'] for d in caught.value.diagnostics)


def test_an_argument_that_reads_an_input_is_held_as_its_node_and_reads_its_value():
    """The model holds each argument that reads other values as the node of its expression, with the
    structure's names. With n = 10 people, uniform(n / 1 people * 0.5 h, n / 1 people * 1 h) runs from
    5 h to 10 h: its median is 7.5 h, also after a pickle of the model."""
    text = with_end('uniform(n / 1 people * 0.5 h, n / 1 people * 1 h)')
    model = compiled(text, library())
    ((written, arguments),) = model.arguments['service.end'].items()
    assert written.startswith('uniform(') and set(arguments) == {'min', 'max'}
    for argument in arguments.values():
        assert isinstance(argument, nodes.Node) and nodes.names(argument) == {'service.n'}
    assert model.run_values('a')['service.end'] == pytest.approx(7.5)
    again = pickle.loads(pickle.dumps(model))
    assert again.run_values('a')['service.end'] == pytest.approx(7.5)


# The rate of the analytic transfer, and the same rate in another unit: 24 people a day is 1 person an
# hour.
RATE_LINE = 'input rate: people/day = 24 people/day in 1 people/day to 48 people/day  @fixture'
RATE_IN_HOURS = 'input rate: people/h = 1 people/h in 1 people/day to 48 people/day  @fixture'
# Hours in one unit of time (identity: 1 day is 24 h).
HOURS = {'h': 1, 'days': 24}


@pytest.mark.parametrize('rate_line', [RATE_LINE, RATE_IN_HOURS])
@pytest.mark.parametrize('end_unit', sorted(HOURS))
def test_a_distribution_that_reads_an_input_gives_the_same_time_in_any_units(rate_line, end_unit):
    """The units in which the file writes an input are not a part of what it means. So the central
    value of `end`, whose arguments read `rate`, is the same time whatever the units of `rate` and of
    `end`. The oracle is the case where both are in hours."""

    def central_hours(line, unit):
        text = edit(
            scenario(),
            replace(RATE_LINE, line),
            replace(
                END_LINE,
                f'input end: {unit} = uniform(rate / 1 people/day * 0.25 h, rate / 1 people/day * 0.5 h)'
                ' in 1 h to 24 h  @fixture',
            ),
        )
        model = compiled(text, library())
        assert model.inputs['service.end']['unit'] == unit
        values = (model.inputs['service.end']['value'], model.run_values('a')['service.end'])
        return [value * HOURS[unit] for value in values]

    oracle = central_hours(RATE_IN_HOURS, 'h')
    assert central_hours(rate_line, end_unit) == pytest.approx(oracle)


@pytest.mark.parametrize(
    'curve, branch',
    [('"fast"', '2 h'), ('"slow"', '6 h'), ('categorical(slow=0.3, fast=0.7)', '2 h')],
)
def test_a_distribution_that_reads_a_named_input_reads_its_value(curve, branch):
    """An argument that tests a named input reads the value of that input: the central value of
    `end` is the central value of the same distribution with the branch of that value written in
    place of the test. The central value of a categorical is its most likely value, here "fast"."""

    def central(end):
        line = f'input end: h = {end} in 1 h to 24 h  @fixture'
        model = compiled(edit(with_curve(curve), replace(END_LINE, line)), library())
        return model.inputs['service.end']['value'], model.run_values('a')['service.end']

    read = central('uniform(2 h if curve is "fast" else 6 h, 10 h)')
    assert read == pytest.approx(central(f'uniform({branch}, 10 h)'))


def edits_of(model, values):
    """The problems of an edit that sets `values`, in the run table of the model."""
    runs = Runs.from_scenario(model.scenario, model.library)
    return runs.errors(edits_for(model, {'set': values}), model.model_hash)


def test_an_edit_gives_a_distribution_with_numbers_or_a_name():
    model = compiled(with_curve(), library())
    assert edits_of(model, {'service.end': 'pert(2 h, 6 h, 20 h)', 'service.curve': 'fast'}) == []
    found = {
        (d['code'], d['path'])
        for d in edits_of(
            model,
            {
                'service.end': 'uniform(1 h, n / 1 people * 1 h)',
                'service.n': 'uniform(5 people, 500 people)',
                'service.rate': 'uniform(1, 2)',
                'service.curve': 'quick',
            },
        )
    }
    assert found == {
        ('distribution', 'edits/set/service.end'),
        ('bounds', 'edits/set/service.n'),
        ('distribution', 'edits/set/service.rate'),
        ('value', 'edits/set/service.curve'),
    }


def test_a_named_input_is_a_test_of_the_code_of_its_value():
    model = compiled(with_curve(), library())
    info = model.inputs['service.curve']
    assert (info['type'], list(info['values']), info['value'], info['range']) == (
        'names',
        ['slow', 'fast'],
        'slow',
        None,
    )
    parameter = model.structure_of('a').parameters['service.curve']
    assert (parameter.value, parameter.adjust.plain()) == (0, {'mode': 'range', 'min': 0, 'max': 1})
    assert 'service.curve == 1' in written(model.structure_of('a').computed['service.delivery'].expr)
    assert model.resolve('a', {'service.curve': 'fast'}).parameter_values['service.curve'] == 1
    with pytest.raises(ModelError) as caught:
        model.resolve('a', {'service.curve': 'quick'})
    assert [d['code'] for d in caught.value.diagnostics] == ['choice']


@pytest.mark.parametrize(
    ('written', 'test', 'code'),
    [
        ('"quick"', 'curve is "fast"', 'build'),
        ('"slow"', 'curve is "quick"', 'build'),
        ('"slow"', 'curve', 'build'),
    ],
    ids=["quick-self.curve == 'fast'-structure", "slow-self.curve == 'quick'-build", 'slow-self.curve-build'],
)
def test_a_named_input_takes_and_tests_one_of_its_values(written, test, code):
    found = rejected(with_curve(written, test), library())
    assert any(c == code for c, _ in found), found


def test_a_named_input_has_no_range():
    curve = 'input curve: "slow" | "fast" = "slow"'
    text = edit(with_curve(), replace(f'{curve}  @fixture', f'{curve} in 0 to 1  @fixture'))
    assert ('structure', f'{CURVE}/min:') in rejected(text, library())


def test_a_distribution_reports_no_single_datum_of_a_source():
    """An inventory of the F5 fixture's tank cites the exact datum that a source reports: a
    distribution in its place reports no single value, so the citation is an error at the value."""
    datum = in_place('source', 'The synthetic exact inventory datum.', block('T_DATUM', 'datum: inventory'))
    inventory = block('let inventory: L = uniform(50 L, 150 L)', datum)
    with pytest.raises(ModelError) as caught:
        model_of('F5', [member('tank', inventory)])
    assert [(d['code'], d['path']) for d in caught.value.diagnostics] == [('build', 'tank/inventory')]


TEXTS = json.loads((ROOT / 'tests/fixtures/distribution-texts.json').read_text(encoding='utf-8'))
KIND = {'number': 'unit', 'bool': 'bool', 'names': 'names'}


@pytest.mark.parametrize('case', TEXTS['cases'], ids=lambda case: case['text'])
def test_the_reader_reads_each_distribution_as_an_edit_writes_it(case):
    """An edit document writes these texts (docs/engine.md, "The edit document"); the reader gives the
    same arguments, bit for bit, in the unit of the input."""
    written = case['input']
    record = read_distribution(
        case['text'], KIND[written['type']], written['unit'], UnitRegistry(UNITS), written.get('values')
    )
    assert (record['family'], record['args']) == (case['family'], case['args'])


@pytest.mark.parametrize('call', ['sum(0.25, 0.5)', 'any(0.25, 0.5)', 'all(1)'])
def test_a_function_over_a_list_is_no_function_of_an_argument_of_a_distribution(call):
    """The lowering writes a sum, an any and an all over the members of a list of the model; an
    author does not call them with values. The reader refuses each as it refuses a word that is no
    function, and takes a function of the language in the same place."""
    units = UnitRegistry(library()['units'])

    def problem(argument):
        with pytest.raises(Exception) as raised:
            read_distribution(f'uniform({argument}, 1.5)', 'unit', 'fraction', units)
        return type(raised.value), str(raised.value)

    assert problem(call) == problem('no_such_function(0.25)')
    taken = read_distribution('uniform(max(0.25, 0.5), 1.5)', 'unit', 'fraction', units)
    assert taken['args']['min'] == 0.5


def flat(count, number):
    """A call of `max` with `count` arguments, each the number `number`: one part of Python's tree for
    each argument, and no nesting."""
    return 'max(' + ', '.join([number] * count) + ')'


@pytest.mark.parametrize(
    ('read', 'refused'),
    [
        # 1,000 parts of Python's tree, and 1,001.
        (flat(996, '1'), flat(997, '1')),
        # 9,999 characters, and 10,013.
        (flat(714, '1.2345678901'), flat(715, '1.2345678901')),
    ],
    ids=['parts', 'characters'],
)
def test_an_argument_of_a_distribution_has_the_two_limits_of_size_of_an_expression(read, refused):
    """The reader finds the value of an argument from its typed nodes, and it keeps the two limits of
    size of an expression text. Python's own count of the parts of the text, and the length of the
    text, say on which side of a limit each argument is. The reader of an expression text reads the
    first argument and refuses the second: its value and its reason are those of the distribution."""

    def size(text):
        return len(text), sum(1 for _ in ast.walk(ast.parse(text, mode='eval')))

    assert all(found <= limit for found, limit in zip(size(read), (LONGEST, LARGEST)))
    assert any(found > limit for found, limit in zip(size(refused), (LONGEST, LARGEST)))
    units = UnitRegistry(library()['units'])
    taken = read_distribution(f'uniform({read}, 5)', 'unit', 'fraction', units)
    # The node of each text, read with no limit of size: the check of the expression says the limit.
    assert taken['args']['min'] == compile_expression(parse(read), {}, units).evaluate({})
    with pytest.raises(ExpressionError) as reason:
        compile_expression(parse(refused), {}, units)
    with pytest.raises(DistributionProblem) as raised:
        read_distribution(f'uniform({refused}, 5)', 'unit', 'fraction', units)
    assert str(raised.value) == f'min: {reason.value}'


# ---- an argument that reads other values, as the author wrote it -----------------------------------


@pytest.mark.parametrize(
    ('written', 'expected'),
    [
        (
            'pert(1 h, 2 h * (n / 10 people), 8 h)',
            [(None, '1 h'), (None, '2 h * (n / 10 people)'), (None, '8 h')],
        ),
        # A comma inside brackets is of the call inside, and a name with `=` is the name of the argument.
        (
            'normal(mean=10 h, sd = max(1 h, 2 h), min=4 h,max=16 h)',
            [('mean', '10 h'), ('sd', 'max(1 h, 2 h)'), ('min', '4 h'), ('max', '16 h')],
        ),
        # A comma and a bracket inside a text are of the text.
        ('bernoulli(0.5 if state is "a, (b" else 0.1)', [(None, '0.5 if state is "a, (b" else 0.1')]),
        # A comparison is no name of an argument.
        ('uniform(x <= 2, y >= 1)', [(None, 'x <= 2'), (None, 'y >= 1')]),
        ('categorical()', []),
        ('uniform( 1 , )', [(None, '1'), (None, '')]),
    ],
)
def test_the_arguments_of_a_written_call_are_those_between_its_commas(written, expected):
    assert written_arguments(written) == expected


def test_a_unit_that_ends_inside_a_word_gets_a_space_and_the_language_reads_the_same_units():
    """`literal_quantities` finds the longest unit that the word after a number spells. With `spaced`
    it writes the expression in the language, with a space where the unit ends: the reader of the
    language, which takes the whole word after a number as its unit, then reads the same units."""
    units = {'h', 'L', 'L/h', 'people'}
    written = '2 h/self.x + 3 L/h - 1 h-end + 4 people'
    assert (
        literal_quantities(written, units)
        == "q(2, 'h')/self.x + q(3, 'L/h') - q(1, 'h')-end + q(4, 'people')"
    )
    spaced = literal_quantities(written, units, spaced=True)
    assert spaced == '2 h /self.x + 3 L/h - 1 h -end + 4 people'
    found = [token.value for token in expressions.tokens_of(spaced) if token.kind == 'unit']
    assert found == ['h', 'L/h', 'h', 'people']
    # The words as the author wrote them are no units of the language.
    assert next(token.value for token in expressions.tokens_of(written) if token.kind == 'unit') == 'h/self.x'


@pytest.mark.parametrize(
    ('written', 'source', 'top'),
    [
        # The greatest stop time is the mean of 2 h and the wait.
        ('uniform(1 h, (2 h + wait) / 2)', '(2 h + wait) / 2', lambda wait: (2 + wait) / 2),
        ('uniform(min=1 h, max=wait*0.5 + 0.5 h)', 'wait * 0.5 + 0.5 h', lambda wait: wait / 2 + 0.5),
        # A unit that ends inside a word: 24 h less the wait.
        ('uniform(1 h, 24 h-wait)', '24 h -wait', lambda wait: 24 - wait),
    ],
)
def test_an_argument_that_reads_an_input_stays_as_written_and_takes_the_value_of_the_input(
    written, source, top
):
    """The record of the distribution keeps an argument that reads other values as the author wrote
    it, in the spacing of the language. The run takes the median of the distribution, which is the
    middle of 1 h and the greatest stop time with the wait of the run: 10 h in the file, and 16 h
    when a caller gives it."""
    wait = parameter('wait', 10, 'h', 1, 24)
    model = compiled(edit(with_end(written), after_delivery(wait)), library())
    record = model.run_table.data['inputs']['service.end']['value']
    assert dict(record['args']) == {'min': 1, 'max': {'reads': source}}
    assert model.resolve('a').parameter_values['service.end'] == pytest.approx((1 + top(10)) / 2)
    given = model.resolve('a', {'service.wait': 16})
    assert given.parameter_values['service.end'] == pytest.approx((1 + top(16)) / 2)


def test_the_text_that_is_kept_for_an_argument_is_the_argument(monkeypatch):
    """The reader keeps the text of each argument beside its node. If the two were not the same
    argument, the record would say one thing and the run would take another: the reader refuses."""
    from napkin.model import uncertain

    units = UnitRegistry(library()['units'])
    real = uncertain.written_arguments
    assert read_distribution('uniform(0.25, x + 1)', 'unit', 'fraction', units)['args'] == {
        'min': 0.25,
        'max': {'reads': 'x + 1'},
    }
    monkeypatch.setattr(uncertain, 'written_arguments', lambda written: list(reversed(real(written))))
    with pytest.raises(DistributionProblem, match='is not one call of uniform with its arguments'):
        read_distribution('uniform(0.25, x + 1)', 'unit', 'fraction', units)
