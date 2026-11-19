"""What `napkin draw` draws (`model_map.picture`): the cards with their stocks, pipes and state machines,
the arrows between them, and the groups. The legend is the layout's (tests/draw/test_layout.py).

Each model of these tests writes its things in its own lines, so each expectation follows from the text
of the test and from the rule that the test names. `picture_problems` checks a picture against the
contract between `picture` and the layout and SVG (layout.py, svg.py), from the document alone: the
frozen example `picture.json` passes it, and so does each picture of these tests and of the catalogue
(`test_catalogue.py`).
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from napkin.draw import notation, style
from napkin.draw.model_map import picture
from tests.draw.models import WORKS, WORKS_STYLE, compiled, package, works

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
CHANGE_WORDS = ('sets', 'adds', 'takes', 'shares', 'solves')
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
ROW_KINDS = ('input', 'fixed', 'stock', 'tally', 'state', 'formula', 'flow', 'event', 'text')
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
        if run is not None and keys(run, ('name', 'label', 'options'), 'facts.run'):
            need(run['name'] == doc['run'], 'facts.run.name', 'is the run of the picture')
            need(_text(run['label']), 'facts.run.label', 'is a text')
            options = run['options']
            need(
                isinstance(options, list) and all(_text(o) for o in options),
                'facts.run.options',
                'is a list of options',
            )
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
            lambda doc: doc['cards'][0]['triggers']['events'][0].update(event='plant.alarm'),
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


CONTRACT_STYLE = WORKS_STYLE + (
    '\n[place]\nattacker = { column = 1, row = 1 }\nplant = { column = 2, row = 1 }\n'
    '\n[group]\n"Site" = ["plant", "crews"]\n'
    '\n[state.plant]\nmode = "beside"\n'
    '\n[triggers]\nrules = ["attacker"]\ncount = ["crews"]\n'
)


def contract_picture():
    """The picture of the water works, with a stylesheet that places, groups and moves a state
    machine."""
    sheet = style.read(CONTRACT_STYLE)
    model = works()
    assert style.check(sheet, model) == []
    return picture(model, sheet)


def test_the_picture_of_the_water_works_keeps_the_contract():
    assert picture_problems(contract_picture()) == []
    for run in (None, 'base', 'attack'):
        assert picture_problems(picture(works(), style.Style(), run=run)) == []


def test_the_frozen_example_keeps_the_contract():
    """The layout and the SVG are built on `picture.json` (WP E2's frozen example): it keeps the same
    contract as each picture that `picture` gives."""
    assert picture_problems(json.loads(FROZEN.read_text(encoding='utf-8'))) == []


# ---- the parts of a card ----------------------------------------------------------------------------


def card_of(doc, card):
    return next(item for item in doc['cards'] if item['id'] == card)


def arrows_of(doc):
    return {(arrow['from'], arrow['to'], arrow['kind']): arrow for arrow in doc['arrows']}


def test_each_stock_and_pipe_of_a_card_and_each_moves_arrow():
    doc = picture(works(), style.Style())
    plant = card_of(doc, 'plant')
    # Raw water: the treatment takes from it; treated water: the supplies take from it; the water
    # treated: a flow only fills it, so it is a tally (by use).
    stocks = [(item['key'], item['kind']) for item in plant['stocks']]
    assert stocks == [('plant.raw', 'stock'), ('plant.treated', 'stock'), ('plant.treated_total', 'tally')]
    pipes = [(pipe['from'], pipe['to'], pipe['flows'], pipe['label']) for pipe in plant['pipes']]
    assert pipes == [
        (None, 'plant.raw', ['plant.intake'], 'Intake'),
        ('plant.raw', 'plant.treated', ['plant.treat'], 'Treatment'),
        (None, 'plant.treated_total', ['plant.count'], 'Count'),
    ]
    # The supplies of the town and of the hospital take from the plant's treated water: arrows of the
    # kind "moves", and no pipe; each zone fills from the town.
    arrows = arrows_of(doc)
    assert arrows[('town', 'plant', 'moves')]['values'] == ['plant.treated']
    assert arrows[('hospital', 'plant', 'moves')]['values'] == ['plant.treated']
    assert arrows[('north', 'town', 'moves')]['values'] == ['town.stored']
    assert card_of(doc, 'town')['pipes'] == []
    assert [item['key'] for item in card_of(doc, 'town')['stocks']] == ['town.stored']


def test_a_hidden_thing_is_absent_with_its_arrows():
    doc = picture(works(), style.read(WORKS_STYLE))
    assert 'hospital' not in [card['id'] for card in doc['cards']]
    assert not [arrow for arrow in doc['arrows'] if 'hospital' in (arrow['from'], arrow['to'])]
    assert doc['facts']['hidden'] == ['Hospital']
    assert picture_problems(doc) == []


def test_a_run_leaves_out_the_events_that_it_cannot_start():
    model = works()
    base, attack, joined = (picture(model, style.Style(), run=run) for run in ('base', 'attack', None))
    # Without the AI the attacker cannot break in, so it never gains access, holds it or takes over
    # (the reachability of the run's configuration, D16).
    transitions = {
        name: [item['event'] for item in card_of(doc, 'attacker')['machines'][0]['transitions']]
        for name, doc in (('base', base), ('attack', attack), ('joined', joined))
    }
    assert transitions == {
        'base': [],
        'attack': ['attacker.break_in', 'attacker.hold'],
        'joined': ['attacker.break_in', 'attacker.hold'],
    }
    assert ('attacker', 'plant', 'changes') not in arrows_of(base)
    assert arrows_of(attack)[('attacker', 'plant', 'changes')]['values'] == ['plant.mode']
    # Joined, an event is drawn when one run can start it; the count is the largest of the runs.
    assert (
        arrows_of(joined)[('attacker', 'plant', 'changes')]
        == arrows_of(attack)[('attacker', 'plant', 'changes')]
    )
    assert (joined['facts']['runs'], base['facts']['runs']) == (2, 1)


def test_a_statement_that_starts_an_event_of_another_card_is_a_fires_arrow():
    arrows = arrows_of(picture(works(), style.Style()))
    assert arrows[('plant', 'crews', 'fires')]['values'] == ['crews.repair']
    assert arrows[('plant', 'crews', 'fires')]['how'] == []


def test_a_read_of_when_another_card_s_event_started_is_a_follows_arrow():
    model = compiled(
        """
        a:
            go = event():
                after 0 h
        b:
            waited = formula(since(a.go))
            starts = formula(count(a.go.occurrences))
            level: L = 0 L
        c:
            seen = formula(b.level)

        a.go.start()
        """
    )
    arrows = arrows_of(picture(model, style.Style()))
    assert arrows[('a', 'b', 'follows')]['values'] == ['a.go']
    assert arrows[('b', 'c', 'reads')]['values'] == ['b.level']
    assert ('a', 'b', 'reads') not in arrows


def test_a_change_names_how_it_changes():
    arrows = arrows_of(picture(works(), style.Style()))
    # The crews set the mode of the plant; the plant's treated water shares out the supplies by its
    # allocation, and the take over of the attacker sets the mode too.
    assert arrows[('crews', 'plant', 'changes')]['how'] == ['sets']
    assert arrows[('plant', 'town', 'changes')] == {
        'from': 'plant',
        'to': 'town',
        'kind': 'changes',
        'count': 1,
        'values': ['town.supply'],
        'how': ['shares'],
    }


# A template with a table of three rows and a member, and three things written once: a crew, a meter and
# an operator that decides at random.
CARDS = """
Ward:
    people: people = 0 people
    flow arrive: SOURCE -> this.people
        request = 1 people/h
wards: Ward from "wards.csv"
north: Ward
crew:
    x: people = 0 people
meter:
    y: people = 0 people
operator:
    forecast = categorical(ACT: 0.5, WAIT: 0.5)
    decide = event():
        order: enum[ACT, WAIT] = WAIT
        after 0 h:
            order = operator.forecast.draw()
            switch order:
                ACT:
                    meter.y += 1 people
                WAIT:
                    meter.y -= 1 people

operator.decide.start()
"""
WARDS = {'wards.csv': 'id\na\nb\nc\n'}
# Who plays the parts of CARDS: the template, whose rows and member it gives the role; the crew, whose
# role is a word that is none of the six; the operator. The meter has no role.
CARDS_ROLES = '[role]\ncommunity = ["Ward"]\ncrew = ["crew"]\noperator = ["operator"]\n'


def test_a_card_names_its_template_copies_and_role():
    doc = picture(compiled(CARDS, tables=WARDS), style.read(CARDS_ROLES))
    found = {card['id']: (card['template'], card['copies'], card['role']) for card in doc['cards']}
    # A role that is none of the six, and no role, are no role.
    assert found == {
        'wards': ('Ward', 3, 'community'),
        'north': ('Ward', 1, 'community'),
        'crew': (None, 1, None),
        'meter': (None, 1, None),
        'operator': (None, 1, 'operator'),
    }
    # The rows of one table share its card, its stocks and its pipes.
    wards = card_of(doc, 'wards')
    assert [item['key'] for item in wards['stocks']] == ['wards.people']
    assert [pipe['flows'] for pipe in wards['pipes']] == [['wards.arrive']]
    assert picture_problems(doc) == []


# ---- the state machines ----------------------------------------------------------------------------

STATES = """
plant:
    x: enum[A, B, C] = A
    y: enum[A, B, C] = B
    input plan: enum[A, B, C] = C
    z: enum[A, B, C] = this.plan
    to_b = event():
        when this.x == A:
            this.to_b.start()
        after 0 h:
            this.x = B
    to_c = event():
        when this.x != C:
            this.to_c.start()
        after 0 h:
            this.x = C
    back = event():
        when this.x == A or this.x == B:
            this.back.start()
        after 0 h:
            this.x = A
    later = event():
        when this.x == B and t >= 1 h:
            this.later.start()
        after 0 h:
            this.x = C
    loose = event():
        when this.x == C or this.y == A:
            this.loose.start()
        after 0 h:
            this.x = A
    either = event():
        when not (this.x == A):
            this.either.start()
        after 0 h:
            this.x = B if t > 3 h else A
    vague = event():
        when not (this.x == A and this.y == A):
            this.vague.start()
        after 0 h:
            this.x = B
    stays = event():
        when this.x == B:
            this.stays.start()
        after 0 h:
            this.x = B
    mirror = event():
        when t >= 4 h:
            this.mirror.start()
        after 0 h:
            this.x = this.y
    waits = event():
        when this.x == A:
            this.waits.start()
        after 1 h:
            this.x = C
    guarded = event():
        when t >= 6 h:
            this.guarded.start()
        after 0 h when this.x == C:
            this.x = A
    branched = event():
        when t >= 7 h:
            this.branched.start()
        after 0 h:
            if this.x == B:
                this.x = C
    switched = event():
        when t >= 8 h:
            this.switched.start()
        after 0 h:
            switch this.x:
                A:
                    this.x = B
"""
# Who plays the plant of STATES.
STATES_ROLES = '[role]\noperator = ["plant"]\n'
# STATES with options that start the named state `z` in two states.
PLANS = (
    'scenario "Plans"\n    horizon 10 h\n\noptions "Plan":\n    "Planned A":\n        "A."\n'
    '        plant.plan = A\n    "Planned B":\n        "B."\n        plant.plan = B\n' + STATES
)


def test_each_assignment_of_a_named_state_is_a_transition_from_the_states_where_it_can_run():
    doc = picture(compiled(STATES), style.read(STATES_ROLES))
    (x,) = [machine for machine in card_of(doc, 'plant')['machines'] if machine['var'] == 'plant.x']
    assert (x['states'], x['initial']) == (['A', 'B', 'C'], 'A')
    found = {(item['event'].rpartition('.')[2], item['to']): item['from'] for item in x['transitions']}
    assert found == {
        # The triggers of an event narrow the states when they are its only start and its first stage
        # runs at once: `==` gives its state, `!=` the others, `or` and `and` join and meet them.
        ('to_b', 'B'): ['A'],
        ('to_c', 'C'): ['A', 'B'],
        ('back', 'A'): ['B'],
        ('later', 'C'): ['B'],
        # A part that does not narrow the states: `or` narrows nothing, `not` of an inexact part too.
        ('loose', 'A'): None,
        ('vague', 'B'): None,
        # `not` of an exact part gives the other states; each branch of a conditional is a state.
        ('either', 'A'): ['B', 'C'],
        ('either', 'B'): ['C'],
        # A read of a value of the enum gives each of its members.
        ('mirror', 'A'): None,
        ('mirror', 'B'): None,
        ('mirror', 'C'): None,
        # A stage after a delay: the state may change in the meantime, so the trigger narrows nothing.
        ('waits', 'C'): None,
        # The guard of a stage, a branch and the case of a switch on the state narrow it.
        ('guarded', 'A'): ['C'],
        ('branched', 'C'): ['B'],
        ('switched', 'B'): ['A'],
    }
    # A transition that only keeps its state is absent.
    assert ('stays', 'B') not in found
    assert all(item['by'] == 'plant' for item in x['transitions'])
    assert picture_problems(doc) == []


def test_an_option_that_sets_the_input_of_a_start_shows_on_its_machine():
    doc = picture(compiled(PLANS), style.read(STATES_ROLES))
    (z,) = [machine for machine in card_of(doc, 'plant')['machines'] if machine['var'] == 'plant.z']
    assert z['starts_by'] == [{'option': 'Planned A', 'state': 'A'}, {'option': 'Planned B', 'state': 'B'}]
    # Its start is no member that the file writes.
    assert z['initial'] is None and z['transitions'] == []


# ---- the stylesheet, the facts and the start ---------------------------------------------------------


def test_the_stylesheet_places_groups_and_marks_the_cards():
    doc = contract_picture()
    attacker, plant = card_of(doc, 'attacker'), card_of(doc, 'plant')
    assert (attacker['place'], plant['place']) == ({'column': 1, 'row': 1}, {'column': 2, 'row': 1})
    assert doc['groups'] == [{'label': 'Site', 'members': ['plant', 'crews']}]
    assert plant['icon'] == 'factory' and plant['machines'][0]['place'] == 'beside'
    assert attacker['icon'] == style.ROLE_ICONS['adversary']
    assert (attacker['triggers']['level'], card_of(doc, 'crews')['triggers']['level']) == ('rules', 'count')
    assert [event['event'] for event in attacker['triggers']['events']] == [
        'attacker.break_in',
        'attacker.hold',
        'attacker.take_over',
    ]


def test_the_stocks_table_gives_the_rows_of_a_card():
    doc = picture(works(), style.read('[stocks]\nplant = ["treated_total", "raw"]\n'))
    assert card_of(doc, 'plant')['stock_order'] == ['plant.treated_total', 'plant.raw']
    assert card_of(doc, 'town')['stock_order'] is None


def test_the_facts_name_the_run_its_options_and_what_is_hidden():
    model = works()
    doc = picture(model, style.read(WORKS_STYLE), run='attack')
    assert doc['facts'] == {
        'run': {'name': 'attack', 'label': 'An attack with an AI', 'options': ['Attacker AI']},
        'runs': 1,
        'horizon': '48 h',
        'hidden': ['Hospital'],
    }
    assert picture(model, style.Style(), run='base')['facts']['run']['label'] == 'base'
    assert picture(model, style.Style())['facts'] == {'run': None, 'runs': 2, 'horizon': '48 h', 'hidden': []}
    with pytest.raises(ValueError, match='nowhere'):
        picture(model, style.Style(), run='nowhere')


def test_the_card_whose_event_the_setup_starts_has_the_start_mark(tmp_path):
    model = package(
        tmp_path / 'started',
        """
        scenario "Started"
            horizon 10 h

        a:
            go = event():
                after 0 h

        b:
            stay = event():
                after 0 h

        a.go.start()
        """,
    )
    doc = picture(model)
    assert [(card['id'], card['starts'], card['file']) for card in doc['cards']] == [
        ('a', True, 'model.scn'),
        ('b', False, 'model.scn'),
    ]
    assert doc['name'] == 'started'


SCRIPT = (
    'import json, sys\n'
    'from napkin.draw import style\n'
    'from napkin.draw.model_map import picture\n'
    'from tests.draw.models import works\n'
    'sys.stdout.write(json.dumps(picture(works(), style.read(sys.argv[1])), sort_keys=True))\n'
)


def test_the_picture_is_the_same_for_every_hash_seed():
    here = json.dumps(contract_picture(), sort_keys=True)
    for seed in ('0', '4242'):
        env = {**os.environ, 'PYTHONHASHSEED': seed, 'PYTHONPATH': str(ROOT)}
        done = subprocess.run(
            [sys.executable, '-B', '-c', SCRIPT, CONTRACT_STYLE],
            cwd=ROOT,
            env=env,
            capture_output=True,
            text=True,
            timeout=300,
            check=False,
        )
        assert done.returncode == 0, done.stderr
        assert done.stdout == here


def test_the_water_works_text_is_the_fixture():
    # The fixture of the other tests of the picture is this text.
    assert compiled(WORKS).declared.scenario.title.startswith('A water works')
