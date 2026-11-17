"""The picture of a model as one SVG file: the cards with their stocks, pipes and state machines, the
arrows by kind, the group frames, the legend and the icons (`layout.py` places each of them).

The file stands alone: it has no script, no external font and no image, and the icons of
`icons.py` are `<symbol>`s in it, drawn in `currentColor`; a card without an icon draws none, and its
title keeps its place. It themes for light and dark: CSS custom
properties give the colours, a `prefers-color-scheme: dark` block changes them, and each element also
has its light colour as a presentation attribute, for a reader that does not know `var()`. The tooltip
of a card lists its connections by kind (D-58), and CSS rules light its arrows while a reader points at
it (`_hover`).

Each part of the picture is a `<g>` with a `<title>` (its tooltip) and the `data-*` attribute of its
kind, which names the part in the picture (`model_map.picture`):

| Element | Attribute |
| --- | --- |
| card | `data-thing`: the card's id |
| stock row, meter | `data-stock`: the stock's key |
| "+n" row | `data-stock`: the keys of the stocks that it stands for, separated by spaces |
| pipe | `data-flow`: its flows, separated by spaces |
| state machine | `data-var`: its var |
| state | `data-state`: the state (none for "any state") |
| transition | `data-event`: its events, separated by spaces |
| row of the events of a card (`[triggers]`) | `data-event`: the events that it stands for, separated by spaces |
| arrow | `data-from`, `data-to` (card ids) and `data-kind` |
| bundle of arrows | `data-from` (the card id) and `data-kind` |
| group frame | `data-group`: its label |
| mark of the legend | `data-mark`: the mark (`layout.MARKS`) |
| block of the Equations | `data-block`: its name in the picture's panels |
| line of a block | `data-latex`: its LaTeX (D-57); `data-part`: its part; `data-record`: its records |
| row of the Symbols table | `data-key`: its key; `data-record`: its records |
| entry of the References | `data-number`: its number; `data-record`: the IDs and names of its records |
| tag of a stock row or a meter | `data-key`: the stock's key |

The panels go after the legend (`g.equations`, `g.symbols`, `g.references`, `g.note`). The marks are
`<tspan>`s, smaller and raised by their own y, with the class `mark mark-<colour>` of their entry's
kind (`references.COLOUR_KIND`). A record goes only in `data-record`, never in a visible text. The
link of an entry of the References is the one `<a href>` of the picture, to its `http` or `https`
address (D-55). The rules of the panels and the typesetter (`typeset.STYLE`) are in the style only when
the picture has panels or tags.

A bundle (D-51) is before its arrows. It draws the line that its arrows share and their branches,
and a dot at each junction. Each arrow of a bundle draws the head on its last segment, and has its
whole line as a path with the classes `route member` and no colour (stroke-opacity 0), which a rule of
the style can show.
"""

from __future__ import annotations

import itertools

from . import icons
from . import references as refs
from .defaults import DEFAULT_LOOKS
from .layout import (
    KINDS,
    MACHINE_GAP,
    METER_TEXT,
    PAD,
    PICTURE_TITLE_SIZE,
    SMALL_SIZE,
    SUBTITLE_LINE,
    TEXT_SIZE,
    TITLE_SIZE,
    shorten,
)

NAMESPACE = 'http://www.w3.org/2000/svg'
XLINK = 'http://www.w3.org/1999/xlink'
FONT = 'system-ui, -apple-system, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif'

# The colours: {custom property: (light, dark)}. The light colour is also each element's presentation
# attribute. The flows of a card (`pipe`) and the arrows that move material (`moves`) have colours of
# their own.
COLOURS = {
    'paper': ('#ffffff', '#0d1117'),
    'ink': ('#1f2328', '#e6edf3'),
    'muted': ('#59636e', '#9198a1'),
    'card': ('#f6f8fa', '#151b23'),
    'edge': ('#8c959f', '#3d444d'),
    'icon': ('#59636e', '#9198a1'),
    'actor': ('#1f2328', '#e6edf3'),
    'stock': ('#ddf4ff', '#0c2d6b'),
    'stock-edge': ('#54aeff', '#1f6feb'),
    'tally': ('#fff8c5', '#3b2e00'),
    'tally-edge': ('#d4a72c', '#9e6a03'),
    'pipe': ('#0f766e', '#2dd4bf'),
    'state': ('#ffffff', '#0d1117'),
    'state-edge': ('#8c959f', '#656c76'),
    'start': ('#1a7f37', '#3fb950'),
    'transition': ('#8250df', '#ab7df8'),
    'reads': ('#818b98', '#656c76'),
    'follows': ('#8250df', '#ab7df8'),
    'changes': ('#cf222e', '#f85149'),
    'fires': ('#bc4c00', '#f0883e'),
    'moves': ('#0969da', '#4493f8'),
    'frame': ('#bf8700', '#bb8009'),
    'frame-fill': ('#fffbeb', '#1c1a10'),
    # The panels (D-55): a link of the References, and the marks of each colour of a kind of entry
    # (`references.COLOURS`), each 4.5:1 or more against the paper and the stripes of the table, and
    # none the colour of a kind of arrow or of the start: a source blue, a source applied here teal,
    # an identity or a convention grey, an assumption amber (the owner's choice at CP-E).
    'link': ('#0969da', '#4493f8'),
    'mark-source': ('#0550ae', '#79c0ff'),
    'mark-transfer': ('#0e7490', '#39c5cf'),
    'mark-rule': ('#57606a', '#b1bac4'),
    'mark-assumption': ('#9a6700', '#e3b341'),
}
# How each kind of arrow is drawn (D-50): its width, its dashes, the size of its head and the shape of
# the head. Each two kinds differ in their width, their dashes or their head, so that they differ in
# grey too.
ARROWS = {
    'reads': {'width': 1.0, 'dash': '1.5 3', 'head': 7.0, 'opacity': 0.85, 'shape': 'chevron'},
    'follows': {'width': 1.0, 'dash': '4 2.5', 'head': 7.0, 'opacity': 0.85, 'shape': 'circle'},
    'changes': {'width': 1.6, 'dash': '6 3', 'head': 8.0, 'opacity': 1.0, 'shape': 'triangle'},
    'fires': {'width': 1.6, 'dash': '6 2 1.5 2', 'head': 8.0, 'opacity': 1.0, 'shape': 'barred'},
    'moves': {'width': 2.4, 'dash': None, 'head': 10.0, 'opacity': 1.0, 'shape': 'triangle'},
}
# The heads of the arrows, in a box of 10 by 10 with the tip at the right. An open head is a line; a
# filled head is an area.
HEADS = {
    'chevron': ('open', 'M1 1L9 5L1 9'),
    'circle': ('open', 'M8.5 5A3.5 3.5 0 1 1 1.5 5A3.5 3.5 0 1 1 8.5 5Z'),
    'triangle': ('filled', 'M0 0L10 5L0 10Z'),
    'barred': ('filled', 'M0 0L7 5L0 10ZM8.2 0.5L10 0.5L10 9.5L8.2 9.5Z'),
}
# The light look of each kind (D-51): its colour mixed with the paper's, `LIGHT_SHARE` of it, in each
# theme, and a line `LIGHT_WIDTH` times as wide. It is a look of its own (`<kind>-light`), not a lower
# opacity, so that the colours stay colours.
LIGHT_SHARE = 0.7
LIGHT_WIDTH = 0.8


