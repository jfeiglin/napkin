"""The layout of a picture (napkin/draw/layout.py), by its properties: on the frozen picture of the
contract (tests/draw/picture.json), on pictures that Hypothesis makes, on small counterexamples, and on
the pictures of the water works (`tests/draw/models.py`) for each of its runs and joined.

`check(picture, found)` holds every property that a layout keeps; the SVG tests and the catalogue test
(`test_catalogue.py`) use it too. No test pins a coordinate: each property is geometry (boxes that do not overlap, segments
that are horizontal or vertical, points on borders) or a rule of the brief (at most `cards_per_column`
cards to a column, at most `stocks` stocks to a card, a card at least `card_width` wide, the rows of
`[stocks]` in its order, a machine inside when it is small).
"""

from __future__ import annotations

import copy
import dataclasses
import itertools
import json
import math
import time
from pathlib import Path

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from napkin.draw import layout as layouts
from napkin.draw import notation, typeset
from napkin.draw.defaults import ARROW_LOOKS
from napkin.draw.layout import KINDS, MARKS, layout
from napkin.draw.model_map import picture
from napkin.draw.references import LEFT_OUT_WORDS
from tests.draw.models import WORKS_STYLE, works

FIXTURE = Path(__file__).with_name('picture.json')
PICTURE = json.loads(FIXTURE.read_text(encoding='utf-8'))
SHAPE = settings(derandomize=True, max_examples=60, deadline=None)
# The kinds that bundle when a picture's settings do not say (D-51).
DEFAULT_BUNDLE = ('reads', 'follows')


def load():
    """A fresh copy of the frozen picture."""
    return copy.deepcopy(PICTURE)


# ---- the properties of a layout ---------------------------------------------------------------------


def joining_arrows(picture):
    """The arrows of a picture between two different cards of it."""
    ids = {card['id'] for card in picture['cards']}
    return [a for a in picture['arrows'] if a['from'] in ids and a['to'] in ids and a['from'] != a['to']]


def hidden_kinds(picture):
    """The kinds whose look is hidden (`[arrows]`, D-51) and that the picture has between two cards."""
    looks = (picture.get('settings') or {}).get('looks') or {}
    have = {a['kind'] for a in joining_arrows(picture)}
    return tuple(kind for kind in KINDS if looks.get(kind) == 'hidden' and kind in have)


def drawn_arrows(picture):
    """The arrows that a layout draws: those between two different cards of the picture, of a kind
    whose look is not hidden."""
    hidden = hidden_kinds(picture)
    return [a for a in joining_arrows(picture) if a['kind'] not in hidden]


def is_small(machine):
    return (
        len(machine['states']) <= layouts.INSIDE_STATES
        and len(machine['transitions']) <= layouts.INSIDE_TRANSITIONS
    )


def numbers(value):
    """Every number in a layout, recursively: each coordinate and size. The width of the stroke of a
    typeset rule is no coordinate (`typeset.Rule.stroke`)."""
    if isinstance(value, bool):
        return
    if isinstance(value, (int, float)):
        yield value
    elif dataclasses.is_dataclass(value):
        for field in dataclasses.fields(value):
            if isinstance(value, typeset.Rule) and field.name == 'stroke':
                continue
            yield from numbers(getattr(value, field.name))
    elif isinstance(value, (tuple, list)):
        for item in value:
            yield from numbers(item)


def on_border(point, box):
    x, y = point
    vertical = x in (box.x, box.right) and box.y <= y <= box.bottom
    horizontal = y in (box.y, box.bottom) and box.x <= x <= box.right
    return vertical or horizontal


def crosses(a, b, box):
    """Whether the segment a-b meets the inside of a box (its border excluded)."""
    (x0, y0), (x1, y1) = a, b
    if y0 == y1:
        return box.y < y0 < box.bottom and max(x0, x1) > box.x and min(x0, x1) < box.right
    return box.x < x0 < box.right and max(y0, y1) > box.y and min(y0, y1) < box.bottom


def within(inner, outer):
    return outer.contains(inner)


def marks_drawn(found):
    marks = {route.kind for route in found.routes}
    machines = [*found.machines, *(m for card in found.cards for m in card.machines)]
    for card in found.cards:
        if card.stocks:
            marks.add('stock')
        if card.meters:
            marks.add('tally')
        if card.pipes:
            marks.add('pipe')
    if machines:
        marks.add('state')
    if any(machine.transitions for machine in machines):
        marks.add('transition')
    return marks


def limits_of(picture):
    """(the most stock rows of a card, the most cards of a column, the least width of a card) that the
    picture's settings give (D-52), else the layout's defaults."""
    settings = picture.get('settings') or {}
    return (
        settings.get('stocks') or layouts.MAX_STOCKS,
        settings.get('cards_per_column') or layouts.MAX_COLUMN,
        settings.get('card_width') or layouts.CARD_MIN,
    )


def check(picture, found):
    """Every property of the layout `found` of `picture`."""
    cards = {card['id']: card for card in picture['cards']}
    placed = {card.id: card for card in found.cards}
    # Each card of the picture once, in its order; each arrow once.
    assert [card.id for card in found.cards] == [card['id'] for card in picture['cards']]
    assert sorted((r.source, r.target, r.kind) for r in found.routes) == sorted(
        (a['from'], a['to'], a['kind']) for a in drawn_arrows(picture)
    )
    # Every coordinate is a multiple of 0.5.
    assert all(float(value * 2).is_integer() for value in numbers(found))
    check_boxes(picture, found, cards, placed)
    check_columns(picture, found, cards)
    check_routes(found, placed)
    check_tracks(found)
    check_bundles(picture, found, placed)
    check_cards(picture, found, cards)
    check_panels(picture, found)
    # The legend shows the marks that the layout draws, each once, in the order of MARKS.
    shown = [mark for mark, _, _ in found.legend.items]
    hidden = hidden_kinds(picture)
    assert shown == [mark for mark in MARKS if mark in marks_drawn(found) or mark in hidden]
    assert found.legend.hidden == hidden
    assert found.width > 0 and found.height > 0
    # The picture is wide enough for its bold title.
    title = str(picture.get('title', ''))
    assert layouts.bold_width(title, layouts.PICTURE_TITLE_SIZE) + 2 * layouts.MARGIN <= found.width


def check_boxes(picture, found, cards, placed):
    """The boxes of the cards, the machines beside them, the frames and the legend do not overlap,
    apart from a frame and its own members; each frame holds its members and nothing else; each
    part of a card or a machine lies inside it; everything lies inside the picture."""
    page = layouts.Box(0, 0, found.width, found.height)
    boxes = [('card', card.id, card.box) for card in found.cards]
    boxes += [('machine', machine.card, machine.box) for machine in found.machines]
    boxes += [('frame', frame.label, frame.box) for frame in found.frames]
    if found.legend.items:
        boxes.append(('legend', None, found.legend.box))
    boxes += [('panel', panel.kind, panel.box) for panel in found.panels]
    members = {frame.label: set(frame.members) for frame in found.frames}
    for (kind_a, a, box_a), (kind_b, b, box_b) in itertools.combinations(boxes, 2):
        own = (kind_a == 'frame' and kind_b in ('card', 'machine') and b in members[a]) or (
            kind_b == 'frame' and kind_a in ('card', 'machine') and a in members[b]
        )
        assert own or not box_a.overlaps(box_b), (kind_a, a, kind_b, b)
    for _, _, box in boxes:
        assert within(box, page)
    groups = {
        group['label']: [m for m in group['members'] if m in cards] for group in picture.get('groups', ())
    }
    assert {frame.label: list(frame.members) for frame in found.frames} == {
        label: list(names) for label, names in groups.items() if names
    }
    for frame in found.frames:
        for name in frame.members:
            assert within(placed[name].box, frame.box)
        for machine in found.machines:
            if machine.card in frame.members:
                assert within(machine.box, frame.box)
    for card in found.cards:
        for part in (*card.stocks, *card.meters, *((card.more,) if card.more else ()), *card.machines):
            assert within(part.box, card.box), (card.id, part)
        assert within(card.icon_box, card.box)
        for pipe in card.pipes:
            assert all(within(layouts.Box(x, y, 0, 0), card.box) for x, y in pipe.points)
        for machine in card.machines:
            check_machine(machine)
    for machine in found.machines:
        check_machine(machine)
        card = placed[machine.card]
        # Beside its card: in the same column, below it.
        assert (machine.box.x, machine.box.width) == (card.box.x, card.box.width)
        assert machine.box.y >= card.box.bottom


def check_machine(machine):
    for state in machine.states:
        assert within(state.box, machine.box)
    for a, b in itertools.combinations(machine.states, 2):
        assert not a.box.overlaps(b.box)
    for step in machine.transitions:
        assert all(within(layouts.Box(x, y, 0, 0), machine.box) for x, y in step.points)
        assert all(x0 == x1 or y0 == y1 for (x0, y0), (x1, y1) in itertools.pairwise(step.points))
    assert [step.number for step in machine.transitions] == list(range(1, len(machine.transitions) + 1))


