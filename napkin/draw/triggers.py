"""The trigger lines of the cards (D-56): in short plain words, what makes each event of a thing
happen, how it waits, its chances, what it changes and the options that switch it.

The words are literal. They follow the rule as the file writes it, in the rule's own order: each name
comes from the model, and only generic words join the names ("when", "from", "has passed since", "is
at most", …). Nothing here is written for one model. The layout puts the lines on the cards and
chooses how much of them shows; this module only gives the words.

- `condition_words(node, name_of)`: the words of an expression with its names resolved, from its
  typed nodes (`Expression.node`, `napkin/model/resolved.py`).
- `namer(model, entity, expressions)`: the `name_of` of one line: the words of each name that the
  expressions read, made distinct. `event_namer(model, entity, event)` is the one of an event's line.
- `event_line(model, entity, event)`: the `Line` of one event.
- `card_events(model, card)` and `card_lines(model, card)`: the events of one card, and their lines, in
  the order of the file.
- `shorten(text, width, lines, measure)`: a text in at most `lines` lines of at most `width`.

The choices of the words:
- **Names.** A value reads as its member's name in words, and an event as its own name in words
  (`reaction_time` "reaction time", `strike_again` "strike again"). A label never replaces a name: a
  label is a phrase or a sentence, which is too long for a line and reads badly before "is", and the
  name matches the rule on the hover, the values of the arrows and the symbols. An outcome `o` of an
  event `e` reads "e (o)". When two names in one line read the same, each one of another card adds
  "of <the card's title>"; when they still read the same, each adds the title of its thing, then its
  name in the model. A template instance reads its own trees, so its words use the template's names.
- **Values.** A named value reads in words (`"coming_back"` "coming back"). `true` and `false` read
  "yes" and "no", as a yes/no state reads on a page (CONTRIBUTING.md, "Writing style", rule 13). A
  number reads plainly: an integer as it is, any other number in its shortest form (`0.5`, `1e-9`),
  with its unit as the file writes it (`2 h`, `0 Mgal`).
- **Forms.** `x is s` "x is s"; `is not` "is not"; `<`, `<=`, `>`, `>=` "is below", "is at most", "is
  above", "is at least"; `since(e) >= d` "d has passed since e", `since(e) > d` "more than d has passed
  since e", `since(e) < d` and `<= d` "within d of e"; `elapsed(s) >= d` "d has passed since s
  changed"; `count(e) > 0` "e has happened", `count(e) > n` "e has happened more than n times" (and "at
  least", "exactly", "no more than", "fewer than"; "once" for 1); `t >= x` "from x", `t < x` "before x";
  `any`, `all`, `sum`, `min` and `max` of a list "any x of L", "every x of L", "sum of x over L", "least
  x of L", "most x of L"; `count` of a list "number of L where x", and in a comparison "x holds in more
  than n of L". Any other use of these reads literally ("time since e", "times e has happened").
- **Groups.** `and` reads "A and B", or "A, B, and C"; `or` reads "A or B"; `not` reads "not x", or "not
  (…)" around a comparison or a group. A group inside a group of the other kind is in parentheses, and
  nowhere else; an `and` inside an `and` is one list. A tree has no parentheses of its own, so the
  outer parentheses of a rule never show.
- **Arithmetic** uses the symbols `+`, `−`, `×`, `/` and `^`, with parentheses only where the order of
  the operations needs them. Any other function keeps its name: `abs(x)`, `pert(1 h, 3 h, 12 h)`.

- **Outcomes.** The changes of an outcome name each target after its verb, and the verb once for each
  run of lines with the same verb: "sets a, b, adds to c, moves from d to e, fires <card>: <event>".
  An event with several outcomes names each outcome that has a chance or a change. A chance shows only
  when it is a number or an expression ("chance 1 − share", and `else` "chance of the rest"); a chance
  that is a condition, and the condition of an outcome, say when the outcome happens, so they show
  nothing.

The full line (`Line.full`) is the name, " — ", and then the parts that the event has, joined by "; ":
when (or "from x" for a rule that starts with the time), after, while, the window, once, the choice,
the outcomes, and the options. For example: "strike again — when watch is preparing, access is kept,
and reaction time has passed since controls back; sets watch, strikes; only with <option>".
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from ..core import expr
from ..model import resolved
from ..model.ir import thaw
from ..model.semantic import Assign, Expression, Fire, Move, Ref, flat_entity, in_words
from . import style as styles
from .model_map import card_title, operator_word, plain_text
from .text import ELLIPSIS, shorten  # noqa: F401  (shorten is part of this module's words)

# The marks of a line.
DASH = ' — '
PARTS = '; '

# The words of a comparison, and its mirror when its two sides change places. Each operation has the
# name that a typed node gives it (`napkin/core/expr.py`).
COMPARE_WORDS = {
    'eq': 'is',
    'ne': 'is not',
    'lt': 'is below',
    'le': 'is at most',
    'gt': 'is above',
    'ge': 'is at least',
}
MIRROR = {
    'eq': 'eq',
    'ne': 'ne',
    'lt': 'gt',
    'le': 'ge',
    'gt': 'lt',
    'ge': 'le',
}
# How many times, for `count`, by the comparison: the word before the number.
HOW_MANY = {
    'gt': 'more than',
    'ge': 'at least',
    'eq': 'exactly',
    'ne': 'not exactly',
    'le': 'no more than',
    'lt': 'fewer than',
}
# The symbols of arithmetic and their precedence: a higher one binds tighter.
ARITHMETIC = {'add': ('+', 5), 'sub': ('−', 5), 'mul': ('×', 6), 'div': ('/', 6), 'pow': ('^', 8)}
# The precedence of the other forms: a group of `or` and of `and`, a `not`, a comparison, a sign, and
# a name, a number or a call, which never needs parentheses.
OR, AND, NOT, COMPARISON, SIGN, ATOM = 1, 2, 3, 4, 7, 9
# The words of the functions of a list.
LIST_WORDS = {'any': 'any', 'all': 'every', 'min': 'least', 'max': 'most'}
# How a verb of a change reads.
VERBS = {'sets': 'sets', 'adds': 'adds to', 'takes': 'takes from'}


def words(name):
    """A name of the model in words, in lower case: `strike_again` "strike again", `coming_back` "coming
    back"; an acronym keeps its capitals (`AIShare` "AI share")."""
    found = in_words(str(name))
    first = found.split(' ', 1)[0]
    if len(first) > 1 and first.isupper():
        return found
    return found[:1].lower() + found[1:]


