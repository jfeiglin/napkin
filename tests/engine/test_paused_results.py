"""Paused play prefixes cannot become completed reports or cache entries; the checks of a run read
them up to their pause."""

import pickle
import zlib

import pytest

import napkin.engine.study as study_module
from napkin import store
from napkin.engine.report import (
    ReportingError,
    evaluate_outputs,
    outputs_until,
    peak_candidates,
    sample_result,
)
from napkin.engine.runtime import simulate
from napkin.engine.study import StudyResult, run_checks
from napkin.model.ir import thaw
from tests.build import append, compiled, edit, output, play_scenario


@pytest.fixture
def paused_run():
    model = compiled(play_scenario())
    resolved = model.resolve('a')
    library = thaw(model.library)
    trajectory = simulate(resolved, library, play={'control': {'guard': 'reader'}}, pause_at_decision=True)
    assert trajectory.paused
    return model, resolved, library, trajectory


@pytest.mark.parametrize('kind', ('outputs', 'peaks', 'final'))
def test_completed_reporting_rejects_a_paused_prefix_even_at_observed_times(paused_run, kind):
    model, resolved, library, trajectory = paused_run
    completed = {'resolved': resolved, 'trajectory': trajectory}
    with pytest.raises(ReportingError, match='paused trajectory'):
        if kind == 'outputs':
            evaluate_outputs(completed, library, [0, trajectory.end_time])
        elif kind == 'peaks':
            peak_candidates(completed, library)
        else:
            sample_result(StudyResult(model.model_hash, True, [], {}, runs={'a': completed}, model=model))


def test_completed_store_refuses_a_paused_write(paused_run, tmp_path):
    _, resolved, library, trajectory = paused_run
    key = store.key(resolved, library)
    with pytest.raises(ValueError, match='cannot cache a paused trajectory'):
        store._save(tmp_path, key, (resolved, library['units'], None), trajectory)
    assert not list(tmp_path.rglob('*.run'))


def test_paused_cache_entry_is_a_miss_and_legacy_full_play_remains_cacheable(paused_run, tmp_path):
    _, resolved, library, paused = paused_run
    play = {'control': {'guard': 'reader'}}
    key = store.key(resolved, library, None, play)
    # What a played run asks is a part of the key of its run.
    assert key != store.key(resolved, library) and key != store.key(resolved, library, None, {'control': {}})
    path = store._entry(tmp_path, key)
    path.parent.mkdir(parents=True)
    injected = {'format': store.FORMAT, 'trajectory': paused}
    path.write_bytes(store.MAGIC + zlib.compress(pickle.dumps(injected)))
    assert store._load(tmp_path, key) is None
    # Legacy play still computes its default continuation and is a full run,
    # even though it also exposes an unanswered decision.
    full = simulate(resolved, library, play=play)
    assert not full.paused and full.decision is not None
    restored = store._save(tmp_path, key, (resolved, library['units'], None, play), full)
    assert store.fingerprint(restored) == store.fingerprint(full)
    assert not store._load(tmp_path, key).paused


def test_the_checks_of_a_run_read_a_paused_run_up_to_its_pause(monkeypatch):
    """The checks that a study makes of each simulated run (`run_checks`) read a paused run up to its
    pause, where the completed-run report refuses it: no error, and the outcomes before the pause are
    the complete run's. A time after the pause is not reportable, and a reporting failure up to the
    pause is a diagnostic of the run, never an exception."""
    level = output('level', 'world.level', 'fraction', 'level', doc='Level')
    model = compiled(edit(play_scenario(), append(level)))
    resolved = model.resolve('a')
    library = thaw(model.library)
    paused = simulate(resolved, library, play={'control': {'guard': 'reader'}}, pause_at_decision=True)
    assert paused.paused and 0 < paused.end_time < paused.horizon
    found = run_checks(resolved, paused, library, 'a')
    assert [d for d in found if d.get('severity', 'error') == 'error'] == []
    assert all(d['run'] == 'a' for d in found)
    before = [0, paused.end_time / 2]
    complete = simulate(resolved, library)
    rows = outputs_until({'resolved': resolved, 'trajectory': paused}, library, before)
    assert rows == evaluate_outputs({'resolved': resolved, 'trajectory': complete}, library, before)
    assert rows[1]['values'][model.outputs['level']] > 0
    with pytest.raises(ReportingError, match='outside'):
        outputs_until({'resolved': resolved, 'trajectory': paused}, library, [paused.horizon])

    def failing(*args, **kwargs):
        raise ReportingError('Injected reporting failure')

    monkeypatch.setattr(study_module, 'outputs_until', failing)
    (failure,) = [d for d in run_checks(resolved, paused, library, 'a') if d['severity'] == 'error']
    assert (failure['code'], failure['run']) == ('evaluation_error', 'a')
