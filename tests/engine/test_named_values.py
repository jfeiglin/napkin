"""Any named value can be reported, in its declared unit, on every path that reads one (the review of
`2cd1751`, R01, R02 and R07; `scratch/rewrite/briefs/audit3b.md`, agent V).

The rule (spec, "Formulas and the values a caller can read": "Any named value can be reported. The
caller selects paths"; D10): each value that the program names reads alike on every path, whatever
else the model reads, each number in the unit that its declaration gives and with that unit:

- a solver's own unknown lives on the solver (spec, "Solver and execution contract") in the unit of
  its declaration: `clinic.staffing.care` is 70 h of 100 available (spec, "Allocating staff hours"),
  70/24 day in a model that declares it in days;
- an endpoint's `actual_rate` is the sum of the actual rates of its flows, and its `request` is zero
  where the model sets none (spec, "What each scope can see": `sum(water.outflow.flows.actual_rate)`
  equals `water.outflow.actual_rate`; "Capacity, request and bounds");
- a distribution's `.mean` and `.std` describe it, and consume no draw (spec, "Distributions and
  explicit draws"): of `uniform(a, b)` (a + b) / 2 and (b - a) / sqrt(12), of `triangular(a, m, b)`
  (a + m + b) / 3 and sqrt((a^2 + m^2 + b^2 - am - ab - mb) / 18), of `normal(m, s)` m and s;
- a flow's capacity is the ceiling that it declares. One that declares none "has no ceiling of its
  own" (spec, "Capacity, request and bounds"): it is no number, and every path says so.

A path that names no value is refused by name: a KeyError of the reader, a usage error of a command.

The paths: `read` of a record of every value and of a record of that value alone; the report, with a
lag of 0.5 h to 1 h (each value is constant, so the mean of a window is the value, whether the lag
holds or is refused, and the trail of each value is made); the run store, cold and warm; the view of a
session at a stop at 1 h; `napkin run`, `napkin play` and `napkin sample` with `--value`. The models
are random: a tank in mL, L or kL that a flow may fill and two flows drain at rates with or without a
capacity, a distribution in h, min or day, the staffing solver of the spec with its unknowns in h, min
or day, and, or not, formulas that read each of these. The tank holds far more than the flows can move
in the run, so no rate meets a bound: each expected value is the rule above, worked by hand.
"""

from __future__ import annotations

import io
import json
import math
import random
import sys
from dataclasses import dataclass, replace

import pytest

from napkin import store
from napkin.engine.report import Lag, report
from napkin.engine.timeline import read, run
from napkin.engine.timeline.plan import Plan
from napkin.engine.timeline.record import declaration, key_of
from napkin.model.compile import compile_text
from napkin.program.checkpoint import Breakpoint
from napkin.program.config import Request
from napkin.program.record import Unavailable
from napkin.session import Session
from tests.commands.call import napkin

# Each unit of the models in its canonical unit: litres and hours.
VOLUMES = {'mL': 0.001, 'L': 1, 'kL': 1000}
DURATIONS = {'h': 1, 'min': 1 / 60, 'day': 24}
UNITS = {
    'h': {'time': 1},
    'min': ({'time': 1}, 1 / 60),
    'day': ({'time': 1}, 24),
    'L': {'volume': 1},
    'mL': ({'volume': 1}, 0.001),
    'kL': ({'volume': 1}, 1000),
}
# The units of a package: the prelude has h and day.
PACKAGE_UNITS = {
    'L': {'dimensions': {'volume': 1}, 'scale': 1, 'description': 'A litre.'},
    'mL': {'dimensions': {'volume': 1}, 'scale': 0.001, 'description': 'A millilitre.'},
    'kL': {'dimensions': {'volume': 1}, 'scale': 1000, 'description': 'A kilolitre.'},
    'min': {'dimensions': {'time': 1}, 'scale': 1 / 60, 'description': 'A minute.'},
}
HORIZON = 4
TIMES = [0.5, 2.0]
LAG, LAGGED = Lag(0.5, 1.0), [2.0, 3.0]
STOP = Breakpoint('tank.tick.step[0]')
NO_CEILING = 'has no ceiling of its own'


