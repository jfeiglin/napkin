"""A scenario's stylesheet: `style.toml`, an optional TOML file of the package.

A model's file is found in this order (`lookup`): the file in the folder of the model's file, which is a
variant's own folder for a variant, then the one in the folder of its package. The file that is found
replaces the other whole, and the two never merge. A caller can name a file of its own instead (`of`).

`style.toml` is the picture only: how `napkin draw` and the map of the system draw the model. Its
keys:

| Key | What it gives | Without it |
| --- | --- | --- |
| `[layout]` with `direction = "left-to-right"` | The direction of the picture: the one direction of this version (`DIRECTIONS`) | `left-to-right` |
| `[layout]` with `hide = [n, …]` | The templates and things that the picture does not draw: a template hides each of its members, and a member hides only itself | Nothing hidden |
| `[place]` with `n = {column = c, row = r}` | The column of a thing, from 1, and its row, from 1 (`row` is optional). A template places each of its members on the rows that follow its row | The layout places it |
| `[group]` with `"Label" = [n, …]` | A frame with its label around these things and no other thing; a thing is in one group at most | No frame |
| `[icon]` with `icon = [n, …]` | The icon of each thing and template that a line names (`ICONS`) | The icon of its role (`ROLE_ICONS`), else no icon |
| `[role]` with `role = [n, …]` | Who plays each thing and template that a line names: a word, such as `operator`. A card has the icon of its role when `[icon]` gives it none (`ROLE_ICONS`), and the map names its role (`model_map.ROLES`) | No role |
| `[state.n]` with `var = "inside"` | Where the state machine of the named state `n.var` goes: `inside` its thing, `beside` it, or `hidden` (`STATE_PLACES`) | `inside` |
| `[arrows]` with `kind = "light"` | The look of the arrows of a kind (`ARROW_KINDS`): `full`, `light` (a paler, thinner line) or `hidden` (no line; the legend and the tooltips still name the kind) (`ARROW_LOOKS`, D-51) | `light` for reads and follows, `full` for the others |
| `[arrows]` with `bundle = [kind, …]` | The kinds whose arrows from one card toward one side share one trunk that branches near the cards at their ends (D-51) | reads and follows |
| `[layout]` with `stocks = k` (D-52) | The most stock and tally rows of a card before its "+n" row, 1 to 8 (`LAYOUT_RANGES`) | 4 |
| `[layout]` with `cards_per_column = k` (D-52) | The most cards of a column: a fuller layer splits into sub-columns, 2 to 16 | 8 |
| `[layout]` with `card_width = w` (D-52) | The least width of a card in px, 170 to 400: a card whose title, rows or machines need more is wider, and each card of a column is as wide as the widest | 170 |
| `[stocks]` with `n = [stock, …]` (D-52) | The stocks and tallies of the card of `n` that its rows show, in this order; the others are in its "+n" row | The layout chooses them |
| `[triggers]` with `level = [n, …]` | What the card of each thing and template shows of its events (`TRIGGER_LEVELS`, D-56): `count` a row "n events", `names` a row for each event's name, `rules` the line of each event, shortened, and `hover` nothing; each level puts the full lines in the card's tooltip | Nothing |
| `[triggers]` with `lines`, `events`, `options` | The most rows of a line at `rules` (1 to 4), the most events with a row before "+n more" (1 to 20), and whether the lines name the options that switch an event (`TRIGGER_RANGES`) | 2, 6, true |
| `[symbol.n]` with `member = "W_s"` | The symbol of a value, a flow or an event of `n` in the equations: a letter or a Greek name, an optional prime and an optional subscript (`symbols.parse`, D-54). A template's symbol has no subscript: each instance adds its own | Made from the model's names |
| `[subscript]` with `n = "s"` | The subscript of the card of the thing `n` (`symbols.parse_tag`, D-54) | Made from the thing's name |
| `[equations]` with `things = [n, …]` (D-53) | The things and templates whose equations the panel under the map shows (`panels.py`) | No panel |
| `[equations]` with `depth`, `width`, `lines` | The hops of formulas from the rates (0 to 5), the width of the panel in px (320 to 2400) and the most rows of one line (1 to 8) (`EQUATION_RANGES`) | 1, 720, 3 |
| `[equations]` with `tags`, `symbols`, `checks`, `instances` | Whether each shown stock row carries its symbol, whether the Symbols table shows, whether the `assert` lines show, and whether the members of a template with the same equations share a block (`together`) or each has its own (`each`, `INSTANCES`) | true, true, false, `together` |
| `[references]` with `show`, `kinds` (D-55) | Whether the marks and the References list show (it needs `[equations] things`), and the kinds of entry that the list holds (`REFERENCE_KINDS`; `assumption` always) | false, every kind |

A name is a thing (a card of the picture: an entity written once, a member written by hand, or a
table, whose rows share one card) or a template, which stands for each of its members. A thing's own
setting wins over its template's, and for an icon, the template's wins over the role's. A thing plays
one role at most, by its own name or by its template's.

The model has no role (PLAN.md, change 23 after G0): who plays a part belongs to the scenario's
wrapper (`roles.toml`, which the publisher and the UI read) and, for the pictures, to `[role]`. A role
of `[role]` names things and templates of the model, drawn or not, since who plays a part is no part
of the picture.

The built-in `tomllib` reads the file. A key that the file does not know is an error, so that a
misspelt key shows. Each name is one that the model declares, and each icon is one of `ICONS`. The
compiler, the engine and the studies never read the file, so the model hash does not cover it. An
error in the file stops what reads it (`StyleError`, each problem with its file and its key), never a
build or a run. The brief settings (`brief.toml`) use the same reading of a file (`table`, `names_of`,
`unknown`, `checked`).
"""

from __future__ import annotations

import re
import tomllib
from collections import OrderedDict
from dataclasses import dataclass
from pathlib import Path

from .. import paths
from .defaults import ARROW_KINDS, ARROW_LOOKS, DEFAULT_DEPTH, DEFAULT_PANEL_LINES, DEFAULT_PANEL_WIDTH

