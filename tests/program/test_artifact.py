"""The compiled program as a file (`napkin/program/artifact.py`) and the reading of canonical bytes
(`canonical.decode`).

A program saved and loaded is equal to the one saved, with the same bytes and the same nodes; so is
a configuration. The header names the format and the language, and a loader refuses another format,
another version of either, and damaged bytes, each by its code and with a message that names what
it found.
"""

import hashlib

import pytest

from napkin.core import expr as nodes
from napkin.program.artifact import (
    EXECUTABLE,
    FORMAT_VERSION,
    LANGUAGE_VERSION,
    RECORDS,
    Artifact,
    ArtifactError,
    Evidence,
    Location,
    SideTable,
    load,
    loads,
    origins,
    value_of,
)
from napkin.program.canonical import Malformed, decode, program_bytes, value_bytes

from .examples import EXAMPLES, grinder_refill

TABLE = SideTable(
    (
        Location('grinder', 'template', 'grinder', 'grinder.scn', 1, 1),
        Location(
            'grinder.beans',
            'value',
            'beans',
            'grinder.scn',
            2,
            5,
            'Beans in the hopper',
            (Evidence('weighed', 'source', 'Weighed by hand', (('assumption', 'A-SCALE'),), (('C-1', 'mass'),)),),
        ),
        Location('grinder.refill.step[0]', 'stage', '', 'grinder.scn', 5, 9),
    )
)


@pytest.mark.parametrize('name', sorted(EXAMPLES))
def test_a_saved_program_loads_equal_with_its_bytes(name):
    example = EXAMPLES[name]()
    loaded = loads(Artifact(example.program, TABLE).data())
    assert loaded.program == example.program
    assert program_bytes(loaded.program) == program_bytes(example.program)
    assert loaded.table == TABLE
    assert value_of(value_bytes(example.configuration)) == example.configuration


def test_a_loaded_program_holds_the_nodes_themselves():
    """A node of `napkin/core/expr` is made once, so the loaded program's nodes are the very objects
    of the program that was saved."""
    program = grinder_refill().program
    loaded = loads(Artifact(program).data()).program
    original = program.templates[0].values[1].init.expr.node
    assert loaded.templates[0].values[1].init.expr.node is original


def test_the_header_names_the_format_the_language_and_the_digest():
    program = grinder_refill().program
    data = Artifact(program).data()
    digest = hashlib.sha256(program_bytes(program)).hexdigest()
    head = b'napkin program %d\nlanguage %s\nprogram %d %s\n' % (
        FORMAT_VERSION,
        LANGUAGE_VERSION.encode(),
        len(program_bytes(program)),
        digest.encode(),
    )
    assert data.startswith(head)
    assert data[len(head) : len(head) + len(program_bytes(program))] == program_bytes(program)
    assert Artifact(program).digest == digest


def test_a_file_round_trip(tmp_path):
    program = grinder_refill().program
    Artifact(program, TABLE).save(tmp_path / 'grinder.napkin')
    loaded = load(tmp_path / 'grinder.napkin')
    assert (loaded.program, loaded.table) == (program, TABLE)


def refused(data):
    with pytest.raises(ArtifactError) as caught:
        loads(data)
    return caught.value


def test_another_format_is_refused_by_name():
    found = refused(b'{"model_hash": "abc", "set": {}}')
    assert found.code == 'not_a_program'
    assert '"napkin program"' in found.message and '{"model_hash"' in found.message


def test_another_version_of_the_format_is_refused_by_name():
    data = Artifact(grinder_refill().program).data().replace(b'napkin program 1\n', b'napkin program 2\n', 1)
    found = refused(data)
    assert found.code == 'format_version'
    assert "format '2'" in found.message and f'reads format {FORMAT_VERSION}' in found.message


def test_another_version_of_the_language_is_refused_by_name():
    data = Artifact(grinder_refill().program).data()
    found = refused(data.replace(b'language %s\n' % LANGUAGE_VERSION.encode(), b'language 9.9.9\n', 1))
    assert found.code == 'language_version'
    assert 'the language 9.9.9' in found.message and f'runs the language {LANGUAGE_VERSION}' in found.message


def with_program(data, program):
    """The bytes of a file with other program bytes, under a line with their right size and digest."""
    head, _, rest = data.partition(b'\nprogram ')
    line, _, rest = rest.partition(b'\n')
    size = int(line.split(b' ')[0])
    table = rest[size:]
    line = b'%d %s' % (len(program), hashlib.sha256(program).hexdigest().encode())
    return head + b'\nprogram ' + line + b'\n' + program + table


def test_damaged_bytes_are_refused():
    data = Artifact(grinder_refill().program, TABLE).data()
    program = program_bytes(grinder_refill().program)
    flipped = data.replace(b's5:beans', b's5:BEANS', 1)
    cases = {
        'a byte of the program': flipped,
        'a cut file': data[: len(data) // 2],
        'bytes after the table': data + b'\n',
        'no language line': data.replace(b'language ', b'tongue ', 1),
        # A record of another napkin, whose field `readonly` has another name: the digest holds.
        'a field of another napkin': with_program(data, program.replace(b's8:readonly', b's8:readable')),
        'a record of no napkin': with_program(data, program.replace(b'R7:Program', b'R7:Process', 1)),
    }
    for what, bad in cases.items():
        found = refused(bad)
        assert found.code == 'damaged', what
    assert 'the field readonly here' in refused(cases['a field of another napkin']).message
    assert 'Process' in refused(cases['a record of no napkin']).message


def test_decode_reads_each_kind_of_value_back():
    """Each tag of the encoding: none, yes/no, an int, a float bit for bit, a fraction, a text, a
    tuple, a node and a record."""
    from fractions import Fraction

    from napkin.program.record import Key

    node = nodes.binary('add', nodes.ref('a'), nodes.const(-0.0))
    values = (None, True, False, -12, 0.1, -0.0, Fraction(-3, 7), 'é\n', (), (1, ('x',)), node, Key('', ('t',)))
    found = decode(value_bytes(values), RECORDS)
    assert found == values
    assert [type(item) for item in found] == [type(item) for item in values]
    assert found[10] is node
    assert str(found[5]) == '-0.0'


def test_decode_refuses_what_is_no_value():
    for data in (b'', b'i12', b'X', b's9:short', b'(2:i1;)', b'R3:Key{}', b'i1;i2;'):
        with pytest.raises(Malformed):
            decode(data, RECORDS)


def test_the_side_table_finds_a_location_by_its_origin():
    assert TABLE.location('grinder.beans').label == 'Beans in the hopper'
    assert [location.origin for location in TABLE.executable()] == ['grinder.refill.step[0]']
    with pytest.raises(KeyError):
        TABLE.location('grinder.missing')


def test_origins_find_each_part_of_a_program():
    """The grinder of the spec: its template, its two values, its event with its parameter, its
    stage and its statement, and the setup's start, each by the origin that `build` gives it."""
    found = origins(grinder_refill().program)
    assert list(found) == [
        'grinder',
        'grinder.beans',
        'grinder.low_on_beans',
        'grinder.refill',
        'grinder.refill.amount',
        'grinder.refill.step[0]',
        'grinder.refill.step[0].do[0]',
        'setup[0]',
    ]
    assert {type(part).__name__ for part in found.values()} >= {'Event', 'After', 'Assign', 'Start'}
    assert set(EXECUTABLE) >= {'event', 'stage', 'assign', 'start'}
