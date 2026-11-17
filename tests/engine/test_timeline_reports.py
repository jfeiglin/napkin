"""The reports of a run of a model with a table (`napkin/engine/timeline/reports.py`).

A report of a model with no table reads a trajectory. A run of a table has none: its rows come from
the result of the run. The oracles:

- closed forms of the model, from the numbers of its table: each cell spills at a constant rate for
  two days from the time at which its gate opens, and an output with a lag has the value of that
  many hours before;
- the report of the flat structure of the same file, where each row is written out and the run has
  a trajectory: the rows of the outputs, and the evidence trail with each part under the name of the
  row that stands for its class.
"""

import itertools
import json
from collections import Counter

import pytest
from jsonschema import Draft202012Validator

from napkin.core.expr import read
from napkin.engine import evaluate_study, report, sample_result, timeline
from napkin.engine.errors import SimulationError
from napkin.engine.runtime import simulate
from napkin.engine.timeline import reports
from napkin.expressions import UnitSystem, names_in
from napkin.model import hybrid
from napkin.model.ir import thaw
from napkin.model.model import build_model
from napkin.schema import FOLDER as SCHEMAS
from tests.engine.test_timeline import DAY, GATES, HORIZON, package

# The cells of `GATES` with a flow that never moves anything, and with the water that the cells
# spilled 12 h before.
REPORTED = (
    GATES.replace(
        '    flow spill: water -> spilled at spillway while gate is "open"\n',
        '    flow spill: water -> spilled at spillway while gate is "open"\n'
        '    flow drip: water -> seeped at 0 fraction/day\n',
    )
    + """
output spilled_late: fraction = sum(Cell.spilled)  @shape
    "Water that all cells spilled 12 h before"
    lag 12 h
"""
)
LEVELS = [0.05, 0.2, 0.11]
INFLOW, SPILLWAY, OPEN_FOR = 0.06, 0.15, 2 * DAY
TIMES = [0.0, 30.0, 60.0, 100.0, HORIZON]


def spilled(hours):
    """What the cells have spilled together at a time: the gate of a cell opens when what arrived
    (the inflow, from zero) is at its level, and the cell spills at the rate of the spillway for
    the two days in which the gate is open."""
    total = 0.0
    for level in LEVELS:
        opened = level / INFLOW * DAY
        total += SPILLWAY / DAY * min(max(hours - opened, 0.0), OPEN_FOR)
    return total


def both(tmp_path, values=None):
    """The run of the table from its hybrid core, with its record, and the run of its flat
    structure with the library of the model."""
    assert REPORTED.count('flow drip') == 1
    path = package(tmp_path, REPORTED, cells=('level: fraction @shape', LEVELS))
    result = timeline.run(timeline.Plan.of(hybrid.compile(path)), values, record=True)
    model = build_model(path)
    library = thaw(model.library)
    flat = {
        f'cells_{k}.{name.split(".", 1)[1]}': value
        for name, value in (values or {}).items()
        for k in (1, 2, 3)
    }
    resolved = model.resolve(next(iter(model.runs)), flat)
    return result, resolved, simulate(resolved, library), library


def test_the_rows_of_the_outputs_of_a_table_are_those_of_its_closed_forms_and_of_its_flat_structure(tmp_path):
    result, resolved, trajectory, library = both(tmp_path)
    rows = reports.outputs(result, TIMES)
    assert [row['t'] for row in rows] == TIMES
    for row in rows:
        assert row['values']['spilled_total'] == pytest.approx(spilled(row['t']), rel=1e-12, abs=1e-15)
        # An output with a lag of 12 h has what its expression had 12 h before, and nothing before
        # the start of the run.
        assert row['values']['spilled_late'] == pytest.approx(spilled(row['t'] - 12.0), rel=1e-12, abs=1e-15)
    flat = report.evaluate_outputs({'resolved': resolved, 'trajectory': trajectory}, library, TIMES)
    for row, other in zip(rows, flat):
        assert row['statuses'] == other['statuses'] and set(row['values']) == set(other['values'])
        for name, value in other['values'].items():
            assert row['values'][name] == pytest.approx(value, rel=1e-9, abs=1e-15), (row['t'], name)
    # The value of an output of the result itself is its expression at the horizon, with no lag.
    assert result.outputs['spilled_late'] == pytest.approx(spilled(HORIZON), rel=1e-12)


