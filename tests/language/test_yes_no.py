"""Yes/no inputs and states in the front end, ported from the dormant
`tests/engine/test_binary_controls.py` (its front-end cases): a yes/no value is `true` or `false` in
the file, in a stage and in a condition, and never a number between, a unit, a range or a stock.
Its edit cases (an edit that sets a yes/no input to 0.5, the values that a run resolves) wait for the
run configuration of S6; its case that pinned the old 0/1 quantity has no form here, since the program
has a yes/no type."""

import textwrap

import pytest

from napkin.model.compile import compile_text
from napkin.model.language.problems import LanguageError
from napkin.program.build import BOOL, Builder, after, assign, event, input_, q, start, this, value, when
from napkin.program.canonical import program_bytes
from tests.program.examples import UNITS


def compiled(text):
    return compile_text(textwrap.dedent(text), UNITS)


def test_a_yes_no_input_and_state_are_set_and_read_as_true_and_false():
    """A stage sets the state to true, and a trigger reads it as a condition."""
    text = """
        service:
            input enabled: bool = false
            reported = false
            noticed = false
            stop = event():
                after 1 h:
                    this.reported = true
            notice = event():
                when this.reported and this.enabled:
                    this.notice.start()
                after 0 h:
                    this.noticed = true

        service.stop.start()
        """
    b = Builder(UNITS)
    service = b.entity(
        'service',
        input_('enabled', BOOL, False),
        value('reported', BOOL, False),
        value('noticed', BOOL, False),
        event('stop', after(q(1, 'h'), assign(this.reported, True))),
        event(
            'notice',
            when(this.reported & this.enabled, start(this.notice)),
            after(q(0, 'h'), assign(this.noticed, True)),
        ),
    )
    b.setup(start(service.stop))
    assert program_bytes(compiled(text).program) == program_bytes(b.finish())


@pytest.mark.parametrize(
    ('declaration', 'code', 'words'),
    [
        ('input enabled: bool = 0.5', 'type', 'declared bool'),
        ('input enabled: bool = yes', 'unknown_name', 'true or false'),
        ('input enabled: bool = no', 'unknown_name', 'true or false'),
        ('input enabled = false in [0, 2]', 'range', 'a range belongs to a number'),
        ('input enabled: person = true', 'type', 'declared person'),
        ('input enabled: yes/no = false', 'unit', 'yes is no unit'),
        ('reported: bool = 0', 'type', 'declared bool'),
    ],
)
def test_a_yes_no_declaration_takes_true_or_false(declaration, code, words):
    with pytest.raises(LanguageError) as caught:
        compiled(f'service:\n    {declaration}\n')
    assert caught.value.codes == [code], caught.value
    assert words in caught.value.problems[0].message, caught.value.problems[0].message
    assert caught.value.problems[0].line == 2


@pytest.mark.parametrize(
    ('declaration', 'statement', 'code', 'words'),
    [
        ('reported = false', 'this.reported = 1', 'type', 'reported is bool'),
        ('reported = false', 'this.reported += true', 'assign_value', 'takes ='),
        ('reported: number = 0 in [0, 1]', 'this.reported = true', 'type', 'reported is a plain number'),
    ],
)
def test_a_stage_sets_a_yes_no_state_to_true_or_false(declaration, statement, code, words):
    """A number state from 0 to 1 is a number, not a yes/no: a stage cannot set it to true."""
    text = f'service:\n    {declaration}\n    stop = event():\n        after 1 h:\n            {statement}\n'
    with pytest.raises(LanguageError) as caught:
        compiled(text)
    assert caught.value.codes == [code], caught.value
    assert words in caught.value.problems[0].message, caught.value.problems[0].message
    assert caught.value.problems[0].line == 5


def test_a_yes_no_state_is_no_stock():
    """A store that a flow takes from holds a number of a unit, never a yes/no."""
    with pytest.raises(LanguageError) as caught:
        compiled('service:\n    reported = false\n    flow leak: this.reported -> SINK\n')
    assert caught.value.codes == ['flow_end'] and caught.value.problems[0].line == 3
