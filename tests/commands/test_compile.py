"""`napkin compile`: the diagnostics of a model with their places, or a summary of its program."""

from __future__ import annotations

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
    assert found.out.splitlines() == [
        f'{model / "model.scn"}: Tank',
        '  run:           median, to 4 h, steps of at most 1 h',
        '  entities:      tank, clinic',
        '  stores:        tank.water',
        '  flows:         clinic.delivery: tank.water -> SINK',
        '  units:         L, L/h',
    ]
    doc = napkin(capsys, 'compile', model, '--json').doc
    assert doc['stores'] == [{'path': 'tank.water', 'unit': 'L'}]
    assert doc['flows'] == [
        {'path': 'clinic.delivery', 'source': 'tank.water', 'sink': 'SINK', 'unit': 'L/h'}
    ]
    assert (doc['horizon'], doc['inputs'], doc['diagnostics']) == (4, [], [])


def test_a_part_of_a_later_slice_is_refused_by_name(tmp_path, capsys):
    """A solver comes with S5: the front end names the part and the slice."""
    solver = 'plan:\n    split: L = 1\n    s = solver:\n        solve_for:\n            this.split\n\nclinic:'
    model = package(tmp_path / 'plan', TANK.replace('clinic:', solver), UNITS)
    found = napkin(capsys, 'compile', model)
    assert found.code == 1
    assert '[later_slice]' in found.err
    assert '(S5)' in found.err


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
