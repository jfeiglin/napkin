"""Status displays (spec, "Model text, status cases and evidence"): the cases of an entity or a template
in written order, lowered to the program's display, each member's display followed by the record of a
run as the case that applies (`case[k]`), and the refusals of a display, each with its code and line.
The expected cases are worked by hand: the first case whose condition holds, else the last."""

import textwrap

import pytest

from napkin.engine import read, run
from napkin.model.compile import compile_text
from napkin.model.language.problems import LanguageError
from tests.program.examples import UNITS

CREW = """
    scenario "Crews"
        horizon 6 h
    crew:
        work_state: enum[WAITING, WORKING, DONE] = WAITING
            "Crew work state"
        status ok when this.work_state == DONE
            "Repairs are complete."
        status degraded when this.work_state == WORKING
            "Crews are carrying out repairs."
        status degraded
            "Crews are waiting for access."
        work = event():
            after 2 h:
                this.work_state = WORKING
            after 2 h:
                this.work_state = DONE
    crew.work.start()
    """


def compiled(text):
    return compile_text(textwrap.dedent(text), UNITS)


def refused(text, codes, lines):
    with pytest.raises(LanguageError) as caught:
        compiled(text)
    assert caught.value.codes == codes, caught.value
    assert [problem.line for problem in caught.value.problems] == lines
    return caught.value.problems[0].message


def test_the_record_follows_the_case_that_applies():
    """The crew waits until 2 h (the fallback, `case[2]`), works until 4 h (`case[1]`, which shares its
    rating with the fallback and has its own text), and is done from 4 h (`case[0]`)."""
    model = compiled(CREW)
    record = run(model.program, model.configuration)
    (status,) = read(record, model.program, ['crew.status'], [0, 1.5, 2, 3.9, 4, 6])
    assert status.values == ('case[2]', 'case[2]', 'case[1]', 'case[1]', 'case[0]', 'case[0]')
    texts = [model.declared.part(f'crew.status.{case}').text for case in ('case[0]', 'case[1]', 'case[2]')]
    assert texts == [
        'Repairs are complete.',
        'Crews are carrying out repairs.',
        'Crews are waiting for access.',
    ]


def test_each_member_of_a_template_has_its_own_display():
    text = """
        scenario "Wells"
            horizon 2 h
        Well:
            input depth: m = 10 m
            status degraded when this.depth > 20 m
                "Deep."
            status ok
                "Shallow."
        north: Well
        south: Well
            depth = 30 m
        """
    model = compile_text(textwrap.dedent(text), {**UNITS, 'm': {'length': 1}})
    record = run(model.program, model.configuration)
    found = read(record, model.program, ['north.status', 'south.status'], [0, 2])
    assert [reading.values for reading in found] == [('case[1]', 'case[1]'), ('case[0]', 'case[0]')]


@pytest.mark.parametrize(
    ('cases', 'codes', 'lines'),
    [
        # The fallback stands last, and only it has no condition: each case out of place is named.
        (
            '    status ok\n        "Fine."\n    status degraded when this.a < 1\n',
            ['status', 'status'],
            [3, 5],
        ),
        ('    status ok when this.a > 1\n        "Fine."\n', ['status'], [3]),
        ('    status ok when this.a\n    status ok\n', ['type'], [3]),
        ('    status ok when uniform(0, 1).draw() < 0.5\n    status ok\n', ['formula_draws'], [3]),
    ],
)
def test_a_display_is_refused_with_its_code_and_line(cases, codes, lines):
    message = refused(f'c:\n    a = 2\n{cases}', codes, lines)
    if codes[0] == 'status':
        assert 'last case' in message


def test_an_owner_with_a_display_declares_no_value_named_status():
    message = refused('c:\n    status = 1\n    status ok\n        "Fine."\n', ['status'], [3])
    assert 'c.status names the status display' in message
