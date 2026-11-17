"""Reports read from finished runs: outcomes, lags, health, peaks and the evidence behind them
(docs/engine.md).

Reporting never changes a run. Every value is read from a trajectory's stored solution, so the
same run can be sampled at any times without running again.

A function here takes a resolved run as its typed parts (`model/structure.py`).
"""

from __future__ import annotations

import bisect
import copy
import dataclasses
import itertools
import math
from collections import OrderedDict
from collections.abc import Mapping

from scipy.integrate import quad

from .. import SCHEMA_VERSION, __version__
from ..core import expr as nodes
from ..expressions import ExpressionError, UnitSystem, evaluate, names_in
from ..model import structure as typed
from ..model.analysis.structure import lag_delays
from ..model.evidence import claim_digest, digest
from ..model.ir import COUNT, ENTERED, TIME, thaw
from ..paths import names_of


class ReportingError(ValueError):
    """An outcome cannot be reported: a nonfinite value or a violated sign claim."""


def diagnostic(code, message, **context):
    return {'code': code, 'severity': 'error', 'message': str(message), **context}


class UnknownValue(Exception):
    pass


def _require_complete(trajectory):
    if trajectory.paused:
        raise ReportingError('A paused trajectory cannot be reported as a completed run')


# ---- outcomes -----------------------------------------------------------------------------------


def evaluate_outputs(run, library, times, *, unit_registry=None):
    """Outcome values and statuses at each time, in each outcome's own unit, of one completed run
    ({'resolved', 'trajectory'})."""
    _require_complete(run['trajectory'])
    return outputs_until(run, library, times, unit_registry=unit_registry)


def outputs_until(run, library, times, *, unit_registry=None):
    """The rows of `evaluate_outputs` of a run that is complete or that paused at a decision: each
    time lies from zero to the end that the run reached, its horizon or the time of its pause."""
    rs, trajectory = run['resolved'], run['trajectory']
    defs, units = rs.outcomes, library['units']
    registry = unit_registry if unit_registry is not None else UnitSystem(units)
    return outputs_from(defs, _OfTrajectory(trajectory, defs, registry), units, registry, times)


class _OfTrajectory:
    """What the rows of the outputs read of a trajectory (`outputs_from`): the end that the run
    reached, the times of its events, and the value of an expression at a time."""

    def __init__(self, trajectory, defs, registry):
        self.trajectory, self.defs, self.registry = trajectory, defs, registry
        self.end = trajectory.horizon if trajectory.end_time is None else trajectory.end_time
        self.environments = {}

    def moments(self):
        return {entry['t'] for entry in self.trajectory.trace}

    def number(self, expression, t, value, name=None):
        """The value of an expression at t. Another outcome that it names has its value at that
        time (`value(name, t)` gives it with its status); `name` is the outcome whose own
        expression this is, or None for a delay of a lag."""
        env = self.environments.get(t)
        if env is None:
            env = self.environments[t] = _OutcomeEnvironment(self.trajectory.env_at(t), t, self.defs, value)
        return evaluate(expression, env, self.registry)


class _OutcomeEnvironment(dict):
    """A trajectory environment in which other outcomes resolve to their values at the same time."""

    def __init__(self, env, t, defs, value):
        super().__init__(env)
        self.t, self.defs, self.value = t, defs, value

    def __contains__(self, key):
        return key in self.defs or super().__contains__(key)

    def __getitem__(self, key):
        if key in self.defs:
            val, status = self.value(key, self.t)
            if status != 'estimated':
                raise UnknownValue(key)
            return val
        return super().__getitem__(key)


