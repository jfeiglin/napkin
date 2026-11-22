"""Exact authored numbers through the package loader, table reader and command-line readers."""

import json
import math
import re
from decimal import Decimal
from fractions import Fraction
from pathlib import Path
from random import Random
from tempfile import TemporaryDirectory

from napkin.commands import common, play, sample
from napkin.commands.run import Offered
from napkin.engine.expectations import exceedance
from napkin.engine.timeline import read, run
from napkin.model import load_scenario
from napkin.model.language.problems import LanguageError
from napkin.model.library import empty_library
from napkin.program.checkpoint import Breakpoint
from napkin.session import Session

HEADER = 'scenario "Numbers"\n    horizon 1 h\n'
NUMBER = re.compile(r'(?<![\w.])[-+]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][-+]?\d+)?')


def spellings(seed):
    rng = Random(seed)
    base = 1 if seed == 0 else rng.randint(1, 9)
    offset = Decimal('1e-17') if seed == 0 else Decimal(rng.randint(1, 9)).scaleb(-rng.randint(18, 22))
    tiny = '1e-325' if seed == 0 else f'{rng.randint(1, 9)}e-{rng.randint(325, 345)}'
    big = '1e400' if seed == 0 else f'{rng.randint(1, 9)}e{rng.randint(310, 410)}'
    return base, str(base - offset), str(base + offset), tiny, big


def compiled(entry):
    """Keep a public diagnostic distinct from an exception escaping the loader."""
    try:
        return load_scenario(entry), 'accepted', ''
    except LanguageError as error:
        problem = error.problems[0]
        return None, problem.code, problem.message
    except Exception as error:
        return None, f'{type(error).__name__}: {error}', ''


def expect(differences, label, actual, wanted):
    if actual != wanted:
        differences[label] = (actual, wanted)


def diagnostic_number(differences, label, message, token):
    if not any(Fraction(match.group()) == Fraction(token) for match in NUMBER.finditer(message)):
        differences[label + '.diagnostic'] = (message, token)


def units(root, seed, differences):
    base, inside, outside, _, _ = spellings(seed)
    for location in ('package', 'vocabulary'):
        folder = root / location
        folder.mkdir()
        entry = folder / 'model.scn'
        header = HEADER
        if location == 'vocabulary':
            (folder / 'library').mkdir()
            unit_file = folder / 'library/vocabulary.json'
            header += '    library "library"\n'
        else:
            unit_file = folder / 'units.json'
        for spelling in (inside, outside):
            shape = {'hx': {'dimensions': {'time': 1}, 'scale': 'SCALE'}}
            if location == 'vocabulary':
                shape = {**empty_library(), 'id': 'timing', 'title': 'Timing', 'units': shape}
            unit_file.write_text(json.dumps(shape).replace('"SCALE"', spelling))
            # An unrestricted declaration exposes the stored scale even when a subsequent
            # bounded declaration is rejected. The expected scale comes from the input token.
            entry.write_text(header + 'input amount: hx = 1 hx\n')
            model, status, _ = compiled(entry)
            actual = status if model is None else model.program.unit('hx').scale
            expect(differences, f'{location}.{spelling}.scale', actual, Fraction(spelling))
            wanted = 'range' if Fraction(spelling) > base else 'accepted'
            for form, quantity in [('unit', '1 hx'), ('literal', f'{spelling} h')]:
                entry.write_text(header + f'input amount: h = {quantity} in [0 h, {base} h]\n')
                _, status, message = compiled(entry)
                label = f'{location}.{spelling}.{form}'
                expect(differences, label, status, wanted)
                if form == 'literal' and status == wanted == 'range':
                    diagnostic_number(differences, label, message, spelling)


def cells(root, seed, differences):
    base, inside, outside, tiny, big = spellings(seed)
    entry, table = root / 'model.scn', root / 'cells.csv'
    bounded = f' in [0 h, {base} h]'
    for token, bounds, wanted in (
        ('-' + tiny, bounded, 'range'),
        (tiny, bounded, 'accepted'),
        (str(base), bounded, 'accepted'),
        (outside, bounded, 'range'),
        (big, '', 'diagnostic'),
        ('-' + big, '', 'diagnostic'),
    ):
        entry.write_text(HEADER + f'Cell:\n    input amount: h = 0 h{bounds}\ncells: Cell from "cells.csv"\n')
        table.write_text(f'id,amount: h\none,{token}\n')
        _, status, message = compiled(entry)
        if wanted == 'diagnostic' and message:
            status = 'diagnostic'
        expect(differences, f'table.{token}', status, wanted)
        if status == wanted == 'range':
            diagnostic_number(differences, f'table.{token}', message, token)
        if bounds:
            entry.write_text(HEADER + f'input amount: h = {token} h{bounds}\n')
            _, text_status, message = compiled(entry)
            expect(differences, f'text.{token}', text_status, wanted)
            if text_status == wanted == 'range':
                diagnostic_number(differences, f'text.{token}', message, token)
    for token, wanted in ((outside, 'range'), (inside, 'accepted'), (str(base), 'accepted')):
        entry.write_text(HEADER + f'input amount: h = uniform(0 h, {token} h).draw(){bounded}\n')
        _, status, _ = compiled(entry)
        expect(differences, f'uniform.{token}', status, wanted)


def cli(root, seed, differences):
    base, inside, outside, tiny, big = spellings(seed)
    entry = root / 'model.scn'
    entry.write_text(
        HEADER + f'box:\n    n: number = 0 in [0, {base}]\n    pause = event():\n'
        '        after 0 h:\n            this.n = this.n\nbox.pause.start()\n'
    )
    model = load_scenario(entry)
    known = Offered(run(model.program, model.configuration), model.program)
    for token in ('-' + tiny, tiny, '0', inside, str(base), outside, big, '-' + big, 'NaN', 'Infinity'):
        # The session owns the checkpoint and its unit/bounds. Start each edit at the same stop.
        session = Session(model.program, model.configuration, (Breakpoint('box.pause.step[0]'),))
        session.advance()
        number = Decimal(token)
        writable = number.is_finite() and 0 <= number <= base
        label = f'play.{token}'
        before = session.log
        try:
            play.edited(session, 'box.n', token)
        except ValueError:
            expect(differences, label, 'refused', 'accepted' if writable else 'refused')
            expect(differences, label + '.edits', session.log.edits, before.edits)
        else:
            expect(differences, label, 'accepted', 'accepted' if writable else 'refused')
            if writable and token == inside:
                saved = root / 'edited.checkpoint'
                session.save(saved)
                restored = Session.load(saved, model.program)
                restored.advance()
                actual = read(restored.record, model.program, ['box.n'], [1])[0].values[0]
                expect(differences, label + '.restored', actual, float(number))
        label = f'sample.{token}'
        # The two sample outcomes are exactly representable. A strict exceedance must compare
        # against the submitted decimal even when it rounds to one of those samples as a float.
        valid = math.isfinite(float(number))
        wanted = sum(Decimal(value) > number for value in (0, base)) / 2 if valid else 'refused'
        try:
            ((_, threshold),) = sample.exceedances([f'box.n={token}'], known)
        except common.UsageError:
            actual = 'refused'
        else:
            actual = exceedance([0.0, float(base)], threshold).value
        expect(differences, label, actual, wanted)


def check_authored_number(seed, family):
    differences = {}
    with TemporaryDirectory(prefix='napkin-number-') as root:
        {'units': units, 'cells': cells, 'cli': cli}[family](Path(root), seed, differences)
    assert not differences, (seed, family, differences)
