"""The symbols of the picture's equations (D-54): one symbol for each value, flow and event of the
cards that the picture draws.

A symbol (`Symbol`) is a base, an optional prime and an optional subscript: `W_s`, `δ_s`, `W'_s,w`.
The base is a Latin letter or a Greek letter (`GREEK`), and the subscript is letters and digits, with
a comma between two parts. The key of a symbol is `entity.member`: the name of the entity, as a `Ref`
names it (an instance's own name, and `set.k` for copy k of a set), then the name of its value, its
flow or its event. A value has a symbol when it is an input, a fixed value, a state, a stock, a tally
or a formula (`CLASSES`); a text and an output have none.

The symbol of an event is the time since it happened, τ by default. Its count is N with the same
subscript (`Symbol.counted`), and the two are symbols of their own: no value has either of them.

`style.toml` can give symbols (`[symbol.<thing or template>]`, `given`) and the subscripts of cards
(`[subscript]`, `tags`). `symbols` makes every other symbol from the model's names, over the cards that
the picture draws:
- The base is the initial of the first word of the member's name (`in_words`): an upper-case Latin
  letter for a stock, a tally and a state; a lower-case Latin letter for a flow and a formula; a
  lower-case Greek letter with that initial for an input and a fixed value (`GREEK_OF`), or the Latin
  letter when no Greek letter fits; τ for an event.
- The subscript starts with the card's tag (`tags`): the initials of the words of its name. Cards
  that share a tag add letters, one at a time, to the word that tells their names apart soonest,
  until no other card has their tag. An instance takes its own tag. The subscript of an event adds
  the initial of the event's first word.
- Two members of one card that would have one symbol: each that has a second word adds that word's
  initial, and then a number from 2 gives the first free symbol (`_candidates`).
- Each copy of a set adds its number: `H_w,1`, `H_w,2`.

The symbols that the file gives come first, and no made symbol is one of them. A thing's own symbol is
used as it is written. The symbol of a template is a base only: each instance adds its subscript, and
an instance's own symbol wins over its template's. A `[subscript]` replaces the tag of its card.
Everything here is deterministic: the order of the cards, of the entities and of the members, and
never the order of a set.
"""

from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass

from ..model.semantic import in_words
from . import style as styles

# The Greek letters of a symbol, by their names in LaTeX: each lower-case letter but omicron, and each
# upper-case letter whose shape is not a Latin letter. The text of a symbol has the letter, and its
# LaTeX the name (`\varepsilon` and `\varphi` are the shapes of ε and φ).
GREEK = {
    'alpha': 'α',
    'beta': 'β',
    'gamma': 'γ',
    'delta': 'δ',
    'epsilon': 'ε',
    'zeta': 'ζ',
    'eta': 'η',
    'theta': 'θ',
    'iota': 'ι',
    'kappa': 'κ',
    'lambda': 'λ',
    'mu': 'μ',
    'nu': 'ν',
    'xi': 'ξ',
    'pi': 'π',
    'rho': 'ρ',
    'sigma': 'σ',
    'tau': 'τ',
    'upsilon': 'υ',
    'phi': 'φ',
    'chi': 'χ',
    'psi': 'ψ',
    'omega': 'ω',
    'Gamma': 'Γ',
    'Delta': 'Δ',
    'Theta': 'Θ',
    'Lambda': 'Λ',
    'Xi': 'Ξ',
    'Pi': 'Π',
    'Sigma': 'Σ',
    'Upsilon': 'Υ',
    'Phi': 'Φ',
    'Psi': 'Ψ',
    'Omega': 'Ω',
}
LATEX = {letter: '\\' + name for name, letter in GREEK.items()}
LATEX.update({'ε': '\\varepsilon', 'φ': '\\varphi'})
# The Greek letters whose shape is a Latin letter, which a symbol writes as that Latin letter.
AS_LATIN = {
    'Alpha': 'A',
    'Beta': 'B',
    'Epsilon': 'E',
    'Zeta': 'Z',
    'Eta': 'H',
    'Iota': 'I',
    'Kappa': 'K',
    'Mu': 'M',
    'Nu': 'N',
    'Omicron': 'O',
    'omicron': 'o',
    'Rho': 'P',
    'Tau': 'T',
    'Chi': 'X',
}
# The Greek letter of an input or a fixed value, by the initial of its name.
GREEK_OF = {
    'a': 'α',
    'b': 'β',
    'g': 'γ',
    'd': 'δ',
    'e': 'ε',
    'z': 'ζ',
    'h': 'η',
    't': 'θ',
    'i': 'ι',
    'k': 'κ',
    'l': 'λ',
    'm': 'μ',
    'n': 'ν',
    'x': 'ξ',
    'p': 'π',
    'r': 'ρ',
    's': 'σ',
    'f': 'φ',
    'c': 'χ',
    'o': 'ω',
    'u': 'υ',
}
# The base of the time since an event and of its count.
TIME, COUNT = 'τ', 'N'
# The class of the symbol of each kind of value: an upper-case Latin letter, a lower-case Latin letter
# or a lower-case Greek letter. A flow is `lower` and an event `event`.
CLASSES = {
    'stock': 'upper',
    'tally': 'upper',
    'state': 'upper',
    'formula': 'lower',
    'input': 'greek',
    'fixed': 'greek',
}
# The most characters of a symbol as the file writes it, and of a subscript of `[subscript]`.
LONGEST = 12
LONGEST_TAG = 10
_BASE = '|'.join(sorted((re.escape(name) for name in (*GREEK, *GREEK.values())), key=len, reverse=True))
WRITTEN = re.compile(rf"(?P<base>{_BASE}|[A-Za-z])(?P<prime>')?(?:_(?P<sub>[A-Za-z0-9]+(?:,[A-Za-z0-9]+)*))?")
TAG = re.compile(r'[A-Za-z0-9]+', re.ASCII)
FORM = (
    "a letter or a Greek name (such as delta), an optional ', and an optional _ with a subscript of "
    'letters, digits and commas, 12 characters at most, such as "W_s", "delta_2" or "S\'_r,1"'
)


