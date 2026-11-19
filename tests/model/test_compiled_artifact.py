"""The compiled program with its side table (`Compiled.table`, `lowering.side_table`), saved and run by
a fresh process.

The side table places each part of the program in its file, at its line and column, with its label
and its evidence; it is outside the program's identity, so a label, a record or a moved line leaves
the program's bytes and the model's hash. A program compiled, saved, and loaded by a fresh process
that never imports the parser has the same bytes and runs to the same record. Each line and column
below is counted by hand in the text.
"""

import json
import pickle
import subprocess
import sys
from dataclasses import fields, is_dataclass
from pathlib import Path

from napkin.engine import run
from napkin.model.compile import compile_text, load_scenario
from napkin.program.artifact import Evidence, Location
from napkin.program.canonical import program_bytes, value_bytes
from napkin.program.config import SAMPLED, Configuration, Request
from tests.program.examples import UNITS

ROOT = Path(__file__).resolve().parents[2]

GRINDER = """\
record weighed: source "The hopper, weighed by hand."
grinder:
    beans: g = 8 g  @weighed
        "Beans in the hopper"
        @assumption "Full at the start"
    refill = event(amount: g):
        "Refill the hopper"
        after 0.5 h:
            this.beans += amount
grinder.refill.start(50 g)
"""


def test_the_side_table_places_each_part_with_its_label_and_evidence():
    table = compile_text(GRINDER, UNITS, file='grinder.scn').table
    assert table.location('grinder.beans') == Location(
        'grinder.beans',
        'value',
        'beans',
        'grinder.scn',
        3,
        5,
        'Beans in the hopper',
        (
            Evidence('weighed', 'source', 'The hopper, weighed by hand.'),
            Evidence('', 'assumption', 'Full at the start'),
        ),
    )
    found = {
        location.origin: (location.kind, location.line, location.column, location.label)
        for location in table.executable()
    }
    assert found == {
        'grinder.refill': ('event', 6, 5, 'Refill the hopper'),
        'grinder.refill.step[0]': ('stage', 8, 9, None),
        'grinder.refill.step[0].do[0]': ('assign', 9, 13, None),
        'setup[0]': ('start', 10, 1, None),
    }
    assert {location.file for location in table.locations} == {'grinder.scn'}


def test_a_label_a_record_or_a_moved_line_moves_no_key():
    edited = '# A comment that moves every line.\n\n' + GRINDER.replace(
        'Beans in the hopper', 'Coffee beans'
    ).replace('weighed by hand.', 'weighed on a scale.')
    first, second = compile_text(GRINDER, UNITS), compile_text(edited, UNITS)
    assert program_bytes(first.program) == program_bytes(second.program)
    assert first.artifact().digest == second.artifact().digest
    assert first.model_hash == second.model_hash
    before, after = first.table.location('grinder.beans'), second.table.location('grinder.beans')
    assert (before.label, after.label) == ('Beans in the hopper', 'Coffee beans')
    assert (before.line, after.line) == (3, 5)
    assert after.evidence[0].explanation == 'The hopper, weighed on a scale.'


# Two tanks of one template, the first with its title, and a pump written once with its own.
TITLED = """\
Tank:
    water: L = 10 L
first: Tank
    "The tank by the gate."
    title "Gate tank"
second: Tank
pump:
    title "Main pump"
    rate: L/h = 2 L/h
"""


def test_a_title_is_kept_with_the_labels_in_the_side_table():
    """A member written by hand has a location of its own, with its title (PLAN, change 19); an entity
    written once has its title at its template's location; a member with none has no title."""
    table = compile_text(TITLED, UNITS, file='tanks.scn').table
    assert table.location('first') == Location(
        'first', 'member', 'first', 'tanks.scn', 3, 1, 'The tank by the gate.', (), 'Gate tank'
    )
    assert table.location('pump').kind == 'template'
    assert [table.title(name) for name in ('first', 'second', 'pump', 'Tank')] == [
        'Gate tank',
        None,
        'Main pump',
        None,
    ]
    assert table.title('nothing') is None and 'first' not in [item.origin for item in table.executable()]


