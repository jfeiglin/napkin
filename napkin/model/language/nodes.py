"""The parts of a model file as the parser reads them (docs/language.md).

Each node has its place in the file (`place`, a tuple that is unique in the file) and the line where
it starts (`line`). A place is the name of each declaration that holds it, and a key with its colon
for a keyed line: `('plant', 'outflow', 'min:')`. A line of a block is its number in the block:
`('attacker', 'tamper_again', 'done', 0)`. A declaration at the top level that is not a thing starts
with its keyword and a colon, so that it never has the place of a thing: `('output:', 'deaths')`,
`('options:', 'Response', 'Early response')`.

An expression keeps its tokens (`Expr`); `expressions.py` reads them. A text is a `Text`, whose value
is one text or a list of texts. Evidence is a list of `Cite` (a named record, `@name`) and `Record`
(a record written in place), in the order of the line: the names at its end, then the lines under it.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class Node:
    place: tuple
    line: int


@dataclass
class Text(Node):
    """A text, or a list of texts (`value` is a list)."""

    value: object = None


@dataclass
class Expr(Node):
    """An expression, as its tokens."""

    tokens: list = field(default_factory=list)


@dataclass
class Cite(Node):
    """`@name`: a named record."""

    name: str = ''


@dataclass
class Claim(Node):
    """A claim that a record lists, with the key of an exact figure of the claim's data (`datum`)."""

    id: str = ''
    datum: str | None = None


@dataclass
class Record(Node):
    """A record: `@kind [ID] "explanation"` in place, or `record name: kind [ID] "explanation"` (with
    its `name`). `id` is the assumption ID that it names."""

    kind: str = ''
    id: str | None = None
    text: str = ''
    claims: list = field(default_factory=list)
    name: str | None = None


@dataclass
class Keyed(Node):
    """A key with an expression and its evidence: `when: C  @r`, `wait: d`, `min: 2 h`, `limit: E`. A
    bound (`min:`, `max:`) has a text that says where it comes from."""

    expr: Expr | None = None
    support: list = field(default_factory=list)
    text: Text | None = None


@dataclass
class Bounds(Node):
    """`bounds: sourced` or `bounds: chosen`, with its text and its evidence."""

    kind: str = ''
    text: Text | None = None
    support: list = field(default_factory=list)


@dataclass
class Lag(Node):
    """A reporting lag: `fixed` (one delay), `uniform` (its two edges) or `mixture` (a share, as its
    number token, and a delay for each part)."""

    kind: str = 'fixed'
    delays: list = field(default_factory=list)
    shares: list = field(default_factory=list)


@dataclass
class OutputLines(Node):
    """The lines of an output: of `output name`, or under a value's `output: true`."""

    text: Text | None = None
    support: list = field(default_factory=list)
    about: Text | None = None
    category: str | None = None
    scope: Text | None = None  # whom the output covers
    measure: str | None = None
    signed: bool = False
    distinct: Keyed | None = None
    lag: Lag | None = None
    unestimated: Text | None = None
    keys: dict = field(default_factory=dict)  # {key: place} of each line that it writes


@dataclass
class Value(Node):
    """A value: `kind name[: type] = value`. `type` is a unit as written, `bool`, or a list of named
    values; `value` its default, start value or formula."""

    kind: str = ''
    name: str = ''
    type: object = None
    type_place: tuple = ()
    value: Expr | None = None
    text: Text | None = None
    support: list = field(default_factory=list)
    min: Keyed | None = None
    max: Keyed | None = None
    bounds: Bounds | None = None
    size: Keyed | None = None
    rate: Keyed | None = None
    output: OutputLines | None = None


@dataclass
class Output(Node):
    """`output name: unit = E`, or `output name: unit` with `unestimated:`."""

    name: str = ''
    type: object = None
    expr: Expr | None = None
    lines: OutputLines | None = None


@dataclass
class LinkDecl(Node):
    """A link that a template declares: `link x: T`, or a list, `link xs: [T]`."""

    name: str = ''
    target: str = ''
    many: bool = False


@dataclass
class LinkBind(Node):
    """A link that an entity binds: `link x = e`, or a list, `link xs = [a, b]`."""

    name: str = ''
    targets: object = None  # a name, or a list of names
    many: bool = False


@dataclass
class Assign(Node):
    """`x = v`, `x += v` or `x -= v`."""

    target: str = ''
    op: str = '='
    value: Expr | None = None


