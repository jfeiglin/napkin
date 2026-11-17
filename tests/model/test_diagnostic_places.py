"""The place of a diagnostic, `file:line:column`, and the close names that it suggests (difflib).

The column of a line's place is where the line starts in its file: a map of its own beside the line
map, so that the lines, which order the events of one moment, stay numbers. A syntax problem gives
the column of the token that it is about. A name that names nothing gets the names of the model that
are closest to it, and a name far from every name gets none."""

from __future__ import annotations

import pytest

from napkin.model import ModelError
from napkin.model.ir import close_names
from napkin.model.language import front
from napkin.model.model import build_model
from tests.model.modeltest import FIXTURE, LIB, located


def start(row):
    """The column where a row of a file starts: after its indentation, from 1."""
    return len(row) - len(row.lstrip(' ')) + 1


def rows(tmp_path):
    return (tmp_path / 'MODELTEST.scn').read_text(encoding='utf-8').split('\n')


def test_each_place_has_the_column_where_its_line_starts():
    file = front.read(FIXTURE, 'MODELTEST.scn')
    written = FIXTURE.split('\n')
    assert file.columns.keys() == file.lines.keys()
    assert all(isinstance(line, int) for line in file.lines.values())
    for place, line in file.lines.items():
        assert file.columns[place] == start(written[line - 1]), place


@pytest.mark.parametrize(
    'old, new',
    [
        # A value, an event, a record and a unit that name nothing, at several depths of the file.
        ('at service_rate * waiting', 'at service_rat * waiting'),
        ('count(service.repaired) > 0', 'count(servce.repaired) > 0'),
        ('    let users = 1000 people  @ident', '    let users = 1000 people  @idnet'),
        ('let users = 1000 people', 'let users = 1000 peple'),
        ('    fast = "Fast repair"', '    fast = "Fast repiar"'),
    ],
)
def test_a_diagnostic_gives_the_column_where_the_line_of_its_place_starts(tmp_path, old, new):
    diagnostics = located(tmp_path, ('replace', old, new))
    written = rows(tmp_path)
    found = [item for item in diagnostics if item.get('line')]
    assert found, diagnostics
    for item in found:
        assert item['column'] == start(written[item['line'] - 1]), item


def test_a_syntax_problem_gives_the_column_of_its_token(tmp_path):
    diagnostics = located(tmp_path, ('replace', '1000 people  @ident', '1000 people )  @ident'))
    (item,) = diagnostics
    assert written_at(rows(tmp_path), item) == ')'


def written_at(written, item):
    return written[item['line'] - 1][item['column'] - 1]


def test_a_problem_of_a_module_gives_the_file_line_and_column_of_the_module(tmp_path):
    # The responders move to the module `crew` of the package; the module names a value of theirs wrongly.
    begin, end = FIXTURE.index('responders:'), FIXTURE.index('attacker:')
    crew = FIXTURE[begin:end].rstrip('\n').replace('>= removal_time', '>= removal_tim') + '\n'
    head, _, rest = (FIXTURE[:begin] + FIXTURE[end:]).partition('\nswitch:')
    (tmp_path / 'model.scn').write_text(f'{head}\nuse crew\n\nswitch:{rest}', encoding='utf-8')
    (tmp_path / 'crew.scn').write_text(crew, encoding='utf-8')
    with pytest.raises(ModelError) as caught:
        build_model(tmp_path / 'model.scn', LIB)
    (item,) = caught.value.diagnostics
    assert item['file'] == (tmp_path / 'crew.scn').as_posix()
    written = crew.split('\n')
    assert '>= removal_tim:' in written[item['line'] - 1]
    assert item['column'] == start(written[item['line'] - 1])
    assert item['message'].endswith('did you mean removal_time?')


@pytest.mark.parametrize(
    'old, new, meant',
    [
        ('at service_rate * waiting', 'at service_rat * waiting', 'service_rate'),
        ('count(service.repaired) > 0', 'count(servce.repaired) > 0', 'service.repaired'),
        ('elapsed(status) >= repair_time:', 'elapsed(status) >= repair_time and count(fail) > 0:', 'fails'),
        ('    let users = 1000 people  @ident', '    let users = 1000 people  @idnet', 'ident'),
        ('let users = 1000 people', 'let users = 1000 peple', 'people'),
        ('    fast = "Fast repair"', '    fast = "Fast repiar"', 'Fast repair'),
    ],
)
def test_a_name_that_names_nothing_gets_the_closest_names_of_the_model(tmp_path, old, new, meant):
    diagnostics = located(tmp_path, ('replace', old, new))
    (item,) = [item for item in diagnostics if 'did you mean' in item['message']]
    suggested = item['message'].rpartition('did you mean ')[2].rstrip('?')
    assert suggested.split(', ')[0].split(' or ')[0] == meant


def test_a_name_far_from_every_name_gets_no_suggestion(tmp_path):
    diagnostics = located(tmp_path, ('replace', 'at service_rate * waiting', 'at zzqx * waiting'))
    assert diagnostics and not any('did you mean' in item['message'] for item in diagnostics)


def test_close_names_are_at_most_three_known_names_and_never_the_name_itself():
    names = ['repair_time', 'repair_times', 'repairs_time', 'repair_tim', 'settle_time']
    text = close_names('repair_time', names)
    listed = text.removeprefix('; did you mean ').removesuffix('?').replace(' or ', ', ').split(', ')
    assert 1 <= len(listed) <= 3 and set(listed) <= set(names) - {'repair_time'}
    assert close_names('zzqx', names) == '' and close_names('a', []) == ''
