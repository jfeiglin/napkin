"""Initializers of the setup scope (spec, "Flows and algebraic solvers"): `clinic.delivery.request =
3 L/h` at the top level is the same initializer as `request = 3 L/h` under the flow, so the two texts
give one program. A path is initialized once, and the setup scope initializes the parts of entities
written once and the values of members written by hand (`semantic.Resolver.wired`)."""

from __future__ import annotations

import pytest

from napkin.model.compile import compile_text
from napkin.model.language.problems import LanguageError
from napkin.program.canonical import program_bytes

UNITS = {
    'L': {'volume': 1},
    'kg': {'mass': 1},
    'h': {'time': 1},
    'L/h': {'volume': 1, 'time': -1},
    'kg/h': {'mass': 1, 'time': -1},
}

INDENTED = """\
tank:
    readonly water: L = 8 in [0, 20]
        outflow.capacity = 4 L/h

clinic:
    flow delivery: tank.water -> SINK
        capacity = 5 L/h
        request = 3 L/h

west:
    water: L = 10 in [0, 20]

channel:
    flow link: west.water <-> tank.water
        request = -1 L/h

site:
    work: L = 100 in [0,]
    parts: kg = 10 in [0,]
    flow restore:
        flow labor: this.work -> SINK
            request = 4 L/h
        flow spend: this.parts -> SINK
            request = 8 kg/h

Tank:
    input ask: L/h = 1 L/h
    got: L = 0 in [0,]
    flow take: west.water -> this.got
        request = this.ask

a1: Tank
    ask = 2 L/h

a2: Tank
"""

SETUP = """\
tank:
    readonly water: L in [0, 20]

clinic:
    flow delivery: tank.water -> SINK
        capacity = 5 L/h

west:
    water: L = 10 in [0, 20]

channel:
    flow link: west.water <-> tank.water

site:
    work: L = 100 in [0,]
    parts: kg = 10 in [0,]
    flow restore:
        flow labor: this.work -> SINK
        flow spend: this.parts -> SINK

Tank:
    input ask: L/h = 1 L/h
    got: L = 0 in [0,]
    flow take: west.water -> this.got
        request = this.ask

a1: Tank

a2: Tank

tank.water = 8
tank.water.outflow.capacity = 4 L/h
clinic.delivery.request = 3 L/h
channel.link.request = -1 L/h
site.restore.labor.request = 4 L/h
site.restore.spend.request = 8 kg/h
a1.ask = 2 L/h
"""


def compiled(text):
    return compile_text(text, UNITS)


def refused(text):
    with pytest.raises(LanguageError) as caught:
        compiled(text)
    return [(item.code, item.line, item.message) for item in caught.value.problems]


def line_of(text, words):
    return next(k for k, row in enumerate(text.split('\n'), 1) if row.strip().startswith(words))


def test_an_initializer_of_the_setup_scope_is_the_initializer_under_its_declaration():
    """A value of an entity (also a readonly one, which its declaration leaves without one), an
    endpoint's setting, the request of a flow, of a route and of each leg, and a member's own value:
    the two texts give one program. No setup line cites a record, as no initializer under a
    declaration does."""
    assert program_bytes(compiled(SETUP).program) == program_bytes(compiled(INDENTED).program)


@pytest.mark.parametrize(
    ('line', 'first'),
    [
        # By the declaration, by a line under the declaration, by a member's own line.
        ('tank.water = 5 L', 'readonly water'),
        ('tank.water.outflow.capacity = 2 L/h', 'outflow.capacity'),
        ('clinic.delivery.request = 3 L/h', 'request = 3 L/h'),
        ('site.restore.labor.request = 1 L/h', 'request = 4 L/h'),
        ('a1.ask = 3 L/h', 'ask = 2 L/h'),
    ],
)
def test_a_path_that_is_initialized_already_is_an_error_that_names_both_lines(line, first):
    text = INDENTED + '\n' + line + '\n'
    ((code, at, message),) = refused(text)
    assert (code, at) == ('property', line_of(text, line))
    assert f'on line {line_of(text, first)} and on line {at}' in message


def test_two_setup_lines_of_one_path_are_an_error_that_names_both():
    text = SETUP + 'clinic.delivery.request = 2 L/h\n'
    ((code, at, message),) = refused(text)
    assert (code, at) == ('property', len(text.split('\n')) - 1)
    assert f'on line {line_of(text, "clinic.delivery.request = 3")} and on line {at}' in message


def test_a_readonly_value_takes_its_initializer_and_still_refuses_an_assignment():
    """`readonly` bars a direct assignment, in a stage, through any path; an initializer of the setup
    scope is the value's initializer (spec: "the same initializer")."""
    text = SETUP + 'filler:\n    fill = event():\n        after 1 h:\n            tank.water = 10 L\n'
    assert [code for code, _, _ in refused(text)] == ['readonly_write']


@pytest.mark.parametrize(
    ('line', 'code'),
    [
        # A template's parts are its declaration's, and a member gives no setting of its template's parts.
        ('Tank.ask = 3 L/h', 'property'),
        ('a1.take.request = 1 L/h', 'property'),
        # A part that is no value, flow, leg or endpoint setting, and a name of nothing.
        ('clinic.delivery.size = 1', 'property'),
        ('tank.level = 1 L', 'property'),
        ('nothing.water = 1 L', 'unknown_name'),
        # The initializer is checked where it stands, as under its declaration.
        ('a2.ask = 3 kg/h', 'unit'),
    ],
)
def test_what_the_setup_scope_does_not_initialize_is_refused_at_its_line(line, code):
    text = SETUP.replace('channel.link.request = -1 L/h\n', '') + line + '\n'
    found = refused(text)
    assert [(item[0], item[1]) for item in found] == [(code, line_of(text, line))], found


def test_a_row_of_a_table_is_initialized_by_its_cells():
    text = 'Place:\n    input need: L = 1 L\n\nsites: Place from "sites.csv"\n\nsites.clinic.need = 2 L\n'
    with pytest.raises(LanguageError) as caught:
        compile_text(text, UNITS, tables={'sites.csv': 'id,need\nclinic,\n'})
    assert [(item.code, item.line) for item in caught.value.problems] == [('property', 6)]


def test_a_problem_of_the_initializer_is_at_the_setup_line():
    text = SETUP.replace('tank.water = 8\n', 'tank.water = 8 kg\n')
    assert [(code, at) for code, at, _ in refused(text)] == [('unit', line_of(text, 'tank.water = 8 kg'))]
