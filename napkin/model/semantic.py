"""The semantic model of a scenario (docs/language.md).

It says what a scenario declares, in terms that do not depend on the syntax of its file: its
entities and their values, its profiles and its runs, and its evidence. The front end fills it from
a model file (`model/language/resolve.py`). The builder, the run table and the evidence index read it.

Every part has `where`, its place in the file: a tuple of the keys and names of the lines that hold
it, which the diagnostics write as `a/b/c` (`path_text`) and the line map turns into a line. Content
passes through as written, frozen (`ir.freeze`): texts, written values and evidence records keep
their shape, and a reader thaws what it needs.

An expression (`Expression`) holds typed nodes whose names are resolved (`napkin/model/resolved.py`).
The front end makes them from its own working tree, a Python `ast` tree: each name of a value is a
`Ref`, each event that `since()` or `count()` reads is an `EventRef`, the argument of `sum()` is
`Terms`, and `true` and `false` are `Word`s. The time stays the name `t`.

The front end never fails on a part that the builder reads: a part that it cannot read holds a
`Problem`, and the builder raises its message where it reads the part, so the diagnostics keep
their order. Each part has the place where the builder reports it.
"""

from __future__ import annotations

import ast
import re
from collections.abc import Mapping
from dataclasses import dataclass
from types import MappingProxyType


def path_text(where):
    """The text of a place: `service/rate`, `notes:/premises:/START:`."""
    return '/'.join(map(str, where))


# ---- names and the problem of a part ------------------------------------------------------------
#
# Every name is the structure's (docs/python-api.md, "Names"): an entity is its name, and copy k of a
# set, `set.k`, is `set_k`, because a name in an expression is an identifier. A value is
# `entity.value`, an event and its rule `entity.event`, and a milestone of the main and the first
# move keep their names.

# The entity of the parts that belong to no single entity.
MAIN = 'simulate'
# The one run of a model whose file has no runs and no options.
BASE_RUN = 'base'


class AnalysisError(Exception):
    """A part of the file that the builder cannot read, with the place of the part."""

    def __init__(self, path, message):
        self.path = tuple(path)
        super().__init__(message)


def as_list(value):
    return value if isinstance(value, list) else [value]


def split_key(key):
    """(entity, value) of `entity.value`; an entity name can hold dots (a copy, `waves.1`)."""
    entity, _, member = key.rpartition('.')
    return entity, member


def flat_entity(name):
    """An entity's name in the structure: its own, and `set_k` for copy k of a set (`set.k`)."""
    return name.replace('.', '_')


def flat_key(key):
    """`entity.value` of a key, with the entity's name in the structure (`set.k.value` is
    `set_k.value`)."""
    entity, member = split_key(key)
    return f'{flat_entity(entity)}.{member}'


def first_text(doc):
    """The text of the first time that an event happens: a text can list one text for each time."""
    return doc[0] if isinstance(doc, list) else doc


_WORD = re.compile(r'[A-Z]+(?=[A-Z][a-z])|[A-Z]?[a-z]+|[A-Z]+|\d+')


def in_words(name):
    """A template or entity name in words: `RepairCrews` reads "Repair crews", `AIAgent` "AI agent" and
    `first_batch` "First batch". An acronym keeps its capitals; every other word after the first is
    in lower case."""
    parts = [w for chunk in name.split('_') for w in (_WORD.findall(chunk) or [chunk]) if w]

    def word(w, first):
        if len(w) > 1 and w.isupper():
            return w
        return w[:1].upper() + w[1:].lower() if first else w.lower()

    return ' '.join(word(w, i == 0) for i, w in enumerate(parts))


def value_label(text, title, shared):
    """The name of a value on the pages: its text, after its entity's title when another entity of its
    template shows the same text for the value (`shared`), so that two entities never show one label
    ("First group: instances restored"). After the colon the text goes on in lower case, unless it
    starts with an acronym ("AI")."""
    if text is None or not shared:
        return text
    first = text.split(' ', 1)[0]
    lower = first[1:] == first[1:].lower()
    return f'{title}: {text[:1].lower() + text[1:] if lower else text}'


