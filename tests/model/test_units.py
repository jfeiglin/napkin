"""Units (spec, "Units, comparisons and layout"; D12): a spelling with `*` and `/` composes the units of
the library from the left (`semantic.Units`), so `a/b*c` is (a/b)·c and `a/b/c` is a per b per c, and
a name that is no unit makes the spelling no unit. The prelude gives every model its times and people.
Each expected scale and dimension here comes from exact rational arithmetic on the declared parts
(`fractions.Fraction`), never from the registry's own arithmetic.

A package with units of its own composes them with the prelude's: a rate in tunings per tuner per year
runs per hour, and the hash of the model follows the scales of the units that its program uses, and
neither an unused unit nor a unit's description (`napkin/model/identity.py`)."""

from __future__ import annotations

import json
from collections import Counter
from fractions import Fraction

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from napkin.engine import read, run
from napkin.model.compile import library_units, load_scenario
from napkin.model.language.problems import LanguageError
from napkin.model.library import PRELUDE, empty_library, prelude_units
from napkin.model.load import schema_errors
from napkin.model.semantic import Units

# Declared units, name: (dimensions, scale), with scales that are not all exact in binary.
DECLARED = {
    'h': ({'time': 1}, 1),
    'day': ({'time': 1}, 24),
    'year': ({'time': 1}, 8760),
    'person': ({'people': 1}, 1),
    'tuner': ({'tuners': 1}, 1),
    'tunings': ({'tunings': 1}, 1),
    'gal': ({'volume': 1}, Fraction('3.785411784')),
    'ft': ({'length': 1}, Fraction('0.3048')),
    'percentage_points': ({}, Fraction(1, 100)),
    'USD_k': ({'USD': 1}, 1000),
}


def registry():
    return Units(DECLARED)


def exact(factors):
    """(dimensions, scale) of the factors [(+1 or -1, name)], as `Units.of` gives them: the dimensions
    add, each times its sign, and the scale is the product of the scales, each to the power of its
    sign."""
    dimensions, scale = Counter(), Fraction(1)
    for sign, name in factors:
        own, size = DECLARED[name]
        for key, value in own.items():
            dimensions[key] += sign * value
        scale = scale * Fraction(size) if sign > 0 else scale / Fraction(size)
    return tuple(sorted((key, value) for key, value in dimensions.items() if value)), scale


NAME = st.sampled_from(sorted(DECLARED))


@settings(derandomize=True, max_examples=300, deadline=None)
@given(NAME, st.lists(st.tuples(st.sampled_from('*/'), NAME), max_size=4))
def test_a_spelling_is_its_factors_from_the_left(first, rest):
    """Each factor after `*` multiplies what is on its left, and each after `/` divides it."""
    spelling = first + ''.join(op + name for op, name in rest)
    signed = [(1, first), *((1 if op == '*' else -1, name) for op, name in rest)]
    assert registry().of(spelling) == exact(signed), spelling


def test_a_product_after_a_quotient_multiplies_the_quotient():
    """`tunings/tuner*year` is tunings years per tuner (D12); tunings per tuner per year is
    `tunings/tuner/year`, or `tunings / (tuner * year)` in a type."""
    units = registry()
    assert units.of('tunings/tuner*year') == exact([(1, 'tunings'), (-1, 'tuner'), (1, 'year')])
    assert units.of('tunings/tuner/year') == exact([(1, 'tunings'), (-1, 'tuner'), (-1, 'year')])
    assert units.of('tunings/tuner*year') != units.of('tunings/tuner/year')


@pytest.mark.parametrize('spelling', ['furlong', 'tunings/yr', 'h/2', 'gal/h*lb'])
def test_a_spelling_with_a_name_that_is_no_unit_is_no_unit(spelling):
    assert registry().of(spelling) is None


# ---- the prelude ------------------------------------------------------------------------------------


