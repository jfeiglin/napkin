"""The trigger lines of the cards (D-56): in short plain words, how each event of a thing starts, what
its stages wait for and change, and the runs that leave it out.

The words are literal. They follow the event as the file writes it, in its own order: each name comes
from the model, and only generic words join the names ("when", "after", "has passed since", "is at
most", …). Nothing here is written for one model. The layout puts the lines on the cards and chooses
how much of them shows; this module only gives the words.

- `condition_words(expression, name_of)`: the words of an expression of the typed form
  (`napkin/model/semantic.py`), with the words of each read from `name_of`.
- `namer(found, card, expressions)`: the `name_of` of one line: the words of each name that the
  expressions read, made distinct.
- `card_lines(found, card)`: the `Line` of each event of one card, in written order.

The choices of the words:
- **Names.** A value reads as its name in words, and an event as its own name (`reaction_time`
  "reaction time", `strike_again` "strike again"). A label never replaces a name: a label is a phrase
  or a sentence, which is too long for a line. When two names in one line read the same, each one of
  another card adds "of <the card's title>"; when they still read the same, each adds its thing's
  name in the model. A rate reads as its flow; a request, a capacity, an outflow, an inflow, a mean
  and a spread read "request of f", "outflow of s", "mean of d".
- **Values.** An enum member and a named value read in words (`COMING_BACK` "coming back"); `true`
  and `false` read "yes" and "no". A number reads plainly: an integer as it is, any other number in
  its shortest form (`0.5`, `1e-9`), with its unit (`2 h`, `0 L`); a text is in quotes.
- **Forms.** `x == s` "x is s"; `!=` "is not"; `<`, `<=`, `>`, `>=` "is below", "is at most", "is
  above", "is at least"; `since(e) >= d` "d has passed since e", `since(e) > d` "more than d has passed
  since e", `since(e) < d` and `<= d` "within d of e"; `elapsed(s) >= d` "d has passed since s
  changed"; `count(e.occurrences) > 0` "e has started", `> n` "e has started more than n times" (and
  "at least", "exactly", "no more than", "fewer than"; "once" for 1); `t >= x` "from x", `t < x`
  "before x"; `any`, `all`, `sum`, `min` and `max` of a collection "any x of L", "every x of L", "sum
  of x over L", "least x of L", "most x of L"; `count` of yes/no values "number of L where x", and in
  a comparison "x holds in more than n of L". A collection reads as written: `T.instances` "T
  instances", a literal its members, `where` "L where c", a keyed read "x of L with k v".
- **Groups.** `and` reads "A and B", or "A, B, and C"; `or` reads "A or B"; `not` reads "not x", or
  "not (…)" around a comparison or a group. A group inside a group of the other kind is in
  parentheses, and nowhere else.
- **Arithmetic** uses the symbols `+`, `−`, `×`, `/` and `^`, with parentheses only where the order of
  the operations needs them. Any other function keeps its name: `abs(x)`, `clip(x, 1 L, 6 L)`.
- **Starts.** A trigger reads "when C" ("from x" for a condition that starts with the time), with
  its reset: "once" for `reset when false`, "again when D", "again after T". An event that another
  event starts reads "when <card>: <event> starts it" (or "<event>" of its own card), one that the
  setup starts "the setup starts it", and one that nothing starts "never: nothing starts it".
- **Steps.** A stage reads "after d" (with "when g" for its guard) and what it changes; a wait
  "waits d"; a gate "until c". The changes name each target after its verb, the verb once for each
  run of the same verb: "sets a, b, adds to c, moves from d to e, starts <card>: <event>". A branch
  reads "if c: …, else: …"; a switch names what selects its case ("draws fixed (chance 0.7) or
  failed (chance 0.3)", "dispatcher chooses send or wait", "by mode") and what each case changes.
- **Runs.** "only with <option>" or "not with <option>" when some runs cannot start the event
  (`things.Things.startable`); "" when every run can.

The full line (`Line.full`) is the name, " — ", and then the parts that the event has, joined by "; ":
how it starts, its steps, and the runs. For example: "strike again — when watch is preparing and
reaction time has passed since controls back; after 1 h: sets watch, adds to strikes".
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from ..model import semantic as s
from .text import ELLIPSIS, in_words, shorten  # noqa: F401  (shorten is part of this module's words)

# The marks of a line.
DASH = ' — '
PARTS = '; '

# The words of a comparison by its operator, and its mirror when its two sides change places.
OPS = {'==': 'eq', '!=': 'ne', '<': 'lt', '<=': 'le', '>': 'gt', '>=': 'ge'}
COMPARE_WORDS = {
    'eq': 'is',
    'ne': 'is not',
    'lt': 'is below',
    'le': 'is at most',
    'gt': 'is above',
    'ge': 'is at least',
}
MIRROR = {'eq': 'eq', 'ne': 'ne', 'lt': 'gt', 'le': 'ge', 'gt': 'lt', 'ge': 'le'}
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
# The precedence of the other forms: a conditional, a group of `or` and of `and`, a `not`, a
# comparison, a sign, and a name, a number or a call, which never needs parentheses.
IF, OR, AND, NOT, COMPARISON, SIGN, ATOM = 0, 1, 2, 3, 4, 7, 9
# The words of the reductions of a collection.
LIST_WORDS = {'any': 'any', 'all': 'every', 'min': 'least', 'max': 'most'}
# How a verb of a change reads, by the operator of an assignment.
VERBS = {'=': 'sets', '+=': 'adds to', '-=': 'takes from'}
# The words of the steps after a flow, a value or an endpoint that a read takes.
OF_WORDS = {
    'request': 'request of',
    'capacity': 'capacity of',
    'outflow': 'outflow of',
    'inflow': 'inflow of',
    'mean': 'mean of',
    'std': 'spread of',
    'served_fraction': 'served fraction of',
}


def words(name):
    """A name of the model in words, in lower case: `strike_again` "strike again", `COMING_BACK`
    "coming back"; an acronym keeps its capitals (`AIShare` "AI share")."""
    name = str(name)
    found = in_words(name.lower() if name.isupper() and len(name) > 1 else name)
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


def constant(expression):
    """The number of a constant number of the typed form, else None."""
    if isinstance(expression, s.Const) and isinstance(expression.value, (int, float)):
        return None if isinstance(expression.value, bool) else expression.value
    return None


def _with_unit(value, kind):
    unit = getattr(kind, 'unit', '')
    return f'{number(value)} {unit}' if unit else number(value)


# ---- the words of a condition -------------------------------------------------------------------


def condition_words(expression, name_of):
    """The words of an expression of the typed form, in its order. `name_of(read)` gives the words of
    each read, and `name_of.collection(read)` those of a collection."""
    return _Words(name_of).text(expression)


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
        if isinstance(node, s.Read):
            return self.name_of(node), ATOM
        if isinstance(node, s.Const):
            value = node.value
            if isinstance(value, bool):
                return number(value), ATOM
            if isinstance(value, str):
                return (words(value) if isinstance(node.type, s.EnumOf) else f'"{value}"'), ATOM
            return _with_unit(value, node.type), ATOM
        if isinstance(node, s.Retain):
            return self.phrase(node.body)
        if isinstance(node, s.Reduced):
            return self.reduced(node), ATOM
        if isinstance(node, s.History):
            if node.op == 'elapsed':
                return f'time since {self.text(node.source)} changed', ATOM
            return f'time since {self.text(node.source)}', ATOM
        if isinstance(node, s.Distribution):
            return self.distribution(node), ATOM
        if isinstance(node, s.Drawn):
            source = node.source
            found = self.distribution(source) if isinstance(source, s.Distribution) else self.text(source)
            return f'a draw of {found}', ATOM
        if isinstance(node, s.Chosen):
            return f'the choice of {self.text(node.actor)}', ATOM
        if isinstance(node, s.Apply):
            return self.apply(node)
        return str(node), ATOM

    def apply(self, node):
        op, args = node.op, node.args
        if op in ('and', 'or'):
            return self.group(node)
        if op == 'compare':
            parts = _pairs(node)
            if len(parts) == 1:
                return self.comparison(*parts[0]), COMPARISON
            return _listed([self.comparison(*part) for part in parts]), AND
        if op == 'not':
            found, own = self.phrase(args[0])
            return (f'not ({found})' if own <= COMPARISON else f'not {found}'), NOT
        if op == 'neg':
            return '−' + self.wrapped(args[0], SIGN), SIGN
        if op in ARITHMETIC:
            symbol, level = ARITHMETIC[op]
            # `-` and `/` do not regroup on the right, and `^` does not on the left.
            left = self.wrapped(args[0], level + 1 if op == 'pow' else level)
            right = self.wrapped(args[1], level + 1 if op in ('sub', 'div') else level)
            return f'{left} {symbol} {right}', level
        if op == 'if':
            test, body, orelse = args
            text = f'{self.wrapped(body, OR)} if {self.wrapped(test, OR)}, else {self.wrapped(orelse, OR)}'
            return text, IF
        if op == 'call':
            if node.detail in ('min', 'max'):
                return f'{LIST_WORDS[node.detail]} of ' + _listed([self.text(arg) for arg in args]), ATOM
            return f'{node.detail}(' + ', '.join(self.text(arg) for arg in args) + ')', ATOM
        return f'{op}(' + ', '.join(self.text(arg) for arg in args) + ')', ATOM

    def distribution(self, node):
        if node.family == 'categorical':
            return (
                'categorical('
                + ', '.join(
                    f'{words(member)}: {number(weight)}' for member, weight in zip(node.outcomes, node.params)
                )
                + ')'
            )
        kind = node.type.of
        return f'{node.family}(' + ', '.join(_with_unit(value, kind) for value in node.params) + ')'

    def reduced(self, node):
        member, group = self.name_of.collection(node.source)
        if node.op == 'sum':
            return f'sum of {member} over {group}'
        if node.op == 'count':
            if member is None:
                return f'number of {group}'
            if isinstance(node.source.type, s.Many) and isinstance(node.source.type.of, s.Occ):
                return f'times {member} has started'
            return f'number of {group} where {member}'
        return f'{LIST_WORDS[node.op]} {member} of {group}'

    def group(self, node):
        """An `and` as one list, "A, B, and C", or an `or`, "A or B": a group of the other kind inside
        it is in parentheses."""
        if node.op == 'and':
            return _listed([self.item(value, AND) for value in _conjuncts(node)]), AND
        return ' or '.join(self.item(value, OR) for value in _disjuncts(node)), OR

    def item(self, node, level):
        """A member of a group: in parentheses when it is a group of the other kind (a chain of
        comparisons is an `and`) or a conditional."""
        found, own = self.phrase(node)
        other = OR if level == AND else AND
        return f'({found})' if own in (other, IF) else found

    def comparison(self, left, op, right):
        """The words of one comparison, with the forms of the clocks, the counts and the time."""
        if _special(right) and not _special(left):
            left, op, right = right, MIRROR[op], left
        elif isinstance(left, s.Const) and isinstance(left.value, str) and op in ('eq', 'ne'):
            left, right = right, left
        amount = self.wrapped(right, COMPARISON + 1)
        if isinstance(left, s.History):
            what = self.text(left.source)
            if left.op == 'elapsed':
                if op == 'ge':
                    return f'{amount} has passed since {what} changed'
                if op == 'gt':
                    return f'more than {amount} has passed since {what} changed'
                if op in ('lt', 'le'):
                    return f'within {amount} after {what} changed'
                return f'time since {what} changed {COMPARE_WORDS[op]} {amount}'
            if op == 'ge':
                return f'{amount} has passed since {what}'
            if op == 'gt':
                return f'more than {amount} has passed since {what}'
            if op in ('lt', 'le'):
                return f'within {amount} of {what}'
            return f'time since {what} {COMPARE_WORDS[op]} {amount}'
        if isinstance(left, s.Reduced) and left.op == 'count':
            member, group = self.name_of.collection(left.source)
            if isinstance(left.source.type, s.Many) and isinstance(left.source.type.of, s.Occ):
                return self.count(member, op, right, amount)
            if member is not None:
                return f'{member} holds in {HOW_MANY[op]} {amount} of {group}'
        if isinstance(left, s.Read) and left.start == ('time',):
            if op == 'ge':
                return f'from {amount}'
            if op == 'lt':
                return f'before {amount}'
        return f'{self.wrapped(left, COMPARISON + 1)} {COMPARE_WORDS[op]} {amount}'

    @staticmethod
    def count(event, op, right, amount):
        """How many times an event has started, by a comparison with `right` (its words `amount`)."""
        value = constant(right)
        if value is not None:
            if (op, value) in {('gt', 0), ('ge', 1), ('ne', 0)}:
                return f'{event} has started'
            if (op, value) in {('eq', 0), ('le', 0), ('lt', 1)}:
                return f'{event} has not started'
            times = 'once' if value == 1 else f'{amount} times'
        else:
            times = f'{amount} times'
        if op == 'ne':
            return f'{event} has not started exactly {times}'
        return f'{event} has started {HOW_MANY[op]} {times}'


def _listed(items):
    """A list in words: A; A and B; A, B, and C."""
    if len(items) <= 2:
        return ' and '.join(items)
    return ', '.join(items[:-1]) + ', and ' + items[-1]


def _conjuncts(node):
    """The parts of an `and`, with each `and` inside it, and each comparison of a chain, in order."""
    if isinstance(node, s.Apply) and node.op == 'and':
        for value in node.args:
            yield from _conjuncts(value)
    elif isinstance(node, s.Apply) and node.op == 'compare' and len(node.detail) > 1:
        for left, op, right in _pairs(node):
            yield s.Apply('compare', (left, right), s.BOOL, ({v: k for k, v in OPS.items()}[op],))
    else:
        yield node


def _disjuncts(node):
    """The parts of an `or`, with each `or` inside it, in order."""
    if isinstance(node, s.Apply) and node.op == 'or':
        for value in node.args:
            yield from _disjuncts(value)
    else:
        yield node


def _pairs(node):
    """The comparisons of a chain, `a < b < c`, each (left, the name of its operator, right)."""
    sides = node.args
    return [(sides[k], OPS[op], sides[k + 1]) for k, op in enumerate(node.detail)]


def _special(node):
    """Whether a side of a comparison is a clock, a count of occurrences or the time, which reads
    first."""
    if isinstance(node, s.Read):
        return node.start == ('time',)
    if isinstance(node, s.History):
        return True
    return isinstance(node, s.Reduced) and node.op == 'count'


# ---- the names of one line ------------------------------------------------------------------------


def _reads(expression):
    """The reads of an expression whose words name them: each read, without the members of a
    collection that a reduction or a keyed read names as a whole."""
    if isinstance(expression, s.Read):
        yield expression
    elif isinstance(expression, s.Apply):
        for arg in expression.args:
            yield from _reads(arg)
    elif isinstance(expression, (s.Retain,)):
        yield from _reads(expression.body)
    elif isinstance(expression, s.History):
        yield from _reads(expression.source)
    elif isinstance(expression, (s.Drawn, s.Chosen)):
        if isinstance(expression, s.Chosen):
            yield expression.actor
        if isinstance(expression.source, s.Read):
            yield expression.source


class namer:
    """The `name_of` of one line of the card `card` (`condition_words`; None for the top level): the
    words of each name that the expressions read, distinct within the line. A name of another card that reads like another
    name adds "of <the card's title>"; names that still read the same add their member's name in the
    model."""

    def __init__(self, found, card, expressions=()):
        self.found, self.card = found, card
        self.members = found.cards[card].members if card is not None else ()
        self.final = {}
        keys = {}
        for expression in expressions:
            for read in _reads(expression):
                key, base, owner = self.key(read)
                keys.setdefault(key, (base, owner))
        self.final = {key: base for key, (base, _) in keys.items()}
        for qualify, others_only in ((self.card_words, True), (lambda owner: owner, False)):
            groups = {}
            for key, text in self.final.items():
                groups.setdefault(text, []).append(key)
            for members in groups.values():
                if len(members) < 2:
                    continue
                for key in members:
                    base, owner = keys[key]
                    if owner is None or (others_only and found.card_of.get(owner) == card):
                        continue
                    extra = qualify(owner)
                    if extra:
                        self.final[key] = f'{base} of {extra}'

    def card_words(self, owner):
        card = self.found.cards.get(self.found.card_of.get(owner))
        return card.title if card is not None else None

    def key(self, read):
        """(the key of a read, its words, the member that owns it, or None). A field of the item of a
        `where` reads as its field, and a member of a keyed collection names the collection."""
        if read.start == ('item',):
            return ('item', read.steps), words(read.steps[-1]) if read.steps else 'it', None
        found = self.found.reached(read, self.members)
        if found is None:
            name = read.start[1] if read.start[0] == 'local' else (read.steps[-1] if read.steps else 'time')
            base = 'time' if read.start == ('time',) else words(name)
            return ('own', read.start, read.steps), base, None
        if found.what == 'member':
            # A member reads as the file writes it: its id.
            owner = found.members[0] if len(found.members) == 1 else None
            return ('member', found.members), owner if owner is not None else 'members', owner
        base = words(found.name)
        steps = [step for step in found.steps if step not in ('actual_rate', 'occurrences')]
        if found.what == 'solver' and steps:
            base, steps = words(steps[0]), steps[1:]
        for step in steps:
            base = f'{OF_WORDS[step]} {base}' if step in OF_WORDS else f'{base} {words(step)}'
        owner = found.members[0] if len(set(found.members)) == 1 else None
        if read.start[0] in ('where', 'by', 'lookup'):
            base = f'{base} of {self.group(s.Read(read.start, (), None))}'
        return (found.what, found.members, found.name, tuple(found.steps)), base, owner

    def __call__(self, read):
        key, base, _ = self.key(read)
        return self.final.get(key, base)

    def collection(self, read):
        """(the words of the member or the projected field, the words of the collection) of the
        source of a reduction."""
        of = read.type.of if isinstance(read.type, s.Many) else None
        if isinstance(of, s.Occ):
            # The occurrences of an event: the event.
            return self(read), None
        if isinstance(of, s.Ent) or not read.steps:
            return None, self.group(read)
        return words(read.steps[-1]), self.group(s.Read(read.start, read.steps[:-1], None))

    def group(self, read):
        """The words of a collection as the file writes it."""
        start = read.start
        if start[0] == 'instances' and not read.steps:
            return f'{words(start[1])} instances'
        if start[0] == 'literal' and not read.steps:
            return _listed([self(item) for item in start[1]])
        if start[0] == 'where' and not read.steps:
            test = _Words(self).text(start[2])
            return f'{self.group(start[1])} where {test}'
        if start[0] == 'by' and not read.steps:
            return f'{self.group(start[1])} by {words(start[2])}'
        if start[0] == 'lookup' and not read.steps:
            return f'{self.group(start[1])} at {_Words(self).text(start[2])}'
        if read.steps:
            return words(read.steps[-1])
        return self(read)


# ---- the line of an event -------------------------------------------------------------------------


@dataclass(frozen=True)
class Line:
    """The trigger line of one event, as words.

    - `card`, `event`, `key`: the card, the event's name, and `card.event`; `path` the event's
      declared path (its origin in the program).
    - `name`: the event's name in words.
    - `starts`: how it starts: its triggers, the events and the setup that start it.
    - `steps`: each step in words, in order.
    - `options`: "only with <option>" or "not with <option>" when some runs cannot start the event;
      "" when every run can.
    - `label`: the event's text, or that of its first stage or case that has one, for the hover.
    - `rule`: the condition of its first trigger exactly as the file writes it, for the hover; None
      without a trigger.
    - `full`: the whole line, uncut: `name — part; part; …` (`joined`).
    """

    card: str
    event: str
    key: str
    path: str
    name: str
    starts: str
    steps: tuple
    options: str
    label: str | None
    rule: str | None
    full: str

    def joined(self, options=True):
        """The whole line (`full`), or the line without the options that switch the event."""
        parts = [self.starts, *self.steps, self.options if options else '']
        return _joined(self.name, [part for part in parts if part])


def _joined(name, parts):
    """A line: the name, a dash, and its parts with '; ' between them."""
    return name + (DASH + PARTS.join(parts) if parts else '')


def _shown(event):
    """The expressions whose names a line of an event reads out: its triggers' conditions and resets,
    its delays, guards and gates, and the targets, ends, events, selectors and guards of its
    statements."""
    found = []
    for trigger in event.triggers:
        found.append(trigger.test)
        if trigger.reset is not None:
            found.append(trigger.reset[1])
    for step in event.steps:
        if isinstance(step, s.DeclaredStage):
            found += [step.delay, step.guard]
            for statement in s.statements_of(step.body):
                found += _statement_expressions(statement)
        elif isinstance(step, s.DeclaredGate):
            found.append(step.test)
    return [item for item in found if item is not None]


def _statement_expressions(statement):
    if isinstance(statement, s.DeclaredAssign):
        return [statement.target]
    if isinstance(statement, s.DeclaredMove):
        return [statement.source, statement.destination]
    if isinstance(statement, s.DeclaredStart):
        return [statement.event]
    if isinstance(statement, s.DeclaredIf):
        return [statement.test]
    if isinstance(statement, s.DeclaredSwitch):
        selector = statement.selector
        if isinstance(selector, s.Drawn) and isinstance(selector.source, s.Distribution):
            found = []
        elif isinstance(selector, s.Chosen):
            found = [selector.actor]  # the line names who chooses, and the cases
        else:
            found = [selector]
        return found + [case.guard for case in statement.cases if case.guard is not None]
    return []


class _Lines:
    """What the lines of one model share: the cards and the events that start each event."""

    def __init__(self, found):
        self.found = found
        self.callers = {}  # event path -> [(card, event path)] of the events that start it
        self.setup = set()  # the event paths that the setup starts
        for card in found.cards.values():
            for event in found.events(card.id):
                starts = [start for trigger in event.triggers for start in trigger.starts]
                for step in event.steps:
                    if isinstance(step, s.DeclaredStage):
                        starts += [
                            item for item in s.statements_of(step.body) if isinstance(item, s.DeclaredStart)
                        ]
                for start in starts:
                    target = event_of(start.event)
                    if target == event.path:
                        continue  # a trigger starts its own event: the trigger says when
                    item = (card.id, event)
                    if item not in self.callers.setdefault(target, []):
                        self.callers[target].append(item)
        for start in found.declared.setup:
            self.setup.add(event_of(start.event))

    def event_words(self, card, event, own):
        """An event in words: its name, after its card's title when it is of another card."""
        if card == own:
            return words(event.name)
        return f'{self.found.cards[card].title}: {words(event.name)}'

    def line(self, card, event):
        found = self.found
        name_of = namer(found, card, _shown(event))
        say = _Words(name_of).text
        parts = []
        for trigger in event.triggers:
            condition = say(trigger.test)
            text = condition if _starts_with_time(trigger.test) else f'when {condition}'
            reset = trigger.reset
            if reset is not None:
                kind, value = reset
                if kind == 'when' and isinstance(value, s.Const) and value.value is False:
                    text += ', once'
                else:
                    text += f', again {"when" if kind == "when" else "after"} {say(value)}'
            parts.append(text)
        callers = []
        for caller, by in self.callers.get(event.path, ()):
            text = self.event_words(caller, by, card)
            if text not in callers:
                callers.append(text)
        if callers:
            parts.append(f'when {" or ".join(callers)} starts it')
        if event.path in self.setup:
            parts.append('the setup starts it')
        starts = ', or '.join(parts) if parts else 'never: nothing starts it'
        steps = []
        for step in event.steps:
            if isinstance(step, s.DeclaredGate):
                steps.append(f'until {say(step.test)}')
                continue
            delay = say(step.delay)
            if step.wait:
                steps.append(f'waits {delay}')
                continue
            head = f'after {delay}' + (f' when {say(step.guard)}' if step.guard is not None else '')
            changes = self.changes(card, step.body, name_of)
            steps.append(f'{head}: {changes}' if changes else head)
        options = _options(found, event)
        rule = None
        if event.triggers:
            rule = found.written('Trigger', event.triggers[0].line, 'test')
        name = words(event.name)
        full = _joined(name, [part for part in (starts, *steps, options) if part])
        return Line(
            card=card,
            event=event.name,
            key=f'{card}.{event.name}',
            path=event.path,
            name=name,
            starts=starts,
            steps=tuple(steps),
            options=options,
            label=_label(event),
            rule=rule,
            full=full,
        )

    def changes(self, card, body, name_of):
        """What the statements of a body change: the verb once for each run of statements with the
        same verb, "sets a, b, adds to c"."""
        say = _Words(name_of).text
        items = []
        for statement in body:
            if isinstance(statement, s.DeclaredAssign):
                items.append((VERBS[statement.op], name_of(statement.target)))
            elif isinstance(statement, s.DeclaredMove):
                items.append(
                    ('moves', f'from {name_of(statement.source)} to {name_of(statement.destination)}')
                )
            elif isinstance(statement, s.DeclaredStart):
                items.append(('starts', self.started(card, statement, name_of)))
            elif isinstance(statement, s.DeclaredIf):
                text = f'if {say(statement.test)}: {self.changes(card, statement.then, name_of) or "nothing"}'
                if statement.orelse:
                    text += f', else: {self.changes(card, statement.orelse, name_of)}'
                items.append(('', text))
            elif isinstance(statement, s.DeclaredSwitch):
                items.append(('', self.switch(card, statement, name_of)))
        out, verb = [], None
        for found, target in items:
            out.append(target if found and found == verb else f'{found} {target}'.strip())
            verb = found
        return ', '.join(out)

    def switch(self, card, statement, name_of):
        """A switch: what selects its case, and what each case changes."""
        say = _Words(name_of).text
        selector = statement.selector
        members = [case.member for case in statement.cases]
        if isinstance(selector, s.Drawn) and isinstance(selector.source, s.Distribution):
            source = selector.source
            weights = dict(zip(source.outcomes, source.params))
            head = 'draws ' + ' or '.join(f'{words(m)} (chance {number(weights.get(m, 0))})' for m in members)
        elif isinstance(selector, s.Drawn):
            head = f'draws {" or ".join(words(m) for m in members)} from {say(selector.source)}'
        elif isinstance(selector, s.Chosen):
            head = f'{say(selector.actor)} chooses {" or ".join(words(m) for m in members)}'
        else:
            head = f'by {say(selector)}'
        cases = []
        for case in statement.cases:
            changes = self.changes(card, case.body, name_of)
            guard = f' when {say(case.guard)}' if case.guard is not None else ''
            if changes or guard:
                cases.append(f'{words(case.member)}{guard}: {changes or "nothing"}')
        if statement.orelse:
            cases.append(f'else: {self.changes(card, statement.orelse, name_of)}')
        return ', '.join([head, *cases])

    def started(self, card, statement, name_of):
        """The event that a statement starts: "<card>: <event>", or the event of its own card; on
        each member of a collection, "<event> of <collection>"."""
        found = self.found.reached(statement.event, self.found.cards[card].members)
        event = event_of(statement.event).rpartition('.')[2]
        if found is None or found.what != 'event' or not found.members:
            return words(event)
        cards = list(dict.fromkeys(self.found.card_of.get(m) for m in found.members))
        if len(found.members) > 1:
            return f'{words(event)} of {name_of.group(s.Read(statement.event.start, statement.event.steps[:-1], None))}'
        if cards == [card]:
            return words(event)
        other = self.found.cards.get(cards[0])
        return f'{other.title}: {words(event)}' if other is not None else words(event)


