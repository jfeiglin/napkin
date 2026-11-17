"""Studies: one edit document, checked as one transaction, and the runs simulated.

A study resolves the runs of a model under one edit document (napkin/schema/edits.schema.json).
`model/runs.py` checks the document itself: its shape, its model revision, the names that it uses,
each value against its input, and the edits of one level that meet in a run. Then the model resolves
runs (`Model.resolve`), which applies the blocking checks of the inputs and proves the bounds and
domains of each run's structure. A study of every run is one transaction over the declared runs. A
study of named runs resolves those runs only. A combination of options that no run makes is a run of
its own model (`Model.combination`), which checks it when it is asked for. If one check fails, the
study is rejected and nothing runs. The orders of the results of the standard runs are acceptance
tests (each scenario's `tests/expected-orders.json`, which scenarios/tests/test_catalogue.py checks),
not checks of a study.
"""

from __future__ import annotations

import json
import math
from dataclasses import dataclass, field

from .. import SCHEMA_VERSION, store
from ..expressions import ExpressionError
from ..model.analysis.values import input_check_failures
from ..model.ir import ModelError, thaw
from ..model.model import input_name
from ..model.runs import Runs
from .report import ReportingError, diagnostic, edits_report_copy, outputs_until
from .runtime import SimulationError, simulate

# Model, expression, numerical and reporting failures reject a study; anything else is an
# engine defect and raises.
STUDY_FAILURES = (ModelError, ExpressionError, SimulationError, ReportingError)
# The levels of an edit document, from the broadest to the narrowest.
EDIT_LEVELS = ('set', 'options', 'runs')


def edits_for(model, edits=None):
    """An edit document for this model revision: the schema version and the model hash, with the
    given edits (`set`, `options`, `runs`, `reason`)."""
    return {'schema_version': SCHEMA_VERSION, 'model_hash': model.model_hash, **(edits or {})}


@dataclass
class StudyResult:
    model_hash: str
    admissible: bool
    diagnostics: list
    effective_edits: dict
    runs: dict = field(default_factory=dict)
    model: object = field(default=None, repr=False)
    implementation_hash: str = ''
    # A played study (`play`): the first decision of its played run that waits for a pick, or None.
    decision: dict | None = None

    def __post_init__(self):
        if not self.implementation_hash and self.model is not None:
            self.implementation_hash = self.model.implementation_hash


def _errors(exc, **context):
    items = getattr(exc, 'diagnostics', None)
    if items:
        return [{**x, **context} for x in items]
    return [diagnostic('evaluation_error', str(exc), **context)]


def resolve_edits(model, edits=None, runs=None):
    """{run: resolved structure} of every run, or of the named `runs`, under one edit document.

    `model/runs.py` checks the document itself, whatever runs are named: its shape, its model
    revision, its names, each value against its input, and the edits of one level that meet. Each run
    resolves through `Model.resolve`, with its blocking input checks and the proofs of its structure.
    With no `runs`, the edits are one transaction over every run of the model. With `runs`, only the
    named runs resolve. Raises ModelError with every diagnostic, and resolves nothing, if one check
    fails. A diagnostic of a run names it (`run`).
    """
    if runs is not None:
        runs = set(runs)
        if runs - model.runs.keys():
            raise ModelError([diagnostic('run', f'Unknown runs {sorted(runs - model.runs.keys())}')])
    admitted = getattr(model, 'admission_runs', None)
    if admitted is not None:
        if runs is None:
            raise ModelError(
                [
                    diagnostic(
                        'admission_scope', 'A scoped model requires an explicit selection of admitted runs'
                    )
                ]
            )
        outside = runs - set(admitted)
        if outside:
            raise ModelError(
                [diagnostic('admission_scope', f'Runs outside the model admission scope: {sorted(outside)}')]
            )
    table = Runs.from_table(model.run_table)
    values = table.resolve(edits, runs, model_hash=model.model_hash)
    errors, resolved = [], {}
    for run, result in values.items():
        try:
            resolved[run] = model.resolve(run, result.values)
        except ModelError as exc:
            errors += [{**item, 'run': run} for item in exc.diagnostics]
    if errors:
        raise ModelError(errors)
    return resolved


# Who may pick the outcomes of an actor's choices in a played run.
CONTROLLERS = ('reader', 'agent')
METHODS = ('chance', *CONTROLLERS)  # how a run takes the outcome of a choice


