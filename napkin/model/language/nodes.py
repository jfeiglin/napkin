"""The tree of a model text: one frozen record for each kind of expression, type and line.

The parser (`parse.py`) makes the tree and the formatter (`format.py`) writes it again; the declared
model (`napkin/model/semantic.py`) reads it. Two texts that mean the same have equal trees: a place in
the file (`line`, `column`) and the layout (comments, `lead` and `tail`; a range written on a row of
its own) take no part in equality, so `parse(format(tree)) == tree`.

Expressions keep what the author wrote and nothing that a name means. In particular a number's unit is
its *unit run* (`Quantity.unit`, D12): the names joined by `*` and `/` that follow the number for as
long as each is a bare name. Which of them are units and which are values is the declared model's to
say, by the units of the library; the arithmetic is the same either way.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from fractions import Fraction


def _place():
    """A field of a place or a layout: kept for messages and for the formatter, never compared."""
    return field(default=0, compare=False, repr=False, kw_only=True)


def _layout(default=()):
    return field(default=default, compare=False, repr=False, kw_only=True)


@dataclass(frozen=True)
class Node:
    """A node with its place in the file."""

    line: int = _place()
    column: int = _place()


# ---- expressions ------------------------------------------------------------------------------------


def _decimal(value, written):
    """The exact number that a token writes (`34.000000000000000001`, which no float holds), or that
    a number made by hand is: the decimal that writes it (`0.1` is 1/10)."""
    try:
        return Fraction(written) if written else Fraction(repr(value) if isinstance(value, float) else value)
    except (ValueError, TypeError, OverflowError):
        return None


@dataclass(frozen=True)
class Number(Node):
    """A number with no unit: an int, or a float when it is written with a point or an exponent.
    `written` is its spelling (`0.30`), which the formatter keeps. `exact` is the exact decimal that
    it writes, never read through a float: the front end compares numbers by it, so two numbers that
    a float cannot tell apart (`34` and `34.000000000000000001`) are two trees."""

    value: int | float
    written: str = _layout('')
    exact: Fraction | None = field(default=None, kw_only=True, repr=False)

    def __post_init__(self):
        if self.exact is None:
            object.__setattr__(self, 'exact', _decimal(self.value, self.written))


@dataclass(frozen=True)
class Quantity(Node):
    """A number and its unit run: `5 L/h` is (5, (('', 'L'), ('/', 'h'))). `exact` is the exact
    decimal of its number, as for a `Number`."""

    value: int | float
    unit: tuple[tuple[str, str], ...]
    written: str = _layout('')
    exact: Fraction | None = field(default=None, kw_only=True, repr=False)

    def __post_init__(self):
        if self.exact is None:
            object.__setattr__(self, 'exact', _decimal(self.value, self.written))


@dataclass(frozen=True)
class Text(Node):
    value: str


@dataclass(frozen=True)
class Bool(Node):
    value: bool


@dataclass(frozen=True)
class Name(Node):
    """A bare name: a value, `this`, `t`, an entity, a template or an enum member (a capital)."""

    name: str


@dataclass(frozen=True)
class Member(Node):
    """`base.name`."""

    base: Node
    name: str


@dataclass(frozen=True)
class Method(Node):
    """An operation after a dot: `.where(...)`, `.by(...)`, `.at(...)`, `.draw()`, `.start(...)`,
    `.choose(...)`."""

    base: Node
    name: str
    args: tuple[Node, ...] = ()


@dataclass(frozen=True)
class Call(Node):
    """A call of a function of the language. `named` holds the outcomes of `categorical(A: p, B: q)`."""

    function: str
    args: tuple[Node, ...] = ()
    named: tuple[tuple[str, Node], ...] = ()


@dataclass(frozen=True)
class Formula(Node):
    """`formula(body)`: a calculation that is kept."""

    body: Node


@dataclass(frozen=True)
class Unary(Node):
    """`-x`, `+x` or `not x`."""

    op: str
    operand: Node


@dataclass(frozen=True)
class Binary(Node):
    """`+`, `-`, `*`, `/` or `**`."""

    op: str
    left: Node
    right: Node


@dataclass(frozen=True)
class Compare(Node):
    """A chain of comparisons that points one way: `lo <= x < hi`."""

    ops: tuple[str, ...]
    operands: tuple[Node, ...]


@dataclass(frozen=True)
class BoolOp(Node):
    """`a and b and c`, or `or`."""

    op: str
    values: tuple[Node, ...]


@dataclass(frozen=True)
class IfElse(Node):
    """`body if test else orelse`."""

    test: Node
    body: Node
    orelse: Node


@dataclass(frozen=True)
class Within(Node):
    """`value in [low, high]`, a membership test; a side left empty is None."""

    value: Node
    low: Node | None
    high: Node | None


@dataclass(frozen=True)
class Collection(Node):
    """`<a, b>`, or `<>`."""

    items: tuple[Node, ...] = ()


# ---- types --------------------------------------------------------------------------------------------


@dataclass(frozen=True)
class UnitOp:
    """`left * right` or `left / right` in the unit of a type; a leaf is a unit's name (or `1`)."""

    op: str
    left: UnitOp | str
    right: UnitOp | str


