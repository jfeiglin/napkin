"""The declared model (`napkin/model/semantic.py`): names resolved, types and units checked by their
dimensions, the unit run of D12, the places where a bare number takes a unit, the paths of the
declared parts, and each refusal with its code and its line."""

import textwrap
from fractions import Fraction

import pytest

from napkin.model import semantic as s
from napkin.model.language.parse import parse
from napkin.model.language.problems import LanguageError
from tests.program.examples import UNITS


def declared(text, units=UNITS):
    return s.declare(parse(textwrap.dedent(text)), units)


def refused(text, code, line=None):
    with pytest.raises(LanguageError) as caught:
        declared(text)
    assert code in caught.value.codes, caught.value
    if line is not None:
        assert caught.value.problems[caught.value.codes.index(code)].line == line
    return caught.value


def root(text, name):
    return next(value for value in declared(text).root if value.name == name)


# ---- units ------------------------------------------------------------------------------------------


def test_a_spelling_composes_from_the_left():
    units = s.Units(UNITS)
    # kW/h is energy per time squared, 1000 W of it per hour; year/h is a plain 8760.
    assert units.of('kW/h') == ((('energy', 1), ('time', -2)), Fraction(1000))
    assert units.of('year/h') == ((), Fraction(8760))
    assert units.of('furlong') is None


def test_a_derived_unit_cancels_a_name_over_and_under_the_line():
    assert s.spelling_of([*s.factors('tunings/tuner/year'), (1, 'tuner')]) == 'tunings/year'
    assert s.spelling_of([*s.factors('h'), (-1, 'h')]) == ''
    assert s.spelling_of([(-1, 'h')]) == '1/h'


def test_a_type_with_brackets_is_flat_from_the_left():
    value = declared('x: person * year = 1\ny: L / (person * h) = 1\n').root
    assert [item.type.unit for item in value] == ['person*year', 'L/person/h']


def test_products_and_quotients_make_their_units():
    model = declared('a = (3 person) * (2 year)\nb = (6 L) / (2 h)\nc = 48 h / 2\nd = (2 h) ** 2\n')
    assert [value.type.unit for value in model.root] == ['person*year', 'L/h', 'h', 'h*h']


def chain(written, count, operator):
    """`count` copies of a written value joined by `operator`, from the left."""
    return f' {operator} '.join([written] * count)


def test_a_sum_longer_than_the_deepest_tree_is_one_sum_of_its_terms():
    """`a + b - c` reads as `sum(a, b, -c)` past 150 operations (`DEEPEST`), which adds from the
    left bit for bit, so its tree stays shallow; up to there it stays a chain of `+` and `-`."""
    rate = 'x: L/h = 1 L/h\n'
    short = root(rate + f'total = formula({chain("x", s.DEEPEST + 1, "+")})\n', 'total').init.body
    assert short.op == 'add' and short.args[0].op == 'add'
    terms = chain('x', s.DEEPEST + 1, '+') + ' - x + 0'
    found = root(rate + f'total = formula({terms})\n', 'total').init.body
    assert (found.op, found.detail, len(found.args), found.type.unit) == ('call', 'sum', s.DEEPEST + 3, 'L/h')
    assert found.args[-2].op == 'neg' and found.args[-1] == s.Const(0, found.type)


def test_a_chain_of_signs_longer_than_the_deepest_tree_is_the_sign_that_it_makes():
    x = 'x = 1\n'
    assert root(x + 'y = formula(' + '- ' * 150 + 'x)\n', 'y').init.body.op == 'neg'
    assert isinstance(root(x + 'y = formula(' + '- ' * 152 + 'x)\n', 'y').init.body, s.Read)
    odd = root(x + 'y = formula(' + '- ' * 151 + 'x)\n', 'y').init.body
    assert odd.op == 'neg' and isinstance(odd.args[0], s.Read)
    assert root('c = true\nd = formula(' + 'not ' * 153 + 'c)\n', 'd').init.body.op == 'not'


