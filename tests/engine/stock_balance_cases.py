"""Exact balances and atomic boundary decisions for stocks with and without an idle pipe."""

from dataclasses import dataclass
from decimal import Decimal
from fractions import Fraction
from hashlib import sha256
from random import Random

from napkin.engine import read, run
from napkin.model.compile import compile_text
from napkin.program.record import Key
from tests.reference.evaluate import label
from tests.reference.from_program import run_of, value_at


@dataclass(frozen=True)
class Case:
    name: str
    source: str
    balances: tuple
    moves: tuple
    refused: bool = False


def _model(fields, stages, idle=False):
    lines = ['scenario "Stock balances"', '    horizon 2 h', 'yard:']
    lines.extend(f'    {name}: L = {number} L{bounds}' for name, number, bounds in fields)
    if idle:
        lines.extend(('    flow idle: this.stock -> SINK', '        request = 0 L/h'))
    lines.append('    work = event():')
    for statements in stages:
        lines.append('        after 1 h:')
        lines.extend('            ' + statement for statement in statements)
    return '\n'.join((*lines, 'yard.work.start()', ''))


def _move(amount, source, destination):
    return f'move {amount} L from this.{source} to this.{destination}'


LOWER = ' in [0 L,]'


def _inventory(seed):
    rng = Random(seed)
    multiplier = 1 if not seed else rng.randint(1, 250)
    small = Decimal('5e-9') if not seed else Decimal(rng.randint(1, 6)).scaleb(-9)
    for op in ('+=', '=', '-='):
        stock = Decimal(10**16 if op == '=' else 10**8) * multiplier
        amount = Decimal(1) if op == '=' else small
        bulk = stock - 2 * amount if op == '-=' else stock
        write = f'this.stock {op} {amount} L' if op != '=' else f'this.stock = this.stock + {amount} L'
        fields = (('stock', stock, LOWER), ('bulk', 0, LOWER), ('receipt', 0, LOWER))
        stages = ((write, _move(bulk, 'stock', 'bulk')), (_move(amount, 'stock', 'receipt'),))
        for idle in (False, True):
            yield Case(
                op + ('.idle' if idle else '.move-only'),
                _model(fields, stages, idle),
                (('stock', 0), ('bulk', bulk), ('receipt', amount)),
                ((1, 'stock', 'bulk', bulk), (2, 'stock', 'receipt', amount)),
            )
    principal = Decimal(4 * 10**6) * multiplier
    extra = Decimal('1e-10') if not seed else Decimal(rng.randint(1, 9)).scaleb(-11)
    fields = (
        ('anchor', principal + extra, LOWER),
        ('stock', f'this.anchor + {extra}', LOWER),
        ('bulk', 0, LOWER),
        ('receipt', 0, LOWER),
    )
    stages = (
        (_move(principal, 'stock', 'bulk'), _move(principal, 'anchor', 'bulk')),
        (_move(2 * extra, 'stock', 'receipt'), _move(extra, 'anchor', 'receipt')),
    )
    yield Case(
        'stock-dependent-opening',
        _model(fields, stages),
        (('anchor', 0), ('stock', 0), ('bulk', 2 * principal), ('receipt', 3 * extra)),
        (
            (1, 'stock', 'bulk', principal),
            (1, 'anchor', 'bulk', principal),
            (2, 'stock', 'receipt', 2 * extra),
            (2, 'anchor', 'receipt', extra),
        ),
    )
    upper = principal + extra
    bounded = (('stock', 0, f' in [0 L, {upper} L]'), ('bulk', 0, LOWER), ('receipt', 0, LOWER))
    stages = (
        (f'this.stock = {upper} L', _move(principal, 'stock', 'bulk')),
        (_move(extra, 'stock', 'receipt'),),
    )
    yield Case(
        'assign-decimal-bound',
        _model(bounded, stages),
        (('stock', 0), ('bulk', principal), ('receipt', extra)),
        ((1, 'stock', 'bulk', principal), (2, 'stock', 'receipt', extra)),
    )