def check_columns(picture, found, cards):
    """At most `cards_per_column` cards to a column (D-52), and a layer in the fewest sub-columns that
    hold it; the columns in order from left to right; the stylesheet's column of a card holds, and its row
    in a layer without a member of a group; the cards with a row that are in no group follow their rows
    down each column; the members of a group are one block in each column, and the blocks go in the order
    of the groups."""
    _, most, _ = limits_of(picture)
    by_column = {}
    for card in found.cards:
        by_column.setdefault((card.column, card.sub), []).append(card)
    for column in by_column.values():
        assert len(column) <= most
        assert len({(card.box.x, card.box.width) for card in column}) == 1
    for a, b in itertools.combinations(found.cards, 2):
        if (a.column, a.sub) < (b.column, b.sub):
            assert a.box.right < b.box.x
        elif (b.column, b.sub) < (a.column, a.sub):
            assert b.box.right < a.box.x
    layers = {}
    for card in found.cards:
        layers.setdefault(card.column, []).append(card)
    for layer in layers.values():
        ordered = sorted(layer, key=lambda card: (card.sub, card.box.y))
        assert [card.row for card in ordered] == list(range(1, len(layer) + 1))
        assert len({card.sub for card in layer}) == math.ceil(len(layer) / most)
    for card in found.cards:
        place = cards[card.id].get('place')
        if place:
            assert card.column == place['column']
    member = {}
    for group in picture.get('groups', ()):
        for name in group['members']:
            member.setdefault(name, group['label'])
    labels = list(dict.fromkeys(member.values()))
    row_of = {c.id: (cards[c.id].get('place') or {}).get('row') for c in found.cards}
    # A row holds when the rows of a layer of at most `cards_per_column` cards are distinct and inside the
    # layer, and no member of a group is in the layer.
    for number, layer in layers.items():
        rows = [row_of[c.id] for c in layer if row_of[c.id]]
        if (
            len(layer) <= most
            and len(set(rows)) == len(rows)
            and all(r <= len(layer) for r in rows)
            and not any(c.id in member for c in layer)
        ):
            for card in layer:
                if row_of[card.id]:
                    assert card.row == row_of[card.id], (number, card.id)
    for column in by_column.values():
        down = sorted(column, key=lambda card: card.box.y)
        # When the rows of a column are distinct, the cards with a row that are in no group keep the
        # order of their rows.
        rows = [row_of[c.id] for c in down if row_of[c.id]]
        if len(set(rows)) == len(rows):
            loose = [row_of[c.id] for c in down if row_of[c.id] and c.id not in member]
            assert loose == sorted(loose), [c.id for c in down]
        # The members of each group are one block, the blocks in the order of the groups.
        runs = [label for label, _ in itertools.groupby(member.get(c.id) for c in down) if label is not None]
        assert runs == sorted(set(runs), key=labels.index), [c.id for c in down]


def same_bundle(a, b):
    """Whether two routes are in one bundle."""
    return a.bundle is not None and a.bundle == b.bundle


def check_routes(found, placed):
    """Each route: its segments horizontal or vertical; its start on its source's border and its end
    on its target's; no segment through a card or a machine beside a card. No two ends of arrows at one
    point of a card and no stretch of line shared by two routes, apart from the routes of one bundle,
    which share their start and the line from it (`check_bundles`). A card tall enough for the ends on
    each of its sides."""
    obstacles = [card.box for card in found.cards] + [machine.box for machine in found.machines]
    ends = {}
    for k, route in enumerate(found.routes):
        points = route.points
        assert len(points) >= 2
        for a, b in itertools.pairwise(points):
            assert a != b and (a[0] == b[0] or a[1] == b[1]), route
            for box in obstacles:
                assert not crosses(a, b, box), (route.source, route.target, route.kind, box)
        source, target = placed[route.source], placed[route.target]
        assert on_border(points[0], source.box) and on_border(points[-1], target.box), route
        # The ends are on the left or the right side.
        assert points[0][0] in (source.box.x, source.box.right) and points[-1][0] in (
            target.box.x,
            target.box.right,
        )
        key_a, key_b = (source.column, source.sub), (target.column, target.sub)
        assert route.back == (key_a > key_b)
        # The start of a route of a bundle is the bundle's; every other end is the route's own.
        starts = ('bundle', route.bundle) if route.bundle is not None else ('route', k)
        for card, point, owner in (
            (route.source, points[0], starts),
            (route.target, points[-1], ('route', k)),
        ):
            assert ends.setdefault(card, {}).setdefault(point, owner) == owner, (card, point)
    # No two routes share a stretch of line, unless they are in one bundle.
    lines = {}
    for k, route in enumerate(found.routes):
        for (x0, y0), (x1, y1) in itertools.pairwise(route.points):
            key = ('h', y0) if y0 == y1 else ('v', x0)
            low, high = (min(x0, x1), max(x0, x1)) if y0 == y1 else (min(y0, y1), max(y0, y1))
            lines.setdefault(key, []).append((low, high, k))
    for segments in lines.values():
        for (a0, a1, a), (b0, b1, b) in itertools.combinations(segments, 2):
            one = same_bundle(found.routes[a], found.routes[b])
            assert a == b or one or min(a1, b1) <= max(a0, b0), (found.routes[a], found.routes[b])
    for name, points in ends.items():
        box = placed[name].box
        for side in (box.x, box.right):
            count = sum(1 for x, _ in points if x == side)
            assert (count + 1) * layouts.PORT <= box.height


def most_meeting(intervals):
    """The most closed intervals [(low, high)] that meet at one point: a sweep over their ends, where a
    start at a point comes before an end there, so two intervals that touch meet."""
    ends = sorted([(low, 0) for low, _ in intervals] + [(high, 1) for _, high in intervals])
    most = held = 0
    for _, end in ends:
        held += -1 if end else 1
        most = max(most, held)
    return most


def verticals(found):
    """{gap: {owner: [(x, low, high)]}}: the vertical segments of the routes in each gap between two
    bands of columns, by their owner, ('bundle', index) for a route of a bundle and ('route', index) for
    each other route."""
    bands = []
    for low, high in sorted(
        (box.x, box.right) for box in [c.box for c in found.cards] + [m.box for m in found.machines]
    ):
        if bands and low <= bands[-1][1]:
            bands[-1][1] = max(bands[-1][1], high)
        else:
            bands.append([low, high])
    gaps = {}
    for k, route in enumerate(found.routes):
        owner = ('bundle', route.bundle) if route.bundle is not None else ('route', k)
        for (x0, y0), (x1, y1) in itertools.pairwise(route.points):
            if x0 == x1:
                gap = sum(1 for _, right in bands if right < x0)
                gaps.setdefault(gap, {}).setdefault(owner, []).append((x0, min(y0, y1), max(y0, y1)))
    return gaps


def check_tracks(found):
    """In each gap between two columns, the arrows use as few tracks as they can (D-50, D-51): as many as
    the most track intervals that meet at one height, each with half a track of room above and below.
    The vertical segments of a bundle's routes in a gap are on one track, and their interval is the
    bundle's trunk, from the lowest of them to the highest; each other vertical segment is an interval
    of its own. With the same heights, the trunks meet no more often than their segments one by one."""
    room = layouts.TRACK / 2
    for owners in verticals(found).values():
        trunks, own, tracks = [], [], set()
        for owner, segments in owners.items():
            xs = {x for x, _, _ in segments}
            assert len(xs) == 1 and (owner[0] == 'bundle' or len(segments) == 1), (owner, segments)
            tracks |= xs
            trunks.append(
                (min(low for _, low, _ in segments) - room, max(high for *_, high in segments) + room)
            )
            own += [(low - room, high + room) for _, low, high in segments]
        assert len(tracks) == most_meeting(trunks), owners
        assert most_meeting(trunks) <= most_meeting(own)


def lengths(points):
    """Each segment of a route with the length of the route before it."""
    out, at = [], 0.0
    for a, b in itertools.pairwise(points):
        out.append((a, b, at))
        at += abs(b[0] - a[0]) + abs(b[1] - a[1])
    return out


def meeting(a, b):
    """The parts of the route `a` (points) that lie on the route `b`, as merged intervals of the length
    along `a`: a stretch that they share, or one point where they cross or touch."""
    found = []
    for p, q, at in lengths(a):
        for r, s, _ in lengths(b):
            # A segment as the box of its two ends: two orthogonal segments meet where their boxes do.
            low = (max(min(p[0], q[0]), min(r[0], s[0])), max(min(p[1], q[1]), min(r[1], s[1])))
            high = (min(max(p[0], q[0]), max(r[0], s[0])), min(max(p[1], q[1]), max(r[1], s[1])))
            if low[0] <= high[0] and low[1] <= high[1]:
                ends = [abs(point[0] - p[0]) + abs(point[1] - p[1]) for point in (low, high)]
                found.append((at + min(ends), at + max(ends)))
    merged = []
    for low, high in sorted(found):
        if merged and low <= merged[-1][1]:
            merged[-1][1] = max(merged[-1][1], high)
        else:
            merged.append([low, high])
    return [tuple(span) for span in merged]


def point_at(points, length):
    """The point of a route at `length` along it."""
    for a, b, at in lengths(points):
        if length <= at + abs(b[0] - a[0]) + abs(b[1] - a[1]):
            step = length - at
            return tuple(p + (step if q > p else -step if q < p else 0.0) for p, q in zip(a, b))
    return points[-1]


def check_bundles(picture, found, placed):
    """The bundles (D-51). The arrows of one kind of the picture's `settings.bundle` from one card toward
    one side (right: to a later or the same column; left: to an earlier column) are one bundle when
    they are two or more, and no other arrows are. The routes of a bundle start at one point and share
    the line from it; after they split, they do not meet again. The junctions of a bundle are the
    points where two of its routes split."""
    settings = picture.get('settings') or {}
    kinds = settings.get('bundle', DEFAULT_BUNDLE)
    expected = {}
    for k, route in enumerate(found.routes):
        if route.kind in kinds:
            source, target = placed[route.source], placed[route.target]
            right = (target.column, target.sub) >= (source.column, source.sub)
            expected.setdefault((route.source, route.kind, 'right' if right else 'left'), []).append(k)
    groups = {}
    for k, route in enumerate(found.routes):
        if route.bundle is not None:
            groups.setdefault(route.bundle, []).append(k)
    assert sorted(groups) == list(range(len(found.bundles)))
    assert sorted(groups.values()) == sorted(members for members in expected.values() if len(members) > 1)
    for index, members in groups.items():
        bundle = found.bundles[index]
        routes = [found.routes[k] for k in members]
        assert {(r.source, r.kind) for r in routes} == {(bundle.source, bundle.kind)}
        assert bundle.targets == tuple(r.target for r in routes)
        assert members in expected.values() and expected[(bundle.source, bundle.kind, bundle.side)] == members
        assert len({r.points[0] for r in routes}) == 1
        splits = set()
        for a, b in itertools.combinations(routes, 2):
            # What a shares with b is one part from their start, as long in each.
            shared = meeting(a.points, b.points)
            assert len(shared) == 1 and shared[0][0] == 0 < shared[0][1], (a, b, shared)
            assert meeting(b.points, a.points) == shared, (a, b)
            splits.add(point_at(a.points, shared[0][1]))
        assert splits == set(bundle.junctions), (bundle, splits)


