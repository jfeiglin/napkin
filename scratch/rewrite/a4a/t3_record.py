"""Task 3 of brief A4a: what a run records.

    python t3_record.py lag OUT              two histories with the same readings and other means
    python t3_record.py scale OUT P R        the size and the cost of the record with P places and R
                                             routes: ten reductions and five rows, and everything
    python t3_record.py today OUT            what the present engine keeps: the trajectory of a run
                                             with each row written out, and the record of the table
                                             path (`record=True`) with 35,000 rows, with the cost
                                             of a report with a lag. Needs the base commit on
                                             PYTHONPATH (the copy with 01_id_column.patch).

Each part prints what it finds and writes OUT/<part>….json. `measure.py` runs them all.
"""

from __future__ import annotations

import io
import json
import os
import pickle
import resource
import sys
import time
import zlib
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import model  # noqa: E402
import record  # noqa: E402


def load():
    return [round(x, 2) for x in os.getloadavg()]


def save(out, name, data):
    out = Path(out)
    out.mkdir(parents=True, exist_ok=True)
    (out / f'{name}.json').write_text(json.dumps(data, indent=1, default=float))


def best(function, runs=3):
    times = []
    for _ in range(runs):
        start = time.perf_counter()
        found = function()
        times.append(time.perf_counter() - start)
    return min(times), found


# ---- histories, not readings ----------------------------------------------------------------------


def lag(out):
    """A tally that only rises, read at 0, 6 and 12 h, and its mean over the window from 6 h ago to
    2 h ago, at 12 h. Two runs add the same 8 L, one at 7 h and one at 9 h."""
    early, late = record.History(), record.History()
    early.add(0.0, 0.0)
    early.add(7.0, 8.0)
    late.add(0.0, 0.0)
    late.add(9.0, 8.0)
    times = [0.0, 6.0, 12.0]
    found = {
        'readings_early': [early.at(t) for t in times], 'readings_late': [late.at(t) for t in times],
        'window': [6.0, 10.0],
        'mean_early': early.mean(6.0, 10.0), 'mean_late': late.mean(6.0, 10.0),
    }
    print(found)
    save(out, 'lag', found)


# ---- the record at scale ----------------------------------------------------------------------------


def request(built, extremes=True):
    """The request of the measurement: ten reductions over the tables, and five rows."""
    P = built.places.n
    stock = built.stores.place(built.places, 'stock', np.arange(P))
    used = built.stores.place(built.places, 'used', np.arange(P))
    critical = np.flatnonzero(built.places.cols['critical'])
    carried = np.arange(built.carried, built.carried + built.routes.n)
    use = np.arange(built.use, built.use + P)
    reductions = [
        record.SumOfStores('held = formula(sum(Place.instances.stock))', stock),
        record.SumOfStores('used_total = formula(sum(Place.instances.used))', used),
        record.SumOfStores('critical_held = formula(sum(Place.instances.where(critical).stock))', stock[critical]),
        record.CountOfStores('empty_places = formula(count(Place.instances.empty))', stock, 0.0),
        record.CountOfStores('low_places = formula(count(Place.instances.low))', stock, 10.0),
        record.CountOfStores('any_critical_empty = formula(any(Place.instances.where(critical).empty))', stock[critical], 0.0, any=True),
        record.SumOfFlows('carried_now = formula(sum(Route.instances.carried.actual_rate))', carried),
        record.SumOfFlows('unmet_use = formula(sum(Place.instances.unmet))', use, unmet=True),
    ]
    if extremes:
        reductions += [
            record.Extreme('fullest = formula(max(Place.instances.stock))', stock),
            record.Extreme('emptiest = formula(min(Place.instances.stock))', stock, least=True, bound=0.0),
        ]
    five = np.linspace(0, P - 1, 5).astype(int)
    rows = np.concatenate([stock[five], used[five]])
    return record.Recorder(rows=rows, flow_rows=use[five], reductions=reductions), five


def sizes(recorder):
    arrays = recorder.arrays()
    raw = sum(a.nbytes for a in arrays.values())
    start = time.perf_counter()
    buffer = io.BytesIO()
    np.savez_compressed(buffer, **arrays)
    packed = time.perf_counter() - start
    return arrays, {'pieces': recorder.pieces(), 'bytes': raw, 'bytes_packed': buffer.getbuffer().nbytes, 'pack_s': packed}


