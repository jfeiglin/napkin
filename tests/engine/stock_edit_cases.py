"""Exact edits on a stock before, between or in the same stage as its only two moves."""

from fractions import Fraction
from random import Random
from traceback import format_exc

from napkin.commands.run import Offered
from napkin.engine.timeline import Plan, Run, read
from napkin.model.compile import compile_text
from napkin.program.checkpoint import Breakpoint, Checkpoint, dumps, loads
from napkin.program.record import Key
from tests.reference.from_program import run_of, value_at

UNITS = {'h': {'time': 1}, 'L': {'volume': 1}}
TANK = Key('yard', ('tank',))
STOPS = {
    'before': 'yard.transfer.step[0]',
    'between': 'yard.transfer.step[1]',
    'within': 'yard.transfer.step[0].do[1]',
}


def stock_edit_amounts(seed):
    """Opening amount, transfer in, whole part of the edit and retained fractional remainder."""
    if seed == 0:
        return 0, 2, 5, Fraction(0)
    rng = Random(seed)
    opening = rng.choice((10**8, 10**12, 10**16)) if seed % 2 else rng.randrange(9)
    intake = rng.randrange(1, 8)
    principal = opening + intake + rng.choice((-1, 1)) * rng.randrange(1, 5)
    principal = max(principal, 1)
    remainder = Fraction(rng.randrange(1, 10), 10 ** rng.randrange(11, 16)) if seed % 2 else Fraction(0)
    return opening, intake, principal, remainder


def stock_edit_source(seed, position, idle):
    opening, intake, principal, _ = stock_edit_amounts(seed)
    idle_flow = '    flow idle: SOURCE -> this.tank\n        request = 0 L/h\n' if idle else ''
    second_stage = '' if position == 'within' else '        after 0.5 h:\n'
    withdraw = principal + intake if position == 'before' else principal
    return f"""scenario "Edit a transfer stock"
    horizon 1 h
yard:
    tank: L = {opening} L in [0 L,]
    supply: L = {intake} L in [0 L,]
    receipt: L = 0 L in [0 L,]
    ordinary = 7
{idle_flow}    transfer = event():
        after 0.25 h:
            move {intake} L from this.supply to this.tank
{second_stage}            move {withdraw} L from this.tank to this.receipt
yard.transfer.start()
"""


def _expect(differences, label, actual, expected):
    if actual != expected:
        differences[label] = {'actual': str(actual), 'expected': str(expected)}


def _external(record, program, stock, times):
    try:
        return read(record, program, [f'yard.{stock}.external'], list(times))[0].values
    except KeyError as error:
        return str(error)


def _record(differences, label, record, program, times, external):
    offered = Offered(record, program)
    for name in ('tank', 'receipt', 'supply', 'ordinary'):
        path = f'yard.{name}.external'
        actual = _external(record, program, name, times)
        is_stock = name != 'ordinary'
        if is_stock:
            wanted = external if name == 'tank' else (0,) * len(times)
            _expect(differences, f'{label}.read.{name}', actual, wanted)
        else:
            _expect(differences, f'{label}.read.{name}', isinstance(actual, str), True)
        _expect(differences, f'{label}.listed.{name}', path in offered.held, is_stock)
        _expect(differences, f'{label}.offered.{name}', offered.refused(path) is None, is_stock)


def _case(seed, position, idle, differences):
    opening, intake, principal, remainder = stock_edit_amounts(seed)
    replacement = principal + remainder
    incoming = opening if position == 'before' else opening + intake
    delta = replacement - incoming
    withdraw = principal + intake if position == 'before' else principal
    stop = STOPS[position]
    label = f'{position}.{"idle" if idle else "move-only"}'
    model = compile_text(stock_edit_source(seed, position, idle), UNITS)
    balances = {'tank': remainder, 'receipt': withdraw, 'supply': 0}
    oracle, error = run_of(model.program, model.configuration, [(stop, None, [(TANK, replacement)])])
    _expect(differences, label + '.reference.failure', error, None)
    if error is None:
        for name, wanted in balances.items():
            observed = value_at(oracle, model.program, Key('yard', (name,)), 1)
            _expect(differences, f'{label}.reference.balance.{name}', observed, wanted)
        external = sum(
            change for kind, *_, cell, change in oracle.ledger if kind == 'edit' and cell.name == 'tank'
        )
        _expect(differences, label + '.reference.external', external, delta)

    plan = Plan.of(model.program, model.configuration)
    live = Run(plan, (Breakpoint(stop),))
    paused = live.run()
    if not isinstance(paused, Checkpoint):
        _expect(differences, label + '.stop', str(paused.failure), stop)
        return
    _record(differences, label + '.checkpoint', paused.record, model.program, (0,), (0,))
    edited = live.edit(TANK, replacement)
    edit_time = 0.75 if position == 'between' else 0.25
    times = (1, 0, edit_time)
    for route in ('live', 'restored'):
        route_label = f'{label}.{route}'
        machine = (
            live
            if route == 'live'
            else Run.restored(Plan.of(model.program, model.configuration), loads(dumps(edited)))
        )
        final = machine.resume()
        _expect(differences, route_label + '.failure', final.failure, None)
        if final.failure is not None:
            continue
        for name, wanted in balances.items():
            actual = machine.stock_balance('yard.' + name, 1)
            _expect(differences, f'{route_label}.balance.{name}', actual, wanted)
        # The raw booked history and its validity as an external path are independent.
        # An unedited store is entitled to a zero reading without an explicit piece.
        try:
            booked = final.history(Key('yard', ('tank', 'external'))).at(1)
        except KeyError:
            booked = 0
        _expect(differences, route_label + '.booked', booked, float(delta))
        _record(differences, route_label, final, model.program, times, (float(delta), 0, float(delta)))
        actual = read(final, model.program, ['yard.tank', 'yard.receipt'], [1])
        _expect(
            differences,
            route_label + '.final',
            tuple(row.values[0] for row in actual),
            (float(remainder), float(withdraw)),
        )


def check_stock_edit(seed):
    differences = {}
    for position in STOPS:
        for idle in (False, True):
            try:
                _case(seed, position, idle, differences)
            except Exception:
                differences[f'{position}.idle={idle}.exception'] = format_exc()
    assert not differences, (seed, differences)
