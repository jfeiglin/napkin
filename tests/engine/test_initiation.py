"""The start of a run: the build-time rules on the start, and the run-time check that the start fires
first, at t=0.

The fixture is sc99 (tests/build.py): a start, the event `start` of the attacker, whose change
compromises the control system at t=0, and the service stop `end` hours after it. Expected
diagnostics follow from the contract (docs/language.md, §2.6, and docs/python-api.md), not from engine
output. Each rejected case has a counterexample that differs only in the rule's subject and is
accepted.
"""

import textwrap

import pytest

from napkin.engine import evaluate_study
from napkin.engine.study import initiation_diagnostics
from napkin.model import ModelError
from tests.build import (
    BASIS,
    X,
    compiled,
    drop,
    edit,
    event,
    evidence_library,
    indent,
    member,
    named,
    option,
    options,
    parameter,
    rejected,
    replace,
    run,
    sc99,
)
from tests.owned import block_at

# The place of the start: the event `start` of the attacker, and its line.
START = 'attacker/start'
HEAD = 'event start when t >= 0 h:'
# The change of the first move, the line of the start's one outcome.
CHANGE = 'control.state = "compromised"'
# The condition that would let the first move be stopped (`keep`) or skipped (`if`), as `event` takes it.
ENDINGS = {'keep': 'keep', 'if': 'condition'}
TRUSTED = 'control.state is "trusted"'


def lines_at(text, place):
    """The rows of the line at `place` and of the lines under it."""
    return block_at(text, place).rstrip('\n')


def accepted(text, lib=None):
    return compiled(text, lib or evidence_library())


def refused(text):
    """The (code, line of the file) of each diagnostic that rejects a text."""
    with pytest.raises(ModelError) as raised:
        accepted(text)
    return {(d['code'], d.get('line')) for d in raised.value.diagnostics}


def line_of(text, row):
    """The number of the one line of `text` that is `row`, after its indentation."""
    (number,) = [i for i, line in enumerate(text.split('\n'), 1) if line.strip() == row]
    return number


def operation(text, after='0', **ending):
    """The same attack as an operation that the start begins: the start, with its text and no change,
    starts the clock at t=0, and the attacker's own event `strike`, which waits on the start, makes the
    first effect after `after`, with the change and the records of the start's first move. `ending`
    (`keep`, `condition`) can stop or skip it."""
    head, words, *first_move = lines_at(text, START).split('\n')
    strike = event(
        'strike',
        'count(attacker.start) > 0',
        textwrap.dedent('\n'.join(first_move)),
        after=after,
        done='Unauthorized commands',
        **ending,
    )
    return edit(
        text,
        member('attacker', strike),
        replace(lines_at(text, START), '\n'.join((head, words))),
        replace('since(attacker.start) >= end', 'since(compromised) >= end'),
    )


def plain(text):
    """sc99 with identities as the bases of the start, of its first move and of the entity that it
    reaches, and with no premise in the review: no claim, so no technique."""
    return edit(
        text,
        replace('control:  @access', f'control:  {BASIS}'),
        replace(f'{HEAD}  @access', f'{HEAD}  {BASIS}'),
        drop(f'{START}/@/0', 'notes:/premises:', 'record:/access'),
    )


def test_a_valid_incident_runs_from_the_first_move():
    s = sc99()
    model = accepted(s)
    for name in model.runs:
        end = model.run_values(name)['service.end']
        rs, trajectory = run(s, name, evidence_library())
        semantic = [(e['event'], e['t']) for e in trajectory.trace if e['semantic']]
        assert semantic == [(X, 0), ('service.stop.done', end)]
        assert initiation_diagnostics(rs, trajectory, name) == []


@pytest.mark.parametrize('form', [lambda text: text, operation], ids=['sc99', '<lambda>'])
def test_a_start_needs_no_premise_and_no_cited_claim(form):
    """The language gives a start no meaning of its own: with no premise in the review, and with
    identities as the bases of the start, of its first move and of the entity that it reaches (no
    claim, so no technique), the model builds and its default study is admitted. The start acts as the
    attacker, and its event happens in every run."""
    model = accepted(form(plain(sc99())))
    study = evaluate_study(model)
    assert study.admissible, study.diagnostics
    assert model.initiation['entity'] == 'attacker'
    for name, item in study.runs.items():
        assert initiation_diagnostics(item['resolved'], item['trajectory'], name) == []
        assert model.initiation['effect'] in {entry['event'] for entry in item['trajectory'].trace}


