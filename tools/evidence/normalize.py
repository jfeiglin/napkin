"""Quote normalization and token-boundary matching against extracted document text.

Superscript digits and vulgar fractions first become tokens of their own ('10²' is '10 sup2',
'1½' is '1 frac1_2') so NFKC cannot fold them into plain digits, and digit groups split by a
no-break, thin or narrow no-break space are joined ('225 000' is one number). NFKC then folds
compatibility forms (the fi/fl/ff/ffi/ffl ligatures), a soft hyphen that ends a line between two
letters joins the two halves of its word, other soft hyphens and zero-width characters are
dropped, a hyphen that ends a line before a lowercase letter is joined, text is casefolded,
and every run of other non-alphanumerics becomes one space. Numbers keep their boundaries: a
decimal point or comma between two digits is kept, '·' there is a decimal point, a sign
(-, −, –) or a leading '.' or ',' directly before a number stays attached unless a letter, digit
or another dash precedes it (so an extracted range such as '104---127' is not a negative number), and '%' is its own token. So '14 days' never matches '114 days', '4.2%'
never matches '42%' or '14·2%', '5%' never matches '.5%' and '0.4%' never matches '−0.4%'.
A quote matches only on whole tokens, so 'confident' never matches 'confidence'.
"""

import re
import unicodedata

NORMALIZATION = 'nfkc-lig-v2'
_INVISIBLE = dict.fromkeys(map(ord, '­\u200b‌‍⁠﻿'))
_SUPERSCRIPT = re.compile('[⁺⁻]?[⁰¹²³⁴-⁹]+')
_SUPER_DIGITS = str.maketrans('⁺⁻⁰¹²³⁴⁵⁶⁷⁸⁹', '+-0123456789')
_FRACTION = re.compile('[¼-¾⅐-⅟↉]')
_DIGIT_GROUP = re.compile(r'(?<=\d)[   ](?=\d{3}(?!\d))')
_DECIMAL_DOT = re.compile(r'(?<=\d)·(?=\d)')
_LINE_HYPHEN = re.compile(r'([^\W\d_])[-‐][ \t]*\r?\n\s*(?=[^\W\d_])')
# A soft hyphen marks a place where a word can break: at a line end, the word goes on in the next
# line. It is never part of the word, so both readings of a hyphen at a line end join it.
_SOFT_BREAK = re.compile(r'([^\W\d_])\u00ad[ \t]*\r?\n\s*(?=[^\W\d_])')
_TOKEN = re.compile(
    r'(?<![^\W_])(?:sup[-+]?\d+|frac\d+_\d*)(?![^\W_])'
    r'|(?<![^\W_])(?:(?<![-−–])[-−–](?=[.,]?\d))?(?:[.,](?=\d))?(?:\d[.,](?=\d)|[^\W_])+|%'
)
_SIGN = str.maketrans('−–', '--')


def normalize(text, join_hyphenation=True):
    text = _SUPERSCRIPT.sub(lambda m: f' sup{m.group().translate(_SUPER_DIGITS)} ', text)
    text = _FRACTION.sub(
        lambda m: f' frac{unicodedata.normalize("NFKC", m.group()).replace("⁄", "_")} ', text
    )
    text = unicodedata.normalize('NFKC', _DIGIT_GROUP.sub('', text))
    text = _SOFT_BREAK.sub(r'\1', text).translate(_INVISIBLE)
    text = _DECIMAL_DOT.sub('.', text)
    if join_hyphenation:
        text = _LINE_HYPHEN.sub(lambda m: m.group(1) if text[m.end()].islower() else m.group(0), text)
    return ' '.join(_TOKEN.findall(text.casefold())).translate(_SIGN)


def matches(quote, text):
    """True when the normalized quote occurs in the normalized text on token boundaries.

    A hyphen at a line end is ambiguous (hyphenation or a hyphenated compound), so the
    text is tried both joined and split; neither reading can merge digits or tokens.
    """
    needle = normalize(quote)
    return bool(needle) and any(f' {needle} ' in f' {normalize(text, join)} ' for join in (True, False))


def match_quotes(quotes, text):
    """(matched, total) for a claim's quotes against one extracted text."""
    joined, split = (f' {normalize(text, join)} ' for join in (True, False))
    needles = [normalize(q['text'] if isinstance(q, dict) else q) for q in quotes]
    return sum(bool(n) and (f' {n} ' in joined or f' {n} ' in split) for n in needles), len(needles)