def table_at(arrays, t):
    """Every store at a time, from the table of a record with everything."""
    first = arrays['stores/first']
    times, y, rate = arrays['stores/t'], arrays['stores/y'], arrays['stores/rate']
    S = len(first) - 1
    store = np.repeat(np.arange(S), np.diff(first))
    span = float(times.max()) + 2.0
    k = np.searchsorted(store * span + times, np.arange(S) * span + t, side='right') - 1
    return y[k] + rate[k] * (t - times[k])


def flows_at(arrays, t):
    first, times, rate = arrays['flows/first'], arrays['flows/t'], arrays['flows/rate']
    F = len(first) - 1
    flow = np.repeat(np.arange(F), np.diff(first))
    span = float(times.max()) + 2.0
    return rate[np.searchsorted(flow * span + times, np.arange(F) * span + t, side='right') - 1]


def scale(out, places, routes, horizon=48.0, runs=3):
    folder = model.write(Path(out) / 'record' / f'{places}_{routes}', *model.synthetic(places, routes, seed=0), horizon=horizon, old=False)
    built = model.Built(folder)
    P = built.places.n
    rows = []

    def one(label, make):
        kept = {}

        def go():
            recorder = make()
            kept['recorder'] = recorder[0] if isinstance(recorder, tuple) else recorder
            return built.lines_run(horizon, kept['recorder']).run()

        took, run = best(go, runs)
        row = {'record': label, 'run_s': took, 'moments': run.counts['moments'], 'line_restarts': run.counts['line restarts']}
        recorder = kept['recorder']
        arrays = None
        if recorder is not None:
            arrays, size = sizes(recorder)
            row.update(size)
        rows.append(row)
        print(json.dumps(row))
        return run, recorder, arrays

    plain, _, _ = one('nothing', lambda: None)
    _, eight, _ = one('eight reductions (no max, no min) and five rows', lambda: request(built, extremes=False))
    run, asked, asked_arrays = one('ten reductions and five rows', lambda: request(built))
    whole, everything, table = one('every store and every flow', lambda: record.Recorder(everything=True))
    for row in rows[1:]:
        row['added_s'] = row['run_s'] - rows[0]['run_s']
    # Recording changes nothing in the run.
    same = bool(np.array_equal(plain.values(horizon), run.values(horizon)) and np.array_equal(plain.values(horizon), whole.values(horizon)))
    # Each reduction of the request against the same reduction made from the record of everything.
    stock = built.stores.place(built.places, 'stock', np.arange(P))
    used = built.stores.place(built.places, 'used', np.arange(P))
    critical = np.flatnonzero(built.places.cols['critical'])
    carried = np.arange(built.carried, built.carried + built.routes.n)
    use = np.arange(built.use, built.use + P)
    want = built.want()
    checks, worst = [], {}
    for t in (0.5, 1.0, 7.3, 20.0, 33.3, 47.9, 48.0):
        y, a = table_at(table, t), flows_at(table, t)
        direct = {
            'held': y[stock].sum(), 'used_total': y[used].sum(), 'critical_held': y[stock[critical]].sum(),
            'empty_places': float((y[stock] <= 0.0).sum()), 'low_places': float((y[stock] <= 10.0).sum()),
            'any_critical_empty': float((y[stock[critical]] <= 0.0).any()),
            'carried_now': a[carried].sum(), 'unmet_use': (want[use] - a[use]).sum(),
            'fullest': y[stock].max(), 'emptiest': y[stock].min(),
        }
        for item in asked.reductions:
            name = item.name.split(' = ')[0]
            got = item.history.at(t)
            miss = abs(got - direct[name])
            worst[name] = max(worst.get(name, 0.0), miss / max(1.0, abs(direct[name])))
            checks.append((t, name, got, float(direct[name])))
    # The five rows of the request against the record of everything.
    row_worst = 0.0
    for s, history in asked.rows.items():
        other = record.store_history(table, s)
        for t in (0.5, 7.3, 20.0, 48.0):
            row_worst = max(row_worst, abs(history.at(t) - other.at(t)))
    # A report from the record: each reduction at three times, and the lag of a tally.
    tally = next(item for item in asked.reductions if item.name.startswith('used_total')).history
    start = time.perf_counter()
    readings = {item.name.split(' = ')[0]: [item.history.at(t) for t in (12.0, 24.0, 48.0)] for item in asked.reductions}
    lagged = [tally.mean(t - 6.0, t - 2.0) for t in (12.0, 24.0, 48.0)]
    report_s = time.perf_counter() - start
    # The same lag from the readings of the tally at many times (a trapezium rule): what a record of
    # readings would give. With the readings of each hour it is not the mean.
    def from_readings(t, step):
        grid = np.arange(t - 6.0, t - 2.0 + step / 2, step)
        values = np.array([tally.at(x) for x in grid])
        return float(((values[:-1] + values[1:]) / 2).sum() * step / 4.0)

    hourly = [from_readings(t, 1.0) for t in (12.0, 24.0, 48.0)]
    found = {
        'places': places, 'routes': routes, 'stores': built.stores.count, 'flows': built.net.count,
        'horizon_h': horizon, 'rows': rows, 'load': load(), 'runs': runs,
        'recording_changes_the_run': not same,
        'largest_relative_difference_of_each_reduction': worst,
        'largest_difference_of_a_recorded_row_L': row_worst,
        'pieces_of_each_history': {item.name.split(' = ')[0]: len(item.history) for item in asked.reductions},
        'passes_over_the_rows': {item.name.split(' = ')[0]: item.passes for item in asked.reductions if isinstance(item, record.Extreme)},
        'report_s': report_s, 'readings': readings,
        'lag_of_used_total_exact': lagged, 'lag_from_hourly_readings': hourly,
        'peak_memory_MB': resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024,
    }
    for key, value in found.items():
        if key not in ('rows', 'readings'):
            print(f'   {key}: {value}')
    save(out, f'record_{places}_{routes}', found)


