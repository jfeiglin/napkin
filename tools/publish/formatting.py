"""Shared display precision for calculated counts and outcomes."""

import re
from decimal import ROUND_HALF_UP, Decimal

OUTSIDE = 'Outside this pathway'
# A money amount: dollars of a stated (or unstated) price year, in ones, millions or billions. The
# library's units agree: each has one currency dimension and this many dollars as its scale.
MONEY_UNIT = re.compile(r'USD(?:\d{4})?(_m|_bn)?')
MONEY_SCALES = {None: 1, '_m': 1e6, '_bn': 1e9}
# Below this magnitude a calculated value is a numerical residual, shown as ≈0.
NEGLIGIBLE = 1e-6


def dollars(unit):
    """Dollars in one ``unit`` when it is a money amount, such as USD2025_bn; otherwise None."""
    match = MONEY_UNIT.fullmatch(unit or '')
    return MONEY_SCALES[match[1]] if match else None


def decimal_text(value):
    """A Decimal as grouped plain decimal text without trailing fractional zeros; never an exponent."""
    text = format(value, ',f')
    return text.rstrip('0').rstrip('.') if '.' in text else text


def rounded(value, significant):
    """``value`` as an exact Decimal at ``significant`` figures, ties half up.

    A carry into the next power of ten keeps the figure count: 999.6 at three figures is 1.00E+3.
    """
    number = Decimal(str(value))
    if not number:
        return number
    for _ in range(2):
        quantum = Decimal(1).scaleb(number.adjusted() - (significant - 1))
        number = number.quantize(quantum, rounding=ROUND_HALF_UP)
    return number
