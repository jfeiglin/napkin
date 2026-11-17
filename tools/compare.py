"""Compare two revisions of the checkout bit for bit: python -m tools.compare
[--base REV | --baseline DIR] [--scenario ID] [--allow FILE] [--rename FILE] [--jobs N] [--keep DIR]
[--tolerance].

The comparison follows the contract in CONTRIBUTING.md ("Testing", "Refactor comparisons"). The base (by
default the merge base of HEAD with main) goes into a temporary git worktree; the working tree is the
other side. Each side runs its own revision's capture code (its `compare.py`, copied out of its
package) with its own package, and records for each scenario:

- `structure`: the compiled model: its structures in their order of quantities, rules and flows,
  its runs, inputs, events, outputs, start options, run table, evidence and index;
- `order`: the compiled order by names only: for each structure, the names of each section in their
  order, the rules in the order of one moment, the kind of each rule's trigger, the order in which the
  formulas are computed, and the names of the parts that it leaves out;
- `pages`: what the pages show of the model;
- `default`: the default study: its admission, its diagnostics, its report (the values, the
  states, the events in their round and order, and the evidence trail of each run), the record of
  each run's trajectory and the numbers of each run (`states`);
- `sweeps`: each sweep of the brief settings (`[[sweep]]` in `brief.toml`) as a study;
- `edits`: the admission or rejection of each example edit set, with its diagnostics, when the
  scenario has any.

A trajectory's record is a digest of each of its numeric parts (its states, values, segments,
snapshots, steps, bounds and the rest) and its unit table, kept only for the units that the run's
resolved structure names and sorted by name. Its trace and diagnostics are not in it: the report
holds the trace and the study its diagnostics, as plain records that an allow file can map. Each side
also writes the machine it ran on (`environment.json`).

`order` and `states` hold names and numbers only, and nothing of how a revision keeps a model or a
run: no expression text, no field of an internal object. So two revisions that keep them in different
forms still compare, where `structure` and a trajectory's record cannot. The numbers of a run are the
names of its quantities in the compiled order, then the time, the quantities and the discrete values
after each step in order, and the same with the formulas at each sixteenth of the run's length. The
discrete values are those that the engine keeps for the run, by the engine's names. The numbers also
hold what the comparison of a change of the numerical core judges with: the absolute tolerance of each
quantity, the time at which the run's first numerical segment starts, and for each step the time that
the model itself writes for it, if it writes one (`written_times`).

What no record holds: a Monte Carlo sample of a spread, and a played run. A change that only these can
show needs its own check.

Beside the catalogue, a comparison captures each example (`examples/<name>/`, the owner
`examples.<name>`) and the acceptance fixture (`tests/acceptance/F5.scn`, the owner `acceptance.F5`):
their compiled model, its order and their default study. A package's name has no dot, so these owners
meet no owner of the catalogue.

Before the comparison, both sides' records take a canonical form: no source positions (the model's
`lines`, and the `file` and each `line` of its `index`), each event `rank` as its ordinal among the
ranks of the record, and no `controls` in the pages. A capture failure on either side fails the
comparison, even when the other side fails alike. Then the records are compared exactly: floats bit
for bit, mappings and lists in their order. Only `implementation_hash` differs without a word,
because every change of code changes it. An allow file (`--allow FILE`) names:

- `"ignore"`: keys to leave out anywhere, such as `model_hash`;
- `"ignore_paths"`: paths to leave out, each the record's name, then its keys, with `*` for one key
  and `**` for any number of keys: `default/report/runs/*/peaks/*/t`;
- `"map"`: texts of the base to read as other texts, such as a source location that moved;
- `"reporting": "final"`: keep only the final reporting point of each run, on both sides.

`--rename FILE` maps old owners and paths of the base to new ones (`{"SC97_east": "SC97:east"}`). A
key matches only whole paths: a whole text, or whole segments between slashes anywhere in a text,
never part of a word; so name whole paths (`scenarios/SC97_east`), not short segments. Two base
records that a rename gives one name fail the comparison.
Every other difference fails.

`--baseline DIR` compares the working tree with the base records that `--keep DIR` saved (`DIR/base`,
the pinned revision), instead of capturing a base; `--scenario` then compares only those owners. It
refuses, before capturing, records of another machine (another Python, numpy or scipy, another
processor or set of CPU features), whose last bits can differ: capture the base again there with
`--base REV --keep DIR`. A `--keep` folder may not overlap the baseline.

`--tolerance` is for a change of the numerical core, which does not keep the bits (CONTRIBUTING.md,
"Comparisons of a change of the numerical core"). The compiled model, its order and the pages still
compare exactly. In each study, the numbers of the simulation compare within their tolerances
(`VALUE_RELATIVE`, `VALUE_TOLERANCES`, `VALUE_SHARE`, `OUTCOME_ABSOLUTE`, `EXACT_TIME_H`,
`LOCATED_TIME_RELATIVE`),
and every other value exactly: each step of the trace with its rule, its event, its outcome and its
place in its moment, each status, each warning and the evidence trail. The base side gives each
tolerance and says which times a root can have given, so the side under test cannot widen what judges
it; a base that an earlier revision of this file captured has no such record and is captured again. A
number that is not finite is listed. The record of a trajectory's parts, the list of the numerical
segments and the notes of the numerics (`info`) are left out or only counted, because they say how one
revision's engine cut the run. The command prints how many values differ within tolerance, how many
moments shifted and by how much, and each difference that must be explained: a discrete one, or a
number beyond its tolerance. Agreement shows that a change kept the results; it does not show that
either side is right, which the independent oracles do.

Both sides take their runs from the run store of this checkout, so a refactor whose resolved runs stay
the same compares without simulating, and a base is simulated only once for many revisions. No test
reads a record of this command; the tests stay the oracles of correctness, and agreement between two
revisions shows only that a change keeps the results.
"""

from __future__ import annotations

import argparse
import contextlib
import hashlib
import json
import math
import multiprocessing
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
from collections.abc import Mapping
from concurrent.futures import ProcessPoolExecutor
from dataclasses import fields, is_dataclass
from pathlib import Path

# Each change of code changes the implementation hash, so a comparison of code never reports it.
DEFAULT_IGNORE = ('implementation_hash',)
# The parts of a compiled model that a comparison reads: not the semantic model, the library's
# texts or the model's caches, whose form a refactor may change.
STRUCTURE = (
    'model_hash',
    'library_hash',
    'menu',
    'swap',
    'runs',
    'start_options',
    'inputs',
    'entities',
    'outputs',
    'events',
    'structures',
    'left_out',
    'whole',
    'time',
    'initiation',
    'index',
    'run_table',
    'evidence',
    'arguments',
    'lines',
)
# The sections of a structure whose order of names the `order` record keeps.
ORDERED = (
    'entities',
    'parameters',
    'quantities',
    'modes',
    'computed',
    'labels',
    'rates',
    'flows',
    'allocation',
    'coupling',
    'rules',
    'events',
    'input_checks',
    'state_checks',
    'partitions',
    'outcomes',
    'links',
)
# The times of a run's numbers: each k / GRID of its length, both ends with them.
GRID = 16
# The models outside the catalogue that a comparison also captures: the folder of the examples, whose
# owners are `examples.<name>`, and the acceptance fixture (its owner, its file, its library).
EXAMPLES = 'examples'
ACCEPTANCE = ('acceptance.F5', 'tests/acceptance/F5.scn', 'tests/acceptance/library.json')
SHOWN = 12  # differences shown for each record that differs
FAILURE = '<capture failure>'
# The parts of a trajectory that its record leaves out: the report and the study hold them.
NOT_NUMERIC = ('trace', 'diagnostics', '_units')
# Where a revision keeps its capture code, newest layout first.
CAPTURE_CODE = ('tools/compare.py', 'napkin/compare.py', 'cyber_scenarios/compare.py')
# The run store variable of each package name; both sides get both.
STORE_VARIABLES = ('CYBER_SCENARIOS_STORE', 'NAPKIN_STORE')
ALLOWED = {'ignore', 'ignore_paths', 'map', 'reporting'}


# --- Records: plain JSON data and digests ---------------------------------------------------------


