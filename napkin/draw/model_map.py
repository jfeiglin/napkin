"""The map of the system (docs/draw.md): the things of a model, and what
the parts of each read of the other things, what they change and what material they move.

The map reads the semantic model (`model.scenario`), the structure of each run to know which parts the
run leaves out, and the picture (`style.toml`: `[layout] hide` and `[icon]`). Nothing in the model, the
engine or the studies reads it.

- A **card** is an entity line: an entity, an instance of a template, or a set of copies, whose
  copies share one card.
- A **part** is a part of a thing that acts or that has a value: an event (its condition, its delay,
  the chances of its outcomes and their changes), a flow, a formula, the start value, rate or bounds
  of a number, a profile's start value, a status and an allocation. Outputs and checks are left out:
  they report or test a run, and nothing in the run reads them.
- A **relation** is a value of another card that a part reads (`reads`, also an event's time), changes
  (`changes`: sets, adds to, takes from, or fires an event, or shares out a flow), or a stock of
  another card that it moves material into or out of (`moves`).
- An **arrow** stands for the relations of one kind between two cards that the map draws. Its head is
  the card that the relations affect: the reader of what it reads, and the owner of what is changed
  or moved.

By default, the cards stand in columns by role, in the order of `COLUMNS`. `system_map` gives the map,
and `map_payload` gives it with its words: the labels of its columns and parts, and for each run its
variant and the labels that the run changes.

`picture` gives what `napkin draw` draws (layout.py and svg.py read it, and never the model): each card
with its stocks, the pipes of its flows and the state machines of its named states, the arrows of each
kind between the cards, and the groups, for one run or for every run joined. The layout works out the
legend from what it draws.

The words of the map: who acts, in the words an event card shows (`ACTOR_NAMES`, `actor_name`), and
a text with the fields it names in braces filled in (`filled`). The published pages use these words
too, so they live here, below the pages.
"""

from __future__ import annotations

import re
from pathlib import Path

from .. import paths
from ..core import expr
from ..model import resolved
from ..model.ir import thaw
from ..model.runs import Runs
from ..model.semantic import Assign, Expression, Fire, Move, Ref, flat_entity, in_words, path_text
from ..model.views import actors
from . import style as styles
from .defaults import (
    ARROW_KINDS,
    DEFAULT_BUNDLE,
    DEFAULT_CARDS_PER_COLUMN,
    DEFAULT_LOOKS,
    DEFAULT_STOCKS,
    DEFAULT_TRIGGER_EVENTS,
    DEFAULT_TRIGGER_LINES,
    DEFAULT_TRIGGER_OPTIONS,
    READ_KINDS,
)

# Who acts, in the words an event card shows. An actor that names an entity shows the entity's label.
ACTOR_NAMES = {
    'adversary': 'Attacker',
    'responder': 'Responders',
    'operator': 'Operators',
    'environment': 'Conditions',
    'community': 'Residents',
    'clinician': 'Clinicians',
}
FIELD = re.compile(r'\{([A-Za-z_][A-Za-z0-9_.]*\.[A-Za-z_][A-Za-z0-9_]*)\}')
# A text names a text value of the entity that acts in braces: `{actor}`.
BRACES = re.compile(r'\{([A-Za-z_][A-Za-z0-9_]*)\}')

# The default order of the columns: who attacks, the systems that the attack reaches, the actors that
# a role names, the defenders, and the conditions and the people that the attack harms. A role that
# names an entity takes the place of None, in the order that the cards first show it.
COLUMNS = ('adversary', 'operator', None, 'responder', 'environment', 'clinician', 'community')
# The kinds of the relations of `Walk`.
KINDS = ('reads', 'changes', 'moves')
# The kinds of the arrows, their looks and the defaults of the stylesheet's settings (`defaults`).


def settings_of(sheet):
    """What the stylesheet chooses for the layout and the SVG (D-51, D-52), with the defaults: the
    look of each kind of arrow (`looks`), the kinds that bundle (`bundle`), the most stock rows of a
    card (`stocks`), the most cards of a column (`cards_per_column`) and the width of a card
    (`card_width`, None for the layout's own)."""
    looks = dict(DEFAULT_LOOKS)
    looks.update(dict(getattr(sheet, 'looks', ()) or ()))
    bundle = getattr(sheet, 'bundle', None)
    return {
        'looks': {kind: looks[kind] for kind in ARROW_KINDS},
        'bundle': [kind for kind in ARROW_KINDS if kind in (DEFAULT_BUNDLE if bundle is None else bundle)],
        'stocks': getattr(sheet, 'stocks', None) or DEFAULT_STOCKS,
        'cards_per_column': getattr(sheet, 'cards_per_column', None) or DEFAULT_CARDS_PER_COLUMN,
        'card_width': getattr(sheet, 'card_width', None),
    }


def filled(text, texts):
    """A card's text with the fields it names in braces, `{entity.field}`, as one run's `texts` read."""
    return FIELD.sub(lambda m: str(texts.get(m.group(1), m.group(0))), text)


def actor_name(actor, labels):
    """Who acts, in the words of the event cards: the name on the pages of the entity that the actor
    names (`labels`), else the word for its role (`ACTOR_NAMES`), else the actor in words."""
    return labels.get(actor) or ACTOR_NAMES.get(actor, actor.replace('_', ' ').capitalize())


def references(node):
    """The names that an expression reads, in the order of its typed nodes (`Expression.node`,
    `napkin/model/resolved.py`): each `Ref` and `EventRef`, and each `Ref` that a `sum()` adds."""
    if isinstance(node, (resolved.Ref, resolved.EventRef)):
        yield node
    elif isinstance(node, resolved.Terms):
        for ref in node.refs:
            yield from references(ref)
    elif isinstance(node, expr.Node):
        for child in node.children:
            yield from references(child)


