"""Models built and run, with closed forms: occurrences of one event that wait each on their own, the
reads of history and their refusals, an error of a stage that stops the run with its expression, its
occurrence and its time, and lines that the compiler reads as text only.

A gate is jammed twice by the setup at t = 0, by occurrences that wait 2 h and 5 h (spec, "History
and optional domain status"): the jams count 0, then 1 from 2 h and 2 from 5 h; both occurrences
start at 0, so `since(this.jam)` is t, and they finish at 2 h and 5 h. An occurrence of another event
divides by zero at 3 h ("Time, waiting and completion": an execution error fails the run with the
expression, the invocation and the simulation time).

The rest of the old file went with the old language or is live elsewhere: the restarts of `elapsed`
in `tests/engine/test_firing_values.py`; options and edits in `tests/language/test_runs.py`; the
misuses of each part in the refusal tests of `tests/language/`; reachability (D16) in
`tests/program/test_reach.py`; the support of each part in `tests/evidence/`; and outcomes, start
structures, copies and key inputs left the language.
"""

from __future__ import annotations

import pytest

from napkin.engine import read, run
from napkin.model.compile import compile_text
from napkin.model.language.problems import LanguageError
from tests.program.examples import UNITS

GATE = """\
scenario "Jams"
    horizon 10 h

gate:
    "A gate that an attacker jams."
    jams = 0
    ratio = 0
    jam = event(delay: h):
        after delay:
            this.jams += 1
    split = event():
        after 3 h:
            this.ratio = 1 / (this.jams - this.jams)
    seen = formula(count(this.jam.occurrences))
    finished = formula(count(this.jam.occurrences.done))
    quiet = formula(since(this.jam))

gate.jam.start(2 h)
gate.jam.start(5 h)
"""


def compiled(text=GATE):
    return compile_text(text, UNITS)


def test_occurrences_of_one_event_wait_each_on_their_own():
    model = compiled()
    record = run(model.program, model.configuration)
    assert record.failure is None
    times = [1, 2, 4, 5, 10]
    jams, seen, finished, quiet = read(
        record, model.program, ['gate.jams', 'gate.seen', 'gate.finished', 'gate.quiet'], times
    )
    assert jams.values == finished.values == (0, 1, 1, 2, 2)
    assert seen.values == (2,) * 5 and quiet.values == tuple(times)


def test_an_error_of_a_stage_stops_the_run_with_its_expression_occurrence_and_time():
    model = compiled(GATE + 'gate.split.start()\n')
    record = run(model.program, model.configuration)
    assert record.failure is not None and record.failure.t == 3
    message = record.failure.detail('message')
    assert "'1 / (gate.jams - gate.jams)'" in message and 'division by zero' in message
    assert 'gate.split' in message and 't = 3 h' in message


@pytest.mark.parametrize(
    ('read_', 'code', 'words'),
    [
        ('since(this.jams)', 'history', 'since takes an event'),
        ('elapsed(this.jam)', 'history', 'elapsed takes a value'),
        ('elapsed(this.jams + 1)', 'history', 'a named part, not an expression'),
        ('since(this.jam, this.split)', 'arguments', 'since takes an event'),
    ],
)
def test_a_read_of_history_names_one_event_or_one_value(read_, code, words):
    text = GATE.replace('quiet = formula(since(this.jam))', f'quiet = formula({read_})')
    with pytest.raises(LanguageError) as raised:
        compiled(text)
    (problem,) = raised.value.problems
    assert (problem.code, problem.line) == (code, text.split('\n').index(f'    quiet = formula({read_})') + 1)
    assert words in problem.message


def test_a_model_has_no_role():
    """No part of a model has a role (PLAN, change 23): who plays a part is the wrapper's
    (`roles.toml`) and the pictures' stylesheet's, so a role under an entity is refused by name and
    says where it goes."""
    with pytest.raises(LanguageError) as caught:
        compiled(
            GATE.replace(
                '    "A gate that an attacker jams."\n',
                '    "A gate that an attacker jams."\n    role operator\n',
            )
        )
    (problem,) = caught.value.problems
    assert problem.code == 'role' and 'roles.toml' in problem.message and 'style.toml' in problem.message


@pytest.mark.parametrize('word', ['frobnicate', 'Max', 'mean'])
def test_a_call_of_a_word_that_is_no_function_names_the_word_as_the_file_writes_it(word):
    text = GATE.replace('quiet = formula(since(this.jam))', f'quiet = formula({word}(this.jams, 1))')
    with pytest.raises(LanguageError) as raised:
        compiled(text)
    (problem,) = raised.value.problems
    assert problem.code == 'syntax' and f'{word}(...) is no function of the language' in problem.message
