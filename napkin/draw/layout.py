"""The layout of the picture of a model: where `svg.py` draws each card, stock, pipe, state machine,
arrow, group frame and the legend.

The layout reads only the picture (`model_map.picture`, a plain dict). The picture already holds what
the stylesheet chooses: the `place` of each card, the `groups`, and the `place` of each state machine.
The layout never reads the model. Every step is deterministic: it sorts by explicit keys, never by the
order of a set, and it rounds each coordinate to 0.5.

1. **Size.** A title wraps at 28 characters, on at most 2 lines. A text is about 0.6 em wide for each
   character; nothing measures a font.
2. **Collapse.** Pipes between the same two ends become one pipe, which shows its number of flows. A
   card shows at most `settings.stocks` of its stocks and tallies (`limits`; 4 by default). A card
   with a `stock_order` (`[stocks]`, D-52) shows the first keys of that list, up to that number, in
   their order; else it shows stocks before tallies, then the ones with more pipes, then in the order
   of the picture. A row
   "+n" stands for the others. The stock rows are above the meters, so the order holds among the
   stocks and among the tallies. A card is at least `settings.card_width` wide (`CARD_MIN` by
   default), and wider when its title, its rows or its machines need more. The tallies that it
   shows are meters, each as wide as its name (up to `METER_MAX`, and never wider than the card), in
   rows that wrap when a row is full; a meter whose name does not fit shows its start and '…', and the
   card grows wider when two meters would show the same text. A pipe is drawn between two stock rows,
   or between a stock row and the outside; a pipe of a tally, or of a stock that is not shown, is in
   the tooltip of its meter or of the "+n" row. A state machine goes inside its card when it has at
   most 4 states and 6 transitions, else beside it (below the card, in the same column). A machine
   that the stylesheet puts beside stays beside, and a hidden machine is not drawn. The rows of the
   events of a card (`[triggers]`, D-56) are at its bottom, under its machines: a row "n events" at
   `count`; a row for each event's name at `names`; at `rules`, the line of each event (its name in
   bold, then its condition, its timing, its chances, what it changes and the options that switch it)
   in at most `lines` rows, cut with '…' (`text.shorten`); and at `names` and `rules` a row "+n more"
   after the first `events` events. A card at `rules` is at least `RULES_WIDTH` wide, so that a row
   holds about 44 characters, and at `names` its names widen it up to that width. The tooltip of the
   card holds the full line of each event at every level, `hover` too.
3. **Rank.** A card's `place.column` gives its column. The changes, fires and moves arrows (`RANKING`) rank the other
   cards: the Eades–Lin–Smyth greedy order (ties in the order of the cards) breaks the cycles, and
   each card takes the layer after the latest card that changes, fires or moves it (longest path). A card
   with only reads and follows takes the median layer of the cards that it reads or that read it; a card with no
   arrow takes the last layer.
4. **Columns.** A column holds at most `settings.cards_per_column` cards (8 by default): a fuller
   layer splits into the fewest adjacent sub-columns that hold it. A card with a row goes to the
   sub-column of its row, or to the nearest one with room when that one is full.
5. **Bundles and slots.** The arrows of one kind of `settings.bundle` (default reads and follows) from
   one card toward one side are a bundle when they are two or more (D-51): to the right for the cards
   in later columns and in the card's own column, to the left for the cards in earlier columns. Each
   other arrow is alone. An arrow alone that passes a column goes through a slot of its own in that
   column; a bundle has one slot in each column that it passes, which its arrows share. An arrow that
   goes from right to left is routed as from left to right, with its head at its true end.
6. **Order.** Barycenter sweeps over all arrows (reads and follows at half weight) order each column; of 24
   sweeps, the order with the fewest crossings wins (an exact count, each crossing weighted as its two
   arrows are; a segment of a bundle between two items counts once). In each column the members of a group are one block, and the blocks go in the order of
   the groups. A card's `place.row` orders it among the cards of its column; when that puts it inside
   the block of a group that it is not in, or when the rows of the members put other cards between
   them, each card that is not a member goes to the nearer end of the block (before its first member
   when fewer members are before it than after it, else after its last).
7. **Positions.** A group is a band across the columns that its members span, drawn as a frame with
   its label around its members only; the other cards of those columns go above or below the band.
   Each column is centred vertically in the space that it has.
8. **Routes.** Each arrow goes horizontally, vertically on a track in the gap between two columns,
   then horizontally. Greedy interval colouring in the order of the intervals' low ends gives the
   tracks, as few as the most intervals that meet at one height need (D-50), and each gap is as wide
   as its tracks need. An arrow between two cards of one column uses the gap on the right of the column.
   The ports of the arrows are spread evenly on each side of a card, in the order of the height of
   their other end, and a card grows taller when a side needs more ports. Arrows of other kinds
   between the same two cards stay separate.
9. **Bundles.** The arrows of a bundle share one port at its card. In each gap, the vertical part of
   a bundle is one trunk on one track, from its lowest end to its highest; each arrow leaves the trunk
   at the height of its next item (its card's port, or the bundle's next slot). So the routes of a
   bundle share their start and the line from it, and after they split they do not meet again. A
   junction is each point inside a trunk where a branch leaves it.
10. **Panels** (`picture['panels']`, D-53, D-55, D-57). Under the legend, at the left margin, each
   `settings.width` wide (the picture widens to hold them), one under another: the Equations; the
   Symbols table when `settings.symbols`; the References when there are entries; and the note on a
   chosen range when there is one. A panel has a heading and rows; every row is a box inside its
   panel, under the row before it, and every item of a row (`Run`, `Math`, `Marks`) is inside it,
   apart from the others. The text of a row wraps by words at the estimate of `text_width`; a word
   wider than a row breaks where it must.
   - **Equations.** A head for each block (its title, and "For …" with the titles of its members
     when it stands for several), then each line, `INDENT` in: an equation typeset as `lhs = rhs`
     (`typeset.typeset` with `left` and `relation`), the trees of any other line typeset one by one
     with a comma between them, at most `settings.lines` rows of them; for a jump, "at" and the name
     of its event in words (and its outcome), muted; the line's few words, muted; and its marks last. The time
     since an event and its count are the symbols of the event and of its count, as the LaTeX writes
     them (`panels.line_latex`). The math leaves room for the marks after it. A block without lines
     says "No equations.".
   - **Symbols.** A head, then a row for each symbol, in the columns of `COLUMNS` that hold something
     (the symbol and the meaning always): the symbol (and its count) with the marks of its value; the
     meaning (an event's: the time since it happens); the unit; the value, each instance's value, each
     option's value with its marks, or the number of options that set it; "chosen range lo–hi" for a
     range that the scenario chose, else "range lo–hi", with its marks; the distribution. A column is
     as wide as its widest cell, at most `COLUMN_MOST`; the meaning takes the rest. When the table is
     too wide, the columns share the room (`COLUMN_WEIGHT`), never below `COLUMN_LEAST`.
   - **References.** Each entry: its number, then its label in bold, its text and its link text,
     wrapped after the number. The link is the entry's `http` or `https` address only.
   - **Tags.** A stock row or a meter of `panels.tags` carries its symbol in a small box at its right
     end, inside the row: the row's text leaves room for it, and the card grows for it.
"""

from __future__ import annotations

import dataclasses
import itertools
import math
from dataclasses import dataclass

from .defaults import (
    ARROW_KINDS,
    DEFAULT_BUNDLE,
    DEFAULT_CARDS_PER_COLUMN,
    DEFAULT_PANEL_LINES,
    DEFAULT_PANEL_WIDTH,
    DEFAULT_STOCKS,
    RANKING,
)
from .references import left_out_words, web_host
from .text import shorten as fit_lines

# The kinds of arrows (D-50), and the kinds that rank the cards: an arrow that only reads a value or
# follows an event does not put its reader in a later column.
KINDS = ARROW_KINDS
# The weight of an arrow in the order of a column.
WEIGHTS = {'reads': 0.5, 'follows': 0.5, 'changes': 1.0, 'fires': 1.0, 'moves': 1.0}
# The kinds whose arrows from one card toward one side share a trunk, when the picture's settings do not
# say (D-51).
BUNDLE = DEFAULT_BUNDLE
# The marks of the legend, in its order, and their words.
LEGEND_WORDS = {
    'reads': 'Reads a value',
    'follows': 'Follows an event',
    'changes': 'Changes a value',
    'fires': 'Fires an event',
    'moves': 'Moves material',
    'stock': 'Stock',
    'tally': 'Tally',
    'pipe': 'Flow',
    'state': 'State',
    'transition': 'Event that changes the state',
    'decides': 'Decides',
}
MARKS = tuple(LEGEND_WORDS)

# The limits of the collapse. `MAX_STOCKS` and `MAX_COLUMN` are the most stock rows of a card and the
# most cards of a column of a picture without `settings` (D-52, `limits`).
TITLE_WRAP = 28
TITLE_LINES = 2
MAX_STOCKS = DEFAULT_STOCKS
INSIDE_STATES = 4
INSIDE_TRANSITIONS = 6
MAX_COLUMN = DEFAULT_CARDS_PER_COLUMN
SWEEPS = 24

# Text: the size of each kind of text (px), and the width of one character (em).
TITLE_SIZE = 12.0
PICTURE_TITLE_SIZE = 17.0  # the title of the picture
TEXT_SIZE = 10.5
SMALL_SIZE = 9.5
EM = 0.6
# A bold text (weight 600) is at most this much wider than `typeset.run_width` gives for it, in the
# common sans-serif fonts. The widest letters against that estimate are DejaVu Sans Bold's b, d, g, p
# and q (0.716 em, 1.085 times the estimate).
BOLD = 1.1
LINE = 15.0  # the height of a line of a title
KEY_LINE = 13.0  # the height of a line of a machine's key
START_LINES = 4  # the most lines of a machine's key that name the options that set its start

# A card.
PAD = 8.0
ICON = 18.0
CARD_MIN = 170.0  # the least width of a card without `settings.card_width` (D-52)
ROW = 20.0  # a stock row
ROW_GAP = 4.0
METER = 20.0  # a row of meters
METER_TEXT = 20.0  # from the left of a meter to its text, after the gauge
METER_END = 8.0  # from the text of a meter to its right
METER_MAX = 190.0  # the widest meter that widens a card for its text
MORE = 15.0  # the "+n" row
TRIGGER_TOP = 6.0  # above the rows of the events of a card
TRIGGER_LINE = 13.0  # a line of the row of an event
TRIGGER_GAP = 2.0  # between the rows of two events
TRIGGER_MARK = 10.0  # from the left of the row of an event to its text, after its mark
RULES_WIDTH = 280.0  # the least width of a card that shows the lines of its events (D-56)
LANE = 10.0  # a lane of the pipes between stocks
STUB = 34.0  # a pipe to or from the outside
TANK_MIN = 80.0
TANK_MAX = 190.0
BADGE_GAP = 6.0

# A state machine.
MPAD = 6.0
MHEAD = 14.0
PILL = 16.0
PILL_GAP = 8.0
MGAP = 10.0
MTRACK = 12.0
BADGE = 5.0
MACHINE_GAP = 10.0  # between a card and a machine beside it

# The picture.
MARGIN = 24.0
TITLE_AREA = 44.0
SUBTITLE_LINE = 14.0  # each line of the subtitle after the first
ITEM_GAP = 18.0  # between two items of a column
SLOT = 8.0  # the slot of an arrow that passes a column
SLOT_GAP = 3.0  # between a slot and the item next to it
PORT = 8.0  # between two ends of arrows on one side of a card
TRACK = 6.0  # between two tracks of a gap
GAP_EDGE = 22.0  # from a column to the first track of a gap
FRAME_PAD = 10.0
FRAME_TOP = 24.0  # the label of a frame
FRAME_GAP = 16.0  # between two frames
LEGEND_GAP = 24.0
LEGEND_ROW = 22.0
LEGEND_SAMPLE = 30.0

# The panels under the legend (D-53, D-55): their width when the picture's settings do not give one,
# the most lines of an equation, and their spaces.
PANEL_WIDTH = float(DEFAULT_PANEL_WIDTH)
PANEL_LINES = DEFAULT_PANEL_LINES
PANEL_GAP = 18.0  # above each panel: from the legend, or from the panel before it
PANEL_PAD = 12.0  # inside a panel
# The tallest page of a PDF, 200 in at 96 px to the inch: `napkin draw` says when a picture is taller.
PAGE_HEIGHT = 19200.0
HEADING_SIZE = 13.0  # the heading of a panel
HEADING_GAP = 8.0  # under the heading
BLOCK_GAP = 10.0  # above the head of a block after the first
INDENT = 14.0  # the lines of a block, in from the head of their block
LINE_GAP = 5.0  # between two lines of a block, two entries, the rows of a text
ROW_PAD = 3.0  # above and below the cells of a row of the Symbols table
CELL_GAP = 10.0  # between two columns of the Symbols table
MARK_SIZE = 7.0  # the numbers of the marks
MARK_RISE = 4.0  # the baseline of the marks, above the baseline of their text
# The columns of the Symbols table, their headings, the least and the most width of each that holds
# text, and the weight of each when the table is too wide: the meaning gives up room last.
COLUMNS = ('symbol', 'meaning', 'unit', 'value', 'range', 'distribution')
HEADINGS = {
    'symbol': 'Symbol',
    'meaning': 'Meaning',
    'unit': 'Unit',
    'value': 'Value',
    'range': 'Range',
    'distribution': 'Distribution',
}
COLUMN_LEAST = 40.0
COLUMN_MOST = {'unit': 120.0, 'value': 260.0, 'range': 200.0, 'distribution': 220.0}
COLUMN_WEIGHT = {'meaning': 2.0}
# The tag of a stock row or a meter: the size of its symbol, the room around the symbol in its box,
# from the box to the right end of the row, and between the row's text and the box.
TAG_SIZE = SMALL_SIZE
TAG_PAD = 3.0
TAG_INSET = 3.0
TAG_GAP = 4.0
# What follows a key to name the count of its event (`panels.COUNTED`): no key has a `#`.
COUNTED = '#count'


def half(value):
    """`value` rounded to the nearest 0.5, halves upward."""
    return math.floor(value * 2 + 0.5) / 2


def up(value):
    """`value` rounded up to a multiple of 0.5."""
    return math.ceil(value * 2) / 2


def text_width(text, size):
    """The width of a text in px, at about 0.6 em for each character."""
    return len(text) * EM * size


def bold_width(text, size):
    """The width of a bold text in px: the width of each character (`typeset.run_width`) times `BOLD`,
    and never less than `text_width`."""
    from . import typeset  # typeset imports this module

    return up(max(text_width(text, size), BOLD * typeset.run_width(text, size)))


