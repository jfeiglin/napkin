"""The spec's worked models as programs (`examples.py`).

Each example builds, and its program passes `finish()`. Every row of the spec's table "Acceptance
cases" has an example, and every example says what it expects in terms that the program can answer:
each value names a member, the root or an occurrence of an event of the program, each trace names
a part that the program has, and each configuration names inputs of the program.
"""

from dataclasses import fields, is_dataclass

import pytest

from napkin.program import parts as p
from napkin.program.record import KINDS
from napkin.program.refs import Draw, Expr

from .examples import EXAMPLES, ROWS, At, Fails, Traced

# The rows of the spec's table "Acceptance cases" (spec.md, "Acceptance cases").
ACCEPTANCE_ROWS = 32


@pytest.fixture(scope='module')
def built():
    return {name: function() for name, function in EXAMPLES.items()}


def origins(value, found):
    """Each origin of a program, and each site of a draw."""
    if isinstance(value, Expr):
        for _, read in value.reads:
            if isinstance(read, Draw):
                found.append(read.site)
        return
    if isinstance(value, tuple):
        for each in value:
            origins(each, found)
    elif is_dataclass(value) and not isinstance(value, type):
        for item in fields(value):
            if item.name == 'origin':
                found.append(value.origin)
            else:
                origins(getattr(value, item.name), found)


def test_every_acceptance_row_has_an_example():
    assert len(ROWS) == ACCEPTANCE_ROWS
    named = [name for names in ROWS.values() for name in names]
    assert sorted(set(named)) == sorted(named)
    assert set(named) <= set(EXAMPLES)


@pytest.mark.parametrize('name', sorted(EXAMPLES))
def test_an_example_builds_and_finishes(name, built):
    example = built[name]
    assert example.name == name
    assert isinstance(example.program, p.Program)
    assert example.expected
    assert example.configuration.request.horizon >= max(
        (each.t for each in example.expected if isinstance(each, (At, Fails)) and each.t is not None),
        default=0,
    )
    assert sum(isinstance(each, Fails) for each in example.expected) <= 1


@pytest.mark.parametrize('name', sorted(EXAMPLES))
def test_the_origins_of_an_example_are_its_own(name, built):
    """Each part of a program has one origin, and no two parts share one."""
    found = []
    origins(built[name].program, found)
    assert all(found)
    assert len(found) == len(set(found)), sorted(each for each in found if found.count(each) > 1)


def owners(program):
    """Each owner that a key can name: the members, the root, and the occurrences of each event
    of each member, as `member.event#n`."""
    found = {'': None}
    for template in program.templates:
        for member in template.members:
            found[member.id] = template
            for event in template.events:
                found[f'{member.id}.{event.name}'] = event
    return found


@pytest.mark.parametrize('name', sorted(EXAMPLES))
def test_what_an_example_expects_is_in_its_program(name, built):
    example = built[name]
    program = example.program
    known = owners(program)
    parts = []
    origins(program, parts)
    for expected in example.expected:
        if isinstance(expected, At):
            owner, _, number = expected.key.owner.partition('#')
            assert owner in known, expected
            assert (number == '') == (
                owner == '' or owner in {m.id for t in program.templates for m in t.members}
            )
            assert expected.key.steps
        elif isinstance(expected, Traced):
            assert expected.kind in KINDS
            assert expected.part in parts, expected
            assert expected.rounds is None or len(expected.rounds) == len(expected.times)
            assert list(expected.times) == sorted(expected.times)
        else:
            assert isinstance(expected, Fails) and expected.message


@pytest.mark.parametrize('name', sorted(EXAMPLES))
def test_the_configuration_of_an_example_names_the_program(name, built):
    example = built[name]
    program, configuration = example.program, example.configuration
    members = {m.id: t for t in program.templates for m in t.members}
    for given in configuration.inputs:
        template = members[given.member]
        assert template.part(given.name).kind == p.INPUT
