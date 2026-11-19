"""The panels under the map (docs/draw.md, D-53, D-55, D-57): the Equations, the Symbols and the
References of the things that `[equations] things` names, as plain JSON data in the picture
(`model_map.picture`, its key `panels`). The layout and the SVG read this data and never the model;
`latex` writes the same data as a LaTeX fragment (`napkin draw --latex FILE`).

`panels(found, sheet, run, cards)` gives the panels of a model (`things.Things`), or None when
`[equations] things` names nothing:

- `settings`: what `[equations]` and `[references]` choose (`style.equation_settings`): `depth`,
  `width`, `lines`, `tags`, `symbols`, `checks`, `instances`, `references` and `kinds`.
- `equations`: one block for each shown card, in the order of the cards:
  `{name, title, template, members, lines}`. A thing that `things` names has its own block; a
  template stands for each of its members that `things` does not name itself. With `instances =
  "together"`, the members whose blocks are the same up to the member share one block, written with
  the keys of the template (`equations.Equations.together`); a table that `things` names shares one
  written with the keys of its card. A group of one member is that member's own block. With `"each"`,
  each member and each row has its own block. `name` is the member whose keys the block writes (a
  member, a template or a table's card); `members` are the members that it stands for, `{entity,
  card, title}`. Each line is `{kind, lhs, rhs, math, words, part, event, outcome, keys, marks,
  records, relation, when, latex}`: the trees as `notation.as_dict` (`lhs` and `rhs` for a balance, a
  rate and a formula, else `math`), the few words of E3, the key of the part whose form it shows, the
  event and the case of a jump, the keys of the symbols that it names in order (`equations.Line.keys`),
  the marks of the records of its form, the names of those records (for a `data-record` attribute;
  never shown), the relation of an equation (`=`, or `⇔` for a yes/no formula), when a jump happens in
  words (`when_words`: "repairs start", or "check, fixed" for a case of a switch; None for another
  line), and its LaTeX with the panel's symbols (`line_latex`).
- `symbols`: one row for each key that a line names, in reading order, then one for each stock row of
  a shown card that carries a tag: `{key, symbol, count, meaning, kind, unit, value, value_math,
  options, option_count, instances, range, range_status, distribution, marks, range_marks, records}`.
  `symbol` is `{base, prime, sub, text, latex}` (`Symbol.parts`, `text`, `latex`); `count` is the
  symbol of an event's count when a line names it, else None. `meaning` is the text of the part, else
  its name in words. `unit` is the unit of its type; a flow's is the unit of its rate; an event's (its
  time since) is h. `value` is the start as the file writes it (a member's own value first), or with
  `run` the value of the run's last option that sets the input; a yes/no reads Yes or No; a formula,
  a flow and an event have none. A start that an expression of other values sets is `value_math`, its
  tree, and each value that it names has a row too. `options` are the values that the options give an
  input, `{option, value, math, marks}`, when `OPTIONS_SHOWN` or fewer options set it, else none;
  `option_count` is their number. A template's row stands for its members: each field that the
  members share, and `instances`, `{entity, title, value, math}` of each member, when their values
  differ. `range` is `[lo, hi]` of an input's range as the file writes it (None for an open side);
  `range_status` is `chosen` (the drawing words it "chosen range lo–hi", with the note). `distribution`
  is the text of a distribution. `marks` are the marks of the records of the shown value, for an input
  and a fixed value only, and a start that the file writes as a value: a value worked out from others
  has none (its equation leads to the cited inputs). `range_marks` are those of the records of the
  range, which are its line's. `records` are the names and IDs of the records, never shown.
- `references`: the entries of the cited places (`references.references`), in the order of their
  numbers, `{number, kind, label, text, url, link_text, hover, record}`. The places are the lines,
  then, when the Symbols table shows, the rows of inputs and fixed values, their options and their
  ranges, in reading order: only what shows is cited. Without `[references] show`, there are no
  entries and no marks.
- `tags`: `{stock key: symbol text}` of each stock and tally row of the shown cards, with `tags`.
- `note`: the words of the note on a chosen range when a row shows one, else None (`NOTE`).

A mark is `[number, kind]`, the kind of its entry (`references.KINDS`), which gives its colour
(`references.COLOUR_KIND`).

The symbols. One symbol for each key, unique in the panel. A value, a flow and an event has the symbol
that `symbols.symbols` makes over the cards that the picture draws (and the cards of the members that a
line reads and the picture hides), for the keys that the panel shows. The panel makes the others from
them, each the first of its candidates that no other symbol (or an event's count) has (`_numbered`):
- a leg of a flow with legs, `member.flow.leg`: the flow's symbol with the initial of the leg at the
  end of its subscript; a leg of a route, `member.flow.forward`, the same;
- a key of a template or of a table, `Template.name`: the symbol of its first member with the
  template's own tag in place of the member's tag (a tag that no card has, `symbols.tags`), and
  without a row's number; a table keeps the tag of its card;
- a parameter or a local of an event, `member.event.name`: the initial of its name, with the event's
  subscript;
- any other key (a result of a solver): its initial and x.
The time since an event is its symbol, and its count the count's symbol (`Symbol.counted`): in the
LaTeX, `since(e)` is the symbol of e and `count(e)` the symbol of its count.
"""

from __future__ import annotations

