"""The symbols of the picture's equations (D-54, `napkin/draw/symbols.py`): the grammar of a symbol, the
symbols that the model's names make, and the symbols and subscripts that `style.toml` gives.

The synthetic models of the tests write their own generic names, and each expectation follows from
the rule of D-54 that it names, never from a list of the symbols that the code makes. The catalogue's
models wait for stage M (`test_catalogue.py`), with properties only.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import unicodedata
from pathlib import Path

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from napkin.draw import style
from napkin.draw import symbols as made
from napkin.draw.symbols import Symbol, copies, members, parse, symbols, tags
from napkin.draw.things import Things
from napkin.model import semantic as sem
from tests.draw.models import compiled

ROOT = Path(__file__).resolve().parents[2]

# The kinds of value that have a symbol, and the class of each (D-54): an upper-case Latin letter, a
# lower-case Latin letter, or a lower-case Greek letter. A flow is lower and an event's base is τ.
UPPER, LOWER, GREEK = ('stock', 'tally', 'state'), ('formula',), ('input', 'fixed')
# The Greek letter of an input or a fixed value by its initial, as D-54 lists it; the other initials
# keep their Latin letter.
SPEC_GREEK = dict(zip('abgdezhtiklmnxprsfco', 'αβγδεζηθικλμνξπρσφχω', strict=True))
SUBSCRIPT = re.compile(r'[A-Za-z0-9]+(,[A-Za-z0-9]+)*')


# ---- the grammar of a symbol ---------------------------------------------------------------------


@pytest.mark.parametrize(
    ('written', 'base', 'prime', 'sub'),
    [
        ('W_s', 'W', False, 's'),
        ('x', 'x', False, ''),
        ('delta_s', 'δ', False, 's'),
        ('δ_s', 'δ', False, 's'),
        ('Delta', 'Δ', False, ''),
        ("W'_s,w", 'W', True, 's,w'),
        ("omega'", 'ω', True, ''),
        ('pi_12', 'π', False, '12'),
        ('P_abcdefghij', 'P', False, 'abcdefghij'),
    ],
)
def test_a_symbol_is_a_letter_or_a_greek_name_a_prime_and_a_subscript(written, base, prime, sub):
    found = parse(written)
    assert (found.base, found.prime, found.sub) == (base, prime, sub)
    # The plain text writes the Greek letter, and reads back to the same symbol.
    assert parse(found.text()) == found


@pytest.mark.parametrize(
    ('written', 'match'),
    [
        ('', 'not a symbol'),
        ('WW', 'not a symbol'),
        ('W_', 'not a symbol'),
        ('W__s', 'not a symbol'),
        ("W''", 'not a symbol'),
        ("W_s'", 'not a symbol'),
        ('W_s,', 'not a symbol'),
        ('W_,s', 'not a symbol'),
        ('W_s w', 'not a symbol'),
        ('W_é', 'not a symbol'),
        ('W^2', 'not a symbol'),
        ('_s', 'not a symbol'),
        ('1', 'not a symbol'),
        ('deltas', 'not a symbol'),
        ('δδ', 'not a symbol'),
        # A capital Greek letter whose shape is a Latin letter is written as that letter.
        ('Alpha', 'the shape of A'),
        ('Rho_s', 'the shape of P'),
        ('omicron', 'the shape of o'),
        ('P_abcdefghijk', '13 characters'),
        (3, 'is a symbol'),
        (None, 'is a symbol'),
    ],
)
def test_anything_else_is_not_a_symbol(written, match):
    with pytest.raises(ValueError, match=match):
        parse(written)


@pytest.mark.parametrize('written', ['s', 'n2', 'North', 'abcdefghij'])
def test_a_subscript_is_letters_and_digits(written):
    assert made.parse_tag(written) == written


@pytest.mark.parametrize('written', ['', 's,w', 's_w', 'é', 'abcdefghijk', 3, None])
def test_anything_else_is_not_a_subscript(written):
    with pytest.raises(ValueError, match='is a subscript'):
        made.parse_tag(written)


def test_the_text_the_latex_and_the_parts_of_a_symbol():
    # D-54's own examples.
    assert Symbol('W', False, 's').text() == 'W_s' and Symbol('δ', False, 's').text() == 'δ_s'
    assert Symbol('W', False, 's').latex() == 'W_{s}'
    assert Symbol('δ', False, 's').latex() == r'\delta_{s}'
    assert Symbol('W', True, 's').latex() == "W'_{s}"
    assert Symbol('W', True, 's,w').parts() == ('W', "'", 's,w')
    assert Symbol('x').text() == Symbol('x').latex() == 'x'
    # An event's count is N with the same subscript, and no prime.
    assert Symbol('τ', True, 'a,e').counted() == Symbol('N', False, 'a,e')


LETTERS = st.sampled_from([*'abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ', *made.GREEK.values()])
PARTS = st.lists(st.text('abcXYZ019', min_size=1, max_size=3), max_size=3)


@settings(derandomize=True, max_examples=300, deadline=None)
@given(LETTERS, st.booleans(), PARTS)
def test_a_symbol_reads_back_from_its_text_and_its_greek_name(base, prime, parts):
    symbol = Symbol(base, prime, ','.join(parts))
    if len(symbol.text()) <= made.LONGEST:
        assert parse(symbol.text()) == symbol
    names = {letter: name for name, letter in made.GREEK.items()}
    written = names.get(base, base) + symbol.text()[1:]
    if len(written) <= made.LONGEST:
        assert parse(written) == symbol
    # The LaTeX has the subscript in braces after the base, and a Greek letter by its name.
    latex = symbol.latex()
    assert latex.endswith(f'_{{{symbol.sub}}}') if symbol.sub else '_' not in latex
    assert latex.startswith('\\') == (base in names)


def test_the_latex_names_each_greek_letter_once_and_by_its_own_name():
    # Each Greek base has a LaTeX name of its own, and that name is the letter's Unicode name (ε and φ
    # by their shapes, `varepsilon` and `varphi`; Unicode writes lambda as LAMDA).
    latex = [Symbol(letter).latex() for letter in made.GREEK.values()]
    assert len(set(latex)) == len(latex)
    for letter in made.GREEK.values():
        name = unicodedata.name(letter).split()[-1].lower().replace('lamda', 'lambda')
        assert Symbol(letter).latex().lower().lstrip('\\').removeprefix('var') == name
        assert unicodedata.name(letter).startswith('GREEK')


# ---- the symbols of a model -------------------------------------------------------------------------


def world(text, tables=None):
    """The things of a model of the text."""
    return Things(compiled(text, tables))


# Three cards whose names start with one letter, a template with two members, and a table of two rows.
# `supply` holds values of each kind, and values with one initial: one with a second word, and two
# without; an event whose subscript would give its count the symbol of a value; and a text.
DECLARATIONS = """\
supply:
    water: people = 100 people in [0 people,]
    waste: people = 0 people in [0 people,]
    heat: people = 1 people
    hot_water: people = 1 people
    humidity: people = 1 people
    nurses: people = 3 people
    nurses_beds: people = 3 people
    phase: enum[CALM, BUSY] = CALM
    input delay: h = 2 h in [1 h, 9 h]
    input capacity: people = 4 people
    input window: h = 4 h in [1 h, 9 h]
    demand = formula(2 * this.water)
    input label: text = "A supply"
    flow drain: this.water -> this.waste
        request = this.water / (10 h)
    breach = event():
        when t >= this.delay:
            this.breach.start()
            reset when false
        after 0 h:
            this.phase = BUSY
    burst = event():
        after 0 h:
            this.heat -= 1 people
            this.hot_water += 1 people
            this.humidity += 1 people
            this.nurses += 1 people
            this.nurses_beds += 1 people