def shorten(text, size, width):
    """`text`, cut with '…' to fit in `width` px."""
    if text_width(text, size) <= width:
        return text
    keep = max(1, int(width / (EM * size)) - 1)
    return text[:keep].rstrip() + '…'


def wrap(text, width=TITLE_WRAP, lines=TITLE_LINES):
    """The lines of a title: words of at most `width` characters to a line, at most `lines` lines; the
    last line ends with '…' when the title is longer. A word longer than a line breaks."""
    out, line = [], ''
    for written in str(text).split():
        word = written
        while len(word) > width:
            if line:
                out.append(line)
                line = ''
            out.append(word[:width])
            word = word[width:]
        if not word:
            continue
        if not line:
            line = word
        elif len(line) + 1 + len(word) <= width:
            line += ' ' + word
        else:
            out.append(line)
            line = word
    if line:
        out.append(line)
    if len(out) > lines:
        last = ' '.join(out[lines - 1 :])
        out = [*out[: lines - 1], last[: width - 1].rstrip() + '…']
    return tuple(out) or ('',)


# ---- the result ------------------------------------------------------------------------------------


@dataclass(frozen=True)
class Box:
    """A rectangle: its top left corner, its width and its height."""

    x: float
    y: float
    width: float
    height: float

    @property
    def right(self):
        return self.x + self.width

    @property
    def bottom(self):
        return self.y + self.height

    def overlaps(self, other):
        """Whether the insides of two boxes meet (boxes that only touch do not)."""
        return (
            self.x < other.right and other.x < self.right and self.y < other.bottom and other.y < self.bottom
        )

    def contains(self, other):
        """Whether `other` lies inside this box (its border included)."""
        return (
            self.x <= other.x
            and other.right <= self.right
            and self.y <= other.y
            and other.bottom <= self.bottom
        )


@dataclass(frozen=True)
class Stock:
    """A stock row or a meter of a card: its key and name in the picture, its kind (`stock` or
    `tally`), its box, the text that it shows, the flows of its pipes that are not drawn, and the tag
    of its symbol (`Tag`, D-53) or None."""

    key: str
    name: str
    kind: str
    box: Box
    text: str
    flows: tuple = ()
    tag: Tag | None = None


@dataclass(frozen=True)
class Math:
    """A typeset node (`typeset.Equation`) with its top left corner at (x, y), and its box."""

    equation: object
    x: float
    y: float
    box: Box


@dataclass(frozen=True)
class Tag:
    """The symbol of a stock row or a meter (`panels.tags`, D-53): its text, its box at the right end
    of the row, and its typeset symbol inside the box."""

    text: str
    box: Box
    math: Math


@dataclass(frozen=True)
class More:
    """The "+n" row of a card: the keys and names of the stocks that it stands for (`hidden` more that
    the picture does not name), its box and its text."""

    keys: tuple
    names: tuple
    hidden: int
    box: Box
    text: str


@dataclass(frozen=True)
class Trigger:
    """A row of the events of a card (`[triggers]`, D-56): its kind (`count`, `name`, `rule`, or `more`
    for the "+n more" row), the events that it stands for (`card.event`), its box, the lines of its text
    (each `TRIGGER_LINE` high), the baseline of its first line, and for each line the number of its
    first characters that are of the event's name, which the SVG draws in bold."""

    kind: str
    events: tuple
    box: Box
    lines: tuple
    text_at: tuple
    strong: tuple = ()


@dataclass(frozen=True)
class EventLine:
    """The full line of an event of a card, for the card's tooltip (D-56): the event (`card.event`), its
    name and its line in words, its text (None without one) and its condition as the file writes it
    (None without one)."""

    event: str
    name: str
    full: str
    label: str | None = None
    rule: str | None = None


@dataclass(frozen=True)
class Pipe:
    """A pipe of a card: its keys and flows in the picture, its ends (stock keys, None for the
    outside), its label (the number of its flows when it has several), its points from its start to
    its end, the place of its valve, the place of its source or sink circle (None between two stocks),
    and the labels of its flows, which its tooltip shows (D-59)."""

    keys: tuple
    flows: tuple
    source: str | None
    target: str | None
    label: str
    points: tuple
    valve: tuple
    cloud: tuple | None
    words: str = ''


@dataclass(frozen=True)
class State:
    """A state of a machine: its name (None for "any state"), its box, and whether the var starts in
    it."""

    name: str | None
    box: Box
    initial: bool


@dataclass(frozen=True)
class Transition:
    """An arrow of a machine: its states (`source` None: from any state), its events, the cards that
    cause it, its number in the key of the machine, its points and the centre of its number."""

    source: str | None
    target: str
    events: tuple
    by: tuple
    number: int
    points: tuple
    badge: tuple


@dataclass(frozen=True)
class Machine:
    """A state machine: its var and name, its card, where it goes (`inside` or `beside`), its box, the
    baseline of its name, its states, its transitions, and the lines of its key, each (number, text,
    (x, y))."""

    var: str
    name: str
    card: str
    place: str
    box: Box
    title_at: tuple
    states: tuple
    transitions: tuple
    key: tuple


@dataclass(frozen=True)
class Card:
    """A card: what the picture says of it, the lines of its title, and its box. `column` is its layer,
    from 1, as `place.column` counts; `sub` is its sub-column in a layer split in several, from 0;
    `row` is its place among the cards of its layer, from 1, top to bottom and sub-column by
    sub-column. Then its icon's box, the baseline of its first title line, its stock rows, its meters,
    its "+n" row, its pipes and the machines inside it; the rows of its events (`triggers`, D-56), and
    the full line of each of its events for its tooltip (`events`) at every level of `[triggers]`."""

    id: str
    title: str
    lines: tuple
    role: str | None
    icon: str | None
    template: str | None
    copies: int
    actor: bool
    box: Box
    column: int
    sub: int
    row: int
    icon_box: Box
    title_at: tuple
    stocks: tuple
    meters: tuple
    more: More | None
    pipes: tuple
    machines: tuple
    starts: bool = False
    file: str | None = None
    triggers: tuple = ()
    events: tuple = ()


@dataclass(frozen=True)
class Route:
    """An arrow: its cards, its kind, its count and values, and its points from its true start to its
    true end. `back` is True for an arrow that goes from right to left. `how` holds the words of a
    "changes" arrow's relations (sets, adds, takes, shares). `bundle` is the index of its bundle in
    `Layout.bundles`, or None for an arrow that shares no trunk (D-51)."""

    source: str
    target: str
    kind: str
    count: int
    values: tuple
    points: tuple
    back: bool
    how: tuple = ()
    bundle: int | None = None


@dataclass(frozen=True)
class Bundle:
    """Two or more arrows of one kind from one card toward one side, which share a trunk (D-51): the
    card, the kind, the side of the card (`right` or `left`), the cards at the other ends in the order
    of the routes, and the points where a branch leaves the trunk inside its span (`junctions`). The
    routes of a bundle share their start and the part of their line from it; after they split, they
    do not meet again."""

    source: str
    kind: str
    side: str
    targets: tuple
    junctions: tuple


@dataclass(frozen=True)
class Frame:
    """The frame of a group: its label, its members, its box and the baseline of its label."""

    label: str
    members: tuple
    box: Box
    label_at: tuple


@dataclass(frozen=True)
class Legend:
    """The legend: its box, and each mark (`MARKS`) with its words and the box of its sample and
    words. `hidden` holds the kinds of arrows that the picture has but does not draw (`[arrows]`,
    D-51): their items say so and have no sample."""

    box: Box
    items: tuple
    hidden: tuple = ()


@dataclass(frozen=True)
class Run:
    """A run of text of a panel: its text, the x of its start and the y of its baseline, its size, its
    look (`plain`, `strong`, `muted`, `link`, `heading` or `number`), its box by the estimate of
    `text_width`, and the address of a link (an `http` or `https` URL) or None."""

    text: str
    x: float
    y: float
    size: float
    look: str
    box: Box
    url: str | None = None


@dataclass(frozen=True)
class Mark:
    """A mark: the number of its entry of the References list and the entry's kind
    (`references.KINDS`), whose colour it has (`references.COLOUR_KIND`)."""

    number: int
    kind: str


@dataclass(frozen=True)
class Marks:
    """The marks of a place, as a superscript after its text: the marks, the y of their baseline (raised
    `MARK_RISE` above the text's), their size, the x of each part of their text ((text, x, mark or None
    for a comma), …), and their box."""

    marks: tuple
    y: float
    size: float
    parts: tuple
    box: Box

    def text(self):
        return ''.join(text for text, _, _ in self.parts)


@dataclass(frozen=True)
class Block:
    """The head of a block of the Equations panel: the index of the block in `panels.equations`, its
    name, its title, the titles of its members (more than one for a template's block), its box and its
    items (`Run`) in reading order."""

    index: int
    name: str
    title: str
    members: tuple
    box: Box
    items: tuple


@dataclass(frozen=True)
class EquationLine:
    """A line of a block of the Equations panel: the indexes of its block and of the line, its kind and
    part, its LaTeX and the names of its records (for the SVG's `data-latex` and `data-record`; never
    shown), its box and its items (`Math`, `Run`, `Marks`) in reading order."""

    block: int
    index: int
    kind: str
    part: str | None
    latex: str
    records: tuple
    box: Box
    items: tuple


@dataclass(frozen=True)
class Cell:
    """A cell of a row of the Symbols table: its column (`COLUMNS`), its box and its items."""

    column: str
    box: Box
    items: tuple


@dataclass(frozen=True)
class SymbolRow:
    """A row of the Symbols table: its key (None for the head of the table), the text of its symbol,
    its meaning, the names of its records (never shown), its box and its cells, left to right."""

    key: str | None
    symbol: str
    meaning: str
    records: tuple
    box: Box
    cells: tuple


@dataclass(frozen=True)
class Entry:
    """An entry of the References list: its number and kind, its hover text, the IDs and names of its
    records (never shown), its link (an `http` or `https` URL) or None, its box and its items (`Run`):
    the number, then the label, the text and the link text, wrapped."""

    number: int
    kind: str
    hover: str
    record: tuple
    url: str | None
    box: Box
    items: tuple


@dataclass(frozen=True)
class Note:
    """A row of a panel that is only text: "No equations." of a block without lines, or the note on a
    chosen range. Its kind (`empty` or `note`), its box and its items (`Run`)."""

    kind: str
    box: Box
    items: tuple


@dataclass(frozen=True)
class Panel:
    """A panel under the map (D-53): its kind (`equations`, `symbols`, `references`, or `note` for the
    note on a chosen range), its heading (`Run`, None for the note), its box and its rows from the top:
    the heads of blocks and their lines, the rows of the Symbols table (its head first), the entries
    of the References list, or the note."""

    kind: str
    heading: Run | None
    box: Box
    rows: tuple


@dataclass(frozen=True)
class Layout:
    """The whole picture: its size, the baseline of its title, the cards, the machines beside their
    cards, the arrows, the group frames, the legend, the lines of the subtitle (`subtitle`), the
    bundles of arrows (`bundles`, D-51), and the panels under the legend (`panels`, D-53)."""

    width: float
    height: float
    title_at: tuple
    cards: tuple
    machines: tuple
    routes: tuple
    frames: tuple
    legend: Legend
    subtitle: tuple = ()
    bundles: tuple = ()
    panels: tuple = ()


def subtitle(picture):
    """The lines of the subtitle of a picture (D-59), from its `facts`: its name and its run with its
    label (and its options, when the label does not name them), or the number of runs that it joins;
    then how long a run lasts, and the things that `[layout] hide` leaves out. A picture without facts
    has its name only."""
    facts = picture.get('facts') or {}
    run = facts.get('run')
    first = str(picture.get('name') or '')
    if run:
        first += f' · run {run["name"]}: {run["label"]}'
        options = [option for option in run.get('options') or () if option not in run['label']]
        if options:
            first += f' ({", ".join(options)})'
    elif int(facts.get('runs') or 0) > 1:
        first += f' · all {facts["runs"]} runs'
    second = []
    if facts.get('horizon'):
        second.append(f'a run lasts {facts["horizon"]}')
    if facts.get('hidden'):
        second.append(f'not drawn: {", ".join(facts["hidden"])}')
    return (first, ' · '.join(second)) if second else (first,)


# ---- the collapse: a card and its machines, measured ---------------------------------------------


def _merged(pipes):
    """The pipes of a card, one for each pair of ends, in the order of their ends (the outside last)."""
    found = {}
    for pipe in pipes:
        key = (pipe['from'], pipe['to'])
        found.setdefault(key, []).append(pipe)
    out = []
    for (source, target), group in sorted(
        found.items(),
        key=lambda item: (item[0][0] is None, item[0][0] or '', item[0][1] is None, item[0][1] or ''),
    ):
        flows = tuple(dict.fromkeys(flow for pipe in group for flow in pipe['flows']))
        labels = tuple(dict.fromkeys(pipe['label'] for pipe in group if pipe['label']))
        out.append(
            {
                'keys': tuple(pipe['key'] for pipe in group),
                'flows': flows,
                'from': source,
                'to': target,
                'label': ', '.join(labels),
            }
        )
    return out


def lane(y, odd):
    """`y` on the lines of its column: a whole number in an even column, a half in an odd one. The ends
    of the arrows on the two sides of a gap are then never at one height, so no two arrows share a
    stretch of line in the gap."""
    return math.floor(y) + 0.5 if odd else float(math.floor(y + 0.5))


def _event_name(event, by):
    """An event in the key of a machine: `card.event` without its card when the key names the card
    (`by`), else as it is."""
    card, dot, name = event.partition('.')
    return name if dot and card in by else event


def _spread(top, height, count):
    """`count` points spread evenly inside a length, from `top`."""
    return [half(top + (k + 1) * height / (count + 1)) for k in range(count)]


def _tracks(intervals, fewest=False):
    """{index: track} of closed intervals [(low, high, index)]: each interval goes on the first track
    where it meets no interval already there (greedy interval colouring). The intervals go in the order
    of their lengths, the shorter first; with `fewest`, in the order of their low ends, which needs only
    as many tracks as the most intervals that meet at one point (D-50)."""
    if fewest:
        order = sorted(intervals, key=lambda item: (item[0], item[1], item[2]))
    else:
        order = sorted(intervals, key=lambda item: (item[1] - item[0], item[0], item[1], item[2]))
    tracks, out = [], {}
    for low, high, index in order:
        for number, held in enumerate(tracks):
            if all(high < start or end < low for start, end in held):
                held.append((low, high))
                out[index] = number
                break
        else:
            tracks.append([(low, high)])
            out[index] = len(tracks) - 1
    return out


