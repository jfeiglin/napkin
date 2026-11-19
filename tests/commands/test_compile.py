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
    input hour: h = 0  @log
    input factor = 1  @log

readings: Reading from "readings.csv"

factor_now = formula(Reading.instances.by(hour).at(t).factor)

record log: source "The readings of a test."
"""
    model = package(tmp_path / 'readings', text, UNITS)
    (model / 'readings.csv').write_text(
        'id,hour: h @log,factor @log\nmorning,0,2\nnoon,0,3\n', encoding='utf-8'
    )
    found = napkin(capsys, 'compile', model)
    assert found.code == 0
    (line,) = found.err.splitlines()
    assert line.startswith(f'{model / "readings.csv"}:3: warning: ')
    assert line.endswith('[equal_keys]')


# ---- the evidence rule: the parts that rest on no record (napkin.model.support) --------------------

# The tank of `call.TANK` with a second store: neither cites a record, and a flow needs none.
UNRECORDED = TANK.replace(
    '    readonly water: L = 8 in [0, 20]\n', '    readonly water: L = 8 in [0, 20]\n    spare: L = 2 L\n'
)
MISSING = 'a stored value rests on no record: cite one (@name) or write one under it [no_record]'


def test_compile_lists_each_part_that_rests_on_no_record_at_its_line(tmp_path, capsys):
    """`napkin compile` is the checking command: a warning for each store, at its line, and the model
    compiles; `--json` keeps each warning with its place."""
    model = package(tmp_path / 'tank', UNRECORDED, UNITS)
    found = napkin(capsys, 'compile', model)
    assert found.code == 0
    assert found.err.splitlines() == [
        f'{model / "model.scn"}:5: warning: tank.water: {MISSING}',
        f'{model / "model.scn"}:6: warning: tank.spare: {MISSING}',
    ]
    warnings = napkin(capsys, 'compile', model, '--json').doc['warnings']
    assert [(item['code'], item['file'], item['line']) for item in warnings] == [
        ('no_record', str(model / 'model.scn'), 5),
        ('no_record', str(model / 'model.scn'), 6),
    ]


def test_another_command_counts_the_parts_that_rest_on_no_record_in_one_line(tmp_path, capsys):
    """Every other command writes one line that counts them, so a model being explored gets one line
    of noise; its `--json` keeps each warning with its place."""
    model = package(tmp_path / 'tank', UNRECORDED, UNITS)
    found = napkin(capsys, 'run', model)
    assert found.code == 0
    assert found.err.splitlines() == [
        'warning: 2 values have no record (napkin compile lists them) [no_record]'
    ]
    warnings = napkin(capsys, 'run', model, '--json').doc['warnings']
    assert [(item['code'], item['line']) for item in warnings] == [('no_record', 5), ('no_record', 6)]