def test_a_family_in_the_general_tier_has_the_rows_of_the_flat_structure(tmp_path):
    """A spillway of 4 a day empties a cell while its gate is open: the run of the family is made
    in the general tier, where each cell is a component. The rows come from the same record."""
    result, resolved, trajectory, library = both(tmp_path, {'cells_1.spillway': 4.0})
    assert result.run.plan.general - {0}
    rows = reports.outputs(result, TIMES)
    flat = report.evaluate_outputs({'resolved': resolved, 'trajectory': trajectory}, library, TIMES)
    for row, other in zip(rows, flat):
        assert row['statuses'] == other['statuses']
        for name, value in other['values'].items():
            assert row['values'][name] == pytest.approx(value, rel=1e-7, abs=1e-12), (row['t'], name)
    # Each cell held 0.6 and got the inflow: it cannot spill more than that.
    assert rows[-1]['values']['spilled_total'] <= 3 * (0.6 + INFLOW * HORIZON / DAY)


@pytest.mark.parametrize('values', [None, {'cells_1.spillway': 4.0}])
def test_the_evidence_trail_of_a_table_has_the_parts_of_each_class_once(tmp_path, values):
    """The flat structure has each part once for each row; the hybrid core has it once for each
    class, under the name of the row that stands for the class. A part of a class is exercised when
    it is for one of its rows. The spill moved material while a gate was open, though no gate is
    open at the end of the run; the drip never moved anything, so it is possible and not exercised."""
    result, resolved, trajectory, library = both(tmp_path, values)
    trail = reports.evidence(result)
    flat = report.evidence_trail(resolved, trajectory, library, UnitSystem(library['units']))
    assert trail['library'] == flat['library'] and trail['records'] == flat['records']

    def of_class(names):
        return {'cells_1.' + name.split('.', 1)[1] if name.startswith('cells_') else name for name in names}

    assert set(trail['outcomes']) == set(flat['outcomes'])
    for name, found in trail['outcomes'].items():
        other = flat['outcomes'][name]
        assert set(found['exercised']) == of_class(other['exercised'])
        assert set(found['possible']) == of_class(other['possible']) - set(found['exercised'])
        assert found['basis'] == other['basis']
        assert 'cells_1.spill' in found['exercised'] and 'cells_1.drip' in found['possible']
    assert set(trail['parts']) == of_class(flat['parts'])


def test_a_report_needs_the_record_of_the_run_and_names_an_output_that_it_does_not_give(tmp_path):
    path = package(tmp_path, REPORTED, cells=('level: fraction @shape', LEVELS))
    plan = timeline.Plan.of(hybrid.compile(path))
    with pytest.raises(ValueError, match='record'):
        reports.outputs(timeline.run(plan), TIMES)
    with pytest.raises(report.ReportingError):
        reports.outputs(timeline.run(plan, record=True), [HORIZON + 1.0])
    twice = (
        REPORTED
        + """
output late_twice: fraction = 2 * spilled_late  @shape
    "Twice the water of 12 h before"
"""
    )
    other = timeline.Plan.of(
        hybrid.compile(package(tmp_path / 'twice', twice, cells=('level: fraction @shape', LEVELS)))
    )
    with pytest.raises(timeline.Outside, match='late_twice'):
        reports.outputs(timeline.run(other, record=True), TIMES)


# ---- the report of a run: the things of a table by group ----------------------------------------------

