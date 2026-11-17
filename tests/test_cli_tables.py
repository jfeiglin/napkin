"""`napkin run` for a model with a table (napkin/commands/run.py, docs/cli.md).

A model with a table runs from its hybrid core, and what the report says of the rows of a table is
by group. The definition of each number is the study of the flat model of the same file
(`evaluate_study`, `sample_result`), in which each row is a thing of its own. The packages are
written in tmp_path with a reserved name.
"""

from __future__ import annotations

import json

import pytest

from napkin import cli
from napkin.engine import edits_for, evaluate_study, sample_result
from napkin.model import load_scenario
from tests.engine.test_timeline import package
from tests.engine.test_timeline_reports import CLASSES, LEVELS, TWO_CLASSES, WITH_STATUS
from tests.model.test_hybrid import SELF_LIST


@pytest.fixture
def cells(tmp_path):
    """A package whose table has six rows of two classes, with a status that follows a gate."""
    folder = tmp_path / 'SC97'
    package(folder, WITH_STATUS, cells=('level: fraction @shape', LEVELS))
    (folder / 'cells.csv').write_text(TWO_CLASSES, encoding='utf-8')
    return folder


def run(capsys, *argv):
    """(the exit code, what the command prints, what it writes of errors)."""
    code = cli.main(['run', '--no-store', *map(str, argv)])
    done = capsys.readouterr()
    return code, done.out, done.err


def flat_report(folder, times=()):
    study = evaluate_study(load_scenario(folder / 'model.scn'))
    return next(iter(sample_result(study, list(times))['runs'].values()))


def test_the_outcomes_of_a_table_model_are_those_of_the_study_of_its_flat_model(cells, capsys):
    code, out, err = run(capsys, cells, '--json', '--at', '30h')
    assert code == 0 and err == ''
    doc = json.loads(out)
    assert doc['admissible'] and doc['scenario'] == 'SC97'
    # The model is the same model: the table gives its hash, whichever way it runs.
    assert doc['model_hash'] == load_scenario(cells / 'model.scn').model_hash
    (shown,) = doc['runs'].values()
    flat = flat_report(cells, [30.0])
    assert list(shown['reporting_points']) == list(flat['reporting_points'])
    for point, row in flat['reporting_points'].items():
        mine = shown['reporting_points'][point]
        assert mine['t'] == row['t'] and mine['statuses'] == row['statuses']
        for name, value in row['values'].items():
            assert mine['values'][name] == pytest.approx(value, rel=1e-9, abs=1e-15)
    assert {group['group']: group['rows'] for group in shown['groups']} == {host: 3 for host in CLASSES}
    # No row is named: the events of the rows are in the counts of their groups only.
    assert shown['events'] == []
    steps = [entry for entry in flat['trace'] if entry['outcome'] is not None]
    assert sum(item['count'] for item in shown['group_events'] if item['outcome'] is not None) == len(steps)
    assert 'health' not in shown and 'peaks' not in shown


def test_the_full_document_has_the_health_of_the_groups_and_the_peaks(cells, capsys):
    code, out, _ = run(capsys, cells, '--json', 'full')
    (shown,) = json.loads(out)['runs'].values()
    flat = flat_report(cells)
    assert code == 0 and set(shown['peaks']) == set(flat['peaks'])
    (end,) = shown['health']
    at_end = flat['health'][-1]['entities']
    for host, rows in CLASSES.items():
        statuses = [at_end[f'cells_{k}']['health'] for k in rows]
        assert end['groups'][host]['health'] == {status: statuses.count(status) for status in set(statuses)}


