"""The run configuration: everything that one run of a program needs besides the program itself.

One engine invocation runs one program under one configuration and gives one record (D9). The
configuration holds the values of the inputs, the mode and the seed, the limits of a runaway run
(D6), the solver budgets (D0), the numerical settings, and the request of what to record. It has no
player and no pick (docs/design/decisions.md, change 15): a caller who wants another value stops
the run at a breakpoint and edits it (`checkpoint.py`).

- **An input value** follows the declared type (D2): a number with a unit of its dimension, a
  yes/no, an enum member, a text, or a distribution for a distribution-valued input. A number
  overrides a default draw: the draw is skipped. Its unit is a spelling of the program's table, or a
  unit of the library that the program does not spell, given whole with its dimension and scale
  (`parts.Unit`), so a caller can write a repair time in days for a model that spells only hours.
- **The mode** is `sampled` (each executed draw samples, under the seed) or `median` (a numeric
  draw is its distribution's median, a categorical one the most likely eligible outcome, the first
  declared of them on a tie). A median run has no seed.
- **Budgets** count work, never seconds, so a run that succeeds on one machine succeeds on another:
  the linear programs of one fair-sharing step, the Newton steps of each distance stage, and the
  iterations of its exact fallback. A step that cannot finish within its budget stops the run with
  a diagnostic that names it.
- **The request** says until when and what to record, within a budget of pieces (R-A4a-07): the
  values that the record holds have at most that many pieces, and a record that would hold more ends
  at the last time at which they fit, with a failure that names the budget (`record.Record.within`).
  The store keys the requested record by its horizon, selection and budget together with the
  rest of the configuration (`store.key`).
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, fields

from .parts import Unit
from .record import Key
from .refs import Distribution, EnumValue, Number

SAMPLED, MEDIAN = 'sampled', 'median'


class ConfigurationError(ValueError):
    """A configuration that no run can take."""


@dataclass(frozen=True)
class Quantity:
    """A number in a unit: a spelling of the program's table (`''` for a plain number), or a unit of
    the library with its dimension and scale, `Unit('day', (('time', 1),), Fraction(24))`."""

    number: Number
    unit: str | Unit = ''


@dataclass(frozen=True)
class InputValue:
    """The value of one input of one member (`''` names the root)."""

    member: str
    name: str
    value: Quantity | bool | EnumValue | str | Distribution


def _positive(record):
    for item in fields(record):
        value = getattr(record, item.name)
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not value > 0:
            raise ConfigurationError(f'{item.name} must be a positive number, not {value!r}')


@dataclass(frozen=True)
class Limits:
    """The limits of a runaway run (D6): starts of one event over the run, occurrences of one event
    alive at once, and rounds at one time."""

    max_occurrences: int = 1_000_000
    max_active: int = 100_000
    max_rounds: int = 1_000

    def __post_init__(self):
        _positive(self)


@dataclass(frozen=True)
class Budgets:
    """The work that one solve may spend on its two costly steps (D0), in the units of the solve
    library (`napkin/engine/solve/solver.py`, `Budget`): the linear programs of the fair-sharing
    step over all its tiers, the Newton steps of each distance stage, and the iterations of the QP
    that is the exact fallback of a distance stage. The defaults are the library's."""

    fair_programs: int = 1_000
    newton_steps: int = 500
    qp_iterations: int = 100_000

    def __post_init__(self):
        _positive(self)


@dataclass(frozen=True)
class Numerics:
    """The numerical settings: the relative tolerance of integration, the absolute tolerance of a
    store as a factor of its scale, the longest step (h), the most evaluations of one run, and the
    tolerance in time of a crossing (h), which is also the time between two moments that the engine
    tells apart."""

    rtol: float = 1e-9
    atol_factor: float = 1e-10
    max_step: float = 1.0
    max_evaluations: int = 2_000_000
    crossing: float = 1e-8

    def __post_init__(self):
        _positive(self)


@dataclass(frozen=True)
class Request:
    """What to record: the horizon (h, an inclusive cutoff), and every value or only `keys`, within a
    budget of pieces (R-A4a-07): the most pieces that the values of the record may have, which the
    record enforces (see the module).

    The horizon is held as the run holds every time (`engine.timeline.moment.Clock`): its exact value,
    rounded once to a float. A model's `horizon 0.3 days` is the exact 36/5 h, and the request holds
    7.2, the very float of the run's last moment and of a caller's `7.2 h`, so a read at the horizon
    however it is spelled is a read at the time that the run reached, not past it."""

    horizon: Number
    everything: bool = True
    keys: tuple[Key, ...] = ()
    pieces: int = 10_000_000

    def __post_init__(self):
        if isinstance(self.horizon, bool) or not isinstance(self.horizon, Number) or self.horizon < 0:
            raise ConfigurationError(f'the horizon must be a number of hours, not {self.horizon!r}')
        object.__setattr__(self, 'horizon', float(self.horizon))
        if isinstance(self.pieces, bool) or not isinstance(self.pieces, int) or self.pieces < 1:
            raise ConfigurationError(
                f'the budget of pieces must be a whole number from 1, not {self.pieces!r}'
            )


@dataclass(frozen=True)
class Configuration:
    """One run's inputs, mode, seed, limits, budgets, numerics and request."""

    request: Request
    inputs: tuple[InputValue, ...] = ()
    mode: str = MEDIAN
    seed: int | None = None
    limits: Limits = Limits()
    budgets: Budgets = Budgets()
    numerics: Numerics = Numerics()

    def __post_init__(self):
        if self.mode not in (SAMPLED, MEDIAN):
            raise ConfigurationError(f'the mode is sampled or median, not {self.mode!r}')
        if self.mode == SAMPLED and (isinstance(self.seed, bool) or not isinstance(self.seed, int)):
            raise ConfigurationError('a sampled run needs a whole-number seed')
        if self.mode == MEDIAN and self.seed is not None:
            raise ConfigurationError('a median run has no seed')
        counts = Counter((item.member, item.name) for item in self.inputs)
        twice = sorted(str(key) for key, count in counts.items() if count > 1)
        if twice:
            raise ConfigurationError(f'an input is given twice: {", ".join(twice)}')
