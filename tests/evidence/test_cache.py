"""The evidence cache is shared across worktrees and can be explicitly located."""

from subprocess import CompletedProcess

from tools.evidence.cache import evidence_cache


def test_explicit_cache_precedes_checkout_discovery(tmp_path, monkeypatch):
    cache = tmp_path / 'bytes'
    monkeypatch.setenv('EVIDENCE_CACHE', str(cache))
    monkeypatch.setattr('subprocess.run', lambda *a, **k: (_ for _ in ()).throw(AssertionError('git called')))
    assert evidence_cache(tmp_path / 'worktree') == cache


def test_linked_worktree_uses_main_checkout_cache(tmp_path, monkeypatch):
    monkeypatch.delenv('EVIDENCE_CACHE', raising=False)
    common = tmp_path / 'main/.git'
    common.mkdir(parents=True)
    monkeypatch.setattr('subprocess.run', lambda *a, **k: CompletedProcess(a, 0, str(common) + '\n', ''))
    assert evidence_cache(tmp_path / 'linked') == common.parent / '.evidence-cache'


def test_non_git_install_uses_its_root(tmp_path, monkeypatch):
    monkeypatch.delenv('EVIDENCE_CACHE', raising=False)

    def unavailable(*args, **kwargs):
        raise OSError('git unavailable')

    monkeypatch.setattr('subprocess.run', unavailable)
    assert evidence_cache(tmp_path) == tmp_path / '.evidence-cache'
