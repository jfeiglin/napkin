"""The benchmark harness (`tools/bench/`), on synthetic models and made-up profiles.

Each family compiles and runs at its smallest size, and is what its docstring says, read from its
program and its record: copies that read only themselves, an aggregate that only a value of the top
level reads, a guard that reads every copy, a rate that reads every copy, flows that differ by the
stiffness, `n` starts at equal steps, a tank drained to its bound with rates that read the state, the
same tank in order, a linear chain of compartments, a chain of formulas, and each family of copies
again from a table. The closed forms are worked by hand. The attribution of a profile puts each
function in the group of its file, a factorization of C in the linear algebra, moves the time of a
helper to its callers, and keeps the whole. A workload that fails is a record, and the harness goes
on. The document has its slots and goes through JSON. The catalogue is found by its locator and is
opt-in. No test judges a duration: the times are only recorded.
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

import napkin
from napkin import expressions
from tools import catalogue
from tools.bench import families, measure
from tools.bench.__main__ import main
from tools.bench.workloads import ALL, Workload, workloads

ROOT = catalogue.ROOT


@pytest.fixture(scope='module')
def made(tmp_path_factory):
    """`made(family, n)`: the compiled model of a family at a size and the record of its default run,
    each made once for the module."""
    folder, found = tmp_path_factory.mktemp('families'), {}

    def make(family, n):
        if (family, n) not in found:
            model = napkin.load_scenario(families.write(family, n, folder))
            found[family, n] = (model, napkin.run(model.program, model.configuration))
        return found[family, n]

    return make


def at(made, family, n, paths, times):
    """The values of paths of a family's run at times ([path][time])."""
    model, record = made(family, n)
    return [reading.values for reading in napkin.read(record, model.program, paths, times)]


def written(made, family, n, template, part):
    """The names that a part of a family's program reads directly: a flow's request, or a value's
    formula (`this.c1`, `pool.mean`)."""
    model, _ = made(family, n)
    found = model.program.template(template).part(part)
    expr = getattr(found, 'request', None) or found.init
    return {name for name, _ in getattr(expr, 'expr', expr).reads}


def reads(made, family, n, path):
    """The origins of the parts that a value of a family's run can read (its evidence trail)."""
    model, record = made(family, n)
    found = napkin.report(record, model.program, model.configuration, [path], [0], model=model.declared)
    return {used.origin for used in found.values[0].trail}


# --- The families ---------------------------------------------------------------------------------


@pytest.mark.parametrize('family', list(families.FAMILIES))
def test_each_family_compiles_and_its_run_reaches_its_horizon_at_its_smallest_size(family, made):
    _, record = made(family, 1)
    assert record.failure is None, record.failure
    assert float(record.manifest.horizon) == (48 if family in ('rationing', 'priority') else 240)
    assert families.FAMILIES[family].stresses


def test_a_family_has_no_size_below_one(tmp_path):
    for n in (0, -1, 1.5, True):
        with pytest.raises(ValueError):
            families.write('events', n, tmp_path)
    with pytest.raises(KeyError):
        families.write('no_such_family', 1, tmp_path)


def test_the_copies_of_instances_read_only_themselves(made):
    """The water of each copy rests on its own flows and inputs, and on no other copy's."""
    for k in (1, 2, 3):
        found = reads(made, 'instances', 3, f'c{k}.water')
        assert 'Cell.storm' in found and 'Cell.inflow' in found
    model, _ = made('instances', 3)
    assert [member.id for template in model.program.templates for member in template.members] == [
        'c1',
        'c2',
        'c3',
    ]


def test_only_a_value_of_the_top_level_reads_the_aggregate_of_aggregate_output(made):
    assert 'pool.held' in reads(made, 'aggregate_output', 2, 'held')
    for path in ('c1.water', 'c1.spill.actual_rate', 'spilled_total'):
        assert 'pool.held' not in reads(made, 'aggregate_output', 2, path), path