def _mixed(colour, ground, share):
    """`colour` mixed with `ground` (#rrggbb): `share` of the colour, the rest of the ground."""
    a = [int(colour[k : k + 2], 16) for k in (1, 3, 5)]
    b = [int(ground[k : k + 2], 16) for k in (1, 3, 5)]
    return '#' + ''.join(f'{round(share * x + (1 - share) * y):02x}' for x, y in zip(a, b))


for _kind in tuple(ARROWS):
    COLOURS[f'{_kind}-light'] = tuple(
        _mixed(COLOURS[_kind][theme], COLOURS['paper'][theme], LIGHT_SHARE) for theme in (0, 1)
    )
    ARROWS[f'{_kind}-light'] = {
        **ARROWS[_kind],
        'width': ARROWS[_kind]['width'] * LIGHT_WIDTH,
        'opacity': 1.0,
    }
del _kind


def drawn_as(kind, looks):
    """The look that a kind is drawn with: `<kind>-light` when `looks` (the picture's
    `settings.looks`, else `DEFAULT_LOOKS`) makes it light, else the kind."""
    found = (looks or DEFAULT_LOOKS).get(kind)
    return f'{kind}-light' if found == 'light' and f'{kind}-light' in ARROWS else kind


# The words of an arrow's tooltip. An arrow of a kind of READ_VERBS goes to the card that reads.
VERBS = {'changes': 'changes', 'fires': 'fires events of', 'moves': 'moves material of'}
READ_VERBS = {'reads': 'reads values of', 'follows': 'follows events of'}
# The words of a card's connections in its tooltip (D-58), for each kind: when the card does it to the
# others, and when the others do it to the card. A kind whose look is hidden adds NOT_DRAWN.
LINKS = {
    'reads': ('Reads values of', 'Things that read its values'),
    'follows': ('Follows events of', 'Things that follow its events'),
    'changes': ('Changes values of', 'Things that change its values'),
    'fires': ('Fires events of', 'Things that fire its events'),
    'moves': ('Moves material of', 'Things that move its material'),
}
NOT_DRAWN = 'not drawn'
# The opacity of an arrow that does not join the card that a reader points at.
DIMMED = '.15'
# The first words of the tooltip of a bundle of arrows that go to the cards that read (D-51).
BUNDLE_VERBS = {'reads': 'Read by', 'follows': 'Followed by'}


def _light(name):
    return COLOURS[name][0]


def number(value):
    """A coordinate as the file writes it: an integer, or one decimal (the layout rounds to 0.5)."""
    text = f'{float(value):.1f}'
    text = text[:-2] if text.endswith('.0') else text
    return '0' if text == '-0' else text


def escape(text):
    """`text` for the content or an attribute of an element."""
    return (
        str(text)
        .replace('&', '&amp;')
        .replace('<', '&lt;')
        .replace('>', '&gt;')
        .replace('"', '&quot;')
        .replace("'", '&#39;')
    )


def _attributes(items):
    return ''.join(f' {key}="{escape(value)}"' for key, value in items.items() if value is not None)


def _tag(name, items, inner=None):
    attributes = _attributes(items)
    if inner is None:
        return f'<{name}{attributes}/>'
    return f'<{name}{attributes}>{inner}</{name}>'


def _path(points):
    """The `d` of a polyline."""
    head, *rest = points
    return f'M{number(head[0])} {number(head[1])}' + ''.join(f'L{number(x)} {number(y)}' for x, y in rest)


def _rect(box, cls, fill, stroke, **extra):
    return _tag(
        'rect',
        {
            'class': cls,
            'x': number(box.x),
            'y': number(box.y),
            'width': number(box.width),
            'height': number(box.height),
            'fill': fill,
            'stroke': stroke,
            **extra,
        },
    )


def _text(x, y, text, cls, fill, **extra):
    return _tag('text', {'class': cls, 'x': number(x), 'y': number(y), 'fill': fill, **extra}, escape(text))


def _title(text):
    return f'<title>{escape(text)}</title>'


def _group(cls, data, tooltip, *inner):
    return _tag('g', {'class': cls, **data}, _title(tooltip) + ''.join(inner))


def _plural(count, word):
    return f'{count} {word}' if count == 1 else f'{count} {word}s'


def css_string(text):
    """`text` as the inside of a CSS string in double quotes, which the `<style>` of the SVG holds as it
    is. Each character that is not an ASCII letter, a digit, `_` or `-` becomes a hex escape and a space
    (`"` becomes `\\22 `), so the result has no `"`, no newline and no `\\` of its own, and no `<` or
    `&` for the XML. CSS reads NUL and a lone surrogate as U+FFFD, so they raise ValueError."""
    out = []
    for char in str(text):
        if char.isascii() and (char.isalnum() or char in '_-'):
            out.append(char)
            continue
        code = ord(char)
        if code == 0 or 0xD800 <= code <= 0xDFFF:
            raise ValueError(f'a CSS string cannot hold the character U+{code:04X}')
        out.append(f'\\{code:x} ')
    return ''.join(out)


# ---- the style and the definitions ---------------------------------------------------------------


def _hover(ids):
    """The rules that light the arrows of a card while a reader points at the card (D-58), with no
    script: one block `@media (hover:hover)`, and two rules for each card id of `ids`. The first dims
    each arrow that does not join the card and each bundle that does not start at it. The second shows
    the full path (`.member`) of each arrow that joins the card: a bundle draws that path with no
    opacity, under its trunk.

    The rules need `:has()`: Chrome and Edge 105, Safari 15.4, Firefox 121. Each rule is separate, so a
    browser that does not know a rule drops only that rule, and the picture stays as it is. A picture in
    an `<img>` or a PDF gets no pointer, so it does not change."""
    rules = []
    for card_id in ids:
        name = css_string(card_id)
        pointed = f'.napkin-draw:has(.card[data-thing="{name}"]:hover)'
        rules.append(
            f'{pointed} :is(.arrow:not([data-to="{name}"]),.bundle):not([data-from="{name}"])'
            f'{{opacity:{DIMMED}}}'
        )
        rules.append(
            f'{pointed} :is(.arrow[data-from="{name}"],.arrow[data-to="{name}"]) .member{{stroke-opacity:1}}'
        )
    return '@media (hover:hover){' + ''.join(rules) + '}' if rules else ''


