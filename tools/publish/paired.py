"""Pair empirical outcome differences by sample seed before computing their percentiles."""

import math
import sys
from numbers import Real

import numpy as np

from napkin.engine.sampling import sample_seed

from .readings import display, visible_value

FILENAME = 'paired-spreads.json'


def numeric(value):
    return isinstance(value, Real) and not isinstance(value, bool) and math.isfinite(value)


def percent_change(difference, against, unit):
    """A relative change needs a positive denominator on a ratio scale."""
    if against <= 0 or unit in {'degC', 'degF', '°C', '°F'}:
        return None
    value = 100 * (difference / against)
    return value if math.isfinite(value) else None


def contrast(baseline, alternative, base_scale, run_scale, unit):
    delta = visible_value(alternative - baseline, max(base_scale or 0, run_scale or 0))
    if not math.isfinite(delta):
        raise ValueError('The difference exceeds the finite range of the reading unit')
    return delta, percent_change(delta, visible_value(baseline, base_scale), unit)


def keyed_samples(result, spec, name, *, with_scales=False):
    """Require every authored sample exactly once and preserve the seed rather than array position."""
    if result.refused:
        raise ValueError(f'{name}: {result.refused}')
    expected = {sample_seed(spec.seed, k) for k in range(spec.samples)}
    found = {}
    for sample in result.samples:
        if sample.stopped is not None:
            raise ValueError(f'{name}: seed {sample.seed} stopped: {sample.stopped}')
        if sample.seed in found:
            raise ValueError(f'{name}: duplicate sample seed {sample.seed}')
        found[sample.seed] = (sample.values, sample.scales)
    if found.keys() != expected:
        raise ValueError(f'{name}: incomplete or unexpected sample seeds for {spec.samples} requested draws')
    for seed, (values, scales) in found.items():
        if len(values) != len(result.paths) or any(len(readings) != len(result.times) for readings in values):
            raise ValueError(f'{name}: incomplete outcome readings for seed {seed}')
        if with_scales and (
            len(scales) != len(values) or any(len(line) != len(result.times) for line in scales)
        ):
            raise ValueError(f'{name}: incomplete comparison scales for seed {seed}')
    return found


def distribution(values):
    magnitude = max(abs(x) for x in values)
    # Keep a finite sum and percentile interpolation even near the float range limits.
    scale = magnitude if magnitude > sys.float_info.max / max(2, len(values)) else 1
    series = [v / scale for v in values] if scale != 1 else values
    low, high = np.percentile(series, (5, 95), method='linear')
    mean = math.fsum(series) / len(series)
    return {
        key: float(display(value * scale)) for key, value in (('mean', mean), ('p05', low), ('p95', high))
    }


def comparison(pair, studies):
    base_result, base = studies[pair.against]
    run_result, run = studies[pair.run]
    if (
        base.keys() != run.keys()
        or base_result.paths != run_result.paths
        or base_result.times != run_result.times
    ):
        raise ValueError(
            f'{pair.run} against {pair.against}: samples must share seeds, paths and reading times'
        )
    metrics = []
    for index, path in enumerate(base_result.paths):
        for j, time in enumerate(base_result.times):
            unit = base_result.spread(path, time).unit
            if unit != run_result.spread(path, time).unit:
                raise ValueError(f'{pair.run} against {pair.against}: {path} units differ')
            item = {'path': path, 'time_hours': time, 'unit': unit or '1'}
            metrics.append(item)
            left = [values[index][j] for values, _ in base.values()]
            right = [run[seed][0][index][j] for seed in base]
            if not all(numeric(value) for series in (left, right) for value in series):
                item['unavailable'] = 'One or more readings are unavailable or nonnumeric.'
                continue
            changes, percentages = [], []
            for k, seed in enumerate(base):
                base_scale = base[seed][1][index][j]
                run_scale = run[seed][1][index][j]
                delta, percent = contrast(left[k], right[k], base_scale, run_scale, unit)
                changes.append(delta)
                percentages.append(percent)
                left[k] = visible_value(left[k], base_scale)
                right[k] = visible_value(right[k], run_scale)
            item.update(against=distribution(left), run=distribution(right), difference=distribution(changes))
            if None in percentages:
                item['percent_change'] = None
                item['percent_unavailable'] = (
                    'A positive, ratio-scale baseline is required for every paired draw.'
                )
            else:
                item['percent_change'] = distribution(percentages)
    return {'run': pair.run, 'against': pair.against, 'paired_draws': len(base), 'readings': metrics}