def check_meters(card):
    """The meters of a card: each as wide as its name, or as the inside of the card when the name does not
    fit, which shows its start and '…'; in rows from the top, a row as full as it can be before the next
    starts; no two with other names show one text."""
    inner = card.box.width - 2 * layouts.PAD
    rows = [list(row) for _, row in itertools.groupby(card.meters, key=lambda meter: meter.box.y)]
    assert len({meter.box.y for meter in card.meters}) == len(rows)
    for meter in card.meters:
        # A meter's text leaves the room of its tag (D-53).
        space = layouts.METER_TEXT + layouts.METER_END + tag_room(meter)
        assert layouts.text_width(meter.text, layouts.SMALL_SIZE) <= meter.box.width - space
        if meter.text != meter.name:
            assert meter.text.endswith('…') and meter.name.startswith(meter.text[:-1])
            assert meter.box.width == inner
        if layouts.text_width(meter.name, layouts.SMALL_SIZE) + space <= inner:
            assert meter.text == meter.name
    used = []
    for row in rows:
        assert all(a.box.right + layouts.ROW_GAP == b.box.x for a, b in itertools.pairwise(row))
        assert row[0].box.x == card.box.x + layouts.PAD
        used.append(row[-1].box.right - row[0].box.x)
        assert used[-1] <= inner
    for k in range(1, len(rows)):
        assert rows[k][0].box.y > rows[k - 1][0].box.y
        assert used[k - 1] + layouts.ROW_GAP + rows[k][0].box.width > inner
    for a, b in itertools.combinations(card.meters, 2):
        assert a.name == b.name or a.text != b.text, (a.name, b.name)


def check_cards(picture, found, cards):
    """The collapse: the title's lines, the width of a card, the stocks and meters that a card shows,
    its "+n" row, its pipes, and where its machines go."""
    most, _, least = limits_of(picture)
    beside = {}
    for machine in found.machines:
        beside.setdefault(machine.card, []).append(machine.var)
    for card in found.cards:
        given = cards[card.id]
        assert 1 <= len(card.lines) <= layouts.TITLE_LINES
        assert all(len(line) <= layouts.TITLE_WRAP for line in card.lines)
        if not card.lines[-1].endswith('…'):
            assert ''.join(card.lines).replace(' ', '') == ''.join(given['title'].split())
        # A card is at least `card_width` wide (D-52), and wide enough for its icon and title, to the
        # nearest 0.5 px.
        assert card.box.width >= least
        for line in card.lines:
            space = 2 * layouts.PAD + layouts.ICON + 6
            assert space + layouts.bold_width(line, layouts.TITLE_SIZE) <= card.box.width + 0.25
        stocks = given['stocks']
        kind = {stock['key']: stock['kind'] for stock in stocks}
        shown = [stock.key for stock in (*card.stocks, *card.meters)]
        assert all(stock.kind != 'tally' for stock in card.stocks)
        assert all(stock.kind == 'tally' for stock in card.meters)
        listed = given.get('stock_order')
        if listed is None:
            assert len(shown) == min(most, len(stocks))
            order = [stock['key'] for stock in stocks]
            assert [s.key for s in card.stocks] == [k for k in order if k in {s.key for s in card.stocks}]
            assert [s.key for s in card.meters] == [k for k in order if k in {s.key for s in card.meters}]
        else:
            # The first `stocks` rows of [stocks], in its order: its stocks above its tallies.
            wanted = [key for key in dict.fromkeys(listed) if key in kind][:most]
            assert [s.key for s in card.stocks] == [k for k in wanted if kind[k] != 'tally']
            assert [s.key for s in card.meters] == [k for k in wanted if kind[k] == 'tally']
        hidden = [stock for stock in stocks if stock['key'] not in shown]
        if card.meters:
            if listed is None:
                # Stocks come before tallies.
                assert all(stock['kind'] == 'tally' for stock in hidden)
            check_meters(card)
        more = len(hidden) + int(given.get('hidden_stocks') or 0)
        assert (card.more is None) == (more == 0)
        if card.more is not None:
            assert card.more.text == f'+{more} more' and sorted(card.more.keys) == sorted(
                s['key'] for s in hidden
            )
        # One pipe for each pair of ends; drawn between two stock rows, or a row and the outside.
        rows = {stock.key for stock in card.stocks}
        flows = {}
        for pipe in given['pipes']:
            flows.setdefault((pipe['from'], pipe['to']), []).extend(pipe['flows'])
        drawable = {
            ends: list(dict.fromkeys(names))
            for ends, names in flows.items()
            if all(end is None or end in rows for end in ends) and any(end is not None for end in ends)
        }
        assert {(p.source, p.target): list(p.flows) for p in card.pipes} == drawable
        assert len(card.pipes) == len(drawable)
        # A small machine goes inside unless the stylesheet puts it beside; a hidden one is not drawn.
        machines = given['machines']
        inside = [m['var'] for m in machines if m['place'] == 'inside' and is_small(m)]
        out = [m['var'] for m in machines if m['place'] != 'hidden' and m['var'] not in inside]
        assert [m.var for m in card.machines] == inside
        assert beside.get(card.id, []) == out
        check_triggers(card, given)
        check_tags(picture, card)


def tag_room(stock):
    """The width that the tag of a stock row or a meter takes from the right of its box, with the gap
    before it: 0 without a tag."""
    return 0.0 if stock.tag is None else stock.box.right - stock.tag.box.x + layouts.TAG_GAP


def check_tags(picture, card):
    """The tags of a card (D-53): exactly its shown stock rows and meters that `panels.tags` names have
    one, with the text of `tags`; the tag is inside its row at the right end, its symbol inside it, and
    the row's text keeps clear of it."""
    tags = (picture.get('panels') or {}).get('tags') or {}
    for stock in (*card.stocks, *card.meters):
        assert (stock.tag is not None) == (stock.key in tags), stock.key
        if stock.tag is None:
            continue
        tag = stock.tag
        assert tag.text == tags[stock.key]
        assert within(tag.box, stock.box) and stock.box.right - tag.box.right == layouts.TAG_INSET
        assert within(tag.math.box, tag.box)
        lines = tag.math.equation.lines
        assert len(lines) == 1 and all(
            within(atom.box, shifted(tag.math)) for atom in tag.math.equation.atoms()
        )
        if stock.kind != 'tally':
            assert 6 + layouts.text_width(stock.text, layouts.TEXT_SIZE) <= stock.box.width - tag_room(stock)


def shifted(math):
    """The box of a typeset node in its own coordinates (from its top left corner)."""
    return layouts.Box(0, 0, math.equation.width, math.equation.height)


# ---- the panels (D-53, D-55, D-57) ------------------------------------------------------------------


def runs_of(items):
    return [item for item in items if isinstance(item, layouts.Run)]


def marks_of(items):
    """[(number, kind)] of the marks among items, in order."""
    return [
        (mark.number, mark.kind) for item in items if isinstance(item, layouts.Marks) for mark in item.marks
    ]


def words_of(items):
    """The words of the runs among items, in order."""
    return ' '.join(run.text for run in runs_of(items)).split()


def text_of(items):
    """The text of the runs among items, in order, without spaces: a word that breaks over two rows is
    one word here."""
    return ''.join(run.text for run in runs_of(items)).replace(' ', '')


def check_items(items, box):
    """The items of a row: each inside its row, none on another; a set of marks after the item before it,
    raised above its baseline; each typeset node in its box."""
    for item in items:
        assert within(item.box, box), (item, box)
    for a, b in itertools.combinations(items, 2):
        assert not a.box.overlaps(b.box), (a, b)
    for item in items:
        if isinstance(item, layouts.Math):
            assert item.box == layouts.Box(item.x, item.y, item.equation.width, item.equation.height)
            assert all(within(atom.box, shifted(item)) for atom in item.equation.atoms())
        if isinstance(item, layouts.Marks):
            # Marks that go on from the row before start with a comma.
            assert item.text().removeprefix(',') == ','.join(str(mark.number) for mark in item.marks)
            assert item.size < layouts.TEXT_SIZE


def contains(items, wanted):
    """Whether the runs among items hold the text `wanted` (spaces aside)."""
    return wanted.replace(' ', '') in text_of(items)


def check_panels(picture, found):
    """The panels under the legend (D-53): one for each part that shows, in their order (the note
    under the table), each as wide as `settings.width`. When the picture above them is wide enough for
    two, the Equations at the left margin and the others in a second column from the same top; else all
    at the left margin; each below the legend and the panel before it in its column. The rows of each
    inside it, one under another, and their items inside them (`check_items`). Then each panel says what
    the picture holds (`check_equations`, `check_table`, `check_entries`), and the note is its words."""
    data = picture.get('panels')
    if not data:
        assert found.panels == ()
        return
    settings = data['settings']
    kinds = ['equations']
    kinds += ['symbols'] if settings['symbols'] and data['symbols'] else []
    kinds += ['note'] if data['note'] else []
    kinds += ['references'] if data['references'] or data.get('left_out') else []
    assert [panel.kind for panel in found.panels] == kinds
    page = layouts.Box(0, 0, found.width, found.height)
    # The picture above the panels is as wide as its right-most card, machine or legend with a margin,
    # as the right-most track of an arrow with the edge of its gap and a margin, and as its title. A
    # frame does not make it wider: a frame reaches into the margin around its members.
    above_panels = [found.legend.box, *(c.box for c in found.cards), *(m.box for m in found.machines)]
    tracks = max((x for route in found.routes for x, _ in route.points), default=0.0)
    room = layouts.half(
        max(
            max(box.right for box in above_panels) + layouts.MARGIN,
            tracks + layouts.GAP_EDGE + layouts.MARGIN,
            layouts.bold_width(str(picture.get('title', '')), layouts.PICTURE_TITLE_SIZE)
            + 2 * layouts.MARGIN,
            320.0,
        )
    )
    width = settings['width']
    two = room >= 2 * layouts.MARGIN + 2 * width + layouts.PANEL_GAP
    second = layouts.MARGIN + width + layouts.PANEL_GAP
    lefts = [layouts.MARGIN] + [second if two else layouts.MARGIN] * (len(found.panels) - 1)
    assert [(panel.box.x, panel.box.width) for panel in found.panels] == [(x, width) for x in lefts]
    if two and len(found.panels) > 1:
        assert found.panels[1].box.y == found.panels[0].box.y
    above = {x: found.legend.box.bottom for x in set(lefts)}
    for panel in found.panels:
        assert panel.box.y >= above[panel.box.x] and within(panel.box, page)
        above[panel.box.x] = panel.box.bottom
    for a, b in itertools.combinations(found.panels, 2):
        apart = a.box.right <= b.box.x or b.box.right <= a.box.x
        assert apart or a.box.bottom <= b.box.y or b.box.bottom <= a.box.y, (a.kind, b.kind)
    for panel in found.panels:
        top = panel.box.y
        if panel.heading is not None:
            assert within(panel.heading.box, panel.box) and panel.heading.look == 'heading'
            top = panel.heading.box.bottom
        for row in panel.rows:
            assert within(row.box, panel.box) and row.box.y >= top, (panel.kind, row)
            top = row.box.bottom
            if isinstance(row, layouts.SymbolRow):
                for cell in row.cells:
                    assert within(cell.box, row.box)
                    check_items(cell.items, cell.box)
                for a, b in itertools.pairwise(row.cells):
                    assert a.box.right <= b.box.x
            else:
                check_items(row.items, row.box)
    by_kind = {panel.kind: panel for panel in found.panels}
    check_equations(data, by_kind['equations'])
    if 'symbols' in by_kind:
        check_table(data, by_kind['symbols'])
    if 'references' in by_kind:
        check_entries(data, by_kind['references'])
    if 'note' in by_kind:
        (row,) = by_kind['note'].rows
        assert text_of(row.items) == data['note'].replace(' ', '')


