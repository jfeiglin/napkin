"""The benchmark harness (`tools/bench/`), on synthetic models and made-up profiles.

Each family compiles and runs at its smallest size, and is what its docstring says, read from its
compiled model: copies that read only themselves, an aggregate that only an output reads, a guard
that reads every copy, a rate that reads every copy, flows that differ by the stiffness, `n` firings
at equal steps, a share that is drained to its bound with rates that read the state, the same share
in order, compartments with no numerical segment, and a chain of formulas. The attribution of a
profile puts each function in the group of its file, a factorization of C in the linear algebra,
moves the time of a helper to its callers, and keeps the whole. A workload that fails is a
record, and the harness goes on. The document has its slots and goes through JSON. The catalogue is
found by its locator and is opt-in. No test judges a duration: the times are only recorded.
"""

import cProfile
import inspect
import json
import math
import re
import statistics
from pathlib import Path
from types import SimpleNamespace

import pytest
from scipy.integrate import OdeSolution

import napkin
from napkin import expressions
from napkin.engine.continuous.kernels import MatrixExponential
from napkin.engine.runtime import simulate
from napkin.model import hybrid
from napkin.model import structure as typed
from napkin.model.ir import thaw
from tools import catalogue, compare
from tools.bench import families, measure
from tools.bench.__main__ import main
from tools.bench.workloads import ALL, Workload, workloads

ROOT = catalogue.ROOT
COPIES = 3  # the size at which a test reads "every copy"


@pytest.fixture(scope='module')
def made(tmp_path_factory):
    """`made(family, n)`: the model of a family at a size, the resolved structure of its run and the
    library, each made once for the module."""
    folder, found = tmp_path_factory.mktemp('families'), {}

    def make(family, n):
        if (family, n) not in found:
            model = napkin.load_scenario(families.write(family, n, folder))
            found[family, n] = (model, model.resolve(next(iter(model.runs))), thaw(model.library))
        return found[family, n]

    return make


@pytest.fixture(scope='module')
def ran(made):
    """`ran(family, n)`: the trajectory of the run of a family at a size, simulated once."""
    found = {}

    def run(family, n):
        if (family, n) not in found:
            _, rs, library = made(family, n)
            found[family, n] = simulate(rs, library)
        return found[family, n]

    return run


def formulas_read(rs, source):
    """The formulas that an expression reads, itself or through the formulas that it reads."""
    found, pending = set(), [typed.node(source)]
    while pending:
        for name in expressions.names_in(pending.pop()):
            if name in rs.computed and name not in found:
                found.add(name)
                pending.append(typed.node(rs.computed[name].expr))
    return found


def quantities_read(rs, source):
    """The quantities that an expression reads, itself or through the formulas that it reads."""
    sources = [
        typed.node(source),
        *(typed.node(rs.computed[name].expr) for name in formulas_read(rs, source)),
    ]
    return {name for text in sources for name in expressions.names_in(text) if name in rs.quantities}


def rate_sources(rs):
    """[(entity, expression)] of each rate of change of a structure: its rates and its flows."""
    rates = [(rs.quantities[name].entity, item.expr) for name, item in rs.rates.items()]
    return rates + [(flow.entity, flow.rate) for flow in rs.flows.values()]


def texts(value):
    """Every text in a part of a structure, its keys with them."""
    if isinstance(value, str):
        yield value
    elif isinstance(value, dict):
        for key, item in value.items():
            yield str(key)
            yield from texts(item)
    elif isinstance(value, (list, tuple)):
        for item in value:
            yield from texts(item)


def names(rs, section):
    """The names that the expressions of one section of a structure read."""
    found = set()
    for text in texts(typed.thawed(rs.section(section))):
        found.update(re.findall(r'[A-Za-z_][\w.]*', text))
    return found


def of(rs, entity):
    return {name for name, item in rs.quantities.items() if item.entity == entity}


def members(rs, member):
    """The quantity `member` of each copy of the template `Cell`."""
    return {name for name, item in rs.quantities.items() if item.path == f'Cell/{member}'}


# --- The families ---------------------------------------------------------------------------------


TABLED = [name for name, family in families.FAMILIES.items() if family.files]


def end_of_first_run(path):
    model = napkin.load_scenario(path)
    run = simulate(model.resolve(next(iter(model.runs))), thaw(model.library), None)
    return [(event['t'], event['event']) for event in run.trace], run.env_at(run.horizon)


@pytest.mark.parametrize('family', TABLED)
def test_a_family_from_a_table_runs_as_its_family_of_copies(family, tmp_path):
    """The table gives each cell the value that the copy takes from its number, so the two models are
    one model but for how that one value is written: the same events in the same order, at the same
    times and with the same values to the rounding of that value."""
    assert len(TABLED) == 4
    n = 6
    events, end = end_of_first_run(families.write(family, n, tmp_path))
    copy_events, copy_end = end_of_first_run(families.write(family.removeprefix('table_'), n, tmp_path))
    assert [name for _, name in events] == [name for _, name in copy_events]
    assert [t for t, _ in events] == pytest.approx([t for t, _ in copy_events], rel=1e-9, abs=1e-9)
    numbers = sorted(name for name, value in end.items() if isinstance(value, float))
    assert numbers and set(end) == set(copy_end)
    assert [end[name] for name in numbers] == pytest.approx(
        [copy_end[name] for name in numbers], rel=1e-9, abs=1e-12
    )


@pytest.mark.parametrize('family', TABLED)
@pytest.mark.parametrize('n', [1, 12])
def test_the_hybrid_core_of_a_family_from_a_table_stands_for_its_flat_structure(family, n, tmp_path):
    """Every row of such a table has one shape: one class, one instance lowered, and the checking mode
    of the hybrid core finds no difference from the flat structure of all the rows."""
    core = hybrid.compile(families.write(family, n, tmp_path))
    assert [len(found) for found in core.families] == [n]
    assert hybrid.problems(core) == []