# The cells with a status, which follows the gate.
WITH_STATUS = REPORTED.replace(
    '    event open once when arrived >= level:  @shape\n',
    '    status degraded when gate is "open"  @shape\n'
    '        "The gate is open."\n'
    '    status ok\n'
    '        "The gate is closed."\n'
    '    event open once when arrived >= level:  @shape\n',
)
# Six rows of two classes: the rows 1, 3 and 5 give no spillway (they have that of the template),
# and the rows 2, 4 and 6 give one.
TWO_CLASSES = (
    'level: fraction @shape,spillway: fraction/day @shape\n0.05,\n0.2,0.3\n0.11,\n0.05,0.3\n0.3,\n0.08,0.25\n'
)
CLASSES = {'cells_1': (1, 3, 5), 'cells_2': (2, 4, 6)}
ASKED = [30.0, 60.0, 100.0]


def grouped(tmp_path, rows=()):
    """(the report of the run of the table from its hybrid core, the report of the same run in the
    study of the flat model: `sample_result`)."""
    path = package(tmp_path, WITH_STATUS, cells=('level: fraction @shape', LEVELS))
    (tmp_path / 'cells.csv').write_text(TWO_CLASSES, encoding='utf-8')
    core = hybrid.compile(path)
    assert sorted((family.host, family.rows) for family in core.families) == sorted(CLASSES.items())
    result = timeline.run(timeline.Plan.of(core), record=True)
    model = build_model(path)
    flat = sample_result(evaluate_study(model), ASKED)
    assert flat['status'] == 'accepted', flat['diagnostics']
    return reports.report_of(result, ASKED, rows), next(iter(flat['runs'].values()))


def test_the_health_of_a_group_counts_the_rows_of_the_flat_report_in_each_status(tmp_path):
    """The flat report has the health of each cell. The report of the table has, for each class, how
    many of its cells are in each status and in each state of the gate, with the text of each
    status: the counts of the cells of the class in the flat report."""
    got, flat = grouped(tmp_path)
    assert [item['t'] for item in got['health']] == [item['t'] for item in flat['health']]
    seen = Counter()
    for mine, theirs in zip(got['health'], flat['health']):
        assert mine['entities'] == {}  # this model has no thing outside its table
        assert set(mine['groups']) == set(CLASSES)
        for host, rows in CLASSES.items():
            cells = [theirs['entities'][f'cells_{k}'] for k in rows]
            group = mine['groups'][host]
            assert group['rows'] == len(rows)
            assert group['health'] == Counter(cell['health'] for cell in cells)
            assert group['modes'] == {
                f'{host}.gate': Counter(cell['modes'][f'cells_{k}.gate'] for k, cell in zip(rows, cells))
            }
            assert group['labels'] == {cell['health']: cell['label'] for cell in cells}
            seen.update(group['health'])
    # Both statuses are in the counts: the test is of open gates and of closed ones.
    assert seen['degraded'] > 0 and seen['ok'] > 0


def test_the_events_of_a_group_count_the_steps_of_the_flat_trace(tmp_path):
    """For each event of a class and each outcome: how many steps the flat trace has of it for the
    cells of the class, for how many cells, and the first and the last time."""
    got, flat = grouped(tmp_path)
    assert got['trace'] == []  # no thing outside the table, and no row is named
    want = {}
    for entry in flat['trace']:
        cell, event = entry['rule'].split('.', 1)
        host = next(host for host, rows in CLASSES.items() if int(cell.split('_')[1]) in rows)
        key = (host, f'{host}.{event}', entry['outcome'])
        found = want.setdefault(key, {'count': 0, 'cells': set(), 'first': entry['t'], 'last': entry['t']})
        found['count'] += 1
        found['cells'].add(cell)
        found['first'], found['last'] = min(found['first'], entry['t']), max(found['last'], entry['t'])
    assert {(item['group'], item['event'], item['outcome']) for item in got['events']} == set(want)
    assert len(got['events']) == len(want) >= 6
    for item in got['events']:
        found = want[item['group'], item['event'], item['outcome']]
        assert (item['count'], item['rows']) == (found['count'], len(found['cells']))
        assert item['first'] == pytest.approx(found['first'], abs=1e-9)
        assert item['last'] == pytest.approx(found['last'], abs=1e-9)
    assert sum(item['count'] for item in got['events']) == len(flat['trace'])


