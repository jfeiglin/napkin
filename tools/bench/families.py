"""The synthetic families of the benchmark: models made as text, one for each size.

A family is a function `text(n)` that gives the main file of a model of size `n` (1 or more), in the
scenario language (docs/language.md). Each family stresses one part of the compiler or of the engine,
and the docstring of its function says which. The names are generic (`Cell`, `tank`, `chain`): no
family is a model of the catalogue, and none reads a library. Every value rests on one record, `shape`,
an assumption that says that the model is synthetic.

`write(family, n, folder)` writes `<folder>/<family>_<n>/model.scn`, with a `units.json` beside it when
the family needs a unit that the prelude lacks. The harness writes the models into a temporary folder:
no file of a family is kept in the checkout.

A run lasts ten days, or two days for `rationing` and `priority`. In a family with events, each event has a time of
its own, so the number of moments grows with `n`. An event that watches a quantity watches a tally,
which only rises: the language allows a crossing of no other moving quantity
(docs/language.md, §2.6, "What a `when` may be").
"""

from __future__ import annotations

import json
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from pathlib import Path

RECORD = 'record shape: assumption "A synthetic model of the benchmark, with no source."'


def _file(title, summary, horizon, *blocks):
    """The text of a main file: the scenario line, the blocks of its things and outputs, the record."""
    head = (
        f'scenario "{title}"',
        f'    summary "{summary}"',
        f'    horizon {horizon}',
        '    scope "Nothing: the model is synthetic."',
    )
    return '\n\n'.join('\n'.join(block) for block in (head, *blocks, (RECORD,))) + '\n'


def _cell(n):
    """The template of the families of instances: a stock with three flows, a tally that fills at a
    constant rate, and two events. The first event watches the tally, so each copy opens its gate at
    a time of its own (`level` reads `copy`); the second shuts the gate two days later."""
    return (
        'Cell:  @shape',
        '    "One cell."',
        '    input inflow: fraction/day = 0.06 fraction/day in 0 fraction/day to 0.08 fraction/day  @shape',
        '    input leak: ratio/day = 0.02 ratio/day in 0 ratio/day to 1 ratio/day  @shape',
        '    input spillway: fraction/day = 0.15 fraction/day in 0.05 fraction/day to 0.3 fraction/day  @shape',
        f'    let level: fraction = 0.02 + 0.3 * copy / {n}  @shape',
        '    var water: fraction = 0.6 size 1  @shape',
        '    var gate: "closed" | "open" = "closed"',
        '    var spilled: fraction = 0 size 1  @shape',
        '    var seeped: fraction = 0 size 1  @shape',
        '    var arrived: fraction = 0 size 1  @shape',
        '    flow arrive: -> arrived at inflow',
        '    flow storm: -> water at inflow',
        '    flow seep: water -> seeped at leak * water',
        '    flow spill: water -> spilled at spillway while gate is "open"',
        '    share water limit 10 fraction/day',
        '    event open once when arrived >= level:  @shape',
        '        "The gate opens."',
        '        gate = "open"',
        '    event shut once after 2 days when count(open) > 0:  @shape',
        '        "The gate shuts."',
        '        gate = "closed"',
    )


_CELL_OUTPUTS = (
    ('output spilled_total: fraction = sum(Cell.spilled)  @shape', '    "Water that all cells spill"'),
    ('output seeped_total: fraction = sum(Cell.seeped)  @shape', '    "Water that seeps from all cells"'),
)


def instances(n):
    """`n` independent copies of one template. Each copy has a stock, four flows, a tally and two
    events at times of its own, and no copy reads another. Two outputs add a tally of every copy.

    It stresses how the cost of the compiler and of a run grows with the number of instances when
    nothing joins them: the work that a moment of one copy makes for the other copies is waste."""
    return _file(
        'Independent instances',
        f'{n} cells of one template, each with a gate that opens and shuts at a time of its own.',
        '10 days',
        _cell(n),
        (f'cells: Cell * {n}',),
        *_CELL_OUTPUTS,
    )


def aggregate_output(n):
    """The cells of `instances`, and one formula of a separate thing that adds the water of every
    copy. Only an output reads the formula: no rate, no event and no check does.

    It stresses an aggregate that the run itself never needs: an engine that calculates every formula
    at each evaluation pays for it, and an engine that calculates only what is read does not."""
    return _file(
        'An aggregate that only an output reads',
        f'{n} cells of one template, and the water that they hold together, which only an output reads.',
        '10 days',
        _cell(n),
        (f'cells: Cell * {n}',),
        (
            'pool:  @shape',
            '    "What the cells hold together."',
            '    let held: fraction = sum(Cell.water)  @shape',
        ),
        *_CELL_OUTPUTS,
        ('output held: fraction = pool.held  @shape', '    "Water in all cells"', '    level'),
    )