STYLE_FILE = 'style.toml'
# The tables of `style.toml` that this version reads, the keys of `[layout]` and of a place, the
# directions of a picture and the places of a state machine. `[icon]` has a key for each icon, `[role]`
# one for each role, `[place]` and `[group]` one for each place and group, `[state.<thing>]` one for
# each named state, `[stocks]` one for each thing or template, `[symbol.<thing>]` one for each member,
# and `[subscript]` one for each thing.
STYLE_TABLES = (
    'layout',
    'place',
    'group',
    'icon',
    'role',
    'state',
    'arrows',
    'stocks',
    'symbol',
    'subscript',
    'triggers',
    'equations',
    'references',
)
LAYOUT_KEYS = ('direction', 'hide', 'stocks', 'cards_per_column', 'card_width')
# The whole numbers of `[layout]` (D-52), each with its least and its most value: the most stock rows of a
# card, the most cards of a column and the width of a card in px.
LAYOUT_RANGES = {'stocks': (1, 8), 'cards_per_column': (2, 16), 'card_width': (170, 400)}
# The kinds of the values that `[stocks]` names: the stocks and the tallies.
STOCK_KINDS = ('stock', 'tally')
PLACE_KEYS = ('column', 'row')
DIRECTIONS = ('left-to-right',)
STATE_PLACES = ('inside', 'beside', 'hidden')
# The kinds of arrows (D-50), the looks of an arrow and the keys of `[arrows]` (D-51).
ARROWS_KEYS = (*ARROW_KINDS, 'bundle')
# The levels of `[triggers]` (D-56), from the least that a card shows of its events to the most, and
# then `hover`, which shows them in the tooltip only; the whole numbers of `[triggers]` with their
# ranges; and its keys.
TRIGGER_LEVELS = ('count', 'names', 'rules', 'hover')
TRIGGER_RANGES = {'lines': (1, 4), 'events': (1, 20)}
TRIGGERS_KEYS = (*TRIGGER_LEVELS, *TRIGGER_RANGES, 'options')
# The keys of `[equations]` (D-53): the whole numbers with their ranges, the keys that are true or
# false with their defaults, and how the instances of a template share blocks; and the keys of
# `[references]` (D-55), with the kinds of entry of its list (`references.KINDS`).
EQUATION_RANGES = {'depth': (0, 5), 'width': (320, 2400), 'lines': (1, 8)}
EQUATION_FLAGS = {'tags': True, 'symbols': True, 'checks': False}
INSTANCES = ('together', 'each')
EQUATIONS_KEYS = ('things', *EQUATION_RANGES, *EQUATION_FLAGS, 'instances')
REFERENCE_KINDS = ('source', 'source_transfer', 'identity', 'convention', 'assumption')
REFERENCES_KEYS = ('show', 'kinds')
# The icons that the map draws (icons.py, with the same names in tests/draw/map-icons.json), and the
# icon of a thing that `[icon]` gives none: the icon of its role of `[role]`. A thing without a role, or
# with another role, has no icon.
ICONS = (
    'target',
    'server',
    'shield',
    'hospital',
    'people',
    'gauge',
    'factory',
    'tank',
    'pipe',
    'bolt',
    'drop',
    'wrench',
    'truck',
    'box',
    'document',
    'money',
    'house',
    'shop',
    'sun',
    'alert',
)
ROLE_ICONS = {
    'adversary': 'target',
    'operator': 'server',
    'responder': 'shield',
    'clinician': 'hospital',
    'community': 'people',
    'environment': 'gauge',
}
# A role of `[role]`: a word, as a name of the language is (`napkin/model/language/lex.py`, NAME).
ROLE = re.compile(r'[A-Za-z_][A-Za-z0-9_]*')
# The line that tomllib names in the message of a text that is not TOML.
AT_LINE = re.compile(r'\(at line (\d+), column \d+\)')


class StyleError(ValueError):
    """A stylesheet or a brief that cannot be used: its problems (`diagnostics`), each with its file,
    its key (None for the whole file) and, for a text that is not TOML, its line."""

    def __init__(self, diagnostics):
        self.diagnostics = list(diagnostics)
        super().__init__('\n'.join(f'{place(d)}: {d["message"]}' for d in self.diagnostics))


def place(diagnostic):
    """`file:line`, or `file` for a problem without a line."""
    line = diagnostic.get('line')
    return f'{diagnostic["file"]}:{line}' if line else diagnostic['file']


def problem(origin, key, message, line=None):
    """A diagnostic of the file `origin` at its key, `table.key` or `key` (None for the whole file),
    with the key at the start of its message."""
    found = {
        'code': 'style',
        'severity': 'error',
        'file': origin,
        'key': key,
        'message': f'{key}: {message}' if key else message,
    }
    if line is not None:
        found['line'] = line
    return found


# ---- reading a file -------------------------------------------------------------------------------


def table(text, origin):
    """The table of a TOML text. A text that is not TOML raises `StyleError` at the line that
    `tomllib` names."""
    try:
        return tomllib.loads(text)
    except tomllib.TOMLDecodeError as exc:
        found = AT_LINE.search(str(exc))
        line = int(found.group(1)) if found else None
        raise StyleError([problem(origin, None, f'the file is not TOML: {exc}', line)]) from None


def names_of(value, key, origin, problems):
    """The names of a list of names, in order, or None with its problem: a value that is not a list
    of names, or a list that names an item twice."""
    if not isinstance(value, list) or not all(isinstance(name, str) and name for name in value):
        short = key.rpartition('.')[2]
        problems.append(problem(origin, key, f'holds a list of names, such as {short} = ["a", "b.c"]'))
        return None
    twice = [name for i, name in enumerate(value) if name in value[:i]]
    for name in dict.fromkeys(twice):
        problems.append(problem(origin, key, f'names {name} twice'))
    return None if twice else tuple(value)


def unknown(found, known, origin, problems, prefix=''):
    """The problems of the keys of a table that are not in `known`."""
    for key in found:
        if key not in known:
            where = f'{prefix}{key}'
            listed = ', '.join(f'{prefix}{name}' for name in known)
            problems.append(problem(origin, where, f'is not a key that this file reads; it reads {listed}'))


# ---- the picture: style.toml ---------------------------------------------------------------------