def test_a_row_that_is_named_has_its_own_health_and_its_own_steps(tmp_path):
    """The rows that a caller names are in the report as the things outside a table are: the health
    of the cell and the steps of its events, as the flat report has them."""
    got, flat = grouped(tmp_path, rows=('cells_4', 'cells_5'))
    for mine, theirs in zip(got['health'], flat['health']):
        assert mine['entities'] == {name: theirs['entities'][name] for name in ('cells_4', 'cells_5')}
    steps = [entry for entry in flat['trace'] if entry['rule'].split('.')[0] in ('cells_4', 'cells_5')]
    assert len(got['trace']) == len(steps) >= 4
    for mine, theirs in zip(got['trace'], steps):
        assert mine['t'] == pytest.approx(theirs['t'], abs=1e-9)
        for key in ('rule', 'entity', 'event', 'outcome', 'label', 'changes', 'before', 'path', 'fires'):
            assert mine[key] == theirs[key], key
    with pytest.raises(ValueError, match='cells_9 is no row of a table'):
        grouped(tmp_path / 'other', rows=('cells_9',))


def test_the_report_of_a_table_has_the_outputs_the_peaks_and_the_groups_of_the_flat_report(tmp_path):
    got, flat = grouped(tmp_path)
    assert got['horizon'] == flat['horizon'] and list(got['outcomes']) == list(flat['outcomes'])
    for name, output in flat['outcomes'].items():
        mine = got['outcomes'][name]
        assert {key: value for key, value in mine.items() if key != 'expr'} == {
            key: value for key, value in output.items() if key != 'expr'
        }
        # The flat expression adds the six cells. That of the table has one member for each class.
        member = 'seeped' if name == 'seeped_total' else 'spilled'
        assert names_in(read(output['expr'])) == {f'cells_{k}.{member}' for k in range(1, 7)}
        assert names_in(read(mine['expr'])) == {f'{host}.{member}' for host in CLASSES}
    assert list(got['reporting_points']) == list(flat['reporting_points'])
    for mine, theirs in zip(got['samples'], flat['samples']):
        assert mine['t'] == theirs['t'] and mine['statuses'] == theirs['statuses']
        for name, value in theirs['values'].items():
            assert mine['values'][name] == pytest.approx(value, rel=1e-9, abs=1e-15)
    # A peak: the same value, and certified for the same outputs. (The candidate times of the two
    # reports differ: the flat report has those of the segments of its trajectory.)
    assert set(got['peaks']) == set(flat['peaks'])
    for name, peak in flat['peaks'].items():
        assert got['peaks'][name]['certified'] == peak['certified']
        assert got['peaks'][name]['status'] == peak['status']
        assert got['peaks'][name]['value'] == pytest.approx(peak['value'], rel=1e-9, abs=1e-15)
    # Each class with its rows, and the least and the greatest of each input over them: from the
    # numbers of the table and of the template.
    groups = {item['group']: item for item in got['groups']}
    assert {host: (item['set'], item['rows']) for host, item in groups.items()} == {
        'cells_1': ('cells', 3),
        'cells_2': ('cells', 3),
    }
    assert groups['cells_1']['inputs']['cells_1.spillway'] == {'least': 0.15, 'greatest': 0.15}
    spillway = groups['cells_2']['inputs']['cells_2.spillway']
    assert (spillway['least'], spillway['greatest']) == pytest.approx((0.25, 0.3))
    assert got['effective_inputs'] == {}


# The cells of `REPORTED` with an output that falls: the water that the cells hold rises with the
# storm and falls as it spills and seeps.
HELD = (
    REPORTED
    + """
output held: fraction = sum(Cell.water)  @shape
    "Water that all cells hold"
    level
"""
)