def aggregate_guard(n):
    """`n` copies with a yes/no state each, which the copy's own event sets at a time of its own, and
    one event of a separate thing whose `when` counts the states of all copies. The count reaches its
    threshold only with the last copy, so the condition is read again after each of the `n` events.

    It stresses a guard over an aggregate: each moment changes one member, and an engine that reads
    the whole list again at each moment makes the cost of a run grow with the square of `n`."""
    return _file(
        'An aggregate that a guard reads',
        f'{n} cells raise a flag one after the other, and a watcher counts the flags.',
        '10 days',
        (
            'Cell:  @shape',
            '    "One cell."',
            '    input pace: fraction/day = 0.05 fraction/day in 0 fraction/day to 0.1 fraction/day  @shape',
            f'    let due: h = 9 days * copy / {n}  @shape',
            '    var flag = false  @shape',
            '    var filled: fraction = 0 size 1  @shape',
            '    flow fill: -> filled at pace while not flag',
            '    event raise_flag once when t >= due:  @shape',
            '        "The cell raises its flag."',
            '        flag = true',
        ),
        (f'cells: Cell * {n}',),
        (
            'watch:  @shape',
            '    "The watcher of the cells."',
            '    var alarm: "off" | "on" = "off"',
            f'    event sound once when count(Cell.flag) >= {n}:  @shape',
            '        "Every cell has its flag up."',
            '        alarm = "on"',
        ),
        ('output filled_total: fraction = sum(Cell.filled)  @shape', '    "Content of all cells"'),
    )


def aggregate_feedback(n):
    """`n` copies whose one flow reads a formula of a separate thing, the mean level of all copies. So
    the rate of each copy depends on the level of every copy. The copies start at different levels.

    It stresses a dense coupling: the Jacobian of the rates has no zero entry, and no copy can be
    solved alone."""
    return _file(
        'An aggregate that feeds back into the rates',
        f'{n} cells grow together until their mean level reaches 1.',
        '10 days',
        (
            'pool:  @shape',
            '    "What the cells hold together."',
            f'    let mean: fraction = sum(Cell.level) / {n}  @shape',
        ),
        (
            'Cell:  @shape',
            '    "One cell."',
            '    input gain: ratio/day = 0.5 ratio/day in 0 ratio/day to 2 ratio/day  @shape',
            f'    let start: fraction = 0.05 + 0.4 * copy / {n}  @shape',
            '    var level: fraction = start size 1  @shape',
            '    flow grow: -> level at gain * level * max(0, 1 - pool.mean)',
        ),
        (f'cells: Cell * {n}',),
        ('output level_total: fraction = sum(Cell.level)  @shape', '    "Level of all cells"'),
    )


def _chain(n, rate):
    """The vars and the flows of a chain of `n` compartments, `c1` to `cn`, that ends in the tally
    `out`, an output: `rate(k)` is the rate of the flow out of compartment `k`. Only the first
    compartment holds something at the start."""
    lines = ['    var c1: fraction = 1 size 1  @shape']
    lines += [f'    var c{k}: fraction = 0 size 1  @shape' for k in range(2, n + 1)]
    lines += [
        '    var out: fraction = 0 size 1  @shape',
        '        "Content that left the chain"',
        '    output out',
    ]
    for k in range(1, n + 1):
        lines.append(f'    flow f{k}: c{k} -> {f"c{k + 1}" if k < n else "out"} at {rate(k)}')
    return lines


def stiff(n):
    """A chain of `n` compartments in one thing. The flow out of each compartment saturates with its
    content, so no flow is linear, and the flows out of the odd compartments are `stiffness` times as
    fast as those out of the even ones: 1000 times, an input.

    It stresses the stiff solver: the fast compartments settle in minutes and the slow ones in days,
    so an explicit method would need steps of the fast time over the whole run."""
    return _file(
        'A stiff chain',
        f'A chain of {n} compartments, by turns fast and slow.',
        '10 days',
        (
            'chain:  @shape',
            '    "The chain."',
            '    input slow: ratio/h = 0.02 ratio/h in 0.001 ratio/h to 1 ratio/h  @shape',
            '    input stiffness: ratio = 1000 in 1 to 1000000  @shape',
            '    input half: fraction = 0.5 in 0.1 to 10  @shape',
            *_chain(n, lambda k: f'slow * {"stiffness * " if k % 2 else ""}c{k} / (half + c{k})'),
        ),
    )


