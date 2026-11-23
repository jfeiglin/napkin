"""Recover the guard properties of already-passed deep plant cases at 93ebabf.

Run from the pinned checkout, using the original Linux environment. --ids is an
explicit list of full pytest node IDs, one per line. --pass-log is its original
verbose xdist log (plain or gzip). Output must be a new JSONL file. --self-check
validates the projection on synthetic controls on either operating system.
"""

import argparse
import functools
import gzip
import hashlib
import json
import os
import platform
import re
import subprocess
import sys
from dataclasses import replace
from fractions import Fraction
from importlib.metadata import version
from pathlib import Path
from unittest.mock import patch

PIN = '93ebabf349d051f6fa71f1615732f5326b61ec4e'
FAMILIES = ('empty_event', 'named', 'small_unit', 'split', 'builder', 'artifact',
            'checkpoint', 'sparse', 'roundoff')
PREFIX = 'tests/engine/test_port_invariance.py::test_all_port_transforms'
NODE = re.compile(re.escape(PREFIX) + r'\[(\d+)-([a-z_]+)\]')
ANSI = re.compile(r'\x1b\[[0-9;]*m')
STATUS = re.compile(r'^\s*(?:\[gw\d+\]\s*)?(?:\[\s*\d+%\]\s*)?'
                    r'(PASSED|FAILED|ERROR|SKIPPED|XFAIL|XPASS)\s+(\S+)\s*$')
OWNER = 'plant.observe#0'


def require(condition, reason):
    if not condition:
        raise ValueError(str(reason))


