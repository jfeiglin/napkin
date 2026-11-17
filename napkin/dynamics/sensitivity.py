"""Global sensitivity of one result to the inputs (docs/python-api.md, "Dynamics").

Two methods, for any function `f` that takes {input: value} and gives a number:

- **Morris screening** moves one input at a time along random paths through a grid of the inputs'
  ranges. The mean of the absolute elementary effects (mu*) ranks the inputs by their influence, and
  their spread (sigma) shows effects that change along the ranges: curvature or interactions.
- **Sobol indices** split the variance of the result over the inputs' ranges. The first-order index of
  an input is the share of the variance that it causes alone; its total index adds every interaction
  that it takes part in. The estimators are those of Saltelli et al. (2010) for the first order and of
  Jansen (1999) for the total, on two independent samples A and B and the samples A_B^i, which take
  input i from B. Percentile intervals come from a bootstrap over the rows.

Each input draws its numbers from a stream of its own, named by the input and seeded by the seed
(`engine.sampling.stream`), so adding an input never changes the draws of the others. The ranges are
uniform: a range that a reader can explore is not a measured interval, and the indices say how the
result depends on the assumed ranges, not how likely each result is.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from ..engine.report import evaluate_outputs
from ..engine.sampling import stream
from ..engine.study import edits_for, evaluate_study
from ..model.ir import thaw


@dataclass(frozen=True)
class Factor:
    """An input and the range that the analysis gives it, in the input's own unit."""

    name: str
    low: float
    high: float

    def __post_init__(self):
        if not self.high > self.low:
            raise ValueError(f'The range of {self.name} needs a high end above its low end')

    def at(self, u):
        return self.low + (self.high - self.low) * u


def factors_from_model(model, names):
    """The factors of the named inputs, each over the range that the model gives it."""
    out = []
    for name in names:
        found = model.inputs.get(name)
        if found is None or found.get('range') is None:
            raise ValueError(f'{name} is not a number input with a range')
        low, high = found['range']
        out.append(Factor(name, float(low), float(high)))
    return out


def _uniform(seed, name, n):
    """n numbers of the open interval (0, 1) from the stream `name`."""
    generator = stream(seed, name)
    return (generator.integers(0, 2**53, size=n).astype(float) + 0.5) / 2.0**53


def _evaluate(f, factors, units):
    """f at each row of `units` (rows of numbers in (0, 1), one column for each factor)."""
    return np.array(
        [float(f({factor.name: factor.at(u) for factor, u in zip(factors, row)})) for row in units],
        dtype=float,
    )


@dataclass(frozen=True)
class MorrisResult:
    names: tuple
    mu: np.ndarray
    mu_star: np.ndarray
    sigma: np.ndarray
    effects: dict  # {name: the elementary effects}
    evaluations: int

    def ranking(self):
        """The inputs from the largest mu* to the smallest."""
        return [self.names[i] for i in np.argsort(-self.mu_star, kind='stable')]


def morris(f, factors, *, trajectories=20, levels=4, seed=0):
    """Morris elementary effects on a grid of `levels` points of each range. An elementary effect is
    the change of f for one step of the grid, over the step as a share of the range."""
    if levels < 2 or levels % 2:
        raise ValueError('Morris screening needs an even number of levels, at least 2')
    k = len(factors)
    delta = levels / (2 * (levels - 1))
    starts = np.floor(_uniform(seed, 'morris/start', trajectories * k) * (levels / 2)).reshape(
        trajectories, k
    )
    orders = _uniform(seed, 'morris/order', trajectories * k).reshape(trajectories, k)
    effects = {factor.name: [] for factor in factors}
    evaluations = 0
    for r in range(trajectories):
        x = starts[r] / (levels - 1)
        value = float(f({factor.name: factor.at(u) for factor, u in zip(factors, x)}))
        evaluations += 1
        for i in np.argsort(orders[r], kind='stable'):
            moved = x.copy()
            moved[i] += delta
            changed = float(f({factor.name: factor.at(u) for factor, u in zip(factors, moved)}))
            evaluations += 1
            effects[factors[i].name].append((changed - value) / delta)
            x, value = moved, changed
    names = tuple(factor.name for factor in factors)
    table = [np.array(effects[name]) for name in names]
    return MorrisResult(
        names=names,
        mu=np.array([e.mean() for e in table]),
        mu_star=np.array([np.abs(e).mean() for e in table]),
        sigma=np.array([e.std(ddof=1) if len(e) > 1 else 0.0 for e in table]),
        effects={name: e for name, e in zip(names, table)},
        evaluations=evaluations,
    )


