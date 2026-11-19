"""The SVG of a picture (napkin/draw/svg.py), by its properties: it parses, it stands alone, it themes
for light and dark, it is the same text every time, and each `data-*` attribute names a part of the
picture (and, for a picture of a model, a part of the model).

`check_svg(picture, found, text)` holds every property; the catalogue test and the tests of
`napkin draw` use it too.
"""

from __future__ import annotations

import hashlib
import itertools
import json
import os
import re
import subprocess
import sys
import xml.etree.ElementTree as ET
from pathlib import Path
from urllib.parse import urlsplit

import pytest
from hypothesis import given
from hypothesis import strategies as st

from napkin.draw import icons, typeset
from napkin.draw.defaults import ARROW_LOOKS, DEFAULT_LOOKS
from napkin.draw.layout import KINDS, MARKS, TEXT_SIZE, layout
from napkin.draw.model_map import picture, settings_of
from napkin.draw.references import COLOUR_KIND, web_host
from napkin.draw.svg import COLOURS, LINKS, NAMESPACE, NOT_DRAWN, XLINK, css_string, svg
from tests.draw.models import WORKS_STYLE, works
from tests.draw.test_layout import SHAPE, arrow, bundling, check, load, marks_drawn, picture_of, pictures
from tests.draw.test_layout import card as sample_card

ROOT = Path(__file__).resolve().parents[2]
SVG = f'{{{NAMESPACE}}}'
# The kinds of parts that the SVG draws, by their class, and the attribute that names each.
PARTS = {
    'card': ('data-thing',),
    'stock': ('data-stock',),
    'tally': ('data-stock',),
    'more': ('data-stock',),
    'pipe': ('data-flow',),
    'machine': ('data-var',),
    'state': (),
    'transition': ('data-event',),
    'trigger': ('data-event',),
    'arrow': ('data-from', 'data-to', 'data-kind'),
    'bundle': ('data-from', 'data-kind'),
    'group': ('data-group',),
    'mark': ('data-mark',),
    # The panels (D-53, D-55, D-57) and the tags of the stock rows.
    'block': ('data-block',),
    'equation': ('data-latex',),
    'symbol': ('data-key',),
    'reference': ('data-number',),
    'tag': ('data-key',),
}


def kind_of(element):
    classes = (element.get('class') or '').split()
    return next((cls for cls in classes if cls in PARTS), None)


def parts(root):
    """[(kind, element, the card or machine that holds it)] of every part of the SVG, in document
    order."""
    out = []

    def walk(element, card, machine):
        kind = kind_of(element) if element.tag == f'{SVG}g' else None
        if kind == 'card':
            card = element.get('data-thing')
        if kind == 'machine':
            machine = element.get('data-var')
        if kind is not None:
            out.append((kind, element, card, machine))
        for child in element:
            walk(child, card, machine)

    walk(root, None, None)
    return out


def check_svg(picture, found, text):
    """Every property of the SVG `text` of `picture` and its layout `found`."""
    root = ET.fromstring(text)
    assert root.tag == f'{SVG}svg' and root.get('role') == 'img'
    title, desc = root[0], root[1]
    assert title.tag == f'{SVG}title' and title.text and desc.tag == f'{SVG}desc' and desc.text
    assert root.get('aria-labelledby') == f'{title.get("id")} {desc.get("id")}'
    assert (root.get('width'), root.get('height')) == tuple(root.get('viewBox').split()[2:])
    check_alone(root, text)
    check_theme(root)
    check_parts(picture, found, root)
    check_links(picture, found, root)
    check_hover(found, root)
    check_panels(picture, found, root)


def check_alone(root, text):
    """No script, image or external file: the icons are symbols, and each reference is to the file. The
    one exception is a link `<a>` of the References list, to an `http` or `https` address (D-55), which
    `check_panels` holds to its entry."""
    tags = {element.tag.split('}')[-1] for element in root.iter()}
    assert not tags & {'script', 'image', 'foreignObject', 'iframe', 'audio', 'video'}
    assert '@import' not in text and '@font-face' not in text
    links = {id(element) for element in root.iter(f'{SVG}a')}
    for element in root.iter():
        for key, value in element.attrib.items():
            if key.startswith('on'):
                pytest.fail(f'an event handler: {key}')
            for found in re.findall(r'url\(([^)]*)\)', value):
                assert found.startswith('#'), value
            if key.endswith('href') and id(element) in links:
                assert urlsplit(value).scheme in ('http', 'https') and web_host(value), value
            elif key.endswith('href'):
                assert value.startswith('#'), value
    ids = {element.get('id') for element in root.iter() if element.get('id')}
    for element in root.iter():
        for key, value in element.attrib.items():
            for found in re.findall(r'url\(#([^)]*)\)', value):
                assert found in ids
            if key.endswith('href') and id(element) not in links:
                assert value[1:] in ids
    # The icons are symbols drawn in currentColor; each symbol is used.
    symbols = [e for e in root.iter(f'{SVG}symbol')]
    used = {e.get('href')[1:] for e in root.iter(f'{SVG}use')}
    assert {s.get('id') for s in symbols} == used
    for symbol in symbols:
        assert symbol.get('id').removeprefix('icon-') in icons.SHAPES
        assert 'currentColor' in ET.tostring(symbol, encoding='unicode')


def check_theme(root):
    """CSS custom properties for light and dark, every one defined in both, and a light colour as a
    presentation attribute on each shape and text."""
    style = ''.join(e.text or '' for e in root.iter(f'{SVG}style'))
    light, _, rest = style.partition('@media (prefers-color-scheme: dark)')
    assert rest, 'no dark block'
    used = set(re.findall(r'var\(--([a-z-]+)\)', style))
    defined_light = set(re.findall(r'--([a-z-]+):#', light))
    defined_dark = set(re.findall(r'--([a-z-]+):#', rest))
    assert used <= defined_light and used <= defined_dark and defined_light == defined_dark == set(COLOURS)
    defs = {id(e) for d in root.iter(f'{SVG}symbol') for e in d.iter()}
    styled = set(re.findall(r'\.([a-z][a-z0-9-]*)', style))
    # The classes whose rules paint each property; every `<text>` has the ink of its theme.
    painted = {key: set() for key in ('fill', 'stroke', 'color')}
    for selectors, body in re.findall(r'([^{}]+)\{([^{}]*)\}', style):
        for key, found in painted.items():
            if re.search(rf'(?:^|;){key}:var\(--', body):
                found |= set(re.findall(r'\.([a-z][a-z0-9-]*)', selectors))
    for element in root.iter():
        tag = element.tag.split('}')[-1]
        if id(element) in defs or tag not in ('rect', 'path', 'circle', 'text', 'line', 'tspan'):
            continue
        if tag != 'tspan':
            assert element.get('fill') or element.get('stroke'), ET.tostring(element, encoding='unicode')[
                :120
            ]
        # A colour of its own is the light fallback: a rule of the style gives the colour of each theme,
        # a rule of one of its classes that paints that property (a `<text>`'s fill: the rule of `text`).
        own = set((element.get('class') or '').split())
        for key in ('fill', 'stroke', 'color'):
            if element.get(key, '').startswith('#'):
                assert own & styled, ET.tostring(element, encoding='unicode')[:120]
                assert own & painted[key] or (tag == 'text' and key == 'fill'), (
                    key,
                    ET.tostring(element, encoding='unicode')[:120],
                )


