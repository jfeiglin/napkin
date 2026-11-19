"""Spreads (`napkin/spread.py`): the Monte Carlo study of one run of a model, from its file or from the
compiled model, under an edit document; in a pool of processes or in this process, which agree, and the
same spread gives the same study again. Invalid settings and a refused document stop before any run, a
cancelled spread stops between samples, and the processes of a pool end with the process that made
them. Each sample of the tank holds its closed form: its start plus 4 h times the rate that it drew.
"""

from __future__ import annotations

import json
import os
import signal
import subprocess
import sys
import textwrap
import threading
import time
from pathlib import Path

import pytest

from napkin import spread as spreads
from napkin import store
from napkin.engine.sampling import SamplingSettings
from napkin.engine.study import Cancelled, edits_for
from napkin.engine.uncertainty import monte_carlo
from napkin.model.compile import load_scenario
from napkin.model.language.problems import LanguageError

ROOT = Path(__file__).resolve().parents[1]
MODEL = textwrap.dedent("""\
    scenario "Tank"
        horizon 4 h
    tank:
        input pace = uniform(1 L/h, 3 L/h)  @measured
        rate: L/h = this.pace.draw()
        input start: L = 0 L in [0 L, 10 L]  @measured
        water: L = this.start in [0 L,]
            "Water in the tank"
        flow fill: SOURCE -> this.water
            request = this.rate
    options "Start":
        "Empty":
            "An empty tank."
        "Some":
            "Two litres to start."
            tank.start = 2 L  @measured
    runs:
        empty = "Empty"
        some = "Some"
    record measured: source "A gauge reading."
    """)
RATE = 'tank.rate.draw[0]'


@pytest.fixture
def path(tmp_path):
    folder = tmp_path / 'tank'
    folder.mkdir()
    (folder / 'model.scn').write_text(MODEL, encoding='utf-8')
    (folder / 'units.json').write_text(json.dumps({'L': {'dimensions': {'volume': 1}, 'scale': 1}}))
    return folder / 'model.scn'


def rates(found):
    return [next(value for site, _, value in sample.draws if site == RATE) for sample in found.samples]


def test_a_spread_of_a_file_is_the_study_of_its_compiled_run(path):
    found = spreads.spread(path, ['tank.water'], [0, 4], run='some', samples=12, seed=3)
    model = load_scenario(path)
    assert found == monte_carlo(
        model.program,
        model.configure('some'),
        ['tank.water'],
        [0, 4],
        SamplingSettings(12, 3),
        model=model.declared,
    )
    assert [sample.values[0] for sample in found.samples] == pytest.approx(
        [(2, 2 + 4 * r) for r in rates(found)]
    )
    water = found.spread('tank.water', 4)
    assert (water.unit, water.label, water.summary.central) == ('L', 'Water in the tank', pytest.approx(10))
    assert spreads.spread(model, ['tank.water'], [0, 4], run='some', samples=12, seed=3) == found


def test_the_times_of_a_spread_are_its_horizon_unless_it_names_others(path):
    found = spreads.spread(path, ['tank.water'], samples=4)
    assert found.times == (4.0,) and found.spread('tank.water', 4).summary.central == pytest.approx(8)


def test_an_edit_gives_an_input_a_distribution_or_a_number(path):
    """`set` gives the pace uniform(4, 5) L/h: each sample draws from it. A number for the start puts 3 L
    in every sample's tank, over the option of the run."""
    model = load_scenario(path)
    edits = edits_for(model, {'set': {'tank.pace': 'uniform(4 L/h, 5 L/h)', 'tank.start': 3}})
    found = spreads.spread(model, ['tank.water'], [4], run='some', edits=edits, samples=10)
    assert all(4 <= r <= 5 for r in rates(found)) and found.spread('tank.water', 4).summary.central == 21
    assert [sample.values[0][0] for sample in found.samples] == pytest.approx(
        [3 + 4 * r for r in rates(found)]
    )


def test_a_refused_edit_document_and_invalid_settings_stop_before_any_run(path, monkeypatch):
    model = load_scenario(path)
    asked = []
    monkeypatch.setattr(store, 'run', lambda program, configuration: asked.append(configuration))
    with pytest.raises(LanguageError) as caught:
        spreads.spread(model, ['tank.water'], edits=edits_for(model, {'set': {'tank.start': 50}}))
    assert caught.value.codes == ['range']
    for settings in ({'samples': 0}, {'seed': -1}, {'jobs': 0}):
        with pytest.raises(ValueError):
            spreads.spread(model, ['tank.water'], **settings)
    with pytest.raises(ValueError, match='from 0 h to the horizon'):
        spreads.spread(model, ['tank.water'], [5])
    with pytest.raises(KeyError):
        spreads.spread(model, ['tank.nothing'])
    assert asked == []


def test_a_spread_in_a_pool_agrees_with_one_process_and_is_the_same_again(path):
    here = spreads.spread(path, ['tank.water'], [1, 4], samples=12, seed=5)
    pool = spreads.spread(path, ['tank.water'], [1, 4], samples=12, seed=5, jobs=2)
    assert rates(pool) == rates(here)
    for one, other in zip(here.samples, pool.samples):
        assert other.values[0] == pytest.approx(one.values[0], rel=1e-12)
    assert spreads.spread(path, ['tank.water'], [1, 4], samples=12, seed=5) == here


def test_a_cancelled_spread_stops_between_samples(path):
    cancel, seen = threading.Event(), []

    def progress(done, total):
        seen.append(done)
        cancel.set()

    with pytest.raises(Cancelled):
        spreads.spread(path, ['tank.water'], samples=50, progress=progress, cancel=cancel)
    assert seen == [1]


PARENT = """
import os, sys, time, multiprocessing
from napkin.spread import spread

def progress(done, total):
    print(' '.join(str(child.pid) for child in multiprocessing.active_children()), flush=True)
    time.sleep(120)

if __name__ == '__main__':
    spread(sys.argv[1], ['tank.water'], samples=40, jobs=2, progress=progress)
"""


@pytest.mark.skipif(not Path('/proc').is_dir(), reason='reads the state of a process in /proc')
def test_the_processes_of_a_pool_end_with_the_process_that_made_them(path, tmp_path):
    """The parent waits in its progress, and is killed: its two sample processes end too."""
    script = tmp_path / 'parent.py'
    script.write_text(PARENT)
    environment = {**os.environ, 'PYTHONPATH': str(ROOT), 'NAPKIN_STORE': 'off'}
    parent = subprocess.Popen(
        [sys.executable, str(script), str(path)], stdout=subprocess.PIPE, text=True, env=environment, cwd=ROOT
    )
    try:
        children = [int(pid) for pid in parent.stdout.readline().split()]
        assert len(children) == 2
        parent.send_signal(signal.SIGKILL)
        parent.wait(10)
        deadline = time.monotonic() + 10
        alive = children
        while alive and time.monotonic() < deadline:
            time.sleep(0.1)
            alive = [pid for pid in alive if _running(pid)]
        assert alive == []
    finally:
        parent.kill()
        parent.stdout.close()


def _running(pid):
    """Whether a process runs: a zombie, which has ended but whose parent has not read its end, does not."""
    try:
        with open(f'/proc/{pid}/stat', encoding='ascii') as stat:
            return stat.read().rsplit(')', 1)[1].split()[0] != 'Z'
    except FileNotFoundError:
        return False