def test_the_harness_measures_the_hybrid_core_of_a_table_and_no_flat_structure_of_a_large_one(tmp_path):
    large = measure.FLAT_ROWS + 1
    selected = workloads(families=['table_instances'], sizes=[3, large], folder=tmp_path)
    small, big = measure.bench(selected, repeats=1, run_task=measure.inline)
    for item, rows in ((small, 3), (big, large)):
        slot = item['compile']['shape_classes']
        assert slot['available'] is True and slot['instances'] == rows and slot['classes'] == 1
        assert slot['seconds'] > 0 and slot['peak_mb'] > 0 and slot['things_lowered'] == 1
    assert small['compile']['cold']['seconds'] > 0 and 'median_seconds' in small['values']['one_run']['warm']
    assert 'not tried' in big['compile']['cold']['failed']
    assert big['values']['one_run']['warm']['from'] == 'compile'


@pytest.mark.parametrize('family', families.FAMILIES)
def test_each_family_compiles_and_its_first_run_finishes_at_its_smallest_size(family, made, ran, tmp_path):
    _, rs, _ = made(family, 1)
    trajectory = ran(family, 1)
    assert not trajectory.paused and trajectory.end_time == rs.time.horizon
    assert not [item for item in trajectory.diagnostics if item.get('severity') == 'error']
    path = families.write(family, 1, tmp_path)
    assert path == tmp_path / f'{family}_1' / 'model.scn'
    assert (path.parent / 'units.json').is_file() == bool(families.FAMILIES[family].units)
    assert families.FAMILIES[family].stresses  # each family says what it stresses


def test_a_family_has_no_size_below_one(tmp_path):
    for size in (0, -3, True, 2.0):
        with pytest.raises(ValueError):
            families.write('events', size, tmp_path)
    with pytest.raises(KeyError):
        families.write('no_such_family', 2, tmp_path)
    assert list(tmp_path.iterdir()) == []


def test_the_copies_of_instances_read_only_themselves(made):
    model, rs, library = made('instances', COPIES)
    copies = {item.entity for item in rs.quantities.values() if item.path.startswith('Cell/')}
    assert len(napkin.instances(model, 'Cell')) == COPIES == len(copies)
    assert {entity for entity, _ in rate_sources(rs)} == copies
    for entity, source in rate_sources(rs):
        assert quantities_read(rs, source) <= of(rs, entity)
    for rule in rs.rules.values():
        assert rule.entity in copies
        assert quantities_read(rs, rule.trigger.when) <= of(rs, rule.entity)
        assert all(name.startswith(f'{rule.entity}.') for o in rule.outcomes for name in o.do.set)
    # Each copy has a time of its own: no two copies open their gates at one threshold.
    units = expressions.UnitSystem(library['units'])
    watched = [str(rule.trigger.value) for rule in rs.rules.values() if rule.trigger.value is not None]
    thresholds = {expressions.evaluate(rs.computed[name].expr, rs.values, units) for name in watched}
    assert len(watched) == COPIES == len(thresholds)
    # The outputs add a tally of every copy.
    assert members(rs, 'spilled') <= names(rs, 'outcomes')


def test_only_an_output_reads_the_aggregate_of_aggregate_output(made):
    _, rs, _ = made('aggregate_output', COPIES)
    water = members(rs, 'water')
    assert len(water) == COPIES
    whole = [name for name, item in rs.computed.items() if water <= expressions.names_in(item.expr)]
    assert len(whole) == 1
    (aggregate,) = whole
    for entity, source in rate_sources(rs):
        assert aggregate not in formulas_read(rs, source)
        assert quantities_read(rs, source) <= of(rs, entity)
    for section in (
        'rates',
        'flows',
        'allocation',
        'coupling',
        'rules',
        'state_checks',
        'input_checks',
        'labels',
    ):
        assert aggregate not in names(rs, section)
    assert not any(aggregate in expressions.names_in(item.expr) for item in rs.computed.values())
    assert aggregate in names(rs, 'outcomes')
    # The counterexample: the same reading finds the aggregate of `aggregate_feedback` in its rates.
    _, coupled, _ = made('aggregate_feedback', COPIES)
    assert any(formulas_read(coupled, source) for _, source in rate_sources(coupled))


def test_the_guard_of_aggregate_guard_reads_every_copy_and_each_event_changes_one(made, ran):
    _, rs, _ = made('aggregate_guard', COPIES)
    flags = members(rs, 'flag')
    assert len(flags) == COPIES
    own = {name: rule for name, rule in rs.rules.items() if of(rs, rule.entity) & flags}
    (guard,) = [rule for name, rule in rs.rules.items() if name not in own]
    assert len(own) == COPIES
    assert flags <= expressions.names_in(guard.trigger.when)
    for rule in own.values():
        changed = {name for outcome in rule.outcomes for name in outcome.do.set}
        assert len(changed) == 1 and changed <= of(rs, rule.entity) & flags
        assert not expressions.names_in(rule.trigger.when) & (flags - of(rs, rule.entity))
    # The run: the copies raise their flags at different times, and the guard fires with the last.
    trace = ran('aggregate_guard', COPIES).trace
    raised = [entry['t'] for entry in trace if entry['rule'] in own]
    fired = [entry['t'] for entry in trace if entry['rule'] == guard.id]
    assert len(set(raised)) == COPIES
    assert fired == [max(raised)]


def test_every_rate_of_aggregate_feedback_reads_every_copy(made):
    _, rs, _ = made('aggregate_feedback', COPIES)
    levels = members(rs, 'level')
    assert len(levels) == COPIES and len(rate_sources(rs)) == COPIES
    for _, source in rate_sources(rs):
        assert levels <= quantities_read(rs, source)
    # The copies start at different levels.
    assert len({str(rs.quantities[name].initial) for name in levels}) == COPIES


def test_the_flows_of_stiff_differ_by_the_stiffness_and_need_the_numerical_solver(made, ran):
    _, rs, library = made('stiff', 4)
    units = expressions.UnitSystem(library['units'])
    stocks = [name for name, item in rs.quantities.items() if item.kind == 'stock']
    assert len(stocks) == 4 and len(rs.flows) == 4
    # With the same content in each compartment, the fast flows are `stiffness` times the slow ones.
    environment = {**rs.values, **dict.fromkeys(rs.quantities, 0.25)}
    speeds = sorted({expressions.evaluate(flow.rate, environment, units) for flow in rs.flows.values()})
    slow, fast = speeds
    assert rs.values['chain.stiffness'] > 1
    assert fast == pytest.approx(slow * rs.values['chain.stiffness'])
    assert sum('chain.stiffness' in expressions.names_in(flow.rate) for flow in rs.flows.values()) == 2
    # No flow is linear in its content: twice the content gives less than twice the flow.
    double = {**environment, **dict.fromkeys(rs.quantities, 0.5)}
    for flow in rs.flows.values():
        once, twice = (expressions.evaluate(flow.rate, env, units) for env in (environment, double))
        assert once < twice < 2 * once
    assert any(isinstance(segment.solution, OdeSolution) for segment in ran('stiff', 1)._segments)