@dataclass(frozen=True, eq=False)
class Expression:
    """An expression as the file writes it (`written`: a text or a number), and its typed nodes with
    its names resolved (`node`, `napkin/model/resolved.py`). The node is a `Problem` when the front end
    cannot read the expression, and None for a bare number, which has no nodes of its own."""

    written: object
    node: object
    where: tuple


@dataclass(frozen=True, eq=False)
class Bound:
    """The minimum, maximum or size of a stock, tally or number state: a number with its unit, or an
    expression. A problem of its unit is reported at `unit_where`."""

    expression: Expression
    unit_where: tuple


@dataclass(frozen=True, eq=False)
class Rate:
    """The rate of a stock, tally or number state, with its own records, or None for its value's."""

    expression: Expression
    records: object
    where: tuple


@dataclass(frozen=True, eq=False)
class Words:
    """A text whose braces name text values (`{actor}`), filled; or why they cannot be
    (`problem`)."""

    text: object
    problem: object
    where: tuple


@dataclass(frozen=True, eq=False)
class Fault:
    """A problem that the front end found in a part, and where the builder reports it."""

    message: str
    where: tuple


@dataclass(frozen=True, eq=False)
class Time:
    """A time as the file writes it: `24 h`."""

    written: object
    where: tuple


@dataclass(frozen=True, eq=False)
class Range:
    """The range of a value, as written: its edges, each `(written, where)` or None for an edge that
    the file leaves out, and its basis (a range note and records)."""

    edges: tuple
    basis: object
    where: tuple


@dataclass(frozen=True, eq=False)
class Setting:
    """The value that one profile gives a value, as written: `{value, basis}`, or a bare value. The
    rest is read from it: the value that it sets (`target`), the value that it gives and its records,
    the value as the start value of a state, stock or tally (`start`), and where it writes the value
    (`value_at`). `places` are the places of the profile's lines for the value, which the evidence
    report reads."""

    profile: str
    written: object
    where: tuple
    target: str | None = None
    value: object = None
    records: object = None
    start: Expression | None = None
    value_at: tuple = ()
    places: tuple = ()


@dataclass(frozen=True, eq=False)
class Value:
    """A value of an entity. Its kind is `input`, `fixed`, `state`, `stock`, `tally`, `formula`,
    `output` or `text`, or None for a member that is none of them."""

    name: str
    kind: str | None
    type: object  # as written: a unit (with its braces), `bool`, named values, or `text`
    text: object  # its label, as written
    value: object  # its default, start value or text, as written
    range: Range | None
    records: object  # its basis, as written
    settings: tuple  # Setting, in the order of the profiles
    where: tuple  # its declaration
    value_where: tuple  # where the file writes the value, its range and its type, for the run table
    range_where: tuple  # (an instance's change writes them in the instance)
    type_where: tuple
    label: object = None  # its name on the pages: its text, after its entity's title when another
    #                       entity of its template shows the same text
    initial: Expression | None = None  # the start value of a state, stock or tally
    minimum: Bound | None = None
    maximum: Bound | None = None
    size: Bound | None = None  # the size that it reaches, for one that the engine cannot size
    rate: Rate | None = None
    formula: Expression | None = None
    output: Output | None = None
    # The arguments of its distributions that read other values: (where, the distribution's text,
    # ((argument, Expression), ...)) for each distribution, its default first.
    arguments: tuple = ()
    # Where the builder reports the value, its range, the two edges of its range, its unit and its
    # records.
    value_at: tuple = ()
    range_at: tuple = ()
    edges_at: tuple = ()
    unit_where: tuple = ()
    records_at: tuple = ()


@dataclass(frozen=True, eq=False)
class Lag:
    """The reporting lag of an output: `fixed` (one delay), `uniform` (its two edges) or `mixture` (a
    weight, as written, for each delay)."""

    kind: str
    delays: tuple  # Expression
    weights: tuple
    where: tuple


