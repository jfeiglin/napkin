"""The samples of a Monte Carlo study: how many, and the seed of each (docs/engine/README.md,
"Studies").

A sample is one run of the study's program in `sampled` mode under a seed of its own. The engine keys
each executed draw by the seed, the draw's site and the member, occurrence or firing that executes it
(`timeline/chance.py`), so the seed of a sample decides every draw of its run and nothing else does: an
unexecuted branch, an extra read or the step size of the integrator moves no draw.

- `SamplingSettings(samples, seed)`: the number of samples and the seed of the study.
- `sample_seed(seed, k)`: the seed of sample k, the first 63 bits of the SHA-256 of `seed|k`. Sample k
  does not depend on the number of samples, and two studies with other seeds share no sample's seed
  but by chance (one in 2^63 for each pair of samples), where `seed + k` would share all but one.
- `sampled(configuration, settings)`: the configuration of each sample: the study's configuration in
  `sampled` mode, with the sample's seed.

Two configurations of one program sampled with one study seed take the same seed in sample k, so a
draw that both make at one site, by one owner, has one value in both: two runs of a study compare
sample by sample as far as their draws coincide. Once they take other branches, their later draws need
not coincide (D9).

`stream(seed, name)` is a generator of numbers named by a text, for an analysis that draws its own
numbers rather than running samples (`napkin.dynamics.sensitivity`).
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, replace

import numpy as np

from ..program.config import SAMPLED

# The most samples of one study.
LIMIT = 100_000


@dataclass(frozen=True)
class SamplingSettings:
    """The samples of a Monte Carlo study: how many (1 to `LIMIT`), and the seed of the study (a whole
    number from 0 to 2^63 - 1)."""

    samples: int = 200
    seed: int = 0

    def __post_init__(self):
        if (
            isinstance(self.samples, bool)
            or not isinstance(self.samples, int)
            or not 1 <= self.samples <= LIMIT
        ):
            raise ValueError(f'samples is a whole number from 1 to {LIMIT}, not {self.samples!r}')
        if isinstance(self.seed, bool) or not isinstance(self.seed, int) or not 0 <= self.seed < 2**63:
            raise ValueError(f'seed is a whole number from 0 to 2^63 - 1, not {self.seed!r}')

    def record(self):
        """The settings as plain data, for a report."""
        return {'samples': self.samples, 'seed': self.seed}


def sample_seed(seed, k):
    """The seed of sample k of a study with this seed (see the module)."""
    digest = hashlib.sha256(f'{seed}|{k}'.encode()).digest()
    return int.from_bytes(digest[:8], 'big') >> 1


def sampled(configuration, settings):
    """The configuration of each sample of a study (see the module), in the order of the samples."""
    return tuple(
        replace(configuration, mode=SAMPLED, seed=sample_seed(settings.seed, k))
        for k in range(settings.samples)
    )


def stream(seed, name):
    """The generator of the numbers of one named stream: a child of the seed whose key is the SHA-256
    of the name, so that the numbers of a stream never depend on the other streams."""
    digest = hashlib.sha256(name.encode('utf-8')).digest()
    key = tuple(int.from_bytes(digest[i : i + 4], 'little') for i in range(0, len(digest), 4))
    return np.random.Generator(np.random.PCG64(np.random.SeedSequence(seed, spawn_key=key)))