def _style(ids=(), panels=False):
    """The `<style>` of the picture: the colours of each theme, the rules of each class, the rules of the
    panels and the tags when the picture has them (`panels`), and the hover rules of the cards."""
    light = ';'.join(f'--{name}:{light}' for name, (light, _) in COLOURS.items())
    dark = ';'.join(f'--{name}:{dark}' for name, (_, dark) in COLOURS.items())
    rules = [
        f'.napkin-draw{{{light};font-family:{FONT}}}',
        f'@media (prefers-color-scheme: dark){{.napkin-draw{{{dark}}}}}',
        '.napkin-draw .paper{fill:var(--paper)}',
        '.napkin-draw text{fill:var(--ink)}',
        f'.napkin-draw .heading{{font-size:{PICTURE_TITLE_SIZE:g}px;font-weight:600}}',
        '.napkin-draw .subheading,.napkin-draw .more,.napkin-draw .key{fill:var(--muted)}',
        '.napkin-draw .box{fill:var(--card);stroke:var(--edge)}',
        '.napkin-draw .icon{color:var(--icon)}',
        f'.napkin-draw .card-title{{font-size:{TITLE_SIZE}px;font-weight:600}}',
        f'.napkin-draw .label{{font-size:{TEXT_SIZE}px}}',
        f'.napkin-draw .small,.napkin-draw .more,.napkin-draw .key,.napkin-draw .subheading{{font-size:{SMALL_SIZE}px}}',
        '.napkin-draw .badge{fill:var(--paper);stroke:var(--edge)}',
        '.napkin-draw .decides{fill:var(--actor)}',
        '.napkin-draw .starts{fill:var(--start)}',
        '.napkin-draw .tank{fill:var(--stock);stroke:var(--stock-edge)}',
        '.napkin-draw .meter{fill:var(--tally);stroke:var(--tally-edge)}',
        '.napkin-draw .gauge{stroke:var(--tally-edge)}',
        '.napkin-draw .flow{stroke:var(--pipe)}',
        '.napkin-draw .valve{fill:var(--pipe)}',
        '.napkin-draw .cloud{fill:var(--paper);stroke:var(--pipe)}',
        '.napkin-draw .machine-box{fill:var(--card);stroke:var(--edge)}',
        '.napkin-draw .rule,.napkin-draw .tie{stroke:var(--edge)}',
        '.napkin-draw .pill{fill:var(--state);stroke:var(--state-edge)}',
        '.napkin-draw .start{fill:var(--start)}',
        '.napkin-draw .step{stroke:var(--transition)}',
        '.napkin-draw .step-badge{fill:var(--transition)}',
        '.napkin-draw .step-number{fill:var(--paper)}',
        '.napkin-draw .trigger-mark{fill:var(--transition)}',
        '.napkin-draw .event-name{font-weight:600}',
        '.napkin-draw .frame{fill:var(--frame-fill);stroke:var(--frame)}',
        '.napkin-draw .frame-label{fill:var(--frame);font-size:11px;font-weight:600}',
        '.napkin-draw .legend-box{fill:var(--paper);stroke:var(--edge)}',
        *(f'.napkin-draw .line-{kind}{{stroke:var(--{kind})}}' for kind in ARROWS),
        *(
            f'.napkin-draw .head-{kind}-open{{stroke:var(--{kind})}}'
            if HEADS[how['shape']][0] == 'open'
            else f'.napkin-draw .head-{kind}{{fill:var(--{kind})}}'
            for kind, how in ARROWS.items()
        ),
        *(f'.napkin-draw .dot-{kind}{{fill:var(--{kind})}}' for kind in ARROWS),
        '.napkin-draw .head-pipe{fill:var(--pipe)}',
        '.napkin-draw .head-step{fill:var(--transition)}',
        *(_panel_style() if panels else ()),
    ]
    return '<style>' + ''.join(rules) + _hover(ids) + '</style>'


def _markers():
    out = []
    for kind, how in ARROWS.items():
        size = number(how['head'])
        fill, shape = HEADS[how['shape']]
        style = (
            {'fill': 'none', 'stroke': _light(kind), 'stroke-width': '1.6', 'class': f'head-{kind}-open'}
            if fill == 'open'
            else {'fill': _light(kind), 'class': f'head-{kind}'}
        )
        out.append(
            _tag(
                'marker',
                {
                    'id': f'head-{kind}',
                    'viewBox': '0 0 10 10',
                    'refX': '9.5',
                    'refY': '5',
                    'markerWidth': size,
                    'markerHeight': size,
                    'markerUnits': 'userSpaceOnUse',
                    'orient': 'auto',
                },
                _tag('path', {'d': shape, **style}),
            )
        )
    for name, colour, size in (('pipe', 'pipe', '6.5'), ('step', 'transition', '7')):
        out.append(
            _tag(
                'marker',
                {
                    'id': f'head-{name}',
                    'viewBox': '0 0 10 10',
                    'refX': '9.5',
                    'refY': '5',
                    'markerWidth': size,
                    'markerHeight': size,
                    'markerUnits': 'userSpaceOnUse',
                    'orient': 'auto',
                },
                _tag('path', {'d': 'M0 0L10 5L0 10Z', 'fill': _light(colour), 'class': f'head-{name}'}),
            )
        )
    return ''.join(out)


def _symbols(names):
    drawing = {key: value for key, value in icons.ATTRIBUTES.items() if key != 'viewBox'}
    return ''.join(
        _tag(
            'symbol',
            {'id': f'icon-{name}', 'viewBox': icons.ATTRIBUTES['viewBox']},
            _tag('g', drawing, icons.SHAPES[name]),
        )
        for name in icons.SHAPES
        if name in names
    )


# ---- the parts -----------------------------------------------------------------------------------


def _connections(picture, titles):
    """The lines of the connections of each card for its tooltip (D-58): {card id: [line, …]}. For each
    kind, in the order of `KINDS`, a line names the things that the card reads, follows, changes, fires
    or moves, then a line names the things that do so to it, by their titles in the order of the cards;
    a "changes" line gives the words of each arrow (sets, adds, …). The lines come from the picture's
    arrows, not from the routes, so a kind whose look is hidden is there too, with NOT_DRAWN."""
    looks = (picture.get('settings') or {}).get('looks') or {}
    order = {card_id: k for k, card_id in enumerate(titles)}
    ends = {}
    for arrow in picture.get('arrows', ()):
        source, target, kind = arrow['from'], arrow['to'], arrow['kind']
        if source == target or source not in titles or target not in titles or kind not in LINKS:
            continue
        doer, other = (target, source) if kind in READ_VERBS else (source, target)
        how = tuple(arrow.get('how') or ())
        ends.setdefault((doer, kind, 0), []).append((other, how))
        ends.setdefault((other, kind, 1), []).append((doer, how))
    out = {}
    for card_id in titles:
        lines = []
        for kind in KINDS:
            hidden = f' ({NOT_DRAWN})' if looks.get(kind) == 'hidden' else ''
            for side, words in enumerate(LINKS.get(kind, ())):
                found = sorted(ends.get((card_id, kind, side), ()), key=lambda end: order[end[0]])
                if found:
                    names = (titles[other] + (f' ({", ".join(how)})' if how else '') for other, how in found)
                    lines.append(f'{words}{hidden}: {", ".join(names)}')
        out[card_id] = lines
    return out


