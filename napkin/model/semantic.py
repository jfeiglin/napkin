"""The declared model: a parsed model text with its names resolved and its types and units checked.

It holds what a run needs and what the report and the drawings read beside the program: the scenario
line, the entities and templates with their values and flows, their members (instances written by
hand and the rows of tables), the values and assertions of the top level, the records and the notes,
each with its texts and its evidence. Each declared part has a stable path, the path that the program
gives the part as its `origin` (`tank.water`, `Place.level`, `close` at the top level, the member
`sites.clinic`), so a report or a trace finds the label and the evidence of a part from the program.

- **Types and units.** A value's type is declared (`water: L`) or inferred from its initializer. A
  number's unit is checked by its dimension, from the units of the library and of the model: `+`,
  `-`, comparisons, `min`, `max`, `clip` and both sides of `if ... else` need one dimension, and `*`
  and `/` make the dimension of their result (D12). A bare number takes the declared unit where the
  spec says so: the whole initializer, a bare end of the declaration's range, its scale, the value
  arguments of a distribution that (or whose draw) is the whole initializer, a member's own value and
  a table cell; and a bare zero beside a value of known unit.
- **A quantity is its dimension and its scale**, never its spelling. A number written out is the
  exact decimal that its token writes (`nodes.Number.exact`, never read through a float) and a
  unit's scale is exact (`rational`), and every comparison of numbers that the front end makes
  reads them in the canonical unit of their dimension, from the compiler's own folding of constants
  (`folded`, `exact_value`: every operation folded exactly where its result is rational): an
  interval (`interval`: a range, a domain, the ends of a test, so `[6 h, 1 day]` runs from 6 h to
  24 h, `[0.1 day, 2.4 h]` holds one value and a reversed one is an error wherever it stands), a
  value in its range (`within`), the support of a drawn input, the rule of a distribution, a fixed
  key and a cited datum (`support.cited_data`). A membership with two ends (`x in [lo, hi]`) is the
  program's operation `within`, which checks its ends each time a run evaluates it, so an interval
  that only a run reverses fails there by name (`napkin.core.ops.REVERSED`); in a solver's
  constraint it is the chain of its two relations (`lowering`). A square root and a power take the
  dimension's powers times the exponent, each whole (`raised`: `sqrt(24 h * 1 day)` is a time, the
  square root of a ratio a plain number). The run converts each quantity the same way, once
  (`napkin.core.units.UnitRegistry.normalize`).
- **Unit runs.** After a number, a name is a unit while the library has a unit of that name and the
  run has not stopped; the first name that is no unit stops the run, and it and the names after it
  are values (`(2 h) * hour` against `2 h * hour`). The arithmetic is the same either way.
- **Members and links.** A template (`Place:`) is the schema that its members share; an entity
  written once (`tank:`) is the template of its one member, under its own name. A member is written
  by hand (`north: Utility`, with its own values and links under it, and its `title`) or is a row of
  a table. A link (`origin: Place`) names one member, fixed for the run: the member sets it, or the
  link's initializer names it (`origin = sites.junction`), so the declared model knows each target.
- **Titles, and no roles** (PLAN, changes 19 and 23 after G0). An entity, a template and a member
  written by hand may have a `title` ("DC Water"), a label that reports and playback give the
  member (`DeclaredModel.title`) and no hash covers. No part of a model has a `role`: who plays a
  part belongs to the scenario's wrapper (`roles.toml`), and the pictures take it from the `[role]`
  of `style.toml`; the parser refuses each by name (`role`), and says where it goes.
- **Cycles** are the members' (change 19). A value that its template reads through other members
  (`total = this.demand + sum(this.children.total)`) is read, while it is resolved, as its
  declaration types it (`provisional`); one with no declared type is refused, since its type is not
  known before its value. `Order` then follows each member's own connections, which the links fix
  when the model compiles (R-A1-30): a `where` that compares links keeps the members that it names.
  A cycle is refused with its chain, `a.total reads b.total reads a.total`.
- **Collections** (`<T>`) carry their member type and their key. In a `where` comparison, the left
  field comes from the member and the right expression from the enclosing scope. The operations
  include `by(field)` (the key) and `.at(x)` (one member, `x` in the
  key's unit). A key fixed when the model compiles selects its entry there: over the instances or a
  literal of members it is that member, read by its id (`chosen`), and `Order` reads the entry of
  each member's own collection (`Order.chosen`), so what reads the entry depends on it alone. A
  step from a collection is a projection, which only a reduction reads: `sum` and
  `min`/`max` of numbers, `count` of members or of yes/no values, `any` and `all` of yes/no values.
  A collection of flows takes a `where` too: in its test the bare names `source` and
  `sink` are the member's ends (`FlowEnd`), fixed for the flow's lifetime, which compare with `==`
  or `!=` to a stored number, by identity (`count(tank.water.outflow.flows.where(sink ==
  clinic.water))`); a flow's rates and settings are live, and no where tests them.
- **Flows and endpoints.** A directed flow ends at `SOURCE`, `SINK` or a stored number: of its own
  member, through links (`this.origin.power`), of a named member (`reservoir.water`) or of the top
  level. A stored number has an `outflow` and an `inflow` (`EndOf`): their `actual_rate` (the sum of
  the incident flows), `request`, `capacity` and `flows` (a collection of flows) are read, and their
  settings are written under the store (`outflow.capacity = 10 L/h`, `inflow.allocation =
  priority(this.main, this.backup)`; `DeclaredEndpoint`). A setting is resolved after its store, so
  it may read it. `priority(...)` ranks flows, or a projection of flows over a collection by its
  keys; that each is incident at the store is the program's rule (`check.priority_item`).
- **Routes and legs.** A reversible route (`flow link: west.water <-> east.water`, a
  `DeclaredRoute`) has one signed `actual_rate` and `request` and a `capacity` on the magnitude,
  and its legs `link.forward` and `link.backward` (`FlowOf.view`), which read the positive part of
  the rate and of the request in their direction, are members of the flows of its ends and are what
  a `priority(...)` names; a bare route is no claim there. Both ends of a route are stores. No mark
  makes a store receive-only: a tally is a store that nothing takes from, and a route takes from
  both of its ends, so a store at an end of a route is a stock, and only `SOURCE` and `SINK` (and
  what is no stored number) are refused there. A flow with legs (`DeclaredLegs`) reads its
  `served_fraction` and its legs, each a directed flow in its own unit at `owner.flow.leg`, named in
  the priority of its own endpoint; it has no rate and no request of its own.
- **The ends of a flow** (`f.source`, `f.sink`, also of a leg and of a leg of a route) read the
  store at that end, with its amount and the steps of a store. The ends are fixed for the run, so
  the read goes to the store's own path from the flow's member (`end`); an end at `SOURCE` or
  `SINK`, or of a member of an endpoint's `flows`, which may end anywhere, has no store to read.
- **Events** (`DeclaredEvent`) belong to an entity or a template. Inside an event a bare name is a
  parameter or a local of the occurrence (`Scope.event`; they stand in `syntax` under the event's
  path, `grinder.refill.amount`): a parameter is a value copy or an entity (D13), and a parameter
  holds no stock (`parameter_end`). A plain initializer of a local, and a plain property of a local
  flow, reads only what is above it (D14, `local_order`); a formula may read below. Stages (`after D:`,
  `after D when C:`, the wait `after D`) and gates (`until C`) are steps in order; a stage's
  statements assign, move, start and branch (`if`/`else`, `switch` over an enum with guarded
  cases, a case of which may do nothing but carry its text, its card). A trigger (`when C:`) has
  no occurrence: its condition reads the receiver, its captures what is above them, its starts and
  its reset the captures. The paths of an event's parts are the origins that the program gives them
  (`grinder.refill.step[0].do[1]`, `.when[0]`).
- **Writes.** A statement assigns a stored value, a local or a parameter's copy, a formula (with a
  formula) or a distribution (with another), of this, through a link or an entity parameter, of a
  live occurrence, or a setting of a flow or an endpoint. An input, a link, an event and the ends of
  a flow are fixed (`fixed_write`), also through `f.source` or `f.sink`, which read the store at that
  end; readonly forbids `=`, `+=` and `-=` (`readonly_write`); what the run computes, a rate, a
  served fraction and an occurrence's `started`, `done` and `active`, no statement assigns
  (`result_write`).
- **Occurrences** (`Occ`): `e.occurrences` is a collection keyed by start times, read with `count`,
  `any`, a projection and `.at(t)`; an occurrence reads its parameters, its locals and flows, and
  `started`, `done`, `active`. `since(e)` and `elapsed(x)` are `History` reads. A local of an event
  may hold a reference to an occurrence (`job = this.repair.occurrences.at(t)`), set when its own
  occurrence enters and assigned by no statement; `job.crew_size` reads that occurrence.
- **Lifetimes.** A value lives as long as its owner: the run's and an entity's for the run, an
  occurrence's parameters and locals while it runs (frozen once it finishes, D7). A formula that a
  stage installs may read only what lives at least as long as its place, or a copy (`lifetime`); a
  place lives as long as the owner of the target that it resolves to, whatever its spelling
  (`this.x`, a link, an event's parameter, a saved reference, a member of a collection), so an
  entity's formula that reads a parameter of the occurrence that installs it is refused.
- **Order of resolution.** A value is resolved once, after what it reads, on an explicit stack
  (`resolved`); the walks of the members' starting values run on one too (`walked`), so a chain of
  values of any length costs no depth of Python's calls (the audit's row 15).
- **Enums** (`EnumOf`) are their members in written order (E1 of the front end of S4): two
  declarations of `enum[OPEN, CLOSED]` are one type, and the program names it `enum[OPEN,
  CLOSED]`. A bare member takes its enum from its place: a declared type, the other side of a
  comparison or a conditional, an assignment's target, a parameter, a switch's selector, a column.
  A categorical takes the enum of its place, or the enum of its outcomes.
- **Draws.** `d.draw()` of a distribution written in place or held by a value stands where a value
  is captured once (an initializer, a stage, a capture, an argument); a formula and a condition that
  is read again (a gate, a trigger, a reset, an assertion) makes none (`formula_draws`). A
  distribution's parameters are numbers written in place, which hold its family's rule in one unit
  (`_broken`: `uniform(min, max)` needs min below max, and `uniform(5 h, 2 h)` is refused).
- **No player machinery** (item 15 of the plan's changes after G0): `actor.choose(d)` and `sees`
  are refused by name (`choose`, `sees`). A decision is a value stored in a field that a branch
  reads, and a caller that wants another value pauses before the branch and edits the field.
- **Expressions** become a small typed form (`Const`, `Read`, `Apply`, `Retain`, `Distribution`,
  `Drawn`, `History`, `Reduced`) that the lowering writes as a program. A `Read` knows
  whether what it reads is fixed for the run (inputs, links and the members of fixed collections),
  which `where` and `assert` need, whether it ends at a stored number, which a flow, an endpoint and a
  move need, and the declared value that it ends at, which an assignment needs.
- **Solvers** (`DeclaredSolver`) belong to an entity or a template. An input (`DeclaredBinding`)
  names a value, a flow, a member or a collection by its path in the owner's scope, and the solver
  reads it under its own name; inside the solver a bare name is an input or an unknown
  (`Scope.solver`; they stand in `syntax` under the solver's path, `clinic.staffing.care`).
  `solve_for` names stored numbers, the rates of flows and routes and served fractions, also
  projected over a collection (`places.supply.actual_rate`), and declares new unknowns, each a
  number with its domain, its preferred value and its scale; a yes/no unknown is a yes-or-no
  problem, which the language leaves out (`nonlinear`). A caller reads a solver's unknowns
  (`this.staffing.care`, `SolverOf`) and assigns none (`result_write`). What a constraint and an
  objective may say about what the solver determines (affine relations, the participants of the
  decision, one solver for each connected set) is checked on the program (`solvers.py`).
- **Packages.** A package's files are declared as one model (`Files`: each file's lines follow those
  of the file before it, so a problem is placed at its file). A `change` (`register_changes`) names
  an entity, a template or a member written by hand of an earlier file and gives a value or a link
  that it declares a new initializer, of its kind and type, as a member's own value is (`own`): an
  entity's or a template's declaration takes it, and a member's own line gives way to it; two
  changes of one value are an error (R-A5-03), and its text, `title` and records replace those of
  what it names; it sets no role.
- **The setup scope's initializers** (`wired`): `clinic.delivery.request = 3 L/h` at the top level is
  the initializer under its declaration, and the tree is read with it there: a value or a setting
  of an entity written once, of a leg or of an endpoint, or a member's own value. A path has one
  initializer (`property`, naming both lines); a readonly value takes it, since readonly bars an
  assignment and not an initializer.
- **Options and runs** (`DeclaredOption`, `DeclaredRun`): a setting names an input by its full path
  (R-A5-04) and gives it a constant of its type, in the input's unit and range (D2, `constant`); a
  number or a yes/no that an option or a change sets cites its record (R-A5-05, `recorded`). An
  option's name is its own across the groups, and a run takes known options, at most one of each
  group, no two of which set one input (`choice_problem`). `napkin/model/runs.py` makes a run's
  configuration of them.
- **Status displays** (`DeclaredStatus`): the `status` cases of an entity or a template, in written
  order, are its display at `owner.status`; each case (`owner.status.case[k]`) has its rating, its
  condition (a yes/no that reads what its member reads, and makes no draw), its text and its evidence.
  The first case whose condition holds gives both the rating and the text, and the last case, and
  only it, has no condition: it is the fallback. A display names `status` of its owner, so the owner
  declares no value of that name.
"""

from __future__ import annotations

import difflib
import math
import re
from dataclasses import dataclass, field, replace
from decimal import Decimal
from fractions import Fraction
from functools import cached_property

from ..core.comparisons import DEFAULT_FACTOR, against, collapsed_interval, numeric_gap_band
from ..core.expr import DEEPEST
from ..core.literals import Literals
from ..core.units import authored_decimal, dimension_power, rational, scale_of
from ..program.refs import numeric_support
from .language import nodes as n
from .language import tables
from .language.format import expression as written_as
from .language.parse import parse_expression
from .language.problems import LanguageError, Problem, SyntaxProblem

# ---- units ------------------------------------------------------------------------------------------


class Units:
    """The units of a model: a spelling and its dimension (base dimensions with their powers) or a
    pair of the dimension and its scale, as `napkin.program.build.Builder` takes them. A spelling with
    `*` and `/` is composed from the left (D12). Each scale is exact (`core.units.scale_of`: a float
    written as a decimal is that decimal, so 0.01 is 1/100; one that a program wrote out from a ratio
    is the ratio, so 0.041666666666666664 is 1/24)."""

    def __init__(self, table):
        self.table = dict(table)
        self.base = {}
        for name, spec in self.table.items():
            dimension, scale = spec if isinstance(spec, tuple) else (spec, 1)
            powers = ((k, dimension_power(v)) for k, v in dimension.items() if v)
            self.base[name] = (tuple(sorted(powers)), scale_of(scale))

    def has(self, name):
        return name in self.base

    def of(self, spelling):
        """(dimension, scale) of a spelling, or None when a name of it is no unit."""
        dimension, scale = {}, Fraction(1)
        for sign, name in factors(spelling):
            if name == '1':
                continue
            if name not in self.base:
                return None
            found, size = self.base[name]
            for key, power in found:
                dimension[key] = dimension.get(key, 0) + sign * power
            scale = scale * size if sign > 0 else scale / size
        return tuple(sorted((k, v) for k, v in dimension.items() if v)), scale


def factors(spelling):
    """The factors of a spelling, [(+1 or -1, name)] from the left: `L/h` is [(1, 'L'), (-1, 'h')]."""
    out, sign, name = [], 1, ''
    for char in spelling:
        if char in '*/':
            out.append((sign, name))
            sign, name = (1 if char == '*' else -1), ''
        else:
            name += char
    if name:
        out.append((sign, name))
    return out


def spelling_of(found):
    """The spelling of factors [(sign, name)]: the names over the line first, in their order, and the
    same name over and under the line cancels (`tunings/tuner/year * tuner` is `tunings/year`)."""
    powers = {}
    for sign, name in found:
        if name != '1':
            powers[name] = powers.get(name, 0) + sign
    above = [name for name, power in powers.items() for _ in range(max(power, 0))]
    below = [name for name, power in powers.items() for _ in range(max(-power, 0))]
    if not above and not below:
        return ''
    return '/'.join(['*'.join(above) or '1', *below])


def flat_unit(unit):
    """The factors of a unit of a type (`nodes.UnitOp` or a name), from the left with no brackets:
    `tunings / (tuner * year)` is tunings/tuner/year."""

    def walk(item, sign):
        if isinstance(item, str):
            return [(sign, item)]
        return walk(item.left, sign) + walk(item.right, sign if item.op == '*' else -sign)

    return walk(unit, 1)


# ---- types ------------------------------------------------------------------------------------------


@dataclass(frozen=True)
class Num:
    """A number in a unit (its spelling, '' for a plain number) and the unit's dimension."""

    unit: str = ''
    dimension: tuple = ()

    def __str__(self):
        return self.unit or 'a plain number'


@dataclass(frozen=True)
class Word:
    """`bool` or `text`."""

    word: str

    def __str__(self):
        return self.word


BOOL, TEXT = Word('bool'), Word('text')
PLAIN = Num()


@dataclass(frozen=True)
class EnumOf:
    """Named states: the members of an enum in written order. An enum is its members, so two
    declarations that write `enum[OPEN, CLOSED]` have one type, and a value of it can be stored in a
    local of that type; the program names the enum by its spelling (`enum[OPEN, CLOSED]`)."""

    members: tuple[str, ...]

    def __str__(self):
        return f'enum[{", ".join(self.members)}]'


@dataclass(frozen=True)
class Dist:
    """A distribution of numbers in a unit, or of the members of an enum (a categorical)."""

    of: Num | EnumOf

    def __str__(self):
        return f'distribution({self.of})'


@dataclass(frozen=True)
class EventOf:
    """A bound event (`grinder.refill`), which is no value: its `occurrences` are read, a stage or
    the setup starts it, and `since` reads its latest start. `event` is the path of its declaration
    (`grinder.refill`, `Utility.restore`)."""

    event: str

    def __str__(self):
        return f'the event {self.event}'


@dataclass(frozen=True)
class Occ:
    """An occurrence of an event: its parameters, its locals and its flows by their names, and its
    built-in `started` (its start time), `done` (normal completion) and `active`. A collection of
    occurrences is keyed by their start times."""

    event: str

    def __str__(self):
        return f'an occurrence of {self.event}'


@dataclass(frozen=True)
class Ent:
    """A member of a template: `this`, a link, a named member, a row or a keyed read. An entity
    written once is the template of its one member, under its own name."""

    template: str

    def __str__(self):
        return f'a member of {self.template}'


@dataclass(frozen=True)
class Many:
    """A collection of members (`of` is an `Ent`), or a projection of a field over one (`of` is the
    field's type), with the type of its keys: the creation number (a plain number) or the field that
    a `by` names."""

    of: object
    key: Num = PLAIN

    def __str__(self):
        if isinstance(self.of, Ent):
            return f'a collection of {self.of.template}'
        if isinstance(self.of, (FlowOf, Occ)):
            return f'a collection of {self.of}'
        return f'a projection of {self.of}'


@dataclass(frozen=True)
class FlowOf:
    """A directed flow, which is no value: its rates are read (`actual_rate`, `request`, `capacity`)
    and its ends (`source`, `sink`). `flow` is the path of its declaration: a flow, a leg of a flow
    with legs (`site.restore.labor`) or a leg of a route (`channel.link.forward`, a `view`), or ''
    for a member of an endpoint's `flows`, which may be any of the flows incident there. A leg of a
    route reads the positive part of the route's rate and request in its direction, and has no
    capacity of its own."""

    rate: Num
    flow: str = field(default='', compare=False)
    view: bool = field(default=False, compare=False)

    def __str__(self):
        return f'a flow in {self.rate}'


@dataclass(frozen=True)
class RouteOf:
    """A reversible route, which is no value: its signed `actual_rate` and `request` (positive from
    its first end to its second), its `capacity` on the magnitude, and its two legs `forward` and
    `backward`, which are members of the collections of flows of its ends."""

    rate: Num
    flow: str = ''

    def __str__(self):
        return f'a reversible route in {self.rate}'


@dataclass(frozen=True)
class LegsOf:
    """A flow with several legs (`flow` is the path of its declaration), which is no value and has
    no rate of its own: its `served_fraction` (a plain number from 0 to 1) and each leg by its name
    (`restore.labor`, a directed flow in its own unit) are read."""

    flow: str

    def __str__(self):
        return 'a flow with legs'


@dataclass(frozen=True)
class EndOf:
    """The outflow or the inflow of a store, which is no value: its total rate (`actual_rate`), its
    settings (`request`, `capacity`) and its incident flows (`flows`) are read. `rate` is the store's
    unit per hour."""

    rate: Num

    def __str__(self):
        return f'an endpoint in {self.rate}'


@dataclass(frozen=True)
class FlowEnd:
    """An end of the member under test of a `where` over flows (`source`, `sink`): the
    store at that end, or SOURCE or SINK, fixed for the flow's lifetime. It is no value: the test
    compares it with `==` or `!=` to a stored number, or to the member's other end, and the program
    compares stores by identity there. `rate` is the unit of the flows' rates."""

    rate: Num

    def __str__(self):
        return 'an end of a flow'


@dataclass(frozen=True)
class SolverOf:
    """A declared solver (`solver` is the path of its declaration, `provider.dispatch`), which is no
    value: a caller reads its published results, the new unknowns that it declares under
    `solve_for` (`clinic.staffing.care`)."""

    solver: str

    def __str__(self):
        return f'the solver {self.solver}'


def compatible(a, b):
    """Whether a value of type `a` stands where `b` is expected: numbers of one dimension, whatever
    the units that spell them, and distributions and projections of such numbers; any other type is
    itself (a collection of members is one of their template, whatever its key)."""
    if isinstance(a, Num) and isinstance(b, Num):
        return a.dimension == b.dimension
    if isinstance(a, Dist) and isinstance(b, Dist):
        return compatible(a.of, b.of)
    if isinstance(a, Many) and isinstance(b, Many):
        return compatible(a.of, b.of)
    return a == b


# ---- the typed form of an expression -----------------------------------------------------------------


@dataclass(frozen=True)
class Const:
    """A number (in the unit of its type), a yes/no or a text. `exact` is the exact decimal of a
    number written out (`34.000000000000000001`, which no float holds), in the unit of its type, for
    the front end's exact comparisons (`exact_value`); the program and the run take `value`."""

    value: object
    type: object
    exact: object = field(default=None, compare=False, repr=False)


@dataclass(frozen=True)
class Read:
    """A read from a start through its steps (a value, a link, a flow and its rate). The starts are
    `('this',)`, `('named', id)` (an entity, an instance or a row), `('root',)`, `('time',)`,
    `('item',)` (the member of a `where`), `('instances', template)`, `('literal', reads)`, `('where',
    source, test)`, `('by', source, field)` and `('lookup', source, key)`. `fixed` says that what it
    reads is fixed for the run."""

    start: tuple
    steps: tuple
    type: object
    fixed: bool = False
    # The path of the formula that the read ends at, when the way to it is fixed: an assertion that
    # reads it is over inputs when the formula is.
    formula: str = field(default='', compare=False)
    # Whether the read ends at a stored number, which can be an end of a flow and has an outflow and
    # an inflow.
    stored: bool = field(default=False, compare=False)
    # The path of the declared value, parameter or local that the read ends at (an assignment asks
    # it whether it is writable), or ''.
    part: str = field(default='', compare=False)


@dataclass(frozen=True)
class Apply:
    """An operation: `add`, `sub`, `mul`, `div`, `pow`, `neg`, `not`, `and`, `or`, `if`, `compare`
    (its operators in `detail`) or `call` (the function in `detail`)."""

    op: str
    args: tuple
    type: object
    detail: object = None


@dataclass(frozen=True)
class Reduced:
    """`sum`, `count`, `any`, `all`, `min` or `max` of a collection or of a projection (`source`)."""

    op: str
    source: Read
    type: object


@dataclass(frozen=True)
class Retain:
    """`formula(body)`."""

    body: object
    type: object


@dataclass(frozen=True)
class Distribution:
    """A distribution of a family, its parameters as numbers in one unit; a categorical has a weight
    for each of its `outcomes`, members of the enum of its type."""

    family: str
    params: tuple
    type: Dist
    outcomes: tuple = ()


@dataclass(frozen=True)
class Drawn:
    """`d.draw()` of a distribution written in place, or of the one that a value holds (a `Read`)."""

    source: Distribution | Read
    type: object


@dataclass(frozen=True)
class History:
    """`since(e)` (the time since the latest start of an event) or `elapsed(x)` (since the value of
    `x` last changed at a commit)."""

    op: str
    source: Read
    type: object


def reads_of(expression):
    """The reads of a typed expression, outside the starts of its keyed reads."""
    if isinstance(expression, Read):
        yield expression
    elif isinstance(expression, (Reduced, History)):
        yield expression.source
    elif isinstance(expression, Apply):
        for arg in expression.args:
            yield from reads_of(arg)
    elif isinstance(expression, Retain):
        yield from reads_of(expression.body)
    elif isinstance(expression, Drawn) and isinstance(expression.source, Read):
        yield expression.source


def _local_reads(expression):
    """The reads of an occurrence's own bare names in a typed expression, at any depth: its reads,
    and those of the tests, the keys and the items of the collections that it reads."""
    for read in reads_of(expression):
        yield from _local_starts(read)


def _local_starts(read):
    kind = read.start[0]
    if kind == 'local':
        yield read
    elif kind in ('where', 'lookup'):
        yield from _local_starts(read.start[1])
        for each in reads_of(read.start[2]):
            yield from _local_starts(each)
    elif kind == 'by':
        yield from _local_starts(read.start[1])
    elif kind == 'literal':
        for each in read.start[1]:
            yield from _local_starts(each)


def draws_of(expression):
    """The draws of a typed expression, which a formula and a condition that is read again may not
    make."""
    if isinstance(expression, Drawn):
        yield expression
    elif isinstance(expression, Apply):
        for arg in expression.args:
            yield from draws_of(arg)
    elif isinstance(expression, Retain):
        yield from draws_of(expression.body)


def fixed(expression):
    """Whether a typed expression reads only what is fixed for the run."""
    if isinstance(expression, Const):
        return True
    if isinstance(expression, Read):
        return expression.fixed
    if isinstance(expression, Reduced):
        return expression.source.fixed
    if isinstance(expression, Apply):
        return all(fixed(arg) for arg in expression.args)
    return False


# ---- the declared parts -------------------------------------------------------------------------------

INPUT, STATE, FORMULA, DISTRIBUTION = 'input', 'state', 'formula', 'distribution'
LINK, COLLECTION = 'link', 'collection'
UNKNOWN = 'unknown'  # a new unknown of a solver: a result that the solver publishes