@dataclass(frozen=True)
class Case:
    """A random model, the paths of its named values, and for each its expected unit and value (a
    number in that unit, or None for a capacity left out)."""

    text: str
    expected: dict
    stock: int = 0  # the tank's water at the start, in its unit


def _distribution(rng, unit):
    """A distribution in `unit` as the model writes it, with its mean and its standard deviation."""
    family = rng.choice(['uniform', 'triangular', 'normal'])
    if family == 'uniform':
        a, b = sorted(rng.sample(range(1, 30), 2))
        return f'uniform({a} {unit}, {b} {unit})', (a + b) / 2, (b - a) / math.sqrt(12)
    if family == 'triangular':
        a, m, b = sorted(rng.sample(range(1, 30), 3))
        spread = (a * a + m * m + b * b - a * m - a * b - m * b) / 18
        return f'triangular({a} {unit}, {m} {unit}, {b} {unit})', (a + m + b) / 3, math.sqrt(spread)
    m, s = rng.randint(10, 40), rng.randint(1, 5)
    return f'normal({m} {unit}, {s} {unit})', m, s


def case(seed):
    """The random model of a seed (see the module)."""
    rng = random.Random(seed)
    volume, kind, staff = rng.choice(list(VOLUMES)), rng.choice(list(DURATIONS)), rng.choice(list(DURATIONS))
    distribution, mean, std = _distribution(rng, kind)
    hours = rng.choice([40, 100, 160])
    fill = rng.choice([None, rng.randint(1, 9)])
    drains = []
    for _ in range(2):
        request = rng.randint(1, 9)
        drains.append((request, rng.choice([None, rng.randint(1, 9)])))
    moved = sum(request if capacity is None else min(request, capacity) for request, capacity in drains)
    stock = 100 * (moved + (fill or 0))
    reads = rng.random() < 0.5

    def flow(owner, request, capacity):
        lines = ['    flow delivery: tank.water -> SINK', f'        request = {request} {volume}/h']
        if capacity is not None:
            lines.append(f'        capacity = {capacity} {volume}/h')
        return [f'{owner}:', *lines]

    lines = [
        'scenario "Named values"',
        f'    horizon {HORIZON} h',
        '',
        'tank:',
        f'    water: {volume} = {stock} {volume} in [0 {volume},]',
        '    ticks = 0',
        f'    spread = {distribution}',
        '    tick = event():',
        '        after 1 h:',
        '            this.ticks += 1',
    ]
    if fill is not None:
        lines += ['    flow fill: SOURCE -> this.water', f'        request = {fill} {volume}/h']
    lines += [
        '',
        'clinic:',
        f'    staff_hours: h = {hours} h',
        '    outreach_minimum = formula(0.30 * this.staff_hours)',
        '    staffing = solver:',
        '        inputs:',
        '            available = this.staff_hours',
        '            minimum = this.outreach_minimum',
        '        solve_for:',
        f'            care: {staff} in [0 h, available]',
        f'            outreach: {staff} in [minimum, available]',
        '        constraints:',
        '            care + outreach == available',
        '        objective:',
        '            maximize(care)',
        *flow('', *drains[0])[1:],
        '',
        *flow('garden', *drains[1]),
        '',
    ]
    if reads:
        lines += [
            'seen = formula(tank.water.outflow.actual_rate + tank.water.outflow.request)',
            'described = formula(tank.spread.mean + tank.spread.std)',
            'staffed = formula(clinic.staffing.care + clinic.staffing.outreach)',
            'ceiling = formula(clinic.delivery.request)',
        ]
    lines.append('tank.tick.start()')
    rate = f'{volume}/h'
    expected = {
        'tank.water.outflow.actual_rate': (rate, moved),
        'tank.water.outflow.request': (rate, 0),
        'tank.spread.mean': (kind, mean),
        'tank.spread.std': (kind, std),
        'clinic.staffing.care': (staff, 0.7 * hours / DURATIONS[staff]),
        'clinic.staffing.outreach': (staff, 0.3 * hours / DURATIONS[staff]),
        'clinic.delivery.capacity': (rate, drains[0][1]),
        'garden.delivery.capacity': (rate, drains[1][1]),
    }
    if fill is not None:
        expected['tank.water.inflow.actual_rate'] = (rate, fill)
    return Case('\n'.join(lines) + '\n', expected, stock)


