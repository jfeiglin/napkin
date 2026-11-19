"""`napkin compile`: the diagnostics of a model with their places, or a summary of its program."""

from __future__ import annotations

from napkin.model.compile import load_scenario
from tests.commands.call import TANK, UNITS, napkin, package


def test_compile_reports_a_diagnostic_with_its_place(tmp_path, capsys):
    """The flow drains `tank.wate`, which the tank does not have: the refusal is at the flow, the
    8th line of the file, whose declaration starts in the 5th column."""
    model = package(tmp_path / 'tank', TANK.replace('tank.water -> SINK', 'tank.wate -> SINK'), UNITS)
    found = napkin(capsys, 'compile', model)
    assert found.code == 1
    assert found.out == ''
    assert found.err.splitlines() == [
        f'{model / "model.scn"}:8:5: error: tank.wate is no stored number of tank [flow_end]'
    ]
    as_json = napkin(capsys, 'compile', model, '--json')
    assert as_json.code == 1
    (problem,) = as_json.doc['diagnostics']
    assert (problem['file'], problem['line'], problem['column'], problem['code']) == (
        str(model / 'model.scn'),
        8,
        5,
        'flow_end',
    )


def test_compile_summarizes_the_program_of_the_tank(tmp_path, capsys):
    model = package(tmp_path / 'tank', TANK, UNITS)
    found = napkin(capsys, 'compile', model)
    assert found.code == 0, found.err
    lines = found.out.splitlines()
    assert lines[:-1] == [
        f'{model / "model.scn"}: Tank',
        '  run:           median, to 4 h, steps of at most 1 h',
        '  entities:      tank, clinic',
        '  stores:        tank.water',
        '  flows:         clinic.delivery: tank.water -> SINK',
        '  units:         L, L/h',
    ]
    # The hash that an edit document names: the model's own.
    assert lines[-1] == f'  model hash:    {load_scenario(model / "model.scn").model_hash}'
    doc = napkin(capsys, 'compile', model, '--json').doc
    assert (doc['model_hash'], doc['runs']) == (load_scenario(model / 'model.scn').model_hash, [])
    assert doc['stores'] == [{'path': 'tank.water', 'unit': 'L'}]
    assert doc['flows'] == [
        {'path': 'clinic.delivery', 'source': 'tank.water', 'sink': 'SINK', 'unit': 'L/h'}
    ]
    assert (doc['horizon'], doc['inputs'], doc['diagnostics']) == (4, [], [])


def test_a_status_display_compiles(tmp_path, capsys):
    """A status display, which stage C brings, compiles with the entity that shows it."""
    model = package(tmp_path / 'tank', TANK + '\nlamp:\n    status ok\n        "Fine."\n', UNITS)
    found = napkin(capsys, 'compile', model)
    assert found.code == 0, found.err
    assert '  entities:      tank, clinic, lamp' in found.out.splitlines()


def test_a_report_of_the_setup_is_a_warning_and_refuses_nothing(tmp_path, capsys):
    """Two rows of a keyed view that `.at(...)` reads have one key (spec, "Collections, keys and
    projections"): setup reports it at the row that wins, the second row of the table, and the model
    still compiles."""
    text = """\
scenario "Readings"
    horizon 4 h

Reading:
    input hour: h = 0
    input factor = 1

readings: Reading from "readings.csv"

factor_now = formula(Reading.instances.by(hour).at(t).factor)
"""
    model = package(tmp_path / 'readings', text, UNITS)
    (model / 'readings.csv').write_text('id,hour: h,factor\nmorning,0,2\nnoon,0,3\n', encoding='utf-8')
    found = napkin(capsys, 'compile', model)
    assert found.code == 0
    (line,) = found.err.splitlines()
    assert line.startswith(f'{model / "readings.csv"}:3: warning: ')
    assert line.endswith('[equal_keys]')
