"""An edit belongs to the physical stop at which the session made it."""

import json
from dataclasses import replace

import pytest

from napkin.engine import read
from napkin.model.compile import compile_text
from napkin.program.checkpoint import Breakpoint, CheckpointError, dumps, loads
from napkin.program.config import InputValue, Quantity
from napkin.session import Session, play

MODEL = """scenario "Saved edit stops"
    horizon 5 h
yard:
    input delay: h = 3 h
    total = 0
    work = event():
        after this.delay:
            this.total += 1
        after 4 h - this.delay:
            this.total += 1
yard.work.start()
"""


@pytest.fixture
def waiting():
    model = compile_text(MODEL, {'h': {'time': 1}})
    stops = [Breakpoint(f'yard.work.step[{i}]') for i in range(2)]
    session = Session(model.program, model.configuration, stops)
    assert session.advance().stop.t == 3
    session.edit('yard.total', 10)
    assert session.advance().stop.t == 4
    return model, session


def _restore(kind, model, session, tmp_path):
    if kind == 'memory':
        return Session.restored(model.program, session.checkpoint)
    if kind == 'saved':
        path = tmp_path / 'second.checkpoint'
        session.save(path)
        return Session.load(path, model.program)
    return session


@pytest.mark.parametrize('kind', ('original', 'memory', 'saved'))
def test_replay_rejects_a_shifted_edit_stop_even_when_the_saved_stop_repeats(waiting, tmp_path, kind):
    model, original = waiting
    session = _restore(kind, model, original, tmp_path)
    moved = replace(model.configuration, inputs=(InputValue('yard', 'delay', Quantity(2, 'h')),))
    with pytest.raises(CheckpointError, match=r'stop 1 .*3 h, .*2 h'):
        play(model.program, moved, session.log)


@pytest.mark.parametrize('kind', ('memory', 'saved'))
def test_replaying_a_restored_edit_uses_the_original_stops(waiting, tmp_path, kind):
    model, original = waiting
    session = _restore(kind, model, original, tmp_path)
    record = play(model.program, model.configuration, session.log)
    assert read(record, model.program, ['yard.total'], [5])[0].values == (12,)
    assert session.log == original.log


def test_a_log_refuses_an_edit_at_a_hit_for_which_it_has_no_stop(waiting):
    model, session = waiting
    incomplete = replace(session.log, stops=(session.log.stops[1],))
    with pytest.raises(CheckpointError, match='stop 1'):
        Session(model.program, model.configuration, log=incomplete)


def test_legacy_checkpoint_resumes_but_its_unwitnessed_edit_cannot_replay(waiting):
    model, session = waiting
    header, body = dumps(session.checkpoint).split(b'\n', 1)
    legacy = json.loads(body)
    legacy.pop('stops', None)  # the checkpoint format before it retained stop identities
    saved = loads(header + b'\n' + json.dumps(legacy).encode())
    restored = Session.restored(model.program, saved)
    assert restored.advance() is None
    assert read(restored.record, model.program, ['yard.total'], [5])[0].values == (12,)
    with pytest.raises(CheckpointError, match='stop 1'):
        play(model.program, model.configuration, restored.log)


def test_a_legacy_first_checkpoint_keeps_its_own_edit_stop():
    model = compile_text(MODEL, {'h': {'time': 1}})
    session = Session(model.program, model.configuration, (Breakpoint('yard.work.step[0]'),))
    session.advance()
    session.edit('yard.total', 10)
    header, body = dumps(session.checkpoint).split(b'\n', 1)
    legacy = json.loads(body)
    legacy.pop('stops', None)
    restored = Session.restored(model.program, loads(header + b'\n' + json.dumps(legacy).encode()))
    assert restored.log == session.log
    result = play(model.program, model.configuration, restored.log)
    assert read(result, model.program, ['yard.total'], [5])[0].values == (12,)