# The refusals of the player machinery, which left the language (item 15 of the plan's changes after
# G0): each names what it refuses and says what to write instead.
CHOOSE = (
    'actor.choose(d) is not in the language: store the value in a field and branch on it '
    '(order = forecast.draw(), then switch order:); a wrapper can pause before the branch and edit the field'
)
SEES = (
    'sees is not in the language: store the value in a field and branch on it; a wrapper can pause '
    'before the branch, show any value and edit the field'
)


@dataclass(frozen=True)
class DeclaredEndpoint:
    """The settings of a store's `outflow` or `inflow`, written under the store
    (`outflow.capacity = 10 L/h`): a hard `capacity` and a soft `request` on the total rate in that
    direction (each captured once, or a `Retain`), and the `allocation` among the incident flows,
    `('proportional',)` (the default) or `('priority', items)` with the `Read` of each item, a flow
    or a projection of flows (`Customer.instances.by(rank).delivery`), first to last. Its path is
    the store's and the side (`reservoir.water.outflow`); its line is that of its first setting."""

    path: str
    capacity: object = None
    request: object = None
    allocation: tuple = ('proportional',)
    line: int = 0


@dataclass(frozen=True)
class DeclaredValue:
    """A value of an entity, a template or the top level: its kind (`input`, `state`, `formula`,
    `distribution`, `link`, `collection`, or `unknown` for a new unknown of a solver), its type, its
    initializer (None for a value of a template that each member gives, or a link that each member
    sets; of an unknown, its preferred value), its range (either side None; of an unknown, its
    domain), its scale, its texts and its evidence (the records that it cites and those written under
    it). A stored number has the settings of its `outflow` and its `inflow` (`DeclaredEndpoint`), or
    None."""

    path: str
    name: str
    kind: str
    type: object
    init: object
    lower: object = None
    upper: object = None
    scale: object = None
    readonly: bool = False
    text: str | None = None
    evidence: tuple = ()
    line: int = 0
    outflow: DeclaredEndpoint | None = None
    inflow: DeclaredEndpoint | None = None


def fixed_kind(value):
    """Whether a declared value is fixed for the run: an input, a link, or a collection whose members
    are fixed."""
    if value.kind in (INPUT, LINK):
        return True
    return value.kind == COLLECTION and value.init is not None and value.init.fixed


def _stored(value):
    """Whether a declared value is a stored number: an end of a flow, with an outflow and an inflow."""
    return value.kind == STATE and isinstance(value.type, Num)


@dataclass(frozen=True)
class DeclaredFlow:
    """A directed flow, or a leg of a flow with legs: its ends (`'SOURCE'`, `'SINK'` or the `Read` of
    a store: of its own member, through a link, of a named member or of the top level), the type of
    its rates, its request and its capacity (captured once, or a `Retain`)."""

    path: str
    name: str
    source: object
    sink: object
    rate: Num
    request: object = None
    capacity: object = None
    text: str | None = None
    evidence: tuple = ()
    line: int = 0


@dataclass(frozen=True)
class DeclaredRoute(DeclaredFlow):
    """A reversible route (`flow link: west.water <-> east.water`): one signed rate, positive from
    `source` to `sink`, a signed request and a capacity on the magnitude. Both ends are stores, which
    supply and receive through it: `SOURCE` and `SINK` stand at the ends of a directed flow only."""


@dataclass(frozen=True)
class DeclaredLegs:
    """A flow with several legs, served at one fraction: each leg is a `DeclaredFlow` with its own
    ends, unit, request and capacity, at the path `owner.flow.leg` (`site.restore.labor`). The
    parent has no request and no rate of its own."""

    path: str
    name: str
    legs: tuple[DeclaredFlow, ...]
    text: str | None = None
    evidence: tuple = ()
    line: int = 0


@dataclass(frozen=True)
class DeclaredAssert:
    """An assertion: its test, its message (`text`) and its evidence. Its path is `assert[k]` of its
    owner. `fixed` says that it reads only what is fixed for the run, so it is checked once, after the
    effective inputs are assembled; an assertion over state is checked after every round."""

    path: str
    test: object
    text: str | None = None
    evidence: tuple = ()
    line: int = 0
    fixed: bool = True


# ---- solvers ------------------------------------------------------------------------------------


@dataclass(frozen=True)
class DeclaredBinding:
    """An input of a solver (`places = Place.instances`): a name for the `Read` of a value, a flow,
    a member or a collection in the scope of the solver's owner, which follows its source. Its path
    is the solver's and its name (`provider.dispatch.places`)."""

    path: str
    name: str
    read: Read
    line: int = 0


@dataclass(frozen=True)
class DeclaredRelation:
    """A constraint of a solver (its `test`, a yes/no) or an objective (`sense` is `minimize` or
    `maximize`, and `test` the number that it ranks), at `solver.constraint[k]` or
    `solver.objective[k]`."""

    path: str
    test: object
    sense: str = ''
    line: int = 0


@dataclass(frozen=True)
class DeclaredSolver:
    """A solver of an entity or a template (`provider.dispatch`): its inputs, the existing fields
    that it determines (`solve_for`, each the `Read` of a stored number, of the rate of a flow or a
    route, of a served fraction, or a projection of one of these over a collection), its new unknowns
    (`DeclaredValue`s of kind `unknown`), its constraints and its objectives in written order. Inside
    it a bare name is an input or an unknown (`Scope.solver`). What it may write in its constraints
    and objectives is the program's affair (`napkin/model/solvers.py`)."""

    path: str
    name: str
    inputs: tuple[DeclaredBinding, ...] = ()
    solve_for: tuple[Read, ...] = ()
    unknowns: tuple[DeclaredValue, ...] = ()
    constraints: tuple[DeclaredRelation, ...] = ()
    objective: tuple[DeclaredRelation, ...] = ()
    text: str | None = None
    evidence: tuple = ()
    line: int = 0


def solver_parts(solver):
    """Each part of a solver that has a path: its inputs, its unknowns, its constraints and its
    objectives."""
    yield from solver.inputs
    yield from solver.unknowns
    yield from solver.constraints
    yield from solver.objective


# ---- events: their statements, steps and triggers ------------------------------------------------


@dataclass(frozen=True)
class DeclaredAssign:
    """`target = value`, `target += value` or `target -= value` in a stage: the target's `Read`
    (a value of this, through a link or an entity parameter, of a live occurrence, a local or a
    parameter, a setting of a flow or of an endpoint) and the typed value (a `Retain` for a formula,
    a `Distribution` for a distribution, the allocation `('priority', items)`)."""

    path: str
    target: Read
    op: str
    value: object
    line: int = 0


@dataclass(frozen=True)
class DeclaredMove:
    """`move amount from source to destination`: one checked debit and credit of two stores."""

    path: str
    amount: object
    source: Read
    destination: Read
    line: int = 0


@dataclass(frozen=True)
class DeclaredStart:
    """`event.start(args)`: of one event (`EventOf`), or of one on each member of a collection, with
    the arguments that the caller evaluates once, left to right, each of its parameter's type."""

    path: str
    event: Read
    args: tuple = ()
    line: int = 0


@dataclass(frozen=True)
class DeclaredIf:
    """`if test:` with its actions, and `else:` with its own (D11)."""

    path: str
    test: object
    then: tuple
    orelse: tuple = ()
    line: int = 0


@dataclass(frozen=True)
class DeclaredCase:
    """A case of a switch: a member of the selector's enum, its guard (read once, before the
    selector) and its actions; its path is the switch's and the member (`...do[0].FIXED`)."""

    path: str
    member: str
    body: tuple
    guard: object = None
    text: str | None = None
    evidence: tuple = ()
    line: int = 0


@dataclass(frozen=True)
class DeclaredSwitch:
    """`switch selector:` over an enum (a value or a draw), its cases and `else`."""

    path: str
    selector: object
    cases: tuple[DeclaredCase, ...]
    orelse: tuple = ()
    line: int = 0


@dataclass(frozen=True)
class DeclaredStage:
    """`after delay [when guard]:` and its actions; `after delay` alone (`wait`) waits. The delay is
    captured when the step is reached, the guard read once when the stage comes due."""

    path: str
    delay: object
    body: tuple = ()
    guard: object = None
    wait: bool = False
    text: str | None = None
    evidence: tuple = ()
    line: int = 0


@dataclass(frozen=True)
class DeclaredGate:
    """`until test`: the occurrence waits until the live condition holds."""

    path: str
    test: object
    line: int = 0


@dataclass(frozen=True)
class DeclaredTrigger:
    """`when test:` of an event: its condition on the receiver, its captures in written order (each
    a `DeclaredValue` at `trigger.name`), its starts of its own event, and its reset, `('when',
    test)` or `('after', duration)`, or None (it rearms when its condition becomes false)."""

    path: str
    test: object
    captures: tuple = ()
    starts: tuple[DeclaredStart, ...] = ()
    reset: tuple | None = None
    text: str | None = None
    evidence: tuple = ()
    line: int = 0


@dataclass(frozen=True)
class DeclaredEvent:
    """An event of an entity or a template (`grinder.refill`): its parameters (`DeclaredValue`s
    with no initializer, a value copy or an entity), its locals (values and flows, whose plain
    initializers run in written order, D14), its steps (stages and gates, in order) and its
    triggers. Its parts have the paths that the program gives them as their origins
    (`grinder.refill.amount`, `.step[0]`, `.step[0].do[1]`, `.when[0]`)."""

    path: str
    name: str
    params: tuple = ()
    locals: tuple = ()
    steps: tuple = ()
    triggers: tuple = ()
    text: str | None = None
    evidence: tuple = ()
    line: int = 0


def statements_of(body):
    """The statements of a body and of the branches inside it, outermost first."""
    for statement in body:
        yield statement
        if isinstance(statement, DeclaredIf):
            yield from statements_of((*statement.then, *statement.orelse))
        elif isinstance(statement, DeclaredSwitch):
            for case in statement.cases:
                yield case
                yield from statements_of(case.body)
            yield from statements_of(statement.orelse)


def event_parts(event):
    """Each part of an event that has a path: its parameters, locals (and the legs of a local flow
    with legs), steps, statements, triggers, captures and starts."""
    yield from event.params
    for local in event.locals:
        yield local
        yield from local.legs if isinstance(local, DeclaredLegs) else ()
    for step in event.steps:
        yield step
        if isinstance(step, DeclaredStage):
            yield from statements_of(step.body)
    for trigger in event.triggers:
        yield trigger
        yield from trigger.captures
        yield from trigger.starts


@dataclass(frozen=True)
class DeclaredEntity:
    """An entity written once: a template of one member, with its parts in written order and its
    status display, or None."""

    path: str
    parts: tuple = ()
    text: str | None = None
    title: str | None = None
    evidence: tuple = ()
    line: int = 0
    status: DeclaredStatus | None = None


@dataclass(frozen=True)
class DeclaredTemplate(DeclaredEntity):
    """A template: the schema and the behaviour that its members share, with its parts in written
    order."""


@dataclass(frozen=True)
class Given:
    """A member's own initializer of a value of its template (a typed expression, a `Retain` in
    place of the template's formula, a `Distribution`), or for a link the id of the member that it
    names."""

    name: str
    init: object
    evidence: tuple = ()
    line: int = 0


@dataclass(frozen=True)
class DeclaredMember:
    """A member of a template: written by hand (`north: Utility`), or a row of the table `table`. Its
    path is its id (`north`, `sites.clinic`, or `readings[0]` for a row of a table without ids). Its
    line is in `file`: the model's ('') or the table's. A member written by hand may have its title
    (`title "DC Water"`), the name that the reports and the playback give it."""

    path: str
    template: str
    values: tuple[Given, ...] = ()
    links: tuple[Given, ...] = ()
    table: str | None = None
    text: str | None = None
    evidence: tuple = ()
    line: int = 0
    file: str = ''
    title: str | None = None


@dataclass(frozen=True)
class DeclaredTable:
    """A table: its name, its template, the file that the model names and the one read (`origin`),
    its columns (`tables.Column`, with their units and records) and the ids of its members in file
    order."""

    path: str
    template: str
    file: str
    origin: str
    columns: tuple = ()
    members: tuple[str, ...] = ()
    text: str | None = None
    evidence: tuple = ()
    line: int = 0


@dataclass(frozen=True)
class DeclaredStatusCase:
    """A case of a status display: its rating, its condition (None for the last case, the fallback),
    its text and its evidence. Its path is `owner.status.case[k]`, the origin that the program gives
    it."""

    path: str
    rating: str
    test: object = None
    text: str | None = None
    evidence: tuple = ()
    line: int = 0


@dataclass(frozen=True)
class DeclaredStatus:
    """The status display of an entity or a template: its cases in written order. Its path is
    `owner.status`."""

    path: str
    cases: tuple[DeclaredStatusCase, ...]
    line: int = 0


@dataclass(frozen=True)
class DeclaredSetting:
    """`path = value` of an option: the input that it sets, of one member (`member` is its id, `''`
    for the top level) or of every member of a template (`instances`), and its value, a constant of
    the input's type (`Const`, or a `Distribution` for a distribution-valued input)."""

    path: str
    name: str
    value: object
    member: str | None = None
    instances: str | None = None
    evidence: tuple = ()
    line: int = 0


@dataclass(frozen=True)
class DeclaredOption:
    """An option of a group: its name, its group, its settings, its text (its line in a menu) and its
    evidence."""

    name: str
    group: str
    settings: tuple[DeclaredSetting, ...] = ()
    text: str | None = None
    evidence: tuple = ()
    line: int = 0


@dataclass(frozen=True)
class DeclaredRun:
    """A named run: its options, at most one of each group, and its text."""

    name: str
    options: tuple[str, ...]
    text: str | None = None
    evidence: tuple = ()
    line: int = 0


@dataclass(frozen=True)
class Scenario:
    """The scenario line: its role (`main` or `variant`), its title and texts, and its times in hours."""

    role: str
    title: str
    summary: str | None = None
    scope: str | None = None
    library: str | None = None
    horizon: object = None
    resolution: object = None
    line: int = 0


@dataclass(frozen=True)
class DeclaredModel:
    """A declared model: its scenario line; its entities and templates, its top-level values, its
    members (instances by hand and table rows, in written order) and its top-level assertions; its
    tables, records and notes; its options, in the order of their groups, and its named runs; its
    units and its tree. `files` names the files of a model read
    from several (`place`)."""

    scenario: Scenario | None
    entities: tuple[DeclaredEntity, ...]
    root: tuple[DeclaredValue, ...]
    records: tuple = ()
    notes: tuple = ()
    units: Units = None
    tree: n.File = field(default=None, repr=False)
    members: tuple[DeclaredMember, ...] = ()
    tables: tuple[DeclaredTable, ...] = ()
    asserts: tuple[DeclaredAssert, ...] = ()
    setup: tuple[DeclaredStart, ...] = ()
    options: tuple[DeclaredOption, ...] = ()
    runs: tuple[DeclaredRun, ...] = ()
    files: tuple[tuple[str, int], ...] = ()

    def place(self, line):
        """(the file, the line in it) of a line of the model: the lines of a model read from several
        files follow one another, each file's after the file before it (`Files`)."""
        return Files(self.files).place(line)

    def option(self, name):
        """The option of a name, or None."""
        return next((item for item in self.options if item.name == name), None)

    def run(self, name):
        """The named run of a name, or None."""
        return next((item for item in self.runs if item.name == name), None)

    def evidence_scopes(self):
        """Each group of citations attached to specific members or option settings of a field."""
        for member in self.members:
            if member.table is None:
                for given in member.values:
                    if given.evidence:
                        yield f'{member.template}.{given.name}', (member.path,), '', given.evidence
        for table in self.tables:
            for column in table.columns:
                if column.cites:
                    yield (
                        f'{table.template}.{column.name}',
                        table.members,
                        '',
                        tuple(n.Cite(name) for name in column.cites),
                    )
        for option in self.options:
            for setting in option.settings:
                if not setting.evidence:
                    continue
                if setting.instances:
                    origin, members = f'{setting.instances}.{setting.name}', None
                elif setting.member:
                    owner = self.part(setting.member)
                    template = owner.template if isinstance(owner, DeclaredMember) else setting.member
                    origin, members = f'{template}.{setting.name}', (setting.member,)
                else:
                    origin, members = setting.name, ('',)
                yield origin, members, option.name, setting.evidence

    @cached_property
    def _evidence_index(self):
        from ..program.artifact import index_evidence

        return index_evidence(self.evidence_scopes())

    def evidence(self, origin, member='', options=()):
        """The source citations of a field under the same scopes a compiled report uses."""
        from ..program.artifact import scoped_items

        base = getattr(self.part(origin), 'evidence', ())
        return (*base, *scoped_items(self._evidence_index, origin, member, options))

    def title(self, member):
        """The title of a member (`title "DC Water"`): of an entity written once or of a member
        written by hand, as its line or a change gives it; None for a row of a table or a member with
        none. The title is a label: no hash covers it (`identity.model_hash`)."""
        found = self.part(member)
        if isinstance(found, DeclaredMember) or (
            isinstance(found, DeclaredEntity) and not isinstance(found, DeclaredTemplate)
        ):
            return found.title
        return None

    def part(self, path):
        """The declared part of a path (an entity, a template, a value, the settings of an
        endpoint, a flow, a leg, an event or a solver and each part of it, a status display and each
        of its cases, an assertion, a member, a table or a start of the setup), or None."""
        return self._paths.get(path)

    @cached_property
    def _paths(self):
        """Each declared part by its path, made once, so that a large model places each of many
        diagnostics at once: the first of two parts of one path wins, entities before members."""
        found = {}
        for entity in self.entities:
            found.setdefault(entity.path, entity)
            for part in entity.parts:
                found.setdefault(part.path, part)
                for leg in part.legs if isinstance(part, DeclaredLegs) else ():
                    found.setdefault(leg.path, leg)
                for inner in event_parts(part) if isinstance(part, DeclaredEvent) else ():
                    found.setdefault(inner.path, inner)
                for inner in solver_parts(part) if isinstance(part, DeclaredSolver) else ():
                    found.setdefault(inner.path, inner)
            if entity.status is not None:
                for part in (entity.status, *entity.status.cases):
                    found.setdefault(part.path, part)
        for part in (*self.members, *self.tables, *self.root, *self.asserts, *self.setup):
            found.setdefault(part.path, part)
        for value in [part for part in found.values() if isinstance(part, DeclaredValue)]:
            for side in (value.outflow, value.inflow):
                if side is not None:
                    found.setdefault(side.path, side)
        return found


@dataclass(frozen=True)
class Files:
    """The files of a model read from several, each `(name, offset)` in the order in which they are
    read: the lines of a file are numbered after those of the file before it (its line k is the
    model's line offset + k), so each line of the model names one line of one file. A model of one
    text has no files: its lines are its own."""

    files: tuple[tuple[str, int], ...] = ()

    def place(self, line):
        """(the file, the line in it) of a line of the model; ('', line) for a model of one text."""
        found = ('', 0)
        for file, offset in self.files:
            if offset >= line:
                break
            found = (file, offset)
        return found[0], line - found[1]


# ---- resolution ---------------------------------------------------------------------------------------


# How many values one inside the other a resolution resolves inside itself (`Resolver.value`); a
# value deeper than that is resolved first on the explicit stack (`Resolver.resolved`).
INLINE = 4


class _Unresolved(Exception):
    """A value that a resolution under way reads before it is resolved (`Resolver.resolved`), and
    the values that read it on the way, innermost first (`readers`)."""

    def __init__(self, path):
        super().__init__(path)
        self.path, self.readers = path, []


class Refused(Exception):
    """A diagnostic that stops the resolution of one part."""

    def __init__(self, code, message, node=None):
        super().__init__(message)
        self.code, self.message = code, message
        self.line = getattr(node, 'line', 0)
        self.column = getattr(node, 'column', 0)


@dataclass(frozen=True)
class Scope:
    """Where an expression stands: the template whose member `this` names ('' at the top level), and
    inside the test of a `where` the type of the member under test (`item`). Inside an event,
    `event` is its path, whose parameters and locals the bare names read; inside a trigger, which
    has no occurrence (`trigger` is its path), `captures` are the paths of the captures that it has
    taken so far. Inside a solver, `solver` is its path, whose inputs and unknowns the bare names
    read."""

    owner: str = ''
    item: Ent | FlowOf | Occ | None = None
    event: str | None = None
    captures: tuple = ()
    trigger: str | None = None
    solver: str | None = None


TOP = Scope()
FLOW_READS = ('actual_rate', 'request', 'capacity')
ENDS = ('source', 'sink')
SIDES = ('outflow', 'inflow')
SETTINGS = ('capacity', 'request', 'allocation')
ALLOCATIONS = ('priority', 'proportional')
KEYED = ('where', 'by', 'at')
SHAPES = {'lognormal': {1}}  # the positions of the plain (shape) arguments of a family: the gsd
# The parameters of each family in their order (spec, "Distributions"), for its rule (`_broken`).
PARAMETERS = {
    'uniform': ('min', 'max'),
    'triangular': ('min', 'mode', 'max'),
    'pert': ('min', 'mode', 'max'),
    'loguniform': ('min', 'max'),
    'normal': ('mean', 'sd', 'min', 'max'),
    'lognormal': ('median', 'gsd', 'min', 'max'),
}
ARITY = {
    'uniform': (2,),
    'triangular': (3,),
    'pert': (3,),
    'loguniform': (2,),
    'normal': (2, 4),
    'lognormal': (2, 4),
}
PURE = ('exp', 'expm1', 'ln', 'log1p', 'erf')
HISTORY = ('since', 'elapsed')
OCCURRENCE = {'started': 'h', 'done': BOOL, 'active': BOOL}  # the built-in fields of an occurrence
# What the run computes, which no statement assigns: the rates of a flow and of an endpoint, the
# served fraction of a flow with legs, the built-in fields of an occurrence.
RESULTS = ('actual_rate', 'served_fraction', *OCCURRENCE)
ID = re.compile(r'[A-Za-z_][A-Za-z0-9_]*\Z')


def close(name, names):
    found = difflib.get_close_matches(name, sorted(set(names) - {name}), n=3)
    return f'; did you mean {" or ".join(found)}?' if found else ''


def literal(node):
    """The number of a literal (a number or a quantity, with its signs), or None."""
    sign = 1
    while isinstance(node, n.Unary) and node.op in ('-', '+'):
        sign = -sign if node.op == '-' else sign
        node = node.operand
    if isinstance(node, (n.Number, n.Quantity)):
        return sign * node.value, node
    return None


def decimal(node):
    """The exact number of a literal (`literal`), with its signs: the decimal that its token writes
    (`34.000000000000000001` is that, and not the float 34.0), or the number that a node made by hand
    holds; None for any other node."""
    sign = 1
    while isinstance(node, n.Unary) and node.op in ('-', '+'):
        sign = -sign if node.op == '-' else sign
        node = node.operand
    if not isinstance(node, (n.Number, n.Quantity)) or node.exact is None:
        return None
    return sign * node.exact