def _card(card, titles, links=()):
    box = card.box
    lines = [card.title]
    if card.copies > 1:
        lines.append(f'{card.copies} copies of {card.template}' if card.template else f'{card.copies} copies')
    elif card.template:
        lines.append(f'Made from {card.template}')
    if card.actor:
        lines.append('It decides.')
    if card.starts:
        lines.append('Its start event begins each run.')
    if card.file:
        lines.append(f'Written in {card.file}')
    lines.extend(links)
    inner = [_rect(box, 'box', _light('card'), _light('edge'), rx='6')]
    if card.icon in icons.SHAPES:
        inner.append(
            _tag(
                'use',
                {
                    'class': 'icon',
                    'href': f'#icon-{card.icon}',
                    'xlink:href': f'#icon-{card.icon}',
                    'x': number(card.icon_box.x),
                    'y': number(card.icon_box.y),
                    'width': number(card.icon_box.width),
                    'height': number(card.icon_box.height),
                    'color': _light('icon'),
                },
            )
        )
    x, y = card.title_at
    for k, line in enumerate(card.lines):
        inner.append(
            _text(x, y + 15 * k, line, 'card-title', _light('ink'), **{'font-size': f'{TITLE_SIZE}'})
        )
    right = box.right - PAD
    if card.actor:
        cx, cy = right - 5, box.y + PAD + 9
        inner.append(
            _tag(
                'path',
                {
                    'class': 'decides',
                    'd': f'M{number(cx)} {number(cy - 5)}L{number(cx + 5)} {number(cy)}'
                    f'L{number(cx)} {number(cy + 5)}L{number(cx - 5)} {number(cy)}Z',
                    'fill': _light('actor'),
                },
            )
        )
        right -= 16
    if card.starts:
        cx, cy = right - 5, box.y + PAD + 9
        inner.append(
            _tag(
                'path',
                {
                    'class': 'starts',
                    'd': f'M{number(cx - 4)} {number(cy - 5)}L{number(cx + 5)} {number(cy)}'
                    f'L{number(cx - 4)} {number(cy + 5)}Z',
                    'fill': _light('start'),
                },
            )
        )
        right -= 16
    if card.copies > 1:
        text = f'×{card.copies}'
        width = len(text) * 0.6 * SMALL_SIZE + 8
        badge = type(box)(right - width, box.y + PAD + 2, width, 14)
        inner.append(_rect(badge, 'badge', _light('paper'), _light('edge'), rx='7'))
        inner.append(
            _text(
                badge.x + width / 2,
                badge.y + 10.5,
                text,
                'small',
                _light('ink'),
                **{'text-anchor': 'middle', 'font-size': f'{SMALL_SIZE}'},
            )
        )
    for stock in card.stocks:
        tip = f'{stock.name} ({stock.key}): a stock'
        if stock.flows:
            tip += f'\nFlows to stocks that are not drawn: {", ".join(stock.flows)}'
        inner.append(
            _group(
                'stock',
                {'data-stock': stock.key},
                tip,
                _rect(stock.box, 'tank', _light('stock'), _light('stock-edge'), rx='3'),
                _text(
                    stock.box.x + 6,
                    stock.box.y + 14,
                    stock.text,
                    'label',
                    _light('ink'),
                    **{'font-size': f'{TEXT_SIZE}'},
                ),
                _tag_of(stock) if stock.tag is not None else '',
            )
        )
    for meter in card.meters:
        tip = f'{meter.name} ({meter.key}): a tally'
        if meter.flows:
            tip += f'\nIts flows: {", ".join(meter.flows)}'
        b = meter.box
        gx, gy = b.x + 11, b.y + 13
        inner.append(
            _group(
                'tally',
                {'data-stock': meter.key},
                tip,
                _rect(b, 'meter', _light('tally'), _light('tally-edge'), rx='9'),
                _tag(
                    'path',
                    {
                        'class': 'gauge',
                        'd': f'M{number(gx - 5)} {number(gy)}A5 5 0 0 1 {number(gx + 5)} {number(gy)}'
                        f'M{number(gx)} {number(gy)}L{number(gx + 3)} {number(gy - 3.5)}',
                        'fill': 'none',
                        'stroke': _light('tally-edge'),
                        'stroke-width': '1.4',
                        'stroke-linecap': 'round',
                    },
                ),
                _text(
                    b.x + METER_TEXT,
                    b.y + 14,
                    meter.text,
                    'small',
                    _light('ink'),
                    **{'font-size': f'{SMALL_SIZE}'},
                ),
                _tag_of(meter, tally=True) if meter.tag is not None else '',
            )
        )
    if card.more is not None:
        more = card.more
        names = list(more.names)
        if more.hidden:
            names.append(f'{more.hidden} more')
        inner.append(
            _group(
                'more',
                {'data-stock': ' '.join(more.keys)},
                f'Not drawn: {", ".join(names)}',
                _text(
                    more.box.x,
                    more.box.y + 11,
                    more.text,
                    'more',
                    _light('muted'),
                    **{'font-size': f'{SMALL_SIZE}'},
                ),
            )
        )
    names = {stock.key: stock.name for stock in card.stocks}
    for pipe in card.pipes:
        inner.append(_pipe(pipe, names))
    for machine in card.machines:
        inner.append(_machine(machine, titles))
    for row in card.triggers:
        inner.append(_trigger(row, card.events))
    lines += _events_tip(card)
    return _group('card', {'data-thing': card.id}, '\n'.join(lines), *inner)


def _event_tip(event):
    """The lines of the tooltip of one event (D-56): its full line, its text and its rule as the file
    writes it."""
    out = [event.full]
    if event.label:
        out.append(f'  {event.label}')
    if event.rule:
        out.append(f'  Rule: {event.rule}')
    return out


def _events_tip(card):
    """The lines that the events of a card add to its tooltip at every level of `[triggers]` (D-56),
    `hover` too: the tooltip of each event."""
    if not card.events:
        return []
    out = ['Events:']
    for event in card.events:
        first, *rest = _event_tip(event)
        out += [f'• {first}', *rest]
    return out


def _trigger(row, events):
    """A row of the events of a card (D-56): a small mark and the lines of its text, the event's name in
    bold; a "+n more" row has no mark. Its tooltip gives the full line of its event, or the names of the
    events that it stands for."""
    box, (x, y) = row.box, row.text_at
    step = box.height / len(row.lines)
    found = {event.event: event for event in events}
    named = [found[key].name if key in found else key for key in row.events]
    if row.kind in ('name', 'rule') and row.events[0] in found:
        tip = '\n'.join(_event_tip(found[row.events[0]]))
    elif row.kind == 'more':
        tip = f'Not drawn: {", ".join(named)}'
    else:
        tip = f'{row.lines[0]}: {", ".join(named)}' if named else row.lines[0]
    inner = []
    if row.kind != 'more':
        inner.append(
            _tag(
                'circle',
                {
                    'class': 'trigger-mark',
                    'cx': number(box.x + 3),
                    'cy': number(box.y + step / 2),
                    'r': '2',
                    'fill': _light('transition'),
                },
            )
        )
    cls, colour = ('more', 'muted') if row.kind == 'more' else ('small', 'ink')
    for k, line in enumerate(row.lines):
        strong = row.strong[k] if k < len(row.strong) else 0
        body = escape(line[strong:])
        if strong:
            body = _tag('tspan', {'class': 'event-name', 'font-weight': '600'}, escape(line[:strong])) + body
        attributes = {
            'class': cls,
            'x': number(x),
            'y': number(y + k * step),
            'fill': _light(colour),
            'font-size': f'{SMALL_SIZE}',
        }
        inner.append(_tag('text', attributes, body))
    return _group('trigger', {'data-event': ' '.join(row.events)}, tip, *inner)


