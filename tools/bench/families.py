"""The synthetic families of the benchmark: models made as text, one for each size.

A family is a function `text(n)` that gives the main file of a model of size `n` (1 or more), in the
language of the rewrite (docs/language.md), which the front end lowers to a program. Each family
stresses one part of the compiler or of the engine, and the docstring of its function says which. The
names are generic (`Cell`, `tank`, `chain`): no family is a model of the catalogue, and none reads a
library. Every value rests on one record, `shape`, an assumption that says that the model is
synthetic.

`write(family, n, folder)` writes `<folder>/<family>_<n>/model.scn`, with a `units.json` beside it when
the family needs a unit that the prelude lacks, and the table of a family whose members are the rows
of a table. The harness writes the models into a temporary folder: no file of a family is kept in the
checkout.

A run lasts ten days, or two days for `rationing` and `priority`. The copies of a family are members
written by hand (`c1: Cell`, each with its own value), or the rows of a table in the families
`table_...`. In a family with events, each event has a time of its own, so the number of moments grows
with `n`. An event that watches a moving quantity watches a tally, which only rises: a contact on a
curve is certified for a store that only rises or only falls.
"""

from __future__ import annotations

import json
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from pathlib import Path

RECORD = 'record shape: assumption "A synthetic model of the benchmark, with no source."'


def _file(title, summary, horizon, *blocks):
    """The text of a main file: the scenario line, the blocks of its entities and values, the
    record."""
    head = (
        f'scenario "{title}"',
        f'    summary "{summary}"',
        f'    horizon {horizon}',
        '    scope "Nothing: the model is synthetic."',
    )
    return '\n\n'.join('\n'.join(block) for block in (head, *blocks, (RECORD,))) + '\n'


def _copies(n, name, value):
    """`n` members of the template `Cell`, `c1` to `cn`, each with its own `name`: `value(k)`."""
    return tuple(line for k in range(1, n + 1) for line in (f'c{k}: Cell', f'    {name} = {value(k)} @shape'))


def _cell(level):
    """The template of the families of copies: a stock with three flows out of it or into it, a tally
    that fills at a constant rate, and two events. The first event watches the tally, so each copy
    opens its gate at a time of its own (its `level`); the second shuts the gate two days later. The
    stock's outflow is capped at 10 fractions a day. The gate is a yes/no: the sparse integrator does
    not read an enum in a moving rate yet (`engine/timeline/sparse.py`, `compiled`)."""
    return (
        'Cell:',
        '    "One cell."',
        '    input inflow: fraction/day = 0.06 fraction/day in [0 fraction/day, 0.08 fraction/day] @shape',
        '    input leak: ratio/day = 0.02 ratio/day in [0 ratio/day, 1 ratio/day] @shape',
        '    input spillway: fraction/day = 0.15 fraction/day in [0.05 fraction/day, 0.3 fraction/day] @shape',
        f'    level: fraction = {level} @shape',
        '    water: fraction = 0.6 in [0,] scale 1 @shape',
        '        outflow.capacity = 10 fraction/day',
        '    gate_open: bool = false',
        '    spilled: fraction = 0 in [0,] scale 1 @shape',
        '    seeped: fraction = 0 in [0,] scale 1 @shape',
        '    arrived: fraction = 0 in [0,] scale 1 @shape',
        '    flow arrive: SOURCE -> this.arrived',
        '        request = this.inflow',
        '        capacity = this.inflow',
        '    flow storm: SOURCE -> this.water',
        '        request = this.inflow',
        '        capacity = this.inflow',
        '    flow seep: this.water -> this.seeped',
        '        request = formula(this.leak * this.water)',
        '    flow spill: this.water -> this.spilled',
        '        request = formula(this.spillway if this.gate_open else 0 fraction/day)',
        '    open = event():',
        '        "The gate opens."',
        '        when this.arrived >= this.level:',
        '            this.open.start()',
        '        after 0 h:',
        '            this.gate_open = true',
        '            this.shut.start()',
        '    shut = event():',
        '        "The gate shuts."',
        '        after 2 days:',
        '            this.gate_open = false',
    )


_CELL_VALUES = (
    ('spilled_total = formula(sum(Cell.instances.spilled)) @shape', '    "Water that all cells spill"'),
    ('seeped_total = formula(sum(Cell.instances.seeped)) @shape', '    "Water that seeps from all cells"'),
)


