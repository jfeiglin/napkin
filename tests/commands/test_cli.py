"""The `napkin` command: its help and version, which load no compiler and no engine, and its list of
commands."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import napkin as package
from napkin.commands import NAMES, modules
from tests.commands.call import napkin

ROOT = Path(__file__).resolve().parents[2]


def test_help_lists_each_command_with_its_summary(capsys):
    found = napkin(capsys, '--help')
    assert found.code == 0
    listed = found.out.split('commands:\n', 1)[1]
    for name, module in modules().items():
        line = next(row for row in listed.splitlines() if row.split()[:1] == [name])
        assert line.endswith(module.SUMMARY)
    assert NAMES == ('compile', 'run', 'sample', 'play', 'fmt', 'draw', 'new')


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


def test_an_unknown_argument_of_a_command_is_a_usage_error(capsys):
    found = napkin(capsys, 'run', ROOT / 'examples' / 'piano_tuners', '--seed', '3')
    assert found.code == 2
    assert 'unrecognized arguments: --seed 3' in found.err