def number(value):
    """A number in plain words: an integer as it is, any other number in its shortest form, with a
    minus sign `−`; `true` and `false` are "yes" and "no"."""
    if isinstance(value, bool):
        return 'yes' if value else 'no'
    if not isinstance(value, (int, float)):
        return str(value)
    if value < 0:
        return '−' + number(-value)
    if isinstance(value, float) and math.isfinite(value) and value == int(value) and value < 1e15:
        return str(int(value))
    text = repr(value)
    if 'e' in text:
        mantissa, exponent = text.split('e')
        text = f'{mantissa}e{int(exponent)}'
    return text


# ---- the words of a condition -------------------------------------------------------------------


def condition_words(node, name_of):
    """The words of an expression whose names are resolved, from its typed nodes
    (`semantic.Expression.node`), in their order. `name_of(node)` gives the words of each name: of a
    `Ref` and an `EventRef`, a text; of a `Terms` (the members of a list), the pair (the member's words,
    the list's words)."""
    return _Words(name_of).text(node)


class _Words:
    def __init__(self, name_of):
        self.name_of = name_of

    def text(self, node):
        return self.phrase(node)[0]

    def wrapped(self, node, level):
        """The words of a node, in parentheses when it binds less tightly than `level`."""
        found, own = self.phrase(node)
        return f'({found})' if own < level else found

    def phrase(self, node):
        """(the words of a node, its precedence)."""
        if isinstance(node, (resolved.Ref, resolved.EventRef)):
            return self.name_of(node), ATOM
        if isinstance(node, resolved.Terms):
            member, group = self.name_of(node)
            return f'{member} of {group}', ATOM
        if isinstance(node, resolved.Word):
            return number(bool(node.value)), ATOM
        if isinstance(node, resolved.Problem):
            return '?', ATOM
        if isinstance(node, expr.Const):
            return (words(node.value) if isinstance(node.value, str) else number(node.value)), ATOM
        if isinstance(node, expr.Ref):
            return ('time' if node.name == 't' else words(node.name)), ATOM
        if isinstance(node, expr.BoolOp):
            return self.group(node)
        if isinstance(node, expr.Compare):
            parts = _pairs(node)
            if len(parts) == 1:
                return self.comparison(*parts[0]), COMPARISON
            return _listed([self.comparison(*part) for part in parts]), AND
        if isinstance(node, expr.Unary):
            if node.op == 'not':
                found, own = self.phrase(node.operand)
                return (f'not ({found})' if own <= COMPARISON else f'not {found}'), NOT
            sign = '−' if node.op == 'neg' else '+'
            return sign + self.wrapped(node.operand, SIGN), SIGN
        if isinstance(node, expr.Binary):
            symbol, level = ARITHMETIC[node.op]
            # `-` and `/` do not regroup on the right, and `^` does not on the left.
            left = self.wrapped(node.left, level + 1 if node.op == 'pow' else level)
            right = self.wrapped(node.right, level + 1 if node.op in ('sub', 'div') else level)
            return f'{left} {symbol} {right}', level
        if isinstance(node, expr.IfElse):
            body = self.wrapped(node.body, OR)
            return f'{body} if {self.wrapped(node.test, OR)}, else {self.wrapped(node.orelse, OR)}', 0
        if isinstance(node, expr.Call):
            return self.call(node), ATOM
        # A part that the language does not have (`expr.Foreign`) reads as its text, and so does a
        # call with arguments by name (`resolved.Named`). The builder refuses a model that has a part
        # outside the language, and the grammar of a file writes no argument by name, so no card
        # shows either.
        return expr.text(node), ATOM

    def group(self, node):
        """An `and` as one list, "A, B, and C", or an `or`, "A or B": a group of the other kind inside
        it is in parentheses."""
        if node.op == 'and':
            return _listed([self.item(value, AND) for value in _conjuncts(node)]), AND
        return ' or '.join(self.item(value, OR) for value in _disjuncts(node)), OR

    def item(self, node, level):
        """A member of a group: in parentheses when it is a group of the other kind (a chain of
        comparisons is an `and`) or an if-else."""
        found, own = self.phrase(node)
        other = OR if level == AND else AND
        return f'({found})' if own in (other, 0) else found

    def comparison(self, left, op, right):
        """The words of one comparison, with the forms of the clocks, the counts and the time."""
        if _special(right) and not _special(left):
            left, op, right = right, MIRROR[op], left
        elif isinstance(left, expr.Const) and isinstance(left.value, str) and op in ('eq', 'ne'):
            left, right = right, left
        if isinstance(left, expr.Call) and len(left.args) == 1:
            function, argument = left.function, left.args[0]
            amount = self.wrapped(right, COMPARISON + 1)
            if function == 'since':
                event = self.text(argument)
                if op == 'ge':
                    return f'{amount} has passed since {event}'
                if op == 'gt':
                    return f'more than {amount} has passed since {event}'
                if op in ('lt', 'le'):
                    return f'within {amount} of {event}'
                return f'time since {event} {COMPARE_WORDS[op]} {amount}'
            if function == 'elapsed':
                state = self.text(argument)
                if op == 'ge':
                    return f'{amount} has passed since {state} changed'
                if op == 'gt':
                    return f'more than {amount} has passed since {state} changed'
                if op in ('lt', 'le'):
                    return f'within {amount} after {state} changed'
                return f'time since {state} changed {COMPARE_WORDS[op]} {amount}'
            if function == 'count' and isinstance(argument, resolved.Terms):
                member, group = self.name_of(argument)
                return f'{member} holds in {HOW_MANY[op]} {amount} of {group}'
            if function == 'count':
                return self.count(self.text(argument), op, right, amount)
        if isinstance(left, expr.Ref) and left.name == 't':
            amount = self.wrapped(right, COMPARISON + 1)
            if op == 'ge':
                return f'from {amount}'
            if op == 'lt':
                return f'before {amount}'
        return (
            f'{self.wrapped(left, COMPARISON + 1)} {COMPARE_WORDS[op]} {self.wrapped(right, COMPARISON + 1)}'
        )

    @staticmethod
    def count(event, op, right, amount):
        """How many times an event has happened, by a comparison with `right` (its words `amount`)."""
        value = _constant(right)
        if value is not None:
            if (op, value) in {('gt', 0), ('ge', 1), ('ne', 0)}:
                return f'{event} has happened'
            if (op, value) in {('eq', 0), ('le', 0), ('lt', 1)}:
                return f'{event} has not happened'
            times = 'once' if value == 1 else f'{amount} times'
        else:
            times = f'{amount} times'
        if op == 'ne':
            return f'{event} has not happened exactly {times}'
        return f'{event} has happened {HOW_MANY[op]} {times}'

    def call(self, node):
        name, args = node.function, node.args
        if name == 'q' and len(args) == 2 and isinstance(args[1], expr.Const):
            return f'{self.wrapped(args[0], ATOM)} {args[1].value}'
        if name == 'since' and len(args) == 1:
            return f'time since {self.text(args[0])}'
        if name == 'elapsed' and len(args) == 1:
            return f'time since {self.text(args[0])} changed'
        if name == 'count' and len(args) == 1:
            if isinstance(args[0], resolved.Terms):
                member, group = self.name_of(args[0])
                return f'number of {group} where {member}'
            return f'times {self.text(args[0])} has happened'
        if name in LIST_WORDS or name == 'sum':
            if len(args) == 1 and isinstance(args[0], resolved.Terms):
                member, group = self.name_of(args[0])
                if name == 'sum':
                    return f'sum of {member} over {group}'
                return f'{LIST_WORDS[name]} {member} of {group}'
            if name in ('min', 'max') and args:
                return f'{LIST_WORDS[name]} of ' + _listed([self.text(arg) for arg in args])
        return f'{name}(' + ', '.join(self.text(arg) for arg in args) + ')'