def _level(n):
    return lambda k: f'{0.02 + 0.3 * k / n!r}'


def instances(n):
    """`n` independent copies of one template. Each copy has a stock, four flows, a tally and two
    events at times of its own, and no copy reads another. Two values of the top level add a tally of
    every copy.

    It stresses how the cost of the compiler and of a run grows with the number of members when
    nothing joins them: the work that a moment of one copy makes for the other copies is waste."""
    return _file(
        'Independent instances',
        f'{n} cells of one template, each with a gate that opens and shuts at a time of its own.',
        '10 days',
        _cell(0.02),
        _copies(n, 'level', _level(n)),
        *_CELL_VALUES,
    )


def aggregate_output(n):
    """The cells of `instances`, and one formula of a separate entity that adds the water of every
    copy. Only a value of the top level reads the formula: no rate, no event and no check does.

    It stresses an aggregate that the run itself never needs: an engine that calculates every formula
    at each evaluation pays for it, and an engine that calculates only what is read does not."""
    return _file(
        'An aggregate that only a value of the top level reads',
        f'{n} cells of one template, and the water that they hold together, which only one value reads.',
        '10 days',
        _cell(0.02),
        _copies(n, 'level', _level(n)),
        (
            'pool:',
            '    "What the cells hold together."',
            '    held = formula(sum(Cell.instances.water)) @shape',
        ),
        *_CELL_VALUES,
        ('held = formula(pool.held) @shape', '    "Water in all cells"'),
    )


def aggregate_guard(n):
    """`n` copies with a yes/no each, which the copy's own event sets at a time of its own, and one
    event of a separate entity whose trigger counts the flags of all copies. The count reaches its
    threshold only with the last copy, so the condition is read again after each of the `n` events.

    It stresses a guard over an aggregate: each moment changes one member, and an engine that reads
    the whole collection again at each moment makes the cost of a run grow with the square of `n`."""
    return _file(
        'An aggregate that a guard reads',
        f'{n} cells raise a flag one after the other, and a watcher counts the flags.',
        '10 days',
        (
            'Cell:',
            '    "One cell."',
            '    input pace: fraction/day = 0.05 fraction/day in [0 fraction/day, 0.1 fraction/day] @shape',
            '    due: h = 9 days @shape',
            '    flag: bool = false @shape',
            '    filled: fraction = 0 in [0,] scale 1 @shape',
            '    flow fill: SOURCE -> this.filled',
            '        request = formula(0 fraction/day if this.flag else this.pace)',
            '    raise_flag = event():',
            '        "The cell raises its flag."',
            '        when t >= this.due:',
            '            this.raise_flag.start()',
            '        after 0 h:',
            '            this.flag = true',
        ),
        _copies(n, 'due', lambda k: f'{9 * 24 * k / n!r} h'),
        (
            'watch:',
            '    "The watcher of the cells."',
            '    alarm: enum[OFF, ON] = OFF',
            '    sound = event():',
            '        "Every cell has its flag up."',
            f'        when count(Cell.instances.flag) >= {n}:',
            '            this.sound.start()',
            '        after 0 h:',
            '            this.alarm = ON',
        ),
        ('filled_total = formula(sum(Cell.instances.filled)) @shape', '    "Content of all cells"'),
    )


def aggregate_feedback(n):
    """`n` copies whose one flow reads a formula of a separate entity, the mean level of all copies.
    So the rate of each copy depends on the level of every copy. The copies start at different
    levels.

    It stresses a dense coupling: the Jacobian of the rates has no zero entry, and no copy can be
    solved alone."""
    return _file(
        'An aggregate that feeds back into the rates',
        f'{n} cells grow together until their mean level reaches 1.',
        '10 days',
        (
            'pool:',
            '    "What the cells hold together."',
            f'    mean = formula(sum(Cell.instances.level) / {n}) @shape',
        ),
        (
            'Cell:',
            '    "One cell."',
            '    input gain: ratio/day = 0.5 ratio/day in [0 ratio/day, 2 ratio/day] @shape',
            '    input start: fraction = 0.05 in [0, 1] @shape',
            '    level: fraction = this.start in [0,] scale 1 @shape',
            '    flow grow: SOURCE -> this.level',
            '        request = formula(this.gain * this.level * max(0, 1 - pool.mean))',
        ),
        _copies(n, 'start', lambda k: f'{0.05 + 0.4 * k / n!r}'),
        ('level_total = formula(sum(Cell.instances.level)) @shape', '    "Level of all cells"'),
    )