def outputs_from(defs, reader, units, registry, times, names=None):
    """The rows of the outputs of a run at `times`: for each outcome its value in its own unit and
    its status, with its lag. `defs` are the outcomes of the run (`Resolved.outcomes`); `names`, the
    outcomes that the rows hold (default: each), and an outcome that one of them reads is computed
    for it. `reader`
    gives what the rows read of the run: `end`, the end that it reached; `moments()`, the times of
    its events; and `number(expression, t, value, name)`, the value of an expression at a time
    (`_OfTrajectory`; `timeline/reports.py` has the reader of a run of a model with a table)."""
    end = reader.end

    def scale_of(unit):
        # A declared unit has its entry's scale; a composed unit with no entry is made of declared
        # units (`UnitRegistry.parse_unit`), as the compiler reads it.
        return units[unit]['scale'] if unit in units else registry[unit].scale

    memo = {}
    # The pieces of the windows of uniform lags: their cuts for each outcome and delays, and the
    # integral over each piece, or the status that stops it.
    cuts, pieces = {}, {}

    def reportable(t):
        return not isinstance(t, bool) and isinstance(t, (int, float)) and math.isfinite(t) and 0 <= t <= end

    def value(name, t, delayed=True):
        key = (name, t, delayed)
        if key in memo:
            return memo[key]
        if t < 0:
            # Before time zero a lagged quantity has not begun: a known zero only where the
            # outcome is estimated at the start, otherwise that same status.
            status = value(name, 0.0, False)[1]
            memo[key] = (0.0, status) if status == 'estimated' else (None, status)
            return memo[key]
        o = defs[name]
        if delayed and o.lag is not None:
            memo[key] = lagged(name, o.lag, t)
            return memo[key]
        status = o.status
        if status != 'estimated':
            memo[key] = (None, status)
            return memo[key]
        try:
            val = reader.number(o.expr, t, value, name)
        except UnknownValue:
            return None, 'unestimated'
        if isinstance(val, bool) or not isinstance(val, (int, float)) or not math.isfinite(val):
            raise ReportingError(f'Outcome {name} is not finite numeric at {t}')
        if o.nonnegative and val < -1e-8 * scale_of(o.unit):
            raise ReportingError(f'Negative nonnegative outcome {name} at {t}: {val}')
        # A nonnegative outcome that roundoff leaves a little below zero is zero.
        if o.nonnegative and val < 0:
            val = 0.0
        memo[key] = (val, 'estimated')
        return memo[key]

    def lagged(name, lag, t):
        """A report kernel over the outcome's history; a jump at exactly t - delay is included."""
        if lag.type == 'fixed':
            return value(name, t - reader.number(lag.delay, t, value), False)
        if lag.type == 'mixture':
            parts = [
                (c.weight, value(name, t - reader.number(c.delay, t, value), False))
                for c in lag.components
                if c.weight > 0
            ]
            statuses = {x[1] for _, x in parts}
            if statuses == {'estimated'}:
                return sum(w * x[0] for w, x in parts), 'estimated'
            return None, 'unestimated' if 'unestimated' in statuses else 'not_applicable'
        a, b = reader.number(lag.minimum, t, value), reader.number(lag.maximum, t, value)
        if a == b:
            return value(name, t - a, False)
        lo, hi = max(0.0, t - b), max(0.0, t - a)
        points = window_cuts(name, a, b)
        inside = points[bisect.bisect_right(points, lo) : bisect.bisect_left(points, hi)]
        try:
            if t - b < 0:  # the window's part before time zero has the status at the start
                integrand(-1.0, name)
            area = sum(
                piece(name, x, y) for x, y in itertools.pairwise([lo, *inside, hi] if hi > lo else [lo])
            )
            return area / (b - a), 'estimated'
        except UnknownValue as missing:
            return None, missing.args[0]

    def integrand(x, name):
        val, st = value(name, x, False)
        if st != 'estimated':
            raise UnknownValue(st)
        return val

    def window_cuts(name, a, b):
        """The ends of the windows of every reporting time and the event times, in order. A window
        is a sum of the pieces between them, and the windows of an outcome share their pieces: its
        delays read inputs only, so every window has the same ends relative to its time."""
        key = (name, a, b)
        if key not in cuts:
            ends = {max(0.0, float(t) - delay) for t in times if reportable(t) for delay in (a, b)}
            cuts[key] = sorted(ends | reader.moments())
        return cuts[key]

    def piece(name, x, y):
        """The integral of an outcome from x to y, once for every window that holds the piece."""
        key = (name, x, y)
        if key not in pieces:
            try:
                pieces[key] = quad(integrand, x, y, args=(name,), epsabs=1e-7, epsrel=1e-10, limit=100)[0]
            except UnknownValue as missing:
                pieces[key] = UnknownValue(missing.args[0])
        if isinstance(pieces[key], UnknownValue):
            raise UnknownValue(pieces[key].args[0])
        return pieces[key]

    rows = []
    for t in times:
        if not reportable(t):
            raise ReportingError(f'Reporting time {t} outside [0, {end}]')
        values, statuses = {}, {}
        for name in defs if names is None else names:
            definition = defs[name]
            v, status = value(name, float(t))
            values[name] = None if v is None else v / scale_of(definition.unit)
            statuses[name] = status
        rows.append({'t': float(t), 'values': values, 'statuses': statuses})
    return rows


