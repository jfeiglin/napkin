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
from decimal import Decimal
from fractions import Fraction

import pytest
from hypothesis import event, given, settings
from hypothesis import strategies as st

from napkin.engine import read, run
from napkin.model.compile import compile_text, library_units, load_scenario
from napkin.model.language.problems import LanguageError
from napkin.model.library import PRELUDE, empty_library, prelude_units
from napkin.model.load import schema_errors
from napkin.model.semantic import Units
from napkin.program import build
from napkin.program.config import Configuration, Request
from tests.comparison_bands import band_samples

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


# ---- a quantity is its dimension and its scale, however it is spelled ------------------------------

# Three families of units with exact scales, each unit of a family a respelling of the others.
FAMILIES = {
    'time': {'h': Fraction(1), 'min': Fraction(1, 60), 'day': Fraction(24)},
    'volume': {'L': Fraction(1), 'mL': Fraction(1, 1000), 'kL': Fraction(1000)},
    'share': {'ratio': Fraction(1), 'fraction': Fraction(1), 'percent': Fraction(1, 100)},
}
DIMENSIONS = {'time': {'time': 1}, 'volume': {'volume': 1}, 'share': {}}
SPELLED = {
    name: (DIMENSIONS[family], scale) for family, units in FAMILIES.items() for name, scale in units.items()
}
# A caller who already decoded these numbers as floats has lost their original spelling.
# The registry recovers the simple ratio for such a minute; authored JSON retains its exact decimal.
FILED = {
    name: (dimension, json.loads(json.dumps(float(scale)))) for name, (dimension, scale) in SPELLED.items()
}
# A canonical step of each family whose multiples are finite decimals in every unit of the family.
STEPS = {'time': Fraction(24, 100), 'volume': Fraction(1, 1000), 'share': Fraction(1, 100)}


@pytest.mark.parametrize(
    ('scale', 'expected'),
    [
        (float(Fraction(1, 60)), Fraction(1, 60)),
        (Decimal('0.016666666666666666'), Fraction('0.016666666666666666')),
        (Fraction(1, 60), Fraction(1, 60)),
    ],
    ids=['bare-float', 'written-decimal', 'exact-fraction'],
)
def test_both_authors_store_the_exact_unit_scale(scale, expected):
    units = {'tick': ({'time': 1}, scale)}
    builder = build.Builder(units)
    builder.root(build.input_('x', 'tick', build.q(1, 'tick')))
    text = compile_text('input x: tick = 1 tick\n', units)
    for program in (builder.finish(), text.program):
        assert program.unit('tick').scale == expected


def written(value, unit):
    """A canonical value in `unit` as the exact decimal text of it with its unit (`0.1 day`): the
    quotient by the unit's scale is taken in fractions, so a minute's 1/60 is no rounded decimal, and
    a step of `STEPS` has a finite decimal in every unit."""
    number = value / FAMILIES_OF[unit][unit]
    return f'{format((Decimal(number.numerator) / Decimal(number.denominator)).normalize(), "f")} {unit}'


FAMILIES_OF = {name: units for units in FAMILIES.values() for name in units}


def checked(text, table=SPELLED):
    """(the codes and lines of the problems of a text, or None) and its compiled model, with the
    units of `table`."""
    try:
        return None, compile_text(text, table)
    except LanguageError as error:
        return sorted((item.code, item.line) for item in error.problems), None


RESPELLED = """\
scenario "Respelled"
    horizon {horizon}
input x: {unit} = {a} in [{b}, {c}] scale {scale}
inside = ({a} in [{b}, {c}])
root = sqrt({a} * {d}) scale {scale}
square = ({a}) ** 2 scale {square_scale}
input drawn = triangular({b}, {a}, {c}).draw() scale {scale}
"""


@st.composite
def models(draw):
    """A model of four quantities of one family and a horizon, written twice: each quantity in a unit
    of its family drawn for each writing, and the same canonical value."""
    family = draw(st.sampled_from(sorted(FAMILIES)))
    # Few distinct values, so that equal ends (`[x, x]`, a mode at its minimum) are common; and the
    # first three in order half the time, so that most models pass their checks.
    a, b, c, d = (STEPS[family] * draw(st.integers(0, 4)) for _ in range(4))
    if draw(st.booleans()):
        b, a, c = sorted((a, b, c))
    values = [a, b, c, d]
    horizon = STEPS['time'] * draw(st.integers(1, 40))
    units = st.sampled_from(sorted(FAMILIES[family]))
    hours = st.sampled_from(sorted(FAMILIES['time']))

    def text():
        named = dict(zip('abcd', (written(value, draw(units)) for value in values)))
        base = next(name for name, size in FAMILIES[family].items() if size == 1)
        return RESPELLED.format(
            unit=draw(units),
            horizon=written(horizon, draw(hours)),
            scale=f'1 {base}',
            square_scale=f'1 {base}*{base}',
            **named,
        )

    return text(), text()