def play_problems(model, resolved, play):
    """Why a play request cannot apply (docs/engine.md, "Play"), or nothing: it names one run,
    its `control` gives a method (`chance`, `reader` or `agent`) to actors of that run (things with
    `sees`, or their sets of copies) or to their choices (events marked `choice`), and its `picks` are
    a list of `{event, outcome}`."""
    if not isinstance(play, dict) or set(play) - {'run', 'control', 'picks'}:
        return [diagnostic('play', 'A play request has a run, its control and its picks')]
    run, control, picks = play.get('run'), play.get('control'), play.get('picks', [])
    if run not in resolved:
        return [diagnostic('play', f'Play one run of the study, not {run!r}')]
    rs = resolved[run]
    entities, rules = rs.entities, rs.rules
    actors = {name for name, entity in entities.items() if entity.sees is not None}
    actors |= {entities[name].origin for name in actors}
    choices = set()  # by `actor.event` and by the event of a set of copies
    for rid, rule in rules.items():
        if rule.choice:
            choices.add(rid)
            origin = entities[rule.entity].origin
            if origin:
                choices.add(f'{origin}.{rid.rsplit(".", 1)[1]}')
    problems = []
    if not isinstance(control, dict) or not control:
        problems.append(diagnostic('play', 'Name the actors that you control: {"thing": "reader"}', run=run))
    else:
        for name, who in control.items():
            if who not in METHODS:
                problems.append(
                    diagnostic(
                        'play', f'{name} is chosen by chance, a reader or an agent, not {who!r}', run=run
                    )
                )
            if name not in actors and name not in choices:
                problems.append(
                    diagnostic(
                        'play', f'{name} is not an actor of this run, nor a choice of an actor', run=run
                    )
                )
    if not isinstance(picks, list) or not all(
        isinstance(item, dict) and isinstance(item.get('event'), str) and isinstance(item.get('outcome'), str)
        for item in picks
    ):
        problems.append(diagnostic('play', 'The picks are a list of {"event": …, "outcome": …}', run=run))
    return problems


def initiation_diagnostics(rs, trajectory, run):
    """The start's event fires first, at t=0: the first entry of the story is its firing, which counts
    also when the start has no text of its own."""
    # The start of a run (`initiation`) is plain data, not a typed part.
    initiation = rs.initiation
    if not initiation:
        return []
    first = next(
        (entry for entry in trajectory.trace if entry['semantic'] or entry['rule'] == initiation['rule']),
        None,
    )
    if first and first['t'] == 0 and first['rule'] == initiation['rule']:
        return []
    seen = 'nothing' if first is None else f'{first["rule"]} at t={first["t"]:g} h'
    return [
        diagnostic(
            'initiation',
            f'The start {initiation["rule"]} must fire first, at t=0; the first event was {seen}',
            run=run,
        )
    ]


def run_checks(rs, trajectory, library, run):
    """The diagnostics of one simulated run, the same wherever a run is simulated: in a study, in a
    sample of a Monte Carlo study and in a played session. They are the diagnostics of its simulation,
    each with the run (`run`), and the check of its start (`initiation_diagnostics`); then, when
    neither has an error, its outcomes at time zero and at the end that it reached, which must be
    reportable: a reporting failure is an error. A run that paused at a decision is checked up to
    its pause."""
    # The typed parts of the run are made once, for the two checks that read the run.
    found = [{**item, 'run': run} for item in trajectory.diagnostics]
    found += initiation_diagnostics(rs, trajectory, run)
    if not any(item.get('severity', 'error') == 'error' for item in found):
        end = trajectory.horizon if trajectory.end_time is None else trajectory.end_time
        try:
            outputs_until({'resolved': rs, 'trajectory': trajectory}, library, [0, end])
        except STUDY_FAILURES as exc:
            found += _errors(exc, run=run)
    return found


