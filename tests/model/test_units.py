"""Units (docs/language.md, §2.1): the prelude, and the units that no entry declares, which are composed
of declared units. `a/b` divides, `a-b` is a product, which binds tighter than `/`, and `a^n` is a power
with a whole exponent; an entry always wins over a composition. Each expected scale and dimension here
comes from exact rational arithmetic on the declared parts (`fractions.Fraction`), never from the
registry's own arithmetic."""

from __future__ import annotations

import json
import math
from collections import Counter
from fractions import Fraction

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from napkin.expressions import ExpressionError, UnitSystem
from napkin.model import ModelError
from napkin.model.library import PRELUDE, prelude_units
from napkin.model.load import schema_errors
from napkin.model.model import build_model

# Declared units, name: (dimensions, scale), with scales that are not all exact in binary.
DECLARED = {
    'h': ({'time': 1}, 1),
    'day': ({'time': 1}, 24),
    'year': ({'time': 1}, 8760),
    'person': ({'people': 1}, 1),
    'tuner': ({'tuners': 1}, 1),
    'tunings': ({'tunings': 1}, 1),
    'gal': ({'volume': 1}, 3.785411784),
    'ft': ({'length': 1}, 0.3048),
    'percentage_points': ({}, 0.01),
    'USD_k': ({'USD': 1}, 1000),
}


def registry(extra=None):
    table = {**DECLARED, **(extra or {})}
    return UnitSystem({name: {'dimensions': dims, 'scale': scale} for name, (dims, scale) in table.items()})


def exact(factors, table=DECLARED):
    """(dimensions, scale) of the product of `factors`, [(name, power)], in exact arithmetic: the
    dimensions add, each times its power, and the scale is the product of the scales, each raised to its
    power."""
    dimensions, scale = Counter(), Fraction(1)
    for name, power in factors:
        own, size = table[name]
        for key, value in own.items():
            dimensions[key] += value * power
        scale *= Fraction(size) ** power
    return {key: value for key, value in dimensions.items() if value}, scale


def written(name, power):
    return name if power == 1 else f'{name}^{power}'


def same(unit, dimensions, scale):
    return dict(unit.dimensions) == dimensions and math.isclose(unit.scale, float(scale), rel_tol=1e-13)


FACTOR = st.tuples(st.sampled_from(sorted(DECLARED)), st.integers(-3, 3))
PRODUCT = st.lists(FACTOR, min_size=1, max_size=3)


@settings(derandomize=True, max_examples=300, deadline=None)
@given(PRODUCT, st.lists(PRODUCT, max_size=2))
def test_a_composed_unit_is_the_product_of_its_parts_with_their_powers(numerator, denominators):
    """`a-b^2/c-d/e` is a·b²/(c·d)/e: the scale is the product of the parts' scales raised to their
    powers, and the dimensions add."""
    name = '/'.join(
        '-'.join(written(*factor) for factor in product) for product in (numerator, *denominators)
    )
    factors = [*numerator, *((part, -power) for product in denominators for part, power in product)]
    dimensions, scale = exact(factors)
    assert same(registry().parse_unit(name), dimensions, scale), name
    assert name in registry()


def test_a_product_binds_tighter_than_a_quotient():
    """`tunings/tuner-year` is tunings per tuner per year: the product `tuner-year` divides."""
    units = registry()
    found = units.parse_unit('tunings/tuner-year')
    assert same(found, *exact([('tunings', 1), ('tuner', -1), ('year', -1)]))
    assert found == units.parse_unit('tunings/tuner/year')
    assert not same(found, *exact([('tunings', 1), ('tuner', -1), ('year', 1)]))


def test_an_entry_wins_over_a_composition_of_the_whole_name_and_of_each_part():
    """An entry of the whole name wins, and so does an entry of a product or of the first part of a
    quotient that a longer name is made of, even when its definition is not the composition's."""
    declared = {
        'tunings/tuner-year': ({'tunings': 1, 'tuners': -1, 'time': -1}, 2),
        'tuner-year': ({'tuners': 1, 'time': 1}, 5),
        'gal/day': ({'volume': 1, 'time': -1}, 7),
    }
    units = registry(declared)
    table = {**DECLARED, **declared}
    assert same(units.parse_unit('tunings/tuner-year'), {'tunings': 1, 'tuners': -1, 'time': -1}, 2)
    # Tunings per (the declared tuner-year), and the declared gal/day per person.
    assert same(units.parse_unit('USD_k/tuner-year'), *exact([('USD_k', 1), ('tuner-year', -1)], table))
    assert same(units.parse_unit('gal/day/person'), *exact([('gal/day', 1), ('person', -1)], table))
    assert same(units.parse_unit('tunings-tuner-year'), *exact([('tunings', 1), ('tuner-year', 1)], table))
    # Without those entries, the same names are their compositions.
    plain = registry()
    assert same(plain.parse_unit('USD_k/tuner-year'), *exact([('USD_k', 1), ('tuner', -1), ('year', -1)]))


@pytest.mark.parametrize(
    'name',
    ['h/2', 'tunings/yr', 'h//day', '/h', 'h/', '-h', 'h-', 'h^', 'h^x', 'h^1.5', 'h^^2', '2', '', 'h day'],
)
def test_a_name_that_is_not_made_of_declared_units_is_no_unit(name):
    units = registry()
    assert name not in units
    with pytest.raises(ExpressionError):
        units.parse_unit(name)