def agrees(path, found, wanted):
    """Whether a value read is the expected one: a number within roundoff, or for a capacity left
    out an `Unavailable` that says that the flow has no ceiling of its own."""
    if wanted is None:
        return (
            isinstance(found, Unavailable)
            and NO_CEILING in found.reason
            and path.rsplit('.', 1)[0] in found.reason
        )
    return (
        isinstance(found, int | float)
        and not isinstance(found, bool)
        and math.isclose(found, wanted, rel_tol=1e-9, abs_tol=1e-9)
    )


def check(where, path, unit, values, expected):
    """Each value of a path read one way, with its unit, against the rule."""
    wanted_unit, wanted = expected[path]
    assert unit == wanted_unit, f'{where}: {path} is in {unit!r}, not {wanted_unit!r}'
    for value in values:
        assert agrees(path, value, wanted), f'{where}: {path} reads {value!r}, not {wanted!r} {wanted_unit}'


def compiled(made):
    """The compiled model of a case."""
    return compile_text(made.text, UNITS)


SEEDS = range(16)


@pytest.mark.parametrize(
    'seed', [*SEEDS[:4], *(pytest.param(seed, marks=pytest.mark.deep) for seed in SEEDS[4:])]
)
def test_every_named_value_reads_in_its_declared_unit_on_every_path_of_the_engine(seed, tmp_path):
    """`read` of a record of every value and of one of the value alone, the report with a lag and its
    trail, the run store cold and warm, the view of a session at its stop, and the record of the run
    edited there (the tank halved: no rate and no unknown reads its level) and resumed from the file
    of the stop give each named value of a random model its declared unit and the value of its rule."""
    made = case(seed)
    c = compiled(made)
    program, configuration = c.program, c.configuration
    paths = list(made.expected)
    everything = run(program, configuration)
    assert everything.failure is None, everything.failure
    for found in read(everything, program, paths, TIMES):
        check('a record of every value', found.path, found.unit, found.values, made.expected)
    for path in paths:
        alone = replace(
            configuration, request=Request(HORIZON, everything=False, keys=(key_of(program, path),))
        )
        (found,) = read(run(program, alone), program, [path], TIMES)
        check('a record of the value alone', path, found.unit, found.values, made.expected)
    plain = report(everything, program, configuration, paths, TIMES, model=c.declared)
    lagged = report(
        everything, program, configuration, paths, LAGGED, dict.fromkeys(paths, LAG), model=c.declared
    )
    for value in (*plain.values, *lagged.values):
        check('the report', value.path, value.unit, value.values, made.expected)
        assert value.trail, f'the report gives {value.path} no trail'
    for value in plain.values:
        if value.path.startswith('clinic.staffing.'):
            assert any(used.kind == 'solver' for used in value.trail), value.trail
    with store.use(tmp_path / 'store'):
        cold = store.run(program, configuration)
        for path in paths:
            alone = replace(
                configuration, request=Request(HORIZON, everything=False, keys=(key_of(program, path),))
            )
            (found,) = read(store.run(program, alone), program, [path], TIMES)
            check('the store, warm', path, found.unit, found.values, made.expected)
        for found in read(cold, program, paths, TIMES):
            check('the store, cold', found.path, found.unit, found.values, made.expected)
    session = Session(program, configuration, (STOP,))
    session.advance()
    view = session.view(paths)
    assert view.stop.t == 1
    for shown in view.values:
        check('a view at the stop', shown.path, shown.unit, [shown.value], made.expected)
        assert not shown.editable, f'a view offers to edit {shown.path}, which no edit changes'
    session.edit('tank.water', made.stock / 2)
    session.save(tmp_path / 'stop.checkpoint')
    resumed = Session.load(tmp_path / 'stop.checkpoint', program, configuration=configuration)
    assert resumed.advance() is None
    for found in read(resumed.record, program, paths, LAGGED):
        check('a run edited at its stop and resumed', found.path, found.unit, found.values, made.expected)