def held_run(tmp_path):
    path = package(tmp_path, HELD, cells=('level: fraction @shape', LEVELS))
    result = timeline.run(timeline.Plan.of(hybrid.compile(path)), record=True)
    plan = result.run.plan
    assert 'held' not in plan.resolved.proven_cumulative_outcomes
    assert {'spilled_total', 'seeped_total'} <= set(plan.resolved.proven_cumulative_outcomes)
    return result, plan.resolved


def test_the_peaks_of_a_table_are_those_of_a_reading_of_each_output_at_each_candidate_time(tmp_path):
    """The definition of a peak: each output read at each candidate time (`report.peaks_of`). The
    report reads an output that never falls at the horizon only, and each other output at each
    candidate time when the table is small: the peaks are the same, and none says that it read
    fewer times."""
    result, resolved = held_run(tmp_path)
    times = reports.candidate_times(result)
    every = report.peaks_of(
        reports.outputs(result, times),
        resolved.outcomes,
        resolved.proven_cumulative_outcomes,
        float(result.horizon),
    )
    assert reports.peaks(result) == every
    assert every['spilled_total']['certified'] and not every['held']['certified']
    # The water that the cells hold falls after its peak: the peak is before the horizon.
    assert every['held']['t'] < float(result.horizon)


def test_a_peak_over_a_large_table_is_read_at_fewer_times_and_says_so(tmp_path, monkeypatch):
    """When the candidate times times the rows are more than the work of the peaks, an output that
    can fall is read at fewer times, evenly spread, and its peak says how many of how many. An output
    that never falls is still certified at the horizon."""
    result, _ = held_run(tmp_path)
    times = reports.candidate_times(result)
    monkeypatch.setattr(reports, 'PEAK_WORK', 1)
    monkeypatch.setattr(reports, 'FEWEST_CANDIDATES', 5)
    got = reports.peaks(result)
    read = reports.thinned(times, 5)
    assert got['held']['candidates'] == {'read': 5, 'of': len(times)}
    rows = reports.outputs(result, read, ['held'])
    best = max(rows, key=lambda row: row['values']['held'])
    assert (got['held']['value'], got['held']['t']) == (best['values']['held'], best['t'])
    for name in ('spilled_total', 'seeped_total'):
        assert got[name]['certified'] and got[name]['t'] == float(result.horizon)
        assert 'candidates' not in got[name]


@pytest.mark.parametrize(
    'count, most', [(1, 2), (2, 2), (7, 7), (8, 3), (100, 7), (4204, 1000), (42004, 200)]
)
def test_thinned_times_are_at_most_so_many_evenly_spread_with_the_first_and_the_last(count, most):
    times = [0.5 * k for k in range(count)]
    got = reports.thinned(times, most)
    assert got == sorted(set(got)) and set(got) <= set(times)
    assert len(got) == min(count, most)
    assert got[0] == times[0] and got[-1] == times[-1]
    # Evenly spread: the gaps between neighbours differ by one place at most.
    places = [times.index(t) for t in got]
    gaps = [b - a for a, b in itertools.pairwise(places)]
    if gaps:
        assert max(gaps) - min(gaps) <= 1


def test_the_rows_of_a_table_can_each_take_their_steps_at_one_moment(tmp_path):
    """The budget of the steps of one moment (`max_steps`) is for one thing: with a table it is that
    number times the rows of the largest table. Here 30 cells with one level open at one moment and
    start to wait, 60 steps, where the budget of one thing is 10; one cell alone has 2 steps. With a
    budget of 1 for each row, 60 steps are more than the 30 that the table has, and the run stops
    with the name of the step that is next."""
    path = package(tmp_path, WITH_STATUS, cells=('level: fraction @shape', [0.11] * 30))
    plan = timeline.Plan.of(hybrid.compile(path))
    result = timeline.run(plan, record=True, settings={'max_steps': 10})
    found = {(item['event'], item['outcome']): item for item in reports.events(result)}
    opened = found['cells_1.open', 'done']
    assert (opened['count'], opened['rows']) == (30, 30) and opened['first'] == opened['last']
    assert opened['first'] == pytest.approx(0.11 / INFLOW * DAY)
    with pytest.raises(SimulationError, match='does not settle within 30 steps') as stopped:
        timeline.run(plan, settings={'max_steps': 1})
    assert stopped.value.diagnostics[0]['code'] == 'step_budget'