def plain(value):
    """JSON data of a record: mappings in their order (a mapping with keys that are not texts becomes
    a list of [key, value] pairs), sequences, sets sorted, numbers exactly, objects by their fields;
    anything else its repr, without a memory address."""
    numpy = sys.modules.get('numpy')
    if isinstance(value, Mapping):
        if all(isinstance(key, str) for key in value):
            return {key: plain(item) for key, item in value.items()}
        return [['<key>', plain(key), plain(item)] for key, item in value.items()]
    if isinstance(value, (list, tuple)):
        return [plain(item) for item in value]
    if isinstance(value, (set, frozenset)):
        return sorted((plain(item) for item in value), key=repr)
    if numpy is not None and isinstance(value, numpy.ndarray):
        return {'<array>': value.dtype.str, 'values': plain(value.tolist())}
    if numpy is not None and isinstance(value, numpy.generic):
        return plain(value.item())
    if value is None or isinstance(value, (bool, int, float, str)):
        return value
    if is_dataclass(value):
        return {
            '<object>': type(value).__qualname__,
            **{f.name: plain(getattr(value, f.name)) for f in fields(value)},
        }
    if hasattr(value, '__dict__'):
        return {'<object>': type(value).__qualname__, **plain(dict(sorted(vars(value).items())))}
    return re.sub(r' at 0x[0-9a-fA-F]+', '', repr(value))


def relocated(value, roots):
    """`value` with each path under one of `roots` written from `<root>`, so that the records of two
    checkouts in different places compare."""
    if isinstance(value, dict):
        return {key: relocated(item, roots) for key, item in value.items()}
    if isinstance(value, list):
        return [relocated(item, roots) for item in value]
    if isinstance(value, str):
        for root in roots:
            value = value.replace(root, '<root>')
    return value


def _encode(value, out):
    numpy = sys.modules.get('numpy')
    kind = type(value)
    if value is None:
        out.append(b'N')
    elif kind is bool:
        out.append(b'T' if value else b'F')
    elif kind is int:
        out.append(b'i%d;' % value)
    elif kind is float:
        out.append(b'f' + value.hex().encode() + b';')
    elif kind is str:
        data = value.encode('utf-8', 'surrogatepass')
        out.append(b's%d:' % len(data) + data)
    elif isinstance(value, Mapping):
        out.append(b'{%d:' % len(value))
        for key, item in value.items():
            _encode(key, out)
            _encode(item, out)
        out.append(b'}')
    elif kind in (tuple, list):
        out.append(b'[%d:' % len(value))
        for item in value:
            _encode(item, out)
        out.append(b']')
    elif kind in (set, frozenset):
        parts = sorted(_bytes(item) for item in value)
        out.append(b'<%d:' % len(parts) + b''.join(parts) + b'>')
    elif numpy is not None and isinstance(value, numpy.ndarray):
        array = numpy.ascontiguousarray(value)
        out.append(b'a' + array.dtype.str.encode() + repr(array.shape).encode() + b':')
        if array.dtype.hasobject:
            _encode(array.tolist(), out)
        else:
            out.append(array.tobytes())
    elif numpy is not None and isinstance(value, numpy.generic):
        out.append(b'g' + value.dtype.str.encode() + b':' + value.tobytes())
    elif is_dataclass(value):
        out.append(b'D' + kind.__qualname__.encode() + b':')
        _encode({item.name: getattr(value, item.name) for item in fields(value)}, out)
    elif hasattr(value, '__dict__'):
        out.append(b'O' + kind.__qualname__.encode() + b':')
        _encode(dict(sorted(vars(value).items())), out)
    else:
        out.append(b'R' + repr(value).encode())


def _bytes(value):
    out = []
    _encode(value, out)
    return b''.join(out)


def digest(value):
    """A digest of a whole result, objects by their fields: equal digests mean equal values, bit for bit."""
    return hashlib.sha256(_bytes(value)).hexdigest()


def _texts(value, out):
    """Every text of a plain value, keys and strings, into the set `out`."""
    if isinstance(value, dict):
        for key, item in value.items():
            out.add(key)
            _texts(item, out)
    elif isinstance(value, list):
        for item in value:
            _texts(item, out)
    elif isinstance(value, str):
        out.add(value)


def named_units(table, structure):
    """The names of `table` that the plain `structure` names: as a whole text, or as a token in a text
    (a unit in a type such as `people/h`, or a literal in an expression)."""
    texts = set()
    _texts(structure, texts)
    joined = '\n'.join(sorted(texts))
    return sorted(
        name
        for name in table
        if name in texts or re.search(r'(?<![\w/.-])' + re.escape(name) + r'(?![\w/.-])', joined)
    )


def trajectory_record(trajectory, resolved):
    """The record of one run's trajectory: a digest of each numeric part, and its unit table, kept for
    the units that the run's resolved structure names, sorted by name. The names are those of the
    builder's mapping, so a typed run gives its mapping again."""
    from napkin.model import structure as typed

    written = resolved.plain() if isinstance(resolved, typed.Resolved) else resolved
    system = getattr(trajectory, '_units', None)
    table = getattr(system, '_units', None) or {}
    return {
        'parts': {
            item.name: digest(getattr(trajectory, item.name))
            for item in fields(trajectory)
            if item.name not in NOT_NUMERIC
        },
        'units': {name: plain(table[name]) for name in named_units(table, plain(written))},
    }


def order_record(model):
    """The compiled order of a model, by names only: for each structure (under its start-state options,
    as a JSON list), the names of each section of `ORDERED` in their order, the rules in the order of
    one moment (`moment`: by rank), the kind of each rule's trigger with the quantity and the
    comparison of a crossing (`triggers`), the order in which the formulas are computed
    (`formula_order`), and the names of the parts that the structure leaves out, by section. It holds
    no expression and no definition, so it does not depend on how a revision keeps its structures."""

    out = {}
    for starts, structure in model.structures.items():
        record = {
            name: list(structure.links if name == 'links' else structure.section(name)) for name in ORDERED
        }
        record['moment'] = [rule.id for rule in structure.moment_order()]
        record['triggers'] = {
            rule: [
                item.trigger.kind if item.trigger.kind is not None else 'discrete',
                item.trigger.var,
                item.trigger.op,
            ]
            for rule, item in structure.rules.items()
        }
        record['formula_order'] = [
            item[0] if isinstance(item, (list, tuple)) else item for item in structure.computed_order
        ]
        record['left_out'] = {section: list(parts) for section, parts in structure.left_out.items()}
        out[json.dumps(list(starts), ensure_ascii=False)] = record
    return out


