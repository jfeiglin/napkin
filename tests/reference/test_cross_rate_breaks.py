"""The reference must carry each upstream rate through its dependents at a switch."""

from fractions import Fraction as F

from napkin.model.compile import compile_text
from napkin.program.record import Key
from tests.reference.from_program import run_of, values_at

UNITS = {'L': {'volume': 1}, 'h': {'time': 1}}
PIPE = Key('yard', ('pipe', 'actual_rate'))
WATER = Key('yard', ('water',))


def reads(source, times):
    model = compile_text(source, UNITS)
    run, error = run_of(model.program, model.configuration)
    assert error is None, error
    return values_at(run, model.program, (PIPE, WATER), times)


def test_a_second_rate_follows_a_first_rate_through_the_downstream_capacity_switch():
    # tap = 2t and relay = 4t. Pipe changes from 2 to 1/4 L/h at t = 1/4.
    source = """scenario "Earlier rates"
    horizon 2 h
yard:
    meter: L = 0 L
    middle: L = 0 L
    water: L = 0 L
    flow tap: SOURCE -> this.meter
        request = formula(2 * t / 1 h * 1 L/h)
    flow relay: SOURCE -> this.middle
        request = formula(2 * this.tap.actual_rate)
    flow pipe: SOURCE -> this.water
        request = 2 L/h
        capacity = formula(0.25 L/h if this.relay.actual_rate > 1 L/h else 2 L/h)
"""
    rows = reads(source, [F(1, 8), F(1, 2), F(2)])
    assert (tuple(rows[PIPE]), tuple(rows[WATER])) == ((2, F(1, 4), F(1, 4)), (F(1, 4), F(9, 16), F(15, 16)))


def test_a_rate_driven_by_a_store_moves_below_its_keyed_cutoff_after_contact():
    # driver = t, tap = 1.25 - t/2. At t = 3/4 the tap moves below 0.875 L/h.
    source = """scenario "Falling rate"
    horizon 1 h
Band:
    input cutoff: L/h = 0 L/h
    input rate: L/h = 0.5 L/h
low: Band
high: Band
    cutoff = 0.875 L/h
    rate = 2 L/h
yard:
    meter: L = 0 L
    water: L = 0 L
    driver: L = 0 L
    flow wind: SOURCE -> this.driver
        request = 1 L/h
    flow tap: SOURCE -> this.meter
        request = formula(1.25 L/h - this.driver / (2 h))
    flow pipe: SOURCE -> this.water
        request = 2 L/h
        capacity = formula(Band.instances.by(cutoff).at(this.tap.actual_rate).rate)
"""
    rows = reads(source, [F(1, 2), F(7, 8), F(1)])
    assert (tuple(rows[PIPE]), tuple(rows[WATER])) == ((2, F(1, 2), F(1, 2)), (1, F(25, 16), F(13, 8)))