def _node(expression):
    """The typed nodes of an `Expression` of the semantic model; the value of a line and the amount
    of a move are their own typed nodes."""
    return expression.node if isinstance(expression, Expression) else expression


def plain_text(doc):
    """The text of a part as its first card shows it: a text, or the first of a list (one for each
    time)."""
    doc = thaw(doc)
    if isinstance(doc, list):
        doc = doc[0] if doc else None
    return doc if isinstance(doc, str) and doc else None


def arrow_kind(relation):
    """The kind of the arrow that a relation of `Walk` belongs to (`ARROW_KINDS`)."""
    how = relation.get('how')
    if relation['kind'] == 'changes' and how == 'runs':
        return 'fires'
    if relation['kind'] == 'reads' and how == 'time':
        return 'follows'
    return relation['kind']


# The words of the relations of a "changes" arrow, which its tooltip shows.
CHANGE_WORDS = ('sets', 'adds', 'takes', 'shares')


def operator_word(line):
    """How an assignment changes its target: `sets`, `adds` (`+=`) or `takes` (`-=`)."""
    if not line.augmented:
        return 'sets'
    return 'takes' if line.operator == 'Sub' else 'adds'


# ---- the names and texts of a model ----------------------------------------------------------------


def _flat(model):
    """{entity of the file: its name in the structure}: its own, and `set_k` for copy k of a set."""
    return {name: flat for flat, name in model.entities.items()}


def _braced(text, owner, flat):
    """A text whose braces name text values of the entity `owner`, `{name}`, with each brace as
    `{entity.name}`, the form that `filled` fills for each run."""
    return BRACES.sub(lambda m: '{' + flat[owner] + '.' + m.group(1) + '}', text)


def _field_name(key, flat):
    """The structure's name of `entity.field` of the file, or None for an entity it does not have."""
    entity, _, member = key.rpartition('.')
    return f'{flat[entity]}.{member}' if entity in flat else None


def _texts(model, flat):
    """{run: {entity.value: text}}: each text value, as the run's profiles set it (the run
    resolution's texts)."""
    runs = Runs.from_table(model.run_table)
    out = {}
    for run, info in model.runs.items():
        texts = runs.values_of(info['options']).texts
        out[run] = {_field_name(key, flat): text for key, text in texts.items()}
    return out


def texts_of(model, run=None):
    """{entity.value: text} of each text value, by the structure's names: the file's own, and with
    `run` the texts that the run's options set. `filled` fills a label's braces with them."""
    flat = _flat(model)
    texts = {
        f'{flat[entity.name]}.{value.name}': thaw(value.value)
        for entity in model.scenario.entities
        for value in entity.values
        if value.kind == 'text'
    }
    if run is not None:
        found = Runs.from_table(model.run_table).values_of(model.runs[run]['options']).texts
        texts.update({_field_name(key, flat): text for key, text in found.items()})
    return texts


def label_of(text, entity, name, flat, texts):
    """A label: the text of a part of `entity` (its first, for a list), with the texts of `texts` in its
    braces (`texts_of`), else `name` in words."""
    found = plain_text(text)
    return filled(_braced(found, entity, flat), texts) if found else in_words(name)


def _entity_labels(model, flat):
    """{entity: its name on the pages}, as the builder writes it in the structure: the file's
    entities in its order, then the main's (`simulate`)."""
    entities = next(iter(model.whole.values())).entities
    own = [flat[entity.name] for entity in model.scenario.entities]
    return {entity: entities[entity].label for entity in [*own, *(e for e in entities if e not in own)]}


# ---- the parts and relations -----------------------------------------------------------------------