DELIVERIES = """\
scenario "Deliveries"
    horizon 5 h

Tank:
    water: L = 100 L in [0 L,]
    deliver = event():
        load: L = 1 L in [0 L,]
        flow pipe: this.water -> SINK
            request = 2 L/h
        flow drop: load -> SINK
            request = 1 L/h
        after 1 h
        when t >= 1 h:
            this.deliver.start()
            reset when false
        when t >= 3 h:
            this.deliver.start()
            reset when false

north: Tank
south: Tank
    water = 50 L
"""


def test_the_endpoint_of_a_store_that_only_the_flows_of_an_event_meet_is_a_value_of_every_run(tmp_path):
    """Spec, "Flows created during a run": two deliveries of 2 L/h, each for an hour, from 1 h and
    3 h, from each tank of a template. The outflow of each tank reads 0, 2, 0, 2 and 0 L/h at 0.5, 1.5,
    2.5, 3.5 and 4.5 h, and its request 0 L/h (the spec's table of deliveries); the load of the first
    delivery, which its own flow drains at 1 L/h, has an outflow of 1 L/h while it runs and 0 L/h once
    it finished, none before its start. Nothing of the model reads them: from a record of every value,
    of the value alone, and from its warm store entry."""
    c = compile_text(DELIVERIES, UNITS)
    program, configuration = c.program, c.configuration
    times = [0.5, 1.5, 2.5, 3.5, 4.5]
    expected = {}
    for tank in ('north', 'south'):
        expected[f'{tank}.water.outflow.actual_rate'] = [0, 2, 0, 2, 0]
        expected[f'{tank}.water.outflow.request'] = [0] * 5
        expected[f'{tank}.deliver#0.load.outflow.actual_rate'] = [None, 1, 0, 0, 0]
        expected[f'{tank}.deliver#0.load.outflow.request'] = [None, 0, 0, 0, 0]
    paths = list(expected)
    with store.use(tmp_path / 'store'):
        records = {'a record of every value': store.run(program, configuration)}
        for path in paths:
            alone = replace(
                configuration, request=Request(5, everything=False, keys=(key_of(program, path),))
            )
            store.run(program, alone)
            records[f'{path} alone, warm'] = store.run(program, alone)
            records[f'{path} alone'] = run(program, alone)
        for where, record in records.items():
            for found in read(
                record, program, [path for path in paths if path in where or 'every' in where], times
            ):
                assert found.unit == 'L/h', (where, found.path, found.unit)
                for value, wanted in zip(found.values, expected[found.path]):
                    if wanted is None:
                        assert isinstance(value, Unavailable) and 'has not started' in value.reason, (
                            where,
                            found,
                        )
                    else:
                        assert value == pytest.approx(wanted, abs=1e-9), (where, found)


POUR = """\
scenario "Pour"
    horizon 3 h

Tank:
    water: L = 10 L in [0 L,]

north: Tank
south: Tank

keeper:
    poured = 0
    pour = event(source: Tank):
        spread = uniform(1 h, 3 h)
        flow pipe: source.water -> SINK
            request = 2 L/h
        after 1 h:
            this.poured += 1

keeper.pour.start(north)
"""


