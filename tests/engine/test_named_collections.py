"""A named collection is the collection that it names (re-audit 15, `briefs/audit3.md` part E).

`tanks = Tank.instances` and then `sum(tanks.water)` was refused by the engine at the top level, and
a collection local of an event had no members at all. The rule (spec, "Collections, keys and
projections": a binding names a collection, and "a path that steps into it reads its init"): every
reduction, projection, keyed read and count over a named collection equals the same read with the
collection written in its place, and the closed form worked here from the members' data:

- at the top level (`tanks = C`, read by a formula of the root), in an entity (`this.tanks`) and in
  an event (a local of an occurrence, read by its stage and by a formula of it);
- for `C` the instances of a template, a literal (its members in their order of creation), a
  `where` on an input, a `by` on an input, and another named collection;
- for `sum`, `min`, `max` and `any`/`all` of a projection, `count` of the members and of a yes/no,
  `.at(x)` after `by`, and `where` after the name;
- an empty collection: `min` and `max` fail when read, both ways;
- a broadcast start over a named collection (at the setup, in a stage of an entity and of an
  event), a priority over a named collection of flows, and a solver's input.
"""

from __future__ import annotations

import random
import textwrap

import pytest

from napkin.engine.timeline import read, run
from napkin.model.compile import compile_text
from napkin.program.record import Unavailable

UNITS = {'h': {'time': 1}, 'L': {'volume': 1}}


def compiled(text):
    return compile_text(textwrap.dedent(text), UNITS)


def tanks(rng):
    """The members t0 ... t{n-1}: (rank, full, water in L), in their order of creation."""
    return [(rng.randint(1, 3), rng.random() < 0.5, rng.randint(1, 9)) for _ in range(rng.randint(1, 5))]


def members_text(data):
    rows = []
    for k, (rank, full, water) in enumerate(data):
        rows += [f't{k}: Tank', f'    rank = {rank}', f'    full = {"true" if full else "false"}']
        rows.append(f'    water = {water} L')
    return '\n'.join(rows)


def collection(rng, data):
    """A collection written in place, and the places of the members that it holds (in their order
    of creation), as the spec reads each form."""
    n = len(data)
    form = rng.choice(['instances', 'literal', 'where', 'where full'])
    if form == 'instances':
        return 'Tank.instances', list(range(n))
    if form == 'literal':
        chosen = rng.sample(range(n), rng.randint(1, n))
        # A literal names each member once and holds them in their order of creation.
        return '<' + ', '.join(f't{k}' for k in chosen) + '>', sorted(chosen)
    if form == 'where':
        least = rng.randint(1, 3)
        return f'Tank.instances.where(rank >= {least})', [k for k in range(n) if data[k][0] >= least]
    return 'Tank.instances.where(full)', [k for k in range(n) if data[k][1]]


def reading(rng, data, held):
    """A read of a collection C (a template with C in it), its value by hand (None when it fails),
    and whether it is a number in L, a count or a yes/no."""
    waters = [data[k][2] for k in held]
    fulls = [data[k][1] for k in held]
    op = rng.choice(['sum', 'min', 'max', 'count', 'count full', 'any', 'all', 'at', 'where'])
    if op == 'sum':
        return 'sum(C.water)', sum(waters), 'L'
    if op in ('min', 'max'):
        return f'{op}(C.water)', ({'min': min, 'max': max}[op](waters) if waters else None), 'L'
    if op == 'count':
        return 'count(C)', len(held), ''
    if op == 'count full':
        return 'count(C.full)', sum(fulls), ''
    if op in ('any', 'all'):
        return f'{op}(C.full)', {'any': any, 'all': all}[op](fulls), 'bool'
    if op == 'at':
        x = rng.choice([1, 1.5, 2, 2.5, 3, 7])
        # The member with the greatest key at or below x, of equal keys the one created later.
        found = [k for k in held if data[k][0] <= x]
        best = max(found, key=lambda k: (data[k][0], k)) if found else None
        return f'C.by(rank).at({x}).water', (data[best][2] if best is not None else None), 'L'
    least = rng.randint(1, 3)
    return f'sum(C.where(rank >= {least}).water)', sum(data[k][2] for k in held if data[k][0] >= least), 'L'