def events(n):
    """A small model whose one event fires `n` times, at equal steps over the run. Each firing sets the
    time of the next one and switches a lamp, which starts or stops a flow.

    It stresses the density of events: the model keeps its size, and the number of moments, and of
    segments between them, grows with `n`."""
    return _file(
        'Many timer events',
        f'A clock rings {n} times, and each ring switches a lamp.',
        '10 days',
        (
            'clock:  @shape',
            '    "The clock."',
            f'    let period: h = 240 h / {n + 0.5}  @shape',
            '    var next: h = period in 0 h to 500 h  @shape',
            '    var lamp: "off" | "on" = "off"',
            '    var lit: h = 0 h size 240 h  @shape',
            '        "Time with the lamp on"',
            '    output lit',
            '    flow glow: -> lit at 1 while lamp is "on"',
            '    event ring when t >= next:  @shape',
            '        "The clock rings."',
            '        next += period',
            '        lamp = "off" if lamp is "on" else "on"',
        ),
    )


# The unit of `rationing` and of `priority`, which the prelude lacks.
RATIONING_UNITS = {'L': {'dimensions': {'volume': 1}, 'scale': 1, 'description': 'One litre.'}}


def _tank(n, title, ordered):
    """The model of `rationing` and of `priority`: `n` flows out of one tank. The first asks 20 L/h at
    the start, the second 40 L/h, and so on, and each asks more as its user has taken more, up to twice
    as much. A `share` caps their total at 80% of what they ask at the start; `ordered` says whether it
    serves them in order or in proportion. The tank fills at a quarter of what they ask at the start,
    so it is empty after about 14 of the 48 hours, and from then the flows share the inflow."""
    pairs = n * (n + 1)  # the flows ask 10 × pairs L/h together at the start
    order = f' order {", ".join(f"use_{k}" for k in range(1, n + 1))}' if ordered else ''
    return _file(
        title,
        f'{n} users drain a tank that fills more slowly than they ask.',
        '48 h',
        (
            'tank:  @shape',
            '    "The tank."',
            f'    input inflow = {5 * pairs // 2} L/h in 0 L/h to {10 * pairs} L/h  @shape',
            f'    input habit: L = {200 * n} L in 1 L to {100000 * n} L  @shape',
            f'    var water: L = {80 * pairs} L size {80 * pairs} L  @shape',
            *(f'    var used_{k}: L = 0 L size {2000 * n} L  @shape' for k in range(1, n + 1)),
            '    flow fill: -> water at inflow',
            *(
                f'    flow use_{k}: water -> used_{k} at {20 * k} L/h * (1 + used_{k} / (habit + used_{k}))'
                for k in range(1, n + 1)
            ),
            f'    share water limit {8 * pairs} L/h{order}',
        ),
        (
            f'output used: L = {" + ".join(f"tank.used_{k}" for k in range(1, n + 1))}  @shape',
            '    "Water that the users take"',
        ),
    )


def rationing(n):
    """`n` flows out of one tank, which a `share` serves in proportion to what they ask. Each flow asks
    more as its user has taken more, the share caps their total, and the tank fills more slowly than
    they ask: it is empty after about 14 of the 48 hours, and from then the flows share the inflow.

    It stresses the allocation: each evaluation of the rates applies the cap, and the stock rests on its
    bound, where the flows are limited to what comes in. The rates read the state, so the segments are
    numerical."""
    return _tank(n, 'Rationing at a bound', ordered=False)


def priority(n):
    """The tank of `rationing`, with a `share` that serves the flows in order: the first flows get all
    that they ask, one flow gets what is left, and the flows after it get nothing. The flow at which
    the share cuts changes as the users ask more.

    It stresses the allocation in order, at the cap and at the bound of the stock, with requests that
    change at each evaluation of the rates."""
    return _tank(n, 'Priority at a bound', ordered=True)


def compartments(n):
    """A chain of `n` compartments in one thing. The rate of each flow is proportional to the content
    of its compartment, with one of three coefficients.

    It stresses the exact solution of a linear system of compartments, which today's engine finds from
    the structure and solves by a matrix exponential, with no numerical step."""
    return _file(
        'A linear chain of compartments',
        f'A chain of {n} compartments, each of which drains in proportion to its content.',
        '10 days',
        (
            'chain:  @shape',
            '    "The chain."',
            '    input pace: ratio/h = 0.05 ratio/h in 0.001 ratio/h to 1 ratio/h  @shape',
            *_chain(n, lambda k: f'pace * {1 + k % 3} * c{k}'),
        ),
    )


