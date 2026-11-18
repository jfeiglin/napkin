"""Other estimators of the expectation of an outcome (docs/engine.md, "Estimators").

A Monte Carlo study (`uncertainty.py`) draws every uncertain value and the outcome of every event
that goes by chance, and gives the mean of an outcome with the error of independent samples. Each
function here is another estimator of the same expectation, at the horizon of one run. A caller
asks for it by name; each says what it assumes and gives the interval that belongs to it
(`estimators.py` has the mathematics, with no model).

- `weighted`: the outcomes of the events that go by chance are not drawn. For each sample of the
  uncertain values, every path of those outcomes is run, and the paths are added with their
  weights. What is left of the error is that of the uncertain values and of the values that an
  event draws; a run with neither has no sampling error at all.
"""

from __future__ import annotations

import math

import numpy as np
from scipy import integrate

from ..distributions import FAMILIES, quantile
from . import estimators
from .sampling import SamplingSettings, uncertain
from .study import evaluate_study
from .uncertainty import drawn, run_sample

# The most paths of the outcomes of one sample (`weighted`).
PATHS = 4096


def _draws(rs):
    """Whether an event of the run draws a value when it fires."""
    return any(item.kind == 'draw' for rule in rs.rules.values() for item in rule.extras or ())


def _refused(diagnostics):
    return {'admissible': False, 'diagnostics': list(diagnostics)}


def _interval(values, settings, confidence):
    """The mean of one number for each sample, with the interval of the sampling method: that of
    the blocks for `sobol`, that of independent samples else. One sample has no interval."""
    if len(values) == 1:
        return {'mean': float(values[0]), 'se': None, 'low': None, 'high': None, 'n': 1}
    if settings.method == 'sobol':
        return estimators.replicate_interval(
            np.split(np.asarray(values, dtype=float), settings.replicates), confidence
        )
    return estimators.mean_interval(values, confidence)


def weighted(
    model,
    run,
    edits=None,
    settings=None,
    numerical_settings=None,
    *,
    limit=PATHS,
    confidence=0.95,
    check_samples=None,
):
    """The mean of each outcome of one run at its horizon, with the outcomes of the events that go
    by chance weighted and not drawn.

    The central study and the samples of the uncertain values are those of a Monte Carlo study
    with the same `settings` (`uncertainty.drawn`); the values that an event draws when it fires
    come from the streams of the sample, as there. For each sample, every path of the outcomes is
    run (`estimators.every_path`, at most `limit` paths), and the mean of an outcome in that sample
    is the sum over its paths, each with its weight: the expectation over the outcomes, given the
    values of the sample. The estimate is the mean of those sums over the samples, with the
    interval of the sampling method. A run with no uncertain value and no drawn value has one
    sample: the estimate is exact but for the numerical error of the runs (`se` is None).

    It gives {admissible, run, samples, paths, settings, confidence, outcomes, events}:
    `outcomes[name]` is {estimated, mean, se, low, high, sd, unit}, `sd` being the standard
    deviation of the outcome itself; an outcome that one path does not estimate has no value, and
    its statuses. `events[event][outcome]` is the expected number of firings with that outcome.
    A path that fails, or more paths than the limit, refuses the estimate, with the diagnostics."""
    settings = settings or SamplingSettings()
    study = evaluate_study(model, edits, numerical_settings, runs=[run])
    if not study.admissible:
        return _refused(study.diagnostics)
    values, points, errors = drawn(model, study, settings, check_samples)
    if errors:
        return _refused(errors)
    central = study.runs[run]
    rs, horizon = central['resolved'], central['trajectory'].horizon
    names = uncertain(values[run])
    sampled = bool(names) or _draws(rs)
    # With nothing drawn but the outcomes, every sample has the same paths: one is enough.
    samples = points[run] if sampled else [model.point_values(values[run])]
    means = {name: [] for name in rs.outcomes}
    squares = {name: [] for name in rs.outcomes}
    statuses = {name: set() for name in rs.outcomes}
    events, count = {}, 0
    for k, point in enumerate(samples):
        luck = {'seed': settings.seed, 'sample': k} if sampled else None
        context = {'run': run, 'sample': k, 'seed': settings.seed}
        failed = []

        def one(places, point=point, luck=luck, failed=failed):
            found = run_sample(model, run, point, numerical_settings, [horizon], luck, outcomes=places)
            if found['failures']:
                failed.extend({**item, 'outcomes': list(places)} for item in found['failures'])
                raise _Failed
            return [(chances, place) for _, chances, place in found['firings']], found

        try:
            paths = estimators.every_path(one, limit)
        except _Failed:
            return _refused({**item, **context} for item in failed)
        except estimators.TooManyPaths as problem:
            return _refused([{'code': 'paths', 'severity': 'error', 'message': str(problem), **context}])
        count += len(paths)
        rows = [(weight, found['rows'][0]) for weight, _, found in paths]
        for name in rs.outcomes:
            statuses[name] |= {row['statuses'][name] for _, row in rows}
            if statuses[name] == {'estimated'}:
                one_mean = estimators.weighted([(weight, row['values'][name]) for weight, row in rows])
                means[name].append(one_mean['mean'])
                squares[name].append(one_mean['variance'] + one_mean['mean'] ** 2)
        for weight, _, found in paths:
            for event, counts in found['events'].items():
                total = events.setdefault(event, dict.fromkeys(counts, 0.0))
                for outcome, n in counts.items():
                    total[outcome] += weight * n / len(samples)
    outcomes = {}
    for name, definition in rs.outcomes.items():
        if statuses[name] != {'estimated'}:
            outcomes[name] = {'estimated': False, 'statuses': sorted(statuses[name])}
            continue
        found = _interval(means[name], settings, confidence)
        # The variance of the outcome is the mean of its squares less the square of its mean.
        spread = math.sqrt(max(0.0, float(np.mean(squares[name])) - found['mean'] ** 2))
        outcomes[name] = {'estimated': True, **found, 'sd': spread, 'unit': definition.unit}
    return {
        'admissible': True,
        'run': run,
        'samples': len(samples),
        'paths': count,
        'settings': settings.record(),
        'confidence': confidence,
        'outcomes': outcomes,
        'events': events,
    }


class _Failed(Exception):
    """A path of a sample failed: its diagnostics are with the caller."""


def mean_of(family, args):
    """The mean of a distribution of numbers: the integral of its quantile function over (0, 1),
    by adaptive quadrature. One function serves every family."""
    if FAMILIES[family].kind != 'number':
        raise ValueError(f'a {family} gives no numbers')
    found, _ = integrate.quad(
        lambda u: float(quantile(family, args, u)), 0.0, 1.0, epsabs=0.0, epsrel=1e-11, limit=400
    )
    return float(found)
