"""Every number of some runs, as text: the proof that a change of the engine keeps a run bit for bit.

Run it once with the package of the base commit and once with the package of a worktree. The two
files must be equal, byte for byte:

    PYTHONPATH=/home/user/napkin-base python scratch/rewrite/b0/bitwise.py /tmp/base.txt
    PYTHONPATH=$PWD                   python scratch/rewrite/b0/bitwise.py /tmp/mine.txt
    cmp /tmp/base.txt /tmp/mine.txt && sha256sum /tmp/base.txt /tmp/mine.txt

The package comes from PYTHONPATH. The model files come from the checkout that holds this script, for
both runs, so the two runs read the same files (`--models ROOT` names another checkout).

What it runs (`--list` names the cases, and a word after the file keeps the cases that hold it):

- each run of the two models of `examples/` and of `tests/acceptance/F5.scn`, through `simulate`:
  the central run, two samples with luck, the run with given outcomes, and played runs (a pause at
  the decision, each pick, the decisions settled last, a resolver);
- runs of the scenarios `iv_fluid_shortage` (each run; the default one also with luck and with given
  outcomes), `heat_wave_blackout`, `cyber_learning_loop` and `water_controls_wipe`, through
  `simulate`;
- the study and the report of each example, through the public API;
- the same models, the families of the benchmark (four with a table, ten with none) and a model of
  two linked tables through the hybrid core (`hybrid.compile`, `Plan.of`, `timeline.run`): with the
  things outside the tables in each tier, with the record of the past and the report of the run,
  with the reading of every rule, with luck, with given outcomes, with other values of two inputs,
  as a batch and through `timeline.check`.

What it writes of a run: every field of its result that is not of a derivative, and the state of
the run at its end. A float is written as its repr and its hexadecimal form, so two floats are equal
in the file only when their bits are. A field that exists only for a run with derivatives is not
written; the script stops when such a field holds anything (`Hidden`), so it hides no number. Two
things are left out:

- `own` of the state of a rule, the moment at which the own time of the rule came. At the base
  commit every run writes it, and only a run with derivatives reads it (for the tangent of the time
  of the rule), so it goes with them;
- the `implementation_hash` of a report: it is a digest of the source files of the package, so
  every change of a file moves it.

`record_runs.py`, beside this file, writes the same numbers for every run that a test makes.
"""

from __future__ import annotations

import argparse
import dataclasses
import hashlib
import importlib.util
import json
import math
import sys
import tempfile
import time
import traceback
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve()
# Objects of these modules hold numbers only: the walk reads their fields.
OPEN = ('napkin.engine.continuous.kernels', 'napkin.engine.solvers', 'scipy.integrate')
DEPTH = 40


class Hidden(Exception):
    """The script would leave out a number of a result, or cannot write a value."""


def number(value):
    value = float(value)
    if math.isnan(value):
        return 'nan'
    if math.isinf(value):
        return 'inf' if value > 0 else '-inf'
    return f'{value!r}|{value.hex()}'


def walk(value, depth=0, seen=()):
    """A value as lists, mappings and texts that `json` writes, with each float by its bits."""
    if depth > DEPTH:
        raise Hidden('the value is too deep')
    if value is None or isinstance(value, (bool, str)):
        return value
    if isinstance(value, (int, np.integer)) and not isinstance(value, (bool, np.bool_)):
        return int(value)
    if isinstance(value, np.bool_):
        return bool(value)
    if isinstance(value, (float, np.floating)):
        return number(value)
    if isinstance(value, complex):
        return {'<complex>': [number(value.real), number(value.imag)]}
    if isinstance(value, bytes):
        return {'<bytes>': value.hex()}
    if id(value) in seen:
        return '<cycle>'
    seen = (*seen, id(value))
    if isinstance(value, np.ndarray):
        items = value.ravel() if value.dtype == object else value.ravel().tolist()
        return {
            '<array>': str(value.dtype),
            'shape': list(value.shape),
            'values': [walk(item, depth + 1, seen) for item in items],
        }
    if isinstance(value, dict) or hasattr(value, 'keys') and hasattr(value, '__getitem__'):
        return {'<map>': [[walk(key, depth + 1, seen), walk(value[key], depth + 1, seen)] for key in value]}
    if isinstance(value, (list, tuple)) or type(value).__name__ == 'deque':
        return [walk(item, depth + 1, seen) for item in value]
    if isinstance(value, (set, frozenset)):
        return {'<set>': sorted((walk(item, depth + 1, seen) for item in value), key=json.dumps)}
    kind = f'{type(value).__module__}.{type(value).__qualname__}'
    if callable(value) and not kind.startswith(OPEN):
        return f'<callable {getattr(value, "__qualname__", kind)}>'
    if not kind.startswith(OPEN):
        return f'<{kind}>'
    if dataclasses.is_dataclass(value):
        fields = {item.name: getattr(value, item.name) for item in dataclasses.fields(value)}
    else:
        fields = dict(vars(value)) if hasattr(value, '__dict__') else {}
        for name in getattr(type(value), '__slots__', ()):
            if hasattr(value, name):
                fields[name] = getattr(value, name)
    return {
        '<object>': kind,
        'fields': {name: walk(fields[name], depth + 1, seen) for name in sorted(fields)},
    }


