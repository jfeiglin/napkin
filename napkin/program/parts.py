"""The parts of a program: frozen records for the whole language, with no text and no place in a file.

A `Program` is what runs: its units and enums, its templates (each with its values, flows, events,
solvers, status display, assertions and members), the values of the run's root, the statements of
the setup scope, and the root's assertions. The front end lowers a model to a program; the engine,
the proofs and the oracle read programs; tests build them with `build.py`.

- **No text.** Labels, descriptions, cards, menu lines, messages and evidence stay with the declared
  model. Each record carries `origin`, the stable path of the declared part that it comes from
  (`Tank.water`, `grinder.refill.step[0]`), never a line number, so a report or a trace finds its
  label and its evidence from it. A member's id (`sites.clinic`) is its origin.
- **Expressions** are `refs.Expr`: a node of `napkin/core/expr` and the structured read of each of
  its names. A retained calculation is a `refs.Formula`; an ordinary expression in its place is
  captured once.
- **Units.** A number type names a unit by its spelling (`L/h`, `person*year`), and `units` gives
  each spelling its dimension and its exact scale, so no reader parses a unit. The spelling `''` is
  the plain number and needs no entry. Time is in hours: the dimension `time` at scale 1.
- **Members** are the rows of their template: the hand-written instances and the table rows, in
  creation order. A row's number is its natural key. A table with ids lists its rows in the order of
  their ids, so reordering the file changes no program (R-A4a-02). Each link of a member is the row
  number of the member that it names, in the link's template.
- **No `none` (D4).** Every link of every member names a row, every stored value has a starting
  value, and no constant is None.

What an engine may rely on is checked by `check.check`, which `build.Builder.finish` runs.
"""

from __future__ import annotations

from dataclasses import dataclass
from fractions import Fraction
from functools import cached_property

from .refs import Distribution, Expr, Formula, Path

# ---- units and types ----------------------------------------------------------------------------


@dataclass(frozen=True)
class Unit:
    """A spelling of a unit, its dimension (base dimensions with their powers, sorted) and the size
    of one of it in the canonical unit of that dimension (`kW` is 1000 of `W`; `min` is 1/60 h)."""

    name: str
    dimension: tuple[tuple[str, int], ...]
    scale: Fraction

    def compatible(self, other):
        """Whether two units measure one dimension."""
        return self.dimension == other.dimension


PLAIN = Unit('', (), Fraction(1))


@dataclass(frozen=True)
class Enum:
    """Named states. Two enums with the same members are two types; `name` tells them apart."""

    name: str
    members: tuple[str, ...]


@dataclass(frozen=True)
class Bool:
    """`bool`: a yes/no, which no arithmetic takes."""


@dataclass(frozen=True)
class Text:
    """Quoted text: `==` and `!=`, and nothing else."""


BOOL, TEXT = Bool(), Text()


@dataclass(frozen=True)
class Number:
    """A number in a unit of the program's table; `''` is a plain number."""

    unit: str = ''


@dataclass(frozen=True)
class EnumType:
    """A value that is a member of the enum `enum`."""

    enum: str


@dataclass(frozen=True)
class EntityType:
    """A reference to a member of a template: a link, or a parameter that passes an entity (D13)."""

    template: str


@dataclass(frozen=True)
class CollectionType:
    """`<T>`: a collection of members of one template."""

    template: str


@dataclass(frozen=True)
class DistributionType:
    """A distribution of numbers in a unit, or of the members of an enum."""

    of: Number | EnumType


Type = Bool | Text | Number | EnumType | EntityType | CollectionType | DistributionType

# ---- values ---------------------------------------------------------------------------------------

# The kinds of a value: how it gets its value over a run.
INPUT = 'input'  # fixed for the run; a configuration can override it with a value of its type
STATE = 'state'  # stored: captured from its initializer, then changed by stages, flows and moves
FORMULA = 'formula'  # a retained calculation (`init` is a Formula)
LINK = 'link'  # a reference to a member, fixed for the run (each member's row is in `Member.links`)
COLLECTION = 'collection'  # a collection binding, such as `<this.primary, this.backup>`
DISTRIBUTION = 'distribution'  # a distribution, which a stage may replace unless readonly
KINDS = (INPUT, STATE, FORMULA, LINK, COLLECTION, DISTRIBUTION)


@dataclass(frozen=True)
class Proportional:
    """`proportional()`: equal fractions of the positive claims, with unused shares passed on."""


PROPORTIONAL = Proportional()


@dataclass(frozen=True)
class Priority:
    """`priority(a, b, ...)`: incident flows or legs served first to last. An item that projects a
    keyed collection (`customers.by(rank).delivery`) ranks its flows by their keys; equal ranks
    share proportionally, and unlisted flows share the remainder."""

    items: tuple[Path, ...]


@dataclass(frozen=True)
class Endpoint:
    """The settings of `store.outflow` or `store.inflow`: a hard `capacity` and a soft `request` on
    the total rate in that direction, and the `allocation` among the incident flows."""

    capacity: Expr | Formula | None = None
    request: Expr | Formula | None = None
    allocation: Proportional | Priority = PROPORTIONAL
    origin: str = ''


