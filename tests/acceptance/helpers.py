"""Run the acceptance fixtures and read their traces.

Each fixture is a model file (`F*.scn`). It is built with the front end, resolved with
`model.resolve` and run with the engine's runtime; its output values come from `evaluate_outputs`. A
case's edit is a list of steps that change the file (`steps`). Expected values live in
`F*.expect.yaml`, worked out independently of the engine. Nothing here derives an expectation from a
run.
"""

from __future__ import annotations

import math
from pathlib import Path
from types import SimpleNamespace

from napkin.engine.report import evaluate_outputs
from napkin.engine.runtime import simulate
from napkin.model.ir import thaw
from napkin.model.language import front
from napkin.model.load import load_json
from tests.acceptance.strict_yaml import parse
from tests.build import append, edit, member, replace

HERE = Path(__file__).parent
LIBRARY = load_json(HERE / 'library.json')
RUN = 'closing'


def fixture(name):
    """The text of one fixture."""
    return (HERE / f'{name}.scn').read_text(encoding='utf-8')


def expectations(family):
    """The transcribed expectations of one family."""
    return parse((HERE / f'{family}.expect.yaml').read_text(encoding='utf-8'), f'{family}.expect.yaml')[0]


def steps(written):
    """The steps (`tests.build.edit`) of a case's edit, as the expectations write them:
    - `{into: NAME, add: TEXT}` puts member lines at the end of the block of the top-level entity or
      template NAME, one level deeper;
    - `{append: TEXT}` puts top-level lines at the end of the file;
    - `{replace: OLD, with: NEW}` changes OLD, which occurs once, to NEW."""
    out = []
    for step in written or ():
        if 'into' in step:
            out.append(member(step['into'], step['add'].rstrip('\n')))
        elif 'append' in step:
            out.append(append(step['append'].rstrip('\n')))
        else:
            out.append(replace(step['replace'], step['with']))
    return out


def model_of(name_or_text, changes=(), library=LIBRARY):
    """The model of a fixture, named, or of a model text, with the steps of an edit."""
    if '\n' in name_or_text:
        text, origin = name_or_text, 'test.scn'
    else:
        text, origin = fixture(name_or_text), f'{name_or_text}.scn'
    text = edit(text, *changes)
    return front.compile_file(front.read(text, origin), origin, thaw(library))


def execute(name_or_text, changes=(), settings=None, times=None, library=LIBRARY):
    """The run `baseline` of a fixture or a text, with the steps of an edit: its model, resolved
    structure, trajectory and the output values at `times`."""
    model = model_of(name_or_text, changes, library)
    rs = model.resolve(RUN)
    trajectory = simulate(rs, library, settings)
    rows = evaluate_outputs({'resolved': rs, 'trajectory': trajectory}, library, times) if times else []
    return SimpleNamespace(model=model, resolved=rs, trajectory=trajectory, rows=rows)


def run(name_or_text, changes=(), settings=None, times=None, library=LIBRARY):
    """An accepted run: (trajectory, output values at `times`)."""
    done = execute(name_or_text, changes, settings, times, library)
    return done.trajectory, done.rows


def close(actual, expected):
    if expected is None or isinstance(expected, str) or isinstance(actual, str):
        return actual == expected
    return math.isclose(actual, expected, rel_tol=1e-9, abs_tol=1e-9)


def entries(trajectory, rule=None, event=None, t=None):
    return [
        (i, entry)
        for i, entry in enumerate(trajectory.trace)
        if (rule is None or entry['rule'] == rule)
        and (event is None or entry['event'] == event)
        and (t is None or entry['t'] == t)
    ]


def captured(trajectory, name):
    """Whether any step ever wrote `name`."""
    return any(name in entry['changes'] for entry in trajectory.trace)


def check_state(env, trajectory, expected, where):
    for name, value in expected.items():
        if value is None:
            assert not captured(trajectory, name), f'{where}: {name} was captured'
        else:
            assert close(env[name], value), f'{where}: {name} = {env[name]!r}, expected {value!r}'


def final_store(trajectory):
    return trajectory._snapshots[-1][2]