def _chain(n, rate):
    """The stores and the flows of a chain of `n` compartments, `c1` to `cn`, that ends in the tally
    `out`: `rate(k)` is the request of the flow out of compartment `k`. Only the first compartment
    holds something at the start."""
    lines = ['    c1: fraction = 1 in [0,] scale 1 @shape']
    lines += [f'    c{k}: fraction = 0 in [0,] scale 1 @shape' for k in range(2, n + 1)]
    lines += ['    out: fraction = 0 in [0,] scale 1 @shape', '        "Content that left the chain"']
    for k in range(1, n + 1):
        lines += [
            f'    flow f{k}: this.c{k} -> this.{f"c{k + 1}" if k < n else "out"}',
            f'        request = formula({rate(k)})',
        ]
    return lines


def stiff(n):
    """A chain of `n` compartments in one entity. The flow out of each compartment saturates with its
    content, so no flow is linear, and the flows out of the odd compartments are `stiffness` times as
    fast as those out of the even ones: 1000 times, an input.

    It stresses the stiff solver: the fast compartments settle in minutes and the slow ones in days,
    so an explicit method would need steps of the fast time over the whole run."""
    return _file(
        'A stiff chain',
        f'A chain of {n} compartments, by turns fast and slow.',
        '10 days',
        (
            'chain:',
            '    "The chain."',
            '    input slow: ratio/h = 0.02 ratio/h in [0.001 ratio/h, 1 ratio/h] @shape',
            '    input stiffness: ratio = 1000 in [1, 1000000] @shape',
            '    input half: fraction = 0.5 in [0.1, 10] @shape',
            *_chain(
                n,
                lambda k: (
                    f'this.slow * {"this.stiffness * " if k % 2 else ""}this.c{k} / (this.half + this.c{k})'
                ),
            ),
        ),
    )


def events(n):
    """A small model whose one event starts `n` times, at equal steps over the run: its trigger rearms
    once the time is before the next ring again. Each start sets the time of the next one and switches
    a lamp, which starts or stops a flow.

    It stresses the density of events: the model keeps its size, and the number of moments, and of
    segments between them, grows with `n`."""
    return _file(
        'Many timer events',
        f'A clock rings {n} times, and each ring switches a lamp.',
        '10 days',
        (
            'clock:',
            '    "The clock."',
            f'    period: h = {240 / (n + 0.5)!r} h @shape',
            '    next: h = this.period in [0 h, 500 h] @shape',
            '    lamp: enum[OFF, ON] = OFF',
            '    lit: h = 0 h in [0 h,] scale 240 h @shape',
            '        "Time with the lamp on"',
            '    flow glow: SOURCE -> this.lit',
            '        request = formula(1 if this.lamp == ON else 0)',
            '    ring = event():',
            '        "The clock rings."',
            '        when t >= this.next:',
            '            this.ring.start()',
            '            reset when t < this.next',
            '        after 0 h:',
            '            this.next += this.period',
            '            this.lamp = OFF if this.lamp == ON else ON',
        ),
    )


# The unit of `rationing` and of `priority`, which the prelude lacks.
RATIONING_UNITS = {'L': {'dimensions': {'volume': 1}, 'scale': 1, 'description': 'One litre.'}}