def written_times(trajectory, resolved, units):
    """For each step of the trace, the time that the model writes for it, or None.

    The model writes the time of a step when exact arithmetic on the inputs gives it:

    - the largest of the times of the step's trigger, when each time that is the largest, or as near to
      it as a root can move a time, is exact, and the step is at that time within the tolerance of a
      timer;
    - the time of a firing that waits, when the moment of its trigger has a written time and its delay
      was exact as the rule triggered: the engine adds the two then.

    A time or a delay can read the inputs, the formulas of the inputs, a value that the rule draws from
    exact values, and each discrete value and each quantity that only rules set, while that value is
    exact. A value is exact when a step set it from exact values: the time of an event or of a change
    of state, when the moment of that step has a written time; a number that an effect sets, when the
    effect reads exact values only. A quantity that a flow moves is never exact, and neither is a value
    of the run's past (`delayed`): they carry the accuracy of the segments. A step with a written time
    gives that time to every step of its moment.

    So the time of a crossing that a root gives is not written, and neither is a time that follows it
    by a wait; a timer on the inputs is written, and so is each timer that waits on it."""
    from napkin.expressions import evaluate, names_in

    values, computed, rules = resolved.values, resolved.computed, resolved.rules
    moved = {name for name, item in resolved.quantities.items() if item.kind != 'variable'}
    known = set(resolved.quantities) | set(trajectory._snapshots[0][2] if trajectory._snapshots else ())
    inexact = set()
    trace = trajectory.trace
    before = {id(step): trajectory._snapshots[k - 1] for k, step in enumerate(trajectory._snapshots) if k}

    def exact(expr, rule, at_exact_time=False, seen=()):
        """Whether exact arithmetic on the inputs gives the present value of an expression of a rule."""
        extras = {item.name: item for item in rule.extras or ()}
        for name in names_in(expr):
            if name in computed:
                if name in seen or not exact(computed[name].expr, rule, at_exact_time, (*seen, name)):
                    return False
            elif name == 't':
                if not at_exact_time:
                    return False
            elif name in extras:
                # A value that the rule draws is exact when what it is drawn from is; a value of the
                # run's past is not.
                sources = (extras[name].args or {}).values()
                if extras[name].kind == 'delayed' or name in seen:
                    return False
                if not all(exact(source, rule, at_exact_time, (*seen, name)) for source in sources):
                    return False
            elif name in moved or name in inexact or not (name in values or name in known):
                return False
        return True

    def largest(rule, times, environment, t):
        """The largest time of a trigger, when it is written and the step is at it."""
        try:
            found = [(float(evaluate(time, environment, units)), exact(time, rule)) for time in times]
        except Exception:
            return None
        last = max(value for value, _ in found)
        near = LOCATED_TIME_RELATIVE * max(1.0, abs(last))
        if all(holds for value, holds in found if last - value <= near) and abs(t - last) <= EXACT_TIME_H:
            return last
        return None

    def effects(rule, entry):
        """{name: the expression that sets it} of the outcome of a step."""
        for outcome in rule.outcomes:
            if outcome.name == entry.get('outcome'):
                return {name: item.expr for name, item in outcome.do.set.items()}
        return {}

    found, waiting = [None] * len(trace), {}
    position = 0
    while position < len(trace):
        t = trace[position]['t']
        last = position
        while last + 1 < len(trace) and trace[last + 1]['t'] == t:
            last += 1
        environment = None
        moment = None
        for entry in trace[position : last + 1]:
            rule = rules.get(entry['rule'])
            if rule is None or moment is not None:
                continue
            times = rule.trigger.times
            if rule.delay is not None and entry['outcome'] is not None:
                if waiting.get(entry['rule']):
                    moment = t
            elif times:
                if environment is None:
                    environment = trajectory.env_at(t, 'left')
                moment = largest(rule, times, environment, t)
        for index in range(position, last + 1):
            found[index] = moment
            entry = trace[index]
            rule = rules.get(entry['rule'])
            if rule is None:
                continue
            if rule.delay is not None and entry['outcome'] is None:
                # The rule triggers and waits: the engine reads its delay now.
                waiting[entry['rule']] = moment is not None and exact(rule.delay, rule, True)
            # What the step sets: the times of its event and of its changes of state take the
            # exactness of the moment, and a number takes the exactness of what its effect reads.
            step = trajectory._steps[index]
            earlier = before[id(step)][2]
            for name, value in step[2].items():
                if name.endswith(TIME_SUFFIXES) and not same(value, earlier.get(name)):
                    (inexact.discard if moment is not None else inexact.add)(name)
            sets = effects(rule, entry)
            for name, value in (entry.get('changes') or {}).items():
                if isinstance(value, (int, float)) and not isinstance(value, bool):
                    expr = sets.get(name)
                    holds = expr is not None and exact(expr, rule, moment is not None)
                    (inexact.discard if holds else inexact.add)(name)
        position = last + 1
    return found


def run_states(trajectory, resolved=None, units=None):
    """The numbers of one run, with nothing of how a revision keeps a trajectory: the names of the
    quantities in the compiled order (`names`), of the discrete values, sorted (`discrete`), and of the
    formulas in their order (`formulas`); then the time, each quantity and each discrete value after
    each step, in the order of the steps (`steps`), and the same with each formula at each k / GRID of
    the run's length (`grid`), on the later side of a moment.

    For the comparison of a change of the numerical core, it also holds the absolute tolerance of each
    quantity (`tolerances`); the time at which the first numerical segment of the run starts
    (`numerical_from`, None when the run has none), before which every time comes from a timer, a
    delay or a closed form; and, for each step, the time that the model writes for it (`written`,
    `written_times`), when the run's resolved structure is given."""

    names = list(trajectory._states)
    discrete = sorted(trajectory._snapshots[0][2]) if trajectory._snapshots else []
    formulas = list(resolved.computed) if resolved is not None else []
    numerical = [segment['start_h'] for segment in trajectory.settings.get('integration_segments', ())]
    written = written_times(trajectory, resolved, units) if resolved is not None else None

    def row(t, values, store):
        return {
            't': float(t),
            'values': [float(value) for value in values],
            'discrete': [store[name] for name in discrete],
        }

    steps = [row(t, state, store) for t, state, store in trajectory._steps]
    if written is not None:
        for step, time in zip(steps, written):
            step['written'] = time
    grid = []
    for k in range(GRID + 1):
        t = trajectory.end_time * k / GRID
        environment = trajectory.env_at(t)
        grid.append(
            row(t, [environment[name] for name in names], environment)
            | {'formulas': [environment[name] for name in formulas]}
        )
    return {
        'names': names,
        'tolerances': [float(value) for value in trajectory._bounds[3]],
        'numerical_from': min(numerical) if numerical else None,
        'discrete': discrete,
        'formulas': formulas,
        'steps': steps,
        'grid': grid,
    }


def extras(root):
    """{owner: the path of its model file} of the models outside the catalogue that a comparison
    captures: each example, and the acceptance fixture."""
    root = Path(root)
    found = {f'{EXAMPLES}.{path.parent.name}': path for path in sorted((root / EXAMPLES).glob('*/model.scn'))}
    owner, model, _ = ACCEPTANCE
    if (root / model).is_file():
        found[owner] = root / model
    return found


# --- The capture of one side, with that side's package ----------------------------------------


def _builders(model, name):
    """One part of a compiled model for the record `structure`. The structures and the whole
    structures are written as plain data (`Structure.plain`): each part with its keys in the
    order of the compile, and each expression as its text. That is the form of the record."""
    if name in ('structures', 'whole'):
        return {starts: structure.plain() for starts, structure in getattr(model, name).items()}
    return getattr(model, name)


def _part(make):
    """A record, or the failure that made none, which then fails the comparison."""
    try:
        return plain(make())
    except Exception as exc:
        return {FAILURE: f'{type(exc).__name__}: {exc}'}


def _use_store():
    """Use this checkout's run store when the side's package has one."""
    with contextlib.suppress(ImportError):
        from napkin import store

        store.activate(store.default_directory())


def _environment():
    """The machine and the numerical libraries of this side, as the run store keys them."""
    try:
        from napkin import store
    except ImportError:
        return {}
    return plain(store.ENVIRONMENT)


def _study(study):
    from napkin.engine import sample_result

    return {
        'admissible': study.admissible,
        'diagnostics': study.diagnostics,
        'report': sample_result(study) if study.admissible else None,
        'trajectories': {
            run: trajectory_record(item['trajectory'], item['resolved']) for run, item in study.runs.items()
        },
        'states': {
            run: run_states(item['trajectory'], item['resolved'], item['trajectory']._units)
            for run, item in study.runs.items()
        },
    }


def _write(folder, records, root):
    """Write each record into `folder`, with the paths of the checkout written from `<root>`."""
    roots = sorted({str(Path(root)), str(Path(root).resolve())}, key=len, reverse=True)
    for name, record in records.items():
        text = json.dumps(relocated(record, roots), ensure_ascii=False, indent=1)
        (folder / f'{name}.json').write_text(text)


def _extra_model(sid, root):
    """The model of an owner outside the catalogue (`extras`): an example from its folder, and the
    acceptance fixture with its own library, as its test builds it."""
    from napkin.model import load_json, load_scenario

    path = extras(root)[sid]
    if sid != ACCEPTANCE[0]:
        return load_scenario(path)
    from napkin.model.ir import thaw
    from napkin.model.language import front

    origin = path.relative_to(root).as_posix()
    library = thaw(load_json(Path(root) / ACCEPTANCE[2]))
    return front.compile_file(front.read(path.read_text(encoding='utf-8'), origin), origin, library)


def capture_extra(sid, out, root):
    """The records of one owner outside the catalogue, written into `out/<ID>/`: its compiled model,
    its order and its default study. It has no pages, sweeps or edit sets."""
    from napkin.engine import evaluate_study

    folder = Path(out) / sid
    folder.mkdir(parents=True, exist_ok=True)

    def records():
        model = _extra_model(sid, Path(root))
        study = evaluate_study(model)
        return {
            'structure': _part(
                lambda: {name: _builders(model, name) for name in STRUCTURE if hasattr(model, name)}
            ),
            'order': _part(lambda: order_record(model)),
            'default': _part(lambda: _study(study)),
        }

    try:
        made = records()
    except Exception as exc:
        made = {'default': {FAILURE: f'{type(exc).__name__}: {exc}'}}
    _write(folder, made, root)