@dataclass(frozen=True)
class Style:
    """The picture that `style.toml` gives, each part in the order of the file:
    - `hide`: the names that `[layout]` hides;
    - `icons`: the names of each icon of `[icon]`, ((icon, (name, …)), …);
    - `roles`: the names of each role of `[role]`, ((role, (name, …)), …);
    - `origin`: the file;
    - `direction`: the direction of `[layout]`;
    - `places`: each place of `[place]`, ((name, column, row or None), …);
    - `groups`: each group of `[group]`, ((label, (name, …)), …);
    - `states`: the place of each state machine of `[state.<name>]`, ((name, ((var, place), …)), …);
    - `looks`: the look of each kind of arrow that `[arrows]` gives, ((kind, look), …);
    - `bundle`: the kinds that `[arrows] bundle` names, or None without the key;
    - `stocks`, `cards_per_column` and `card_width`: the numbers of `[layout]` (D-52), each None when
      the file does not give it;
    - `stock_order`: the stocks and tallies of each list of `[stocks]` (D-52), ((name, (stock, …)), …);
    - `symbols`: the symbols of `[symbol.<name>]` as written (D-54), ((name, ((member, symbol), …)), …);
    - `subscripts`: the subscript of each card of `[subscript]` (D-54), ((name, subscript), …);
    - `triggers`: the names of each level of `[triggers]`, ((level, (name, …)), …);
    - `trigger_lines`, `trigger_events`, `trigger_options`: the other keys of `[triggers]`, or None
      without the key;
    - `equations`: the names of `[equations] things` (D-53); `equation_depth`, `equation_width`,
      `equation_lines`, `equation_tags`, `equation_symbols`, `equation_checks` and
      `equation_instances`: its other keys, each None without the key;
    - `references_show` and `references_kinds`: the keys of `[references]` (D-55), each None without
      the key.
    Without a file, nothing is hidden, placed or grouped, no thing has an icon of its own or a role,
    each state machine is inside its thing, the layout chooses the rows of each card, every symbol is
    made from the model's names, and there is no panel of equations."""

    hide: tuple = ()
    icons: tuple = ()
    roles: tuple = ()
    origin: str | None = None
    direction: str = DIRECTIONS[0]
    places: tuple = ()
    groups: tuple = ()
    states: tuple = ()
    looks: tuple = ()
    bundle: tuple | None = None
    stocks: int | None = None
    cards_per_column: int | None = None
    card_width: int | None = None
    stock_order: tuple = ()
    symbols: tuple = ()
    subscripts: tuple = ()
    triggers: tuple = ()
    trigger_lines: int | None = None
    trigger_events: int | None = None
    trigger_options: bool | None = None
    equations: tuple = ()
    equation_depth: int | None = None
    equation_width: int | None = None
    equation_lines: int | None = None
    equation_tags: bool | None = None
    equation_symbols: bool | None = None
    equation_checks: bool | None = None
    equation_instances: str | None = None
    references_show: bool | None = None
    references_kinds: tuple | None = None


def _tables(found, key):
    """The table `key` of a file, or an empty table when the file has none or another value there (a
    problem that `read` reports)."""
    value = found.get(key)
    return value if isinstance(value, dict) else {}


def _whole(value):
    """Whether a value of the file is a whole number of 1 or more (TOML's true and false are not)."""
    return isinstance(value, int) and not isinstance(value, bool) and value >= 1


def read(text, origin=STYLE_FILE):
    """The picture of `text` (`Style`). It reads:
    - `[layout]`: `direction`, which is one of `DIRECTIONS`, `hide`, a list of names, and `stocks`,
      `cards_per_column` and `card_width`, each a whole number in its range (`LAYOUT_RANGES`);
    - `[place]`: for each name, a table with a `column` and an optional `row`, each 1 or more;
    - `[group]`: for each label, a list of one name or more;
    - `[icon]`: for each icon of `ICONS`, a list of names;
    - `[role]`: for each role, a word (`ROLE`), a list of names;
    - `[state.<name>]`: for each named state, one of `STATE_PLACES`;
    - `[arrows]`: for each kind of `ARROW_KINDS`, one of `ARROW_LOOKS`, and `bundle`, a list of kinds;
    - `[stocks]`: for each name, a list of one stock or tally or more;
    - `[symbol.<name>]`: for each member, a symbol (`symbols.parse`); `[subscript]`: for each name, a
      subscript (`symbols.parse_tag`);
    - `[triggers]`: for each level of `TRIGGER_LEVELS`, a list of names; `lines` and `events`, whole
      numbers in their `TRIGGER_RANGES`; and `options`, true or false;
    - `[equations]`: `things`, a list of names; `depth`, `width` and `lines`, whole numbers in their
      `EQUATION_RANGES`; `tags`, `symbols` and `checks`, true or false; `instances`, one of
      `INSTANCES`;
    - `[references]`: `show`, true or false, which needs `[equations] things`; `kinds`, a list of
      `REFERENCE_KINDS` that keeps `assumption`.
    Another key, a value of another shape or outside its range, a name that two icons, two roles or two
    groups name, and a name written twice in one list raise `StyleError`, with every problem of the
    file."""
    found, problems = table(text, origin), []
    unknown(found, STYLE_TABLES, origin, problems)
    for key in STYLE_TABLES:
        if key in found and not isinstance(found[key], dict):
            problems.append(problem(origin, key, f'is a table, [{key}]'))
    layout = _tables(found, 'layout')
    unknown(layout, LAYOUT_KEYS, origin, problems, 'layout.')
    direction = layout.get('direction', DIRECTIONS[0])
    if direction not in DIRECTIONS:
        listed = ', '.join(f'"{name}"' for name in DIRECTIONS)
        problems.append(problem(origin, 'layout.direction', f'is one of {listed}'))
    hide = names_of(layout['hide'], 'layout.hide', origin, problems) if 'hide' in layout else ()
    numbers = _read_numbers(layout, origin, problems)
    icons, given = [], {}
    for icon, value in _tables(found, 'icon').items():
        key = f'icon.{icon}'
        if icon not in ICONS:
            problems.append(problem(origin, key, f'{icon} is not an icon; the icons are {", ".join(ICONS)}'))
            continue
        listed = names_of(value, key, origin, problems)
        for name in listed or ():
            if name in given:
                problems.append(problem(origin, key, f'names {name}, which icon.{given[name]} also names'))
            given.setdefault(name, icon)
        if listed is not None:
            icons.append((icon, listed))
    roles = _read_roles(_tables(found, 'role'), origin, problems)
    places = _read_places(_tables(found, 'place'), origin, problems)
    groups = _read_groups(_tables(found, 'group'), origin, problems)
    states = _read_states(_tables(found, 'state'), origin, problems)
    looks, bundle = _read_arrows(_tables(found, 'arrows'), origin, problems)
    stock_order = _read_stock_order(_tables(found, 'stocks'), origin, problems)
    symbols = _read_symbols(found, origin, problems)
    triggers = _read_triggers(_tables(found, 'triggers'), origin, problems)
    equations = _read_equations(_tables(found, 'equations'), origin, problems)
    references = _read_references(
        _tables(found, 'references'), bool(equations['equations']), origin, problems
    )
    if problems:
        raise StyleError(problems)
    return Style(
        hide=hide or (),
        icons=tuple(icons),
        roles=roles,
        origin=origin,
        direction=direction,
        places=places,
        groups=groups,
        states=states,
        looks=looks,
        bundle=bundle,
        **numbers,
        stock_order=stock_order,
        **symbols,
        **triggers,
        **equations,
        **references,
    )


