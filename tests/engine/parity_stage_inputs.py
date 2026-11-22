"""Common scalar data for the independent text and builder fixtures."""

from decimal import Decimal
from fractions import Fraction

from napkin.model.compile import compile_text
from tests.engine.program_parity import authored_number

UNITS = {'h': {'time': 1}, 'L': {'volume': 1}}


def number(n):
    """Choose the builder's ordinary numeric literal or an exact rational for an authored decimal."""
    if isinstance(n, Fraction):
        return authored_number(format(Decimal(n.numerator) / Decimal(n.denominator), 'f'))
    return authored_number(n)


def text(source, units=UNITS):
    return compile_text(source, units).program