def _pipe(pipe, names):
    source = names.get(pipe.source, 'outside the model') if pipe.source else 'outside the model'
    target = names.get(pipe.target, 'outside the model') if pipe.target else 'outside the model'
    head = pipe.words or pipe.label or ', '.join(pipe.flows)
    tip = f'{head}: from {source} to {target}'
    if len(pipe.flows) > 1:
        tip += f'\n{len(pipe.flows)} flows: {", ".join(pipe.flows)}'
    inner = [
        _tag(
            'path',
            {
                'class': 'flow',
                'd': _path(pipe.points),
                'fill': 'none',
                'stroke': _light('pipe'),
                'stroke-width': '2',
                'marker-end': 'url(#head-pipe)',
            },
        )
    ]
    x, y = pipe.valve
    if pipe.cloud is None:
        shape = (
            f'M{number(x - 3.5)} {number(y - 4)}L{number(x)} {number(y)}L{number(x + 3.5)} {number(y - 4)}Z'
            f'M{number(x - 3.5)} {number(y + 4)}L{number(x)} {number(y)}L{number(x + 3.5)} {number(y + 4)}Z'
        )
    else:
        shape = (
            f'M{number(x - 3)} {number(y - 2.5)}L{number(x)} {number(y)}L{number(x - 3)} {number(y + 2.5)}Z'
            f'M{number(x + 3)} {number(y - 2.5)}L{number(x)} {number(y)}L{number(x + 3)} {number(y + 2.5)}Z'
        )
    inner.append(_tag('path', {'class': 'valve', 'd': shape, 'fill': _light('pipe')}))
    if pipe.cloud is not None:
        cx, cy = pipe.cloud
        inner.append(
            _tag(
                'circle',
                {
                    'class': 'cloud',
                    'cx': number(cx),
                    'cy': number(cy),
                    'r': '3',
                    'fill': _light('paper'),
                    'stroke': _light('pipe'),
                    'stroke-width': '1.4',
                },
            )
        )
    if len(pipe.flows) > 1:
        dx = 6 if pipe.cloud is None else 0
        dy = 3 if pipe.cloud is None else -6
        inner.append(
            _text(x + dx, y + dy, str(len(pipe.flows)), 'small', _light('ink'), **{'font-size': '8.5'})
        )
    return _group('pipe', {'data-flow': ' '.join(pipe.flows)}, tip, *inner)


def _machine(machine, titles, beside=False):
    box = machine.box
    inner = []
    if beside:
        inner.append(
            _tag(
                'line',
                {
                    'class': 'tie',
                    'x1': number(box.x + box.width / 2),
                    'y1': number(box.y - MACHINE_GAP),
                    'x2': number(box.x + box.width / 2),
                    'y2': number(box.y),
                    'stroke': _light('edge'),
                    'stroke-dasharray': '2 2',
                },
            )
        )
        inner.append(_rect(box, 'machine-box', _light('card'), _light('edge'), rx='6'))
    else:
        inner.append(
            _tag(
                'line',
                {
                    'class': 'rule',
                    'x1': number(box.x),
                    'y1': number(box.y - 3),
                    'x2': number(box.right),
                    'y2': number(box.y - 3),
                    'stroke': _light('edge'),
                },
            )
        )
    x, y = machine.title_at
    inner.append(
        _text(
            x,
            y,
            shorten(machine.name, SMALL_SIZE, box.width - 12),
            'small',
            _light('muted'),
            **{'font-size': f'{SMALL_SIZE}', 'font-style': 'italic'},
        )
    )
    for state in machine.states:
        b = state.box
        name = 'any state' if state.name is None else state.name
        tip = 'Any state' if state.name is None else (f'{name} (at the start)' if state.initial else name)
        parts = [
            _rect(
                b,
                'pill',
                _light('state'),
                _light('state-edge'),
                rx=number(min(8.0, b.height / 2)),
                **({'stroke-dasharray': '3 2'} if state.name is None else {}),
            )
        ]
        tx = b.x + 8
        if state.initial:
            parts.append(
                _tag(
                    'circle',
                    {
                        'class': 'start',
                        'cx': number(b.x + 8),
                        'cy': number(b.y + b.height / 2),
                        'r': '3',
                        'fill': _light('start'),
                    },
                )
            )
            tx = b.x + 15
        parts.append(
            _text(
                tx, b.y + b.height / 2 + 3.5, name, 'small', _light('ink'), **{'font-size': f'{SMALL_SIZE}'}
            )
        )
        data = {} if state.name is None else {'data-state': state.name}
        inner.append(_group('state', data, tip, *parts))
    for step in machine.transitions:
        source = 'any state' if step.source is None else step.source
        tip = (
            f'{step.number}: {", ".join(step.events)}, from {source} to {step.target}, '
            f'by {", ".join(titles.get(by, by) for by in step.by)}'
        )
        bx, by = step.badge
        inner.append(
            _group(
                'transition',
                {'data-event': ' '.join(step.events)},
                tip,
                _tag(
                    'path',
                    {
                        'class': 'step',
                        'd': _path(step.points),
                        'fill': 'none',
                        'stroke': _light('transition'),
                        'stroke-width': '1.2',
                        'marker-end': 'url(#head-step)',
                    },
                ),
                _tag(
                    'circle',
                    {
                        'class': 'step-badge',
                        'cx': number(bx),
                        'cy': number(by),
                        'r': '5',
                        'fill': _light('transition'),
                    },
                ),
                _text(
                    bx,
                    by + 2.5,
                    str(step.number),
                    'step-number',
                    _light('paper'),
                    **{'font-size': '7', 'text-anchor': 'middle'},
                ),
            )
        )
    for number_, text, (kx, ky) in machine.key:
        inner.append(
            _text(
                kx,
                ky,
                (f'{number_}  ' if number_ != '' else '') + shorten(text, SMALL_SIZE, box.width - 24),
                'key',
                _light('muted'),
                **{'font-size': f'{SMALL_SIZE}'},
            )
        )
    tip = (
        f'{machine.name} ({machine.var}): {_plural(sum(s.name is not None for s in machine.states), "state")}'
    )
    return _group('machine', {'data-var': machine.var}, tip, *inner)


def _line(kind, d, **extra):
    """The attributes of a line of an arrow of `kind` whose `d` is given: its class, its colour and its
    look (D-50), then `extra`."""
    how = ARROWS.get(kind, ARROWS['reads'])
    return {
        'class': f'line-{kind}',
        'd': d,
        'fill': 'none',
        'stroke': _light(kind) if kind in COLOURS else _light('reads'),
        'stroke-width': number(how['width']),
        'stroke-dasharray': how['dash'],
        'stroke-linecap': 'round' if kind.split('-')[0] == 'reads' else None,
        'stroke-opacity': None if how['opacity'] == 1 else f'{how["opacity"]}',
        **extra,
    }


def _head(kind):
    return f'url(#head-{kind if kind in ARROWS else "reads"})'