def evaluate_study(model, edits=None, numerical_settings=None, *, runs=None, play=None):
    """Every run is checked under one edit document, as one transaction, and simulated.

    ``runs`` resolves, checks and simulates only the named runs; the checks of the edit document
    itself still apply (`resolve_edits`). Reporting is separate, so repeated samples reuse the same
    trajectories. ``play`` (`{run, control, picks}`) plays one run: the decisions of the actors that
    `control` names take the picks of the log, in order, and the first decision without one takes the
    model's choice and is the result's `decision` (docs/engine.md, "Play").
    """
    document, problem = edit_document(edits)
    if problem:
        # A document that is no object has no copy for the report.
        shown = edits_report_copy(edits or {}) if edits is None or isinstance(edits, dict) else {}
        return StudyResult(model.model_hash, False, [problem], shown, model=model)
    edits = document
    result = StudyResult(model.model_hash, False, [], edits, model=model)
    runs = None if runs is None else list(runs)
    unknown = set(runs or ()) - model.runs.keys()
    if unknown:
        result.diagnostics.append(diagnostic('run', f'Unknown runs {sorted(unknown)}'))
        return result
    try:
        resolved = resolve_edits(model, edits, runs)
    except STUDY_FAILURES as exc:
        result.diagnostics.extend(_errors(exc))
        return result
    asked = {}  # what the played run asks of its run: who picks, and the picks
    if play is not None:
        problems = play_problems(model, resolved, play)
        if problems:
            result.diagnostics.extend(problems)
            return result
        # The engine reads which outcome each pick takes; the log keeps who picked, when and why.
        picks = [{'event': item['event'], 'outcome': item['outcome']} for item in play.get('picks', [])]
        asked[play['run']] = {'control': dict(play['control']), 'picks': picks}
    library = thaw(model.library)
    result.diagnostics.extend(evidence_warnings(model))
    # First each run's checks, then the simulations of the runs that they let run, together, so the
    # run store (`napkin/store.py`) can share them between processes. Each run's
    # diagnostics keep their order: its checks, then its simulation's.
    names = [run for run in model.runs if runs is None or run in runs]
    found, ready = {}, []
    for run in names:
        diagnostics = found[run] = []
        try:
            rs = resolved[run]
            checks = [{**item, 'run': run} for item in input_check_failures(rs, library['units'])]
            diagnostics.extend(checks)
            if not any(item['severity'] == 'error' for item in checks):
                ready.append(run)  # a blocking check stops this run before it runs
        except STUDY_FAILURES as exc:
            diagnostics.extend(_errors(exc, run=run))
    # The played run goes with what it asks: who picks, and the picks.
    items = [
        (resolved[run], library, numerical_settings, *([asked[run]] if run in asked else ())) for run in ready
    ]
    simulated = store.simulate_all(simulate, items, STUDY_FAILURES)
    trajectories = dict(zip(ready, simulated))
    for run in names:
        result.diagnostics.extend(found[run])
        if run not in trajectories:
            continue
        trajectory = trajectories[run]
        if isinstance(trajectory, STUDY_FAILURES):
            result.diagnostics.extend(_errors(trajectory, run=run))
            continue
        try:
            rs = resolved[run]
            # Endpoint output failures are simulation failures, even if nobody asks for a plot.
            result.diagnostics.extend(run_checks(rs, trajectory, library, run))
            result.runs[run] = {'resolved': rs, 'trajectory': trajectory}
            if play is not None and run == play['run']:
                result.decision = trajectory.decision
        except STUDY_FAILURES as exc:
            result.diagnostics.extend(_errors(exc, run=run))
    result.admissible = not any(x.get('severity', 'error') == 'error' for x in result.diagnostics)
    if not result.admissible:
        result.runs = {}  # never expose partial accepted runs from a rejected transaction
        result.decision = None
    return result


def edit_document(edits):
    """(the JSON copy of an edit document, None), or (None, its first problem): the first checks of
    a study, before it resolves any run. The document is an object, or nothing; its tree is finite
    JSON (`_json_input_problem`); and the copy is what `json` writes and reads again. A study and a
    `Session` check a document with this one function."""
    if edits is not None and not isinstance(edits, dict):
        return None, diagnostic('edits_shape', 'Edits must be an object')
    supplied = edits or {}
    problem = _json_input_problem(supplied)
    if problem:
        return None, problem
    # Arbitrary Python callers receive the same serializable admission envelope.
    # JSON copying rejects cycles, resource objects and nonfinite values directly.
    try:
        return json.loads(json.dumps(supplied, allow_nan=False)), None
    except (ValueError, TypeError, RecursionError, OverflowError) as exc:
        return None, diagnostic('edits_json', f'Use finite JSON input values: {exc}')


def _json_input_problem(value, path='edits', active=None):
    active = set(active or ())
    if len(active) >= 64:
        return diagnostic('edits_json', 'Use an input tree within 64 nested containers', path=path)
    if isinstance(value, (dict, list)):
        if id(value) in active:
            return diagnostic('edits_json', 'Supply a finite JSON tree at this input', path=path)
        active.add(id(value))
        children = value.items() if isinstance(value, dict) else enumerate(value)
        for key, child in children:
            if isinstance(value, dict) and not isinstance(key, str):
                return diagnostic('edits_json', 'Use string input identifiers', path=path)
            found = _json_input_problem(child, f'{path}/{key}', active)
            if found:
                return found
        return None
    if value is None or isinstance(value, (str, bool)):
        return None
    if isinstance(value, (int, float)):
        try:
            if math.isfinite(value):
                return None
        except OverflowError:
            pass
    return diagnostic('edits_json', 'Supply a finite JSON value at this input', path=path)


