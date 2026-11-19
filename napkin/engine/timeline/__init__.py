"""The timeline engine: the engine of every run (docs/engine.md).

It reads a program (`napkin/program`) under a run configuration and gives the record of the run
(`napkin/program/record.py`): the history of each value as pieces, and the trace.

- `run(program, configuration)`: one run to the horizon, as its `Record`. A run that a player's
  choice pauses gives the record to the pause, whose entry ends its trace (`paused`); a run of the
  configuration with the pick replays it, and `Run(plan).run()` then `.resume(pick)` goes on in place.
- `Plan.of(program, configuration)`: what the run reads of the program (`plan.py`), and `Outside`,
  the refusal of a part that the engine does not run, with its reason.
- `read(record, program, paths, times)`: the values of named paths at chosen times, each in its
  declared unit (`record.py`).

What it runs: inputs (set by the configuration or by their defaults, which a draw can give), stored
numbers, yes/no values, enum members and texts with their bounds, formulas, and directed flows
between stores, from `SOURCE` or to `SINK`, each with a request and a capacity, captured once or
live; templates with members written by hand and table rows, links and paths through them,
collections (`Template.instances`, literals, `where` on fixed fields, `by`), projections, the six
reductions, keyed reads `.at(x)` with their key times or with a key or members that move, assertions
over inputs, and starting values in the order of what they read across members; endpoints with
their capacities, requests and allocations, local sharing across junctions and stores at their
bounds, and flows across members; reversible routes with one signed rate and their legs, and flows
with legs at one served fraction; events with their occurrences, stages, triggers, gates, moves and
the retirement of an occurrence's stores; draws in stages and in events under the modes `median`
and `sampled`, inputs that are distributions, actors' choices with their controllers, picks and the
pause of one stage, assertions over state, `elapsed` and `delayed` (`chance.py`); declared solvers
(`declared.py`); and the definitions that stages give formulas, requests and capacities. The
members of each template are rows of a pool (`pools.py`); collections and
reductions are in `collections.py`. The flows and the stores are one network (`network.py`), whose
local sharing at an instant is a closed form or the selection order (`selection.py`). A connected
set of one directed flow whose rate reads nothing that moves runs with every other such set on
arrays (`family.py`); any other set whose rates read nothing that moves runs on lines (`lines.py`);
a set whose rates move is a component of the continuous engine (`component.py`) when it is small and
simple, else it runs on the sparse integrator (`sparse.py`), with the sets whose rates read its
moving rates; `ways.py` holds them, and builds again the sets that a moment changes. A run
(`run.py`) goes from moment to moment: the rounds of a moment (`moment.py`), the occurrences
(`occurrences.py`), and the conditions with the times at which their answers can change
(`triggers.py`).
"""

from __future__ import annotations

from .chance import paused
from .plan import Outside, Plan
from .record import Reading, read
from .run import Run

__all__ = ['Outside', 'Plan', 'Reading', 'Run', 'paused', 'read', 'run']


def run(program, configuration):
    """One run of a program under a configuration, to the horizon of its request: its record. A run
    that fails gives the record to the time at which it stopped, with the failure. A part that this
    engine does not run is refused (`Outside`), and so is a configuration that the program cannot
    take (`napkin.program.config.ConfigurationError`)."""
    return Run(Plan.of(program, configuration)).run()