def _tank(n, title, ordered):
    """The model of `rationing` and of `priority`: `n` flows out of one tank. The first asks 20 L/h at
    the start, the second 40 L/h, and so on, and each asks more as its user has taken more, up to twice
    as much. The tank's outflow is capped at 80% of what they ask at the start; `ordered` says whether
    it serves them in order (`priority`) or in proportion (the default). The tank fills at a quarter of
    what they ask at the start, and no faster (a request is soft, D15: the capacity holds it), so it is
    empty after about 14 of the 48 hours, and from then the flows share the inflow."""
    pairs = n * (n + 1)  # the flows ask 10 x pairs L/h together at the start
    order = f'priority({", ".join(f"this.use_{k}" for k in range(1, n + 1))})'
    return _file(
        title,
        f'{n} users drain a tank that fills more slowly than they ask.',
        '48 h',
        (
            'tank:',
            '    "The tank."',
            f'    input inflow: L/h = {5 * pairs // 2} L/h in [0 L/h, {10 * pairs} L/h] @shape',
            f'    input habit: L = {200 * n} L in [1 L, {100000 * n} L] @shape',
            f'    water: L = {80 * pairs} L in [0 L,] scale {80 * pairs} L @shape',
            f'        outflow.capacity = {8 * pairs} L/h',
            *((f'        outflow.allocation = {order}',) if ordered else ()),
            *(f'    used_{k}: L = 0 L in [0 L,] scale {2000 * n} L @shape' for k in range(1, n + 1)),
            '    flow fill: SOURCE -> this.water',
            '        request = this.inflow',
            '        capacity = this.inflow',
            *(
                line
                for k in range(1, n + 1)
                for line in (
                    f'    flow use_{k}: this.water -> this.used_{k}',
                    f'        request = formula({20 * k} L/h * (1 + this.used_{k} / (this.habit + this.used_{k})))',
                )
            ),
        ),
        (
            f'used = formula({" + ".join(f"tank.used_{k}" for k in range(1, n + 1))}) @shape',
            '    "Water that the users take"',
        ),
    )


def rationing(n):
    """`n` flows out of one tank, whose outflow serves them in proportion to what they ask. Each flow
    asks more as its user has taken more, the outflow's capacity caps their total, and the tank fills
    more slowly than they ask: it is empty after about 14 of the 48 hours, and from then the flows
    share the inflow.

    It stresses local sharing: each change of the rates applies the cap, and the stock rests on its
    bound, where the flows are limited to what comes in. The rates read the state, so they move."""
    return _tank(n, 'Rationing at a bound', ordered=False)


def priority(n):
    """The tank of `rationing`, whose outflow serves the flows in order (`priority`): the first flows
    get all that they ask, one flow gets what is left, and the flows after it get nothing. The flow at
    which the cap cuts changes as the users ask more.

    It stresses the allocation in order, at the cap and at the bound of the stock, with requests that
    move."""
    return _tank(n, 'Priority at a bound', ordered=True)


def compartments(n):
    """A chain of `n` compartments in one entity. The rate of each flow is proportional to the content
    of its compartment, with one of three coefficients.

    It stresses a linear system of compartments, whose rates read the state."""
    return _file(
        'A linear chain of compartments',
        f'A chain of {n} compartments, each of which drains in proportion to its content.',
        '10 days',
        (
            'chain:',
            '    "The chain."',
            '    input pace: ratio/h = 0.05 ratio/h in [0.001 ratio/h, 1 ratio/h] @shape',
            *_chain(n, lambda k: f'this.pace * {1 + k % 3} * this.c{k}'),
        ),
    )


def formulas(n):
    """A chain of `n` formulas in one entity: the first reads a stock, and each other one reads the
    formula before it, once, and the stock. Three flows read the last formula, the middle one and the
    first.

    It stresses the evaluation of formulas: each evaluation of the rates needs the whole chain, and
    the checks of the compiler and of the engine follow a chain of `n` names."""
    return _file(
        'Many formulas',
        f'A tank whose flows read a chain of {n} formulas.',
        '10 days',
        (
            'tank:',
            '    "The tank."',
            '    input pace: ratio/h = 0.02 ratio/h in [0 ratio/h, 1 ratio/h] @shape',
            '    level: fraction = 1 in [0,] scale 1 @shape',
            '    passed: fraction = 0 in [0,] scale 1 @shape',
            '        "Content that left the tank"',
            '    seen: fraction = 0 in [0,] scale 10 @shape',
            '    noted: fraction = 0 in [0,] scale 10 @shape',
            '    f1 = formula(this.level / (1 + this.level)) @shape',
            *(
                f'    f{k} = formula((this.f{k - 1} + this.level) / (1 + this.level)) @shape'
                for k in range(2, n + 1)
            ),
            '    flow drain: this.level -> this.passed',
            f'        request = formula(this.pace * this.f{n})',
            '    flow see: SOURCE -> this.seen',
            f'        request = formula(this.pace * this.f{max(1, n // 2)})',
            '    flow note: SOURCE -> this.noted',
            '        request = formula(this.pace * this.f1)',
        ),
    )