from dataclasses import dataclass, field, fields, replace
from itertools import count
from urllib.parse import quote

from ..model import semantic as sem
from . import notation
from . import references as refs
from . import style as styles
from . import symbols as made
from .equations import PLACEHOLDER, Equations, records_of, rename
from .layout import range_words
from .notation import Count, Deriv, Elapsed, Node, Since, Sum, Sym, split
from .symbols import Symbol, _texts
from .text import in_words

# The note on a chosen range (CONTRIBUTING.md, "Writing style", rule 4).
NOTE = 'A chosen range is the range a reader can set. It is not a measured interval.'
# The most options of a value whose values a row lists.
OPTIONS_SHOWN = 3
# The kinds of row whose value has marks: a value worked out from others has none. A start of a
# stock, a tally or a state has marks too when the file writes it as a value, not as an expression
# (`_Facts.marked`).
MARKED = ('input', 'fixed')
# The kinds of value whose start is their value, and the unit of the time since an event.
STARTS = ('stock', 'tally', 'state')
HOURS = 'h'
# What follows a key to name the count of its event, in the trees that `line_latex` writes. No key has
# it: a name of the language has no `#`.
COUNTED = '#count'
# The separator of two trees of one line in its LaTeX: a comma and a quad, which no tree writes.
BETWEEN = r',\quad '
# The relation of an equation in LaTeX, with its spaces: `=`, and `\iff` for a yes/no formula.
LATEX_RELATIONS = {'=': ' = ', '⇔': r' \iff '}


def panels(found, sheet, run=None, cards=()):
    """The panels of a picture (see the module's text), or None when `[equations] things` names
    nothing. `found` is the model's `things.Things`, `sheet` the picture (`style.Style`), `run` the run
    of the picture or None for every run joined, and `cards` the picture's cards
    (`model_map.picture`), in its order."""
    if not sheet.equations:
        return None
    return _Panel(found, sheet, run, list(cards)).data()


# ---- the facts of a row ---------------------------------------------------------------------------


@dataclass
class _Facts:
    """What a row says of one key, before its marks: the records are those of the shown value, of each
    option and of the range."""

    kind: str | None
    meaning: str
    unit: str | None = None
    value: str | None = None
    distribution: str | None = None
    options: list = field(default_factory=list)  # (option, value text, records, tree)
    range: list | None = None
    range_status: str | None = None
    records: object = None
    range_records: object = None
    names: tuple = ()  # every record of the key, for `records`
    instances: list = field(default_factory=list)  # {entity, title, value, math} of a template's members
    value_tree: Node | None = None  # the start, when an expression of other values sets it
    instance_trees: list = field(default_factory=list)  # the start of each member, when an expression sets it

    def marked(self):
        """Whether the row's value carries the marks of its records: an input's and a fixed value's,
        and a start that the file writes as a value; a start that an expression of other values sets
        is worked out from others, and its marks are those of the values that it reads."""
        if self.kind in MARKED:
            return True
        return self.kind in STARTS and self.value_tree is None and not self.instance_trees

    def trees(self):
        """Each tree of a start that an expression sets: the value's, each option's, each member's."""
        found = [self.value_tree, *(option[3] for option in self.options), *self.instance_trees]
        return [tree for tree in found if tree is not None]


def tree_keys(tree):
    """The keys of the values and events that a tree names, in order, each once."""
    out = []
    for node in notation.nodes(tree):
        if isinstance(node, (Sym, Elapsed, Deriv)):
            key = node.key
        elif isinstance(node, (Since, Count)):
            key = node.target
        else:
            continue
        if key not in out:
            out.append(key)
    return out


def shown(init, kind=None):
    """(the text of a start as the file writes it, the text of its distribution): a yes/no reads Yes
    or No, a number with the unit of its type, an enum member and a text as they are; a distribution,
    and a draw of one, is its text only. None for a start that is an expression of other values."""
    if isinstance(init, sem.Const):
        value = init.value
        if isinstance(value, bool):
            return ('Yes' if value else 'No'), None
        if isinstance(value, (int, float)):
            unit = getattr(init.type, 'unit', '')
            text = notation_number(value)
            return (f'{text} {unit}' if unit else text), None
        return str(value), None
    if isinstance(init, sem.Drawn) and isinstance(init.source, sem.Distribution):
        init = init.source
    if isinstance(init, sem.Distribution):
        return None, distribution_text(init)
    return None, None


def notation_number(value):
    """A number as the Symbols table writes it: an integer as it is, any other number as Python writes
    it."""
    if isinstance(value, float) and value.is_integer() and abs(value) < 1e15:
        return str(int(value))
    return repr(value) if isinstance(value, float) else str(value)


def distribution_text(node):
    """The text of a distribution as the file writes it: `uniform(1 h, 3 h)`,
    `categorical(FIXED: 0.7, FAILED: 0.3)`."""
    if node.family == 'categorical':
        pairs = ', '.join(
            f'{member}: {notation_number(weight)}' for member, weight in zip(node.outcomes, node.params)
        )
        return f'categorical({pairs})'
    unit = getattr(node.type.of, 'unit', '')
    values = ', '.join(notation_number(value) + (f' {unit}' if unit else '') for value in node.params)
    return f'{node.family}({values})'