class Walk:
    """The parts and relations of one model, from its semantic model."""

    def __init__(self, model):
        self.model = model
        self.scenario = model.scenario
        self.flat = _flat(model)
        self.lines = thaw(self.model.lines)
        self.card_of = {entity.name: entity.entry for entity in self.scenario.entities}
        self.entities = {entity.name: entity for entity in self.scenario.entities}
        self.parts = []  # {kind, node, name, place, line, text}
        self.tests = []  # for each part: how a structure holds it, (section, key) or a special test
        self.found = {}  # (node, kind, name) -> part index: the copies of a set share their parts
        self.relations = []
        self.seen = set()
        self.values = {}
        self.runs = []  # (caller part, (entity, event)): the events that each part fires

    # ---- parts ------------------------------------------------------------------------------------

    def line(self, where, default=None):
        return self.lines.get(tuple(where), default) if where else default

    def part(self, kind, entity, name, where, text=None, test=None):
        """The index of the part `name` of `entity`'s card, made once for the copies of a set."""
        node = self.card_of[entity]
        key = (node, kind, name)
        index = self.found.get(key)
        if index is None:
            index = self.found[key] = len(self.parts)
            self.parts.append(
                {
                    'kind': kind,
                    'node': node,
                    'name': name,
                    'place': path_text(where),
                    'line': self.line(where),
                    'text': _braced(text, entity, self.flat) if text else None,
                }
            )
            self.tests.append([])
        if test is not None:
            self.tests[index].append(test)
        return index

    def relate(self, index, kind, other, value, where=None, how=None, ending=None):
        """A relation of part `index` to the value `value` of entity `other`, which another card owns."""
        by, of = self.parts[index]['node'], self.card_of.get(other)
        if of is None or of == by:
            return
        relation = {'kind': kind, 'by': by, 'of': of, 'value': value, 'part': index}
        if how is not None:
            relation['how'] = how
        if ending is not None:
            relation['ending'] = ending
        key = tuple(sorted(relation.items()))
        if key in self.seen:
            return
        self.seen.add(key)
        relation['line'] = self.line(where, self.parts[index]['line'])
        self.relations.append(relation)

    def value_key(self, entity, member, kind=None, part=None):
        """The key of a value on the map, `card.member`: a copy's value is the value of its set."""
        key = f'{self.card_of[entity]}.{member}'
        if key not in self.values:
            found = self.entities[entity].value(member)
            item = {'node': self.card_of[entity], 'kind': kind or (found.kind if found is not None else None)}
            if part is not None:
                item['part'] = part
            elif found is not None:
                item['label'] = plain_text(found.text)
            self.values[key] = item
        return key

    def reads(self, index, expression, where=None, skip=None):
        """The relations of the names that an expression reads."""
        if expression is None:
            return
        at = where if where is not None else getattr(expression, 'where', None)
        for ref in references(_node(expression)):
            if isinstance(ref, resolved.Ref):
                if ref.entity is None or ref.entity not in self.entities or (ref.entity, ref.member) == skip:
                    continue
                self.relate(index, 'reads', ref.entity, self.value_key(ref.entity, ref.member), at)
            else:
                owner, value = self.event_value(ref)
                if owner is not None:
                    self.relate(index, 'reads', owner, value, at, how='time', ending=ref.ending)

    def event_value(self, ref):
        """(the entity, the value key) of an event that `since()` or `count()` reads."""
        entity, _, event = ref.key.rpartition('.')
        if entity not in self.entities:
            return None, None
        return entity, self.event_key(entity, event)

    def event_key(self, entity, event):
        key = f'{self.card_of[entity]}.{event}'
        if key not in self.values:
            self.values[key] = {'node': self.card_of[entity], 'kind': 'event'}
        return key

    def change_lines(self, index, change):
        """The relations of the lines of a change: what each line sets, moves and runs, and what it
        reads."""
        for line in change.lines:
            if isinstance(line, Move):
                self.reads(index, line.amount, line.where)
                for (_, end), how in zip(line.ends, ('from', 'to')):
                    if isinstance(end, Ref) and end.entity in self.entities:
                        key = self.value_key(end.entity, end.member)
                        self.relate(index, 'moves', end.entity, key, line.where, how=how)
            elif isinstance(line, Fire):
                for target in line.targets if isinstance(line.targets, tuple) else ():
                    self.runs.append((index, target, line.where))
            else:
                target = line.target if isinstance(line.target, Ref) else None
                skip = (target.entity, target.member) if target is not None and line.augmented else None
                self.reads(index, line.value, line.where, skip=skip)
                if target is not None and target.entity in self.entities:
                    key = self.value_key(target.entity, target.member)
                    self.relate(index, 'changes', target.entity, key, line.where, how=operator_word(line))

    # ---- the model --------------------------------------------------------------------------------

    def walk(self):
        for entity in self.scenario.entities:
            self.entity(entity)
        for index, (entity, event), where in self.runs:
            if entity in self.entities:
                key = self.event_key(entity, event)
                self.relate(index, 'changes', entity, key, where, how='runs')
        # The values that a relation names: a part's reads of its own card name none.
        named = {relation['value'] for relation in self.relations}
        self.values = {key: item for key, item in self.values.items() if key in named}
        return self

    def entity(self, entity):
        e, card = entity.name, entity.entry
        flat = flat_entity(e)
        for value in entity.values:
            key = f'{flat}.{value.name}'
            if value.kind == 'formula' and value.formula is not None:
                index = self.part(
                    'formula',
                    e,
                    f'{card}.{value.name}',
                    value.where,
                    plain_text(value.text),
                    ('formula', key),
                )
                self.reads(index, value.formula)
            if value.kind in ('stock', 'tally', 'state'):
                test = ('quantity', key)
                for kind, expression in (
                    ('value', value.initial),
                    ('rate', value.rate.expression if value.rate is not None else None),
                    ('min', value.minimum.expression if value.minimum is not None else None),
                    ('max', value.maximum.expression if value.maximum is not None else None),
                ):
                    if expression is not None and any(True for _ in references(_node(expression))):
                        name = f'{card}.{value.name}' + ('' if kind == 'value' else f' {kind}')
                        index = self.part(kind, e, name, expression.where, plain_text(value.text), test)
                        self.reads(index, expression)
            for where, _, arguments in value.arguments:
                index = self.part(
                    'distribution',
                    e,
                    f'{card}.{value.name}',
                    where,
                    plain_text(value.text),
                    ('parameter', key),
                )
                for _, expression in arguments:
                    self.reads(index, expression)
        for setting in entity.settings:
            if setting.start is not None and any(True for _ in references(_node(setting.start))):
                found = entity.value(setting.target)
                index = self.part(
                    'option',
                    e,
                    f'{setting.profile}: {card}.{setting.target}',
                    setting.where,
                    plain_text(found.text) if found is not None else None,
                    ('option', setting.profile, f'{flat}.{setting.target}'),
                )
                self.reads(index, setting.start)
        if entity.status is not None:
            index = self.part(
                'status', e, f'{card}.status', entity.status.where, None, ('label', f'{flat}.health')
            )
            for case in entity.status.cases:
                self.reads(index, case.condition)
        for flow in entity.flows:
            index = self.part(
                'flow',
                e,
                f'{card}.{flow.name}',
                flow.where,
                plain_text(flow.text),
                ('flow', f'{flat}.{flow.name}'),
            )
            self.values.setdefault(f'{card}.{flow.name}', {'node': card, 'kind': 'flow', 'part': index})
            self.reads(index, flow.rate)
            self.reads(index, flow.condition)
            for pair in flow.pairs:
                self.reads(index, pair.rate)
                for how, end in pair.ends:
                    if isinstance(end, Ref) and end.entity in self.entities:
                        key = self.value_key(end.entity, end.member)
                        self.relate(index, 'moves', end.entity, key, pair.where, how=how)
        for allocation in entity.allocations:
            index = self.part(
                'share',
                e,
                f'{card}.{allocation.name}',
                allocation.where,
                None,
                ('allocation', f'{flat}.{allocation.name}'),
            )
            self.reads(index, allocation.limit)
            stock = allocation.stock
            if isinstance(stock, Ref) and stock.entity in self.entities:
                self.relate(
                    index,
                    'reads',
                    stock.entity,
                    self.value_key(stock.entity, stock.member),
                    allocation.stock_where,
                )
            for _, owner, name, where in allocation.serve or ():
                if isinstance(owner, str) and owner in self.entities:
                    key = f'{self.card_of[owner]}.{name}'
                    self.values.setdefault(key, {'node': self.card_of[owner], 'kind': 'flow'})
                    self.relate(index, 'changes', owner, key, where, how='shares')
        for event in entity.events:
            index = self.part(
                'event',
                e,
                f'{card}.{event.name}',
                event.where,
                plain_text(self.event_text(e, event)),
                ('rule', f'{flat}.{event.name}'),
            )
            item = self.values.setdefault(f'{card}.{event.name}', {'node': card, 'kind': 'event'})
            item['part'] = index
            self.reads(index, event.when)
            self.reads(index, event.after)
            for item in (*event.each, event.keep):
                self.reads(index, item)
            for outcome in event.outcomes:
                if outcome.chance not in (None, 'else'):
                    self.reads(index, outcome.chance)
                if outcome.available is not None:
                    self.reads(index, outcome.available)
                self.change_lines(index, outcome)

    @staticmethod
    def event_text(entity, event):
        """An event's text, or the text of its first outcome that has one."""
        if event.text is not None:
            return event.text
        return next((outcome.text for outcome in event.outcomes if outcome.text is not None), None)

    # ---- the runs ---------------------------------------------------------------------------------

    def present(self, structure, starts):
        """The indices of the parts that a structure holds."""
        sections = {
            'rule': 'rules',
            'formula': 'computed',
            'quantity': 'quantities',
            'parameter': 'parameters',
            'label': 'labels',
            'flow': 'flows',
            'allocation': 'allocation',
        }
        held = set()
        entities = structure.entities
        for index, tests in enumerate(self.tests):
            for test in tests:
                kind, *rest = test
                if kind == 'option':
                    profile, key = rest
                    ok = profile in starts and (key in structure.quantities or key in structure.modes)
                elif kind == 'formula':
                    # A formula that the builder writes into its readers is held while its entity is.
                    key = rest[0]
                    ok = key in structure.computed or key.rpartition('.')[0] in entities
                elif kind == 'quantity':
                    key = rest[0]
                    ok = key in structure.quantities or key in structure.modes
                elif kind == 'flow':
                    # A flow from outside into a tally is the tally's rate.
                    key = rest[0]
                    ok = (
                        key in structure.flows
                        or f'{key}.0' in structure.flows
                        or any(key in rate.flows for rate in structure.rates.values())
                    )
                else:
                    ok = rest[0] in structure.section(sections[kind])
                if ok:
                    held.add(index)
                    break
        return held