@dataclass(frozen=True, eq=False)
class Output:
    """An output: of the scenario (`entity` None), or a value of an entity that is also an output, with
    that value's name, type and formula."""

    name: str
    entity: str | None
    text: object  # its text
    label: object  # its name on the pages
    type: object
    unit_where: tuple
    measure: object  # `cumulative`, `stock`, `instantaneous` or `net`
    reports: object  # its category, a tag as written, or None
    about: object
    scope: object  # whom it covers, as written, or None
    signed: bool
    not_estimated: object  # why it is not estimated, or None
    lag: Lag | None
    distinct: Site | None  # the records that say why the terms that it adds are distinct
    records: object
    formula: Expression | None
    formula_where: tuple  # where the builder reports its expression
    where: tuple
    places: tuple = ()  # the places of the file that write it, which the evidence report reads


@dataclass(frozen=True, eq=False)
class Case:
    """A case of a status: its condition (None for the last case, which holds when no other does), its
    value, its text and its records."""

    condition: Expression | None
    value: object
    text: Words
    records: object
    where: tuple


@dataclass(frozen=True, eq=False)
class Status:
    """The status of an entity: its cases, in order, and its own records (None: its entity's)."""

    cases: tuple
    where: tuple
    records: object = None


@dataclass(frozen=True, eq=False)
class Check:
    """A check of an entity (`entity`), or of the scenario (None). A `sum` adds stocks (`parts`: each a
    `Ref`, or a `Problem`), which equal `total`, within `within`. A `check` tests the inputs
    (`condition`), with its severity; an `always` holds in every state."""

    kind: str
    entity: str | None
    parts: tuple
    total: Expression | None
    within: Expression | None
    condition: Expression | None
    severity: object
    message: object
    records: object
    where: tuple
    parts_where: tuple  # where the builder reports a part of a sum


@dataclass(frozen=True, eq=False)
class Pair:
    """A pair of a flow: the stocks or tallies that it moves between (`ends`: (`from` or `to`, a `Ref`
    or a `Problem`), without an end outside the model), its own rate and records (None: the flow's),
    and whether it writes its own rate or records (`own`: then its parts are reported at the pair)."""

    ends: tuple
    rate: Expression | None
    records: object
    own: bool
    where: tuple


@dataclass(frozen=True, eq=False)
class Flow:
    """A flow: its pairs, which move together, its rate and the condition while it flows (`while`)."""

    name: str
    pairs: tuple
    rate: Expression
    condition: Expression | None
    text: object  # its text
    records: object
    together: Site | None  # the records that say why its pairs move together
    where: tuple


@dataclass(frozen=True, eq=False)
class Allocation:
    """A stock that several flows draw on, shared among them up to its limit: in the listed order
    (`serve`: for each flow, (its name as written, its entity or a `Problem`, the flow's name, where)),
    or in proportion (`serve` None)."""

    name: str
    stock: object  # a Ref, or a Problem
    limit: Expression
    serve: tuple | None
    records: object
    where: tuple
    stock_where: tuple
    serve_where: tuple


@dataclass(frozen=True, eq=False)
class Assign:
    """A line that sets a value, `x = v`, or one that adds to it or takes from it, `x += v` and
    `x -= v` (`augmented`, its `operator` the name of the Python operator, and `value` the whole of
    `x ± v`). `target` is a `Ref` or a `Problem`; `written` is the target as written."""

    target: object
    written: object
    value: object  # the typed nodes of the value, its names resolved (`napkin/model/resolved.py`)
    augmented: bool
    operator: object
    where: tuple


@dataclass(frozen=True, eq=False)
class Move:
    """A line `move amount from a to b`. `ends` are `from` and `to`: (as written, the end: a `Ref`, a
    `Problem` or `outside`)."""

    amount: object  # the typed nodes of the amount, its names resolved
    ends: tuple
    where: tuple


@dataclass(frozen=True, eq=False)
class Fire:
    """A line that names an event, which then fires: `targets`, each (entity, event), in order (each
    member of a list, each copy of a set), or a `Problem`."""

    targets: object
    written: str
    where: tuple


