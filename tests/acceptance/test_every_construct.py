"""One model that writes every construct of the language, from source to `napkin.engine.run` (gate G1).

The package `every` has a main file with its scenario line, options, runs and notes; a module that it
uses (`use parts`), with every kind of value, unit, range, flow, endpoint setting, route, flow with
legs, table, member, link, collection, reduction, event, stage, guard, gate, trigger, draw (one into
an occurrence's field that a switch reads, as a decision is written since item 15 of the plan's
changes after G0), move, solver, assertion and record; and a variant that changes a value of the
module. Each value
below is worked by hand from the text: a rate times a time, a bound reached, a share of a limit, a
median, the closed form of a solver.

Written elsewhere and not here, for the length of this file: a status display
(`tests/language/test_status.py`, `tests/engine/test_report.py`), the captures of a trigger, an event
parameter that passes an entity (D13), `.at(t)` of occurrences and a start on each member of a
collection (`tests/language/test_events.py`).
"""

from __future__ import annotations

import json
import math

import pytest

from napkin.engine import read, run
from napkin.model.compile import load_scenario
from napkin.model.language.format import format_text
from napkin.model.language.parse import parse

MAIN = """\
scenario "Every construct"
    summary "One model that writes each construct of the language once. A fixture for tests only."
    horizon 4 h
    resolution 1 h
    scope "A fixture."
use parts

options "Fill":
    "Usual fill":
        "The plant fills at its own rate."
    "Quick fill":
        "The plant fills at 4 L/h."
        plant.rate = 4 L/h  @fixture

runs:
    usual = "Usual fill"
    quick = "Quick fill"
        "The quick fill"

notes:
    by: "The fixture"
"""

PARTS = """\
plant:
    "A plant with one tank."
    title "The plant"
    input rate: L/h = 2 L/h in [0 L/h, 10 L/h]  @fixture
        "Fill rate"
    input repair: h = uniform(1 h, 3 h).draw() in [0 h,]  @fixture
    input spread = uniform(1 h, 5 h)  @fixture
    input label: text = "plant"
    readonly tank: L = 0 L in [0 L, 100 L] scale 10 L
    flow fill: SOURCE -> this.tank
        request = this.rate
        capacity = 5 L/h
    mode: enum[CALM, BUSY] = CALM
    low = formula(this.tank < 5 L)
    half: h = 48 h/2
    effort: person * year = (3 person) * (2 year)
    spread_mean: h = this.spread.mean
    spread_std: h = this.spread.std
    clipped = formula(clip(this.tank, 1 L, 6 L))
    over = formula(max(this.tank - 5 L, 0 L))
    root = sqrt(16)
    calm_for = formula(elapsed(this.mode))

reservoir:
    water: L = 20 L in [0 L,]
        outflow.capacity = 10 L/h
        outflow.allocation = priority(hospital.delivery, garden.delivery)

hospital:
    got: L = 0 L in [0 L,]
    flow delivery: reservoir.water -> this.got
        request = 8 L/h

garden:
    got: L = 0 L in [0 L,]
    flow delivery: reservoir.water -> this.got
        request = 12 L/h

spring:
    water: L = 10 L in [0 L,]
        outflow.capacity = 4 L/h
        outflow.allocation = proportional()
    flow small: this.water -> SINK
        request = 2 L/h
    flow large: this.water -> SINK
        request = 6 L/h

filler:
    level: L = 0 L in [0 L,]
    fill = event():
        when t >= 0.5 h:
            this.fill.start()
            reset when false
        flow pipe: SOURCE -> this.level
            request = 3 L/h
        until this.level >= 3 L

west:
    water: L = 10 L in [0 L, 20 L]

east:
    water: L = 10 L in [0 L, 20 L]

channel:
    flow link: west.water <-> east.water
        request = -3 L/h
    backward = formula(this.link.backward.actual_rate)

site:
    work: L = 100 L in [0 L,]
    done: L = 0 L in [0 L,]
    parts: kg = 10 kg in [0 kg,]
    used: kg = 0 kg in [0 kg,]
    flow restore:
        flow labor: this.work -> this.done
            request = 4 L/h
        flow spend: this.parts -> this.used
            request = 8 kg/h
            capacity = 4 kg/h

Place:
    input need: L = 1 L in [0 L,]
    input rank = 0
    big = formula(this.need >= 2 L)

places: Place from "places.csv"

d: Place
    need = 4 L  @fixture
    rank = 4  @fixture

Pump:
    home: Place
    home_need = formula(this.home.need)

pump_one: Pump
    home = places.c

total_need = sum(Place.instances.need)
big_count = count(Place.instances.big)
any_big = any(Place.instances.big)
all_big = all(Place.instances.big)
least = min(Place.instances.need)
most = max(Place.instances.need)
first_ranked = Place.instances.by(rank).at(1).need
ranked_need = sum(Place.instances.where(rank >= 2).need)
pair_need = sum(<places.a, places.c>.need)

grinder:
    beans: g = 8
    readonly low_on_beans: formula(bool) = formula(this.beans <= 10 g)
    refill = event(amount: g):
        after 0.5 h:
            this.beans += amount
    last_refill = formula(since(this.refill))

clock:
    ticks = 0
    tick = event():
        when t >= 1 h:
            this.tick.start()
            reset after 1 h
        after 0 h:
            this.ticks += 1

inspector:
    open: bool = true
    passed = 0
    failed = 0
    inspect = event(level: L):
        ok: bool = false
        after 1 h when this.open:
            ok = level >= 5 L
            if ok:
                this.passed += 1
            else:
                this.failed += 1
    inspections = formula(count(this.inspect.occurrences))

machine:
    operational: bool = false
    check = event():
        after 2 h:
            switch categorical(FIXED: 0.7, FAILED: 0.3).draw():
                FIXED:
                    this.operational = true
                FAILED:
                    this.repair.start()
    repair = event():
        after 0 h

left:
    readonly water: L = 8 in [0,]

right:
    readonly water: L = 0 in [0, 4]

mover:
    shift = event(amount: L):
        after 0 h:
            move amount from left.water to right.water

dispatcher:
    forecast = categorical(SEND: 0, WAIT: 1)

depot:
    spares = 1 in [0,]
    waits = 0
    request_pump = event():
        order: enum[SEND, WAIT] = WAIT
        after 0 h:
            order = dispatcher.forecast.draw()
            switch order:
                SEND when this.spares >= 1:
                    this.send_pump.start()
                WAIT:
                    this.waits += 1
    send_pump = event():
        after 0 h:
            this.spares -= 1

clinic:
    staff_hours: h = 100 h
    outreach_minimum = formula(0.30 * this.staff_hours)
    staffing = solver:
        inputs:
            available = this.staff_hours
            minimum_outreach = this.outreach_minimum
        solve_for:
            care: h in [0 h, available]
            outreach: h in [minimum_outreach, available]
        constraints:
            care + outreach == available
        objective:
            maximize(care)
    cut = event():
        after 1 h:
            this.staff_hours = 80 h

assert plant.rate <= 5 L/h  @fixture
    "The plant fills slowly."
assert reservoir.water >= 0 L

grinder.refill.start(50 g)
inspector.inspect.start(8 L)
inspector.inspect.start(2 L)
machine.check.start()
mover.shift.start(3 L)
depot.request_pump.start()
clinic.cut.start()

record fixture: assumption "A synthetic test fixture."
"""