def test_a_power_in_an_expression_is_two_stars_and_a_caret_writes_a_units_power():
    import ast

    from napkin.model.language.expressions import tokens_of, tree
    from napkin.model.language.lex import SyntaxProblem

    with pytest.raises(SyntaxProblem, match=r'\*\*'):
        tree(tokens_of('area ^ 2'))
    node, _ = tree(tokens_of('5 m^2 * 2'))
    assert "'m^2'" in ast.unparse(node)


def test_an_unknown_unit_suggests_the_composition_closest_to_it():
    """A part that names no unit is the closest declared name in the suggestion (`tunings/yr` →
    `tunings/year`), and each suggestion is a unit."""
    units = registry()
    found = units.suggestions('tunings/yr')
    assert 'tunings/year' in found
    assert all(name in units for name in found)


# ---- the prelude ------------------------------------------------------------------------------------


def test_the_prelude_is_a_valid_units_file_of_times_people_and_ratios():
    """Every unit of the prelude is a unit of a units file; each alias has the definition of the unit
    that it names, and a week is seven days."""
    units = prelude_units()
    assert schema_errors(json.loads(PRELUDE.read_text(encoding='utf-8')), 'scenario-units') == []
    for alias, unit in (
        ('hour', 'h'),
        ('hours', 'h'),
        ('day', 'days'),
        ('month', 'months'),
        ('year', 'years'),
    ):
        assert units[alias] == units[unit], alias
    assert units['person'] == units['people'] and units['weeks'] == units['week']
    system = UnitSystem(units)
    assert system.parse_unit('week').scale == 7 * system.parse_unit('days').scale
    assert system.parse_unit('days').scale == 24 * system.parse_unit('h').scale


# ---- a model with composed units --------------------------------------------------------------------

TUNERS = """scenario "Piano tuners"
    summary "Tuners tune pianos. A synthetic fixture for tests only."
    horizon 2 weeks
    scope "The tuners of one town."

tuners:  @counted
    "The tuners of the town."
    role environment
    input rate: tunings/tuner-year = 1000 tunings/tuner-year in 0 tunings/tuner-year to 2000 tunings/tuner-year
        @counted
        "Tunings that one tuner does in a year"
    input staff: tuner = 3 tuner in 1 tuner to 10 tuner  @counted
        "Tuners"
    var done: tunings = 0 tunings size 1000 tunings  @counted
        "Tunings done"
    flow tune: -> done at rate * staff  @counted
    event start when t >= 0 h:  @counted
        "The tuners start."

output tunings_done: tunings = tuners.done  @counted
    "Tunings done"

record counted: assumption A-TUNERS "Fixture counts."
"""


def tuners(tmp_path, units):
    folder = tmp_path / 'tuners'
    folder.mkdir(parents=True)
    (folder / 'model.scn').write_text(TUNERS, encoding='utf-8')
    (folder / 'units.json').write_text(json.dumps(units), encoding='utf-8')
    assumption = {
        'id': 'A-TUNERS',
        'statement': 'Fixture.',
        'rationale': 'Fixture.',
        'review': {'status': 'unreviewed'},
    }
    (folder / 'evidence').mkdir()
    (folder / 'evidence/assumptions.json').write_text(json.dumps([assumption]), encoding='utf-8')
    return folder / 'model.scn'


COUNTS = {
    'tunings': {'dimensions': {'tunings': 1}, 'scale': 1},
    'tuner': {'dimensions': {'tuners': 1}, 'scale': 1},
}


def test_a_package_with_two_units_of_its_own_writes_tunings_per_tuner_year(tmp_path):
    """`tunings/tuner-year` needs no entry: the package declares tunings and tuner, and the prelude the
    year and the week. A rate in it runs in execution units, per hour."""
    model = build_model(tuners(tmp_path, COUNTS))
    values = model.resolve('base').values
    year = prelude_units()['year']['scale']
    assert math.isclose(values['tuners.rate'], float(Fraction(1000) / Fraction(year)), rel_tol=1e-13)
    assert model.time['horizon'] == 2 * prelude_units()['week']['scale']


def test_the_model_hash_covers_the_parts_of_a_composed_unit_and_no_unused_unit(tmp_path):
    first = build_model(tuners(tmp_path / 'a', COUNTS)).model_hash
    unused = {**COUNTS, 'pianos': {'dimensions': {'pianos': 1}, 'scale': 1}}
    assert build_model(tuners(tmp_path / 'b', unused)).model_hash == first
    described = {**COUNTS, 'tuner': {**COUNTS['tuner'], 'description': 'One tuner, working full time.'}}
    assert build_model(tuners(tmp_path / 'c', described)).model_hash != first


def test_a_unit_that_is_no_unit_is_an_error_with_the_closest_composition(tmp_path):
    path = tuners(tmp_path, COUNTS)
    path.write_text(TUNERS.replace('input staff: tuner =', 'input staff: tuner/yr ='), encoding='utf-8')
    with pytest.raises(ModelError) as raised:
        build_model(path)
    assert any('tuner/year' in item['message'] for item in raised.value.diagnostics)
