"""The builder's field and event parameter must reject a reversed interval beyond its band."""

from fractions import Fraction

from napkin.program.build import Builder, after, event, param, q, start, value
from napkin.program.check import ProgramError


def check(kind):
    b = Builder({'h': {'time': 1}})
    lo, hi = q(Fraction(2, 10**9), 'h'), q(0, 'h')
    if kind == 'field':
        b.entity('box', value('duration', 'h', hi, lower=lo, upper=hi))
    else:
        box = b.entity('box', event('receive', param('duration', 'h', lower=lo, upper=hi), after(q(1, 'h'))))
        b.setup(start(box.receive, hi))
    try:
        b.finish()
    except ProgramError as error:
        assert 'range' in str(error).lower(), error
        return
    raise AssertionError(f'{kind} accepted the reversed interval')


if __name__ == '__main__':
    for field_kind in ('field', 'parameter'):
        check(field_kind)