def plain(found, name, empty):
    """A field of a result that exists only for a run with derivatives holds nothing here."""
    value = getattr(found, name, empty)
    if value != empty:
        raise Hidden(f'{name} of a run with no derivative holds {value!r}')


# ---- a trajectory -------------------------------------------------------------------------------

GRID = 10


def grid(start, end):
    if end <= start:
        return [start]
    return [*(start + (end - start) * k / GRID for k in range(GRID)), end]


def trajectory_numbers(trajectory):
    out = {
        name: walk(getattr(trajectory, name))
        for name in (
            'horizon',
            'end_time',
            'paused',
            'decision',
            'evaluations',
            'layers',
            'moved',
            'settings',
            'diagnostics',
            '_states',
            '_values',
            '_bounds',
            'trace',
            '_snapshots',
            '_steps',
        )
    }
    segments = []
    for segment in trajectory._segments:
        segments.append(
            {
                'start': walk(segment.start),
                'end': walk(segment.end),
                'store': walk(segment.store),
                'solution': walk(segment.solution),
                'states': [[walk(at), walk(segment.solution(at))] for at in grid(segment.start, segment.end)],
            }
        )
    out['segments'] = segments
    # Every name of the run at the times of its moments, on both sides, and between them.
    moments = sorted({0.0, float(trajectory.end_time), *(float(snap[0]) for snap in trajectory._snapshots)})
    times = set(moments)
    for start, end in zip(moments, moments[1:]):
        times.update([(start + end) / 2, math.nextafter(end, start)])
    environments = []
    for at in sorted(times):
        for side in ('left', 'right'):
            try:
                env = trajectory.env_at(at, side)
            except Exception as problem:
                environments.append([walk(at), side, f'<{type(problem).__name__}: {problem}>'])
                continue
            environments.append([walk(at), side, {name: walk(env[name]) for name in sorted(env)}])
    out['environments'] = environments
    return out


def flat_cases(label, model, runs, library, every=True, actor=None):
    """The cases of the runs of a compiled model with no table, through `simulate`. `actor` names a
    thing with a decision, (thing, event, outcomes): the runs are then played too."""
    from napkin.engine import timeline
    from napkin.engine.runtime import simulate

    def central(run):
        return lambda: trajectory_numbers(simulate(model.resolve(run), library))

    def lucky(run, sample):
        def made():
            rs = model.resolve(run).adding(luck={'seed': 7, 'sample': sample})
            return trajectory_numbers(simulate(rs, library))

        return made

    def given(run):
        def made():
            found = timeline.result(model.resolve(run), library, None, outcomes=())
            return {'result': result_numbers(found), 'trajectory': trajectory_numbers(found.trajectory())}

        return made

    def played(run, by, picks, **options):
        def made():
            thing, event, _ = actor
            asked = {'control': {thing: by}, 'picks': [{'event': event, 'outcome': pick} for pick in picks]}
            return trajectory_numbers(simulate(model.resolve(run), library, play=asked, **options))

        return made

    def resolved(run):
        def made():
            thing, event, outcomes = actor
            seen = []

            def resolver(decision, env, trace):
                # The first outcome that can happen, and what the resolver was shown.
                seen.append([walk(decision), {name: walk(env[name]) for name in sorted(env)}, len(trace)])
                return {'event': decision['event'], 'outcome': decision['outcomes'][0]['name']}

            asked = {'control': {thing: 'agent'}, 'picks': []}
            found = simulate(
                model.resolve(run),
                library,
                play=asked,
                pause_at_decision=True,
                settled_decisions=True,
                decision_resolver=resolver,
            )
            return {'seen': seen, 'trajectory': trajectory_numbers(found)}

        return made

    for run in runs:
        yield f'{label}/{run}/central', central(run)
        if every:
            for sample in (0, 1):
                yield f'{label}/{run}/luck{sample}', lucky(run, sample)
            yield f'{label}/{run}/given', given(run)
        if actor is not None:
            yield f'{label}/{run}/play/pause', played(run, 'reader', [], pause_at_decision=True)
            yield f'{label}/{run}/play/model', played(run, 'agent', [])
            for outcome in actor[2]:
                yield f'{label}/{run}/play/{outcome}', played(run, 'reader', [outcome])
                yield (
                    f'{label}/{run}/play/{outcome}/settled',
                    played(run, 'reader', [outcome], pause_at_decision=True, settled_decisions=True),
                )
            yield f'{label}/{run}/play/resolver', resolved(run)