def event_of(read):
    """The declared path of the event that a start reads: of one event, or of the event of each
    member of a collection."""
    kind = read.type
    return kind.of.event if isinstance(kind, s.Many) else kind.event


def _starts_with_time(node):
    """Whether a condition's words start with "from": a comparison `t >= x`, or an `and` that starts
    with one."""
    first = next(_conjuncts(node))
    if not (isinstance(first, s.Apply) and first.op == 'compare' and len(first.detail) == 1):
        return False
    left, op, right = _pairs(first)[0]
    if _special(right) and not _special(left):
        left, op = right, MIRROR[op]
    return isinstance(left, s.Read) and left.start == ('time',) and op == 'ge'


def _options(found, event):
    """The options that switch an event, by the runs that can start it (`Things.startable`): "only
    with <option>" when the runs that can are those with the option, "not with <option>" when they are
    those without it, else the options of each run that can; "" when every run can, and "in no run"
    when none can."""
    runs = found.runs
    held = [run for run in runs if found.startable(run).get(event.path, True)]
    if len(held) == len(runs):
        return ''
    if not held:
        return 'in no run'
    # An option that sets nothing switches nothing: the options of a run that set an input.
    setting = {option.name for option in found.declared.options if option.settings}
    chosen = {
        run: set(found.declared.run(run).options) & setting if run is not None else set() for run in runs
    }
    lacking = [run for run in runs if run not in held]
    options = [
        option.name for option in found.declared.options if any(option.name in chosen[run] for run in runs)
    ]
    for option in options:
        if all(option in chosen[r] for r in held) and not any(option in chosen[r] for r in lacking):
            return f'only with {option}'
    for option in options:
        if not any(option in chosen[r] for r in held) and all(option in chosen[r] for r in lacking):
            return f'not with {option}'
    return 'only in ' + _listed([run for run in held if run is not None])


def _label(event):
    """The event's text, or that of its first stage or case that has one."""
    if event.text:
        return event.text
    for step in event.steps:
        if isinstance(step, s.DeclaredStage):
            if step.text:
                return step.text
            for statement in s.statements_of(step.body):
                if isinstance(statement, s.DeclaredCase) and statement.text:
                    return statement.text
    return None


def card_events(found, card):
    """The events of one card (`Things.events`), in written order."""
    if card not in found.cards:
        raise ValueError(f'{card} is not a thing of the model')
    return tuple(found.events(card))


def card_lines(found, card):
    """The `Line` of each event of one card (`card_events`), in written order."""
    lines = _Lines(found)
    return tuple(lines.line(card, event) for event in card_events(found, card))