@dataclass(frozen=True)
class Value:
    """A named value of a template, of the root, of an event (a parameter or a local), a capture of
    a trigger, or a new unknown of a solver.

    `init` is an expression captured once, a `Formula` (kind FORMULA), a `Distribution`, or a path
    to a collection (kind COLLECTION); a parameter and a link have none (the argument and the member
    give them). `lower` and `upper` are its closed range, either side open (None); for a stored
    value they bound its inventory, for an input they bound what a configuration may set, and for
    a solver's unknown they are its domain, read at each solve. `scale` is a numerical hint and no
    bound (D8). `outflow` and `inflow` are its settings as an endpoint of flows."""

    name: str
    kind: str
    type: Type
    init: Expr | Formula | Distribution | Path | None = None
    lower: Expr | None = None
    upper: Expr | None = None
    readonly: bool = False
    scale: Expr | None = None
    outflow: Endpoint | None = None
    inflow: Endpoint | None = None
    origin: str = ''


# ---- flows ----------------------------------------------------------------------------------------


@dataclass(frozen=True)
class Outside:
    """`SOURCE` or `SINK`: the boundary of the model, whose unit the other end gives."""

    name: str


SOURCE, SINK = Outside('SOURCE'), Outside('SINK')
End = Path | Outside

DIRECTED = 'directed'  # `source -> sink`, with its own `actual_rate`
REVERSIBLE = 'reversible'  # `a <-> b`: one signed rate, and the legs `forward` and `backward`
LEGS = 'legs'  # several directed legs served at one `served_fraction`


@dataclass(frozen=True)
class Flow:
    """A flow of a template or of an event. A directed flow or a reversible route has its two ends
    and `unit`, the unit of its rates; `request` is soft (signed on a route) and `capacity` hard,
    each captured once or a live `Formula`. A flow with legs has only `legs`, each a directed flow
    with its own unit and request, all served at one fraction."""

    name: str
    kind: str
    source: End | None = None
    sink: End | None = None
    unit: str = ''
    request: Expr | Formula | None = None
    capacity: Expr | Formula | None = None
    legs: tuple[Flow, ...] = ()
    origin: str = ''


# ---- statements, steps and triggers ---------------------------------------------------------------


@dataclass(frozen=True)
class Assign:
    """`target = value`, `target += value` or `target -= value` (`op` is `=`, `+=` or `-=`). The
    value of a formula target is a `Formula`, of a distribution a `Distribution`, of a collection a
    path, of an allocation an allocation."""

    target: Path
    op: str
    value: Expr | Formula | Distribution | Path | Proportional | Priority
    origin: str = ''


@dataclass(frozen=True)
class Move:
    """`move amount from source to destination`: one checked debit and credit, or a failure."""

    amount: Expr
    source: Path
    destination: Path
    origin: str = ''


@dataclass(frozen=True)
class Start:
    """`event.start(args)`. A path to one event starts one occurrence; a path that projects an event
    over a collection (`this.machines.repair`) starts one on each member, with the same arguments,
    which the caller evaluates once, left to right."""

    event: Path
    args: tuple[Expr, ...] = ()
    origin: str = ''


@dataclass(frozen=True)
class If:
    """`if test: then else: orelse` (D11)."""

    test: Expr
    then: tuple[Statement, ...]
    orelse: tuple[Statement, ...] = ()
    origin: str = ''


@dataclass(frozen=True)
class Case:
    """A case of a switch: a member of the selector's enum, an optional guard, and its body. A case
    whose guard is false is not eligible."""

    member: str
    body: tuple[Statement, ...]
    guard: Expr | None = None
    origin: str = ''


@dataclass(frozen=True)
class Switch:
    """`switch selector:`. The guards are read once, before the selector; a draw or a choice as the
    selector picks among the eligible cases. With no eligible case, `orelse` runs."""

    selector: Expr
    cases: tuple[Case, ...]
    orelse: tuple[Statement, ...] = ()
    origin: str = ''


Statement = Assign | Move | Start | If | Switch


@dataclass(frozen=True)
class After:
    """`after delay [when guard]:` and its stage. The delay is captured when the step is reached; the
    guard is read once, when the stage comes due. A stage with no body is a wait."""

    delay: Expr
    body: tuple[Statement, ...] = ()
    guard: Expr | None = None
    origin: str = ''


@dataclass(frozen=True)
class Until:
    """`until test`: a gate between steps, which waits until the live condition holds."""

    test: Expr
    origin: str = ''


Step = After | Until


@dataclass(frozen=True)
class Reset:
    """How a trigger rearms after it fires: `when` a condition holds, or `after` a duration captured
    at the firing. A trigger with no reset rearms when its condition becomes false."""

    kind: str
    expr: Expr


@dataclass(frozen=True)
class Trigger:
    """`when test:` of an event: it fires when its condition first becomes true, takes its captures
    in written order, and runs its body, which starts its own event and nothing else."""

    test: Expr
    body: tuple[Statement, ...]
    captures: tuple[Value, ...] = ()
    reset: Reset | None = None
    origin: str = ''