def analyze_bounds(model, edits, target):
    """Declared candidates and witnessed points, never falsely certified intervals.

    target: {'input': entity.field, 'level': 'set', 'options' or 'runs', 'name': the option or the
    run (no name for `set`)}. A level is one that an edit document accepts, with the same meaning
    (model/runs.py): the option is one that a run names. Each point edits the input at that level,
    with the other edits kept, and evaluates the study, which checks the point in every run that the
    edit reaches. The current value is the input's value in the first run that the level reaches. The
    candidate is the two values of a bool input or the names of a named input (`values`), or the
    input's range (`min`, `max`).
    Static check feasibility does not prove full dynamic admissibility, so this API never labels a
    range safe.
    """
    level, owner = target['level'], target.get('name')
    if level not in EDIT_LEVELS:
        raise ValueError(f'Unknown edit level {level!r}')
    key = input_name(target['input'])
    info = model.inputs.get(key)
    if info is None:
        raise ValueError(f'Unknown input {target["input"]!r}')
    table = Runs.from_table(model.run_table)
    # The edits name an input as runs.py does: a copy's input is `set.k.field`.
    written = next(name for name in table.inputs if input_name(name) == key)
    document = thaw(edits) if edits else edits_for(model)
    # The run whose value of the input is the current one.
    if level == 'set':
        run, options = next(iter(table.runs.items()))
    elif level == 'options':
        if not isinstance(owner, str) or owner not in table.group_of:
            raise ValueError(f'Unknown option {owner!r}')
        # An edit of an option reaches each run that names it: take the first.
        run, options = next(((r, p) for r, p in table.runs.items() if owner in p), (None, None))
        if options is None:
            raise ValueError(f'No run names the option {owner!r}')
    elif owner in table.runs:
        run, options = owner, table.runs[owner]
    else:
        raise ValueError(f'Unknown run {owner!r}')
    if info['fixed']:
        return {'status': 'locked', 'input': key, 'certified': False, 'candidates': [], 'checked_points': []}
    # The edits as given must hold as one transaction, as each probe's study checks them.
    resolve_edits(model, document)
    # The current value of an uncertain input is its central value.
    current = model.point_values(table.values_of(options, document, run).values)[key]
    if info['type'] == 'bool':
        probes = [False, True]
        candidate = {'values': probes}
    elif info['type'] == 'names':
        probes = list(info['values'])
        candidate = {'values': probes}
    else:
        low, high = info['range']
        probes = sorted({low, high, (low + high) / 2, current})
        candidate = {'min': low, 'max': high}
    points = []
    for value in probes:
        probe = thaw(document)
        if level == 'set':
            probe.setdefault('set', {})[written] = value
        else:
            probe.setdefault(level, {}).setdefault(owner, {})[written] = value
        result = evaluate_study(model, probe)
        points.append({'value': value, 'admissible': result.admissible, 'diagnostics': result.diagnostics})
    return {
        'status': 'unresolved',
        'input': key,
        'certified': False,
        'candidates': [candidate],
        'checked_points': points,
    }


def evidence_warnings(model):
    """Reachable source limitations survive every accepted execution path: each unverified claim and
    each assumption that is not confirmed gives one warning. The notes of the file give none: the
    calculation never reads them."""
    claims, assumptions = map(set, (model.evidence['claims'], model.evidence['assumptions']))
    warnings = []
    for record in model.library.get('claims', ()):
        if record['id'] not in claims:
            continue
        status = record.get('verification', {}).get('status', 'unverified')
        if status != 'verified':
            warnings.append(
                {
                    'code': 'evidence:' + record['id'],
                    'severity': 'warning',
                    'message': f'Source claim {record["id"]}. Verification status: {status}. Coefficient transfers use their recorded input basis.',
                    'evidence': thaw(record.get('verification', {})),
                }
            )
    for record in model.library.get('assumptions', ()):
        status = record.get('review', {}).get('status', 'unreviewed')
        if record['id'] in assumptions and status != 'confirmed':
            warnings.append(
                {
                    'code': 'assumption:' + record['id'],
                    'severity': 'warning',
                    'message': f'{record["id"]}. Input basis: selected scenario assumption. Review status: {status}.',
                }
            )
    return warnings