def check_equations(data, panel):
    """A head for each block, then a row for each of its lines, or a row "No equations." for a block
    without lines. A line keeps its LaTeX, its part and its records; its math shows at most `lines` rows
    of each typeset tree, its words follow it, and its marks are the line's, last."""
    rows = list(panel.rows)
    most = data['settings']['lines']
    for b, block in enumerate(data['equations']):
        head = rows.pop(0)
        assert isinstance(head, layouts.Block) and (head.index, head.name, head.title) == (
            b,
            block['name'],
            block['title'],
        )
        assert head.members == tuple(member['title'] for member in block['members'])
        assert contains(head.items, block['title'])
        if len(block['members']) > 1:
            for member in block['members']:
                assert contains(head.items, member['title'])
        if not block['lines']:
            empty = rows.pop(0)
            assert isinstance(empty, layouts.Note) and empty.kind == 'empty'
        for k, line in enumerate(block['lines']):
            row = rows.pop(0)
            assert isinstance(row, layouts.EquationLine)
            assert (row.block, row.index, row.kind, row.part) == (b, k, line['kind'], line['part'])
            assert row.latex == line['latex'] and row.records == tuple(line['records'])
            maths = [item for item in row.items if isinstance(item, layouts.Math)]
            assert all(len(item.equation.lines) <= most for item in maths)
            if line['words']:
                assert contains(row.items, line['words'])
            assert marks_of(row.items) == [tuple(mark) for mark in line['marks']]
            if line['marks']:
                assert isinstance(row.items[-1], layouts.Marks)
    assert rows == []


def first_item(items):
    """The item that a reader meets first: the left-most item of the top row, or None without items."""
    if not items:
        return None
    top = min(items, key=lambda item: item.box.y)
    return min((item for item in items if item.box.y < top.box.bottom), key=lambda item: item.box.x)


def check_table(data, panel):
    """The Symbols table: its head, then a row for each symbol in order, in the columns of `COLUMNS`
    that hold something (the symbol and the meaning always); each column at one x and width in every
    row. A row shows its meaning, its unit and its value, "chosen range" exactly when its range is a
    chosen one, and the marks of its value, its options and its range, in that order."""
    head, *rows = panel.rows
    assert head.key is None
    assert [row.key for row in rows] == [row['key'] for row in data['symbols']]
    columns = [cell.column for cell in head.cells]
    assert columns[:2] == ['symbol', 'meaning'] and columns == [c for c in layouts.COLUMNS if c in columns]
    for row in panel.rows:
        assert [cell.column for cell in row.cells] == columns
        assert [(cell.box.x, cell.box.width) for cell in row.cells] == [
            (cell.box.x, cell.box.width) for cell in head.cells
        ]
    for row, wanted in zip(rows, data['symbols']):
        cells = {cell.column: cell for cell in row.cells}
        assert row.records == tuple(wanted['records'])
        assert contains(cells['meaning'].items, wanted['meaning'].rstrip('.'))
        if wanted['unit']:
            assert text_of(cells['unit'].items) == wanted['unit'].replace(' ', '')
        # The row's own start is at the top of its cell, alone on its rows: the start of an instance or
        # of an option comes under it, after its name. So the start is typeset exactly when the first
        # item of the cell is math; any other math of the cell is the start of an instance or an option.
        first = first_item(getattr(cells.get('value'), 'items', ()))
        if wanted['value_math'] is not None and isinstance(first, layouts.Math):
            # A start that a formula sets: typeset, with the symbol of each value that it names (of
            # what shows, when the line is cut and says so).
            reading = first.equation.reading()
            symbols = {row['key']: row['symbol'] for row in data['symbols']}
            if typeset.MARKER not in reading:
                for node in notation.nodes(notation.from_dict(wanted['value_math'])):
                    if isinstance(node, notation.Sym):
                        symbol = symbols[node.key]
                        written = typeset.letters(symbol['base']) + typeset.primes(symbol['prime'])
                        assert written + (symbol['sub'] or '') in reading
        elif wanted['value_math'] is not None:
            # A column too narrow for the math: the start as the file writes it.
            assert wanted['value'] and contains(cells['value'].items, wanted['value'])
        elif wanted['value'] is not None:
            assert contains(cells['value'].items, wanted['value'])
        if wanted['distribution']:
            assert text_of(cells['distribution'].items) == wanted['distribution'].replace(' ', '')
        ranged = text_of(cells['range'].items) if 'range' in cells else ''
        chosen = wanted['range'] is not None and wanted['range_status'] == 'chosen'
        assert ('chosenrange' in ranged) == chosen
        assert (ranged != '') == (wanted['range'] is not None)
        options = [tuple(mark) for option in wanted['options'] for mark in option['marks']]
        expected = (
            [tuple(mark) for mark in wanted['marks']] + options + [tuple(m) for m in wanted['range_marks']]
        )
        assert [mark for cell in row.cells for mark in marks_of(cell.items)] == expected
        maths = [item for item in cells['symbol'].items if isinstance(item, layouts.Math)]
        assert len(maths) == (2 if wanted['count'] else 1)


def check_entries(data, panel):
    """The References: an entry for each, numbered 1 to n in order; each starts with its number, then its
    label in bold, then its text; its link is the entry's `http` or `https` address and shows its link
    text, and an entry without such an address has no link."""
    entries = data['references']
    rows = list(panel.rows)
    if data.get('left_out'):
        # First, the line that names the kinds that the list leaves out, each in its words.
        line = rows.pop(0)
        assert isinstance(line, layouts.Note) and all(run.look == 'muted' for run in runs_of(line.items))
        said = text_of(line.items)
        assert said.startswith('Notlisted:')
        assert all(LEFT_OUT_WORDS[kind].replace(' ', '') in said for kind in data['left_out'])
    assert [entry.number for entry in rows] == [entry['number'] for entry in entries]
    assert [entry.number for entry in rows] == list(range(1, len(entries) + 1))
    for row, wanted in zip(rows, entries):
        assert (row.kind, row.hover, row.record) == (wanted['kind'], wanted['hover'], tuple(wanted['record']))
        number, *runs = runs_of(row.items)
        assert (number.look, number.text) == ('number', f'{wanted["number"]}.')
        assert runs[0].look == 'strong' and text_of(runs).startswith(wanted['label'].replace(' ', ''))
        assert contains(row.items, wanted['text'])
        links = [run for run in runs if run.url is not None]
        web = wanted['url'] is not None and layouts.web_host(wanted['url']) is not None
        assert row.url == (wanted['url'] if web else None)
        assert all(run.url == wanted['url'] and run.look == 'link' for run in links)
        assert bool(links) == web
        if web:
            assert ''.join(run.text for run in links).replace(' ', '') == (
                str(wanted['link_text'] or '').strip() or wanted['url']
            ).replace(' ', '')


def check_triggers(card, given):
    """The rows of the events of a card (`[triggers]`, D-56): none without `triggers` and at `hover`;
    at `count` one row for every event, which says their number; at `names` and `rules` a row for each
    event with a text, in order, then a "+n more" row for the others. A row is inside the card, as wide
    as its inside, under its other parts and apart from the other rows; each line fits the width of the
    row's text; a row has one line, or at most `lines` at `rules`, where a line that does not fit is cut
    and ends with '…', and the bold start of a row is of the event's name. The tooltip gives the full
    line of every event at every level."""
    found = given.get('triggers')
    rows = card.triggers
    if found is None:
        assert rows == () and card.events == ()
        return
    events, level = found['events'], found['level']
    assert [(line.event, line.full) for line in card.events] == [(e['event'], e['full']) for e in events]
    if level == 'hover':
        assert rows == ()
    elif level == 'count':
        (row,) = rows
        assert row.kind == 'count' and row.events == tuple(e['event'] for e in events)
        assert str(len(events)) in row.lines[0].split()
    else:
        shown = [e for e in events if e['text'] is not None]
        kind = 'rule' if level == 'rules' else 'name'
        expected = [(kind, (e['event'],)) for e in shown]
        if found['more']:
            expected.append(('more', tuple(e['event'] for e in events if e['text'] is None)))
            assert rows[-1].lines == (f'+{found["more"]} more',)
        assert [(row.kind, row.events) for row in rows] == expected
        most = int(found['lines']) if level == 'rules' else 1
        for row, event in zip(rows, shown):
            assert 1 <= len(row.lines) <= most
            kept = ''.join(row.lines).replace(' ', '')
            whole = event['text'].replace(' ', '')
            if row.lines[-1].endswith('…'):
                assert kept[:-1] and whole.startswith(kept[:-1]) and len(kept) - 1 < len(whole)
            else:
                assert kept == whole
            if level == 'rules':
                assert len(row.strong) == len(row.lines)
                bold = ''.join(line[:k] for line, k in zip(row.lines, row.strong))
                assert event['name'].replace(' ', '').startswith(bold.replace(' ', ''))
                assert row.strong[0] > 0
        if level == 'rules':
            assert card.box.width >= layouts.RULES_WIDTH
    others = [part.box for part in (*card.stocks, *card.meters, *card.machines)]
    others += [card.more.box] if card.more else []
    for row in rows:
        assert within(row.box, card.box)
        assert (row.box.x, row.box.width) == (card.box.x + layouts.PAD, card.box.width - 2 * layouts.PAD)
        assert row.box.height == len(row.lines) * layouts.TRIGGER_LINE
        # The text starts inside the row, after the mark, and each line ends inside it.
        x, y = row.text_at
        assert row.box.x < x < row.box.right and row.box.y < y <= row.box.y + layouts.TRIGGER_LINE
        for line in row.lines:
            assert layouts.text_width(line, layouts.SMALL_SIZE) <= row.box.right - x
        assert all(row.box.y >= box.bottom for box in others), (card.id, row)
    for a, b in itertools.pairwise(rows):
        assert b.box.y >= a.box.bottom


