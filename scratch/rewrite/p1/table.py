"""Prototype P1: the tables of FINDINGS.md from the records in /home/user/p1-data (not linted).

    /home/user/venvs/p1/bin/python scratch/rewrite/p1/table.py distance|fair

The last record of each (problem, method) is shown. Times are seconds, the best of the runs of the
record (three at 3,000 places, one at 30,000), with the load of the machine (4 shared cores).
"""

import json
import sys

DATA = '/home/user/p1-data'


def last(path, key):
    found = {}
    with open(path) as f:
        for line in f:
            record = json.loads(line)
            found[key(record)] = record
    return found


def e(v):
    return '-' if v is None else f'{v:.0e}' if isinstance(v, float) and v else ('0' if v == 0 else str(v))


def exact_errors():
    """The largest error against the exact references of each method (correct.jsonl)."""
    out = {}
    try:
        with open(f'{DATA}/correct.jsonl') as f:
            for line in f:
                r = json.loads(line)
                out.setdefault(r['method'], f"{r['worst_error']:.0e} ({r['failed']} of {r['passed'] + r['failed']} out)")
    except FileNotFoundError:
        pass
    return out


ALIAS = {'library-ldl': 'ldl', 'piqp+polish': 'polish:piqp', 'clarabel+polish': 'polish:clarabel'}


def distance(tags, methods):
    found = last(f'{DATA}/distance.jsonl', lambda r: (r['tag'], r['method']))
    exact = exact_errors()
    print('| problem | method | s | steps (stages) | status | rows | optima | level short | diff flows, levels '
          '| exact ref. | after polish: books W, equal, bounds | bitwise | load |')
    print('|' + '---|' * 13)
    for tag in tags:
        for method in methods:
            r = found.get((tag, method))
            if r is None:
                continue
            m, infos = r['measures'], r['infos']
            if isinstance(infos, dict):
                steps = '+'.join(str(s) for s in infos.get('newton', []))
                status = ','.join(sorted(set(infos.get('methods', []))))
            else:
                steps = '+'.join(str(i.get('iterations')) for i in infos)
                status = ','.join(str(i.get('status')).replace('PIQP_', '').lower() for i in infos)
            diff = '-' if m.get('diff flows') is None else f'{e(m.get("diff flows"))}, {e(m.get("diff others"))}'
            polished = f'{e(m.get("p books abs"))}, {e(m.get("p equal spread"))}, {e(m.get("p bounds abs"))}'
            print(
                f'| {tag} | {method} | {r["seconds"]:.2f} | {steps} | {status} | {e(m["rows"])} | {e(m["optima"])} | '
                f'{e(m.get("level short"))} | {diff} | {exact.get(ALIAS.get(method, method), "-")} | {polished} | '
                f'{r["bitwise"]} | {r["load"]} |'
            )


def distance_full(tags, methods):
    found = last(f'{DATA}/distance.jsonl', lambda r: (r['tag'], r['method']))
    print('| problem | method | s | iterations (stages) | status | rows | bounds | optima | level short | '
          'equal spread | books | diff flows | diff levels | bitwise | load |')
    print('|' + '---|' * 15)
    for tag in tags:
        for method in methods:
            r = found.get((tag, method))
            if r is None:
                continue
            m, infos = r['measures'], r['infos']
            if isinstance(infos, dict):
                steps = '+'.join(str(s) for s in infos.get('newton', []))
                status = ','.join(infos.get('methods', []))
            else:
                steps = '+'.join(str(i.get('iterations')) for i in infos)
                status = ','.join(str(i.get('status')) for i in infos)
            print(
                f'| {tag} | {method} | {r["seconds"]:.2f} | {steps} | {status} | {e(m["rows"])} | {e(m["bounds abs"])} | '
                f'{e(m["optima"])} | {e(m.get("level short"))} | {e(m.get("equal spread"))} | {e(m.get("books"))} | '
                f'{e(m.get("diff flows"))} | {e(m.get("diff others"))} | {r["bitwise"]} | {r["load"]} |'
            )


def fair(tags):
    found = last(f'{DATA}/fair.jsonl', lambda r: (r['tag'], r['variant'], r['tol'], r['fix'], r.get('updates', 100)))
    print('| problem | variant | tol | s | programs | levels | iterations | tight | renewals | level diff | '
          'near ties | failure | bitwise | load |')
    print('|' + '---|' * 14)
    for tag in tags:
        for (t, variant, tol, fix, updates), r in found.items():
            if t != tag or fix != 1e-7 or updates != 100:
                continue
            print(
                f'| {tag} | {variant} | {tol:g} | {r["seconds"]:.2f} | {r["programs"]} | {r["levels"]} | {r["iterations"]} | '
                f'{r["tight"]} | {r["renewals"]} | {e(r.get("level diff"))} | {r.get("near tie count", "-")} | '
                f'{(r["failure"] or "")[:60]} | {r["bitwise"]} | {r["load"]} |'
            )


if __name__ == '__main__':
    bench = [f'bench-{n}-{s}' for n in (3000, 30000) for s in ('normal', 'shortage', 'damaged', 'global')]
    engine = ['engine-3000-normal', 'engine-30000-normal']
    if sys.argv[1] == 'distance':
        methods = ['library', 'library-ldl', 'library-loose', 'clarabel', 'clarabel-box', 'piqp', 'piqp-box',
                   'piqp-long-box', 'piqp+polish', 'osqp', 'osqp-tight']  # fmt: skip
        distance(bench[:4] + engine[:1] + bench[4:] + engine[1:], methods)
    else:
        fair(bench[:4] + engine[:1] + bench[4:] + engine[1:])