def test_the_guard_of_aggregate_guard_counts_every_flag_and_fires_with_the_last(made):
    """The k-th flag of 3 rises at 9 days k / 3: at 72, 144 and 216 h; the watcher sounds once, at
    216 h, when the count of flags reaches 3."""
    _, record = made('aggregate_guard', 3)
    raised = sorted(
        float(entry.t) for entry in record.trace if entry.kind == 'start' and entry.part == 'Cell.raise_flag'
    )
    assert raised == pytest.approx([72, 144, 216])
    (sound,) = [entry for entry in record.trace if entry.kind == 'start' and entry.part == 'watch.sound']
    assert float(sound.t) == pytest.approx(216)
    assert 'Cell.flag' in reads(made, 'aggregate_guard', 3, 'watch.alarm')


def test_every_rate_of_aggregate_feedback_reads_the_mean_of_every_copy(made):
    for k in (1, 2, 3):
        assert 'pool.mean' in reads(made, 'aggregate_feedback', 3, f'c{k}.grow.actual_rate')
    # The mean starts at the mean of the starts 0.05 + 0.4 k / 3: 0.05 + 0.4 * 2 / 3.
    (levels,) = at(made, 'aggregate_feedback', 3, ['level_total'], [0])
    assert levels[0] == pytest.approx(3 * (0.05 + 0.4 * 2 / 3))


def test_the_flows_of_stiff_differ_by_the_stiffness(made):
    assert written(made, 'stiff', 2, 'chain', 'f1') == {'this.slow', 'this.stiffness', 'this.c1', 'this.half'}
    assert written(made, 'stiff', 2, 'chain', 'f2') == {'this.slow', 'this.c2', 'this.half'}
    # Nothing leaves the chain: what the first compartment held is in the compartments or out.
    c1, c2, out = at(made, 'stiff', 2, ['chain.c1', 'chain.c2', 'chain.out'], [240])
    assert c1[0] + c2[0] + out[0] == pytest.approx(1, abs=1e-8)


@pytest.mark.parametrize('n', [1, 2, 3])
def test_the_event_of_events_starts_n_times_at_equal_steps(n, made):
    """The period is 240 h / (n + 0.5); the k-th ring is at k periods, and the lamp is on from the
    first ring to the second, from the third to the fourth, and so on, until 240 h."""
    _, record = made('events', n)
    period = 240 / (n + 0.5)
    rings = [float(entry.t) for entry in record.trace if entry.kind == 'start']
    assert rings == pytest.approx([k * period for k in range(1, n + 1)])
    ends = [*rings, 240.0]
    lit = sum(ends[k + 1] - ends[k] for k in range(0, n, 2))
    assert at(made, 'events', n, ['clock.lit'], [240])[0][0] == pytest.approx(lit)


def test_rationing_drains_its_tank_to_its_bound_then_serves_the_inflow(made):
    """One user asks at least 20 L/h, capped at 16 L/h, from 160 L that 5 L/h fill: empty at
    160 / 11 h, and from then the user takes the inflow."""
    use, water = at(made, 'rationing', 1, ['tank.use_1.actual_rate', 'tank.water'], [10, 47])
    assert use == pytest.approx([16, 5]) and water == pytest.approx([160 - 11 * 10, 0], abs=1e-9)
    assert at(made, 'rationing', 1, ['tank.water'], [160 / 11 - 0.5])[0][0] == pytest.approx(5.5)


def test_priority_serves_the_first_user_in_full_and_the_rest_to_the_second(made):
    """Two users capped at 48 L/h from 480 L that 15 L/h fill: the first takes its whole request and
    the second the rest of the cap until the tank empties at 480 / 33 h; then the first takes the
    inflow and the second nothing."""
    first, second = at(made, 'priority', 2, ['tank.use_1.actual_rate', 'tank.use_2.actual_rate'], [10, 47])
    assert first[0] + second[0] == pytest.approx(48) and first[0] > 20
    assert (first[1], second[1]) == (pytest.approx(15), pytest.approx(0, abs=1e-9))
    assert at(made, 'priority', 2, ['tank.water'], [480 / 33 - 0.5])[0][0] == pytest.approx(16.5)