class _Machine:
    """A state machine, measured: its edges (one for each pair of states, with every event of the
    pair), the nodes in their order (the "any state" node first, when an edge comes from it), the
    tracks of its edges on each side, its least width and its height."""

    def __init__(self, machine, card, titles):
        self.var, self.name, self.card = machine['var'], machine['name'], card
        states = list(machine['states'])
        edges = {}
        for transition in machine['transitions']:
            target = transition['to']
            sources = [None] if transition['from'] is None else transition['from']
            for source in sources:
                if source == target or target not in states or (source is not None and source not in states):
                    continue
                events, by = edges.setdefault((source, target), ([], []))
                if transition['event'] not in events:
                    events.append(transition['event'])
                if transition['by'] not in by:
                    by.append(transition['by'])
        self.nodes = ([None] if any(source is None for source, _ in edges) else []) + states
        self.initial = machine.get('initial')
        index = {node: k for k, node in enumerate(self.nodes)}
        self.edges = [
            (source, target, tuple(events), tuple(by))
            for (source, target), (events, by) in sorted(
                edges.items(), key=lambda e: (index[e[0][0]], index[e[0][1]])
            )
        ]
        self.index = index
        # Each edge goes down on the right of the states, or up on their left.
        self.side = [
            'right' if index[source] < index[target] else 'left' for source, target, _, _ in self.edges
        ]
        self.track = {}
        for side in ('left', 'right'):
            spans = [
                (min(index[s], index[t]), max(index[s], index[t]), k)
                for k, (s, t, _, _) in enumerate(self.edges)
                if self.side[k] == side
            ]
            self.track.update(_tracks(spans))
        self.counts = {
            side: 1 + max((self.track[k] for k in range(len(self.edges)) if self.side[k] == side), default=-1)
            for side in ('left', 'right')
        }
        # The ends of the edges on each side of each node, in the order of their other node.
        self.ends = {}
        for k, (source, target, _, _) in enumerate(self.edges):
            for node, other in ((source, target), (target, source)):
                self.ends.setdefault((node, self.side[k]), []).append((index[other], k))
        self.heights = [
            max(PILL, 4 * (1 + max(len(self.ends.get((node, side), ())) for side in ('left', 'right'))))
            for node in self.nodes
        ]
        names = [('any state' if node is None else node) for node in self.nodes]
        self.pill = max(text_width(name, SMALL_SIZE) + 22 for name in names) if names else 40.0
        self.key = [
            (
                k + 1,
                f'{", ".join(_event_name(e, by) for e in events)}, by {", ".join(titles.get(b, b) for b in by)}',
            )
            for k, (_, _, events, by) in enumerate(self.edges)
        ]
        self.diagram = self.pill + sum(self._side_width(side) for side in ('left', 'right'))
        inner = max(
            self.diagram,
            text_width(self.name, SMALL_SIZE),
            max((text_width(f'{n}  {text}', SMALL_SIZE) for n, text in self.key), default=0),
        )
        self.min_width = half(2 * MPAD + inner)
        # The options that set the start of the state (D-59): lines of the key with no number, wrapped to
        # the width of the rest of the machine, so that they never make the machine wider.
        starts = [f'{item["option"]} ({item["state"]})' for item in machine.get('starts_by') or ()]
        if starts:
            room = max(16, int((inner - 4) / (EM * SMALL_SIZE)))
            text = f'Options set the start: {", ".join(starts)}'
            self.key.extend(('', line) for line in wrap(text, room, START_LINES))
        self.height = half(
            MPAD
            + MHEAD
            + sum(self.heights)
            + PILL_GAP * max(0, len(self.nodes) - 1)
            + 6
            + KEY_LINE * len(self.key)
            + MPAD
        )

    def _side_width(self, side):
        count = self.counts[side]
        return MGAP + (count - 1) * MTRACK + BADGE + 2 if count else 0.0

    def place(self, x, y, width, place):
        """The machine at (x, y), `width` wide (at least `min_width`): a `Machine`."""
        left = half(x + (width - self.diagram) / 2 + self._side_width('left'))
        right = half(left + self.pill)
        top = y + MPAD + MHEAD
        boxes = []
        for height in self.heights:
            boxes.append(Box(left, half(top), half(right - left), height))
            top += height + PILL_GAP
        states = tuple(
            State(node, box, node is not None and node == self.initial)
            for node, box in zip(self.nodes, boxes)
        )
        port = {}
        for (node, _), ends in self.ends.items():
            box = boxes[self.index[node]]
            ordered = sorted(ends)
            for (_, k), at in zip(ordered, _spread(box.y, box.height, len(ordered))):
                port[(k, node)] = at
        transitions = []
        for k, (source, target, events, by) in enumerate(self.edges):
            side = self.side[k]
            edge = left if side == 'left' else right
            step = -MTRACK if side == 'left' else MTRACK
            tx = half(edge + (-MGAP if side == 'left' else MGAP) + step * self.track[k])
            y0, y1 = port[(k, source)], port[(k, target)]
            points = ((edge, y0), (tx, y0), (tx, y1), (edge, y1))
            transitions.append(
                Transition(source, target, events, by, k + 1, points, (tx, half((y0 + y1) / 2)))
            )
        key_top = top - PILL_GAP + 6
        key = tuple(
            (number, text, (half(x + MPAD), half(key_top + (n + 1) * KEY_LINE - 3)))
            for n, (number, text) in enumerate(self.key)
        )
        return Machine(
            self.var,
            self.name,
            self.card,
            place,
            Box(x, y, width, self.height),
            (half(x + MPAD), half(y + MPAD + 9)),
            states,
            tuple(transitions),
            key,
        )


def symbol_parts(symbol):
    """(base, prime, subscript) of a symbol of the panels (`{base, prime, sub, …}`)."""
    return symbol['base'], symbol['prime'], symbol['sub']


def tags_of(picture):
    """{stock key: (the text of its symbol, its parts)} of the stock rows and meters that carry a tag
    (`panels.tags`, D-53): none without panels. The parts are those of the key's row of the Symbols
    table, which every tag has; a tag without one is its text as a base."""
    found = picture.get('panels') or {}
    rows = {row['key']: row for row in found.get('symbols') or ()}
    out = {}
    for key, text in (found.get('tags') or {}).items():
        row = rows.get(key)
        out[key] = (text, symbol_parts(row['symbol']) if row else (text, False, None))
    return out


def limits(picture):
    """What the picture's `settings` choose for the collapse and the columns (D-52), with the default of
    each that a picture without them takes: the most stock rows of a card (`stocks`, `MAX_STOCKS`), the
    most cards of a column (`cards_per_column`, `MAX_COLUMN`) and the least width of a card
    (`card_width`, `CARD_MIN`)."""
    settings = picture.get('settings') or {}
    width = settings.get('card_width')
    return {
        'stocks': int(settings.get('stocks') or MAX_STOCKS),
        'cards_per_column': int(settings.get('cards_per_column') or MAX_COLUMN),
        'card_width': float(width) if width is not None else CARD_MIN,
    }