def capture_scenario(job):
    """Every record of one scenario, written into `out/<ID>/`: (ID, seconds)."""
    sid, out, root = job
    started = time.monotonic()
    _use_store()
    if sid in extras(root):
        capture_extra(sid, out, root)
        return sid, round(time.monotonic() - started, 1)
    from napkin.engine import edits_for, evaluate_study
    from napkin.model import load_json, load_scenario
    from tools import catalogue

    folder = Path(out) / sid
    folder.mkdir(parents=True, exist_ok=True)
    owner = catalogue.locate(sid, root)
    model = load_scenario(catalogue.entries(root)[sid])

    def structure():
        return {name: _builders(model, name) for name in STRUCTURE if hasattr(model, name)}

    def pages():
        from tools.publish.pages import Pages

        return Pages(model).all()

    study = evaluate_study(model)

    def sweeps():
        from tools.publish.brief import brief_of

        return {
            sweep.id: _study(evaluate_study(model, edits_for(model, sweep.edits), runs=[sweep.run]))
            for sweep in brief_of(model).sweeps
        }

    edit_files = sorted((owner.folder / 'edits').glob('*.json'))

    def edits():
        found = {}
        for path in edit_files:
            body = {key: value for key, value in load_json(path).items() if key != 'scenario'}
            found[path.name] = _study(evaluate_study(model, edits_for(model, body)))
        return found

    records = {
        'structure': _part(structure),
        'order': _part(lambda: order_record(model)),
        'pages': _part(pages),
        'default': _part(lambda: _study(study)),
        'sweeps': _part(sweeps),
        **({'edits': _part(edits)} if edit_files else {}),
    }
    _write(folder, records, root)
    return sid, round(time.monotonic() - started, 1)


def capture(out, root, scenario_ids=None, jobs=4):
    """Write the records of every scenario of `root` and of each model outside the catalogue that a
    comparison captures (`extras`), or of `scenario_ids` only, into `out`, and the machine they were
    captured on into `out/environment.json`."""
    _use_store()
    from tools import catalogue

    out, root = Path(out), Path(root)
    ids = list(scenario_ids or [*catalogue.entries(root), *extras(root)])
    out.mkdir(parents=True, exist_ok=True)
    (out / 'environment.json').write_text(json.dumps(_environment(), ensure_ascii=False, indent=1))
    context = multiprocessing.get_context('spawn')
    with ProcessPoolExecutor(jobs, mp_context=context) as pool:
        for sid, seconds in pool.map(capture_scenario, [(sid, str(out), str(root)) for sid in ids]):
            print(f'  {sid}: {seconds} s', flush=True)


# --- The canonical form of a record -----------------------------------------------------------------


def _ranks(value, out):
    if isinstance(value, dict):
        for key, item in value.items():
            if key == 'rank' and isinstance(item, list):
                out.add(tuple(item))
            else:
                _ranks(item, out)
    elif isinstance(value, list):
        for item in value:
            _ranks(item, out)


