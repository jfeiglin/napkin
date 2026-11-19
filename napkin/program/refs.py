"""References: what an expression of a program reads, each as a structured record.

An expression of a program (`Expr`) is a node of `napkin/core/expr` and the reads that its names
stand for. A name in a node is only a key into those reads: what it reads is a record here, never a
meaning taken from the spelling or the prefix of the name. So `this.origin.level` and
`this.destination.level` are two reads through two link columns, whatever their names look like,
and a node of `napkin/core` stays a scalar calculation with no new kind.

A `Path` starts somewhere (`start`) and takes named steps. The starts are the scopes of the
language: the receiving member (`THIS`), the run's root (`ROOT`), the member inside a `where`
(`ITEM`), a member named by its id (`Named`), a bare name of the enclosing scope (`Local`: a
parameter or a local of an occurrence, a capture of a trigger, an input or an unknown of a solver),
and the collections and keyed reads (`Instances`, `Literal`, `Where`, `By`, `Lookup`). Each step is
resolved by the type of what precedes it, as the language resolves a dotted name: a field, a link
(which goes on to the member that it names), a flow, an event, a solver, a property such as
`actual_rate` or `outflow`. A step from a collection applies to each member, so a path through a
collection is a projection, as `routes.limit` is in the language.

The other reads are the named parts that the language spells as calls: a reduction of a collection
(`Reduce`), a draw (`Draw`, keyed by its site), `since` and `elapsed`, a member of an enum (`EnumValue`) and the time `t` (`TIME`). A number with a unit is the
core's literal call `q(number, unit)`, whose unit is a spelling of the program's table of units.
"""

from __future__ import annotations

from dataclasses import dataclass
from fractions import Fraction

from ..core import expr as nodes

# A number of a program, outside a node: a node holds an int or a float, as the core's constants do.
Number = int | float | Fraction

REDUCTIONS = ('sum', 'count', 'any', 'all', 'min', 'max')
# The families of distributions, with the numbers of their parameters: today's constructors and
# order of arguments, the bounded forms of `normal` and `lognormal`, and `categorical` over an enum.
FAMILIES = {
    'uniform': (2,),
    'triangular': (3,),
    'pert': (3,),
    'loguniform': (2,),
    'normal': (2, 4),
    'lognormal': (2, 4),
    'categorical': (),
}


# ---- where a path starts ---------------------------------------------------------------------------


@dataclass(frozen=True)
class This:
    """The owning or receiving member: of a member's declaration, of an event, a trigger or a
    solver on it."""


@dataclass(frozen=True)
class Root:
    """The run's root, whose values are the top-level declarations of the model."""


@dataclass(frozen=True)
class Item:
    """The member that the test of a `where` is about: the field on the left of `destination ==
    this`."""


THIS, ROOT, ITEM = This(), Root(), Item()


@dataclass(frozen=True)
class Named:
    """A member named by its id: a top-level entity (`tank`) or a table row (`sites.clinic`)."""

    id: str


@dataclass(frozen=True)
class Local:
    """A bare name of the enclosing scope: a parameter or a local (a value, a store or a flow) of an
    occurrence, a capture of a trigger, or an input or an unknown of a solver."""

    name: str


@dataclass(frozen=True)
class Instances:
    """`Template.instances`: every member of a template, keyed by its creation number."""

    template: str


@dataclass(frozen=True)
class Literal:
    """`<a, b>`: the members that the paths name, each once, of one template."""

    items: tuple[Path, ...]


@dataclass(frozen=True)
class Where:
    """`source.where(test)`: the members for which the test holds, with their keys. The test reads
    the member through `ITEM` and the enclosing scope as it is."""

    source: Path
    test: Expr


@dataclass(frozen=True)
class By:
    """`source.by(key)`: the same members, keyed by their field `key`."""

    source: Path
    key: str


@dataclass(frozen=True)
class Lookup:
    """`source.at(key)`: the member with the greatest key at or below `key`; of equal keys, the one
    created later. On an empty collection or below the first key it fails when it is read."""

    source: Path
    key: Expr


Start = This | Root | Item | Named | Local | Instances | Literal | Where | By | Lookup


@dataclass(frozen=True)
class Path:
    """A read from a start through named steps (`this.origin.power.outflow.actual_rate` is
    `Path(THIS, ('origin', 'power', 'outflow', 'actual_rate'))`)."""

    start: Start
    steps: tuple[str, ...] = ()

    def then(self, *steps):
        """The path with more steps."""
        return Path(self.start, self.steps + steps)


# ---- the other named parts that an expression reads -------------------------------------------------


@dataclass(frozen=True)
class Time:
    """`t`: the time of the run, in hours."""


TIME = Time()