class _Card:
    """A card, measured: the lines of its title, its collapsed stocks and pipes, its machines inside
    and beside, its least width and the height of what it holds. `limits` are the picture's
    (`limits`)."""

    def __init__(self, card, titles, limits, tags=None):
        self.card = card
        self.id = card['id']
        self.lines = wrap(card['title'])
        stocks = list(card['stocks'])
        # The symbols of the stock rows and meters that carry a tag (D-53): {key: (text, parts)} of the
        # picture's tags, typeset.
        given = {stock['key']: tags[stock['key']] for stock in stocks if tags and stock['key'] in tags}
        self.tag_text = {key: text for key, (text, _) in given.items()}
        self.tags = {key: _tag_math(parts) for key, (_, parts) in given.items()}
        pipes = _merged(card['pipes'])
        most = limits['stocks']
        order = card.get('stock_order')
        if order is None:
            touches = {stock['key']: 0 for stock in stocks}
            for pipe in pipes:
                for end in (pipe['from'], pipe['to']):
                    if end in touches:
                        touches[end] += 1
            rank = sorted(
                range(len(stocks)),
                key=lambda k: (stocks[k]['kind'] == 'tally', -touches[stocks[k]['key']], k),
            )
            shown = sorted(rank[:most])
        else:
            # The rows of `[stocks]`, in its order (D-52).
            index = {stock['key']: k for k, stock in enumerate(stocks)}
            shown = list(dict.fromkeys(index[key] for key in order if key in index))[:most]
        self.rows = [stocks[k] for k in shown if stocks[k]['kind'] != 'tally']
        self.meters = [stocks[k] for k in shown if stocks[k]['kind'] == 'tally']
        taken = set(shown)
        self.hidden = [stock for k, stock in enumerate(stocks) if k not in taken]
        self.extra = int(card.get('hidden_stocks') or 0)
        row_of = {stock['key']: k for k, stock in enumerate(self.rows)}
        self.inner, self.outer, self.untold = [], [], {}
        for pipe in pipes:
            source, target = pipe['from'], pipe['to']
            if source in row_of and target in row_of:
                self.inner.append(pipe)
            elif (source is None and target in row_of) or (target is None and source in row_of):
                self.outer.append(pipe)
            else:
                for end in (source, target):
                    if end is not None:
                        self.untold.setdefault(end, []).extend(pipe['flows'])
        self.row_of = row_of
        self.lane = _tracks(
            [
                (min(row_of[p['from']], row_of[p['to']]), max(row_of[p['from']], row_of[p['to']]), k)
                for k, p in enumerate(self.inner)
            ]
        )
        self.lanes = 1 + max(self.lane.values(), default=-1)
        self.machines, self.beside = [], []
        for machine in card['machines']:
            if machine['place'] == 'hidden':
                continue
            found = _Machine(machine, self.id, titles)
            small = (
                len(machine['states']) <= INSIDE_STATES and len(machine['transitions']) <= INSIDE_TRANSITIONS
            )
            if machine['place'] == 'inside' and small:
                self.machines.append(found)
            else:
                self.beside.append(found)
        self.triggers = card.get('triggers') or None
        # The width: the title and its badges, the stock rows, the meters, the machines inside, the rows
        # of the events.
        self.badges = self._badges()
        header = PAD + ICON + 6 + max(bold_width(line, TITLE_SIZE) for line in self.lines) + self.badges + PAD
        tank = max(
            [
                min(TANK_MAX, max(TANK_MIN, text_width(stock['name'], TEXT_SIZE) + 14)) + self.tag_room(stock)
                for stock in self.rows
            ],
            default=0.0,
        )
        rows = PAD + self.lanes * LANE + (4 if self.lanes else 0) + tank + (STUB if self.outer else 0) + PAD
        # Each meter as wide as its gauge and its name.
        self.wide = [
            up(METER_TEXT + text_width(stock['name'], SMALL_SIZE) + METER_END + self.tag_room(stock))
            for stock in self.meters
        ]
        meters = PAD + min(METER_MAX, max(self.wide)) + PAD if self.meters else 0.0
        # The machines inside go one to a row, or two to a row when there are more than two.
        self.across = 1 if len(self.machines) <= 2 else 2
        self.grid = [self.machines[k : k + self.across] for k in range(0, len(self.machines), self.across)]
        self.cell = max((m.min_width for m in self.machines), default=0.0)
        machines = 2 * PAD + self.across * self.cell + (self.across - 1) * PAD if self.machines else 0.0
        self.min_width = half(
            max(limits['card_width'], header, rows, meters, machines, self._trigger_width())
        )
        # The card grows until two meters with other names show other texts: at the latest when each
        # shows its whole name.
        inner = self.min_width - 2 * PAD
        while self.meters and _alike(self.meters, self.meter_texts(inner)) and inner < max(self.wide):
            inner = up(inner + EM * SMALL_SIZE)
        self.min_width = max(self.min_width, inner + 2 * PAD)
        # The texts of the meters in the narrowest card, which no two meters share.
        self.texts = self.meter_texts(self.min_width - 2 * PAD)
        self.header = half(PAD + max(ICON, len(self.lines) * LINE) + 6)
        height = self.header
        if self.rows:
            height += len(self.rows) * ROW + (len(self.rows) - 1) * ROW_GAP + ROW_GAP
        if self.hidden or self.extra:
            height += MORE
        for line in self.grid:
            height += 6 + max(machine.height for machine in line)
        # What the card holds, apart from its rows of meters.
        self.base = height + PAD

    def content(self, width):
        """The height of what the card holds when it is `width` wide, with its rows of meters and the rows
        of its events at that width."""
        rows = len(self.meter_rows(width - 2 * PAD)) if self.meters else 0
        found = self.trigger_rows(width - 2 * PAD)
        events = (
            TRIGGER_TOP + sum(len(row[2]) * TRIGGER_LINE for row in found) + TRIGGER_GAP * (len(found) - 1)
        )
        return half(self.base + rows * (METER + ROW_GAP) + (events if found else 0.0))

    def _trigger_width(self):
        """The least width that the rows of the events need (D-56): `RULES_WIDTH` at `rules`; at `count`
        and `names`, the widest text of a row, up to that width."""
        if self.triggers is None:
            return 0.0
        level = self.triggers['level']
        if level == 'rules':
            return RULES_WIDTH
        texts = [self._count_text()] if level == 'count' else []
        if level == 'names':
            texts = [event['text'] for event in self.triggers['events'] if event['text'] is not None]
        if not texts:
            return 0.0
        widest = max(text_width(text, SMALL_SIZE) for text in texts)
        return min(RULES_WIDTH, up(PAD + TRIGGER_MARK + widest + PAD))

    def _count_text(self):
        count = len(self.triggers['events'])
        return f'{count} event' if count == 1 else f'{count} events'

    def trigger_rows(self, inner):
        """The rows of the events in a card whose inside is `inner` wide (D-56), from the top: (kind,
        events, lines, strong) of each `Trigger`. A line of a row is at most `inner - TRIGGER_MARK` wide.
        At `rules` the line of an event takes at most `lines` rows, and its last row ends with '…' when
        the line does not fit (`text.shorten`); at `names` a name takes one row."""
        found = self.triggers
        if found is None or found['level'] == 'hover':
            return []
        width = inner - TRIGGER_MARK

        def measure(text):
            return text_width(text, SMALL_SIZE)

        events = found['events']
        if found['level'] == 'count':
            lines, _ = fit_lines(self._count_text(), width, 1, measure)
            return [('count', tuple(event['event'] for event in events), tuple(lines), ())]
        rule = found['level'] == 'rules'
        out = []
        for event in events:
            if event['text'] is None:
                continue
            fits = measure
            if rule:
                # The event's name is bold: a line holds at most all of it.
                bold = max(0.0, bold_width(event['name'], SMALL_SIZE) - text_width(event['name'], SMALL_SIZE))

                def fits(text, bold=bold):
                    return text_width(text, SMALL_SIZE) + bold

            lines, _ = fit_lines(event['text'], width, int(found['lines']) if rule else 1, fits)
            strong = _strong(lines, event['name']) if rule else ()
            out.append(('rule' if rule else 'name', (event['event'],), tuple(lines), strong))
        if found['more']:
            rest = tuple(event['event'] for event in events if event['text'] is None)
            lines, _ = fit_lines(f'+{found["more"]} more', width, 1, measure)
            out.append(('more', rest, tuple(lines), ()))
        return out

    def event_lines(self):
        """The full line of each event of the card, for its tooltip (`EventLine`), at every level."""
        if self.triggers is None:
            return ()
        return tuple(
            EventLine(event['event'], event['name'], event['full'], event.get('label'), event.get('rule'))
            for event in self.triggers['events']
        )

    def meter_widths(self, inner):
        """The width of each meter in a card whose inside is `inner` wide."""
        return [min(wide, inner) for wide in self.wide]

    def meter_texts(self, inner):
        """The text of each meter in a card whose inside is `inner` wide: its name, or its start and
        '…'. A meter with a tag keeps the room of its tag."""
        return [
            shorten(stock['name'], SMALL_SIZE, width - METER_TEXT - METER_END - self.tag_room(stock))
            for stock, width in zip(self.meters, self.meter_widths(inner))
        ]

    def tag_room(self, stock):
        """The width that the tag of a stock row or a meter takes from its text: its box and the gap
        before it, or 0 without a tag."""
        found = self.tags.get(stock['key'])
        return 0.0 if found is None else up(found.width + 2 * TAG_PAD) + TAG_INSET + TAG_GAP

    def tag(self, stock, box):
        """The tag of a stock row or a meter whose box is `box`, at its right end, or None."""
        found = self.tags.get(stock['key'])
        if found is None:
            return None
        width, height = up(found.width + 2 * TAG_PAD), up(found.height)
        tag = Box(half(box.right - TAG_INSET - width), half(box.y + (box.height - height) / 2), width, height)
        x, y = tag.x + TAG_PAD, tag.y
        return Tag(self.tag_text[stock['key']], tag, Math(found, x, y, Box(x, y, found.width, found.height)))

    def meter_rows(self, inner):
        """The meters of each row, by their index: each row as full as `inner` allows, in order."""
        rows, used = [], 0.0
        for k, width in enumerate(self.meter_widths(inner)):
            if rows and used + ROW_GAP + width <= inner:
                rows[-1].append(k)
                used += ROW_GAP + width
            else:
                rows.append([k])
                used = width
        return rows

    def _badges(self):
        """The width of the badges of the title: the number of copies, the mark of an actor and the mark
        of the thing that makes the start event (D-59)."""
        width = 0.0
        if int(self.card.get('copies') or 1) > 1:
            width += BADGE_GAP + text_width(f'×{self.card["copies"]}', SMALL_SIZE) + 8
        if self.card.get('actor'):
            width += BADGE_GAP + 10
        if self.card.get('starts'):
            width += BADGE_GAP + 10
        return width

    def place(self, x, y, width, height, column, sub, row):
        """The card at (x, y), `width` wide and `height` tall: a `Card`."""
        card = self.card
        top = y + self.header
        rows = []
        tank_x = half(x + PAD + self.lanes * LANE + (4 if self.lanes else 0))
        tank_right = half(x + width - PAD - (STUB if self.outer else 0))
        row_boxes = []
        for k in range(len(self.rows)):
            row_boxes.append(Box(tank_x, half(top + k * (ROW + ROW_GAP)), half(tank_right - tank_x), ROW))
        for stock, box in zip(self.rows, row_boxes):
            text = shorten(stock['name'], TEXT_SIZE, box.width - 12 - self.tag_room(stock))
            rows.append(
                Stock(
                    stock['key'],
                    stock['name'],
                    stock['kind'],
                    box,
                    text,
                    tuple(self.untold.get(stock['key'], ())),
                    self.tag(stock, box),
                )
            )
        if self.rows:
            top += len(self.rows) * (ROW + ROW_GAP)
        pipes = self._pipes(row_boxes, tank_x, tank_right)
        meters = []
        if self.meters:
            inner = width - 2 * PAD
            widths, texts = self.meter_widths(inner), self.meter_texts(inner)
            if _alike(self.meters, texts):
                texts = self.texts
            for line in self.meter_rows(inner):
                left = x + PAD
                for k in line:
                    stock = self.meters[k]
                    box = Box(half(left), half(top), widths[k], METER)
                    meters.append(
                        Stock(
                            stock['key'],
                            stock['name'],
                            stock['kind'],
                            box,
                            texts[k],
                            tuple(self.untold.get(stock['key'], ())),
                            self.tag(stock, box),
                        )
                    )
                    left += widths[k] + ROW_GAP
                top += METER + ROW_GAP
        more = None
        if self.hidden or self.extra:
            count = len(self.hidden) + self.extra
            more = More(
                tuple(stock['key'] for stock in self.hidden),
                tuple(stock['name'] for stock in self.hidden),
                self.extra,
                Box(half(x + PAD), half(top), half(width - 2 * PAD), MORE),
                f'+{count} more',
            )
            top += MORE
        machines = []
        each = half((width - 2 * PAD - (self.across - 1) * PAD) / self.across)
        for line in self.grid:
            top += 6
            for k, machine in enumerate(line):
                machines.append(machine.place(half(x + PAD + k * (each + PAD)), half(top), each, 'inside'))
            top += max(machine.height for machine in line)
        triggers = []
        found = self.trigger_rows(width - 2 * PAD)
        if found:
            top += TRIGGER_TOP
        for kind, events, lines, strong in found:
            box = Box(half(x + PAD), half(top), half(width - 2 * PAD), len(lines) * TRIGGER_LINE)
            text_at = (half(box.x + TRIGGER_MARK), half(box.y + TRIGGER_LINE - 3))
            triggers.append(Trigger(kind, events, box, lines, text_at, strong))
            top += box.height + TRIGGER_GAP
        return Card(
            id=self.id,
            title=card['title'],
            lines=self.lines,
            role=card.get('role'),
            icon=card.get('icon'),
            template=card.get('template'),
            copies=int(card.get('copies') or 1),
            actor=bool(card.get('actor')),
            box=Box(x, y, width, height),
            column=column,
            sub=sub,
            row=row,
            icon_box=Box(half(x + PAD), half(y + PAD), ICON, ICON),
            title_at=(half(x + PAD + ICON + 6), half(y + PAD + 11)),
            stocks=tuple(rows),
            meters=tuple(meters),
            more=more,
            pipes=tuple(pipes),
            machines=tuple(machines),
            starts=bool(card.get('starts')),
            file=card.get('file'),
            triggers=tuple(triggers),
            events=self.event_lines(),
        )

    def _pipes(self, rows, tank_x, tank_right):
        """The pipes that the card draws: between two stock rows on lanes to the left of the rows, and to
        or from the outside on the right of a row."""
        out = []
        # The ends of the pipes between rows, on the left side of each row, in the order of their other
        # row.
        ends = {}
        for k, pipe in enumerate(self.inner):
            a, b = self.row_of[pipe['from']], self.row_of[pipe['to']]
            ends.setdefault(a, []).append((b, k))
            ends.setdefault(b, []).append((a, k))
        port = {}
        for row, items in ends.items():
            box = rows[row]
            for (_, k), at in zip(sorted(items), _spread(box.y, box.height, len(items))):
                port.setdefault(k, {})[row] = at
        for k, pipe in enumerate(self.inner):
            a, b = self.row_of[pipe['from']], self.row_of[pipe['to']]
            at = half(tank_x - 4 - LANE / 2 - (self.lanes - 1 - self.lane[k]) * LANE)
            y0, y1 = port[k][a], port[k][b]
            points = ((tank_x, y0), (at, y0), (at, y1), (tank_x, y1))
            out.append(self._pipe(pipe, points, (at, half((y0 + y1) / 2)), None))
        sides = {}
        for pipe in self.outer:
            row = self.row_of[pipe['to'] if pipe['from'] is None else pipe['from']]
            sides.setdefault(row, []).append(pipe)
        for row, found in sorted(sides.items()):
            box = rows[row]
            items = sorted(found, key=lambda p: p['from'] is not None)
            for pipe, at in zip(items, _spread(box.y, box.height, len(items))):
                far = half(tank_right + STUB - 7)
                if pipe['from'] is None:
                    points = ((far, at), (tank_right, at))
                else:
                    points = ((tank_right, at), (far, at))
                out.append(
                    self._pipe(pipe, points, (half(tank_right + STUB / 2 - 3), at), (half(far + 3), at))
                )
        return out

    @staticmethod
    def _pipe(pipe, points, valve, cloud):
        count = len(pipe['flows'])
        return Pipe(
            pipe['keys'],
            pipe['flows'],
            pipe['from'],
            pipe['to'],
            str(count) if count > 1 else '',
            points,
            valve,
            cloud,
            pipe.get('label') or '',
        )


def _tag_math(parts):
    """The typeset symbol of a tag: `parts` are its (base, prime, subscript). (The import is here: the
    typesetter imports this module.)"""
    from . import notation, typeset

    return typeset.typeset(notation.Sym('tag'), lambda key: parts, size=TAG_SIZE)


def _strong(lines, name):
    """For each line of a text that starts with an event's name, the number of its first characters
    that are of the name: a long name goes on over the next line."""
    out, rest = [], name
    for line in lines:
        k = 0
        while k < min(len(line), len(rest)) and line[k] == rest[k]:
            k += 1
        out.append(k)
        rest = rest[k:].lstrip()
    return tuple(out)


def _alike(stocks, texts):
    """Whether two of `stocks` with other names show one text."""
    seen = {}
    return any(seen.setdefault(text, stock['name']) != stock['name'] for stock, text in zip(stocks, texts))


# ---- rank ------------------------------------------------------------------------------------------


def greedy_order(nodes, pairs):
    """The Eades–Lin–Smyth order of `nodes` (a list) under the directed `pairs` [(a, b)]: the sinks go
    to the end and the sources to the start while there are any; else the node whose out-degree most
    exceeds its in-degree goes to the start. Ties go in the order of `nodes`. A pair that goes back in
    this order is a back edge: the back edges break every cycle."""
    succ = {node: set() for node in nodes}
    pred = {node: set() for node in nodes}
    for a, b in pairs:
        if a != b:
            succ[a].add(b)
            pred[b].add(a)
    alive = dict.fromkeys(nodes)
    head, tail = [], []

    def remove(node):
        del alive[node]

    while alive:
        moved = True
        while moved:
            moved = False
            for node in list(alive):
                if not succ[node] & alive.keys():
                    tail.insert(0, node)
                    remove(node)
                    moved = True
                    break
        moved = True
        while moved:
            moved = False
            for node in list(alive):
                if not pred[node] & alive.keys():
                    head.append(node)
                    remove(node)
                    moved = True
                    break
        if alive:
            best = max(
                alive,
                key=lambda n: (len(succ[n] & alive.keys()) - len(pred[n] & alive.keys()), -nodes.index(n)),
            )
            head.append(best)
            remove(best)
    return head + tail


def drawn(picture, known):
    """The arrows that the picture draws between two cards of `known`: not from a card to itself, and
    not of a kind whose look is hidden (`settings.looks`, D-51)."""
    looks = (picture.get('settings') or {}).get('looks') or {}
    return [
        a
        for a in picture['arrows']
        if a['from'] in known
        and a['to'] in known
        and a['from'] != a['to']
        and looks.get(a['kind']) != 'hidden'
    ]