def _read_roles(found, origin, problems):
    """((role, (name, …)), …) of `[role]`, in the shape of `[icon]`, with the problems of its lists: a
    role that is not a word (`ROLE`), a value that is not a list of names, and a name that two roles
    name."""
    roles, given = [], {}
    for role, value in found.items():
        key = f'role.{role}'
        if not ROLE.fullmatch(role):
            problems.append(problem(origin, key, 'a role is a word, such as operator = ["pump"]'))
            continue
        listed = names_of(value, key, origin, problems)
        for name in listed or ():
            if name in given:
                problems.append(problem(origin, key, f'names {name}, which role.{given[name]} also names'))
            given.setdefault(name, role)
        if listed is not None:
            roles.append((role, listed))
    return tuple(roles)


def _read_arrows(found, origin, problems):
    """((kind, look), …) and the kinds of `bundle` (None without the key) of `[arrows]` (D-51), with the
    problems of its values."""
    unknown(found, ARROWS_KEYS, origin, problems, 'arrows.')
    looks = []
    for kind in ARROW_KINDS:
        if kind not in found:
            continue
        if found[kind] in ARROW_LOOKS:
            looks.append((kind, found[kind]))
        else:
            listed = ', '.join(f'"{name}"' for name in ARROW_LOOKS)
            problems.append(problem(origin, f'arrows.{kind}', f'is one of {listed}'))
    if 'bundle' not in found:
        return tuple(looks), None
    value = found['bundle']
    if not isinstance(value, list) or not all(isinstance(kind, str) for kind in value):
        problems.append(
            problem(origin, 'arrows.bundle', 'holds a list of kinds, such as bundle = ["reads", "follows"]')
        )
        return tuple(looks), None
    wrong = False
    for k, kind in enumerate(value):
        if kind not in ARROW_KINDS:
            message = f'names {kind}, which is not a kind of arrow; the kinds are {", ".join(ARROW_KINDS)}'
            problems.append(problem(origin, 'arrows.bundle', message))
            wrong = True
        elif kind in value[:k]:
            problems.append(problem(origin, 'arrows.bundle', f'names {kind} twice'))
            wrong = True
    return tuple(looks), None if wrong else tuple(value)


def _read_numbers(layout, origin, problems):
    """{key: value} of the whole numbers of `[layout]` that the file gives (`LAYOUT_RANGES`), with the
    problem of each value that is not a whole number in its range."""
    numbers = {}
    for key, (least, most) in LAYOUT_RANGES.items():
        if key not in layout:
            continue
        value = layout[key]
        if isinstance(value, int) and not isinstance(value, bool) and least <= value <= most:
            numbers[key] = value
        else:
            unit = ' of px' if key == 'card_width' else ''
            problems.append(
                problem(origin, f'layout.{key}', f'is a whole number{unit} from {least} to {most}')
            )
    return numbers


def _read_stock_order(found, origin, problems):
    """((name, (stock, …)), …) of `[stocks]`, with the problems of its lists: a value that is not a list
    of names, a list that names a stock twice, and a list that names none."""
    out = []
    for name, value in found.items():
        key = f'stocks.{name}'
        listed = names_of(value, key, origin, problems)
        if listed == ():
            problems.append(problem(origin, key, f'names no stock or tally: write {name} = ["a", "b"]'))
        elif listed is not None:
            out.append((name, listed))
    return tuple(out)


def _read_triggers(found, origin, problems):
    """The `Style` fields of `[triggers]` (D-56), with the problems of its values: a level that is not a
    list of names, a name that two levels name, a number out of its range and an `options` that is not
    true or false."""
    unknown(found, TRIGGERS_KEYS, origin, problems, 'triggers.')
    levels, given = [], {}
    for level, value in found.items():
        if level not in TRIGGER_LEVELS:
            continue
        key = f'triggers.{level}'
        listed = names_of(value, key, origin, problems)
        for name in listed or ():
            if name in given:
                problems.append(
                    problem(origin, key, f'names {name}, which triggers.{given[name]} also names')
                )
            given.setdefault(name, level)
        if listed is not None:
            levels.append((level, listed))
    out = {'triggers': tuple(levels)}
    for name, (low, high) in TRIGGER_RANGES.items():
        value = found.get(name)
        if name in found and not (_whole(value) and low <= value <= high):
            problems.append(problem(origin, f'triggers.{name}', f'is a whole number from {low} to {high}'))
            value = None
        out[f'trigger_{name}'] = value
    value = found.get('options')
    if 'options' in found and not isinstance(value, bool):
        problems.append(problem(origin, 'triggers.options', 'is true or false'))
        value = None
    out['trigger_options'] = value
    return out


def _flag(found, key, origin, problems):
    """The value of a key of a table that is true or false, or None without the key or with a value of
    another kind (a problem)."""
    name = key.partition('.')[2]
    if name not in found:
        return None
    if isinstance(found[name], bool):
        return found[name]
    problems.append(problem(origin, key, 'is true or false'))
    return None