def test_an_endpoint_that_a_flow_meets_through_a_parameter_and_a_distribution_of_an_event(tmp_path):
    """Spec, "Any named value can be reported": a flow of an event that pours from the tank that its
    entity parameter names meets the outflow of each tank that the parameter's type allows, from the
    start of the run: north's reads 2 L/h while the pour from it runs and 0 L/h after it, south's
    0 L/h, and each request 0 L/h; the `.mean` and `.std` of the pour's own distribution, uniform(1 h,
    3 h), are 2 h and 2/sqrt(12) h from its start, and keep them once it finished. From a record of
    every value, of each value alone, from its warm store entry, at a stop before the pour's stage, and from
    the run resumed there."""
    c = compile_text(POUR, UNITS)
    program, configuration = c.program, c.configuration
    times = [0.5, 1.5, 2.5]
    expected = {
        'north.water.outflow.actual_rate': ('L/h', [2, 0, 0]),
        'north.water.outflow.request': ('L/h', [0, 0, 0]),
        'south.water.outflow.actual_rate': ('L/h', [0, 0, 0]),
        'south.water.outflow.request': ('L/h', [0, 0, 0]),
        'keeper.pour#0.spread.mean': ('h', [2, 2, 2]),
        'keeper.pour#0.spread.std': ('h', [2 / math.sqrt(12)] * 3),
    }
    paths = list(expected)

    def holds(where, found, at=times):
        unit, wanted = expected[found.path]
        assert found.unit == unit, (where, found.path, found.unit)
        values = [wanted[times.index(t)] for t in at]
        assert list(found.values) == pytest.approx(values, abs=1e-12), (where, found)

    with store.use(tmp_path / 'store'):
        for found in read(store.run(program, configuration), program, paths, times):
            holds('a record of every value', found)
        for path in paths:
            alone = replace(
                configuration, request=Request(3, everything=False, keys=(key_of(program, path),))
            )
            store.run(program, alone)
            for where, record in (('alone', run(program, alone)), ('alone, warm', store.run(program, alone))):
                holds(where, read(record, program, [path], times)[0])
    session = Session(program, configuration, (Breakpoint('keeper.pour.step[0]'),))
    session.advance()
    for shown in session.view(paths).values:
        unit, wanted = expected[shown.path]
        assert shown.unit == unit and shown.value == pytest.approx(wanted[0], abs=1e-12), shown
    assert session.advance() is None
    for found in read(session.record, program, paths, times):
        holds('resumed from its stop', found)


def ways(plan, bare=False):
    """The way of each connected set of a plan, by its flows, and how many endpoints it declares that
    its program does not set; with `bare`, of the sets that `connect` makes once those endpoints are
    taken away, as the plan was before it declared each endpoint that a flow meets."""
    unset = [
        (name, side)
        for name, side in plan.ends
        if getattr(declaration(plan.program, key_of(plan.program, name)).part, side) is None
    ]
    sets = plan.sets
    if bare:
        for pair in unset:
            del plan.ends[pair]
        sets = plan.connect(list(plan.flows), plan.moving)
    return {frozenset(connected.flows): connected.way for connected in sets}, len(unset)


FAMILIES = [
    ('instances', 300),
    ('table_instances', 1000),
    ('aggregate_feedback', 300),
    ('compartments', 300),
    ('rationing', 300),
    ('priority', 300),
    ('stiff', 100),
    ('formulas', 100),
]


@pytest.mark.parametrize(
    'family, size', [*FAMILIES, pytest.param('table_instances', 5000, marks=pytest.mark.deep)]
)
def test_an_endpoint_that_sets_nothing_changes_the_way_of_no_set(family, size, tmp_path):
    """Declaring every endpoint that a flow meets leaves the way of each connected set as it was: an
    endpoint with no request and no capacity is no setting (`Plan.settled`), so each set of a large
    family of the benchmark (`tools/bench`, each with endpoints that it does not set) has the same
    flows and the same way whether its plan declares those endpoints or not, and so does each set of
    the random models of this module."""
    from napkin.model.compile import load_scenario
    from tools.bench import families

    folder = families.write(family, size, tmp_path)
    c = load_scenario(folder if folder.name == 'model.scn' else folder / 'model.scn')
    (found, unset), (bare, _) = (ways(Plan.of(c.program, c.configuration), each) for each in (False, True))
    assert unset > 0 and found == bare, (family, unset)
    for seed in range(4):
        made = compiled(case(seed))
        assert ways(Plan.of(made.program, made.configuration)) == ways(
            Plan.of(made.program, made.configuration), bare=True
        )


def package(tmp_path, made):
    """The package of a case: its model and its units."""
    folder = tmp_path / 'named'
    folder.mkdir()
    (folder / 'model.scn').write_text(made.text, encoding='utf-8')
    (folder / 'units.json').write_text(json.dumps(PACKAGE_UNITS), encoding='utf-8')
    return folder


def cells(out, path):
    """The cells after the path of the row of a table that the command printed for a path."""
    for line in out.splitlines():
        words = line.split()
        if words and words[0] == path:
            return words[1:]
    raise AssertionError(f'no row of {path} in:\n{out}')


