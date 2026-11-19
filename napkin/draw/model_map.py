"""The map of the system (docs/draw.md): the things of a model, and what the parts of each read of the
other things, what they change, the events that they start and the material that they move.

The map reads the declared model and the program through `things.Things`, the reachability of each
run to know which events it can start (D16), and the picture (`style.toml`: `[layout] hide` and
`[icon]`). Nothing in the model, the engine or the studies reads it.

- A **card** is a thing: an entity written once, a member written by hand, or a table, whose rows
  share one card (`things.Card`).
- A **part** is a part of a thing that acts or that has a value: a formula, the initializer and the
  bounds of a value, a member's own value, the settings of an endpoint, a flow (its request, its
  capacity and its ends), an event (its triggers, its stages, its gates and their statements) and a
  solver (its inputs and what it solves for). Assertions are left out: they test a run, and nothing
  in the run reads them.
- A **relation** is a value of another card that a part reads (`reads`; `follows` for the time since
  an event started and its occurrences), changes (`changes`: sets, adds to, takes from, shares out a
  flow by an allocation, or solves for), an event of another card that it starts (`fires`), or a
  store of another card that it moves material into or out of (`moves`).
- An **arrow** stands for the relations of one kind between two cards that the map draws. Its head is
  the card that the relations affect: the reader of what it reads, and the owner of what is changed,
  started or moved.

`picture` gives what `napkin draw` draws (layout.py and svg.py read it, and never the model): each card
with its stocks, the pipes of its flows and the state machines of its named states, the arrows of each
kind between the cards, and the groups, for one run or for every run joined. The layout works out the
legend from what it draws.
"""

from __future__ import annotations

from pathlib import Path

from .. import paths
from ..model import semantic as s
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
from .text import in_words
from .things import FLOWS, TABLE, walk_expression

# Who acts, in the words of a card: the word for each role.
ACTOR_NAMES = {
    'adversary': 'Attacker',
    'responder': 'Responders',
    'operator': 'Operators',
    'environment': 'Conditions',
    'community': 'Residents',
    'clinician': 'Clinicians',
}
# The roles that a card names; a role that names a thing, and no role, are None.
ROLES = ('adversary', 'operator', 'responder', 'environment', 'clinician', 'community')
# The words of the relations of a "changes" arrow, which its tooltip shows.
CHANGE_WORDS = ('sets', 'adds', 'takes', 'shares', 'solves')
# How an assignment changes its target, by its operator.
OPERATOR_WORDS = {'=': 'sets', '+=': 'adds', '-=': 'takes'}


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


def actor_name(role):
    """Who acts, in the words of a card: the word for its role (`ACTOR_NAMES`), else the role in
    words."""
    return ACTOR_NAMES.get(role, in_words(role))


def label(text, name):
    """A label: the text of a part, else its name in words."""
    return text if text else in_words(name)


def arrow_kind(relation):
    """The kind of the arrow that a relation of `Walk` belongs to (`ARROW_KINDS`)."""
    how = relation.get('how')
    if relation['kind'] == 'changes' and how == 'runs':
        return 'fires'
    if relation['kind'] == 'reads' and how == 'time':
        return 'follows'
    return relation['kind']


# ---- the parts and relations -----------------------------------------------------------------------