def check_parts(picture, found, root):
    """Each part has its tooltip and its `data-*` attribute, which names a part of the picture; every
    part of the layout is drawn; the legend shows what the layout draws."""
    cards = {card['id']: card for card in picture['cards']}
    machines = {m['var']: m for card in picture['cards'] for m in card['machines']}
    arrows = {(a['from'], a['to'], a['kind']) for a in picture['arrows']}
    labels = {group['label'] for group in picture.get('groups', ())}
    panels = picture.get('panels') or {}
    blocks = {block['name'] for block in panels.get('equations') or ()}
    latex = {line['latex'] for block in panels.get('equations') or () for line in block['lines']}
    rows = {row['key'] for row in panels.get('symbols') or ()}
    numbers = {str(entry['number']) for entry in panels.get('references') or ()}
    seen = {kind: [] for kind in PARTS}
    for kind, element, card, machine in parts(root):
        tooltip = element[0]
        assert tooltip.tag == f'{SVG}title' and tooltip.text, kind
        for key in PARTS[kind]:
            assert key in element.attrib, (kind, key)
        seen[kind].append(element)
        if kind == 'card':
            assert element.get('data-thing') in cards
            # Every level of `[triggers]` puts the full line of each event in the tooltip (D-56).
            for event in (cards[element.get('data-thing')].get('triggers') or {}).get('events', ()):
                assert event['full'] in tooltip.text
        elif kind in ('stock', 'tally', 'more'):
            keys = {stock['key'] for stock in cards[card]['stocks']}
            assert set(element.get('data-stock').split()) <= keys
        elif kind == 'pipe':
            flows = {flow for pipe in cards[card]['pipes'] for flow in pipe['flows']}
            assert element.get('data-flow').split() and set(element.get('data-flow').split()) <= flows
        elif kind == 'machine':
            assert element.get('data-var') in machines
            assert machines[element.get('data-var')]['place'] != 'hidden'
        elif kind == 'state':
            given = machines[machine]
            if 'data-state' in element.attrib:
                assert element.get('data-state') in given['states']
        elif kind == 'transition':
            events = {t['event'] for t in machines[machine]['transitions']}
            assert element.get('data-event').split() and set(element.get('data-event').split()) <= events
        elif kind == 'trigger':
            events = {e['event'] for e in (cards[card].get('triggers') or {}).get('events', ())}
            assert set(element.get('data-event').split()) <= events
        elif kind == 'arrow':
            assert (element.get('data-from'), element.get('data-to'), element.get('data-kind')) in arrows
        elif kind == 'bundle':
            assert element.get('data-from') in cards and element.get('data-kind') in KINDS
        elif kind == 'group':
            assert element.get('data-group') in labels
        elif kind == 'mark':
            assert element.get('data-mark') in MARKS
        elif kind == 'block':
            assert element.get('data-block') in blocks
        elif kind == 'equation':
            assert element.get('data-latex') in latex
        elif kind == 'symbol':
            assert element.get('data-key') in rows
        elif kind == 'reference':
            assert element.get('data-number') in numbers
        elif kind == 'tag':
            assert element.get('data-key') in panels['tags']
            assert element.get('data-key') in {stock['key'] for stock in cards[card]['stocks']}
    # Every part of the layout is drawn once.
    assert [e.get('data-thing') for e in seen['card']] == [card.id for card in found.cards]
    assert sorted(e.get('data-stock') for e in seen['stock']) == sorted(
        s.key for c in found.cards for s in c.stocks
    )
    assert sorted(e.get('data-stock') for e in seen['tally']) == sorted(
        s.key for c in found.cards for s in c.meters
    )
    assert len(seen['pipe']) == sum(len(card.pipes) for card in found.cards)
    inside = [m.var for card in found.cards for m in card.machines]
    assert sorted(e.get('data-var') for e in seen['machine']) == sorted(
        [*inside, *(m.var for m in found.machines)]
    )
    assert len(seen['arrow']) == len(found.routes)
    assert len(seen['bundle']) == len(found.bundles)
    assert [e.get('data-event') for e in seen['trigger']] == [
        ' '.join(row.events) for card in found.cards for row in card.triggers
    ]
    assert [e.get('data-group') for e in seen['group']] == [frame.label for frame in found.frames]
    assert {e.get('data-mark') for e in seen['mark']} == marks_drawn(found) | set(found.legend.hidden)
    check_arrows(found, seen['arrow'], seen['bundle'], looks_of(picture))


# ---- the panels (D-53, D-55, D-57) ------------------------------------------------------------------

PANEL_PARTS = ('block', 'equation', 'symbol', 'reference', 'tag')


def visible(element):
    """The visible words of an element: the text of each `<text>` in it (a `<title>` is not visible),
    with spaces between the texts."""
    return ' '.join(''.join(text.itertext()) for text in element.iter(f'{SVG}text'))


def marks_in(element):
    """[(number, the classes of its tspan)] of each mark in an element, in document order."""
    return [
        (int(span.text), classes(span)) for span in element.iter(f'{SVG}tspan') if 'mark' in classes(span)
    ]