@dataclass(frozen=True)
class WordType(Node):
    """`bool`, `text` or `number`."""

    word: str


@dataclass(frozen=True)
class NamedType(Node):
    """One name where a type stands: a unit (`g`) or a template (`Place`)."""

    name: str


@dataclass(frozen=True)
class UnitType(Node):
    """A unit made of others: `L/h`, `person * year`, `tunings / (tuner * year)`."""

    unit: UnitOp


@dataclass(frozen=True)
class EnumType(Node):
    members: tuple[str, ...]


@dataclass(frozen=True)
class FormulaType(Node):
    of: Node


@dataclass(frozen=True)
class CollectionType(Node):
    of: Node


@dataclass(frozen=True)
class DistributionType(Node):
    of: Node


@dataclass(frozen=True)
class Range(Node):
    """`in [low, high]`: a closed range, either side left empty (None)."""

    low: Node | None
    high: Node | None


# ---- evidence -----------------------------------------------------------------------------------------


@dataclass(frozen=True)
class Cite(Node):
    """`@name`: a record of the model."""

    name: str


@dataclass(frozen=True)
class Claim(Node):
    """A claim of a record by its ID, with the key of one of its data (`datum:`)."""

    id: str
    datum: str = ''


@dataclass(frozen=True)
class Inline(Node):
    """A record written in place under a line: `@kind "explanation"`, with the IDs that it rests on
    (`assumption A-TIMING`) and its claims under it."""

    kind: str
    text: str
    relations: tuple[tuple[str, str], ...] = ()
    claims: tuple[Claim, ...] = ()


# ---- lines ---------------------------------------------------------------------------------------------


@dataclass(frozen=True)
class Line(Node):
    """A logical line. `lead` holds the comment and empty rows just above it, each (depth, text) with
    '' for an empty row; `tail` the comments that end its rows."""

    lead: tuple[tuple[int, str], ...] = _layout()
    tail: tuple[str, ...] = _layout()


@dataclass(frozen=True)
class Described(Line):
    """A line with what describes it: the records named at its end (`cites`), its text, and the
    evidence rows under it (`Cite` and `Inline`)."""

    cites: tuple[Cite, ...] = field(default=(), kw_only=True)
    text: str | None = field(default=None, kw_only=True)
    evidence: tuple[Cite | Inline, ...] = field(default=(), kw_only=True)


@dataclass(frozen=True)
class Record(Line):
    """`record name: kind "explanation"`, with its relations and claims under it."""

    name: str
    kind: str
    text: str
    relations: tuple[tuple[str, str], ...] = ()
    claims: tuple[Claim, ...] = ()