def study_case(model):
    def made():
        from napkin.engine import evaluate_study, sample_result

        study = evaluate_study(model)
        report = sample_result(study) if study.admissible else None
        if report is not None:
            # A digest of the source files of the package: every change of a file moves it.
            report['implementation_hash'] = '<left out>'
        return {
            'admissible': study.admissible,
            'diagnostics': walk(study.diagnostics),
            'report': walk(report),
            'runs': {
                name: trajectory_numbers(run['trajectory'])
                for name, run in study.runs.items()
                if run.get('trajectory') is not None
            },
        }

    return made


# ---- a result of the timeline engine ------------------------------------------------------------


def result_numbers(result):
    """Every field of a `timeline.Result` but its run, which `run_numbers` writes."""
    plain(result, 'tangents', {})
    plain(result, 'notes', ())
    margins = getattr(result, 'margins', None)
    if margins not in (None, {}, {'crossing_time_h': 0.0, 'moments_apart_h': math.inf, 'outcome': math.inf}):
        raise Hidden(f'margins of a run with no derivative hold {margins!r}')
    firings = []
    for firing in result.firings:
        # (the event, the chance of each outcome, the place taken); a run with no derivative has
        # nothing after them.
        if any(item is not None for item in firing[3:]):
            raise Hidden(f'a firing of a run with no derivative holds {firing[3:]!r}')
        firings.append(walk(firing[:3]))
    return {
        'horizon': walk(result.horizon),
        'end_time': walk(result.end_time),
        'paused': walk(result.paused),
        'decision': walk(result.decision),
        'reading': walk(result.reading),
        'counts': walk(result.counts),
        'unestimated': walk(result.unestimated),
        'outputs': walk(result.outputs),
        'trace': walk(result.trace),
        'firings': firings,
    }


def piece_numbers(piece):
    return {
        'start': walk(piece.start),
        'end': walk(piece.end),
        'first': walk(piece.first),
        'last': walk(piece.last),
        'waits': walk(piece.waits),
        'store': walk(piece.store),
        'solution': walk(piece.solution),
    }


def solution_numbers(solution):
    """What a block of a run holds of a segment."""
    if type(solution).__name__ == 'Component':
        pieces = [*solution.done, *([solution.current] if solution.current is not None else [])]
        return {
            'component': True,
            't0': walk(solution.t0),
            'y0': walk(solution.y0),
            'pieces': [piece_numbers(piece) for piece in pieces],
        }
    return {
        't0': walk(solution.t0),
        'y0': walk(solution.y0),
        'frontier': walk(solution.frontier),
        'settled': walk(solution.settled),
        'mode': walk(solution.mode),
        'matrix': walk(solution.matrix),
        'ends': walk(solution.ends),
        'cuts': walk(solution.cuts),
        'evaluations': walk(getattr(solution, 'evaluations', None)),
        'steps': [walk(step) for step in solution.steps],
    }


