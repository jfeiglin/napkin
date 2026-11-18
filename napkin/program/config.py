"""The run configuration: everything that one run of a program needs besides the program itself.

One engine invocation runs one program under one configuration and gives one record (D9). The
configuration holds the values of the inputs, the mode and the seed, the controller of each actor
and its picks, the limits of a runaway run (D6), the solver budgets (D0), the numerical settings,
and the request of what to record.

- **An input value** follows the declared type (D2): a number with a unit of its dimension, a
  yes/no, an enum member, a text, or a distribution for a distribution-valued input. A number
  overrides a default draw: the draw is skipped.
- **The mode** is `sampled` (each executed draw samples, under the seed) or `median` (a numeric
  draw is its distribution's median, a categorical one the most likely eligible outcome, the first
  declared of them on a tie). A median run has no seed.
- **A controller** decides an actor's choices: `forecast` (none: the choice is a draw of its
  forecast under the mode) or `player`, whose answers are the `picks`, each keyed by the choice's
  site and the occurrence that makes it.
- **Budgets** count work, never seconds, so a run that succeeds on one machine succeeds on another:
  the linear programs of one fair-sharing step and the iterations of one final distance step. A
  step that cannot finish within its budget stops the run with a diagnostic that names it.
- **The request** says until when and what to record. It is not part of what a run computes, so the
  key of a stored run leaves it out (`canonical.configuration_bytes`, R-A4a-08).
"""

from __future__ import annotations

from dataclasses import dataclass, fields

from .record import Key
from .refs import Distribution, EnumValue, Number

SAMPLED, MEDIAN = 'sampled', 'median'
FORECAST, PLAYER = 'forecast', 'player'


class ConfigurationError(ValueError):
    """A configuration that no run can take."""


@dataclass(frozen=True)
class Quantity:
    """A number in a unit of the program's table (`''` for a plain number)."""

    number: Number
    unit: str = ''


@dataclass(frozen=True)
class InputValue:
    """The value of one input of one member (`''` names the root)."""

    member: str
    name: str
    value: Quantity | bool | EnumValue | str | Distribution


@dataclass(frozen=True)
class Controller:
    """Who decides the choices of an actor, a member: `forecast` or `player`."""

    actor: str
    by: str = FORECAST


@dataclass(frozen=True)
class Pick:
    """A player's answer: the member of the enum chosen at a choice's site by one occurrence."""

    site: str
    occurrence: str
    value: str


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
    """The work that one solve may spend on its two costly steps (D0): linear programs of the
    fair-sharing step, and iterations of the final distance step."""

    fair_sharing: int = 10_000
    distance: int = 100_000

    def __post_init__(self):
        _positive(self)


@dataclass(frozen=True)
class Numerics:
    """The numerical settings: the relative tolerance of integration, the absolute tolerance of a
    store as a factor of its scale, the longest step (h), the most evaluations of one run, and the
    tolerance in time of a crossing (h)."""

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
    budget of pieces (R-A4a-07)."""

    horizon: Number
    everything: bool = True
    keys: tuple[Key, ...] = ()
    pieces: int = 10_000_000

    def __post_init__(self):
        if isinstance(self.horizon, bool) or not isinstance(self.horizon, Number) or self.horizon < 0:
            raise ConfigurationError(f'the horizon must be a number of hours, not {self.horizon!r}')


@dataclass(frozen=True)
class Configuration:
    """One run's inputs, mode, seed, controllers, picks, limits, budgets, numerics and request."""

    request: Request
    inputs: tuple[InputValue, ...] = ()
    mode: str = MEDIAN
    seed: int | None = None
    controllers: tuple[Controller, ...] = ()
    picks: tuple[Pick, ...] = ()
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
        for controller in self.controllers:
            if controller.by not in (FORECAST, PLAYER):
                raise ConfigurationError(f'{controller.actor}: a controller is forecast or player')
        for what, keys in (
            ('input', [(item.member, item.name) for item in self.inputs]),
            ('controller', [item.actor for item in self.controllers]),
            ('pick', [(item.site, item.occurrence) for item in self.picks]),
        ):
            twice = sorted({str(key) for key in keys if keys.count(key) > 1})
            if twice:
                raise ConfigurationError(f'a {what} is given twice: {", ".join(twice)}')