def check_panels(picture, found, root):
    """The panels in the SVG (D-53, D-55, D-57):
    - `<a>` only in the entries of the References, each to its entry's `http` or `https` address (`href`
      and `xlink:href`), and an entry has a link exactly when its address is such;
    - the entries numbered 1 to n in order, with their records and their full words in the tooltip;
    - each mark a number of an entry, in the class of its kind's colour (`references.COLOUR_KIND`), a
      smaller tspan raised by its own y (no `baseline-shift`); the marks of each line and each row of
      the table those of the picture, in order;
    - each equation line's `data-latex` its line's LaTeX, and its part and records;
    - the Symbols table exactly when `settings.symbols`, a row for each symbol; "chosen range" exactly in
      the rows whose range is a chosen one; the note exactly when the picture has one;
    - a tag exactly on each shown stock row and meter of `tags`, inside it, with its symbol;
    - the style holds the rules of the typesetter (`typeset.STYLE`) when the picture has panels."""
    data = picture.get('panels')
    found_parts = parts(root)
    by_kind = {}
    for kind, element, _, _ in found_parts:
        by_kind.setdefault(kind, []).append(element)
    links = list(root.iter(f'{SVG}a'))
    groups = {name: [g for g in root.iter(f'{SVG}g') if name in classes(g)] for name in ('note', 'equations')}
    if not data:
        assert not links and not marks_in(root) and not groups['note'] and not groups['equations']
        assert not any(by_kind.get(kind) for kind in PANEL_PARTS)
        return
    style = ''.join(e.text or '' for e in root.iter(f'{SVG}style'))
    assert all(rule in style for rule in typeset.STYLE)
    entries = data['references']
    numbered = {entry['number']: entry for entry in entries}
    drawn = by_kind.get('reference', [])
    assert [int(e.get('data-number')) for e in drawn] == [entry['number'] for entry in entries]
    assert [entry['number'] for entry in entries] == list(range(1, len(entries) + 1))
    inside = set()
    for element, entry in zip(drawn, entries):
        assert element.get('data-record') == (' '.join(entry['record']) or None)
        if entry['hover']:
            assert element[0].text == entry['hover']
        anchors = list(element.iter(f'{SVG}a'))
        inside |= {id(a) for a in anchors}
        web = bool(entry['url']) and web_host(entry['url']) is not None
        assert bool(anchors) == web
        for anchor in anchors:
            assert anchor.get('href') == anchor.get(f'{{{XLINK}}}href') == entry['url']
            assert urlsplit(anchor.get('href')).scheme in ('http', 'https')
    assert all(id(anchor) in inside for anchor in links)
    for span in root.iter(f'{SVG}tspan'):
        if 'mark' not in classes(span):
            continue
        entry = numbered[int(span.text)]
        assert f'mark-{COLOUR_KIND[entry["kind"]]}' in classes(span)
        assert span.get('y') is not None and span.get('baseline-shift') is None
        assert float(span.get('font-size')) < TEXT_SIZE
    lines = [line for block in data['equations'] for line in block['lines']]
    equations = by_kind.get('equation', [])
    assert [e.get('data-block') for e in by_kind.get('block', [])] == [b['name'] for b in data['equations']]
    assert [e.get('data-latex') for e in equations] == [line['latex'] for line in lines]
    assert [e.get('data-part') for e in equations] == [line['part'] for line in lines]
    for element, line in zip(equations, lines):
        assert [number for number, _ in marks_in(element)] == [number for number, _ in line['marks']]
        assert element.get('data-record') == (' '.join(line['records']) or None)
    rows = data['symbols'] if data['settings']['symbols'] else []
    table = by_kind.get('symbol', [])
    assert [e.get('data-key') for e in table] == [row['key'] for row in rows]
    for element, row in zip(table, rows):
        chosen = row['range'] is not None and row['range_status'] == 'chosen'
        # A word can break over two rows of a narrow column: the words without spaces.
        assert ('chosenrange' in visible(element).replace(' ', '')) == chosen
        wanted = [*row['marks'], *(mark for option in row['options'] for mark in option['marks'])]
        wanted += row['range_marks']
        assert [number for number, _ in marks_in(element)] == [number for number, _ in wanted]
        assert element.get('data-record') == (' '.join(row['records']) or None)
    if data['note']:
        (note,) = groups['note']
        assert ' '.join(visible(note).split()) == ' '.join(data['note'].split())
    else:
        assert not groups['note']
    check_tags(data, found, found_parts)


def check_tags(data, found, found_parts):
    """A tag on exactly the shown stock rows and meters that `tags` names, inside the row's group, whose
    visible text is the symbol of its row as the typesetter writes it."""
    tags = data['tags']
    rows = {row['key']: row for row in data['symbols']}
    shown = {stock.key for card in found.cards for stock in (*card.stocks, *card.meters)}
    tagged = {}
    for kind, element, _, _ in found_parts:
        if kind in ('stock', 'tally'):
            own = [g for g in element if g.tag == f'{SVG}g' and 'tag' in classes(g)]
            if own:
                (tagged[element.get('data-stock')],) = own
    assert set(tagged) == shown & set(tags)
    assert len([kind for kind, _, _, _ in found_parts if kind == 'tag']) == len(tagged)
    for key, element in tagged.items():
        assert element.get('data-key') == key
        symbol = rows[key]['symbol']
        reading = typeset.letters(symbol['base']) + typeset.primes(symbol['prime']) + (symbol['sub'] or '')
        assert visible(element).replace(' ', '') == reading
        assert tags[key] == symbol['text']


# ---- the connections of a card and the hover rules (D-58) ------------------------------------------


def classes(element):
    return (element.get('class') or '').split()


def names_in(text, titles):
    """[(title, words)] of a list `title (words), title, …`: each title is the longest of `titles` that
    starts the rest of the text, and `words` are the words in brackets after it, or ()."""
    out = []
    while True:
        title = max((t for t in titles if text.startswith(t)), key=len, default=None)
        assert title is not None, text
        text = text[len(title) :]
        words = ()
        if text.startswith(' ('):
            inside, _, text = text[2:].partition(')')
            words = tuple(inside.split(', '))
        out.append((title, words))
        if not text:
            return out
        assert text.startswith(', '), text
        text = text[2:]


def links_of(tooltip, titles):
    """{(kind, side): (hidden, [(title, words), …])} of the lines of a card's tooltip that list its
    connections, in their order. Side 0 is what the card does to the others and side 1 what they do to
    it (`LINKS`); `hidden` says that the line has NOT_DRAWN."""
    labels = {words: (kind, side) for kind, pair in LINKS.items() for side, words in enumerate(pair)}
    found = {}
    for line in tooltip.split('\n'):
        label, colon, rest = line.partition(': ')
        hidden = label.endswith(f' ({NOT_DRAWN})')
        key = labels.get(label.removesuffix(f' ({NOT_DRAWN})'))
        if colon and key is not None:
            assert key not in found, line
            found[key] = (hidden, names_in(rest, titles))
    return found


def expected_links(picture, ids):
    """{card: {(kind, side): [(other card, how), …]}} from the arrows of the picture between two cards
    of `ids`, in the order of the arrows. The head of an arrow is at the card that reads or follows, and
    at the card that is changed, fired or moved (D-50). So the card that does it is the arrow's end for
    "reads" and "follows" and its start for the other kinds; side 0 is that card, side 1 the other."""
    out = {card: {} for card in ids}
    for a in picture['arrows']:
        if a['from'] == a['to'] or a['from'] not in out or a['to'] not in out:
            continue
        doer, other = (a['to'], a['from']) if a['kind'] in ('reads', 'follows') else (a['from'], a['to'])
        how = tuple(a.get('how') or ())
        out[doer].setdefault((a['kind'], 0), []).append((other, how))
        out[other].setdefault((a['kind'], 1), []).append((doer, how))
    return out


def check_links(picture, found, root):
    """The tooltip of each card names exactly the cards that its arrows join, by title, for each kind and
    side, and nothing else (D-58): the lines go in the order of the kinds, the titles in the order of the
    cards, with the words of each arrow ("sets", …). The lines of a kind whose look is hidden have
    NOT_DRAWN, and no other line has it. The routes play no part: a hidden kind draws none."""
    titles = {card.id: card.title for card in found.cards}
    order = {card: k for k, card in enumerate(titles)}
    looks = (picture.get('settings') or {}).get('looks') or {}
    expected = expected_links(picture, titles)
    for kind, element, _, _ in parts(root):
        if kind != 'card':
            continue
        card = element.get('data-thing')
        got = links_of(element[0].text, set(titles.values()))
        want = {
            key: (
                looks.get(key[0]) == 'hidden',
                [(titles[other], how) for other, how in sorted(ends, key=lambda end: order[end[0]])],
            )
            for key, ends in expected[card].items()
        }
        assert got == want, card
        assert list(got) == sorted(got, key=lambda key: (KINDS.index(key[0]), key[1])), card


