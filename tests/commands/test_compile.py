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
    """An enum member comes with S4: the front end names the part and the slice."""
    model = package(tmp_path / 'gate', TANK.replace('clinic:', 'gate:\n    state = OPEN\n\nclinic:'), UNITS)
    found = napkin(capsys, 'compile', model)
    assert found.code == 1
    assert '[later_slice]' in found.err
    assert '(S4)' in found.err