@pytest.mark.parametrize(
    'seed', [*SEEDS[:2], *(pytest.param(seed, marks=pytest.mark.deep) for seed in SEEDS[2:8])]
)
def test_every_named_value_reads_in_its_declared_unit_on_every_command(seed, tmp_path, capsys, monkeypatch):
    """`napkin run --value`, `napkin play --value` at a stop and at its end, and `napkin sample
    --value` give each named value of a random model its declared unit and its value, and say of a
    capacity left out that the flow has no ceiling of its own."""
    made = case(seed)
    model = package(tmp_path, made)
    paths = list(made.expected)
    found = napkin(capsys, 'run', model, '--json', '--value', ','.join(paths), '--at', '0.5h,2h')
    assert found.code == 0, found.err
    for path in paths:
        value = found.doc['values'][path]
        values = [
            Unavailable(item['unavailable']) if isinstance(item, dict) else item for item in value['values']
        ]
        check('napkin run', path, value['unit'], values, made.expected)
    monkeypatch.setattr(sys, 'stdin', io.StringIO('go\n'))
    played = napkin(capsys, 'play', model, '--break', STOP.at, '--value', ','.join(paths))
    assert played.code == 0, played.err
    stop, end = played.out.split('The run ends at', 1)
    for path in paths:
        unit, wanted = made.expected[path]
        shown = ' '.join(cells(stop, path))
        if wanted is None:
            assert shown.startswith('unavailable') and NO_CEILING in shown, (
                f'napkin play at the stop: {path} {shown}'
            )
        else:
            number, written = shown.split()[:2]
            assert written == unit and math.isclose(float(number), wanted, rel_tol=1e-5), (
                f'napkin play at the stop: {path} {shown}, not {wanted} {unit}'
            )
        row = cells(end, path)
        if wanted is None:
            assert row[-2:] == ['unavailable', 'unavailable'], f'napkin play at its end: {path} {row}'
            assert f'{path} at 0 h: unavailable:' in end and NO_CEILING in end
        else:
            assert row[0] == unit and all(
                math.isclose(float(cell), wanted, rel_tol=1e-5) for cell in row[1:]
            ), f'napkin play at its end: {path} {row}, not {wanted} {unit}'
    sampled = napkin(
        capsys, 'sample', model, '--json', '--value', ','.join(paths), '--samples', '2', '--jobs', '1'
    )
    assert sampled.code == 0, sampled.err
    for path in paths:
        value = sampled.doc['values'][path]
        unit, wanted = made.expected[path]
        assert value['unit'] == unit, f'napkin sample: {path} is in {value["unit"]!r}, not {unit!r}'
        if wanted is None:
            assert value['central'] is None and NO_CEILING in value['reason'], (
                f'napkin sample: {path} {value}'
            )
        else:
            assert math.isclose(value['central'], wanted, rel_tol=1e-9), f'napkin sample: {path} {value}'


def test_a_path_that_names_no_value_is_refused_by_name_on_every_path(tmp_path, capsys, monkeypatch):
    """A step that no value has (`tank.water.level`), an endpoint of a value that no flow meets on that
    side (`clinic.staff_hours.outflow.actual_rate`), an unknown that the solver does not have, a value
    that the model does not have: the reader raises a KeyError that names the path, and each command
    refuses it as a usage error."""
    made = case(0)
    c = compiled(made)
    record = run(c.program, c.configuration)
    model = package(tmp_path, made)
    wrong = [
        'tank.water.level',
        'clinic.staff_hours.outflow.actual_rate',
        'clinic.staffing.rest',
        'tank.missing',
        'tank.spread.median',
    ]
    for path in wrong:
        with pytest.raises(KeyError, match=path.replace('.', r'\.')):
            read(record, c.program, [path], [1])
        for command in (['run'], ['sample', '--samples', '2', '--jobs', '1']):
            found = napkin(capsys, *command, model, '--value', path)
            assert found.code == 2 and path in found.err, (command, path, found.err)
        monkeypatch.setattr(sys, 'stdin', io.StringIO('go\n'))
        found = napkin(capsys, 'play', model, '--break', STOP.at, '--value', path)
        assert found.code == 2 and path in found.err, ('play', path, found.err)