@pytest.mark.parametrize('n', [1, 7])
def test_the_event_of_events_fires_n_times_at_equal_steps(n, made, ran):
    _, rs, _ = made('events', n)
    (rule,) = rs.rules
    times = [entry['t'] for entry in ran('events', n).trace if entry['rule'] == rule]
    assert len(times) == n and times == sorted(set(times))
    assert 0 < times[0] <= times[-1] < rs.time.horizon
    assert [b - a for a, b in zip([0.0, *times], times)] == pytest.approx([times[0]] * n)
    # The model keeps its size: the same quantities and rules at each number of firings.
    assert set(rs.quantities) == set(made('events', 1)[1].quantities)


def tank_facts(rs, library, n):
    """(the share, the flows that drain the tank, what each asks at the start, the cap) of the tank of
    `rationing` or `priority`, with each flow in the group of the share and a rate that reads the tally
    of its own user."""
    units = expressions.UnitSystem(library['units'])
    (share,) = rs.allocation.values()
    drains = [name for name, flow in rs.flows.items() if flow.source == 'tank.water']
    assert len(drains) == n and all(rs.flows[name].allocation in rs.allocation for name in drains)
    for name in drains:
        assert quantities_read(rs, rs.flows[name].rate) == {rs.flows[name].target}
    start = {**rs.values, **{name: 0.0 for name in rs.quantities}}
    asked = [expressions.evaluate(rs.flows[name].rate, start, units) for name in drains]
    return share, drains, asked, expressions.evaluate(share.capacity, rs.values, units)


def test_rationing_has_a_share_that_is_drained_to_its_bound_with_rates_that_read_the_state(made, ran):
    n = 4
    _, rs, library = made('rationing', n)
    share, drains, asked, limit = tank_facts(rs, library, n)
    assert share.policy == 'proportional' and share.order is None
    inflow, horizon, habit = rs.values['tank.inflow'], rs.time.horizon, rs.values['tank.habit']
    assert inflow < limit < sum(asked)  # the cap cuts the flows from the start, and the tank drains
    trajectory = ran('rationing', n)
    # The rates read the state, so no segment has a closed form: the allocation runs at each evaluation.
    solutions = [segment.solution for segment in trajectory._segments]
    assert solutions and all(isinstance(solution, OdeSolution) for solution in solutions)
    assert trajectory.evaluations > 10 * len(solutions)
    start, end = trajectory.env_at(0.0), trajectory.env_at(trajectory.end_time)
    used = [end[rs.flows[name].target] for name in drains]
    # The water is counted once: what was there and what came in is in the tank or with a user.
    assert start['tank.water'] + inflow * horizon == pytest.approx(end['tank.water'] + sum(used))
    assert start['tank.water'] > 0 and end['tank.water'] == pytest.approx(0, abs=1e-6 * start['tank.water'])
    # Each user is cut: uncut, a user that asks a at the start, and a (habit + 2 u) / (habit + u) when
    # it has taken u, has u / 2 + habit / 4 × ln(1 + 2 u / habit) = a × the time.
    for took, a in zip(used, asked):
        assert took / 2 + habit / 4 * math.log1p(2 * took / habit) < 0.99 * a * horizon
    # In proportion: a user that asks more at the start has taken more.
    assert used == sorted(used) and len(set(used)) == n


def test_priority_is_the_tank_of_rationing_with_a_share_in_order(made, ran):
    n = 4
    _, rs, library = made('priority', n)
    share, drains, asked, limit = tank_facts(rs, library, n)
    assert share.policy == 'priority' and list(share.order) == drains
    inflow, horizon, habit = rs.values['tank.inflow'], rs.time.horizon, rs.values['tank.habit']
    assert inflow < limit < sum(asked)
    _, plain, plain_library = made('rationing', n)
    assert tank_facts(plain, plain_library, n)[1:] == (drains, asked, limit)
    assert typed.thawed(rs.quantities) == typed.thawed(plain.quantities)
    trajectory = ran('priority', n)
    solutions = [segment.solution for segment in trajectory._segments]
    assert solutions and all(isinstance(solution, OdeSolution) for solution in solutions)
    start, end = trajectory.env_at(0.0), trajectory.env_at(trajectory.end_time)
    used = [end[rs.flows[name].target] for name in drains]
    assert start['tank.water'] + inflow * horizon == pytest.approx(end['tank.water'] + sum(used))
    assert end['tank.water'] == pytest.approx(0, abs=1e-6 * start['tank.water'])
    # In order: the first user is never cut, at the cap or at the empty tank, because the inflow is more
    # than twice what it asks at the start. Uncut, a user that asks a at the start has
    # u / 2 + habit / 4 × ln(1 + 2 u / habit) = a × the time. The last user is cut.
    assert 2 * asked[0] < inflow
    assert used[0] / 2 + habit / 4 * math.log1p(2 * used[0] / habit) == pytest.approx(
        asked[0] * horizon, rel=1e-6
    )
    assert used[-1] / 2 + habit / 4 * math.log1p(2 * used[-1] / habit) < 0.9 * asked[-1] * horizon


def test_the_run_of_compartments_has_no_numerical_segment(made, ran):
    n = 5
    _, rs, _ = made('compartments', n)
    stocks = [name for name, item in rs.quantities.items() if item.kind == 'stock']
    assert len(stocks) == n
    for flow in rs.flows.values():
        # Each rate reads the content of its own compartment only.
        assert quantities_read(rs, flow.rate) == {flow.source}
    trajectory = ran('compartments', n)
    solutions = [segment.solution for segment in trajectory._segments]
    assert solutions and not any(isinstance(solution, OdeSolution) for solution in solutions)
    assert any(isinstance(solution, MatrixExponential) for solution in solutions)
    # Nothing leaves the chain but into its tally.
    start, end = trajectory.env_at(0.0), trajectory.env_at(trajectory.end_time)
    assert sum(end[name] for name in rs.quantities) == pytest.approx(
        sum(start[name] for name in rs.quantities)
    )
    assert end['chain.out'] > 0


