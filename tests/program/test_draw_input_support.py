"""A numeric input drawing directly from a bounded distribution inherits that distribution's range."""

from fractions import Fraction

import pytest

from napkin.engine import run
from napkin.model.compile import compile_text
from napkin.program import build as b
from napkin.program.canonical import program_bytes
from napkin.program.config import Configuration, ConfigurationError, InputValue, Quantity, Request

UNITS = {'h': {'time': 1}, 'min': ({'time': 1}, Fraction(1, 60))}


@pytest.mark.parametrize('scope', ['root', 'member'])
@pytest.mark.parametrize(
    ('source', 'distribution'),
    [
        ('uniform(1 h, 3 h)', b.uniform(1, 3, 'h')),
        ('triangular(1 h, 2 h, 3 h)', b.triangular(1, 2, 3, 'h')),
        ('pert(1 h, 2 h, 3 h)', b.pert(1, 2, 3, 'h')),
        ('loguniform(1 h, 3 h)', b.loguniform(1, 3, 'h')),
        ('normal(2 h, 1 h, 1 h, 3 h)', b.normal(2, 1, 'h', 1, 3)),
        ('lognormal(2 h, 1.2, 1 h, 3 h)', b.lognormal(2, 1.2, 'h', 1, 3)),
        ('normal(2 h, 1 h)', b.normal(2, 1, 'h')),
        ('lognormal(2 h, 1.2)', b.lognormal(2, 1.2, 'h')),
    ],
    ids=[
        'uniform',
        'triangular',
        'pert',
        'loguniform',
        'bounded-normal',
        'bounded-lognormal',
        'open-normal',
        'open-lognormal',
    ],
)
def test_text_and_builder_give_the_draw_input_the_same_domain(scope, source, distribution):
    line = f'input delay: h = {source}.draw()'
    model = compile_text((line if scope == 'root' else f'yard:\n    {line}') + '\n', UNITS)
    make = b.Builder(UNITS)
    part = b.input_('delay', 'h', b.draw(distribution))
    if scope == 'root':
        make.root(part)
    else:
        make.entity('yard', part)
    assert program_bytes(make.finish()) == program_bytes(model.program)


@pytest.mark.parametrize(
    'extra,low,high', [(' in [0 h,]', 0, None), (' in [, 6 h]', None, 6), (' in [0 h, 6 h]', 0, 6)]
)
def test_a_written_bound_keeps_the_supplied_domain(extra, low, high):
    model = compile_text(f'input delay: h = uniform(1 h, 3 h).draw(){extra}\n', UNITS)
    make = b.Builder(UNITS)
    make.root(b.input_('delay', 'h', b.draw(b.uniform(1, 3, 'h')), lower=low, upper=high))
    assert program_bytes(make.finish()) == program_bytes(model.program)


@pytest.mark.parametrize(
    ('written', 'initial'),
    [
        ('this.prior.draw()', b.this.prior.draw()),
        ('uniform(1 h, 3 h).draw() + 1 h', b.draw(b.uniform(1, 3, 'h')) + b.q(1, 'h')),
    ],
    ids=['named-distribution', 'calculated-default'],
)
def test_a_named_or_calculated_default_keeps_its_open_range(written, initial):
    source = f'yard:\n    prior: distribution(h) = uniform(1 h, 3 h)\n    input delay: h = {written}\n'
    expected = compile_text(source, UNITS).program
    make = b.Builder(UNITS)
    make.entity(
        'yard', b.value('prior', b.dist_of('h'), b.uniform(1, 3, 'h')), b.input_('delay', 'h', initial)
    )
    actual = make.finish()
    assert actual.templates[0].values[1].lower is actual.templates[0].values[1].upper is None
    assert program_bytes(actual) == program_bytes(expected)


@pytest.mark.parametrize('minutes,valid', [(29, False), (30, True), (60, True), (90, True), (91, False)])
def test_overrides_respect_the_draws_physical_support_in_a_different_unit(minutes, valid):
    make = b.Builder(UNITS)
    make.entity('yard', b.input_('delay', 'min', b.draw(b.uniform(Fraction(1, 2), Fraction(3, 2), 'h'))))
    config = Configuration(Request(1), inputs=(InputValue('yard', 'delay', Quantity(minutes, 'min')),))
    if valid:
        assert run(make.finish(), config).failure is None
    else:
        with pytest.raises(ConfigurationError, match='outside its admitted range'):
            run(make.finish(), config)