@dataclass(frozen=True)
class Symbol:
    """A symbol: its base (a Latin letter or a Greek letter), whether it has a prime, and its subscript
    (letters and digits, a comma between two parts; '' for none)."""

    base: str
    prime: bool = False
    sub: str = ''

    def text(self):
        """The plain text, as `style.toml` writes it with a Greek letter: `W_s`, `δ_s`, `W'_s,w`."""
        return self.base + ("'" if self.prime else '') + (f'_{self.sub}' if self.sub else '')

    def latex(self):
        """The LaTeX: `W_{s}`, `\\delta_{s}`, `W'_{s,w}`."""
        base = LATEX.get(self.base, self.base)
        return base + ("'" if self.prime else '') + (f'_{{{self.sub}}}' if self.sub else '')

    def parts(self):
        """(base, prime, subscript) for the typesetter: the prime is `'` or ''."""
        return self.base, "'" if self.prime else '', self.sub

    def counted(self):
        """The count of an event whose symbol this is: N with the same subscript."""
        return Symbol(COUNT, False, self.sub)

    def under(self, *parts):
        """The symbol with more parts at the end of its subscript."""
        return Symbol(self.base, self.prime, ','.join([*([self.sub] if self.sub else []), *parts]))


def parse(written):
    """The symbol that `style.toml` writes (`WRITTEN`, at most `LONGEST` characters). Anything else
    raises ValueError with the reason."""
    if not isinstance(written, str):
        raise ValueError(f'is a symbol: {FORM}')
    found = WRITTEN.fullmatch(written)
    latin = AS_LATIN.get(re.split(r"['_]", written, maxsplit=1)[0])
    if found is None and latin is not None:
        raise ValueError(
            f'"{written}" is not a symbol: that Greek letter has the shape of {latin}, so write {latin}'
        )
    if found is None:
        raise ValueError(f'"{written}" is not a symbol: write {FORM}')
    if len(written) > LONGEST:
        raise ValueError(f'"{written}" has {len(written)} characters: a symbol has {LONGEST} at most')
    base = found.group('base')
    return Symbol(GREEK.get(base, base), found.group('prime') is not None, found.group('sub') or '')


def parse_tag(written):
    """The subscript of a card that `[subscript]` writes: letters and digits, at most `LONGEST_TAG`.
    Anything else raises ValueError with the reason."""
    if not isinstance(written, str) or TAG.fullmatch(written) is None or len(written) > LONGEST_TAG:
        raise ValueError(f'is a subscript: letters and digits, {LONGEST_TAG} at most, such as "s" or "n2"')
    return written


# ---- the members of a card -------------------------------------------------------------------------


def words(name):
    """The words of a name, in lower case (`in_words`): `water_level` and `waterLevel` are water, level."""
    return in_words(name).lower().split(' ')


def members(entity):
    """(name, class) of each member of an entity that has a symbol, in order: its values (`CLASSES`),
    then its flows (`lower`), then its events (`event`)."""
    out = [(value.name, CLASSES[value.kind]) for value in entity.values if value.kind in CLASSES]
    out += [(flow.name, 'lower') for flow in entity.flows]
    out += [(event.name, 'event') for event in entity.events]
    return out


def lacking(entity, member, name):
    """Why the member `member` of an entity has no symbol, with `name` for the entity (a template or a
    thing of the stylesheet), or None when it has one."""
    if any(found == member for found, _ in members(entity)):
        return None
    value = entity.value(member)
    if value is not None and value.kind == 'text':
        return f'{member} is a text of {name}, which has no symbol'
    if value is not None and value.kind == 'output':
        return f'{member} is an output of {name}, which has no symbol'
    return f'{member} is not a value, a flow or an event of {name}'