sewer:
    sludge: people = 3 people in [0 people,]
    flow settle: this.sludge -> SINK
        request = this.sludge / (10 h)

Utility:
    stored: people = 10 people in [0 people,]
    input rate: people/h = 1 people/h in [0 people/h, 2 people/h]
    flow use: this.stored -> SINK
        request = this.rate

north: Utility

south: Utility

Pump:
    pressure: people = 10 people in [0 people,]
    flow bleed: this.pressure -> SINK
        request = this.pressure / (10 h)

pumps: Pump from "pumps.csv"

supply.burst.start()
"""
TABLES = {'pumps.csv': 'id\na\nb\n'}


@pytest.fixture(scope='module')
def model():
    return world(DECLARATIONS, TABLES)


def sheet_of(text):
    return style.read(text)


def keys_of(found, cards):
    """The keys that have a symbol, from the model's own parts: each value of a kind with a symbol,
    each flow and each event of each member of the cards."""
    out = []
    for card in cards:
        for member, _ in copies(found, card):
            for part in found.parts(card):
                if (
                    isinstance(part, sem.DeclaredValue) and found.kind(part) in (*UPPER, *LOWER, *GREEK)
                ) or isinstance(part, (sem.DeclaredFlow, sem.DeclaredLegs, sem.DeclaredEvent)):
                    out.append(f'{member}.{part.name}')
    return out


def events_of(found):
    return {
        f'{member}.{event.name}'
        for card in found.cards
        for member, _ in copies(found, card)
        for event in found.events(card)
    }


def taken_texts(found, made_symbols):
    """Every text that the symbols take: each symbol's, and the count of each event."""
    events = events_of(found)
    counts = [Symbol('N', False, symbol.sub).text() for key, symbol in made_symbols.items() if key in events]
    return [symbol.text() for symbol in made_symbols.values()] + counts