@dataclass
class Move(Node):
    """`move A from S to D`."""

    amount: Expr | None = None
    source: str = ''
    target: str = ''


@dataclass
class Fire(Node):
    """A line that names an event, which then fires: `e`, `thing.e`, or `list.e` for each member."""

    target: str = ''


@dataclass
class Outcome(Node):
    """An outcome of an event: its name, its chance (`chance`: an expression, None for 1, or `else`
    when `is_else`), the condition under which it can happen (`when`, None for always), its text, role
    and evidence, and its lines. The one outcome of an event that writes its lines under itself is
    `done`."""

    name: str = 'done'
    chance: Expr | None = None
    is_else: bool = False
    when: Expr | None = None
    text: Text | None = None
    role: str | None = None
    support: list = field(default_factory=list)
    lines: list = field(default_factory=list)


@dataclass
class Event(Node):
    """`event name [once] [after D] [each W] [when C] [while K]:`, its text, role, `choice` and evidence,
    and its outcomes. An event with no `when` and no `each` fires only when a line names it; an event with
    no lines changes nothing. A `choice` is an actor's event whose outcome a person or an agent can
    choose in a run."""

    name: str = ''
    once: bool = False
    after: Expr | None = None
    each: list = field(default_factory=list)  # Expr: the values of its window
    when: Expr | None = None
    keep: Expr | None = None  # `while K`: the condition under which a waiting firing still happens
    text: Text | None = None
    role: str | None = None
    choice: bool = False
    support: list = field(default_factory=list)
    outcomes: list = field(default_factory=list)  # Outcome; one `done` for an event with lines


@dataclass
class Pair(Node):
    """A pair of a flow: `A -> B`, with its own evidence and rate. The pair on the flow's line has
    neither, and the place of the flow; the pair of one, on a line of its own, has its evidence."""

    source: str = ''
    target: str = ''
    support: list = field(default_factory=list)
    rate: Keyed | None = None


@dataclass
class Flow(Node):
    """`flow name: A -> B`, `flow name:` with its pair on a line under it (`pair`, with its records), or
    `flow name:` with `together:`."""

    name: str = ''
    pair: Pair | None = None
    text: Text | None = None
    support: list = field(default_factory=list)
    rate: Keyed | None = None
    keep: Keyed | None = None  # `while:`
    together: list | None = None  # Pair
    together_support: list = field(default_factory=list)
    together_place: tuple = ()


@dataclass
class Allocate(Node):
    """`share VAR limit RATE [order f, g]`: its stock, its limit, and the flows that it serves in order
    (`serve`, a list of (name, place)), or in proportion (`serve` None)."""

    name: str = ''
    text: Text | None = None
    support: list = field(default_factory=list)
    stock: str = ''
    stock_place: tuple = ()
    limit: Keyed | None = None
    serve: list | None = None
    serve_place: tuple = ()


@dataclass
class Check(Node):
    """`assert C [within TOL]`, or a sum, `assert a + b is T within TOL` (`terms`, each (name, place),
    and `total`)."""

    kind: str = ''
    expr: Expr | None = None
    terms: list = field(default_factory=list)
    total: Expr | None = None
    within: Keyed | None = None
    severity: str | None = None
    text: Text | None = None
    support: list = field(default_factory=list)


@dataclass
class StatusLine(Node):
    """A line of `status:`: a status and its condition (None for the last line), and its text. The
    records written under it support the status, as those on its line do."""

    status: str = ''
    condition: Expr | None = None
    text: Text | None = None
    support: list = field(default_factory=list)


@dataclass
class Status(Node):
    lines: list = field(default_factory=list)
    support: list = field(default_factory=list)


@dataclass
class Change(Node):
    """A line of an instance that changes a member of its template: `m = v`, `m:` with lines under it,
    or a line with a kind, `input m = v` (`kind`, `type`). `lines` holds what the change gives: a
    `Value` with the parts that it writes."""

    name: str = ''
    kind: str | None = None
    lines: Value | None = None
    together: list | None = None  # the evidence of a flow's `together:`


@dataclass
class Column(Node):
    """A column of a table (`Table`), from its header `name`, `name: unit` and then `@record`s: the
    member of the template, the link or `title` that its cells give; the unit of its numbers, as
    written (`type`, like the type of a value); and the records that its header cites."""

    name: str = ''
    type: str | None = None
    support: list = field(default_factory=list)


@dataclass
class Row(Node):
    """A row of a table: its cells as the file writes them, without the spaces around each; an empty
    cell is `''`. Its line is its line in the file of the table."""

    cells: list = field(default_factory=list)