def css_unescape(text):
    """The text that the inside of a CSS string stands for: each `\\hex` escape (and the one space after
    it) is its character, and `\\c` is `c`."""
    return re.sub(
        r'\\([0-9a-fA-F]{1,6})(?:\r\n|[ \t\r\n\f])?|\\(.)',
        lambda m: chr(int(m[1], 16)) if m[1] else m[2],
        text,
        flags=re.S,
    )


def outside(text, start=0):
    """(k, char, depth) for each character of `text` from `start` that is outside a CSS string, with the
    depth of the brackets around it (an opening bracket counts itself, a closing one does not)."""
    depth, quoted, k = 0, False, start
    while k < len(text):
        char = text[k]
        if quoted:
            k += 2 if char == '\\' else 1
            quoted = char != '"'
            continue
        quoted = char == '"'
        depth += (char in '([') - (char in ')]')
        yield k, char, depth
        k += 1


def split_outside(text, separator):
    """`text` split at each `separator` that is outside brackets and strings."""
    cuts = [k for k, char, depth in outside(text) if char == separator and depth == 0]
    return [part for part in (text[a + 1 : b] for a, b in zip([-1, *cuts], [*cuts, len(text)])) if part]


def closing(text, start):
    """The index of the `)` that closes the bracket that opens just before `start`."""
    return next(k for k, char, depth in outside(text, start) if char == ')' and depth == -1)


SIMPLE = re.compile(r'\.([\w-]+)|\[([\w-]+)="((?:[^"\\]|\\.)*)"\]|:(hover)(?![\w-])|:(not|is|has)\(')


def selector(text):
    """A CSS selector list of the forms that the hover rules use: [[compound, …], …], one list of
    compounds for each selector, joined by descendant combinators. A compound is a list of simple
    selectors: ('class', name), ('attr', name, value), ('hover',), or ('not' | 'is' | 'has', list)."""
    return [[compound(part) for part in split_outside(one.strip(), ' ')] for one in split_outside(text, ',')]


def compound(text):
    out, k = [], 0
    while k < len(text):
        found = SIMPLE.match(text, k)
        assert found, text[k:]
        if found[1]:
            out.append(('class', found[1]))
        elif found[2]:
            out.append(('attr', found[2], css_unescape(found[3])))
        elif found[4]:
            out.append(('hover',))
        else:
            end = closing(text, found.end())
            out.append((found[5], selector(text[found.end() : end])))
            k = end + 1
            continue
        k = found.end()
    return out


class Pointer:
    """CSS matching on the SVG tree while a reader points at one element: that element and its
    ancestors match `:hover`. A selector inside `:has()` is one compound, which is enough here."""

    def __init__(self, root, pointed):
        self.parent = {child: element for element in root.iter() for child in element}
        self.hovered = set()
        while pointed is not None:
            self.hovered.add(pointed)
            pointed = self.parent.get(pointed)
        self.known = {}

    def any(self, options, element):
        return any(self.complex(option, element) for option in options)

    def complex(self, compounds, element):
        if not self.compound(compounds[-1], element):
            return False
        for part in reversed(compounds[:-1]):
            element = self.parent.get(element)
            while element is not None and not self.compound(part, element):
                element = self.parent.get(element)
            if element is None:
                return False
        return True

    def compound(self, simples, element):
        for simple in simples:
            kind = simple[0]
            if kind == 'class':
                fits = simple[1] in classes(element)
            elif kind == 'attr':
                fits = element.get(simple[1]) == simple[2]
            elif kind == 'hover':
                fits = element in self.hovered
            elif kind == 'is':
                fits = self.any(simple[1], element)
            elif kind == 'not':
                fits = not self.any(simple[1], element)
            else:
                key = (id(element), id(simple))
                if key not in self.known:
                    self.known[key] = any(
                        self.any(simple[1], inner) for inner in element.iter() if inner is not element
                    )
                fits = self.known[key]
            if not fits:
                return False
        return True


def hover_rules(style):
    """[(selector, declarations)] of the one `@media (hover:hover)` block of a style, and none when it
    has no block; no rule outside the block has `:hover`."""
    head = '@media (hover:hover){'
    if head not in style:
        assert ':hover' not in style
        return []
    assert style.count(head) == 1
    before, _, rest = style.partition(head)
    depth, end = 1, 0
    while depth:
        depth += {'{': 1, '}': -1}.get(rest[end], 0)
        end += 1
    inner, after = rest[: end - 1], rest[end:]
    assert ':hover' not in before + after
    rules = re.findall(r'([^{}]+)\{([^{}]*)\}', inner)
    assert ''.join(f'{s}{{{d}}}' for s, d in rules) == inner
    return rules


def hover_effect(root, rules, card):
    """What `rules` do while a reader points at the card `card`: the elements that they dim (an
    opacity below 1) and the elements that they show (a stroke opacity of 1)."""
    pointed = next(e for e in root.iter(f'{SVG}g') if 'card' in classes(e) and e.get('data-thing') == card)
    pointer = Pointer(root, pointed)
    dimmed, shown = set(), set()
    # Each parsed rule stays alive while the pointer keeps what `:has()` found by the ids of its parts.
    parsed = [(selector(text), body) for text, body in rules]
    for options, body in parsed:
        declared = dict(item.split(':') for item in body.split(';') if item)
        hit = {e for e in root.iter() if pointer.any(options, e)}
        if set(declared) == {'opacity'}:
            assert float(declared['opacity']) < 1, body
            dimmed |= hit
        else:
            assert declared == {'stroke-opacity': '1'}, body
            shown |= hit
    return dimmed, shown


def wanted_effect(root, card):
    """What pointing at `card` must do (D-58): dim each arrow that does not join it and each bundle that
    does not start at it, and show the full path (`.member`) of each arrow that joins it."""
    dimmed, shown = set(), set()
    for element in root.iter(f'{SVG}g'):
        joins = card in (element.get('data-from'), element.get('data-to'))
        if 'arrow' in classes(element):
            if joins:
                shown |= {e for e in element.iter() if 'member' in classes(e)}
            else:
                dimmed.add(element)
        elif 'bundle' in classes(element) and element.get('data-from') != card:
            dimmed.add(element)
    return dimmed, shown