def _listed(items):
    """A list in words: A; A and B; A, B, and C."""
    if len(items) <= 2:
        return ' and '.join(items)
    return ', '.join(items[:-1]) + ', and ' + items[-1]


def _conjuncts(node):
    """The parts of an `and`, with each `and` inside it, and each comparison of a chain, in order."""
    if isinstance(node, expr.BoolOp) and node.op == 'and':
        for value in node.values:
            yield from _conjuncts(value)
    elif isinstance(node, expr.Compare) and len(node.ops) > 1:
        for left, op, right in _pairs(node):
            yield expr.compare([op], [left, right])
    else:
        yield node


def _disjuncts(node):
    """The parts of an `or`, with each `or` inside it, in order."""
    if isinstance(node, expr.BoolOp) and node.op == 'or':
        for value in node.values:
            yield from _disjuncts(value)
    else:
        yield node


def _pairs(node):
    """The comparisons of a chain, `a < b < c`, each (left, the name of its operator, right)."""
    sides = node.operands
    return [(sides[k], op, sides[k + 1]) for k, op in enumerate(node.ops)]


def _special(node):
    """Whether a side of a comparison is a clock, a count or the time, which reads first."""
    if isinstance(node, expr.Ref):
        return node.name == 't'
    return (
        isinstance(node, expr.Call) and node.function in ('since', 'elapsed', 'count') and len(node.args) == 1
    )