def _capacity(seed):
    rng = Random(seed)
    replicas = 1 if not seed else rng.randint(1, 250)
    for magnitude, step in ((10**16, Decimal(1)), (4 * 10**6, Decimal('3e-10'))):
        base = Decimal(magnitude) * replicas
        for shortage in ('destination', 'source'):
            destination_full = shortage == 'destination'
            bounds = f' in [0 L, {base} L]' if destination_full else f' in [{base} L,]'
            fields = (('stock', base, bounds), ('supply', 4 * step, LOWER), ('receipt', 0, LOWER))
            first = ('stock', 'receipt') if destination_full else ('supply', 'stock')
            second = ('supply', 'stock') if destination_full else ('stock', 'receipt')
            # The second stage includes an earlier valid move. Its entries and physical
            # changes must roll back together if the last transfer is even one unit short.
            stages = (
                (_move(step, *first),),
                (_move(step, 'supply', 'receipt'), _move(2 * step, *second)),
            )
            yield Case(
                f'{shortage}.{magnitude}',
                _model(fields, stages),
                (
                    ('stock', base - step if destination_full else base + step),
                    ('supply', 4 * step if destination_full else 3 * step),
                    ('receipt', step if destination_full else 0),
                ),
                ((1, *first, step),),
                refused=True,
            )
    principal = Decimal(4 * 10**6) * replicas
    leftover = Decimal('1e-10') if not seed else Decimal(rng.randint(1, 9)).scaleb(-11)
    fields = (
        ('stock', principal, f' in [0 L, {principal + leftover} L]'),
        ('small', leftover, LOWER),
        ('bulk', 0, LOWER),
    )
    stages = ((_move(leftover, 'small', 'stock'),), (_move(principal, 'stock', 'bulk'),))
    yield Case(
        'exact-capacity',
        _model(fields, stages),
        (('stock', leftover), ('small', 0), ('bulk', principal)),
        ((1, 'small', 'stock', leftover), (2, 'stock', 'bulk', principal)),
    )
    for funded in ('opening', 'transfer'):
        opening = principal + leftover if funded == 'opening' else principal
        fields = (
            ('stock', opening, LOWER),
            ('bulk', 0, LOWER),
            ('small', 0 if funded == 'opening' else leftover, LOWER),
        )
        stages = ((_move(principal, 'stock', 'bulk'),),)
        moves = ((1, 'stock', 'bulk', principal),)
        if funded == 'transfer':
            stages = ((_move(leftover, 'small', 'stock'),), *stages)
            moves = ((1, 'small', 'stock', leftover), (2, 'stock', 'bulk', principal))
        yield Case(
            'leftover.' + funded,
            _model(fields, stages),
            (('stock', leftover), ('bulk', principal), ('small', 0)),
            moves,
        )


def _observe(case, model, reference):
    keys = tuple(Key('yard', (name,)) for name, _ in case.balances)
    if reference:
        record, error = run_of(model.program, model.configuration)
        failure = str(error) if error is not None else ''
        at = record.view.t
        amounts = tuple(value_at(record, model.program, key, at) for key in keys)
        moves = tuple(
            (when, label(src), label(dst), amount)
            for kind, *args in record.ledger
            if kind == 'move'
            for when, src, dst, amount in [args]
        )
    else:
        record = run(model.program, model.configuration)
        failure = record.failure.detail('message') if record.failure else ''
        at = record.end
        amounts = tuple(row.values[0] for row in read(record, model.program, keys, [at]))
        moves = tuple(
            (entry.t, entry.detail('source'), entry.detail('destination'), entry.detail('amount'))
            for entry in record.entries('move')
        )
    outcome = 'refused' if 'nothing is moved' in failure else (failure or 'finished')
    number = Fraction if reference else float
    expected_moves = tuple((at, 'yard.' + src, 'yard.' + dst, number(n)) for at, src, dst, n in case.moves)
    checks = {
        'outcome': (outcome, 'refused' if case.refused else 'finished'),
        'end': (at, 2),
        'moves': (moves, expected_moves),
    }
    for (name, expected), actual in zip(case.balances, amounts, strict=True):
        checks[name] = actual, number(expected)
    return {what: (actual, expected) for what, (actual, expected) in checks.items() if actual != expected}


def check_stock_balance(seed, family):
    """Exercise every inventory or boundary subcase before reporting the differences for this seed."""
    differences = {}
    for case in {'inventory': _inventory, 'capacity': _capacity}[family](seed):
        found = {}
        try:
            model = compile_text(case.source, {'h': {'time': 1}, 'L': {'volume': 1}})
        except Exception as error:
            found['compile'] = f'{type(error).__name__}: {error}'
        else:
            for reference in (False, True):
                who = 'reference' if reference else 'engine'
                try:
                    mismatch = _observe(case, model, reference)
                except Exception as error:
                    found[who] = f'{type(error).__name__}: {error}'
                else:
                    if mismatch:
                        found[who] = mismatch
        if found:
            differences[case.name] = {
                'source_sha256': sha256(case.source.encode()).hexdigest(),
                'source': case.source,
                **found,
            }
    assert not differences, (seed, family, differences)