def entities_of(model):
    """{entity line: [its entities]}: one entity, or each copy of a set in order."""
    out = {}
    for entity in model.scenario.entities:
        out.setdefault(entity.entry, []).append(entity)
    return out


def _base(name, kind):
    initial = words(name)[0][0]
    if kind == 'upper':
        return initial.upper()
    if kind == 'greek':
        return GREEK_OF.get(initial, initial)
    return TIME if kind == 'event' else initial


def _head(name, kind, tag):
    """The first parts of the subscript of a member: the card's tag, and for an event the initial of
    its first word."""
    return [tag, words(name)[0][0]] if kind == 'event' else [tag]


def _texts(symbol, kind):
    """The texts that a symbol takes: its own, and for an event its count too."""
    return [symbol.text(), symbol.counted().text()] if kind == 'event' else [symbol.text()]


# ---- the tags of the cards -------------------------------------------------------------------------


def _shared(found):
    """The number of letters at the start of each of these words that they all have, and None when
    the words are all one word: nothing tells them apart."""
    if all(word == found[0] for word in found):
        return None
    count = 0
    while all(word is not None and len(word) > count and word[count] == found[0][count] for word in found):
        count += 1
    return count


def _apart(group, names, size):
    """The word of a name that the cards of `group` extend next (`tags`), or None when none can: the
    word whose letters tell their names apart soonest (the fewest shared letters at its start), the
    first on a tie, among those that a card can extend. A lone card, whose tag `[subscript]` gives
    another card, extends its first word that has a letter left."""
    able = {i for card in group for i, word in enumerate(names[card]) if size[card][i] < len(word)}
    if len(group) == 1:
        return min(able, default=None)
    found = []
    for i in sorted(able):
        shared = _shared([names[card][i] if i < len(names[card]) else None for card in group])
        if shared is not None:
            found.append((shared, i))
    return min(found)[1] if found else None


def tags(model, sheet, cards=None):
    """{card: its tag}, for each of `cards` (entity lines; by default the ones that the picture draws),
    in their order. A card that `[subscript]` names has that subscript. Every other card starts with
    the initials of the words of its name (`words`). Then, as long as cards share a tag, or a card has a
    tag of `[subscript]`, each of them adds the next letter of one word (`_apart`), all at once. A card
    whose tag an earlier card still has adds the first number from 2 that gives a new tag."""
    cards = list(styles.drawn(sheet, model) if cards is None else cards)
    given = {name: text for name, text in sheet.subscripts if name in cards}
    made = [card for card in cards if card not in given]
    names = {card: words(card) for card in made}
    size = {card: [1] * len(names[card]) for card in made}
    fixed = set(given.values())

    def tag(card):
        return ''.join(word[:n] for word, n in zip(names[card], size[card]))

    moved = True
    while moved:
        moved = False
        groups = {}
        for card in made:
            groups.setdefault(tag(card), []).append(card)
        for text, group in groups.items():
            if len(group) == 1 and text not in fixed:
                continue
            i = _apart(group, names, size)
            for card in group if i is not None else ():
                if i < len(names[card]) and size[card][i] < len(names[card][i]):
                    size[card][i] += 1
                    moved = True
    every = fixed | {tag(card) for card in made}
    seen, out = set(fixed), {}
    for card in cards:
        if card in given:
            out[card] = given[card]
            continue
        text = tag(card)
        if text in seen:
            number = 2
            while f'{text}{number}' in every:
                number += 1
            text = f'{text}{number}'
            every.add(text)
        seen.add(text)
        out[card] = text
    return out


# ---- the symbols that the file gives --------------------------------------------------------------


def given(model, sheet, cards=None, tag=None):
    """[(key, symbol, where, class)]: the symbols that `[symbol.<name>]` gives the members of `cards`
    (by default the ones that the picture draws), in the order of the file, then of the entity lines
    that a name stands for, then of the copies of a set. `where` is the key of the file,
    `symbol.<name>.<member>`, and `class` the class of the member (`members`). A thing's own symbol is
    as written; for a template, the instance's tag (`tag`, by default `tags`) is its subscript; a copy
    of a set adds its number. An instance's own symbol wins over its template's, and a member that has
    no symbol, or a name that is not on the map, gives nothing (`style.check` reports them)."""
    cards = list(styles.drawn(sheet, model) if cards is None else cards)
    tag = tags(model, sheet, cards) if tag is None else tag
    lines, entities = styles.entity_lines(model), entities_of(model)
    own = {name: dict(found) for name, found in sheet.symbols}
    shown, out, done = set(cards), [], set()
    for name, found in sheet.symbols:
        for member, written in found:
            for card in styles.expand(name, lines, model):
                if card not in shown or (card != name and member in own.get(card, {})):
                    continue
                kinds = dict(members(lines[card]))
                if member not in kinds:
                    continue
                symbol = parse(written)
                if card != name:
                    symbol = Symbol(symbol.base, symbol.prime, tag[card])
                copies = entities[card]
                for entity in copies:
                    key = f'{entity.name}.{member}'
                    if key in done:
                        continue
                    done.add(key)
                    each = symbol.under(str(entity.copy)) if entity.copy is not None else symbol
                    out.append((key, each, f'symbol.{name}.{member}', kinds[member]))
    return out