def _constant(node):
    """The number of a plain number (`0`) or of a number with its unit (`0 h`), else None."""
    if isinstance(node, expr.Call) and node.function == 'q' and node.args:
        node = node.args[0]
    if (
        isinstance(node, expr.Const)
        and isinstance(node.value, (int, float))
        and not isinstance(node.value, bool)
    ):
        return node.value
    return None


# ---- the names of one line ------------------------------------------------------------------------


def _node(item):
    """The typed nodes of an `Expression`; any other item is its own nodes."""
    return item.node if isinstance(item, Expression) else item


def _names(node):
    """The `Ref`s and `EventRef`s of the nodes of an expression, in their order, without the members
    of a list: a list reads as one name."""
    if isinstance(node, (resolved.Ref, resolved.EventRef)):
        yield node
    elif isinstance(node, expr.Node) and not isinstance(node, resolved.Terms):
        for child in node.children:
            yield from _names(child)


def namer(model, entity, expressions=()):
    """The `name_of` of one line of `entity` (`condition_words`): the words of each name that the
    expressions (or typed nodes) read, distinct within the line. A name of another card that reads like
    another name adds "of <the card's title>"; names that still read the same add the title of their
    thing, then its name in the model. A list reads as the file writes it (`Terms.written`)."""
    scenario = model.scenario
    lines = styles.entity_lines(model)
    own = entity.entry
    keys = {}  # the key of each name: its base words and its owner
    for item in expressions:
        if item is None:
            continue
        for node in _names(_node(item)):
            key, base, owner = _name_key(node)
            keys.setdefault(key, (base, owner))
    final = {key: base for key, (base, _) in keys.items()}

    def owner_entity(owner):
        return scenario.entity(owner) if owner is not None else None

    def card_words(owner):
        found = owner_entity(owner)
        return card_title(lines[found.entry]) if found is not None else None

    def thing_words(owner):
        found = owner_entity(owner)
        return (thaw(found.title) or in_words(found.name)) if found is not None else None

    for qualify, others_only in ((card_words, True), (thing_words, False), (lambda owner: owner, False)):
        groups = {}
        for key, text in final.items():
            groups.setdefault(text, []).append(key)
        for members in groups.values():
            if len(members) < 2:
                continue
            for key in members:
                base, owner = keys[key]
                found = owner_entity(owner)
                if others_only and (found is None or found.entry == own):
                    continue
                extra = qualify(owner)
                if extra:
                    final[key] = f'{base} of {extra}'

    def name_of(node):
        if isinstance(node, resolved.Terms):
            head, member = None, None
            if node.written is not None:
                head, _, member = node.written.rpartition('.')
            if member is None:
                member = node.refs[0].member if node.refs else '?'
            if head is None:
                templates = {scenario.entity(ref.entity).template for ref in node.refs if ref.entity}
                head = templates.pop() if len(templates) == 1 and None not in templates else 'the list'
            return words(member), words(head)
        key, base, _ = _name_key(node)
        return final.get(key, base)

    return name_of