class Resolver:
    """Resolves the parts of one parsed text against a table of units, reading its tables with
    `read_table` (see `tables.in_folder`)."""

    def __init__(self, tree, units, read_table, files=()):
        self.units, self.read_table = units, read_table
        self.files = Files(tuple(files))
        self.problems = []
        self.tree = tree = self.wired(tree)
        # The changes of the model: each line by the path of the value that it sets
        # (`pool.start_water`, `a1.ask`), with the name that its change names; the changes of labels
        # by that name.
        self.changes, self.labels = {}, {}
        self.entities, self.templates, self.instances, self.tables = {}, {}, {}, {}
        self.root, self.records = {}, {}
        # The values whose resolution is under way, outermost first (a dict as an ordered set), and
        # how many of them a resolution resolves inside itself now (`value`).
        self.syntax, self.done, self.active, self.inline = {}, {}, {}, 0
        self.ids, self.data = {}, {}  # the ids of the rows of each table that was read, and its form
        self.owned = {}  # the paths of the values of each template, once a member asks for them
        self.creation = {}  # the creation numbers of the members of each template (`created`)
        self.inputs_only = {}  # whether each formula that an assertion reaches reads inputs only
        # The scope of each event by its path: the parameters and locals of an event are in `syntax`
        # under the event's path (`grinder.refill.amount`), with the event's path as their owner.
        self.scopes = {}
        for item in tree.items:
            if isinstance(item, n.Entity):
                (self.entities if item.name[:1].islower() else self.templates)[item.name] = item
                for member in item.members:
                    name = getattr(member, 'name', None)
                    if isinstance(member, (n.Declaration, n.Flow, n.Event, n.Solver)) and name:
                        # The first declaration of a name keeps it; a second is `duplicate_name`.
                        self.syntax.setdefault(f'{item.name}.{name}', (item.name, member))
                    if isinstance(member, n.Event):
                        event = f'{item.name}.{name}'
                        self.scopes[event] = Scope(item.name, event=event)
                        for part in (*member.params, *member.locals):
                            self.syntax.setdefault(f'{event}.{part.name}', (event, part))
                    if isinstance(member, n.Solver):
                        # The inputs and the unknowns of a solver are in `syntax` under its path.
                        solver = f'{item.name}.{name}'
                        self.scopes[solver] = Scope(item.name, solver=solver)
                        unknowns = [part for part in member.solve_for if isinstance(part, n.Unknown)]
                        for part in (*member.inputs, *unknowns):
                            self.syntax.setdefault(f'{solver}.{part.name}', (solver, part))
        for item in tree.items:
            if isinstance(item, n.Table):
                self.tables[item.name] = item
            elif isinstance(item, n.Declaration):
                if (
                    item.value is None
                    and isinstance(item.type, n.NamedType)
                    and item.type.name in self.templates
                ):
                    self.instances[item.name] = item
                else:
                    self.root[item.name] = item
                    self.syntax[item.name] = ('', item)
            elif isinstance(item, n.Record):
                self.records.setdefault(item.name, item)  # a second of one name is `duplicate_name`
        self.register_changes()

    def fail(self, code, message, node=None):
        raise Refused(code, message, node)

    def on_line(self, line):
        """`on line N` of a line of the model, in its own file, and naming the file when the model
        has several."""
        file, local = self.files.place(line)
        return f'on line {local} of {file}' if len(self.files.files) > 1 else f'on line {local}'

    def file_of(self, line):
        """The number of the file of a line in the order in which the files are read (0 for a
        model of one text)."""
        return sum(1 for _, offset in self.files.files[1:] if offset < line)

    def scope_of(self, owner):
        """The scope of what an owner declares: a template's or an entity's, or an event's (whose
        bare names are its parameters and locals)."""
        return self.scopes.get(owner) or Scope(owner)

    def parts_of(self, template):
        """The names of the parts of a template, for a suggestion."""
        prefix = f'{template}.'
        return [
            key[len(prefix) :]
            for key in self.syntax
            if key.startswith(prefix) and '.' not in key[len(prefix) :]
        ]

    def report(self, code, message, line=0, column=0, file=''):
        self.problems.append(Problem(code, message, line, column, file))

    # ---- types and units ---------------------------------------------------------------------

    def per_hour(self, kind):
        """The type of the rates of a store of a number type: its unit per hour (`1/h` for a plain
        number), the spelling that the program's builder gives a flow between such stores."""
        return self.num(f'{kind.unit}/h' if kind.unit else '1/h')

    def num(self, spelling, node=None):
        found = self.units.of(spelling)
        if found is None:
            unknown = [name for _, name in factors(spelling) if name != '1' and not self.units.has(name)]
            self.fail(
                'unit',
                f'{unknown[0]} is no unit of the library or of the model'
                + close(unknown[0], self.units.base),
                node,
            )
        return Num(spelling, found[0])

    def declared_type(self, node):
        """The type that a declaration writes; `formula(T)` gives (T, True)."""
        if isinstance(node, n.FormulaType):
            inner, retained = self.declared_type(node.of)
            if retained:
                self.fail('type', 'a formula of a formula: reading a formula gives its value', node)
            return inner, True
        if isinstance(node, n.WordType):
            return (PLAIN if node.word == 'number' else Word(node.word)), False
        if isinstance(node, n.NamedType):
            if node.name in self.templates:
                return Ent(node.name), False
            if node.name[:1].isupper() and not self.units.has(node.name):
                self.fail(
                    'unknown_name',
                    f'{node.name} is no unit and no template' + close(node.name, self.templates),
                    node,
                )
            return self.num(node.name, node), False
        if isinstance(node, n.UnitType):
            return self.num(spelling_of(flat_unit(node.unit)), node), False
        if isinstance(node, n.DistributionType):
            inner, _ = self.declared_type(node.of)
            if not isinstance(inner, (Num, EnumOf)):
                self.fail('type', f'a distribution is of numbers or of an enum, not {inner}', node)
            return Dist(inner), False
        if isinstance(node, n.EnumType):
            return EnumOf(node.members), False
        if isinstance(node, n.CollectionType):
            inner, _ = self.declared_type(node.of)
            if not isinstance(inner, Ent):
                self.fail('type', 'a collection holds members of a template, as <Pump>', node)
            return Many(inner), False
        self.fail('type', 'no type', node)

    # ---- expressions -----------------------------------------------------------------------------

    def is_member(self, node):
        """Whether a bare name can be an enum value in a typed expression."""
        return isinstance(node, n.Name) and node.name[:1].isupper()

    def member_of(self, node, expected):
        """A bare member of an enum, which takes its enum from its place (`expected`)."""
        if not isinstance(expected, EnumOf):
            self.fail(
                'enum_member',
                f'{node.name} is a member of an enum, which takes its enum from its place: compare it with '
                'a value of the enum, or declare the type, as gate: enum[OPEN, CLOSED] = OPEN',
                node,
            )
        if node.name not in expected.members:
            self.fail(
                'enum_member',
                f'{node.name} is not a member of {expected}' + close(node.name, expected.members),
                node,
            )
        return Const(node.name, expected)

    def expression(self, node, scope, unit=None):
        """The typed form of an expression in a scope. `unit` is the declared type of the place: a
        bare number takes its unit (the whole initializer), and a bare member of an enum its enum."""
        found = literal(node)
        if found is not None:
            value, written = found
            exact = decimal(node)
            if isinstance(written, n.Quantity):
                return self.quantity(value, written, scope, exact)
            if isinstance(unit, Num) and isinstance(value, (int, float)) and not isinstance(value, bool):
                return Const(value, unit, exact)
            return Const(value, PLAIN, exact)
        if isinstance(node, n.Bool):
            return Const(node.value, BOOL)
        if isinstance(node, n.Text):
            return Const(node.value, TEXT)
        if (
            self.is_member(node)
            and not self.item_field(scope, node.name)
            and (isinstance(unit, EnumOf) or node.name not in self.templates)
        ):
            return self.member_of(node, unit)
        if isinstance(node, (n.Name, n.Member, n.Collection)) or (
            isinstance(node, n.Method) and node.name in KEYED
        ):
            found = self.path(node, scope)
            if isinstance(found.type, (FlowOf, RouteOf)):
                self.fail(
                    'type',
                    'a flow is no value: read its actual_rate, request or capacity, as delivery.actual_rate',
                    node,
                )
            if isinstance(found.type, LegsOf):
                self.fail(
                    'type',
                    'a flow with legs is no value: read its served_fraction, or the actual_rate of a leg, '
                    'as restore.labor.actual_rate',
                    node,
                )
            if isinstance(found.type, EndOf):
                self.fail(
                    'type',
                    'an outflow or an inflow is no value: read its actual_rate, request or capacity, or '
                    'its flows, as water.outflow.actual_rate',
                    node,
                )
            if isinstance(found.type, EventOf):
                self.fail(
                    'type',
                    'an event is no value: read its occurrences, as count(this.refill.occurrences), or '
                    'since(this.refill), and start it with .start(...)',
                    node,
                )
            if isinstance(found.type, SolverOf):
                self.fail(
                    'type',
                    'a solver is no value: read one of the unknowns that it declares, as this.staffing.care',
                    node,
                )
            return found
        if isinstance(node, n.Method):
            if node.name == 'diff':
                self.fail('not_in_v1', 'formula differentiation (.diff) is not in the first version', node)
            if node.name == 'start':
                self.fail('start', '.start(...) starts an occurrence and gives no value', node)
            if node.name == 'draw':
                return self.drawn(node, scope, unit)
            self.fail('choose', CHOOSE, node)
        if isinstance(node, n.Call):
            return self.call(node, scope)
        if isinstance(node, n.Formula):
            self.fail(
                'formula',
                'formula(...) keeps a calculation where a value stands: it is the whole initializer',
                node,
            )
        if isinstance(node, n.Unary):
            return self.unary(node, scope)
        if isinstance(node, n.Binary):
            return self.binary(node, scope)
        if isinstance(node, n.Compare):
            # A bare member of an enum takes the enum of the operand beside it (`gate == OPEN`).
            scoped = [(item, self.operand_scope(scope, i, item)) for i, item in enumerate(node.operands)]
            operands = [
                None
                if self.is_member(item) and not self.item_field(own, item.name)
                else self.expression(item, own)
                for item, own in scoped
            ]
            enum = next(
                (item.type for item in operands if item is not None and isinstance(item.type, EnumOf)), None
            )
            operands = [
                self.expression(item, own, enum) if found is None else found
                for (item, own), found in zip(scoped, operands)
            ]
            if len(node.ops) > 1 and any(isinstance(item.type, FlowEnd) for item in operands):
                self.fail('type', 'an end of a flow is compared once, as sink == clinic.water', node)
            for k, op in enumerate(node.ops):
                operands[k], operands[k + 1] = self.alike(operands[k], operands[k + 1], node, op)
            return Apply('compare', tuple(operands), BOOL, node.ops)
        if isinstance(node, n.BoolOp):
            values = tuple(self.expression(item, scope) for item in node.values)
            for value in values:
                self.want_bool(value, node, node.op)
            return Apply(node.op, values, BOOL)
        if isinstance(node, n.IfElse):
            test = self.expression(node.test, scope)
            self.want_bool(test, node, 'if')
            # A bare member of an enum takes the enum of the place, or of the other side.
            expected = unit if isinstance(unit, EnumOf) else None
            body = (
                None
                if self.is_member(node.body) and expected is None
                else self.expression(node.body, scope, expected)
            )
            if expected is None and body is not None and isinstance(body.type, EnumOf):
                expected = body.type
            orelse = self.expression(node.orelse, scope, expected)
            if body is None:
                body = self.expression(
                    node.body, scope, orelse.type if isinstance(orelse.type, EnumOf) else None
                )
            body, orelse = self.alike(body, orelse, node, 'if')
            return Apply('if', (test, body, orelse), body.type if body.type != PLAIN else orelse.type)
        if isinstance(node, n.Within):
            # The interval of a test is an interval as a range is: ends fixed when the model compiles
            # are checked by `interval`, and a membership with two ends is the program's operation
            # `within`, which checks them each time a run evaluates it (spec: reversed bounds are an
            # error). An interval with one end left empty cannot be reversed: it is one comparison.
            value = self.expression(node.value, scope)
            self.want_number(value, node, 'in')
            outer = replace(scope, item=None) if scope.item is not None else scope
            low = high = None
            if node.low is not None:
                low, value = self.alike(self.expression(node.low, outer), value, node, 'in')
            if node.high is not None:
                value, high = self.alike(value, self.expression(node.high, outer), node, 'in')
            self.interval(low, high, 'the interval of this test', node, (node.low, node.high))
            if low is not None and high is not None:
                return Apply('call', (value, low, high), BOOL, 'within')
            if low is not None:
                return Apply('compare', (low, value), BOOL, ('<=',))
            return Apply('compare', (value, high), BOOL, ('<=',))
        self.fail('syntax', f'{type(node).__name__} is no value here', node)

    def quantity(self, value, node, scope, exact=None):
        """A number and its unit run: the names that are units, then the names that are values.
        `exact` is the decimal that the number writes."""
        first = node.unit[0][1]
        if not self.units.has(first):
            self.fail(
                'unit',
                f'{first} is no unit of the library or of the model' + close(first, self.units.base),
                node,
            )
        taken = [(1, first)]
        k = 1
        while k < len(node.unit) and self.units.has(node.unit[k][1]):
            taken.append((1 if node.unit[k][0] == '*' else -1, node.unit[k][1]))
            k += 1
        spelling = taken[0][1] + ''.join(('*' if sign > 0 else '/') + name for sign, name in taken[1:])
        result = Const(value, self.num(spelling, node), exact)
        for op, name in node.unit[k:]:
            other = self.path(n.Name(name, line=node.line, column=node.column), scope)
            if isinstance(other.type, (Ent, Many, FlowOf)):
                self.fail('type', f'{name} is no number', node)
            result = self.product('mul' if op == '*' else 'div', result, other, node)
        return result

    def unary(self, node, scope):
        """A chain of signs or of `not` (`- -x`, `not not c`), read from the inside out with no call
        of Python for each: `+` keeps a number, `-` negates it and `not` negates a yes/no. A chain of
        more than `DEEPEST` is the one negation that it makes, or none, since each is its own inverse
        exactly: so its tree stays shallow."""
        chain = []
        while isinstance(node, n.Unary):
            chain.append(node)
            node = node.operand
        inner = found = self.expression(node, scope)
        negations = 0
        for each in reversed(chain):
            if each.op == 'not':
                self.want_bool(found, each, 'not')
                found = Apply('not', (found,), BOOL)
            else:
                self.want_number(found, each, each.op)
                if each.op == '-':
                    found = Apply('neg', (found,), found.type)
            negations += each.op != '+'
        if len(chain) <= DEEPEST:
            return found
        if negations % 2 == 0:
            return inner
        return Apply('not' if chain[0].op == 'not' else 'neg', (inner,), inner.type)

    def binary(self, node, scope):
        """`+ - * / **` of two operands. A chain of `+` and `-` from the left, or of `*` and `/`, is
        read operation by operation with no call of Python for each, so a sum of hundreds of terms
        costs no depth of calls. A sum of more than `DEEPEST` operations is one `sum(...)` of its
        terms, whose tree is shallow: `sum(a, b, c)` is `a + b + c` added from the left, bit for
        bit (`napkin/core/expr.py`), and `a - b` is `a + (-b)`. A longer product is refused by name."""
        if node.op == '**':
            return self.power(node, scope)
        group = ('+', '-') if node.op in ('+', '-') else ('*', '/')
        chain = []
        while isinstance(node, n.Binary) and node.op in group:
            chain.append(node)
            node = node.left
        found = self.expression(node, scope)
        terms = [found]
        for each in reversed(chain):
            right = self.expression(each.right, scope)
            if group[0] == '*':
                found = self.product('mul' if each.op == '*' else 'div', found, right, each)
                continue
            left, right = self.alike(found, right, each, each.op)
            if len(terms) == 1:
                terms[0] = left  # a first term that is a bare zero takes the other's unit
            self.want_number(left, each, each.op)
            kind = left.type if left.type != PLAIN or right.type == PLAIN else right.type
            found = Apply('add' if each.op == '+' else 'sub', (left, right), kind)
            terms.append(right if each.op == '+' else Apply('neg', (right,), right.type))
        if len(chain) <= DEEPEST:
            return found
        if group[0] == '*':
            self.fail(
                'deep',
                f'a product of more than {DEEPEST} factors one after the other: give a part of it a name '
                'of its own, as part = formula(...), and multiply by that name',
                chain[-1],
            )
        return Apply('call', tuple(terms), found.type, 'sum')

    def power(self, node, scope):
        """`a ** b`: a number with no dimension to any power; a number with a dimension to a number
        written in place, read exactly (`2.0` is 2, `0.5` is 1/2), whose result has the powers of its
        dimension times the exponent, each whole (`raised`, as `sqrt` is the power 1/2)."""
        left, right = self.expression(node.left, scope), self.expression(node.right, scope)
        self.want_number(left, node, '**')
        self.want_number(right, node, '**')
        if right.type.dimension:
            self.fail('unit', 'an exponent has no unit', node)
        if not left.type.dimension:
            return Apply('pow', (left, right), PLAIN)
        written = literal(node.right)
        if written is None or isinstance(written[1], n.Quantity):
            self.fail('unit', f'a value in {left.type} is raised only to a number written in place', node)
        exponent = rational(written[0])
        return Apply(
            'pow',
            (left, right),
            self.raised(left.type, exponent, node, f'{left.type} ** {_fraction_text(exponent)}'),
        )

    def product(self, op, left, right, node):
        self.want_number(left, node, '*' if op == 'mul' else '/')
        self.want_number(right, node, '*' if op == 'mul' else '/')
        found = factors(left.type.unit) if left.type.unit else []
        other = factors(right.type.unit) if right.type.unit else []
        if op == 'div':
            other = [(-sign, name) for sign, name in other]
        return Apply(
            op, (left, right), self.num(spelling_of(found + other), node) if found or other else PLAIN
        )

    def raised(self, kind, exponent, node, what):
        """The type of a number of type `kind` to the rational power `exponent` (a square root is the
        power 1/2): its dimension, each power times the exponent, which must be whole, so that
        `sqrt(24 h * 1 day)` is a time as `sqrt(24 h * 24 h)` is, and `sqrt` of a ratio is a plain
        number. A run computes the value in the canonical unit of its dimension, so any unit of that
        dimension names it exactly: the spelling that the exponent makes of `kind`'s own names when
        their powers allow it (`h*h` gives `h`), no unit for no dimension, and else a unit of the
        model of the dimension (`unit_for`)."""
        dimension = []
        for base, power in kind.dimension:
            found = power * exponent
            if found.denominator != 1:
                rule = (
                    'a square root needs each power of it even, as in h*h or h*day'
                    if exponent == Fraction(1, 2)
                    else f'each power of it times {_fraction_text(exponent)} must be whole'
                )
                self.fail(
                    'unit', f'{what}: its dimension is {_dimension_text(kind.dimension)}, and {rule}', node
                )
            dimension.append((base, int(found)))
        powers = {}
        for sign, name in factors(kind.unit) if kind.unit else []:
            powers[name] = powers.get(name, 0) + sign
        scaled = {name: power * exponent for name, power in powers.items()}
        if all(power.denominator == 1 for power in scaled.values()):
            spelling = spelling_of(
                [
                    (1 if power > 0 else -1, name)
                    for name, power in scaled.items()
                    for _ in range(abs(int(power)))
                ]
            )
            return self.num(spelling, node) if spelling else PLAIN
        if not dimension:
            return PLAIN
        return self.unit_for(tuple(dimension), powers, node, what)

    def unit_for(self, dimension, names, node, what):
        """A unit of the model of a dimension, for a value whose own names do not spell it: of the
        units of exactly that dimension, one of `names` first, then one of scale 1, then the first that
        the model declares; else a product of such units of its base dimensions."""
        order = {name: k for k, name in enumerate(self.units.base)}

        def best(wanted):
            found = [name for name, (dims, _) in self.units.base.items() if dims == wanted]
            if not found:
                return None
            return min(
                found, key=lambda name: (name not in names, self.units.base[name][1] != 1, order[name])
            )

        whole = best(dimension)
        if whole is not None:
            return self.num(whole, node)
        parts = []
        for base, power in dimension:
            name = best(((base, 1),))
            if name is None:
                self.fail('unit', f'{what}: no unit of the model is a {base} alone, to name its result', node)
            parts += [(1 if power > 0 else -1, name)] * abs(power)
        return self.num(spelling_of(parts), node)

    def alike(self, left, right, node, op):
        """Two operands of one dimension; a bare zero takes the other's unit."""
        if isinstance(left.type, FlowEnd) or isinstance(right.type, FlowEnd):
            return self.ends_alike(left, right, node, op)
        if isinstance(left.type, Num) and isinstance(right.type, Num):
            if left.type.dimension != right.type.dimension:
                if _zero(left) and not left.type.dimension:
                    return Const(left.value, right.type), right
                if _zero(right) and not right.type.dimension:
                    return left, Const(right.value, left.type)
                self.fail(
                    'unit', f'{op} needs one dimension on both sides: {left.type} and {right.type}', node
                )
            return left, right
        if isinstance(left.type, Many) or isinstance(right.type, Many):
            self.fail('type', f'{op} takes values, not collections: reduce one, as sum(c.f)', node)
        if left.type != right.type:
            self.fail('type', f'{op} needs one type on both sides: {left.type} and {right.type}', node)
        if op not in ('==', '!=', 'if'):
            self.fail('type', f'{left.type} has == and != only', node)
        return left, right

    def want_number(self, value, node, op):
        if not isinstance(value.type, Num):
            hint = ': write (1 if c else 0)' if value.type == BOOL else ''
            if isinstance(value.type, Many):
                hint = ': reduce it, as sum(c.f)'
            self.fail('type', f'{op} takes numbers, not {value.type}{hint}', node)

    def want_bool(self, value, node, op):
        if value.type != BOOL:
            self.fail('type', f'{op} takes a yes/no, not {value.type}', node)

    def history(self, node, scope):
        """`since(e)` of an event, a duration that fails before its first start; `elapsed(x)`, the
        time since a value last changed at a commit."""
        if len(node.args) != 1 or node.named:
            what = 'an event' if node.function == 'since' else 'a value'
            self.fail('arguments', f'{node.function} takes {what}, as {node.function}(...)', node)
        if not isinstance(node.args[0], (n.Name, n.Member)):
            self.fail('history', f'{node.function} reads a named part, not an expression', node)
        source = self.path(node.args[0], scope)
        hours = self.num('h', node)
        if node.function == 'since':
            if not isinstance(source.type, EventOf):
                self.fail('history', f'since takes an event, as since(this.repair), not {source.type}', node)
            return History('since', source, hours)
        if (
            isinstance(source.type, (Many, Ent, EventOf, FlowOf, RouteOf, LegsOf, EndOf, Dist, SolverOf))
            or not source.part
        ):
            self.fail('history', f'elapsed takes a value, not {source.type}', node)
        if self.value(source.part).kind == UNKNOWN:
            self.fail(
                'history',
                "elapsed takes a value that commits change, and a solver's result changes when its "
                'solver settles',
                node,
            )
        return History('elapsed', source, hours)

    def call(self, node, scope):
        if node.function in HISTORY:
            return self.history(node, scope)
        if node.function in ALLOCATIONS:
            self.fail(
                'allocation',
                f'{node.function}(...) is an allocation, no value: it is the value of '
                'outflow.allocation or inflow.allocation under a store',
                node,
            )
        if node.function in ('sum', 'count', 'any', 'all') or (
            node.function in ('min', 'max') and len(node.args) == 1
        ):
            return self.reduction(node, scope)
        if node.function in ARITY or node.function == 'categorical':
            self.fail(
                'draw',
                f'{node.function}(...) is a distribution: it is the whole initializer of a value or an '
                'input, and a draw of it the default of an input',
                node,
            )
        args = [self.expression(arg, scope) for arg in node.args]
        for arg in args:
            self.want_number(arg, node, node.function)
        wanted = {'clip': 3, 'abs': 1, 'sqrt': 1}.get(node.function, 1 if node.function in PURE else None)
        if wanted is not None and len(args) != wanted:
            self.fail(
                'arguments', f'{node.function} takes {wanted} argument' + ('s' if wanted > 1 else ''), node
            )
        if node.function in ('min', 'max', 'clip'):
            reference = next((arg for arg in args if arg.type != PLAIN), args[0])
            for k, arg in enumerate(args):
                _, args[k] = self.alike(reference, arg, node, node.function)
            return Apply('call', tuple(args), reference.type, node.function)
        if node.function == 'abs':
            return Apply('call', tuple(args), args[0].type, 'abs')
        if node.function == 'sqrt':
            kind = self.raised(args[0].type, Fraction(1, 2), node, f'sqrt of {args[0].type}')
            return Apply('call', tuple(args), kind, 'sqrt')
        if args[0].type.dimension:
            self.fail('unit', f'{node.function} takes a plain number, not {args[0].type}', node)
        return Apply('call', tuple(args), PLAIN, node.function)

    def reduction(self, node, scope):
        """`sum`, `count`, `any`, `all`, `min` or `max` of one collection or projection (D4: an empty
        `sum` is zero in its unit, `count` zero, `any` false, `all` true)."""
        op = node.function
        if len(node.args) != 1:
            self.fail('arguments', f'{op} takes one collection or projection, as {op}(c.f)', node)
        source = self.expression(node.args[0], scope)
        if not (isinstance(source, Read) and isinstance(source.type, Many)):
            what = 'of values is min(a, b)' if op in ('min', 'max') else 'takes a collection'
            self.fail('collection', f'{op} {what}: {op}(c.f) reduces a projection', node)
        of = source.type.of
        if op == 'count':
            if isinstance(of, Num):
                self.fail(
                    'type',
                    'count counts members, or true values: sum(c.f) is the total of numbers, and '
                    'count(c) the number of members',
                    node,
                )
            if not (isinstance(of, (Ent, FlowOf, Occ)) or of == BOOL):
                self.fail('type', f'count counts members or yes/no values, not {of}', node)
            return Reduced(op, source, PLAIN)
        if op in ('any', 'all'):
            if of != BOOL:
                self.fail('type', f'{op} takes yes/no values, not {of}', node)
            return Reduced(op, source, BOOL)
        if not isinstance(of, Num):
            self.fail('type', f'{op} takes numbers, not {of}', node)
        return Reduced(op, source, of)

    # ---- paths -------------------------------------------------------------------------------------

    def item_field(self, scope, name):
        """Whether a bare name denotes a field of the member under test."""
        item = scope.item
        if isinstance(item, Ent):
            return isinstance(self.syntax.get(f'{item.template}.{name}', (None, None))[1], n.Declaration)
        if isinstance(item, Occ):
            return name in OCCURRENCE or self.syntax.get(f'{item.event}.{name}', (None,))[0] == item.event
        return isinstance(item, FlowOf) and name in (*ENDS, *FLOW_READS)

    def operand_scope(self, scope, index, node):
        """A filter comparison takes its left field from the member and its right expression from
        the enclosing scope. An unbound flow-end marker also works in a reversed end comparison."""
        if scope.item is None or index == 0:
            return scope
        outer = replace(scope, item=None)
        if isinstance(scope.item, FlowOf) and isinstance(node, n.Name) and node.name in ENDS:
            name = node.name
            if (
                name not in self.root
                and name not in self.entities
                and name not in self.instances
                and name not in self.tables
                and name not in self.templates
                and self.scoped_name(node, outer) is None
            ):
                return scope
        return outer

    def filter_field(self, read):
        """Fixed member fields and the current arguments of occurrences can select a member.
        An argument can change within its invocation, so the read itself does not become fixed."""
        return read.fixed or isinstance(self.syntax.get(read.part, (None, None))[1], n.Param)

    def path(self, node, scope):
        """What a name, a dotted path, a keyed operation or a literal names, as a `Read` with its
        type: a value, a member, a collection, a projection or a flow."""
        if isinstance(node, n.Name):
            return self.name(node, scope)
        if isinstance(node, n.Collection):
            return self.literal(node, scope)
        if isinstance(node, n.Method) and node.name in KEYED:
            return self.keyed(node, scope)
        if not isinstance(node, n.Member):
            self.fail('syntax', 'only a name, a member or a collection has parts', node)
        head = node.base.name if isinstance(node.base, n.Name) else None
        if head is not None and (head in self.tables or head in self.templates or node.name == 'instances'):
            local = self.scoped_name(node.base, scope)
            if local is not None:
                return self.step(local, node.name, node)
            if head in self.tables:
                return self.row(head, node.name, node)
            if head in self.templates:
                if node.name == 'instances':
                    return Read(('instances', head), (), Many(Ent(head)), True)
                self.fail('unknown_name', f'{head} is a template: {head}.instances names its members', node)
            if node.name == 'instances' and head[:1].isupper():
                self.fail('unknown_name', f'{head} is no template' + close(head, self.templates), node)
        return self.step(self.path(node.base, scope), node.name, node)

    def scoped_name(self, node, scope):
        """What the scope binds before the top-level declarations or a dotted table/template head."""
        name = node.name
        if name == 'this':
            if not scope.owner:
                self.fail('unknown_name', 'this is the entity of a member: the top level has none', node)
            return Read(('this',), (), Ent(scope.owner), True)
        if name == 't':
            return Read(('time',), (), self.num('h', node))
        if isinstance(scope.item, FlowOf) and name in (*ENDS, *FLOW_READS):
            # A bare name of a flow's own in the test of a where over flows is the member's.
            if name in FLOW_READS:
                self.fail(
                    'where_live',
                    f'where tests what is fixed for each member, and the {name} of a flow is not: a '
                    'where over flows compares their ends, as sink == clinic.water',
                    node,
                )
            return Read(('item',), (name,), FlowEnd(scope.item.rate), True)
        if self.item_field(scope, name):
            return self.step(Read(('item',), (), scope.item, True), name, node)
        for capture in scope.captures:
            if capture.rpartition('.')[2] == name:
                return Read(('local', name), (), self.done[capture].type, part=capture)
        own = f'{scope.event}.{name}'
        if scope.event is not None and self.syntax.get(own, ('',))[0] == scope.event:
            # A parameter, a local or a flow of this occurrence (a bare name belongs to it).
            syntax = self.syntax[own][1]
            if isinstance(syntax, n.Flow):
                return Read(('local', name), (), self.flow_type(own, scope.event, syntax))
            value = self.value(own)
            return Read(
                ('local', name), (), value.type, stored=_stored(value) and value.init is not None, part=own
            )
        own = f'{scope.solver}.{name}'
        if scope.solver is not None and self.syntax.get(own, ('',))[0] == scope.solver:
            # An input of the solver reads as its source, under its own name; an unknown is a number.
            if isinstance(self.syntax[own][1], n.Binding):
                source = self.binding(own).read
                return Read(
                    ('local', name), (), source.type, source.fixed, source.formula, source.stored, source.part
                )
            return Read(('local', name), (), self.value(own).type, part=own)
        return None

    def name(self, node, scope):
        local = self.scoped_name(node, scope)
        if local is not None:
            return local
        name = node.name
        if name in self.root:
            value = self.value(name)
            formula = name if value.kind == FORMULA else ''
            return Read(('root',), (name,), value.type, fixed_kind(value), formula, _stored(value), name)
        if name in self.entities:
            return Read(('named', name), (), Ent(name), True)
        if name in self.instances:
            return Read(('named', name), (), Ent(self.instances[name].type.name), True)
        if name in self.templates:
            self.fail('unknown_name', f'{name} is a template: {name}.instances names its members', node)
        if name in self.tables:
            template = self.tables[name].template
            self.fail(
                'unknown_name',
                f'{name} is a table: {name}.id names one of its rows, and {template}.instances every member',
                node,
            )
        if name[:1].isupper():
            self.member_of(node, None)
        known = [*self.root, *self.entities, *self.instances]
        for inner in (scope.event, scope.solver):
            if inner is not None:
                known += [key.rpartition('.')[2] for key, (owner, _) in self.syntax.items() if owner == inner]
        hint = '; a trigger has no occurrence: it reads its captures and this' if scope.trigger else ''
        if name in ('yes', 'no'):
            hint = '; a yes/no value is written true or false'
        self.fail('unknown_name', f'{name} names nothing here' + close(name, known) + hint, node)

    def row(self, table, id, node):
        """`sites.clinic`: the row of a table by its id."""
        if table not in self.ids:
            raise Refused('depends', f'the table {table} has a problem of its own')
        ids = self.ids[table]
        if ids is None:
            self.fail('unknown_name', f'the rows of {table} have no ids: an id column names them', node)
        template = self.tables[table].template
        if id not in ids:
            if f'{template}.{id}' in self.syntax:
                self.fail(
                    'unknown_name',
                    f'{table} is a table, which names its rows by their ids: the {id} of every member is '
                    f'{template}.instances.{id}',
                    node,
                )
            self.fail('unknown_name', f'{table} has no row {id}' + close(id, ids), node)
        return Read(('named', f'{table}.{id}'), (), Ent(template), True)

    def step(self, base, name, node):
        """The read one step on from `base`: a part of a member (a projection from a collection), a
        rate or an end of a flow, a rate or a leg of a route, the fraction or a leg of a flow with
        legs, the outflow or the inflow of a stored number, or what an endpoint reads (its rates and
        its flows)."""
        kind = base.type
        many = isinstance(kind, Many)
        inner = kind.of if many else kind
        steps = (*base.steps, name)
        if isinstance(inner, FlowEnd):
            self.fail(
                'where_live',
                f'a where over flows compares their ends, as sink == clinic.water: the store at an end '
                f'is live, and {base.steps[-1]}.{name} is not read there',
                node,
            )
        if isinstance(inner, Ent):
            template = inner.template
            path = f'{template}.{name}'
            if path not in self.syntax:
                parts = self.parts_of(template)
                self.fail('unknown_name', f'{template} has no {name}' + close(name, parts), node)
            _, syntax = self.syntax[path]
            formula, stored, part = '', False, ''
            if isinstance(syntax, n.Flow):
                found, steady = self.flow_type(path, template, syntax), False
            elif isinstance(syntax, n.Declaration):
                value = self.value(path)
                found, steady = value.type, base.fixed and fixed_kind(value)
                formula = path if base.fixed and value.kind == FORMULA else ''
                stored, part = _stored(value), path
            elif isinstance(syntax, n.Event):
                found, steady = EventOf(path), False
            else:
                found, steady = SolverOf(path), False
            return Read(
                base.start, steps, self.projected(found, kind, name, node), steady, formula, stored, part
            )
        if isinstance(inner, SolverOf):
            own = f'{inner.solver}.{name}'
            if isinstance(self.syntax.get(own, (0, 0))[1], n.Unknown):
                found = self.value(own).type
                return Read(base.start, steps, self.projected(found, kind, name, node), part=own)
            unknowns = [
                key.rpartition('.')[2]
                for key, (owner, syntax) in self.syntax.items()
                if owner == inner.solver and isinstance(syntax, n.Unknown)
            ]
            hint = (
                f': {name} is an input, which a caller reads by its own path'
                if isinstance(self.syntax.get(own, (0, 0))[1], n.Binding)
                else close(name, unknowns)
            )
            self.fail(
                'unknown_name',
                f'a solver publishes the unknowns that it declares under solve_for, not {name}{hint}',
                node,
            )
        if isinstance(inner, EventOf):
            if name == 'occurrences':
                found = Many(Occ(inner.event), self.num('h', node))
                return Read(base.start, steps, self.projected(found, kind, name, node))
            self.fail(
                'unknown_name',
                f'an event reads its occurrences, and a stage starts it with .start(...), not {name}',
                node,
            )
        if isinstance(inner, Occ):
            own = f'{inner.event}.{name}'
            if self.syntax.get(own, ('',))[0] == inner.event:
                syntax = self.syntax[own][1]
                if isinstance(syntax, n.Flow):
                    found = self.flow_type(own, inner.event, syntax)
                    return Read(base.start, steps, self.projected(found, kind, name, node))
                value = self.value(own)
                stored = _stored(value) and value.init is not None
                return Read(
                    base.start,
                    steps,
                    self.projected(value.type, kind, name, node),
                    fixed=base.fixed and fixed_kind(value),
                    stored=stored,
                    part=own,
                )
            if name in OCCURRENCE:
                found = OCCURRENCE[name]
                found = self.num(found, node) if isinstance(found, str) else found
                return Read(
                    base.start,
                    steps,
                    self.projected(found, kind, name, node),
                    fixed=base.fixed and name == 'started',
                )
            names = [
                key.rpartition('.')[2] for key, (owner, _) in self.syntax.items() if owner == inner.event
            ]
            self.fail(
                'unknown_name',
                f'an occurrence of {inner.event} has no {name}: it reads its parameters, its locals and '
                'started, done and active' + close(name, [*names, *OCCURRENCE]),
                node,
            )
        if isinstance(inner, FlowOf):
            if name in FLOW_READS and not (inner.view and name == 'capacity'):
                return Read(base.start, steps, Many(inner.rate, kind.key) if many else inner.rate)
            if name in ENDS:
                return self.end(base, inner, name, node)
            if inner.view:
                self.fail(
                    'unknown_name',
                    f'a leg of a route reads actual_rate, request, source and sink, not {name}: the '
                    "route's capacity limits both its legs",
                    node,
                )
            self.fail(
                'unknown_name',
                f'a directed flow reads actual_rate, request, capacity, source and sink, not {name}',
                node,
            )
        if isinstance(inner, RouteOf):
            if name in FLOW_READS:
                return Read(base.start, steps, Many(inner.rate, kind.key) if many else inner.rate)
            if name in ('forward', 'backward'):
                leg = FlowOf(inner.rate, f'{inner.flow}.{name}', view=True)
                return Read(base.start, steps, Many(leg, kind.key) if many else leg)
            hint = f': a route has its ends through its legs, as forward.{name}' if name in ENDS else ''
            self.fail(
                'unknown_name',
                f'a reversible route reads actual_rate, request, capacity, forward and backward, not '
                f'{name}{hint}',
                node,
            )
        if isinstance(inner, LegsOf):
            owner, parent = self.syntax[inner.flow]
            leg = next((each for each in parent.legs if each.name == name), None)
            if leg is not None:
                found = FlowOf(self.rate(owner, leg), f'{inner.flow}.{name}')
                return Read(base.start, steps, Many(found, kind.key) if many else found)
            if name == 'served_fraction':
                return Read(base.start, steps, Many(PLAIN, kind.key) if many else PLAIN)
            if name in FLOW_READS:
                self.fail(
                    'type',
                    f'a flow with legs has no {name} of its own: read a leg, as '
                    f'{parent.name}.{parent.legs[0].name}.{name}, or its served_fraction',
                    node,
                )
            legs = [each.name for each in parent.legs]
            self.fail(
                'unknown_name',
                f'{parent.name} reads served_fraction and its legs ({", ".join(legs)}), not {name}'
                + close(name, legs),
                node,
            )
        if isinstance(inner, EndOf):
            if name in FLOW_READS:
                return Read(base.start, steps, Many(inner.rate, kind.key) if many else inner.rate)
            if name == 'flows':
                return Read(base.start, steps, self.projected(Many(FlowOf(inner.rate)), kind, name, node))
            if name == 'allocation':
                self.fail(
                    'allocation',
                    'an allocation is no value: it is set under the store, as outflow.allocation = '
                    'priority(...)',
                    node,
                )
            self.fail(
                'unknown_name',
                f'an outflow or an inflow reads actual_rate, request, capacity and flows, not {name}',
                node,
            )
        if name in SIDES:
            if not base.stored:
                self.fail(
                    'flow_end',
                    f'{".".join(base.steps) or name} is no stored number: a store has an outflow and an '
                    'inflow',
                    node,
                )
            return Read(base.start, steps, self.projected(EndOf(self.per_hour(inner)), kind, name, node))
        if isinstance(inner, Dist) and name in ('mean', 'std'):
            if not isinstance(inner.of, Num):
                self.fail('type', f'a categorical has no {name}: its outcomes are no numbers', node)
            return Read(base.start, steps, self.projected(inner.of, kind, name, node))
        self.fail('unknown_name', f'{name} is no part of a value of {kind}', node)

    def projected(self, found, kind, name, node):
        """The type of a step: of the one thing that it names, or from a collection the projection
        of it over each member, with the collection's keys. A projection of collections is none."""
        if not isinstance(kind, Many):
            return found
        if isinstance(found, Many):
            self.fail(
                'collection',
                f'{name} is a collection on each member, and a projection of collections is no '
                'collection: reduce it on the member, then reduce that value',
                node,
            )
        return Many(found, kind.key)

    def literal(self, node, scope):
        """`<a, b>`: members of one template, each named once."""
        if not node.items:
            self.fail('collection', 'an empty collection needs its type: name: <Template> = <>', node)
        items = tuple(self.path(item, scope) for item in node.items)
        for item in items:
            if not isinstance(item.type, Ent):
                self.fail('collection', f'a collection lists members, and one of these is {item.type}', node)
        templates = sorted({item.type.template for item in items})
        if len(templates) > 1:
            self.fail(
                'collection', f'a collection holds members of one template, not {", ".join(templates)}', node
            )
        if len(set(items)) < len(items):
            self.fail('duplicate_literal', 'a collection names each member once', node)
        return Read(('literal', items), (), Many(Ent(templates[0])), all(item.fixed for item in items))

    def keyed(self, node, scope):
        """Filter a collection, set its numeric key, or select one member."""
        source = self.path(node.base, scope)
        if not (isinstance(source.type, Many) and isinstance(source.type.of, (Ent, FlowOf, Occ))):
            self.fail(
                'collection', f'.{node.name}(...) takes a collection of members, not {source.type}', node
            )
        of, key = source.type.of, source.type.key
        if len(node.args) != 1:
            self.fail('arguments', f'.{node.name}(...) takes one argument', node)
        (arg,) = node.args
        if node.name == 'where':
            test = self.expression(arg, replace(scope, item=of))
            self.want_bool(test, node, 'where')
            for read in reads_of(test):
                if read.start == ('item',) and not self.filter_field(read):
                    self.fail(
                        'where_live',
                        f'where tests what is fixed for each member, and {".".join(read.steps)} is not: '
                        'for a live test, put a yes/no formula on the member and reduce it',
                        node,
                    )
            return Read(('where', source, test), (), source.type, source.fixed and fixed(test))
        if node.name == 'by':
            if not isinstance(arg, n.Name):
                self.fail('unknown_name', 'by names a numeric field of a member', node)
            key_field = self.step(Read(('item',), (), of, True), arg.name, arg)
            if not isinstance(key_field.type, Num):
                self.fail('type', f'a key is a number, and {arg.name} is {key_field.type}', node)
            return Read(
                ('by', source, arg.name), (), Many(of, key_field.type), source.fixed and key_field.fixed
            )
        found = self.expression(arg, scope)
        self.want_number(found, node, '.at')
        if found.type.dimension != key.dimension:
            if not _zero(found):
                self.fail('unit', f'.at(...) reads a key in {key}, not {found.type}', node)
            found = Const(found.value, key)
        chosen = self.chosen(source, found)
        if chosen is not None:
            # The member that the fixed key selects, read by its id: what depends on the read depends
            # on that member alone, in the declared model and in the program.
            return Read(('named', chosen), (), of, True)
        return Read(('lookup', source, found), (), of, source.fixed and fixed(found))

    def chosen(self, source, key):
        """The id of the member that `source.at(key)` reads when the model fixes it when it compiles:
        the key is fixed then (`exact`), and so are the members with their natural keys, their
        creation numbers (`created`), the same for every member that reads them: the instances of a
        template, or a literal of named members (`<leaf, top>`). Of them, the one with the greatest key
        at or below the key (`select`); None for any other read, and below the first key, which a run
        refuses when it reads it."""
        at = self.exact(key)
        if at is None or _own(source) or source.steps or not isinstance(source.type.of, Ent):
            return None
        numbers = self.created(source.type.of.template)
        if source.start[0] == 'instances':
            # The creation numbers of the instances are 0, 1, 2, ... in their order: the greatest at
            # or below the key is its floor, and the last member's beyond the last.
            if at < 0 or not numbers:
                return None
            return list(numbers)[min(math.floor(at), len(numbers) - 1)]
        if source.start[0] != 'literal' or not all(
            item.start[0] == 'named' and not item.steps for item in source.start[1]
        ):
            return None
        named = sorted((item.start[1] for item in source.start[1]), key=numbers.get)
        return select({member: numbers[member] for member in named}, at)

    def created(self, template):
        """{id: creation number} of a template's members in their order of creation, the natural keys
        that number them from 0 as the program orders them (`napkin.program.build.Builder`): an entity
        written once is its one member; a template's members are its members written by hand and the
        rows of its tables in the order of the text, the rows of a table with ids in the order of
        their ids."""
        found = self.creation.get(template)
        if found is not None:
            return found
        ids = [template] if template in self.entities else []
        for item in self.tree.items:
            if isinstance(item, n.Declaration) and self.instances.get(item.name) is item:
                if item.type.name == template:
                    ids.append(item.name)
            elif isinstance(item, n.Table) and item.template == template and item.name in self.data:
                rows = self.ids.get(item.name)
                if rows is None:
                    ids += [f'{item.name}[{k}]' for k in range(len(self.data[item.name].rows))]
                else:
                    ids += [f'{item.name}.{id}' for id in sorted(rows)]
        self.creation[template] = found = {id: number for number, id in enumerate(ids)}
        return found

    def ends_alike(self, left, right, node, op):
        """The sides of a comparison of an end of a flow (`FlowEnd`): `==` or `!=` with another end,
        or with one stored number of the flows' quantity, which it is, or is not."""
        end, other = (left, right) if isinstance(left.type, FlowEnd) else (right, left)
        if op not in ('==', '!='):
            self.fail(
                'type',
                f'an end of a flow is compared with == or != to a stored number, as sink == clinic.water, '
                f'not with {op}',
                node,
            )
        if isinstance(other.type, FlowEnd):
            return left, right
        if not (isinstance(other, Read) and other.stored and isinstance(other.type, Num)):
            what = other.type
            if isinstance(what, Num):
                what = f'a number in {what.unit}' if what.unit else 'a plain number'
            self.fail(
                'type',
                f'an end of a flow is a store, compared to a stored number, as sink == clinic.water, not '
                f'to {what}',
                node,
            )
        if self.per_hour(other.type).dimension != end.type.rate.dimension:
            self.fail(
                'unit',
                f'these flows carry {end.type.rate}, and {".".join(other.steps)} holds {other.type}: no '
                'flow of them ends there',
                node,
            )
        return left, right

    def link_target(self, found, expected, node):
        """The id of the member that a link's initializer names: an entity, an instance or a row."""
        if not (
            isinstance(found, Read)
            and found.start[0] == 'named'
            and not found.steps
            and isinstance(found.type, Ent)
        ):
            self.fail(
                'link',
                'a link names a member: an entity, an instance or a row of a table (sites.junction)',
                node,
            )
        if expected is not None and found.type != expected:
            self.fail(
                'type',
                f'the link is to a member of {expected.template}, and {found.start[1]} is a member of '
                f'{found.type.template}',
                node,
            )
        return found.start[1]

    # ---- values ------------------------------------------------------------------------------------

    def value(self, path):
        """The declared value of a path, resolved once; a value with a problem refuses its readers
        quietly (`depends`), since its own problem is reported. A value that its own resolution reads
        (a template's, through other members) is read as its declaration types it (`provisional`):
        whether a member reads itself is the members' connections' to say (`Order`).

        A value that a resolution under way reads is resolved before it and not inside it
        (`resolved`), so a chain of values costs no depth of calls (the audit's row 15)."""
        if path in self.done:
            found = self.done[path]
            if found is None:
                raise Refused('depends', f'{path} has a problem of its own')
            return found
        syntax = self.syntax[path][1]
        if path in self.active:
            found = self.provisional(path, syntax)
            if found is not None:
                return found
            active = list(self.active)
            chain = ' reads '.join([*active[active.index(path) :], path])
            if any(self.syntax[each][0] in self.templates for each in active[active.index(path) :]):
                self.fail(
                    'cycle',
                    f'{chain}: its type is not known before its value, so declare its type '
                    f'({syntax.name}: type = value), and the connections of the members decide whether '
                    'one of them reads itself',
                    syntax,
                )
            self.fail('cycle', f'{chain}: the values on a cycle have no order', syntax)
        if not self.active:
            return self.resolved(path)
        if self.inline >= INLINE:
            raise _Unresolved(path)
        # A value that a resolution under way reads, resolved inside it, at most `INLINE` deep: so a
        # wide expression of values not resolved yet is resolved once, and a chain costs no depth.
        self.inline += 1
        self.active[path] = None
        try:
            found = self.declared(path)
        except _Unresolved as unresolved:
            unresolved.readers.append(path)  # the driver resolves it again after what it reads
            raise
        except Refused:
            self.done[path] = None
            raise
        finally:
            self.inline -= 1
            del self.active[path]
        self.done[path] = found
        return found

    def resolved(self, path):
        """Resolve a value, and each value that its resolution reads before it, on an explicit stack
        (`active`, outermost first, so that a cycle is its chain from the value that it returns to):
        the value on top is resolved; a value that it reads is resolved inside it, up to `INLINE`
        deep, and one deeper that is not resolved yet raises `_Unresolved`, goes on top and is
        resolved first, and the value under it is then resolved again, from its start. A resolution
        has no effect but the values that it resolves, so resolving it again gives what one
        resolution would, and each value is resolved a few times at most. A problem of a value
        refuses each value under it on the stack, as a problem of what it reads, and is the caller's
        to report."""
        stack = self.active
        stack[path] = None
        self.inline = 0
        try:
            while stack:
                current = next(reversed(stack))
                try:
                    found = self.declared(current)
                except _Unresolved as unresolved:
                    # The values that were resolved inside `current` and wait for it, outermost first,
                    # then the one that they read: so the stack is the chain of what reads what.
                    for each in (*reversed(unresolved.readers), unresolved.path):
                        stack[each] = None
                    continue
                except Refused:
                    for each in stack:
                        self.done[each] = None
                    raise
                self.done[current] = found
                del stack[current]
        finally:
            stack.clear()
        return self.done[path]

    def declared(self, path):
        """One resolution of the value of a path: a parameter, an unknown of a solver, or a
        declaration, with the `change` of the model that sets it."""
        owner, syntax = self.syntax[path]
        scope = self.scope_of(owner)
        if isinstance(syntax, n.Param):
            return self.param(path, scope, syntax)
        if isinstance(syntax, n.Unknown):
            return self.unknown(path, scope, syntax)
        found = self.declaration(path, scope, syntax)
        if path in self.changes and (owner in self.entities or owner in self.templates):
            found = self.changed(found, owner, self.changes[path][1])
        return found

    def provisional(self, path, syntax):
        """The value of a path that its own resolution reads: its declared kind and type, with no
        initializer yet, so that the read has its type. None when the declaration gives no type, or
        gives a link or a collection, whose readers need its initializer."""
        if not isinstance(syntax, n.Declaration) or syntax.type is None:
            return None
        declared, retained = self.declared_type(syntax.type)
        if not isinstance(declared, (Num, Word, EnumOf)):
            return None
        kind = FORMULA if retained else INPUT if syntax.modifier == 'input' else STATE
        readonly = syntax.modifier == 'readonly'
        return DeclaredValue(path, syntax.name, kind, declared, None, readonly=readonly, line=syntax.line)

    def param(self, path, scope, node):
        """A parameter of an event: a value copy (a number, a yes/no, a text, a member of an enum) or a
        reference to an entity (D13), with its entry bounds; each start gives its argument."""
        declared, retained = self.declared_type(node.type)
        if retained or isinstance(declared, (Many, Dist)):
            self.fail(
                'type',
                f'the parameter {node.name} is a number, a yes/no, a text, a member of an enum or an entity, '
                f'not {"a formula" if retained else declared}',
                node,
            )
        lower = upper = None
        if node.range is not None:
            if not isinstance(declared, Num):
                self.fail('range', f'a range belongs to a number, and {node.name} is {declared}', node.range)
            lower, upper = (
                self.bound(end, scope, declared, node) for end in (node.range.low, node.range.high)
            )
            self.interval(
                lower,
                upper,
                f'the range of {node.name}',
                node.range,
                (node.range.low, node.range.high),
                floor=self.scale(declared),
            )
        kind = LINK if isinstance(declared, Ent) else STATE
        return DeclaredValue(path, node.name, kind, declared, None, lower, upper, line=node.line)

    def declaration(self, path, scope, node):
        declared, retained = (None, False) if node.type is None else self.declared_type(node.type)
        template = scope.owner in self.templates
        if scope.event is not None and node.value is None:
            self.fail(
                'no_value',
                f'{node.name} is a local of an event, which has its starting value: {node.name}: type = value',
                node,
            )
        if node.value is None:
            if isinstance(declared, Ent):
                if not template:
                    self.fail(
                        'link',
                        f'{node.name} names no member: a link of an entity names its member, as '
                        f'{node.name} = pump_a',
                        node,
                    )
                return self.finish(path, scope, node, LINK, declared, None)
            if template and declared is not None and not retained:
                kind = (
                    COLLECTION if isinstance(declared, Many) else INPUT if node.modifier == 'input' else STATE
                )
                return self.finish(path, scope, node, kind, declared, None)
            self.fail(
                'no_value', f'{node.name} has no starting value: an annotation gives no value (D4)', node
            )
        unit = declared if isinstance(declared, (Num, EnumOf, Dist)) else None
        kind, init = self.initializer(node, scope, declared, retained, unit)
        value_type = init.type if declared is None else declared
        if declared is not None and not compatible(init.type, declared):
            code = 'unit' if isinstance(declared, Num) and isinstance(init.type, Num) else 'type'
            self.fail(
                code, f'{node.name} is declared {declared}, and its initializer is {init.type}', node.value
            )
        if isinstance(init, Retain) and isinstance(init.type, (Ent, Many, Occ)):
            self.fail(
                'formula',
                'a formula gives a number, a yes/no or a text, not a member or a collection, nor an occurrence',
                node,
            )
        if isinstance(init.type, Occ) and scope.event is None:
            self.fail(
                'occurrence',
                f'{node.name} would hold an occurrence: a reference to an occurrence is a local of an event, '
                'set when its own occurrence enters, and a value of an entity or of the top level starts '
                'before any occurrence: read them where they stand, as this.repair.occurrences.at(t).crew_size',
                node,
            )
        if isinstance(init.type, Ent) and scope.event is not None:
            self.fail(
                'link',
                f'{node.name} would hold an entity: a local holds a value, and an entity reaches an event '
                'as a parameter (D13)',
                node,
            )
        if isinstance(init.type, Ent):
            if not scope.owner:
                self.fail(
                    'link',
                    'a link belongs to an entity or a template; at the top level, name: Template is an instance',
                    node,
                )
            if node.modifier == 'input':
                self.fail('link', f'{node.name} is a link, fixed for the run: it is no input', node)
            self.link_target(init, None, node)
            kind = LINK
        elif isinstance(init.type, Many):
            if isinstance(init.type.of, FlowOf):
                self.fail(
                    'collection',
                    'a collection of flows is read where it stands, as count(c) or sum(c.actual_rate): '
                    'it is no value of its own',
                    node,
                )
            if not isinstance(init.type.of, Ent):
                self.fail(
                    'collection',
                    'a projection is no list of values: put the calculation on the member and reduce it, '
                    'as sum(c.f)',
                    node,
                )
            # A collection value is a collection written in place (a literal, the instances of a
            # template, a where or a by of one) or a read of one that another value holds, of the top
            # level, of a member (through its links) or of the event (`tanks = big`): it is the
            # collection that it names (re-audit 15). No other read gives a collection: a parameter
            # holds none.
            if node.modifier == 'input':
                self.fail('collection', f'{node.name} is a collection: it is no input', node)
            kind = COLLECTION
        return self.finish(path, scope, node, kind, value_type, init)

    def finish(self, path, scope, node, kind, value_type, init):
        """The declared value, with its range, its scale and its evidence."""
        lower = upper = scale = None
        if node.scale is not None:
            if not isinstance(value_type, Num):
                self.fail('range', f'a scale belongs to a number, and {node.name} is {value_type}', node)
            scale = self.bound(node.scale, scope, value_type, node)
        if node.range is not None:
            if not isinstance(value_type, Num):
                self.fail(
                    'range', f'a range belongs to a number, and {node.name} is {value_type}', node.range
                )
            lower, upper = (
                self.bound(end, scope, value_type, node) for end in (node.range.low, node.range.high)
            )
            floor = self.scale(value_type) if scale is None else self.exact(scale)
            if floor is not None:
                self.interval(
                    lower,
                    upper,
                    f'the range of {node.name}',
                    node.range,
                    (node.range.low, node.range.high),
                    floor=abs(floor),
                )
        if (
            kind == INPUT
            and isinstance(init, Drawn)
            and isinstance(init.type, Num)
            and isinstance(init.source, Distribution)
        ):
            lower, upper = self.support(init.source, lower, upper, node)
        found = DeclaredValue(
            path,
            node.name,
            kind,
            value_type,
            init,
            lower,
            upper,
            scale,
            node.modifier == 'readonly',
            node.text,
            self.evidence(node),
            node.line,
        )
        self.within(init, found, node)
        return found

    def initializer(self, node, scope, declared, retained, unit):
        """(kind, typed initializer) of a declaration."""
        value = node.value
        if isinstance(value, n.Formula):
            if node.modifier == 'input':
                self.fail('formula', 'an input is fixed for the run: it cannot keep a calculation', node)
            if declared is not None and not retained:
                self.fail(
                    'formula',
                    f'{node.name} keeps a calculation: declare it {node.name}: formula({declared})',
                    node,
                )
            body = self.expression(value.body, scope, unit if isinstance(unit, EnumOf) else None)
            self.no_draws(body, node, 'a formula')
            return FORMULA, Retain(body, body.type)
        if retained:
            self.fail('formula', f'{node.name} is declared a formula: its initializer is formula(...)', node)
        if isinstance(value, n.Collection) and not value.items:
            if not isinstance(declared, Many):
                self.fail(
                    'collection', f'an empty collection needs its type: {node.name}: <Template> = <>', node
                )
            return STATE, Read(('literal', ()), (), declared, True)
        if isinstance(value, n.Call) and (value.function in ARITY or value.function == 'categorical'):
            source = self.distribution(value, unit.of if isinstance(unit, Dist) else unit)
            return (INPUT if node.modifier == 'input' else DISTRIBUTION), source
        if (
            node.modifier == 'input'
            and isinstance(value, n.Method)
            and value.name == 'draw'
            and not value.args
            and isinstance(value.base, n.Call)
            and value.base.function in ARITY
        ):
            # The default of an input that draws keeps the support of its distribution as its range.
            source = self.distribution(value.base, unit if isinstance(unit, Num) else None)
            return INPUT, Drawn(source, source.type.of)
        init = self.expression(value, scope, unit)
        return (INPUT if node.modifier == 'input' else STATE), init

    def bound(self, node, scope, unit, owner):
        """An end of a range, or a scale: a bare number takes the value's unit."""
        if node is None:
            return None
        found = self.expression(node, scope, unit)
        if not compatible(found.type, unit):
            if _zero(found):
                return Const(found.value, unit)
            self.fail(
                'unit', f'the range and the scale of {owner.name} are in {unit}, not {found.type}', node
            )
        return found

    def interval(self, lower, upper, what, node, written=(None, None), floor=None):
        """Refuse a closed interval whose two ends are fixed when the model compiles and reversed,
        compared in their own units within the default comparison band: a range, a domain or the interval of a test, so that
        [6 h, 1 day] runs from 6 h to 24 h, [0.1 day, 2.4 h] holds one value and [5 h, 1 h] is an
        error wherever it stands (spec: reversed bounds are an error). An end that only a run knows
        is not compared here. `what` names the interval (`the range of x`); `written` are the ends as
        the text writes them, for an end that is no number written out."""
        ends = [None if end is None else self.exact(end) for end in (lower, upper)]
        if None in ends:
            return
        if not _literals(self.units).ordered('gt', *ends, floor=floor):
            return
        shown = [
            _written(end) if isinstance(end, Const) else written_as(text)
            for end, text in zip((lower, upper), written)
        ]
        self.fail(
            'range',
            f'{what} is reversed: [{shown[0]}, {shown[1]}]: an interval runs from its lower end to its upper end',
            node,
        )

    def within(self, found, value, node):
        """A value fixed when the model compiles (a starting value, a member's own value, a cell, the
        constant of an option or an edit) lies in the value's range, compared exactly in one unit
        (`exact`), so that `0.1 day` lies in [2.4 h, 2.4 h]."""
        at = self.exact(found) if isinstance(found, (Const, Apply)) else None
        if at is None:
            return
        if value.lower is not None and value.upper is not None:
            lo, hi = self.exact(value.lower), self.exact(value.upper)
            if lo is not None and hi is not None and lo > hi:
                floor = self.scale(value.type) if value.scale is None else self.exact(value.scale)
                if floor is None:
                    return
                collapsed = collapsed_interval(DEFAULT_FACTOR, abs(floor), lo, hi)
                if collapsed is not None:
                    midpoint, band = collapsed
                    if against('eq', at - midpoint, band):
                        return
        # A fixed authored datum must lie in the exact support of its declared range.
        for bound, op, side in ((value.lower, 'lt', 'below'), (value.upper, 'gt', 'above')):
            end = None if bound is None else self.exact(bound)
            if end is not None and against(op, *numeric_gap_band(0, 0, at, end)):
                if isinstance(found, Const):
                    shown = _written(found)
                else:
                    shown = f'{_fraction_text(at / self.scale(value.type))} {value.type.unit}'.strip()
                self.fail('range', f'{shown} is {side} the range of {value.name}', node)

    def categorical(self, node, expected):
        """`categorical(FIXED: 0.7, FAILED: 0.3)`: a weight, a plain number written in place, for each
        outcome. Its enum is the one that its place expects (`expected`), of which each outcome is a
        member, or else the enum of its outcomes in written order."""
        if node.args or not node.named:
            self.fail(
                'arguments',
                'categorical names each outcome with its weight: categorical(A: 0.7, B: 0.3)',
                node,
            )
        weights = []
        for name, arg in node.named:
            found = literal(arg)
            if found is None or isinstance(found[1], n.Quantity):
                self.fail('distribution', f'the weight of {name} is a plain number written in place', arg)
            weight = _parameter(found[0], decimal(arg))
            if weight < 0:
                self.fail('distribution', f'the weight of {name} is not negative', arg)
            weights.append(weight)
        if not any(weights):
            self.fail('distribution', 'the weights of a categorical are not all zero', node)
        if not any(map(float, weights)):
            self.fail(
                'distribution', 'the weights of a categorical are all zero at execution precision', node
            )
        outcomes = tuple(name for name, _ in node.named)
        enum = expected if isinstance(expected, EnumOf) else EnumOf(outcomes)
        for name in outcomes:
            if name not in enum.members:
                self.fail(
                    'enum_member', f'{name} is not a member of {enum}' + close(name, enum.members), node
                )
        return Distribution('categorical', tuple(weights), Dist(enum), outcomes)

    def distribution(self, node, unit):
        """A distribution of numbers: its value arguments take the declared unit, or they write one. A
        categorical takes the enum of its place (`unit`)."""
        if node.function == 'categorical':
            return self.categorical(node, unit)
        if len(node.args) not in ARITY[node.function]:
            counts = ' or '.join(str(count) for count in ARITY[node.function])
            self.fail('arguments', f'{node.function} takes {counts} arguments', node)
        found = [literal(arg) for arg in node.args]
        if any(item is None for item in found):
            # The program holds a distribution's parameters as numbers (`refs.Distribution`); a
            # distribution that a run should change is an input that holds it (D2).
            self.fail(
                'distribution',
                f'the parameters of {node.function} are numbers written in place, as uniform(1 h, 3 h): an '
                'input that holds a distribution is what a run changes (D2)',
                node,
            )
        if isinstance(unit, EnumOf):
            self.fail('type', f'{node.function}(...) gives numbers, and its place takes {unit}', node)
        shapes = SHAPES.get(node.function, set())
        written = {
            item[1].unit
            for k, item in enumerate(found)
            if k not in shapes and isinstance(item[1], n.Quantity)
        }
        target = unit
        if target is None and written:
            first = next(
                item for k, item in enumerate(found) if k not in shapes and isinstance(item[1], n.Quantity)
            )
            target = self.quantity(1, first[1], TOP).type
        target = target or PLAIN
        params = []
        for k, (value, written_node) in enumerate(found):
            exact = decimal(node.args[k])
            if k in shapes:
                if isinstance(written_node, n.Quantity):
                    self.fail('unit', f'the argument {k + 1} of {node.function} is a plain number', node)
            elif isinstance(written_node, n.Quantity):
                own = self.quantity(1, written_node, TOP).type
                if own.dimension != target.dimension:
                    self.fail('unit', f'{node.function} takes its arguments in {target}, not {own}', node)
                exact *= self.scale(own) / self.scale(target)
            elif target.dimension and unit is None:
                self.fail(
                    'unit', f'{node.function} has an argument with no unit beside one in {target}', node
                )
            try:
                params.append(_parameter(value, exact))
            except OverflowError:
                self.fail(
                    'number', f'argument {k + 1} of {node.function} overflows in {target}', node.args[k]
                )
        broken = _broken(node.function, params)
        if broken is not None:
            names = ', '.join(PARAMETERS[node.function][: len(params)])
            self.fail('distribution', f'{written_as(node)}: {node.function}({names}) needs {broken}', node)
        return Distribution(node.function, tuple(params), Dist(target))

    def support(self, source, lower, upper, node):
        """The range of an input whose default draws: the written range, which must hold the support
        of the distribution, or the support of a bounded distribution."""
        unit = source.type.of
        ends = numeric_support(source.family, source.params)
        if lower is None and upper is None:
            if math.inf in ends:
                return None, None
            return Const(ends[0], unit), Const(ends[1], unit)
        scale = self.scale(unit)
        for end, bound, sign in ((ends[0], lower, 1), (ends[1], upper, -1)):
            limit = None if bound is None else self.exact(bound)
            if limit is None:
                continue
            # A bound that cuts an unbounded support, or cuts into a bounded one, holds less than it.
            if not math.isfinite(end) or sign * (limit - rational(end) * scale) > 0:
                shown = [_fraction_text(part) if isinstance(part, Fraction) else str(part) for part in ends]
                self.fail(
                    'range',
                    f'the range of {node.name} must hold the support of its distribution, '
                    f'[{shown[0]}, {shown[1]}] {unit.unit}'.rstrip(),
                    node,
                )
        return lower, upper

    def drawn(self, node, scope, expected):
        """`d.draw()`: of a distribution written in place (its value arguments take the unit of the
        place, as when the draw is the whole initializer), or of a value that holds one."""
        if node.args:
            self.fail('arguments', '.draw() takes no argument', node)
        base = node.base
        if isinstance(base, n.Call) and (base.function in ARITY or base.function == 'categorical'):
            source = self.distribution(base, expected if isinstance(expected, (Num, EnumOf)) else None)
            return Drawn(source, source.type.of)
        if not isinstance(base, (n.Name, n.Member)):
            self.fail('draw', '.draw() takes a distribution, or a value that holds one', node)
        source = self.path(base, scope)
        if not isinstance(source.type, Dist):
            self.fail('draw', f'.draw() takes a distribution, and this is {source.type}', node)
        return Drawn(source, source.type.of)

    def no_draws(self, expression, node, what):
        """A formula, and a condition that is read again, makes no draw: it may read a stored draw."""
        for _ in draws_of(expression):
            self.fail(
                'formula_draws',
                f'{what} is read again, and a read never draws: store the drawn value in a local',
                node,
            )

    def scale(self, kind):
        """The size of one of a number's unit in the canonical unit of its dimension, exactly."""
        return self.units.of(kind.unit)[1] if kind.unit else Fraction(1)

    def exact(self, expression):
        """The value of an expression fixed when the model compiles, exactly (`exact_value`)."""
        return exact_value(expression, self.units)

    def evidence(self, node):
        """The records that a line cites and those written under it; each cited name is a record."""
        found = (*node.cites, *node.evidence)
        for item in found:
            if isinstance(item, n.Cite) and item.name not in self.records:
                self.fail(
                    'unknown_record',
                    f'@{item.name} names no record of the model' + close(item.name, self.records),
                    item,
                )
        return found

    # ---- flows and endpoints ---------------------------------------------------------------------

    def flow_type(self, path, owner, node):
        """The type of a declared flow: a directed flow, a reversible route or a flow with legs."""
        if node.arrow == '->':
            return FlowOf(self.rate(owner, node), path)
        if node.arrow == '<->':
            return RouteOf(self.rate(owner, node), path)
        return LegsOf(path)

    def rate(self, owner, node):
        """The type of the rates of a directed flow, a leg or a route, from its ends (a store's unit
        per hour), or for `SOURCE -> SINK` from a rate written with its unit."""
        # As the program's builder does: a rate written with its unit first, then a store's unit per hour.
        for item in node.properties:
            found = literal(item.value.body if isinstance(item.value, n.Formula) else item.value)
            if (
                item.path[-1] in ('request', 'capacity')
                and found is not None
                and isinstance(found[1], n.Quantity)
            ):
                return self.quantity(1, found[1], self.scope_of(owner)).type
        for end in (node.source, node.sink):
            if end not in (('SOURCE',), ('SINK',)):
                return self.per_hour(self.store(end, owner, node).type)
        self.fail('flow_units', f'flow {node.name}: SOURCE -> SINK needs a rate written with its unit', node)

    def store(self, end, owner, node):
        """The `Read` of the stored number that an end of a flow names, in the scope of the flow's
        owner: a store of its own member (`this.water`), through links (`this.origin.power`), of a
        named member (`reservoir.water`, `sites.junction.power`) or of the top level."""
        written = n.Name(end[0], line=node.line, column=node.column)
        for name in end[1:-1]:
            written = n.Member(written, name, line=node.line, column=node.column)
        spelled = '.'.join(end)
        found = self.path(written, self.scope_of(owner))
        if len(end) > 1:
            kind = found.type.of if isinstance(found.type, Many) else found.type
            if isinstance(kind, Ent) and f'{kind.template}.{end[-1]}' not in self.syntax:
                self.fail('flow_end', f'{spelled} is no stored number of {kind.template}', node)
            found = self.step(found, end[-1], node)
        if isinstance(found.type, Many):
            self.fail('flow_end', f'{spelled} is a projection: an end of a flow is one stored number', node)
        if found.start[0] == 'local' and not found.steps and isinstance(self.syntax[found.part][1], n.Param):
            self.fail(
                'parameter_end',
                f'{spelled} is a parameter, a value copy that holds no stock: an event that takes from a store '
                'takes its entity, as source: Tank, and uses source.water (D13)',
                node,
            )
        if not found.stored:
            self.fail(
                'flow_end',
                f'{spelled} is no stored number: a flow ends at a stored value, SOURCE or SINK',
                node,
            )
        return found

    def flow(self, path, owner, node):
        """A declared flow: a directed flow (or a leg), a reversible route (`DeclaredRoute`), or a
        flow with legs (`DeclaredLegs`). Each end is `SOURCE`, `SINK` or a stored number of the
        dimension of the rates per time; the parser keeps `SOURCE` and `SINK` off a route."""
        if not node.arrow:
            return self.legs(path, owner, node)
        rate = self.rate(owner, node)
        ends = []
        for end in (node.source, node.sink):
            if end in (('SOURCE',), ('SINK',)):
                ends.append(end[0])
                continue
            store = self.store(end, owner, node)
            if self.per_hour(store.type).dimension != rate.dimension:
                self.fail(
                    'flow_units',
                    f'flow {node.name}: its ends and its rates are of two dimensions '
                    f'({store.type} against {rate}; a rate is its stock per time)',
                    node,
                )
            ends.append(store)
        route = node.arrow == '<->'
        settings = {}
        for item in node.properties:
            key = '.'.join(item.path)
            if key not in ('request', 'capacity'):
                what = 'a reversible route' if route else 'a directed flow'
                self.fail('property', f'{what} takes request and capacity, not {key}', item)
            if key in settings:
                self.fail('property', f'{key} is given twice', item)
            settings[key] = self.rate_setting(item, self.scope_of(owner), rate, f'the {key} of {node.name}')
        return (DeclaredRoute if route else DeclaredFlow)(
            path,
            node.name,
            ends[0],
            ends[1],
            rate,
            settings.get('request'),
            settings.get('capacity'),
            node.text,
            self.evidence(node),
            node.line,
        )

    def legs(self, path, owner, node):
        """A flow with legs: each leg a directed flow of its own, at `path.leg`, named once, and by no
        name that the flow reads or refuses itself (`restore.served_fraction`, `restore.request`)."""
        legs, seen = [], {}
        for leg in node.legs:
            if leg.name in ('served_fraction', *FLOW_READS):
                self.fail(
                    'reserved',
                    f'a leg is not named {leg.name}: {node.name}.{leg.name} reads the flow with legs',
                    leg,
                )
            if leg.name in seen:
                self.fail(
                    'duplicate_name',
                    f'{node.name} has two legs named {leg.name}; the first is {self.on_line(seen[leg.name])}',
                    leg,
                )
            seen[leg.name] = leg.line
            legs.append(self.flow(f'{path}.{leg.name}', owner, leg))
        return DeclaredLegs(path, node.name, tuple(legs), node.text, self.evidence(node), node.line)

    def end(self, base, flow, name, node):
        """`f.source` or `f.sink` of one declared flow, leg or leg of a route (`base` reads the flow):
        the store at that end, read as that store, with its amount and the steps of a store. The ends
        of a flow are fixed for the run, so the read goes to the store's own path, from the member of
        the flow: `this.main.sink` of `flow main: SOURCE -> this.water` reads `this.water`, and
        `Site.instances.restore.labor.sink` reads `Site.instances.crew.used`. An end at SOURCE or SINK
        holds nothing to read, and a member of an endpoint's `flows` may end anywhere."""
        if not flow.flow:
            self.fail(
                'flow_end',
                f'a member of flows may end at any store, or at SOURCE or SINK: read the {name} of a '
                f'declared flow, as this.main.{name}',
                node,
            )
        owner, ends = self.ends_of(flow)
        end = ends[0] if name == 'source' else ends[1]
        if end in (('SOURCE',), ('SINK',)):
            self.fail('flow_end', f'the {name} of {flow.flow} is {end[0]}, which holds nothing to read', node)
        store = self.store(end, owner, node)
        if owner in self.scopes:
            # A flow of an occurrence: inside its event its ends are read as written there.
            if base.start[0] != 'local':
                self.fail(
                    'flow_end',
                    f'the {name} of a flow of an occurrence is read inside its event; outside it, read the '
                    'store by its path',
                    node,
                )
            return store
        many = isinstance(base.type, Many)
        if store.start != ('this',):
            if many:
                self.fail(
                    'collection',
                    f'the {name} of {flow.flow} is {".".join(end)} for every member: read it by its path',
                    node,
                )
            return store
        # The flow's own steps follow its member's: one for a flow, two for a leg (`restore.labor`).
        member = base.steps[: -flow.flow.count('.')]
        kind = Many(store.type, base.type.key) if many else store.type
        return Read(base.start, (*member, *store.steps), kind, stored=not many)

    def ends_of(self, flow):
        """The owner of a declared flow, leg or leg of a route, and its two ends as written: a leg of
        a route runs from its route's first end (`forward`) or from its second (`backward`)."""
        if flow.flow in self.syntax:
            owner, node = self.syntax[flow.flow]
            return owner, (node.source, node.sink)
        parent, _, name = flow.flow.rpartition('.')
        owner, node = self.syntax[parent]
        if flow.view:
            return owner, ((node.source, node.sink) if name == 'forward' else (node.sink, node.source))
        leg = next(each for each in node.legs if each.name == name)
        return owner, (leg.source, leg.sink)

    def rate_setting(self, item, scope, rate, what):
        """A request or a capacity (of a flow or of an endpoint): a rate of the dimension of `rate`,
        captured once, or a `Retain`; a bare zero takes the rate's unit."""
        if isinstance(item.value, n.Formula):
            body = self.expression(item.value.body, scope)
            self.no_draws(body, item, what)
            found = Retain(body, body.type)
        else:
            found = self.expression(item.value, scope)
        if not compatible(found.type, rate):
            if not _zero(found):
                self.fail('unit', f'{what} is a rate in {rate}, not {found.type}', item)
            found = Const(found.value, rate)
        return found

    def declared_value(self, path, owner, node):
        """A value with the settings of its outflow and its inflow, written under it: only a stored
        number has them. Each setting is resolved after the value, so that it may read the store (a
        request that fills a tank to a level). A setting with a problem is reported, or deferred,
        and leaves the value as it is."""
        value = self.value(path)
        if not node.properties:
            return value
        if not _stored(value):
            self.report(
                'property',
                f'{value.name} is no stored number: only a store takes the settings of its outflow and '
                'its inflow (capacity, request, allocation)',
                node.properties[0].line,
            )
            return value
        scope, sides = self.scope_of(owner), {}
        for item in node.properties:
            key = '.'.join(item.path)
            side = item.path[0]
            if len(item.path) != 2 or side not in SIDES or item.path[1] not in SETTINGS:
                self.report(
                    'property',
                    f'{key} is no setting of a store: a store takes outflow.capacity, outflow.request, '
                    'outflow.allocation and the same of inflow',
                    item.line,
                )
                continue
            settings = sides.setdefault(side, {'line': item.line})
            if item.path[1] in settings:
                self.report('property', f'{key} is given twice', item.line)
                continue
            try:
                if item.path[1] == 'allocation':
                    settings['allocation'] = self.allocation(item.value, scope)
                else:
                    rate = self.per_hour(value.type)
                    settings[item.path[1]] = self.rate_setting(item, scope, rate, f'{value.name}.{key}')
            except Refused as refused:
                if refused.code != 'depends':
                    self.report(refused.code, refused.message, refused.line or item.line, refused.column)
        found = {
            side: DeclaredEndpoint(
                f'{value.path}.{side}',
                settings.get('capacity'),
                settings.get('request'),
                settings.get('allocation', ('proportional',)),
                settings['line'],
            )
            for side, settings in sides.items()
        }
        value = replace(value, outflow=found.get('outflow'), inflow=found.get('inflow'))
        self.done[value.path] = value
        return value

    def allocation(self, node, scope):
        """`proportional()`, or `priority(...)` over flows, first to last: each a directed flow
        (`hospital.delivery`, `this.main`), a leg of a flow with legs (`this.restore.labor`), a leg of
        a route (`this.link.forward`), or a projection of these over a collection
        (`Customer.instances.by(rank).delivery`, ranked by the collection's keys), each named once.
        A bare route or a flow with legs is no claim at one endpoint. That each flow is incident at
        the store, in its direction, is the program's rule (`check.priority_item`)."""
        if not (isinstance(node, n.Call) and node.function in ALLOCATIONS):
            self.fail('allocation', 'an allocation is priority(...) or proportional()', node)
        if node.function == 'proportional':
            if node.args:
                self.fail('arguments', 'proportional() takes no argument', node)
            return ('proportional',)
        if not node.args:
            self.fail('arguments', 'priority(...) names the flows that it serves first, in order', node)
        items = []
        for arg in node.args:
            if not isinstance(arg, (n.Name, n.Member, n.Method)):
                self.fail('priority_item', 'priority(...) names flows, as hospital.delivery', arg)
            found = self.path(arg, scope)
            kind = found.type.of if isinstance(found.type, Many) else found.type
            if isinstance(kind, RouteOf):
                self.fail(
                    'priority_item',
                    'a reversible route is no claim at one endpoint: name its leg in the direction of '
                    'this endpoint, as link.forward or link.backward',
                    arg,
                )
            if isinstance(kind, LegsOf):
                self.fail(
                    'priority_item',
                    'a flow with legs is no claim at one endpoint: name its leg at this endpoint, as '
                    'restore.labor',
                    arg,
                )
            if not isinstance(kind, FlowOf) or not kind.flow:
                what = "an endpoint's collection of flows" if isinstance(kind, FlowOf) else str(found.type)
                self.fail(
                    'priority_item',
                    f'priority(...) ranks flows, or a projection of flows (customers.by(rank).delivery), '
                    f'not {what}',
                    arg,
                )
            items.append(found)
        if len(set(items)) < len(items):
            self.fail('priority_item', 'priority(...) names each flow once', node)
        return ('priority', tuple(items))

    def assertion(self, path, scope, node):
        """An assertion: over what is fixed for the run (`fixed`), checked once; over state, checked
        after every round, every moment and every contact between moments. It makes no draw."""
        test = self.expression(node.test, scope)
        self.want_bool(test, node, 'assert')
        self.no_draws(test, node, 'an assertion')
        return DeclaredAssert(path, test, node.text, self.evidence(node), node.line, self.over_inputs(test))

    def over_inputs(self, expression):
        """Whether an expression reads only what is fixed for the run, also through the formulas that
        it reads: each formula is looked at once, on an explicit stack (`walked`), so a deep chain of
        shared formulas costs its length and no depth of calls."""
        return walked(self._over_inputs(expression))

    def _over_inputs(self, expression):
        for read in reads_of(expression):
            if read.fixed:
                continue
            if not read.formula:
                return False
            if read.formula not in self.inputs_only:
                template, _, name = read.formula.rpartition('.')
                # A member written by hand may replace its template's formula with one of its own.
                replaced = any(
                    member.type.name == template and any(item.path == (name,) for item in member.properties)
                    for member in self.instances.values()
                )
                # A formula met again on its own way is not shown to read inputs only.
                self.inputs_only[read.formula] = False
                found = not replaced and (yield self._over_inputs(self.value(read.formula).init.body))
                self.inputs_only[read.formula] = found
            if not self.inputs_only[read.formula]:
                return False
        return True

    # ---- events --------------------------------------------------------------------------------------

    def event(self, path, owner, node):
        """An event: its parameters, its locals and flows (whose plain initializers run in written
        order, D14), its steps and its triggers."""
        seen = {}
        for item in (*node.params, *node.locals):
            if item.name in seen:
                self.fail(
                    'duplicate_name',
                    f'{path}.{item.name} is declared twice; the first is {self.on_line(seen[item.name])}',
                    item,
                )
            seen[item.name] = item.line
        params = tuple(self.value(f'{path}.{item.name}') for item in node.params)
        locals_ = []
        for index, item in enumerate(node.locals):
            own = f'{path}.{item.name}'
            found = (
                self.flow(own, path, item)
                if isinstance(item, n.Flow)
                else self.declared_value(own, path, item)
            )
            self.local_order(node, index, found, item)
            locals_.append(found)
        scope = self.scopes[path]
        steps = tuple(self.timing(f'{path}.step[{k}]', scope, item) for k, item in enumerate(node.steps))
        triggers = tuple(
            self.trigger(f'{path}.when[{k}]', owner, item) for k, item in enumerate(node.triggers)
        )
        return DeclaredEvent(
            path,
            node.name,
            params,
            tuple(locals_),
            steps,
            triggers,
            node.text,
            self.evidence(node),
            node.line,
        )

    def local_order(self, event, index, found, node):
        """D14: a plain initializer of a local, and a plain property of a local flow, reads the
        parameters and the locals above it; only a `formula(...)` may read a local below it."""
        below = {item.name for item in event.locals[index:]}
        if isinstance(found, DeclaredValue):
            plain = [] if isinstance(found.init, Retain) else [found.init]
            plain += [found.lower, found.upper]
        else:
            flows = found.legs if isinstance(found, DeclaredLegs) else (found,)
            plain = [setting for flow in flows for setting in (flow.request, flow.capacity)]
        for expression in plain:
            if expression is None or isinstance(expression, Retain):
                continue
            for read in reads_of(expression):
                if read.start[0] == 'local' and read.start[1] in below:
                    self.fail(
                        'local_order',
                        f'{node.name} reads {read.start[1]}, a local declared below it: a plain initializer '
                        'runs in written order (D14), and a formula(...) is read later',
                        node,
                    )

    def timing(self, path, scope, node):
        """A timing step: a stage (`after D:`, `after D when C:`), a wait (`after D`) or a gate."""
        if isinstance(node, n.Gate):
            return DeclaredGate(path, self.condition(node.test, scope, node, 'until'), node.line)
        delay = self.duration(node.delay, scope, node, 'after')
        guard = None if node.guard is None else self.test(node.guard, scope, node, 'when')
        body = self.statements(path, 'do', scope, node.body)
        return DeclaredStage(path, delay, body, guard, node.wait, node.text, self.evidence(node), node.line)

    def duration(self, node, scope, line, what):
        """A time: the delay of a stage or the duration of a reset; a bare zero is 0 h."""
        found = self.expression(node, scope)
        hours = self.num('h', line)
        if _zero(found):
            return Const(found.value, hours)
        if not (isinstance(found.type, Num) and found.type.dimension == hours.dimension):
            self.fail('unit', f'{what} takes a time, not {found.type}', line)
        return found

    def test(self, node, scope, line, what):
        """A yes/no that is read once, when its statement runs or its stage comes due."""
        found = self.expression(node, scope)
        self.want_bool(found, line, what)
        return found

    def condition(self, node, scope, line, what):
        """A yes/no that the run reads again (a gate, a trigger, a reset): it makes no draw."""
        found = self.test(node, scope, line, what)
        self.no_draws(found, line, f'the condition of {what}')
        return found

    def statements(self, path, label, scope, body):
        """The statements of a body, at `path.label[k]` (`step[0].do[1]`, `do[0].then[0]`)."""
        return tuple(self.statement(f'{path}.{label}[{k}]', scope, item) for k, item in enumerate(body or ()))

    def statement(self, path, scope, node):
        if isinstance(node, n.Assign):
            return self.assignment(path, scope, node)
        if isinstance(node, n.Move):
            return self.transfer(path, scope, node)
        if isinstance(node, n.Start):
            return self.start(path, scope, node)
        if isinstance(node, n.If):
            test = self.test(node.test, scope, node, 'if')
            then = self.statements(path, 'then', scope, node.then)
            return DeclaredIf(path, test, then, self.statements(path, 'else', scope, node.orelse), node.line)
        return self.switch(path, scope, node)

    def through_end(self, node, scope):
        """Refuse a target through `f.source` or `f.sink`: the front end reads either as the store at
        that end, so an assignment would reach the store (`fixed_write`)."""
        while isinstance(node, n.Member):
            if node.name in ENDS:
                base = self.path(node.base, scope)
                kind = base.type.of if isinstance(base.type, Many) else base.type
                if isinstance(kind, FlowOf):
                    self.fail(
                        'fixed_write',
                        f'{node.name} of a flow is the store at that end, and the ends of a flow are fixed '
                        'for the run: assign to the store by its own path',
                        node,
                    )
            node = node.base

    def assignment(self, path, scope, node):
        """`target = value`, `+=` or `-=`: a writable value (stored, a local or a parameter's copy, a
        formula or a distribution that a stage replaces), or a setting of a flow or of an endpoint.
        An input and a link are fixed (`fixed_write`), a readonly value is assigned by no statement
        (`readonly_write`), and what the run computes neither (`result_write`)."""
        self.through_end(node.target, scope)
        base = self.path(node.target.base, scope) if isinstance(node.target, n.Member) else None
        if base is not None and isinstance(base.type, EndOf) and node.target.name == 'allocation':
            if node.op != '=':
                self.fail('assign_value', 'an allocation takes =', node)
            target = Read(base.start, (*base.steps, 'allocation'), base.type)
            return DeclaredAssign(path, target, '=', self.allocation(node.value, scope), node.line)
        target = self.path(node.target, scope)
        spelled = '.'.join(target.steps) or getattr(node.target, 'name', '')
        if isinstance(target.type, Many):
            self.fail('collection', f'{spelled} is a projection: a statement assigns one value', node)
        inner = None if base is None else base.type
        name = getattr(node.target, 'name', '')
        if isinstance(inner, (FlowOf, RouteOf, LegsOf, EndOf, Occ)) and not target.part:
            if name in RESULTS or (isinstance(inner, FlowOf) and inner.view):
                self.fail('result_write', f'the run computes {spelled}: no statement assigns it', node)
            if node.op != '=' and isinstance(node.value, n.Formula):
                self.fail('assign_value', f'{spelled} takes a formula with =', node)
            item = n.Property((name,), node.value, line=node.line, column=node.column)
            found = self.rate_setting(item, scope, target.type, spelled)
            self.lifetime(target, found, scope, written_as(node.target), node)
            return DeclaredAssign(path, target, node.op, found, node.line)
        if not target.part:
            self.fail('fixed_write', f'{spelled} is no value that a statement assigns', node)
        value = self.done.get(target.part) or self.value(target.part)
        if value.kind == UNKNOWN:
            self.fail(
                'result_write',
                f'{spelled} is a result of the solver {target.part.rpartition(".")[0]}, read-only to its '
                'callers: change its inputs',
                node,
            )
        if value.kind in (INPUT, LINK) or isinstance(value.type, Ent):
            self.fail('fixed_write', f'{spelled} is fixed for the run: no statement assigns it', node)
        if isinstance(value.type, Occ):
            self.fail(
                'fixed_write',
                f'{spelled} names an occurrence, set when its own occurrence enters: no statement assigns it',
                node,
            )
        if value.readonly:
            self.fail(
                'readonly_write',
                f'{spelled} is readonly, which no statement assigns: a flow or a move can still change a stock',
                node,
            )
        if value.kind == FORMULA:
            if node.op != '=' or not isinstance(node.value, n.Formula):
                self.fail(
                    'assign_value',
                    f'{spelled} keeps a calculation: a stage gives it formula(...) with =',
                    node,
                )
            body = self.expression(
                node.value.body, scope, value.type if isinstance(value.type, EnumOf) else None
            )
            self.no_draws(body, node, 'a formula')
            if not compatible(body.type, value.type):
                self.fail('unit', f'{spelled} is {value.type}, and this formula {body.type}', node)
            self.lifetime(target, Retain(body, body.type), scope, written_as(node.target), node)
            return DeclaredAssign(path, target, '=', Retain(body, body.type), node.line)
        if value.kind == DISTRIBUTION:
            call = node.value
            if node.op != '=' or not (
                isinstance(call, n.Call) and (call.function in ARITY or call.function == 'categorical')
            ):
                self.fail(
                    'assign_value', f'{spelled} holds a distribution: a stage gives it another with =', node
                )
            found = self.distribution(call, value.type.of)
            if not compatible(found.type.of, value.type.of):
                self.fail('unit', f'{spelled} is {value.type}, and this {found.type}', node)
            return DeclaredAssign(path, target, '=', found, node.line)
        if isinstance(node.value, n.Formula):
            self.fail('assign_value', f'{spelled} keeps no calculation: a stage gives it a value', node)
        found = self.expression(node.value, scope, value.type if isinstance(value.type, EnumOf) else None)
        if node.op != '=' and not isinstance(value.type, Num):
            self.fail('assign_value', f'{spelled} is {value.type}, which takes =, not {node.op}', node)
        if not compatible(found.type, value.type):
            if not (_zero(found) and isinstance(value.type, Num)):
                code = 'unit' if isinstance(found.type, Num) and isinstance(value.type, Num) else 'type'
                self.fail(code, f'{spelled} is {value.type}, and this value is {found.type}', node)
            found = Const(found.value, value.type)
        return DeclaredAssign(path, target, node.op, found, node.line)

    def lifetime(self, target, found, scope, spelled, node):
        """Refuse a formula that a stage installs where it outlives the stage's occurrence and that
        reads that occurrence's own names: a parameter, a local, a flow of it (spec, "State owned by an
        invocation": a live formula installed in a longer-lived entity that would read a retired local
        is refused, and the calculated scalar is safe). A formula may read only what lives at least as
        long as it: a place lives as long as the owner of the target that the statement resolves to
        (`own_place`), whatever its spelling, so a value or a setting of an entity or of the top level
        lives for the run, reached through `this`, a link, a parameter that names an entity or a member
        of a collection, and a local of another occurrence (reached through a reference to it, or
        `.at(t)`) as long as that one; this occurrence's own locals and the settings of its own flows
        and stores live as long as it does."""
        if scope.event is None or not isinstance(found, Retain) or self.own_place(target, scope):
            return
        for read in _local_reads(found.body):
            name = read.start[1]
            syntax = self.syntax[f'{scope.event}.{name}'][1]
            what = (
                'parameter'
                if isinstance(syntax, n.Param)
                else 'flow'
                if isinstance(syntax, n.Flow)
                else 'local'
            )
            self.fail(
                'lifetime',
                f'{spelled} outlives this occurrence of {scope.event}, and its formula reads {name}, a {what} '
                f'of the occurrence, which ends with it: give {spelled} the value now ({spelled} = ... without '
                'formula), or read only what lives as long as it',
                node,
            )

    def own_place(self, target, scope):
        """Whether an assignment's target is a place of the stage's own occurrence, by the owner of the
        target that it resolves to: one of the occurrence's bare names (a local, a parameter's copy, a
        flow or a store of its own) and the settings of its own flows and stores. A step from a bare
        name that refers to something else reaches a place of that thing: an entity that a parameter
        names, another occurrence that a saved reference names, a member of a collection."""
        if target.start[0] != 'local':
            return False
        head = self.name(n.Name(target.start[1]), scope)
        return not isinstance(head.type, (Ent, Occ, Many))

    def transfer(self, path, scope, node):
        """`move amount from source to destination`: an amount of the dimension of two stores, each a
        stored number (readonly or not); a formula, an input or a parameter is no store."""
        ends = []
        for item, what in ((node.source, 'from'), (node.destination, 'to')):
            found = self.path(item, scope)
            if isinstance(found.type, Many) or not found.stored:
                self.fail('move_end', f'a move takes {what} a stored number, and this is {found.type}', node)
            ends.append(found)
        if ends[0].type.dimension != ends[1].type.dimension:
            self.fail(
                'unit', f'a move joins two stores of one dimension: {ends[0].type} and {ends[1].type}', node
            )
        amount = self.expression(node.amount, scope)
        self.want_number(amount, node, 'move')
        if amount.type.dimension != ends[0].type.dimension:
            if not _zero(amount):
                self.fail('unit', f'the amount of a move is in {ends[0].type}, not {amount.type}', node)
            amount = Const(amount.value, ends[0].type)
        return DeclaredMove(path, amount, ends[0], ends[1], node.line)

    def start(self, path, scope, node):
        """`event.start(args)`: of an event, or of one on each member of a collection; one argument for
        each parameter, of its type, evaluated by the caller left to right."""
        call = node.call
        event = self.path(call.base, scope)
        kind = event.type.of if isinstance(event.type, Many) else event.type
        if not isinstance(kind, EventOf):
            self.fail('start', f'.start(...) starts an event, not {event.type}', node)
        params = [self.value(f'{kind.event}.{item.name}') for item in self.syntax[kind.event][1].params]
        if len(call.args) != len(params):
            names = ', '.join(param.name for param in params) or 'none'
            self.fail(
                'arguments',
                f'{kind.event} takes {len(params)} argument{"s" if len(params) != 1 else ""} ({names}), '
                f'not {len(call.args)}',
                node,
            )
        args = []
        for arg, param in zip(call.args, params):
            found = self.expression(arg, scope, param.type if isinstance(param.type, EnumOf) else None)
            # A literal zero adopts its numeric parameter's unit in the program.
            # Program.check validates the signature of both ways of authoring the call.
            if _zero(found) and isinstance(param.type, Num) and found.type != param.type:
                found = Const(found.value, param.type)
            args.append(found)
        return DeclaredStart(path, event, tuple(args), node.line)

    def switch(self, path, scope, node):
        """`switch selector:` over an enum: each case a member of it, with a guard read once before the
        selector, and an optional `else`."""
        selector = self.expression(node.selector, scope)
        if not isinstance(selector.type, EnumOf):
            hint = ': a yes/no branches with if C: and else:' if selector.type == BOOL else ''
            self.fail('type', f'switch takes a member of an enum, not {selector.type}{hint}', node)
        cases = []
        for case in node.cases:
            if case.member not in selector.type.members:
                self.fail(
                    'enum_member',
                    f'{case.member} is not a member of {selector.type}'
                    + close(case.member, selector.type.members),
                    case,
                )
            own = f'{path}.{case.member}'
            guard = None if case.guard is None else self.test(case.guard, scope, case, 'a guard')
            body = self.statements(own, 'do', scope, case.body)
            cases.append(
                DeclaredCase(own, case.member, body, guard, case.text, self.evidence(case), case.line)
            )
        orelse = self.statements(path, 'else', scope, node.orelse)
        return DeclaredSwitch(path, selector, tuple(cases), orelse, node.line)

    def trigger(self, path, owner, node):
        """`when test:` of an event, once for each receiver: its condition reads the receiver; its
        captures, in written order, the receiver and the captures above them; its starts and its
        reset, the receiver and every capture. A trigger has no occurrence of its own."""
        test = self.condition(node.test, Scope(owner, trigger=path), node, 'when')
        captures, taken = [], ()
        for capture in node.captures:
            own = f'{path}.{capture.name}'
            if own in taken:
                self.fail('duplicate_name', f'the capture {capture.name} is written twice', capture)
            found = self.expression(capture.value, Scope(owner, captures=taken, trigger=path))
            if not isinstance(found.type, (Num, Word, EnumOf)):
                self.fail(
                    'type',
                    f'a capture holds a number, a yes/no, a text or a member of an enum, not {found.type}',
                    capture,
                )
            self.done[own] = DeclaredValue(own, capture.name, STATE, found.type, found, line=capture.line)
            captures.append(self.done[own])
            taken += (own,)
        scope = Scope(owner, captures=taken, trigger=path)
        starts = tuple(self.start(f'{path}.do[{k}]', scope, item) for k, item in enumerate(node.starts))
        reset = None
        if node.reset is not None:
            if node.reset.kind == 'when':
                reset = ('when', self.condition(node.reset.value, scope, node.reset, 'reset when'))
            else:
                reset = ('after', self.duration(node.reset.value, scope, node.reset, 'reset after'))
        return DeclaredTrigger(
            path, test, tuple(captures), starts, reset, node.text, self.evidence(node), node.line
        )

    # ---- solvers -----------------------------------------------------------------------------------

    def solver(self, path, owner, node):
        """A solver of an entity or a template: its inputs, read in the owner's scope; its new
        unknowns and the fields that it determines; its constraints (each a yes/no) and its
        objectives (each a number), read in the solver's scope, where a bare name is an input or an
        unknown. None of them draws: a solve reads them again."""
        seen = {}
        unknowns = [entry for entry in node.solve_for if isinstance(entry, n.Unknown)]
        for item in (*node.inputs, *unknowns):
            if item.name in seen:
                self.fail(
                    'duplicate_name',
                    f'{path}.{item.name} is declared twice; the first is {self.on_line(seen[item.name])}',
                    item,
                )
            seen[item.name] = item.line
        scope = self.scopes[path]
        inputs = tuple(self.binding(f'{path}.{item.name}') for item in node.inputs)
        declared = tuple(self.value(f'{path}.{item.name}') for item in unknowns)
        solve_for = tuple(
            self.determined(entry, scope) for entry in node.solve_for if not isinstance(entry, n.Unknown)
        )
        constraints, objective = [], []
        for k, item in enumerate(node.constraints):
            test = self.expression(item, scope)
            self.want_bool(test, item, 'a constraint')
            self.no_draws(test, item, 'a constraint')
            constraints.append(DeclaredRelation(f'{path}.constraint[{k}]', test, line=item.line))
        for k, item in enumerate(node.objective):
            value = self.expression(item.value, scope)
            self.want_number(value, item, f'{item.sense}(...)')
            self.no_draws(value, item, 'an objective')
            objective.append(DeclaredRelation(f'{path}.objective[{k}]', value, item.sense, item.line))
        return DeclaredSolver(
            path,
            node.name,
            inputs,
            solve_for,
            declared,
            tuple(constraints),
            tuple(objective),
            node.text,
            self.evidence(node),
            node.line,
        )

    def binding(self, path):
        """An input of a solver, resolved once: the `Read` of what its path names in the scope of the
        solver's owner (a value, a flow, a member or a collection), which the input follows. A
        calculation is a formula of the owner, which the input then names."""
        if path in self.done:
            if self.done[path] is None:
                raise Refused('depends', f'{path} has a problem of its own')
            return self.done[path]
        solver, node = self.syntax[path]
        try:
            if not isinstance(node.value, (n.Name, n.Member, n.Collection)) and not (
                isinstance(node.value, n.Method) and node.value.name in KEYED
            ):
                self.fail(
                    'solver_input',
                    f'the input {node.name} names a value, a flow, a member or a collection by its path: '
                    'put a calculation in a formula of the entity, and name the formula',
                    node,
                )
            found = self.path(node.value, Scope(self.scopes[solver].owner))
            if found.start == ('time',):
                self.fail(
                    'solver_input', f'the input {node.name} names the time, which a solver reads as t', node
                )
        except Refused:
            self.done[path] = None
            raise
        self.done[path] = DeclaredBinding(path, node.name, found, node.line)
        return self.done[path]

    def unknown(self, path, scope, node):
        """A new unknown of a solver: a number with its domain (its range, read at each solve), its
        preferred value (its initializer; zero in its unit without one) and its scale. A yes/no or a
        member of an enum would make a yes-or-no problem, which the language leaves out."""
        declared, retained = self.declared_type(node.type)
        if declared == BOOL or isinstance(declared, EnumOf):
            self.fail(
                'nonlinear',
                f'the unknown {node.name} is {declared}: a solver chooses numbers, and a yes-or-no '
                'problem is left out of the language',
                node,
            )
        if retained or not isinstance(declared, Num):
            self.fail(
                'type',
                f'the unknown {node.name} is a number, not {"a formula" if retained else declared}',
                node,
            )
        init = None
        if node.value is not None:
            init = self.expression(node.value, scope, declared)
            if not compatible(init.type, declared):
                if not _zero(init):
                    self.fail(
                        'unit',
                        f'the unknown {node.name} is in {declared}, and its preferred value in {init.type}',
                        node,
                    )
                init = Const(init.value, declared)
        lower = upper = scale = None
        if node.scale is not None:
            scale = self.bound(node.scale, scope, declared, node)
        if node.range is not None:
            lower, upper = (
                self.bound(end, scope, declared, node) for end in (node.range.low, node.range.high)
            )
            floor = self.scale(declared) if scale is None else self.exact(scale)
            if floor is not None:
                self.interval(
                    lower,
                    upper,
                    f'the domain of {node.name}',
                    node.range,
                    (node.range.low, node.range.high),
                    floor=abs(floor),
                )
        for found in (init, lower, upper, scale):
            if found is not None:
                self.no_draws(found, node, f'the domain of {node.name}')
        value = DeclaredValue(path, node.name, UNKNOWN, declared, init, lower, upper, scale, line=node.line)
        self.within(init, value, node)
        return value

    def determined(self, node, scope):
        """An entry of `solve_for` that names an existing field: a stored number, the `actual_rate` of
        a directed flow or of a route, the `served_fraction` of a flow with legs, or a projection of
        one of these. A leg's rate follows its route's rate or its flow's fraction, and an endpoint's
        total its flows, so neither is named; a yes/no or a member of an enum would make a yes-or-no
        problem."""
        found = self.path(node, scope)
        written = _spelled(node)
        if isinstance(node, n.Member) and node.name in ('actual_rate', 'served_fraction'):
            base = self.path(node.base, scope)
            of = base.type.of if isinstance(base.type, Many) else base.type
            if isinstance(of, RouteOf) and node.name == 'actual_rate':
                return found
            if isinstance(of, LegsOf) and node.name == 'served_fraction':
                return found
            if isinstance(of, FlowOf) and node.name == 'actual_rate':
                # The flow that a leg belongs to, as written (`link` of `link.forward`).
                parent = (
                    _spelled(node.base.base)
                    if isinstance(node.base, n.Member)
                    else of.flow.rpartition('.')[0].rpartition('.')[2]
                )
                if of.view:
                    self.fail(
                        'solve_for',
                        f"{written} follows its route's one signed rate: name {parent}.actual_rate",
                        node,
                    )
                if of.flow and of.flow not in self.syntax:
                    self.fail(
                        'solve_for',
                        f'{written} is a leg, served at the fraction of its flow: name '
                        f'{parent}.served_fraction',
                        node,
                    )
                if of.flow:
                    return found
            if isinstance(of, EndOf):
                self.fail(
                    'solve_for',
                    f'{written} is the total of an endpoint, which follows its flows: name the actual_rate '
                    'of each flow',
                    node,
                )
        value = self.value(found.part) if found.part in self.syntax else None
        kind = found.type.of if isinstance(found.type, Many) else found.type
        if value is not None and value.kind == STATE and (kind == BOOL or isinstance(kind, EnumOf)):
            self.fail(
                'nonlinear',
                f'{written} is {kind}: a solver chooses numbers, and a yes-or-no problem is left out of '
                'the language',
                node,
            )
        if value is None or value.kind != STATE or not isinstance(kind, Num):
            what = 'an unknown of a solver' if value is not None and value.kind == UNKNOWN else kind
            self.fail(
                'solve_for',
                f'a solver cannot determine {written}, which is {what}: name a stored number, the '
                'actual_rate of a flow or a route, or a served_fraction',
                node,
            )
        return found

    # ---- members -----------------------------------------------------------------------------------

    def given(self, template, path, node, line_node, evidence):
        """A member's own value or link: (whether it is a link, the `Given`)."""
        if len(path) != 1:
            self.fail(
                'property',
                f'{".".join(path)} is a setting of a part of {template}: a member gives the values and '
                'the links of its template, and its template the settings of its parts',
                line_node,
            )
        (name,) = path
        found = self.syntax.get(f'{template}.{name}')
        if found is None:
            parts = self.parts_of(template)
            self.fail('unknown_name', f'{template} has no {name}' + close(name, parts), line_node)
        if isinstance(found[1], n.Flow):
            self.fail(
                'property',
                f"{name} is a flow of {template}: the settings of a flow are its template's",
                line_node,
            )
        if isinstance(found[1], n.Event):
            self.fail(
                'property',
                f'{name} is an event of {template}: a member gives values and links, and its template the events',
                line_node,
            )
        if isinstance(found[1], n.Solver):
            self.fail(
                'property',
                f'{name} is a solver of {template}: a member gives values and links, and its template the '
                'solver',
                line_node,
            )
        return self.own(self.value(f'{template}.{name}'), template, node, line_node, evidence)

    def own(self, value, template, node, line_node, evidence):
        """(whether it is a link, the `Given`) of a value of a template given in place of the
        template's own initializer, by a member or a change: of the value's kind and type, and for a
        formula a formula (R-A5-07)."""
        name, scope, line = value.name, Scope(template), line_node.line
        if value.kind == LINK:
            target = self.link_target(self.expression(node, scope), value.type, node)
            return True, Given(name, target, evidence, line)
        if value.kind == FORMULA:
            if not isinstance(node, n.Formula):
                self.fail(
                    'formula',
                    f'{name} is a formula of {template}: a member replaces it with formula(...)',
                    node,
                )
            body = self.expression(node.body, scope, value.type if isinstance(value.type, EnumOf) else None)
            if not compatible(body.type, value.type):
                self.fail('unit', f'{name} of {template} is {value.type}, and this formula {body.type}', node)
            return False, Given(name, Retain(body, body.type), evidence, line)
        if isinstance(node, n.Formula):
            self.fail(
                'formula', f'{name} of {template} keeps no calculation: a member gives it a value', node
            )
        if isinstance(value.type, Dist):
            if not (isinstance(node, n.Call) and (node.function in ARITY or node.function == 'categorical')):
                self.fail(
                    'type', f'{name} holds a distribution: a member gives another, as uniform(1 h, 3 h)', node
                )
            found = self.distribution(node, value.type.of)
            if not compatible(found.type.of, value.type.of):
                self.fail('unit', f'{name} of {template} is {value.type}, and this {found.type}', node)
            return False, Given(name, found, evidence, line)
        unit = value.type if isinstance(value.type, (Num, EnumOf)) else None
        if isinstance(node, n.Collection) and not node.items and isinstance(value.type, Many):
            return False, Given(name, Read(('literal', ()), (), value.type, True), evidence, line)
        found = self.expression(node, scope, unit)
        if not compatible(found.type, value.type):
            if not (_zero(found) and isinstance(value.type, Num)):
                code = 'unit' if isinstance(found.type, Num) and isinstance(value.type, Num) else 'type'
                self.fail(code, f'{name} of {template} is {value.type}, and this value is {found.type}', node)
            found = Const(found.value, value.type)
        # A member's own collection is a collection value as a declaration's is: one written in
        # place, or a read of one that another value holds.
        self.within(found, value, node)
        return False, Given(name, found, evidence, line)

    def instance(self, node):
        """A member written by hand: `north: Utility` with its own values and links under it."""
        template = node.type.name
        if node.range is not None or node.scale is not None:
            self.fail(
                'range', f'{node.name} is a member: a range or a scale belongs to a value of {template}', node
            )
        values, links, seen = [], [], {}
        for item in node.properties:
            key = '.'.join(item.path)
            if key in seen:
                self.report(
                    'property', f'{key} is given twice; the first is {self.on_line(seen[key])}', item.line
                )
                continue
            seen[key] = item.line
            try:
                is_link, found = self.given(template, item.path, item.value, item, self.evidence(item))
            except Refused as refused:
                if refused.code != 'depends':
                    self.report(refused.code, refused.message, refused.line or item.line, refused.column)
                continue
            (links if is_link else values).append(found)
        written = {path[0] for path in (item.path for item in node.properties)}
        for target, line_node in self.changes.values():
            if target != node.name:
                continue
            # A change of the member wins over its own line (R-A5-03).
            try:
                evidence = self.evidence(line_node)
                is_link, found = self.given(template, (line_node.name,), line_node.value, line_node, evidence)
                self.recorded(self.value(f'{template}.{line_node.name}'), evidence, line_node, 'a change')
            except Refused as refused:
                if refused.code != 'depends':
                    self.report(refused.code, refused.message, refused.line or line_node.line, refused.column)
                continue
            kept = links if is_link else values
            kept[:] = [item for item in kept if item.name != found.name] + [found]
            written.add(line_node.name)
        text, title, evidence = node.text, node.title, self.evidence(node)
        label = self.labels.get(node.name)
        if label is not None:
            # A change of the labels of a member replaces each label that it writes, as of an entity.
            text = label.text if label.text is not None else text
            title = label.title if label.title is not None else title
            evidence = self.evidence(label) or evidence
        member = DeclaredMember(
            node.name, template, tuple(values), tuple(links), None, text, evidence, node.line, title=title
        )
        self.complete(member, written)
        return member

    def complete(self, member, written=()):
        """Each link of a member names a member, and each value has a starting value (D4). A value that
        the member writes (`written`) has its own problem if it is not among its values."""
        given = {item.name for item in (*member.values, *member.links)} | set(written)
        if member.template not in self.owned:
            self.owned[member.template] = [
                key
                for key, (owner, syntax) in self.syntax.items()
                if owner == member.template and isinstance(syntax, n.Declaration)
            ]
        for key in self.owned[member.template]:
            if key.rpartition('.')[2] in given:
                continue
            try:
                value = self.value(key)
            except Refused:
                continue
            if value.init is not None:
                continue
            if value.kind == LINK:
                message = (
                    f'{member.path} sets no {value.name}: a link names a member, and there is no none value'
                )
                self.report('link_unset', message, member.line, 0, member.file)
            else:
                message = (
                    f'{member.path} gives no {value.name}, which {member.template} leaves without a value'
                )
                self.report('no_value', message, member.line, 0, member.file)

    # ---- tables ------------------------------------------------------------------------------------

    def load(self, node):
        """Read the form of a table and the ids of its rows, before any name is resolved."""
        if node.template not in self.templates:
            message = f'{node.template} is no template' + close(node.template, self.templates)
            self.report('unknown_name', message, node.line)
            return
        text, origin = self.read_table(node.file)
        if text is None:
            self.report('table', f'{node.file!r} {origin}', node.line)
            return
        try:
            data = tables.read(text, origin)
        except LanguageError as error:
            self.problems.extend(error.problems)
            return
        self.data[node.name] = data
        names = [column.name for column in data.columns]
        if 'id' not in names:
            self.ids[node.name] = None
            return
        where, ids = names.index('id'), {}
        for row in data.rows:
            cell = row.cells[where]
            if not cell:
                self.report(
                    'table',
                    f'a row of {node.name} has no id: each row of a table with ids has one',
                    row.line,
                    0,
                    origin,
                )
            elif not ID.match(cell):
                self.report(
                    'table',
                    f'the id {cell!r} is no name: an id is written as a name, as junction',
                    row.line,
                    0,
                    origin,
                )
            elif cell in ids:
                message = f'{node.name} names the row {cell} twice; the first is on line {ids[cell]}'
                self.report('duplicate_name', message, row.line, 0, origin)
            else:
                ids[cell] = row.line
        self.ids[node.name] = ids

    def table(self, node):
        """A table and its members, one for each row: each cell that is not empty is the row's value
        of its column."""
        data = self.data.get(node.name)
        if data is None:
            return None, []
        evidence = ()
        try:
            evidence = self.evidence(node)
        except Refused as refused:
            self.report(refused.code, refused.message, refused.line, refused.column)
        columns, names = [], [column.name for column in data.columns]
        for k, column in enumerate(data.columns):
            if column.name == 'id':
                continue
            try:
                columns.append((k, column, self.column(node.template, column)))
            except Refused as refused:
                if refused.code != 'depends':
                    self.report(refused.code, refused.message, 1, 0, data.origin)
        ids, members = self.ids[node.name], []
        for index, row in enumerate(data.rows):
            if ids is None:
                id = f'{node.name}[{index}]'
            else:
                cell = row.cells[names.index('id')]
                if ids.get(cell) != row.line:
                    continue  # a row without its own id has its problem already
                id = f'{node.name}.{cell}'
            values, links = [], []
            for k, column, value in columns:
                if not row.cells[k]:
                    continue
                try:
                    is_link, found = self.cell(value, column, row.cells[k], row.line)
                except Refused as refused:
                    if refused.code != 'depends':
                        self.report(refused.code, f'{id}: {refused.message}', row.line, 0, data.origin)
                    continue
                (links if is_link else values).append(found)
            member = DeclaredMember(
                id,
                node.template,
                tuple(values),
                tuple(links),
                node.name,
                None,
                evidence,
                row.line,
                data.origin,
            )
            self.complete(member, {name for name, cell in zip(names, row.cells) if cell})
            members.append(member)
        declared = DeclaredTable(
            node.name,
            node.template,
            node.file,
            data.origin,
            data.columns,
            tuple(member.path for member in members),
            node.text,
            evidence,
            node.line,
        )
        return declared, members

    def column(self, template, column):
        """The value or the link of the template that a column gives, with the unit of its header."""
        key = f'{template}.{column.name}'
        found = self.syntax.get(key)
        if found is None:
            parts = [name.split('.', 1)[1] for name in self.syntax if name.startswith(f'{template}.')]
            self.fail(
                'unknown_name',
                f'the column {column.name} names no value of {template}' + close(column.name, parts),
            )
        if not isinstance(found[1], n.Declaration):
            self.fail(
                'table',
                f'the column {column.name} names no value of {template}: a column gives a value or a link',
            )
        value = self.value(key)
        if value.kind not in (INPUT, STATE, LINK) or isinstance(value.type, Dist):
            self.fail(
                'table',
                f'the column {column.name} names a {value.kind} of {template} ({value.type}): a column '
                'gives a number, a yes/no or a text of an input or a stored value, or a link',
            )
        if column.unit is not None:
            if not isinstance(value.type, Num):
                self.fail('unit', f'{column.name} takes no number: its header names no unit')
            unit = self.num(column.unit)
            if unit.dimension != value.type.dimension:
                self.fail(
                    'unit',
                    f'the column {column.name} is in {unit}, and {template}.{column.name} in {value.type}',
                )
        for name in column.cites:
            if name not in self.records:
                self.fail(
                    'unknown_record', f'@{name} names no record of the model' + close(name, self.records)
                )
        return value

    def cell(self, value, column, text, line):
        """A cell as the row's value of its column: a number (in the unit of the header, its own, or
        the value's), true or false, a text, or for a link the name of a member."""
        cites = tuple(n.Cite(name, line=line) for name in column.cites)
        if value.kind == LINK:
            node = _cell_path(text) or _cell_expression(text)
            if not isinstance(node, (n.Name, n.Member)):
                self.fail('link', f'{text!r} names no member: a link cell names a row, as sites.junction')
            return True, Given(
                column.name, self.link_target(self.path(node, TOP), value.type, None), cites, line
            )
        if value.type == BOOL:
            if text not in ('true', 'false'):
                self.fail('table', f'{column.name} is a yes/no: true or false, not {text!r}')
            return False, Given(column.name, Const(text == 'true', BOOL), cites, line)
        if value.type == TEXT:
            return False, Given(column.name, Const(text, TEXT), cites, line)
        if isinstance(value.type, EnumOf):
            if text not in value.type.members:
                self.fail('enum_member', f'{column.name} is {value.type}, and {text!r} is no member of it')
            return False, Given(column.name, Const(text, value.type), cites, line)
        try:
            node = _cell_number(text) or parse_expression(text)
        except SyntaxProblem as error:
            if error.code == 'number':
                self.fail('number', f'{column.name}: {text!r} is not a finite number')
            node = None
        except ValueError:
            self.fail('number', f'{column.name}: {text!r} is not a finite number')
        found = literal(node)
        if found is None or not isinstance(value.type, Num):
            self.fail(
                'table', f'{text!r} is not a number, true or false: a cell holds a value, not a calculation'
            )
        number, written = found
        if isinstance(written, n.Quantity):
            if column.unit is not None:
                self.fail(
                    'unit', f'the header of {column.name} gives its unit: a cell writes the number alone'
                )
            names = [name for _, name in written.unit]
            for name in names:
                if not self.units.has(name):
                    self.fail(
                        'unit',
                        f'{name} is no unit of the library or of the model' + close(name, self.units.base),
                    )
            unit = self.num(names[0] + ''.join(op + name for op, name in written.unit[1:]))
        else:
            unit = self.num(column.unit) if column.unit is not None else value.type
        if unit.dimension != value.type.dimension:
            self.fail('unit', f'{column.name} is in {value.type}, not {unit}')
        result = Const(number, unit, decimal(node))
        self.within(result, value, None)
        return False, Given(column.name, result, cites, line)

    # ---- the model ---------------------------------------------------------------------------------

    def part(self, path, owner, node):
        """A declared part of an entity, a template or the top level, or None after a problem."""
        try:
            if isinstance(node, n.Declaration):
                return self.declared_value(path, owner, node)
            if isinstance(node, n.Flow):
                return self.flow(path, owner, node)
            if isinstance(node, n.Assert):
                return self.assertion(path, Scope(owner), node)
            if isinstance(node, n.Event):
                return self.event(path, owner, node)
            if isinstance(node, n.Sees):
                self.fail('sees', SEES, node)
            if isinstance(node, n.Start):
                return self.start(path, TOP, node)
            if isinstance(node, n.Solver):
                return self.solver(path, owner, node)
        except Refused as refused:
            if refused.code != 'depends':
                self.report(refused.code, refused.message, refused.line or node.line, refused.column)
            return None
        if isinstance(node, n.Property):
            self.report('property', PROPERTY_IN_ENTITY.format('.'.join(node.path)), node.line)
            return None
        raise TypeError(f'{path}: no part of a model: {type(node).__name__}')

    def status(self, owner, cases):
        """The status display of an entity or a template: its cases in written order (see the
        module). A case with a problem is reported and left out."""
        path, found = f'{owner}.status', []
        for k, node in enumerate(cases):
            try:
                test = None
                if node.test is not None:
                    test = self.expression(node.test, Scope(owner))
                    self.want_bool(test, node, 'a status case')
                    self.no_draws(test, node, 'a status case')
                if (node.test is None) != (k == len(cases) - 1):
                    self.fail('status', STATUS_FALLBACK, node)
                found.append(
                    DeclaredStatusCase(
                        f'{path}.case[{k}]', node.rating, test, node.text, self.evidence(node), node.line
                    )
                )
            except Refused as refused:
                self.report(refused.code, refused.message, refused.line or node.line, refused.column)
        return DeclaredStatus(path, tuple(found), cases[0].line)

    def entity(self, item):
        """An entity written once or a template, with its parts. A second declaration of a name is
        not read: `check_names` reports it."""
        parts, asserts = [], 0
        for k, member in enumerate(item.members):
            if isinstance(member, n.Status):
                continue
            if isinstance(member, n.Assert):
                name, asserts = f'assert[{asserts}]', asserts + 1
            else:
                name = getattr(member, 'name', None) or f'{type(member).__name__.lower()}[{k}]'
            if self.syntax.get(f'{item.name}.{name}', (None, member))[1] is not member:
                continue
            found = self.part(f'{item.name}.{name}', item.name, member)
            if found is not None:
                parts.append(found)
        cases = [member for member in item.members if isinstance(member, n.Status)]
        status = self.status(item.name, cases) if cases else None
        if status is not None and any(part.path == status.path for part in parts):
            self.report('status', STATUS_NAME.format(status.path), cases[0].line)
        text, title, label = item.text, item.title, self.labels.get(item.name)
        try:
            evidence = self.evidence(item)
            if label is not None:
                # A change of the labels of an entity replaces each label that it writes.
                text = label.text if label.text is not None else text
                title = label.title if label.title is not None else title
                evidence = self.evidence(label) or evidence
        except Refused as refused:
            self.report(refused.code, refused.message, refused.line, refused.column)
            evidence = ()
        kind = DeclaredTemplate if item.name in self.templates else DeclaredEntity
        return kind(item.name, tuple(parts), text, title, evidence, item.line, status)

    def model(self):
        for item in self.tree.items:
            if isinstance(item, n.Table):
                self.load(item)
        entities = [self.entity(item) for item in self.tree.items if isinstance(item, n.Entity)]
        root, members, tables_, asserts, notes, setup, scenario = [], [], [], [], (), [], None
        groups, run_lines = [], []
        for item in self.tree.items:
            if isinstance(item, n.Scenario):
                scenario = self.scenario(item)
            elif isinstance(item, (n.Entity, n.Record, n.Change)):
                continue
            elif isinstance(item, n.Options):
                groups.append(item)
            elif isinstance(item, n.Runs):
                run_lines.extend(item.runs)
            elif isinstance(item, n.Use):
                self.report('use', USE_ALONE, item.line)
            elif isinstance(item, n.Table):
                declared, rows = self.table(item)
                if declared is not None:
                    tables_.append(declared)
                    members.extend(rows)
            elif isinstance(item, n.Declaration) and item.name in self.instances:
                try:
                    members.append(self.instance(item))
                except Refused as refused:
                    self.report(refused.code, refused.message, refused.line or item.line, refused.column)
            elif isinstance(item, (n.Declaration, n.Assert)):
                path = item.name if isinstance(item, n.Declaration) else f'assert[{len(asserts)}]'
                found = self.part(path, '', item)
                if isinstance(found, DeclaredAssert):
                    asserts.append(found)
                elif found is not None:
                    root.append(found)
            elif isinstance(item, n.Notes):
                self.note_records(item.notes)
                notes = merged_notes(notes, item.notes)
            elif isinstance(item, n.Start):
                found = self.part(f'setup[{len(setup)}]', '', item)
                setup.append(found)
        if scenario is not None and scenario.role == 'variant' and not self.files.files:
            self.report('scenario', VARIANT_ALONE, scenario.line)
        options = self.declared_options(groups)
        runs = self.declared_runs(run_lines, options)
        self.check_names()
        if not self.problems:
            self.problems.extend(Order(entities, members, root, self.exact, self.created).cycles())
        if self.problems:
            raise LanguageError(sorted(self.problems, key=lambda item: (item.file, item.line, item.column)))
        return DeclaredModel(
            scenario,
            tuple(entities),
            tuple(root),
            tuple(self.records.values()),
            tuple(notes),
            self.units,
            self.tree,
            members=tuple(members),
            tables=tuple(tables_),
            asserts=tuple(asserts),
            setup=tuple(found for found in setup if found is not None),
            options=options,
            runs=runs,
            files=self.files.files,
        )

    # ---- the setup scope's initializers ------------------------------------------------------------

    def wired(self, tree):
        """The tree with each initializer of the setup scope in its place: `clinic.delivery.request =
        3 L/h` at the top level is the same initializer as `request = 3 L/h` under the flow (spec,
        "Flows and algebraic solvers"), so it becomes that line, and so do a value of an entity
        written once (`tank.water = 8 L`), a setting of a store's endpoint (`tank.water.outflow.capacity
        = 10 L/h`), a property of a leg (`site.restore.labor.request = 4 L/h`) and a member's own value
        (`a1.ask = 2 L/h`). It then stands where that initializer stands in the order of R-A5-03, so a
        `change`, an option and an edit still win over it. A path is initialized once: a second
        initializer, by the declaration, a member's own line or another setup line, is an error that
        names both lines. A template's parts, a row's cells and the parts of events and solvers are
        initialized where they are written."""
        items = [item for item in tree.items if not isinstance(item, n.Property)]
        place = {
            item.name: k
            for k, item in enumerate(items)
            if isinstance(item, (n.Entity, n.Declaration, n.Table)) and getattr(item, 'name', None)
        }
        first = {}  # the line of the setup initializer of each path, for a second one
        for item in tree.items:
            if not isinstance(item, n.Property):
                continue
            path = '.'.join(item.path)
            k = place.get(item.path[0]) if len(item.path) > 1 else None
            try:
                found = self.wire(None if k is None else items[k], item, first.get(path))
            except Refused as refused:
                self.report(refused.code, refused.message, refused.line or item.line, refused.column)
                continue
            # The entity or the member takes the initializer in its own place in the tree.
            items[k] = found
            first[path] = item.line
        return replace(tree, items=tuple(items))

    def wire(self, head, item, earlier):
        """The entity or the member `head` with the initializer of the setup line `item` under the
        declaration that its path names; `earlier` is the line of an earlier setup line of that path."""
        path = '.'.join(item.path)
        if isinstance(head, n.Table) or (isinstance(head, n.Entity) and not head.name[:1].islower()):
            what = (
                'a row of a table, whose values are its cells' if isinstance(head, n.Table) else 'a template'
            )
            self.fail('property', f'{path}: {head.name} is {what}: {SETUP_TARGETS}', item)
        if isinstance(head, n.Declaration) and head.value is None and isinstance(head.type, n.NamedType):
            # A member written by hand: its own value, as a line under it.
            if len(item.path) != 2:
                self.fail(
                    'property',
                    f'{path}: a member gives the values and the links of its template, and its template '
                    'the settings of its parts',
                    item,
                )
            line = n.Property(
                item.path[1:],
                item.value,
                cites=item.cites,
                text=item.text,
                evidence=item.evidence,
                line=item.line,
                column=item.column,
            )
            self.once(path, [own for own in head.properties if own.path == line.path], earlier, item)
            return replace(head, properties=(*head.properties, line))
        if not isinstance(head, n.Entity):
            self.fail('unknown_name', f'{path} names no part of an entity or a member: {SETUP_TARGETS}', item)
        name, *rest = item.path[1:]
        part = next((member for member in head.members if getattr(member, 'name', None) == name), None)
        if isinstance(part, n.Declaration) and not rest:
            if part.value is not None:
                self.fail(
                    'property',
                    f'{path} is initialized twice: {self.on_line(earlier or part.line)} and '
                    f'{self.on_line(item.line)}; a value has one initializer',
                    item,
                )
            found = replace(
                part,
                value=item.value,
                cites=(*part.cites, *item.cites),
                evidence=(*part.evidence, *item.evidence),
            )
        elif (isinstance(part, n.Declaration) and len(rest) == 2 and rest[0] in SIDES) or (
            isinstance(part, n.Flow) and len(rest) == 1
        ):
            # An endpoint's setting under its store, or a property of a flow.
            found = self.wired_property(part, tuple(rest), item, earlier)
        elif isinstance(part, n.Flow) and len(rest) == 2 and any(leg.name == rest[0] for leg in part.legs):
            legs = tuple(
                self.wired_property(leg, (rest[1],), item, earlier) if leg.name == rest[0] else leg
                for leg in part.legs
            )
            found = replace(part, legs=legs)
        else:
            parts = [member.name for member in head.members if getattr(member, 'name', None)]
            self.fail(
                'property',
                f'{path} names no value, flow, leg or endpoint setting of {head.name}: {SETUP_TARGETS}'
                + close(name, parts),
                item,
            )
        return replace(head, members=tuple(found if member is part else member for member in head.members))

    def wired_property(self, part, steps, item, earlier):
        """A declaration or a flow with the property `steps` that the setup line `item` initializes."""
        line = n.Property(
            steps,
            item.value,
            cites=item.cites,
            text=item.text,
            evidence=item.evidence,
            line=item.line,
            column=item.column,
        )
        self.once('.'.join(item.path), [own for own in part.properties if own.path == steps], earlier, item)
        return replace(part, properties=(*part.properties, line))

    def once(self, path, found, earlier, item):
        """A path that a line already initializes is not initialized again."""
        if found:
            self.fail(
                'property',
                f'{path} is initialized twice: {self.on_line(earlier or found[0].line)} and '
                f'{self.on_line(item.line)}; a value has one initializer',
                item,
            )

    # ---- packages: changes, options and runs ------------------------------------------------------

    def register_changes(self):
        """Each line of each `change name:` by the path of the value or the link that it sets. A change
        names an entity, a template or a member written by hand of an earlier file, sets only what it
        declares (R-A5-03: a change of a missing name is an error), and sets each value once: two
        changes of one value are an error, whatever the order of the files. Its own text, `title`
        and records replace those of what it names."""
        for item in self.tree.items:
            if not isinstance(item, n.Change):
                continue
            target = self.entities.get(item.name) or self.templates.get(item.name)
            target = target or self.instances.get(item.name)
            if target is None or self.file_of(target.line) >= self.file_of(item.line):
                names = [*self.entities, *self.templates, *self.instances]
                self.report(
                    'change',
                    f'change {item.name}: names no entity, template or member of an earlier file'
                    + close(item.name, names),
                    item.line,
                )
                continue
            if item.text is not None or item.title is not None or item.cites:
                first = self.labels.setdefault(item.name, item)
                if first is not item:
                    self.report(
                        'change',
                        f'the labels of {item.name} are changed twice; the first change is '
                        f'{self.on_line(first.line)}',
                        item.line,
                    )
            template = target.type.name if item.name in self.instances else item.name
            for line_node in item.members:
                if self.change_line(item.name, template, line_node):
                    key = f'{item.name}.{line_node.name}'
                    if key in self.changes:
                        self.report(
                            'change',
                            f'{key} is changed twice; the first change is '
                            f'{self.on_line(self.changes[key][1].line)}: one change sets a value (R-A5-03)',
                            line_node.line,
                        )
                        continue
                    self.changes[key] = (item.name, line_node)

    def change_line(self, name, template, node):
        """Whether a line of a change sets a declared value or link of its template (`x = value`);
        else its problem is reported."""
        if not isinstance(node, n.Declaration):
            self.report(
                'change',
                f'change {name}: sets values, links and labels; a {type(node).__name__.lower()} '
                f'belongs to the declaration of {template}',
                node.line,
            )
            return False
        if node.value is None or node.type is not None or node.modifier or node.range or node.scale:
            self.report(
                'change',
                f'change {name}: gives {node.name} a value, as {node.name} = value; the type, the range '
                'and the scale stay those of its declaration, and a change declares no new value',
                node.line,
            )
            return False
        if node.properties:
            self.report(
                'change',
                f'change {name}: gives {node.name} a value; the settings of a part stay with its declaration',
                node.properties[0].line,
            )
            return False
        found = self.syntax.get(f'{template}.{node.name}')
        if found is None or not isinstance(found[1], n.Declaration):
            self.report(
                'change',
                f'change {name}: {template} declares no value {node.name}'
                + close(node.name, self.parts_of(template)),
                node.line,
            )
            return False
        return True

    def changed(self, value, owner, node):
        """A value of an entity or a template with the initializer that a change gives it: of the
        value's kind and type, as a member's own value is (`own`), with the change's records."""
        evidence = self.evidence(node)
        is_link, given = self.own(value, owner, node.value, node, evidence)
        self.recorded(value, evidence, node, 'a change')
        init = self.expression(node.value, Scope(owner)) if is_link else given.init
        return replace(value, init=init, evidence=evidence)

    def recorded(self, value, evidence, node, what):
        """A number or a yes/no that an option or a change sets cites a record (R-A5-05); a text, a
        member of an enum, a link, a collection and a formula, which calculates, need none."""
        typed = value.type.of if isinstance(value.type, Dist) else value.type
        numeric = isinstance(typed, Num) or typed == BOOL or isinstance(value.type, Dist)
        if not evidence and numeric and value.kind != FORMULA:
            self.fail(
                'record',
                f'{value.path}: {what} sets a number or a yes/no, which cites its record (@name)',
                node,
            )

    def declared_options(self, groups):
        """The options of the groups, in written order. An option's name is its own across the
        groups, since a run names it alone; a group written in two files is one group."""
        found, seen = [], {}
        for group in groups:
            for item in group.options:
                first = seen.get(item.name)
                if first is not None:
                    self.report(
                        'option',
                        f'{item.name} is already an option of the group {first.group}, {self.on_line(first.line)}',
                        item.line,
                    )
                    continue
                settings, written = [], {}
                for node in item.settings:
                    key = '.'.join(node.path)
                    if key in written:
                        self.report(
                            'option',
                            f'{item.name} sets {key} twice; the first is {self.on_line(written[key])}',
                            node.line,
                        )
                        continue
                    written[key] = node.line
                    try:
                        settings.append(self.setting(node))
                    except Refused as refused:
                        if refused.code != 'depends':
                            self.report(
                                refused.code, refused.message, refused.line or node.line, refused.column
                            )
                try:
                    evidence = self.evidence(item)
                except Refused as refused:
                    self.report(refused.code, refused.message, refused.line or item.line, refused.column)
                    evidence = ()
                seen[item.name] = DeclaredOption(
                    item.name, group.group, tuple(settings), item.text, evidence, item.line
                )
                found.append(seen[item.name])
        return tuple(found)

    def setting(self, node):
        """A setting of an option (R-A5-04): the input that its full path names, of one member
        (`tank.rate`, `sites.clinic.rate`), of every member of a template (`Pump.instances.rate`) or
        of the top level (`rate`), and the value that it gives, a constant of the input's type (D2)
        with its record (R-A5-05)."""
        member = instances = None
        *owner, name = node.path
        if len(owner) == 2 and owner[1] == 'instances' and owner[0] in self.templates:
            template = instances = owner[0]
        elif not owner:
            template, member = '', ''
        else:
            member, template = '.'.join(owner), self.member_template(owner, node)
        key = f'{template}.{name}' if template else name
        found = self.syntax.get(key)
        if found is None or not isinstance(found[1], n.Declaration):
            parts = self.parts_of(template) if template else list(self.root)
            self.fail('unknown_name', f'{".".join(node.path)} names no value' + close(name, parts), node)
        value = self.value(key)
        if value.kind != INPUT:
            self.fail(
                'option',
                f'{".".join(node.path)} is a {value.kind} value: an option sets an input (R-A5-04)',
                node,
            )
        evidence = self.evidence(node)
        given = self.constant(value, node.value)
        self.recorded(value, evidence, node, 'an option')
        return DeclaredSetting('.'.join(node.path), name, given, member, instances, evidence, node.line)

    def member_template(self, owner, node):
        """The template of the member that the steps `owner` name: an entity written once, a member
        written by hand, or a row of a table by its id (`sites.clinic`)."""
        id = '.'.join(owner)
        if id in self.entities:
            return id
        if id in self.instances:
            return self.instances[id].type.name
        if len(owner) == 2 and owner[0] in self.tables and owner[1] in (self.ids.get(owner[0]) or ()):
            return self.tables[owner[0]].template
        names = [
            *self.entities,
            *self.instances,
            *(f'{t}.{i}' for t, ids in self.ids.items() for i in ids or ()),
        ]
        self.fail('unknown_name', f'{id} names no member' + close(id, names), node)

    def constant(self, value, node):
        """The value that an option or an edit gives an input: a number with a unit of its dimension
        (or bare, in the input's unit), true or false, a member of its enum, a text, or for a
        distribution-valued input a distribution; written out, and in the input's range."""
        if isinstance(value.type, Dist):
            if not (isinstance(node, n.Call) and (node.function in ARITY or node.function == 'categorical')):
                self.fail(
                    'type', f'{value.name} holds a distribution: it takes another, as uniform(1 h, 3 h)', node
                )
            found = self.distribution(node, value.type.of)
            if not compatible(found.type.of, value.type.of):
                self.fail('unit', f'{value.name} is {value.type}, and this is {found.type}', node)
            return found
        found = self.expression(node, TOP, value.type if isinstance(value.type, (Num, EnumOf)) else None)
        if not isinstance(found, Const):
            self.fail(
                'value',
                f'{value.name} takes a value written out (a number with its unit, true or false, a member '
                'of its enum or a text), not a calculation',
                node,
            )
        if not compatible(found.type, value.type):
            if not (_zero(found) and isinstance(value.type, Num)):
                code = 'unit' if isinstance(found.type, Num) and isinstance(value.type, Num) else 'type'
                self.fail(code, f'{value.name} is {value.type}, and this value is {found.type}', node)
            found = Const(found.value, value.type)
        self.within(found, value, node)
        if isinstance(found.type, Num) and found.type != value.type:
            # In the input's own unit, so that two equal values are one value of a configuration; a
            # decimal is converted as written (`0.1 days` is 2.4 h).
            exact = self.exact(found) / self.scale(value.type)
            number = float(exact) if isinstance(found.value, float) else exact
            if exact.denominator == 1:
                number = int(exact)
            found = Const(number, value.type, exact)
        return found

    def declared_runs(self, lines, options):
        """The named runs: each a name of its own and known options, at most one of each group, no
        two of which set one input (R-A5-03)."""
        by_name, found, seen = {item.name: item for item in options}, [], {}
        for line in lines:
            if line.name in seen:
                self.report(
                    'run',
                    f'the run {line.name} is named twice; the first is {self.on_line(seen[line.name])}',
                    line.line,
                )
                continue
            seen[line.name] = line.line
            missing = [name for name in line.options if name not in by_name]
            for name in missing:
                self.report('run', f'{line.name}: {name!r} is no option' + close(name, by_name), line.line)
            chosen = [by_name[name] for name in line.options if name in by_name]
            problem = choice_problem(chosen)
            if problem is not None:
                self.report('run', f'{line.name}: {problem}', line.line)
            try:
                evidence = self.evidence(line)
            except Refused as refused:
                self.report(refused.code, refused.message, refused.line or line.line, refused.column)
                evidence = ()
            if not missing and problem is None:
                found.append(DeclaredRun(line.name, line.options, line.text, evidence, line.line))
        return tuple(found)

    def check_names(self):
        """Two declarations of one scope with one name are an error, and so are two records of one
        name in the model."""
        seen, records = {}, {}
        for item in self.tree.items:
            if isinstance(item, n.Record):
                if item.name in records:
                    self.report(
                        'duplicate_name',
                        f'the record {item.name} is declared twice, {self.on_line(records[item.name])} and '
                        f'{self.on_line(item.line)}: a record has one name in its model',
                        item.line,
                    )
                records.setdefault(item.name, item.line)
            name = getattr(item, 'name', None)
            if isinstance(item, (n.Entity, n.Table, n.Declaration)) and name:
                if name in seen:
                    self.report(
                        'duplicate_name',
                        f'{name} is declared twice; the first is {self.on_line(seen[name])}',
                        item.line,
                    )
                seen.setdefault(name, item.line)
            if isinstance(item, n.Entity):
                own = {}
                for member in item.members:
                    member_name = getattr(member, 'name', None)
                    if isinstance(member, (n.Declaration, n.Flow, n.Event, n.Solver)) and member_name:
                        if member_name in own:
                            self.report(
                                'duplicate_name',
                                f'{item.name}.{member_name} is declared twice; the first is '
                                f'{self.on_line(own[member_name])}',
                                member.line,
                            )
                        own.setdefault(member_name, member.line)

    def note_records(self, notes):
        """Each record that a note cites, at any depth, is a record of the model (`unknown_record`
        at the line of the citation)."""
        pending = list(notes)
        while pending:
            note = pending.pop()
            pending += note.notes
            for item in (*note.cites, *note.evidence):
                if isinstance(item, n.Cite) and item.name not in self.records:
                    self.report(
                        'unknown_record',
                        f'@{item.name} names no record of the model' + close(item.name, self.records),
                        item.line or note.line,
                        item.column,
                    )

    def scenario(self, node):
        def hours(value, key):
            if value is None:
                return None
            try:
                found = self.expression(value, TOP)
            except Refused:
                self.report('scenario', f'{key} is a time, such as 30 days', node.line)
                return None
            if not isinstance(found, Const) or found.type.dimension != (('time', 1),):
                self.report('scenario', f'{key} is a time, such as 30 days', node.line)
                return None
            # Exact hours, however the time is spelled: `0.15 day` and `216 min` are both 18/5 h.
            hours = self.exact(found)
            return int(hours) if hours.denominator == 1 else hours

        return Scenario(
            'main' if node.role == 'scenario' else 'variant',
            node.title,
            node.summary,
            node.scope,
            node.library,
            hours(node.horizon, 'horizon'),
            hours(node.resolution, 'resolution'),
            node.line,
        )