def sha(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def load_owner(self_check):
    """Refuse other versions of the comparison, both interpreters or their libraries."""
    global corpus
    root = Path.cwd().resolve()
    def git(*args):
        return subprocess.check_output(['git', *args], text=True).strip()
    require(root == Path(git('rev-parse', '--show-toplevel')).resolve(), 'run from the checkout root')
    head = git('rev-parse', 'HEAD')
    require(self_check or head == PIN, f'expected Linux checkout {PIN}, found {head}')
    require(not git('diff', '--name-only', PIN, '--', 'napkin', 'tests', 'tools',
                    'pyproject.toml', 'requirements.lock', 'conftest.py'), 'runtime or test source differs')
    require(not sys.flags.optimize, 'use normal Python assertion settings')
    for line in (root / 'requirements.lock').read_text().splitlines():
        name, wanted = line.split('==')
        require(version(name) == wanted, f'locked {name} {wanted} is required')
    sys.path.insert(0, str(root))
    from tests.engine import test_port_invariance as corpus
    require(Path(corpus.__file__).resolve() == root / 'tests/engine/test_port_invariance.py',
            'imported the wrong test module')
    require(tuple(corpus.TRANSFORMS[:9]) == FAMILIES, 'plant families changed')
    return head


def view(at, stage):
    # The original views include the Fraction(1) sample as a value key before
    # stage times are merged. Keep its type in compare()'s returned property repr.
    require(at == 1 and stage.owner == OWNER and stage.origin == corpus.GUARD and stage.kind == 'decision',
            ('unexpected guard', at, stage))
    return corpus.View({Fraction(1): {}}, {at: [stage]}, {}, {}, (corpus.HORIZON, 'finished'))


def oracle_guard(oracle):
    rows = []
    for entry in oracle.trace:
        if entry.origin == corpus.GUARD:
            kind = {'stage': 'commit', 'done': 'finish'}.get(entry.kind, entry.kind)
            stage = corpus.stage_entry(kind, entry.label, entry.origin, entry.round)
            if stage and stage.kind == 'decision':
                rows.append((entry.t, stage))
    require(len(rows) == 1, ('oracle guard count', rows))
    return view(*rows[0])


def engine_guard(record):
    require(record.failure is None and record.end == corpus.HORIZON,
            ('engine cutoff', record.end, record.failure))
    rows = []
    finishes = []
    for entry in record.trace:
        if entry.owner != OWNER:
            continue
        stage = corpus.stage_entry(entry.kind, entry.owner, entry.part, entry.round, entry.detail('near'))
        if stage and stage.kind == 'decision':
            rows.append((entry.t, stage))
        if entry.kind == 'finish':
            finishes.append(entry)
    require(len(finishes) == 1, ('engine observer finish count', len(finishes)))
    if not rows:
        # Same silent, out-of-band false guard as engine_view's finish fallback.
        finish = finishes[0]
        rows.append((finish.t, corpus.Stage('decision', finish.owner, corpus.GUARD, finish.round, False)))
    require(len(rows) == 1 and rows[0][0] == finishes[0].t, ('engine guard ordering', rows))
    return view(*rows[0])


class Captured(Exception):
    """Stop the corpus *view projection* at its first post-run public read."""


def capture(helper, first_read, project, *args, **kwargs):
    def intercept(completed, *_args, **_kwargs):
        raise Captured(project(completed))
    with patch.object(corpus, first_read, intercept):
        try:
            helper(*args, **kwargs)
        except Captured as observed:
            return observed.args[0]
    raise ValueError(f'{helper.__name__} never reached the expected post-run read')


@functools.lru_cache(maxsize=1)
def baseline(seed):
    case = corpus.Case.of(seed)
    original = corpus.text_program(case, corpus.Spelling())
    reference = capture(corpus.oracle_view, 'values_at', oracle_guard, case, original.program)
    base = capture(corpus.engine_view, 'read', engine_guard, case, original.program, False, False)
    return case, original, reference, base, corpus.compare(base, reference, seed, 'original vs reference')


def candidate(case, original, name):
    if name in ('sparse', 'roundoff', 'checkpoint'):
        return original.program
    if name == 'builder':
        return corpus.builder_program(case, corpus.Spelling())
    if name == 'artifact':
        return corpus.load_artifact(original.artifact().data()).program
    return corpus.text_program(case, corpus.Spelling(**{name: True})).program


def decision(observed):
    ((at, (stage,)),) = observed.stages.items()
    return {'at': repr(at), 'round': stage.round, 'ran': stage.ran, 'near': repr(stage.tie)}


def observe(seed, name, validate=False):
    case, original, reference, base, base_tie = baseline(seed)
    program = candidate(case, original, name)
    observations = {'reference': decision(reference), 'original': decision(base)}
    properties = []
    if validate:
        full_ref = corpus.oracle_view(case, original.program)
        full_base = corpus.engine_view(case, original.program, False, False)
        assert_same(full_ref, reference)
        assert_same(full_base, base)
        require(repr(corpus.compare(full_base, full_ref, seed, 'original vs reference')) == repr(base_tie),
                'base property mismatch')
        if name == 'checkpoint' and base_tie is None:
            # Inject a flagged disagreement into the real, full event sequence to check
            # the payload's exact spelling, including its timestamp and earlier moves.
            flagged = ('threshold', 0, 1e-9)
            def flipped(stage):
                return replace(stage, ran=not stage.ran, tie=flagged) if stage.kind == 'decision' else stage
            modified = replace(full_base, stages={at: list(map(flipped, stages))
                                                  for at, stages in full_base.stages.items()})
            ((at, (stage,)),) = base.stages.items()
            full_result = corpus.compare(modified, full_ref, seed, 'flagged control')
            projected = corpus.compare(view(at, flipped(stage)), reference, seed, 'flagged control')
            require(full_result and repr(full_result) == repr(projected), ('positive control', full_result, projected))
    for probe in (-2, 2) if name == 'roundoff' else (0,):
        label = f'{name} {probe:+d}' if probe else name
        with patch('napkin.engine.timeline.plan.LIMIT', 0 if name == 'sparse' else 150), \
                patch.object(corpus.stocks, 'LEDGER_PROBE', probe):
            args = (case, program, name == 'checkpoint', name == 'sparse')
            changed = capture(corpus.engine_view, 'read', engine_guard, *args)
            if validate:
                full_changed = corpus.engine_view(*args)
                assert_same(full_changed, changed)
        observations[label] = decision(changed)
        ties = (base_tie, corpus.compare(changed, reference, seed, label + ' vs reference'),
                corpus.compare(changed, base, seed, label + ' vs original'))
        if validate:
            full_ties = (base_tie, corpus.compare(full_changed, full_ref, seed, label + ' vs reference'),
                         corpus.compare(full_changed, full_base, seed, label + ' vs original'))
            require(repr(ties) == repr(full_ties), ('full and projected properties differ', ties, full_ties))
        if any(ties):
            properties.append([f'near-tie-{label}', repr((seed, *ties))])
    return {'observations': observations, 'properties': properties}


def assert_same(full, projected):
    rows = [(t, stage) for t, stages in full.stages.items() for stage in stages if stage.kind == 'decision']
    require(len(rows) == 1 and repr(view(*rows[0]).stages) == repr(projected.stages),
            ('full and projected guards differ', rows, projected.stages))


def self_check():
    # Force a positive property, its reverse, equal decisions with near info, and
    # a divergent unflagged guard. compare() must retain its original behavior.
    flagged = ('threshold', 0, 1e-9)
    false = view(1.0, corpus.Stage('decision', OWNER, corpus.GUARD, 2, False, flagged))
    true = view(Fraction(1), corpus.Stage('decision', OWNER, corpus.GUARD, 2, True))
    for ours, theirs, left, right in ((false, true, False, True), (true, false, True, False)):
        actual = corpus.compare(ours, theirs, 7, 'fixture')
        expected = (7, 'fixture', Fraction(1), corpus.GUARD, left, right,
                    flagged if not left else None, flagged if not right else None)
        require(repr(actual) == repr(expected), (actual, expected))
    require(corpus.compare(false, false, 7, 'fixture') is None, 'same decision flagged')
    plain = view(1.0, corpus.Stage('decision', OWNER, corpus.GUARD, 2, False))
    try:
        corpus.compare(plain, true, 7, 'fixture')
    except AssertionError:
        pass
    else:
        raise ValueError('unflagged divergence was accepted')
    return {f'{n}-{f}': observe(n, f, validate=True) for n, f in ((0, 'checkpoint'), (87, 'sparse'), (2, 'roundoff'))}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--ids', type=Path)
    parser.add_argument('--pass-log', type=Path)
    parser.add_argument('--output', type=Path)
    parser.add_argument('--self-check', action='store_true')
    args = parser.parse_args()
    head = load_owner(args.self_check)
    if args.self_check:
        print(json.dumps({'mode': 'synthetic-self-check', 'head': head, 'pairs': self_check()}, indent=2))
        return
    require(args.ids and args.pass_log and args.output, '--ids, --pass-log and --output are required')
    require(sys.platform == 'linux', 'Linux evidence requires running in the original Linux environment')
    ids = args.ids.read_text().splitlines()
    require(ids and len(set(ids)) == len(ids), 'empty or duplicate requested IDs')
    wanted = {}
    for node in ids:
        m = NODE.fullmatch(node)
        require(m and 0 <= int(m[1]) < 2000 and m[2] in FAMILIES, ('invalid property-capable ID', node))
        wanted[node] = int(m[1]), m[2]
    statuses = {node: [] for node in ids}
    linux = False
    opener = gzip.open if args.pass_log.suffix == '.gz' else open
    with opener(args.pass_log, 'rt', errors='replace') as log:
        for line in log:
            line = ANSI.sub('', line).strip()
            if line.startswith('platform linux -- Python '):
                require(f'Python {platform.python_version()},' in line, 'Python version differs from primary')
                linux = True
            status = STATUS.fullmatch(line)
            if status and status[2] in statuses:
                statuses[status[2]].append(status[1])
    require(linux, 'primary Linux environment header missing')
    missing = [node for node, observed in statuses.items() if observed != ['PASSED']]
    require(not missing, ('expected a single unambiguous PASSED result per requested node', missing[:15]))
    provenance = {'source': 'recomputed-guard', 'sha': head, 'primary_log_sha256': sha(args.pass_log),
                  'script_sha256': sha(Path(__file__)), 'machine': platform.machine(),
                  'platform': platform.platform(), 'python': platform.python_version(),
                  'thread_limits': {key: os.getenv(key) for key in ('OPENBLAS_NUM_THREADS',
                                    'OMP_NUM_THREADS', 'VECLIB_MAXIMUM_THREADS', 'MKL_NUM_THREADS')}}
    failed = 0
    with args.output.open('x', encoding='utf-8') as out:
        for node, (seed, name) in sorted(wanted.items(), key=lambda item: (item[1][0], FAMILIES.index(item[1][1]))):
            row = {**provenance, 'nodeid': node}
            try:
                result = observe(seed, name)
            except Exception as error:
                row.update(status='unresolved', reason=f'{type(error).__name__}: {error}')
                failed += 1
            else:
                row.update(status='recovered', **result)
            out.write(json.dumps(row) + '\n')
            out.flush()
            os.fsync(out.fileno())
    print(f'{len(ids) - failed} recovered, {failed} unresolved in {args.output}')
    if failed:
        raise SystemExit(1)


if __name__ == '__main__':
    main()