def record_names(*records):
    """The names and the IDs of records, in order, each once: a cited record's name, the IDs that a
    record rests on, and the claims of its links."""
    from ..model.language import nodes as n

    out = []
    for item in records_of(*records):
        found = []
        if isinstance(item, n.Cite):
            found.append(item.name)
        elif isinstance(item, (n.Inline, n.Record)):
            found += [getattr(item, 'name', None), *(identifier for _, identifier in item.relations)]
            found += [claim.id for claim in item.claims]
        elif hasattr(item, 'get'):
            found += [item.get('name'), item.get('assumption'), item.get('convention')]
            found += [link.get('claim') for link in item.get('links') or () if hasattr(link, 'get')]
        out += [name for name in found if isinstance(name, str) and name and name not in out]
    return out


# ---- the clocks of the LaTeX -------------------------------------------------------------------------


def _clocks(node):
    """A tree with the time since each event as the event's symbol, and its count as the symbol of its
    count (the key and `COUNTED`): the forms that `line_latex` writes."""
    if isinstance(node, Since):
        return Sym(node.target)
    if isinstance(node, Count):
        return Sym(node.target + COUNTED)
    if isinstance(node, Sum):
        return node
    changed = {}
    for item in fields(node):
        value = getattr(node, item.name)
        if isinstance(value, (Node, tuple)):
            changed[item.name] = _clocks_in(value)
    return replace(node, **changed) if changed else node


def _clocks_in(value):
    if isinstance(value, Node):
        return _clocks(value)
    if isinstance(value, tuple):
        return tuple(_clocks_in(item) for item in value)
    return value


def for_words(block):
    """The line under the title of a block of several members: "For A, B." and, for a template,
    which subscript stands for which: "For North, South (z: n, s)." """
    titles = ', '.join(member['title'] for member in block['members'])
    subs = [member.get('subscript') for member in block['members']]
    if block.get('subscript') and all(subs):
        return f'For {titles} ({block["subscript"]}: {", ".join(subs)}).'
    return f'For {titles}.'


def when_words(event, outcome):
    """When a jump happens, in words: the name of its event (`member.event`) in words, and the case of
    its switch after a comma; None for a line of no event."""
    if event is None:
        return None
    words = in_words(split(event)[1]).lower()
    return f'{words}, {in_words(outcome.lower()).lower()}' if outcome else words


def line_latex(kind, trees, symbol, counted, relation='='):
    """The LaTeX of a line: `lhs = rhs` for an equation (`trees` is (lhs, rhs); `lhs \\iff rhs` for the
    relation `⇔`), else its trees with a comma and a quad between them. `symbol(key)` is the LaTeX of a
    key's symbol, and `counted(key)` that of the count of its event."""

    def written(key):
        return counted(key[: -len(COUNTED)]) if key.endswith(COUNTED) else symbol(key)

    texts = [notation.latex(_clocks(tree), written) for tree in trees]
    if kind in ('balance', 'rate', 'formula'):
        return LATEX_RELATIONS[relation].join(texts)
    return BETWEEN.join(texts)


# ---- the panel ------------------------------------------------------------------------------------


def _numbered(symbol):
    """The candidates of a made symbol: itself, then with 2, 3, … at the end of its subscript."""
    yield symbol
    for number in count(2):
        yield symbol.under(str(number))