HEAD = """
scenario "Named"
    horizon 2 h

Tank:
    input rank = 1
    input full: bool = false
    water: L = 1 L
    fill = event(amount: L):
        after 0 h:
            this.water += amount

"""


def place_model(where, read_text, collection_text, named, kind):
    """A model that reads `read_text` (over C) at a place: as a formula of the root, of an entity,
    or of an occurrence and its stage; with C named (`tanks = ...`) or written in place. It
    returns the model and the path of what it reads at 1 h."""
    name = {'top': 'tanks', 'entity': 'this.tanks', 'event': 'tanks'}[where]
    read_of = read_text.replace('C', name if named else collection_text)
    unit = {'L': 'L', '': '1', 'bool': 'bool'}[kind]
    if where == 'top':
        binding = f'tanks = {collection_text}\n' if named else ''
        return HEAD + binding + f'total = formula({read_of})\n', 'total'
    if where == 'entity':
        binding = f'    tanks = {collection_text}\n' if named else ''
        return HEAD + f'boss:\n{binding}    total = formula({read_of})\n', 'boss.total'
    binding = f'        tanks = {collection_text}\n' if named else ''
    initial = {'L': '0 L', '1': '0', 'bool': 'false'}[unit]
    return (
        HEAD
        + 'boss:\n'
        + (f'    seen: {unit} = {initial}\n' if unit != '1' else f'    seen = {initial}\n')
        + '    look = event():\n'
        + binding
        + f'        total = formula({read_of})\n'
        + '        after 1 h:\n'
        + '            this.seen = total\n'
        + '        after 1 h\n'
        + '\nboss.look.start()\n'
    ), 'boss.seen'


def outcome(text, path):
    found = compiled(text)
    record = run(found.program, found.configuration)
    if record.failure is not None:
        return 'failed'
    (value,) = read(record, found.program, [path], [1.5 if path == 'boss.seen' else 1])
    # A formula that cannot be read has no value; its reason names it as it is spelled.
    return 'failed' if isinstance(value.values[0], Unavailable) else value.values[0]


@pytest.mark.parametrize('where', ['top', 'entity', 'event'])
@pytest.mark.parametrize('seed', range(12))
def test_a_read_over_a_named_collection_is_the_read_over_the_collection_in_its_place(where, seed):
    rng = random.Random(f'{where}{seed}')
    data = tanks(rng)
    collection_text, held = collection(rng, data)
    read_text, expected, kind = reading(rng, data, held)
    members = members_text(data) + '\n\n'
    named = outcome(*_with(place_model(where, read_text, collection_text, True, kind), members))
    written = outcome(*_with(place_model(where, read_text, collection_text, False, kind), members))
    assert named == written
    assert named == ('failed' if expected is None else expected)


def _with(made, members):
    text, path = made
    return text.replace('boss:\n', members + 'boss:\n', 1) if 'boss:' in text else text + '\n' + members, path


def test_a_named_collection_of_a_named_collection_reads_its_members():
    """`big = Tank.instances.where(full)`, `tanks = big.where(rank >= 2)`: at the top level, in an
    entity and in an event, the sum over `tanks` is that over the full tanks of rank 2 at least: 6 L.
    (A bare `tanks = big` is no collection value of the language.)"""
    text = HEAD + members_text([(1, True, 4), (2, False, 5), (3, True, 6)]) + """

big = Tank.instances.where(full)
tanks = big.where(rank >= 2)
total = formula(sum(tanks.water))

boss:
    big = Tank.instances.where(full)
    tanks = this.big.where(rank >= 2)
    total = formula(sum(this.tanks.water))
    seen: L = 0 L
    look = event():
        big = Tank.instances.where(full)
        tanks = big.where(rank >= 2)
        after 1 h:
            this.seen = sum(tanks.water)

boss.look.start()
"""
    found = compiled(text)
    record = run(found.program, found.configuration)
    assert record.failure is None, record.failure.detail('message')
    paths = ['total', 'boss.total', 'boss.seen']
    assert [r.values[0] for r in read(record, found.program, paths, [1.5])] == [6, 6, 6]


BROADCAST = HEAD + members_text([(1, False, 1), (2, False, 2), (3, False, 3)]) + """

tanks = <t2, t0>

boss:
    mine = <t1>
    poke = event():
        theirs = <t2>
        after 1 h:
            this.mine.fill.start(10 L)
            theirs.fill.start(100 L)

tanks.fill.start(1 L)
boss.poke.start()
"""