class Walk:
    """The parts and relations of one model (`things.Things`).

    `parts` are {kind, card, name, event}: `event` is the declared path of the event that a part of an
    event belongs to, else None. `relations` are {kind, by, of, value, part, how}: the card of the
    part (`by`), the card of what it reaches (`of`), the key of that `card.name` (`value`), the index
    of the part and how (`from`, `to` for a move, `time` for a read of an event, `runs` for a start,
    and the words of a change)."""

    def __init__(self, found):
        self.found = found
        self.parts = []
        self.relations = []
        self.seen = set()
        self.values = {}
        for card in found.cards.values():
            self.card(card)

    def part(self, kind, card, name, event=None):
        self.parts.append({'kind': kind, 'card': card, 'name': name, 'event': event})
        return len(self.parts) - 1

    def relate(self, index, kind, reached, how=None):
        """The relations of part `index` to what a read reaches (`things.Reached`) on other cards."""
        if reached is None or reached.what in ('member', 'local'):
            return
        by = self.parts[index]['card']
        for member in reached.members:
            of = self.found.card_of.get(member)
            if of is None or of == by:
                continue
            relation = {'kind': kind, 'by': by, 'of': of, 'value': f'{of}.{reached.name}', 'part': index}
            if reached.what == 'event' and kind == 'reads':
                relation['how'] = 'time'
            elif how is not None:
                relation['how'] = how
            key = tuple(sorted(relation.items()))
            if key not in self.seen:
                self.seen.add(key)
                self.relations.append(relation)
                self.values.setdefault(relation['value'], {'card': of, 'what': reached.what})

    def reads(self, index, expression, members):
        """The relations of what an expression reads."""
        if expression is None or isinstance(expression, str):
            return
        if isinstance(expression, tuple) and expression and expression[0] in ('priority', 'proportional'):
            return
        for read, item in walk_expression(expression):
            if read.start[0] in ('time', 'root'):
                continue
            found = self.found.reached(read, members, item)
            self.relate(index, 'reads', found)

    def card(self, card):
        found, entry, members = self.found, card.id, card.members
        for part in found.parts(entry):
            if isinstance(part, s.DeclaredValue):
                self.value(entry, part, members)
            elif isinstance(part, FLOWS):
                index = self.part('flow', entry, part.name)
                self.flow(index, part, members)
            elif isinstance(part, s.DeclaredEvent):
                self.event(entry, part, members)
            elif isinstance(part, s.DeclaredSolver):
                index = self.part('solver', entry, part.name)
                for binding in part.inputs:
                    self.reads(index, binding.read, members)
                for read in part.solve_for:
                    self.relate(index, 'changes', found.reached(read, members), how='solves')
        # A member's own values and links.
        for member in members:
            declared = found.declared.part(member)
            for given in getattr(declared, 'values', ()):
                index = self.part('value', entry, given.name)
                self.reads(index, given.init, (member,))

    def value(self, entry, value, members):
        kind = 'formula' if value.kind == s.FORMULA else 'value'
        if value.kind in (s.STATE, s.FORMULA, s.COLLECTION):
            index = self.part(kind, entry, value.name)
            self.reads(index, value.init, members)
            self.reads(index, value.lower, members)
            self.reads(index, value.upper, members)
        for side in (value.outflow, value.inflow):
            if side is None:
                continue
            index = self.part('endpoint', entry, f'{value.name}.{side.path.rpartition(".")[2]}')
            self.reads(index, side.capacity, members)
            self.reads(index, side.request, members)
            self.allocation(index, side.allocation, members)

    def allocation(self, index, allocation, members):
        """The relations of an allocation: each flow that a priority ranks, which it shares out."""
        if allocation[0] != 'priority':
            return
        for item in allocation[1]:
            self.relate(index, 'changes', self.found.reached(item, members), how='shares')

    def flow(self, index, flow, members):
        """The relations of a flow: its request and capacity read, its ends moved."""
        for leg in flow.legs if isinstance(flow, s.DeclaredLegs) else (flow,):
            self.reads(index, leg.request, members)
            self.reads(index, leg.capacity, members)
            for end, how in ((leg.source, 'from'), (leg.sink, 'to')):
                if isinstance(end, s.Read):
                    self.relate(index, 'moves', self.found.reached(end, members), how=how)

    def event(self, entry, event, members):
        index = self.part('event', entry, event.name, event.path)
        for trigger in event.triggers:
            self.reads(index, trigger.test, members)
            for capture in trigger.captures:
                self.reads(index, capture.init, members)
            for start in trigger.starts:
                self.statement(index, start, members)
            if trigger.reset is not None:
                self.reads(index, trigger.reset[1], members)
        for local in event.locals:
            if isinstance(local, FLOWS):
                self.flow(index, local, members)
            else:
                self.reads(index, local.init, members)
        for step in event.steps:
            if isinstance(step, s.DeclaredGate):
                self.reads(index, step.test, members)
                continue
            self.reads(index, step.delay, members)
            self.reads(index, step.guard, members)
            for statement in s.statements_of(step.body):
                self.statement(index, statement, members)

    def statement(self, index, statement, members):
        found = self.found
        if isinstance(statement, s.DeclaredAssign):
            self.reads(index, statement.value, members)
            how = OPERATOR_WORDS[statement.op]
            self.relate(index, 'changes', found.reached(statement.target, members), how=how)
        elif isinstance(statement, s.DeclaredMove):
            self.reads(index, statement.amount, members)
            self.relate(index, 'moves', found.reached(statement.source, members), how='from')
            self.relate(index, 'moves', found.reached(statement.destination, members), how='to')
        elif isinstance(statement, s.DeclaredStart):
            for arg in statement.args:
                self.reads(index, arg, members)
            self.relate(index, 'changes', found.reached(statement.event, members), how='runs')
        elif isinstance(statement, s.DeclaredIf):
            self.reads(index, statement.test, members)
        elif isinstance(statement, s.DeclaredSwitch):
            self.reads(index, statement.selector, members)
        elif isinstance(statement, s.DeclaredCase):
            self.reads(index, statement.guard, members)

    def held(self, runs):
        """The indices of the parts that can act in one of `runs`: an event's when it can start in
        one of them (`Things.startable`), and every other part."""
        found = self.found
        startable = [found.startable(run) for run in runs]
        return {
            k
            for k, part in enumerate(self.parts)
            if part['event'] is None or any(item.get(part['event'], True) for item in startable)
        }


