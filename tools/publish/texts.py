"""The texts of the summaries: an input's value in the words of its unit, a range of values, how an
event reads, and the cards of one time that an event happens.

A card's text with its braces filled in (`filled`) and the words for who acts (`ACTOR_NAMES`) are the
words of the map (`draw/model_map.py`).
"""

import math

MONEY = {
    'USD2025_bn/yr': 'bn a year',
    'USD2025_bn': 'bn',
    'USD2025_m': 'm',
    'USD2025': '',
    'USD2025/h': ' an hour',
    'USD2025/person-day': ' per person-day',
    'USD2025/person': ' per person',
    'USD2025/L': ' per litre',
}
UNIT_WORDS = {
    'L': 'litres',
    'people/h': 'people an hour',
    'people/day': 'people a day',
    'L/people': 'L per patient',
    'L/day': 'L a day',
    'L/h': 'L an hour',
    'people/case': 'per case',
    'per_unmet_day': 'per day without support',
    'per_h': 'per hour',
    'work_h': 'work-hours',
    'work_h/h': 'work-hours an hour',
    'ratio': 'times',
}
# Unit words that read wrong at exactly one.
SINGULAR = {
    'work-hours an hour': 'work-hour an hour',
    'people an hour': 'person an hour',
}


def _digits(x, significant=4):
    """Plain decimal text with thousands separators, never scientific notation."""
    if x == 0:
        return '0'
    places = max(0, significant - 1 - math.floor(math.log10(abs(x))))
    text = f'{x:,.{places}f}'
    return text.rstrip('0').rstrip('.') if '.' in text else text


def _parts(value, unit, multiplier, switch):
    """Prefix, number and suffix of one input in its authored unit."""
    if switch:
        return '', {0: 'No', 1: 'Yes'}.get(value, _digits(value)), ''
    if unit == 'fraction':
        return ('×', _digits(value), '') if multiplier else ('', _digits(value * 100), '%')
    if unit in MONEY:
        return ('-$' if value < 0 else '$'), _digits(abs(value)), MONEY[unit]
    words = UNIT_WORDS.get(unit, unit)
    # "1 work-hours an hour" reads wrong: exactly one of a counted thing takes the singular.
    if value == 1 and (singular := SINGULAR.get(words)):
        words = singular
    return '', _digits(value), ' ' + words


def input_text(value, unit, *, multiplier=False, switch=False):
    """Display text for one input; the page arranges these strings and does no arithmetic."""
    if value is None:
        return None
    text = ''.join(_parts(value, unit, multiplier, switch))
    if unit == 'h' and 0 < value < 1:
        text += f' ({_digits(value * 60, 3)} min)'
    if unit == 'h' and value >= 48:
        days = value / 24
        text += (
            f' ({_digits(days, 3)} days)'
            if days < 1000
            else f' ({_digits(value / 8766, 2)} year{"" if round(value / 8766) == 1 else "s"})'
        )
    return text


def event_label(entry):
    """How a trace entry reads as an event: its label, and how it ended when it has an outcome."""
    return f'{entry["label"]}: {entry["outcome"]}' if entry['outcome'] else entry['label']


def cards_for(cards, occurrence):
    """The cards of one occurrence of an event, counted from 1. A card that names an occurrence
    shows only then, and the last named occurrence also covers every later one; a card that names
    none shows each time."""
    named = [card['occurrence'] for card in cards if 'occurrence' in card]
    if not named:
        return cards
    n = min(occurrence, max(named))
    return [card for card in cards if card.get('occurrence', n) == n]


def range_text(low, high, unit, *, multiplier=False):
    prefix, lo, _ = _parts(low, unit, multiplier, False)
    _, hi, suffix = _parts(high, unit, multiplier, False)
    return f'{prefix}{lo}–{prefix if prefix == "×" else ""}{hi}{suffix}'


def _text_options(definition):
    """How one definition's values read: a fraction above one is a multiplier; a binary control (a
    bool input) is a switch. The kind of a value's evidence does not change how it reads."""
    adjust = definition.adjust
    metadata = definition.metadata if definition.metadata is not None else {}
    return {
        'multiplier': definition.unit == 'fraction'
        and max(definition.value, adjust.maximum if adjust.maximum is not None else 0) > 1,
        'switch': metadata.get('control') == 'binary',
    }