def test_the_rates_of_formulas_read_a_chain_of_n_formulas(made):
    n = 6
    _, rs, _ = made('formulas', n)
    assert len(rs.computed) == n
    read = {name: formulas_read(rs, item.expr) for name, item in rs.computed.items()}
    # A chain: the formulas that each one reads, itself with them, are 1, 2, … n formulas.
    assert sorted(len(found) + 1 for found in read.values()) == list(range(1, n + 1))
    lengths = sorted(len(formulas_read(rs, source)) for _, source in rate_sources(rs))
    assert lengths[0] == 1 and lengths[-1] == n and len(lengths) == 3


# --- Where the time goes ----------------------------------------------------------------------------


def entry(seconds, callers=None):
    """One function of made-up statistics, in the shape of `pstats.Stats(…).stats`: its own seconds,
    and its callers as {caller: its own seconds under that caller}."""
    callers = {caller: (1, 1, under, under) for caller, under in (callers or {}).items()}
    return (1, 1, seconds, seconds, callers)


PLACES = {
    'analysis': ['/x/napkin/model/lower/builder.py', '/x/napkin/model/language/front.py'],
    'expressions': ['<model>', '<string>'],
    'field': [
        '/x/napkin/engine/allocation.py',
        *(
            f'/x/napkin/engine/continuous/{name}.py'
            for name in ('fields', 'kernels', 'bounds', 'system', 'highs')
        ),
    ],
    'solver': [
        '/x/napkin/engine/continuous/integrate.py',
        '/lib/site-packages/scipy/integrate/_ivp/radau.py',
    ],
    'linear_algebra': [
        '/lib/site-packages/scipy/sparse/linalg/_dsolve/linsolve.py',
        '/lib/site-packages/scipy/linalg/_decomp_lu.py',
        '/lib/site-packages/numpy/linalg/_linalg.py',
    ],
    'scheduler': [
        '/x/napkin/engine/timeline/run.py',
        '/x/napkin/engine/timeline/component.py',
        '/x/napkin/engine/runtime.py',
        '/x/napkin/engine/continuous/segment.py',
    ],
    'reporting': ['/x/napkin/engine/report.py'],
    'other': [
        '/x/napkin/engine/session_notes.py',
        '/usr/lib/python3/copy.py',
        '/elsewhere/continuous/fields.py',
        '/x/napkin/model_notes.py',
        '/x/tools/scheduler.py',
    ],
}


def test_each_function_of_a_made_up_profile_lands_in_the_group_of_its_file():
    stats, expected = {}, dict.fromkeys(measure.GROUPS, 0.0)
    for group, files in PLACES.items():
        for file in files:
            seconds = float(len(stats) + 1)  # each function has its own time, so a swap shows
            stats[file, 10, 'work'] = entry(seconds)
            expected[group] += seconds
            assert measure.group_of((file, 10, 'work')) == group
    assert set(PLACES) == set(measure.GROUPS)
    found = measure.attribution(stats)
    assert set(found['groups']) == set(measure.GROUPS)
    for group in measure.GROUPS:
        assert found['groups'][group]['own_seconds'] == pytest.approx(expected[group])
        assert found['groups'][group]['seconds'] == pytest.approx(expected[group])
    assert found['seconds'] == pytest.approx(sum(expected.values()))
    assert sum(item['share'] for item in found['groups'].values()) == pytest.approx(1)
    assert measure.attribution({})['seconds'] == 0


def test_the_expression_file_is_split_between_analysis_and_evaluation():
    file = '/x/napkin/expressions.py'
    for name in measure.ANALYSIS:
        assert measure.group_of((file, 1, name)) == 'analysis'
    assert measure.group_of((file, 1, '_evaluate')) == 'expressions'
    # The typed nodes, the contracts of the operations, the units, the intervals and the proof on the
    # faces are analysis; the code of a value is not.
    for name in ('expr', 'ops', 'units', 'intervals', 'faces'):
        assert measure.group_of((f'/x/napkin/core/{name}.py', 1, 'read')) == 'analysis'
    assert measure.group_of(('/x/napkin/core/evaluation.py', 1, 'function')) == 'expressions'
    # A function inside an analysis function has another name: its place in the file says it. The file
    # here is a small one with two analysis functions and an evaluation function.
    inside = (
        'def names_in(source):\n'
        '    def walk(node):\n'
        '        return node\n'
        '\n'
        'def domain_prover():\n'
        '    def prove(node):\n'
        '        return node\n'
        '\n'
        'def evaluate():\n'
        '    def value():\n'
        '        return 0\n'
    )
    spans = measure.analysis_spans(inside)
    assert spans == ((1, 3), (5, 7))
    for line, name in ((3, 'walk'), (7, 'prove')):
        assert measure.group_of((file, line, name), spans) == 'analysis'
        assert measure.group_of((file, line, name)) == 'expressions'
    assert measure.group_of((file, 11, 'value'), spans) == 'expressions'
    # Each analysis function and class at the top of the real file has a span.
    source = Path(expressions.__file__).read_text(encoding='utf-8')
    spans = measure.analysis_spans(source)
    assert len(spans) == len(set(measure.ANALYSIS) & set(dir(expressions)))
    evaluation = inspect.getsourcelines(expressions.evaluate)[1]
    assert measure.group_of((file, evaluation + 1, 'some_inner_name'), spans) == 'expressions'