@dataclass(frozen=True)
class EnumValue:
    """A member of an enum, such as `DONE` of the enum `Crew.work_state`."""

    enum: str
    member: str


@dataclass(frozen=True)
class Reduce:
    """`sum`, `count`, `any`, `all`, `min` or `max` of a collection or of a projection. An empty
    `sum` is zero in the projected unit, `count` zero, `any` false, `all` true; `min` and `max` of
    an empty collection fail when they are read (D4)."""

    op: str
    source: Path


@dataclass(frozen=True)
class Distribution:
    """A distribution: a family and its parameters. A numeric family has its parameters in one unit
    (`uniform(1 h, 3 h)` is `('uniform', (1, 3), unit='h')`), except a parameter of shape, which is a
    plain number whatever `unit` says: the second parameter of `lognormal`, its geometric standard
    deviation (`lognormal(4 h, 1.5)` is `('lognormal', (4, 1.5), unit='h')`). `categorical` has a
    weight for each outcome, a member of the enum `enum`."""

    family: str
    params: tuple[Number, ...]
    unit: str = ''
    enum: str = ''
    outcomes: tuple[str, ...] = ()


@dataclass(frozen=True)
class Draw:
    """`d.draw()`: one value of a distribution under the run's mode. `site` is its place in the
    program; a run keys each draw by its site and by the member or occurrence that executes it.

    While a program is built, a draw carries a temporary site, distinct for each draw (`?3`, or
    `?lowered3` from the front end); `build.Builder.finish` replaces it with the draw's place in the
    program (`machine.repair_time.draw[0]`). A program that `finish` made has no temporary site."""

    source: Path | Distribution
    site: str


@dataclass(frozen=True)
class Since:
    """`since(e)`: the time since the latest start of an event; it fails before the first start."""

    event: Path


@dataclass(frozen=True)
class Elapsed:
    """`elapsed(x)`: the time since the value of `x` last changed at a commit."""

    value: Path


Read = Time | Path | EnumValue | Reduce | Draw | Since | Elapsed


# ---- expressions -----------------------------------------------------------------------------------


@dataclass(frozen=True)
class Expr:
    """A node of `napkin/core/expr` and, by name, the read of each name in it (sorted by name)."""

    node: nodes.Node
    reads: tuple[tuple[str, Read], ...] = ()

    def read(self, name):
        """The read of a name of the node."""
        for found, read in self.reads:
            if found == name:
                return read
        raise KeyError(name)


@dataclass(frozen=True)
class Formula:
    """`formula(e)`: a retained calculation, evaluated again at each read. Where an ordinary
    expression stands, its value is captured once."""

    expr: Expr


# ---- spellings, for the names of reads and for messages ---------------------------------------------


def text(expression):
    """The text of an expression, with its names as they are spelled."""
    return nodes.text(expression.node)


def _number(value):
    if isinstance(value, Fraction) and value.denominator != 1:
        return f'{value.numerator}/{value.denominator}'
    return str(value)


def spelled(item):
    """A readable spelling of a read, a start or a distribution, as the language writes it. It names
    the read in a node; two reads with one spelling in one expression get a suffix (`#1`)."""
    if isinstance(item, Time):
        return 't'
    if isinstance(item, Path):
        head = spelled(item.start)
        if not item.steps:
            return head or ('item' if isinstance(item.start, Item) else 'root')
        return '.'.join(part for part in (head, *item.steps) if part)
    if isinstance(item, This):
        return 'this'
    if isinstance(item, (Root, Item)):
        return ''
    if isinstance(item, (Named, Local)):
        return item.id if isinstance(item, Named) else item.name
    if isinstance(item, Instances):
        return f'{item.template}.instances'
    if isinstance(item, Literal):
        return '<' + ', '.join(spelled(path) for path in item.items) + '>'
    if isinstance(item, Where):
        return f'{spelled(item.source)}.where({text(item.test)})'
    if isinstance(item, By):
        return f'{spelled(item.source)}.by({item.key})'
    if isinstance(item, Lookup):
        return f'{spelled(item.source)}.at({text(item.key)})'
    if isinstance(item, EnumValue):
        return item.member
    if isinstance(item, Reduce):
        return f'{item.op}({spelled(item.source)})'
    if isinstance(item, Distribution):
        if item.family == 'categorical':
            args = (f'{name}: {_number(weight)}' for name, weight in zip(item.outcomes, item.params))
        else:
            args = (f'{_number(value)} {item.unit}'.strip() for value in item.params)
        return f'{item.family}({", ".join(args)})'
    if isinstance(item, Draw):
        return f'{spelled(item.source)}.draw()'
    if isinstance(item, Since):
        return f'since({spelled(item.event)})'
    if isinstance(item, Elapsed):
        return f'elapsed({spelled(item.value)})'
    raise TypeError(f'no read: {type(item).__name__}')
