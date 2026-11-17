"""The reports of a run of a plan of a hybrid core: a model with a table (docs/engine.md, "Tables
and tiers").

A report of a model with no table reads a `Trajectory`, which holds every quantity at every time
(`engine/report.py`). A run of a table of many rows has none. These functions give the same rows
from the result of the run:

- `outputs(result, times)`: the value and the status of each output at each time, as
  `report.evaluate_outputs` gives them, with the lag of each output. The run must keep the record
  of its past (`timeline.run(plan, record=True)`); a value at a time is read from that record.
- `evidence(result)`: the evidence trail, as `report.evidence_trail` gives it, with the parts of
  the model of the representatives: a part of a class is exercised when it is for one of its rows.

- `report(result, times, rows)`: the report of the run, with the parts of the report of a run of a
  study (`report.sample_result`). A table can have very many rows, so what the report says of the
  things of a table is by group: a group is one class of rows, the rows that the engine runs as one
  family. For each group the report gives how many of its rows are in each status and in each
  value of each named state at each time, and, for each event and outcome, how many times it
  happened, in how many rows, and the first and the last time. The rows that `rows` names have their
  own health and their own steps of the trace, as each thing outside a table has. The expression of
  an output is written with one member of a list for each group: the name of the row that stands
  for the group.

What they do not give: the rows of a study with edits or samples. An output that reads an output
with a lag is named as outside.
"""

from __future__ import annotations

import itertools
import math
from collections import Counter
from dataclasses import asdict
from types import SimpleNamespace

from ...core import expr
from ...expressions import names_in
from ...model.structure import thawed
from .. import report
from .plan import SCALARS, Outside
from .run import Past, Unknown, _one


class _OfResult:
    """What the rows of the outputs read of a run (`report.outputs_from`)."""

    def __init__(self, result):
        run = result.run
        if not run.record:
            raise ValueError('the run kept no record of its past: timeline.run(plan, record=True)')
        self.run, self.plan = run, run.plan
        self.end = float(result.end_time)
        self.environments, self.delays = {}, {}

    def moments(self):
        return {float(entry[0]) for entry in self.run.trace}

    def number(self, expression, t, value, name=None):
        plan, run = self.plan, self.run
        if name is not None:
            node = plan.outputs[name]
        else:
            node = self.delays.get(expression)
            if node is None:
                node = self.delays[expression] = plan.node(expression, SCALARS, 'the delay of a lag')
        env = self.environments.get(t)
        if env is None:
            env = self.environments[t] = Past(run, SCALARS, None, t)
        try:
            found = _one(run.value(node, env))
        except Unknown as missing:
            raise report.UnknownValue(str(missing)) from None
        return found.item() if hasattr(found, 'item') else found


def outputs(result, times, names=None):
    """The rows of `report.evaluate_outputs` of a run of a plan: for each time, the value of each
    output (of `names`, default each) in its own unit and its status."""
    if result.paused:
        raise report.ReportingError('A paused run cannot be reported as a completed run')
    plan = result.run.plan
    outcomes = plan.s.outcomes
    lagged = {name for name, item in outcomes.items() if item.lag is not None}
    for name, item in outcomes.items():
        read = names_in(item.expr) & lagged if item.expr is not None else ()
        if read:
            raise Outside(f'the output {name}, which reads an output with a lag ({sorted(read)[0]})')
    units = plan.library['units']
    return report.outputs_from(plan.resolved.outcomes, _OfResult(result), units, plan.units, times, names)