def test_a_helper_gives_its_time_to_the_functions_that_call_it():
    field = ('/x/napkin/engine/continuous/fields.py', 5, 'rates')
    scheduler = ('/x/napkin/engine/timeline/run.py', 7, 'settle')
    resolve = ('/x/napkin/model/model.py', 9, 'resolve')
    built_in = ('~', 0, '<built-in method builtins.sum>')
    wrapper = ('/lib/site-packages/numpy/_core/fromnumeric.py', 3, 'any')
    copy, copy_dict = (
        ('/usr/lib/python3/copy.py', 1, 'deepcopy'),
        ('/usr/lib/python3/copy.py', 2, '_deepcopy_dict'),
    )
    alone = ('/usr/lib/python3/json.py', 4, 'loads')
    stats = {
        field: entry(2.0),
        scheduler: entry(1.0),
        resolve: entry(0.5),
        # A function of C under two groups: three parts of four under the field.
        built_in: entry(4.0, {field: 3.0, scheduler: 1.0}),
        # A library function that the function of C calls: its time goes on to the same callers.
        wrapper: entry(8.0, {built_in: 8.0}),
        # A recursive copy: almost every call of each comes from the other, and one from `resolve`.
        copy: entry(16.0, {resolve: 0.001, copy_dict: 15.999, copy: 5.0}),
        copy_dict: entry(32.0, {copy: 32.0}),
        alone: entry(64.0),
    }
    found = measure.attribution(stats)['groups']
    assert found['field']['seconds'] == pytest.approx(2 + 0.75 * (4 + 8))
    assert found['scheduler']['seconds'] == pytest.approx(1 + 0.25 * (4 + 8))
    assert found['analysis']['seconds'] == pytest.approx(0.5 + 16 + 32)
    assert found['other']['seconds'] == pytest.approx(64)
    assert sum(item['seconds'] for item in found.values()) == pytest.approx(
        sum(item[2] for item in stats.values())
    )
    # The time by the file alone stays apart: the helpers are functions of no group.
    assert found['field']['own_seconds'] == 2 and found['analysis']['own_seconds'] == 0.5
    assert found['other']['own_seconds'] == 4 + 8 + 16 + 32 + 64
    # A helper that the statistics give calls but no time under its callers goes by the calls.
    counted = {
        field: entry(1.0),
        built_in: (4, 4, 2.0, 2.0, {field: (3, 3, 0.0, 0.0), scheduler: (1, 1, 0.0, 0.0)}),
    }
    assert measure.attribution(counted)['groups']['field']['seconds'] == pytest.approx(1 + 0.75 * 2)


def test_a_factorization_of_c_is_linear_algebra_whatever_calls_it():
    """The solver calls the factorization and the solves of SuperLU from its own file. Their time is
    linear algebra, and another function of C that the solver calls stays a helper of the solver."""
    radau = ('/lib/site-packages/scipy/integrate/_ivp/radau.py', 3, 'solve_collocation_system')
    factor = ('~', 0, '<built-in method scipy.sparse.linalg._dsolve._superlu.gstrf>')
    solve = ('~', 0, "<method 'solve' of 'SuperLU' objects>")
    dot = ('~', 0, "<method 'dot' of 'numpy.ndarray' objects>")
    for function in (factor, solve):
        assert measure.group_of(function) == 'linear_algebra'
    assert measure.group_of(dot) == 'other'
    stats = {
        radau: entry(1.0),
        factor: entry(2.0, {radau: 2.0}),
        solve: entry(4.0, {radau: 4.0}),
        dot: entry(8.0, {radau: 8.0}),
    }
    found = measure.attribution(stats)['groups']
    assert found['linear_algebra']['seconds'] == pytest.approx(2 + 4)
    assert found['solver']['seconds'] == pytest.approx(1 + 8)
    assert found['linear_algebra']['own_seconds'] == pytest.approx(2 + 4)


def test_the_statistics_of_a_profile_add_up_functions_that_share_a_key():
    """The engine's generated programs share one file name, line and name. `pstats` keeps one of them."""
    programs = []
    for factor in (2, 3):
        namespace = {}
        exec(compile(f'def program(x):\n    return len(x) * {factor}', '<model>', 'exec'), namespace)
        programs.append(namespace['program'])

    def work():
        return [programs[0]('ab') for _ in range(3)] + [programs[1]('ab') for _ in range(5)]

    profile = cProfile.Profile()
    profile.enable()
    work()
    profile.disable()
    key = ('<model>', 1, 'program')
    stats = measure.profile_stats(profile)
    assert stats[key][1] == 8 and stats[key][0] == 8
    (length,) = [function for function in stats if function[0] == '~' and 'len' in function[2]]
    assert stats[length][1] == 8 and stats[length][4][key][0] == 8
    (caller,) = stats[key][4]
    assert caller[2] == 'work' and stats[key][4][caller][0] == 8
    assert measure.group_of(key) == 'expressions'
    assert measure.attribution(stats)['seconds'] == pytest.approx(sum(item[2] for item in stats.values()))


def test_a_function_that_the_profiler_gives_no_entry_of_its_own_keeps_its_time():
    """The profiler can list a function only under its caller. Its time still counts, to its group."""
    from types import SimpleNamespace as Entry

    def code(file, line, name):
        return SimpleNamespace(co_filename=file, co_firstlineno=line, co_name=name)

    field = code('/x/napkin/engine/continuous/fields.py', 10, 'rates')
    lost = code('/x/napkin/engine/continuous/fields.py', 352, 'solve_it')
    helper = code('/x/site-packages/library.py', 5, 'helper')
    call = Entry(code=lost, callcount=3, reccallcount=0, inlinetime=2.0, totaltime=2.5, calls=None)
    entries = [
        Entry(code=field, callcount=1, reccallcount=0, inlinetime=1.0, totaltime=3.5, calls=[call]),
        # `solve_it` has no entry of its own; the helper that it calls has one, with no caller listed.
        Entry(code=helper, callcount=3, reccallcount=0, inlinetime=0.5, totaltime=0.5, calls=None),
    ]
    stats = measure.profile_stats(SimpleNamespace(getstats=lambda: entries))
    key = ('/x/napkin/engine/continuous/fields.py', 352, 'solve_it')
    assert stats[key][:4] == (3, 3, 2.0, 2.5)
    assert stats[key][4] == {('/x/napkin/engine/continuous/fields.py', 10, 'rates'): (3, 3, 2.0, 2.5)}
    found = measure.attribution(stats)
    assert found['seconds'] == pytest.approx(3.5)
    assert found['groups']['field']['own_seconds'] == pytest.approx(3.0)


# --- The harness ------------------------------------------------------------------------------------

BROKEN = families.events(1).replace('t >= next', 't >= nothing_declared')
# A model that compiles and whose run stops: the chances of an event's outcomes do not add up to 1.
STOPS = """scenario "A run that stops"
    summary "The chances of an event do not add up."
    horizon 10 h
    scope "Nothing: the model is synthetic."

tank:  @shape
    "The tank."
    var valve: "shut" | "open" | "stuck" = "shut"
    event turn once when t >= 1 h:  @shape
        opens 0.5:
            valve = "open"
        sticks 0.4:
            valve = "stuck"

record shape: assumption "A synthetic model of the benchmark, with no source."
"""