def _name_key(node):
    """(the key of a name, its words, the entity that owns it) of a `Ref` or an `EventRef`."""
    if isinstance(node, resolved.EventRef):
        owner, _, event = node.key.rpartition('.')
        base = words(event) + (f' ({words(node.ending)})' if node.ending else '')
        return ('event', node.key, node.ending), base, owner
    return ('value', node.entity, node.member), words(node.member), node.entity


# ---- the line of an event -------------------------------------------------------------------------


@dataclass(frozen=True)
class Line:
    """The trigger line of one event, as words.

    - `card`, `event`, `key`: the entity line of the card, the event's name, and the event in the
      structure (`entity.event`).
    - `name`: the event's name in words.
    - `when`: "when <the condition>"; "from <x>" for a condition that starts with the time; "when
      <card>: <event> fires it" (or "<event>" of its own card) for an event without `when` that only a
      line fires; "" for an event without `when` that a window triggers.
    - `timing`: "after <d>", "while <k>", "once for each value of <w>", "once", in that order.
    - `chance`: for each outcome whose chance is a number or an expression, "chance <p>", after the
      outcome's name when the event has several ("manual, chance 0.7"); with such a chance, `else`
      reads "chance of the rest". A chance that is a condition reads nothing: it says when the
      outcome happens, not how likely it is.
    - `choice`: "chooses <outcome> or <outcome>" for an actor's choice, else "".
    - `changes`: for each outcome with lines, what they change, after the outcome's name when the event
      has several: "sets a, b, adds to c, takes from d, moves from e to f, fires <card>: <event>".
    - `outcomes`: the chance and the changes of each outcome together, as `full` shows them.
    - `options`: "only with <option>" or "not with <option>" when some start options leave the event
      out; "" when every structure holds it.
    - `label`: the event's text with its braces filled (or the first outcome's), for the hover.
    - `rule`: the condition exactly as the file writes it, for the hover; None without `when`.
    - `full`: the whole line, uncut: `name — part; part; …` (`joined`).
    """

    card: str
    event: str
    key: str
    name: str
    when: str
    timing: tuple
    chance: tuple
    choice: str
    changes: tuple
    outcomes: tuple
    options: str
    label: str | None
    rule: str | None
    full: str

    def joined(self, options=True):
        """The whole line (`full`), or the line without the options that switch the event."""
        parts = [self.when, *self.timing, self.choice, *self.outcomes, self.options if options else '']
        return _joined(self.name, [part for part in parts if part])