def test_the_start_and_its_first_effect_are_parts_of_every_structure():
    # The start fires an event that does not exist.
    s = edit(sc99(), replace(f'        {CHANGE}', '        ghost'))
    assert rejected(s) == {('build', f'{START}/done/0')}
    # An option that keeps the start from ever happening leaves it out of that option's structure.
    link = options(
        'Link',
        option(
            'Isolated',
            'The service is cut off from the control system.',
            f'service.link = "isolated"  {BASIS}',
        ),
    )
    s = edit(
        sc99(),
        member('service', named('link', 'connected', 'isolated')),
        replace(HEAD, 'event start when t >= 0 h and service.link is "connected":'),
        replace('\nruns:', f'\n{link}\n\nruns:'),
    )
    assert rejected(edit(s, member('runs:', 'isolated = "Default" + "Isolated"'))) == {('initiation', START)}
    accepted(s)


@pytest.mark.parametrize(
    'after', ['1 h', 'attack_h', 'fixed_h', '0'], ids=["q(1, 'h')", 'self.attack_h', 'self.fixed_h', '0']
)
def test_an_incident_starts_with_an_instant_method(after):
    s = edit(sc99(), member('attacker', parameter('attack_h', 0, 'h', 0, 1), parameter('fixed_h', 0, 'h')))
    accepted(s)
    # The first change takes no time: the start has no delay.
    head = f'event start after {after} when t >= 0 h:'
    waiting = edit(s, replace(HEAD, head))
    assert refused(waiting) == {('structure', line_of(waiting, f'{head}  @access'))}
    # An operation that the start begins starts the clock earlier, and its first effect may take time.
    accepted(operation(s, after))


@pytest.mark.parametrize('field', ['keep', 'if'])
def test_an_incident_first_move_cannot_be_stopped_or_skipped(field):
    # The start's change under an outcome that holds only while (keep) or when (if) the control system
    # is trusted, and the outcome that stops or skips it otherwise.
    other = 'stopped' if field == 'keep' else 'skipped'
    outcomes = '\n'.join((f'done {TRUSTED}:', f'    {CHANGE}', f'{other} else:'))
    s = edit(sc99(), replace(f'        {CHANGE}', indent(outcomes, 2)))
    assert refused(s) == {('structure', line_of(s, f'{HEAD}  @access'))}
    # The first effect of an operation is a waiting event's, which can be stopped or skipped.
    accepted(operation(sc99(), '0', **{ENDINGS[field]: TRUSTED}))


def preceded(text):
    return edit(text, member('service', event('early', 't >= 0 h', doc='Early warning')))


def late(text):
    """The start an hour late: its condition holds from t = 1 h."""
    return edit(text, replace(HEAD, 'event start when t >= 1 h:'))


def test_a_start_that_runs_an_action_runs_it_first_at_time_zero():
    """Another event at t=0, on a line before the start's, comes after the start: the start fires
    first. A start that fires later lets that event come first. The model builds, and the run breaks
    the rule of the start; an operation's start fires first, as any start does."""
    for s in (preceded(sc99()), preceded(operation(sc99()))):
        rs, trajectory = run(s, 'a', evidence_library())
        assert [(e['event'], e['t']) for e in trajectory.trace if e['semantic']][:2] == [
            (X, 0),
            ('service.early.done', 0),
        ]
        assert initiation_diagnostics(rs, trajectory, 'a') == []
    rs, trajectory = run(late(preceded(sc99())), 'a', evidence_library())
    assert [d['code'] for d in initiation_diagnostics(rs, trajectory, 'a')] == ['initiation']


def test_a_study_whose_first_move_is_preceded_is_not_admitted():
    assert not evaluate_study(accepted(late(preceded(sc99())))).admissible
    assert evaluate_study(accepted(preceded(sc99()))).admissible