# ---- the families whose members are the rows of a table (docs/language.md) ----------------------------
#
# The four families of copies again, each with its cells from a table: the value that each copy wrote
# by hand is a column of the table.


def _table(n, header, value):
    """The text of a table of `n` rows with one column of numbers: `value(k)` for row k, from 1."""
    return '\n'.join([header, *(repr(value(k)) for k in range(1, n + 1))]) + '\n'


def _from_table(text, n):
    """The text of a family of copies with its cells from the table `cells.csv` in place of the
    members written by hand."""
    first, last = text.index('c1: Cell'), text.index('\n\n', text.index(f'c{n}: Cell'))
    return text[:first] + 'cells: Cell from "cells.csv"' + text[last:]


def table_instances(n):
    """`instances` with its `n` cells from a table: the level at which each gate opens is a column.

    It stresses the compile of many rows of one shape, with no collection over them but two sums."""
    return _from_table(instances(n), n)


def table_aggregate_output(n):
    """`aggregate_output` with its `n` cells from a table.

    It stresses a sum over every row that only a value of the top level reads."""
    return _from_table(aggregate_output(n), n)


def table_aggregate_guard(n):
    """`aggregate_guard` with its `n` cells from a table: the time of each flag is a column.

    It stresses a guard over every row while each event changes one row."""
    return _from_table(aggregate_guard(n), n)


def table_aggregate_feedback(n):
    """`aggregate_feedback` with its `n` cells from a table: the start level of each cell is a column.

    It stresses a sum over every row that feeds the rate of every row."""
    return _from_table(aggregate_feedback(n), n)


def _levels(n):
    return {'cells.csv': _table(n, 'level: fraction', lambda k: 0.02 + 0.3 * k / n)}


def _dues(n):
    return {'cells.csv': _table(n, 'due: h', lambda k: 9 * 24 * k / n)}


def _starts(n):
    return {'cells.csv': _table(n, 'start: fraction', lambda k: 0.05 + 0.4 * k / n)}


@dataclass(frozen=True)
class Family:
    """One family: its name, the function that gives the text of its model of size `n`, the units of
    its own (the content of a `units.json`), if it needs any, and the other files of its package
    (`files(n)`, {name: text}: the table of a family whose instances are the rows of a table)."""

    name: str
    text: Callable[[int], str]
    units: Mapping | None = None
    files: Callable[[int], Mapping] | None = None

    @property
    def stresses(self):
        """What the family is and what it stresses: the docstring of its function, on one line."""
        return ' '.join((self.text.__doc__ or '').split())


FAMILIES = {
    family.name: family
    for family in (
        Family('instances', instances),
        Family('aggregate_output', aggregate_output),
        Family('aggregate_guard', aggregate_guard),
        Family('aggregate_feedback', aggregate_feedback),
        Family('stiff', stiff),
        Family('events', events),
        Family('rationing', rationing, RATIONING_UNITS),
        Family('priority', priority, RATIONING_UNITS),
        Family('compartments', compartments),
        Family('formulas', formulas),
        Family('table_instances', table_instances, files=_levels),
        Family('table_aggregate_output', table_aggregate_output, files=_levels),
        Family('table_aggregate_guard', table_aggregate_guard, files=_dues),
        Family('table_aggregate_feedback', table_aggregate_feedback, files=_starts),
    )
}


def write(family, n, folder):
    """Write the model of size `n` of the family named `family` into `<folder>/<family>_<n>/` and
    return the path of its main file. An unknown family raises KeyError, and a size below 1
    ValueError."""
    found = FAMILIES[family]
    if isinstance(n, bool) or not isinstance(n, int) or n < 1:
        raise ValueError(f'the size of a family is a whole number from 1: {n!r}')
    target = Path(folder) / f'{family}_{n}'
    target.mkdir(parents=True, exist_ok=True)
    path = target / 'model.scn'
    path.write_text(found.text(n), encoding='utf-8')
    if found.units:
        (target / 'units.json').write_text(json.dumps(found.units, indent=1), encoding='utf-8')
    for name, text in (found.files(n) if found.files else {}).items():
        (target / name).write_text(text, encoding='utf-8')
    return path