def _read_equations(found, origin, problems):
    """The `Style` fields of `[equations]` (D-53), with the problems of its values: `things` that is not
    a list of names, a number out of its range, a flag that is not true or false and an `instances`
    that is not one of `INSTANCES`."""
    unknown(found, EQUATIONS_KEYS, origin, problems, 'equations.')
    things = names_of(found['things'], 'equations.things', origin, problems) if 'things' in found else ()
    out = {'equations': things or ()}
    for name, (low, high) in EQUATION_RANGES.items():
        value = found.get(name)
        if name in found and not (
            isinstance(value, int) and not isinstance(value, bool) and low <= value <= high
        ):
            unit = ' of px' if name == 'width' else ''
            problems.append(
                problem(origin, f'equations.{name}', f'is a whole number{unit} from {low} to {high}')
            )
            value = None
        out[f'equation_{name}'] = value
    for name in EQUATION_FLAGS:
        out[f'equation_{name}'] = _flag(found, f'equations.{name}', origin, problems)
    value = found.get('instances')
    if 'instances' in found and value not in INSTANCES:
        listed = ', '.join(f'"{name}"' for name in INSTANCES)
        problems.append(problem(origin, 'equations.instances', f'is one of {listed}'))
        value = None
    out['equation_instances'] = value
    return out


def _read_references(found, panel, origin, problems):
    """The `Style` fields of `[references]` (D-55), with the problems of its values: a `show` that is
    not true or false, or that is true without `[equations] things` (`panel`), and `kinds` that is not
    a list of `REFERENCE_KINDS`, names a kind twice or leaves out `assumption`."""
    unknown(found, REFERENCES_KEYS, origin, problems, 'references.')
    show = _flag(found, 'references.show', origin, problems)
    if show and not panel:
        problems.append(problem(origin, 'references.show', 'needs [equations]: the marks go on its symbols'))
    out = {'references_show': show, 'references_kinds': None}
    if 'kinds' not in found:
        return out
    value = found['kinds']
    if not isinstance(value, list) or not all(isinstance(kind, str) for kind in value):
        problems.append(
            problem(
                origin, 'references.kinds', 'holds a list of kinds, such as kinds = ["source", "assumption"]'
            )
        )
        return out
    wrong = False
    for k, kind in enumerate(value):
        if kind not in REFERENCE_KINDS:
            listed = ', '.join(REFERENCE_KINDS)
            message = f'names {kind}, which is not a kind of reference; the kinds are {listed}'
            problems.append(problem(origin, 'references.kinds', message))
            wrong = True
        elif kind in value[:k]:
            problems.append(problem(origin, 'references.kinds', f'names {kind} twice'))
            wrong = True
    if not wrong and 'assumption' not in value:
        message = 'keeps "assumption": a value that rests on an assumption shows it'
        problems.append(problem(origin, 'references.kinds', message))
        wrong = True
    out['references_kinds'] = None if wrong else tuple(value)
    return out


def _read_places(found, origin, problems):
    """((name, column, row or None), …) of `[place]`, with the problems of its values."""
    places = []
    for name, value in found.items():
        key = f'place.{name}'
        if not isinstance(value, dict):
            problems.append(problem(origin, key, 'is a table, such as {column = 1, row = 2}'))
            continue
        unknown(value, PLACE_KEYS, origin, problems, f'{key}.')
        ok = True
        if 'column' not in value:
            problems.append(problem(origin, key, 'has no column: write {column = 1}'))
            ok = False
        for part in PLACE_KEYS:
            if part in value and not _whole(value[part]):
                problems.append(problem(origin, f'{key}.{part}', 'is a whole number of 1 or more'))
                ok = False
        if ok and not set(value) - set(PLACE_KEYS):
            places.append((name, value['column'], value.get('row')))
    return tuple(places)


def _read_groups(found, origin, problems):
    """((label, (name, …)), …) of `[group]`, with the problems of its lists: a group without a label or
    without a name, and a name that two groups name."""
    groups, given = [], {}
    for label, value in found.items():
        key = f'group.{label}'
        if not label.strip():
            problems.append(problem(origin, key, 'a group has a label: write "Label" = ["a", "b"]'))
            continue
        listed = names_of(value, key, origin, problems)
        if listed == ():
            problems.append(problem(origin, key, 'names no thing'))
            continue
        for name in listed or ():
            if name in given:
                problems.append(problem(origin, key, f'names {name}, which group.{given[name]} also names'))
            given.setdefault(name, label)
        if listed is not None:
            groups.append((label, listed))
    return tuple(groups)


def _read_states(found, origin, problems):
    """((name, ((var, place), …)), …) of the tables `[state.<name>]`, with the problems of their
    values."""
    states = []
    listed = ', '.join(f'"{name}"' for name in STATE_PLACES)
    for name, value in found.items():
        key = f'state.{name}'
        if not isinstance(value, dict):
            problems.append(problem(origin, key, f'is a table, [state.{name}], such as phase = "inside"'))
            continue
        own = []
        for var, where in value.items():
            if where not in STATE_PLACES:
                problems.append(problem(origin, f'{key}.{var}', f'is one of {listed}'))
                continue
            own.append((var, where))
        states.append((name, tuple(own)))
    return tuple(states)


def _read_symbols(found, origin, problems):
    """{symbols, subscripts} of a file (D-54), the fields of `Style`: ((name, ((member, symbol), …)),
    …) of the tables `[symbol.<name>]`, each symbol as written, and ((name, subscript), …) of
    `[subscript]`, with the problems of their values: a value that is not a table where a table goes,
    no symbol (`symbols.parse`) or no subscript (`symbols.parse_tag`)."""
    from . import symbols as made

    tables = []
    for name, value in _tables(found, 'symbol').items():
        key = f'symbol.{name}'
        if not isinstance(value, dict):
            problems.append(problem(origin, key, f'is a table, [symbol.{name}], such as stored = "S_r"'))
            continue
        own = []
        for member, written in value.items():
            try:
                made.parse(written)
            except ValueError as exc:
                problems.append(problem(origin, f'{key}.{member}', str(exc)))
                continue
            own.append((member, written))
        tables.append((name, tuple(own)))
    subscripts = []
    for name, written in _tables(found, 'subscript').items():
        try:
            subscripts.append((name, made.parse_tag(written)))
        except ValueError as exc:
            problems.append(problem(origin, f'subscript.{name}', str(exc)))
    return {'symbols': tuple(tables), 'subscripts': tuple(subscripts)}


def things_of(model):
    """The things of a model (`things.Things`): a `Things` as it is, else those of a compiled model."""
    from .things import Things

    return model if isinstance(model, Things) else Things(model)


def templates_of(found):
    """The names of the templates of a model (`Things`): each, also one without a member, which is
    still a name."""
    from ..model.semantic import DeclaredTemplate

    return {path for path, entity in found.entities.items() if isinstance(entity, DeclaredTemplate)}