def evidence(result):
    """The evidence trail of a run of a plan (`report.evidence_trail`), over the parts of the model
    of the representatives. A rule of a class fired when it fired for one of its rows, and a flow
    of a class moved material when it did for one of its rows (`Run.flowing`)."""
    run = result.run
    plan = run.plan
    run.flows_at_end()
    stands = {
        host: space.family.host
        for space in plan.spaces
        if space.family is not None
        for host in space.family.hosts
    }

    def of_class(name):
        host, dot, rest = name.partition('.')
        return stands.get(host, host) + dot + rest

    read = SimpleNamespace(
        trace=[{'rule': of_class(rule)} for _, rule, _ in result.trace],
        moved=set(run.flowing) | {of_class(name) for name in run.moved},
    )
    return report.evidence_trail(plan.resolved, read, plan.library, plan.units)


# ---- the report of a run ------------------------------------------------------------------------


def _families(plan):
    """(space, family) of each group of the plan, in the order of the model."""
    return [(space, space.family) for space in plan.spaces if space.family is not None]


def _named_rows(plan, rows):
    """{the name of a row: (its space, its place)} of the rows that a caller names."""
    places = {host: (space, j) for space, family in _families(plan) for j, host in enumerate(family.hosts)}
    unknown = sorted(set(rows) - places.keys())
    if unknown:
        raise ValueError(f'{unknown[0]} is no row of a table of this model')
    return {name: places[name] for name in rows}


def events(result):
    """What happened in each group: for each event of the group and each outcome (None for an event
    that starts to wait), how many times it happened, in how many rows, and the first and the last
    time. An event has the name that it has for the row that stands for the group."""
    run = result.run
    plan = run.plan
    found = {}
    for t, _, index, j, outcome, *_ in run.log:
        rule = plan.rules[index]
        if rule.space == SCALARS:
            continue
        key = (rule.space, index, None if outcome is None else outcome.name)
        entry = found.get(key)
        if entry is None:
            found[key] = [1, {j}, t, t]
        else:
            entry[0] += 1
            entry[1].add(j)
            entry[3] = t
    out = []
    for (space, index, outcome), (count, places, first, last) in found.items():
        family = plan.spaces[space].family
        out.append(
            {
                'group': family.host,
                'event': run.rule_name(plan.rules[index], 0),
                'outcome': outcome,
                'count': count,
                'rows': len(places),
                'first': first,
                'last': last,
            }
        )
    return out


def _texts(plan, label):
    """{status: its text} of a label of the model of the representatives."""
    item = plan.s.labels[label]
    return {case.value: case.text for case in (*item.cases, item.default)}


def health(result, t, rows=()):
    """The health of the things at one time. `entities`: each thing outside a table, and each row
    that `rows` names, as `report.health` gives it (its named states, its status, the text of its
    status). `groups`: for each group, the number of its rows, how many of them have each value of
    each named state, and how many have each status, with the text of each status. A thing that
    shows no status is `inactive`."""
    run = result.run
    plan = run.plan
    named = _named_rows(plan, rows)
    entities, groups = {}, {}
    for eid, entity in plan.s.entities.items():
        if entity.metadata.get('internal', False):
            continue
        space = plan.spaces[_space_of_entity(plan, eid)]
        label = entity.health
        modes = {mode: run.read_past(mode, space.index, None, t) for mode in entity.modes}
        statuses = None
        if label:
            # A status is a formula of the plan: the value of its first case that holds.
            node = plan.node(expr.ref(label), space.index, 'the status of a thing')
            statuses = run.value(node, Past(run, space.index, None, t))
        texts = _texts(plan, label) if label else {}

        def one(j):
            status = 'inactive' if statuses is None else _one_of(statuses, j)
            return {
                'modes': {mode: _one_of(values, j) for mode, values in modes.items()},
                'health': status,
                'label': texts.get(status),
            }

        if space.family is None:
            entities[eid] = one(0)
            continue
        family = space.family
        for name, (other, j) in named.items():
            if other is space:
                entities[name] = {
                    'modes': {
                        name + mode[len(family.host) :]: _one_of(values, j) for mode, values in modes.items()
                    },
                    'health': one(j)['health'],
                    'label': one(j)['label'],
                }
        counted = Counter({'inactive': space.count}) if statuses is None else _counted(statuses, space.count)
        groups[family.host] = {
            'rows': space.count,
            'modes': {mode: dict(_counted(values, space.count)) for mode, values in modes.items()},
            'health': dict(counted),
            'labels': {status: texts.get(status) for status in counted},
        }
    return {'entities': entities, 'groups': groups}