# ---- the map ---------------------------------------------------------------------------------------


def cards(model, style):
    """The cards: one for each entity line, in the order of the file, with its column and row when the
    map draws it, and the icon that the picture `style` gives it."""
    lines = styles.entity_lines(model)
    drawn = styles.drawn(style, model)
    icons = styles.icon_of(style, model)
    members = {}
    statuses = set()
    for entity in model.scenario.entities:
        members.setdefault(entity.entry, []).append(flat_entity(entity.name))
        if entity.status is not None:
            statuses.add(entity.entry)
    roles = {entry: thaw(entity.role) or 'environment' for entry, entity in lines.items()}
    named = [roles[entry] for entry in drawn if roles[entry] not in COLUMNS]
    order = []
    for role in COLUMNS:
        order += list(dict.fromkeys(named)) if role is None else [role]
    columns = [role for role in order if any(roles[entry] == role for entry in drawn)]
    rows = {}
    nodes = []
    for entry, entity in lines.items():
        node = {
            'id': entry,
            'title': card_title(entity),
            'role': roles[entry],
            'icon': icons[entry],
            'drawn': entry in drawn,
            'status': entry in statuses,
            'members': members[entry],
            'copies': len(members[entry]) if entity.copy is not None else None,
        }
        if entry in drawn:
            column = columns.index(roles[entry])
            node['column'] = column
            node['row'] = rows.get(column, 0)
            rows[column] = node['row'] + 1
        nodes.append(node)
    order_of = {entry: i for i, entry in enumerate(drawn)}
    nodes.sort(key=lambda node: (not node['drawn'], order_of.get(node['id'], 0)))
    return columns, nodes


def card_title(entity):
    """The title of an entity line: its entity's title, and for a set of copies the title of its line,
    or its name in words."""
    title = thaw(entity.title)
    if entity.copy is not None and title == f'{in_words(entity.entry)} {entity.copy}':
        return in_words(entity.entry)
    return title


def system_map(model, style=None):
    """The map of a model (docs/draw.md): its columns (`role`), its
    cards, its parts, the values that its relations name, its relations, and a variant for each
    structure of the model: the parts that the structure leaves out (`lacks`) and the arrows. `style`
    is its picture (`style.Style`), by default the model's own (`style.toml` beside its file)."""
    columns, nodes = cards(model, styles.of(model) if style is None else style)
    walk = Walk(model).walk()
    drawn = [node['id'] for node in nodes if node['drawn']]
    rank = {entry: i for i, entry in enumerate(drawn)}
    variants = []
    for starts, frozen in model.structures.items():
        held = walk.present(frozen, starts)
        lacks = [index for index in range(len(walk.parts)) if index not in held]
        counts = {}
        for relation in walk.relations:
            if relation['part'] not in held or relation['by'] not in rank or relation['of'] not in rank:
                continue
            ends = (
                (relation['of'], relation['by'])
                if relation['kind'] == 'reads'
                else (relation['by'], relation['of'])
            )
            counts.setdefault((*ends, relation['kind']), set()).add(relation['value'])
        arrows = [
            {'from': source, 'to': target, 'kind': kind, 'values': len(values)}
            for (source, target, kind), values in sorted(
                counts.items(), key=lambda item: (rank[item[0][0]], rank[item[0][1]], KINDS.index(item[0][2]))
            )
        ]
        variants.append({'starts': list(starts), 'lacks': lacks, 'arrows': arrows})
    return {
        'columns': [{'role': role} for role in columns],
        'nodes': nodes,
        'parts': walk.parts,
        'values': walk.values,
        'relations': walk.relations,
        'variants': variants,
    }


