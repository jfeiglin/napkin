"""Texts that fit a width: the one way of the picture to cut a text into lines, which the layout and
the words of the events (`triggers`) share. This module imports nothing of the model.
"""

ELLIPSIS = '…'


def shorten(text, width, lines, measure):
    """(the lines of `text`, whether it was cut): at most `lines` lines, each at most `width` wide by
    `measure(text) -> width`. The lines break at spaces; a word wider than a line breaks where it must.
    When the text does not fit, the last line ends with '…'. A text that fits on one line comes back
    unchanged."""
    if lines < 1:
        raise ValueError('a text has one line or more')
    if measure(ELLIPSIS) > width:
        raise ValueError(f'a line of width {width} cannot hold {ELLIPSIS}')
    if measure(text) <= width:
        return [text], False
    rows, current, stopped = [], '', False
    for word in text.split():
        joined = f'{current} {word}' if current else word
        if measure(joined) <= width:
            current = joined
            continue
        if current:
            rows.append(current)
            current = ''
        rest = word
        while measure(rest) > width:
            k = _fits(rest, width, measure)
            if k == 0:
                stopped = True
                break
            rows.append(rest[:k])
            rest = rest[k:]
        if stopped:
            break
        current = rest
    if current:
        rows.append(current)
    if not stopped and len(rows) <= lines:
        return rows, False
    kept = rows[:lines] or ['']
    last = kept[-1]
    while last and measure(last + ELLIPSIS) > width:
        last = last.rsplit(' ', 1)[0] if ' ' in last else last[:-1]
    kept[-1] = last.rstrip() + ELLIPSIS
    return kept, True


def _fits(word, width, measure):
    """The most characters of the start of `word` that fit in `width`."""
    k = 0
    while k < len(word) and measure(word[: k + 1]) <= width:
        k += 1
    return k