def layers(picture):
    """{card id: its layer, from 0}: `place.column` for a placed card; the longest path along the
    arrows of `RANKING` (changes, fires and moves) for the others, with the back edges of `greedy_order`
    reversed; the lower median layer of its neighbours for a card with only reads and follows; the last
    layer for a card with no arrow. Only the arrows that the picture draws count (`drawn`): a kind that
    `[arrows]` hides places no card, so hiding a kind closes up the columns."""
    ids = [card['id'] for card in picture['cards']]
    known = set(ids)
    pinned = {
        card['id']: int(card['place']['column']) - 1
        for card in picture['cards']
        if card.get('place') and card['place'].get('column') is not None
    }
    arrows = drawn(picture, known)
    pairs = list(dict.fromkeys((a['from'], a['to']) for a in arrows if a['kind'] in RANKING))
    order = greedy_order(ids, pairs)
    at = {node: k for k, node in enumerate(order)}
    pred = {node: [] for node in ids}
    for a, b in pairs:
        if at[a] < at[b]:
            pred[b].append(a)
        else:
            pred[a].append(b)
    ranked = {node for pair in pairs for node in pair}
    layer = {}
    for node in order:
        if node in pinned:
            layer[node] = pinned[node]
        elif node in ranked:
            layer[node] = max((layer[p] + 1 for p in pred[node]), default=0)
    neighbours = {node: [] for node in ids}
    for a in arrows:
        neighbours[a['from']].append(a['to'])
        neighbours[a['to']].append(a['from'])
    moved = True
    while moved:
        moved = False
        for node in ids:
            if node in layer or not neighbours[node]:
                continue
            found = sorted(layer[other] for other in neighbours[node] if other in layer)
            if found:
                layer[node] = found[(len(found) - 1) // 2]
                moved = True
    last = max(layer.values(), default=0)
    for node in ids:
        layer.setdefault(node, last)
    return layer


def back_pairs(picture):
    """The pairs (a, b) of the arrows of `RANKING` that `greedy_order` turns back: the edges that break
    the cycles of the ranking."""
    ids = [card['id'] for card in picture['cards']]
    known = set(ids)
    pairs = list(dict.fromkeys((a['from'], a['to']) for a in drawn(picture, known) if a['kind'] in RANKING))
    at = {node: k for k, node in enumerate(greedy_order(ids, pairs))}
    return [(a, b) for a, b in pairs if at[a] > at[b]]


# ---- the layout ------------------------------------------------------------------------------------


def crossing_count(segments):
    """The crossings of segments between two columns, each segment (its position on the left, its
    position on the right, its weight): two segments cross when one is above the other on the left and
    below it on the right, and the crossing weighs the product of their weights. Two segments that share
    an end do not cross. An exact count, in O(n log n), by a Fenwick tree over the positions on the
    right."""
    segments = sorted(segments)
    size = 1 + max((right for _, right, _ in segments), default=0)
    tree = [0.0] * (size + 1)

    def add(index, weight):
        index += 1
        while index <= size:
            tree[index] += weight
            index += index & -index

    def upto(index):
        index += 1
        found = 0.0
        while index > 0:
            found += tree[index]
            index -= index & -index
        return found

    total = placed = 0.0
    k = 0
    while k < len(segments):
        end = k
        while end < len(segments) and segments[end][0] == segments[k][0]:
            end += 1
        for _, right, weight in segments[k:end]:
            total += weight * (placed - upto(right))
        for _, right, weight in segments[k:end]:
            add(right, weight)
            placed += weight
        k = end
    return total


def gathered(order, group_of):
    """The items of a column in `order` with the members of each group (`group_of`: {item: group}) in
    one block, and the blocks in the order of the groups. First, for each group in its order, each item
    between its first and its last member that is not a member goes to the nearer end of the members:
    before the first when fewer members are before the item than after it, else after the last. The
    items that go to one end keep their order, and a block of another group goes whole, as its
    members are together. Then the blocks take the groups in their order, each where a block stands."""
    order = list(order)
    for group in sorted(set(group_of.values())):
        at = [k for k, item in enumerate(order) if group_of.get(item) == group]
        if not at:
            continue
        first, last = at[0], at[-1]
        seen, before, members, after = 0, [], [], []
        for item in order[first : last + 1]:
            if group_of.get(item) == group:
                members.append(item)
                seen += 1
            elif seen < len(at) - seen:
                before.append(item)
            else:
                after.append(item)
        order[first : last + 1] = before + members + after
    units = []
    for item in order:
        group = group_of.get(item)
        if group is not None and units and units[-1][0] == group:
            units[-1][1].append(item)
        else:
            units.append((group, [item]))
    blocks = {group: items for group, items in units if group is not None}
    turn = iter(sorted(blocks))
    return [item for group, items in units for item in (items if group is None else blocks[next(turn)])]


class _Work:
    """The state of one layout while it is made."""

    def __init__(self, picture):
        if picture.get('direction', 'left-to-right') != 'left-to-right':
            raise ValueError(f'{picture["direction"]} is not a direction; the one direction is left-to-right')
        self.picture = picture
        self.cards = list(picture['cards'])
        self.ids = [card['id'] for card in self.cards]
        self.card_index = {card_id: k for k, card_id in enumerate(self.ids)}
        titles = {card['id']: card['title'] for card in self.cards}
        self.limits = limits(picture)
        tags = tags_of(picture)
        self.measured = {card['id']: _Card(card, titles, self.limits, tags) for card in self.cards}
        known = set(self.ids)
        joining = [
            arrow
            for arrow in picture['arrows']
            if arrow['from'] in known and arrow['to'] in known and arrow['from'] != arrow['to']
        ]
        # A kind whose look is hidden (`[arrows]`, D-51) draws no arrow; the legend names it.
        looks = (picture.get('settings') or {}).get('looks') or {}
        self.arrows = [arrow for arrow in joining if looks.get(arrow['kind']) != 'hidden']
        self.hidden_kinds = tuple(
            kind for kind in KINDS if looks.get(kind) == 'hidden' and any(a['kind'] == kind for a in joining)
        )
        self.groups = []
        member_of = {}
        for group in picture.get('groups', ()):
            members = [m for m in group['members'] if m in known and m not in member_of]
            if members:
                for member in members:
                    member_of[member] = len(self.groups)
                self.groups.append((group['label'], members))
        self.member_of = member_of

    # ---- columns ------------------------------------------------------------------------------

    def columns(self):
        """The columns: each (layer, sub-column), left to right, with its cards; and for each card, its
        column. A layer of more than `cards_per_column` cards (`limits`) splits into the fewest
        sub-columns that hold it, each of at most `size` cards. `first_row` gives the number of cards in
        the sub-columns before each one of its layer."""
        layer = layers(self.picture)
        self.layer = layer
        by_layer = {}
        for card_id in self.ids:
            by_layer.setdefault(layer[card_id], []).append(card_id)
        self.columns_of = []
        self.column_of = {}
        self.first_row = {}
        most = self.limits['cards_per_column']
        for number in sorted(by_layer):
            cards = by_layer[number]
            count = math.ceil(len(cards) / most)
            size = math.ceil(len(cards) / count)
            subs = [[] for _ in range(count)]
            fixed = {}
            for card_id in cards:
                row = self._row(card_id)
                if row is not None:
                    fixed[card_id] = min(count - 1, (row - 1) // size)
            score = {}
            for arrow in self.arrows:
                for here, there in ((arrow['from'], arrow['to']), (arrow['to'], arrow['from'])):
                    if here in fixed or layer[here] != number:
                        continue
                    if layer[there] < number:
                        score[here] = score.get(here, 0) + 1
                    elif layer[there] > number:
                        score[here] = score.get(here, 0) - 1
            # A card with a row goes to the sub-column of its row; when that one is full, to the nearest
            # one with room, the earlier on a tie. The lower rows choose first.
            for card_id in sorted(fixed, key=lambda c: (self._row(c), self.card_index[c])):
                room = [k for k in range(count) if len(subs[k]) < size]
                subs[min(room, key=lambda k: (abs(k - fixed[card_id]), k))].append(card_id)
            free = sorted(
                (c for c in cards if c not in fixed), key=lambda c: (-score.get(c, 0), self.card_index[c])
            )
            for card_id in free:
                sub = next((k for k in range(count) if len(subs[k]) < size), count - 1)
                subs[sub].append(card_id)
            first = 0
            for sub, members in enumerate(subs):
                if not members:
                    continue
                self.first_row[(number, sub)] = first
                first += len(members)
                for card_id in members:
                    self.column_of[card_id] = len(self.columns_of)
                self.columns_of.append((number, sub, sorted(members, key=self.card_index.__getitem__)))

    def _row(self, card_id):
        place = self.measured[card_id].card.get('place') or {}
        row = place.get('row')
        return int(row) if row is not None else None

    # ---- slots and segments -------------------------------------------------------------------

    def gather(self):
        """The trees of the arrows: the arrows of one kind of the picture's `settings.bundle` from one
        card toward one side share one tree (a bundle, D-51); each other arrow is a tree of its own. The
        side is `right` for an arrow to a later column or to the same column, which uses the gap on the
        right of the column, and `left` for an arrow to an earlier column. Each tree is (card, kind,
        side, [arrow index]), in the order of its first arrow."""
        settings = self.picture.get('settings') or {}
        kinds = settings.get('bundle')
        bundled = set(BUNDLE if kinds is None else kinds)
        self.tree = []
        self.tree_of = []
        found = {}
        for k, arrow in enumerate(self.arrows):
            a, b = self.column_of[arrow['from']], self.column_of[arrow['to']]
            side = 'right' if a <= b else 'left'
            key = (arrow['from'], arrow['kind'], side) if arrow['kind'] in bundled else (k,)
            if key not in found:
                found[key] = len(self.tree)
                self.tree.append((arrow['from'], arrow['kind'], side, []))
            self.tree[found[key]][3].append(k)
            self.tree_of.append(found[key])

    def segments(self):
        """The slots of the trees that pass a column, and the segments between items of adjacent
        columns: each item is ('card', id), ('slot', tree index, column) or ('band', group index). A
        tree has one slot in each column that it passes, which each of its arrows that goes beyond the
        column shares, and each segment of a tree between two items counts once."""
        self.gather()
        self.chains = []
        self.slot_column = {}
        self.links = {}  # column -> [(left item, right item, weight)] between column and column + 1
        seen = set()
        for k, arrow in enumerate(self.arrows):
            tree = self.tree_of[k]
            a, b = self.column_of[arrow['from']], self.column_of[arrow['to']]
            low, high = min(a, b), max(a, b)
            left = arrow['from'] if a <= b else arrow['to']
            right = arrow['to'] if a <= b else arrow['from']
            chain = [('card', left)]
            for column in range(low + 1, high):
                item = ('slot', tree, column)
                chain.append(item)
                self.slot_column[item] = column
            chain.append(('card', right))
            self.chains.append((low, high, chain))
            if low == high:
                continue
            weight = WEIGHTS.get(arrow['kind'], 1.0)
            for column, (u, v) in enumerate(itertools.pairwise(chain), start=low):
                if (tree, column, u, v) in seen:
                    continue
                seen.add((tree, column, u, v))
                self.links.setdefault(column, []).append((u, v, weight))
        self.neighbours = {}
        for links in self.links.values():
            for u, v, weight in links:
                self.neighbours.setdefault((v, 'left'), []).append((u, weight))
                self.neighbours.setdefault((u, 'right'), []).append((v, weight))
        # The span of each group: its first and last column.
        self.spans = []
        for _, members in self.groups:
            found = [self.column_of[m] for m in members]
            self.spans.append((min(found), max(found)))

    # ---- order --------------------------------------------------------------------------------

    def items(self, column):
        """The items of a column: its cards, the slots of the arrows that pass it, and a band for each
        group that spans the column without a member in it."""
        cards = [('card', c) for c in self.columns_of[column][2]]
        slots = sorted(item for item in self.slot_column if self.slot_column[item] == column)
        bands = [
            ('band', g)
            for g, (low, high) in enumerate(self.spans)
            if low <= column <= high and not any(self.member_of.get(c[1]) == g for c in cards)
        ]
        return cards + slots + bands

    def arrange(self, column, keys):
        """The order of a column from a key of each item (smaller first): the members of each group
        together, the groups in their order, and each card with a row at its row among the cards of its
        column; then each group in one block again (`gathered`)."""
        items = list(keys)
        position = {item: k for k, item in enumerate(items)}
        group_of = {}
        for item in items:
            if item[0] == 'card' and item[1] in self.member_of:
                group_of[item] = self.member_of[item[1]]
            elif item[0] == 'band':
                group_of[item] = item[1]
        blocks = {}
        for item in items:
            if item in group_of:
                blocks.setdefault(group_of[item], []).append(item)
        loose = [item for item in items if item not in group_of]
        block_keys = {g: sum(keys[i] for i in members) / len(members) for g, members in blocks.items()}
        # The groups keep their order: their keys, sorted, go to the groups in that order.
        for g, value in zip(sorted(block_keys), sorted(block_keys.values())):
            block_keys[g] = value
        entries = [(keys[item], 0, position[item], [item]) for item in loose]
        for g, members in blocks.items():
            inside = sorted(members, key=lambda i: (keys[i], position[i]))
            entries.append((block_keys[g], 1, g, inside))
        order = [item for *_, members in sorted(entries, key=lambda e: e[:3]) for item in members]
        # A card with a row goes to its row among the cards of its sub-column.
        layer, sub, _ = self.columns_of[column]
        first = self.first_row[(layer, sub)]
        fixed = []
        for item in order:
            if item[0] == 'card':
                row = self._row(item[1])
                if row is not None:
                    fixed.append((max(0, row - 1 - first), self.card_index[item[1]], item))
        if fixed:
            for *_, item in fixed:
                order.remove(item)
            for want, _, item in sorted(fixed):
                seen, at = 0, len(order)
                for k, other in enumerate(order):
                    if seen == want:
                        at = k
                        break
                    if other[0] == 'card':
                        seen += 1
                order.insert(at, item)
        return gathered(order, group_of)

    def order(self):
        """The order of every column: the best of `SWEEPS` barycenter sweeps by the weighted count of
        crossings."""
        count = len(self.columns_of)
        start = {}
        for column in range(count):
            items = self.items(column)
            keys = {}
            for item in items:
                if item[0] == 'card':
                    keys[item] = float(self.card_index[item[1]])
                elif item[0] == 'slot':
                    keys[item] = float(len(self.ids) + item[1])
                else:
                    keys[item] = float(len(self.ids) + len(self.arrows) + item[1])
            start[column] = self.arrange(column, keys)
        orders = start
        best, best_cost = {c: list(o) for c, o in orders.items()}, self.crossings(orders)
        for sweep in range(SWEEPS):
            down = sweep % 2 == 0
            sequence = range(1, count) if down else range(count - 2, -1, -1)
            for column in sequence:
                reference = column - 1 if down else column + 1
                side = 'left' if down else 'right'
                at = {item: k for k, item in enumerate(orders[reference])}
                keys = {}
                current = orders[column]
                for k, item in enumerate(current):
                    found = [(at[u], w) for u, w in self.neighbours.get((item, side), ()) if u in at]
                    if item[0] == 'band':
                        # A band without members follows its group in the other column.
                        found = [
                            (at[other], 1.0)
                            for other in orders[reference]
                            if (other[0] == 'band' and other[1] == item[1])
                            or (other[0] == 'card' and self.member_of.get(other[1]) == item[1])
                        ]
                    if found:
                        keys[item] = sum(p * w for p, w in found) / sum(w for _, w in found)
                    else:
                        keys[item] = float(k)
                orders[column] = self.arrange(column, keys)
            cost = self.crossings(orders)
            if cost < best_cost:
                best, best_cost = {c: list(o) for c, o in orders.items()}, cost
        self.order_of = best
        self.cost = best_cost

    def crossings(self, orders):
        """The weighted crossings of the segments between every two adjacent columns
        (`crossing_count`)."""
        total = 0.0
        for column, links in self.links.items():
            left = {item: k for k, item in enumerate(orders[column])}
            right = {item: k for k, item in enumerate(orders[column + 1])}
            total += crossing_count([(left[u], right[v], w) for u, v, w in links])
        return total

    # ---- sizes --------------------------------------------------------------------------------

    def sides(self):
        """The ends of the arrows on each side of each card: {(card, 'left' | 'right'): {port: [(arrow
        index, end)]}}, where an end is 0 for the left end of the arrow's chain and -1 for its right
        end. The arrows of one tree share one port at its card, ('tree', tree index); each other end
        has a port of its own, ('end', arrow index, end)."""
        self.ends = {}
        for k, (low, high, chain) in enumerate(self.chains):
            tree = self.tree_of[k]
            shared = 0 if self.tree[tree][2] == 'right' else -1
            for which, item, side in (
                (0, chain[0], 'right'),
                (-1, chain[-1], 'right' if low == high else 'left'),
            ):
                port = ('tree', tree) if which == shared else ('end', k, which)
                ports = self.ends.setdefault((item[1], side), {})
                ports.setdefault(port, []).append((k, which))

    def heights(self):
        """The height of each card (what it holds in the width of its column, or what the ports of its
        arrows need) and of each item."""
        self.card_height = {}
        for card_id, measured in self.measured.items():
            need = max(len(self.ends.get((card_id, side), ())) for side in ('left', 'right'))
            width = self.column_width[self.column_of[card_id]]
            self.card_height[card_id] = half(max(measured.content(width), (need + 1) * PORT))
        self.item_height = {}
        for column in range(len(self.columns_of)):
            for item in self.order_of[column]:
                if item[0] == 'card':
                    measured = self.measured[item[1]]
                    height = self.card_height[item[1]]
                    for machine in measured.beside:
                        height += MACHINE_GAP + machine.height
                    self.item_height[item] = height
                elif item[0] == 'slot':
                    self.item_height[item] = SLOT
                else:
                    self.item_height[item] = 0.0

    def widths(self):
        """The width of each column: its widest card or machine beside a card."""
        self.column_width = []
        for _, _, cards in self.columns_of:
            width = 0.0
            for card_id in cards:
                measured = self.measured[card_id]
                width = max(width, measured.min_width, *(m.min_width for m in measured.beside))
            self.column_width.append(half(width))

    # ---- vertical positions -------------------------------------------------------------------

    def vertical(self):
        """The y of each item: the strips of the picture (a zone, then each group's band and a zone
        after it), and in each strip the items of each column, centred."""
        count = len(self.groups)
        strips = 2 * count + 1
        height = [0.0] * strips
        if count:
            for g in range(count - 1):
                height[2 * g + 2] = FRAME_GAP
        segments = []  # (column, first strip, last strip, items)
        bands = []  # (column, group, items)
        for column in range(len(self.columns_of)):
            order = self.order_of[column]
            relevant = [g for g, (low, high) in enumerate(self.spans) if low <= column <= high]
            cuts = []
            for g in relevant:
                found = [
                    k
                    for k, item in enumerate(order)
                    if (item[0] == 'card' and self.member_of.get(item[1]) == g) or item == ('band', g)
                ]
                cuts.append((min(found), max(found), g))
            cuts.sort()
            start, strip = 0, 0
            for at, last, g in cuts:
                first = max(at, start)
                segments.append((column, strip, max(strip, 2 * g), order[start:first]))
                bands.append((g, order[first : last + 1]))
                start, strip = last + 1, max(strip, 2 * g + 2)
            segments.append((column, strip, strips - 1, order[start:]))
        for g, items in bands:
            height[2 * g + 1] = max(height[2 * g + 1], self._stack(items) + FRAME_TOP + FRAME_PAD)
        # Each segment needs the height of its items in its strips: the shortfall goes to its last strip,
        # a zone, the segments that end first first.
        for _, first, last, items in sorted(segments, key=lambda item: (item[2], item[1], item[0])):
            value = self._stack(items) + (ITEM_GAP if items and count else 0.0)
            deficit = value - sum(height[first : last + 1])
            if deficit > 0:
                height[last] += deficit
        top = [MARGIN + TITLE_AREA + SUBTITLE_LINE * (len(subtitle(self.picture)) - 1)]
        for value in height:
            top.append(top[-1] + half(value))
        self.strip_top = top
        self.y = {}
        for _, first, last, items in segments:
            self._centre(items, top[first], top[last + 1])
        for g, items in bands:
            self._centre(items, top[2 * g + 1] + FRAME_TOP, top[2 * g + 2] - FRAME_PAD)
        self.bottom = top[-1]

    @staticmethod
    def _gap(a, b):
        """The space between two items of a column: less next to a slot, whose line is in its middle."""
        return SLOT_GAP if a[0] == 'slot' or b[0] == 'slot' else ITEM_GAP

    def _stack(self, items):
        shown = [item for item in items if self.item_height[item] > 0]
        return sum(self.item_height[item] for item in shown) + sum(
            self._gap(a, b) for a, b in itertools.pairwise(shown)
        )

    def _centre(self, items, top, bottom):
        y = half(top + (bottom - top - self._stack(items)) / 2)
        before = None
        for item in items:
            if self.item_height[item] <= 0:
                self.y[item] = y
                continue
            if before is not None:
                y = half(y + self.item_height[before] + self._gap(before, item))
            self.y[item] = y
            before = item

    def centre_y(self, item):
        if item[0] == 'card':
            return self.y[item] + self.card_height[item[1]] / 2
        return self.y[item] + self.item_height[item] / 2

    # ---- ports, tracks and horizontal positions -----------------------------------------------

    def ports(self):
        """The y of each end of each arrow: the ports spread on their side of their card, in the order
        of the y of the items at their other ends (the mean, for the port of a tree)."""
        self.port = {}
        for (card_id, _), ports in sorted(
            self.ends.items(), key=lambda item: (self.card_index[item[0][0]], item[0][1])
        ):
            here = ('card', card_id)
            entries = []
            for port, ends in ports.items():
                others = []
                for k, which in ends:
                    low, high, chain = self.chains[k]
                    if low == high:
                        other = chain[-1] if which == 0 else chain[0]
                    else:
                        other = chain[1] if which == 0 else chain[-2]
                    if other not in others:
                        others.append(other)
                k, which = ends[0]
                arrow = self.arrows[k]
                entries.append(
                    (
                        sum(self.centre_y(other) for other in others) / len(others),
                        KINDS.index(arrow['kind']) if arrow['kind'] in KINDS else len(KINDS),
                        k,
                        which,
                        port,
                    )
                )
            entries.sort()
            top, odd = self.y[here], self.column_of[card_id] % 2 == 1
            spread = [lane(at, odd) for at in _spread(top, self.card_height[card_id], len(entries))]
            for (*_, port), at in zip(entries, spread):
                for k, which in ports[port]:
                    self.port[(k, which)] = at

    def point_ys(self, k):
        """The y of an arrow at each item of its chain, from left to right."""
        chain = self.chains[k][2]
        out = [self.port[(k, 0)]]
        for item in chain[1:-1]:
            out.append(lane(self.centre_y(item), self.slot_column[item] % 2 == 1))
        out.append(self.port[(k, -1)])
        return out

    def trunk(self, tree):
        """{gap: the y of each end of the vertical part of the tree in the gap}: its y on the side of
        the tree's card (the card's port, or the tree's slot) and the y of each next item of its arrows
        (their ports, or the tree's next slot). One arrow's tree has one vertical part in each gap where
        its two ys differ."""
        found = {}
        side = self.tree[tree][2]
        for k in self.tree[tree][3]:
            low, high, _ = self.chains[k]
            ys = self.point_ys(k)
            if low == high:
                steps = [(low, ys[0], ys[-1])]
            else:
                steps = [(gap, ys[step], ys[step + 1]) for step, gap in enumerate(range(low, high))]
            for gap, a, b in steps:
                near, far = (a, b) if side == 'right' else (b, a)
                found.setdefault(gap, [near]).append(far)
        return {gap: sorted(set(ys)) for gap, ys in found.items()}

    def tracks(self):
        """The track of the vertical part of each tree in each gap, and the width of each gap: a tree's
        vertical part in a gap is one interval, from its lowest y to its highest."""
        count = len(self.columns_of)
        spans = {gap: [] for gap in range(count)}
        for tree in range(len(self.tree)):
            for gap, ys in self.trunk(tree).items():
                if len(ys) > 1:
                    spans[gap].append((ys[0], ys[-1], (tree, gap)))
        self.track = {}
        self.gap_width = []
        for gap in range(count):
            found = _tracks(
                [(low - TRACK / 2, high + TRACK / 2, key) for low, high, key in spans[gap]], fewest=True
            )
            self.track.update(found)
            tracks = 1 + max(found.values(), default=-1)
            last = gap == count - 1
            if last and not tracks:
                self.gap_width.append(0.0)
            else:
                self.gap_width.append(half(2 * GAP_EDGE + max(0, tracks - 1) * TRACK))

    def horizontal(self):
        """The x of each column."""
        self.column_x = []
        x = MARGIN
        for column in range(len(self.columns_of)):
            self.column_x.append(half(x))
            x += self.column_width[column] + self.gap_width[column]
        self.right = x

    def track_x(self, gap, track):
        return half(self.column_x[gap] + self.column_width[gap] + GAP_EDGE + track * TRACK)

    # ---- the result ---------------------------------------------------------------------------

    def bundles(self):
        """The trees of two or more arrows (`Bundle`), and {tree index: its index among them}. A
        junction is each y of a tree's vertical part in a gap that is neither its lowest nor its
        highest: there a branch leaves the trunk."""
        self.bundle_of = {}
        out = []
        for tree, (source, kind, side, members) in enumerate(self.tree):
            if len(members) < 2:
                continue
            junctions = []
            for gap, ys in sorted(self.trunk(tree).items()):
                if len(ys) > 2:
                    x = self.track_x(gap, self.track[(tree, gap)])
                    junctions += [(x, y) for y in ys[1:-1]]
            self.bundle_of[tree] = len(out)
            targets = tuple(self.arrows[k]['to'] for k in members)
            out.append(Bundle(source, kind, side, targets, tuple(junctions)))
        return tuple(out)

    def routes(self):
        """The route of each arrow, from its true start to its true end (`Route`); the arrows of a
        tree take the tree's track in each gap. Call `bundles` first."""
        out = []
        for k, (low, high, chain) in enumerate(self.chains):
            arrow = self.arrows[k]
            tree = self.tree_of[k]
            ys = self.point_ys(k)
            if low == high:
                edge = half(self.column_x[low] + self.column_width[low])
                points = [(edge, ys[0])]
                if ys[0] != ys[-1]:
                    x = self.track_x(low, self.track[(tree, low)])
                    points += [(x, ys[0]), (x, ys[-1])]
                points.append((edge, ys[-1]))
                if chain[0][1] != arrow['from']:
                    points.reverse()
                back = False
            else:
                points = [(half(self.column_x[low] + self.column_width[low]), ys[0])]
                for step, gap in enumerate(range(low, high)):
                    a, b = ys[step], ys[step + 1]
                    if a != b:
                        x = self.track_x(gap, self.track[(tree, gap)])
                        points += [(x, a), (x, b)]
                    nxt = gap + 1
                    if nxt < high:
                        points += [
                            (self.column_x[nxt], b),
                            (half(self.column_x[nxt] + self.column_width[nxt]), b),
                        ]
                    else:
                        points.append((self.column_x[nxt], b))
                back = self.column_of[arrow['from']] > self.column_of[arrow['to']]
                if back:
                    points.reverse()
            out.append(
                Route(
                    arrow['from'],
                    arrow['to'],
                    arrow['kind'],
                    int(arrow.get('count', len(arrow.get('values', ()))) or 0),
                    tuple(arrow.get('values', ())),
                    _simplified(points),
                    back,
                    tuple(arrow.get('how', ())),
                    self.bundle_of.get(tree),
                )
            )
        return tuple(out)

    def placed(self):
        cards, machines, boxes = [], [], {}
        for column, (layer, sub, _) in enumerate(self.columns_of):
            x, width = self.column_x[column], self.column_width[column]
            first = self.first_row[(layer, sub)]
            row = 0
            for item in self.order_of[column]:
                if item[0] != 'card':
                    continue
                card_id = item[1]
                measured = self.measured[card_id]
                y = self.y[item]
                height = self.card_height[card_id]
                card = measured.place(x, y, width, height, layer + 1, sub, first + row + 1)
                row += 1
                cards.append(card)
                boxes[card_id] = card.box
                top = y + height
                for found in measured.beside:
                    top += MACHINE_GAP
                    machines.append(found.place(x, half(top), width, 'beside'))
                    top += found.height
        order = self.card_index
        cards.sort(key=lambda card: order[card.id])
        machines.sort(key=lambda machine: (order[machine.card], machine.var))
        frames = []
        for g, (label, members) in enumerate(self.groups):
            low, high = self.spans[g]
            left = self.column_x[low] - FRAME_PAD
            right = self.column_x[high] + self.column_width[high] + FRAME_PAD
            top, bottom = self.strip_top[2 * g + 1], self.strip_top[2 * g + 2]
            box = Box(half(left), half(top), half(right - left), half(bottom - top))
            frames.append(
                Frame(
                    label, tuple(m for m in self.ids if m in members), box, (half(left + 10), half(top + 16))
                )
            )
        return tuple(cards), tuple(machines), tuple(frames)


def _simplified(points):
    """The points of a path without repeats and without a point in the middle of a straight run."""
    out = []
    for point in points:
        if out and out[-1] == point:
            continue
        if len(out) >= 2:
            (x0, y0), (x1, y1) = out[-2], out[-1]
            if (x0 == x1 == point[0]) or (y0 == y1 == point[1]):
                out[-1] = point
                continue
        out.append(point)
    return tuple(out)


def _legend(marks, top, width, hidden=()):
    """The legend of the marks that the picture draws, and of the kinds of arrows that it has but does
    not draw (`hidden`), in rows that fit in `width`."""
    items, x, y, right = [], MARGIN, top + 10, MARGIN
    for mark in MARKS:
        if mark not in marks and mark not in hidden:
            continue
        words = LEGEND_WORDS[mark] + (': not drawn' if mark in hidden else '')
        item = half(LEGEND_SAMPLE + 8 + text_width(words, SMALL_SIZE) + 18)
        if x > MARGIN and x + item > max(width, 480.0) - MARGIN:
            x, y = MARGIN, y + LEGEND_ROW
        items.append((mark, words, Box(half(x + 10), half(y), item - 10, LEGEND_ROW)))
        right = max(right, x + item)
        x += item
    height = (y + LEGEND_ROW + 6) - top if items else 0.0
    return Legend(
        Box(MARGIN, half(top), half(right - MARGIN + 10), half(height)), tuple(items), tuple(hidden)
    )


# ---- the panels under the legend (D-53, D-55, D-57) ---------------------------------------------------


def _ascent(size):
    """The height of a text of `size` above its baseline, as the typesetter counts it."""
    return up(0.8 * size)


def _descent(size):
    return up(0.25 * size)


@dataclass
class _Bit:
    """A piece of a flow while it is placed (`_rows`, `_place`): its kind (`run`, `math`, `marks`, or
    `break` to start a new row), what it holds (a word, a `typeset.Equation`, or the marks and the x of
    each part of their text), its width, its ascent and descent from its baseline, the room before it
    when it follows another piece on a row, and whether it stays on the row of the piece before it
    (`glue`). A run has its look, size and link. A start's math (`node`) can be typeset again for a
    narrower column, and has its text as the file writes it (`text`) for a column too narrow for it."""

    kind: str
    value: object = None
    width: float = 0.0
    ascent: float = 0.0
    descent: float = 0.0
    space: float = 0.0
    glue: bool = False
    look: str = 'plain'
    size: float = SMALL_SIZE
    url: str | None = None
    node: object = None
    text: str | None = None


def _space(size):
    return up(text_width(' ', size))


# The looks of a panel's text that the SVG draws in bold.
BOLD_LOOKS = ('strong', 'head', 'heading', 'number')


def _run_width(text, size, look):
    """The width of a run of a panel: `bold_width` for a bold look, else `text_width`."""
    return bold_width(text, size) if look in BOLD_LOOKS else up(text_width(text, size))


def _words(text, size=SMALL_SIZE, look='plain', url=None, glue=False):
    """The pieces of the words of a text: a row can break before each word but the first, and with
    `glue` the first stays on the row of the piece before it."""
    return [
        _Bit(
            'run',
            word,
            _run_width(word, size, look),
            _ascent(size),
            _descent(size),
            space=_space(size),
            glue=glue and k == 0,
            look=look,
            size=size,
            url=url,
        )
        for k, word in enumerate(str(text).split())
    ]


def _math_bit(equation, space=0.0, glue=False):
    return _Bit(
        'math',
        equation,
        equation.width,
        equation.ascent,
        equation.height - equation.ascent,
        space=space,
        glue=glue,
    )


def _marks_bit(marks, lead=False):
    """The piece of the marks of a place (`[number, kind]`, …): their numbers with commas between them,
    glued to the piece before them; with `lead`, a comma first (marks that go on from a row before)."""
    parts, x = [], 0.0
    for k, (number, kind) in enumerate(marks):
        if k or lead:
            parts.append((',', x, None))
            x += up(text_width(',', MARK_SIZE))
        parts.append((str(number), x, Mark(int(number), str(kind))))
        x += up(text_width(str(number), MARK_SIZE))
    return _Bit('marks', tuple(parts), x, MARK_RISE + _ascent(MARK_SIZE), 0.0, space=1.0, glue=True)


def _split_marks(bit, room):
    """Marks wider than `room`, as pieces of marks that fit, each but the first starting with a comma."""
    marks = [[mark.number, mark.kind] for _, _, mark in bit.value if mark is not None]
    out, chunk = [], []
    for mark in marks:
        if chunk and _marks_bit([*chunk, mark], lead=bool(out)).width > room:
            out.append(_marks_bit(chunk, lead=bool(out)))
            chunk = []
        chunk.append(mark)
    out.append(_marks_bit(chunk, lead=bool(out)))
    for piece in out:
        piece.glue, piece.space = False, 0.0
    out[0].glue, out[0].space = bit.glue, bit.space
    return out


def _broken(bit, room):
    """A run wider than `room`, cut into runs that fit, each but the first with no room before it."""
    out, rest = [], bit.value
    while rest:
        k = 1
        while k < len(rest) and _run_width(rest[: k + 1], bit.size, bit.look) <= room:
            k += 1
        piece, rest = rest[:k], rest[k:]
        out.append(
            _Bit(
                'run',
                piece,
                _run_width(piece, bit.size, bit.look),
                bit.ascent,
                bit.descent,
                space=bit.space if not out else 0.0,
                glue=bit.glue if not out else False,
                look=bit.look,
                size=bit.size,
                url=bit.url,
            )
        )
    return out


def _rows(bits, left, right, indent=0.0):
    """The rows of pieces between x `left` and `right`: [[(x, piece), …], …]. A piece goes on the row
    of the piece before it when it fits there, after its room; else it starts a row, at `left` for the
    first and at `left + indent` for the others. A glued piece takes the piece before it to the next
    row when the two do not fit, and a run wider than a row breaks where it must."""
    room = right - left - indent
    found = []
    for bit in bits:
        if bit.kind == 'break':
            found.append(None)
        elif bit.glue and found and found[-1] is not None:
            found[-1].append(bit)
        else:
            found.append([bit])
    # A group wider than a row: when its first piece is a run and the rest leaves room for a character
    # of it, the run breaks and its last piece keeps the pieces glued to it; else each piece goes alone,
    # and a run or marks wider than a row break.
    groups = []
    for group in found:
        if group is None or group[0].width + sum(bit.space + bit.width for bit in group[1:]) <= room:
            groups.append(group)
            continue
        rest = sum(bit.space + bit.width for bit in group[1:])
        if group[0].kind == 'run' and room - rest >= up(text_width('M', group[0].size)):
            pieces = _broken(group[0], room - rest)
            groups += [[piece] for piece in pieces[:-1]]
            groups.append([pieces[-1], *group[1:]])
            continue
        for bit in group:
            if bit.kind == 'run' and bit.width > room:
                groups += [[piece] for piece in _broken(bit, room)]
            elif bit.kind == 'marks' and bit.width > room:
                groups += [[piece] for piece in _split_marks(bit, room)]
            else:
                groups.append([bit])
    rows, x, fresh = [], left, True
    for group in groups:
        if group is None:
            fresh = True
            continue
        width = group[0].width + sum(bit.space + bit.width for bit in group[1:])
        if rows and not fresh and x + group[0].space + width <= right:
            x += group[0].space
        else:
            x = left if not rows else left + indent
            rows.append([])
            fresh = False
        for k, bit in enumerate(group):
            if k:
                x += bit.space
            rows[-1].append((x, bit))
            x += bit.width
    return rows


def _place(rows, top, gap=0.0):
    """The items of rows of pieces (`_rows`) from y `top`, each row `gap` under the one before it, on
    the baseline of its tallest piece: (the items, the bottom of the last row). Two runs side by side on
    a row with one look, size and link are one run."""
    items, bottom = [], top
    for k, row in enumerate(rows):
        row_top = top if k == 0 else bottom + gap
        ascent = max(bit.ascent for _, bit in row)
        descent = max(bit.descent for _, bit in row)
        baseline = row_top + ascent
        last = None
        for x, bit in row:
            if bit.kind == 'run':
                box = Box(x, baseline - bit.ascent, bit.width, bit.ascent + bit.descent)
                same = (
                    isinstance(last, Run)
                    and (last.look, last.size, last.url) == (bit.look, bit.size, bit.url)
                    and last.y == baseline
                )
                if same:
                    joined = last.text + (' ' if x > last.box.right else '') + bit.value
                    box = Box(last.x, last.box.y, x + bit.width - last.x, last.box.height)
                    items[-1] = last = Run(joined, last.x, baseline, bit.size, bit.look, box, bit.url)
                    continue
                last = Run(bit.value, x, baseline, bit.size, bit.look, box, bit.url)
            elif bit.kind == 'math':
                equation = bit.value
                y = baseline - equation.ascent
                last = Math(equation, x, y, Box(x, y, equation.width, equation.height))
            else:
                y = baseline - MARK_RISE
                parts = tuple((text, x + at, mark) for text, at, mark in bit.value)
                marks = tuple(mark for _, _, mark in parts if mark is not None)
                last = Marks(marks, y, MARK_SIZE, parts, Box(x, baseline - bit.ascent, bit.width, bit.ascent))
            items.append(last)
        bottom = baseline + descent
    return items, bottom


def _flow(bits, left, right, top, gap=0.0, indent=0.0):
    return _place(_rows(bits, left, right, indent), top, gap)


def _clocked(node, notation):
    """A tree with the time since each event as the event's symbol, and its count as the symbol of its
    count (its key and `COUNTED`): as `panels.line_latex` writes them, so that the picture and the
    LaTeX name the same symbols."""
    if isinstance(node, notation.Since):
        return notation.Sym(node.target)
    if isinstance(node, notation.Count):
        return notation.Sym(node.target + COUNTED)
    if isinstance(node, notation.Sum):
        return node
    changed = {}
    for item in dataclasses.fields(node):
        value = getattr(node, item.name)
        if isinstance(value, (notation.Node, tuple)):
            changed[item.name] = _clocked_in(value, notation)
    return dataclasses.replace(node, **changed) if changed else node


def _clocked_in(value, notation):
    if isinstance(value, notation.Node):
        return _clocked(value, notation)
    if isinstance(value, tuple):
        return tuple(_clocked_in(item, notation) for item in value)
    return value


def span(low, high):
    """The words of a range, `lo–hi`, with one unit when both edges have the same: `0–5 h`."""
    if low is None or high is None:
        return f'up to {high}' if low is None else f'from {low}'
    a, _, unit = str(low).partition(' ')
    b, _, other = str(high).partition(' ')
    return f'{a}–{b} {unit}' if unit and unit == other else f'{low}–{high}'


def range_words(row):
    """The words of the range of a row of the Symbols table: "chosen range lo–hi" for a range that the
    scenario chose (`range_status` "chosen"), "range lo–hi" for another; None without a range."""
    if row.get('range') is None:
        return None
    low, high = row['range']
    return ('chosen range ' if row.get('range_status') == 'chosen' else 'range ') + span(low, high)


def meaning_words(row):
    """The meaning of a row of the Symbols table: an event's symbol is the time since it happens, and its
    count how many times (as the LaTeX fragment says)."""
    meaning = str(row.get('meaning') or '')
    if row.get('kind') == 'event':
        meaning = meaning.rstrip('.') + ': the time since it happens'
        meaning += ', and how many times' if row.get('count') else ''
    return meaning


class _Panels:
    """The panels of a picture (`picture['panels']`), measured and placed from y `top` down: the
    Equations, the Symbols table when `settings.symbols`, the note on a chosen range when there is one,
    under the table, and the References when there are entries. Each panel is `settings.width` wide.
    When the picture above them (`room` wide) holds two panels side by side, the Equations go at the
    left margin and the others in a second column from the same top; else they all go one under another
    at the left margin."""

    def __init__(self, data, top, room=0.0):
        # The imports are here: the typesetter imports this module.
        from . import notation, typeset

        self.notation, self.typeset = notation, typeset
        self.data = data
        self.settings = data.get('settings') or {}
        self.width = half(float(self.settings.get('width') or PANEL_WIDTH))
        self.lines = int(self.settings.get('lines') or PANEL_LINES)
        self.top = top
        self.inner = self.width - 2 * PANEL_PAD
        self.columns = 2 if room >= 2 * MARGIN + 2 * self.width + PANEL_GAP else 1
        self.place(MARGIN)
        self.rows = {row['key']: row for row in data.get('symbols') or ()}

    def place(self, left):
        """The panels that come next go in the column whose left edge is `left`."""
        self.left = left
        self.x0 = left + PANEL_PAD
        self.right = self.x0 + self.inner

    # ---- the symbols and the trees

    def symbol(self, key):
        """(base, prime, subscript) of the symbol of a key: its row's, or its count's for a key with
        `COUNTED`; a key without a row is its own base."""
        counted = key.endswith(COUNTED)
        row = self.rows.get(key[: -len(COUNTED)] if counted else key)
        if row is None:
            return key, False, None
        return symbol_parts(row['count'] if counted and row.get('count') else row['symbol'])

    def tree(self, data):
        return _clocked(self.notation.from_dict(data), self.notation)

    def typeset_(self, node, width, size=TEXT_SIZE, **given):
        return self.typeset.typeset(node, self.symbol, size=size, width=width, lines=self.lines, **given)

    # ---- the panels

    def panels(self):
        self.place(MARGIN)
        out = [self.equations(self.top)]
        y = out[-1].box.bottom + PANEL_GAP
        if self.columns == 2:
            self.place(MARGIN + self.width + PANEL_GAP)
            y = self.top
        makers = []
        if self.settings.get('symbols', True) and self.data.get('symbols'):
            makers.append(self.symbols)
        if self.data.get('note'):
            makers.append(self.note)  # right under the table, which it is about
        if self.data.get('references') or self.data.get('left_out'):
            makers.append(self.references)
        for make in makers:
            out.append(make(y))
            y = out[-1].box.bottom + PANEL_GAP
        self.place(MARGIN)
        return tuple(out)

    def heading(self, text, top):
        size = HEADING_SIZE
        width = bold_width(text, size)
        box = Box(self.x0, top, width, _ascent(size) + _descent(size))
        return Run(text, self.x0, top + _ascent(size), size, 'heading', box)

    def panel(self, kind, top, title, rows, bottom):
        heading = self.heading(title, top + PANEL_PAD)
        return Panel(
            kind, heading, Box(self.left, top, self.width, half(bottom + PANEL_PAD - top)), tuple(rows)
        )

    def body(self, top):
        """The y of the first row of a panel whose top is `top`, under its heading."""
        return top + PANEL_PAD + _ascent(HEADING_SIZE) + _descent(HEADING_SIZE) + HEADING_GAP

    # ---- the Equations

    def equations(self, top):
        y = self.body(top)
        rows = []
        for b, block in enumerate(self.data.get('equations') or ()):
            if b:
                y += BLOCK_GAP
            head = self.block(b, block, y)
            rows.append(head)
            y = head.box.bottom + LINE_GAP
            if not block['lines']:
                items, bottom = _flow(_words('No equations.', look='muted'), self.x0 + INDENT, self.right, y)
                rows.append(Note('empty', Box(self.x0, y, self.inner, bottom - y), tuple(items)))
                y = bottom + LINE_GAP
            for k, item in enumerate(block['lines']):
                line = self.line(b, k, item, y)
                rows.append(line)
                y = line.box.bottom + LINE_GAP
        return self.panel('equations', top, 'Equations', rows, y - LINE_GAP)

    def block(self, b, block, top):
        """The head of a block: its title, and for a block of several members the line "For …"."""
        bits = _words(block['title'], TEXT_SIZE, 'strong')
        members = tuple(member['title'] for member in block['members'])
        if len(members) > 1:
            from .panels import for_words  # panels reads this module's names

            bits.append(_Bit('break'))
            bits += _words(for_words(block), look='muted')
        items, bottom = _flow(bits, self.x0, self.right, top, gap=2.0)
        box = Box(self.x0, top, self.inner, bottom - top)
        return Block(b, block['name'], block['title'], members, box, tuple(items))

    def line(self, b, k, item, top):
        """A line of a block: its math, then for a jump "at <event>" (and its outcome), its words, and its
        marks. The math leaves room for the marks after its widest line."""
        left = self.x0 + INDENT
        marks = _marks_bit(item['marks']) if item.get('marks') else None
        room = self.right - left - (marks.width + marks.space if marks else 0.0)
        if marks is not None and room < self.typeset.run_width(self.typeset.MARKER, TEXT_SIZE) + INDENT:
            # Too many marks to keep room for them: the math takes the row, and the marks follow on
            # the next row when they must.
            room, marks.glue = self.right - left, False
        bits = self.math_bits(item, left, room)
        if item.get('when'):
            bits += self.when(item)
        words = _words(item.get('words') or '', look='muted')
        if words:
            words[0].space = up(0.8 * TEXT_SIZE)
            bits += words
        if marks is not None:
            bits.append(marks)
        items, bottom = _flow(bits, left, self.right, top, gap=LINE_GAP)
        return EquationLine(
            b,
            k,
            item['kind'],
            item.get('part'),
            item.get('latex') or '',
            tuple(item.get('records') or ()),
            Box(self.x0, top, self.inner, bottom - top),
            tuple(items),
        )

    def math_bits(self, item, left, room):
        """The pieces of the math of a line. An equation (`lhs = rhs`) is one typeset node; the trees of
        any other line are typeset one by one, with a comma between them, and at most `lines` rows of
        them show: when they need more, the last trees go and `typeset.MARKER` follows."""
        if item.get('lhs') is not None:
            node, left_side = self.tree(item['rhs']), self.tree(item['lhs'])
            relation = item.get('relation') or '='
            return [_math_bit(self.typeset_(node, room, left=left_side, relation=relation))]
        equations = [self.typeset_(self.tree(tree), room) for tree in item.get('math') or ()]
        if not equations:
            return []

        def joined(count, marker):
            bits = []
            for k, equation in enumerate(equations[:count]):
                if k:
                    bits += _words(',', TEXT_SIZE, glue=True)
                    bits[-1].space = 0.0
                bits.append(_math_bit(equation, space=_space(TEXT_SIZE)))
            if marker:
                bits += _words(self.typeset.MARKER, TEXT_SIZE, 'muted', glue=True)
            return bits

        def used(bits):
            rows = _rows(bits, left, left + room)
            return sum(
                max(len(bit.value.lines) if bit.kind == 'math' else 1 for _, bit in row) for row in rows
            )

        count, bits = len(equations), joined(len(equations), False)
        while count > 1 and used(bits) > self.lines:
            count -= 1
            bits = joined(count, True)
        return bits

    def when(self, item):
        """The pieces that say when a jump happens: "at" and the line's `when`, the name of its event
        in words and its outcome (as the LaTeX fragment writes them), muted."""
        bits = _words(f'at {item["when"]}', look='muted')
        bits[0].space = up(0.8 * TEXT_SIZE)
        return bits

    # ---- the Symbols table

    def cells(self, row):
        """The paragraphs of each cell of a row: {column: [[piece, …], …]}."""
        notation = self.notation
        symbol = [_math_bit(self.typeset_(notation.Sym(row['key']), None))]
        if row.get('count'):
            symbol += _words(',', TEXT_SIZE, glue=True)
            symbol[-1].space = 0.0
            symbol.append(
                _math_bit(self.typeset_(notation.Sym(row['key'] + COUNTED), None), _space(TEXT_SIZE))
            )
        if row.get('marks'):
            symbol.append(_marks_bit(row['marks']))
        out = {'symbol': [symbol], 'meaning': [_words(meaning_words(row))]}
        if row.get('unit'):
            out['unit'] = [_words(row['unit'])]
        value = []
        if row.get('value_math') is not None:
            # A start that a formula sets, typeset with the table's symbols.
            value.append([self.start_math(row['value_math'], row.get('value'))])
        elif row.get('value') is not None:
            value.append(_words(row['value']))
        for member in row.get('instances') or ():
            if member.get('math') is not None:
                value.append(
                    [
                        *_words(f'{member["title"]}:'),
                        self.start_math(member['math'], member.get('value'), _space(SMALL_SIZE)),
                    ]
                )
            elif member.get('value'):
                value.append(_words(f'{member["title"]}: {member["value"]}'))
        for option in row.get('options') or ():
            # An option that gives the members of a template other values: its name, and its marks.
            given = option.get('value')
            if option.get('math') is not None:
                paragraph = [
                    *_words(f'{option["option"]}:'),
                    self.start_math(option['math'], given, _space(SMALL_SIZE)),
                ]
            else:
                paragraph = _words(
                    f'{option["option"]}: {given}' if given is not None else f'{option["option"]} sets it'
                )
            if option.get('marks'):
                paragraph.append(_marks_bit(option['marks']))
            value.append(paragraph)
        if not row.get('options') and row.get('option_count'):
            value.append(_words(f'{row["option_count"]} options set it', look='muted'))
        if value:
            out['value'] = value
        words = range_words(row)
        if words is not None:
            paragraph = _words(words)
            if row.get('range_marks'):
                paragraph.append(_marks_bit(row['range_marks']))
            out['range'] = [paragraph]
        if row.get('distribution'):
            out['distribution'] = [_words(row['distribution'])]
        return out

    def start_math(self, data, text, space=0.0):
        """A start that a formula sets, typeset no wider than the Value column can be; `text` is the
        start as the file writes it."""
        node = self.tree(data)
        bit = _math_bit(self.typeset_(node, COLUMN_MOST['value']), space=space)
        return dataclasses.replace(bit, node=node, text=text)

    def fitted(self, bit, width):
        """The pieces of `bit` in a column `width` wide: a start's math wider than the column is typeset
        again at its width; when it still does not fit, the start's text as the file writes it."""
        if bit.kind != 'math' or bit.node is None or bit.width <= width:
            return [bit]
        equation = self.typeset_(bit.node, width)
        if equation.width <= width:
            again = _math_bit(equation, space=bit.space, glue=bit.glue)
            return [dataclasses.replace(again, node=bit.node, text=bit.text)]
        words = _words(bit.text or '', glue=bit.glue)
        if words:
            words[0].space = bit.space
        return words

    @staticmethod
    def natural(paragraphs):
        """The width of the widest paragraph of a cell on one row."""
        return max(
            (bits[0].width + sum(bit.space + bit.width for bit in bits[1:]) for bits in paragraphs if bits),
            default=0.0,
        )

    def widths(self, columns, cells):
        """{column: width}: the symbols as wide as the widest; the other columns as wide as their widest
        cell (at most `COLUMN_MOST`), the meaning taking the rest of the panel; when that is too wide,
        each other column is cut to a share of the room (`COLUMN_WEIGHT`), never below its least width
        (`COLUMN_LEAST`, or its share of the room when the panel is narrower still)."""
        head = {column: bold_width(HEADINGS[column], SMALL_SIZE) for column in columns}
        natural = {
            column: max([head[column], *(self.natural(cell.get(column, ())) for cell in cells)])
            for column in columns
        }
        # The symbols take a third of the table at most, unless one piece needs more: the count of an
        # event and the marks then go on the next row of the cell.
        widest = max((bit.width for cell in cells for bits in cell['symbol'] for bit in bits), default=0.0)
        widths = {'symbol': min(natural['symbol'], max(widest, up(self.inner / 3)))}
        flexible = [column for column in columns if column != 'symbol']
        room = self.inner - widths['symbol'] - CELL_GAP * (len(columns) - 1)
        least = {column: min(max(COLUMN_LEAST, head[column]), room / len(flexible)) for column in flexible}
        if 'value' in least:
            # A start's math does not break as words do: the Value column takes its width when the
            # table has room for it.
            widest = max(
                (
                    bit.width
                    for cell in cells
                    for bits in cell.get('value', ())
                    for bit in bits
                    if bit.node is not None
                ),
                default=0.0,
            )
            others = sum(least[column] for column in flexible if column != 'value')
            least['value'] = max(least['value'], min(widest, room - others))
        want = {
            column: max(least[column], min(natural[column], COLUMN_MOST.get(column, room)))
            for column in flexible
        }
        if sum(want.values()) <= room:
            widths.update(want)
            widths['meaning'] += room - sum(want.values())
        else:
            low, high = 0.0, room
            for _ in range(60):
                level = (low + high) / 2
                taken = sum(min(want[c], max(least[c], COLUMN_WEIGHT.get(c, 1.0) * level)) for c in flexible)
                low, high = (level, high) if taken <= room else (low, level)
            for column in flexible:
                found = min(want[column], max(least[column], COLUMN_WEIGHT.get(column, 1.0) * low))
                widths[column] = found
        return {column: math.floor(width * 2) / 2 for column, width in widths.items()}

    def symbols(self, top):
        data = self.data['symbols']
        cells = [self.cells(row) for row in data]
        columns = [
            column
            for column in COLUMNS
            if column in ('symbol', 'meaning') or any(cell.get(column) for cell in cells)
        ]
        widths = self.widths(columns, cells)
        lefts, x = {}, self.x0
        for column in columns:
            lefts[column] = x
            x += widths[column] + CELL_GAP
        y = self.body(top)
        rows = [
            self.table_row(
                None, {c: [_words(HEADINGS[c], look='head')] for c in columns}, columns, lefts, widths, y
            )
        ]
        y = rows[-1].box.bottom
        for row, found in zip(data, cells):
            rows.append(self.table_row(row, found, columns, lefts, widths, y))
            y = rows[-1].box.bottom
        return self.panel('symbols', top, 'Symbols', rows, y)

    def table_row(self, row, found, columns, lefts, widths, top):
        placed, bottom = [], top + ROW_PAD
        for column in columns:
            bits = []
            for k, paragraph in enumerate(found.get(column, ())):
                pieces = [piece for bit in paragraph for piece in self.fitted(bit, widths[column])]
                bits += ([_Bit('break')] if k else []) + pieces
            left = lefts[column]
            items, end = (
                _flow(bits, left, left + widths[column], top + ROW_PAD, gap=1.0)
                if bits
                else ([], top + ROW_PAD)
            )
            placed.append(
                Cell(column, Box(left, top + ROW_PAD, widths[column], end - top - ROW_PAD), tuple(items))
            )
            bottom = max(bottom, end)
        box = Box(self.x0, top, self.inner, bottom + ROW_PAD - top)
        if row is None:
            return SymbolRow(None, '', '', (), box, tuple(placed))
        text = row['symbol']['text'] + (f', {row["count"]["text"]}' if row.get('count') else '')
        return SymbolRow(
            row['key'], text, meaning_words(row), tuple(row.get('records') or ()), box, tuple(placed)
        )

    # ---- the References

    def references(self, top):
        entries = self.data['references']
        widest = max((bold_width(f'{entry["number"]}.', SMALL_SIZE) for entry in entries), default=0.0)
        left = self.x0 + widest + 6.0
        y = self.body(top)
        rows = []
        words = left_out_words(self.data.get('left_out'))
        if words:
            # The kinds of record that the list leaves out ([references] kinds), under its heading.
            items, bottom = _flow(_words(words, look='muted'), self.x0, self.right, y, gap=2.0)
            rows.append(Note('left_out', Box(self.x0, y, self.inner, bottom - y), tuple(items)))
            y = bottom + LINE_GAP
        for entry in entries:
            bits = _words(f'{entry["label"]}.', look='strong') + _words(entry.get('text') or '')
            url = entry.get('url') if web_host(entry.get('url')) else None
            if url is not None:
                bits += _words(str(entry.get('link_text') or '').strip() or url, look='link', url=url)
            items, bottom = _flow(bits, left, self.right, y, gap=1.0)
            baseline = items[0].y if items else y + _ascent(SMALL_SIZE)
            text = f'{entry["number"]}.'
            width = bold_width(text, SMALL_SIZE)
            number = Run(
                text,
                self.x0,
                baseline,
                SMALL_SIZE,
                'number',
                Box(
                    self.x0, baseline - _ascent(SMALL_SIZE), width, _ascent(SMALL_SIZE) + _descent(SMALL_SIZE)
                ),
            )
            bottom = max(bottom, number.box.bottom)
            rows.append(
                Entry(
                    int(entry['number']),
                    str(entry['kind']),
                    str(entry.get('hover') or ''),
                    tuple(entry.get('record') or ()),
                    url,
                    Box(self.x0, y, self.inner, bottom - y),
                    (number, *items),
                )
            )
            y = bottom + LINE_GAP
        return self.panel('references', top, 'References', rows, y - LINE_GAP)

    # ---- the note

    def note(self, top):
        items, bottom = _flow(_words(self.data['note'], look='muted'), self.x0, self.right, top, gap=2.0)
        row = Note('note', Box(self.x0, top, self.inner, bottom - top), tuple(items))
        return Panel('note', None, Box(self.left, top, self.width, half(bottom - top)), (row,))


def layout(picture, style=None):
    """The layout of a picture (`model_map.picture`): a `Layout`. The picture holds what the stylesheet
    chooses (the places, the groups and where each machine goes), so `style` (the `style.Style` that
    made the picture) changes nothing here; it is the same argument as the picture's. A picture with
    another direction than left-to-right raises ValueError."""
    del style
    work = _Work(picture)
    work.columns()
    work.segments()
    work.order()
    work.sides()
    work.widths()
    work.heights()
    work.vertical()
    work.ports()
    work.tracks()
    work.horizontal()
    bundles = work.bundles()
    routes = work.routes()
    cards, machines, frames = work.placed()
    marks = {route.kind for route in routes}
    for card in cards:
        marks.update(stock.kind for stock in (*card.stocks, *card.meters))
        if card.pipes:
            marks.add('pipe')
        if card.actor:
            marks.add('decides')
    for machine in (*machines, *(m for card in cards for m in card.machines)):
        marks.add('state')
        if machine.transitions:
            marks.add('transition')
    title = bold_width(str(picture.get('title', '')), PICTURE_TITLE_SIZE) + 2 * MARGIN
    width = half(max(work.right + MARGIN, title, 320.0))
    legend = _legend(marks, work.bottom + LEGEND_GAP, width, work.hidden_kinds)
    width = half(max(width, legend.box.right + MARGIN))
    bottom = legend.box.bottom
    # The panels go under the legend, and the picture is as wide as they need (D-53).
    panels = ()
    if picture.get('panels'):
        panels = _Panels(picture['panels'], half(bottom + PANEL_GAP), width).panels()
        width = half(max(width, *(panel.box.right + MARGIN for panel in panels)))
        bottom = max(panel.box.bottom for panel in panels)
    height = half(bottom + MARGIN)
    return Layout(
        width,
        height,
        (MARGIN, MARGIN + 18),
        cards,
        machines,
        routes,
        frames,
        legend,
        subtitle(picture),
        bundles=bundles,
        panels=panels,
    )


__all__ = [
    'BUNDLE',
    'COLUMNS',
    'KINDS',
    'LEGEND_WORDS',
    'MARKS',
    'Block',
    'Box',
    'Bundle',
    'Card',
    'Cell',
    'Entry',
    'EquationLine',
    'EventLine',
    'Frame',
    'Layout',
    'Legend',
    'Machine',
    'Mark',
    'Marks',
    'Math',
    'More',
    'Note',
    'Panel',
    'Pipe',
    'Route',
    'Run',
    'State',
    'Stock',
    'SymbolRow',
    'Tag',
    'Transition',
    'Trigger',
    'back_pairs',
    'crossing_count',
    'gathered',
    'greedy_order',
    'half',
    'lane',
    'layers',
    'layout',
    'meaning_words',
    'range_words',
    'shorten',
    'span',
    'symbol_parts',
    'tags_of',
    'text_width',
    'up',
    'wrap',
]