def test_the_chain_of_compartments_drains_in_closed_form(made):
    """One compartment that drains at 2 x 0.05 an hour: c1 = e^(-0.1 t)."""
    c1, out = at(made, 'compartments', 1, ['chain.c1', 'chain.out'], [10, 240])
    assert c1 == pytest.approx([math.exp(-1), math.exp(-24)], rel=1e-6, abs=1e-10)
    assert out[0] == pytest.approx(1 - math.exp(-1), rel=1e-8)


def test_the_rates_of_formulas_read_a_chain_of_n_formulas(made):
    """Each formula reads the one before it and the stock; the flows read the last, the middle and
    the first, and through them the drain rests on the whole chain."""
    n = 4
    assert written(made, 'formulas', n, 'tank', 'f1') == {'this.level'}
    for k in range(2, n + 1):
        assert written(made, 'formulas', n, 'tank', f'f{k}') == {f'this.f{k - 1}', 'this.level'}
    assert written(made, 'formulas', n, 'tank', 'drain') == {'this.pace', f'this.f{n}'}
    assert written(made, 'formulas', n, 'tank', 'see') == {'this.pace', f'this.f{n // 2}'}
    assert written(made, 'formulas', n, 'tank', 'note') == {'this.pace', 'this.f1'}
    assert {f'tank.f{k}' for k in range(1, n + 1)} <= reads(made, 'formulas', n, 'tank.drain.actual_rate')


@pytest.mark.parametrize(
    'family, total',
    [
        ('instances', 'spilled_total'),
        ('aggregate_output', 'held'),
        ('aggregate_guard', 'filled_total'),
        ('aggregate_feedback', 'level_total'),
    ],
)
def test_a_family_from_a_table_runs_as_its_family_of_copies(family, total, made):
    """The same cells, written by hand or read from a table, give the same sums."""
    plain = at(made, family, 3, [total], [60, 240])[0]
    tabled = at(made, f'table_{family}', 3, [total], [60, 240])[0]
    assert tabled == pytest.approx(plain, rel=1e-9, abs=1e-12)
    model, _ = made(f'table_{family}', 3)
    assert sum(len(template.members) for template in model.program.templates if template.name == 'Cell') == 3


# --- Where the time goes ----------------------------------------------------------------------------


def entry(seconds, callers=None):
    """One function of made-up statistics, in the shape of `pstats.Stats(…).stats`: its own seconds,
    and its callers as {caller: its own seconds under that caller}."""
    callers = {caller: (1, 1, under, under) for caller, under in (callers or {}).items()}
    return (1, 1, seconds, seconds, callers)