# ---- the frozen picture -------------------------------------------------------------------------


def test_the_layout_of_the_frozen_picture_holds_every_property():
    check(PICTURE, layout(load()))


def test_the_frozen_picture_keeps_what_its_stylesheet_says():
    found = layout(load())
    cards = {card.id: card for card in found.cards}
    # The placed cards keep their column (and row); the group is one frame around its two members.
    assert cards['attacker'].column == 1
    assert (cards['hospital'].column, cards['hospital'].row) == (4, 1)
    assert [(f.label, f.members) for f in found.frames] == [('Water systems', ('plant', 'town'))]
    # The plant's big machine goes beside it, the crews' machine beside them as the stylesheet says,
    # the attacker's small one inside, and the hidden valve nowhere.
    assert [m.var for m in cards['attacker'].machines] == ['attacker.access']
    assert [(m.card, m.var) for m in found.machines] == [('plant', 'plant.mode'), ('crews', 'crews.status')]
    assert all(m.var != 'plant.valve' for card in found.cards for m in card.machines)
    # Seven stocks and tallies: four shown, the stocks first, and "+3".
    assert (
        len(cards['plant'].stocks) == 4
        and not cards['plant'].meters
        and cards['plant'].more.text == '+3 more'
    )
    # The pipe from raw water to treated water shows its number of flows.
    merged = [p for p in cards['plant'].pipes if (p.source, p.target) == ('plant.raw', 'plant.treated')]
    assert [len(p.flows) for p in merged] == [3] and merged[0].label == '3'
    # The isolated card takes the last layer, under the placed card with row 1.
    assert cards['weather'].column == max(card.column for card in found.cards)
    assert cards['weather'].box.y > cards['hospital'].box.bottom


def test_the_same_picture_gives_the_same_layout():
    first = layout(load())
    assert layout(load()) == first
    # The order of the keys of each dict changes nothing.
    turned = json.loads(json.dumps(load()), object_pairs_hook=lambda pairs: dict(reversed(pairs)))
    assert layout(turned) == first


def test_an_arrow_to_a_card_that_is_not_drawn_is_left_out():
    picture = load()
    picture['arrows'].append({'from': 'plant', 'to': 'nowhere', 'kind': 'reads', 'count': 1, 'values': ['x']})
    picture['arrows'].append({'from': 'town', 'to': 'town', 'kind': 'reads', 'count': 1, 'values': ['x']})
    found = layout(picture)
    check(picture, found)
    assert len(found.routes) == len(PICTURE['arrows'])


def test_another_direction_is_refused():
    picture = load()
    picture['direction'] = 'top-to-bottom'
    with pytest.raises(ValueError):
        layout(picture)


# ---- counterexamples ------------------------------------------------------------------------------


def card(name, **extra):
    found = {
        'id': name,
        'title': name.capitalize(),
        'role': None,
        'icon': None,
        'template': None,
        'copies': 1,
        'place': None,
        'stocks': [],
        'hidden_stocks': 0,
        'pipes': [],
        'machines': [],
    }
    return {**found, **extra}


def arrow(a, b, kind='changes'):
    return {'from': a, 'to': b, 'kind': kind, 'count': 1, 'values': [f'{b}.x']}


def picture_of(cards, arrows=(), groups=(), settings=None):
    """A picture of these parts; with `settings` (D-52) when they are given, else the layout's
    defaults."""
    found = {
        'name': 'sample',
        'title': 'A sample',
        'run': None,
        'direction': 'left-to-right',
        'cards': list(cards),
        'arrows': sorted(arrows, key=lambda a: (a['from'], a['to'], a['kind'])),
        'groups': list(groups),
    }
    if settings is not None:
        found['settings'] = dict(settings)
    return found


def test_the_sweeps_undo_a_ladder_given_crossed():
    # a_k changes b_k; the b cards come in the reverse order. One order of each column has no crossing,
    # and the sweeps find it: the b cards stand in the order of their a cards.
    count = 5
    cards = [card(f'a{k}') for k in range(count)] + [card(f'b{k}') for k in reversed(range(count))]
    found = layout(picture_of(cards, [arrow(f'a{k}', f'b{k}') for k in range(count)]))
    y = {c.id: c.box.y for c in found.cards}
    a = sorted(range(count), key=lambda k: y[f'a{k}'])
    b = sorted(range(count), key=lambda k: y[f'b{k}'])
    assert a == b


def test_a_cycle_is_broken_and_its_back_arrow_ends_at_its_true_end():
    cards = [card(name) for name in 'abc']
    arrows = [arrow('a', 'b'), arrow('b', 'c'), arrow('c', 'a', 'moves')]
    found = layout(picture_of(cards, arrows))
    placed = {c.id: c for c in found.cards}
    back = [route for route in found.routes if route.back]
    assert len(back) == 1
    route = back[0]
    assert on_border(route.points[-1], placed[route.target].box)
    assert placed[route.target].box.x < placed[route.source].box.x


def test_an_arrow_inside_one_column_uses_the_gap_on_its_right():
    cards = [card('a', place={'column': 1, 'row': None}), card('b', place={'column': 1, 'row': None})]
    found = layout(picture_of(cards, [arrow('a', 'b', 'reads')]))
    (route,) = found.routes
    right = found.cards[0].box.right
    assert all(x >= right for x, _ in route.points)
    assert route.points[0][0] == route.points[-1][0] == right


def test_a_full_layer_splits_into_sub_columns_of_at_most_eight():
    cards = [card(f'c{k:02d}') for k in range(20)]
    found = layout(picture_of(cards))
    subs = {}
    for c in found.cards:
        subs.setdefault((c.column, c.sub), []).append(c)
    assert sorted(len(v) for v in subs.values()) == [6, 7, 7]
    check(picture_of(cards), found)


def bundling(picture, kinds):
    """`picture` with `kinds` as the kinds that bundle (`settings.bundle`, D-51)."""
    return {**picture, 'settings': {**(picture.get('settings') or {}), 'bundle': list(kinds)}}


def sub_columns(found):
    """{(layer, sub-column): [card id, …]} of a layout."""
    subs = {}
    for c in found.cards:
        subs.setdefault((c.column, c.sub), []).append(c.id)
    return subs


def test_two_cards_to_a_column_split_a_layer_of_five_into_three():
    # D-52: cards_per_column = 2. Five cards with no arrow are one layer: ceil(5 / 2) = 3 sub-columns.
    picture = picture_of([card(f'c{k}') for k in range(5)], settings={'cards_per_column': 2})
    found = layout(picture)
    check(picture, found)
    assert sorted(len(v) for v in sub_columns(found).values()) == [1, 2, 2]
    # The default holds all five in one column.
    assert len(sub_columns(layout(picture_of([card(f'c{k}') for k in range(5)])))) == 1


def test_a_full_sub_column_sends_a_card_with_a_row_to_the_nearest_one_with_room():
    # Three cards of one layer in sub-columns of two: rows 3, 4 and 5 all fall in the second, which holds
    # two, so the last row goes to the first.
    cards = [card(f'r{row}', place={'column': 1, 'row': row}) for row in (3, 4, 5)]
    picture = picture_of(cards, settings={'cards_per_column': 2})
    found = layout(picture)
    check(picture, found)
    assert sorted(len(v) for v in sub_columns(found).values()) == [1, 2]


def test_the_rows_of_a_layer_count_on_when_a_later_sub_column_is_full_first():
    # Nine cards, so two sub-columns of at most five: the five with rows 6 to 10 fill the second, and the
    # four without a row are the first. The rows of the layer count 1 to 9, the second sub-column after the
    # first.
    cards = [card(f'p{row}', place={'column': 1, 'row': row}) for row in range(6, 11)]
    cards += [card(f'f{k}', place={'column': 1, 'row': None}) for k in range(4)]
    picture = picture_of(cards)
    found = layout(picture)
    check(picture, found)
    rows = {c.id: (c.sub, c.row) for c in found.cards}
    assert sorted(rows[f'p{row}'] for row in range(6, 11)) == [(1, row) for row in range(5, 10)]


def stocks_of(*kinds):
    """The stocks of a card `m`, `m.s0`, `m.s1`, …, of these kinds."""
    return [{'key': f'm.s{k}', 'name': f'Stock {k}', 'kind': kind} for k, kind in enumerate(kinds)]


def test_the_stock_order_shows_its_rows_in_its_order_and_the_others_in_more():
    stocks = stocks_of('stock', 'stock', 'tally', 'stock', 'tally')
    for most, order, rows, meters in (
        # All three listed rows fit: the stocks in the order of the list, above the tally.
        (4, ['m.s3', 'm.s2', 'm.s0'], ['m.s3', 'm.s0'], ['m.s2']),
        # Two rows: the first two of the list.
        (2, ['m.s3', 'm.s2', 'm.s0'], ['m.s3'], ['m.s2']),
        # A list of tallies shows no stock row, though stocks come first without a list.
        (4, ['m.s4', 'm.s2'], [], ['m.s4', 'm.s2']),
    ):
        picture = picture_of([card('m', stocks=stocks, stock_order=order)], settings={'stocks': most})
        found = layout(picture)
        check(picture, found)
        (placed,) = found.cards
        assert [s.key for s in placed.stocks] == rows and [s.key for s in placed.meters] == meters
        others = sorted(s['key'] for s in stocks if s['key'] not in rows + meters)
        assert sorted(placed.more.keys) == others and placed.more.text == f'+{len(others)} more'


