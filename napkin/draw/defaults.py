"""The kinds of arrows of a picture and the defaults of what the stylesheet chooses (D-50, D-51, D-52,
D-56). The stylesheet (`style`), the picture (`model_map`), the layout and the SVG read them from
here, so that each default is written once. This module imports nothing.
"""

# The kinds of the arrows of a picture (D-50): "fires" is a line that runs another card's event, and
# "follows" a read of when another card's event happened (`since`, `count`).
ARROW_KINDS = ('reads', 'follows', 'changes', 'fires', 'moves')
# The kinds whose arrow goes from the card whose value is read to the card that reads it.
READ_KINDS = ('reads', 'follows')
# The kinds whose arrows put a card in a later column than the card at their start.
RANKING = ('changes', 'fires', 'moves')
# The looks of an arrow (D-51), and the look of each kind without `[arrows]`.
ARROW_LOOKS = ('full', 'light', 'hidden')
DEFAULT_LOOKS = {'reads': 'light', 'follows': 'light', 'changes': 'full', 'fires': 'full', 'moves': 'full'}
# The kinds whose arrows from one card share a trunk without `[arrows] bundle` (D-51).
DEFAULT_BUNDLE = ('reads', 'follows')
# The most stock rows of a card and the most cards of a column without `[layout]` (D-52).
DEFAULT_STOCKS = 4
DEFAULT_CARDS_PER_COLUMN = 8
# The most rows of the line of an event at the level `rules`, the most events with a row on a card,
# and whether the lines name the options that switch an event, without `[triggers]` (D-56).
DEFAULT_TRIGGER_LINES = 2
DEFAULT_TRIGGER_EVENTS = 6
DEFAULT_TRIGGER_OPTIONS = True
# The hops of formulas from the rates, the width of the panels in px and the most rows of one line,
# without those keys of `[equations]` (D-53).
DEFAULT_DEPTH = 1
DEFAULT_PANEL_WIDTH = 720
DEFAULT_PANEL_LINES = 3