# ---- the picture: what `napkin draw` draws ---------------------------------------------------------


def picture(model, style=None, run=None):
    """What `napkin draw` draws of a model (a `Compiled`): a plain dict that JSON writes, the same for
    the same model, picture and run. `style` is the picture (`style.Style`), by default the model's own
    (`style.of`). With `run`, the events that the run cannot start are absent, with their lines,
    transitions and relations (`Things.startable`). Without it, the picture joins the runs: an event
    is drawn when it can start in one run or more. A `run` that the model does not have raises
    ValueError.

    - `name`: the package, or `package:variant`; `title`: the scenario's title; `run`; `direction`.
    - `facts` (D-59): what the subtitle says. `run`: None, or `{name, label, options}` for `run`,
      with its options; `runs`: the number of runs that the picture joins (1 with `run`); `horizon`:
      the horizon as written, or None; `hidden`: the titles of the things (a template's name) that
      `[layout] hide` leaves out, sorted.
    - `settings` (D-51, D-52): what the stylesheet chooses for the layout and the SVG (`settings_of`).
    - `cards`: each card that the picture draws, in their order (`_Drawing.card`).
    - `arrows`: one for each two cards and kind (`ARROW_KINDS`, `arrow_kind`),
      `{from, to, kind, count, values, how}`, sorted by `(from, to, kind)`. `values` are the values of
      `to` that the parts of `from` change, start or move, or the values and events of `from` that the
      parts of `to` read or follow (the relations of `Walk`), sorted. `count` is the number of them that
      the run holds; joined, it is the largest of the runs. `how` holds the words of a "changes" arrow's
      relations (`CHANGE_WORDS`), sorted; it is empty for the other kinds.
    - `groups`: each group of `[group]` that holds a card, `{label, members}`, its members in the order
      of the cards.
    - `panels` (D-53, D-55): the Equations, Symbols and References panels under the map
      (`panels.panels`), or None when `[equations] things` names nothing.

    A thing that `[layout] hide` hides is absent, with each arrow and transition of its parts. Each
    name of the picture is one that the model declares: a card is a thing, a stock and a named state
    `card.name`, a flow and an event `card.name`, and a state a member of its enum."""
    found = styles.things_of(model)
    sheet = styles.of(found.compiled) if style is None else style
    if run is not None and run not in found.runs:
        names = ', '.join(name for name in found.runs if name is not None) or 'none'
        raise ValueError(f'{run} is not a run of the model; its runs are {names}')
    drawing = _Drawing(found, sheet, run)
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
    scenario = found.declared.scenario
    return {
        'name': _name_of(found),
        'title': scenario.title if scenario is not None else '',
        'run': run,
        'direction': sheet.direction,
        'facts': drawing.facts(),
        'settings': settings_of(sheet),
        'cards': cards,
        'arrows': arrows,
        'groups': [
            {'label': label_, 'members': names} for label_, names in styles.groups_of(sheet, found) if names
        ],
        'panels': _panels(found, sheet, run, cards),
    }