def test_one_stock_row_shows_one_row_and_the_others_in_more():
    stocks = stocks_of('tally', 'stock', 'stock')
    picture = picture_of([card('m', stocks=stocks)], settings={'stocks': 1})
    found = layout(picture)
    check(picture, found)
    (placed,) = found.cards
    assert len(placed.stocks) + len(placed.meters) == 1
    assert placed.more.text == '+2 more' and len(placed.more.keys) == 2


def test_a_card_is_as_wide_as_the_card_width_unless_it_needs_more():
    # A short title needs less than 300 px: each card is 300 px wide, the least width of the setting.
    picture = picture_of(
        [card('a'), card('b', place={'column': 2, 'row': None})], settings={'card_width': 300}
    )
    found = layout(picture)
    check(picture, found)
    assert {c.box.width for c in found.cards} == {300}
    # A title of two lines of 28 characters needs more than 170 px: its card is wider.
    long = card('c', title=' '.join(['w' * 28] * 2))
    picture = picture_of([long], settings={'card_width': 170})
    found = layout(picture)
    check(picture, found)
    assert found.cards[0].box.width > 170


def test_a_card_grows_taller_for_the_ends_of_its_arrows():
    # Twenty-four cards in the second column read the hub. Without bundles its right side holds 24
    # ends; as one bundle, they hold one, and the hub keeps the height of what it holds.
    many = 24
    others = [card(f'r{k:02d}', place={'column': 2, 'row': None}) for k in range(many)]
    picture = picture_of(
        [card('hub', place={'column': 1, 'row': None}), *others],
        [arrow('hub', f'r{k:02d}', 'reads') for k in range(many)],
    )
    alone = layout(picture_of([card('hub')])).cards[0].box.height
    plain = bundling(picture, [])
    found = layout(plain)
    check(plain, found)
    assert found.cards[0].box.height >= (many + 1) * layouts.PORT
    assert found.cards[0].box.height > alone
    found = layout(picture)
    check(picture, found)
    assert len(found.bundles) == 1 and len({route.points[0] for route in found.routes}) == 1
    assert found.cards[0].box.height == alone


def tallies(*names):
    return [{'key': f'm.t{k}', 'name': name, 'kind': 'tally'} for k, name in enumerate(names)]


def test_meters_with_one_long_start_show_other_texts():
    # The names differ only after a start longer than any meter: the card grows until their texts differ.
    start = 'x' * 60
    for names in ((f'{start} a', f'{start} b'), (f'{start}a{start}', f'{start}b{start}', 'y')):
        picture = picture_of([card('m', stocks=tallies(*names))])
        found = layout(picture)
        check(picture, found)
        (placed,) = found.cards
        texts = [meter.text for meter in placed.meters]
        assert len(set(texts)) == len(names), texts


def test_meters_wrap_onto_more_rows():
    # Four tallies whose names are as wide as the card: one row each.
    names = [f'{k} {"w" * 30}' for k in range(4)]
    picture = picture_of([card('m', stocks=tallies(*names))])
    found = layout(picture)
    check(picture, found)
    (placed,) = found.cards
    assert len({meter.box.y for meter in placed.meters}) > 1
    # In a wider column, the rows stay inside the card.
    wide = picture_of([card('m', stocks=tallies(*names)), card('n', title='n' * 28 + ' ' + 'n' * 28)])
    check(wide, layout(wide))


def test_a_hidden_kind_draws_no_arrow_and_the_legend_says_so():
    # D-51: [arrows] reads = "hidden". The picture keeps its reads; the layout draws none of them.
    cards = [card('a'), card('b'), card('c')]
    arrows = [arrow('a', 'b', 'reads'), arrow('b', 'c', 'changes'), arrow('c', 'a', 'reads')]
    doc = picture_of(cards, arrows)
    doc['settings'] = {'looks': {kind: 'full' for kind in KINDS} | {'reads': 'hidden', 'fires': 'hidden'}}
    found = layout(doc)
    check(doc, found)
    assert {route.kind for route in found.routes} == {'changes'}
    # Only a hidden kind that the picture has is in the legend: fires is hidden but absent.
    assert found.legend.hidden == ('reads',)
    words = {mark: text for mark, text, _ in found.legend.items}
    assert words['reads'].endswith(': not drawn') and 'fires' not in words


def test_the_options_that_set_a_start_wrap_and_never_widen_the_machine():
    # D-59: a long list of options that set a state's start wraps inside the machine's width.
    machine = {
        'var': 'a.mode',
        'name': 'Mode',
        'states': ['off', 'on'],
        'initial': 'off',
        'transitions': [],
        'place': 'inside',
    }
    starts = [{'option': f'An option with a long name number {k}', 'state': 'on'} for k in range(6)]
    plain = layout(picture_of([card('a', machines=[machine])]))
    long = layout(picture_of([card('a', machines=[{**machine, 'starts_by': starts}])]))
    (before,), (after,) = plain.cards[0].machines, long.cards[0].machines
    assert after.box.width == before.box.width
    lines = [text for number, text, _ in after.key if number == '']
    assert 1 < len(lines) <= layouts.START_LINES
    inner = after.box.width - 2 * layouts.MPAD
    assert all(layouts.text_width(line, layouts.SMALL_SIZE) <= inner for line in lines)


def test_a_hidden_kind_places_no_card():
    # The owner's choice after CP-A: a kind that [arrows] hides does not rank the cards. A chain of
    # changes a → b → c puts the cards in three columns; with changes hidden, no arrow places them, so
    # they share the last column.
    cards = [card('a'), card('b'), card('c')]
    chain = [arrow('a', 'b', 'changes'), arrow('b', 'c', 'changes')]
    shown = layout(picture_of(cards, chain))
    hidden = picture_of(cards, chain)
    hidden['settings'] = {'looks': {kind: 'full' for kind in KINDS} | {'changes': 'hidden'}}
    closed = layout(hidden)
    check(hidden, closed)
    assert len({c.column for c in shown.cards}) == 3
    assert len({c.column for c in closed.cards}) == 1


def test_two_arrows_of_other_kinds_between_one_pair_stay_separate():
    cards = [card('a'), card('b')]
    arrows = [arrow('a', 'b', kind) for kind in KINDS] + [arrow('b', 'a', 'reads')]
    found = layout(picture_of(cards, arrows))
    assert len(found.routes) == len(KINDS) + 1
    assert len({route.points for route in found.routes}) == len(KINDS) + 1


def tracks_of(found):
    """The tracks in each gap: the distinct x of the vertical segments."""
    return {
        gap: len({x for segments in owners.values() for x, _, _ in segments})
        for gap, owners in verticals(found).items()
    }


def test_six_readers_in_the_next_column_share_one_track():
    # One arrow to a track would need more than one track here; the bundle needs one (D-51).
    readers = [card(f'r{k}', place={'column': 2, 'row': None}) for k in range(6)]
    picture = picture_of(
        [card('s', place={'column': 1, 'row': None}), *readers],
        [arrow('s', f'r{k}', 'reads') for k in range(6)],
    )
    found = layout(picture)
    check(picture, found)
    assert tracks_of(found) == {1: 1}
    assert len(found.bundles) == 1 and found.bundles[0].side == 'right'
    plain = bundling(picture, [])
    alone = layout(plain)
    check(plain, alone)
    assert not alone.bundles and tracks_of(alone)[1] > 1


def test_a_bundle_shares_one_slot_in_each_column_that_it_passes():
    # Two readers in column 4 read a card in column 1: their routes pass columns 2 and 3 on one line.
    picture = picture_of(
        [
            card('s', place={'column': 1, 'row': None}),
            card('m', place={'column': 2, 'row': None}),
            card('n', place={'column': 3, 'row': None}),
            card('a', place={'column': 4, 'row': None}),
            card('b', place={'column': 4, 'row': None}),
        ],
        [arrow('s', 'a', 'reads'), arrow('s', 'b', 'reads'), arrow('m', 'n')],
    )

    def lines_through(found, name):
        box = next(c.box for c in found.cards if c.id == name)
        return {
            y0
            for route in found.routes
            if route.source == 's'
            for (x0, y0), (x1, y1) in itertools.pairwise(route.points)
            if y0 == y1 and min(x0, x1) <= box.x and box.right <= max(x0, x1)
        }

    found = layout(picture)
    check(picture, found)
    assert len(lines_through(found, 'm')) == len(lines_through(found, 'n')) == 1
    plain = bundling(picture, [])
    alone = layout(plain)
    check(plain, alone)
    assert len(lines_through(alone, 'm')) == len(lines_through(alone, 'n')) == 2


def test_a_bundle_counts_each_segment_of_its_tree_once_in_the_order():
    # Four readers in column 4: the bundle's tree has one segment between columns 1 and 2 and between 2
    # and 3, and one to each reader; one arrow at a time, each segment counts four times. The arrow from
    # m to n is the one other segment between columns 2 and 3.
    picture = picture_of(
        [
            card('s', place={'column': 1, 'row': None}),
            card('m', place={'column': 2, 'row': None}),
            card('n', place={'column': 3, 'row': None}),
            *(card(f'r{k}', place={'column': 4, 'row': None}) for k in range(4)),
        ],
        [*(arrow('s', f'r{k}', 'reads') for k in range(4)), arrow('m', 'n')],
    )
    for kinds, expected in (((), [4, 5, 4]), (DEFAULT_BUNDLE, [1, 2, 4])):
        work = layouts._Work(bundling(picture, kinds))
        work.columns()
        work.segments()
        assert [len(work.links[column]) for column in range(3)] == expected
        weights = {w for links in work.links.values() for u, _, w in links if u == ('card', 's')}
        assert weights == {layouts.WEIGHTS['reads']}