class Order:
    """The starting values of a model's members follow their dependencies, across members and
    whatever the order of the file (spec, "Model-level initializers follow their value
    dependencies"): a value needs what its initializer reads, its own or its template's, and a
    formula what it reads. Links are fixed when the model compiles (R-A1-30), so each read reaches
    known members, and a `where` that compares links keeps only the members that it names
    (`decided`). A cycle has no order and is an error, given at a value on it with its chain; mutual
    links are no cycle, and neither is a template that reads itself through other members.

    A keyed read whose key is fixed when the model compiles (`exact`) and whose members are known
    then, with their natural keys (`known`), reads the one entry that the key selects (`chosen`), so
    `this.children.at(0).total` needs the first child's total alone. A node is `(member, value)`,
    `('', value)` of the top level, or `('*', read)` for a read that is the same for every member
    (`sum(Place.instances.need)`), which is walked once, so a template's read of all its members costs
    the members once and not once for each of them. `exact` and `created` are the resolver's
    (`Resolver.exact`, `Resolver.created`)."""

    def __init__(self, entities, members, root, exact, created):
        self.parts = {
            entity.path: {part.name: part for part in entity.parts if isinstance(part, DeclaredValue)}
            for entity in entities
        }
        self.members = {entity.path: [] for entity in entities}
        self.own, self.template, self.files = {}, {}, {}
        for entity in entities:
            if not isinstance(entity, DeclaredTemplate):
                self.members[entity.path].append(entity.path)
                self.own[entity.path], self.template[entity.path] = {}, entity.path
                self.files[entity.path] = ''
        for member in members:
            self.members[member.template].append(member.path)
            self.own[member.path] = {given.name: given for given in (*member.values, *member.links)}
            self.template[member.path], self.files[member.path] = member.template, member.file
        self.root = {value.name: value for value in root}
        self.shared = {}
        # What the walk of each collection value of the top level reaches and reads, which is the same
        # for every reader: walked once, so a chain of collection values costs its length.
        self.collected = {}
        self.exact, self.created = exact, created

    def init(self, node):
        """The initializer of a node: the member's own, or its template's."""
        member, name = node
        if member == '':
            return self.root[name].init
        given = self.own[member].get(name)
        return given.init if given is not None else self.parts[self.template[member]][name].init

    def needs(self, expression, member, item=()):
        """The nodes that a typed expression reads for a member ('' at the top level), in the order
        in which it reads them (a dict used as an ordered set, so the search is the same each run)."""
        return walked(self._needs(expression, member, item))

    def walk(self, read, member, item, found):
        """The members that a read reaches, adding to `found` each value that it reads on its way. A
        flow's rate is no starting value, so a read through a flow reaches nothing."""
        return walked(self._walk(read, member, item, found))

    # Each walk below is a generator, run by `walked` on an explicit stack: it yields the walk that it
    # needs and is sent its answer, so a chain of collection values costs no depth of calls.

    def _needs(self, expression, member, item=()):
        found = {}
        for read in reads_of(expression):
            if _own(read):
                yield self._walk(read, member, item, found)
            else:
                key = ('*', read)
                if key not in self.shared:
                    self.shared[key] = {}
                    yield self._walk(read, '', (), self.shared[key])
                found[key] = None
        return found

    def _walk(self, read, member, item, found):
        kind, steps = read.start[0], read.steps
        if kind == 'time':
            return {}
        if kind == 'root':
            value = self.root.get(steps[0])
            if value is None or value.kind != COLLECTION:
                if value is not None:
                    found[('', steps[0])] = None
                return {}
            if steps[0] not in self.collected:
                read_on_its_way = {}
                reached = yield self._walk(value.init, '', (), read_on_its_way)
                self.collected[steps[0]] = (reached, read_on_its_way)
            reached, read_on_its_way = self.collected[steps[0]]
            found.update(read_on_its_way)
            current, steps = dict(reached), steps[1:]
        else:
            current = yield self._starts(read.start, member, item, found)
        for step in steps:
            following = {}
            for each in current:
                part = self.parts[self.template[each]].get(step)
                if part is None:
                    continue
                if part.kind == LINK:
                    given = self.own[each].get(step)
                    target = given.init if given is not None else part.init and part.init.start[1]
                    if target:
                        following[target] = None
                elif part.kind == COLLECTION:
                    init = self.init((each, step))
                    if init is not None:
                        following.update((yield self._walk(init, each, (), found)))
                else:
                    found[(each, step)] = None
            current = following
        return current

    def _starts(self, start, member, item, found):
        kind = start[0]
        if kind == 'this':
            return {member: None}
        if kind == 'named':
            return {start[1]: None}
        if kind == 'item':
            return dict.fromkeys(item)
        if kind == 'instances':
            return dict.fromkeys(self.members.get(start[1], ()))
        if kind == 'literal':
            reached = {}
            for each in start[1]:
                reached.update((yield self._walk(each, member, item, found)))
            return reached
        source = yield self._walk(start[1], member, item, found)
        if kind == 'where':
            found.update((yield self._needs(start[2], member, tuple(source))))
            return {each: None for each in source if self.decided(start[2], member, each) is not False}
        if kind == 'by':
            found.update(dict.fromkeys((each, start[2]) for each in source))
            return source
        found.update((yield self._needs(start[2], member, item)))
        chosen = yield self._chosen(start[1], start[2], member, item)
        return source if chosen is None else chosen

    def _chosen(self, source, key, member, item):
        """The entry, or none, that a lookup reads for one member when its key is fixed when the model
        compiles and the members of its source are known then (`_known`): the one that the key selects
        (`select`), or none below the first key, where the read fails if a run evaluates it. None when
        only a run knows it, so that the lookup needs each member of its source."""
        at = self.exact(key)
        if at is None:
            return None
        members = yield self._known(source, member, item)
        if members is None:
            return None
        found = select(members, at)
        return {} if found is None else {found: None}

    def _known(self, read, member, item):
        """The members of a collection read with their keys at the start ({id: key}, in the order of
        creation) when the model fixes them when it compiles: the instances of a template and a
        literal, keyed by their creation numbers; a where whose test is decided for each member
        (`decided`); a `by` of a field whose starting value each member fixes, a stored number written
        out (an input is a configuration's, so it is not fixed when the model compiles); and a
        collection value one step from a member or the top level that is one of these. None for any
        other. The keys are those of the start, which is what the starting values read."""
        kind = read.start[0]
        if read.steps:
            owner = {'root': '', 'this': member, 'named': read.start[1] if kind == 'named' else None}.get(
                kind
            )
            if owner is None or len(read.steps) != 1:
                return None
            if owner == '':
                value = self.root.get(read.steps[0])
                init = value.init if value is not None and value.kind == COLLECTION else None
            else:
                part = self.parts[self.template[owner]].get(read.steps[0])
                init = (
                    self.init((owner, read.steps[0]))
                    if part is not None and part.kind == COLLECTION
                    else None
                )
            return None if init is None else (yield self._known(init, owner, ()))
        if kind == 'by':
            inner = yield self._known(read.start[1], member, item)
            if inner is None:
                return None
            keys = {}
            for each in inner:
                part = self.parts[self.template[each]].get(read.start[2])
                number = None
                if part is not None and part.kind == STATE:
                    number = self.exact(self.init((each, read.start[2])))
                if number is None:
                    return None
                keys[each] = number
            return keys
        if kind == 'where':
            inner = yield self._known(read.start[1], member, item)
            if inner is None:
                return None
            kept = {}
            for each, number in inner.items():
                verdict = self.decided(read.start[2], member, each)
                if verdict is None:
                    return None
                if verdict:
                    kept[each] = number
            return kept
        if kind == 'instances':
            return self.created(read.start[1])
        if kind != 'literal':
            return None
        ids = []
        for each in read.start[1]:
            reached = yield self._walk(each, member, item, {})
            if len(reached) != 1:
                return None
            ids.extend(reached)
        numbers = self.created(read.type.of.template)
        return {each: numbers[each] for each in sorted(ids, key=numbers.get)}

    def decided(self, test, member, item):
        """The value of a where's test for one member of its source (`item`), when the test compares
        links, which the model fixes when it compiles (`seller == this`, with `and`, `or` and `not`);
        None when it reads anything else, which only a run knows, so that the where keeps the member."""
        if isinstance(test, Const) and test.type == BOOL:
            return test.value
        if not isinstance(test, Apply):
            return None
        found = [self.decided(each, member, item) for each in test.args]
        if test.op == 'not':
            return None if found[0] is None else not found[0]
        if test.op in ('and', 'or'):
            stop = test.op == 'or'  # the value that decides: true for `or`, false for `and`
            if stop in found:
                return stop
            return None if None in found else not stop
        if test.op != 'compare' or test.detail not in (('==',), ('!=',)):
            return None
        ends = [self.linked(each, member, item) for each in test.args]
        if None in ends:
            return None
        return (ends[0] == ends[1]) == (test.detail == ('==',))

    def linked(self, read, member, item):
        """The member that a read through links names (`this`, the member under test, a named member,
        and their links), or None for any other read."""
        if not isinstance(read, Read) or not isinstance(read.type, Ent):
            return None
        current = {'this': member, 'item': item}.get(read.start[0])
        if read.start[0] == 'named':
            current = read.start[1]
        for step in read.steps:
            part = self.parts.get(self.template.get(current), {}).get(step)
            if part is None or part.kind != LINK:
                return None
            given = self.own[current].get(step)
            current = given.init if given is not None else part.init and part.init.start[1]
        return current or None

    def cycles(self):
        """The problems of the cycles among the members' values, each with its chain, at the line of a
        value on it: one for each shape of a cycle that the search meets, by the template values on it,
        so that a template whose every member reads itself is one problem and not one for each
        member."""
        nodes = [('', name) for name in self.root]
        for member, template in self.template.items():
            nodes += [(member, name) for name, part in self.parts[template].items() if part.kind != LINK]
        state, problems, seen = {}, [], set()
        for first in nodes:
            if first in state:
                continue
            state[first] = 'open'
            stack = [(first, iter(self.edges(first)))]
            while stack:
                node, edges = stack[-1]
                following = next(edges, None)
                if following is None:
                    state[node] = 'done'
                    stack.pop()
                elif following not in state:
                    state[following] = 'open'
                    stack.append((following, iter(self.edges(following))))
                elif state[following] == 'open':
                    path = [each for each, _ in stack]
                    ring = [each for each in path[path.index(following) :] if each[0] != '*']
                    shape = frozenset((self.template.get(member, ''), name) for member, name in ring)
                    if shape not in seen:
                        seen.add(shape)
                        problems.append(self.problem(ring))
        return problems

    def edges(self, node):
        """The nodes that a node needs; a constant needs none."""
        if node[0] == '*':
            return self.shared[node]
        init = self.init(node)
        if init is None or isinstance(init, Const):
            return ()
        return self.needs(init, node[0])

    def problem(self, ring):
        """The problem of a cycle, its chain (`a.total reads b.total reads a.total`), at the line of
        its first value: a member's own, in the file of the member, or its template's."""
        names = [f'{member}.{name}' if member else name for member, name in ring]
        member, name = ring[0]
        if member == '':
            line, file = self.root[name].line, ''
        elif name in self.own[member]:
            line, file = self.own[member][name].line, self.files[member]
        else:
            line, file = self.parts[self.template[member]][name].line, ''
        chain = ' reads '.join([*names, names[0]])
        return Problem('cycle', f'{chain}: the values on a cycle have no order', line, 0, file)


