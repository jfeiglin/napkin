"""Monte Carlo studies: a study of the runs with their uncertain values drawn (docs/engine.md,
"Monte Carlo studies").

A Monte Carlo study is a study of the runs (`study.evaluate_study`), in which each distribution takes
its central value and each event takes its likeliest outcome, and N samples of each run that has
uncertain values or events with outcomes by chance. Each sample draws every uncertain value once,
before the run (`sampling.py`), and the outcome of each firing of such an event during the run, from
the stream of the event in that sample. Every sample resolves through `Model.resolve`, with the checks of any run, before any
sample runs: one that fails rejects the study, and so does a sample whose run fails. No sample is
left out, because leaving one out biases the results.

N admitted samples are not a proof for every draw: a value that no sample draws can still fail, as
the points that `analyze_bounds` checks are not a proof for the whole range.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

import numpy as np

from .. import store
from ..expressions import ExpressionError
from ..model.ir import ModelError, thaw
from ..model.model import input_name
from ..model.runs import Runs
from .estimators import replicate_interval
from .report import (
    ReportingError,
    _closure,
    diagnostic,
    evaluate_outputs,
    evidence_parts,
    report_envelope,
    reporting_points,
    sample_result,
)
from .runtime import simulate
from .sampling import SamplingSettings, samples, uncertain, uniforms
from .study import STUDY_FAILURES, _errors, evaluate_study, run_checks

# The percentiles of each summary (Hyndman and Fan type 7, NumPy's `linear`).
PERCENTILES = (5, 25, 50, 75, 95)


@dataclass
class UncertaintyResult:
    """The central study, the sampling settings, and the samples of each run with uncertain values or
    events by chance: `{run: {'values': [the point values of each sample], 'runs': [each completed
    sample, or None when the samples ran elsewhere], 'rows': [the outcome rows of each sample at the
    study's times, or None], 'events': [the outcome counts of each sample]}}`."""

    study: object
    settings: SamplingSettings
    admissible: bool
    diagnostics: list
    samples: dict = field(default_factory=dict)
    times: list | None = None


class StudyCancelled(Exception):
    """The caller stopped a Monte Carlo study before its samples ran."""


def written_values(model, edits, runs):
    """{run: {input: value}} of each run under the edits, with each distribution as its record."""
    table = Runs.from_table(model.run_table)
    resolved = table.resolve(edits, runs, model_hash=model.model_hash)
    return {run: {input_name(k): thaw(v) for k, v in item.values.items()} for run, item in resolved.items()}


def check_sample(model, run, point):
    """The diagnostics of one sample's resolution through `Model.resolve`, with the checks of any run:
    none for a sample that can run."""
    try:
        model.resolve(run, point)
    except ModelError as exc:
        return list(exc.diagnostics)
    return []


def drawn(model, study, settings, check_samples=None):
    """({run: its values}, {run: [the point values of each sample]}, diagnostics) of the runs of an
    admitted study: each run with uncertain values draws `settings.samples` samples, and every sample
    resolves through `Model.resolve` before any sample runs. `check_samples(tasks)` resolves the
    samples, `[(run, k, point values)]`, and gives the diagnostics of each in order (`check_sample`,
    in this process by default). A diagnostic of a sample names the run, the sample, the seed and the
    drawn values."""
    values = written_values(model, study.effective_edits, list(study.runs))
    names = list(dict.fromkeys(name for run in values for name in uncertain(values[run])))
    # With sobol sampling each input has its own dimension of the points: its place in the model.
    inputs = next(iter(model.structures.values())).parameters
    numbers = uniforms(names, settings, {name: place for place, name in enumerate(inputs)})
    points, errors = {}, []
    for run, run_values in values.items():
        own = uncertain(run_values)
        if not own:
            # A run whose events have outcomes by chance draws its samples with the central values.
            if chancy(study.runs[run]['resolved']):
                points[run] = [model.point_values(run_values)] * settings.samples
            continue
        try:
            points[run] = samples(model, run_values, {name: numbers[name] for name in own})
        except ModelError as exc:
            errors += [{**item, 'run': run, 'seed': settings.seed} for item in exc.diagnostics]
    tasks = [(run, k, point) for run, sampled in points.items() for k, point in enumerate(sampled)]
    if check_samples is None:
        found = [check_sample(model, run, point) for run, _, point in tasks]
    else:
        found = list(check_samples(tasks))
    for (run, k, point), diagnostics in zip(tasks, found):
        drawn_values = {n: point[n] for n in uncertain(values[run])}
        context = {'run': run, 'sample': k, 'seed': settings.seed, 'drawn': drawn_values}
        errors += [{**item, **context} for item in diagnostics]
    return values, points, errors


def chancy(rs):
    """Whether a run's events go by chance: one has two outcomes or more, or draws a distribution when
    it fires (`extras` of kind `draw`)."""
    return any(
        len(rule.outcomes) > 1 or any(item.kind == 'draw' for item in rule.extras or ())
        for rule in rs.rules.values()
    )


def outcome_counts(trajectory, rs):
    """{event: {outcome: the number of its firings}} of the events of a run with two outcomes or
    more."""
    rules = rs.rules
    counts = {}
    for entry in trajectory.trace:
        rule = rules.get(entry['rule'])
        if entry['outcome'] is None or rule is None or len(rule.outcomes) < 2:
            continue
        found = counts.setdefault(entry['rule'], dict.fromkeys([o.name for o in rule.outcomes], 0))
        found[entry['outcome']] += 1
    return counts


def report_points(study, run, times=None):
    """{point: time} of a run's report points: each of `times`, then `final` at its horizon
    (`report.reporting_points`)."""
    return reporting_points(times, study.runs[run]['trajectory'].horizon)


def sample_times(study, run, times):
    """The times at which each sample of a run gives its outcome rows: `times`, with the end of the
    run; None when no times are asked."""
    if times is None:
        return None
    return sorted(set(report_points(study, run, times).values()))


def run_sample(model, run, point, numerical_settings=None, times=None, luck=None, outcomes=None):
    """One sample: `{'completed', 'rows', 'failures', 'events'}`. It resolves the run with the
    sample's values, runs it with the sample's `luck` ({seed, sample}: the draws of the outcomes of
    its events), checks it as a study checks a run (`study.run_checks`: its outcomes at time zero and
    at the horizon among them), and evaluates its outcomes at `times` when they are given (`rows`).
    `events` counts the outcomes of its events that go by chance (`outcome_counts`). A run that
    fails gives its diagnostics and nothing else.

    With `outcomes` (the places of the outcomes of the first firings that go by chance) the run
    takes those outcomes and draws none (`timeline.Run`): the sample has `firings` too, the record
    of each such firing of the run. Such a run is not kept in the run store."""
    library = thaw(model.library)
    firings = None
    try:
        rs = model.resolve(run, point)
        if luck is not None:
            rs = rs.adding(luck=dict(luck))
        if outcomes is None:
            trajectory = store.simulate(simulate, rs, library, numerical_settings)
        else:
            from . import timeline

            made = timeline.result(rs, library, numerical_settings, outcomes=outcomes)
            trajectory, firings = made.trajectory(), made.firings
        failures = [
            d for d in run_checks(rs, trajectory, library, run) if d.get('severity', 'error') == 'error'
        ]
        if failures:
            return {'completed': None, 'rows': None, 'failures': failures}
        completed = {'resolved': rs, 'trajectory': trajectory}
        rows = evaluate_outputs(completed, library, times) if times is not None else None
    except STUDY_FAILURES as exc:
        return {'completed': None, 'rows': None, 'failures': _errors(exc), 'events': {}}
    found = {'completed': completed, 'rows': rows, 'failures': [], 'events': outcome_counts(trajectory, rs)}
    return found if firings is None else {**found, 'firings': firings}


def evaluate_uncertainty(
    model,
    edits=None,
    settings=None,
    numerical_settings=None,
    *,
    runs=None,
    times=None,
    run_samples=None,
    check_samples=None,
):
    """A Monte Carlo study of every run, or of the named `runs`, under one edit document.

    The central study comes first, with every check of a study. Then each run with uncertain values
    draws `settings.samples` samples, and each sample resolves before any sample runs (`drawn`). A
    sample that fails, in its resolution or its run, rejects the study: its diagnostics name the run,
    the sample, the seed and the drawn values, and the result keeps no sample.

    `times` asks for each sample's outcome rows at those times (the summaries' `series`), or is a
    function that gives them from the admitted central study. `check_samples(tasks)` resolves the
    samples, `[(run, k, point values)]`, and gives the diagnostics of each in order (`check_sample`);
    then, when none fails, `run_samples(tasks)` runs them, `[(run, k, point values, times of the
    sample's rows, the sample's luck)]`, and gives the result of each in order (`run_sample`). Both work one sample after
    another in this process by default; a caller can do the work in other processes, and stop the
    study by raising `StudyCancelled`."""
    settings = settings or SamplingSettings()
    study = evaluate_study(model, edits, numerical_settings, runs=runs)
    result = UncertaintyResult(study, settings, study.admissible, list(study.diagnostics))
    if not study.admissible:
        return result
    if callable(times):
        times = times(study)
    times = None if times is None else sorted({float(t) for t in times})
    result.times = times
    values, points, errors = drawn(model, study, settings, check_samples)
    if errors:
        result.diagnostics += errors
        result.admissible = False
        return result
    tasks = [
        (run, k, point, sample_times(study, run, times), {'seed': settings.seed, 'sample': k})
        for run, run_points in points.items()
        for k, point in enumerate(run_points)
    ]
    if run_samples is None:
        outcomes = [
            run_sample(model, run, point, numerical_settings, at, luck) for run, _, point, at, luck in tasks
        ]
    else:
        outcomes = list(run_samples(tasks))
    for (run, k, point, _, _), outcome in zip(tasks, outcomes):
        drawn_values = {n: point[n] for n in uncertain(values[run])}
        context = {'run': run, 'sample': k, 'seed': settings.seed, 'drawn': drawn_values}
        errors += [{**item, **context} for item in outcome['failures']]
        sampled = result.samples.setdefault(run, {'values': [], 'runs': [], 'rows': [], 'events': []})
        sampled['values'].append(point)
        sampled['runs'].append(outcome.get('completed'))
        sampled['rows'].append(outcome.get('rows'))
        sampled['events'].append(outcome.get('events') or {})
    if errors:
        result.diagnostics += errors
        result.admissible = False
        result.samples = {}  # never expose part of a rejected study
    return result


# ---- summaries --------------------------------------------------------------------------------------


def _number(value, parameter):
    """A drawn value as a number for a rank correlation: a bool is 1 or 0, a named value its code."""
    if isinstance(value, bool):
        return 1.0 if value else 0.0
    if isinstance(value, str):
        return float(list(parameter.metadata['values']).index(value))
    return float(value)


def spearman(x, y):
    """The Spearman rank correlation of two samples, with tied values at their mean rank; None when
    either sample has one value only."""
    # scipy.stats takes a third of a second to import, and only Monte Carlo studies need it.
    from scipy.stats import rankdata

    x, y = rankdata(x), rankdata(y)
    if np.ptp(x) == 0 or np.ptp(y) == 0:
        return None
    return float(np.corrcoef(x, y)[0, 1])


def summary(central, values, replicates=None):
    """The summary of one outcome over the samples: the central run's value, the mean, the standard
    deviation, the standard error of the mean, the extremes and the percentiles (type 7). The
    standard error is that of independent samples, `sd / sqrt(n)`. With `replicates` (the blocks
    of `sobol` sampling, one after another in the samples) the samples of one block are not
    independent, and the standard error is that of the means of the blocks
    (`estimators.replicate_interval`)."""
    x = np.asarray(values, dtype=float)
    sd = float(x.std(ddof=1)) if len(x) > 1 else None
    sem = None if sd is None else sd / math.sqrt(len(x))
    if replicates is not None:
        sem = replicate_interval(np.split(x, replicates))['se']
    out = {
        'estimated': True,
        'central': central,
        'mean': float(x.mean()),
        'sd': sd,
        'sem': sem,
        'min': float(x.min()),
        'max': float(x.max()),
    }
    for p, value in zip(PERCENTILES, np.percentile(x, PERCENTILES, method='linear')):
        out[f'p{p}'] = float(value)
    return out


def depends_on(rs, uncertain_names):
    """{outcome: the uncertain inputs that it can depend on} of one run's structure."""
    parts, depends, starts = evidence_parts(rs)
    return {
        outcome: sorted(_closure(start, parts, depends) & set(uncertain_names))
        for outcome, start in starts.items()
    }