# ---- what the present engine keeps ---------------------------------------------------------------------

BASELINE = '''Place:  @shape
    "A place."
    input need: fraction = 1 in 0 to 100  @shape
    var open = true  @shape

Route:  @shape
    "A route."
    let dest: Place
    input capacity: fraction = 5 in 0 to 100  @shape
    input fail_at: h = 1000 h in 0 h to 10000 h  @shape
    var up = true  @shape
    var lost: fraction = 0 size 1  @shape
    input loss: fraction/h = 0.001 fraction/h in 0 fraction/h to 1 fraction/h  @shape
    flow lose: -> lost at loss while not up
    event fail once when t >= fail_at:  @shape
        "The route fails."
        up = false

places: Place from "places.csv"
routes: Route from "routes.csv"

output down: fraction = sum(Route.lost)  @shape
    "Lost"
LAG'''


def write_baseline(folder, places, routes, lagged, horizon=168.0, seed=0):
    """The model of scratch/networks/baseline.py (the table path of today runs it): each route
    fails at a time of its own and then loses at a constant rate. With `lagged`, its output has a
    uniform lag."""
    folder.mkdir(parents=True, exist_ok=True)
    rng = np.random.default_rng(seed)
    body = BASELINE.replace('LAG', '    lag uniform(2 h, 6 h)\n' if lagged else '')
    (folder / 'model.scn').write_text(model.HEAD.format(horizon=horizon) + body + model.RECORD)
    (folder / 'places.csv').write_text('need: fraction @shape\n' + '\n'.join(f'{x:.3f}' for x in rng.uniform(0.5, 2, places)) + '\n')
    to = rng.integers(1, places + 1, routes)
    fail = rng.uniform(1, 160, routes)
    lines = ['dest,capacity: fraction @shape,fail_at: h @shape']
    lines += [f'places.{a},{c:.3f},{f:.6f}' for a, c, f in zip(to, rng.uniform(1, 10, routes), fail)]
    (folder / 'routes.csv').write_text('\n'.join(lines) + '\n')
    return folder / 'model.scn'


def deep_size(value, seen=None):
    """The bytes of a value with what it holds (arrays by their data)."""
    seen = set() if seen is None else seen
    if id(value) in seen:
        return 0
    seen.add(id(value))
    if isinstance(value, np.ndarray):
        return value.nbytes + 100
    size = sys.getsizeof(value)
    if isinstance(value, dict):
        size += sum(deep_size(k, seen) + deep_size(v, seen) for k, v in value.items())
    elif isinstance(value, (list, tuple, set, frozenset)):
        size += sum(deep_size(item, seen) for item in value)
    return size


