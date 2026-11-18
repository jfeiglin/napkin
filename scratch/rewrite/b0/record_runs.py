"""A pytest plugin: a digest of every run of the timeline engine that a test makes.

    NAPKIN_RECORD=/tmp/base PYTHONPATH=$PWD:scratch/rewrite/b0 python -m pytest -p record_runs tests/engine/test_timeline.py
    python scratch/rewrite/b0/record_runs.py /tmp/base /tmp/mine

The first line runs tests and writes, for each run that a test makes with no derivative, one line
into a file of the folder `NAPKIN_RECORD`: the test, the number of the run in the test, and the
digest of every number of the result and of the state of the run (`bitwise.result_numbers`,
`bitwise.run_numbers`), or of the error that the run stops with. The second line compares two such
folders: each test that both have must have the same runs, bit for bit. A test that only one of
them has is named and not compared (a test of the derivatives has no place in the other).

`NAPKIN_RECORD_FULL=WORD` also writes the whole text of each run of the tests whose name holds the
word, into `full/` of the folder: two such texts show where two runs differ.

The record changes nothing of a run: it reads the fields of the run after it ends. A run with
directions (at the base commit) is not recorded, and does not count.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import sys
from pathlib import Path

OUT = os.environ.get('NAPKIN_RECORD')
FULL = os.environ.get('NAPKIN_RECORD_FULL')
state = {'test': '<no test>', 'count': 0, 'file': None}


def _write(kind, found):
    text = json.dumps(found, indent=1, allow_nan=False)
    test, index = state['test'], state['count']
    state['count'] += 1
    digest = hashlib.sha256(text.encode()).hexdigest()
    if state['file'] is None:
        folder = Path(OUT)
        folder.mkdir(parents=True, exist_ok=True)
        state['file'] = open(folder / f'{os.getpid()}.jsonl', 'a', encoding='utf-8')
    state['file'].write(json.dumps({'test': test, 'index': index, 'kind': kind, 'digest': digest}) + '\n')
    state['file'].flush()
    if FULL and FULL in test:
        folder = Path(OUT) / 'full'
        folder.mkdir(parents=True, exist_ok=True)
        name = re.sub(r'[^A-Za-z0-9_.-]+', '_', test)[-150:]
        (folder / f'{name}.{index}.json').write_text(text, encoding='utf-8')


def _numbers(run, result, problem):
    import bitwise

    if problem is not None:
        found = {'<error>': type(problem).__name__, 'message': str(problem)}
    else:
        found = {'result': bitwise.result_numbers(result)}
    try:
        found['state'] = bitwise.run_numbers(run)
    except bitwise.Hidden:
        raise
    except Exception as missing:
        # A run that stops before its start has no state to write.
        if problem is None:
            raise
        found['state'] = f'<{type(missing).__name__}>'
    return found


def pytest_configure(config):
    if not OUT:
        return
    from napkin.engine.timeline.run import Run

    original = Run.run

    def run(self):
        if getattr(self, 'directions', ()):
            return original(self)
        try:
            result = original(self)
        except Exception as problem:
            _write('error', _numbers(self, None, problem))
            raise
        _write('result', _numbers(self, result, None))
        return result

    Run.run = run


def pytest_runtest_setup(item):
    state['test'], state['count'] = item.nodeid, 0


def pytest_runtest_teardown(item):
    state['test'], state['count'] = f'<after {item.nodeid}>', 0


def read(folder):
    found = {}
    for path in sorted(Path(folder).glob('*.jsonl')):
        for line in path.read_text(encoding='utf-8').splitlines():
            item = json.loads(line)
            found.setdefault(item['test'], {})[item['index']] = (item['kind'], item['digest'])
    return {test: [runs[k] for k in sorted(runs)] for test, runs in found.items()}


def compare(one, other):
    a, b = read(one), read(other)
    both = sorted(a.keys() & b.keys())
    differ = [test for test in both if a[test] != b[test]]
    runs = sum(len(a[test]) for test in both)
    print(f'{len(both)} tests in both, with {runs} runs; {len(differ)} tests differ')
    for test in differ:
        places = [k for k, (x, y) in enumerate(zip(a[test], b[test])) if x != y]
        # A test that lost a run of its own (one with directions) has the other runs at other
        # places: then each run of the second is still a run of the first.
        among = 'each run of the second is one of the first' if set(b[test]) <= set(a[test]) else 'NEW RUNS'
        print(f'  differs: {test}: {len(a[test])} and {len(b[test])} runs, first at {places[:1]}; {among}')
    for name, only in (('first', sorted(a.keys() - b.keys())), ('second', sorted(b.keys() - a.keys()))):
        print(f'{len(only)} tests only in the {name}, with {sum(len((a | b)[test]) for test in only)} runs')
        for test in only:
            print(f'  only in the {name}: {test}')
    return 1 if differ else 0


if __name__ == '__main__':
    sys.exit(compare(*sys.argv[1:3]))