def authored(found, sheet):
    """The keys that `[symbol]` names: each member of a table, of each member of the cards that its
    name stands for."""
    out = set()
    for name, own in sheet.symbols:
        for card in style.expand(name, found):
            out |= {f'{member}.{item}' for member, _ in copies(found, card) for item, _ in own}
    return out


def well_formed(symbol):
    """A base that is one letter, Latin or Greek, a prime or none, and a subscript of letters and
    digits with commas between its parts."""
    base = symbol.base
    latin = len(base) == 1 and base.isascii() and base.isalpha()
    greek = len(base) == 1 and unicodedata.name(base, '').startswith('GREEK')
    return (
        (latin or greek)
        and isinstance(symbol.prime, bool)
        and (not symbol.sub or SUBSCRIPT.fullmatch(symbol.sub))
    )


def is_tag_of(tag, name):
    """Whether a made tag is a start of each word of a name, in order, then a number or none."""
    found = name.split('_')

    def fits(rest, words):
        if not words:
            return rest == '' or (rest.isdigit() and int(rest) >= 2)
        word = words[0]
        return any(rest.startswith(word[:k]) and fits(rest[k:], words[1:]) for k in range(1, len(word) + 1))

    return fits(tag, found)


def check_symbols(found, sheet, made_symbols, cards=None):
    """The properties of the symbols of a model (D-54): every key of the cards has one; no two symbols,
    or an event's count, are one; each follows the grammar; each made symbol has the base of its class
    and initial, and its subscript starts with its card's tag (an event's then with its initial, and a
    row's ends with its number); each symbol of the file is as written or has its template's base."""
    cards = style.drawn(sheet, found) if cards is None else cards
    keys = keys_of(found, cards)
    assert sorted(made_symbols) == sorted(keys)
    texts = taken_texts(found, made_symbols)
    assert len(texts) == len(set(texts))
    assert all(well_formed(symbol) for symbol in made_symbols.values())
    tag = tags(found, sheet, cards)
    assert len(set(tag.values())) == len(tag)
    given_tags = dict(sheet.subscripts)
    for card in cards:
        assert tag[card] == given_tags[card] if card in given_tags else is_tag_of(tag[card], card)
    events, own = events_of(found), authored(found, sheet)
    for card in cards:
        kinds = dict(members(found, card))
        for member, number in copies(found, card):
            for name, kind in kinds.items():
                key = f'{member}.{name}'
                symbol = made_symbols[key]
                parts = symbol.sub.split(',')
                if number is not None:
                    assert parts[-1] == str(number)
                if key in own:
                    continue
                initial = name[0]
                if key in events:
                    assert symbol.base == made.TIME and parts[1] == initial
                elif kind == 'upper':
                    assert symbol.base == initial.upper()
                elif kind == 'greek':
                    assert symbol.base == SPEC_GREEK.get(initial, made.GREEK_OF.get(initial, initial))
                    assert unicodedata.name(symbol.base).startswith('GREEK SMALL') or symbol.base == initial
                else:
                    assert symbol.base == initial
                assert parts[0] == tag[card] and not symbol.prime