def _panels(found, sheet, run, cards):
    """The panels of the picture (`panels.panels`), or None when `[equations] things` names nothing."""
    if not sheet.equations:
        return None
    # panels.py reads the names of this module, so it comes in here.
    from .panels import panels

    return panels(found, sheet, run, cards)


def _name_of(found):
    """The name of a model's package, or `package:variant` for a variant (`paths.names_of`); `model`
    for a model of one text."""
    if found.origin is None:
        return 'model'
    scenario, variant = paths.names_of(found.origin)
    return scenario if variant is None else f'{scenario}:{variant}'


class _Drawing:
    """The parts of a picture of one model, for one run or for every run joined: the parts that can
    act (`held`), the arrows between the cards that the picture draws (`arrows`: {(from, to, kind):
    {count, values, how}}) and the transitions of the named states."""

    def __init__(self, found, sheet, run):
        self.found, self.sheet, self.run = found, sheet, run
        self.walk = Walk(found)
        self.shown = styles.drawn(sheet, found)
        self.runs = (run,) if run is not None else found.runs
        self.held, self.arrows = set(), {}
        for each in self.runs:
            self.join(self.walk.held((each,)))
        # The things that decide: each actor (`napkin.model.views.actors`) with a choice.
        self.deciders = {item['name'] for item in actors(found.compiled) if item['choices']}
        self.starters = {
            found.card_of.get(member)
            for start in found.declared.setup
            for member in getattr(found.reached(start.event, ()), 'members', ())
        }
        self.events = {part['event'] for k, part in enumerate(self.walk.parts) if k in self.held}
        self.transitions = _transitions(found, self.events, set(self.shown))
        self.places = styles.place_of(sheet, found)
        self.machine_places = styles.state_places(sheet, found)
        self.stock_orders = styles.stock_orders(sheet, found)
        self.icons = styles.icon_of(sheet, found)
        self.levels = styles.trigger_levels(sheet, found)

    def facts(self):
        """What the subtitle of the picture says (D-59): the run, the number of runs joined, the
        horizon and the names that `[layout] hide` leaves out."""
        found, run = self.found, self.run
        horizon = found.declared.tree.scenario.horizon if found.declared.tree is not None else None
        out = {
            'run': None,
            'runs': len(self.runs),
            'horizon': None if horizon is None else _written(horizon),
            'hidden': sorted(self.hidden_title(name) for name in self.sheet.hide),
        }
        if run is not None:
            item = found.declared.run(run)
            out['run'] = {'name': run, 'label': item.text or run, 'options': list(item.options)}
        return out

    def hidden_title(self, name):
        """The words of a name that `[layout] hide` gives: the title of a thing, or a template's name."""
        card = self.found.cards.get(name)
        return name if card is None else card.title

    def join(self, held):
        """Adds what one run holds: its parts that can act, and its arrows, with the number of values
        of each."""
        self.held |= held
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

    def card(self, entry):
        """A card of the picture: `id`; `title`; `role`, one of `ROLES` or None; `icon`; `template`,
        the template of a member or a table, else None; `copies`, the number of rows of a table, else
        1; `actor`, whether it is an actor with a choice (`napkin.model.views.actors`); `starts`,
        whether the setup starts an event of it; `file`, the file that writes its line, from the
        folder of the package; `place`, `{column, row}` from `[place]` or None; its stocks, pipes and
        state machines; `stock_order`, the rows that `[stocks]` gives it (D-52); `hidden_stocks`,
        always 0 (the layout collapses stocks); and `triggers`, what the card shows of its events
        (D-56)."""
        card = self.found.cards[entry]
        place = self.places.get(entry)
        stocks = self.stocks(entry)
        keys = {stock['key'] for stock in stocks}
        return {
            'id': entry,
            'title': card.title,
            'role': card.role if card.role in ROLES else None,
            'icon': self.icons[entry],
            'template': card.shown_template,
            'copies': len(card.members) if card.kind == TABLE else 1,
            'actor': card.template in self.deciders,
            'starts': entry in self.starters,
            'file': self.file_of(entry),
            'place': None if place is None else {'column': place[0], 'row': place[1]},
            'stocks': stocks,
            'stock_order': self.stock_order(entry, keys),
            'hidden_stocks': 0,
            'pipes': self.pipes(entry, keys),
            'machines': self.machines(entry),
            'triggers': self.triggers(entry),
        }

    def file_of(self, entry):
        """The file that writes a card's line, from the folder of its package, with `/`; None for a
        model of one text."""
        name = self.found.file_of(entry)
        if name is None:
            return None
        path, package = Path(name), paths.package_of(name)
        try:
            return path.relative_to(package).as_posix() if package is not None else path.name
        except ValueError:
            return path.name

    def stock_order(self, entry, keys):
        """The rows that `[stocks]` gives the card (D-52), its own list else its template's: the keys of
        the stocks and tallies of the list that the card has (`keys`), in the order of the list. None
        without a list: the layout chooses the rows."""
        listed = self.stock_orders.get(entry)
        if listed is None:
            return None
        return [key for key in (f'{entry}.{name}' for name in listed) if key in keys]

    def stocks(self, entry):
        """The stocks and tallies of a card, in written order: `{key, name, kind}`."""
        found = self.found
        return [
            {'key': f'{entry}.{value.name}', 'name': label(value.text, value.name), 'kind': found.kind(value)}
            for value in found.stocks(entry)
        ]

    def pipes(self, entry, stocks):
        """The pipes of a card, `{key, flows, from, to, label}`: for each two ends, the flows of the card
        that can act and that move material between two of its stocks (`stocks`, their keys), or between
        one of them and outside the model (an end None), in written order. `key` is `from->to`, with
        nothing for outside. A flow with an end on another card moves its material: an arrow of kind
        `moves`, and no pipe. A flow of an event acts when its event can start; a leg is a flow of its
        flow with legs, and a route goes from its first end to its second."""
        found, members = self.found, self.found.cards[entry].members
        flows = []
        for part in found.parts(entry):
            if isinstance(part, FLOWS):
                flows.append((part.name, part))
            elif isinstance(part, s.DeclaredEvent) and part.path in self.events:
                flows += [
                    (f'{part.name}.{local.name}', local) for local in part.locals if isinstance(local, FLOWS)
                ]
        grouped = {}
        for name, flow in flows:
            for leg in flow.legs if isinstance(flow, s.DeclaredLegs) else (flow,):
                ends = []
                for end in (leg.source, leg.sink):
                    if not isinstance(end, s.Read):
                        ends.append(None)
                        continue
                    reached = found.reached(end, members)
                    key = (
                        f'{entry}.{reached.name}' if reached is not None and reached.what == 'value' else None
                    )
                    on_card = reached is not None and {found.card_of.get(m) for m in reached.members} == {
                        entry
                    }
                    ends.append(key if on_card and key in stocks else False)
                if False in ends or ends == [None, None]:
                    continue
                pipe = grouped.setdefault(tuple(ends), {})
                pipe.setdefault(f'{entry}.{name}', label(flow.text, flow.name))
        return [
            {
                'key': f'{source or ""}->{target or ""}',
                'flows': list(pipe),
                'from': source,
                'to': target,
                'label': _joined(pipe.values()),
            }
            for (source, target), pipe in grouped.items()
        ]

    def machines(self, entry):
        """The state machines of a card, sorted by var: for each named state, `{var, name, states,
        initial, starts_by, transitions, place}`. `states` are the members of its enum in order,
        `initial` its start (None when its members start in other states, or when the start is no
        member that the file writes), `starts_by` holds `{option, state}` for each option that sets
        the input that its start reads (D-59), `transitions` (`_transitions`) are sorted by (event,
        state), and `place` is the one of `[state]`, else `inside`."""
        found = self.found
        out = []
        for value in found.machines(entry):
            var = f'{entry}.{value.name}'
            out.append(
                {
                    'var': var,
                    'name': label(value.text, value.name),
                    'states': list(value.type.members),
                    'initial': _initial(found, entry, value),
                    'starts_by': _starts_by(found, entry, value),
                    'transitions': [
                        {'from': item['from'], 'to': to, 'event': event, 'by': item['by']}
                        for (event, to), item in sorted(self.transitions.get(var, {}).items())
                    ],
                    'place': self.machine_places.get(entry, {}).get(value.name, styles.STATE_PLACES[0]),
                }
            )
        return sorted(out, key=lambda machine: machine['var'])

    def triggers(self, entry):
        """What the card shows of its events (D-56), or None for a card that `[triggers]` does not name:
        `{level, lines, events, more}`.

        - `level`: one of `TRIGGER_LEVELS` (`count`, `names`, `rules`, `hover`).
        - `lines`: the most rows of the text of an event (`[triggers] lines`); the layout uses it at
          `rules`.
        - `events`: each event of the card that can act, in written order, `{event, name, text, full,
          label, rule}`. `event` is `card.event`; `name`, the event's name in words; `text`, what the
          card shows before the layout shortens it: the name at `names`, the line at `rules`, and None
          at `count` and `hover` and for each event after the first `[triggers] events`; `full`, the
          whole line (`triggers.Line.full`) for the tooltip; `label`, the event's text, or None;
          `rule`, the condition of its first trigger as the file writes it, or None. With `[triggers]
          options = false`, `text` and `full` leave out the options that switch the event.
        - `more`: the number of events without a text at `names` and `rules` (a row "+n more"), else
          0."""
        level = self.levels.get(entry)
        if level is None:
            return None
        from .triggers import card_lines

        sheet = self.sheet
        limit = sheet.trigger_events or DEFAULT_TRIGGER_EVENTS
        options = DEFAULT_TRIGGER_OPTIONS if sheet.trigger_options is None else sheet.trigger_options
        rows = level in ('names', 'rules')
        events = []
        for line in card_lines(self.found, entry):
            if line.path not in self.events:
                continue
            full = line.joined(options)
            shown = rows and len(events) < limit
            events.append(
                {
                    'event': line.key,
                    'name': line.name,
                    'text': (line.name if level == 'names' else full) if shown else None,
                    'full': full,
                    'label': line.label or None,
                    'rule': line.rule,
                }
            )
        return {
            'level': level,
            'lines': sheet.trigger_lines or DEFAULT_TRIGGER_LINES,
            'events': events,
            'more': sum(event['text'] is None for event in events) if rows else 0,
        }