class _Panel:
    def __init__(self, found, sheet, run, cards):
        self.found, self.sheet, self.run = found, sheet, run
        self.settings = styles.equation_settings(sheet)
        self.cards = cards
        self.order = {card['id']: k for k, card in enumerate(cards)}
        self.titles = {card['id']: card['title'] for card in cards}
        self.equations = Equations(found, run)
        self.options = list(found.declared.run(run).options) if run is not None else []
        # The names whose keys stand for several members: {name: its members}.
        self.groups = {}
        for card in cards:
            members = found.cards[card['id']].members
            if found.cards[card['id']].kind == 'table':
                self.groups[card['id']] = list(members)

    # ---- the blocks

    def blocks(self):
        """The blocks of the shown cards, in the order of the cards (see the module's text)."""
        found = self.found
        named = set(self.sheet.equations)
        depth, checks = self.settings['depth'], self.settings['checks']
        together = self.settings['instances'] == 'together'
        out, templates = [], {}
        for card in self.cards:
            entry = card['id']
            thing = found.cards[entry]
            if entry in named:
                members = list(thing.members)
                if together and len(members) > 1:
                    out += self.grouped(self.equations.together(members, entry, depth=depth, checks=checks))
                else:
                    out += [self.single(name, depth, checks) for name in members]
            elif thing.shown_template in named:
                templates.setdefault(thing.shown_template, []).append(entry)
        for template, entries in templates.items():
            members = [member for entry in entries for member in found.cards[entry].members]
            if together:
                out += self.grouped(self.equations.together(members, template, depth=depth, checks=checks))
            else:
                out += [self.single(name, depth, checks) for name in members]
        position = {member: k for k, member in enumerate(found.template_of)}
        out.sort(key=lambda item: (self.order[item[1]['members'][0]['card']], position[item[0][0]]))
        return out

    def member(self, name):
        card = self.found.card_of[name]
        title = self.titles[card] if self.found.cards[card].kind != 'table' else self.found.title_of(name)
        return {'entity': name, 'card': card, 'title': title}

    def single(self, name, depth, checks):
        block = self.equations.block(name, depth=depth, checks=checks)
        member = self.member(name)
        info = {'name': name, 'title': member['title'], 'template': None, 'members': [member]}
        return (name,), info, block

    def grouped(self, groups):
        out = []
        for group in groups:
            if len(group.members) == 1:
                (name,) = group.members
                member = self.member(name)
                info = {'name': name, 'title': member['title'], 'template': None, 'members': [member]}
                out.append(((name,), info, group.blocks[0]))
                continue
            card = self.found.cards.get(group.name)
            template = card.template if card is not None else group.name
            title = self.titles.get(group.name) if card is not None else in_words(group.name)
            members = [self.member(name) for name in group.members]
            self.groups.setdefault(group.name, [])
            self.groups[group.name] += [name for name in group.members if name not in self.groups[group.name]]
            info = {'name': group.name, 'title': title, 'template': template, 'members': members}
            out.append((group.members, info, group.block))
        return out

    # ---- the keys

    def resolve(self, key):
        """(the member, the path below its template, its declared part) of a key; (None, the name,
        the declared value) for a value of the top level; (None, key, None) for any other key."""
        parts = key.split('.')
        for k in range(len(parts) - 1, 0, -1):
            member = '.'.join(parts[:k])
            if member in self.found.template_of:
                name = '.'.join(parts[k:])
                return member, name, self.found.part(self.found.template_of[member], name)
        return None, key, self.found.declared.part(key)

    def kind_of(self, key):
        """The kind of the part that a key names: a value's kind (`things.Things.kind`), `flow`,
        `event`, a parameter's `input`, or None."""
        entity, name = split(key)
        if entity in self.groups:
            return self.kind_of(f'{self.groups[entity][0]}.{name}')
        _, _, part = self.resolve(key)
        if isinstance(part, sem.DeclaredValue):
            event = self.event_of_local(key)
            if event is not None and part in event.params:
                return 'input'
            return self.found.kind(part)
        if isinstance(part, (sem.DeclaredFlow, sem.DeclaredLegs)):
            return 'flow'
        if isinstance(part, sem.DeclaredEvent):
            return 'event'
        return None

    def event_of_local(self, key):
        """The event whose parameter or local a key names (`member.event.name`), or None."""
        member, name, _ = self.resolve(key)
        head = name.rpartition('.')[0]
        if member is None or not head:
            return None
        part = self.found.part(self.found.template_of[member], head)
        return part if isinstance(part, sem.DeclaredEvent) else None

    def base_keys(self, key):
        """The keys of `symbols.symbols` that the symbol of a key is made from."""
        entity, name = split(key)
        if entity in self.groups:
            return [f'{member}.{name}' for member in self.groups[entity][:1]]
        member, path, _ = self.resolve(key)
        if member is not None and '.' in path:
            return [f'{member}.{path.split(".")[0]}']
        return [key]

    # ---- the symbols

    def make_symbols(self, keys):
        """{key: Symbol} of each key (see the module's text)."""
        found = self.found
        wanted = list(dict.fromkeys(base for key in keys for base in self.base_keys(key)))
        drawn = [card['id'] for card in self.cards]
        extra = []
        for key in wanted:
            member, _, _ = self.resolve(key)
            card = found.card_of.get(member)
            if card is not None and card not in drawn and card not in extra:
                extra.append(card)
        cards = [*drawn, *(card for card in found.cards if card in extra)]
        self.made = made.symbols(found, self.sheet, cards, wanted)
        self.card_tags = made.tags(found, self.sheet, cards)
        self.taken = set()
        for key, symbol in self.made.items():
            self.taken.update(_texts(symbol, self.kind_of(key)))
        templates = [name for name in self.groups if name not in found.cards]
        given = replace(self.sheet, subscripts=tuple(self.card_tags.items()))
        self.template_tags = made.tags(found, given, [*cards, *templates]) if templates else {}
        self.own = {name: dict(items) for name, items in self.sheet.symbols}
        self.done = {}
        return {key: self.symbol(key) for key in keys}

    def subscripted(self, info):
        """A block's facts with the subscripts: the template's of a block that stands for its members,
        and each member's card's, so that its head can say which stands for which (`for_words`)."""
        template = info['template'] if info['name'] == info['template'] else None
        sub = self.template_tags.get(template) if template is not None else None
        members = [{**member, 'subscript': self.card_tags.get(member['card'])} for member in info['members']]
        return {**info, 'subscript': sub, 'members': members}

    def free(self, candidates, kind):
        for symbol in candidates:
            texts = _texts(symbol, kind)
            if not any(text in self.taken for text in texts) and len(set(texts)) == len(texts):
                self.taken.update(texts)
                return symbol
        raise AssertionError('a list of candidates has no end')

    def symbol(self, key):
        if key in self.done:
            return self.done[key]
        if key in self.made:
            self.done[key] = self.made[key]
            return self.made[key]
        entity, name = split(key)
        kind = self.kind_of(key)
        member, path, part = self.resolve(key)
        initial = made.words(name)[0][0]
        if entity in self.groups:
            symbol = self.free(_numbered(self.group_symbol(entity, name)), kind)
        elif member is not None and '.' in path and path.split('.')[0] in self.base(member, path):
            parent = self.symbol(f'{member}.{path.split(".")[0]}')
            if isinstance(part, (sem.DeclaredFlow, sem.DeclaredLegs)) or kind is None:
                symbol = self.free(_numbered(parent.under(initial)), 'flow')
            else:
                base = made.base_of(name, made.CLASSES.get(kind, 'lower'))
                symbol = self.free(_numbered(Symbol(base, False, parent.sub)), kind)
        else:
            # A key that no card draws a symbol for: its initial and x, the first that is free.
            base = initial.upper() if kind in STARTS else initial
            symbol = self.free(_numbered(Symbol(base, False, 'x')), kind)
        self.done[key] = symbol
        return symbol

    def base(self, member, path):
        """The names of the parts of a member's template that have a symbol of their own."""
        return {name for name, _ in made.members(self.found, self.found.card_of[member])}

    def group_symbol(self, name, member):
        """The first candidate of the symbol of `name.member` (see the module's text)."""
        first = self.groups[name][0]
        mine = self.made.get(f'{first}.{member}') or self.symbol(f'{first}.{member}')
        parts = mine.sub.split(',') if mine.sub else []
        rows = dict(made.copies(self.found, self.found.card_of[first]))
        if rows.get(first) is not None and parts and parts[-1] == str(rows[first]):
            parts = parts[:-1]
        if name in self.found.cards:
            return Symbol(mine.base, mine.prime, ','.join(parts))
        given = self.own.get(name, {}).get(member)
        written = mine if given is None else made.parse(given)
        return Symbol(written.base, written.prime, ','.join([self.template_tags[name], *parts[1:]]))

    # ---- the facts

    def run_setting(self, member, value):
        """The setting of the run's last option that sets an input of a member, or None."""
        template = self.found.template_of[member]
        found = None
        for option in self.options:
            for setting in self.found.declared.option(option).settings:
                if setting.name != value.name:
                    continue
                if setting.member == member or setting.instances == template or setting.path == value.path:
                    found = setting
        return found

    def facts(self, key):
        """The facts of a key, or of a template's key from its members' facts."""
        entity, name = split(key)
        if entity in self.groups:
            return self.group_facts(entity, name)
        member, _, part = self.resolve(key)
        if isinstance(part, sem.DeclaredValue):
            return self.value_facts(member, part)
        if isinstance(part, (sem.DeclaredFlow, sem.DeclaredLegs)):
            return self.flow_facts(member, part)
        if isinstance(part, sem.DeclaredEvent):
            return _Facts(
                'event',
                part.text or in_words(part.name),
                HOURS,
                records=part.evidence,
                names=record_names(part.evidence),
            )
        return _Facts(None, in_words(name))

    def value_facts(self, member, value):
        kind = self.kind_of_value(member, value)
        init, records = value.init, value.evidence
        own = None
        if member is not None:
            declared = self.found.declared.part(member)
            own = next((item for item in getattr(declared, 'values', ()) if item.name == value.name), None)
        if own is not None:
            init, records = own.init, records_of(own.evidence, value.evidence)
        setting = self.run_setting(member, value) if self.run is not None and member is not None else None
        if setting is not None:
            init, records = setting.value, setting.evidence or records
        unit = value.type.unit or None if isinstance(value.type, sem.Num) else None
        text, distribution = shown(init) if kind in (*MARKED, *STARTS) else (None, None)
        facts = _Facts(
            kind,
            value.text or in_words(value.name),
            unit,
            text,
            distribution,
            records=records,
            names=record_names(value.evidence, own.evidence if own is not None else None),
        )
        if kind in STARTS and text is None and distribution is None and init is not None:
            tree = notation.build(init, self.equations.keys(member)) if member is not None else None
            facts.value_tree = tree if tree is not None and tree_keys(tree) else None
            if facts.value_tree is not None:
                # In a table too narrow for the math, the start shows as the file writes it.
                kind_of_line, line = (
                    ('Property', own.line) if own is not None else ('Declaration', value.line)
                )
                facts.value = self.found.written(kind_of_line, line, 'value')
        if kind == 'input' and member is not None:
            for option in self.found.declared.options:
                for item in option.settings:
                    if item.name == value.name and (
                        item.member == member or item.instances == self.found.template_of[member]
                    ):
                        option_text, option_distribution = shown(item.value)
                        facts.options.append(
                            (option.name, option_text or option_distribution, item.evidence, None)
                        )
                        facts.names = (*facts.names, *record_names(item.evidence))
        if (
            kind == 'input'
            and isinstance(value.type, sem.Num)
            and (value.lower is not None or value.upper is not None)
        ):
            facts.range = [None if edge is None else shown(edge)[0] for edge in (value.lower, value.upper)]
            facts.range_status = 'chosen'
            facts.range_records = value.evidence
        return facts

    def kind_of_value(self, member, value):
        if member is not None:
            event = (
                self.event_of_local(f'{member}.{value.path.split(".", 1)[1]}') if '.' in value.path else None
            )
            if event is not None and value in event.params:
                return 'input'
        return self.found.kind(value)

    def flow_facts(self, member, flow):
        unit = None
        legs = flow.legs if isinstance(flow, sem.DeclaredLegs) else (flow,)
        if isinstance(flow, sem.DeclaredFlow):
            unit = flow.rate.unit or None
        elif isinstance(flow, sem.DeclaredLegs):
            unit = None  # a flow with legs is its served fraction, a plain number
        records = record_names(flow.evidence, *(leg.evidence for leg in legs))
        return _Facts('flow', flow.text or in_words(flow.name), unit, records=flow.evidence, names=records)

    def group_facts(self, name, member):
        """A template's facts: each field that its members share, and the value of each member."""
        each = [self.facts(f'{entity}.{member}') for entity in self.groups[name]]
        first = each[0]

        def shared(attribute):
            values = [getattr(item, attribute) for item in each]
            return values[0] if all(value == values[0] for value in values) else None

        meanings = {item.meaning for item in each}
        facts = _Facts(
            first.kind,
            first.meaning if len(meanings) == 1 else in_words(member),
            shared('unit'),
            shared('value'),
            shared('distribution'),
            range=shared('range'),
            range_status=shared('range_status') if shared('range') is not None else None,
            records=records_of(*(item.records for item in each)),
            range_records=records_of(*(item.range_records for item in each)) if shared('range') else None,
            names=tuple(record_names(*(item.names for item in each))),
        )
        entities = self.groups[name]
        options = {}
        for entity, item in zip(entities, each):
            for option, text, records, tree in item.options:
                options.setdefault(option, []).append((entity, text, records, tree))
        for option, items in options.items():
            texts = {text for _, text, _, _ in items}
            together = records_of(*(records for _, _, records, _ in items))
            every = len(items) == len(each)
            facts.options.append((option, texts.pop() if len(texts) == 1 and every else None, together, None))
        # A start that an expression sets: the template's tree when the members' are the same up to
        # the member, else each member's own.
        facts.value_tree = self.shared_tree(list(zip(entities, (item.value_tree for item in each))), name)
        facts.instances = []
        if facts.value is None and facts.distribution is None and first.kind in (*MARKED, *STARTS):
            facts.instances = [
                {
                    'entity': entity,
                    'title': self.member(entity)['title'],
                    'value': item.value or item.distribution,
                    'math': None if item.value_tree is None else notation.as_dict(item.value_tree),
                }
                for entity, item in zip(entities, each)
            ]
            facts.instance_trees = [item.value_tree for item in each if item.value_tree is not None]
            facts.value_tree = None
        return facts

    @staticmethod
    def shared_tree(trees, name):
        """The tree of a template (`name`) from its members' trees, (member, tree) each: the first one
        written with the template's keys, when each is the same up to its member; else None."""
        if not trees or any(tree is None for _, tree in trees):
            return None
        placed = [rename(tree, entity, PLACEHOLDER) for entity, tree in trees]
        if any(item != placed[0] for item in placed[1:]):
            return None
        entity, tree = trees[0]
        return rename(tree, entity, name)

    # ---- the whole

    def data(self):
        blocks = self.blocks()
        shown_cards = []
        for _, info, _ in blocks:
            shown_cards += [m['card'] for m in info['members'] if m['card'] not in shown_cards]
        line_keys = []
        for _, _, block in blocks:
            for line in block.lines:
                line_keys += [key for key in line.keys if key not in line_keys]
        tag_keys = []
        if self.settings['tags']:
            for card in self.cards:
                if card['id'] in shown_cards:
                    tag_keys += [stock['key'] for stock in card['stocks']]
        keys = list(dict.fromkeys([*line_keys, *tag_keys]))
        # Each value that a start's formula names has a row too, and so on, until no new key comes.
        facts = {}
        k = 0
        while k < len(keys):
            found = facts[keys[k]] = self.facts(keys[k])
            keys += [key for tree in found.trees() for key in tree_keys(tree) if key not in keys]
            keys = list(dict.fromkeys(keys))
            k += 1
        symbols = self.make_symbols(keys)
        trees = [tree for _, _, block in blocks for line in block.lines for tree in line.trees]
        trees += [tree for found in facts.values() for tree in found.trees()]
        counted = {node.target for tree in trees for node in notation.nodes(tree) if isinstance(node, Count)}

        def latex_of(key):
            return symbols[key].latex()

        def count_of(key):
            return symbols[key].counted().latex()

        show_rows = self.settings['symbols']
        cited = []
        for b, (_, _, block) in enumerate(blocks):
            cited += [(('line', b, k), line.records) for k, line in enumerate(block.lines)]
        if show_rows:
            for key in keys:
                found = facts[key]
                if not found.marked():
                    continue
                cited.append((('symbol', key), found.records))
                if len(found.options) <= OPTIONS_SHOWN:
                    cited += [(('option', key, option), records) for option, _, records, _ in found.options]
                if found.range is not None:
                    cited.append((('range', key), found.range_records))
        listed = None
        if self.settings['references']:
            listed = refs.references(cited, self.found, kinds=self.settings['kinds'])

        def marks(place):
            if listed is None:
                return []
            return [[number, kind] for number, kind in listed.marks.get(place, ())]

        equations = []
        for b, (_, info, block) in enumerate(blocks):
            lines = []
            for k, line in enumerate(block.lines):
                trees = line.trees
                lines.append(
                    {
                        'kind': line.kind,
                        'lhs': None if line.lhs is None else notation.as_dict(line.lhs),
                        'rhs': None if line.rhs is None else notation.as_dict(line.rhs),
                        'math': [notation.as_dict(tree) for tree in line.math],
                        'words': line.words,
                        'part': line.part,
                        'event': line.event,
                        'outcome': line.outcome,
                        'keys': list(line.keys),
                        'marks': marks(('line', b, k)),
                        'records': record_names(line.records),
                        'relation': line.relation,
                        'when': when_words(line.event, line.outcome),
                        'latex': line_latex(line.kind, trees, latex_of, count_of, line.relation),
                    }
                )
            equations.append({**self.subscripted(info), 'lines': lines})
        rows = []
        for key in keys:
            found, symbol = facts[key], symbols[key]
            many = len(found.options) > OPTIONS_SHOWN
            marked = show_rows and found.marked()
            rows.append(
                {
                    'key': key,
                    'symbol': _parts(symbol),
                    'count': _parts(symbol.counted()) if key in counted else None,
                    'meaning': found.meaning,
                    'kind': found.kind,
                    'unit': found.unit,
                    'value': found.value,
                    'value_math': None if found.value_tree is None else notation.as_dict(found.value_tree),
                    'options': []
                    if many
                    else [
                        {
                            'option': option,
                            'value': text,
                            'math': None if tree is None else notation.as_dict(tree),
                            'marks': marks(('option', key, option)) if marked else [],
                        }
                        for option, text, _, tree in found.options
                    ],
                    'option_count': len(found.options),
                    'instances': found.instances,
                    'range': found.range,
                    'range_status': found.range_status,
                    'distribution': found.distribution,
                    'marks': marks(('symbol', key)) if marked else [],
                    'range_marks': marks(('range', key)) if marked and found.range is not None else [],
                    'records': list(found.names),
                }
            )
        entries = []
        for entry in listed.entries if listed is not None else ():
            entries.append(
                {
                    'number': entry.number,
                    'kind': entry.kind,
                    'label': entry.label,
                    'text': entry.text,
                    'url': entry.url,
                    'link_text': entry.link_text,
                    'hover': entry.hover,
                    'record': list(entry.record),
                }
            )
        ranged = show_rows and any(
            row['range'] is not None and row['range_status'] == 'chosen' for row in rows
        )
        return {
            'settings': self.settings,
            'equations': equations,
            'symbols': rows,
            'references': entries,
            'left_out': list(listed.left_out) if listed is not None else [],
            'tags': {key: symbols[key].text() for key in tag_keys},
            'note': NOTE if ranged else None,
        }