def run_numbers(run):
    """The state of a run: each value, line and block, each rule, the timeline, the record of the
    past and the whole record. It reads the fields of the run and calls nothing of it, so it changes
    nothing of the run."""
    plan = run.plan
    rules = []
    for rule, state in zip(plan.rules, run.rules):
        for extra in ('cause', 'pending_dt'):
            held = getattr(state, extra, None)
            if held is not None and held.size:
                raise Hidden(f'{extra} of a rule of a run with no derivative holds {held!r}')
        rules.append(
            {
                'rule': rule.name,
                **{
                    name: walk(getattr(state, name))
                    for name in ('armed', 'triggered', 'pending', 'version', 'ready', 'reached', 'window')
                },
            }
        )
    out = {
        'v': {name: walk(column) for name, column in run.v.items()},
        'y0': {name: walk(column) for name, column in run.y0.items()},
        't0': {name: walk(column) for name, column in run.t0.items()},
        'rate': {name: walk(column) for name, column in run.rate.items()},
        'lversion': {name: walk(column) for name, column in run.lversion.items()},
        'atol': {name: walk(column) for name, column in run.atol.items()},
        'slack': {name: walk(column) for name, column in run.slack.items()},
        'rules': rules,
        'whole': {str(index): solution_numbers(solution) for index, solution in run.whole.items()},
        'single': {
            str(index): [solution_numbers(solution) for solution in solutions]
            for index, solutions in run.single.items()
        },
        'times': walk(sorted(run.times)),
        'entries': walk(run.entries),
        'moment': walk(run.moment),
        'now': walk(run.now),
        'wrote': walk(run.wrote),
        'max_step': walk(run.max_step),
        'solver_step': walk(run.solver_step),
        'timescales': walk(run.timescales),
        'flowing': walk(run.flowing),
        'moved': walk(run.moved),
        'given': walk(run.given),
        'general': walk(sorted(plan.general)),
        'counts': walk(run.counts),
        'trace': walk(run.trace),
        # (time, steps, rule, instance, outcome, sets, modes, moved, before, picked) of each step.
        'log': [
            walk([*entry[:4], None if entry[4] is None else entry[4].name, *entry[5:]]) for entry in run.log
        ],
        'undo': walk(run.undo),
        'line_log': walk(run.line_log),
        'block_log': [
            [walk(key), [[walk(when), solution_numbers(old)] for when, old in kept]]
            for key, kept in run.block_log.items()
        ],
        'snapshots': walk(run.snapshots),
        'after_steps': walk(run.after_steps),
        'pieces': [piece_numbers(piece) for piece in run.pieces],
        'streams': walk(sorted(str(key) for key in run.streams)),
        'picked': walk(run.picked),
        'decision': walk(run.decision),
    }
    return out


def read_numbers(result):
    """Each name of the plan as a reader gets it at the end of a run, and the entries of the trace.
    A reader can make a block take more steps: the blocks and the counts of the run after it."""
    run = result.run
    names = {}
    for name in run.plan.kind:
        try:
            names[name] = walk(result.final(name))
        except Exception as problem:
            names[name] = f'<{type(problem).__name__}: {problem}>'
    return {
        'names': names,
        'entries': walk(result.entries),
        'whole': {str(index): solution_numbers(solution) for index, solution in run.whole.items()},
        'single': {
            str(index): [solution_numbers(solution) for solution in solutions]
            for index, solutions in run.single.items()
        },
        'counts': walk(run.counts),
    }


def hybrid_cases(label, path, runs=(None,), tiers=(None, 'fast', 'general'), library=None, every=True):
    """The cases of a model through its hybrid core."""
    from napkin.engine import timeline
    from napkin.engine.timeline import reports
    from napkin.model import hybrid

    cores = {}

    def core():
        if 'core' not in cores:
            cores['core'] = hybrid.compile(path, library)
        return cores['core']

    def one(run, tier, options, report=False, values=False):
        def made():
            plan = timeline.Plan.of(core(), run, scalars=tier)
            given = None
            if values:
                # Another value of the first two inputs that no bound reads, in the unit of the file.
                names = [name for name in plan.parameter_scale if name not in plan.bound_reads][:2]
                given = {name: plan.values[name] / plan.parameter_scale[name] * 0.9375 for name in names}
            result = timeline.run(plan, given, **options)
            out = {'result': result_numbers(result), 'state': run_numbers(result.run)}
            if report:
                horizon = float(result.horizon)
                times = [0.0, horizon / 7, horizon / 2, horizon]
                try:
                    out['report'] = walk(reports.report_of(result, times))
                except Hidden:
                    raise
                except Exception as problem:
                    # A report that the engine refuses: the run has its numbers all the same.
                    out['report'] = f'<{type(problem).__name__}: {problem}>'
            out['read'] = read_numbers(result)
            return out

        return made

    def checked(run):
        return lambda: walk(timeline.check(timeline.Plan.of(core(), run)))

    def batch(run):
        def made():
            plan = timeline.Plan.of(core(), run)
            found = timeline.batch(plan, [None, None], luck={'seed': 3, 'sample': 1})
            return [
                [sample.status, sample.error, None if sample.result is None else result_numbers(sample.result)]
                for sample in found
            ]

        return made

    for run in runs:
        name = f'{label}/{run or "first"}'
        for tier in tiers:
            yield f'{name}/{tier or "default"}', one(run, tier, {})
        if not every:
            continue
        yield f'{name}/default/record', one(run, None, {'record': True}, report=True)
        yield f'{name}/fast/record', one(run, 'fast', {'record': True}, report=True)
        yield f'{name}/default/every', one(run, None, {'reading': 'every'})
        yield f'{name}/fast/every', one(run, 'fast', {'reading': 'every'})
        yield f'{name}/default/luck', one(run, None, {'luck': {'seed': 11, 'sample': 2}})
        yield f'{name}/fast/luck', one(run, 'fast', {'luck': {'seed': 11, 'sample': 2}})
        yield f'{name}/default/given', one(run, None, {'outcomes': ()})
        yield f'{name}/fast/given', one(run, 'fast', {'outcomes': ()})
        yield f'{name}/check', checked(run)
        yield f'{name}/batch', batch(run)
        yield f'{name}/default/values', one(run, None, {}, values=True)
        yield f'{name}/fast/values', one(run, 'fast', {}, values=True)


