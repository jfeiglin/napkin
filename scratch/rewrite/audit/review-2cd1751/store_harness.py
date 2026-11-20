"""Compare a run to a shorter horizon with a longer run cut back: fresh, and through the run store
cold (only the short request) and warm (the long run first)."""

import sys
import tempfile
from dataclasses import replace
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from common import *  # noqa: E402,F403

from napkin import store  # noqa: E402
from napkin.program.config import Request  # noqa: E402


def outcome(record):
    stop = record.stop
    return ('finished',) if stop is None else (stop.kind, float(stop.t), stop.detail('message'))


def trace_of(record):
    return [(round(float(e.t), 9), e.round, e.kind, e.part, e.owner) for e in record.trace]


def values_of(c, record, times, paths=None):
    paths = held_paths(record) if paths is None else paths
    return {p: x.values for p, x in zip(paths, read(record, c.program, paths, times))}


def cut_back(text, short, long, times, units=UNITS, request=None, label='', tol=0.0):
    c = compile_text(text, units)
    base = c.configuration
    s_conf = replace(base, request=Request(short) if request is None else replace(request, horizon=short))
    l_conf = replace(base, request=Request(long) if request is None else replace(request, horizon=long))
    fresh_short = run(c.program, s_conf)
    fresh_long = run(c.program, l_conf)
    with tempfile.TemporaryDirectory() as d:
        with store.use(Path(d) / 'cold'):
            cold = store.run(c.program, s_conf)
        with store.use(Path(d) / 'warm'):
            store.run(c.program, l_conf)
            warm = store.run(c.program, s_conf)
    paths = held_paths(fresh_short)
    ref = values_of(c, fresh_short, times, paths)
    print(f'{label}: outcome fresh short {outcome(fresh_short)} | long {outcome(fresh_long)} | cold {outcome(cold)} | warm {outcome(warm)}')
    for name, rec in (('long cut', fresh_long), ('cold', cold), ('warm', warm)):
        got = values_of(c, rec, times, paths)
        diffs = [(p, t, a, b) for p in paths for t, a, b in zip(times, ref[p], got[p]) if not close_enough(a, b, tol) and a != b]
        tr = [e for e in trace_of(rec) if e[0] <= short]
        tr_ref = trace_of(fresh_short)
        same_trace = tr == tr_ref
        print(f'   {name}: value diffs {len(diffs)}; trace (to the short horizon) equal: {same_trace}')
        for dd in diffs[:6]:
            print('      ', dd)
        if not same_trace:
            for k, (x, y) in enumerate(zip(tr_ref, tr)):
                if x != y:
                    print('       first trace diff', k, x, y)
                    break
            if len(tr) != len(tr_ref):
                print('       trace lengths', len(tr_ref), len(tr))
    return c, fresh_short, fresh_long, cold, warm