def _written(node):
    """The text of a node of the parsed tree as the file writes it."""
    from ..model.language import format as formatter

    return formatter.expression(node)


def _joined(labels):
    """The labels of the flows of one pipe, each once, in order: sentences one after the other, and names
    with a semicolon between them."""
    labels = list(dict.fromkeys(labels))
    return (' ' if all(item.endswith(('.', '!', '?')) for item in labels) else '; ').join(labels)


def _initial(found, entry, value):
    """The start of a named state of a card: the member that its initializer or each member's own
    value writes, when they are one, else None."""
    starts = set()
    for member in found.cards[entry].members:
        own = next(
            (
                given
                for given in getattr(found.declared.part(member), 'values', ())
                if given.name == value.name
            ),
            None,
        )
        init = own.init if own is not None else value.init
        starts.add(init.value if isinstance(init, s.Const) and isinstance(init.value, str) else None)
    start = starts.pop() if len(starts) == 1 else None
    return start if start in value.type.members else None


def _starts_by(found, entry, value):
    """{option, state} of each option that sets the enum input that a named state's start reads, in
    the order of the options."""
    init = value.init
    if not (isinstance(init, s.Read) and init.fixed and init.part):
        return []
    source = found.declared.part(init.part)
    if source is None or source.kind != s.INPUT:
        return []
    out = []
    for option in found.declared.options:
        for setting in option.settings:
            if setting.path == init.part or (
                setting.instances is not None and f'{setting.instances}.{setting.name}' == init.part
            ):
                state = getattr(setting.value, 'value', None)
                if state in value.type.members:
                    out.append({'option': option.name, 'state': state})
    return out