@dataclass(frozen=True, eq=False)
class Outcome:
    """An outcome of an event: its name, its chance (an `Expression`; None, which is 1; or `'else'`,
    which is 1 less the others), its text, role and records, and its lines (`Assign`, `Move`, `Fire`).
    `label` is its text with its braces filled. `available` is the condition (an `Expression`) under
    which it can happen, or None when it always can."""

    name: str
    chance: object
    text: object
    role: object
    records: object
    lines: tuple
    label: Words | None
    where: tuple
    available: object = None


@dataclass(frozen=True, eq=False)
class Event:
    """An event of an entity: the condition that triggers it (`when`; None for an event that only a
    line that names it triggers), whether it triggers at most once, its delay (`after`), and its
    outcomes, of which one happens each time that it fires. `rank` orders the events of one moment:
    the order of the file, then the instances and copies of a template. `label` is its text with its
    braces filled; `doc_problem` is why the braces of its texts cannot be filled."""

    name: str
    entity: str
    when: Expression | None
    once: bool
    after: Expression | None
    outcomes: tuple
    text: object  # its text
    label: Words | None
    role: object  # the role that its cards show, as written, or None for its entity's
    records: object
    doc_problem: Fault | None
    rank: tuple
    where: tuple
    when_where: tuple
    # `each W`: the values of its window (Expressions); it fires at most once for each of their
    # combinations. `keep` (`while K`): a firing that waits happens only while K holds.
    each: tuple = ()
    keep: Expression | None = None
    # `choice`: a person or an agent can choose its outcome in a run (docs/language.md, §2.7).
    choice: bool = False

    def outcome(self, name):
        return next((outcome for outcome in self.outcomes if outcome.name == name), None)


@dataclass(frozen=True, eq=False)
class Start:
    """The start: the event `start` of `entity`, which fires first, at t = 0. `text` and `label` are
    the event's text, as written and filled."""

    entity: str
    text: object
    label: Words | None
    records: object
    where: tuple


@dataclass(frozen=True, eq=False)
class Entity:
    """One thing of the scenario, with its values in the order of its declaration. Each copy of a
    set of copies is an entity of its own."""

    name: str
    entry: str  # the name of the entity line that makes it: a set of copies makes several
    copy: int | None  # its number in its set of copies, from 1
    template: object  # the template that makes it, as written, or None
    values: tuple
    where: tuple
    title: object = None  # its name on the pages: its `title:`, or its name in words
    text: object = None  # its text
    role: object = None  # as written, or None
    records: object = None
    status: Status | None = None
    checks: tuple = ()
    settings: tuple = ()  # Setting, in the order of the profiles and of each profile's values
    flows: tuple = ()
    allocations: tuple = ()
    events: tuple = ()  # Event, in the order of the file
    # The places of the file that write its parts: its entity line, and its template's.
    places: tuple = ()
    # What an actor observes, each a `Ref`, an `EventRef` or a `Problem`; None for a thing of the
    # world.
    sees: tuple | None = None
    # Its links, as its lines or its template's slots bind them: {name: an entity, or a list of them}.
    links: Mapping = MappingProxyType({})

    def value(self, name):
        return next((value for value in self.values if value.name == name), None)

    def text_of(self, name):
        """The text of the text value `name`, which braces name, or `?` when it has none."""
        found = self.value(name)
        if found is not None and found.type == 'text' and isinstance(found.value, str):
            return found.value
        return '?'


@dataclass(frozen=True, eq=False)
class Profile:
    """One choice of a group: its name and its line in the menu."""

    name: str
    text: object
    where: tuple


@dataclass(frozen=True, eq=False)
class Group:
    """A group of profiles, in the order of the menu."""

    name: str
    profiles: tuple
    where: tuple


@dataclass(frozen=True, eq=False)
class Run:
    """A run: the names of its profiles, as written, its own name on the pages (`text`, or None), and
    the run that it is the comparison of (or None), which the file writes at `versus_where`."""

    name: str
    profiles: tuple
    where: tuple
    text: object = None
    comparison: object = None
    versus_where: tuple | None = None


