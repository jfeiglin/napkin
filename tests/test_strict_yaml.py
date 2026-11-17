"""The strict YAML loader that reads the frozen expectations of the acceptance tests
(tests/acceptance/strict_yaml.py)."""

from __future__ import annotations

import pytest

from napkin.model import SourceError
from tests.acceptance.strict_yaml import parse


@pytest.mark.parametrize(
    ('text', 'line'),
    [
        ('a: 1\na: 2\n', 2),  # duplicate key
        ('a: &x 1\nb: *x\n', 1),  # anchor
        ('a: !!str 1\n', 1),  # explicit tag
        ('a: 1e999\n', 1),  # non-finite number
    ],
)
def test_strict_yaml_rejects_ambiguous_text_at_its_line(text, line):
    with pytest.raises(SourceError) as caught:
        parse(text, 'test.yaml')
    assert caught.value.line == line


def test_yaml_one_one_words_and_dates_stay_strings():
    assert parse('a: yes\nb: off\nc: 2026-01-01\nd: true\n', 'test.yaml')[0] == {
        'a': 'yes',
        'b': 'off',
        'c': '2026-01-01',
        'd': True,
    }
