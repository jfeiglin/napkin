"""File, table and distribution number spellings against independently authored builder inputs."""

import json
from fractions import Fraction
from functools import partial
from pathlib import Path
from tempfile import TemporaryDirectory

from napkin.model import load_scenario
from napkin.model.compile import compile_text
from napkin.program import build as b
from tests.engine.authored_number_cases import HEADER, empty_library, spellings
from tests.engine.program_parity import authored_number, check_pairs

UNITS = {'h': {'time': 1}}


def from_text(source, tables=None):
    return compile_text(HEADER + source, UNITS, tables=tables).program


def scaled_program(location, token, declaration):
    with TemporaryDirectory() as raw:
        folder = Path(raw)
        units = {'hx': {'dimensions': {'time': 1}, 'scale': 'EXACT_TOKEN'}}
        if location == 'package':
            settings, obj, header = folder / 'units.json', units, HEADER
        else:
            library = folder / 'library'
            library.mkdir()
            settings = library / 'vocabulary.json'
            obj = dict(empty_library(), id='timing', title='Timing', units=units)
            header = HEADER + '    library "library"\n'
        settings.write_text(json.dumps(obj).replace('"EXACT_TOKEN"', token))
        entry = folder / 'model.scn'
        entry.write_text(header + declaration + '\n')
        return load_scenario(entry).program


def scalar(units, unit, init, base):
    builder = b.Builder(units)
    bounds = {} if base is None else dict(lower=b.q(0, 'h'), upper=b.q(base, 'h'))
    builder.root(b.input_('amount', unit, init, **bounds))
    return builder.finish()


def scaled_pairs(base, inside, outside):
    for location in ('package', 'vocabulary'):
        for token in (inside, outside):
            units = {**UNITS, 'hx': ({'time': 1}, Fraction(token))}
            for field, declaration, kind, operand, bound in (
                ('scale', 'hx = 1 hx', 'hx', b.q(1, 'hx'), None),
                ('quantity', f'h = 1 hx in [0 h, {base} h]', 'h', b.q(1, 'hx'), base),
                ('literal', f'h = {token} h in [0 h, {base} h]', 'h', b.q(authored_number(token), 'h'), base),
            ):
                yield (
                    f'{location}/{token}/{field}',
                    partial(scaled_program, location, token, 'input amount: ' + declaration),
                    partial(scalar, units, kind, operand, bound),
                    bound is None or Fraction(token) <= base,
                )


def table_program(token, base):
    builder = b.Builder(UNITS)
    bounds = {} if base is None else dict(lower=b.q(0, 'h'), upper=b.q(base, 'h'))
    cell = builder.template('Cell', b.input_('amount', 'h', b.q(0, 'h'), **bounds))
    builder.table('cells', cell, [{'id': 'one', 'amount': authored_number(token)}])
    return builder.finish()


def cell_pairs(base, inside, outside, tiny, big):
    for token in ('-' + tiny, tiny, str(base), outside, big, '-' + big):
        bounded = token not in (big, '-' + big)
        bounds = f' in [0 h, {base} h]' if bounded else ''
        accepted = bounded and 0 <= Fraction(token) <= base
        source = f'Cell:\n    input amount: h = 0 h{bounds}\ncells: Cell from "cells.csv"\n'
        table = {'cells.csv': f'id,amount: h\none,{token}\n'}
        yield (
            f'table/{token}',
            partial(from_text, source, table),
            partial(table_program, token, base if bounded else None),
            accepted,
        )
        if bounded:
            yield (
                f'literal/{token}',
                partial(from_text, f'input amount: h = {token} h{bounds}\n'),
                partial(scalar, UNITS, 'h', b.q(authored_number(token), 'h'), base),
                accepted,
            )
    for token in (outside, inside, str(base)):
        init = b.draw(b.uniform(0, authored_number(token), 'h'))
        yield (
            f'draw/{token}',
            partial(from_text, f'input amount: h = uniform(0 h, {token} h).draw() in [0 h, {base} h]\n'),
            partial(scalar, UNITS, 'h', init, base),
            Fraction(token) <= base,
        )


def play_program(base):
    builder = b.Builder(UNITS)
    box = builder.entity(
        'box',
        b.value('n', '', 0, lower=0, upper=base),
        b.event('pause', b.after(b.q(0, 'h'), b.assign(b.this.n, b.this.n))),
    )
    builder.setup(b.start(box.pause))
    return builder.finish()


def check_number_parity(seed):
    base, inside, outside, tiny, big = spellings(seed)
    play = f'box:\n    n: number = 0 in [0, {base}]\n    pause = event():\n        after 0 h:\n            this.n = this.n\nbox.pause.start()\n'
    check_pairs(
        seed,
        (
            *scaled_pairs(base, inside, outside),
            *cell_pairs(base, inside, outside, tiny, big),
            ('cli model', partial(from_text, play), partial(play_program, base), True),
        ),
    )