# ---- the transitions of the named states ------------------------------------------------------------


def _transitions(found, events, shown):
    """{card.var: {(event, state): {from, by}}}: the transitions of each named state of a card in
    `shown`. Each assignment `x = v` in a stage of an event that can act (`events`, their paths), of
    a card in `shown`, whose target is a named state of a card in `shown`, is a transition to each
    state that `v` can give (`_targets`) from the states that the assignment can run in
    (`_narrowed`): those that the stage's guard and the branches around the assignment allow, and
    those of the event's triggers when every start of the event is a trigger and the stage is its
    first step after no delay. The state that it gives is left out of `from`; `from` is None when
    nothing narrows the states, and a transition that only keeps the state is absent. The
    assignments of one event that give one state join their states."""
    callers = _started(found)
    out = {}
    for card in found.cards.values():
        if card.id not in shown:
            continue
        for event in found.events(card.id):
            if event.path not in events:
                continue
            triggered = bool(event.triggers) and event.path not in callers
            for k, step in enumerate(event.steps):
                if not isinstance(step, s.DeclaredStage):
                    continue
                first = triggered and k == 0 and isinstance(step.delay, s.Const) and step.delay.value == 0
                given = [('holds', step.guard)] if step.guard is not None else []
                if first:
                    given.append(('any', tuple(trigger.test for trigger in event.triggers)))
                for statement, conditions in _branches(step.body, given):
                    _transition(found, card, event, statement, conditions, shown, out)
    return out