def map_payload(model, style=None):
    """The map of a model (`system_map`) with its words: the label of each column, the words of who
    acts (`actor_name`), and the label of each part, its text with the model's own text values in its
    braces; and for each run, its variant and the labels of the parts whose texts its profiles change
    (`labels`, by the index of the part). `style` is the map's picture, by default the model's own."""
    found = system_map(model, style)
    flat = _flat(model)
    labels = _entity_labels(model, flat)
    texts = _texts(model, flat)
    own = {
        f'{flat[entity.name]}.{value.name}': thaw(value.value)
        for entity in model.scenario.entities
        for value in entity.values
        if value.kind == 'text'
    }
    for column in found['columns']:
        column['label'] = actor_name(column['role'], labels)
    braced = [part.pop('text') for part in found['parts']]
    for part, text in zip(found['parts'], braced):
        part['label'] = filled(text, own) if text else None
    runs = {}
    for run in model.runs:
        changed = {}
        for index, (part, text) in enumerate(zip(found['parts'], braced)):
            label = filled(text, texts[run]) if text else None
            if label != part['label']:
                changed[str(index)] = label
        runs[run] = {'variant': variant_of(model, run), 'labels': changed}
    return found, runs


def variant_of(model, run):
    """The index of the map's variant of a run: the structure of its start-state options."""
    return list(model.structures).index(model.runs[run]['starts'])


# ---- the picture: what `napkin draw` draws ---------------------------------------------------------

# The roles that a card names; a role that names a thing, and no role, are None.
ROLES = ('adversary', 'operator', 'responder', 'environment', 'clinician', 'community')
STOCK_KINDS = ('stock', 'tally')


def picture(model, style=None, run=None):
    """What `napkin draw` draws of a model: a plain dict that JSON writes, the same for the same model,
    picture and run. `style` is the picture (`style.Style`), by default the model's own (`style.of`).
    With `run`, the parts that the structure of the run leaves out are absent (as `system_map`'s
    `lacks`), and the run's texts fill the labels. Without it, the picture joins the pictures of every
    run: a part is drawn when it can act in one run or more. A `run` that the model does not have raises
    ValueError.

    - `name`: the scenario, or `scenario:variant`; `title`: the scenario's title; `run`; `direction`.
    - `facts` (D-59): what the subtitle says. `run`: None, or `{name, label, options, versus}` for `run`,
      with its options and the label of the run that it is compared with (`versus`) or None; `runs`:
      the number of runs that the picture joins (1 with `run`); `horizon`: the horizon as written, or
      None; `hidden`: the titles of the things (a template's name) that `[layout] hide` leaves out,
      sorted.
    - `settings` (D-51, D-52): what the stylesheet chooses for the layout and the SVG (`settings_of`).
    - `cards`: each entity line that the picture draws, in the order of the file (`_Drawing.card`).
    - `arrows`: one for each two cards and kind (`ARROW_KINDS`, `arrow_kind`),
      `{from, to, kind, count, values, how}`, sorted by `(from, to, kind)`. `values` are the values of
      `to` that the parts of `from` change, fire or move, or the values and events of `from` that the
      parts of `to` read or follow (the relations of `Walk`), sorted. `count` is the number of them that
      the run holds; joined, it is the largest of the runs. `how` holds the words of a "changes" arrow's
      relations (`CHANGE_WORDS`: sets, adds, takes, shares), sorted; it is empty for the other kinds.
    - `groups`: each group of `[group]` that holds a card, `{label, members}`, its members in the order
      of the cards.
    - `panels` (D-53, D-55): the Equations, Symbols and References panels under the map
      (`panels.panels`), or None when `[equations] things` names nothing.

    A thing that `[layout] hide` hides is absent, with each arrow and transition of its parts. Each
    name of the picture is one that the model declares: a card is an entity line, a stock and a named
    state `card.var`, a flow and an event `card.name`, and a state one of its var's states."""
    sheet = styles.of(model) if style is None else style
    if run is not None and run not in model.runs:
        raise ValueError(f'{run} is not a run of the model; its runs are {", ".join(model.runs)}')
    # panels.py reads the names of this module, so it comes in here.
    from .panels import panels

    drawing = _Drawing(model, sheet, run)
    cards = [drawing.card(entry) for entry in drawing.shown]
    arrows = [
        {
            'from': source,
            'to': target,
            'kind': kind,
            'count': item['count'],
            'values': sorted(item['values']),
            'how': sorted(item['how']),
        }
        for (source, target, kind), item in sorted(drawing.arrows.items())
    ]
    return {
        'name': _name_of(model),
        'title': thaw(model.scenario.title),
        'run': run,
        'direction': sheet.direction,
        'facts': drawing.facts(),
        'settings': settings_of(sheet),
        'cards': cards,
        'arrows': arrows,
        'groups': [
            {'label': label, 'members': names} for label, names in styles.groups_of(sheet, model) if names
        ],
        'panels': panels(model, sheet, run, cards),
    }


def _name_of(model):
    """The name of a model's package, or `package:variant` for a variant (`paths.names_of`)."""
    scenario, variant = paths.names_of(model.origin)
    return scenario if variant is None else f'{scenario}:{variant}'


