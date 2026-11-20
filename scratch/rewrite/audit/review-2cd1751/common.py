"""Shared helpers of the review of 2cd1751. Run each reproduction from /home/user/napkin-R with
PYTHONPATH=$PWD NAPKIN_STORE=off /home/user/napkin/.venv/bin/python scratch/rewrite/audit/review-2cd1751/<file>.py"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[4]))

from napkin.engine import read, run  # noqa: E402
from napkin.model.compile import compile_text  # noqa: E402
from tests.program.examples import UNITS as BASE  # noqa: E402

UNITS = {**BASE, 'day': ({'time': 1}, 24), 'min': ({'time': 1}, 1 / 60), 'mL': ({'volume': 1}, 0.001),
         'kL': ({'volume': 1}, 1000)}


def compiled(text, units=UNITS, **kw):
    return compile_text(text, units, **kw)


def go(text, paths, times, units=UNITS, configuration=None):
    c = compile_text(text, units)
    conf = configuration if configuration is not None else c.configuration
    r = run(c.program, conf)
    return c, r, {p: x.values for p, x in zip(paths, read(r, c.program, list(paths), list(times)))}


def held_paths(record):
    from napkin.commands.run import held
    return held(record)


def oracle(c, configuration=None, stops=()):
    """(run, failure) of the reference interpreter."""
    from tests.reference.from_program import run_of
    return run_of(c.program, configuration if configuration is not None else c.configuration, stops)


def oracle_value(c, orun, path, t):
    from tests.reference.from_program import value_at
    from napkin.engine.timeline.record import key_of
    v = value_at(orun, c.program, key_of(c.program, path), t)
    try:
        return float(v)
    except (TypeError, ValueError):
        return v


def show(title, value):
    print(f'{title}: {value}')


def close_enough(a, b, tol=1e-6):
    if isinstance(a, bool) or isinstance(b, bool) or isinstance(a, str) or isinstance(b, str):
        return a == b
    try:
        a, b = float(a), float(b)
    except (TypeError, ValueError):
        return repr(a) == repr(b)
    return abs(a - b) <= tol * max(1.0, abs(a), abs(b))


def crosscheck(text, times, configuration=None, units=UNITS, paths=None, quiet=False):
    """Engine against the reference interpreter on every held path at the times: the differences."""
    c = compile_text(text, units)
    conf = configuration if configuration is not None else c.configuration
    r = run(c.program, conf)
    ps = paths if paths is not None else held_paths(r)
    eng = {p: x.values for p, x in zip(ps, read(r, c.program, ps, list(times)))}
    orun, failure = oracle(c, conf)
    diffs = []
    if (r.failure is None) != (failure is None):
        diffs.append(('failure', r.failure and r.failure.detail('message'), failure))
    if orun is not None:
        for p in ps:
            for t, v in zip(times, eng[p]):
                if r.failure is not None and t >= float(r.failure.t):
                    continue
                try:
                    o = oracle_value(c, orun, p, t)
                except Exception as e:  # noqa: BLE001
                    o = f'<{type(e).__name__}: {str(e)[:60]}>'
                if not close_enough(v, o):
                    diffs.append((p, t, v, o))
    if not quiet:
        print('engine failure:', r.failure and r.failure.detail('message'), '| oracle failure:', failure)
        for d in diffs:
            print('  DIFF', d)
    return c, r, eng, diffs


REPO = Path(__file__).resolve().parents[4]
LITRE = '{"L": {"dimensions": {"volume": 1}, "scale": 1, "description": "A litre."}}'


def package(folder, files):
    """Write a package: {relative path: text}."""
    folder = Path(folder)
    for name, text in files.items():
        (folder / name).parent.mkdir(parents=True, exist_ok=True)
        (folder / name).write_text(text, encoding='utf-8')
    return folder


def cli(*args, cwd=None):
    """Run `python -m napkin ARGS` in a fresh process, with this checkout on the path and the run
    store off: (exit code, stdout, stderr)."""
    import os
    import subprocess
    env = {**os.environ, 'PYTHONPATH': str(REPO), 'NAPKIN_STORE': 'off'}
    done = subprocess.run([sys.executable, '-m', 'napkin', *map(str, args)], capture_output=True, text=True,
                          env=env, cwd=cwd, input='')
    return done.returncode, done.stdout, done.stderr