def check_hover(found, root, every=False):
    """The hover rules (D-58): one `@media (hover:hover)` block holds them; each card has two, which
    name that card only and point at it only, and they do what `wanted_effect` says. With `every`,
    pointing at a card does that with all the rules, those of the other cards too."""
    rules = hover_rules(''.join(e.text or '' for e in root.iter(f'{SVG}style')))
    own = {}
    for text, body in rules:
        names = {css_unescape(name) for name in re.findall(r'"((?:[^"\\]|\\.)*)"', text)}
        pointed = re.findall(r'\[data-thing="((?:[^"\\]|\\.)*)"\]:hover', text)
        assert len(names) == 1 and text.count(':hover') == 1 and len(pointed) == 1, text
        assert css_unescape(pointed[0]) in names, text
        own.setdefault(names.pop(), []).append((text, body))
    assert sorted(own) == sorted(card.id for card in found.cards)
    assert all(len(pair) == 2 for pair in own.values())
    for card, pair in own.items():
        assert hover_effect(root, rules if every else pair, card) == wanted_effect(root, card), card


def polylines(d):
    """The polylines of a path's `d`, which has only M and L commands."""
    out = []
    for command, x, y in re.findall(r'([ML])(-?[0-9.]+) (-?[0-9.]+)', d):
        if command == 'M':
            out.append([])
        out[-1].append((float(x), float(y)))
    assert re.fullmatch(r'([ML]-?[0-9.]+ -?[0-9.]+)+', d), d
    return out


def stretches(lines):
    """{line: [(low, high)]} of the segments of polylines: ('h', y) or ('v', x), and the span along it."""
    out = {}
    for points in lines:
        for (x0, y0), (x1, y1) in itertools.pairwise(points):
            assert x0 == x1 or y0 == y1
            key, span = (
                (('h', y0), (min(x0, x1), max(x0, x1)))
                if y0 == y1
                else (('v', x0), (min(y0, y1), max(y0, y1)))
            )
            out.setdefault(key, []).append(span)
    return out


def union(spans):
    merged = []
    for low, high in sorted(spans):
        if merged and low <= merged[-1][1]:
            merged[-1][1] = max(merged[-1][1], high)
        else:
            merged.append([low, high])
    return merged


def looks_of(picture):
    """{kind: the name of the look that the SVG draws it with}: `<kind>-light` for a kind whose look
    in the picture's settings is light (D-51), else the kind."""
    looks = (picture.get('settings') or {}).get('looks') or DEFAULT_LOOKS
    return {kind: f'{kind}-light' if looks.get(kind) == 'light' else kind for kind in KINDS}


def check_arrows(found, arrows, bundles, looks=None):
    """The lines of the arrows (D-51). An arrow that is in no bundle is one path of its route with the
    head of its kind. An arrow of a bundle has its whole route as a path of the classes `route member`
    with no colour, and the head of its kind on a path of its last segment. Each bundle has a dot at each
    junction, and its path and the heads of its arrows draw each stretch of its routes once."""
    assert [(e.get('data-from'), e.get('data-to'), e.get('data-kind')) for e in arrows] == [
        (route.source, route.target, route.kind) for route in found.routes
    ]
    heads = {}
    for element, route in zip(arrows, found.routes):
        paths = element.findall(f'{SVG}path')
        marked = [p for p in paths if p.get('marker-end')]
        look = (looks or {}).get(route.kind, route.kind)
        assert len(marked) == 1 and marked[0].get('marker-end') == f'url(#head-{look})'
        if route.bundle is None:
            assert len(paths) == 1 and polylines(paths[0].get('d')) == [list(route.points)]
            continue
        (whole,) = [p for p in paths if 'route' in (p.get('class') or '').split()]
        assert {'route', 'member'} <= set(whole.get('class').split()) and whole.get('stroke-opacity') == '0'
        assert polylines(whole.get('d')) == [list(route.points)]
        assert polylines(marked[0].get('d')) == [list(route.points[-2:])]
        heads.setdefault(route.bundle, []).append(list(route.points[-2:]))
    assert len(bundles) == len(found.bundles)
    for index, (element, bundle) in enumerate(zip(bundles, found.bundles)):
        assert (element.get('data-from'), element.get('data-kind')) == (bundle.source, bundle.kind)
        dots = {(float(c.get('cx')), float(c.get('cy'))) for c in element.iter(f'{SVG}circle')}
        assert dots == set(bundle.junctions) and len(list(element.iter(f'{SVG}circle'))) == len(dots)
        (path,) = element.findall(f'{SVG}path')
        drawn = stretches([*polylines(path.get('d')), *heads[index]])
        routes = stretches([list(route.points) for route in found.routes if route.bundle == index])
        assert drawn.keys() == routes.keys()
        for key, spans in drawn.items():
            # No stretch twice, and together the stretches of the routes.
            ordered = sorted(spans)
            assert all(a[1] <= b[0] for a, b in itertools.pairwise(ordered)), (key, ordered)
            assert union(spans) == union(routes[key]), key


def drawn(picture):
    found = layout(picture)
    return found, svg(picture, found)


def test_the_svg_of_the_frozen_picture_holds_every_property():
    picture = load()
    found, text = drawn(picture)
    check(picture, found)
    check_svg(picture, found, text)


def test_the_svg_has_a_marker_for_each_kind_of_arrow_and_the_icons_of_the_cards():
    picture = load()
    _, text = drawn(picture)
    root = ET.fromstring(text)
    markers = {m.get('id') for m in root.iter(f'{SVG}marker')}
    assert {f'head-{kind}' for kind in KINDS} <= markers
    dashes = {}
    for _, element, _, _ in (p for p in parts(root) if p[0] in ('arrow', 'bundle')):
        for line in element.findall(f'{SVG}path'):
            look = looks_of(picture)[element.get('data-kind')]
            assert line.get('marker-end') in (None, f'url(#head-{look})')
            dashes.setdefault(element.get('data-kind'), set()).add(
                (line.get('stroke-dasharray'), line.get('stroke-width'))
            )
    # One look for each kind, and each kind its own.
    assert all(len(looks) == 1 for looks in dashes.values()) and len(
        {next(iter(v)) for v in dashes.values()}
    ) == len(dashes)
    icons_used = {card['icon'] for card in picture['cards'] if card['icon']}
    assert {s.get('id') for s in root.iter(f'{SVG}symbol')} == {f'icon-{name}' for name in icons_used}


def luminance(colour):
    """The relative luminance of a colour `#rrggbb` (WCAG 2.1)."""
    channels = [int(colour[k : k + 2], 16) / 255 for k in (1, 3, 5)]
    linear = [c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4 for c in channels]
    return 0.2126 * linear[0] + 0.7152 * linear[1] + 0.0722 * linear[2]


def contrast(a, b):
    """The contrast ratio of two colours (WCAG 2.1): 1 to 21."""
    high, low = sorted((luminance(a), luminance(b)), reverse=True)
    return (high + 0.05) / (low + 0.05)


@pytest.mark.parametrize('theme', [0, 1])
def test_the_flows_have_a_colour_of_their_own_that_shows_on_the_cards_and_the_page(theme):
    flow = COLOURS['pipe'][theme]
    # Not the colour of an arrow or of a transition.
    assert flow not in {COLOURS[name][theme] for name in (*KINDS, 'transition')}
    # A line that shows on its ground: WCAG's least contrast for a graphic, 3 to 1.
    for ground in ('card', 'paper', 'stock'):
        assert contrast(flow, COLOURS[ground][theme]) >= 3, ground


