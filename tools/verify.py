"""Check that an engine change keeps the results of the runs: python -m tools.verify COMMAND.

- `capture OUT [--set quick|all|timing] [--jobs N]`: run each case of the set with this checkout and
  write one file for each case to the folder OUT.
- `baseline COMMIT OUT [--set ...] [--jobs N]`: the same, with a clean worktree of COMMIT.
- `compare BASE OTHER [--exact]`: compare two captures, case by case.
- `check BASE [--set ...] [--jobs N] [--exact]`: capture this checkout to a temporary folder and compare
  it with BASE.

Compare captures of the same machine only: two platforms can differ in the last bits of their maths.

**A capture** of a case holds the run's record as the checkpoint format writes it (`encode`), its time,
and, for a case with breakpoints, each checkpoint of the stops and the record of the run resumed from
them, each stop through bytes, as another process would. A checkpoint holds the hash of the engine's
code (`Checkpoint.engine`), which every edit of the engine changes: the capture checks that the hash is
the one of the code that made it, and keeps the checkpoint with that field blanked.

**The exact comparison** (`--exact`) wants the same bytes: each record, each checkpoint, each resumed
record. On a difference it shows the first history, trace entry or field that differs.

**The numerical comparison** (the default) checks what a change within tolerance must keep:

- decisions: the trace entries that are decisions (`DECISIONS`), in order, with the same kind, part and
  owner, and times that agree within `MOVED`; the failure; the near-ties, which it lists;
- values: each history of the base at the start and the middle of each piece of either side, within
  `RELATIVE` times the largest of the history's scale and the two values. A time in the window of a jump
  that moved (the two times of the jump, padded by `crossing`) is not compared: the decision check
  already says where the jump went.
"""

from __future__ import annotations

import argparse
import concurrent.futures
import gzip
import json
import os
import subprocess
import sys
import tempfile
import time
from bisect import bisect_right
from dataclasses import dataclass, replace
from itertools import pairwise
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DECISIONS = ('start', 'finish', 'commit', 'fire', 'move', 'failure', 'draw')
MOVED = 1e-6  # h, plus 1e-9 of the time: two decision times that agree
RELATIVE = 1e-4
QUICK_HOURS = 24.0
QUICK_SHORTER = {'heat_wave_blackout': 2.0}  # its first hours are slow; 0b measures it alone
UNITS = {'L': {'volume': 1}, 'h': {'time': 1}}


@dataclass(frozen=True)
class Case:
    name: str
    source: str  # a path of the checkout, or 'fixture:NAME'
    run: str | None = None
    hours: float | None = None  # a shorter horizon
    keys: tuple[str, ...] = ()  # a selected record of these paths
    pieces: int | None = None  # a budget of pieces
    breakpoints: tuple[str, ...] = ()
    numerics: tuple[tuple[str, float], ...] = ()  # other numerical settings (`--rtol`, `--atol-factor`)


# ---- the cases -------------------------------------------------------------------------------------