def _on_map(origin, key, name, found, templates, shown, out):
    """The cards that a name stands for when the picture draws one of them, else [] with the problem:
    a name that is no template or thing, a template without a member, or a name that `layout.hide`
    hides."""
    entries = expand(name, found)
    if name not in templates and name not in found.cards:
        out.append(problem(origin, key, f'{name} is not a template or a thing'))
    elif not entries:
        out.append(problem(origin, key, f'{name} is not on the map: it has no member'))
    elif not shown & set(entries):
        out.append(problem(origin, key, f'{name} is not on the map: layout.hide hides it'))
    else:
        return entries
    return []


def check(style, model):
    """The problems of a picture against its model (a `Compiled`, or its `Things`):
    - `hide` names templates and things (a member too);
    - `[role]` names templates and things too, drawn or not, and gives a thing one role at most, by its
      own name or by its template's (`_check_roles`);
    - `[icon]`, `[place]`, `[group]` and `[state]` name templates and things that the picture draws;
    - two things are never in one cell of `[place]`, and a thing is in one group at most;
    - no thing has a row between the rows of two things of a group that it is not in, in their column
      (`_between`): the frame of the group would hold it;
    - no thing of a group has a row above the row of a thing of an earlier group in their column
      (`_above`): the frames go down in the order of `[group]`;
    - each var of `[state.<name>]` is a named state of each thing that the name stands for;
    - `[stocks]` names templates and things that the picture draws, and each of its lists names stocks
      and tallies of each thing that the name stands for (`stock_names`);
    - `[symbol]` and `[subscript]` hold with the model (`_check_symbols`);
    - `[triggers]` names templates and things that the picture draws, each with an event;
    - `[equations] things` names templates and things that the picture draws."""
    found = things_of(model)
    out = []
    templates = templates_of(found)
    for name in style.hide:
        if name not in templates and name not in found.cards:
            out.append(problem(style.origin, 'layout.hide', f'{name} is not a template or a thing'))
    out += _check_roles(style, found, templates)
    shown = set(drawn(style, found))
    for icon, names in style.icons:
        for name in names:
            _on_map(style.origin, f'icon.{icon}', name, found, templates, shown, out)
    for name, _, _ in style.places:
        _on_map(style.origin, f'place.{name}', name, found, templates, shown, out)
    # Two things in one cell: the later name in the file has the problem.
    taken = {}
    places = place_of(style, found)
    for name, _, _ in style.places:
        for entry in expand(name, found):
            cell = places.get(entry)
            if cell is None or cell[1] is None or _placer(style, found, entry) != name:
                continue
            other = taken.setdefault(cell, entry)
            if other != entry:
                message = f'puts {entry} in column {cell[0]}, row {cell[1]}, where {other} is'
                out.append(problem(style.origin, f'place.{name}', message))
    # A thing between two things of a group in their column, or a thing of a group above a thing of an
    # earlier group in their column: one problem for each such thing.
    groups = groups_of(style, found)
    for name, _, _ in style.places:
        for entry in expand(name, found):
            cell = places.get(entry)
            if cell is None or cell[1] is None or _placer(style, found, entry) != name:
                continue
            between, above = _between(entry, cell, groups, places), _above(entry, cell, groups, places)
            if between is not None:
                label, first, last = between
                message = (
                    f'puts {entry} in column {cell[0]}, row {cell[1]}, between {first} and {last} of '
                    f'group.{label}: the frame of a group holds only its own things'
                )
            elif above is not None:
                label, earlier, other, row = above
                message = (
                    f'puts {entry} of group.{label} in column {cell[0]}, row {cell[1]}, above {other} of '
                    f'group.{earlier} at row {row}: the frames go down in the order of [group]'
                )
            else:
                continue
            out.append(problem(style.origin, f'place.{name}', message))
    member = {}
    for label, names in style.groups:
        for name in names:
            for entry in _on_map(style.origin, f'group.{label}', name, found, templates, shown, out):
                other = member.setdefault(entry, label)
                if other != label:
                    message = f'puts {entry} in this group, but group.{other} has it'
                    out.append(
                        problem(style.origin, f'group.{label}', f'{message}: a thing is in one group at most')
                    )
    for name, own in style.states:
        entries = _on_map(style.origin, f'state.{name}', name, found, templates, shown, out)
        for var, _ in own:
            lacking = [entry for entry in entries if var not in named_states(found, entry)]
            if lacking:
                message = f'{var} is not a named state of {lacking[0]}'
                out.append(problem(style.origin, f'state.{name}.{var}', message))
    for name, listed in style.stock_order:
        key = f'stocks.{name}'
        entries = _on_map(style.origin, key, name, found, templates, shown, out)
        for stock in listed:
            lacking = [entry for entry in entries if stock not in stock_names(found, entry)]
            if lacking:
                owner = name if name in templates else lacking[0]
                message = f'names {stock}, which is not a stock or a tally of {owner}'
                out.append(problem(style.origin, key, message))
    for level, names in style.triggers:
        for name in names:
            entries = _on_map(style.origin, f'triggers.{level}', name, found, templates, shown, out)
            entries = [entry for entry in entries if entry in shown]
            lacking = [entry for entry in entries if not found.events(entry)]
            if lacking:
                which = name if len(lacking) == len(entries) else lacking[0]
                out.append(problem(style.origin, f'triggers.{level}', f'{which} has no event'))
    for name in style.equations:
        _on_map(style.origin, 'equations.things', name, found, templates, shown, out)
    out += _check_symbols(style, found, templates, shown)
    return out


def _check_roles(style, found, templates):
    """The problems of `[role]` against the model: a name that is no template or thing, and a thing
    that two roles give a role, by its own name and by its template's (the later role in the file has
    the problem)."""
    out, given = [], {}
    for role, names in style.roles:
        key = f'role.{role}'
        for name in names:
            if name not in templates and name not in found.cards:
                out.append(problem(style.origin, key, f'{name} is not a template or a thing'))
                continue
            for entry in expand(name, found):
                other = given.setdefault(entry, role)
                if other != role:
                    message = (
                        f'gives {entry} this role, but role.{other} gives it its role: a thing plays one '
                        'role at most'
                    )
                    out.append(problem(style.origin, key, message))
    return out