def walked(walk):
    """The answer of a walk that is a generator (`Order`): it yields each walk that it needs, which
    runs on an explicit stack, and is sent that walk's answer; its own answer is what it returns."""
    stack, answer = [walk], None
    while stack:
        try:
            needed = stack[-1].send(answer)
        except StopIteration as done:
            stack.pop()
            answer = done.value
            continue
        stack.append(needed)
        answer = None
    return answer


def select(keys, at):
    """The member that `.at(at)` reads among members with these keys ({member: key}, in the order of
    their creation): the greatest key at or below `at`, and of equal keys the one created later; None
    when every key is above `at`."""
    found = None
    for member, key in keys.items():
        if key <= at and (found is None or key >= keys[found]):
            found = member
    return found


def _own(read, bound=False):
    """Whether a read depends on the member that reads it: it starts at `this`, or at the member of an
    enclosing `where` (not `bound` by a `where` inside the read), or a collection or a key on the way
    does."""
    kind = read.start[0]
    if kind == 'this' or (kind == 'item' and not bound):
        return True
    if kind == 'literal':
        return any(_own(each, bound) for each in read.start[1])
    if kind == 'where':
        return _own(read.start[1], bound) or any(_own(each, True) for each in reads_of(read.start[2]))
    if kind == 'lookup':
        return _own(read.start[1], bound) or any(_own(each, bound) for each in reads_of(read.start[2]))
    if kind == 'by':
        return _own(read.start[1], bound)
    return False