FIXTURES = {
    # Two rounds at one moment: the second clears what the first wrote (tests/engine/test_budget_rule.py).
    'two_rounds': """scenario "Two rounds at the same moment"
    horizon 2 h
box:
    x = 0
    reading = formula(2 * this.x)
    tick = event():
        after 1 h:
            this.x = 1
            this.clear_flag.start()
    clear_flag = event():
        after 0 h:
            this.x = 0
box.tick.start()
""",
    # A Sparse stock with a moment inside its step (tests/engine/test_sparse_prefix.py).
    'sparse_tank': """scenario "A moment inside a step"
    horizon 2 h
tank:
    water: L = 10 L
    flow fill: SOURCE -> this.water
        request = formula(1 L/h + t * 1 L/h/h)
    flow drain: this.water -> SINK
        request = formula(0.5 L/h + t * 0.25 L/h/h)
    tick = event():
        after 1 h:
            this.pause.start()
    pause = event():
        after 0 h
tank.tick.start()
""",
    # Pieces that a budget stops (tests/engine/test_budget_rule.py).
    'budget_tank': """scenario "A stock with unpublished incoming pieces"
    horizon 2 h
tank:
    water: L = 10 L
    flow fill: SOURCE -> this.water
        request = formula(1 L/h + t * 1 L/h/h)
    flow spare: SOURCE -> this.water
        request = 0.1 L/h
    flow drain: this.water -> SINK
        request = formula(0.5 L/h + t * 0.25 L/h/h)
clock:
    marker = 0
    tick = event():
        after 0.75 h:
            this.marker = 1
        after 0.25 h:
            this.marker = 2
clock.tick.start()
""",
    # A stock that a member reads after its producer retired (tests/engine/test_late_recording.py).
    'meter': """scenario "Meter filled before the first observation"
    horizon 1 h
yard:
    meter: L = 1 L
    pump = event():
        flow first: SOURCE -> this.meter
            request = formula(this.meter / (1 h))
        flow second: SOURCE -> this.meter
            request = formula(this.meter / (1 h))
        after 0.2 h
    prior = formula(this.meter * 3)
    worker = event():
        observation = formula(this.prior + 1 L)
        after 0.2 h
    total = formula(sum(this.worker.occurrences.observation))
    clock = event():
        after 0.3 h:
            this.worker.start()
    watch = event():
        after 0.3 h
yard.pump.start()
yard.clock.start()
yard.watch.start()
""",
}

FIXTURE_CASES = (
    Case('fixture:two_rounds', 'fixture:two_rounds', keys=('box.reading',), pieces=1),
    Case(
        'fixture:two_rounds@break',
        'fixture:two_rounds',
        keys=('box.reading',),
        pieces=1,
        breakpoints=('box.clear_flag.step[0]',),
    ),
    Case('fixture:sparse_tank@break', 'fixture:sparse_tank', breakpoints=('tank.pause.step[0]',)),
    Case('fixture:budget_tank', 'fixture:budget_tank', keys=('tank.water',), pieces=4),
    # A budget that is just enough, and a stop before the end.
    Case(
        'fixture:budget_tank@break',
        'fixture:budget_tank',
        keys=('tank.water',),
        pieces=5,
        breakpoints=('clock.tick.step[0]',),
    ),
    Case('fixture:meter@break', 'fixture:meter', keys=('yard.total',), breakpoints=('yard.watch.step[0]',)),
)

PROTOTYPE = 'prototypes/cyber_workforce_sketch/model.scn'
TIMING = (
    Case('timing:heat_wave', 'scenarios/heat_wave_blackout'),
    Case('timing:washington_dc', 'scenarios/water_controls_wipe/variants/washington_dc'),
    Case('timing:juneau', 'scenarios/water_controls_wipe/variants/juneau'),
    Case('timing:cyber_wartime', 'scenarios/cyber_learning_loop/model.scn', run='wartime'),
    Case('timing:prototype_0.5y', PROTOTYPE, hours=4380.0),
    Case('timing:prototype_1y', PROTOTYPE, hours=8760.0),
    Case('timing:prototype_5y', PROTOTYPE, hours=43800.0),
)


def _examples():
    return [
        Case(f'example:{p.name}', str(p.relative_to(ROOT)))
        for p in sorted((ROOT / 'examples').iterdir())
        if (p / 'model.scn').exists()
    ]


def _catalogue():
    """(owner, entry, run names) of each model of the catalogue."""
    sys.path.insert(0, str(ROOT))
    from napkin import load_scenario
    from tools import catalogue

    found = []
    for owner, entry in catalogue.entries(ROOT).items():
        model = load_scenario(str(entry))
        found.append((owner, str(Path(entry).relative_to(ROOT)), [run.name for run in model.declared.runs]))
    return found


def cases(chosen):
    if chosen == 'timing':
        return list(TIMING)
    found = _examples() + list(FIXTURE_CASES)
    for owner, entry, runs in _catalogue():
        if chosen == 'quick':
            hours = QUICK_SHORTER.get(owner, QUICK_HOURS)
            found.append(Case(f'{owner}@{hours:g}h', entry, hours=hours))
            continue
        found.append(Case(owner, entry))
        found += [Case(f'{owner}:{run}', entry, run=run) for run in runs]
        found.append(Case(f'{owner}@selected', entry, keys=('*',)))
    if chosen == 'all':
        found.append(Case('prototype@0.5y', PROTOTYPE, hours=4380.0))
    return found