def test_bundles_go_left_and_to_their_own_column_with_a_dot_at_each_branch():
    # s reads two cards to its left, three to its right (one two columns away) and one in its column.
    cards = [
        card('l1', place={'column': 1, 'row': None}),
        card('l2', place={'column': 1, 'row': None}),
        card('s', place={'column': 2, 'row': None}),
        card('c', place={'column': 2, 'row': None}),
        card('r1', place={'column': 3, 'row': None}),
        card('r2', place={'column': 3, 'row': None}),
        card('far', place={'column': 4, 'row': None}),
    ]
    readers = ('l1', 'l2', 'c', 'r1', 'r2', 'far')
    picture = picture_of(
        cards, [*(arrow('s', name, 'reads') for name in readers), arrow('s', 'r1', 'follows')]
    )
    found = layout(picture)
    check(picture, found)
    sides = {bundle.side: set(bundle.targets) for bundle in found.bundles}
    assert sides == {'left': {'l1', 'l2'}, 'right': {'c', 'r1', 'r2', 'far'}}
    assert all(bundle.kind == 'reads' and bundle.junctions for bundle in found.bundles)
    # The follows arrow is alone: an arrow of its own.
    assert [r.bundle for r in found.routes if r.kind == 'follows'] == [None]


def test_a_group_is_one_band_and_the_cards_between_go_above_or_below_it():
    # g1 and g2 are in a group in the first and third columns; m, in the middle column, is not.
    cards = [card('g1'), card('m'), card('g2'), card('n')]
    arrows = [arrow('g1', 'm'), arrow('m', 'g2'), arrow('n', 'm', 'reads')]
    groups = [{'label': 'Pair', 'members': ['g1', 'g2']}]
    picture = picture_of(cards, arrows, groups)
    found = layout(picture)
    check(picture, found)
    (frame,) = found.frames
    middle = next(c for c in found.cards if c.id == 'm')
    assert frame.box.x < middle.box.x < frame.box.right
    assert middle.box.bottom <= frame.box.y or middle.box.y >= frame.box.bottom


def column_of(found, column=1):
    """The ids of the cards of a column, from top to bottom."""
    return [c.id for c in sorted(found.cards, key=lambda c: c.box.y) if c.column == column]


def test_a_row_inside_a_group_puts_its_card_next_to_the_group():
    # The row of c falls between a and b, which are one group: c goes to the nearer end of the group, after
    # it on a tie, and the frame holds a and b only.
    cards = [card('a', place={'column': 1, 'row': None}), card('b', place={'column': 1, 'row': None})]
    picture = picture_of(
        [*cards, card('c', place={'column': 1, 'row': 2})], groups=[{'label': 'G', 'members': ['a', 'b']}]
    )
    found = layout(picture)
    check(picture, found)
    (frame,) = found.frames
    boxes = {c.id: c.box for c in found.cards}
    assert frame.members == ('a', 'b') and not frame.box.overlaps(boxes['c'])
    assert all(frame.box.contains(boxes[name]) for name in 'ab')
    assert column_of(found) == ['a', 'b', 'c']


def test_a_row_goes_to_the_nearer_end_of_a_group():
    # With three members, row 2 is after one member and before two: the card goes before the group.
    members = [card(f'a{k}', place={'column': 1, 'row': None}) for k in range(3)]
    groups = [{'label': 'G', 'members': ['a0', 'a1', 'a2']}]
    for row, expected in ((2, ['c', 'a0', 'a1', 'a2']), (3, ['a0', 'a1', 'a2', 'c'])):
        picture = picture_of([*members, card('c', place={'column': 1, 'row': row})], groups=groups)
        found = layout(picture)
        check(picture, found)
        assert column_of(found) == expected, row


def test_the_rows_of_a_group_s_members_put_no_other_card_between_them():
    # a and b, one group, have rows 1 and 3; x and y have no row. The card that the rows would put between
    # them goes after the group, and the frame holds a and b only.
    picture = picture_of(
        [
            card('a', place={'column': 1, 'row': 1}),
            card('x'),
            card('y'),
            card('b', place={'column': 1, 'row': 3}),
        ],
        groups=[{'label': 'G', 'members': ['a', 'b']}],
    )
    found = layout(picture)
    check(picture, found)
    order = column_of(found)
    assert abs(order.index('a') - order.index('b')) == 1
    (frame,) = found.frames
    assert all(not frame.box.overlaps(c.box) for c in found.cards if c.id in 'xy')


def test_the_groups_keep_their_order_when_rows_turn_it():
    # The rows put B's member above A's in the first column and below it in the second: the frames are
    # bands, one above the other, so the groups keep their order in each column.
    picture = picture_of(
        [
            card('a', place={'column': 1, 'row': 2}),
            card('b', place={'column': 1, 'row': 1}),
            card('a2', place={'column': 2, 'row': 1}),
            card('b2', place={'column': 2, 'row': 2}),
        ],
        groups=[{'label': 'A', 'members': ['a', 'a2']}, {'label': 'B', 'members': ['b', 'b2']}],
    )
    found = layout(picture)
    check(picture, found)
    first, second = found.frames
    assert (first.label, second.label) == ('A', 'B') and first.box.bottom <= second.box.y
    assert column_of(found, 1) == ['a', 'b'] and column_of(found, 2) == ['a2', 'b2']


@SHAPE
@given(
    st.lists(st.sampled_from((None, 0, 1, 2)), max_size=14).flatmap(
        lambda groups: st.tuples(st.just(groups), st.permutations(range(len(groups))))
    )
)
def test_gathered_puts_each_group_in_one_block_in_the_order_of_the_groups(case):
    groups, order = case
    items = [('card', f'c{k}') for k in range(len(groups))]
    group_of = {item: group for item, group in zip(items, groups) if group is not None}
    given_order = [items[k] for k in order]
    found = layouts.gathered(given_order, group_of)
    assert sorted(found) == sorted(given_order)
    runs = [
        group for group, _ in itertools.groupby(group_of.get(item) for item in found) if group is not None
    ]
    assert runs == sorted(set(runs))
    # The items in no group keep their order, and an order that has each group in one block, in order,
    # stays as it is.
    loose = [item for item in given_order if item not in group_of]
    assert [item for item in found if item not in group_of] == loose
    assert layouts.gathered(found, group_of) == found


# ---- the rank -------------------------------------------------------------------------------------


@SHAPE
@given(
    st.integers(1, 9).flatmap(
        lambda n: st.tuples(
            st.just(n), st.lists(st.tuples(st.integers(0, n - 1), st.integers(0, n - 1)), max_size=30)
        )
    )
)
def test_the_greedy_order_breaks_every_cycle_with_at_most_half_the_pairs(case):
    count, raw = case
    nodes = [f'n{k}' for k in range(count)]
    pairs = list(dict.fromkeys((nodes[a], nodes[b]) for a, b in raw if a != b))
    order = layouts.greedy_order(nodes, pairs)
    assert sorted(order) == sorted(nodes)
    at = {node: k for k, node in enumerate(order)}
    back = [(a, b) for a, b in pairs if at[a] > at[b]]
    # Each node that the greedy rule removes adds at most half of its remaining pairs as back pairs.
    assert 2 * len(back) <= len(pairs)
    # A graph that is already acyclic has no back pair at all.
    acyclic = [(a, b) for a, b in pairs if nodes.index(a) < nodes.index(b)]
    order = layouts.greedy_order(nodes, acyclic)
    at = {node: k for k, node in enumerate(order)}
    assert all(at[a] < at[b] for a, b in acyclic)


@SHAPE
@given(st.lists(st.tuples(st.integers(0, 40), st.integers(0, 15)), max_size=30))
def test_the_fewest_tracks_are_as_many_as_the_most_intervals_that_meet(spans):
    intervals = [(low, low + length, k) for k, (low, length) in enumerate(spans)]
    found = layouts._tracks(intervals, fewest=True)
    assert set(found) == set(range(len(intervals)))
    assert 1 + max(found.values(), default=-1) == most_meeting([(low, high) for low, high, _ in intervals])
    for (a0, a1, a), (b0, b1, b) in itertools.combinations(intervals, 2):
        if not (a1 < b0 or b1 < a0):
            assert found[a] != found[b]


def test_the_order_of_lengths_can_need_one_track_more_than_the_fewest():
    # Found by a search over random intervals. By length, (15, 18) and (3, 9) go first, on one track;
    # (10, 17) takes a second; (4, 13) meets both and needs a third. No point is in more than two.
    intervals = [(10, 17, 0), (4, 13, 1), (15, 18, 2), (3, 9, 3)]
    assert most_meeting([(low, high) for low, high, _ in intervals]) == 2
    assert 1 + max(layouts._tracks(intervals).values()) == 3
    assert 1 + max(layouts._tracks(intervals, fewest=True).values()) == 2


@SHAPE
@given(st.lists(st.tuples(st.integers(0, 6), st.integers(0, 6), st.sampled_from((0.5, 1.0))), max_size=25))
def test_the_crossing_count_is_the_count_of_every_pair(segments):
    brute = sum(
        a[2] * b[2] for a, b in itertools.combinations(segments, 2) if (a[0] - b[0]) * (a[1] - b[1]) < 0
    )
    assert layouts.crossing_count(segments) == brute


# ---- pictures that Hypothesis makes ------------------------------------------------------------------

WORDS = st.text(alphabet='abcdefgh ijk<&>"\'éø', min_size=1, max_size=70)
# A start that some names share, so that their meters can show one text.
STARTS = ('', 'a start that is shared by some names ')