class _Drawing:
    """The parts of a picture of one model, for one run or for every run joined.

    The structures of the runs give what can act, joined: the parts (`held`, the indices of the parts
    of `walk`), the stocks, tallies and named states (`quantities`, `modes`, by their names in the
    structure) and the arrows between the cards that the picture draws (`arrows`: {(from, to, kind):
    {count, values}}). A run has the one structure of its start values."""

    def __init__(self, model, sheet, run):
        self.model, self.sheet, self.run = model, sheet, run
        self.walk = Walk(model).walk()
        self.lines = styles.entity_lines(model)
        self.shown = styles.drawn(sheet, model)
        # The things that decide: each actor (`napkin.actors`) with a choice.
        self.deciders = {found['name'] for found in actors(model) if found['choices']}
        self.members = {}
        for entity in model.scenario.entities:
            self.members.setdefault(entity.entry, []).append(entity)
        self.held, self.quantities, self.modes, self.arrows = set(), set(), set(), {}
        starts = dict.fromkeys(
            model.runs[name]['starts'] for name in ([run] if run is not None else model.runs)
        )
        self.structures = [model.structures[key] for key in starts]
        for key, structure in zip(starts, self.structures):
            self.join(key, structure)
        self.flat = _flat(model)
        self.texts = texts_of(model, run)
        self.transitions = _transitions(model, self.walk, self.held, set(self.shown))
        self.places = styles.place_of(sheet, model)
        self.machine_places = styles.state_places(sheet, model)
        self.stock_orders = styles.stock_orders(sheet, model)
        self.icons = styles.icon_of(sheet, model)
        self.levels = styles.trigger_levels(sheet, model)
        start = model.scenario.start
        self.starter = start.entity if start is not None else None
        self.package = paths.package_of(model.origin)

    def facts(self):
        """What the subtitle of the picture says (D-59): the run, the number of runs joined, the
        horizon and the names that `[layout] hide` leaves out."""
        model, run = self.model, self.run
        horizon = model.scenario.horizon
        found = {
            'run': None,
            'runs': 1 if run is not None else len(model.runs),
            'horizon': None if horizon is None else str(thaw(horizon.written)),
            'hidden': sorted(self.hidden_title(name) for name in self.sheet.hide),
        }
        if run is not None:
            item = model.runs[run]
            versus = item.get('comparison_of')
            found['run'] = {
                'name': run,
                'label': str(item['name']),
                'options': [str(option) for option in item['options']],
                'versus': None if versus is None else str(model.runs[versus]['name']),
            }
        return found

    def hidden_title(self, name):
        """The words of a name that `[layout] hide` gives: the title of a thing, or a template's name."""
        line = self.lines.get(name)
        return name if line is None else card_title(line)

    def file_of(self, entity):
        """The file that writes the line of `entity`, from the folder of its package, with `/`."""
        found = self.model.files.get((entity.entry,)) or self.model.files.get(entity.where[:1])
        found = found or self.model.origin
        if found is None:
            return None
        path = Path(found)
        try:
            return path.relative_to(self.package).as_posix() if self.package is not None else path.name
        except ValueError:
            return path.name

    def join(self, starts, structure):
        """Adds what one structure holds: its parts that can act, its stocks and named states, and its
        arrows, with the number of values of each."""
        held = self.walk.present(structure, starts)
        self.held |= held
        self.quantities.update(structure.quantities)
        self.modes.update(structure.modes)
        shown = set(self.shown)
        counts, words = {}, {}
        for relation in self.walk.relations:
            if relation['part'] not in held or relation['by'] not in shown or relation['of'] not in shown:
                continue
            kind = arrow_kind(relation)
            ends = (
                (relation['of'], relation['by']) if kind in READ_KINDS else (relation['by'], relation['of'])
            )
            counts.setdefault((*ends, kind), set()).add(relation['value'])
            if kind == 'changes' and relation.get('how') in CHANGE_WORDS:
                words.setdefault((*ends, kind), set()).add(relation['how'])
        for key, values in counts.items():
            item = self.arrows.setdefault(key, {'count': 0, 'values': set(), 'how': set()})
            item['count'] = max(item['count'], len(values))
            item['values'] |= values
            item['how'] |= words.get(key, set())

    def keeps(self, names, entry, member):
        """Whether the structures keep the value `member` of the card `entry`: of one of its copies."""
        return any(f'{flat_entity(entity.name)}.{member}' in names for entity in self.members[entry])

    def words(self, text, entity, name):
        """A label: the text of a part, with the texts of the run in its braces, else its name in
        words (`label_of`)."""
        return label_of(text, entity, name, self.flat, self.texts)

    def card(self, entry):
        """A card of the picture: `id`, the entity line; `title`; `role`, one of `ROLES` or None;
        `icon`; `template`; `copies`, the number of copies of a set, else 1; `actor`, whether it is an
        actor with a choice (`napkin.actors`); `starts`, whether its thing makes the start event of the
        run; `file`, the file that writes its line, from the folder of the package; `place`,
        `{column, row}` from `[place]` or None; its stocks, pipes and state machines; `stock_order`, the
        rows that `[stocks]` gives it (`stock_order`, D-52); `hidden_stocks`, always 0 (the layout
        collapses stocks); and `triggers`, what the card shows of its events (`triggers`, D-56)."""
        first = self.lines[entry]
        role = thaw(first.role)
        place = self.places.get(entry)
        stocks = self.stocks(entry, first)
        keys = {stock['key'] for stock in stocks}
        return {
            'id': entry,
            'title': card_title(first),
            'role': role if role in ROLES else None,
            'icon': self.icons[entry],
            'template': first.template,
            'copies': len(self.members[entry]) if first.copy is not None else 1,
            'actor': first.name in self.deciders,
            'starts': self.starter is not None and self.starter in {e.name for e in self.members[entry]},
            'file': self.file_of(first),
            'place': None if place is None else {'column': place[0], 'row': place[1]},
            'stocks': stocks,
            'stock_order': self.stock_order(entry, keys),
            'hidden_stocks': 0,
            'pipes': self.pipes(entry, first, keys),
            'machines': self.machines(entry, first),
            'triggers': self.triggers(entry, first),
        }

    def stock_order(self, entry, keys):
        """The rows that `[stocks]` gives the card (D-52), its own list else its template's: the keys of
        the stocks and tallies of the list that the card has (`keys`), in the order of the list. None
        without a list: the layout chooses the rows. The layout shows the first `[layout] stocks` of them,
        the stocks above the tallies, and the "+n" row stands for the others."""
        listed = self.stock_orders.get(entry)
        if listed is None:
            return None
        return [key for key in (f'{entry}.{name}' for name in listed) if key in keys]

    def stocks(self, entry, first):
        """The stocks and tallies of a card that the structures keep, in the order of the file:
        `{key, name, kind}`."""
        return [
            {
                'key': f'{entry}.{value.name}',
                'name': self.words(value.text, first.name, value.name),
                'kind': value.kind,
            }
            for value in first.values
            if value.kind in STOCK_KINDS and self.keeps(self.quantities, entry, value.name)
        ]

    def pipes(self, entry, first, stocks):
        """The pipes of a card, `{key, flows, from, to, label}`: for each two ends, the flows of the card
        that can act and that move material between two of its stocks (`stocks`, their keys), or between
        one of them and outside the model (an end None), in the order of the file. `key` is `from->to`,
        with nothing for outside. A flow with an end on another card moves its material: an arrow of
        kind `moves`, and no pipe."""
        found = {}
        for flow in first.flows:
            name = f'{entry}.{flow.name}'
            if self.walk.found[(entry, 'flow', name)] not in self.held:
                continue
            for pair in flow.pairs:
                ends = {}
                for how, end in pair.ends:
                    if not (isinstance(end, Ref) and self.walk.card_of.get(end.entity) == entry):
                        ends = None
                        break
                    ends[how] = f'{entry}.{end.member}'
                if not ends or any(key not in stocks for key in ends.values()):
                    continue
                flows = found.setdefault((ends.get('from'), ends.get('to')), {})
                flows.setdefault(name, self.words(flow.text, first.name, flow.name))
        return [
            {
                'key': f'{source or ""}->{target or ""}',
                'flows': list(flows),
                'from': source,
                'to': target,
                'label': _joined(flows.values()),
            }
            for (source, target), flows in found.items()
        ]

    def machines(self, entry, first):
        """The state machines of a card, sorted by var: for each named state that the structures keep,
        `{var, name, states, initial, starts_by, transitions, place}`. `states` are in the order of its
        type, `starts_by` holds `{option, state}` for each option that sets its start (D-59), in the order
        of the file, `transitions` (`_transitions`) are sorted by (event, state), and `place` is the one
        of `[state]`, else `inside`."""
        named = styles.named_states(first)
        found = [
            {
                'var': f'{entry}.{value.name}',
                'name': self.words(value.text, first.name, value.name),
                'states': list(styles.states_of(value)),
                'initial': self.initial(first, value),
                'starts_by': [
                    {'option': setting.profile, 'state': setting.value}
                    for setting in first.settings
                    if setting.target == value.name and setting.value in styles.states_of(value)
                ],
                'transitions': [
                    {'from': item['from'], 'to': to, 'event': event, 'by': item['by']}
                    for (event, to), item in sorted(self.transitions.get(f'{entry}.{value.name}', {}).items())
                ],
                'place': self.machine_places.get(entry, {}).get(value.name, styles.STATE_PLACES[0]),
            }
            for value in first.values
            if value.name in named and self.keeps(self.modes, entry, value.name)
        ]
        return sorted(found, key=lambda machine: machine['var'])

    def triggers(self, entry, first):
        """What the card shows of its events (D-56), or None for a card that `[triggers]` does not name:
        `{level, lines, events, more}`.

        - `level`: one of `TRIGGER_LEVELS` (`count`, `names`, `rules`, `hover`).
        - `lines`: the most rows of the text of an event (`[triggers] lines`); the layout uses it at
          `rules`.
        - `events`: each event of the card that can act, in the order of the file, `{event, name, text,
          full, label, rule}`. `event` is `card.event`; `name`, the event's name in words; `text`, what
          the card shows before the layout shortens it: the name at `names`, the line at `rules`, and
          None at `count` and `hover` and for each event after the first `[triggers] events`; `full`,
          the whole line (`triggers.Line.full`) for the tooltip; `label`, the event's text with the
          run's texts in its braces, or None; `rule`, its condition as the file writes it, or None.
          With `[triggers] options = false`, `text` and `full` leave out the options that switch the
          event.
        - `more`: the number of events without a text at `names` and `rules` (a row "+n more"), else
          0."""
        level = self.levels.get(entry)
        if level is None:
            return None
        # triggers.py reads the names of this module, so it comes in here.
        from .triggers import card_lines

        sheet = self.sheet
        limit = sheet.trigger_events or DEFAULT_TRIGGER_EVENTS
        options = DEFAULT_TRIGGER_OPTIONS if sheet.trigger_options is None else sheet.trigger_options
        rows = level in ('names', 'rules')
        events = []
        for line in card_lines(self.model, first):
            key = f'{entry}.{line.event}'
            if self.walk.found[(entry, 'event', key)] not in self.held:
                continue
            full = line.joined(options)
            shown = rows and len(events) < limit
            label = line.label and filled(_braced(line.label, first.name, self.flat), self.texts)
            events.append(
                {
                    'event': key,
                    'name': line.name,
                    'text': (line.name if level == 'names' else full) if shown else None,
                    'full': full,
                    'label': label or None,
                    'rule': line.rule,
                }
            )
        return {
            'level': level,
            'lines': sheet.trigger_lines or DEFAULT_TRIGGER_LINES,
            'events': events,
            'more': sum(event['text'] is None for event in events) if rows else 0,
        }

    def initial(self, entity, value):
        """The start value of a named state: the one of the structure of the runs when they have one (an
        option can set it), else the model's, as the file writes it; None for a start value that is not
        one of its states."""
        found = thaw(value.value)
        if len(self.structures) == 1:
            mode = self.structures[0].modes.get(f'{flat_entity(entity.name)}.{value.name}')
            found = found if mode is None else mode.initial
        return found if found in styles.states_of(value) else None