@pytest.fixture(scope='module')
def records(tmp_path_factory):
    """The records of three workloads, measured in this process: a model that does not compile, a model
    whose run stops, and a model that runs."""
    folder = tmp_path_factory.mktemp('harness')
    selected = []
    for name, text in (('broken', BROKEN), ('stops', STOPS)):
        path = folder / name / 'model.scn'
        path.parent.mkdir()
        path.write_text(text, encoding='utf-8')
        selected.append(Workload('family', name, path))
    selected += workloads(ROOT, families=['events'], sizes=[2], folder=folder)
    said = []
    found = measure.bench(selected, repeats=2, samples=4, run_task=measure.inline, say=said.append)
    assert len(said) == len(found)
    return found


def measurements(record):
    one = record['values']['one_run']
    return [
        record['compile']['cold'],
        one['cold'],
        one['warm'],
        one['report'],
        one['where'],
        record['values']['every_run'],
        record['values']['batch'],
    ]


def test_a_workload_that_fails_is_a_record_and_the_harness_goes_on(records):
    assert [record['name'] for record in records] == ['broken', 'stops', 'events_2']
    broken, stops, good = records
    # The compile fails: no later measurement is tried, and each says where its failure comes from.
    assert broken['compile']['cold']['failed'].startswith('ModelError: ')
    assert (
        'nothing_declared' in broken['compile']['cold']['failed'] and 'from' not in broken['compile']['cold']
    )
    for later in measurements(broken)[1:]:
        assert later == {'failed': broken['compile']['cold']['failed'], 'from': 'compile'}
    # The run stops: the compile is measured, and the failure is the first result's.
    assert 'failed' not in stops['compile']['cold']
    failed = stops['values']['one_run']['cold']
    assert re.match(r'[A-Z]\w*(Error|Exception): ', failed['failed']) and 'from' not in failed
    for later in measurements(stops)[2:]:
        assert later == {'failed': failed['failed'], 'from': 'first result'}
    assert not any('failed' in found for found in measurements(good))
    assert good['run'] == 'base' and good['family'] == 'events' and good['size'] == 2


def test_a_long_failure_keeps_its_ends():
    failed = measure.failure(ValueError('start ' + 'x' * 5000 + '\n the end'))['failed']
    assert failed.startswith('ValueError: start ') and failed.endswith('the end') and len(failed) < 400
    assert measure.failure(KeyError('name')) == {'failed': "KeyError: 'name'"}
    assert measure.perform({'kind': 'compile', 'path': '/no/such/model.scn'})['failed']


def test_the_document_has_its_slots_and_goes_through_json(records):
    settings = {'repeats': 2, 'samples': 4, 'timeout': 600, 'runs': 'first'}
    document = measure.document(records, settings)
    assert json.loads(json.dumps(document)) == document
    assert {'commit', 'dirty', 'machine', 'processors', 'settings', 'groups', 'workloads'} <= set(document)
    # The files of each role in this revision are in the document, for a comparison by role.
    assert set(document['groups']) == set(measure.GROUPS) - {'other'}
    for group, places in measure.FILES:
        assert set(places) <= set(document['groups'][group])
    assert document['settings'] == settings and document['machine'] == compare.here()
    assert document['commit'] is None or re.fullmatch(r'[0-9a-f]{40}', document['commit'])
    assert isinstance(document['processors'], int) and len(document['workloads']) == len(records)
    for item in document['workloads']:
        assert {'kind', 'name', 'path', 'run', 'compile', 'values', 'derivative'} <= set(item)
        assert item['derivative'] == {'available': False}
        assert item['compile']['shape_classes'] == {'available': False}
        assert set(item['compile']) == {'cold', 'shape_classes'} and set(item['values']) == {
            'one_run',
            'every_run',
            'batch',
        }
        assert set(item['values']['one_run']) == {'cold', 'warm', 'report', 'where'}
    good = document['workloads'][-1]
    one = good['values']['one_run']
    assert {'seconds', 'peak_mb'} <= set(good['compile']['cold']) and 'runs' not in good['compile']['cold']
    assert {'seconds', 'peak_mb', 'parts'} <= set(one['cold'])
    assert sum(one['cold']['parts'].values()) == pytest.approx(one['cold']['seconds'])
    warm = one['warm']
    assert warm['repeats'] == 2 == len(warm['seconds'])
    assert warm['median_seconds'] == statistics.median(warm['seconds']) and warm['min_seconds'] == min(
        warm['seconds']
    )
    size = {'quantities', 'rules', 'flows', 'formulas', 'evaluations', 'trace', 'segments'}
    assert size <= set(warm['size']) and warm['size']['trace'] == 2 and warm['size']['rules'] == 1
    assert sum(warm['size']['segment_kinds'].values()) == warm['size']['segments']
    assert set(one['where']['groups']) == set(measure.GROUPS)
    assert sum(group['share'] for group in one['where']['groups'].values()) == pytest.approx(1)
    # The study of the run and its report are measured, and the profile is of both: the report has a
    # part of the time, and so has the analysis of the study's checks.
    assert one['report']['study_seconds'] > 0 and one['report']['report_seconds'] > 0
    assert one['where']['groups']['reporting']['own_seconds'] > 0
    assert one['where']['groups']['analysis']['own_seconds'] > 0
    assert good['values']['batch'] == {'skipped': 'no uncertain input'}
    assert good['path'] == 'events_2/model.scn'
    # The table: one row for each record, and a failure in the row of its workload.
    lines = measure.table(document).splitlines()
    assert len(lines) == len(records) + 3  # the heads, the rows, the count, the legend
    for item, line in zip(document['workloads'], lines[1:]):
        assert line.startswith(item['name']) and ('FAILED' in line) == (item is not good)
    assert 'FAILED at the compile' in lines[1] and 'FAILED at the first result' in lines[2]