def problems(doc):
    """What the report schema says against a report, as texts."""
    schema = json.loads((SCHEMAS / 'report.schema.json').read_text(encoding='utf-8'))
    plain = json.loads(json.dumps(thaw(doc), allow_nan=False))
    return [error.message for error in Draft202012Validator(schema).iter_errors(plain)]


def test_the_report_of_the_runs_of_a_table_has_the_envelope_of_the_study_of_the_flat_model(tmp_path):
    """`study_of` gives what `sample_result` gives of the study of the flat model for all that names
    the model and the run, and the schema of a report holds it. A table run with no groups is no
    report: the schema says so."""
    path = package(tmp_path, WITH_STATUS, cells=('level: fraction @shape', LEVELS))
    (tmp_path / 'cells.csv').write_text(TWO_CLASSES, encoding='utf-8')
    got = reports.study_of(hybrid.compile(path), times=ASKED, rows=['cells_4'])
    flat = sample_result(evaluate_study(build_model(path)), ASKED)
    assert problems(got) == [] and problems(flat) == []
    assert {key: got[key] for key in got if key != 'runs'} == {
        key: flat[key] for key in flat if key != 'runs'
    }
    assert list(got['runs']) == list(flat['runs'])
    for name, mine in got['runs'].items():
        assert {key: mine[key] for key in ('label', 'options', 'starts', 'horizon')} == {
            key: flat['runs'][name][key] for key in ('label', 'options', 'starts', 'horizon')
        }
        assert [group['group'] for group in mine['groups']] == list(CLASSES)
    (name,) = got['runs']
    less = {
        **got,
        'runs': {name: {key: value for key, value in got['runs'][name].items() if key != 'groups'}},
    }
    assert problems(less) != []


def test_a_run_of_a_table_that_the_engine_stops_rejects_the_report(tmp_path):
    """30 cells that open at one moment take 60 steps there. With a budget of one step for each row
    the engine stops the run: the report is rejected with what the engine says, and has no run."""
    path = package(tmp_path, WITH_STATUS, cells=('level: fraction @shape', [0.11] * 30))
    core = hybrid.compile(path)
    assert reports.study_of(core)['admissible']
    got = reports.study_of(core, settings={'max_steps': 1})
    assert (got['admissible'], got['status'], got['runs']) == (False, 'rejected', {})
    assert problems(got) == []
    codes = [item['code'] for item in got['diagnostics']]
    assert codes[0] == 'simulation' and 'step_budget' in codes
    assert all(item['run'] == next(iter(core.model.runs)) for item in got['diagnostics'])


def test_a_report_that_fails_for_one_run_has_no_run(tmp_path, monkeypatch):
    """A rejected report holds no run, also when a run before the one that fails gave its report.
    Here the report of the second run that is asked for fails."""
    path = package(tmp_path, WITH_STATUS, cells=('level: fraction @shape', LEVELS))
    core = hybrid.compile(path)
    (name,) = core.model.runs
    made, calls = reports.report_of, []

    def second_fails(result, times=None, rows=()):
        calls.append(result)
        if len(calls) == 2:
            raise report.ReportingError('The second report fails')
        return made(result, times, rows)

    monkeypatch.setattr(reports, 'report_of', second_fails)
    got = reports.study_of(core, [name, name])
    assert len(calls) == 2 and (got['admissible'], got['runs']) == (False, {})
    assert [item['message'] for item in got['diagnostics']] == ['The second report fails']
    assert problems(got) == []