def _arrow(route, titles, looks=None):
    """An arrow. An arrow of a bundle (D-51) draws the head on its last segment, and its whole line
    without colour (`route member`, stroke-opacity 0), which a rule of the style can show; its bundle
    draws the rest of its line. `looks` (the picture's `settings.looks`) can make its kind light."""
    look = drawn_as(route.kind, looks)
    source, target = titles.get(route.source, route.source), titles.get(route.target, route.target)
    if route.kind in READ_VERBS:
        tip = f'{target} {READ_VERBS[route.kind]} {source}'
    else:
        tip = f'{source} {VERBS.get(route.kind, route.kind)} {target}'
        if route.how:
            tip += f' ({", ".join(route.how)})'
    if route.values:
        tip += f': {", ".join(route.values)}'
    if 0 < route.count < len(route.values):
        tip += f' (at most {route.count} in one run)'
    if route.bundle is None:
        lines = [_tag('path', _line(look, _path(route.points), **{'marker-end': _head(look)}))]
    else:
        whole = _line(look, _path(route.points))
        whole.update(
            {'class': f'{whole["class"]} route member', 'stroke-opacity': '0', 'pointer-events': 'none'}
        )
        lines = [
            _tag('path', whole),
            _tag('path', _line(look, _path(route.points[-2:]), **{'marker-end': _head(look)})),
        ]
    return _group(
        f'arrow {route.kind}',
        {'data-from': route.source, 'data-to': route.target, 'data-kind': route.kind},
        tip,
        *lines,
    )


def _shared(routes):
    """The line of the routes of a bundle without the last segment of each route, each stretch once:
    the sorted segments ((x0, y0), (x1, y1)), each from its left or top end."""
    lines = {}
    for route in routes:
        for (x0, y0), (x1, y1) in itertools.pairwise(route.points[:-1]):
            if y0 == y1:
                lines.setdefault(('h', y0), []).append((min(x0, x1), max(x0, x1)))
            else:
                lines.setdefault(('v', x0), []).append((min(y0, y1), max(y0, y1)))
    out = []
    for (axis, at), spans in lines.items():
        merged = []
        for low, high in sorted(spans):
            if merged and low <= merged[-1][1]:
                merged[-1][1] = max(merged[-1][1], high)
            else:
                merged.append([low, high])
        for low, high in merged:
            out.append(((low, at), (high, at)) if axis == 'h' else ((at, low), (at, high)))
    return sorted(out)


def _bundle(bundle, routes, titles, looks=None):
    """A bundle (D-51): its tooltip, the line that its routes share and their branches up to the last
    segment of each, which its arrows draw, and a dot at each junction."""
    targets = ', '.join(titles.get(target, target) for target in bundle.targets)
    if bundle.kind in BUNDLE_VERBS:
        tip = f'{BUNDLE_VERBS[bundle.kind]} {targets}'
    else:
        tip = f'{titles.get(bundle.source, bundle.source)} {VERBS.get(bundle.kind, bundle.kind)} {targets}'
    values = list(dict.fromkeys(value for route in routes for value in route.values))
    if values:
        tip += f': {", ".join(values)}'
    d = ''.join(
        f'M{number(x0)} {number(y0)}L{number(x1)} {number(y1)}' for (x0, y0), (x1, y1) in _shared(routes)
    )
    kind = drawn_as(bundle.kind if bundle.kind in ARROWS else 'reads', looks)
    dots = [
        _tag(
            'circle',
            {'class': f'dot-{kind}', 'cx': number(x), 'cy': number(y), 'r': '1.5', 'fill': _light(kind)},
        )
        for x, y in bundle.junctions
    ]
    return _group(
        f'bundle {bundle.kind}',
        {'data-from': bundle.source, 'data-kind': bundle.kind},
        tip,
        _tag('path', _line(kind, d)),
        *dots,
    )


def _arrows(layout, titles, looks=None):
    """The arrows, in their order, each bundle before its first arrow, in the looks of `looks`."""
    out, drawn = [], set()
    for route in layout.routes:
        if route.bundle is not None and route.bundle not in drawn:
            drawn.add(route.bundle)
            routes = [other for other in layout.routes if other.bundle == route.bundle]
            out.append(_bundle(layout.bundles[route.bundle], routes, titles, looks))
        out.append(_arrow(route, titles, looks))
    return ''.join(out)


def _frame(frame):
    return _group(
        'group',
        {'data-group': frame.label},
        frame.label,
        _rect(
            frame.box, 'frame', _light('frame-fill'), _light('frame'), rx='10', **{'stroke-dasharray': '5 3'}
        ),
        _text(
            frame.label_at[0],
            frame.label_at[1],
            frame.label,
            'frame-label',
            _light('frame'),
            **{'font-size': '11', 'font-weight': '600'},
        ),
    )


def _sample(mark, box, looks=None):
    """The sample of a mark of the legend, in the first 30 px of its box, an arrow in its look."""
    x, y = box.x, box.y + box.height / 2
    if mark in ARROWS:
        look = drawn_as(mark, looks)
        return _tag(
            'path',
            _line(
                look, f'M{number(x)} {number(y)}L{number(x + 28)} {number(y)}', **{'marker-end': _head(look)}
            ),
        )
    if mark == 'stock':
        return _rect(type(box)(x, y - 6, 28, 12), 'tank', _light('stock'), _light('stock-edge'), rx='3')
    if mark == 'tally':
        return _rect(type(box)(x, y - 6, 28, 12), 'meter', _light('tally'), _light('tally-edge'), rx='6')
    if mark == 'pipe':
        return _tag(
            'path',
            {
                'class': 'flow',
                'd': f'M{number(x)} {number(y)}L{number(x + 28)} {number(y)}',
                'fill': 'none',
                'stroke': _light('pipe'),
                'stroke-width': '2',
                'marker-end': 'url(#head-pipe)',
            },
        )
    if mark == 'state':
        return _rect(type(box)(x, y - 7, 28, 14), 'pill', _light('state'), _light('state-edge'), rx='7')
    if mark == 'transition':
        return _tag(
            'path',
            {
                'class': 'step',
                'd': f'M{number(x)} {number(y)}L{number(x + 28)} {number(y)}',
                'fill': 'none',
                'stroke': _light('transition'),
                'stroke-width': '1.2',
                'marker-end': 'url(#head-step)',
            },
        )
    cx = x + 14
    return _tag(
        'path',
        {
            'class': 'decides',
            'd': f'M{number(cx)} {number(y - 5)}L{number(cx + 5)} {number(y)}L{number(cx)} {number(y + 5)}'
            f'L{number(cx - 5)} {number(y)}Z',
            'fill': _light('actor'),
        },
    )


def _legend(legend, looks=None):
    if not legend.items:
        return ''
    inner = [_rect(legend.box, 'legend-box', _light('paper'), _light('edge'), rx='6')]
    for mark, words, box in legend.items:
        inner.append(
            _group(
                'mark',
                {'data-mark': mark},
                words,
                '' if mark in legend.hidden else _sample(mark, box, looks),
                _text(
                    box.x + 38,
                    box.y + box.height / 2 + 3.5,
                    words,
                    'small',
                    _light('ink'),
                    **{'font-size': f'{SMALL_SIZE}'},
                ),
            )
        )
    return _group('legend', {}, 'The marks of the picture', *inner)


# ---- the panels (D-53, D-55, D-57) ----------------------------------------------------------------


def attribute_text(text):
    """`text` for an attribute that must read back as it is (`data-latex`): escaped, with each newline,
    carriage return and tab as a character reference, which an XML reader keeps."""
    return escape(text).replace('\n', '&#10;').replace('\r', '&#13;').replace('\t', '&#9;')