def reporting_points(times, horizon):
    """{point: time} of the reporting points of a run: each time that a request names, by its number
    of hours (`repr`), in order, then `final`, the end of the run."""
    points = {repr(t): t for t in sorted({float(t) for t in times or ()})}
    points['final'] = float(horizon)
    return points


def peak_candidates(run, library, *, unit_registry=None):
    """Observed maxima over the ends and midpoints of the segments: candidates only, since the
    expression language does not establish that an outcome has one peak. The times that a report
    asks for are no candidates, so a peak is the same whatever times a report asks for. A cumulative
    outcome the compiler proved nondecreasing peaks at the horizon, and only its peak is
    `certified`."""
    tr = run['trajectory']
    rs = run['resolved']
    times = {0.0, tr.horizon}
    for seg in tr._segments:
        times.update([seg.start, seg.end, (seg.start + seg.end) / 2])
        if seg.end > seg.start:
            times.add(math.nextafter(seg.end, seg.start))
    # The rows read the typed parts that are made here, so the run is read once.
    rows = evaluate_outputs({**run, 'resolved': rs}, library, sorted(times), unit_registry=unit_registry)
    return peaks_of(rows, rs.outcomes, rs.proven_cumulative_outcomes, tr.horizon)


def peaks_of(rows, outcomes, cumulative, horizon):
    """The peak of each output from its rows at the candidate times (`peak_candidates`): the largest
    value that is known, with its time; the value at the horizon, certified, for an output of
    `cumulative` (the outputs that the compiler proved never to fall) that is estimated at each
    time."""
    out = {}
    for name in outcomes:
        if name in cumulative:
            final = next(row for row in rows if row['t'] == horizon)
            if final['values'][name] is not None and all(
                row['statuses'][name] == 'estimated' for row in rows
            ):
                out[name] = {
                    'value': final['values'][name],
                    't': horizon,
                    'certified': True,
                    'status': 'estimated',
                    'partial': False,
                }
                continue
        known = [r for r in rows if r['values'][name] is not None]
        best = max(known, key=lambda r: r['values'][name]) if known else None
        out[name] = {
            'value': None if best is None else best['values'][name],
            't': None if best is None else best['t'],
            'certified': False,
            'status': 'unresolved' if best else 'unestimated',
            'partial': len(known) != len(rows),
        }
    return out


# ---- entities -----------------------------------------------------------------------


