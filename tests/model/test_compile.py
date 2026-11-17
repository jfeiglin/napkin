"""One rejected model file per class of build diagnostic, each located at the line that it names;
and copies, which are numbered with names that expressions read."""

from __future__ import annotations

import pytest

from napkin.engine.report import evaluate_outputs
from napkin.model import ModelError
from napkin.model.ir import thaw
from napkin.model.language import front
from tests.acceptance.helpers import LIBRARY, fixture
from tests.build import (
    block,
    compiled,
    document,
    edit,
    entity,
    event,
    formula,
    library,
    member,
    output,
    rejected,
    replace,
    run,
    stock,
    template,
)

# {class: (fixture, edit, code, place of the diagnostic, the start of the line that it names)}. The
# parser names a line that breaks the form of the language (`syntax`, at no place); the resolver a
# part that breaks its rules (`structure`); the builder a part that it cannot build (`build`); the
# compiler's checks keep their codes.
CASES = {
    # A line that the language does not have.
    'unknown_key': ('F5', [member('tank/drained', 'kindd: stock')], 'syntax', '', 'kindd: stock'),
    # A formula that reads a name that no entity has.
    'unknown_name': (
        'F5',
        [member('tank', 'let seen: L = basn.water  @fixture')],
        'build',
        'tank/seen',
        'let seen:',
    ),
    # An event that acts on what it reads, with no record for it.
    'trigger_basis': (
        'F5',
        [member('basin', block('event noticed when tank.drain is "open":', 'logs += 1'))],
        'build',
        'basin/noticed',
        'event noticed',
    ),
    # Two writes to one value in one step.
    'written_twice': ('F5', [member('basin/log', 'logs = logs')], 'build', 'basin/log/done/2', 'logs = logs'),
    # Two events that fire each other.
    'calls_itself': (
        'F5',
        [member('basin/log', 'relog'), member('basin', block('event relog:', 'log'))],
        'build',
        'basin/log',
        'event log:',
    ),
    # An event with no memory: it can trigger again on a crossing, and it sets nothing that its
    # condition reads.
    'trigger_memory': (
        'F5',
        [member('tank', block('event again when water <= 50 L:  @fixture', '"The tank is low."'))],
        'unsupported_condition',
        'tank/again/when:',
        'event again when',
    ),
    'expression': (
        'F5',
        [replace('move 5 L from water to spill', 'move 1 h from water to spill')],
        'expression',
        'basin/log/done/0',
        'move 1 h from',
    ),
    'unsupported_condition': (
        'F5',
        [replace('water <= 70 L:', 'water * water <= 70 L * 70 L:')],
        'unsupported_condition',
        'tank/alarm/when:',
        'event alarm when siren is "off" and water * water',
    ),
    'bounds': (
        'F5',
        [replace('var water: L = level0 size 120 L', 'var water: L = level0 in 5 L to 1 L size 120 L')],
        'bounds',
        'tank/water',
        'var water',
    ),
}


def diagnostics(family, steps):
    """(the rows of the edited file, the diagnostics that reject it)."""
    text = edit(fixture(family), *steps)
    origin = f'{family}.scn'
    with pytest.raises(ModelError) as caught:
        front.compile_file(front.read(text, origin), origin, thaw(LIBRARY))
    return text.split('\n'), caught.value.diagnostics


@pytest.mark.parametrize('name', sorted(CASES))
def test_rejected_source_names_its_class_and_line(name):
    family, steps, code, place, row = CASES[name]
    rows, found = diagnostics(family, steps)
    found = [d for d in found if d['code'] == code]
    assert found, found
    assert any(d['path'] == place for d in found), [d['path'] for d in found]
    assert all(d.get('file') == f'{family}.scn' for d in found)
    # Each one names the line of the edited file that it is about.
    assert all(rows[d['line'] - 1].strip().startswith(row) for d in found if d['path'] == place)


def number_state(name):
    """A free number state that starts at zero."""
    return stock(name, 0, 'fraction', minimum=None, kind='state')


def copies(*readers, members=(), count='2', outputs=()):
    """A file with the template System, two copies of it, `s.1` and `s.2`, and `readers`."""
    return document(
        'Numerical fixture',
        template('System', number_state('x'), *members, doc='A numerical fixture.'),
        entity('s', template='System', copies=count),
        *readers,
        *outputs,
        horizon=10,
    )


@pytest.mark.parametrize(
    ('link', 'read'), [(None, 'seen = s.2.x'), ('let target = s.2', 'seen = target.x')], ids=['name', 'link']
)
def test_copies_are_numbered_with_names_that_expressions_can_read(link, read):
    """Copy k of the set `s`, from 1, is `s.k` in the file and `s_k` in the structure, a name that
    expressions can read. Each copy reads its number as `copy`; another entity reads one copy by its
    name, or through a link that names it, and the top level reads the set with `sum()`. Copies with
    keys are not a part of the language, and a copy that the set does not have is no name."""

    def source(count='2', reading=read):
        reader = entity(
            'u',
            *([link] if link else []),
            number_state('seen'),
            event('see', 't >= 2 h', reading),
            doc='A reader of one copy.',
            title='Reader',
        )
        return copies(
            reader,
            members=(formula('number', 'copy', 'fraction'), event('go', 't >= 1 h', 'x = number')),
            count=count,
            outputs=(
                output('total', 'sum(s.x)', 'fraction', 'level', doc='The numbers that the copies took'),
            ),
        )

    assert dict(compiled(source()).entities) == {'s_1': 's.1', 's_2': 's.2', 'u': 'u'}
    rs, trajectory = run(source())
    final = trajectory.env_at(10)
    assert (final['s_1.x'], final['s_2.x'], final['u.seen']) == (1, 2, 2)
    rows = evaluate_outputs({'resolved': rs, 'trajectory': trajectory}, library(), [10])
    assert rows[0]['values'] == {'total': 1 + 2}
    assert rejected(source(count='["a", "b"]')) == {('syntax', '')}
    if link is None:
        assert rejected(source(reading='seen = s.3.x')) == {('build', 'u/see/done/0')}