# ---- the models ---------------------------------------------------------------------------------

# The model of `scratch/networks/baseline.py`: two tables with a link, clocks and a flow.
NETWORK_HEAD = '''scenario "A synthetic model"
    summary "A model of a test, with no source."
    horizon 7 days
    scope "Nothing: the model is synthetic."

'''
NETWORK_RECORD = '\nrecord shape: assumption "A synthetic model, with no source."\n'
NETWORK_BODY = '''Place:  @shape
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
'''


def network(folder, places=9, routes=24, failing=11, seed=5):
    folder.mkdir(parents=True, exist_ok=True)
    rng = np.random.default_rng(seed)
    (folder / 'model.scn').write_text(NETWORK_HEAD + NETWORK_BODY + NETWORK_RECORD, encoding='utf-8')
    needs = '\n'.join(f'{x:.3f}' for x in rng.uniform(0.5, 2, places))
    (folder / 'places.csv').write_text('need: fraction @shape\n' + needs + '\n', encoding='utf-8')
    to = rng.integers(1, places + 1, routes)
    fail = np.full(routes, 1000.0)
    chosen = rng.choice(routes, failing, replace=False)
    fail[chosen] = rng.uniform(1, 160, failing)
    fail[chosen[:3]] = 24.0
    rows = ['dest,capacity: fraction @shape,fail_at: h @shape']
    rows += [f'places.{a},{c:.3f},{f:.6f}' for a, c, f in zip(to, rng.uniform(1, 10, routes), fail)]
    (folder / 'routes.csv').write_text('\n'.join(rows) + '\n', encoding='utf-8')
    return folder / 'model.scn'


# The thing that decides in a model, its event and the outcomes of that event.
ACTORS = {
    'reservoir': ('operator', 'operator.decide', ('open', 'wait')),
    'F5': ('operators', 'operators.decide', ('close', 'wait')),
}