def test_the_five_kinds_of_arrow_differ_in_grey_and_show_on_the_page():
    # One arrow of each kind between two cards (D-50): each two kinds differ in their width, their
    # dashes or the shape of their head, which a reader sees without colour.
    _, text = drawn(
        picture_of([sample_card('a'), sample_card('b')], [arrow('a', 'b', kind) for kind in KINDS])
    )
    root = ET.fromstring(text)
    heads = {m.get('id'): m.find(f'{SVG}path').get('d') for m in root.iter(f'{SVG}marker')}
    looks = {}
    for _, element, _, _ in (p for p in parts(root) if p[0] == 'arrow'):
        line = element.find(f'{SVG}path')
        head = heads[line.get('marker-end')[len('url(#') : -1]]
        looks[element.get('data-kind')] = (line.get('stroke-width'), line.get('stroke-dasharray'), head)
    assert sorted(looks) == sorted(KINDS)
    assert len(set(looks.values())) == len(KINDS)
    for theme in (0, 1):
        colours = [COLOURS[kind][theme] for kind in KINDS]
        assert len(set(colours)) == len(KINDS)
        # A line that shows on the page: WCAG's least contrast for a graphic, 3 to 1.
        for kind in KINDS:
            assert contrast(COLOURS[kind][theme], COLOURS['paper'][theme]) >= 3, (kind, theme)


def test_the_subtitle_draws_each_line_and_the_start_mark_is_on_the_card_that_starts():
    # D-59: a picture of one run with a horizon and a hidden thing has a subtitle of two lines.
    cards = [sample_card('a', starts=True), sample_card('b')]
    doc = picture_of(cards, [arrow('a', 'b')])
    doc['facts'] = {
        'run': {'name': 'r', 'label': 'First option', 'options': ['Second option']},
        'runs': 1,
        'horizon': '30 days',
        'hidden': ['c'],
    }
    doc['run'] = 'r'
    found, text = drawn(doc)
    check(doc, found)
    check_svg(doc, found, text)
    root = ET.fromstring(text)
    lines = [element.text for element in root.iter(f'{SVG}text') if element.get('class') == 'subheading']
    assert lines == list(found.subtitle) and len(lines) == 2
    # The options that the label does not name follow it; the horizon and the hidden things are second.
    assert 'First option (Second option)' in lines[0] and '30 days' in lines[1] and 'not drawn: c' in lines[1]
    marks = [
        card
        for kind, element, card, _ in parts(root)
        if kind == 'card' and any(path.get('class') == 'starts' for path in element.iter(f'{SVG}path'))
    ]
    assert marks == ['a']


def test_a_light_kind_is_paler_and_thinner_and_still_shows_on_the_page():
    # D-51: [arrows] reads = "light". The light look is its own colour (not a lower opacity), between
    # the full colour and the paper in each theme, and a thinner line with a head of its own.
    def lines_of(doc):
        found, text = drawn(doc)
        check(doc, found)
        check_svg(doc, found, text)
        root = ET.fromstring(text)
        lines = {e.get('data-kind'): e.find(f'{SVG}path') for kind, e, _, _ in parts(root) if kind == 'arrow'}
        return lines, {m.get('id') for m in root.iter(f'{SVG}marker')}

    plain = picture_of(
        [sample_card('a'), sample_card('b')], [arrow('a', 'b', 'reads'), arrow('a', 'b', 'changes')]
    )
    plain['settings'] = {'looks': {kind: 'full' for kind in KINDS}}
    light = {**plain, 'settings': {'looks': {kind: 'full' for kind in KINDS} | {'reads': 'light'}}}
    full, _ = lines_of(plain)
    lines, markers = lines_of(light)
    assert lines['reads'].get('stroke') == COLOURS['reads-light'][0] != full['reads'].get('stroke')
    assert float(lines['reads'].get('stroke-width')) < float(full['reads'].get('stroke-width'))
    assert lines['reads'].get('marker-end') == 'url(#head-reads-light)'
    assert lines['changes'].get('stroke') == full['changes'].get('stroke')
    assert 'head-reads-light' in markers
    for theme in (0, 1):
        paper = COLOURS['paper'][theme]
        for kind in KINDS:
            light, whole = COLOURS[f'{kind}-light'][theme], COLOURS[kind][theme]
            low, high = sorted((luminance(whole), luminance(paper)))
            assert low <= luminance(light) <= high, (kind, theme)
            assert contrast(light, paper) < contrast(whole, paper), (kind, theme)
            # Faint, but still a line on the page.
            assert contrast(light, paper) >= 2.0, (kind, theme)


def test_a_hidden_kind_has_a_legend_item_with_no_sample_and_no_arrow():
    doc = picture_of(
        [sample_card('a'), sample_card('b')], [arrow('a', 'b', 'reads'), arrow('a', 'b', 'moves')]
    )
    doc['settings'] = {'looks': {kind: 'full' for kind in KINDS} | {'reads': 'hidden'}}
    found, text = drawn(doc)
    check(doc, found)
    check_svg(doc, found, text)
    root = ET.fromstring(text)
    assert [e.get('data-kind') for kind, e, _, _ in parts(root) if kind == 'arrow'] == ['moves']
    marks = {e.get('data-mark'): e for kind, e, _, _ in parts(root) if kind == 'mark'}
    assert list(marks['reads'].iter(f'{SVG}path')) == [] and list(marks['moves'].iter(f'{SVG}path'))


def test_the_legend_draws_the_flows_and_the_moves_as_the_picture_does():
    picture = load()
    _, text = drawn(picture)
    root = ET.fromstring(text)
    looks = {}
    for kind, element, _, _ in parts(root):
        if kind == 'pipe':
            line = element.find(f'{SVG}path')
            looks.setdefault('pipe', set()).add((line.get('class'), line.get('stroke')))
        elif kind == 'arrow' and element.get('data-kind') == 'moves':
            line = element.find(f'{SVG}path')
            looks.setdefault('moves', set()).add((line.get('class'), line.get('stroke')))
        elif kind == 'mark' and element.get('data-mark') in ('pipe', 'moves'):
            line = element.find(f'{SVG}path')
            looks.setdefault(f'legend {element.get("data-mark")}', set()).add(
                (line.get('class'), line.get('stroke'))
            )
    assert len(looks['pipe']) == len(looks['moves']) == 1
    assert looks['legend pipe'] == looks['pipe'] and looks['legend moves'] == looks['moves']
    assert looks['pipe'] != looks['moves']