# A cell that is a plain number, or a name with at most one dot: most cells of a large table, which
# are read without the parser (each as the parser reads it).
_CELL_NUMBER = re.compile(r'[-+]?[0-9]+(?:\.[0-9]+)?(?:[eE][-+]?[0-9]+)?\Z')
_CELL_PATH = re.compile(r'([A-Za-z_][A-Za-z0-9_]*)(?:\.([A-Za-z_][A-Za-z0-9_]*))?\Z')


def _cell_number(text):
    """The signed literal of a bare numeric cell, or None for a cell that needs the parser."""
    if not _CELL_NUMBER.fullmatch(text):
        return None
    exact = authored_decimal(text)
    number = float(exact) if any(char in text for char in '.eE') else int(exact)
    return n.Number(number, written=text, exact=Fraction(exact))


def _cell_path(text):
    """The tree of a cell that is a name or `table.id`, or None."""
    found = _CELL_PATH.match(text)
    if found is None:
        return None
    head = n.Name(found[1], line=1, column=1)
    return head if found[2] is None else n.Member(head, found[2], line=1, column=1)


def _cell_expression(text):
    """The tree of a cell as an expression, or None when the cell is no expression."""
    try:
        return parse_expression(text)
    except SyntaxProblem:
        return None


def _spelled(node):
    """A path as written (`places.use.actual_rate`), for a message."""
    if isinstance(node, n.Name):
        return node.name
    if isinstance(node, (n.Member, n.Method)):
        return f'{_spelled(node.base)}.{node.name}' + ('(...)' if isinstance(node, n.Method) else '')
    return 'this expression'