@st.composite
def pictures(draw, rows=False, groups=False, places=True, columns=4):
    count = draw(st.integers(1, 12))
    ids = [f'c{k}' for k in range(count)]
    cards = []
    for name in ids:
        stocks = [
            {
                'key': f'{name}.v{j}',
                'name': draw(st.sampled_from(STARTS)) + draw(WORDS),
                'kind': draw(st.sampled_from(('stock', 'tally'))),
            }
            for j in range(draw(st.integers(0, 6)))
        ]
        ends = [None, *(stock['key'] for stock in stocks)]
        pipes = []
        for j in range(draw(st.integers(0, 5)) if stocks else 0):
            a, b = draw(st.sampled_from(ends)), draw(st.sampled_from(ends))
            if a != b:
                extra = [f'g{j}'] if draw(st.booleans()) else []
                pipes.append(
                    {
                        'key': f'{name}.p{j}',
                        'flows': [f'f{j}', *extra],
                        'from': a,
                        'to': b,
                        'label': draw(WORDS),
                    }
                )
        machines = []
        for j in range(draw(st.integers(0, 2))):
            states = [f's{i}' for i in range(draw(st.integers(1, 7)))]
            steps = []
            for i in range(draw(st.integers(0, 9))):
                source = draw(
                    st.one_of(
                        st.none(), st.lists(st.sampled_from(states), min_size=1, max_size=3, unique=True)
                    )
                )
                steps.append(
                    {
                        'from': source,
                        'to': draw(st.sampled_from(states)),
                        'event': f'e{i}',
                        'by': draw(st.sampled_from(ids)),
                    }
                )
            machines.append(
                {
                    'var': f'{name}.m{j}',
                    'name': draw(WORDS),
                    'states': states,
                    'initial': draw(st.sampled_from([None, *states])),
                    'transitions': sorted(steps, key=lambda t: (t['event'], t['to'])),
                    'place': draw(st.sampled_from(('inside', 'beside', 'hidden'))),
                }
            )
        # The rows of [stocks] (D-52): none, or some of the card's stocks in any order.
        keys = [stock['key'] for stock in stocks]
        stock_order = None
        if keys and draw(st.booleans()):
            stock_order = draw(st.lists(st.sampled_from(keys), unique=True, max_size=len(keys)))
        place = None
        if places and draw(st.booleans()):
            place = {
                'column': draw(st.integers(1, columns)),
                'row': draw(st.integers(1, 4)) if rows and draw(st.booleans()) else None,
            }
        cards.append(
            {
                'id': name,
                'title': draw(WORDS),
                'role': None,
                'icon': draw(st.sampled_from((None, 'target', 'sun', 'factory'))),
                'template': None,
                'copies': draw(st.integers(1, 3)),
                'place': place,
                'stocks': stocks,
                'stock_order': stock_order,
                'hidden_stocks': draw(st.integers(0, 2)),
                'pipes': pipes,
                'machines': sorted(machines, key=lambda m: m['var']),
            }
        )
    raw = draw(
        st.lists(
            st.tuples(st.sampled_from(ids), st.sampled_from(ids), st.sampled_from(KINDS)),
            max_size=30,
            unique=True,
        )
    )
    arrows = [
        {'from': a, 'to': b, 'kind': kind, 'count': 1, 'values': [f'{b}.x']}
        for a, b, kind in sorted(raw)
        if a != b
    ]
    found = []
    if groups:
        label = draw(st.lists(st.sampled_from((None, 'One', 'Two')), min_size=count, max_size=count))
        for name in ('One', 'Two'):
            members = [card_id for card_id, given in zip(ids, label) if given == name]
            if members:
                found.append({'label': name, 'members': members})
    return picture_of(cards, arrows, found, draw(limits()))


def limits():
    """The settings of the stock rows, the cards of a column and the width of a card (D-52), and the
    looks and bundles of the arrows (D-51): any value that the stylesheet can give, or none, as a
    picture without `settings`."""
    return st.one_of(
        st.none(),
        st.fixed_dictionaries(
            {
                'stocks': st.integers(1, 8),
                'cards_per_column': st.integers(2, 16),
                'card_width': st.one_of(st.none(), st.integers(170, 400)),
                # D-51: any look of each kind, and any kinds bundled.
                'looks': st.fixed_dictionaries({kind: st.sampled_from(ARROW_LOOKS) for kind in KINDS}),
                'bundle': st.lists(st.sampled_from(KINDS), unique=True).map(
                    lambda kinds: [kind for kind in KINDS if kind in kinds]
                ),
            }
        ),
    )


@SHAPE
@given(pictures(rows=True))
def test_every_property_holds_on_pictures_with_rows(picture):
    check(picture, layout(picture))


@SHAPE
@given(pictures(groups=True))
def test_every_property_holds_on_pictures_with_groups(picture):
    check(picture, layout(picture))


@SHAPE
@given(pictures(rows=True, groups=True, columns=2))
def test_every_property_holds_on_pictures_with_rows_and_groups(picture):
    check(picture, layout(picture))


@SHAPE
@given(pictures(places=False))
def test_the_layers_follow_the_changes_and_the_moves(picture):
    found = layout(picture)
    # Only the drawn arrows rank the cards: a hidden kind places none (`layers`).
    check(picture, found)
    layer = {card.id: card.column for card in found.cards}
    ranking = list(
        dict.fromkeys((a['from'], a['to']) for a in drawn_arrows(picture) if a['kind'] in layouts.RANKING)
    )
    back = set(layouts.back_pairs(picture))
    assert 2 * len(back) <= len(ranking)
    for a, b in ranking:
        # Each pair goes one layer or more to the right, or, when it breaks a cycle, to the left.
        assert (layer[a] > layer[b]) if (a, b) in back else (layer[a] < layer[b])
    ranked = {name for pair in ranking for name in pair}
    neighbours = {}
    for a in drawn_arrows(picture):
        neighbours.setdefault(a['from'], set()).add(a['to'])
        neighbours.setdefault(a['to'], set()).add(a['from'])
    for name, others in neighbours.items():
        if name not in ranked:
            # A card with only reads and follows lies between its neighbours.
            assert min(layer[o] for o in others) <= layer[name] <= max(layer[o] for o in others)
    for c in found.cards:
        if c.id not in neighbours:
            assert c.column == max(layer.values())


@SHAPE
@given(pictures(groups=True), st.lists(st.sampled_from(KINDS), unique=True))
def test_every_property_holds_with_any_kinds_bundled(picture, kinds):
    # A kind that is not in `bundle` is never bundled (check_bundles), and every other property holds.
    picture = bundling(picture, kinds)
    found = layout(picture)
    check(picture, found)
    assert all(route.kind in kinds for route in found.routes if route.bundle is not None)


@SHAPE
@given(pictures(rows=True, groups=True))
def test_without_bundles_no_two_arrows_share_an_end_or_a_stretch(picture):
    picture = bundling(picture, [])
    found = layout(picture)
    check(picture, found)
    assert found.bundles == () and all(route.bundle is None for route in found.routes)


@SHAPE
@given(pictures(groups=True))
def test_a_bundle_of_one_arrow_is_that_arrow(picture):
    # With at most one arrow of each bundled kind from each card, bundling changes nothing.
    seen = set()
    arrows = []
    for given_arrow in picture['arrows']:
        key = (given_arrow['from'], given_arrow['kind'])
        if given_arrow['kind'] not in DEFAULT_BUNDLE or key not in seen:
            seen.add(key)
            arrows.append(given_arrow)
    picture = {**picture, 'arrows': arrows}
    assert layout(picture) == layout(bundling(picture, []))


# ---- a model ------------------------------------------------------------------------------------------


@pytest.mark.parametrize('run', [None, 'base', 'attack'])
def test_the_layout_of_the_water_works_holds_every_property(run):
    from napkin.draw import style

    model = works()
    found = picture(model, style.read(WORKS_STYLE), run=run)
    start = time.perf_counter()
    placed = layout(found)
    took = time.perf_counter() - start
    check(found, placed)
    assert took < 5.0, took


# The advance widths, in 1/2048 em, of the characters of BOLD_CHARS in the bold faces of two common
# fonts, from their `hmtx` tables: DejaVuSans-Bold.ttf and LiberationSans-Bold.ttf (whose widths are
# those of Arial Bold). They are independent of the layout's estimate.
BOLD_CHARS = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789 ',.-:()&/"
DEJAVU_SANS_BOLD = (
    1585,
    1561,
    1503,
    1700,
    1399,
    1399,
    1681,
    1714,
    762,
    762,
    1587,
    1305,
    2038,
    1714,
    1741,
    1501,
    1741,
    1577,
    1475,
    1397,
    1663,
    1585,
    2259,
    1579,
    1483,
    1485,
    1382,
    1466,
    1214,
    1466,
    1389,
    891,
    1466,
    1458,
    702,
    702,
    1362,
    702,
    2134,
    1458,
    1407,
    1466,
    1466,
    1010,
    1219,
    979,
    1458,
    1335,
    1892,
    1321,
    1335,
    1192,
    1425,
    1425,
    1425,
    1425,
    1425,
    1425,
    1425,
    1425,
    1425,
    1425,
    713,
    627,
    778,
    778,
    850,
    819,
    936,
    936,
    1786,
    748,
)
LIBERATION_SANS_BOLD = (
    1479,
    1479,
    1479,
    1479,
    1366,
    1251,
    1593,
    1479,
    569,
    1139,
    1479,
    1251,
    1706,
    1479,
    1593,
    1366,
    1593,
    1479,
    1366,
    1251,
    1479,
    1366,
    1933,
    1366,
    1366,
    1251,
    1139,
    1251,
    1139,
    1251,
    1139,
    682,
    1251,
    1251,
    569,
    569,
    1139,
    569,
    1821,
    1251,
    1251,
    1251,
    1251,
    797,
    1139,
    682,
    1251,
    1139,
    1593,
    1139,
    1139,
    1024,
    1139,
    1139,
    1139,
    1139,
    1139,
    1139,
    1139,
    1139,
    1139,
    1139,
    569,
    487,
    569,
    569,
    682,
    682,
    682,
    682,
    1479,
    569,
)


def bold_advance(text, size, widths):
    return sum(widths[BOLD_CHARS.index(char)] for char in text) / 2048 * size


@settings(max_examples=300, deadline=None)
@given(
    text=st.text(alphabet=BOLD_CHARS, min_size=1, max_size=40),
    size=st.sampled_from(
        [layouts.SMALL_SIZE, layouts.TEXT_SIZE, layouts.TITLE_SIZE, layouts.PICTURE_TITLE_SIZE]
    ),
)
def test_a_bold_text_is_no_wider_than_its_estimate_in_two_fonts(text, size):
    for widths in (DEJAVU_SANS_BOLD, LIBERATION_SANS_BOLD):
        assert bold_advance(text, size, widths) <= layouts.bold_width(text, size)
    assert layouts.bold_width(text, size) >= layouts.text_width(text, size)


def test_the_plain_estimate_is_too_narrow_for_a_bold_title():
    # A counterexample: why a bold text needs its own estimate.
    for text in ('NAWS', 'bdpq', 'Mm'):
        assert layouts.text_width(text, layouts.TITLE_SIZE) < bold_advance(
            text, layouts.TITLE_SIZE, DEJAVU_SANS_BOLD
        )