def _joined(labels):
    """The labels of the flows of one pipe, each once, in order: sentences one after the other, and names
    with a semicolon between them."""
    labels = list(dict.fromkeys(labels))
    return (' ' if all(label.endswith(('.', '!', '?')) for label in labels) else '; ').join(labels)


def _transitions(model, walk, held, shown):
    """{card.var: {(event, state): {from, by}}}: the transitions of each named state of a card in
    `shown`. Each line of an event that can act (`held`), of a card in `shown`, that sets the state is a
    transition for each state that its value can give (`_targets`) from the states in which the event can
    happen (`_narrowed`: its `when`, and the chance and condition of the outcome), the state that it gives
    left out. `from` is None when nothing narrows the states, and a transition that only keeps the
    state is absent. The lines of one event that give one state join their states."""
    found = {}
    for entity in model.scenario.entities:
        by = walk.card_of[entity.name]
        if by not in shown:
            continue
        for event in entity.events:
            name = f'{by}.{event.name}'
            if walk.found[(by, 'event', name)] not in held:
                continue
            for outcome in event.outcomes:
                chance = outcome.chance if outcome.chance != 'else' else None
                for line in outcome.lines:
                    target = line.target if isinstance(line, Assign) and not line.augmented else None
                    owner = walk.entities.get(target.entity) if isinstance(target, Ref) else None
                    card = walk.card_of.get(target.entity) if owner is not None else None
                    if card not in shown or target.member not in styles.named_states(owner):
                        continue
                    states = styles.states_of(owner.value(target.member))
                    sources = _narrowed((event.when, outcome.available, chance), target, states)
                    for to in _targets(line.value, states, walk.entities):
                        given = None if sources is None else [s for s in states if s in sources and s != to]
                        if given == []:
                            continue
                        item = found.setdefault(f'{card}.{target.member}', {}).setdefault(
                            (name, to), {'from': given, 'by': by}
                        )
                        if item['from'] is not None:
                            joined = None if given is None else set(item['from']) | set(given)
                            item['from'] = None if joined is None else [s for s in states if s in joined]
    return found


