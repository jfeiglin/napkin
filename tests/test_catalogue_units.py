"""The catalogue's composed unit spellings retain the dimensions and scales of its evidence."""

import json
from pathlib import Path

import pytest

from napkin.core.units import scale_of
from napkin.model.compile import compile_text, library_units
from napkin.model.language.problems import LanguageError
from napkin.model.library import read_vocabulary

VOCABULARY = Path(__file__).resolve().parents[1] / 'scenarios' / 'library' / 'vocabulary.json'


def test_shared_compounds_compile_at_their_filed_physical_scale():
    definitions = json.loads(VOCABULARY.read_text(encoding='utf-8'))['units']
    spellings = {}
    for name in definitions:
        if '-' not in name and '/' not in name:
            continue
        # The old notation joins products with a hyphen, also in a denominator.
        numerator, *denominators = name.split('/')
        spelling = numerator.replace('-', '*') + ''.join('/' + d.replace('-', '/') for d in denominators)
        # m/s is a primitive speed in the original vocabulary.
        spellings[name] = 'metres_per_second' if name == 'm/s' else spelling

    fields = [f'input quantity_{i}: {unit} = 1 {unit}' for i, unit in enumerate(spellings.values())]
    source = '\n'.join(['scenario "Catalogue quantities"', '    horizon 1 h', *fields, ''])
    program = compile_text(source, library_units(read_vocabulary(VOCABULARY))).program
    for name, spelling in spellings.items():
        unit = program.unit(spelling)
        assert dict(unit.dimension) == definitions[name]['dimensions'], name
        assert unit.scale == scale_of(definitions[name]['scale']), name


def test_prices_from_different_years_still_need_an_explicit_conversion():
    units = library_units(read_vocabulary(VOCABULARY))
    with pytest.raises(LanguageError) as refused:
        compile_text('input price: USD2005 = 1 USD2020\n', units)
    assert refused.value.codes == ['unit']