def health(rs, env, units):
    """Each entity's modes, status and status text: those of the first case that holds, or of the
    default. An entity that shows no status is `inactive` and has no text (null)."""
    out = {}
    for eid, entity in rs.entities.items():
        # The notes of a thing (`metadata`) are plain data, not a typed part.
        if entity.metadata.get('internal', False):
            continue
        status, text = 'inactive', None
        label = rs.labels.get(entity.health) if entity.health else None
        if label:
            case = next((c for c in label.cases if evaluate(c.when, env, units)), label.default)
            status, text = case.value, case.text
        out[eid] = {
            'modes': {mode: env[mode] for mode in entity.modes},
            'health': status,
            'label': text,
        }
    return out


# ---- evidence -----------------------------------------------------------------------------------


def _basis(basis):
    if isinstance(basis, (list, tuple)):
        return [_basis(item) for item in basis]
    if not isinstance(basis, Mapping):
        return None
    out = {key: basis[key] for key in ('name', 'kind', 'assumption', 'convention') if key in basis}
    claims = sorted({link['claim'] for link in basis.get('links', []) if 'claim' in link})
    return out | ({'claims': claims} if claims else {})


def evidence_parts(rs):
    """(every model part with its basis, what each part depends on, what each outcome depends on). An
    outcome is a part too, so that an outcome that reads other outcomes depends on what their
    expressions and lags read. A flow depends on what limits what it delivers: its source stock, a
    destination that has a maximum, its rationing limit and the other flows of a transaction that
    moves together. A count or time of an event is the rules that add the event, and the time that a
    named state was entered is that state. An event that only a line names fires when its caller's
    outcome does: it depends on each rule whose outcome names it.

    What a rule reads and what it can change are the structure's queries (`Structure.reads`,
    `Structure.writes`). An outcome reads its expression and the delays of its lag; a stock, a tally
    or a number state reads its start value, its bounds and its rate."""
    parts, depends = {}, {}
    writers, emitters, callers = {}, {}, {}
    for rid, rule in rs.rules.items():
        for name in rs.writes(rule):
            writers.setdefault(name, set()).add(rid)
        for event in rule.events():
            emitters.setdefault(event, set()).add(rid)
        for outcome in rule.outcomes:
            for target in outcome.do.fire:
                callers.setdefault(target, set()).add(rid)

    def of(names):
        found = set()
        for name in names:
            if name.endswith((COUNT, TIME)):
                found |= emitters.get(name.rsplit('__', 1)[0], set())
            elif name.endswith(ENTERED):
                found.add(name[: -len(ENTERED)])
            else:
                found.add(name)
        return found

    def read(*sources):
        """The names that some expressions of a part read themselves: a number, and a part that
        is not there, read nothing."""
        return set().union(*map(rs.names, sources))

    for collection in ('parameters', 'quantities', 'computed', 'labels', 'flows', 'modes', 'rules'):
        for name, item in rs.section(collection).items():
            parts[name] = _basis(item.basis)
    starts = {}
    for name, outcome in rs.outcomes.items():
        delays = () if outcome.lag is None else lag_delays(outcome.lag)
        starts[name] = of(read(outcome.expr, *delays))
    for name, outcome in rs.outcomes.items():
        if name not in parts:
            parts[name] = _basis(outcome.basis)
            depends[name] = starts[name]
    for name, quantity in rs.quantities.items():
        rate = rs.rates[name].expr if name in rs.rates else None
        found = of(read(quantity.initial, quantity.minimum, quantity.maximum, rate))
        found |= writers.get(name, set())
        found |= {fid for fid, f in rs.flows.items() if name in (f.source, f.target)}
        depends[name] = found
    for name, c in rs.computed.items():
        depends[name] = of(names_in(c.expr))
    for name, label in rs.labels.items():
        depends[name] = of(set().union(*(names_in(case.when) for case in label.cases)))
    together = {f: set(group.flows) - {f} for group in rs.coupling.values() for f in group.flows}
    for fid, flow in rs.flows.items():
        found = of(names_in(flow.rate)) | together.get(fid, set())
        if flow.source:
            found.add(flow.source)
        filled = rs.quantities.get(flow.target) if flow.target else None
        if filled is not None and filled.maximum is not None:
            found.add(flow.target)
        if flow.allocation in rs.allocation:
            found |= of(names_in(rs.allocation[flow.allocation].capacity))
        depends[fid] = found
    for mid in rs.modes:
        depends[mid] = writers.get(mid, set())
    for rid, rule in rs.rules.items():
        depends[rid] = of(rs.reads(rule)) | callers.get(rid, set())
    return parts, depends, starts