def clashes(model, sheet, cards=None):
    """[(where, message)]: each key of the file whose symbol (`given`) an earlier one already is, or
    whose count (an event's) is: the later in the file has the problem, once for each key of the file
    (a template's, for its first instance with it)."""
    taken, out = {}, {}
    for key, symbol, where, kind in given(model, sheet, cards):
        mine = [(symbol.text(), 'symbol')]
        if kind == 'event':
            mine.append((symbol.counted().text(), 'count'))
        for text, what in mine:
            other = taken.get(text)
            if other is not None and where not in out:
                start = text if what == 'symbol' else f'its count {text}'
                out[where] = f'{start} is also the {other[1]} of {other[0]}'
        for text, what in mine:
            taken.setdefault(text, (key, what))
    return list(out.items())


# ---- every symbol ----------------------------------------------------------------------------------


def symbols(model, sheet=None, cards=None, keys=None):
    """{key: Symbol} of each member that has a symbol (`members`) of each entity of `cards`, in the
    order of the cards and of their members, with each copy of a set after the other. `sheet` is the
    picture (`style.Style`), by default the model's own (`style.of`); `cards` are entity lines, by
    default the ones that the picture draws, in its order (`style.drawn`). With `keys`, only those
    keys have a symbol, and only their members share the letters of a card (the copies of a set have
    their symbols made together). The file's symbols come first (`given`); each other symbol is the
    first of its candidates that no symbol has (`_candidates`)."""
    sheet = styles.of(model) if sheet is None else sheet
    cards = list(styles.drawn(sheet, model) if cards is None else cards)
    tag = tags(model, sheet, cards)
    fixed = {key: (symbol, kind) for key, symbol, _, kind in given(model, sheet, cards, tag)}
    taken = {text for key, (symbol, kind) in fixed.items() for text in _texts(symbol, kind)}
    wanted = None if keys is None else set(keys)
    entities = entities_of(model)
    out = {}
    for card in cards:
        copies = entities[card]
        found = []
        for name, kind in members(copies[0]):
            names = [f'{entity.name}.{name}' for entity in copies]
            if wanted is None or any(key in wanted for key in names):
                found.append((name, kind, names))
        first = {
            name: Symbol(_base(name, kind), False, ','.join(_head(name, kind, tag[card]))).text()
            for name, kind, names in found
            if names[0] not in fixed
        }
        shared = Counter(first.values())
        for name, kind, names in found:
            if names[0] in fixed:
                out.update((key, fixed[key][0]) for key in names if key in fixed and _wanted(key, wanted))
                continue
            clash = shared[first[name]] > 1 or first[name] in taken
            for parts in _candidates(name, kind, tag[card], clash):
                each = [
                    Symbol(
                        _base(name, kind), False, ','.join(parts if e.copy is None else [*parts, str(e.copy)])
                    )
                    for e in copies
                ]
                texts = [text for symbol in each for text in _texts(symbol, kind)]
                if not any(text in taken for text in texts) and len(set(texts)) == len(texts):
                    break
            taken.update(texts)
            out.update((key, symbol) for key, symbol in zip(names, each) if _wanted(key, wanted))
    return out


def _wanted(key, wanted):
    return wanted is None or key in wanted


def _candidates(name, kind, tag, clash):
    """The subscripts of a made symbol, as lists of parts, in the order that `symbols` tries them: its
    head (`_head`), unless it clashes and the name has a second word; the head with the initial of the
    second word; then the head with 2, 3, … ."""
    head, found = _head(name, kind, tag), words(name)
    second = found[1][0] if len(found) > 1 else None
    if not clash or second is None:
        yield head
    if second is not None:
        yield [*head, second]
    number = 2
    while True:
        yield [*head, str(number)]
        number += 1


__all__ = [
    'CLASSES',
    'COUNT',
    'GREEK',
    'GREEK_OF',
    'LATEX',
    'LONGEST',
    'LONGEST_TAG',
    'TIME',
    'Symbol',
    'clashes',
    'entities_of',
    'given',
    'lacking',
    'members',
    'parse',
    'parse_tag',
    'symbols',
    'tags',
    'words',
]