def formulas(n):
    """A chain of `n` formulas in one thing: the first reads a stock, and each other one reads the
    formula before it, once, and the stock. Three flows read the last formula, the middle one and the
    first.

    It stresses the evaluation of formulas: each evaluation of the rates needs the whole chain, and
    the checks of the compiler and of the engine follow a chain of `n` names."""
    return _file(
        'Many formulas',
        f'A tank whose flows read a chain of {n} formulas.',
        '10 days',
        (
            'tank:  @shape',
            '    "The tank."',
            '    input pace: ratio/h = 0.02 ratio/h in 0 ratio/h to 1 ratio/h  @shape',
            '    var level: fraction = 1 size 1  @shape',
            '    var passed: fraction = 0 size 1  @shape',
            '        "Content that left the tank"',
            '    output passed',
            '    var seen: fraction = 0 size 10  @shape',
            '    var noted: fraction = 0 size 10  @shape',
            '    let f1: fraction = level / (1 + level)  @shape',
            *(f'    let f{k}: fraction = (f{k - 1} + level) / (1 + level)  @shape' for k in range(2, n + 1)),
            f'    flow drain: level -> passed at pace * f{n}',
            f'    flow see: -> seen at pace * f{max(1, n // 2)}',
            '    flow note: -> noted at pace * f1',
        ),
    )


# ---- the families whose instances are the rows of a table (docs/language.md, §2.3) --------------------
#
# The four families of instances again, each with its cells from a table: the value that a copy took
# from its number (`copy`) is a column. A table can have 100,000 rows; the flat structure of such a
# model is not made, and the harness measures the hybrid core of it (`napkin/model/hybrid.py`).


def _table(n, header, value):
    """The text of a table of `n` rows with one column of numbers: `value(k)` for row k, from 1."""
    return '\n'.join([header, *(repr(value(k)) for k in range(1, n + 1))]) + '\n'


def _from_table(text, n, old, new):
    """The text of a family of copies with its cells from the table `cells.csv`, and one line of its
    template changed: the value that read the number of the copy is a value that the table gives."""
    if text.count(old) != 1 or text.count(f'cells: Cell * {n}') != 1:
        raise ValueError(f'the family has no line {old!r}')
    return text.replace(old, new).replace(f'cells: Cell * {n}', 'cells: Cell from "cells.csv"')


def table_instances(n):
    """`instances` with its `n` cells from a table: the level at which each gate opens is a column.

    It stresses the compile of many rows of one shape, with no list over them but two outputs."""
    old = f'    let level: fraction = 0.02 + 0.3 * copy / {n}  @shape'
    return _from_table(instances(n), n, old, '    let level: fraction = 0.02  @shape')


def table_aggregate_output(n):
    """`aggregate_output` with its `n` cells from a table.

    It stresses a sum over every row that only an output reads: one node of the hybrid core."""
    old = f'    let level: fraction = 0.02 + 0.3 * copy / {n}  @shape'
    return _from_table(aggregate_output(n), n, old, '    let level: fraction = 0.02  @shape')


def table_aggregate_guard(n):
    """`aggregate_guard` with its `n` cells from a table: the time of each flag is a column.

    It stresses a guard over every row while each event changes one row."""
    old = f'    let due: h = 9 days * copy / {n}  @shape'
    return _from_table(aggregate_guard(n), n, old, '    let due: h = 9 days  @shape')


def table_aggregate_feedback(n):
    """`aggregate_feedback` with its `n` cells from a table: the start level of each cell is a column.

    It stresses a sum over every row that feeds the rate of every row."""
    old = f'    let start: fraction = 0.05 + 0.4 * copy / {n}  @shape'
    return _from_table(aggregate_feedback(n), n, old, '    let start: fraction = 0.05  @shape')


def _levels(n):
    return {'cells.csv': _table(n, 'level: fraction @shape', lambda k: 0.02 + 0.3 * k / n)}


def _dues(n):
    return {'cells.csv': _table(n, 'due: h @shape', lambda k: 9 * 24 * k / n)}


def _starts(n):
    return {'cells.csv': _table(n, 'start: fraction @shape', lambda k: 0.05 + 0.4 * k / n)}


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