PLACES = 'id,need,rank\na,1,2\nb,2,1\nc,3,3\n'
WET = 'variant "Wet"\n\nchange reservoir:\n    water = 30 L  @fixture\n'
UNITS = {
    'L': {'dimensions': {'volume': 1}, 'scale': 1},
    'g': {'dimensions': {'mass': 1}, 'scale': 1},
    'kg': {'dimensions': {'mass': 1}, 'scale': 1000},
}

# The values at 2 h and at 3.5 h of the default run of the main file, by hand.
AT = {
    # 2 L/h into a tank with no outflow: 4 L, then 7 L; low below 5 L; clip to [1 L, 6 L].
    'plant.tank': (4, 7),
    'plant.low': (True, False),
    'plant.clipped': (4, 6),
    'plant.over': (0, 2),
    'plant.half': (24, 24),
    'plant.effort': (6, 6),
    'plant.root': (4, 4),
    # The median of uniform(1 h, 3 h), and the mean of uniform(1 h, 5 h).
    'plant.repair': (2, 2),
    'plant.spread_mean': (3, 3),
    'plant.calm_for': (2, 3.5),
    # 20 L under a limit of 10 L/h, the hospital first: 8 and 2 L/h until the reservoir is empty at 2 h.
    'hospital.got': (16, 16),
    'garden.got': (4, 4),
    'reservoir.water': (0, 0),
    # 10 L under a limit of 4 L/h shared in proportion to 2 and 6 L/h: 1 and 3 L/h until 2.5 h.
    'spring.water': (2, 0),
    'spring.small.actual_rate': (1, 0),
    'spring.large.actual_rate': (3, 0),
    # A fill of 3 L/h from 0.5 h until the level reaches 3 L, at 1.5 h.
    'filler.level': (3, 3),
    # A route at -3 L/h: east gives west 3 L/h until east is empty and west full at 10/3 h.
    'west.water': (16, 20),
    'east.water': (4, 0),
    'channel.link.actual_rate': (-3, 0),
    'channel.backward': (3, 0),
    'channel.link.forward.actual_rate': (0, 0),
    # Legs of 4 L/h and 8 kg/h with the second capped at 4 kg/h: half service until 10 kg are spent at
    # 2.5 h.
    'site.done': (4, 5),
    'site.used': (8, 10),
    'site.restore.served_fraction': (0.5, 0),
    # The table's rows a (1 L, rank 2), b (2 L, rank 1), c (3 L, rank 3) and the member d (4 L, rank 4).
    'total_need': (10, 10),
    'big_count': (3, 3),
    'any_big': (True, True),
    'all_big': (False, False),
    'least': (1, 1),
    'most': (4, 4),
    'first_ranked': (2, 2),
    'ranked_need': (8, 8),
    'pair_need': (4, 4),
    'pump_one.home_need': (3, 3),
    # The grinder refilled with 50 g at 0.5 h; its refill started at 0 h.
    'grinder.beans': (58, 58),
    'grinder.low_on_beans': (False, False),
    'grinder.last_refill': (2, 3.5),
    # A trigger at 1 h that resets after 1 h: starts at 1, 2 and 3 h.
    'clock.ticks': (2, 3),
    'inspector.passed': (1, 1),
    'inspector.failed': (1, 1),
    'inspector.inspections': (2, 2),
    # A median categorical draw takes the most likely outcome, FIXED.
    'machine.operational': (True, True),
    'left.water': (5, 5),
    'right.water': (3, 3),
    # The dispatcher's forecast, drawn into `order`, always waits.
    'depot.spares': (1, 1),
    'depot.waits': (1, 1),
    # 80 h of staff with at least 30 % for outreach, care first: 56 h and 24 h.
    'clinic.staffing.care': (56, 56),
    'clinic.staffing.outreach': (24, 24),
}