def _panel_style():
    """The rules of the panels and of the symbol tags, with those of the typesetter (`typeset.STYLE`): in
    the style only when the picture has panels."""
    from . import typeset

    return (
        '.napkin-draw .panel-box{fill:var(--paper);stroke:var(--edge)}',
        '.napkin-draw .panel-text,.napkin-draw .panel-strong,.napkin-draw .panel-heading{fill:var(--ink)}',
        '.napkin-draw .panel-strong,.napkin-draw .panel-head,.napkin-draw .panel-heading{font-weight:600}',
        '.napkin-draw .panel-muted,.napkin-draw .panel-head,.napkin-draw .marks{fill:var(--muted)}',
        '.napkin-draw .panel-link{fill:var(--link);text-decoration:underline}',
        '.napkin-draw .stripe{fill:var(--card)}',
        '.napkin-draw .table-rule{stroke:var(--edge)}',
        '.napkin-draw .tag-box{fill:var(--paper);stroke:var(--stock-edge)}',
        '.napkin-draw .tag-box-tally{fill:var(--paper);stroke:var(--tally-edge)}',
        *(f'.napkin-draw .mark-{colour}{{fill:var(--mark-{colour})}}' for colour in refs.COLOURS),
        *typeset.STYLE,
    )


# The look of each run of a panel: its class, its colour and its other attributes.
RUN_LOOKS = {
    'plain': ('panel-text', 'ink', {}),
    'strong': ('panel-strong', 'ink', {'font-weight': '600'}),
    'muted': ('panel-muted', 'muted', {}),
    'head': ('panel-head', 'muted', {'font-weight': '600'}),
    'heading': ('panel-heading', 'ink', {'font-weight': '600'}),
    'link': ('panel-link', 'link', {'text-decoration': 'underline'}),
}
# The words of the kinds of an equation line, for its tooltip.
LINE_WORDS = {
    'balance': 'Balance',
    'rate': 'Rate of a flow',
    'formula': 'Formula',
    'bound': 'Bounds',
    'share': 'Share of a stock',
    'together': 'Pairs that move together',
    'jump': 'Change at an event',
    'check': 'Check',
}


def _look(run, kind=None):
    """(class, light colour, attributes) of a run; the number of an entry has its kind's colour."""
    if run.look == 'number':
        colour = refs.COLOUR_KIND.get(kind, 'assumption')
        return f'entry-number mark-{colour}', _light(f'mark-{colour}'), {'font-weight': '600'}
    cls, colour, extra = RUN_LOOKS.get(run.look, RUN_LOOKS['plain'])
    return cls, _light(colour), extra


def _span(run, kind=None):
    cls, fill, extra = _look(run, kind)
    inner = _tag('tspan', {'class': cls, 'fill': fill, **extra}, escape(run.text))
    if run.url is not None and refs.web_host(run.url):
        return _tag('a', {'href': run.url, 'xlink:href': run.url}, inner)
    return inner


def _runs(runs, kind=None, marks=None):
    """The `<text>` of runs of one row that follow one another, at the first run's x and baseline: one
    run with its look on the `<text>`, or each run as a `<tspan>` (a link inside `<a>`) with a space
    where the layout leaves one. The marks that follow the last run (`marks`) end the text, so that
    they follow its glyphs whatever the font."""
    first = runs[0]
    if len(runs) == 1 and first.url is None and marks is None:
        cls, fill, extra = _look(first, kind)
        attributes = {'class': cls, 'x': number(first.x), 'y': number(first.y)}
        attributes.update({'font-size': number(first.size), 'fill': fill, **extra})
        return _tag('text', attributes, escape(first.text))
    body = []
    for k, run in enumerate(runs):
        if k and run.x > runs[k - 1].box.right:
            body.append(' ')
        body.append(_span(run, kind))
    if marks is not None:
        body.append(_mark_spans(marks))
    attributes = {
        'class': 'panel-text',
        'x': number(first.x),
        'y': number(first.y),
        'font-size': number(first.size),
        'fill': _light('ink'),
    }
    return _tag('text', attributes, ''.join(body))


def _mark_spans(marks):
    """The `<tspan>`s of marks, each smaller and at the raised y of the marks (an absolute y, not
    `baseline-shift`), after the text before them: a number in the colour of its kind (`mark mark-<colour>`,
    `references.COLOUR_KIND`), and the commas muted."""
    spans = []
    for text, _, mark in marks.parts:
        if mark is None:
            cls, fill = 'panel-muted', _light('muted')
        else:
            colour = refs.COLOUR_KIND.get(mark.kind, 'assumption')
            cls, fill = f'mark mark-{colour}', _light(f'mark-{colour}')
        attributes = {'class': cls, 'y': number(marks.y), 'font-size': number(marks.size), 'fill': fill}
        spans.append(_tag('tspan', attributes, escape(text)))
    return ''.join(spans)


def _marks(marks):
    """Marks that follow no run (after a typeset node, or alone): a `<text>` at their x of
    `<tspan>`s (`_mark_spans`)."""
    attributes = {
        'class': 'marks',
        'x': number(marks.box.x),
        'y': number(marks.y),
        'font-size': number(marks.size),
        'fill': _light('muted'),
    }
    return _tag('text', attributes, _mark_spans(marks))


def _items(items, kind=None):
    """The SVG of the items of a row of a panel, in reading order: the runs that follow one another on
    one baseline in one `<text>`, with the marks that follow them; each typeset node
    (`typeset.svg_parts`); each set of marks after a node."""
    from . import typeset
    from .layout import MARK_RISE, Marks, Math, Run

    out, runs = [], []

    def flush(marks=None):
        if runs:
            out.append(_runs(list(runs), kind, marks))
            runs.clear()

    for item in items:
        if isinstance(item, Run):
            last = runs[-1] if runs else None
            follows = (
                last is not None
                and last.y == item.y
                and last.size == item.size
                and 'number' not in (last.look, item.look)
                and 0 <= item.x - last.box.right <= item.size
            )
            if not follows:
                flush()
            runs.append(item)
        elif isinstance(item, Marks) and runs and runs[-1].y == item.y + MARK_RISE:
            flush(item)
        else:
            flush()
            if isinstance(item, Math):
                out.append(typeset.svg_parts(item.equation, item.x, item.y))
            elif isinstance(item, Marks):
                out.append(_marks(item))
    flush()
    return ''.join(out)


def _tag_of(stock, tally=False):
    """The tag of a stock row or a meter (D-53): a small box with its symbol, at the right of the row."""
    from . import typeset

    tag = stock.tag
    box = _rect(
        tag.box,
        'tag-box-tally' if tally else 'tag-box',
        _light('paper'),
        _light('tally-edge' if tally else 'stock-edge'),
        rx='3',
    )
    return _group(
        'tag',
        {'data-key': stock.key},
        f'The symbol of {stock.name}: {tag.text}',
        box,
        typeset.svg_parts(tag.math.equation, tag.math.x, tag.math.y),
    )


def _heading(panel):
    return _items((panel.heading,)) if panel.heading is not None else ''