@dataclass(frozen=True)
class Event:
    """An event of a template. `params` are its signature, in order. `locals` are its values and
    flows in written order: the plain initializers run in that order at entry (D14). `steps` run
    in order; `triggers` belong to the event, one set for each receiver."""

    name: str
    params: tuple[Value, ...] = ()
    locals: tuple[Value | Flow, ...] = ()
    steps: tuple[Step, ...] = ()
    triggers: tuple[Trigger, ...] = ()
    origin: str = ''


# ---- solvers, displays and assertions ------------------------------------------------------------


@dataclass(frozen=True)
class Binding:
    """An input of a solver: a name for a value, a flow or a collection in the template's scope,
    which follows its source."""

    name: str
    source: Path
    origin: str = ''


@dataclass(frozen=True)
class Constraint:
    """A relation that the solver enforces: affine `==`, `<=`, `>=`, their conjunction and `all`."""

    test: Expr
    origin: str = ''


@dataclass(frozen=True)
class Objective:
    """`minimize(expr)` or `maximize(expr)`, ranked in written order."""

    sense: str
    expr: Expr
    origin: str = ''


@dataclass(frozen=True)
class Solver:
    """A solver of a template. `solve_for` names the existing fields that it determines (a stored
    number, a flow's or a route's `actual_rate`, a flow's `served_fraction`, or a projection of one
    of these); `unknowns` are its new values, each with its domain, its preferred value (`init`,
    zero without one) and its `scale`."""

    name: str
    inputs: tuple[Binding, ...] = ()
    solve_for: tuple[Path, ...] = ()
    unknowns: tuple[Value, ...] = ()
    constraints: tuple[Constraint, ...] = ()
    objective: tuple[Objective, ...] = ()
    origin: str = ''


RATINGS = ('ok', 'degraded', 'failed', 'inactive')


@dataclass(frozen=True)
class StatusCase:
    """A case of a status display: its rating while its condition holds; the last case has none."""

    rating: str
    test: Expr | None = None
    origin: str = ''


@dataclass(frozen=True)
class Status:
    """A status display: the first case whose condition holds, in written order."""

    cases: tuple[StatusCase, ...]
    origin: str = ''


@dataclass(frozen=True)
class Assert:
    """An assertion: over fixed inputs it is checked once; over state after every round, every
    moment and every contact between moments."""

    test: Expr
    origin: str = ''


# ---- members, templates and the program ----------------------------------------------------------


@dataclass(frozen=True)
class Member:
    """A member of a template: its id, its own initializers of the template's values (an input's
    value, a start value, a formula in place of the template's), and the row of each link."""

    id: str
    values: tuple[tuple[str, Expr | Formula | Distribution], ...] = ()
    links: tuple[tuple[str, int], ...] = ()

    def value(self, name):
        """The member's own initializer of a value, or None."""
        return next((init for found, init in self.values if found == name), None)

    def link(self, name):
        """The row that a link of the member names, or None."""
        return next((row for found, row in self.links if found == name), None)


@dataclass(frozen=True)
class Template:
    """A template: a shared schema and behaviour, and its members. An entity written on its own is a
    template of one member with the same name. `sees` are the observations that a human player of
    this actor is shown (it permits nothing)."""

    name: str
    values: tuple[Value, ...] = ()
    flows: tuple[Flow, ...] = ()
    events: tuple[Event, ...] = ()
    solvers: tuple[Solver, ...] = ()
    status: Status | None = None
    asserts: tuple[Assert, ...] = ()
    sees: tuple[Path, ...] = ()
    members: tuple[Member, ...] = ()
    origin: str = ''

    def part(self, name):
        """The value, flow, event or solver of this name, or None."""
        for group in (self.values, self.flows, self.events, self.solvers):
            for part in group:
                if part.name == name:
                    return part
        return None


@dataclass(frozen=True)
class Program:
    """A model as it runs: units, enums, templates with their members, the root's values, the
    statements of the setup scope (round zero, R-A2-05) and the root's assertions."""

    units: tuple[Unit, ...] = ()
    enums: tuple[Enum, ...] = ()
    templates: tuple[Template, ...] = ()
    root: tuple[Value, ...] = ()
    setup: tuple[Statement, ...] = ()
    asserts: tuple[Assert, ...] = ()

    @cached_property
    def _index(self):
        members = {}
        for template in self.templates:
            for row, member in enumerate(template.members):
                members[member.id] = (template, row)
        return (
            {unit.name: unit for unit in self.units},
            {enum.name: enum for enum in self.enums},
            {template.name: template for template in self.templates},
            members,
        )

    def unit(self, name):
        """The unit of a spelling; `''` is the plain number. KeyError for a spelling not in the
        table."""
        return PLAIN if name == '' else self._index[0][name]

    def enum(self, name):
        """The enum of a name, or KeyError."""
        return self._index[1][name]

    def template(self, name):
        """The template of a name, or KeyError."""
        return self._index[2][name]

    def member(self, id):
        """(template, row) of a member's id, or KeyError."""
        return self._index[3][id]

    def root_value(self, name):
        """The root's value of a name, or None."""
        return next((value for value in self.root if value.name == name), None)