def test_every_member_of_a_drawn_card_has_one_symbol_of_its_own(model):
    found = symbols(model, style.Style())
    check_symbols(model, style.Style(), found)
    # A text has none.
    assert 'supply.label' not in found


def test_the_symbols_are_made_over_the_cards_that_the_picture_draws(model):
    sheet = sheet_of('[layout]\nhide = ["Utility"]\n')
    found = symbols(model, sheet)
    check_symbols(model, sheet, found)
    assert not any(key.startswith(('north.', 'south.')) for key in found)
    # A caller can name the cards, and the keys.
    cards = ['sewer', 'pumps']
    check_symbols(model, style.Style(), symbols(model, style.Style(), cards), cards)
    keys = ['supply.heat', 'supply.humidity', 'supply.breach', 'pumps.b.pressure', 'supply.label']
    some = symbols(model, style.Style(), keys=keys)
    assert set(some) == set(keys) - {'supply.label'}
    texts = taken_texts(model, some)
    assert len(texts) == len(set(texts)) and all(well_formed(symbol) for symbol in some.values())


def test_cards_with_one_initial_have_tags_of_their_own(model):
    """Counterexample: supply, sewer and south have the initial s. Each takes a tag that starts with
    s, and the three tags differ; a card whose initials no other card has keeps its initials."""
    found = tags(model, style.Style())
    names = ('supply', 'sewer', 'south')
    assert len({found[name] for name in names}) == 3
    assert all(found[name].startswith('s') and len(found[name]) > 1 for name in names)
    assert (found['north'], found['pumps']) == ('n', 'p')


def test_names_that_share_their_initials_add_letters_where_they_differ():
    """Counterexample: two names with the same initials and one last word differ in their first word,
    and two others differ soon in their last word only. Each tag adds letters to the word that tells
    the names apart soonest, so the tags stay short."""
    names = ('tools_channel', 'targeting_channel', 'effects_program', 'effect_pool')
    other = world('\n'.join(f'{name}:\n    level: people = 1 people\n' for name in names))
    found = tags(other, style.Style())
    assert len(set(found.values())) == 4
    for name, tag in found.items():
        assert is_tag_of(tag, name) and len(tag) <= 3


def test_values_with_one_initial_in_one_card_have_symbols_of_their_own(model):
    """Counterexample (D-54): heat, hot_water and humidity of one card start with h. The one with a
    second word adds that word's initial to its subscript, the first of the others keeps the card's
    tag, and the last takes a number."""
    found = symbols(model, style.Style())
    tag = tags(model, style.Style())['supply']
    heat, hot, humid = (found[f'supply.{name}'] for name in ('heat', 'hot_water', 'humidity'))
    assert heat.base == hot.base == humid.base == 'H'
    assert heat.sub == tag
    assert hot.sub.split(',') == [tag, 'w']
    assert humid.sub.split(',')[0] == tag and humid.sub.split(',')[1].isdigit()


def test_the_count_of_an_event_is_never_the_symbol_of_a_value(model):
    """Counterexample: nurses_beds clashes with nurses and adds b; the event breach would be τ with the
    subscript of the card and b, whose count is the symbol of nurses_beds. It takes another one."""
    found = symbols(model, style.Style())
    tag = tags(model, style.Style())['supply']
    assert found['supply.nurses_beds'] == Symbol('N', False, f'{tag},b')
    assert found['supply.breach'].counted() != found['supply.nurses_beds']
    assert found['supply.breach'].sub.split(',')[:2] == [tag, 'b']