def _equations(panel):
    """The Equations panel: its box and heading, and a `g.block` for each block, its head first, with a
    `g.equation` for each line. A line has its LaTeX (`data-latex`, D-57), its part and its records."""
    from .layout import Block, EquationLine

    blocks, current = [], None
    for row in panel.rows:
        if isinstance(row, Block):
            current = [row]
            blocks.append(current)
        else:
            current.append(row)
    out = []
    for head, *rows in blocks:
        tip = head.title
        if len(head.members) > 1:
            tip += '\nFor ' + ', '.join(head.members)
        inner = [_items(head.items)]
        for row in rows:
            if not isinstance(row, EquationLine):
                inner.append(_items(row.items))
                continue
            line_tip = (
                f'{LINE_WORDS.get(row.kind, row.kind)}: {row.part}'
                if row.part
                else LINE_WORDS.get(row.kind, row.kind)
            )
            data = {'data-latex': row.latex, 'data-part': row.part}
            if row.records:
                data['data-record'] = ' '.join(row.records)
            inner.append(_line_group(data, line_tip, _items(row.items)))
        out.append(_group('block', {'data-block': head.name}, tip, *inner))
    return _group(
        'equations',
        {},
        'Equations',
        _rect(panel.box, 'panel-box', _light('paper'), _light('edge'), rx='6'),
        _heading(panel),
        *out,
    )


def _line_group(data, tip, inner):
    """A `g.equation`: its `data-latex` keeps every character of the LaTeX (`attribute_text`)."""
    latex = data.pop('data-latex')
    head = f'<g class="equation" data-latex="{attribute_text(latex)}"{_attributes(data)}>'
    return head + _title(tip) + inner + '</g>'


def _symbol_table(panel):
    """The Symbols table: its box and heading, its head with a rule under it, and a `g.symbol` for each
    row, every other row on a stripe."""
    head, *rows = panel.rows
    inner = [
        _rect(panel.box, 'panel-box', _light('paper'), _light('edge'), rx='6'),
        _heading(panel),
        ''.join(_items(cell.items) for cell in head.cells),
        _tag(
            'line',
            {
                'class': 'table-rule',
                'x1': number(head.box.x),
                'y1': number(head.box.bottom),
                'x2': number(head.box.right),
                'y2': number(head.box.bottom),
                'stroke': _light('edge'),
            },
        ),
    ]
    for k, row in enumerate(rows):
        parts = []
        if k % 2:
            parts.append(_rect(row.box, 'stripe', _light('card'), None))
        parts += [_items(cell.items) for cell in row.cells]
        data = {'data-key': row.key}
        if row.records:
            data['data-record'] = ' '.join(row.records)
        inner.append(_group('symbol', data, f'{row.symbol} ({row.key}): {row.meaning}', *parts))
    return _group('symbols', {}, 'Symbols', *inner)


def _references(panel):
    """The References list: its box and heading, and a `g.reference` for each entry, whose tooltip is the
    entry's full words. Its link is the one `<a href>` of the picture (D-55), to its `http` or `https`
    address."""
    from .layout import Note

    inner = [_rect(panel.box, 'panel-box', _light('paper'), _light('edge'), rx='6'), _heading(panel)]
    for entry in panel.rows:
        if isinstance(entry, Note):
            # The kinds of record that the list leaves out.
            text = ' '.join(item.text for item in entry.items)
            inner.append(_group('left-out', {}, text, _items(entry.items)))
            continue
        data = {'data-number': str(entry.number)}
        if entry.record:
            data['data-record'] = ' '.join(entry.record)
        text = ' '.join(item.text for item in entry.items)
        inner.append(_group('reference', data, entry.hover or text, _items(entry.items, entry.kind)))
    return _group('references', {}, 'References', *inner)


def _note(panel):
    (row,) = panel.rows
    text = ' '.join(item.text for item in row.items)
    return _group('note', {}, text, _items(row.items))


def _panels(layout):
    """The panels under the legend, in their order."""
    draw = {'equations': _equations, 'symbols': _symbol_table, 'references': _references, 'note': _note}
    return ''.join(draw[panel.kind](panel) for panel in layout.panels)


def _description(picture, layout):
    counts = {kind: sum(route.kind == kind for route in layout.routes) for kind in ARROWS}
    kinds = ', '.join(f'{count} {kind}' for kind, count in counts.items() if count)
    about = '; '.join(layout.subtitle or (str(picture.get('name') or ''),))
    return (
        f'The model {about}: {_plural(len(layout.cards), "thing")} and '
        f'{_plural(len(layout.routes), "arrow")}{f" ({kinds})" if kinds else ""}. Each thing is a box with '
        'its stocks, its flows and its state machines. The arrows show what each thing reads, follows, '
        'changes, fires and moves of the others.'
    )


def svg(picture, layout, *, title=None):
    """The picture as one SVG document (a text): the cards, the arrows, the frames, the legend and the
    panels that `layout` (`layout.layout(picture)`) places. `title` is the title of the document, by default the
    picture's title. Two calls with the same picture and layout give the same text."""
    title = str(picture.get('title') or picture.get('name') or 'Model') if title is None else str(title)
    titles = {card.id: card.title for card in layout.cards}
    links = _connections(picture, titles)
    used = {card.icon for card in layout.cards if card.icon in icons.SHAPES}
    width, height = number(layout.width), number(layout.height)
    head = (
        '<svg'
        + _attributes(
            {
                'xmlns': NAMESPACE,
                'xmlns:xlink': XLINK,
                'class': 'napkin-draw',
                'width': width,
                'height': height,
                'viewBox': f'0 0 {width} {height}',
                'role': 'img',
                'aria-labelledby': 'napkin-title napkin-desc',
                'font-family': FONT,
            }
        )
        + '>'
    )
    x, y = layout.title_at
    subtitle = layout.subtitle or (str(picture.get('name') or ''),)
    looks = (picture.get('settings') or {}).get('looks') or DEFAULT_LOOKS
    tagged = any(stock.tag is not None for card in layout.cards for stock in (*card.stocks, *card.meters))
    parts = [
        head,
        f'<title id="napkin-title">{escape(title)}</title>',
        f'<desc id="napkin-desc">{escape(_description(picture, layout))}</desc>',
        _style(titles, panels=bool(layout.panels) or tagged),
        '<defs>' + _markers() + _symbols(used) + '</defs>',
        _tag('rect', {'class': 'paper', 'width': '100%', 'height': '100%', 'fill': _light('paper')}),
        _text(
            x,
            y,
            shorten(title, PICTURE_TITLE_SIZE, layout.width - 2 * x),
            'heading',
            _light('ink'),
            **{'font-size': f'{PICTURE_TITLE_SIZE:g}', 'font-weight': '600'},
        ),
        *(
            _text(
                x,
                y + 16 + SUBTITLE_LINE * k,
                shorten(line, SMALL_SIZE, layout.width - 2 * x),
                'subheading',
                _light('muted'),
                **{'font-size': f'{SMALL_SIZE}'},
            )
            for k, line in enumerate(subtitle)
        ),
        '<g class="frames">' + ''.join(_frame(frame) for frame in layout.frames) + '</g>',
        '<g class="cards">' + ''.join(_card(card, titles, links[card.id]) for card in layout.cards) + '</g>',
        '<g class="machines">'
        + ''.join(_machine(machine, titles, beside=True) for machine in layout.machines)
        + '</g>',
        '<g class="arrows">' + _arrows(layout, titles, looks) + '</g>',
        _legend(layout.legend, looks),
        *((_panels(layout),) if layout.panels else ()),
        '</svg>',
    ]
    return '\n'.join(parts) + '\n'


__all__ = ['COLOURS', 'NAMESPACE', 'escape', 'number', 'svg']