PLACES = {
    'analysis': [
        '/x/napkin/model/compile.py',
        '/x/napkin/model/language/parse.py',
        '/x/napkin/program/proofs.py',
    ],
    'expressions': [
        '<model>',
        '<string>',
        '/x/napkin/core/evaluation.py',
        '/x/napkin/engine/timeline/reads.py',
    ],
    'field': [
        '/x/napkin/engine/allocation.py',
        '/x/napkin/engine/solve/fair.py',
        '/x/napkin/engine/timeline/network.py',
        '/x/napkin/engine/timeline/selection.py',
        '/x/napkin/engine/timeline/declared.py',
        *(
            f'/x/napkin/engine/continuous/{name}.py'
            for name in ('fields', 'kernels', 'bounds', 'system', 'highs')
        ),
    ],
    'solver': [
        '/x/napkin/engine/continuous/integrate.py',
        '/x/napkin/engine/timeline/sparse.py',
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
        '/x/napkin/engine/timeline/moment.py',
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

BROKEN = families.events(1).replace('t >= this.next', 't >= this.nothing_declared')
# A model that compiles and whose run stops: a move of 9 L from 8 L at 1 h.
STOPS = """scenario "A run that stops"
    summary "A move takes more than the tank holds."
    horizon 10 h
    scope "Nothing: the model is synthetic."

tank:
    "The tank."
    water: L = 8 L in [0 L,] @shape
    out: L = 0 L in [0 L,] @shape
    take = event():
        after 1 h:
            move 9 L from this.water to this.out

tank.take.start()

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
        (path.parent / 'units.json').write_text(json.dumps(families.RATIONING_UNITS), encoding='utf-8')
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
    assert broken['compile']['cold']['failed'].startswith('LanguageError: ')
    assert (
        'nothing_declared' in broken['compile']['cold']['failed'] and 'from' not in broken['compile']['cold']
    )
    for later in measurements(broken)[1:]:
        assert later == {'failed': broken['compile']['cold']['failed'], 'from': 'compile'}
    # The run stops: the compile is measured, and the failure is the first result's.
    assert 'failed' not in stops['compile']['cold']
    failed = stops['values']['one_run']['cold']
    assert failed['failed'].startswith('RuntimeError: the run stops at 1 h: ') and 'from' not in failed
    for later in measurements(stops)[2:]:
        assert later == {'failed': failed['failed'], 'from': 'first result'}
    assert not any('failed' in found for found in measurements(good))
    assert good['run'] is None and good['family'] == 'events' and good['size'] == 2


def test_a_long_failure_keeps_its_ends():
    failed = measure.failure(ValueError('start ' + 'x' * 5000 + '\n the end'))['failed']
    assert failed.startswith('ValueError: start ') and failed.endswith('the end') and len(failed) < 400
    assert measure.failure(KeyError('name')) == {'failed': "KeyError: 'name'"}
    assert measure.perform({'kind': 'compile', 'path': '/no/such/model.scn'})['failed']


def test_the_document_has_its_slots_and_goes_through_json(records):
    from napkin.store import ENVIRONMENT

    settings = {'repeats': 2, 'samples': 4, 'timeout': 600, 'runs': 'first'}
    document = measure.document(records, settings)
    assert json.loads(json.dumps(document)) == document
    assert {'commit', 'dirty', 'machine', 'processors', 'settings', 'groups', 'workloads'} <= set(document)
    # The files of each role in this revision are in the document, for a comparison by role.
    assert set(document['groups']) == set(measure.GROUPS) - {'other'}
    for group, places in measure.FILES:
        assert set(places) <= set(document['groups'][group])
    assert document['settings'] == settings and document['machine'] == json.loads(json.dumps(ENVIRONMENT))
    assert document['commit'] is None or re.fullmatch(r'[0-9a-f]{40}', document['commit'])
    assert isinstance(document['processors'], int) and len(document['workloads']) == len(records)
    for item in document['workloads']:
        assert {'kind', 'name', 'path', 'run', 'compile', 'values'} <= set(item)
        assert set(item['compile']) == {'cold'} and set(item['values']) == {'one_run', 'every_run', 'batch'}
        assert set(item['values']['one_run']) == {'cold', 'warm', 'report', 'where'}
    good = document['workloads'][-1]
    one = good['values']['one_run']
    assert {'seconds', 'peak_mb'} <= set(good['compile']['cold']) and 'runs' not in good['compile']['cold']
    assert {'seconds', 'peak_mb', 'parts'} <= set(one['cold'])
    assert sum(one['cold']['parts'].values()) == pytest.approx(one['cold']['seconds'])
    warm = one['warm']
    assert warm['repeats'] == 2 == len(warm['seconds'])
    assert warm['median_seconds'] == statistics.median(warm['seconds'])
    assert warm['min_seconds'] == min(warm['seconds'])
    # Two rings, each a firing, a start, a commit and a finish; one template, one member, one flow.
    size = warm['size']
    assert (size['templates'], size['members'], size['flows'], size['events']) == (1, 1, 1, 1)
    assert size['trace_kinds'] == {'commit': 2, 'finish': 2, 'fire': 2, 'start': 2} and size['trace'] == 8
    assert size['pieces'] >= size['histories'] > 0
    assert set(one['where']['groups']) == set(measure.GROUPS)
    assert sum(group['share'] for group in one['where']['groups'].values()) == pytest.approx(1)
    # The report of the run is measured, and the profile is of a run and its report.
    assert one['report']['report_seconds'] > 0 and one['report']['values'] > 0
    assert one['where']['groups']['reporting']['own_seconds'] > 0
    assert one['where']['groups']['scheduler']['own_seconds'] > 0
    assert good['values']['batch'] == {'skipped': 'no draw'}
    assert good['path'] == 'events_2/model.scn'
    # The table: one row for each record, and a failure in the row of its workload.
    lines = measure.table(document).splitlines()
    assert len(lines) == len(records) + 3  # the heads, the rows, the count, the legend
    for item, line in zip(document['workloads'], lines[1:]):
        assert line.startswith(item['name']) and ('FAILED' in line) == (item is not good)
    assert 'FAILED at the compile' in lines[1] and 'FAILED at the first result' in lines[2]


def uncertain(tmp_path):
    """The tank of `TWO_RUNS` with its rate drawn from a uniform distribution."""
    text = TWO_RUNS.replace('= 0.05 fraction/h in', '= uniform(0.02 fraction/h, 0.08 fraction/h).draw() in')
    assert text != TWO_RUNS
    path = tmp_path / 'uncertain' / 'model.scn'
    path.parent.mkdir()
    path.write_text(text, encoding='utf-8')
    return napkin.load_scenario(path)


def test_a_study_measures_a_run_with_a_draw_and_skips_one_without(tmp_path):
    found = measure.study(uncertain(tmp_path), None, 5)
    assert (found['samples'], found['jobs'], found['run']) == (5, 1, None)
    assert 'first_seconds' not in found
    assert found['samples_per_second'] == pytest.approx(5 / found['seconds'])
    plain = napkin.load_scenario(families.write('events', 1, tmp_path))
    assert measure.study(plain, None, 5) == {'skipped': 'no draw'}


def test_a_study_on_two_processes_is_measured_after_its_pool_has_started(tmp_path):
    found = measure.study(uncertain(tmp_path), None, 4, jobs=2)
    assert (found['samples'], found['jobs']) == (4, 2) and found['first_seconds'] > 0


# Two runs of one model: the second has a faster inflow.
TWO_RUNS = """scenario "Two runs"
    summary "A tank fills at one of two rates."
    horizon 10 h
    scope "Nothing: the model is synthetic."

tank:
    "The tank."
    input rate: fraction/h = 0.05 fraction/h in [0 fraction/h, 1 fraction/h] @shape
    water: fraction = 0 in [0,] scale 1 @shape
        "Water in the tank"
    flow fill: SOURCE -> this.water
        request = this.rate

options "Inflow":
    "Slow":
        "The inflow as it is."
    "Fast":
        "A faster inflow."
        tank.rate = 0.5 fraction/h @shape

runs:
    slow = "Slow"
    quick = "Fast"

record shape: assumption "A synthetic model of the benchmark, with no source."
"""


def test_the_survey_times_each_run_of_a_model_in_its_order(tmp_path):
    path = tmp_path / 'two' / 'model.scn'
    path.parent.mkdir()
    path.write_text(TWO_RUNS, encoding='utf-8')
    (record,) = measure.bench(
        [Workload('family', 'two', path)], repeats=1, survey=True, run_task=measure.inline
    )
    assert record['run'] == 'slow'  # the measurements in full are of the first named run
    found = record['values']['every_run']
    assert list(found['runs']) == ['slow', 'quick'] and found['slowest'] in found['runs']
    for item in found['runs'].values():
        assert item['seconds'] > 0 and item['trace'] == 0 and item['histories'] > 0
    slowest = found['runs'][found['slowest']]['seconds']
    assert slowest == max(item['seconds'] for item in found['runs'].values())
    line = measure.table(measure.document([record], {'samples': None})).splitlines()[1]
    assert f'slowest of 2 runs: {found["slowest"]}' in line
    (plain,) = measure.bench([Workload('family', 'two', path)], repeats=1, run_task=measure.inline)
    assert plain['values']['every_run'] == {'skipped': 'no survey asked'}


def test_a_measurement_runs_in_a_process_of_its_own_within_its_time(tmp_path):
    good = families.write('events', 1, tmp_path)
    broken = tmp_path / 'broken.scn'
    broken.write_text(BROKEN, encoding='utf-8')
    failed = measure.isolated({'kind': 'compile', 'path': str(broken)}, 120)
    assert failed['failed'].startswith('LanguageError: ') and 'nothing_declared' in failed['failed']
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
    assert item['name'] == 'events_1' and item['kind'] == 'family' and item['run'] is None
    assert not any('failed' in found for found in measurements(item))
    assert item['values']['batch'] == {'skipped': 'no samples asked'}
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