# ---- capturing -------------------------------------------------------------------------------------


def _model(case):
    import napkin
    from napkin.model.compile import compile_text

    if case.source.startswith('fixture:'):
        return compile_text(FIXTURES[case.source.split(':', 1)[1]], UNITS)
    return napkin.load_scenario(str(ROOT / case.source))


def _configuration(model, case, keys):
    configuration = model.configure(case.run) if case.run is not None else model.configuration
    request = configuration.request
    if case.hours is not None:
        request = replace(request, horizon=min(float(request.horizon), case.hours))
    if keys:
        request = replace(request, everything=False, keys=keys)
    if case.pieces is not None:
        request = replace(request, pieces=case.pieces)
    numerics = replace(configuration.numerics, **dict(case.numerics))
    return replace(configuration, request=request, numerics=numerics)


def _keys(model, case):
    from napkin.commands.run import named
    from napkin.engine import run
    from napkin.engine.timeline.record import key_of

    if not case.keys:
        return ()
    paths = case.keys
    if paths == ('*',):
        # Three named values, spread over the sorted names of a full run: no choice of this tree's code.
        whole = run(model.program, _configuration(model, replace(case, keys=()), ()))
        names = sorted(named(model, whole))
        paths = tuple(dict.fromkeys(names[i] for i in (0, len(names) // 2, len(names) - 1))) if names else ()
    return tuple(key_of(model.program, path) for path in paths)


def _blanked(raw, engine):
    head, _, body = raw.partition(b'\n')
    data = json.loads(body)
    if data.get('engine') != engine:
        raise ValueError(f'a checkpoint holds the engine hash {data.get("engine")!r}, not {engine!r}')
    data['engine'] = '<engine>'
    return head.decode() + '\n' + json.dumps(data, separators=(',', ':'))


def capture_one(case):
    from napkin.engine import run
    from napkin.engine.timeline.checkpoints import _engine_version
    from napkin.program.checkpoint import Breakpoint, dumps, encode, loads
    from napkin.session import Session

    os.environ.setdefault('NAPKIN_STORE', 'off')
    data = {'case': case.name, 'error': None, 'record': None, 'checkpoints': [], 'resumed': None}
    start = time.perf_counter()
    try:
        model = _model(case)
        keys = _keys(model, case)
        configuration = _configuration(model, case, keys)
        began = time.perf_counter()
        record = run(model.program, configuration)
        data['seconds'] = time.perf_counter() - began
        data['record'] = encode(record)
        if case.breakpoints:
            engine = _engine_version()
            session = Session(model.program, configuration, [Breakpoint(at) for at in case.breakpoints])
            checkpoint = session.advance()
            while checkpoint is not None:
                raw = dumps(checkpoint)
                data['checkpoints'].append(_blanked(raw, engine))
                session = Session.restored(model.program, loads(raw))
                checkpoint = session.advance()
            data['resumed'] = encode(session.record)
    except Exception as problem:  # a case that fails is a result too
        data['error'] = f'{type(problem).__name__}: {problem}'
    data.setdefault('seconds', time.perf_counter() - start)
    return data


def _file(out, name):
    return Path(out) / (name.replace('/', '_').replace(':', '_').replace('@', '_at_') + '.json.gz')


def capture(out, chosen, jobs, numerics=()):
    out = Path(out)
    out.mkdir(parents=True, exist_ok=True)
    found = [replace(case, numerics=numerics) for case in cases(chosen)]
    with concurrent.futures.ProcessPoolExecutor(max_workers=jobs) as pool:
        for data in pool.map(capture_one, found):
            _file(out, data['case']).write_bytes(gzip.compress(json.dumps(data).encode()))
            print(f'{data["seconds"]:8.2f}s  {data["case"]}  {data["error"] or ""}', flush=True)
    return out


def baseline(commit, out, chosen, jobs):
    out = Path(out).resolve()
    with tempfile.TemporaryDirectory() as folder:
        tree = Path(folder) / 'tree'
        subprocess.run(['git', '-C', str(ROOT), 'worktree', 'add', '--detach', str(tree), commit], check=True)
        try:
            # The baseline's own code runs its cases; this file chooses them and compares.
            (tree / 'tools' / 'verify.py').write_bytes(Path(__file__).read_bytes())
            command = [
                sys.executable,
                '-B',
                '-m',
                'tools.verify',
                'capture',
                str(out),
                '--set',
                chosen,
                '--jobs',
                str(jobs),
            ]
            subprocess.run(command, cwd=tree, check=True)
        finally:
            subprocess.run(['git', '-C', str(ROOT), 'worktree', 'remove', '--force', str(tree)], check=True)


# ---- comparing -------------------------------------------------------------------------------------


def _load(path):
    return json.loads(gzip.decompress(Path(path).read_bytes()))


def _number(value):
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, int | float):
        return float(value)
    if isinstance(value, dict) and 'fraction' in value:
        numerator, denominator = value['fraction']
        return numerator / denominator
    if isinstance(value, dict) and 'float' in value:
        return float(value['float'])
    return None


def _series(coefficients, u):
    after = latest = 0.0
    for c in reversed(coefficients[1:]):
        latest, after = c + 2.0 * u * latest - after, latest
    return coefficients[0] + u * latest - after if coefficients else 0.0


def _at(pieces, starts, t):
    """The value of a history (its JSON pieces) at time t: a number, or another value as JSON."""
    i = bisect_right(starts, t) - 1
    if i < 0:
        return 'before'
    piece = pieces[i]
    elapsed = t - _number(piece['t'])
    base = _number(piece['value'])
    if base is None:
        return json.dumps(piece['value'], sort_keys=True)
    curve = piece.get('curve')
    if curve:
        length, c = float(curve['length']), curve['coefficients']
        return base + _series(c, 2.0 * elapsed / length - 1.0) - _series(c, -1.0)
    return base + float(_number(piece['rate']) or 0.0) * elapsed


def _histories(record):
    return {json.dumps(h['key'], sort_keys=True): h['pieces'] for h in record['histories']}


def _jumps(pieces, starts):
    """The times at which a history jumps (its value at a piece's start is not where the piece before
    ends)."""
    found = []
    for k in range(1, len(pieces)):
        t = _number(pieces[k]['t'])
        before = _at(pieces[k - 1 : k], starts[k - 1 : k], t)
        here = _number(pieces[k]['value'])
        if isinstance(before, float) and here is not None:
            if abs(before - here) > RELATIVE * max(abs(before), abs(here), 1e-300):
                found.append(t)
        elif before != json.dumps(pieces[k]['value'], sort_keys=True):
            found.append(t)
    return found


def _windows(a, b, crossing):
    """The windows of the jumps that moved: each jump of one side to the nearest of the other."""
    windows = []
    for one, other in ((a, b), (b, a)):
        for t in one:
            near = min(other, key=lambda s: abs(s - t), default=None)
            if near is not None and near != t:
                windows.append((min(t, near) - crossing, max(t, near) + crossing))
    return windows


def numerical(base, other, crossing=1e-8):
    """The differences of two records (JSON) that a change within tolerance must not make, and notes."""
    stops, notes = [], []
    decisions = [[e for e in r['trace'] if e['kind'] in DECISIONS] for r in (base, other)]
    worst = 0.0
    for k, (x, y) in enumerate(zip(*decisions)):
        same = (x['kind'], x['part'], x['owner']) == (y['kind'], y['part'], y['owner'])
        if same and x['kind'] == 'draw' and x['details'] != y['details']:
            same = False  # a draw is decided by its value
        if not same:
            stops.append(
                f'decision {k} differs: {x["kind"]} {x["part"]} {x["owner"]} at {x["t"]} h, now '
                f'{y["kind"]} {y["part"]} {y["owner"]} at {y["t"]} h'
            )
            break
        moved = abs(_number(x['t']) - _number(y['t']))
        worst = max(worst, moved)
        if moved > MOVED + 1e-9 * abs(_number(x['t'])):
            stops.append(
                f'decision {k} moved: {x["kind"]} {x["part"]} {x["owner"]} from {x["t"]} to {y["t"]} h'
            )
    if len(decisions[0]) != len(decisions[1]) and not stops:
        stops.append(f'{len(decisions[0])} decisions, now {len(decisions[1])}')
    if worst:
        notes.append(f'decision times moved by up to {worst:.3g} h')
    failures = [
        None if r['failure'] is None else (r['failure']['kind'], r['failure']['part']) for r in (base, other)
    ]
    if failures[0] != failures[1]:
        stops.append(f'failure {failures[0]}, now {failures[1]}')
    ties = [
        [(e['kind'], e['part'], e['owner']) for e in r['trace'] if any(n == 'near' for n, _ in e['details'])]
        for r in (base, other)
    ]
    if ties[0] != ties[1]:
        notes.append(f'near-ties: {len(ties[0])}, now {len(ties[1])}')
    histories = [_histories(r) for r in (base, other)]
    if histories[0].keys() != histories[1].keys():
        only = sorted(histories[0].keys() ^ histories[1].keys())
        stops.append(f'the histories differ in names: {only[:3]}')
    skipped = 0
    for name in sorted(histories[0].keys() & histories[1].keys()):
        p, q = histories[0][name], histories[1][name]
        if p == q:
            continue
        ps, qs = [_number(x['t']) for x in p], [_number(x['t']) for x in q]
        windows = _windows(_jumps(p, ps), _jumps(q, qs), crossing)
        times = sorted(set(ps) | set(qs))
        grid = times + [0.5 * (s + t) for s, t in pairwise(times)]
        values = [v for v in (_at(p, ps, t) for t in grid) if isinstance(v, float)]
        scale = max(map(abs, values), default=0.0)
        for t in grid:
            if any(lo <= t <= hi for lo, hi in windows):
                skipped += 1
                continue
            a, b = _at(p, ps, t), _at(q, qs, t)
            if isinstance(a, float) and isinstance(b, float):
                if abs(a - b) > RELATIVE * max(scale, abs(a), abs(b)):
                    stops.append(f'{name} at {t} h: {a!r}, now {b!r}')
                    break
            elif a != b:
                stops.append(f'{name} at {t} h: {a}, now {b}')
                break
    if skipped:
        notes.append(f'{skipped} times in the windows of moved jumps')
    return stops, notes


def _first_difference(x, y):
    """The first history or trace entry of two records (JSON) that differs, or of the records of two
    checkpoints, or else the first field."""
    if 'histories' not in x:
        if x.get('record') != y.get('record'):
            return f'its record: {_first_difference(x["record"], y["record"])}'
        return next((f'field {field} differs' for field in x if x[field] != y.get(field)), 'the bytes differ')
    for name, pieces in _histories(x).items():
        other = _histories(y).get(name)
        if other != pieces:
            if other is None:
                return f'history {name} is gone'
            k = next(
                (i for i, (a, b) in enumerate(zip(pieces, other)) if a != b), min(len(pieces), len(other))
            )
            return f'history {name}, piece {k}: {pieces[k] if k < len(pieces) else None} -> {other[k] if k < len(other) else None}'
    for k, (a, b) in enumerate(zip(x['trace'], y['trace'])):
        if a != b:
            return f'trace entry {k}: {a} -> {b}'
    for field in x:
        if x[field] != y.get(field):
            return f'field {field} differs'
    return 'the bytes differ'


def compare_one(base, other, exact):
    """(the case's differences, its notes)."""
    if base['error'] or other['error']:
        if base['error'] == other['error']:
            return [], [f'both fail: {base["error"]}']
        return [f'error {base["error"]!r}, now {other["error"]!r}'], []
    pairs = [('record', base['record'], other['record']), ('resumed', base['resumed'], other['resumed'])]
    if len(base['checkpoints']) != len(other['checkpoints']):
        return [f'{len(base["checkpoints"])} checkpoints, now {len(other["checkpoints"])}'], []
    pairs += [
        (f'checkpoint {k}', a, b) for k, (a, b) in enumerate(zip(base['checkpoints'], other['checkpoints']))
    ]
    stops, notes = [], []
    for label, a, b in pairs:
        if a == b:
            continue
        if a is None or b is None:
            stops.append(f'{label}: one side has none')
            continue
        x = json.loads(a.partition('\n')[2] if label.startswith('checkpoint') else a)
        y = json.loads(b.partition('\n')[2] if label.startswith('checkpoint') else b)
        if exact:
            stops.append(f'{label}: {_first_difference(x, y)}')
            continue
        if label.startswith('checkpoint'):
            x, y = x['record'], y['record']
        found, said = numerical(x, y)
        stops += [f'{label}: {s}' for s in found]
        notes += [f'{label}: {s}' for s in said]
    return stops, notes


def compare(base, other, exact):
    base, other = Path(base), Path(other)
    names = sorted(p.name for p in base.glob('*.json.gz'))
    failed = 0
    timings = []
    for name in names:
        if not (other / name).exists():
            print(f'MISSING  {name}')
            failed += 1
            continue
        x, y = _load(base / name), _load(other / name)
        stops, notes = compare_one(x, y, exact)
        timings.append((x['case'], x.get('seconds', 0.0), y.get('seconds', 0.0)))
        if stops:
            failed += 1
            print(f'DIFFERS  {x["case"]}')
            for line in stops[:5]:
                print(f'    {line[:300]}')
        for line in notes[:3]:
            print(f'   note  {x["case"]}: {line[:300]}')
    total = [sum(t[1] for t in timings), sum(t[2] for t in timings)]
    print(
        f'{len(names) - failed} of {len(names)} cases agree ({"exact" if exact else "numerical"}); '
        f'run time {total[0]:.1f} s -> {total[1]:.1f} s'
    )
    slow = sorted(timings, key=lambda t: -t[1])[:8]
    for case, a, b in slow:
        print(f'   time  {case}: {a:.2f} s -> {b:.2f} s')
    return failed


def main(argv=None):
    parser = argparse.ArgumentParser(prog='python -m tools.verify', description=__doc__.split('\n')[0])
    commands = parser.add_subparsers(dest='command', required=True)
    for name in ('capture', 'baseline', 'check'):
        command = commands.add_parser(name)
        if name == 'baseline':
            command.add_argument('commit')
        command.add_argument('folder')
        command.add_argument('--set', default='quick', choices=('quick', 'all', 'timing'))
        command.add_argument('--jobs', type=int, default=max(1, (os.cpu_count() or 2) - 1))
        command.add_argument('--rtol', type=float, help='another relative tolerance for every case')
        command.add_argument('--atol-factor', type=float, help='another absolute tolerance factor')
        if name == 'check':
            command.add_argument('--exact', action='store_true')
    command = commands.add_parser('compare')
    command.add_argument('base')
    command.add_argument('other')
    command.add_argument('--exact', action='store_true')
    options = parser.parse_args(argv)
    numerics = tuple(
        (name, value)
        for name, value in (
            ('rtol', getattr(options, 'rtol', None)),
            ('atol_factor', getattr(options, 'atol_factor', None)),
        )
        if value is not None
    )
    if options.command == 'capture':
        capture(options.folder, options.set, options.jobs, numerics)
        return 0
    if options.command == 'baseline':
        baseline(options.commit, options.folder, options.set, options.jobs)
        return 0
    if options.command == 'compare':
        return 1 if compare(options.base, options.other, options.exact) else 0
    with tempfile.TemporaryDirectory() as folder:
        capture(folder, options.set, options.jobs, numerics)
        return 1 if compare(options.folder, folder, options.exact) else 0


if __name__ == '__main__':
    sys.exit(main())