def _parts(symbol):
    base, prime, sub = symbol.parts()
    return {'base': base, 'prime': prime, 'sub': sub, 'text': symbol.text(), 'latex': symbol.latex()}


# ---- the LaTeX fragment (D-57) ----------------------------------------------------------------------

# The characters of an address that `\href` reads as themselves, at the top level and in the argument
# of another command. hyperref's `\hyper@normalise` makes `&` a plain character and `_` and `~` print
# themselves; in an argument, they only go through `\edef` and the PDF string. `&` must stay: as %26,
# it no longer separates the parameters of a query. Every other character is written as %XX: `$`, the
# math shift of TeX, as %24, which a server reads as `$`; `\`, `{`, `}` and `^`, which an address
# never holds as they are. `%` and `#` stay, written `\%` and `\#`, which hyperref reads in any
# argument. A `#` after the first is %23: hyperref splits the address at its first `#`.
URL_SAFE = ":/?[]@!&'()*+,;=-._~%"
# The packages that the fragment needs, in the order to load them: hyperref last, as its manual says.
PACKAGES = ('amsmath', 'longtable', 'hyperref')


def _escape(text):
    return notation.escape(' '.join(str(text or '').split()))


def _url(url):
    """An address for `\\href`: each character outside `URL_SAFE` as %XX, the first `#` kept, then `%`
    and `#` escaped for TeX."""
    address, mark, fragment = url.partition('#')
    text = quote(address, safe=URL_SAFE) + mark + quote(fragment, safe=URL_SAFE)
    return text.replace('%', r'\%').replace('#', r'\#')