def test_each_row_of_a_table_adds_its_number(model):
    found = symbols(model, style.Style())
    one, two = found['pumps.a.pressure'], found['pumps.b.pressure']
    assert (one.base, one.sub.rsplit(',', 1)[0]) == (two.base, two.sub.rsplit(',', 1)[0])
    assert (one.sub.rsplit(',', 1)[1], two.sub.rsplit(',', 1)[1]) == ('1', '2')


# ---- the symbols and subscripts of the file ----------------------------------------------------------


def test_a_symbol_of_the_file_is_used_as_written_and_no_made_symbol_is_it(model):
    """Without the file, water has the first symbol of supply's W (the card's tag); with waste = that
    symbol, waste has it and water another one."""
    plain = symbols(model, sheet_of('[subscript]\nsupply = "s"\n'))
    assert plain['supply.water'] == Symbol('W', False, 's')
    sheet = sheet_of('[subscript]\nsupply = "s"\n\n[symbol.supply]\nwaste = "W_s"\nbreach = "T_b"\n')
    assert style.check(sheet, model) == []
    found = symbols(model, sheet)
    check_symbols(model, sheet, found)
    assert found['supply.waste'] == parse('W_s') and found['supply.water'] != parse('W_s')
    # An event's own symbol is its time; its count is N with the same subscript, and no value has it.
    assert found['supply.breach'] == parse('T_b')
    assert parse('N_b') not in found.values()


def test_a_template_s_symbol_is_the_base_of_each_instance_and_an_instance_s_own_wins(model):
    sheet = sheet_of('[symbol.Utility]\nstored = "Q"\nrate = "kappa\'"\n')
    found, tag = symbols(model, sheet), tags(model, sheet)
    check_symbols(model, sheet, found)
    for name in ('north', 'south'):
        assert found[f'{name}.stored'] == Symbol('Q', False, tag[name])
        assert found[f'{name}.rate'] == Symbol('κ', True, tag[name])
    own = sheet_of('[symbol.Utility]\nstored = "Q"\n\n[symbol.south]\nstored = "R_x"\n')
    found, tag = symbols(model, own), tags(model, own)
    check_symbols(model, own, found)
    assert found['south.stored'] == parse('R_x')
    assert found['north.stored'] == Symbol('Q', False, tag['north'])


def test_a_table_adds_the_number_of_each_row_to_its_symbol(model):
    sheet = sheet_of('[symbol.Pump]\npressure = "P\'"\n\n[symbol.pumps]\nbleed = "beta_q"\n')
    found, tag = symbols(model, sheet), tags(model, sheet)
    check_symbols(model, sheet, found)
    for k, row in ((1, 'a'), (2, 'b')):
        assert found[f'pumps.{row}.pressure'] == Symbol('P', True, f'{tag["pumps"]},{k}')
        assert found[f'pumps.{row}.bleed'] == Symbol('β', False, f'q,{k}')


def test_a_subscript_replaces_the_tag_of_its_card(model):
    sheet = sheet_of('[subscript]\nnorth = "se"\npumps = "z"\n')
    found, tag = symbols(model, sheet), tags(model, sheet)
    check_symbols(model, sheet, found)
    assert (tag['north'], tag['pumps']) == ('se', 'z')
    # A made tag is never the subscript of another card: sewer would take se.
    assert tag['sewer'] != 'se' and list(tag.values()).count('se') == 1
    for key, symbol in found.items():
        if key.startswith('north.'):
            assert symbol.sub.split(',')[0] == 'se'


# ---- the same symbols each time ---------------------------------------------------------------------

SCRIPT = 'import json\nfrom tests.draw.test_symbols import busy_symbols\nprint(json.dumps(busy_symbols()))\n'


def busy_symbols():
    """{key: text} of the symbols of the fixture, with a file that gives symbols and subscripts."""
    sheet = sheet_of(
        '[symbol.Utility]\nstored = "Q"\n\n[subscript]\npumps = "z"\n\n[symbol.supply]\nwaste = "W_su"\n'
    )
    return {key: symbol.text() for key, symbol in symbols(world(DECLARATIONS, TABLES), sheet).items()}


def test_the_symbols_are_the_same_for_every_hash_seed():
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
    assert json.loads(found[0]) == busy_symbols()