def _joined(name, parts):
    """A line: the name, a dash, and its parts with '; ' between them."""
    return name + (DASH + PARTS.join(parts) if parts else '')


class _Lines:
    """What the lines of one model share: the entity lines and the events that fire each event."""

    def __init__(self, model):
        self.model = model
        self.scenario = model.scenario
        self.lines = styles.entity_lines(model)
        self.callers = {}
        for entity in self.scenario.entities:
            for event in entity.events:
                for outcome in event.outcomes:
                    for line in outcome.lines:
                        if isinstance(line, Fire) and isinstance(line.targets, tuple):
                            for target in line.targets:
                                found = self.callers.setdefault(tuple(target), [])
                                if (entity, event) not in found:
                                    found.append((entity, event))

    def title(self, entity):
        return card_title(self.lines[entity.entry])

    def event_of(self, entity, event, own):
        """An event in words: its name, after its card's title when it is of another card."""
        if entity.entry == own:
            return words(event)
        return f'{self.title(entity)}: {words(event)}'

    def line(self, entity, event):
        model = self.model
        name_of = event_namer(model, entity, event)
        say = _Words(name_of).text
        callers = []
        for caller, by in self.callers.get((entity.name, event.name), ()):
            found = self.event_of(caller, by.name, entity.entry)
            if found not in callers:
                callers.append(found)
        fired = ' or '.join(callers) + ' fires it' if callers else ''
        if event.when is not None:
            condition = say(event.when.node)
            when = condition if _starts_with_time(event.when.node) else f'when {condition}'
            if fired:
                when += f', or when {fired}'
        elif fired:
            when = f'when {fired}'
        elif event.each:
            when = ''
        else:
            when = 'never: no event fires it'
        timing = []
        if event.after is not None:
            timing.append(f'after {say(event.after.node)}')
        if event.keep is not None:
            timing.append(f'while {say(event.keep.node)}')
        if event.each:
            timing.append('once for each value of ' + _listed([say(item.node) for item in event.each]))
        if event.once:
            timing.append('once')
        choice = 'chooses ' + ' or '.join(words(o.name) for o in event.outcomes) if event.choice else ''
        chances, changes, outcomes = self.outcomes(entity, event, name_of)
        options = _options(model, entity, event)
        parts = [part for part in (when, *timing, choice, *outcomes, options) if part]
        name = words(event.name)
        return Line(
            card=entity.entry,
            event=event.name,
            key=f'{flat_entity(entity.name)}.{event.name}',
            name=name,
            when=when,
            timing=tuple(timing),
            chance=tuple(chances),
            choice=choice,
            changes=tuple(changes),
            outcomes=tuple(outcomes),
            options=options,
            label=_label(event),
            rule=_rule(event),
            full=_joined(name, parts),
        )

    def outcomes(self, entity, event, name_of):
        """(the chances, the changes, and both of each outcome together) of an event."""
        say = _Words(name_of).text
        many = len(event.outcomes) > 1
        likely = [
            o for o in event.outcomes if o.chance not in (None, 'else') and not _condition(o.chance, self)
        ]
        chances, changes, outcomes = [], [], []
        for outcome in event.outcomes:
            head = words(outcome.name) if many else ''
            chance = ''
            if outcome.chance == 'else' and likely:
                chance = 'chance of the rest'
            elif outcome in likely:
                chance = f'chance {say(outcome.chance.node)}'
            change = self.changes(entity, outcome, name_of)
            if chance:
                chances.append(f'{head}, {chance}' if head else chance)
            if change:
                changes.append(f'{head}: {change}' if head else change)
            both = ', '.join(part for part in (head, chance) if part)
            if change:
                both = f'{both}: {change}' if both else change
            if chance or change:
                outcomes.append(both)
        return chances, changes, outcomes

    def changes(self, entity, outcome, name_of):
        """What the lines of an outcome change: the verb once for each run of lines with the same verb,
        "sets a, b, adds to c"."""
        items = []
        for line in outcome.lines:
            if isinstance(line, Assign):
                # A target is a `Ref` of the semantic model: `name_of` reads its typed node.
                target = (
                    name_of(resolved.of_tree(line.target))
                    if isinstance(line.target, Ref)
                    else words(line.written)
                )
                items.append((VERBS[operator_word(line)], target))
            elif isinstance(line, Move):
                ends = [
                    name_of(resolved.of_tree(end)) if isinstance(end, Ref) else words(written)
                    for written, end in line.ends
                ]
                items.append(('moves', f'from {ends[0]} to {ends[1]}' if len(ends) == 2 else ' '.join(ends)))
            elif isinstance(line, Fire):
                items.append(('fires', self.fired(entity, line)))
        out, verb = [], None
        for found, target in items:
            out.append(target if found == verb else f'{found} {target}')
            verb = found
        return ', '.join(out)

    def fired(self, entity, line):
        """The events that a line fires: "<card>: <event>", or the event of its own card; the members
        of a list, "<event> of <list>"."""
        targets = line.targets if isinstance(line.targets, tuple) else ()
        if not targets:
            return words(line.written)
        events = {event for _, event in targets}
        if len(targets) > 1 and len(events) == 1:
            head = str(line.written).rpartition('.')[0]
            return f'{words(targets[0][1])} of {words(head) if head else "each"}'
        found = []
        for owner, event in targets:
            thing = self.scenario.entity(owner)
            text = self.event_of(thing, event, entity.entry) if thing is not None else words(event)
            if text not in found:
                found.append(text)
        return ', '.join(found)


