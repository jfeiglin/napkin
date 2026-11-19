"""The timeline engine: the engine of every run (docs/engine.md).

It reads a program (`napkin/program`) under a run configuration and gives the record of the run
(`napkin/program/record.py`): the history of each value as pieces, and the trace.

- `run(program, configuration)`: one run to the horizon, as its `Record`.
- `Plan.of(program, configuration)`: what the run reads of the program (`plan.py`), and `Outside`,
  the refusal of a part that a later slice runs.
- `read(record, program, paths, times)`: the values of named paths at chosen times, each in its
  declared unit (`record.py`).

What it runs so far: inputs (set by the configuration or by their defaults, which a draw can give),
stored numbers and yes/no values with their bounds, formulas, and directed flows between stores,
from `SOURCE` or to `SINK`, each with a request and a capacity, captured once or live (S0);
templates with members written by hand and table rows, links and paths through them, collections
(`Template.instances`, literals, `where` on fixed fields, `by`), projections, the six reductions,
keyed reads `.at(x)` with their key times, assertions over inputs, and starting values in the order
of what they read across members (S1). The members of each template are rows of a pool
(`pools.py`); collections and reductions are in `collections.py`. A connected set of one flow whose
rate reads nothing that moves runs with every other such set on arrays (`family.py`); any other
connected set is one component of the continuous engine (`component.py`).
"""

from __future__ import annotations

from .plan import Outside, Plan
from .record import Reading, read
from .run import Run

__all__ = ['Outside', 'Plan', 'Reading', 'Run', 'read', 'run']


def run(program, configuration):
    """One run of a program under a configuration, to the horizon of its request: its record. A run
    that fails gives the record to the time at which it stopped, with the failure. A part that this
    engine does not run is refused (`Outside`), and so is a configuration that the program cannot
    take (`napkin.program.config.ConfigurationError`)."""
    return Run(Plan.of(program, configuration)).run()