@dataclass(frozen=True)
class SobolResult:
    names: tuple
    first: np.ndarray | None
    total: np.ndarray | None
    first_interval: np.ndarray | None  # (k, 2)
    total_interval: np.ndarray | None
    first_error: np.ndarray | None  # the bootstrap standard error
    total_error: np.ndarray | None
    variance: float
    evaluations: int
    status: str  # 'estimated', or 'constant' when f does not vary over the ranges


def _indices(fa, fb, fab):
    variance = np.var(np.concatenate([fa, fb]), ddof=1)
    if variance <= 0:
        return None, None, variance
    first = np.array([np.mean(fb * (column - fa)) for column in fab.T]) / variance
    total = np.array([np.mean((fa - column) ** 2) for column in fab.T]) / (2 * variance)
    return first, total, variance


def sobol(f, factors, *, samples, seed=0, bootstrap=1000, confidence=0.95):
    """First-order and total Sobol indices of f over the factors' ranges, from N = `samples` rows of
    each of A and B: N (k + 2) evaluations of f."""
    k, n = len(factors), int(samples)
    a = np.column_stack([_uniform(seed, f'sobol/A/{factor.name}', n) for factor in factors])
    b = np.column_stack([_uniform(seed, f'sobol/B/{factor.name}', n) for factor in factors])
    fa, fb = _evaluate(f, factors, a), _evaluate(f, factors, b)
    fab = np.empty((n, k))
    for i in range(k):
        mixed = a.copy()
        mixed[:, i] = b[:, i]
        fab[:, i] = _evaluate(f, factors, mixed)
    names = tuple(factor.name for factor in factors)
    first, total, variance = _indices(fa, fb, fab)
    evaluations = n * (k + 2)
    if first is None:
        return SobolResult(
            names, None, None, None, None, None, None, float(variance), evaluations, 'constant'
        )
    generator = stream(seed, 'sobol/bootstrap')
    firsts, totals = [], []
    for _ in range(bootstrap):
        rows = generator.integers(0, n, size=n)
        s1, st, _ = _indices(fa[rows], fb[rows], fab[rows])
        if s1 is not None:
            firsts.append(s1)
            totals.append(st)
    tail = (1 - confidence) / 2 * 100
    firsts, totals = np.array(firsts), np.array(totals)
    return SobolResult(
        names=names,
        first=first,
        total=total,
        first_interval=np.percentile(firsts, [tail, 100 - tail], axis=0).T,
        total_interval=np.percentile(totals, [tail, 100 - tail], axis=0).T,
        first_error=firsts.std(axis=0, ddof=1),
        total_error=totals.std(axis=0, ddof=1),
        variance=float(variance),
        evaluations=evaluations,
        status='estimated',
    )


def model_function(model, run, output, *, time=None, values=None, numerical_settings=None):
    """f({input: value}): the value of `output` of `run` at `time` (hours; the horizon by default),
    with the given input values in their own units. A study that rejects the values raises, so no
    sample is ever left out silently."""
    library = thaw(model.library)

    def f(inputs):
        edits = edits_for(model, {'runs': {run: {**dict(values or {}), **inputs}}})
        study = evaluate_study(model, edits, numerical_settings, runs=[run])
        if not study.admissible:
            raise ValueError(f'The study rejects the values {inputs}: {study.diagnostics[:1]}')
        completed = study.runs[run]
        at = completed['trajectory'].horizon if time is None else float(time)
        row = evaluate_outputs(completed, library, [at])[0]
        if row['statuses'].get(output) != 'estimated':
            raise ValueError(f'{output} is not estimated: {row["statuses"].get(output)}')
        return float(row['values'][output])

    return f