def event_namer(model, entity, event):
    """The `name_of` of the line of one event (`namer`): over its condition, delay, window and `while`,
    the chances of its outcomes, and the targets of their lines."""
    return namer(model, entity, _shown(event))


def _shown(event):
    """The expressions that a line of an event reads out: its condition, delay, window and `while`, the
    chances of its outcomes, and the targets of their lines (each target as its typed node)."""
    shown = [event.when, event.after, *event.each, event.keep]
    for outcome in event.outcomes:
        if outcome.chance not in (None, 'else'):
            shown.append(outcome.chance)
        for line in outcome.lines:
            if isinstance(line, Assign) and isinstance(line.target, Ref):
                shown.append(resolved.of_tree(line.target))
            elif isinstance(line, Move):
                shown += [resolved.of_tree(end) for _, end in line.ends if isinstance(end, Ref)]
    return [item for item in shown if item is not None]


def _starts_with_time(node):
    """Whether a condition's words start with "from": a comparison `t >= x`, or an `and` that starts
    with one."""
    first = next(_conjuncts(node))
    if not (isinstance(first, expr.Compare) and len(first.ops) == 1):
        return False
    left, op, right = _pairs(first)[0]
    if _special(right) and not _special(left):
        left, op = right, MIRROR[op]
    return isinstance(left, expr.Ref) and left.name == 't' and op == 'ge'


