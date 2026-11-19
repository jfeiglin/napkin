"""The formatter (`napkin/model/language/format.py`): over every code block of the spec (`corpus/`),
`parse(format(text))` is the tree of the text and formatting again changes nothing; and the layout
that it writes: units, brackets, comments, ranges and long texts."""

import textwrap
from pathlib import Path

import pytest

from napkin.model.language.format import WIDTH, format_text, write
from napkin.model.language.parse import parse

CORPUS = Path(__file__).parent / 'corpus'
# The blocks of the spec that are the body of an entity, and those that are the body of an event.
MEMBERS = {'spec_22', 'spec_23', 'spec_24', 'spec_25', 'spec_26', 'spec_28', 'spec_29', 'spec_30'}
EVENT_BODIES = {'spec_18', 'spec_19', 'spec_20', 'spec_21'}
BLOCKS = sorted(CORPUS.glob('spec_*.scn'))


def placed(path):
    """A block of the spec as a text of a file: a fragment goes under an entity or an event."""
    text = path.read_text()
    if path.stem in MEMBERS:
        return 'holder:\n' + textwrap.indent(text, '    ')
    if path.stem in EVENT_BODIES:
        return 'holder:\n    fragment = event():\n' + textwrap.indent(text, '        ')
    return text


def test_the_corpus_holds_every_block_of_the_spec():
    assert len(BLOCKS) == 32
    assert {path.name for path in CORPUS.glob('*.csv')} == {'places.csv', 'routes.csv', 'readings.csv'}


@pytest.mark.parametrize('path', BLOCKS, ids=lambda path: path.stem)
def test_a_block_formats_to_its_own_tree_and_is_stable(path):
    tree = parse(placed(path))
    written = write(tree)
    assert parse(written) == tree
    assert format_text(written) == written


@pytest.mark.parametrize('path', BLOCKS, ids=lambda path: path.stem)
def test_a_block_of_the_spec_is_written_in_the_formatters_layout(path):
    # The spec writes its blocks as the formatter does, apart from a fragment's wrapper.
    text = placed(path)
    assert format_text(text) == text


@pytest.mark.parametrize(
    ('text', 'written'),
    [
        ('x = 48 h/2\n', 'x = 48 h / 2\n'),
        ('x = this.water / 2 h\n', 'x = this.water / (2 h)\n'),
        ('x = 0.30 * 1e-05\n', 'x = 0.30 * 1e-05\n'),
        ('x = 6 person*year\n', 'x = 6 person * year\n'),
        ('x = (2 h) * hour\n', 'x = (2 h) * hour\n'),
        ('x = a * (2 h) * hour\n', 'x = a * (2 h) * hour\n'),
        ('x = 2 h*hour\n', 'x = 2 h * hour\n'),
        ('rate: tunings/(tuner*year) = 1\n', 'rate: tunings/(tuner * year) = 1\n'),
        ('x = ((a + b)) * c\n', 'x = (a + b) * c\n'),
        ('x = a - (b - c)\n', 'x = a - (b - c)\n'),
        ('x = -(a ** 2)\n', 'x = -a ** 2\n'),
        ('ok: bool = (x in [0,])\n', 'ok: bool = (x in [0,])\n'),
        ('x: L = 1 in [ , 10 L ]\n', 'x: L = 1 in [, 10 L]\n'),
    ],
)
def test_the_formatter_writes_the_spacing_and_the_brackets_that_are_needed(text, written):
    assert format_text(text) == written
    assert parse(written) == parse(text)


def test_comments_and_empty_rows_stay_where_they_are():
    text = '# a model\n\ntank:  # the tank\n    # its water\n    water: L = 8\n\n\nclinic:\n    x = 1\n# the end\n'
    assert format_text(text) == (
        '# a model\n\ntank:  # the tank\n    # its water\n    water: L = 8\n\nclinic:\n    x = 1\n# the end\n'
    )


def test_a_long_text_breaks_at_single_spaces_and_keeps_its_value():
    words = ' '.join(f'word{k}' for k in range(40))
    text = f'tank:\n    "{words}"\n    water: L = 8\n'
    written = format_text(text)
    rows = written.split('\n')
    assert all(len(row) <= WIDTH for row in rows)
    assert len(rows) > 4
    assert parse(written) == parse(text)
    assert format_text(written) == written


def test_a_text_with_line_breaks_keeps_them():
    text = 'tank:\n    "first\n\n        second\n\n\n        third"\n'
    tree = parse(text)
    assert tree.items[0].text == 'first\nsecond\n\nthird'
    assert parse(write(tree)) == tree


def test_a_sum_of_thousands_of_terms_formats_and_parses_to_the_same_tree():
    """A chain from the left (`a + b - c ...`, `a * b / c ...`) is written link by link, as the parser
    reads it and the front end resolves it, so a long one costs no depth of calls (the audit's row
    15): at a recursion limit of 400, 3,000 terms of each level, with quantities and the bare names
    after which a quantity is bracketed."""
    import sys

    sums = ' + '.join(f'v{k}' if k % 3 else f'{k} L' for k in range(3000))
    products = ' * '.join('x' if k % 2 else '(2 h)' for k in range(3000))
    text = f'total = formula({sums} - 1 L)\nproduct = formula({products} / y)\n'
    before = sys.getrecursionlimit()
    sys.setrecursionlimit(400)
    try:
        # The text is written as the formatter writes it, so it formats to itself; its tree, read
        # again, writes the same text (a tree thousands deep is compared by its text: Python's own
        # comparison of two such trees recurses).
        written = format_text(text)
        assert written == text and write(parse(written)) == text
    finally:
        sys.setrecursionlimit(before)