def _ordinal(value, order):
    if isinstance(value, dict):
        return {
            key: order[tuple(item)] if key == 'rank' and isinstance(item, list) else _ordinal(item, order)
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [_ordinal(item, order) for item in value]
    return value


def _canonical_text(text):
    """An expression text as `ast.unparse` writes it; a text that is no expression stays."""
    import ast

    if not isinstance(text, str):
        return text
    try:
        return ast.unparse(ast.parse(text, mode='eval').body)
    except (SyntaxError, ValueError, RecursionError):
        return text


def _canonical_triggers(value):
    """A plain value with the `gate` and each of the `times` of every trigger in one form. The
    classification joins them from texts, with brackets that mean nothing, so two revisions can write
    one condition in two ways."""
    if isinstance(value, list):
        return [_canonical_triggers(item) for item in value]
    if not isinstance(value, dict):
        return value
    found = {key: _canonical_triggers(item) for key, item in value.items()}
    trigger = found.get('trigger')
    if isinstance(trigger, dict) and 'when' in trigger:
        if 'gate' in trigger:
            trigger['gate'] = _canonical_text(trigger['gate'])
        if isinstance(trigger.get('times'), list):
            trigger['times'] = [_canonical_text(time) for time in trigger['times']]
    return found


def canonical(name, value):
    """A record of `name` without what a refactor may change and no result depends on: the source
    positions of a model, its event ranks as their order, the brackets of a trigger's `gate` and
    `times`, and the pages' `controls`."""
    if not isinstance(value, dict) or FAILURE in value:
        return value
    if name == 'structure':
        value = {key: item for key, item in value.items() if key != 'lines'}
        index = value.get('index')
        if isinstance(index, dict):
            index = {key: item for key, item in index.items() if key != 'file'}
            if isinstance(index.get('uses'), list):
                index['uses'] = [
                    {key: item for key, item in use.items() if key not in ('file', 'line')}
                    if isinstance(use, dict)
                    else use
                    for use in index['uses']
                ]
            value['index'] = index
        value = _canonical_triggers(value)
        ranks = set()
        _ranks(value, ranks)
        value = _ordinal(value, {rank: position for position, rank in enumerate(sorted(ranks))})
    elif name == 'pages':
        value = {key: item for key, item in value.items() if key != 'controls'}
    return value


def final_only(value):
    """`value` with only the final reporting point of each run report: its `reporting_points`, and its
    `samples` and `health` at that time."""
    if isinstance(value, list):
        return [final_only(item) for item in value]
    if not isinstance(value, dict):
        return value
    value = {key: final_only(item) for key, item in value.items()}
    points = value.get('reporting_points')
    if isinstance(points, dict) and isinstance(points.get('final'), dict):
        end = points['final'].get('t')
        value['reporting_points'] = {'final': points['final']}
        for key in ('samples', 'health'):
            if isinstance(value.get(key), list):
                value[key] = [item for item in value[key] if isinstance(item, dict) and item.get('t') == end]
    return value


def _matches(pattern, path):
    """Whether the keys of `path` match `pattern`: `*` matches one key and `**` any number."""
    if not pattern:
        return not path
    if pattern[0] == '**':
        return any(_matches(pattern[1:], path[start:]) for start in range(len(path) + 1))
    return bool(path) and pattern[0] in ('*', path[0]) and _matches(pattern[1:], path[1:])


def strip_paths(value, patterns, path=()):
    """`value` without the entries whose path (keys, and list positions as texts) a pattern matches."""
    if not patterns:
        return value
    if isinstance(value, dict):
        return {
            key: strip_paths(item, patterns, (*path, key))
            for key, item in value.items()
            if not any(_matches(pattern, (*path, key)) for pattern in patterns)
        }
    if isinstance(value, list):
        return [
            strip_paths(item, patterns, (*path, str(position)))
            for position, item in enumerate(value)
            if not any(_matches(pattern, (*path, str(position))) for pattern in patterns)
        ]
    return value


def strip(value, ignore):
    """`value` without the mapping entries named in `ignore`."""
    if isinstance(value, dict):
        return {key: strip(item, ignore) for key, item in value.items() if key not in ignore}
    if isinstance(value, list):
        return [strip(item, ignore) for item in value]
    return value


def remap(value, mapping):
    """`value` with each text (and key) that `mapping` names read as its new text."""
    if isinstance(value, dict):
        return {mapping.get(key, key): remap(item, mapping) for key, item in value.items()}
    if isinstance(value, list):
        return [remap(item, mapping) for item in value]
    if isinstance(value, str):
        return mapping.get(value, value)
    return value


def renamer(mapping):
    """A function that reads each whole path that a key of `mapping` names as its new path: a whole
    text, or whole segments between slashes, never part of a word. The longest key wins."""
    if not mapping:
        return lambda text: text
    keys = '|'.join(re.escape(key) for key in sorted(mapping, key=len, reverse=True))
    pattern = re.compile(f'(?<![^/])(?:{keys})(?![^/])')
    return lambda text: pattern.sub(lambda match: mapping[match.group(0)], text)


def rename(value, read):
    """`value` with every text and key read by `read` (`renamer`)."""
    if isinstance(value, dict):
        return {read(key): rename(item, read) for key, item in value.items()}
    if isinstance(value, list):
        return [rename(item, read) for item in value]
    if isinstance(value, str):
        return read(value)
    return value


def same(a, b):
    """Whether two plain values are equal bit for bit: a float by its bits (so -0.0 is not 0.0, and
    NaN is NaN), and a number never equals a number of another type."""
    if type(a) is not type(b):
        return False
    if isinstance(a, float):
        return a.hex() == b.hex()
    return a == b


def differences(a, b, path='', out=None, limit=SHOWN):
    """The places where `b` differs from `a`, up to `limit`: types, keys, key order, lengths, values."""
    out = [] if out is None else out
    if len(out) >= limit:
        return out
    if type(a) is not type(b):
        out.append(f'{path or "/"}: {type(a).__name__} {str(a)[:100]} | {type(b).__name__} {str(b)[:100]}')
    elif isinstance(a, dict):
        if list(a) != list(b):
            missing, extra = [k for k in a if k not in b], [k for k in b if k not in a]
            if missing or extra:
                out.append(
                    f'{path or "/"}: keys only in the base {missing[:6]}, only in this tree {extra[:6]}'
                )
            else:
                out.append(f'{path or "/"}: the keys are in another order')
        for key in a:
            if key in b:
                differences(a[key], b[key], f'{path}/{key}', out, limit)
    elif isinstance(a, list):
        if len(a) != len(b):
            out.append(f'{path or "/"}: {len(a)} items | {len(b)} items')
        for index, (x, y) in enumerate(zip(a, b)):
            differences(x, y, f'{path}[{index}]', out, limit)
    elif not same(a, b):
        out.append(f'{path or "/"}: {str(a)[:120]} | {str(b)[:120]}')
    return out


# --- The comparison of a change of the numerical core ---------------------------------------------

# How two results are judged when the numerical core changes (CONTRIBUTING.md, "Comparisons of a change
# of the numerical core"). Two values agree when they differ by no more than VALUE_RELATIVE of the
# larger, plus an absolute term: VALUE_TOLERANCES absolute tolerances of the quantity, but no more than
# VALUE_SHARE of its largest value in the base run, and no less than one absolute tolerance. The
# absolute tolerance of a quantity follows its authored size, which can be far above its values: without
# the share, such a quantity could change by a large part of its value unseen. An outcome and a formula have no
# tolerance of their own: they take VALUE_RELATIVE of their largest value in the run, plus
# OUTCOME_ABSOLUTE. A time that the model writes, and a time before the run's first numerical segment,
# agrees within EXACT_TIME_H. Any other time of a step agrees within LOCATED_TIME_RELATIVE of the larger
# of one hour and the time. The base side says which rule a time takes: the side under test cannot
# widen its own tolerance.
VALUE_RELATIVE = 1e-6
VALUE_TOLERANCES = 1000
VALUE_SHARE = 1e-3
OUTCOME_ABSOLUTE = 1e-9
EXACT_TIME_H = 1e-8
LOCATED_TIME_RELATIVE = 1e-6
# The keys of a run's report that hold numbers of the simulation; every other key compares exactly.
SIMULATED = ('samples', 'reporting_points', 'trace', 'numerical_diagnostics', 'peaks')
# The discrete values that are times: when an event last happened, and when a state took its value.
TIME_SUFFIXES = ('__time', '__entered')


class Sorted:
    """The differences of two captures, sorted for a change of the numerical core:

    - `within`: the number of values and times that differ within their tolerance;
    - `shifted`: the number of moments whose time differs within the tolerance of a time that a root
      gives, and `largest_shift`, the largest such difference in hours;
    - `discrete`: each difference of an event, an outcome, an order, a moment, a status, a warning or
      any other value that is no number of the simulation;
    - `beyond`: each value or time that differs by more than its tolerance, and each number that is
      not finite.

    A difference of the first two kinds needs no word. Each one of the last two is listed, and must be
    explained before the change lands."""

    def __init__(self):
        self.within, self.largest_shift = 0, 0.0
        self.moments = set()
        self.discrete, self.beyond = [], []

    @property
    def shifted(self):
        return len(self.moments)

    def exact(self, path, a, b):
        self.discrete += differences(a, b, path, limit=SHOWN)

    def _finite(self, path, a, b):
        """Whether both numbers are finite; a number that is not is listed, unless the two are the same
        infinity."""
        if math.isfinite(a) and math.isfinite(b):
            return True
        if not (same(float(a), float(b)) and math.isinf(a)):
            self.beyond.append(f'{path}: {a!r} | {b!r} (not finite)')
        return False

    def value(self, path, a, b, floor):
        """Two values of the simulation: numbers within their tolerance, or the same other value."""
        if not _number(a) or not _number(b):
            self.exact(path, a, b)
        elif self._finite(path, a, b) and not same(float(a), float(b)):
            if abs(a - b) <= VALUE_RELATIVE * max(abs(a), abs(b)) + floor:
                self.within += 1
            else:
                self.beyond.append(f'{path}: {a!r} | {b!r} (apart by {abs(a - b):.3g}, allowed {floor:.3g})')

    def time(self, path, a, b, loose, moment=None):
        """Two times of one thing. `loose` says that a root can have given the time, so it takes the
        tolerance of a located time. `moment` names the moment of a step, which counts once however
        many steps and values repeat its time; a time with no moment is an echo and is not counted."""
        if not _number(a) or not _number(b):
            self.exact(path, a, b)
            return
        if not self._finite(path, a, b) or same(float(a), float(b)):
            return
        apart = abs(a - b)
        if apart <= EXACT_TIME_H:
            self.within += moment is not None
        elif loose and apart <= LOCATED_TIME_RELATIVE * max(1.0, abs(a), abs(b)):
            if moment is not None:
                self.moments.add(moment)
                self.largest_shift = max(self.largest_shift, apart)
        else:
            kind = (
                'a time that a root can give'
                if loose
                else 'a time that the model writes or a closed form gives'
            )
            self.beyond.append(f'{path}: {a!r} | {b!r} ({kind}, apart by {apart:.3g} h)')

    @property
    def failed(self):
        return bool(self.discrete or self.beyond)


def _number(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def _floors(states):
    """{quantity: the absolute difference that its tolerance allows} of the numbers of a run of the
    base: VALUE_TOLERANCES absolute tolerances, but no more than VALUE_SHARE of the quantity's largest
    value in the run, and no less than one absolute tolerance."""
    names, tolerances = states.get('names') or (), states.get('tolerances') or ()
    peaks = [0.0] * len(names)
    for key in ('steps', 'grid'):
        for row in states.get(key) or ():
            values = row.get('values') if isinstance(row, dict) else None
            if isinstance(values, list) and len(values) == len(names):
                for k, value in enumerate(values):
                    if _number(value) and math.isfinite(value):
                        peaks[k] = max(peaks[k], abs(value))
    return {
        name: max(tolerance, min(VALUE_TOLERANCES * tolerance, VALUE_SHARE * peak))
        for name, tolerance, peak in zip(names, tolerances, peaks)
        if _number(tolerance)
    }


def _scales(report):
    """{outcome: its largest value in the report of one run of the base}, over the samples, the
    reporting points and the peaks: what the tolerance of an outcome is a share of."""
    found = {}

    def see(values):
        for name, value in (values or {}).items() if isinstance(values, dict) else ():
            if _number(value) and math.isfinite(value):
                found[name] = max(found.get(name, 0.0), abs(value))

    for sample in report.get('samples') or ():
        see(sample.get('values') if isinstance(sample, dict) else None)
    for point in (report.get('reporting_points') or {}).values():
        see(point.get('values') if isinstance(point, dict) else None)
    see(
        {
            name: peak.get('value')
            for name, peak in (report.get('peaks') or {}).items()
            if isinstance(peak, dict)
        }
    )
    return found


def _sort_values(found, path, a, b, floor_of):
    """The values of the outcomes at one time: the same names, each value within its tolerance."""
    if not isinstance(a, dict) or not isinstance(b, dict) or list(a) != list(b):
        found.exact(path, a, b)
        return
    for name in a:
        found.value(f'{path}/{name}', a[name], b[name], floor_of(name))


def _sort_point(found, path, a, b, floor_of):
    """One reporting point or sample: its time and its statuses exactly, its values within tolerance."""
    if not isinstance(a, dict) or not isinstance(b, dict):
        found.exact(path, a, b)
        return
    found.exact(
        path, {k: v for k, v in a.items() if k != 'values'}, {k: v for k, v in b.items() if k != 'values'}
    )
    _sort_values(found, f'{path}/values', a.get('values'), b.get('values'), floor_of)


def _loose(states, t):
    """Whether a root can have given a time of the base run: the time is after the start of the run's
    first numerical segment."""
    first = states.get('numerical_from')
    return _number(first) and _number(t) and t > first


def _sort_discrete(found, path, names, a, b, states):
    """The discrete values after a step or at a time of the grid: a time within the tolerance of a
    time (an echo of a step's time, so it is not counted), every other value exactly."""
    if not isinstance(a, list) or not isinstance(b, list) or len(a) != len(b) or len(a) != len(names):
        found.exact(path, a, b)
        return
    for name, x, y in zip(names, a, b):
        if name.endswith(TIME_SUFFIXES):
            found.time(f'{path}/{name}', x, y, _loose(states, x))
        else:
            found.exact(f'{path}/{name}', x, y)


def _step_loose(states, position):
    """Whether the time of a step of the base run takes the tolerance of a located time: the model
    writes no time for it, and the run's first numerical segment starts before it."""
    steps = states.get('steps') or []
    if position >= len(steps) or not isinstance(steps[position], dict):
        return False
    step = steps[position]
    return step.get('written') is None and _loose(states, step.get('t'))


def _sort_states(found, path, a, b):
    """The numbers of one run (`run_states`). The base side, `a`, gives each tolerance."""
    if not isinstance(a, dict) or not isinstance(b, dict):
        found.exact(path, a, b)
        return
    if (
        'numerical_from' not in a
        or 'tolerances' not in a
        or any('written' not in step for step in a.get('steps') or () if isinstance(step, dict))
    ):
        found.discrete.append(
            f'{path}: the base has no tolerances, no start of its numerical segments or no written times: '
            'capture the base again with this revision of the comparison'
        )
        return
    for key in ('names', 'discrete', 'formulas', 'tolerances'):
        found.exact(f'{path}/{key}', a.get(key), b.get(key))
    names, discrete, formulas = a.get('names') or [], a.get('discrete') or [], a.get('formulas') or []
    floors = _floors(a)
    peaks = {}
    for row in a.get('grid') or ():
        for name, value in zip(formulas, row.get('formulas') or ()) if isinstance(row, dict) else ():
            if _number(value) and math.isfinite(value):
                peaks[name] = max(peaks.get(name, 0.0), abs(value))
    for key in ('steps', 'grid'):
        rows, others = a.get(key) or [], b.get(key) or []
        if len(rows) != len(others):
            found.discrete.append(f'{path}/{key}: {len(rows)} rows | {len(others)} rows')
            continue
        for position, (row, other) in enumerate(zip(rows, others)):
            place = f'{path}/{key}[{position}]'
            if not isinstance(row, dict) or not isinstance(other, dict):
                found.exact(place, row, other)
                continue
            if key == 'steps':
                # The trace has the same step: its time is counted there.
                found.time(f'{place}/t', row.get('t'), other.get('t'), _step_loose(a, position))
            else:
                found.exact(f'{place}/t', row.get('t'), other.get('t'))
            values, theirs = row.get('values') or [], other.get('values') or []
            if len(values) != len(theirs) or len(values) != len(names):
                found.exact(f'{place}/values', values, theirs)
            else:
                for name, x, y in zip(names, values, theirs):
                    found.value(f'{place}/{name}', x, y, floors.get(name, 0.0))
            _sort_discrete(
                found, f'{place}/discrete', discrete, row.get('discrete'), other.get('discrete'), a
            )
            if key == 'grid':
                values, theirs = row.get('formulas') or [], other.get('formulas') or []
                if len(values) != len(theirs) or len(values) != len(formulas):
                    found.exact(f'{place}/formulas', values, theirs)
                else:
                    for name, x, y in zip(formulas, values, theirs):
                        floor = VALUE_RELATIVE * peaks.get(name, 0.0) + OUTCOME_ABSOLUTE
                        found.value(f'{place}/formulas/{name}', x, y, floor)


def _sort_diagnostics(found, path, a, b):
    """Two lists of diagnostics: each warning and each error the same, by its code, its severity, its
    place and its run. A note (`info`) holds numbers of one engine's own steps, such as a correction of
    roundoff at a bound: the notes can differ, and a different number of them counts as one difference
    within tolerance."""

    def serious(items):
        return [
            {key: item.get(key) for key in ('code', 'severity', 'path', 'run')}
            for item in items or ()
            if isinstance(item, dict) and item.get('severity') != 'info'
        ]

    found.exact(path, serious(a), serious(b))
    if len(a or ()) != len(b or ()):
        found.within += 1


def _sort_run(found, path, a, b, states_a, states_b):
    """The report of one run and its numbers. The base side, `a` and `states_a`, gives each tolerance."""
    if not isinstance(a, dict) or not isinstance(b, dict):
        found.exact(path, a, b)
        return
    states_a = states_a if isinstance(states_a, dict) else {}
    floors = _floors(states_a)
    scales = _scales(a)

    def outcome_floor(name):
        return VALUE_RELATIVE * scales.get(name, 0.0) + OUTCOME_ABSOLUTE

    def rest(report):
        """What compares exactly: every key that holds no number of the simulation. The list of the
        numerical segments says how one engine cut the run, so it is left out."""
        kept = {key: value for key, value in report.items() if key not in SIMULATED}
        settings = kept.get('numerical_settings')
        if isinstance(settings, dict):
            kept['numerical_settings'] = {k: v for k, v in settings.items() if k != 'integration_segments'}
        return kept

    found.exact(path, rest(a), rest(b))
    # The samples and the reporting points.
    samples, others = a.get('samples') or [], b.get('samples') or []
    if len(samples) != len(others):
        found.discrete.append(f'{path}/samples: {len(samples)} items | {len(others)} items')
    for position, (sample, other) in enumerate(zip(samples, others)):
        _sort_point(found, f'{path}/samples[{position}]', sample, other, outcome_floor)
    points, others = a.get('reporting_points') or {}, b.get('reporting_points') or {}
    if list(points) != list(others):
        found.exact(f'{path}/reporting_points', list(points), list(others))
    for name in points:
        if name in others:
            _sort_point(found, f'{path}/reporting_points/{name}', points[name], others[name], outcome_floor)
    # The trace: the same steps in the same order, each at its time.
    trace, others = a.get('trace') or [], b.get('trace') or []
    if len(trace) != len(others):
        found.discrete.append(f'{path}/trace: {len(trace)} steps | {len(others)} steps')
    numbers = ('t', 'changes', 'transfers')
    for position, (entry, other) in enumerate(zip(trace, others)):
        place = f'{path}/trace[{position}]'
        if not isinstance(entry, dict) or not isinstance(other, dict):
            found.exact(place, entry, other)
            continue
        found.exact(
            place,
            {key: value for key, value in entry.items() if key not in numbers},
            {key: value for key, value in other.items() if key not in numbers},
        )
        found.time(
            f'{place}/t',
            entry.get('t'),
            other.get('t'),
            _step_loose(states_a, position),
            (path, entry.get('t')),
        )
        changes, theirs = entry.get('changes') or {}, other.get('changes') or {}
        if list(changes) != list(theirs):
            found.exact(f'{place}/changes', changes, theirs)
        else:
            for name in changes:
                found.value(f'{place}/changes/{name}', changes[name], theirs[name], floors.get(name, 0.0))
        moves, theirs = entry.get('transfers') or [], other.get('transfers') or []
        if len(moves) != len(theirs) or any(m[:2] != o[:2] for m, o in zip(moves, theirs)):
            found.exact(f'{place}/transfers', moves, theirs)
        else:
            for move, their in zip(moves, theirs):
                found.value(f'{place}/transfers/{move[0]}', move[2], their[2], floors.get(move[0], 0.0))
    _sort_diagnostics(
        found, f'{path}/numerical_diagnostics', a.get('numerical_diagnostics'), b.get('numerical_diagnostics')
    )
    # The peaks. A peak is the largest of the candidates that one engine's segments give, so its time
    # takes the tolerance of a located time and is not counted.
    peaks, others = a.get('peaks') or {}, b.get('peaks') or {}
    if list(peaks) != list(others):
        found.exact(f'{path}/peaks', list(peaks), list(others))
    for name in peaks:
        peak, other = peaks[name], others.get(name)
        place = f'{path}/peaks/{name}'
        if not isinstance(peak, dict) or not isinstance(other, dict):
            if name in others:
                found.exact(place, peak, other)
            continue
        found.exact(
            place,
            {key: value for key, value in peak.items() if key not in ('value', 't')},
            {key: value for key, value in other.items() if key not in ('value', 't')},
        )
        found.value(f'{place}/value', peak.get('value'), other.get('value'), outcome_floor(name))
        found.time(f'{place}/t', peak.get('t'), other.get('t'), True)
    _sort_states(found, f'{path}/states', states_a, states_b)


def sort_study(found, path, a, b):
    """Sort the differences of two records of one study (`_study`) into `found`; `a` is the base side.
    The record of each trajectory's parts is of one revision's own form, so it is left out: the numbers
    of each run stand in for it."""
    if not isinstance(a, dict) or not isinstance(b, dict) or FAILURE in a or FAILURE in b:
        found.exact(path, a, b)
        return
    apart = ('report', 'trajectories', 'states', 'diagnostics')
    found.exact(
        path,
        {key: value for key, value in a.items() if key not in apart},
        {key: value for key, value in b.items() if key not in apart},
    )
    _sort_diagnostics(found, f'{path}/diagnostics', a.get('diagnostics'), b.get('diagnostics'))
    report, other = a.get('report'), b.get('report')
    if not isinstance(report, dict) or not isinstance(other, dict):
        found.exact(f'{path}/report', report, other)
        return
    found.exact(
        f'{path}/report',
        {key: value for key, value in report.items() if key not in ('runs', 'diagnostics')},
        {key: value for key, value in other.items() if key not in ('runs', 'diagnostics')},
    )
    _sort_diagnostics(
        found, f'{path}/report/diagnostics', report.get('diagnostics'), other.get('diagnostics')
    )
    runs, others = report.get('runs') or {}, other.get('runs') or {}
    if list(runs) != list(others):
        found.exact(f'{path}/report/runs', list(runs), list(others))
    states_a = a.get('states') if isinstance(a.get('states'), dict) else {}
    states_b = b.get('states') if isinstance(b.get('states'), dict) else {}
    for run in runs:
        if run in others:
            place = f'{path}/report/runs/{run}'
            try:
                _sort_run(found, place, runs[run], others[run], states_a.get(run), states_b.get(run))
            except (AttributeError, IndexError, KeyError, TypeError) as exc:
                # Two records of different forms: a difference, never a crash of the comparison.
                found.discrete.append(
                    f'{place}: the two records have different forms ({type(exc).__name__}: {exc})'
                )


def sort_record(found, record, a, b):
    """Sort the differences of two records of one name; `a` is the base side. A study, or a mapping of
    studies (the sweeps and the edit sets), compares within the tolerances; any other record exactly."""
    if record == 'default':
        sort_study(found, '', a, b)
    elif record in ('sweeps', 'edits') and isinstance(a, dict) and isinstance(b, dict) and FAILURE not in a:
        if list(a) != list(b):
            found.exact('', list(a), list(b))
        for name in a:
            if name in b:
                sort_study(found, f'/{name}', a[name], b[name])
    else:
        found.exact('', a, b)


def _owners(folder):
    """The owners of a capture: its folders of records."""
    return {name.split('/')[0] for name in _records(folder)}


def _records(folder):
    """{record name: path} of a capture: `<owner>/<record>.json`."""
    return {path.relative_to(folder).as_posix(): path for path in sorted(Path(folder).glob('*/*.json'))}


def compare(
    base,
    current,
    ignore=DEFAULT_IGNORE,
    mapping=None,
    *,
    renames=None,
    ignore_paths=(),
    reporting=None,
    owners=None,
    sorted_into=None,
):
    """{record: differences} of the records of two captures, and the names of all records; a record on
    one side only differs too. Both sides take their canonical form first; `renames` and `mapping`
    then read the base's owners, paths and texts as the current ones. `owners` (current names) limits
    the comparison to those owners, as a selected capture holds only them.

    With `sorted_into`, a `Sorted`, the comparison is the one of a change of the numerical core: the
    numbers of each study compare within their tolerances and go into it, and the differences of a
    record are then only the ones that must be explained."""
    ignore, mapping = set(ignore), mapping or {}
    read = renamer(renames or {})
    patterns = [tuple(pattern.split('/')) for pattern in ignore_paths]
    before_paths, collisions = {}, {}
    for old, path in _records(base).items():
        name = read(old)
        if name in before_paths:
            collisions.setdefault(name, [before_paths[name].relative_to(base).as_posix()]).append(old)
        before_paths[name] = path
    after_paths = _records(current)
    if owners is not None:
        before_paths = {name: path for name, path in before_paths.items() if name.split('/')[0] in owners}
        after_paths = {name: path for name, path in after_paths.items() if name.split('/')[0] in owners}
    names = sorted(set(before_paths) | set(after_paths))
    found = {
        name: [f'the rename gives these base records one name: {", ".join(olds)}']
        for name, olds in collisions.items()
    }

    def form(name, path):
        record = name.split('/')[-1].removesuffix('.json')
        value = canonical(record, json.loads(path.read_text(encoding='utf-8')))
        if reporting == 'final':
            value = final_only(value)
        value = strip_paths(
            value, [pattern[1:] for pattern in patterns if pattern and pattern[0] in (record, '*')]
        )
        return strip(value, ignore)

    for name in names:
        before, after = before_paths.get(name), after_paths.get(name)
        if name in found:
            continue
        if before is None or after is None:
            found[name] = ['only in this tree' if after is not None else 'only in the base']
            continue
        old = remap(rename(form(name, before), read), mapping)
        new = form(name, after)
        if sorted_into is None:
            changes = differences(old, new)
        else:
            one = Sorted()
            sort_record(one, name.split('/')[-1].removesuffix('.json'), old, new)
            sorted_into.within += one.within
            sorted_into.moments |= {(name, *moment) for moment in one.moments}
            sorted_into.largest_shift = max(sorted_into.largest_shift, one.largest_shift)
            sorted_into.discrete += [f'{name}{line}' for line in one.discrete]
            sorted_into.beyond += [f'{name}{line}' for line in one.beyond]
            changes = [*one.discrete[:SHOWN], *one.beyond[:SHOWN]]
        if changes:
            found[name] = changes
    return found, names


def failures(folder, owners=None):
    """[(record, message)] of each capture failure in the records of `folder` (of `owners` only, when
    given)."""
    out = []
    for name, path in _records(folder).items():
        if owners is not None and name.split('/')[0] not in owners:
            continue
        try:
            value = json.loads(path.read_text(encoding='utf-8'))
        except ValueError as exc:
            out.append((name, f'unreadable record: {exc}'))
            continue
        if isinstance(value, dict) and FAILURE in value:
            out.append((name, value[FAILURE]))
    return out


def environment(folder):
    """The machine that a capture ran on, or None when it did not say."""
    path = Path(folder) / 'environment.json'
    return json.loads(path.read_text(encoding='utf-8')) if path.is_file() else None


def here():
    """The machine and numerical libraries of this process, as a capture writes them."""
    return json.loads(json.dumps(_environment(), ensure_ascii=False))


def baseline_records(directory):
    """The saved base records in `directory`: its `base` folder (the pinned revision of a kept
    comparison), or the folder itself when it holds a capture; None when it holds neither."""
    directory = Path(directory)
    for folder in (directory / 'base', directory):
        if (folder / 'environment.json').is_file():
            return folder
    return None


def overlaps(first, second):
    """Whether two folders are one folder or one holds the other."""
    first, second = Path(first).resolve(), Path(second).resolve()
    return first == second or first in second.parents or second in first.parents


def same_machine(base, current):
    """Whether two captures say they ran on the same machine, with the same numerical libraries."""
    machine = environment(base)
    return machine is not None and machine == environment(current)


def judge(base, current, allowed=None, renames=None, owners=None, tolerance=False):
    """Print the comparison of two captures and return the exit status: 0 when every record is the same,
    1 when a record differs, 2 when a capture failed on either side. `owners` limits it to those owners
    (current names). With `tolerance`, the comparison is the one of a change of the numerical core
    (`Sorted`): 0 when no difference must be explained, 1 when one must."""
    allowed = allowed or {}
    read = renamer(renames or {})
    base_owners = None if owners is None else {old for old in _owners(base) if read(old) in owners}
    failed = [('base', *item) for item in failures(base, base_owners)] + [
        ('tree', *item) for item in failures(current, owners)
    ]
    for side, name, message in failed:
        print(f'CAPTURE FAILED ({side}) {name}: {message}')
    found, names = compare(
        base,
        current,
        (*DEFAULT_IGNORE, *allowed.get('ignore', ())),
        allowed.get('map'),
        renames=renames,
        ignore_paths=allowed.get('ignore_paths', ()),
        reporting=allowed.get('reporting'),
        owners=owners,
        sorted_into=(sorted_into := Sorted() if tolerance else None),
    )
    for name, changes in found.items():
        print(f'DIFFERS {name}')
        for line in changes:
            print(f'    {line}')
    if sorted_into is None:
        print(f'{len(names) - len(found)} of {len(names)} records are the same bit for bit')
    else:
        print(f'{len(names) - len(found)} of {len(names)} records have no difference to explain')
        print(f'  within tolerance: {sorted_into.within} values and times')
        print(
            f'  moments whose time shifted: {sorted_into.shifted}'
            + (f', by {sorted_into.largest_shift:.3g} h at most' if sorted_into.shifted else '')
        )
        print(f'  discrete differences: {len(sorted_into.discrete)}')
        print(f'  beyond tolerance: {len(sorted_into.beyond)}')
    if failed:
        print(f'FAILED: {len(failed)} capture failures')
        return 2
    if sorted_into is None:
        print('IDENTICAL' if not found else f'{len(found)} records differ')
    else:
        print('WITHIN THE CONTRACT' if not found else f'{len(found)} records have differences to explain')
    return 1 if found else 0


# --- The command ------------------------------------------------------------------------------


def _git(root, *arguments):
    done = subprocess.run(['git', *arguments], cwd=root, capture_output=True, text=True, check=False)
    if done.returncode:
        raise SystemExit(f'git {" ".join(arguments)}: {done.stderr.strip()}')
    return done.stdout.strip()


def capture_code(root):
    """The capture code of the revision checked out at `root`."""
    for name in CAPTURE_CODE:
        if (Path(root) / name).is_file():
            return Path(root) / name
    raise SystemExit(f'no capture code in {root} (looked for {", ".join(CAPTURE_CODE)})')


def _side(script, out, root, args, store):
    """Capture one side in its own process, with that side's package first on the path."""
    environment = {
        **os.environ,
        'PYTHONPATH': str(root),
        'PYTHONDONTWRITEBYTECODE': '1',
        **{name: str(store) if store else 'off' for name in STORE_VARIABLES},
        **{name: '1' for name in ('OMP_NUM_THREADS', 'OPENBLAS_NUM_THREADS', 'MKL_NUM_THREADS')},
    }
    command = [
        sys.executable,
        '-B',
        str(script),
        '--capture',
        str(out),
        '--root',
        str(root),
        '--jobs',
        str(args.jobs),
    ]
    command += [part for sid in args.scenario or () for part in ('--scenario', sid)]
    return subprocess.run(command, cwd=root, env=environment, check=False).returncode


def _read_json(path, parser, what):
    try:
        return json.loads(Path(path).read_text(encoding='utf-8'))
    except (OSError, ValueError) as exc:
        parser.error(f'cannot read the {what} {path}: {exc}')


def main(argv=None):
    parser = argparse.ArgumentParser(
        prog='python -m tools.compare',
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument('--base', help='The revision to compare with (default: the merge base with main)')
    parser.add_argument(
        '--baseline', type=Path, help='Compare with the base records that --keep saved in this directory'
    )
    parser.add_argument(
        '--scenario', action='append', metavar='ID', help='Compare only this scenario (repeatable)'
    )
    parser.add_argument(
        '--allow',
        type=Path,
        help='A JSON file: {"ignore": [keys], "ignore_paths": [paths], "map": {base text: new text}, "reporting": "final"}',
    )
    parser.add_argument('--rename', type=Path, help='A JSON file: {old owner or path: new owner or path}')
    parser.add_argument('--jobs', type=int, default=os.cpu_count() or 4, help='Processes for each side')
    parser.add_argument('--keep', type=Path, help='Keep the records of both sides in this directory')
    parser.add_argument(
        '--tolerance',
        action='store_true',
        help='Compare a change of the numerical core: numbers within their tolerances, the rest exactly',
    )
    parser.add_argument('--capture', type=Path, help=argparse.SUPPRESS)
    parser.add_argument('--root', type=Path, help=argparse.SUPPRESS)
    args = parser.parse_args(argv)
    if args.capture:
        capture(args.capture, args.root, args.scenario, args.jobs)
        return 0

    from napkin import store
    from tools.catalogue import ROOT

    if args.base and args.baseline:
        parser.error('--base and --baseline exclude each other')
    allowed = _read_json(args.allow, parser, 'allow file') if args.allow else {}
    unknown = sorted(set(allowed) - ALLOWED)
    if unknown:
        parser.error(f'the allow file has unknown keys: {", ".join(unknown)}')
    if allowed.get('reporting') not in (None, 'final'):
        parser.error('the allow file\'s "reporting" can only be "final"')
    renames = _read_json(args.rename, parser, 'rename file') if args.rename else {}
    if not isinstance(renames, dict) or not all(
        isinstance(k, str) and isinstance(v, str) for k, v in renames.items()
    ):
        parser.error('the rename file maps texts to texts')
    directory = store.default_directory()
    temporary = Path(tempfile.mkdtemp(prefix='napkin-compare-'))
    records = temporary / 'records'
    worktree = temporary / 'base'
    started = time.monotonic()
    ignored = ', '.join((*DEFAULT_IGNORE, *allowed.get('ignore', ())))
    try:
        script = temporary / 'capture.py'
        shutil.copyfile(__file__, script)
        if args.baseline:
            base = baseline_records(args.baseline)
            if base is None:
                parser.error(
                    f'no saved base records in {args.baseline} (expected DIR/base or DIR/environment.json)'
                )
            if args.keep and overlaps(args.keep, args.baseline):
                parser.error(f'--keep {args.keep} would write into the baseline {args.baseline}')
            if environment(base) != here():
                print(
                    f'The records in {base} were captured on another machine, whose last bits can differ: '
                    'capture the base again here with --base REV --keep DIR'
                )
                return 2
            print(f'Compare the records in {base} with this working tree; ignored keys: {ignored}')
        else:
            revision = args.base or _git(ROOT, 'merge-base', 'HEAD', 'main')
            short = _git(ROOT, 'rev-parse', '--short', revision)
            _git(ROOT, 'worktree', 'add', '--detach', '--quiet', str(worktree), revision)
            base_script = temporary / 'capture_base.py'
            shutil.copyfile(capture_code(worktree), base_script)
            print(f'Compare {revision} ({short}) with this working tree; ignored keys: {ignored}')
            print(f'Capture of the base ({time.monotonic() - started:.0f} s):', flush=True)
            if _side(base_script, records / 'base', worktree, args, directory):
                print('The capture of the base failed')
                return 2
            base = records / 'base'
        print(f'Capture of the tree ({time.monotonic() - started:.0f} s):', flush=True)
        if _side(script, records / 'tree', ROOT, args, directory):
            print('The capture of the tree failed')
            return 2
        if args.keep:
            shutil.copytree(records, args.keep, dirs_exist_ok=True)
        if args.baseline and not same_machine(base, records / 'tree'):
            print(
                f'The records in {base} were captured on another machine, whose last bits can differ: '
                'capture the base again here with --base REV --keep DIR'
            )
            return 2
        owners = set(args.scenario) if args.scenario else None
        status = judge(base, records / 'tree', allowed, renames, owners, tolerance=args.tolerance)
        print(f'({time.monotonic() - started:.0f} s)')
        return status
    finally:
        if worktree.exists():
            subprocess.run(
                ['git', 'worktree', 'remove', '--force', str(worktree)],
                cwd=ROOT,
                capture_output=True,
                check=False,
            )
        shutil.rmtree(temporary, ignore_errors=True)


if __name__ == '__main__':
    raise SystemExit(main())