def _space_of_entity(plan, eid):
    """The index of the space of a thing of the model of the representatives."""
    for space in plan.spaces:
        if space.family is not None and space.family.host == eid:
            return space.index
    return SCALARS


def _one_of(values, j):
    """The value at place j of the values of the instances of a space (one value for all, or one each)."""
    if hasattr(values, 'shape') and values.shape:
        found = values[j] if values.shape[0] > 1 else values[0]
    else:
        found = values
    return found.item() if hasattr(found, 'item') else found


def _counted(values, count):
    """{value: how many of the `count` instances have it}."""
    if hasattr(values, 'shape') and values.shape and values.shape[0] > 1:
        return Counter(values.tolist())
    return Counter({_one_of(values, 0): count})


# The work of the peaks of a run: the candidate times of an output that are read, times the rows of
# the largest table (`peaks`). Below it, each candidate time is read.
PEAK_WORK = 1_000_000
# The fewest candidate times that are read, however many rows a table has.
FEWEST_CANDIDATES = 200


def candidate_times(result):
    """The candidate times of a peak (`report.peak_candidates`): the start, the horizon, each moment
    of the run, the time just before it, and the middle between two moments, in order."""
    moments = sorted({0.0, float(result.horizon), *(float(entry[0]) for entry in result.run.trace)})
    times = set(moments)
    for start, end in itertools.pairwise(moments):
        times.update([(start + end) / 2, math.nextafter(end, start)])
    return sorted(times)


def thinned(times, most):
    """At most `most` of the sorted `times`, evenly spread over their order: the first and the last
    are always there."""
    if len(times) <= most:
        return list(times)
    picks = {round(k * (len(times) - 1) / (most - 1)) for k in range(most)}
    return [times[k] for k in sorted(picks)]