def test_a_product_longer_than_the_deepest_tree_is_refused_by_name():
    problem = refused('x = 2\ny = formula(' + chain('x', s.DEEPEST + 2, '*') + ')\n', 'deep', 2)
    assert 'a product of more than 150 factors' in str(problem)


def test_a_unit_run_stops_at_the_first_name_that_is_no_unit():
    # `hour` is a value here: in brackets the quantity is multiplied by it; without them the name
    # continues the unit.
    model = declared('hour = 3\nx = (2 h) * hour\ny = 2 h * hour\n', {**UNITS, 'hour': {'time': 1}})
    x, y = model.root[1:]
    assert x.init == s.Apply('mul', (s.Const(2, x.type), s.Read(('root',), ('hour',), s.PLAIN)), x.type)
    assert (x.type.unit, y.type.unit) == ('h', 'h*hour')
    assert y.init == s.Const(2, y.type)


def test_a_name_that_is_no_unit_in_a_run_is_a_value():
    model = declared('crews = 4\nx = 2 h * crews\n')
    assert model.root[1].init.op == 'mul' and model.root[1].type.unit == 'h'


# ---- bare numbers -------------------------------------------------------------------------------


def test_a_bare_number_takes_the_declared_unit_where_the_spec_says_so():
    model = declared(
        """
        tank:
            water: L = 8 in [0, 20] scale 100
            level = 0 in [-30, 30]
            rate = max(0, this.water / (2 h))
        """
    )
    water, level, rate = model.entities[0].parts
    liters = water.type
    assert (water.init, water.lower, water.upper, water.scale) == (
        s.Const(8, liters),
        s.Const(0, liters),
        s.Const(20, liters),
        s.Const(100, liters),
    )
    assert level.type == s.PLAIN and level.lower == s.Const(-30, s.PLAIN)
    # A bare zero beside a value of known unit takes that unit.
    assert rate.init.args[0] == s.Const(0, rate.type) and rate.type.unit == 'L/h'


def test_the_arguments_of_a_drawn_default_take_the_declared_unit():
    model = declared('m:\n    input repair_time: h = uniform(1, 3).draw()\n')
    value = model.entities[0].parts[0]
    assert value.init.source == s.Distribution('uniform', (1, 3), s.Dist(value.type))
    # With no range, a draw admits the support of its distribution.
    assert (value.lower, value.upper) == (s.Const(1, value.type), s.Const(3, value.type))


def test_a_distribution_converts_its_arguments_to_one_unit():
    model = declared('input x = uniform(1 day, 36 h).draw()\n', {**UNITS, 'day': ({'time': 1}, 24)})
    assert model.root[0].init.source.params == (1, Fraction(3, 2))
    assert model.root[0].type.unit == 'day'


def test_an_input_range_must_hold_the_support_of_its_distribution():
    refused('input x = uniform(1 h, 3 h).draw() in [2 h, 12 h]\n', 'range', 1)
    refused('input x = normal(2 h, 1 h).draw() in [0 h, 12 h]\n', 'range', 1)
    value = root('input x = uniform(1 h, 3 h).draw() in [1 h, 12 h]\n', 'x')
    assert value.upper == s.Const(12, value.type)


# ---- kinds, paths and texts ---------------------------------------------------------------------


def test_values_inputs_formulas_and_flows_have_their_kinds_and_paths():
    model = declared(
        """
        tank:
            "A tank."
            readonly water: L = 8 in [0, 20]
                "Water in the tank"
            input demand: L/h = 3
            readonly empty: formula(bool) = formula(this.water <= 0 L)
        clinic:
            flow delivery: tank.water -> SINK
                request = formula(tank.demand)
        total = formula(clinic.delivery.actual_rate)
        """
    )
    tank, clinic = model.entities
    water, demand, empty = tank.parts
    assert [part.path for part in (tank, water, demand, empty, *clinic.parts)] == [
        'tank',
        'tank.water',
        'tank.demand',
        'tank.empty',
        'clinic.delivery',
    ]
    assert (water.kind, water.readonly, water.text) == (s.STATE, True, 'Water in the tank')
    assert (demand.kind, empty.kind, empty.type) == (s.INPUT, s.FORMULA, s.BOOL)
    (delivery,) = clinic.parts
    assert delivery.source == s.Read(('named', 'tank'), ('water',), water.type)
    assert delivery.sink == 'SINK' and delivery.rate.unit == 'L/h'
    assert model.root[0].type.unit == 'L/h' and model.part('clinic.delivery') is delivery