@pytest.fixture(scope='module')
def package(tmp_path_factory):
    folder = tmp_path_factory.mktemp('catalogue') / 'every'
    (folder / 'variants' / 'wet').mkdir(parents=True)
    for name, text in (
        ('model.scn', MAIN),
        ('parts.scn', PARTS),
        ('places.csv', PLACES),
        ('variants/wet/model.scn', WET),
    ):
        (folder / name).write_text(text, encoding='utf-8')
    (folder / 'units.json').write_text(json.dumps(UNITS), encoding='utf-8')
    return folder


def values(compiled, run_name=None, times=(2, 3.5)):
    """{path: (value at each time)} of a run of a compiled model."""
    record = run(compiled.program, compiled.configure(run_name))
    assert record.failure is None
    readings = read(record, compiled.program, list(AT), list(times))
    return {path: reading.values for path, reading in zip(AT, readings)}


def same(found, expected):
    if isinstance(expected, bool):
        return found is expected
    return math.isclose(found, expected, rel_tol=1e-9, abs_tol=1e-9)


@pytest.mark.parametrize('text', [MAIN, PARTS, WET], ids=['main', 'parts', 'variant'])
def test_each_file_formats_to_a_text_that_reads_back_the_same(text):
    written = format_text(text)
    assert format_text(written) == written
    assert parse(written) == parse(text)


def test_the_main_file_runs_every_construct_to_the_values_worked_by_hand(package):
    found = values(load_scenario(package / 'model.scn'))
    wrong = {path: found[path] for path, expected in AT.items() if not all(map(same, found[path], expected))}
    assert wrong == {}


def test_the_spread_has_the_standard_deviation_of_its_uniform(package):
    compiled = load_scenario(package / 'model.scn')
    record = run(compiled.program, compiled.configure())
    (reading,) = read(record, compiled.program, ['plant.spread_std'], [1])
    assert math.isclose(reading.values[0], 4 / math.sqrt(12), rel_tol=1e-12)


def test_a_run_takes_its_option_and_a_variant_its_change(package):
    """The run `quick` fills at 4 L/h: 8 L at 2 h. The variant Wet starts the reservoir at 30 L, so the
    hospital and the garden take 8 and 2 L/h until 3 h: 24 and 6 L."""
    quick = values(load_scenario(package / 'model.scn'), 'quick')
    assert quick['plant.tank'] == (8, 14)
    wet = load_scenario(package / 'variants/wet/model.scn')
    assert wet.declared.scenario.title == 'Every construct: Wet'
    found = values(wet, None, (2, 3.5))
    assert (found['reservoir.water'], found['hospital.got'], found['garden.got']) == (
        (10, 0),
        (16, 24),
        (4, 6),
    )
    assert values(wet, 'quick')['plant.tank'] == (8, 14)
