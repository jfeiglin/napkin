import pytest

from tests.engine.path_selection_cases import selection_case


@pytest.fixture(scope='module', params=(0, 1), ids=('two-paths', 'reordered-duplicate'))
def selections(request):
    return selection_case(request.param)[1]


@pytest.mark.parametrize('kind', ['list', 'tuple', 'iterator', 'generator'])
@pytest.mark.parametrize('action', ['plain', 'lag', 'unselected lag', 'unknown path'])
def test_reporting_a_path_selection_preserves_each_row_and_diagnostic(selections, kind, action):
    expected, actual = selections[f'{kind}.{action}']
    assert actual == expected


def test_read_accepts_the_same_single_pass_selection(selections):
    expected, actual = selections['read.iterator']
    assert actual == expected