def _started(found):
    """The paths of the events that a statement or the setup starts."""
    from .triggers import event_of

    out = {event_of(start.event) for start in found.declared.setup}
    for card in found.cards.values():
        for event in found.events(card.id):
            for step in event.steps:
                for statement in s.statements_of(step.body) if isinstance(step, s.DeclaredStage) else ():
                    if isinstance(statement, s.DeclaredStart):
                        out.add(event_of(statement.event))
            for trigger in event.triggers:
                out.update(
                    event_of(start.event) for start in trigger.starts if event_of(start.event) != event.path
                )
    return out


def _branches(body, given):
    """(statement, the conditions under which it runs) of each statement of a body: `('holds', c)`,
    `('fails', c)`, `('case', selector, member)` and `('any', (c, …))`, outermost first."""
    for statement in body:
        yield statement, given
        if isinstance(statement, s.DeclaredIf):
            yield from _branches(statement.then, [*given, ('holds', statement.test)])
            yield from _branches(statement.orelse, [*given, ('fails', statement.test)])
        elif isinstance(statement, s.DeclaredSwitch):
            for case in statement.cases:
                inner = [*given, ('case', statement.selector, case.member)]
                if case.guard is not None:
                    inner.append(('holds', case.guard))
                yield from _branches(case.body, inner)
            yield from _branches(statement.orelse, given)


def _transition(found, card, event, statement, conditions, shown, out):
    if not (isinstance(statement, s.DeclaredAssign) and statement.op == '='):
        return
    target = found.reached(statement.target, card.members)
    if target is None or target.what != 'value' or target.steps:
        return
    cards = {found.card_of.get(m) for m in target.members}
    if len(cards) != 1:
        return
    (owner,) = cards
    if owner not in shown or target.name not in styles.named_states(found, owner):
        return
    value = found.part(found.cards[owner].template, target.name)
    states = value.type.members
    key = (target.members, target.name)
    sources = _narrowed(found, card.members, conditions, key, frozenset(states))
    for to in _targets(found, card.members, statement.value, states):
        given = None if sources is None else [state for state in states if state in sources and state != to]
        if given == []:
            continue
        item = out.setdefault(f'{owner}.{target.name}', {}).setdefault(
            (f'{card.id}.{event.name}', to), {'from': given, 'by': card.id}
        )
        if item['from'] is not None:
            joined = None if given is None else set(item['from']) | set(given)
            item['from'] = None if joined is None else [state for state in states if state in joined]