def canonical(reading, program):
    """A reading's values in the canonical unit of its dimension (a yes/no as it is)."""
    scale = program.unit(reading.unit).scale if reading.unit else 1
    return tuple(value if isinstance(value, bool) else value * float(scale) for value in reading.values)


@pytest.mark.parametrize('table', [SPELLED, FILED], ids=['exact', 'as filed'])
@settings(derandomize=True, max_examples=60, deadline=None)
@given(texts=models())
def test_respelling_a_unit_never_changes_a_check_or_a_value(table, texts):
    """The rule of units (spec, "Units, comparisons and layout"): a quantity is its dimension and its
    scale, with its number read exactly as written, so writing one in another unit of its family (h,
    min, day; L, mL, kL; ratio, fraction, percent) changes no check of the front end (the range of an
    input and the value in it, the interval of a test, the unit of a square root and of a power, the
    rule of a distribution and the support of a drawn input) and no value: the configuration's
    horizon and each value that the run reads, in canonical units. A yes/no that compares two
    quantities is the same, so a test of `0.1 day` against `2.4 h` is decided as if both were 2.4 h.
    It holds with unit scales supplied as exact fractions or as decoded bare floats (`FILED`)."""
    first, second = (checked(text, table) for text in texts)
    assert first[0] == second[0], texts
    event('refused' if first[0] is not None else 'compiled and ran')
    if first[0] is not None:
        return
    one, two = first[1], second[1]
    assert one.configuration.request.horizon == two.configuration.request.horizon
    paths = ['x', 'inside', 'root', 'square', 'drawn']
    found = [
        [
            canonical(reading, model.program)
            for reading in read(run(model.program, model.configuration), model.program, paths, [0])
        ]
        for model in (one, two)
    ]
    for path, left, right in zip(paths, *found):
        if isinstance(left[0], bool):
            assert left == right, (path, texts)
        else:
            assert left == pytest.approx(right, rel=1e-12), (path, texts)


def test_a_run_reads_equal_quantities_as_one_number():
    """The run converts each quantity once and exactly (`napkin.core.units.UnitRegistry.normalize`):
    `0.1 day`, `144 min` and `2.4 h` are one float, so a test of one against another is decided as
    the quantities are; and a square root or a power reads the dimension, `sqrt(24 h * 1 day)` being
    24 h by the arithmetic of hours."""
    text = (
        'scenario "Equal"\n    horizon 1 h\n'
        'a = 0.1 day\nb = 144 min\nc = 2.4 h\nsame = (0.1 day == 2.4 h)\n'
        'inside = (2.4 h in [0.1 day, 144 min])\nroot = sqrt(24 h * 1 day)\nhalf = (4 h * 1 day) ** 0.5\n'
    )
    model = compile_text(text, SPELLED)
    found = {
        reading.path: canonical(reading, model.program)[0]
        for reading in read(
            run(model.program, model.configuration),
            model.program,
            ['a', 'b', 'c', 'same', 'inside', 'root', 'half'],
            [0],
        )
    }
    assert found['a'] == found['b'] == found['c'] == float(Fraction(12, 5))
    assert found['same'] is True and found['inside'] is True
    assert found['root'] == 24.0 and found['half'] == pytest.approx(96**0.5, rel=1e-15)


@pytest.mark.parametrize(
    ('unit', 'units_per_litre', 'scale', 'equals_zero'),
    [
        ('L', 1, '', True),
        ('mL', 1000, ' scale 1000 mL', True),
        ('mL', 1000, '', False),
    ],
)
def test_respelling_a_near_zero_value_preserves_its_guard_at_the_same_physical_scale(
    unit, units_per_litre, scale, equals_zero
):
    half_band_l, _ = band_samples(Configuration(Request(1)), 1)
    amount = half_band_l * units_per_litre
    model = compile_text(
        f'scenario "Near zero"\n    horizon 1 h\ninput signal: {unit} = {amount} {unit}{scale}\n'
        'close = formula(signal == 0 L)\n',
        SPELLED,
    )
    record = run(model.program, model.configuration)
    assert record.failure is None
    assert read(record, model.program, ['close'], [0])[0].values == (equals_zero,)