def test_a_title_edit_moves_no_key():
    first = compile_text(TITLED, UNITS)
    second = compile_text(TITLED.replace('Gate tank', 'Tank at the gate'), UNITS)
    assert program_bytes(first.program) == program_bytes(second.program)
    assert first.artifact().digest == second.artifact().digest
    assert first.model_hash == second.model_hash
    assert (first.table.title('first'), second.table.title('first')) == ('Gate tank', 'Tank at the gate')


def test_a_package_places_each_part_in_its_own_file(tmp_path):
    folder = tmp_path / 'tanks'
    files = {
        'model.scn': 'scenario "Tanks"\n    horizon 4 h\nuse common\n\npump:\n    rate: L/h = 2 L/h\n',
        'common.scn': 'tank:\n    water: L = 10 L\n    drain = event():\n        after 1 h:\n'
        '            this.water -= 1 L\n',
    }
    for name, text in files.items():
        (folder / name).parent.mkdir(parents=True, exist_ok=True)
        (folder / name).write_text(text, encoding='utf-8')
    (folder / 'units.json').write_text(json.dumps({'L': {'dimensions': {'volume': 1}, 'scale': 1}}))
    table = load_scenario(folder / 'model.scn').table
    placed = {
        origin: (Path(table.location(origin).file).name, table.location(origin).line)
        for origin in ('tank.water', 'tank.drain.step[0].do[0]', 'pump.rate')
    }
    assert placed == {
        'tank.water': ('common.scn', 2),
        'tank.drain.step[0].do[0]': ('common.scn', 5),
        'pump.rate': ('model.scn', 6),
    }


# A tank drained at 3 L/h; when it falls to 4 L a trigger starts a refill of 5 L after a drawn delay.
TANK = """\
tank:
    water: L = 10 L in [0 L, 20 L]
    refill = event():
        after uniform(1 h, 2 h).draw():
            this.water += 5 L
    watch = event():
        when this.water <= 4 L:
            this.watch.start()
        after 0 h:
            this.refill.start()
clinic:
    flow delivery: tank.water -> SINK
        request = 3 L/h
"""

# The fresh process: it loads the program and the configuration, runs them, and gives back the
# program's bytes, the modules of the front end that it imported, and the record.
FRESH = """\
import pickle, sys
from napkin.engine import run
from napkin.program.artifact import load, value_of
from napkin.program.canonical import program_bytes

artifact = load(sys.argv[1])
with open(sys.argv[2], 'rb') as file:
    configuration = value_of(file.read())
record = run(artifact.program, configuration)
front = sorted(name for name in sys.modules if name.startswith('napkin.model'))
with open(sys.argv[3], 'wb') as file:
    pickle.dump((program_bytes(artifact.program), front, record), file)
"""


def plain(value):
    """A record as canonical data: each record its class's name and fields, each number of NumPy a
    number of Python with the same bits, so two records compare bit for bit."""
    if is_dataclass(value):
        return (type(value).__qualname__, *(plain(getattr(value, item.name)) for item in fields(value)))
    if isinstance(value, tuple):
        return tuple(plain(item) for item in value)
    if type(value).__module__ == 'numpy':
        return value.item()
    return value


def test_a_fresh_process_loads_the_program_and_runs_it_to_the_same_record(tmp_path):
    compiled = compile_text(TANK, UNITS, file='tank.scn')
    configuration = Configuration(Request(10), mode=SAMPLED, seed=7)
    compiled.artifact().save(tmp_path / 'tank.napkin')
    (tmp_path / 'configuration').write_bytes(value_bytes(configuration))
    subprocess.run(
        [
            sys.executable,
            '-c',
            FRESH,
            *(str(tmp_path / name) for name in ('tank.napkin', 'configuration', 'out')),
        ],
        cwd=ROOT,
        check=True,
        timeout=120,
    )
    with open(tmp_path / 'out', 'rb') as file:
        program, front, record = pickle.load(file)
    assert program == program_bytes(compiled.program)
    assert front == []
    here = run(compiled.program, configuration)
    assert value_bytes(plain(record)) == value_bytes(plain(here))
    # The run is the one the text says: the first refill starts when 10 L falls to 4 L at 3 L/h.
    assert here.entries('fire')[0].t == 2
    assert len(here.entries('draw')) >= 2
