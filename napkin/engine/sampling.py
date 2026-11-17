"""The draws of the uncertain values of a run (docs/engine.md, "Monte Carlo studies").

Each stage is a pure function that a test can call alone, with its own uniform numbers:

- `uniforms(names, settings)`: one uniform number in (0, 1) for each sample of each named value;
- `samples(model, values, uniforms)`: the point values of each sample, each distribution drawn as
  the quantile of its uniform number, in the order that the distributions that read other values
  need (`Model.point_values`).

With `random` sampling each value has its own stream of numbers, named by the input: sample k does
not depend on the number of samples, and adding or removing one uncertain value never changes the
draws of the others. Each run of a study reads the same streams, so that two runs compare sample by
sample. With `latin` sampling each value has one sample in each of N equal strata, in an order that
its stream shuffles. Latin strata are for the draws at the start of a run only.

With `sobol` sampling the numbers are scrambled Sobol' points (`scipy.stats.qmc.Sobol`): a study has
`replicates` independent blocks of 2^k points each. Inside a block the points fill the space of the
inputs far more evenly than random numbers do, so the mean of a smooth result has a smaller error;
they are not independent, so the error of a mean comes from how the means of the blocks differ
(`estimators.replicate_interval`). Each input has one dimension of the points for good: its place
among the inputs of the model (`dimensions`), so making another input uncertain changes no number
of this one. Sample k does depend on the size of a block. As with `latin`, the points are for the
draws at the start of a run only: the outcomes of the events of a run keep their own streams.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass

import numpy as np
from scipy.stats import qmc

from ..distributions import quantile
from ..model.uncertain import is_distribution

METHODS = ('random', 'latin', 'sobol')
# The independent blocks of a study with `sobol` sampling, when the settings name no number.
REPLICATES = 8
# A uniform number is (k + 1/2) / 2^52 for a whole number k below 2^52: never 0 and never 1.
RESOLUTION = 2**52
LIMIT = 100_000


@dataclass(frozen=True)
class SamplingSettings:
    """The samples of a Monte Carlo study: how many, the seed of every stream, and the method.
    With the method `sobol`, `replicates` is the number of independent blocks (default 8), and the
    samples are that many blocks of a power of two each."""

    samples: int = 200
    seed: int = 0
    method: str = 'random'
    replicates: int | None = None

    def __post_init__(self):
        if (
            isinstance(self.samples, bool)
            or not isinstance(self.samples, int)
            or not 1 <= self.samples <= LIMIT
        ):
            raise ValueError(f'samples is a whole number from 1 to {LIMIT}')
        if isinstance(self.seed, bool) or not isinstance(self.seed, int) or not 0 <= self.seed < 2**63:
            raise ValueError('seed is a whole number from 0 to 2^63 - 1')
        if self.method not in METHODS:
            raise ValueError(f'method is one of {", ".join(METHODS)}')
        if self.method != 'sobol':
            if self.replicates is not None:
                raise ValueError('replicates are the blocks of sobol sampling')
            return
        if self.replicates is None:
            object.__setattr__(self, 'replicates', REPLICATES)
        blocks = self.replicates
        if isinstance(blocks, bool) or not isinstance(blocks, int) or blocks < 2:
            raise ValueError('replicates is a whole number from 2')
        size, rest = divmod(self.samples, blocks)
        if rest or size < 1 or size & (size - 1):
            raise ValueError(
                f'with sobol sampling the samples are {blocks} blocks of a power of two each '
                f'({blocks}, {2 * blocks}, {4 * blocks}, …), not {self.samples}'
            )

    def record(self):
        found = {'samples': self.samples, 'seed': self.seed, 'method': self.method}
        return {**found, 'replicates': self.replicates} if self.method == 'sobol' else found


def stream(seed, name):
    """The generator of the numbers of one named value: a child of the seed whose key is the SHA-256
    of the name, so that the numbers of a value never depend on the other values."""
    digest = hashlib.sha256(name.encode('utf-8')).digest()
    key = tuple(int.from_bytes(digest[i : i + 4], 'little') for i in range(0, len(digest), 4))
    return np.random.Generator(np.random.PCG64(np.random.SeedSequence(seed, spawn_key=key)))


def _open(generator, n):
    """n uniform numbers in the open interval (0, 1), each from one draw of the generator."""
    k = generator.integers(0, RESOLUTION, size=n, dtype=np.uint64)
    return (k.astype(float) + 0.5) / RESOLUTION


def draws(seed, name):
    """A function that gives the next uniform number of the stream `name` each time it is called:
    one for each firing of an event with outcomes (docs/engine.md, "The step")."""
    generator = stream(seed, name)
    return lambda: float(_open(generator, 1)[0])


def _sobol(names, settings, dimensions):
    """{name: the numbers of each sample} with `sobol` sampling: for each block, scrambled Sobol'
    points of as many dimensions as `dimensions` has, of which each name takes its own."""
    blocks, size = settings.replicates, settings.samples // settings.replicates
    columns = {name: [] for name in names}
    for block in range(blocks):
        # Each block has a scramble of its own, from the seed and the number of the block.
        key = np.random.SeedSequence(settings.seed, spawn_key=(0x50B01, block))
        points = qmc.Sobol(len(dimensions), scramble=True, seed=np.random.Generator(np.random.PCG64(key)))
        found = points.random(size)
        for name in names:
            columns[name].append(found[:, dimensions[name]])
    edge = 0.5 / RESOLUTION
    return {name: np.clip(np.concatenate(parts), edge, 1 - edge) for name, parts in columns.items()}


def uniforms(names, settings, dimensions=None):
    """{name: the uniform number of each sample}, for each named value. `dimensions` is for `sobol`
    sampling: {name: the place of the value among the inputs of the model}, for every input (default:
    the place of each name among `names` in their sorted order)."""
    if settings.method == 'sobol':
        if not names:
            return {}
        if dimensions is None:
            dimensions = {name: place for place, name in enumerate(sorted(names))}
        return _sobol(names, settings, dimensions)
    n, out = settings.samples, {}
    for name in names:
        generator = stream(settings.seed, name)
        if settings.method == 'random':
            out[name] = _open(generator, n)
        else:
            order = generator.permutation(n)
            u = (order + _open(generator, n)) / n
            # Rounding can carry the top of the last stratum to 1.
            out[name] = np.clip(u, 0.5 / RESOLUTION, 1 - 0.5 / RESOLUTION)
    return out


def uncertain(values):
    """The names of the values of a run that are distributions, in the order of the inputs."""
    return [name for name, value in values.items() if is_distribution(value)]


def draw(record, args, u, names=None):
    """The value of one distribution at the uniform number u: a number, a bool, or a named value."""
    value = quantile(record['family'], args, u)
    if record['family'] == 'bernoulli':
        return bool(value)
    if record['family'] == 'categorical':
        return names[int(value)]
    return float(value)


def samples(model, values, numbers):
    """[{input: point value}] of each sample of a run, `values` being its values with the
    distributions as records and `numbers` the uniform numbers of each uncertain value
    (`uniforms`). A distribution that reads other values reads their draws in the same sample."""
    definitions = next(iter(model.structures.values())).parameters
    count = len(next(iter(numbers.values()))) if numbers else 0
    out = []
    for k in range(count):

        def pick(name, record, args, k=k):
            names = (definitions[name].metadata or {}).get('values')
            return draw(record, args, numbers[name][k], names)

        out.append(model.point_values(values, pick))
    return out