def _can_hold(node, reach):
    """False only when a condition cannot hold for any value that its named states can take."""
    if isinstance(node, nodes.BoolOp):
        results = [_can_hold(value, reach) for value in node.values]
        return all(results) if node.op == 'and' else any(results)
    if isinstance(node, nodes.Const) and isinstance(node.value, bool):
        return node.value
    if isinstance(node, nodes.Compare) and len(node.ops) == 1 and node.ops[0] in ('eq', 'ne'):
        left, right = node.operands
        if isinstance(left, nodes.Const):
            left, right = right, left
        name = left.name if isinstance(left, nodes.Ref) else None
        if name in reach and isinstance(right, nodes.Const) and isinstance(right.value, str):
            if node.ops[0] == 'eq':
                return right.value in reach[name]
            return bool(reach[name] - {right.value})
    return True


def firing_rules(rs):
    """The rules that can fire in a run of this structure.

    A named state takes its start value and every value that a rule that can fire gives it. A rule
    can fire unless a condition that it needs asks a named state for a value that it never takes, or,
    for a rule that only a line fires, no rule that can fire names it. Every other condition counts
    as possible, so the set is never too small.
    """
    reach = {name: {mode.initial} for name, mode in rs.modes.items()}
    conditions = {}
    for rid, rule in rs.rules.items():
        trigger = rule.trigger
        text = trigger.gate if trigger.kind in ('timer', 'crossing') else trigger.when
        conditions[rid] = typed.node(text)
    firing, named, changed = set(), set(), True
    while changed:
        changed = False
        for rid, rule in rs.rules.items():
            if rid in firing:
                continue
            if rule.named:
                if rid not in named:
                    continue
            elif conditions[rid] is not None and not _can_hold(conditions[rid], reach):
                continue
            firing.add(rid)
            changed = True
            for step in rule.steps():
                named.update(step.fire)
                for name, value in step.set.items():
                    if name in reach:
                        fixed = isinstance(value.mode, str)
                        reach[name] |= {value.mode} if fixed else set(rs.modes[name].values)
    return firing


def _closure(start, parts, depends, skip=frozenset()):
    """The parts that `start` depends on, never through a part in `skip`."""
    found, pending = set(), list(start)
    while pending:
        part = pending.pop()
        if part in found or part not in parts or part in skip:
            continue
        found.add(part)
        pending.extend(depends.get(part, ()))
    return found


def left_out_parts(left_out):
    """The names of the parts that a run's structure leaves out (`model.left_out[starts]`)."""
    return {name for section in (left_out or {}).values() for name in section}