def rows_of(result, run, times, library):
    """[{t: row}] of each sample of a run at `times`: the rows that the sample gave when it ran, or the
    rows of its completed run."""
    out = []
    for completed, rows in zip(result.samples[run]['runs'], result.samples[run]['rows']):
        if rows is not None and set(times) <= {row['t'] for row in rows}:
            out.append({row['t']: row for row in rows})
        elif completed is not None:
            out.append({row['t']: row for row in evaluate_outputs(completed, library, times)})
        else:
            raise ValueError(f'A sample of {run} ran without its outcomes at these times')
    return out


def band(values):
    """The percentiles of the samples at one time, for a band."""
    return {
        f'p{p}': float(v) for p, v in zip(PERCENTILES, np.percentile(values, PERCENTILES, method='linear'))
    }


def summarize(result, reporting_times=None):
    """{run: its samples, the draws of each uncertain input, and each outcome at each report point}.

    An outcome's summary is estimated only when the outcome is estimated in the central run and in
    every sample; otherwise it has no value, never zero, and gives the statuses that it met. Each
    estimated summary gives each uncertain input's rank correlation with the outcome (the drivers),
    and each outcome names the uncertain inputs that it can depend on: one that depends on none takes
    the central value in every sample. With `reporting_times`, each outcome also has its `series`:
    the percentiles at each of those times, for the bands of a chart."""
    if not result.admissible:
        return {}
    model = result.study.model
    library = thaw(model.library)
    definitions = next(iter(model.structures.values())).parameters
    asked = sorted({float(t) for t in reporting_times or ()})
    out = {}
    # The blocks of a study with sobol sampling: the error of a mean comes from their means.
    blocks = result.settings.replicates if result.settings.method == 'sobol' else None
    for run, sampled in result.samples.items():
        central = result.study.runs[run]
        rs = central['resolved']
        named = report_points(result.study, run, asked)
        times = sorted(set(named.values()))
        central_rows = {row['t']: row for row in evaluate_outputs(central, library, times)}
        sample_rows = rows_of(result, run, times, library)
        written = written_values(model, result.study.effective_edits, [run])[run]
        names = uncertain(written)
        draws = {
            name: [_number(point[name], definitions[name]) for point in sampled['values']] for name in names
        }
        reach = depends_on(rs, names)

        def statuses(outcome, t):
            return {central_rows[t]['statuses'][outcome]} | {
                rows[t]['statuses'][outcome] for rows in sample_rows
            }

        outcomes = {}
        for outcome in rs.outcomes:
            points = {}
            for point, t in sorted(named.items(), key=lambda item: item[1]):
                if statuses(outcome, t) != {'estimated'}:
                    points[point] = {'estimated': False, 'statuses': sorted(statuses(outcome, t))}
                    continue
                values = [rows[t]['values'][outcome] for rows in sample_rows]
                points[point] = summary(central_rows[t]['values'][outcome], values, blocks)
                points[point]['drivers'] = {name: spearman(draws[name], values) for name in reach[outcome]}
            outcomes[outcome] = {'uncertain_inputs': reach[outcome], 'points': points}
            if asked:
                outcomes[outcome]['series'] = [
                    {'t': t, **band([rows[t]['values'][outcome] for rows in sample_rows])}
                    if statuses(outcome, t) == {'estimated'}
                    else {'t': t, **dict.fromkeys(f'p{p}' for p in PERCENTILES)}
                    for t in asked
                ]
        events = {}
        for counts in sampled.get('events') or ():
            for event, found in counts.items():
                total = events.setdefault(event, dict.fromkeys(found, 0))
                for name, n in found.items():
                    total[name] = total.get(name, 0) + n
        out[run] = {
            'samples': len(sampled['values']),
            # How many times each outcome of an event that goes by chance happened in the samples.
            'events': events,
            'inputs': {
                name: {'distribution': written[name], 'draws': [point[name] for point in sampled['values']]}
                for name in names
            },
            'outcomes': outcomes,
        }
    return out


def uncertainty_report(result, reporting_times=None):
    """A JSON-ready report of a Monte Carlo study: the report of its central study
    (`report.sample_result`) with an `uncertainty` section, the settings and the summaries of each
    run. A rejected study reports its diagnostics and no run."""
    if not result.admissible:
        report = report_envelope(result.study, False)
        report['diagnostics'] = thaw(result.diagnostics)
        report['uncertainty'] = {'settings': result.settings.record(), 'runs': {}}
        return report
    report = sample_result(result.study, reporting_times)
    if not report['admissible']:
        return report  # a reporting failure of the central study
    try:
        runs = summarize(result, reporting_times)
    except (ReportingError, ExpressionError, ArithmeticError) as exc:
        # A numerical failure in reporting a sample is never an unknown outcome, and no part of the
        # study is exposed.
        report = report_envelope(result.study, False)
        report['status'] = 'reporting_failure'
        report['diagnostics'].append(diagnostic('reporting_failure', str(exc)))
        runs = {}
    report['uncertainty'] = {'settings': result.settings.record(), 'runs': runs}
    return report