def test_the_prelude_is_a_valid_units_file_of_times_people_and_ratios():
    """Every unit of the prelude is a unit of a units file; each alias has the definition of the unit
    that it names, a day is 24 hours and a week seven days."""
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
    found = Units(library_units(empty_library()))
    assert found.of('days/h') == ((), Fraction(24)) and found.of('week/days') == ((), Fraction(7))


# ---- a package with units of its own -------------------------------------------------------------

TUNERS = """\
scenario "Piano tuners"
    summary "Tuners tune pianos. A synthetic fixture for tests only."
    horizon 2 weeks

tuners:
    "The tuners of the town."
    input rate: tunings/tuner/year = 1000 tunings/tuner/year in [0 tunings/tuner/year, 2000 tunings/tuner/year]  @counted
        "Tunings that one tuner does in a year"
    input staff: tuner = 3 tuner in [1 tuner, 10 tuner]  @counted
        "Tuners"
    done: tunings = 0 tunings  @counted
        "Tunings done"
    flow tune: SOURCE -> this.done  @counted
        request = formula(this.rate * this.staff)

record counted: assumption "Fixture counts."
"""

COUNTS = {
    'tunings': {'dimensions': {'tunings': 1}, 'scale': 1},
    'tuner': {'dimensions': {'tuners': 1}, 'scale': 1},
}


def tuners(folder, units, text=TUNERS):
    """The main file of a package in `folder` that owns the units `units`."""
    folder.mkdir(parents=True)
    (folder / 'model.scn').write_text(text, encoding='utf-8')
    (folder / 'units.json').write_text(json.dumps(units), encoding='utf-8')
    return folder / 'model.scn'


def test_a_package_with_two_units_of_its_own_runs_tunings_per_tuner_per_year_per_hour(tmp_path):
    """The package declares tunings and tuner, and the prelude the year and the week: the horizon is
    two weeks of 168 hours, and three tuners at 1000 tunings a year each do 3000 * 336 / 8760 tunings
    in it."""
    model = load_scenario(tuners(tmp_path / 'tuners', COUNTS))
    hours = 2 * prelude_units()['week']['scale']
    assert model.configuration.request.horizon == hours == 336
    (done,) = read(run(model.program, model.configuration), model.program, ['tuners.done'], [hours])
    assert done.values == pytest.approx((3000 * hours / prelude_units()['year']['scale'],), rel=1e-12)


def test_the_hash_follows_the_scales_that_the_program_uses_and_no_unused_unit_or_description(tmp_path):
    first = load_scenario(tuners(tmp_path / 'a', COUNTS)).model_hash
    unused = {**COUNTS, 'pianos': {'dimensions': {'pianos': 1}, 'scale': 1}}
    assert load_scenario(tuners(tmp_path / 'b', unused)).model_hash == first
    described = {**COUNTS, 'tuner': {**COUNTS['tuner'], 'description': 'One tuner, working full time.'}}
    assert load_scenario(tuners(tmp_path / 'c', described)).model_hash == first
    # Tunings counted by the dozen make every number of tunings another number of the program.
    dozens = {**COUNTS, 'tunings': {'dimensions': {'tunings': 1}, 'scale': 12}}
    assert load_scenario(tuners(tmp_path / 'd', dozens)).model_hash != first


def test_a_name_that_is_no_unit_is_refused_at_its_line_with_the_closest_unit(tmp_path):
    text = TUNERS.replace('input staff: tuner =', 'input staff: tuner/yr =')
    path = tuners(tmp_path / 'tuners', COUNTS, text)
    with pytest.raises(LanguageError) as raised:
        load_scenario(path)
    line = next(number for number, row in enumerate(text.split('\n'), 1) if 'input staff' in row)
    found = [item for item in raised.value.problems if item.code == 'unit']
    assert [(item.file, item.line) for item in found] == [(path.as_posix(), line)]
    assert found[0].message.endswith('did you mean year?')
