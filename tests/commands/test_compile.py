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
        {'path': 'clinic.delivery', 'kind': 'directed', 'source': 'tank.water', 'sink': 'SINK', 'unit': 'L/h'}
    ]
    assert (doc['horizon'], doc['inputs'], doc['diagnostics']) == (4, [], [])


LINKED = """\
scenario "Links"
    horizon 2 h

Tank:
    water: L = 4 L
    next: Tank

east: Tank
    next = west
west: Tank
    next = east
    water = 6 L

tanks = Tank.instances
total = formula(sum(tanks.water))
"""


def test_compile_summarizes_every_kind_of_value_a_links_and_a_collections_included(tmp_path, capsys):
    """Every kind of value of a program has its group in the summary (`compile.GROUPS` holds each of
    `parts.KINDS`), so a model with a link or a collection compiles: it raised a KeyError on the
    first link."""
    from napkin.commands.compile import GROUPS
    from napkin.program.parts import KINDS

    assert {kind for kind, _ in GROUPS} == set(KINDS)
    model = package(tmp_path / 'links', LINKED, UNITS)
    found = napkin(capsys, 'compile', model)
    assert found.code == 0, found.err
    assert '  links:         east.next, west.next' in found.out.splitlines()
    assert '  collections:   tanks' in found.out.splitlines()
    doc = napkin(capsys, 'compile', model, '--json').doc
    assert doc['links'] == [
        {'path': 'east.next', 'unit': '', 'template': 'Tank'},
        {'path': 'west.next', 'unit': '', 'template': 'Tank'},
    ]
    assert doc['collections'] == [{'path': 'tanks', 'unit': '', 'template': 'Tank'}]


FLOWS = """\
scenario "Flows"
    horizon 2 h

west:
    water: L = 10 L in [0 L,]
east:
    water: L = 0 L in [0 L,]
site:
    work: L = 100 L in [0 L,]
    done: L = 0 L in [0 L,]
    parts: L = 10 L in [0 L,]
    used: L = 0 L in [0 L,]
    flow link: west.water <-> east.water
        request = 1 L/h
    flow restore:
        flow labor: this.work -> this.done
            request = 4 L/h
        flow spend: this.parts -> this.used
            request = 8 L/h
    flow drain: west.water -> SINK
        request = 1 L/h
"""


def test_compile_summarizes_each_kind_of_flow_with_its_ends(tmp_path, capsys):
    """Spec, "Flows and algebraic solvers": a directed flow has a source and a sink, a reversible
    route joins two stores with one signed rate, and a flow with several legs has the ends of each
    leg. The summary writes each kind as the model does, `->` or `<->`, and each leg of a flow with
    legs by its own path (`site.restore.labor`), the path a caller reads its rate by; the JSON gives
    each flow its kind. A flow with legs raised an AttributeError (it has no ends of its own), and a
    route was written as a directed flow."""
    model = package(tmp_path / 'flows', FLOWS, UNITS)
    found = napkin(capsys, 'compile', model)
    assert found.code == 0, found.err
    assert (
        '  flows:         '
        + ', '.join(
            [
                'site.link: west.water <-> east.water',
                'site.restore.labor: site.work -> site.done',
                'site.restore.spend: site.parts -> site.used',
                'site.drain: west.water -> SINK',
            ]
        )
        in found.out.splitlines()
    )
    doc = napkin(capsys, 'compile', model, '--json').doc
    assert doc['flows'] == [
        {
            'path': 'site.link',
            'kind': 'reversible',
            'source': 'west.water',
            'sink': 'east.water',
            'unit': 'L/h',
        },
        {
            'path': 'site.restore',
            'kind': 'legs',
            'legs': [
                {'path': 'site.restore.labor', 'source': 'site.work', 'sink': 'site.done', 'unit': 'L/h'},
                {'path': 'site.restore.spend', 'source': 'site.parts', 'sink': 'site.used', 'unit': 'L/h'},
            ],
        },
        {'path': 'site.drain', 'kind': 'directed', 'source': 'west.water', 'sink': 'SINK', 'unit': 'L/h'},
    ]


def test_compile_summarizes_the_package_of_every_construct(tmp_path, capsys):
    """The acceptance package that holds every construct of the language (`tests/acceptance`) compiles
    with its summary, as `napkin run` runs it: its flow with legs crashed the summary."""
    from tests.acceptance.test_every_construct import MAIN, PARTS, PLACES
    from tests.acceptance.test_every_construct import UNITS as EVERY

    model = package(tmp_path / 'every', MAIN, EVERY)
    (model / 'parts.scn').write_text(PARTS, encoding='utf-8')
    (model / 'places.csv').write_text(PLACES, encoding='utf-8')
    for argv in ((), ('--json',)):
        found = napkin(capsys, 'compile', model, *argv)
        assert found.code == 0, found.err
    assert any(flow['kind'] == 'legs' for flow in found.doc['flows'])


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