def today(out, routes=35000, places=30000):
    from napkin.engine import timeline
    from napkin.engine.timeline import reports
    from napkin.model import hybrid

    found = {'load': load()}
    # 1. The trajectory of a run with each row written out (the flat path): everything, as segments
    #    of the whole state and a copy of the state around each step.
    rows = []
    for size in (30, 100, 300):
        folder = model.write(Path(out) / 'today' / f'flat_{size}', *model.synthetic(size, size * 7 // 6, seed=1, rings=False), horizon=300.0)
        _, trajectory = model.old_run(folder, [0.0])
        start = time.perf_counter()
        packed = zlib.compress(pickle.dumps(trajectory, protocol=pickle.HIGHEST_PROTOCOL), 1)
        took = time.perf_counter() - start
        states = len(trajectory._states)
        row = {
            'places': size, 'quantities': states, 'segments': len(trajectory._segments),
            'snapshots': len(trajectory._snapshots), 'steps': len(trajectory._steps), 'trace': len(trajectory.trace),
            'pickle_zlib_bytes': len(packed), 'pack_s': took,
            'state_copies_bytes': 8 * states * (len(trajectory._snapshots) + len(trajectory._steps) + 2 * len(trajectory._segments)),
        }
        print(json.dumps(row))
        rows.append(row)
    found['trajectory'] = rows
    # 2. The record of the table path: what each value and each line was before each change.
    table = {'places': places, 'routes': routes}
    path = write_baseline(Path(out) / 'today' / 'table', places, routes, lagged=False)
    core = hybrid.compile(path)
    plan = timeline.Plan.of(core)
    t_plain, _ = best(lambda: timeline.run(plan), 1)
    t_record, result = best(lambda: timeline.run(plan, record=True), 1)
    run = result.run
    table.update(
        run_s=t_plain, run_with_record_s=t_record, steps=result.counts['steps'],
        undo_entries=sum(len(v) for v in run.undo.values()), line_log_entries=sum(len(v) for v in run.line_log.values()),
        block_log_entries=sum(len(v) for v in run.block_log.values()),
        record_bytes=deep_size(run.undo) + deep_size(run.line_log) + deep_size(run.block_log),
        log_bytes=deep_size(run.log) + deep_size(run.trace),
    )
    start = time.perf_counter()
    values = reports.outputs(result, [24.0, 48.0, 168.0])
    table['report_three_times_s'] = time.perf_counter() - start
    table['readings'] = [row['values']['down'] for row in values]
    print(json.dumps(table))
    found['table_path'] = table
    # 3. The same model with a uniform lag on its output: a report integrates the history piece by
    #    piece, and each reading of a piece reads every row.
    lagged = {}
    for count in (350, 3500, 35000):
        path = write_baseline(Path(out) / 'today' / f'lag_{count}', max(1, count * 6 // 7), count, lagged=True)
        core = hybrid.compile(path)
        result = timeline.run(timeline.Plan.of(core), record=True)
        start = time.perf_counter()
        try:
            import signal

            def stop(*_):
                raise TimeoutError

            signal.signal(signal.SIGALRM, stop)
            signal.alarm(600)
            values = reports.outputs(result, [48.0])
            signal.alarm(0)
            lagged[count] = {'report_one_time_s': time.perf_counter() - start, 'value': values[0]['values']['down']}
        except TimeoutError:
            lagged[count] = {'report_one_time_s': None, 'stopped_after_s': time.perf_counter() - start}
        print(count, json.dumps(lagged[count]))
    found['lag_on_the_table_path'] = lagged
    found['peak_memory_MB'] = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024
    save(out, 'today', found)


if __name__ == '__main__':
    part, out = sys.argv[1], sys.argv[2]
    if part == 'lag':
        lag(out)
    elif part == 'scale':
        scale(out, int(sys.argv[3]), int(sys.argv[4]), runs=int(sys.argv[5]) if len(sys.argv) > 5 else 3)
    elif part == 'today':
        today(out)
    else:
        raise SystemExit(__doc__)