def test_a_study_measures_a_run_with_an_uncertain_input_and_skips_one_without(tmp_path):
    text = families.compartments(2).replace('= 0.05 ratio/h in', '= uniform(0.02 ratio/h, 0.08 ratio/h) in')
    assert text != families.compartments(2)
    path = tmp_path / 'model.scn'
    path.write_text(text, encoding='utf-8')
    model = napkin.load_scenario(path)
    found = measure.study(model, 'base', 5)
    assert found['samples'] == 5 and found['jobs'] == 1 and found['run'] == 'base'
    assert 'first_seconds' not in found and 'processes' not in found
    # The three parts of the study make its whole, and the samples in a second leave the central run out.
    parts = [found[key] for key in ('central_seconds', 'check_seconds', 'run_seconds')]
    assert all(part > 0 for part in parts) and sum(parts) == pytest.approx(found['seconds'])
    assert found['samples_per_second'] == pytest.approx(5 / (found['check_seconds'] + found['run_seconds']))
    plain = napkin.load_scenario(families.write('compartments', 2, tmp_path))
    assert measure.study(plain, 'base', 5) == {'skipped': 'no uncertain input'}


def test_a_study_on_two_processes_is_measured_after_its_pool_has_started(tmp_path):
    from napkin import spread as spreads

    text = families.compartments(2).replace('= 0.05 ratio/h in', '= uniform(0.02 ratio/h, 0.08 ratio/h) in')
    path = tmp_path / 'model.scn'
    path.write_text(text, encoding='utf-8')
    model = napkin.load_scenario(path)
    found = measure.study(model, 'base', 6, jobs=2)
    assert found['samples'] == 6 and found['jobs'] == 2 and found['first_seconds'] > 0
    # The first study started every process of the pool, so the measured one started none: the pool
    # has the same processes after one more study as it had between the two.
    assert found['processes'] == 2
    pool = spreads._pool(2)
    between = set(pool._processes)
    assert len(between) == 2
    again = measure.study(model, 'base', 6, jobs=2)
    assert set(pool._processes) == between and again['processes'] == 2
    parts = [found[key] for key in ('central_seconds', 'check_seconds', 'run_seconds')]
    assert sum(parts) == pytest.approx(found['seconds'])
    plain = napkin.load_scenario(families.write('compartments', 2, tmp_path))
    assert measure.study(plain, 'base', 6, jobs=2) == {'skipped': 'no uncertain input'}


# Two runs of one model: the second has a faster inflow, so its event comes sooner.
TWO_RUNS = """scenario "Two runs"
    summary "A tank fills at one of two rates."
    horizon 10 h
    scope "Nothing: the model is synthetic."

tank:  @shape
    "The tank."
    input rate: fraction/h = 0.05 fraction/h in 0 fraction/h to 1 fraction/h  @shape
    input full: fraction = uniform(0.3, 0.5) in 0.1 to 1  @shape
    var water: fraction = 0 size 1  @shape
        "Water in the tank"
    output water
    var valve: "open" | "closed" = "open"
    flow fill: -> water at rate while valve is "open"
    event close once when water >= full:  @shape
        "The valve closes."
        valve = "closed"

options "Inflow":
    "Slow":
        "The inflow as it is."
    "Fast":
        "A faster inflow."
        tank.rate = 0.5 fraction/h  @shape

runs:
    slow = "Slow"
    quick = "Fast" versus slow
        "The tank fills sooner."

record shape: assumption "A synthetic model of the benchmark, with no source."
"""


def test_the_survey_times_each_run_of_a_model_in_its_order(tmp_path):
    path = tmp_path / 'two' / 'model.scn'
    path.parent.mkdir()
    path.write_text(TWO_RUNS, encoding='utf-8')
    model = napkin.load_scenario(path)
    assert list(model.runs) == ['slow', 'quick']
    (record,) = measure.bench(
        [Workload('family', 'two', path)], repeats=1, survey=True, run_task=measure.inline
    )
    assert record['run'] == 'slow'  # the measurements in full are of the first run
    found = record['values']['every_run']
    assert list(found['runs']) == ['slow', 'quick'] and found['slowest'] in found['runs']
    for name, item in found['runs'].items():
        trajectory = simulate(model.resolve(name), thaw(model.library))
        assert item['seconds'] > 0 and item['trace'] == len(trajectory.trace) == 1
        assert item['evaluations'] == trajectory.evaluations
    slowest = found['runs'][found['slowest']]['seconds']
    assert slowest == max(item['seconds'] for item in found['runs'].values())
    line = measure.table(measure.document([record], {'samples': None})).splitlines()[1]
    assert f'slowest of 2 runs: {found["slowest"]}' in line
    # With a survey, a study samples the slowest run that the survey found, and names it. Without
    # one, it samples the run of the record.
    (studied,) = measure.bench(
        [Workload('family', 'two', path)], repeats=1, survey=True, samples=3, run_task=measure.inline
    )
    assert studied['values']['batch']['run'] == studied['values']['every_run']['slowest']
    assert studied['values']['batch']['samples'] == 3
    (first,) = measure.bench([Workload('family', 'two', path)], repeats=1, samples=3, run_task=measure.inline)
    assert first['values']['batch']['run'] == first['run'] == 'slow'
    # Without the survey, the record says so.
    (plain,) = measure.bench([Workload('family', 'two', path)], repeats=1, run_task=measure.inline)
    assert plain['values']['every_run'] == {'skipped': 'no survey asked'}


def test_a_measurement_runs_in_a_process_of_its_own_within_its_time(tmp_path):
    good = families.write('events', 1, tmp_path)
    broken = tmp_path / 'broken.scn'
    broken.write_text(BROKEN, encoding='utf-8')
    failed = measure.isolated({'kind': 'compile', 'path': str(broken)}, 120)
    assert failed['failed'].startswith('ModelError: ') and 'nothing_declared' in failed['failed']
    late = measure.isolated({'kind': 'compile', 'path': str(good)}, 0.01)
    assert late == {'failed': 'TimeoutError: no result after 0.01 s'}


