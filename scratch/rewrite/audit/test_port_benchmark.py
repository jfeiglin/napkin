"""The held-pipe gate uses matched batches and reports a stopped full baseline as incomplete."""

import hashlib
from argparse import Namespace
from pathlib import Path

import pytest

from scratch.rewrite.audit import port_benchmark as bench


@pytest.mark.parametrize('row', ['held-pipes', 'component-tanks', 'sparse-compartment-tanks'])
def test_calibration_uses_both_engines_and_keeps_one_repeat_count(tmp_path, monkeypatch, row):
    samples = []
    monkeypatch.setattr(bench, 'identity', lambda path: path.name)

    def take(path, args, row, tag, root, sha, repeat):
        samples.append((path.name, repeat))
        return {'batch_seconds': 2 if tag == 'B' else 0.4}

    monkeypatch.setattr(bench, 'take', take)
    bench.campaign(
        Namespace(
            out=tmp_path,
            phase='final',
            rows=[row],
            worker_script=Path(bench.__file__),
            mode='timing',
            revision=['B=B', 'F=F'],
            harness=Path(bench.__file__).resolve().parents[3],
        )
    )
    schedule = bench.read(tmp_path / 'final' / f'{row}.schedule.json')
    assert schedule['worker_sha256'] == bench.file_digest(Path(bench.__file__))
    assert samples == [
        (f'{row}.B.calibration.json', 1),
        (f'{row}.F.calibration.json', 1),
        (f'{row}.1.B.json', 4),
        (f'{row}.1.F.json', 4),
        (f'{row}.2.F.json', 4),
        (f'{row}.2.B.json', 4),
        (f'{row}.3.B.json', 4),
        (f'{row}.3.F.json', 4),
    ]


def sample(phase, elapsed, repeat=1):
    return {
        'phase': phase,
        'row': 'held-pipes',
        'argv': bench.workload('held-pipes', phase)[1],
        'observations': {
            key: [3, 2, 1] for key in ['total', 'drawing', 'critical_stock', 'places.p00042.stock']
        },
        'output': 'checked',
        'output_sha256': hashlib.sha256(b'checked').hexdigest(),
        'batch_seconds': elapsed,
        'run_record_seconds': elapsed / repeat,
        'repeat': repeat,
        'sha': 'sample',
        'peak_rss_bytes': 1024,
    }


def test_short_pair_fails_if_below_one_second_or_repeats_differ(tmp_path):
    folder = tmp_path / 'final'
    folder.mkdir()
    args = Namespace(
        out=tmp_path,
        phase='final',
        rows=['held-pipes'],
        held_baseline_cutoff_seconds=None,
        baseline_guard_run_seconds=None,
    )
    for i in (1, 2, 3):
        for tag in ('B', 'F'):
            bench.save(folder / f'held-pipes.{i}.{tag}.json', sample('final', 2, 2))
    assert bench.summary(args) == 0
    changed = folder / 'held-pipes.2.F.json'
    bench.save(changed, sample('final', 0.99, 2))
    with pytest.raises(ValueError, match='below 1 s'):
        bench.summary(args)
    bench.save(changed, sample('final', 2, 1))
    with pytest.raises(ValueError, match='repeat count'):
        bench.summary(args)


def test_full_guard_refuses_to_infer_a_ratio_from_process_elapsed(tmp_path, capsys):
    folder = tmp_path / 'guard'
    folder.mkdir()
    args = Namespace(
        out=tmp_path,
        phase='guard',
        rows=['held-pipes'],
        held_baseline_cutoff_seconds=12653,
        baseline_guard_run_seconds=None,
    )
    candidate = sample('guard', 106)
    bench.save(folder / 'held-pipes.1.F.json', candidate)
    assert bench.summary(args) == 2
    text = capsys.readouterr().out
    assert '12653 s elapsed' in text and 'F/B ratio unavailable; 1.05 gate unverified' in text
    bench.save(folder / 'held-pipes.1.B.json', sample('guard', 100))
    with pytest.raises(ValueError, match='no completed baseline'):
        bench.summary(args)
    args.held_baseline_cutoff_seconds = None
    assert bench.summary(args) == 1  # 1.06 fails the full pipes guard even though it passes the event limit
    candidate['output'] = 'edited'
    bench.save(folder / 'held-pipes.1.F.json', candidate)
    with pytest.raises(ValueError, match='checksum'):
        bench.summary(args)