def test_the_text_has_the_outcomes_the_groups_and_with_events_their_counts(cells, capsys):
    code, out, err = run(capsys, cells)
    assert code == 0 and err == ''
    flat = flat_report(cells)
    for item in flat['outcomes'].values():
        assert item['label'] in out
    assert '  groups of rows:' in out
    for host in CLASSES:
        assert f'    {host}: 3 rows of cells' in out
    assert 'times in' not in out
    code, out, _ = run(capsys, cells, '--events', '--rows', 'cells_4')
    assert code == 0
    # The events of the row that is named, each with its time, as the flat report has them.
    for entry in flat['trace']:
        if entry['rule'].startswith('cells_4.') and entry['outcome'] is not None:
            assert f'({entry["event"]})' in out
    assert 'cells_5.' not in out
    # Each group with how often each of its events happened: three cells in each. The events of a
    # group are below its own line only.
    for host in CLASSES:
        assert f'      {host}.open (done): 3 times in 3 rows, from ' in out
        assert out.count(f'      {host}.open (done)') == 1
    first, second = (out.index(f'    {host}: 3 rows of cells') for host in CLASSES)
    assert first < out.index('      cells_1.open (done)') < second < out.index('      cells_2.open (done)')


def test_a_value_of_an_input_runs_a_table_model_with_each_row_written_out(cells, capsys):
    """A value of an input, an option and an edit document are not for the groups of a table yet.
    With one of them the model runs as every model does, with each row written out, and a note
    says so. The definition is the study of the flat model with that value; the value matters: the
    cell that leaks more seeps more."""
    model = load_scenario(cells / 'model.scn')
    edited = sample_result(evaluate_study(model, edits_for(model, {'set': {'cells.1.leak': 0.1}})))
    (flat,) = edited['runs'].values()
    code, out, err = run(capsys, cells, '--set', 'cells.1.leak=0.1', '--json')
    assert code == 0
    # The note is no part of the document: it goes to the standard error.
    assert err.startswith('note: this model runs with each row of its table written out: --set ')
    (shown,) = json.loads(out)['runs'].values()
    assert 'groups' not in shown and 'group_events' not in shown
    final = shown['reporting_points']['final']['values']
    assert final == pytest.approx(flat['reporting_points']['final']['values'], rel=1e-12)
    seeped = next(name for name, item in flat['outcomes'].items() if 'seeps' in item['label'])
    assert final[seeped] > flat_report(cells)['reporting_points']['final']['values'][seeped]
    # In the text, the note is the first line, and the groups are not there.
    code, out, err = run(capsys, cells, '--set', 'cells.1.leak=0.1')
    assert code == 0 and err == ''
    assert out.startswith('note: this model runs with each row of its table written out: --set ')
    assert 'groups of rows' not in out


@pytest.mark.parametrize(
    'more, message',
    [
        (['--rows', 'cells_9'], '--rows: cells_9 is no row of a table of this model'),
        # The rows are those of the groups: a run with a value has no groups.
        (
            ['--rows', 'cells_1', '--set', 'cells.1.leak=0.1'],
            'with --set, the model runs with each row written out',
        ),
    ],
)
def test_rows_that_the_run_cannot_give_are_refused_by_name(cells, capsys, more, message):
    code, _, err = run(capsys, cells, *more)
    assert code == 2 and message in err


def test_a_table_that_the_hybrid_core_does_not_hold_runs_with_each_row_written_out(tmp_path, capsys):
    """A template that reads a list over its own table is outside the hybrid core. The model runs as
    any model does, from its flat structure, and a note says so."""
    folder = tmp_path / 'SC98'
    folder.mkdir()
    (folder / 'model.scn').write_text(SELF_LIST, encoding='utf-8')
    (folder / 'cells.csv').write_text('start: fraction @fixture\n0.05\n0.1\n0.2\n', encoding='utf-8')
    code, out, _ = run(capsys, folder)
    assert code == 0
    assert out.startswith('note: this model runs with each row of its table written out')
    assert 'groups of rows' not in out
    code, _, err = run(capsys, folder, '--rows', 'cells_1')
    assert code == 2 and '--rows names rows of a table that the model runs by group' in err