@dataclass(frozen=True, eq=False)
class Record:
    """A named evidence record (docs/language.md, §2.10): the name by which the file cites it, and
    its content as written."""

    name: str
    content: object
    where: tuple


@dataclass(frozen=True, eq=False)
class Site:
    """A place that holds a basis: the part that it supports, and the basis with each named record
    written out (the record, with its `name`). A range note passes through as written."""

    where: tuple
    part: tuple
    value: object


@dataclass(frozen=True, eq=False)
class Citation:
    """A claim, an assumption or a convention that the file names (`kind` is `claim`, `assumption` or
    `convention`)."""

    kind: str
    id: str
    where: tuple


@dataclass(frozen=True, eq=False)
class Scenario:
    """What a scenario declares. Its evidence is its named records, the places that hold a basis
    (`sites`, in the order of the file) and the claims and assumptions that it names (`citations`,
    in the order of the file). Its title is the title of its main file, and for a variant that title,
    a colon and the variant's title. `scope` is whom the outputs that give no scope cover, or None;
    `notes` are the notes of the file (`Note`), which the calculation never reads."""

    groups: tuple
    runs: tuple
    entities: tuple
    menu_where: tuple = ()  # where the file writes its profiles
    title: object = None
    summary: object = None
    records: tuple = ()
    sites: tuple = ()
    citations: tuple = ()
    horizon: Time | None = None
    timescales: tuple | None = None  # Expression
    resolution: Time | None = None  # the longest step of the solver, when the file gives one
    scope: object = None
    scope_where: tuple = ()
    outputs: tuple = ()  # Output of the scenario
    checks: tuple = ()  # Check of the scenario
    notes: tuple = ()
    start: Start | None = None
    templates: tuple = ()  # the names of the templates that the model declares, with or without instances

    def entity(self, name):
        return next((entity for entity in self.entities if entity.name == name), None)

    def start_event(self):
        """The event `start` of the start's entity, or None without a start."""
        entity = self.entity(self.start.entity) if self.start is not None else None
        return next((event for event in entity.events if event.name == 'start'), None) if entity else None

    def output(self, key):
        """The output that `key` names: `entity.value`, or an output of the top level."""
        if '.' in key:
            entity, _, member = key.rpartition('.')
            return self.entity(entity).value(member).output
        return next((output for output in self.outputs if output.name == key), None)

    def event(self, key):
        """The event `entity.event`."""
        entity, _, name = key.rpartition('.')
        found = self.entity(entity)
        return None if found is None else next((event for event in found.events if event.name == name), None)


@dataclass(frozen=True, eq=False)
class Note:
    """A note of `notes:`, as written: its key, its value (a text, a number, a word or a list of them;
    None for a note with only notes under it), its records as the file writes them (names, and records
    written in place), or None, the notes under it, in order, and its place. The language gives no key
    a meaning."""

    key: str
    value: object
    records: object
    notes: tuple
    where: tuple

    def note(self, key):
        """The note `key` under this note, or None."""
        return next((note for note in self.notes if note.key == key), None)


class Ref(ast.expr):
    """A name of a value, resolved: member `member` of entity `entity`, or the output `member` of the
    scenario when `entity` is None. `written` is the name as the file writes it, for messages."""

    _fields = ('entity', 'member', 'written')


class EventRef(ast.expr):
    """An event, resolved: `kind` `trigger`, the event (`key`, `entity.event`) and the outcome that
    the name names (`ending`, or None for the event itself)."""

    _fields = ('kind', 'key', 'ending', 'written')


class Terms(ast.expr):
    """What `sum()` adds: a `Ref` for each entity of a list link, or for each copy of a set. `written`
    is the name of the list and its member as the file writes them (`zones.flag`, `Zone.x`)."""

    _fields = ('refs', 'written')


class Word(ast.expr):
    """`true` or `false`. `problem` is why the word is no name, which a test of a named state needs:
    `true is "on"`."""

    _fields = ('value', 'problem')


class Problem(ast.expr):
    """A part that the front end cannot read (a name that does not resolve, or an expression that does
    not parse), and why."""

    _fields = ('message',)