def _narrowed(found, members, conditions, key, states):
    """The states of the named state `key` (its members and its name) in which every condition can
    hold (`_states_where`), or None when no condition narrows them."""
    out = None
    for condition in conditions:
        narrowed = None
        if condition[0] == 'holds':
            narrowed = _states_where(found, members, condition[1], key, states)
        elif condition[0] == 'fails':
            inner = _states_where(found, members, condition[1], key, states)
            narrowed = (states - inner[0], True) if inner is not None and inner[1] else None
        elif condition[0] == 'case':
            if _same(found, members, condition[1], key):
                narrowed = (states & {condition[2]}, True)
        elif condition[0] == 'any':
            parts = [_states_where(found, members, test, key, states) for test in condition[1]]
            if parts and all(part is not None for part in parts):
                narrowed = (frozenset.union(*(part[0] for part in parts)), True)
        if narrowed is not None:
            out = narrowed[0] if out is None else out & narrowed[0]
    return out


def _same(found, members, expression, key):
    """Whether an expression is a read of the named state `key`."""
    if not isinstance(expression, s.Read):
        return False
    reached = found.reached(expression, members)
    return reached is not None and reached.what == 'value' and (reached.members, reached.name) == key


def _states_where(found, members, node, key, states):
    """(the states of the named state `key` in which a condition can hold, whether the condition holds
    in each of them), or None for a condition that does not narrow the states:
    - `x == s` gives {s}, and `x != s` every other state;
    - `and` gives the states that each part that narrows them gives;
    - `or` gives the states of its parts, when each part narrows them;
    - `not` gives the other states, when its part holds in each state that the part gives;
    - anything else narrows nothing."""
    if not isinstance(node, s.Apply):
        return None
    if node.op == 'compare' and len(node.detail) == 1 and node.detail[0] in ('==', '!='):
        left, right = node.args
        if isinstance(left, s.Const):
            left, right = right, left
        if not (
            _same(found, members, left, key) and isinstance(right, s.Const) and isinstance(right.value, str)
        ):
            return None
        one = frozenset({right.value})
        return (states & one if node.detail[0] == '==' else states - one), True
    if node.op in ('and', 'or'):
        parts = [_states_where(found, members, value, key, states) for value in node.args]
        narrowing = [part for part in parts if part is not None]
        if node.op == 'and':
            if not narrowing:
                return None
            exact = len(narrowing) == len(parts) and all(part[1] for part in narrowing)
            return frozenset.intersection(*(part[0] for part in narrowing)), exact
        if len(narrowing) < len(parts):
            return None
        return frozenset.union(*(part[0] for part in parts)), all(part[1] for part in parts)
    if node.op == 'not':
        inner = _states_where(found, members, node.args[0], key, states)
        if inner is None or not inner[1]:
            return None
        return states - inner[0], True
    return None


def _targets(found, members, node, states):
    """The states that the value of an assignment can give a named state, in the order of its states:
    a member, each state of both branches of an `if`, or each state that a value of an enum that it
    reads can hold; any other value can give each state."""
    if isinstance(node, s.Const) and isinstance(node.value, str):
        return [node.value] if node.value in states else []
    if isinstance(node, s.Apply) and node.op == 'if':
        both = {
            *_targets(found, members, node.args[1], states),
            *_targets(found, members, node.args[2], states),
        }
        return [state for state in states if state in both]
    if isinstance(node, s.Read) and isinstance(node.type, s.EnumOf):
        return [state for state in states if state in node.type.members]
    return list(states)


__all__ = [
    'ACTOR_NAMES',
    'CHANGE_WORDS',
    'ROLES',
    'Walk',
    'actor_name',
    'arrow_kind',
    'label',
    'picture',
    'settings_of',
]