def evidence_trail(rs, trajectory, library, units, left_out=None):
    """For each outcome, the parts it can depend on and which of them this run exercised: a rule
    that fired, a flow that moved material, and every value and parameter read. A rule that can
    never fire in this run's structure is possible, not exercised, and so is every part that the
    outcome reaches only through such a rule. Each part keeps its basis; the trail pins the library
    and the digest of every record it cites.

    `rs` can be a run's resolved structure with the sections of its whole structure
    (`model.whole[starts]`), and `left_out` the parts that the run's structure leaves out
    (`model.left_out[starts]`): the run exercised nothing through a part that it left out, so every
    rule left out is idle and the flows that moved material are among the run's own flows. The
    evidence of a part left out shows as possible, not exercised (docs/python-api.md)."""
    gone = left_out_parts(left_out)
    parts, depends, starts = evidence_parts(rs)
    fired = {entry['rule'] for entry in trajectory.trace}
    idle = (set(rs.rules) - firing_rules(rs)) | gone
    # A flow is exercised when it delivered material, not when it was only asked to move.
    active = set(trajectory.moved) - gone
    outcomes, used, refs = {}, set(), []
    for name, outcome in rs.outcomes.items():
        start = starts[name]
        found = _closure(start, parts, depends)
        exercised = {
            p
            for p in _closure(start, parts, depends, idle)
            if (p not in rs.rules or p in fired) and (p not in rs.flows or p in active)
        }
        outcomes[name] = {
            'basis': _basis(outcome.basis),
            # A lag has no basis of its own: the builder writes none, and the typed lag takes none.
            'kernel': None,
            'exercised': sorted(exercised),
            'possible': sorted(found - exercised),
        }
        used |= found
        for ref in (outcomes[name]['basis'], outcomes[name]['kernel']):
            if ref:
                refs.extend(ref if isinstance(ref, list) else [ref])
    for p in used:
        if parts[p]:
            refs.extend(parts[p] if isinstance(parts[p], list) else [parts[p]])
    claims = {c for ref in refs for c in ref.get('claims', ())}
    assumptions = {ref['assumption'] for ref in refs if ref.get('assumption')}
    conventions = {ref['convention'] for ref in refs if ref.get('convention')}
    records = {item['id']: claim_digest(item) for item in library['claims'] if item['id'] in claims}
    records |= {item['id']: digest(item) for item in library['assumptions'] if item['id'] in assumptions}
    records |= {
        item['id']: digest(item) for item in library.get('conventions', ()) if item['id'] in conventions
    }
    return {
        'library': digest(library),
        'records': dict(sorted(records.items())),
        'parts': {p: parts[p] for p in sorted(used)},
        'outcomes': outcomes,
    }


# ---- report -------------------------------------------------------------------------------------


def edits_report_copy(value, active=None, depth=0):
    """Preserve JSON inputs and represent rejected non-JSON values with null."""
    if depth >= 64:
        return None
    if isinstance(value, Mapping):
        active = set(active or ())
        if id(value) in active:
            return None
        active.add(id(value))
        return {str(key): edits_report_copy(child, active, depth + 1) for key, child in value.items()}
    if isinstance(value, (tuple, list)):
        active = set(active or ())
        if id(value) in active:
            return None
        active.add(id(value))
        return [edits_report_copy(child, active, depth + 1) for child in value]
    if value is None or isinstance(value, (str, bool)):
        return value
    if isinstance(value, (int, float)):
        try:
            return value if math.isfinite(value) else None
        except OverflowError:
            return None
    return None


class _EnvironmentCache:
    """One reporting call's bounded memo of exact trajectory environments.

    Outcomes and entity health sample the same instants. Keys keep the exact timestamp and
    impulse side; every caller receives its own dictionary.
    """

    __slots__ = ('_capacity', '_environments', '_trajectory')

    def __init__(self, trajectory, capacity=1024):
        self._trajectory = trajectory
        self._environments = OrderedDict()
        self._capacity = capacity

    def __getattr__(self, name):
        return getattr(self._trajectory, name)

    def env_at(self, t, side='right'):
        key = (float(t), side)
        if key in self._environments:
            environment = self._environments.pop(key)
        else:
            environment = self._trajectory.env_at(t, side=side)
        self._environments[key] = environment
        if len(self._environments) > self._capacity:
            self._environments.popitem(last=False)
        return dict(environment)