def _narrowed(conditions, ref, states):
    """The states of the named state `ref` in which every condition can hold (`_states_where`), or None
    when no condition narrows them. A condition is an `Expression`, None, or a chance that is a number."""
    found = None
    for condition in conditions:
        node = getattr(condition, 'node', None)
        narrowed = None if node is None else _states_where(node, ref.entity, ref.member, frozenset(states))
        if narrowed is not None:
            found = narrowed[0] if found is None else found & narrowed[0]
    return found


def _states_where(node, entity, member, states):
    """(the states of the named state `entity.member` in which a condition can hold, whether the condition
    holds in each of them), or None for a condition that does not narrow the states:
    - `var is s` gives {s}, and `var is not s` every other state;
    - `and` gives the states that each part that narrows them gives;
    - `or` gives the states of its parts, when each part narrows them;
    - `not` gives the other states, when its part holds in each state that the part gives;
    - anything else narrows nothing."""
    if isinstance(node, expr.Compare) and len(node.ops) == 1 and node.ops[0] in ('eq', 'ne'):
        left, right = node.operands
        if isinstance(left, expr.Const):
            left, right = right, left
        if not (
            isinstance(left, resolved.Ref)
            and (left.entity, left.member) == (entity, member)
            and isinstance(right, expr.Const)
            and isinstance(right.value, str)
        ):
            return None
        one = frozenset({right.value})
        return (states & one if node.ops[0] == 'eq' else states - one), True
    if isinstance(node, expr.BoolOp):
        parts = [_states_where(value, entity, member, states) for value in node.values]
        narrowing = [part for part in parts if part is not None]
        if node.op == 'and':
            if not narrowing:
                return None
            exact = len(narrowing) == len(parts) and all(part[1] for part in narrowing)
            return frozenset.intersection(*(part[0] for part in narrowing)), exact
        if len(narrowing) < len(parts):
            return None
        return frozenset.union(*(part[0] for part in parts)), all(part[1] for part in parts)
    if isinstance(node, expr.Unary) and node.op == 'not':
        inner = _states_where(node.operand, entity, member, states)
        if inner is None or not inner[1]:
            return None
        return states - inner[0], True
    return None


def _targets(node, states, entities):
    """The states that the value of a line can give a named state, in the order of its states: a state,
    each state of both branches of an `if`, or each state that a named state or a named input that it
    names can hold; any other value can give each state. `node` is the value as typed nodes."""
    if isinstance(node, expr.Const) and isinstance(node.value, str):
        return [node.value] if node.value in states else []
    if isinstance(node, expr.IfElse):
        both = {*_targets(node.body, states, entities), *_targets(node.orelse, states, entities)}
        return [state for state in states if state in both]
    if isinstance(node, resolved.Ref) and node.entity in entities:
        given = styles.states_of(entities[node.entity].value(node.member))
        if given is not None:
            return [state for state in states if state in given]
    return list(states)


__all__ = [
    'ACTOR_NAMES',
    'COLUMNS',
    'FIELD',
    'KINDS',
    'ROLES',
    'STOCK_KINDS',
    'Walk',
    'actor_name',
    'cards',
    'filled',
    'label_of',
    'map_payload',
    'picture',
    'references',
    'system_map',
    'texts_of',
    'variant_of',
]