def test_the_scenario_line_gives_its_times_in_hours():
    model = declared(
        'scenario "A"\n    horizon 2 days\n    resolution 30 min\n',
        {**UNITS, 'day': ({'time': 1}, 24), 'days': ({'time': 1}, 24), 'min': ({'time': 1}, Fraction(1, 60))},
    )
    assert (model.scenario.horizon, model.scenario.resolution) == (48, Fraction(1, 2))


def test_a_status_display_keeps_its_cases_in_written_order_with_their_texts():
    model = declared(
        """
        Place:
            a: L = 1
            status degraded when this.a < 1 L
                "Low."
            b: L = 2
            status ok
                "Fine."
        """
    )
    (place,) = model.entities
    assert [part.path for part in place.parts] == ['Place.a', 'Place.b']
    assert place.status.path == 'Place.status'
    cases = [(case.path, case.rating, case.test is None, case.text) for case in place.status.cases]
    assert cases == [
        ('Place.status.case[0]', 'degraded', False, 'Low.'),
        ('Place.status.case[1]', 'ok', True, 'Fine.'),
    ]
    assert model.part('Place.status.case[1]').text == 'Fine.'


# ---- refusals -------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ('text', 'code', 'line'),
    [
        ('x: L = 8 h\n', 'unit', 1),
        ('x = 1 L + 2 h\n', 'unit', 1),
        ('x = 5 furlongs\n', 'unit', 1),
        ('x = 2 h ** 0.5\n', 'unit', 1),
        ('x = true + 1\n', 'type', 1),
        ('x = 1 and true\n', 'type', 1),
        ('x: L = formula(3 L)\n', 'formula', 1),
        ('x = 1\ny = formula(formula(x))\n', 'formula', 2),
        ('x = 3 in [5, 1]\n', 'range', 1),
        ('x = 3 @missing\n', 'unknown_record', 1),
        ('x = missing + 1\n', 'unknown_name', 1),
        ('x = 1\nx = 2\n', 'duplicate_name', 2),
        ('x: L\n', 'no_value', 1),
        ('x = this.y\n', 'unknown_name', 1),
        ('x = y.diff(z)\n', 'not_in_v1', 1),
    ],
)
def test_the_declared_model_refuses_with_a_code_and_a_line(text, code, line):
    refused(text, code, line)


def test_a_cycle_of_starting_values_is_refused():
    refused('tank:\n    a: L = this.b\n    b: L = this.a\n', 'cycle')


@pytest.mark.parametrize(
    ('member', 'code'),
    [
        ('flow f: this.rate -> SINK\n', 'flow_end'),
        ('flow f: this.level -> SINK\n', 'flow_end'),
        ('flow f: SOURCE -> SINK\n    request = formula(this.rate)\n', 'flow_units'),
        ('flow f: SOURCE -> this.water\n    request = 3 W\n', 'flow_units'),
        ('flow f: SOURCE -> this.water\n    request = formula(this.energy)\n', 'unit'),
        ('flow f: SOURCE -> this.water\n    limit = 3 L/h\n', 'property'),
        ('flow f: this.water -> this.energy\n', 'flow_units'),
    ],
)
def test_a_flow_is_refused_with_a_code(member, code):
    text = 'tank:\n    input rate: L/h = 3\n    level = formula(this.water)\n    water: L = 8\n    energy: Wh = 1\n'
    refused(text + textwrap.indent(member, '    '), code)
