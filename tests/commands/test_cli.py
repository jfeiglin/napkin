"""The `napkin` command: its help and version, which load no compiler and no engine, and the commands
that a later stage of the rewrite brings back, which are listed and refused with their stage."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

import napkin as package
from napkin.commands import LATER, NAMES
from tests.commands.call import napkin

ROOT = Path(__file__).resolve().parents[2]


def test_help_lists_each_command_and_marks_those_that_come_later(capsys):
    found = napkin(capsys, '--help')
    assert found.code == 0
    listed = found.out.split('commands:\n', 1)[1]
    for name in NAMES:
        assert f'\n  {name} ' in f'\n{listed}'
    for name in LATER:
        line = next(row for row in listed.splitlines() if row.split()[:1] == [name])
        assert line.endswith('(a later stage brings it back)')


def test_version_is_the_version_of_the_package(capsys):
    found = napkin(capsys, '--version')
    assert (found.code, found.out) == (0, f'{package.__version__}\n')


def test_help_and_version_load_no_compiler_and_no_engine():
    """In a new process: `python -m napkin --help` and `--version`, then the modules of napkin that
    are loaded."""
    script = (
        'import json, runpy, sys\n'
        'for word in ("--help", "--version"):\n'
        '    sys.argv = ["napkin", word]\n'
        '    try:\n'
        '        runpy.run_module("napkin", run_name="__main__")\n'
        '    except SystemExit as stop:\n'
        '        assert stop.code == 0, stop.code\n'
        'print(json.dumps(sorted(name for name in sys.modules if name.startswith("napkin."))))\n'
    )
    done = subprocess.run(
        [sys.executable, '-c', script], cwd=ROOT, capture_output=True, text=True, check=True, timeout=60
    )
    loaded = json.loads(done.stdout.splitlines()[-1])
    assert loaded, done.stdout
    for prefix in ('napkin.engine', 'napkin.model', 'napkin.program', 'napkin.core'):
        assert not [name for name in loaded if name.startswith(prefix)], loaded


@pytest.mark.parametrize('name', sorted(LATER))
@pytest.mark.parametrize('rest', [(), ('--help',), ('examples/piano_tuners', '--json')])
def test_a_command_that_a_later_stage_brings_back_exits_with_status_2(capsys, name, rest):
    """`napkin play` waits for the checkpoints of S7 (PLAN, change 15)."""
    found = napkin(capsys, name, *rest)
    assert found.code == 2
    stage = LATER[name][1]
    assert found.err == f'napkin {name} comes back in a later stage of the rewrite of the language (stage {stage})\n'
    assert found.out == ''
    assert LATER['play'][1] == 'S7'


def test_an_unknown_argument_of_a_command_is_a_usage_error(capsys):
    found = napkin(capsys, 'run', ROOT / 'examples' / 'piano_tuners', '--seed', '3')
    assert found.code == 2
    assert 'unrecognized arguments: --seed 3' in found.err