def report_envelope(study, admissible):
    """The parts of a report that every study has, admitted or not. `scenario` and `variant` name the
    model by its folders (`paths.names_of`): the package, and the variant or None."""
    scenario, variant = names_of(study.model.origin)
    return {
        'model_hash': study.model_hash,
        'implementation_hash': study.implementation_hash,
        'schema_version': SCHEMA_VERSION,
        'engine_version': __version__,
        'admissible': admissible,
        'status': 'accepted' if admissible else 'rejected',
        'library_hash': study.model.library_hash,
        'scenario': scenario,
        'variant': variant,
        'title': study.model.scenario.title,
        'effective_edits': edits_report_copy(study.effective_edits),
        'diagnostics': copy.deepcopy(study.diagnostics),
        'runs': {},
    }


def run_evidence(model, rs, trajectory, library, units):
    """The evidence trail of one run: its resolved structure with every part of its whole structure,
    with the rule that the run exercised nothing through a part that its structure left out."""
    starts = tuple(rs.starts)
    # The run with each section of its whole structure in the place of its own.
    every = model.whole[starts]
    sections = {
        item.name: getattr(every, item.name) for item in dataclasses.fields(typed.Structure) if item.init
    }
    whole = dataclasses.replace(rs, **sections)
    return evidence_trail(whole, trajectory, library, units, thaw(model.left_out[starts]))


def sample_result(study, reporting_times=None):
    """A JSON-ready report of an accepted study. Each run reports its outcomes at `final`, the model
    horizon, and at each of the `reporting_times` (`reporting_points`); the model names no times."""
    for run in study.runs.values():
        _require_complete(run['trajectory'])
    if reporting_times is not None:
        reporting_times = list(reporting_times)
        horizon = study.model.time['horizon']
        for t in reporting_times:
            if (
                isinstance(t, bool)
                or not isinstance(t, (int, float))
                or not math.isfinite(t)
                or not 0 <= t <= horizon
                or any(not 0 <= t <= run['trajectory'].horizon for run in study.runs.values())
            ):
                raise ValueError(f'Invalid reporting time {t!r}')
    try:
        return _sample_result(study, reporting_times)
    except (ReportingError, ExpressionError, ArithmeticError) as exc:
        # A numerical reporting failure is never a legitimate unknown outcome
        # and must not expose a partially accepted comparison.
        report = report_envelope(study, False)
        report['status'] = 'reporting_failure'
        report['diagnostics'].append(diagnostic('reporting_failure', str(exc)))
        return report


def _sample_result(study, reporting_times):
    if not study.admissible:
        return report_envelope(study, False)
    model = study.model
    library = thaw(model.library)
    unit_registry = UnitSystem(library['units'])
    reports = report_envelope(study, True)
    for name, completed in study.runs.items():
        # The typed parts of the run are made once, for each function that reads the run here.
        rs = completed['resolved']
        run = {**completed, 'resolved': rs, 'trajectory': _EnvironmentCache(completed['trajectory'])}
        trajectory = run['trajectory']
        points = reporting_points(reporting_times, trajectory.horizon)
        times = sorted(set(points.values()))
        rows = evaluate_outputs(run, library, times, unit_registry=unit_registry)
        by_time = {r['t']: r for r in rows}
        reports['runs'][name] = {
            'label': model.runs[name]['name'],
            'options': list(rs.options),
            'starts': list(rs.starts),
            'horizon': trajectory.horizon,
            # Each output as its part writes it: with the keys of the compiled model, in their
            # order (`Part.plain`).
            'outcomes': typed.thawed(rs.outcomes),
            'effective_inputs': rs.parameter_values,
            'numerical_settings': trajectory.settings,
            'samples': rows,
            'reporting_points': {point: by_time[t] for point, t in points.items()},
            'trace': trajectory.trace,
            'health': [{'t': t, 'entities': health(rs, trajectory.env_at(t), unit_registry)} for t in times],
            'evidence': run_evidence(model, rs, trajectory, library, unit_registry),
            'numerical_diagnostics': trajectory.diagnostics,
            'peaks': peak_candidates(run, library, unit_registry=unit_registry),
        }
    # thaw rebuilds every mapping and list, so the report shares nothing with the study.
    return thaw(reports)