def _marks(marks, math=False):
    """The marks of a line or a value in the fragment: their numbers as a superscript of the text, so
    that no mark reads as a power; in `\\text{…}` for a place in math."""
    if not marks:
        return ''
    text = r'\textsuperscript{' + ','.join(str(number) for number, _ in marks) + '}'
    return rf'\text{{{text}}}' if math else text


def latex(picture):
    """The LaTeX fragment of a picture's panels (`napkin draw --latex FILE`, D-57), from the picture
    alone. It starts with comments that name the picture and the packages that it needs (`PACKAGES`).
    Then, for each block of equations, its title in `\\paragraph` and one `align*` with a line for each
    line of the block: an equation aligned at its `=`, any other line after the alignment point, then
    its words in `\\text{…}` and its marks as a superscript. Each `align*` is in a group with
    `\\allowdisplaybreaks`, so that a long block breaks across pages. Then the symbols in a `longtable`
    (symbol, meaning, unit, value, range), which breaks across pages and repeats its header on each
    page, with the note on a chosen range; a range has the words of the SVG (`layout.range_words`).
    Then the references in an `enumerate`, each item its kind's words, its text and its link (`\\href`,
    an `http` or `https` address only, `_url`). Every text is escaped (`notation.escape`). A picture
    without panels gives a fragment of comments only, which says that the stylesheet names no thing in
    `[equations] things`."""
    name = str(picture.get('name') or '')
    run = picture.get('run')
    needed = [rf'\usepackage{{{package}}}' for package in PACKAGES]
    head = [
        f'% The equations, symbols and references of the picture of {name}'
        + (f', run {run}' if run else '')
        + ' (napkin draw --latex).',
        '% It needs ' + ', '.join(needed[:-1]) + ' and ' + needed[-1] + ', in this order.',
    ]
    found = picture.get('panels')
    if not found:
        head.append('% The stylesheet names no thing in [equations] things, so there are no equations.')
        return '\n'.join(head) + '\n'
    out = [*head, '']
    rows = {row['key']: row for row in found['symbols']}

    def math(data):
        # A start that a formula sets, with the table's symbols.
        def symbol(key):
            return rows[key]['symbol']['latex']

        def counted(key):
            return rows[key]['count']['latex']

        return '$' + line_latex('bound', [notation.from_dict(data)], symbol, counted) + '$'

    for block in found['equations']:
        out.append(rf'\paragraph{{{_escape(block["title"])}}}')
        if len(block['members']) > 1:
            out.append(_escape(for_words(block)))
        if not block['lines']:
            out += [_escape('No equations.'), '']
            continue
        # A page can break between the lines of the block. `\allowdisplaybreaks` makes a local change
        # of `\interdisplaylinepenalty`, and amsmath reads that value at each `\\` of the `align*`. So
        # the group is sufficient: after the block, the document has its own value again. [1] makes a
        # break the last choice (amsmath's manual).
        out += [r'{\allowdisplaybreaks[1]', r'\begin{align*}']
        lines = []
        for line in block['lines']:
            text = line['latex']
            if line['kind'] in ('balance', 'rate', 'formula'):
                sign = LATEX_RELATIONS[line['relation']]
                text = text.replace(sign, ' &' + sign.lstrip(), 1)
            else:
                text = '& ' + text
            notes = [rf'\text{{{_escape(line["words"])}}}'] if line['words'] else []
            if line['when']:
                # A jump happens when its event happens.
                notes.append(rf'\text{{at {_escape(line["when"])}}}')
            tail = r' \quad '.join(notes) + _marks(line['marks'], math=True)
            lines.append(text + (f' && {tail}' if tail else ''))
        out.append(' \\\\\n'.join(lines))
        out += [r'\end{align*}}', '']
    if found['settings']['symbols'] and found['symbols']:
        # The header row is repeated at the top of each page (`\endhead`). With a short symbol and unit,
        # the columns and the space between them fit the width of the text of an article.
        out += [
            r'\begin{longtable}{l p{0.25\linewidth} l p{0.2\linewidth} p{0.13\linewidth}}',
            r'Symbol & Meaning & Unit & Value & Range \\',
            r'\hline',
            r'\endhead',
        ]
        for row in found['symbols']:
            symbol = f'${row["symbol"]["latex"]}${_marks(row["marks"])}'
            if row['count'] is not None:
                symbol += f', ${row["count"]["latex"]}$'
            meaning = row['meaning']
            if row['kind'] == 'event':
                # The symbol of an event is the time since it happens, and N the number of times.
                meaning = meaning.rstrip('.') + ': the time since it happens'
                meaning += ', and how many times' if row['count'] else ''
            if row['value_math'] is not None:
                values = [math(row['value_math'])]
            else:
                values = [_escape(row['value'] or row['distribution'] or '')]
            for item in row['instances']:
                if item['math'] is not None:
                    values.append(f'{_escape(item["title"])}: {math(item["math"])}')
                elif item['value']:
                    values.append(_escape(f'{item["title"]}: {item["value"]}'))
            value = '; '.join(item for item in values if item)
            for option in row['options']:
                if option['math'] is not None:
                    value += f'; {_escape(option["option"])}: {math(option["math"])}'
                    value += _marks(option['marks'])
                elif option['value'] is not None:
                    value += f'; {_escape(option["option"])}: {_escape(option["value"])}'
                    value += _marks(option['marks'])
            if not row['options'] and row['option_count']:
                value += _escape(f'; {row["option_count"]} options set it')
            # "chosen range lo--hi" or "range lo--hi", as the SVG writes it, with the en dash of TeX.
            words = range_words(row)
            span = '' if words is None else _escape(words).replace('–', '--') + _marks(row['range_marks'])
            cells = [symbol, _escape(meaning), _escape(row['unit'] or ''), value, span]
            out.append(' & '.join(cells) + r' \\')
        out += [r'\end{longtable}', '']
        if found['note']:
            out += [r'\par\noindent ' + _escape(found['note']), '']
    if found.get('left_out'):
        # The kinds of record that the list leaves out ([references] kinds), said, not hidden.
        out += [r'\par\noindent ' + _escape(refs.left_out_words(found.get('left_out'))), '']
    if found['references']:
        out.append(r'\begin{enumerate}')
        for entry in found['references']:
            item = rf'\item \textbf{{{_escape(entry["label"])}.}} {_escape(entry["text"])}'
            if entry['url'] and refs.web_host(entry['url']):
                item += rf' \href{{{_url(entry["url"])}}}{{{_escape(entry["link_text"] or entry["url"])}}}'
            out.append(item)
        out += [r'\end{enumerate}', '']
    return '\n'.join(out)


__all__ = ['NOTE', 'OPTIONS_SHOWN', 'PACKAGES', 'latex', 'line_latex', 'panels', 'record_names', 'shown']