def _broken(family, params):
    """What the parameters of a distribution of numbers break of its family's rule, as the words that
    follow `needs` in its refusal, or None when they hold it. The parameters are in one unit (a
    lognormal's gsd is plain), so `uniform(1 day, 20 h)` compares 24 h with 20 h. The rules are those
    by which the engine draws (`napkin.distributions`): a bounded normal or lognormal keeps some
    probability between its bounds, or no draw has a meaning. Each parameter is read exactly
    (`rational`), so `triangular(0.1 h, 6 min, 1 h)` has its mode at its minimum."""
    a = dict(zip(PARAMETERS[family], map(rational, params)))
    rule = _parameter_rule(family, a)
    if rule is not None or family == 'uniform':
        return rule
    # These families divide by their spread, or take a logarithm, at execution precision.
    # Two distinct authored values can round to the same float, or a positive value to zero.
    rounded = {name: float(value) for name, value in a.items()}
    rule = _parameter_rule(family, rounded)
    if rule is not None:
        return f'{rule} at execution precision'
    if family not in ('normal', 'lognormal') or 'min' not in a:
        return None
    if family == 'normal':
        low, high = ((rounded[end] - rounded['mean']) / rounded['sd'] for end in ('min', 'max'))
    else:
        spread, centre = math.log(rounded['gsd']), math.log(rounded['median'])
        low = (math.log(rounded['min']) - centre) / spread if rounded['min'] > 0 else -math.inf
        high = (math.log(rounded['max']) - centre) / spread
    return None if _mass(low, high) > 0 else 'bounds that hold some probability'