@dataclass(frozen=True)
class Scenario(Line):
    """The first line of a main file (`scenario "Title"`) or of a variant (`variant "Title"`), with the
    lines under it."""

    role: str
    title: str
    summary: str | None = None
    horizon: Node | None = None
    scope: str | None = None
    library: str | None = None
    resolution: Node | None = None


@dataclass(frozen=True)
class Use(Line):
    """`use a.b`: the module `a/b.scn` of the package."""

    name: str


@dataclass(frozen=True)
class Property(Described):
    """`path = value` under a value, a flow or an instance, or by its full path in the setup scope."""

    path: tuple[str, ...]
    value: Node


@dataclass(frozen=True)
class Declaration(Described):
    """`[readonly | input] name[: type] [= value] [in [lo, hi]] [scale s]`, with its properties under
    it. With no value and a template as its type, it is an instance of that template, which may have
    its `title`."""

    modifier: str
    name: str
    type: Node | None = None
    value: Node | None = None
    range: Range | None = None
    scale: Node | None = None
    properties: tuple[Property, ...] = ()
    title: str | None = None
    range_row: bool = _layout(False)


@dataclass(frozen=True)
class Flow(Described):
    """`flow name: source -> sink`, `flow name: a <-> b`, or `flow name:` with its legs under it. An
    end is a path of names, or `SOURCE` or `SINK`."""

    name: str
    arrow: str = ''
    source: tuple[str, ...] = ()
    sink: tuple[str, ...] = ()
    properties: tuple[Property, ...] = ()
    legs: tuple[Flow, ...] = ()


@dataclass(frozen=True)
class Param(Node):
    """A parameter of an event: `name: type [in [lo, hi]]`."""

    name: str
    type: Node
    range: Range | None = None


@dataclass(frozen=True)
class Assign(Line):
    """`target = value`, `+=` or `-=` in a stage."""

    target: Node
    op: str
    value: Node
    cites: tuple[Cite, ...] = ()


@dataclass(frozen=True)
class Start(Line):
    """`event.start(args)` on a line of its own: `call` is the `Method` named `start`."""

    call: Method


@dataclass(frozen=True)
class Move(Line):
    """`move amount from source to destination`."""

    amount: Node
    source: Node
    destination: Node
    cites: tuple[Cite, ...] = ()


@dataclass(frozen=True)
class If(Line):
    """`if test:` with its body, and `else:` with its own (None when there is no else)."""

    test: Node
    then: tuple[Line, ...]
    orelse: tuple[Line, ...] | None = None


@dataclass(frozen=True)
class Case(Described):
    """`MEMBER [when guard]:` in a switch, with its body."""

    member: str
    guard: Node | None = None
    body: tuple[Line, ...] = ()


@dataclass(frozen=True)
class Switch(Line):
    """`switch selector:` with its cases and an optional `else:`."""

    selector: Node
    cases: tuple[Case, ...]
    orelse: tuple[Line, ...] | None = None


@dataclass(frozen=True)
class Stage(Described):
    """`after delay [when guard]:` with its body, or `after delay` alone: a wait."""

    delay: Node
    guard: Node | None = None
    body: tuple[Line, ...] = ()
    wait: bool = False


@dataclass(frozen=True)
class Gate(Line):
    """`until test`."""

    test: Node


@dataclass(frozen=True)
class Capture(Line):
    """`name = value` in a trigger: a value that the firing keeps."""

    name: str
    value: Node


@dataclass(frozen=True)
class Reset(Line):
    """`reset when test` or `reset after duration`: the last line of a trigger."""

    kind: str
    value: Node


@dataclass(frozen=True)
class Trigger(Described):
    """`when test:` of an event: its captures, its starts and its reset."""

    test: Node
    captures: tuple[Capture, ...] = ()
    starts: tuple[Start, ...] = ()
    reset: Reset | None = None