def _condition(chance, lines):
    """Whether the chance of an outcome is a condition (1 when it holds, else 0), not a number."""
    node = _node(chance)
    if isinstance(node, (expr.Compare, expr.BoolOp, resolved.Word)):
        return True
    if isinstance(node, expr.Unary):
        return node.op == 'not'
    if isinstance(node, expr.Const):
        return isinstance(node.value, bool)
    if isinstance(node, expr.IfElse):
        return _condition(node.body, lines)
    if isinstance(node, expr.Call):
        return node.function in ('any', 'all')
    if isinstance(node, resolved.Ref) and node.entity is not None:
        thing = lines.scenario.entity(node.entity)
        value = thing.value(node.member) if thing is not None else None
        return value is not None and thaw(value.type) == 'bool'
    return False


def _options(model, entity, event):
    """The options that switch an event: "only with <option>" when the structures that hold it are
    those with the option, "not with <option>" when they are those without it, else the options of
    each structure that holds it; "" when every structure holds it, and "in no run" when none does. A
    structure holds the event unless it leaves its rule out (`model.left_out`)."""
    key = f'{flat_entity(entity.name)}.{event.name}'
    starts = list(model.structures)
    held = [s for s in starts if key not in model.left_out[s].get('rules', {})]
    if len(held) == len(starts):
        return ''
    if not held:
        return 'in no run'
    lacking = [s for s in starts if s not in held]
    options = [o for o in model.start_options if any(o in s for s in starts)]
    for option in options:
        if all(option in s for s in held) and not any(option in s for s in lacking):
            return f'only with {option}'
    for option in options:
        if not any(option in s for s in held) and all(option in s for s in lacking):
            return f'not with {option}'
    common = [o for o in options if all(o in s for s in held)]
    if common and not any(set(common) <= set(s) for s in lacking):
        return 'only with ' + _listed(common)
    ways = [_listed(list(s)) if s else 'none of ' + ', '.join(options) for s in held]
    return 'only with ' + ', or with '.join(ways)


def _label(event):
    """The event's text with its braces filled, or that of its first outcome that has one."""
    for words_of in (event.label, *(outcome.label for outcome in event.outcomes)):
        found = plain_text(words_of.text) if words_of is not None else None
        if found:
            return found
    return None


def _rule(event):
    """The condition of an event as the file writes it, or None without one."""
    if event.when is None:
        return None
    written = event.when.written
    if isinstance(written, str):
        return written
    return ('true' if written else 'false') if isinstance(written, bool) else number(written)


def event_line(model, entity, event):
    """The `Line` of one event of `entity` (a semantic `Entity`), in words."""
    return _Lines(model).line(entity, event)


def _entity_of(model, card):
    if isinstance(card, str):
        lines = styles.entity_lines(model)
        if card not in lines:
            raise ValueError(f'{card} is not a thing of the model')
        return lines[card]
    return card


def card_events(model, card):
    """The events of one card, in the order of the file: `card` is an entity line (the `id` of a card
    of the picture) or an `Entity`. A set of copies shows the events of its first copy."""
    return tuple(_entity_of(model, card).events)


def card_lines(model, card):
    """The `Line` of each event of one card (`card_events`), in the order of the file."""
    entity = _entity_of(model, card)
    lines = _Lines(model)
    return tuple(lines.line(entity, event) for event in entity.events)
