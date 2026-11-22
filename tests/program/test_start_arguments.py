"""Event signatures apply to expressions in the caller, including readonly fields and flow ends."""

import pytest

from napkin.engine import read, run
from napkin.model.compile import compile_text
from napkin.model.language.problems import LanguageError
from napkin.program import build as b
from napkin.program.check import ProgramError
from napkin.program.config import Configuration, Request

from .examples import UNITS

ENUM = 'enum[OPEN, CLOSED]'


def examples(kind, spelling, expression):
    """The text and builder programs both capture the argument and expose it as gate.seen."""
    initial = {'L': '0 L', 'bool': 'false', ENUM: 'CLOSED'}[kind]
    text = f"""scenario "Event arguments"
    horizon 1 h
OPEN:
    weight: L = 1 L
spare: OPEN
gate:
    readonly amount: L = 8 L
    water: L = 4 L
    state: {ENUM} = CLOSED
    flow fill: SOURCE -> this.water
    seen: {kind} = {initial}
    go = event(arg: {kind}):
        after 0 h:
            this.seen = arg
gate.go.start({spelling})
"""

    def built():
        builder = b.Builder(UNITS)
        opened = builder.template('OPEN', b.value('weight', 'L', 1))
        builder.member(opened, 'spare')
        mode = builder.enum(ENUM, 'OPEN', 'CLOSED')
        param_type = {'L': 'L', 'bool': b.BOOL, ENUM: mode}[kind]
        gate = builder.entity(
            'gate',
            b.value('amount', 'L', 8, readonly=True),
            b.value('water', 'L', 4),
            b.value('state', mode, mode.CLOSED),
            b.flow('fill', b.SOURCE, b.this.water),
            b.value('seen', param_type, {'L': 0, 'bool': False, ENUM: mode.CLOSED}[kind]),
            b.event(
                'go', b.param('arg', param_type), b.after(b.q(0, 'h'), b.assign(b.this.seen, b.local.arg))
            ),
        )
        builder.setup(b.start(gate.go, expression(gate, mode)))
        return builder.finish()

    return lambda: compile_text(text, UNITS).program, built


@pytest.mark.parametrize(
    ('kind', 'spelling', 'expression'),
    [
        ('bool', 'gate.state < gate.state', lambda gate, mode: gate.state < gate.state),
        ('L', 'gate.state * gate.amount', lambda gate, mode: gate.state * gate.amount),
        ('L', 'gate.fill.source', lambda gate, mode: gate.fill.source),
        ('bool', 'gate.go == gate.go', lambda gate, mode: gate.go == gate.go),
        ('bool', 'any(gate.go.occurrences.started)', lambda gate, mode: b.fany(gate.go.occurrences.started)),
    ],
)
def test_both_authors_refuse_invalid_argument_expressions(kind, spelling, expression):
    text, builder = examples(kind, spelling, expression)
    with pytest.raises(LanguageError):
        text()
    with pytest.raises(ProgramError):
        builder()


@pytest.mark.parametrize(
    ('kind', 'spelling', 'expression', 'expected'),
    [
        ('L', 'gate.fill.sink', lambda gate, mode: gate.fill.sink, 4),
        ('L', 'gate.amount / 2', lambda gate, mode: gate.amount / 2, 4),
        ('bool', 'gate.state == CLOSED', lambda gate, mode: gate.state == mode.CLOSED, True),
        (
            ENUM,
            'OPEN if gate.state == CLOSED else gate.state',
            lambda gate, mode: b.ifelse(gate.state == mode.CLOSED, mode.OPEN, gate.state),
            'OPEN',
        ),
    ],
)
def test_both_authors_capture_the_argument_value(kind, spelling, expression, expected):
    for make in examples(kind, spelling, expression):
        program = make()
        record = run(program, Configuration(Request(1)))
        seen, readonly = read(record, program, ['gate.seen', 'gate.amount'], [1])
        assert seen.values == (expected,)
        assert readonly.values == (8,)
