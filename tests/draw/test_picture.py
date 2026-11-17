"""What `napkin draw` draws (`model_map.picture`): the cards with their stocks, pipes and state machines,
the arrows between them, and the groups. The legend is the layout's (tests/draw/test_layout.py).

Each model of these tests writes its things in its own lines, so each expectation follows from the text
of the test and from the rule that the test names. `picture_problems` checks a picture against the
contract between `picture` and the layout and SVG (layout.py, svg.py), from the document alone: the
frozen example `picture.json` passes it, and so does each picture of these tests and of the catalogue.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from napkin import paths
from napkin.draw import layout as layouts
from napkin.draw import notation, style
from napkin.draw.layout import layout
from napkin.draw.model_map import card_title, picture
from tests.build import (
    block,
    compiled,
    document,
    entity,
    event,
    flow,
    named,
    named_event,
    option,
    options,
    parameter,
    runs,
    share,
    start,
    stock,
    template,
)
from tests.draw.test_model_map import FIXTURE_STYLE, fixture_model
from tests.helpers import SCENARIO_IDS, catalogue_model

ROOT = Path(__file__).resolve().parents[2]
FROZEN = Path(__file__).with_name('picture.json')

# ---- the contract, from the document alone --------------------------------------------------------
#
# The contract's own lists: the keys of each part, and the words that a value can be. The icons are the
# 20 of tests/draw/map-icons.json.
TOP = ('name', 'title', 'run', 'direction', 'facts', 'settings', 'cards', 'arrows', 'groups', 'panels')
SETTINGS = ('looks', 'bundle', 'stocks', 'cards_per_column', 'card_width')
LOOKS = ('full', 'light', 'hidden')
FACTS = ('run', 'runs', 'horizon', 'hidden')
CARD = (
    'id',
    'title',
    'role',
    'icon',
    'template',
    'copies',
    'actor',
    'starts',
    'file',
    'place',
    'stocks',
    'stock_order',
    'hidden_stocks',
    'pipes',
    'machines',
    'triggers',
)
STOCK = ('key', 'name', 'kind')
PIPE = ('key', 'flows', 'from', 'to', 'label')
MACHINE = ('var', 'name', 'states', 'initial', 'starts_by', 'transitions', 'place')
TRANSITION = ('from', 'to', 'event', 'by')
ARROW = ('from', 'to', 'kind', 'count', 'values', 'how')
ROLES = ('adversary', 'operator', 'responder', 'environment', 'clinician', 'community')
KINDS = ('reads', 'follows', 'changes', 'fires', 'moves')
# The words of the relations of a changes arrow (D-50).
CHANGE_WORDS = ('sets', 'adds', 'takes', 'shares')
MACHINE_PLACES = ('inside', 'beside', 'hidden')
# What a card shows of its events (D-56): the levels of `[triggers]`, the keys of a card's `triggers` and
# of each of its events, and the most rows of an event's line.
TRIGGER_LEVELS = ('count', 'names', 'rules', 'hover')
TRIGGERS = ('level', 'lines', 'events', 'more')
TRIGGER_EVENT = ('event', 'name', 'text', 'full', 'label', 'rule')
TRIGGER_LINES = 4
# The panels under the map (D-53, D-55): their parts, the settings with their ranges, a block, a member,
# a line and its kinds (the equations of `lhs = rhs` first), a row of the Symbols table and its kinds,
# a symbol, an entry of the References list and its kinds.
PANELS = ('settings', 'equations', 'symbols', 'references', 'left_out', 'tags', 'note')
PANEL_SETTINGS = ('depth', 'width', 'lines', 'tags', 'symbols', 'checks', 'instances', 'references', 'kinds')
PANEL_RANGES = {'depth': (0, 5), 'width': (320, 2400), 'lines': (1, 8)}
BLOCK = ('name', 'title', 'template', 'members', 'subscript', 'lines')
MEMBER = ('entity', 'card', 'title', 'subscript')
LINE = (
    'kind',
    'lhs',
    'rhs',
    'math',
    'words',
    'part',
    'event',
    'outcome',
    'keys',
    'marks',
    'records',
    'relation',
    'when',
    'latex',
)
LINE_KINDS = ('balance', 'rate', 'formula', 'bound', 'share', 'together', 'jump', 'check')
EQUATION_KINDS = ('balance', 'rate', 'formula')
ROW = (
    'key',
    'symbol',
    'count',
    'meaning',
    'kind',
    'unit',
    'value',
    'value_math',
    'options',
    'option_count',
    'instances',
    'range',
    'range_status',
    'distribution',
    'marks',
    'range_marks',
    'records',
)
ROW_KINDS = ('input', 'fixed', 'stock', 'tally', 'state', 'formula', 'flow', 'event', 'text', 'output')
SYMBOL = ('base', 'prime', 'sub', 'text', 'latex')
ENTRY = ('number', 'kind', 'label', 'text', 'url', 'link_text', 'hover', 'record')
REFERENCE_KINDS = ('source', 'source_transfer', 'identity', 'convention', 'assumption')
ICONS = tuple(json.loads(Path(__file__).with_name('map-icons.json').read_text(encoding='utf-8'))['icons'])


def _whole(value, least=1):
    return isinstance(value, int) and not isinstance(value, bool) and value >= least


def _text(value):
    return isinstance(value, str) and bool(value)


def picture_problems(doc):
    """The ways in which `doc` breaks the picture contract, [] for none. It reads the document only: the
    shape and the words of each part, the order of each list, and that each name that one part gives
    another (a card, a stock, a state) is there."""
    out = []

    def need(ok, where, message):
        if not ok:
            out.append(f'{where}: {message}')
        return ok

    def keys(item, names, where):
        return need(
            isinstance(item, dict) and list(item) == list(names), where, f'has the keys {", ".join(names)}'
        )

    if not keys(doc, TOP, 'picture'):
        return out
    need(json.loads(json.dumps(doc)) == doc, 'picture', 'is JSON')
    need(_text(doc['name']), 'name', 'is a text')
    need(isinstance(doc['title'], str), 'title', 'is a text')
    need(doc['run'] is None or _text(doc['run']), 'run', 'is a text or null')
    need(doc['direction'] == 'left-to-right', 'direction', 'is left-to-right')
    facts = doc['facts']
    if keys(facts, FACTS, 'facts'):
        run = facts['run']
        if run is not None and keys(run, ('name', 'label', 'options', 'versus'), 'facts.run'):
            need(run['name'] == doc['run'], 'facts.run.name', 'is the run of the picture')
            need(_text(run['label']), 'facts.run.label', 'is a text')
            options = run['options']
            need(
                isinstance(options, list) and all(_text(o) for o in options),
                'facts.run.options',
                'is a list of options',
            )
            need(run['versus'] is None or _text(run['versus']), 'facts.run.versus', 'is a text or null')
        need((run is None) == (doc['run'] is None), 'facts.run', 'is there for a picture of one run')
        need(
            _whole(facts['runs']) and (doc['run'] is None or facts['runs'] == 1), 'facts.runs', 'is 1 or more'
        )
        need(facts['horizon'] is None or _text(facts['horizon']), 'facts.horizon', 'is a text or null')
        hidden = facts['hidden']
        ok = isinstance(hidden, list) and all(_text(name) for name in hidden)
        need(ok and hidden == sorted(hidden), 'facts.hidden', 'is a sorted list of titles')
    settings = doc['settings']
    if keys(settings, SETTINGS, 'settings'):
        looks = settings['looks']
        need(
            isinstance(looks, dict)
            and list(looks) == list(KINDS)
            and all(v in LOOKS for v in looks.values()),
            'settings.looks',
            'gives each kind a look',
        )
        bundle = settings['bundle']
        need(
            isinstance(bundle, list) and bundle == [kind for kind in KINDS if kind in bundle],
            'settings.bundle',
            'is a list of kinds, in their order',
        )
        need(_whole(settings['stocks']), 'settings.stocks', 'is 1 or more')
        need(_whole(settings['cards_per_column']), 'settings.cards_per_column', 'is 1 or more')
        width = settings['card_width']
        need(
            width is None or (isinstance(width, (int, float)) and width > 0),
            'settings.card_width',
            'is a width or null',
        )
    cards = doc['cards'] if isinstance(doc['cards'], list) else []
    need(isinstance(doc['cards'], list), 'cards', 'is a list')
    ids = [card.get('id') for card in cards if isinstance(card, dict)]
    need(len(set(ids)) == len(ids), 'cards', 'name each card once')
    cells = {}
    for i, card in enumerate(cards):
        where = f'cards[{i}]'
        if not keys(card, CARD, where):
            continue
        need(_text(card['id']), f'{where}.id', 'is a text')
        need(isinstance(card['title'], str), f'{where}.title', 'is a text')
        need(card['role'] is None or card['role'] in ROLES, f'{where}.role', 'is a role or null')
        need(card['icon'] is None or card['icon'] in ICONS, f'{where}.icon', 'is an icon or null')
        need(card['template'] is None or _text(card['template']), f'{where}.template', 'is a text or null')
        need(_whole(card['copies']), f'{where}.copies', 'is 1 or more')
        need(isinstance(card['actor'], bool), f'{where}.actor', 'is true or false')
        need(isinstance(card['starts'], bool), f'{where}.starts', 'is true or false')
        need(card['file'] is None or _text(card['file']), f'{where}.file', 'is a text or null')
        place = card['place']
        if place is not None and keys(place, ('column', 'row'), f'{where}.place'):
            need(_whole(place['column']), f'{where}.place.column', 'is 1 or more')
            need(place['row'] is None or _whole(place['row']), f'{where}.place.row', 'is 1 or more, or null')
            if place['row'] is not None:
                other = cells.setdefault((place['column'], place['row']), card['id'])
                need(other == card['id'], f'{where}.place', f'is the cell of {other}')
        need(_whole(card['hidden_stocks'], 0), f'{where}.hidden_stocks', 'is 0 or more')
        prefix = f'{card["id"]}.'
        stocks = {}
        for k, item in enumerate(card['stocks'] if isinstance(card['stocks'], list) else [None]):
            at = f'{where}.stocks[{k}]'
            if keys(item, STOCK, at):
                need(_text(item['key']) and item['key'].startswith(prefix), f'{at}.key', f'starts {prefix}')
                need(item['key'] not in stocks, f'{at}.key', 'names its stock once')
                need(_text(item['name']), f'{at}.name', 'is a text')
                need(item['kind'] in ('stock', 'tally'), f'{at}.kind', 'is stock or tally')
                stocks[item['key']] = item['kind']
        # The rows that [stocks] gives (D-52): null, or stocks of the card, each once.
        order = card['stock_order']
        need(
            order is None
            or (
                isinstance(order, list) and len(set(order)) == len(order) and all(k in stocks for k in order)
            ),
            f'{where}.stock_order',
            'is null, or stocks of its card, each once',
        )
        ends = set()
        for k, item in enumerate(card['pipes'] if isinstance(card['pipes'], list) else [None]):
            at = f'{where}.pipes[{k}]'
            if not keys(item, PIPE, at):
                continue
            need(_text(item['key']), f'{at}.key', 'is a text')
            flows = item['flows']
            need(
                isinstance(flows, list)
                and flows
                and len(set(flows)) == len(flows)
                and all(_text(name) and name.startswith(prefix) for name in flows),
                f'{at}.flows',
                f'is a list of the flows of {card["id"]}',
            )
            for end in ('from', 'to'):
                need(
                    item[end] is None or item[end] in stocks, f'{at}.{end}', 'is a stock of its card, or null'
                )
            need((item['from'], item['to']) != (None, None), at, 'has a stock at one end')
            need((item['from'], item['to']) not in ends, at, 'is the one pipe between its ends')
            ends.add((item['from'], item['to']))
            need(isinstance(item['label'], str), f'{at}.label', 'is a text')
        machines = card['machines'] if isinstance(card['machines'], list) else [None]
        vars_ = [item.get('var') for item in machines if isinstance(item, dict)]
        need(vars_ == sorted(vars_, key=str), f'{where}.machines', 'are sorted by var')
        for k, item in enumerate(machines):
            at = f'{where}.machines[{k}]'
            if not keys(item, MACHINE, at):
                continue
            need(_text(item['var']) and item['var'].startswith(prefix), f'{at}.var', f'starts {prefix}')
            need(_text(item['name']), f'{at}.name', 'is a text')
            states = item['states']
            ok = isinstance(states, list) and states and all(_text(s) for s in states)
            need(ok and len(set(states)) == len(states), f'{at}.states', 'is a list of states')
            states = states if ok else []
            need(item['initial'] is None or item['initial'] in states, f'{at}.initial', 'is a state or null')
            starts = item['starts_by'] if isinstance(item['starts_by'], list) else [None]
            for m, setting in enumerate(starts):
                there = f'{at}.starts_by[{m}]'
                if keys(setting, ('option', 'state'), there):
                    need(_text(setting['option']), f'{there}.option', 'is a text')
                    need(setting['state'] in states, f'{there}.state', 'is a state')
            need(item['place'] in MACHINE_PLACES, f'{at}.place', 'is inside, beside or hidden')
            moves = item['transitions'] if isinstance(item['transitions'], list) else [None]
            order = [(t.get('event'), t.get('to')) for t in moves if isinstance(t, dict)]
            need(order == sorted(order, key=str), f'{at}.transitions', 'are sorted by (event, to)')
            need(len(set(order)) == len(order), f'{at}.transitions', 'name each event and state once')
            for m, move in enumerate(moves):
                there = f'{at}.transitions[{m}]'
                if not keys(move, TRANSITION, there):
                    continue
                need(move['to'] in states, f'{there}.to', 'is a state')
                need(_text(move['event']), f'{there}.event', 'is a text')
                need(move['by'] in ids, f'{there}.by', 'is a card')
                sources = move['from']
                need(
                    sources is None
                    or (
                        isinstance(sources, list)
                        and sources
                        and len(set(sources)) == len(sources)
                        and all(s in states and s != move['to'] for s in sources)
                    ),
                    f'{there}.from',
                    'is null, or other states',
                )
        triggers_problems(card, f'{where}.triggers', need, keys)
    arrows = doc['arrows'] if isinstance(doc['arrows'], list) else [None]
    order = [(a.get('from'), a.get('to'), a.get('kind')) for a in arrows if isinstance(a, dict)]
    need(order == sorted(order, key=str), 'arrows', 'are sorted by (from, to, kind)')
    need(len(set(order)) == len(order), 'arrows', 'are one for each two cards and kind')
    for k, arrow in enumerate(arrows):
        at = f'arrows[{k}]'
        if not keys(arrow, ARROW, at):
            continue
        need(arrow['from'] in ids and arrow['to'] in ids, at, 'joins two cards')
        need(arrow['from'] != arrow['to'], at, 'joins two cards')
        need(arrow['kind'] in KINDS, f'{at}.kind', 'is reads, follows, changes, fires or moves')
        values = arrow['values']
        ok = isinstance(values, list) and values and all(_text(v) for v in values)
        need(ok and values == sorted(set(values)), f'{at}.values', 'is a sorted list of values')
        need(
            _whole(arrow['count']) and ok and arrow['count'] <= len(values),
            f'{at}.count',
            'is 1 to the values',
        )
        how = arrow['how']
        ok = isinstance(how, list) and how == sorted(set(how)) and all(word in CHANGE_WORDS for word in how)
        need(
            ok and bool(how) == (arrow['kind'] == 'changes'),
            f'{at}.how',
            'is the sorted words of a changes arrow',
        )
    grouped = {}
    for k, group in enumerate(doc['groups'] if isinstance(doc['groups'], list) else [None]):
        at = f'groups[{k}]'
        if not keys(group, ('label', 'members'), at):
            continue
        need(_text(group['label']), f'{at}.label', 'is a text')
        members = group['members']
        ok = isinstance(members, list) and members and all(m in ids for m in members)
        need(ok and members == sorted(members, key=ids.index), f'{at}.members', 'are cards, in card order')
        for member in members if ok else ():
            other = grouped.setdefault(member, k)
            need(other == k, f'{at}.members', f'{member} is in one group')
    panels_problems(doc['panels'], cards, need, keys)
    return out


def _symbol_problems(symbol, where, need, keys):
    """A symbol: its base, its prime (`'` or nothing) and its subscript, and its text from them."""
    if not keys(symbol, SYMBOL, where):
        return None
    base, prime, sub = symbol['base'], symbol['prime'], symbol['sub']
    ok = _text(base) and prime in ('', "'") and isinstance(sub, str) and _text(symbol['latex'])
    text = f'{base}{prime}' + (f'_{sub}' if sub else '') if ok else None
    need(ok and symbol['text'] == text, f'{where}.text', 'is its base, its prime and its subscript')
    return symbol['text']


def _start_keys(data):
    """The keys that a start's tree names (a node of the notation as a dict), or None when it is not
    a node of the notation."""
    try:
        node = notation.from_dict(data)
    except (KeyError, TypeError, ValueError):
        return None
    out = set()
    for part in notation.nodes(node):
        if isinstance(part, (notation.Sym, notation.Elapsed, notation.Deriv)):
            out.add(part.key)
        elif isinstance(part, (notation.Since, notation.Count)):
            out.add(part.target)
    return out


def _marks_problems(marks, where, need):
    """Marks: [number, kind] pairs, sorted by number, each number once."""
    ok = isinstance(marks, list) and all(
        isinstance(mark, list) and len(mark) == 2 and _whole(mark[0]) and mark[1] in REFERENCE_KINDS
        for mark in marks
    )
    numbers = [mark[0] for mark in marks] if ok else []
    need(ok and numbers == sorted(set(numbers)), where, 'is a sorted list of [number, kind]')
    return [tuple(mark) for mark in marks] if ok else []


def panels_problems(found, cards, need, keys):
    """The contract of the panels under the map (D-53, D-55), null or `{settings, equations, symbols,
    references, tags, note}`:
    - the settings are in their ranges, and the kinds of entry keep "assumption";
    - each block stands for cards of the picture, in the order of the cards, and each line has its
      trees in the form of its kind, the keys that it names, its marks and its LaTeX;
    - each key that a line names has one row of the Symbols table, every row is named by a line or a
      tag, and no two rows have one symbol (or an event's count);
    - only an input and a fixed value have marks, and a range has its status;
    - each mark names an entry of its kind, each entry is cited by a mark and has an http or https link
      or none, and without `references` there are no entries and no marks;
    - each tag is a stock of a card of a block, with the symbol of its row;
    - the note shows exactly when the Symbols table shows a chosen range."""
    if found is None or not keys(found, PANELS, 'panels'):
        return
    settings = found['settings']
    if keys(settings, PANEL_SETTINGS, 'panels.settings'):
        for name, (low, high) in PANEL_RANGES.items():
            value = settings[name]
            need(_whole(value, low) and value <= high, f'panels.settings.{name}', f'is {low} to {high}')
        for name in ('tags', 'symbols', 'checks', 'references'):
            need(isinstance(settings[name], bool), f'panels.settings.{name}', 'is true or false')
        need(
            settings['instances'] in ('together', 'each'), 'panels.settings.instances', 'is together or each'
        )
        kinds = settings['kinds']
        need(
            isinstance(kinds, list)
            and kinds == [kind for kind in REFERENCE_KINDS if kind in kinds]
            and 'assumption' in kinds,
            'panels.settings.kinds',
            'are kinds of entry in their order, assumption among them',
        )
    else:
        settings = {'references': True, 'symbols': True, 'kinds': list(REFERENCE_KINDS)}
    order = {card['id']: k for k, card in enumerate(cards) if isinstance(card, dict)}
    stocks = {
        item['key']: card['id']
        for card in cards
        if isinstance(card, dict)
        for item in card.get('stocks') or ()
        if isinstance(item, dict)
    }
    cited, named, shown = [], set(), set()
    blocks = found['equations'] if isinstance(found['equations'], list) else [None]
    firsts = []
    for b, item in enumerate(blocks):
        where = f'panels.equations[{b}]'
        if not keys(item, BLOCK, where):
            continue
        need(_text(item['name']), f'{where}.name', 'is a text')
        need(isinstance(item['title'], str), f'{where}.title', 'is a text')
        need(item['template'] is None or _text(item['template']), f'{where}.template', 'is a text or null')
        need(
            item['subscript'] is None or (_text(item['subscript']) and item['name'] == item['template']),
            f'{where}.subscript',
            "is the template's subscript of a block that stands for a template, or null",
        )
        members = item['members'] if isinstance(item['members'], list) else []
        need(bool(members), f'{where}.members', 'is a list of one member or more')
        for m, member in enumerate(members):
            at = f'{where}.members[{m}]'
            if keys(member, MEMBER, at):
                need(_text(member['entity']), f'{at}.entity', 'is a text')
                need(member['card'] in order, f'{at}.card', 'is a card of the picture')
                need(isinstance(member['title'], str), f'{at}.title', 'is a text')
                need(
                    member['subscript'] is None or _text(member['subscript']),
                    f'{at}.subscript',
                    'is a text or null',
                )
                shown.add(member['card'])
        need(
            len(members) < 2 or item['template'] is not None,
            f'{where}.template',
            'names the template of a group',
        )
        if members and isinstance(members[0], dict) and members[0].get('card') in order:
            firsts.append(order[members[0]['card']])
        lines = item['lines'] if isinstance(item['lines'], list) else [None]
        for k, line in enumerate(lines):
            at = f'{where}.lines[{k}]'
            if not keys(line, LINE, at):
                continue
            kind = line['kind']
            need(kind in LINE_KINDS, f'{at}.kind', 'is a kind of line')
            equation = kind in EQUATION_KINDS
            trees = [line['lhs'], line['rhs']] if equation else line['math']
            ok = isinstance(trees, list) and trees and all(isinstance(tree, dict) for tree in trees)
            if ok:
                try:
                    for tree in trees:
                        notation.from_dict(tree)
                except (KeyError, TypeError, ValueError):
                    ok = False
            need(
                ok and (line['math'] == [] if equation else (line['lhs'], line['rhs']) == (None, None)),
                at,
                'has lhs and rhs for an equation, else its trees in math, each a node of the notation',
            )
            need(line['words'] is None or _text(line['words']), f'{at}.words', 'is a text or null')
            need(line['part'] is None or _text(line['part']), f'{at}.part', 'is a text or null')
            need((line['event'] is None) == (kind != 'jump'), f'{at}.event', 'names the event of a jump')
            need(line['outcome'] is None or _text(line['outcome']), f'{at}.outcome', 'is a text or null')
            need(
                line['relation'] == '=' or (line['relation'] == '⇔' and kind == 'formula'),
                f'{at}.relation',
                'is "=", or "⇔" for a formula',
            )
            need(
                (line['when'] is None) == (kind != 'jump') and (line['when'] is None or _text(line['when'])),
                f'{at}.when',
                'says when a jump happens, in words',
            )
            listed = line['keys'] if isinstance(line['keys'], list) else []
            need(
                isinstance(line['keys'], list)
                and all(_text(key) for key in listed)
                and len(set(listed)) == len(listed),
                f'{at}.keys',
                'is a list of keys, each once',
            )
            named.update(listed)
            cited += [(mark, f'{at}.marks') for mark in _marks_problems(line['marks'], f'{at}.marks', need)]
            records = line['records']
            need(
                isinstance(records, list) and all(_text(r) for r in records),
                f'{at}.records',
                'is a list of names',
            )
            need(_text(line['latex']), f'{at}.latex', 'is a text')
    need(firsts == sorted(firsts), 'panels.equations', 'are in the order of the cards')
    rows = found['symbols'] if isinstance(found['symbols'], list) else [None]
    by_key, texts, ranged, start_named = {}, [], False, set()

    def start(data, at, kind):
        # A start that a formula sets: a node of the notation that names a value, of a stock, a
        # tally or a state.
        if data is None:
            return
        found = _start_keys(data)
        need(found and kind in ('stock', 'tally', 'state'), at, 'is null, or the formula of a start')
        start_named.update(found or ())

    for r, row in enumerate(rows):
        where = f'panels.symbols[{r}]'
        if not keys(row, ROW, where):
            continue
        key = row['key']
        need(_text(key) and key not in by_key, f'{where}.key', 'is a key, each once')
        by_key[key] = row
        texts.append(_symbol_problems(row['symbol'], f'{where}.symbol', need, keys))
        kind = row['kind']
        need(kind is None or kind in ROW_KINDS, f'{where}.kind', 'is a kind of value, a flow or an event')
        if row['count'] is not None:
            need(kind == 'event', f'{where}.count', 'is the count of an event')
            texts.append(_symbol_problems(row['count'], f'{where}.count', need, keys))
        need(_text(row['meaning']), f'{where}.meaning', 'is a text')
        for name in ('unit', 'value', 'distribution'):
            need(row[name] is None or _text(row[name]), f'{where}.{name}', 'is a text or null')
        start(row['value_math'], f'{where}.value_math', kind)
        need(
            row['value_math'] is None or _text(row['value']),
            f'{where}.value',
            'is the text of a formula start',
        )
        options = row['options'] if isinstance(row['options'], list) else [None]
        need(len(options) <= 3, f'{where}.options', 'lists three options at most')
        need(
            _whole(row['option_count'], 0) and row['option_count'] >= len(options),
            f'{where}.option_count',
            'counts the options',
        )
        # An input's and a fixed value's marks, and those of a start that the file writes as a value.
        marked = kind in ('input', 'fixed') or (
            kind in ('stock', 'tally', 'state') and row['value_math'] is None
        )
        for o, given in enumerate(options):
            at = f'{where}.options[{o}]'
            if keys(given, ('option', 'value', 'math', 'marks'), at):
                need(_text(given['option']), f'{at}.option', 'is a text')
                need(given['value'] is None or _text(given['value']), f'{at}.value', 'is a text or null')
                start(given['math'], f'{at}.math', kind)
                need(
                    given['math'] is None or _text(given['value']),
                    f'{at}.value',
                    'is the text of a formula start',
                )
                own = _marks_problems(given['marks'], f'{at}.marks', need)
                need(marked or not own, f'{at}.marks', 'are marks of an input, a fixed value or a start')
                cited += [(mark, f'{at}.marks') for mark in own]
        instances = row['instances']
        need(
            isinstance(instances, list)
            and all(
                isinstance(item, dict) and list(item) == ['entity', 'title', 'value', 'math']
                for item in instances
            ),
            f'{where}.instances',
            'is a list of {entity, title, value, math}',
        )
        for i, item in enumerate(instances if isinstance(instances, list) else ()):
            if isinstance(item, dict):
                start(item.get('math'), f'{where}.instances[{i}].math', kind)
                need(
                    item.get('math') is None or _text(item.get('value')),
                    f'{where}.instances[{i}].value',
                    'is the text of a formula start',
                )
        span = row['range']
        ok = span is None or (
            isinstance(span, list) and len(span) == 2 and all(edge is None or _text(edge) for edge in span)
        )
        need(ok, f'{where}.range', 'is null or [lo, hi]')
        need(
            (span is None) == (row['range_status'] is None)
            and row['range_status'] in (None, 'chosen', 'declared'),
            f'{where}.range_status',
            'is chosen or declared for a range, else null',
        )
        need(span is None or kind == 'input', f'{where}.range', 'is the range of an input')
        ranged = ranged or (span is not None and row['range_status'] == 'chosen')
        for name in ('marks', 'range_marks'):
            own = _marks_problems(row[name], f'{where}.{name}', need)
            need(marked or not own, f'{where}.{name}', 'are marks of an input, a fixed value or a start')
            cited += [(mark, f'{where}.{name}') for mark in own]
        need(span is not None or not row['range_marks'], f'{where}.range_marks', 'are the marks of a range')
        records = row['records']
        need(
            isinstance(records, list) and all(_text(r) for r in records),
            f'{where}.records',
            'is a list of names',
        )
    shown_texts = [text for text in texts if text is not None]
    need(
        len(set(shown_texts)) == len(shown_texts),
        'panels.symbols',
        'have one symbol each, and no two the same',
    )
    need(named <= set(by_key), 'panels.symbols', 'have a row for each key that a line names')
    need(start_named <= set(by_key), 'panels.symbols', "have a row for each key that a start's formula names")
    tags = found['tags']
    ok = isinstance(tags, dict)
    need(ok, 'panels.tags', 'is {stock key: symbol}')
    for key, text in tags.items() if ok else ():
        need(
            stocks.get(key) in shown and key in by_key and by_key[key]['symbol'].get('text') == text,
            f'panels.tags.{key}',
            'is a stock of a card of a block, with the symbol of its row',
        )
    need(
        set(by_key) <= named | set(tags if ok else ()) | start_named,
        'panels.symbols',
        "are each named by a line, a tag or a start's formula",
    )
    entries = found['references'] if isinstance(found['references'], list) else [None]
    kinds = {}
    for e, entry in enumerate(entries):
        where = f'panels.references[{e}]'
        if not keys(entry, ENTRY, where):
            continue
        need(entry['number'] == e + 1, f'{where}.number', 'counts from 1')
        need(entry['kind'] in settings['kinds'], f'{where}.kind', 'is a kind that the list holds')
        need(_text(entry['label']) and isinstance(entry['text'], str), where, 'has its words')
        url = entry['url']
        need(
            url is None or (isinstance(url, str) and url.split(':', 1)[0] in ('http', 'https')),
            f'{where}.url',
            'is an http or https address, or null',
        )
        need(isinstance(entry['hover'], str), f'{where}.hover', 'is a text')
        need(isinstance(entry['record'], list), f'{where}.record', 'is a list of names')
        kinds[entry['number']] = entry['kind']
    for (number, kind), at in cited:
        need(kinds.get(number) == kind, at, f'mark {number} names an entry of kind {kind}')
    need(set(kinds) <= {number for (number, _), _ in cited}, 'panels.references', 'are each cited by a mark')
    need(
        settings['references'] or (not cited and not kinds),
        'panels.references',
        'has no entry and no mark without references',
    )
    left_out = found['left_out']
    need(
        isinstance(left_out, list)
        and all(kind in REFERENCE_KINDS and kind not in settings['kinds'] for kind in left_out)
        and left_out == [kind for kind in REFERENCE_KINDS if kind in left_out]
        and (settings['references'] or not left_out),
        'panels.left_out',
        'lists the kinds that the list leaves out, in order',
    )
    note = found['note']
    need(note is None or _text(note), 'panels.note', 'is a text or null')
    need(
        (note is not None) == (ranged and settings['symbols']),
        'panels.note',
        'shows exactly with a chosen range',
    )


def triggers_problems(card, where, need, keys):
    """The contract of what a card shows of its events (D-56): null, or `{level, lines, events, more}`.
    Each event is of the card and named once, its full line starts with its name, and its text is null,
    or its name at `names` and its line at `rules`; the events with a text come first, and `more` counts
    the others at `names` and `rules`."""
    found = card['triggers']
    if found is None or not keys(found, TRIGGERS, where):
        return
    level = found['level']
    need(level in TRIGGER_LEVELS, f'{where}.level', 'is count, names, rules or hover')
    lines = found['lines']
    need(_whole(lines) and lines <= TRIGGER_LINES, f'{where}.lines', f'is 1 to {TRIGGER_LINES}')
    events = found['events'] if isinstance(found['events'], list) else [None]
    named = [item.get('event') for item in events if isinstance(item, dict)]
    need(len(set(named)) == len(named), f'{where}.events', 'name each event once')
    prefix, shown = f'{card["id"]}.', []
    for k, item in enumerate(events):
        at = f'{where}.events[{k}]'
        if not keys(item, TRIGGER_EVENT, at):
            continue
        need(_text(item['event']) and item['event'].startswith(prefix), f'{at}.event', f'starts {prefix}')
        need(_text(item['name']), f'{at}.name', 'is a text')
        need(
            _text(item['full']) and item['full'].startswith(str(item['name'])),
            f'{at}.full',
            'is a text that starts with the name',
        )
        own = {'names': item['name'], 'rules': item['full']}.get(level)
        text = item['text']
        need(
            text is None or (own is not None and text == own),
            f'{at}.text',
            'is null, the name at names, or the line at rules',
        )
        need(item['label'] is None or _text(item['label']), f'{at}.label', 'is a text or null')
        need(item['rule'] is None or _text(item['rule']), f'{at}.rule', 'is a text or null')
        shown.append(text is not None)
    need(shown == sorted(shown, reverse=True), f'{where}.events', 'with a text come first')
    more = found['more']
    rest = shown.count(False) if level in ('names', 'rules') else 0
    need(_whole(more, 0) and more == rest, f'{where}.more', 'counts the events without a text')


@pytest.mark.parametrize(
    ('change', 'found'),
    [
        (lambda doc: doc.pop('groups'), 'picture: has the keys'),
        (lambda doc: doc.update(legend=['pipe']), 'picture: has the keys'),
        (lambda doc: doc['cards'][0].update(role='crew'), 'cards[0].role'),
        (lambda doc: doc['cards'][0]['place'].update(row=0), 'cards[0].place.row'),
        (lambda doc: doc['cards'][1].update(place=dict(doc['cards'][0]['place'])), 'cards[1].place'),
        (lambda doc: doc['cards'][1]['stocks'][0].update(kind='state'), 'cards[1].stocks[0].kind'),
        (lambda doc: doc['cards'][1].update(stock_order=['elsewhere.store']), 'cards[1].stock_order'),
        (
            lambda doc: doc['cards'][1].update(stock_order=[doc['cards'][1]['stocks'][0]['key']] * 2),
            'cards[1].stock_order',
        ),
        (lambda doc: doc['cards'][1]['pipes'][0].update(to='elsewhere.store'), 'cards[1].pipes[0].to'),
        (lambda doc: doc['cards'][0]['machines'][0]['transitions'][0].update(to='lost'), 'transitions[0].to'),
        (
            lambda doc: doc['cards'][0]['machines'][0]['transitions'][0].update(by='nobody'),
            'transitions[0].by',
        ),
        (lambda doc: doc['arrows'].reverse(), 'arrows: are sorted'),
        (lambda doc: doc['arrows'][0].update(count=9), 'arrows[0].count'),
        (lambda doc: doc['groups'][0]['members'].reverse(), 'groups[0].members'),
        (lambda doc: doc['cards'][0]['triggers'].update(level='all'), 'cards[0].triggers.level'),
        (lambda doc: doc['cards'][0]['triggers'].update(lines=5), 'cards[0].triggers.lines'),
        (lambda doc: doc['cards'][0]['triggers'].update(more=1), 'cards[0].triggers.more'),
        (
            lambda doc: doc['cards'][0]['triggers']['events'][0].update(event='plant.strike'),
            'cards[0].triggers.events[0].event',
        ),
        (
            lambda doc: doc['cards'][0]['triggers']['events'][0].update(text='another text'),
            'cards[0].triggers.events[0].text',
        ),
        (lambda doc: doc['cards'][0]['triggers']['events'][0].pop('rule'), 'cards[0].triggers.events[0]'),
    ],
)
def test_the_contract_check_finds_each_broken_part(change, found):
    doc = contract_picture()
    assert picture_problems(doc) == []
    change(doc)
    assert any(found in problem for problem in picture_problems(doc))


def contract_picture():
    """The picture of the system map's fixture model, with a stylesheet that places, groups and moves a
    state machine."""
    sheet = style.read(
        FIXTURE_STYLE
        + '\n[place]\nattacker = { column = 1, row = 1 }\nplant = { column = 2, row = 1 }\n'
        + '\n[group]\n"Site" = ["plant", "operators"]\n'
        + '\n[state.plant]\nvalve = "beside"\n'
        + '\n[triggers]\nrules = ["attacker"]\ncount = ["operators"]\n'
    )
    model = fixture_model()
    assert style.check(sheet, model) == []
    return picture(model, sheet)


def test_the_picture_of_the_fixture_model_keeps_the_contract():
    doc = contract_picture()
    assert picture_problems(doc) == []
    for run in fixture_model().runs:
        assert picture_problems(picture(fixture_model(), run=run)) == []


def test_the_frozen_example_keeps_the_contract():
    """The layout and the SVG are built on `picture.json` (WP E2's frozen example): it keeps the same
    contract as each picture that `picture` gives."""
    assert picture_problems(json.loads(FROZEN.read_text(encoding='utf-8'))) == []


# ---- the parts of a card ----------------------------------------------------------------------------


def world(*declarations, option_groups=None, run_lines=None):
    groups = option_groups or (options('Response', option('Default', 'The defaults.')),)
    return compiled(document('Picture fixture', *declarations, option_groups=groups, run_lines=run_lines))


def card_of(doc, card):
    return next(item for item in doc['cards'] if item['id'] == card)


def arrows_of(doc):
    return {(a['from'], a['to'], a['kind']): a['values'] for a in doc['arrows']}


PLANT = entity(
    'plant',
    stock('store', 100),
    stock('spare', 50),
    stock('released', kind='tally'),
    stock('vented'),
    parameter('level', 3, 'people', 0, 9),
    flow('escape', 'store -> released', '0.5 per_h * store'),
    flow('leak', 'store -> released', '0.1 per_h * store'),
    flow('vent', 'store ->', '0.2 per_h * store'),
    flow('refill', '-> spare', '1 people/h'),
    flow('mark', ['store -> vented', '-> released'], '0.01 per_h * store'),
    share('store', '1000 people/h'),
    role='operator',
)


def test_each_stock_and_pipe_of_a_card_and_each_moves_arrow():
    model = world(
        PLANT,
        entity(
            'town',
            stock('shelter'),
            flow('evacuate', 'plant.spare -> shelter', '0.1 per_h * plant.spare'),
            flow('take', ['plant.store -> shelter', 'outside -> plant.released'], '1 people/h'),
            role='community',
        ),
    )
    doc = picture(model, style.Style())
    plant, town = card_of(doc, 'plant'), card_of(doc, 'town')
    # Each stock and tally of the file, in its order: the input is neither.
    assert [(s['key'], s['kind']) for s in plant['stocks']] == [
        ('plant.store', 'stock'),
        ('plant.spare', 'stock'),
        ('plant.released', 'tally'),
        ('plant.vented', 'tally'),
    ]
    # Two flows between the same two stocks are one pipe; a pair to or from outside has one stock; each
    # pair of a flow of two pairs is a pipe of its own.
    assert [(p['from'], p['to'], p['flows']) for p in plant['pipes']] == [
        ('plant.store', 'plant.released', ['plant.escape', 'plant.leak']),
        ('plant.store', None, ['plant.vent']),
        (None, 'plant.spare', ['plant.refill']),
        ('plant.store', 'plant.vented', ['plant.mark']),
        (None, 'plant.released', ['plant.mark']),
    ]
    # The town's flows move the plant's stocks: arrows of kind moves, and no pipe.
    assert [s['key'] for s in town['stocks']] == ['town.shelter'] and town['pipes'] == []
    assert arrows_of(doc) == {
        ('town', 'plant', 'moves'): ['plant.released', 'plant.spare', 'plant.store'],
        ('plant', 'town', 'reads'): ['plant.spare'],
    }
    assert {a['count'] for a in doc['arrows']} == {3, 1}
    assert picture_problems(doc) == []


def test_a_hidden_thing_is_absent_with_its_arrows_and_transitions():
    model = world(
        entity(
            'plant', named('valve', 'closed', 'open', records='@fixture'), stock('store', 10), role='operator'
        ),
        entity(
            'operators',
            event('isolate', 'plant.valve is "open"', 'plant.valve = "closed"', do_records='@fixture'),
            role='responder',
        ),
        entity(
            'attacker',
            event('strike', 't >= 1 h', 'plant.valve = "open"', do_records='@fixture'),
            role='adversary',
        ),
    )
    shown, hidden = (
        picture(model, style.Style()),
        picture(model, style.read('[layout]\nhide = ["operators"]\n')),
    )
    (valve,) = card_of(shown, 'plant')['machines']
    assert {t['by'] for t in valve['transitions']} == {'operators', 'attacker'}
    # Hidden: no card, no arrow to or from it, and no transition of its events.
    assert [card['id'] for card in hidden['cards']] == ['plant', 'attacker']
    assert all('operators' not in (a['from'], a['to']) for a in hidden['arrows'])
    (valve,) = card_of(hidden, 'plant')['machines']
    assert [(t['event'], t['to']) for t in valve['transitions']] == [('attacker.strike', 'open')]
    # Only the subtitle's facts name it (D-59): nothing else of the picture does.
    assert 'operators' not in json.dumps({key: value for key, value in hidden.items() if key != 'facts'})
    assert hidden['facts']['hidden'] == [card_of(shown, 'operators')['title']]
    assert picture_problems(hidden) == []


ACCESS = options(
    'Access',
    option('None', 'No access.'),
    option('Kept', 'Kept access.', 'attacker.access = "kept"  @fixture'),
)


def access_model(run_lines=None):
    """An attacker that gets in when its access is "none" and then opens the plant's valve: a run that
    starts with the access kept (`b`) never gets in."""
    return world(
        entity(
            'plant',
            named('valve', 'closed', 'open', records='@fixture'),
            stock('store', 100),
            stock('released', kind='tally'),
            flow('escape', 'store -> released', '0.5 per_h * store', condition='valve is "open"'),
            role='operator',
        ),
        entity(
            'attacker',
            named('access', 'none', 'kept', records='@fixture'),
            event(
                'get_in', 'access is "none"', 'access = "kept"', 'plant.valve = "open"', do_records='@fixture'
            ),
            role='adversary',
        ),
        option_groups=(ACCESS,),
        run_lines=run_lines or runs(a=['None'], b=['Kept']),
    )


def test_a_run_leaves_out_what_cannot_act_in_it():
    model = access_model()
    a, b = picture(model, run='a'), picture(model, run='b')
    assert (a['run'], b['run']) == ('a', 'b')
    # In b, the access starts kept, so the attacker never gets in and never opens the valve.
    assert ('attacker', 'plant', 'changes') in arrows_of(a)
    assert ('attacker', 'plant', 'changes') not in arrows_of(b)
    events = lambda doc: {  # noqa: E731
        t['event'] for card in doc['cards'] for m in card['machines'] for t in m['transitions']
    }
    assert events(a) == {'attacker.get_in'} and events(b) == set()
    # Then nothing changes or reads the access: it has no machine in b.
    assert [m['var'] for m in card_of(a, 'attacker')['machines']] == ['attacker.access']
    assert card_of(b, 'attacker')['machines'] == []
    for doc in (a, b):
        assert picture_problems(doc) == []
    with pytest.raises(ValueError, match='not a run'):
        picture(model, run='c')


def joined(pictures):
    """The parts of the pictures of each run, joined: what the picture without a run draws. A part is
    drawn when one run draws it; an arrow's values are the values of each run, its count the largest,
    and a transition is from any state when one run has it so."""
    cards, arrows = {}, {}
    for doc in pictures:
        for card in doc['cards']:
            found = cards.setdefault(card['id'], {'stocks': set(), 'pipes': {}, 'machines': {}})
            found['stocks'].update(s['key'] for s in card['stocks'])
            for pipe in card['pipes']:
                found['pipes'].setdefault((pipe['from'], pipe['to']), set()).update(pipe['flows'])
            for machine in card['machines']:
                moves = found['machines'].setdefault(machine['var'], {})
                for t in machine['transitions']:
                    key = (t['event'], t['to'], t['by'])
                    before = moves.get(key, set())
                    moves[key] = None if t['from'] is None or before is None else before | set(t['from'])
        for a in doc['arrows']:
            item = arrows.setdefault((a['from'], a['to'], a['kind']), [0, set()])
            item[0] = max(item[0], a['count'])
            item[1].update(a['values'])
    return cards, arrows


def parts_of(doc):
    """The parts of one picture, in the form of `joined`."""
    return joined([doc])


def test_the_picture_without_a_run_joins_the_pictures_of_every_run():
    for model in (access_model(), fixture_model()):
        whole = picture(model, style.Style())
        each = [picture(model, style.Style(), run) for run in model.runs]
        assert parts_of(whole) == joined(each)
        assert [card['id'] for card in whole['cards']] == [card['id'] for card in each[0]['cards']]


# ---- the kinds of the arrows (D-50) -----------------------------------------------------------------


def kinds_model(*lines_of_a, reads_of_b=None):
    """`a` acts on `b`: its event `go` has the lines `lines_of_a`. `b` has a named state `mode`, an event
    `f` that only a line fires, and, with `reads_of_b`, an event `see` whose condition reads `a`. `b` is
    first in the file, so that the order of the file never puts `a` before it."""
    b = [named('mode', 'off', 'on', records='@fixture'), named_event('f', 'mode = "on"')]
    if reads_of_b is not None:
        b.append(event('see', reads_of_b))
    return world(
        entity('b', *b, role='operator'),
        entity(
            'a',
            parameter('level', 3, 'people', 0, 9),
            event('go', 't >= 1 h', *lines_of_a, do_records='@fixture'),
            role='operator',
        ),
    )


def test_a_line_that_fires_another_card_s_event_is_a_fires_arrow():
    doc = picture(kinds_model('b.f'))
    assert arrows_of(doc) == {('a', 'b', 'fires'): ['b.f']}
    assert [a['how'] for a in doc['arrows']] == [[]]
    assert picture_problems(doc) == []


def test_a_read_of_when_another_card_s_event_happened_is_a_follows_arrow():
    # since() and count() read the times of a's event: the arrow goes from a to b, which reads.
    for condition in ('since(a.go) >= 2 h', 'count(a.go) > 0'):
        doc = picture(kinds_model(reads_of_b=condition))
        assert arrows_of(doc) == {('a', 'b', 'follows'): ['a.go']}, condition
        assert picture_problems(doc) == []


def test_a_read_of_another_card_s_value_stays_a_reads_arrow():
    doc = picture(kinds_model(reads_of_b='a.level > 4 people'))
    assert arrows_of(doc) == {('a', 'b', 'reads'): ['a.level']}


def test_a_line_that_fires_and_a_line_that_sets_give_two_arrows():
    # A counterexample to one arrow for each pair: firing b's event and setting b's state are other kinds.
    doc = picture(kinds_model('b.f', 'b.mode = "on"'))
    assert arrows_of(doc) == {('a', 'b', 'fires'): ['b.f'], ('a', 'b', 'changes'): ['b.mode']}
    changes = next(a for a in doc['arrows'] if a['kind'] == 'changes')
    assert changes['how'] == ['sets']
    assert picture_problems(doc) == []


def test_a_fires_arrow_ranks_its_cards_and_a_follows_arrow_does_not():
    def columns(doc):
        return {card.id: card.column for card in layout(doc).cards}

    # a fires b's event, so b goes in a later column than a, although b is first in the file.
    fired = columns(picture(kinds_model('b.f')))
    assert fired['a'] < fired['b']
    # b follows a's event: that ranks nothing, so neither card goes after the other.
    followed = columns(picture(kinds_model(reads_of_b='since(a.go) >= 2 h')))
    assert followed['a'] == followed['b']


def test_a_card_names_its_template_copies_role_and_actor():
    model = world(
        template('Ward', stock('people'), flow('arrive', '-> people', '1 people/h'), role='community'),
        entity('wards', template='Ward', copies=3),
        entity('north', template='Ward'),
        entity('crew', stock('x'), role='crew'),
        entity('meter', stock('y'), role=None),
        '\n'.join(
            [
                'operator:  @fixture',
                '    "An operator who decides."',
                '    role operator',
                '    sees meter.y',
                '    event decide once when meter.y >= 1 people:  @fixture',
                '        choice',
                '        act 0.5:',
                '            "It acts."',
                '        wait else:',
                '            "It waits."',
            ]
        ),
    )
    doc = picture(model, style.Style())
    found = {
        card['id']: (card['template'], card['copies'], card['role'], card['actor']) for card in doc['cards']
    }
    # A role that names a thing, and no role, are no role of the six; only a thing that sees and has a
    # choice is an actor.
    assert found == {
        'wards': ('Ward', 3, 'community', False),
        'north': ('Ward', 1, 'community', False),
        'crew': (None, 1, None, False),
        'meter': (None, 1, None, False),
        'operator': (None, 1, 'operator', True),
    }
    # The copies of one line share its card, its stocks and its pipes.
    wards = card_of(doc, 'wards')
    assert [s['key'] for s in wards['stocks']] == ['wards.people']
    assert [p['flows'] for p in wards['pipes']] == [['wards.arrive']]
    assert picture_problems(doc) == []


# ---- the state machines ----------------------------------------------------------------------------

STATES = entity(
    'plant',
    named('x', 'a', 'b', 'c', records='@fixture'),
    named('y', 'b', 'a', records='@fixture'),
    'input plan: "c" | "a" = "c"  @fixture',
    # From the states that each `when` gives, the state that the line gives left out.
    event('to_b', 'x is "a"', 'x = "b"', do_records='@fixture'),
    event('to_c', 'x is not "c"', 'x = "c"', do_records='@fixture'),
    event('back', 'x is "a" or x is "b"', 'x = "a"', do_records='@fixture'),
    event('later', 'x is "b" and t >= 1 h', 'x = "c"', do_records='@fixture'),
    event('loose', 'x is "c" or y is "a"', 'x = "a"', do_records='@fixture'),
    event('either', 'not (x is "a")', 'x = "b" if t > 3 h else "a"', do_records='@fixture'),
    event('vague', 'not (x is "a" and y is "a")', 'x = "b"', do_records='@fixture'),
    event('stays', 'x is "b"', 'x = "b"', do_records='@fixture'),
    # A line that gives another named state, or a named input, gives each of its states.
    event('mirror', 't >= 4 h', 'x = y', do_records='@fixture'),
    event('planned', 't >= 5 h', 'x = plan', do_records='@fixture'),
    # The chance of an outcome that is a condition, and the condition of an outcome.
    event('checked', 't >= 6 h', 'x = "a"', condition='x is "c"', do_records='@fixture'),
    '\n'.join(
        [
            'event offered once when t >= 7 h:  @fixture',
            '    up 0.5 when x is "b":',
            '        x = "c"',
            '    stay else:',
        ]
    ),
    role='operator',
)


def test_each_event_that_sets_a_named_state_is_a_transition_from_the_states_where_it_can_happen():
    model = world(
        STATES,
        entity(
            'operators',
            event('reset', 'plant.x is "c"', 'plant.x = "a"', do_records='@fixture'),
            role='responder',
        ),
    )
    doc = picture(model, style.Style())
    (x, y) = card_of(doc, 'plant')['machines']
    assert (x['var'], x['states'], x['initial'], x['place']) == ('plant.x', ['a', 'b', 'c'], 'a', 'inside')
    assert [(t['event'], t['to'], t['from'], t['by']) for t in x['transitions']] == [
        # Another thing's event that sets x.
        ('operators.reset', 'a', ['c'], 'operators'),
        # x is "a" or "b": to "a" from "b", and the line that keeps "a" is no transition.
        ('plant.back', 'a', ['b'], 'plant'),
        # The outcome's chance is the condition x is "c".
        ('plant.checked', 'a', ['c'], 'plant'),
        # not (x is "a"): "b" or "c"; each branch of the `if` is a state that the line gives.
        ('plant.either', 'a', ['b', 'c'], 'plant'),
        ('plant.either', 'b', ['c'], 'plant'),
        # `and`: the states of its part that names x.
        ('plant.later', 'c', ['b'], 'plant'),
        # `or` with a part that does not name x narrows nothing: from any state.
        ('plant.loose', 'a', None, 'plant'),
        # y's states, in x's order; and from any state, since nothing narrows x.
        ('plant.mirror', 'a', None, 'plant'),
        ('plant.mirror', 'b', None, 'plant'),
        # The condition of the outcome.
        ('plant.offered', 'c', ['b'], 'plant'),
        # The named input's states.
        ('plant.planned', 'a', None, 'plant'),
        ('plant.planned', 'c', None, 'plant'),
        # x is "a": to "b".
        ('plant.to_b', 'b', ['a'], 'plant'),
        # x is not "c": "a" or "b".
        ('plant.to_c', 'c', ['a', 'b'], 'plant'),
        # `not` of an `and` with a part that names y: x can be any state where it holds.
        ('plant.vague', 'b', None, 'plant'),
    ]
    # The event that only keeps x's state is no transition.
    assert not any(t['event'] == 'plant.stays' for t in x['transitions'])
    # Nothing sets y, so its machine has its states and no transition.
    assert (y['var'], y['states'], y['initial'], y['transitions']) == ('plant.y', ['b', 'a'], 'b', [])
    assert picture_problems(doc) == []


def test_a_state_that_only_an_option_sets_has_its_states_and_no_transitions():
    model = world(
        entity(
            'gate',
            named('plan', 'shut', 'open', records='@fixture'),
            named('door', 'closed', 'opened', records='@fixture'),
            event('opens', 'plan is "open" and t >= 1 h', 'door = "opened"', do_records='@fixture'),
            role='operator',
        ),
        option_groups=(
            options(
                'Plan',
                option('Shut', 'Kept shut.'),
                option('Open', 'Opened.', 'gate.plan = "open"  @fixture'),
            ),
        ),
        run_lines=runs(shut=['Shut'], open=['Open']),
    )
    machine = lambda doc, var: next(  # noqa: E731
        m for m in card_of(doc, 'gate')['machines'] if m['var'] == var
    )
    whole, opened = picture(model, style.Style()), picture(model, style.Style(), 'open')
    # The start value is the file's, or the run's when its option sets it.
    assert (machine(whole, 'gate.plan')['initial'], machine(opened, 'gate.plan')['initial']) == (
        'shut',
        'open',
    )
    for doc in (whole, opened):
        plan = machine(doc, 'gate.plan')
        assert (plan['states'], plan['transitions']) == (['shut', 'open'], [])
        assert [(t['event'], t['to']) for t in machine(doc, 'gate.door')['transitions']] == [
            ('gate.opens', 'opened')
        ]
    # When the plan stays shut, the door never opens: neither state acts in that run.
    assert card_of(picture(model, style.Style(), 'shut'), 'gate')['machines'] == []


# ---- the stylesheet -----------------------------------------------------------------------------------


def styled_model():
    return world(
        template(
            'Ward',
            named('alarm', 'quiet', 'ringing', records='@fixture'),
            stock('people', 10),
            event('rings', 'people >= 5 people', 'alarm = "ringing"', do_records='@fixture'),
            role='community',
        ),
        entity('east', template='Ward'),
        entity('west', template='Ward'),
        entity('south', template='Ward'),
        entity('north', stock('z'), role='environment'),
        entity('depot', stock('w'), role='operator'),
    )


def test_the_stylesheet_places_groups_and_marks_the_cards():
    model = styled_model()
    sheet = style.read(
        '[place]\nWard = { column = 2, row = 3 }\nwest = { column = 4 }\nnorth = { column = 1 }\n'
        '\n[group]\n"Area" = ["depot", "Ward"]\n'
        '\n[icon]\nhouse = ["Ward"]\nshop = ["south"]\n'
        '\n[state.Ward]\nalarm = "beside"\n\n[state.south]\nalarm = "hidden"\n'
    )
    assert style.check(sheet, model) == []
    doc = picture(model, sheet)
    cards = {card['id']: card for card in doc['cards']}
    # A template places each of its instances on its row and the rows after it; a thing's own place, icon
    # and machine place win over its template's.
    assert {card: cards[card]['place'] for card in cards} == {
        'east': {'column': 2, 'row': 3},
        'west': {'column': 4, 'row': None},
        'south': {'column': 2, 'row': 4},
        'north': {'column': 1, 'row': None},
        'depot': None,
    }
    assert {card: cards[card]['icon'] for card in ('east', 'west', 'south')} == {
        'east': 'house',
        'west': 'house',
        'south': 'shop',
    }
    assert {card: cards[card]['machines'][0]['place'] for card in ('east', 'west', 'south')} == {
        'east': 'beside',
        'west': 'beside',
        'south': 'hidden',
    }
    # The members of a group, in the order of the cards.
    assert doc['groups'] == [{'label': 'Area', 'members': ['east', 'west', 'south', 'depot']}]
    assert doc['direction'] == 'left-to-right'
    assert picture_problems(doc) == []


def test_the_stocks_table_gives_the_rows_of_a_card_and_an_instance_s_own_list_wins():
    # D-52. In each ward, a flow takes from beds and one from sick, so both are stocks; cured is only
    # filled, so it is a tally.
    model = world(
        template(
            'Ward',
            stock('beds', 10),
            stock('sick'),
            stock('cured'),
            flow('fall', 'beds -> sick', '1 people/h'),
            flow('cure', 'sick -> cured', '1 people/h'),
            role='community',
        ),
        entity('east', template='Ward'),
        entity('west', template='Ward'),
    )
    assert all(card['stock_order'] is None for card in picture(model, style.Style())['cards'])
    sheet = style.read(
        '[stocks]\nWard = ["cured", "beds"]\neast = ["sick"]\n'
        '\n[layout]\nstocks = 3\ncards_per_column = 4\ncard_width = 220\n'
    )
    assert style.check(sheet, model) == []
    doc = picture(model, sheet)
    assert picture_problems(doc) == []
    # The numbers of [layout] are the picture's settings, for the layout.
    numbers = ('stocks', 'cards_per_column', 'card_width')
    assert [doc['settings'][key] for key in numbers] == [3, 4, 220]
    assert {card['id']: card['stock_order'] for card in doc['cards']} == {
        'east': ['east.sick'],
        'west': ['west.cured', 'west.beds'],
    }
    # The layout shows the listed rows only, the stocks above the tallies, and "+n" for the others.
    cards = {card.id: card for card in layout(doc).cards}
    east, west = cards['east'], cards['west']
    assert ([s.key for s in east.stocks], [m.key for m in east.meters]) == (['east.sick'], [])
    assert sorted(east.more.keys) == ['east.beds', 'east.cured']
    assert ([s.key for s in west.stocks], [m.key for m in west.meters]) == (['west.beds'], ['west.cured'])
    assert list(west.more.keys) == ['west.sick']


def test_a_hidden_machine_leaves_no_mark_in_the_legend():
    model = world(
        entity(
            'gate',
            named('door', 'closed', 'opened', records='@fixture'),
            event('opens', 't >= 1 h', 'door = "opened"', do_records='@fixture'),
            role='operator',
        ),
    )

    def marks(sheet):
        return [mark for mark, _, _ in layout(picture(model, sheet)).legend.items]

    assert marks(style.Style()) == ['state', 'transition']
    assert marks(style.read('[state.gate]\ndoor = "hidden"\n')) == []


def test_hiding_one_instance_hides_it_alone_with_its_arrows_and_transitions():
    model = world(
        entity(
            'plant', named('valve', 'closed', 'open', records='@fixture'), stock('store', 10), role='operator'
        ),
        template(
            'Crew',
            event('open', 'plant.valve is "closed"', 'plant.valve = "open"', do_records='@fixture'),
            role='responder',
        ),
        entity('east', template='Crew'),
        entity('west', template='Crew'),
    )
    sheet = style.read('[layout]\nhide = ["east"]\n')
    assert style.check(sheet, model) == []
    shown, hidden = picture(model, style.Style()), picture(model, sheet)
    assert [card['id'] for card in shown['cards']] == ['plant', 'east', 'west']
    assert [card['id'] for card in hidden['cards']] == ['plant', 'west']
    ends = lambda doc: {(a['from'], a['to'], a['kind']) for a in doc['arrows']}  # noqa: E731
    assert ends(hidden) == {end for end in ends(shown) if 'east' not in end[:2]}
    assert ('west', 'plant', 'changes') in ends(hidden)
    by = lambda doc: [t['by'] for t in card_of(doc, 'plant')['machines'][0]['transitions']]  # noqa: E731
    assert (by(shown), by(hidden)) == (['east', 'west'], ['west'])
    # Only the subtitle's facts name it (D-59): nothing else of the picture does.
    assert 'east' not in json.dumps({key: value for key, value in hidden.items() if key != 'facts'})
    assert hidden['facts']['hidden'] == [card_of(shown, 'east')['title']]
    assert picture_problems(hidden) == []


# ---- determinism -------------------------------------------------------------------------------------

SCRIPT = 'import json\nfrom tests.draw.test_picture import busy_picture\nprint(json.dumps(busy_picture()))\n'


def busy_picture():
    """A picture with many joined parts: transitions whose states join, arrows of several values, places,
    groups, machine places, and the panels of every card with their references."""
    model = world(
        STATES,
        entity(
            'operators',
            event('reset', 'plant.x is "c"', 'plant.x = "a"', do_records='@fixture'),
            event('look', 'plant.x is "b" or plant.y is "a"', 'plant.y = "b"', do_records='@fixture'),
            role='responder',
        ),
        PLANT.replace('plant', 'works', 1),
        entity(
            'town',
            stock('shelter'),
            flow('take', ['works.store -> shelter', 'outside -> works.released'], '1 people/h'),
            role='community',
        ),
    )
    sheet = style.read(
        '[place]\nplant = { column = 1, row = 1 }\n\n[group]\n"Site" = ["works", "town"]\n'
        '\n[state.plant]\ny = "beside"\n'
        '\n[equations]\nthings = ["plant", "operators", "works", "town"]\n\n[references]\nshow = true\n'
    )
    return picture(model, sheet)


def test_the_picture_is_the_same_for_every_hash_seed():
    found = []
    for seed in ('0', '4242'):
        env = {**os.environ, 'PYTHONHASHSEED': seed, 'PYTHONPATH': str(ROOT)}
        done = subprocess.run(
            [sys.executable, '-B', '-c', SCRIPT],
            cwd=ROOT,
            env=env,
            capture_output=True,
            text=True,
            timeout=300,
            check=False,
        )
        assert done.returncode == 0, done.stderr
        found.append(done.stdout)
    assert found[0] == found[1]
    assert json.loads(found[0]) == busy_picture()


# ---- every scenario ----------------------------------------------------------------------------------


def undeclared(model, doc):
    """The names of a picture that its model does not declare: a card that is no entity line, a stock
    that is no stock or tally of its card, a flow or an event that no entity of its card has, a state that
    is not one of its var's, and a value of an arrow that its card does not have."""
    lines = {}
    for thing in model.scenario.entities:
        lines.setdefault(thing.entry, []).append(thing)
    out = []

    def member(key):
        card, _, name = key.partition('.')
        return card, name, lines.get(card, [])

    for card in doc['cards']:
        if card['id'] not in lines:
            out.append(card['id'])
            continue
        first = lines[card['id']][0]
        for item in card['stocks']:
            _, name, _ = member(item['key'])
            value = first.value(name)
            if value is None or value.kind != item['kind']:
                out.append(item['key'])
        for pipe in card['pipes']:
            for name in pipe['flows']:
                _, flow_name, things = member(name)
                if not any(f.name == flow_name for thing in things for f in thing.flows):
                    out.append(name)
        for machine in card['machines']:
            _, name, _ = member(machine['var'])
            value = first.value(name)
            if value is None or value.kind != 'state' or list(value.type) != machine['states']:
                out.append(machine['var'])
            for move in machine['transitions']:
                by, event_name, things = member(move['event'])
                if by != move['by'] or not any(
                    e.name == event_name for thing in things for e in thing.events
                ):
                    out.append(move['event'])
                if move['to'] not in machine['states']:
                    out.append(move['to'])
    for arrow in doc['arrows']:
        for key in arrow['values']:
            _, name, things = member(key)
            owned = {
                part.name
                for thing in things
                for part in (*thing.values, *thing.flows, *thing.events, *thing.allocations)
            }
            if not things or member(key)[0] not in (arrow['from'], arrow['to']) or name not in owned:
                out.append(key)
    return out


@pytest.mark.parametrize('scenario_id', SCENARIO_IDS)
@pytest.mark.scenario_contract
def test_the_picture_of_every_scenario_keeps_the_contract_and_names_what_its_model_declares(scenario_id):
    model = catalogue_model(scenario_id)
    sheet = style.of(model)
    whole = picture(model, sheet)
    assert [card['id'] for card in whole['cards']] == style.drawn(sheet, model)
    each = [picture(model, sheet, run) for run in model.runs]
    for doc in (whole, *each):
        assert picture_problems(doc) == []
        assert undeclared(model, doc) == []
        check_facts(model, sheet, doc)
    assert parts_of(whole) == joined(each)


def check_facts(model, sheet, doc):
    """The facts of a picture are the model's (D-59): its run and the run it is compared with, the
    number of runs it joins, the horizon and the names that `[layout] hide` leaves out; exactly the card
    of the start's thing has the start mark; each card's file is a file of the model."""
    facts, run = doc['facts'], doc['run']
    if run is None:
        assert facts['run'] is None and facts['runs'] == len(model.runs)
    else:
        versus = model.runs[run]['comparison_of']
        assert facts['run'] == {
            'name': run,
            'label': model.runs[run]['name'],
            'options': list(model.runs[run]['options']),
            'versus': None if versus is None else model.runs[versus]['name'],
        }
    horizon = model.scenario.horizon
    assert facts['horizon'] == (None if horizon is None else horizon.written)
    lines = style.entity_lines(model)
    assert facts['hidden'] == sorted(
        card_title(lines[name]) if name in lines else name for name in sheet.hide
    )
    begins = model.scenario.start
    things = {
        entity.entry: {e.name for e in model.scenario.entities if e.entry == entity.entry}
        for entity in model.scenario.entities
    }
    for card in doc['cards']:
        assert card['starts'] == (begins is not None and begins.entity in things[card['id']])
    # The model's own file, and the files that its lines name (a model of one file names none).
    files = {Path(path).resolve() for path in (*model.files.values(), model.origin)}
    package = paths.package_of(model.origin)
    for card in doc['cards']:
        # Each card of a model of a package names a file of the model, a model of one file too.
        if package is not None:
            assert card['file'] is not None and (package / card['file']).resolve() in files, card['id']


def test_the_facts_name_the_run_its_comparison_and_what_is_hidden():
    # b is compared with a: the facts give the labels of both runs, as the model names them.
    model = access_model(run_lines=block('runs:', 'a = "None"', 'b = "Kept" versus a'))
    sheet = style.Style()
    for doc in (picture(model, sheet), picture(model, sheet, 'a'), picture(model, sheet, 'b')):
        assert picture_problems(doc) == []
        check_facts(model, sheet, doc)
    assert picture(model, sheet, 'b')['facts']['run']['versus'] == model.runs['a']['name']
    hiding = style.Style(hide=('plant',))
    assert picture(model, hiding)['facts']['hidden'] == [card_of(picture(model, sheet), 'plant')['title']]
    # The subtitle has a line for the comparison and what is hidden, and the cards go below it.
    for doc in (picture(model, sheet, 'b'), picture(model, hiding)):
        found = layout(doc)
        assert len(found.subtitle) == 2
        assert model.runs['a']['name'] in found.subtitle[1] or 'Plant' in found.subtitle[1]
        top = min(card.box.y for card in found.cards)
        assert top >= layouts.MARGIN + layouts.TITLE_AREA + layouts.SUBTITLE_LINE


def test_the_thing_of_the_start_has_the_start_mark_and_options_set_a_start():
    model = world(
        entity('plant', named('valve', 'closed', 'open', records='@fixture'), role='operator'),
        entity('attacker', named('access', 'none', 'kept', records='@fixture'), role='adversary'),
        start('attacker', 'plant.valve = "open"', do_records='@fixture'),
        option_groups=(ACCESS,),
        run_lines=runs(a=['None'], b=['Kept']),
    )
    doc = picture(model)
    assert [card['id'] for card in doc['cards'] if card['starts']] == ['attacker']
    # The option Kept sets the start of the attacker's access: its machine says so, in its key too.
    (access,) = card_of(doc, 'attacker')['machines']
    assert access['starts_by'] == [{'option': 'Kept', 'state': 'kept'}]
    (valve,) = card_of(doc, 'plant')['machines']
    assert valve['starts_by'] == []
    found = layout(doc)
    (machine,) = next(card for card in found.cards if card.id == 'attacker').machines
    assert 'Kept (kept)' in ' '.join(text for number, text, _ in machine.key if number == '')
    assert [card.id for card in found.cards if card.starts] == ['attacker']
