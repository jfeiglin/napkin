"""Text and builder paths retain exactly the dependencies of a fixed member lookup."""

import pytest

from napkin.model.compile import compile_text
from napkin.model.language.problems import LanguageError
from napkin.program import build as b
from napkin.program.canonical import program_bytes
from napkin.program.check import ProgramError
from napkin.program.refs import Lookup, Named

from .examples import UNITS

BASE = """scenario "Member dependency"
    horizon 1 h
Entry:
    input rank: number = 2
    amount: L = 1 L
first: Entry
middle: Entry
last: Entry
cursor: number = 1
"""


def programs(spelling, lookup):
    def built():
        builder = b.Builder(UNITS)
        entry = builder.template('Entry', b.input_('rank', '', 2), b.value('amount', 'L', 1))
        for name in ('first', 'middle', 'last'):
            builder.member(entry, name)
        builder.root(b.value('cursor', '', 1), b.value('result', 'L', b.formula(lookup(entry).amount)))
        return builder.finish()

    return lambda: compile_text(BASE + f'result = formula({spelling}.amount)\n', UNITS).program, built


@pytest.mark.parametrize(
    ('spelling', 'lookup', 'selected'),
    [
        ('Entry.instances.at(0)', lambda e: e.instances.at(0), 'first'),
        ('Entry.instances.at(1.5)', lambda e: e.instances.at(1.5), 'middle'),
        ('Entry.instances.at(99)', lambda e: e.instances.at(99), 'last'),
        ('<last, first>.at(1)', lambda e: b.literal(b.named('last'), b.named('first')).at(1), 'first'),
        ('<last, middle>.at(0)', lambda e: b.literal(b.named('last'), b.named('middle')).at(0), None),
        ('Entry.instances.at(-1)', lambda e: e.instances.at(-1), None),
        ('Entry.instances.at(cursor)', lambda e: e.instances.at(b.root.cursor), None),
        ('Entry.instances.by(rank).at(2)', lambda e: e.instances.by('rank').at(2), None),
        ('Entry.instances.where(rank > 1).at(0)', lambda e: e.instances.where(b.item.rank > 1).at(0), None),
    ],
)
def test_member_key_dependencies(spelling, lookup, selected):
    text, builder = (make() for make in programs(spelling, lookup))
    for program in (text, builder):
        ((_, path),) = program.root[-1].init.expr.reads
        assert path.steps == ('amount',)
        if selected is None:
            assert isinstance(path.start, Lookup)
        else:
            assert path.start == Named(selected)
    assert program_bytes(text) == program_bytes(builder)


@pytest.mark.parametrize(
    ('spelling', 'lookup'),
    [
        ('<first, first>.at(0)', lambda e: b.literal(b.named('first'), b.named('first')).at(0)),
        ('Entry.instances.at(1 h)', lambda e: e.instances.at(b.q(1, 'h'))),
        ('Entry.instances.at(true)', lambda e: e.instances.at(True)),
    ],
)
def test_invalid_member_reads_are_refused_before_selection(spelling, lookup):
    text, builder = programs(spelling, lookup)
    with pytest.raises(LanguageError):
        text()
    with pytest.raises(ProgramError):
        builder()


def test_fixed_read_initializes_a_member_link():
    text = (
        BASE
        + """Reader:
    neighbor: Entry
reader: Reader
    neighbor = Entry.instances.at(1)
observed = formula(reader.neighbor.amount)
"""
    )
    source = compile_text(text, UNITS).program
    builder = b.Builder(UNITS)
    entry = builder.template('Entry', b.input_('rank', '', 2), b.value('amount', 'L', 1))
    for name in ('first', 'middle', 'last'):
        builder.member(entry, name)
    reader = builder.template('Reader', b.link('neighbor', 'Entry'))
    builder.member(reader, 'reader', neighbor=entry.instances.at(1))
    builder.root(
        b.value('cursor', '', 1), b.value('observed', 'L', b.formula(b.named('reader').neighbor.amount))
    )
    built = builder.finish()
    for program in (source, built):
        assert program.template('Reader').members[0].links == (('neighbor', 1),)
    assert program_bytes(source) == program_bytes(built)