@dataclass
class Table(Node):
    """`from "file.csv"` on the line of an instance (docs/language.md, §2.3): each row of the table is
    one instance. `file` is the path as written, from the folder of the package. `columns` and `rows`
    come from the file (`tables.fill`); they are None for a model that is given as a text, which has
    no folder."""

    file: str = ''
    columns: list | None = None
    rows: list | None = None


@dataclass
class Thing(Node):
    """`n:`, `n: T` (an instance), `n: T * k` (k copies), `n: T from "file.csv"` (one instance for each
    row of a table) or `T:` (a template), with its members in order. `sees` lists the facts that an
    actor observes, or is None for a thing of the world."""

    kind: str = 'entity'
    name: str = ''
    template: str | None = None
    text: Text | None = None
    support: list = field(default_factory=list)
    title: Text | None = None
    role: str | None = None
    copies: int | None = None
    copies_place: tuple = ()
    members: list = field(default_factory=list)
    sees: list | None = None  # (name as written, place)
    sees_place: tuple = ()
    table: Table | None = None


@dataclass
class Setting(Node):
    """A line of a profile: `entity.field = v` or `Template.field = v`."""

    target: str = ''
    value: Expr | None = None
    support: list = field(default_factory=list)


@dataclass
class Profile(Node):
    name: str = ''
    text: Text | None = None
    settings: list = field(default_factory=list)


@dataclass
class Profiles(Node):
    """`profiles "Group":`."""

    name: str = ''
    profiles: list = field(default_factory=list)


@dataclass
class Run(Node):
    """A line of `runs:`: its name, its profiles, its text and the run that it is compared with."""

    name: str = ''
    profiles: list = field(default_factory=list)
    text: Text | None = None
    versus: str | None = None
    versus_place: tuple = ()


@dataclass
class Note(Node):
    """A line of `notes:`: `key: value`, with its evidence and the notes under it. A value is a text,
    a number (its token), a word, a list of values, or None. The language gives no key a meaning."""

    key: str = ''
    value: object = None
    support: list = field(default_factory=list)
    under: list = field(default_factory=list)


@dataclass
class ScenarioBlock(Node):
    """The first declaration of a package's main file, `scenario "Title"` (`role` main), or of a
    variant, `variant "Title"` (`role` variant), with the scenario's fields under it. A field that a
    variant writes replaces the main file's (`modules.overlay_scenario`); only the main file names the
    library."""

    role: str = 'main'
    title: Text | None = None
    summary: Text | None = None
    horizon: Expr | None = None
    timescales: list | None = None  # Expr
    resolution: Expr | None = None  # the longest step of the solver, when the file gives one
    scope: Text | None = None  # whom the outputs that give no scope cover
    library: Text | None = None  # the folder of the library, relative to the main file
    # The title of the variant whose fields overlay the main file's, in a merged model of a variant.
    variant: Text | None = None


@dataclass
class File:
    """A model file: its parts in the order of the file, the place of each line (`lines`, {place:
    line}) and the column where each of those lines starts (`columns`, {place: column}, from 1). The
    columns are a map of their own, so that the lines, which order the events of one moment, stay
    numbers. Its role is its first declaration (`role`): the main file of a package (`scenario
    "Title"`), a variant (`variant "Title"`) or a module (anything else)."""

    scenario: ScenarioBlock | None = None
    things: list = field(default_factory=list)
    checks: list = field(default_factory=list)  # Check, at the top level
    outputs: list = field(default_factory=list)  # Output, at the top level
    profiles: list = field(default_factory=list)  # Profiles: the groups of options
    runs: list = field(default_factory=list)  # Run
    runs_place: tuple | None = None
    notes: list | None = None  # Note
    records: list = field(default_factory=list)  # Record, named
    lines: dict = field(default_factory=dict)
    columns: dict = field(default_factory=dict)
    uses: list = field(default_factory=list)  # Use: the modules whose declarations join the model
    changes: list = field(
        default_factory=list
    )  # Thing of kind 'change': lines over a thing of an earlier file

    @property
    def role(self):
        """`main`, `variant` or `module`: the role that the file's first declaration gives it."""
        return 'module' if self.scenario is None else self.scenario.role


@dataclass
class Use(Node):
    """`use NAME`: the declarations of the module NAME are part of the model of the file. A name is
    read from the folder of the package: `use a.b` is the file `<package>/a/b.scn`."""

    name: str = ''