@dataclass(frozen=True)
class Event(Described):
    """`[readonly] name = event(params):` with its locals and flows (in written order), its triggers
    and its steps."""

    modifier: str
    name: str
    params: tuple[Param, ...] = ()
    locals: tuple[Declaration | Flow, ...] = ()
    triggers: tuple[Trigger, ...] = ()
    steps: tuple[Stage | Gate, ...] = ()


@dataclass(frozen=True)
class Binding(Line):
    """`name = value` under `inputs:` of a solver."""

    name: str
    value: Node


@dataclass(frozen=True)
class Unknown(Line):
    """A new unknown of a solver: `name: type [= value] [in [lo, hi]] [scale s]`."""

    name: str
    type: Node
    value: Node | None = None
    range: Range | None = None
    scale: Node | None = None


@dataclass(frozen=True)
class Objective(Line):
    """`minimize(expr)` or `maximize(expr)`."""

    sense: str
    value: Node


@dataclass(frozen=True)
class Solver(Described):
    """`[readonly] name = solver:` with its four sections."""

    modifier: str
    name: str
    inputs: tuple[Binding, ...] = ()
    solve_for: tuple[Node | Unknown, ...] = ()
    constraints: tuple[Node, ...] = ()
    objective: tuple[Objective, ...] = ()


@dataclass(frozen=True)
class Status(Described):
    """`status rating [when test]`: a case of a status display."""

    rating: str
    test: Node | None = None


@dataclass(frozen=True)
class Assert(Described):
    """`assert test`."""

    test: Node


@dataclass(frozen=True)
class Sees(Line):
    """`sees path`: what a human player of this actor is shown."""

    path: Node


@dataclass(frozen=True)
class Entity(Described):
    """`name:` (an entity) or `Name:` (a template), with its members; `title` describes it for
    displays. It has no role: who plays a part is the scenario's wrapper's, and the pictures'
    stylesheet's (docs/design/decisions.md, change 23)."""

    name: str
    members: tuple[Line, ...] = ()
    title: str | None = None


@dataclass(frozen=True)
class Table(Described):
    """`name: Template from "file.csv"`: one member of the template for each row of the file."""

    name: str
    template: str
    file: str


@dataclass(frozen=True)
class Change(Described):
    """`change name:`: lines that change an entity, a template or a member written by hand of an
    earlier file: values and links under it, and its text and `title`."""

    name: str
    members: tuple[Line, ...] = ()
    title: str | None = None


@dataclass(frozen=True)
class Option(Described):
    """`"Option":` in an options group, with its text (its line in a menu) and its settings."""

    name: str
    settings: tuple[Property, ...] = ()


@dataclass(frozen=True)
class Options(Line):
    """`options "Group":` with its options."""

    group: str
    options: tuple[Option, ...] = ()


@dataclass(frozen=True)
class RunLine(Described):
    """`name = "Option" + "Option"` under `runs:`, with its text."""

    name: str
    options: tuple[str, ...] = ()


@dataclass(frozen=True)
class Runs(Line):
    """`runs:` with its named runs."""

    runs: tuple[RunLine, ...] = ()


@dataclass(frozen=True)
class Note(Line):
    """`key: value` under `notes:`: a text, a number, a word or a list, its records, and the notes
    under it. The calculation never reads a note."""

    key: str
    value: object = None
    cites: tuple[Cite, ...] = ()
    notes: tuple[Note, ...] = ()
    evidence: tuple[Cite | Inline, ...] = ()


@dataclass(frozen=True)
class Notes(Line):
    """`notes:` with its notes."""

    notes: tuple[Note, ...] = ()


@dataclass(frozen=True)
class File:
    """The lines of a text at the top level, and the comment rows after its last line."""

    items: tuple[Line, ...] = ()
    trailing: tuple[tuple[int, str], ...] = field(default=(), compare=False, repr=False)

    @property
    def scenario(self):
        """The scenario line, or None."""
        return next((item for item in self.items if isinstance(item, Scenario)), None)