def _check_symbols(style, found, templates, shown):
    """The problems of `[symbol]` and `[subscript]` against the model (D-54):
    - each name is a template or a thing that the picture draws, and each member of `[symbol.<name>]`
      is a value, a flow or an event of it that has a symbol (`symbols.lacking`);
    - a template's symbol has no subscript, and `[subscript]` names no template;
    - two cards never have one subscript, and two members never have one symbol of the file, or an
      event's count (`symbols.clashes`): the later name in the file has the problem."""
    from . import symbols as made

    out = []
    for name, own in style.symbols:
        key = f'symbol.{name}'
        entries = _on_map(style.origin, key, name, found, templates, shown, out)
        for member, written in own:
            if name in templates and made.parse(written).sub:
                message = "a template's symbol has no subscript; each member adds its own"
                out.append(problem(style.origin, f'{key}.{member}', message))
            reasons = (made.lacking(found, entry, member, name) for entry in entries)
            reason = next((item for item in reasons if item is not None), None)
            if reason is not None:
                out.append(problem(style.origin, f'{key}.{member}', reason))
    given = {}
    for name, written in style.subscripts:
        key = f'subscript.{name}'
        if name in templates:
            message = f'{name} is a template; give each member its own subscript'
            out.append(problem(style.origin, key, message))
        elif _on_map(style.origin, key, name, found, templates, shown, out):
            if written in given:
                out.append(problem(style.origin, key, f'{written} is also the subscript of {given[written]}'))
            given.setdefault(written, name)
    out += [
        problem(style.origin, key, message)
        for key, message in made.clashes(found, style, drawn(style, found))
    ]
    return out


def _between(entry, cell, groups, places):
    """(label, above, below) of the first group (`groups_of`) that `entry`, at `cell` (column, row), is not
    in, and whose things `above` and `below` have rows in that column, one before the row of `entry` and
    one after it; None when there is no such group."""
    column, row = cell
    for label, members in groups:
        if entry in members:
            continue
        rows = sorted(
            (places[m][1], m)
            for m in members
            if m in places and places[m][0] == column and places[m][1] is not None
        )
        above = [m for r, m in rows if r < row]
        below = [m for r, m in rows if r > row]
        if above and below:
            return label, above[-1], below[0]
    return None


def _above(entry, cell, groups, places):
    """(its group, the earlier group, that group's thing, its row) when `entry`, at `cell` (column,
    row), is in a group (`groups_of`) and a group before it in `[group]` has a thing with a later row in
    that column: the first such group, and its thing with the nearest row. None otherwise."""
    column, row = cell
    for k, (label, members) in enumerate(groups):
        if entry not in members:
            continue
        for earlier, others in groups[:k]:
            rows = sorted(
                (places[m][1], m)
                for m in others
                if m in places and places[m][0] == column and places[m][1] is not None
            )
            below = [(r, m) for r, m in rows if r > row]
            if below:
                return label, earlier, below[0][1], below[0][0]
        return None
    return None


def of(model, path=None):
    """The picture of a model (a `Compiled`), read and checked: the stylesheet at `path` when it is
    given, else the model's own `style.toml` (`beside`: a variant's own, else its package's), or an
    empty picture when there is none. A file with a problem, or a `path` that is no file, raises
    `StyleError`."""
    return checked(model, STYLE_FILE, read, check, Style(), path)


def expand(name, found):
    """The cards that a name of the stylesheet stands for: the card itself, or the card of each
    member of a template, in the order of the cards."""
    if name in found.cards:
        return [name]
    return [card.id for card in found.cards.values() if card.kind != 'entity' and card.template == name]


def hidden_lines(style, found):
    """The cards that `hide` hides: each that it names, and each card of a member of a template that
    it names."""
    names = set(style.hide)
    return {card.id for card in found.cards.values() if card.id in names or card.shown_template in names}


def drawn(style, found):
    """The cards that the map draws, in their order: each that `hide` does not hide."""
    hide = hidden_lines(style, found)
    return [card for card in found.cards if card not in hide]


def roles_of(style, found):
    """{card: its role} of each card that `[role]` names, itself or by its template: who plays it. A
    checked file gives a thing one role at most (`check`); in another, its own name wins."""
    return _own_or_template({name: role for role, names in style.roles for name in names}, found)


def icon_of(style, found):
    """{card: its icon}: the icon that `[icon]` gives the card, else its template's, else its role's
    (`roles_of`, `ROLE_ICONS`), else None: a thing without a role, or with a role that has no icon, has
    no icon."""
    given = {name: icon for icon, names in style.icons for name in names}
    roles = roles_of(style, found)
    return {
        card.id: given.get(card.id) or given.get(card.shown_template) or ROLE_ICONS.get(roles.get(card.id))
        for card in found.cards.values()
    }


def states_of(value):
    """The states of a value whose type is an enum (a named state, or an enum input), in the order of
    its type; None for any other value, and for no value."""
    from ..model.semantic import EnumOf

    found = getattr(value, 'type', None)
    return tuple(found.members) if isinstance(found, EnumOf) else None


def named_states(found, card):
    """The names of the named states of a card (`Things.machines`), in written order."""
    return [value.name for value in found.machines(card)]


def stock_names(found, card):
    """The names of the stocks and tallies of a card (`Things.stocks`), in written order."""
    return [value.name for value in found.stocks(card)]


def _placer(style, found, entry):
    """The name of `[place]` whose place a card takes: its own, else its template's, or None."""
    own = {name for name, _, _ in style.places}
    if entry in own:
        return entry
    template = found.cards[entry].shown_template
    return template if template in own else None


def place_of(style, found):
    """{card: (column, row or None)} of each card that the picture draws and that `[place]` places:
    its own place, else its template's. A template with a row places its members on that row and the
    rows that follow it, in the order of the cards; each member with a place of its own takes that
    place instead."""
    given = {name: (column, row) for name, column, row in style.places}
    hidden = hidden_lines(style, found)
    out, rows = {}, {}
    for entry in found.cards:
        name = _placer(style, found, entry)
        if name is None or entry in hidden:
            continue
        column, row = given[name]
        if name != entry and row is not None:
            row = rows.get(name, row)
            rows[name] = row + 1
        out[entry] = (column, row)
    return out


def _own_or_template(given, found):
    """{card: the value that `given` names for it: its own, else its template's}."""
    out = {}
    for card in found.cards.values():
        value = given.get(card.id, given.get(card.shown_template))
        if value is not None:
            out[card.id] = value
    return out