def peaks(result):
    """The peak of each output (`report.peaks_of`), as the report of a run of a flat structure finds
    it (`report.peak_candidates`).

    An output that the compiler proved never to fall, and that is estimated, peaks at the horizon,
    certified: it is read there only, as the other candidates cannot change its peak (its status
    does not change with the time: an output has no value only where it reads one that the model
    does not estimate). Each other output is read at the candidate times. A candidate time costs a
    reading of every row of a table, and a run of a large table has a moment for each event of each
    row: so when the candidates times the rows of the largest table are more than `PEAK_WORK`, an
    output is read at that many of them over the rows (at least `FEWEST_CANDIDATES`), evenly spread
    over their order, and its peak says so (`candidates`: how many times were read, of how many).
    Such a peak, as every peak that is not certified, is the largest of the values that were read."""
    plan = result.run.plan
    outcomes, horizon = plan.resolved.outcomes, float(result.horizon)
    cumulative = plan.resolved.proven_cumulative_outcomes
    found = {}
    rising = [name for name in outcomes if name in cumulative]
    if rising:
        at_end = report.peaks_of(
            outputs(result, [horizon], rising), {n: outcomes[n] for n in rising}, cumulative, horizon
        )
        found.update({name: peak for name, peak in at_end.items() if peak['certified']})
    others = [name for name in outcomes if name not in found]
    if others:
        times = candidate_times(result)
        rows = max((space.count for space in plan.spaces), default=1)
        read = thinned(times, max(FEWEST_CANDIDATES, PEAK_WORK // max(rows, 1)))
        tops = report.peaks_of(
            outputs(result, read, others), {n: outcomes[n] for n in others}, cumulative, horizon
        )
        for name, peak in tops.items():
            found[name] = (
                {**peak, 'candidates': {'read': len(read), 'of': len(times)}}
                if len(read) < len(times)
                else peak
            )
    return {name: found[name] for name in outcomes}


def report_of(result, times=None, rows=()):
    """The report of one run of a plan (the module's text says what it gives of the things of a
    table). `times`: the times that the report asks for, beside the end of the run; `rows`: the
    names of rows of tables whose own health and steps the report gives."""
    if result.paused:
        raise report.ReportingError('A paused run cannot be reported as a completed run')
    run = result.run
    plan = run.plan
    named = _named_rows(plan, rows)
    points = report.reporting_points(times, result.horizon)
    at = sorted(set(points.values()))
    samples = outputs(result, at)
    by_time = {row['t']: row for row in samples}
    shown = {(space.index, j) for space, j in named.values()}
    trace = [
        run.entry_at(k)
        for k, entry in enumerate(run.log)
        if plan.rules[entry[2]].space == SCALARS or (plan.rules[entry[2]].space, entry[3]) in shown
    ]
    inputs, ranges = {}, {}
    for name, scale in plan.parameter_scale.items():
        space = plan.spaces[plan.space_of(name)]
        values = run.v[name] / scale
        if space.family is None:
            inputs[name] = values.item(0)
        else:
            ranges.setdefault(space.family.host, {})[name] = {
                'least': float(values.min()),
                'greatest': float(values.max()),
            }
    return {
        'horizon': float(result.horizon),
        # Each output as the plan reads it: a list has one member for each group.
        'outcomes': thawed(plan.s.outcomes),
        'effective_inputs': inputs,
        'numerical_settings': {**asdict(run.cfg), 'resolution_step_h': run.max_step},
        'samples': samples,
        'reporting_points': {point: by_time[t] for point, t in points.items()},
        'groups': [
            {
                'group': family.host,
                'set': family.of.set,
                'rows': space.count,
                'inputs': ranges.get(family.host, {}),
            }
            for space, family in _families(plan)
        ],
        'trace': trace,
        'events': events(result),
        'health': [{'t': t, **health(result, t, rows)} for t in at],
        'evidence': evidence(result),
        'peaks': peaks(result),
    }


def study_of(core, runs=None, times=None, rows=(), settings=None):
    """The report of the runs of a model with a table, from its hybrid core (`model/hybrid.py`): the
    envelope of the report of a study (`report.sample_result`), and for each run its label, its
    options and `report_of` of its run. `runs` names the runs (default: every run of the model), in
    order; `settings` is the numerical settings of each run. A run that the engine stops, or a part
    that it names as outside, rejects the report, as a study is rejected: the report then has the
    diagnostics and no run (`napkin/schema/report.schema.json`, `table_run`)."""
    from ...model import ModelError
    from ..errors import SimulationError
    from ..study import StudyResult
    from . import Plan, run

    model = core.model
    study = StudyResult(model.model_hash, True, [], {}, model=model)
    found = {}
    for name in runs or list(model.runs):
        info = model.runs[name]
        try:
            result = run(Plan.of(core, name), record=True, settings=settings)
            made = report_of(result, times, rows)
        except ModelError as exc:
            study.diagnostics.extend({**item, 'run': item.get('run') or name} for item in exc.diagnostics)
            break
        except (SimulationError, Outside, report.ReportingError) as exc:
            code = 'outside' if isinstance(exc, Outside) else 'simulation'
            study.diagnostics.append({'code': code, 'severity': 'error', 'message': str(exc), 'run': name})
            study.diagnostics.extend({**item, 'run': name} for item in getattr(exc, 'diagnostics', ()) or ())
            break
        found[name] = {
            'label': info['name'],
            'options': list(info['options']),
            'starts': list(info['starts']),
            **made,
        }
    admitted = not any(item.get('severity', 'error') == 'error' for item in study.diagnostics)
    out = report.report_envelope(study, admitted)
    out['runs'] = found if admitted else {}
    return out