def _parameter_rule(family, a):
    """The order and sign requirements of a distribution in one unit."""
    if family == 'uniform':
        return None if a['min'] < a['max'] else 'min below max'
    if family in ('triangular', 'pert'):
        held = a['min'] <= a['mode'] <= a['max'] and a['min'] < a['max']
        return None if held else 'min <= mode <= max, with min below max'
    if family == 'loguniform':
        return None if 0 < a['min'] < a['max'] else '0 < min < max'
    if family == 'normal':
        if a['sd'] <= 0:
            return 'sd above 0'
        if 'min' in a and a['min'] >= a['max']:
            return 'min below max'
    else:
        if a['median'] <= 0:
            return 'median above 0'
        if a['gsd'] <= 1:
            return 'gsd above 1'
        if 'min' in a and not 0 <= a['min'] < a['max']:
            return '0 <= min < max'
    return None


def _mass(low, high):
    """The probability of a standard normal between two bounds, from its smaller tail, as the engine
    reckons it (`napkin.distributions`): 0 when it underflows."""
    root = math.sqrt(2)
    if low > 0:
        return (math.erfc(low / root) - math.erfc(high / root)) / 2
    return (math.erfc(-high / root) - math.erfc(-low / root)) / 2


def _written(value):
    """A number written out with its unit, for a message: `1 day`, `6`."""
    number = value.value
    if value.exact is not None and rational(number) != value.exact:
        number = value.exact
    shown = _fraction_text(number) if isinstance(number, Fraction) else str(number)
    return f'{shown} {value.type.unit}'.strip()


def _zero(value):
    return (
        isinstance(value, Const)
        and isinstance(value.value, (int, float))
        and value.value == 0
        and value.type == PLAIN
    )


# The refusals of the parts of a package that a text alone cannot have, and of a setting by its path.
STATUS_FALLBACK = (
    'the last case of a status display, and only it, has no condition: it is the fallback, as '
    '`status degraded` under `status ok when this.done`'
)
STATUS_NAME = '{} names the status display: the entity declares no value of that name'
USE_ALONE = "use names a module of a package: a model with modules is read from its package's main file"
VARIANT_ALONE = (
    "a variant is read with its package's main file, from variants/<name>/model.scn of the package"
)
PROPERTY_IN_ENTITY = (
    '{} is a setting of a part: it is written under the part, or at the top level by its full path, '
    'as clinic.delivery.request = 3 L/h'
)
# What the setup scope initializes by a path.
SETUP_TARGETS = (
    "the setup scope initializes a value, a flow's request or capacity, a leg's or an endpoint's "
    'setting of an entity written once, or a value of a member written by hand'
)


def merged_notes(earlier, later):
    """The notes of two blocks: a later note replaces the note of its key, and the notes under one
    key merge the same way, in the order in which their keys first appear."""
    out = {note.key: note for note in earlier}
    for note in later:
        first = out.get(note.key)
        out[note.key] = note if first is None else replace(note, notes=merged_notes(first.notes, note.notes))
    return tuple(out.values())


def setting_key(setting):
    """What a setting sets: (`*Template` for every member of a template, or the member's id, the
    input's name)."""
    return (f'*{setting.instances}' if setting.instances is not None else setting.member, setting.name)


def choice_problem(options):
    """Why options cannot make one run, or None: two of one group, or two that set one input (R-A5-03).
    A member's own line and a line of every member of its template are two values, the member's of
    which wins."""
    groups, sets = {}, {}
    for option in options:
        first = groups.setdefault(option.group, option)
        if first is not option:
            return f'it names two options of the group {option.group}: {first.name} and {option.name}'
        for setting in option.settings:
            other = sets.setdefault(setting_key(setting), option)
            if other is not option:
                return (
                    f'the options {other.name} and {option.name} both set {setting.path}: two options of '
                    'one run set different values (R-A5-03)'
                )
    return None


def constant(value, node, units):
    """The value that an edit gives an input, read from its tree (`Resolver.constant`): raises
    `Refused`."""
    return Resolver(n.File(), units if isinstance(units, Units) else Units(units), tables.no_tables).constant(
        value, node
    )


def _parameter(value, exact):
    """Keep the ordinary int or float representation when it writes the exact parameter in its
    target unit. A more precise decimal or unit conversion stays rational in the artifact."""
    if rational(value) == exact:
        return value
    rounded = float(exact)
    if isinstance(value, float) and rational(rounded) == exact:
        return rounded
    return exact.numerator if exact.denominator == 1 else exact


def exact_value(expression, units):
    """The value of a typed number fixed when the model compiles, exactly and in the canonical unit of
    its dimension, with the model's `Units` (`folded`), or None for one that only a run knows or that
    is no rational number. Every check of a number against another that the front end makes reads
    its numbers here: a range, a domain, the interval of a test, a value in its range, the support of
    a drawn input, a fixed key, a cited datum."""
    found = folded(expression, units)
    return found if isinstance(found, Fraction) else None


def folded(expression, units):
    """The value of a typed expression that the model fixes when it compiles, computed exactly: the
    compiler's own folding of constants. A number is a Fraction in the canonical unit of its
    dimension, the decimal that writes it times its unit's exact scale, so `0.1 day` and `2.4 h` are
    both 12/5 and `34.000000000000000001 h` is not 34; a yes/no is a bool, a text or a member of an
    enum its str. Each operation folds where its result is rational: signs, sums, differences,
    products, quotients, `min`, `max`, `abs`, `clip`, a whole power, a square root (or a power of one
    half) of an exact square, the comparisons, `not`, a membership, and `exp`, `expm1`, `ln`,
    `log1p` and `erf` where they give a whole number; a conditional, `and` and `or` fold from what
    they read, as a run reads it (the branch that a fixed test takes). None for anything else: what a
    value, a reduction, a draw or the time reads is a run's to know."""
    return _literals(units).value(expression)


_SYMBOL = {'==': 'eq', '!=': 'ne', '<': 'lt', '<=': 'le', '>': 'gt', '>=': 'ge'}


def _literal_parts(expression):
    """Operation, operands, and constant data of one typed expression for the shared literal folder."""
    if isinstance(expression, Const):
        if isinstance(expression.type, Num) and not isinstance(expression.value, bool):
            if not isinstance(expression.value, (int, float, Fraction)):
                return 'unknown', (), None
            number = expression.value if expression.exact is None else expression.exact
            return 'number', (), (number, expression.type.unit)
        return 'literal', (), expression.value
    if isinstance(expression, Retain):
        return 'pos', (expression.body,), None
    if isinstance(expression, Apply):
        op = expression.detail if expression.op == 'call' else expression.op
        return (
            op,
            expression.args,
            tuple(_SYMBOL[key] for key in expression.detail) if op == 'compare' else None,
        )
    return 'unknown', (), None


def _literals(units):
    return Literals(_literal_parts, lambda name: units.of(name)[1], DEFAULT_FACTOR)


def _fraction_text(number):
    """An exact terminating decimal for a message, otherwise its fraction."""
    number = Fraction(number)
    denominator = number.denominator
    if denominator == 1:
        return str(number.numerator)
    twos = (denominator & -denominator).bit_length() - 1
    remaining = denominator >> twos
    fives = 0
    while remaining % 5 == 0:
        remaining //= 5
        fives += 1
    if remaining != 1:
        return str(number)
    places = max(twos, fives)
    coefficient = number.numerator * (10**places // denominator)
    return str(Decimal(f'{coefficient}e-{places}'))


def _dimension_text(dimension):
    """A dimension for a message: `time`, `volume/time`, `volume*volume`, or `no dimension`."""
    above = [base for base, power in dimension for _ in range(max(power, 0))]
    below = [base for base, power in dimension for _ in range(max(-power, 0))]
    if not above and not below:
        return 'no dimension'
    return '/'.join(['*'.join(above) or '1', *below])


def declare(tree, units, tables_reader=None, files=()):
    """The declared model of a parsed text (`nodes.File`) with a table of units (`Units`, or a table
    as `Units` takes it), reading its tables with `tables_reader` (`tables.in_folder`,
    `tables.in_memory`; a text with none has no table). The tree of a package's files has their
    `files` (`Files`). Raises `LanguageError` with every problem that it finds."""
    reader = tables_reader or tables.no_tables
    return Resolver(tree, units if isinstance(units, Units) else Units(units), reader, files).model()