def test_a_start_on_a_named_collection_starts_each_member_at_the_setup_and_in_stages():
    """The setup fills t0 and t2 with 1 L; at 1 h a stage fills t1 with 10 L through the entity's
    collection and t2 with 100 L through the event's: 2 L, 12 L and 104 L at 2 h."""
    found = compiled(BROADCAST)
    record = run(found.program, found.configuration)
    assert record.failure is None, record.failure.detail('message')
    values = [r.values[0] for r in read(record, found.program, ['t0.water', 't1.water', 't2.water'], [2])]
    assert values == [2, 12, 104]


PRIORITY = """
scenario "Named"
    horizon 1 h

reservoir:
    water: L = 100 L in [0,]
        outflow.capacity = 6 L/h
        outflow.allocation = priority(RANKED)

Customer:
    input rank = 1
    flow delivery: reservoir.water -> SINK
        request = 4 L/h

first: Customer
    rank = 2
second: Customer

customers = Customer.instances
"""


@pytest.mark.parametrize('ranked', ['customers.by(rank).delivery', 'Customer.instances.by(rank).delivery'])
def test_a_priority_over_a_named_collection_of_flows_serves_by_its_keys(ranked):
    """Ranked by `rank`, `second` (rank 1) takes its 4 L/h and `first` the 2 L/h left of 6."""
    found = compiled(PRIORITY.replace('RANKED', ranked))
    record = run(found.program, found.configuration)
    assert record.failure is None, record.failure.detail('message')
    paths = ['first.delivery.actual_rate', 'second.delivery.actual_rate']
    assert [r.values[0] for r in read(record, found.program, paths, [0.5])] == [2, 4]


SOLVER = """
scenario "Named"
    horizon 1 h

Place:
    input need: L/h = 1 L/h
    stock: L = 10 L in [0,]
    flow use: this.stock -> SINK
        request = this.need

north: Place
    need = 2 L/h
south: Place
    need = 3 L/h

places = Place.instances

planner:
    share = solver:
        inputs:
            served = PLACES
        solve_for:
            served.use.actual_rate
        constraints:
            sum(served.use.actual_rate) <= 4 L/h
        objective:
            maximize(sum(served.use.actual_rate))
"""


@pytest.mark.parametrize('places', ['places', 'Place.instances'])
def test_a_solver_input_that_names_a_named_collection_is_its_members(places):
    """Under a total of 4 L/h, the solver serves 4 L/h of the 5 L/h asked, whatever the name."""
    found = compiled(SOLVER.replace('PLACES', places))
    record = run(found.program, found.configuration)
    assert record.failure is None, record.failure.detail('message')
    paths = ['north.use.actual_rate', 'south.use.actual_rate']
    assert sum(r.values[0] for r in read(record, found.program, paths, [0.5])) == pytest.approx(4)


WATCHED = """
scenario "Named"
    horizon 4 h

Tank:
    water: L = 4 L in [0,]
    flow fill: SOURCE -> this.water
        request = 1 L/h

east: Tank
west: Tank

tanks = Tank.instances

bell:
    rung: h = 0 h
    opened: h = 0 h
    ring = event():
        when SUM >= 12 L:
            this.ring.start()
            reset when false
        after 0 h:
            this.rung = t
    wait = event():
        until SUM >= 14 L
        after 0 h:
            this.opened = t

bell.wait.start()
"""


@pytest.mark.parametrize('total', ['sum(tanks.water)', 'sum(Tank.instances.water)'])
def test_a_trigger_and_a_gate_on_a_named_collection_meet_its_members(total):
    """Two tanks fill from 4 L at 1 L/h each: their sum is 8 L + 2 t, so the trigger on 12 L fires
    at 2 h and the gate on 14 L opens at 3 h."""
    found = compiled(WATCHED.replace('SUM', total))
    record = run(found.program, found.configuration)
    assert record.failure is None, record.failure.detail('message')
    values = [r.values[0] for r in read(record, found.program, ['bell.rung', 'bell.opened'], [4])]
    assert values == [pytest.approx(2), pytest.approx(3)]
