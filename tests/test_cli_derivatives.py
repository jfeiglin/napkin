"""`napkin derivatives` (napkin/commands/derivatives.py, docs/cli.md).

The command prints the report of the derivatives of one run (`timeline.derivatives`, whose tests
are in tests/engine/test_timeline_derivatives.py). Here: what the command prints of a report, in
its two forms, and what it says of a wrong command line. The numbers are closed forms of the
model of this file. The packages are written in tmp_path with a reserved name.
"""

from __future__ import annotations

import json

import pytest

from napkin import cli
from tests.engine.test_timeline_derivatives import HEAD, RECORD, TWO_EVENTS

RUNS = """
options "Timing":
    "As written":
        "The times of the file."
    "Later":
        "The second event is one hour later."
        tank.second_at = 31 h  @shape

runs:
    tied = "As written"
    apart = "Later"
"""


@pytest.fixture
def tank(tmp_path):
    """A package with a tank that fills at 0.01 an hour, doubles at 30 h and gets 1 more at 30 h
    (the run `tied`) or at 31 h (the run `apart`), for 10 days."""
    folder = tmp_path / 'SC97'
    folder.mkdir()
    text = HEAD.replace('{days}', '10') + TWO_EVENTS + RUNS + RECORD
    (folder / 'model.scn').write_text(text, encoding='utf-8')
    return folder


def derivatives(capsys, *argv):
    """(the exit code, what the command prints, what it writes of errors)."""
    code = cli.main(['derivatives', *map(str, argv)])
    done = capsys.readouterr()
    return code, done.out, done.err


def test_the_json_form_is_the_report_of_the_run_that_the_command_names(tank, capsys):
    """The level ends at `r a + r T + 1`: 0.01 by the time of the doubling, 0 by the time of the
    other event, `a + T` by the rate. With the two events one hour apart each derivative is
    smooth; in the run with both at 30 h the two by a time are those of one side."""
    code, out, err = derivatives(capsys, tank, '--run', 'apart', '--json')
    assert code == 0 and err == ''
    report = json.loads(out)
    assert report['run'] == 'apart' and report['unsupported'] is None
    assert report['inputs'] == ['tank.first_at', 'tank.second_at', 'tank.pace']
    assert report['outputs']['level'] == {
        'value': pytest.approx(0.3 + 2.4 + 1),
        'unit': 'fraction',
        'label': 'Level',
    }
    row = report['derivatives']['level']
    assert {name: item['class'] for name, item in row.items()} == dict.fromkeys(report['inputs'], 'smooth')
    assert row['tank.first_at']['value'] == pytest.approx(0.01, rel=1e-12)
    assert row['tank.second_at']['value'] == pytest.approx(0.0, abs=1e-15)
    assert row['tank.pace']['value'] == pytest.approx(270.0, rel=1e-12)
    assert row['tank.pace']['unit'] == 'fraction per fraction/h'
    code, out, _ = derivatives(capsys, tank, '--run', 'tied', '--json', '--input', 'tank.first_at')
    report = json.loads(out)
    assert code == 0 and report['inputs'] == ['tank.first_at']
    (item,) = report['derivatives']['level'].values()
    assert item['class'] == 'one-sided' and item['value'] == pytest.approx(0.01, rel=1e-12)
    assert item['why'] != []


def test_the_printed_form_has_each_derivative_with_its_class_and_the_reason_of_a_class(tank, capsys):
    code, out, err = derivatives(capsys, tank, '--run', 'tied')
    assert code == 0 and err == ''
    lines = out.splitlines()
    assert lines[0].startswith('run tied')
    assert any(line.startswith('Level: 3.7 fraction') for line in lines)
    by = {line.split()[1]: line for line in lines if line.startswith('  by ')}
    assert set(by) == {'tank.first_at', 'tank.second_at', 'tank.pace'}
    assert by['tank.first_at'].endswith('[one-sided]') and by['tank.pace'].endswith('[smooth]')
    assert '0.01' in by['tank.first_at'] and '270' in by['tank.pace']
    # The reason of the class is under the line of the derivative: the two events at one time.
    after = lines[lines.index(by['tank.first_at']) + 1]
    assert 'tank.double' in after and 'tank.add' in after and not after.startswith('  by ')


def test_a_wrong_command_line_is_a_usage_error(tank, capsys):
    """A model of two runs needs `--run`; a name that is no input is refused with the nearest names."""
    code, _, err = derivatives(capsys, tank)
    assert code == 2 and 'tied' in err and 'apart' in err
    code, _, err = derivatives(capsys, tank, '--run', 'tied', '--input', 'tank.frist_at')
    assert code == 2 and 'tank.frist_at is no input of the model' in err and 'tank.first_at' in err
    code, _, err = derivatives(capsys, tank, '--run', 'never')
    assert code == 2 and 'never' in err


def test_the_command_is_in_the_list_of_commands(capsys):
    with pytest.raises(SystemExit) as stop:
        cli.main(['--help'])
    assert stop.value.code == 0
    assert 'derivatives' in capsys.readouterr().out