def test_a_card_without_an_icon_draws_none_and_its_title_keeps_its_place():
    from tests.draw.test_layout import card as thing

    picture = picture_of([thing('a', icon='sun'), thing('b'), thing('c', icon=None)])
    found, text = drawn(picture)
    root = ET.fromstring(text)
    cards = {e.get('data-thing'): e for kind, e, _, _ in parts(root) if kind == 'card'}
    assert [u.get('href') for u in cards['a'].iter(f'{SVG}use')] == ['#icon-sun']
    assert not list(cards['b'].iter(f'{SVG}use')) and not list(cards['c'].iter(f'{SVG}use'))
    boxes = {c.id: c.box for c in found.cards}
    offsets = set()
    for name, element in cards.items():
        title = next(t for t in element.iter(f'{SVG}text') if t.get('class') == 'card-title')
        offsets.add((float(title.get('x')) - boxes[name].x, float(title.get('y')) - boxes[name].y))
    assert len(offsets) == 1


def test_the_title_of_the_svg_is_the_picture_s_unless_one_is_given():
    picture = load()
    found = layout(picture)
    assert ET.fromstring(svg(picture, found))[0].text == picture['title']
    assert (
        ET.fromstring(svg(picture, found, title='Another <title> & more'))[0].text == 'Another <title> & more'
    )


def same_bytes_in_other_processes(picture, path):
    """The SVG of `picture`, written to `path` as JSON, has the same bytes in processes with other hash
    seeds as in this one."""
    path.write_text(json.dumps(picture), encoding='utf-8')
    here = svg(picture, layout(picture))
    code = (
        'import hashlib, json, sys\n'
        'from napkin.draw.layout import layout\n'
        'from napkin.draw.svg import svg\n'
        f'picture = json.load(open({str(path)!r}, encoding="utf-8"))\n'
        'sys.stdout.write(hashlib.sha256(svg(picture, layout(picture)).encode()).hexdigest())\n'
    )
    digests = set()
    for seed in ('0', '1', '4242'):
        env = {**os.environ, 'PYTHONPATH': str(ROOT), 'PYTHONHASHSEED': seed}
        done = subprocess.run(
            [sys.executable, '-B', '-c', code],
            cwd=ROOT,
            env=env,
            capture_output=True,
            text=True,
            timeout=120,
            check=False,
        )
        assert done.returncode == 0, done.stderr
        digests.add(done.stdout)
    assert digests == {hashlib.sha256(here.encode()).hexdigest()}


def test_the_same_picture_gives_the_same_bytes_in_other_processes(tmp_path):
    same_bytes_in_other_processes(load(), tmp_path / 'picture.json')


def test_a_picture_of_a_model_gives_the_same_bytes_in_other_processes(tmp_path):
    # The water works, with its bundles and light looks: the picture is JSON, so the other processes
    # draw it without compiling the model again.
    from napkin.draw import style

    same_bytes_in_other_processes(picture(works(), style.read(WORKS_STYLE)), tmp_path / 'picture.json')


@SHAPE
@given(pictures(groups=True))
def test_every_property_holds_on_pictures_that_hypothesis_makes(picture):
    found, text = drawn(picture)
    check_svg(picture, found, text)


# ---- the connections of a card and the hover rules (D-58) ------------------------------------------

LOOKS = st.fixed_dictionaries({kind: st.sampled_from(ARROW_LOOKS) for kind in KINDS})


@SHAPE
@given(pictures(groups=True), LOOKS)
def test_the_tooltips_and_the_hover_rules_hold_with_any_looks_of_the_arrows(picture, looks):
    # check_svg holds check_links, with the hidden kinds, and check_hover.
    picture['settings'] = {**settings_of(None), 'looks': looks}
    found, text = drawn(picture)
    check_svg(picture, found, text)


@SHAPE
@given(pictures(groups=True), st.lists(st.sampled_from(KINDS), unique=True))
def test_every_property_holds_with_any_kinds_bundled(picture, kinds):
    picture = bundling(picture, kinds)
    found, text = drawn(picture)
    check_svg(picture, found, text)


def test_pointing_at_a_card_of_the_frozen_picture_acts_on_its_arrows_only():
    picture = load()
    found, text = drawn(picture)
    check_hover(found, ET.fromstring(text), every=True)


def test_a_kind_whose_look_is_hidden_stays_in_the_tooltips_and_says_that_it_is_not_drawn():
    cards = [sample_card(name) for name in 'abc']
    arrows = [arrow('a', 'b', 'reads'), arrow('a', 'c', 'reads'), arrow('b', 'c'), arrow('c', 'a', 'follows')]
    lines = {}
    for look in ('full', 'hidden'):
        doc = picture_of(cards, arrows)
        doc['settings'] = settings_of(None)
        doc['settings']['looks']['reads'] = look
        found, text = drawn(doc)
        check_svg(doc, found, text)
        lines[look] = {
            e.get('data-thing'): links_of(e[0].text, {'A', 'B', 'C'})
            for kind, e, _, _ in parts(ET.fromstring(text))
            if kind == 'card'
        }
    for card, got in lines['hidden'].items():
        # The same things in both pictures; only the lines of "reads", and only when it is hidden, say
        # that their arrows are not drawn.
        assert {key: names for key, (_, names) in got.items()} == {
            key: names for key, (_, names) in lines['full'][card].items()
        }
        assert {key for key, (hidden, _) in got.items() if hidden} == {
            key for key in got if key[0] == 'reads'
        }
        assert not any(hidden for hidden, _ in lines['full'][card].values())
    # b and c read the values of a; b reads the values of a.
    assert lines['hidden']['a'][('reads', 1)] == (True, [('B', ()), ('C', ())])
    assert lines['hidden']['b'][('reads', 0)] == (True, [('A', ())])
    assert lines['hidden']['a'][('follows', 0)] == (False, [('C', ())])


def test_the_hover_rules_dim_the_bundles_of_other_cards_and_show_the_full_paths_of_a_card_s_arrows():
    # A bundle (D-51) draws its trunk once, in a `g.bundle` with the card that it starts at, and each of
    # its arrows as a `g.arrow` with a full path `.member` of no opacity. Two bundles, added here to the
    # SVG of three cards.
    _, text = drawn(picture_of([sample_card(name) for name in 'abc']))
    root = ET.fromstring(text)
    layer = next(e for e in root.iter(f'{SVG}g') if 'arrows' in classes(e))

    def add(cls, **data):
        element = ET.SubElement(layer, f'{SVG}g', {'class': cls, **{f'data-{k}': v for k, v in data.items()}})
        ET.SubElement(element, f'{SVG}title').text = cls
        return element

    trunks = {start: add('bundle reads', **{'from': start, 'kind': 'reads'}) for start in 'ac'}
    for trunk in trunks.values():
        ET.SubElement(trunk, f'{SVG}path', {'class': 'line-reads'})
    arrows, members = {}, {}
    for start, end in ('ab', 'ac', 'cb'):
        arrows[start + end] = add('arrow reads', **{'from': start, 'to': end, 'kind': 'reads'})
        members[start + end] = ET.SubElement(
            arrows[start + end], f'{SVG}path', {'class': 'route member', 'stroke-opacity': '0'}
        )
    rules = hover_rules(''.join(e.text or '' for e in root.iter(f'{SVG}style')))
    # Neither bundle starts at b, so both trunks dim; the arrows of b show their full paths.
    assert hover_effect(root, rules, 'b') == (
        {trunks['a'], trunks['c'], arrows['ac']},
        {members['ab'], members['cb']},
    )
    # The trunk of a stays, and so do the arrows of a, with their full paths.
    assert hover_effect(root, rules, 'a') == ({trunks['c'], arrows['cb']}, {members['ab'], members['ac']})
    assert hover_effect(root, rules, 'c') == ({trunks['a'], arrows['ab']}, {members['ac'], members['cb']})
    for card in 'abc':
        assert hover_effect(root, rules, card) == wanted_effect(root, card)


