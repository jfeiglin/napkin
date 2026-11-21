"""Run with PYTHONPATH set to either source tree and NAPKIN_STORE=off."""
import json
import subprocess
import sys
from pathlib import Path
from tempfile import TemporaryDirectory

from napkin.engine import read, run
from napkin.model.compile import compile_text


def stage_results(operand):
    source = f'''scenario "Named or inline"
    horizon 2 h
w:
    gap = formula({operand})
    named_ran = false
    inline_ran = false
    named = event():
        after 1 h when this.gap > 0 h:
            this.named_ran = true
    inline = event():
        after 1 h when {operand} > 0 h:
            this.inline_ran = true
w.named.start()
w.inline.start()
'''
    m = compile_text(source, {'h': {'time': 1}, 'day': ({'time': 1}, 24)})
    record = run(m.program, m.configuration)
    assert record.failure is None, record.failure
    return [(r.path, r.values) for r in read(record, m.program,
            ['w.gap', 'w.named_ran', 'w.inline_ran'], [2])]


import pytest


@pytest.mark.parametrize(('gap', 'outcome'), [
    ('(0.100000024 h + 0 day) - 0.1 h', True),
    ('1000000000.00000005 h - 1000000000 h', True),
])
def test_naming_a_formula_preserves_the_guard(gap, outcome):
    result = dict(stage_results(gap))
    assert (result['w.named_ran'], result['w.inline_ran']) == ((outcome,), (outcome,))


@pytest.mark.parametrize(('bound', 'token', 'valid'), [
    ('0.6', '0.6', True),
    ('0.6', '0.60000000000000001', False),
    ('0.6', '"0.60000000000000001"', False),
    ('9007199254740992', '9007199254740993.0', False),
    ('9007199254740992', '9007199254740993', False),
])
def test_json_input_range_is_independent_of_spelling(tmp_path, bound, token, valid):
    (tmp_path/'model.scn').write_text(
        f'scenario "Edits"\n    horizon 1 h\nw:\n    input x: number = 0 in [0, {bound}]\n')
    edits = tmp_path/'edits.json'
    edits.write_text('{"set":{"w.x":'+token+'}}')
    proc = subprocess.run(
        [sys.executable, '-B', '-m', 'napkin', 'run', str(tmp_path), '--at', '0h',
         '--edits', str(edits), '--json'], capture_output=True, text=True)
    diagnostics = [d['code'] for d in json.loads(proc.stdout)['diagnostics']]
    if valid:
        assert (proc.returncode, diagnostics) == (0, [])
    else:
        assert proc.returncode and 'range' in diagnostics, (proc.returncode, diagnostics)