def test_a_process_that_is_stopped_keeps_what_it_saved(tmp_path):
    problem = TimeoutError('no result after 5 s')
    late = {'failed': 'TimeoutError: no result after 5 s'}
    whole, part = tmp_path / 'whole.json', tmp_path / 'part.json'
    whole.write_text('{"seconds": 1.5}', encoding='utf-8')
    part.write_text('{"warm": {"repeats": 2}, "partial": true}', encoding='utf-8')
    assert measure.outcome(tmp_path / 'none.json', problem) == late
    assert measure.outcome(whole, problem) == {'seconds': 1.5}
    assert measure.outcome(part, problem) == {'warm': {'repeats': 2}, **late}
    # The warm process saves after each measurement; its last write is its whole result.
    path = families.write('events', 1, tmp_path)
    task = {'kind': 'warm', 'path': str(path), 'run': None, 'repeats': 1, 'samples': None}
    saved = []
    found = measure.perform(task, saved.append)
    assert [set(item) for item in saved] == [
        {'run', 'warm'},
        {'run', 'warm', 'report'},
        {'run', 'warm', 'report', 'where'},
        {'run', 'warm', 'report', 'where', 'every_run'},
    ]
    assert set(found) == {'run', 'warm', 'report', 'where', 'every_run', 'batch'}
    assert saved[0]['warm'] == found['warm'] and found['every_run'] == {'skipped': 'no survey asked'}
    out = tmp_path / 'result.json'
    assert measure.child(json.dumps(task), out) == 0
    assert set(json.loads(out.read_text(encoding='utf-8'))) == set(found)
    assert list(tmp_path.glob('*.part')) == []

    # In the record, the first measurement that the process did not finish takes the failure.
    def stopped(task, timeout):
        found = measure.inline(task)
        return {'run': found['run'], 'warm': found['warm'], **late} if task['kind'] == 'warm' else found

    (record,) = measure.bench([Workload('family', 'events_1', path)], repeats=1, run_task=stopped)
    assert 'failed' not in record['values']['one_run']['warm']
    assert record['values']['one_run']['report'] == late
    assert record['values']['one_run']['where'] == {**late, 'from': 'report'}
    assert record['values']['every_run'] == {**late, 'from': 'report'}
    assert record['values']['batch'] == {**late, 'from': 'report'}


def test_the_command_measures_a_family_and_writes_the_document(tmp_path, capsys):
    out = tmp_path / 'results' / 'bench.json'
    assert main(['--family', 'events', '--sizes', '1', '--repeats', '1', '--out', str(out)]) == 0
    document = json.loads(out.read_text(encoding='utf-8'))
    (item,) = document['workloads']
    assert item['name'] == 'events_1' and item['kind'] == 'family' and item['run'] == 'base'
    assert not any('failed' in found for found in measurements(item))
    assert item['values']['batch'] == {'skipped': 'no samples asked'}
    assert item['derivative'] == {'available': False}
    assert all(isinstance(found.get('peak_mb'), float) for found in measurements(item)[:3])
    assert document['settings']['families'] == ['events'] and document['settings']['sizes'] == [1]
    assert document['settings']['scenarios'] == [] and document['settings']['repeats'] == 1
    assert document['settings']['jobs'] == 1
    printed = capsys.readouterr().out
    assert 'events_1' in printed and 'FAILED' not in printed


@pytest.mark.parametrize(
    'arguments',
    [
        [],
        ['--scenario', 'SC97'],
        ['--family', 'no_such_family'],
        ['--family', 'events', '--sizes', '0'],
        ['--runs', 'some'],
    ],
)
def test_the_command_stops_when_it_has_nothing_to_measure(arguments, capsys):
    with pytest.raises(SystemExit) as stopped:
        main(arguments)
    assert stopped.value.code == 2
    assert 'error' in capsys.readouterr().err


# --- The workloads ----------------------------------------------------------------------------------


def test_the_catalogue_is_opt_in_and_the_list_writes_nothing(tmp_path):
    found = workloads(
        ROOT, examples=True, families=['events', 'stiff', 'events'], sizes=[1, 4], folder=tmp_path
    )
    assert [item for item in found if item.kind == 'catalogue'] == []
    examples = sorted((ROOT / 'examples').glob('*/model.scn'))
    assert examples
    assert [(item.name, item.path) for item in found if item.kind == 'example'] == [
        (f'examples.{path.parent.name}', path) for path in examples
    ]
    made_up = [item for item in found if item.kind == 'family']
    assert [item.name for item in made_up] == ['events_1', 'events_4', 'stiff_1', 'stiff_4']
    assert all(item.path == tmp_path / item.name / 'model.scn' for item in made_up)
    assert [(item.family, item.size) for item in made_up[:2]] == [('events', 1), ('events', 4)]
    assert all(item.run is None for item in found)
    assert list(tmp_path.iterdir()) == []  # the list writes nothing
    assert workloads(ROOT) == []
    for wrong in ({'families': ['no_such_family']}, {'families': ['events'], 'sizes': [0]}, {'runs': 'some'}):
        with pytest.raises(ValueError):
            workloads(ROOT, examples=True, **wrong)


def test_the_catalogue_workloads_are_owners_that_the_locator_knows():
    entries = catalogue.entries(ROOT)
    assert entries
    everything = workloads(ROOT, scenarios=[*entries, *entries])
    assert [(item.kind, item.name, item.path) for item in everything] == [
        ('catalogue', name, path) for name, path in entries.items()
    ]
    first = next(iter(entries))
    (one,) = workloads(ROOT, scenarios=[first], runs='all')
    assert one.name == first and one.run == ALL
    for name in entries:
        package, _, variant = name.partition(':')
        if variant:
            # A package with variants gives each of its variants, and nothing else.
            named = [item.name for item in workloads(ROOT, scenarios=[package])]
            assert named == [owner for owner in entries if owner.partition(':')[0] == package]
    with pytest.raises(ValueError):
        workloads(ROOT, scenarios=['SC97'])


def test_a_scenario_is_named_whole(tmp_path):
    """On a made-up catalogue: a name is an owner or a package with variants, never a part of a name."""
    for folder in ('SC97', 'SC98', 'SC98/variants/east', 'SC98/variants/west', 'SC99_more'):
        (tmp_path / 'scenarios' / folder).mkdir(parents=True)
        (tmp_path / 'scenarios' / folder / 'model.scn').write_text('', encoding='utf-8')
    assert set(catalogue.entries(tmp_path)) == {'SC97', 'SC98:east', 'SC98:west', 'SC99_more'}

    def named(*scenarios):
        return [item.name for item in workloads(tmp_path, scenarios=scenarios)]

    assert named('SC97') == ['SC97']
    assert named('SC98') == ['SC98:east', 'SC98:west']
    assert named('SC98:west', 'SC97') == ['SC97', 'SC98:west']
    for part in ('SC9', 'SC99', 'SC98:eas', 'SC98:'):
        with pytest.raises(ValueError):
            named(part)
    assert workloads(tmp_path, examples=True) == []