# Card ids that a CSS string must escape: a quote, a backslash, the marks of XML, a bracket, a space,
# a backslash and hex digits that would read as an escape, and letters outside ASCII.
ODD = ('a"b', 'c\\d', 'e<f&g>', 'h]i)j k', 'l\\22 m', 'é,ø')


def test_odd_card_ids_keep_their_hover_rules_on_their_own_cards():
    cards = [sample_card(name, title=f'Card {k}') for k, name in enumerate(ODD)]
    arrows = [arrow(a, b, kind) for (a, b), kind in zip(itertools.pairwise(ODD), KINDS)]
    doc = picture_of(cards, arrows)
    found, text = drawn(doc)
    check_svg(doc, found, text)
    check_hover(found, ET.fromstring(text), every=True)


@SHAPE
@given(st.text(st.characters(exclude_categories=('Cs',), exclude_characters='\x00'), max_size=40))
def test_a_css_string_holds_any_text_and_reads_back_to_it(text):
    held = css_string(text)
    # No quote, newline or mark of XML of its own, and each backslash starts a hex escape.
    bare = re.sub(r'\\[0-9a-fA-F]{1,6} ?', '', held)
    assert not set(bare) & set('"\\\n\r<>&')
    assert css_unescape(held) == text


@pytest.mark.parametrize('text', ['a\x00b', '\ud800'])
def test_a_css_string_refuses_what_css_cannot_hold(text):
    with pytest.raises(ValueError):
        css_string(text)


def test_a_bundle_is_drawn_before_its_arrows_and_each_arrow_keeps_its_tooltip():
    # Three cards read s, and one of them also follows it: one bundle of three reads (D-51).
    readers = [sample_card(f'r{k}', place={'column': 2, 'row': None}) for k in range(3)]
    doc = picture_of(
        [sample_card('s', place={'column': 1, 'row': None}), *readers],
        [*(arrow('s', f'r{k}', 'reads') for k in range(3)), arrow('s', 'r1', 'follows')],
    )
    found, text = drawn(doc)
    check(doc, found)
    check_svg(doc, found, text)
    root = ET.fromstring(text)
    group = next(e for e in root.iter(f'{SVG}g') if e.get('class') == 'arrows')
    order = [(kind_of(e), e.get('data-to'), e.get('data-kind')) for e in group]
    assert order == [
        ('bundle', None, 'reads'),
        ('arrow', 'r0', 'reads'),
        ('arrow', 'r1', 'follows'),
        ('arrow', 'r1', 'reads'),
        ('arrow', 'r2', 'reads'),
    ]
    # The bundle's tooltip names each reader, and each arrow has a tooltip of its own.
    titles = {card.id: card.title for card in found.cards}
    assert all(titles[f'r{k}'] in group[0][0].text for k in range(3))
    assert len({e[0].text for e in group[1:]}) == 4
    # Without bundles, no part is a bundle and each arrow is one path with its head.
    plain = bundling(doc, [])
    found, text = drawn(plain)
    check_svg(plain, found, text)
    root = ET.fromstring(text)
    assert not [p for p in parts(root) if p[0] == 'bundle']
    assert all(len(e.findall(f'{SVG}path')) == 1 for kind, e, _, _ in parts(root) if kind == 'arrow')


# ---- a model ------------------------------------------------------------------------------------------


@pytest.mark.parametrize('run', [None, 'base', 'attack'])
def test_the_svg_of_the_water_works_holds_every_property(run):
    from napkin.draw import style

    model = works()
    found = picture(model, style.read(WORKS_STYLE), run=run)
    placed, text = drawn(found)
    check_svg(found, placed, text)
    check_model(model, ET.fromstring(text))


def check_model(model, root):
    """Each `data-*` value of the SVG names a part of the model (a `Compiled`): a card is a thing, a
    stock a stock or tally of its card, a flow `card.flow` one of its card's flows (or of its events), a
    machine one of its card's named states, a state one of that var's states, and an event
    `card.event` an event of the model."""
    from napkin.draw import style
    from napkin.draw.things import Things
    from napkin.model import semantic
    from tests.draw.test_references import ids_of

    found = Things(model)
    check_visible(found, root)
    known = ids_of(found)
    for element in root.iter():
        for name in (element.get('data-record') or '').split():
            assert name in known, name
    events = {f'{card}.{event.name}' for card in found.cards for event in found.events(card)}
    for kind, element, card, machine in parts(root):
        if kind == 'card':
            assert element.get('data-thing') in found.cards
        elif kind in ('stock', 'tally', 'more'):
            for key in element.get('data-stock').split():
                owner, _, name = key.rpartition('.')
                assert owner == card and name in style.stock_names(found, card)
        elif kind == 'pipe':
            flows = (semantic.DeclaredFlow, semantic.DeclaredLegs)
            names = {f'{card}.{part.name}' for part in found.parts(card) if isinstance(part, flows)}
            names |= {
                f'{card}.{event.name}.{local.name}' for event in found.events(card) for local in event.locals
            }
            assert set(element.get('data-flow').split()) <= names
        elif kind == 'machine':
            owner, _, name = element.get('data-var').rpartition('.')
            assert name in style.named_states(found, owner)
        elif kind == 'state' and 'data-state' in element.attrib:
            owner, _, name = machine.rpartition('.')
            value = found.part(found.cards[owner].template, name)
            assert element.get('data-state') in style.states_of(value)
        elif kind == 'transition':
            assert set(element.get('data-event').split()) <= events
        elif kind == 'trigger':
            # A row of a card's events names events of that card only.
            named = set(element.get('data-event').split())
            assert named <= events and all(key.rpartition('.')[0] == card for key in named), (card, named)


def check_visible(found, root):
    """No visible text of the SVG shows an ID of a record of the model's library (CONTRIBUTING.md, writing
    rule 15): the text of each `<text>`, searched for each ID as a whole word."""
    library = found.library or {}
    ids = {
        item['id']
        for collection in ('sources', 'claims', 'assumptions', 'conventions')
        for item in library.get(collection, [])
    }
    if not ids:
        return
    pattern = re.compile(
        r'(?<![\w-])(' + '|'.join(map(re.escape, sorted(ids, key=len, reverse=True))) + r')(?![\w-])'
    )
    for text in root.iter(f'{SVG}text'):
        found = pattern.search(''.join(text.itertext()))
        assert found is None, (found and found.group(1), ''.join(text.itertext()))