def cases(root, folder):
    from napkin import load_package
    from napkin.model.ir import thaw
    from napkin.model.language import front
    from napkin.model.load import load_json

    for name in ('piano_tuners', 'reservoir'):
        (model,) = load_package(root / 'examples' / name).values()
        yield from flat_cases(
            f'examples/{name}', model, list(model.runs), thaw(model.library), actor=ACTORS.get(name)
        )
        yield f'examples/{name}/study', study_case(model)
        yield from hybrid_cases(
            f'hybrid/examples/{name}', root / 'examples' / name / 'model.scn', runs=list(model.runs)
        )
    library = load_json(root / 'tests' / 'acceptance' / 'library.json')
    path = root / 'tests' / 'acceptance' / 'F5.scn'
    model = front.compile_file(front.read(path.read_text(encoding='utf-8'), 'F5.scn'), 'F5.scn', thaw(library))
    yield from flat_cases('acceptance/F5', model, list(model.runs), library, actor=ACTORS['F5'])
    yield from hybrid_cases('hybrid/acceptance/F5', path, runs=list(model.runs), library=thaw(library))
    (model,) = load_package(root / 'scenarios' / 'iv_fluid_shortage').values()
    runs = list(model.runs)
    # The default run with its samples and its given outcomes; each other run as the central run.
    yield from flat_cases('scenarios/iv_fluid_shortage', model, runs[:1], thaw(model.library))
    yield from flat_cases('scenarios/iv_fluid_shortage', model, runs[1:], thaw(model.library), every=False)
    path = root / 'scenarios' / 'iv_fluid_shortage' / 'model.scn'
    yield from hybrid_cases('hybrid/scenarios/iv_fluid_shortage', path, runs=[runs[0], runs[3]])
    # Three more scenarios, each with a few of its runs: the first two of each of the first two, and
    # the second run of two variants of the third.
    for name, count in (('heat_wave_blackout', 2), ('cyber_learning_loop', 1)):
        (model,) = load_package(root / 'scenarios' / name).values()
        yield from flat_cases(
            f'scenarios/{name}', model, list(model.runs)[:count], thaw(model.library), every=False
        )
    path = root / 'scenarios' / 'heat_wave_blackout' / 'model.scn'
    yield from hybrid_cases('hybrid/scenarios/heat_wave_blackout', path, tiers=(None,), every=False)
    models = load_package(root / 'scenarios' / 'water_controls_wipe')
    for key in ('water_controls_wipe:asheville', 'water_controls_wipe:washington_dc'):
        model = models[key]
        yield from flat_cases(
            f'scenarios/{key}', model, list(model.runs)[1:2], thaw(model.library), every=False
        )
    # The families of the benchmark: the four with a table, and those with no table.
    spec = importlib.util.spec_from_file_location('families', root / 'tools' / 'bench' / 'families.py')
    families = importlib.util.module_from_spec(spec)
    sys.modules['families'] = families
    spec.loader.exec_module(families)
    sizes = {
        'table_instances': 14,
        'table_aggregate_output': 9,
        'table_aggregate_guard': 12,
        'table_aggregate_feedback': 7,
        'instances': 3,
        'aggregate_output': 3,
        'aggregate_guard': 4,
        'aggregate_feedback': 3,
        'stiff': 4,
        'events': 9,
        'rationing': 3,
        'priority': 3,
        'compartments': 5,
        'formulas': 6,
    }
    for name, size in sizes.items():
        path = families.write(name, size, folder)
        yield from hybrid_cases(f'hybrid/{name}_{size}', path)
    yield from hybrid_cases('hybrid/network', network(folder / 'network'))


def main():
    parser = argparse.ArgumentParser(description=__doc__.split('\n\n')[0])
    parser.add_argument('out', nargs='?', help='the file to write')
    parser.add_argument('only', nargs='*', help='keep the cases whose name holds one of these')
    parser.add_argument('--models', default=str(HERE.parents[3]), help='the checkout of the model files')
    parser.add_argument('--list', action='store_true', help='name the cases and run none')
    args = parser.parse_args()
    import napkin

    print(f'package: {Path(napkin.__file__).parent}', file=sys.stderr)
    print(f'models:  {args.models}', file=sys.stderr)
    root = Path(args.models)
    lines, failed = [], 0
    with tempfile.TemporaryDirectory() as made:
        for name, case in cases(root, Path(made)):
            if args.only and not any(word in name for word in args.only):
                continue
            if args.list:
                print(name)
                continue
            started = time.perf_counter()
            try:
                found = case()
            except Hidden:
                raise
            except Exception as problem:
                # A run that the engine stops is a result too: its error, with no place in a file.
                failed += 1
                last = traceback.extract_tb(problem.__traceback__)[-1]
                found = {'<error>': type(problem).__name__, 'message': str(problem), 'in': last.name}
            # The folder of the made models has another name in each run of the script.
            text = json.dumps(found, indent=1, allow_nan=False).replace(str(made), '<made>')
            digest = hashlib.sha256(text.encode()).hexdigest()
            seconds = time.perf_counter() - started
            print(f'{digest[:16]} {len(text):>9} {seconds:6.1f} s {name}', file=sys.stderr)
            lines.append(f'==== {name} {digest}\n{text}\n')
    if args.list:
        return
    out = ''.join(lines)
    Path(args.out).write_text(out, encoding='utf-8')
    print(f'{hashlib.sha256(out.encode()).hexdigest()}  {args.out}  ({len(lines)} cases, {failed} stopped)')


if __name__ == '__main__':
    main()
