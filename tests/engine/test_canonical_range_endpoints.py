"""A decimal bound written in kL has the same endpoint as the submitted value written in L."""

from fractions import Fraction

import pytest

from napkin.engine import read, run
from napkin.model.compile import compile_text
from napkin.program.record import Key
from tests.reference.from_program import run_of, values_at

UNITS = {'h': {'time': 1}, 'L': {'volume': 1}, 'kL': ({'volume': 1}, 1000)}


def model(scope, bound, value):
    declaration = f'level: kL = 0 L in {bound}'
    lines = ['scenario "Equivalent interval endpoints"', '    horizon 1 h']
    if scope == 'root':
        lines.append(declaration)
    lines += ['yard:', '    seen: L = 0 L', '    limit: L = 100.00000000000001 L']
    if scope == 'member':
        lines.append('    ' + declaration)
    param = f'level: kL in {bound}' if scope == 'parameter' else ''
    lines.append(f'    take = event({param}):')
    if scope == 'local':
        lines.append('        ' + declaration)
    target = 'this.level' if scope == 'member' else 'level'
    rhs = target if scope == 'parameter' else f'{value} L'
    lines += [
        '        after 0.5 h:',
        '            this.limit = 1 L',
        f'            {target} = {rhs}',
        f'            this.seen = {target}',
        '        after 0.5 h',
        f'yard.take.start({value + " L" if param else ""})',
    ]
    return compile_text('\n'.join(lines) + '\n', UNITS)


@pytest.mark.parametrize('scope', ['root', 'member', 'local', 'parameter'])
@pytest.mark.parametrize(
    ('bound', 'value'),
    [
        ('[0 kL, 0.10000000000000001 kL]', '100.00000000000001'),
        ('[-0.10000000000000001 kL, 0 kL]', '-100.00000000000001'),
        ('[0 kL, 0.125 kL]', '125'),
        ('[0 kL, yard.limit]', '100.00000000000001'),
    ],
    ids=['upper', 'lower', 'representable', 'dynamic-snapshot'],
)
def test_the_same_physical_endpoint_is_admitted_once_in_canonical_units(scope, bound, value):
    compiled = model(scope, bound, value)
    oracle, failure = run_of(compiled.program, compiled.configuration)
    assert failure is None, failure
    key = Key('yard', ('seen',))
    assert values_at(oracle, compiled.program, [key], [1])[key] == [Fraction(value)]
    record = run(compiled.program, compiled.configuration)
    assert record.failure is None, record.failure
    assert read(record, compiled.program, [key], [1])[0].values == (float(value),)


@pytest.mark.parametrize(
    ('bounds', 'objective', 'value'),
    [
        ('0 kL, 0.10000000000000001 kL', 'maximize', '100.00000000000001'),
        ('-0.10000000000000001 kL, 0 kL', 'minimize', '-100.00000000000001'),
        ('0 kL, 0.125 kL', 'maximize', '125'),
        ('0 kL, this.limit', 'maximize', '100.00000000000001'),
    ],
    ids=['upper', 'lower', 'representable', 'dynamic'],
)
def test_a_solver_uses_the_same_physical_endpoints_as_a_stored_field(bounds, objective, value):
    source = f'''scenario "Solver endpoint"
    horizon 1 h
yard:
    limit: L = 100.00000000000001 L
    choose = solver:
        solve_for:
            level: kL in [{bounds}]
        objective:
            {objective}(level)
observed: formula(L) = formula(yard.choose.level)
'''
    compiled = compile_text(source, UNITS)
    oracle, failure = run_of(compiled.program, compiled.configuration)
    assert failure is None, failure
    key = Key('', ('observed',))
    assert values_at(oracle, compiled.program, [key], [0])[key] == [Fraction(value)]
    record = run(compiled.program, compiled.configuration)
    assert record.failure is None, record.failure
    assert read(record, compiled.program, [key], [0])[0].values == (float(value),)