def trigger_levels(style, found):
    """{card: its level of `[triggers]`} of each card that `[triggers]` names, itself or by its
    template (D-56): the card's own level wins over its template's, also when the two are in other
    lists."""
    return _own_or_template({name: level for level, names in style.triggers for name in names}, found)


def equation_settings(style):
    """What `[equations]` and `[references]` choose (D-53, D-55), with the defaults: `depth`, `width`,
    `lines`, `tags`, `symbols`, `checks`, `instances`, `references` (whether the marks and the list
    show) and `kinds` (the kinds of entry of the list, in the order of `REFERENCE_KINDS`)."""
    found = {
        'depth': style.equation_depth,
        'width': style.equation_width,
        'lines': style.equation_lines,
        **{name: getattr(style, f'equation_{name}') for name in EQUATION_FLAGS},
        'instances': style.equation_instances,
    }
    defaults = {
        'depth': DEFAULT_DEPTH,
        'width': DEFAULT_PANEL_WIDTH,
        'lines': DEFAULT_PANEL_LINES,
        **EQUATION_FLAGS,
        'instances': INSTANCES[0],
    }
    out = {key: defaults[key] if value is None else value for key, value in found.items()}
    out['references'] = bool(style.references_show)
    kinds = REFERENCE_KINDS if style.references_kinds is None else style.references_kinds
    out['kinds'] = [kind for kind in REFERENCE_KINDS if kind in kinds]
    return out


def groups_of(style, found):
    """[(label, [card, …])]: each group of `[group]` in the order of the file, with the cards that it
    names and that the picture draws, in the order of the cards. A template stands for each of its
    members."""
    shown = set(drawn(style, found))
    out = []
    for label, names in style.groups:
        named = {entry for name in names for entry in expand(name, found)}
        out.append((label, [entry for entry in found.cards if entry in named and entry in shown]))
    return out


def state_places(style, found):
    """{card: {var: place}} of each card that `[state]` names, itself or by its template: the place of
    each of its state machines. The card's own place for a var wins over its template's."""
    given = {name: dict(own) for name, own in style.states}
    out = {}
    for card in found.cards.values():
        places = {**given.get(card.shown_template, {}), **given.get(card.id, {})}
        if places:
            out[card.id] = places
    return out


def stock_orders(style, found):
    """{card: (stock, …)} of each card that `[stocks]` names, itself or by its template (D-52): the
    stocks and tallies that its card shows, in their order. The card's own list wins whole over its
    template's."""
    return _own_or_template(dict(style.stock_order), found)


# ---- the files of a model -------------------------------------------------------------------------


def origin_of(model):
    """The entry file of a compiled model (the last file that its declared model reads), or None for
    a model of one text."""
    files = model.declared.files
    return Path(files[-1][0]) if files else None


def folders(origin):
    """The folders that hold the files of the model file `origin` (`style.toml`, `brief.toml`), in the
    order in which they are looked up: the folder of the file, which is a variant's own folder for a
    variant, then the folder of its package (`napkin.paths.package_of`) when that is another folder.
    It reads no file."""
    path = Path(origin)
    return list(dict.fromkeys(f for f in (path.parent, paths.package_of(path)) if f is not None))


def lookup(origin, name):
    """The file `name` of the model file `origin`: the one in the first of its `folders` that holds it,
    or None. The file that is found is the whole file: a variant's own file replaces its package's, and
    nothing of the two merges."""
    return next((folder / name for folder in folders(origin) if (folder / name).is_file()), None)


def beside(model, name):
    """The path of the file `name` of a compiled model (`lookup`): a variant's own, else its package's;
    the path beside the model's file when neither folder holds it; None for a model of one text."""
    origin = origin_of(model)
    if origin is None or not origin.is_file():
        return None
    return lookup(origin, name) or origin.with_name(name)


# The files read and checked, by their path, their revision and the model's: a Style or a Brief, or the
# StyleError of a file with a problem.
CHECKED = OrderedDict()


def checked(model, name, reader, checker, empty, path=None):
    """The file `name` of a compiled model (`beside`), or the file at `path` when it is given, read and
    checked (`reader`, `checker`); `empty` when the model has no such file. A file with a problem, or a
    `path` that is no file, raises `StyleError`. Each revision of a file is read once for each model:
    the key names the file that was read and the model's hash."""
    if path is not None:
        path = Path(path)
        if not path.is_file():
            raise StyleError([problem(str(path), None, 'there is no such file')])
    else:
        path = beside(model, name)
        if path is None or not path.is_file():
            return empty
    status = path.stat()
    key = (str(path), status.st_mtime_ns, status.st_size, model.model_hash)
    if key not in CHECKED:
        try:
            found = reader(path.read_text(encoding='utf-8'), str(path))
            problems = checker(found, model)
            CHECKED[key] = StyleError(problems) if problems else found
        except StyleError as exc:
            CHECKED[key] = exc
        while len(CHECKED) > 64:
            CHECKED.popitem(last=False)
    found = CHECKED[key]
    if isinstance(found, StyleError):
        raise found
    return found


__all__ = [
    'DIRECTIONS',
    'EQUATIONS_KEYS',
    'EQUATION_FLAGS',
    'EQUATION_RANGES',
    'ICONS',
    'INSTANCES',
    'LAYOUT_KEYS',
    'LAYOUT_RANGES',
    'PLACE_KEYS',
    'REFERENCES_KEYS',
    'REFERENCE_KINDS',
    'ROLE',
    'ROLE_ICONS',
    'STATE_PLACES',
    'STOCK_KINDS',
    'STYLE_FILE',
    'STYLE_TABLES',
    'TRIGGERS_KEYS',
    'TRIGGER_LEVELS',
    'TRIGGER_RANGES',
    'Style',
    'StyleError',
    'beside',
    'check',
    'checked',
    'drawn',
    'equation_settings',
    'expand',
    'folders',
    'groups_of',
    'hidden_lines',
    'icon_of',
    'lookup',
    'named_states',
    'names_of',
    'of',
    'origin_of',
    'place_of',
    'problem',
    'read',
    'roles_of',
    'state_places',
    'states_of',
    'stock_names',
    'stock_orders',
    'table',
    'templates_of',
    'things_of',
    'trigger_levels',
    'unknown',
]
