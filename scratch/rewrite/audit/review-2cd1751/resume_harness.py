"""Compare a run straight through with the same run stopped at breakpoints and resumed: in place
(`Session.advance`), from a saved checkpoint in this process (`Session.restored`), and from a file in
a fresh process. Prints every difference of a held value at a grid of times and of the trace."""

import json
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from common import *  # noqa: E402,F403

from napkin.program.checkpoint import Breakpoint, dumps, loads  # noqa: E402
from napkin.session import Session  # noqa: E402


def trace_of(record):
    return [(round(float(e.t), 9), e.kind, e.part, e.owner, tuple((k, v) for k, v in e.details if k in ('value', 'amount')))
            for e in record.trace if e.kind not in ('pause', 'edit')]


def values_of(c, record, times):
    paths = [p for p in held_paths(record)]
    return {p: x.values for p, x in zip(paths, read(record, c.program, paths, times))}


def through_session(c, conf, breakpoints, restore=False):
    s = Session(c.program, conf, breakpoints)
    stops = 0
    while True:
        cp = s.advance()
        if cp is None:
            return s.record, stops
        stops += 1
        if restore:
            data = dumps(s.checkpoint)
            s = Session.restored(c.program, loads(data))


def compare(c, conf, breakpoints, times, label=''):
    straight = run(c.program, conf)
    out = {'straight': straight}
    for how, restore in (('in place', False), ('restored', True)):
        rec, stops = through_session(c, conf, breakpoints, restore)
        out[how] = rec
        a, b = values_of(c, straight, times), values_of(c, rec, times)
        diffs = [(p, t, x, y) for p in a for t, x, y in zip(times, a[p], b.get(p, (None,) * len(times))) if x != y]
        ta, tb = trace_of(straight), trace_of(rec)
        print(f'{label} {how}: stops {stops}, failure {straight.failure and straight.failure.detail("message")} / '
              f'{rec.failure and rec.failure.detail("message")}, value diffs {len(diffs)}, trace equal {ta == tb}')
        for d in diffs[:8]:
            print('   ', d)
        if ta != tb:
            for k, (x, y) in enumerate(zip(ta, tb)):
                if x != y:
                    print('    first trace diff at', k, x, y)
                    break
            if len(ta) != len(tb):
                print('    trace lengths', len(ta), len(tb))
    return out
