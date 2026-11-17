"""The examples (`examples/`, docs/language.md): packages that a reader runs as written.

Each example compiles with full admission, gives an admissible default study with finite outcomes,
is its own formatted text, has no library and no source, and rests each input and each output on a
record written in place. Their outcomes are checked as properties, by arithmetic of their own on the
inputs that the test reads from the model or edits: the tuners' total is the rate times the tuners
times the time, until the tunings run out; the reservoir's water balance holds, its spillway lets out
its rate for as long as it is open, the operator's choice comes when the water reaches the operator's
level, and the time above the risk level follows from the straight lines of the water.
"""

from __future__ import annotations

import json
import math
import re
import shutil
from itertools import pairwise
from pathlib import Path

import pytest

from napkin import actors, evaluate_study, evaluate_uncertainty, load_package, sample_result
from napkin.engine import SamplingSettings, edits_for
from napkin.model import ModelError, load_scenario
from napkin.model.ir import thaw
from napkin.model.language.format import format_text
from napkin.model.library import vocabulary_path
from napkin.paths import ENTRY

ROOT = Path(__file__).resolve().parents[1]
EXAMPLES = ROOT / 'examples'
FOLDERS = sorted(folder for folder in EXAMPLES.iterdir() if (folder / ENTRY).is_file())
PRELUDE = json.loads((ROOT / 'napkin' / 'std' / 'units.json').read_text(encoding='utf-8'))
# The scales of the prelude's times, in hours.
DAY, YEAR = PRELUDE['day']['scale'], PRELUDE['year']['scale']
# The kinds of a record that needs no source.
KINDS = {'assumption', 'identity', 'convention'}


def model_of(name):
    (model,) = load_package(EXAMPLES / name).values()
    return model


def points(study, run, times):
    """{time: the values of the outputs} of one run of a study, at `times` and at the end."""
    report = sample_result(study, times)
    return {point['t']: point['values'] for point in report['runs'][run]['reporting_points'].values()}


def test_the_examples_are_found():
    assert {folder.name for folder in FOLDERS} >= {'piano_tuners', 'reservoir'}


@pytest.mark.parametrize('folder', FOLDERS, ids=lambda folder: folder.name)
def test_an_example_compiles_with_full_admission_and_its_default_study_is_admissible(folder):
    models = load_package(folder)
    assert list(models) == [folder.name]
    (model,) = models.values()
    assert model.admission_runs is None
    study = evaluate_study(model)
    assert study.admissible, study.diagnostics
    assert not [item for item in study.diagnostics if item.get('severity', 'error') == 'error']
    report = sample_result(study)
    assert set(report['runs']) == set(model.runs)
    for run in report['runs'].values():
        final = run['reporting_points']['final']
        assert set(final['statuses'].values()) == {'estimated'}
        assert all(math.isfinite(value) for value in final['values'].values())


@pytest.mark.parametrize('folder', FOLDERS, ids=lambda folder: folder.name)
def test_an_example_is_its_own_formatted_text(folder):
    text = (folder / ENTRY).read_text(encoding='utf-8')
    assert format_text(text) == text


@pytest.mark.parametrize('folder', FOLDERS, ids=lambda folder: folder.name)
def test_each_input_and_output_rests_on_a_record_written_in_place_and_no_source(folder):
    """A record written in place has no name (a named record is cited by its name), and its kind needs
    no source. The model has no library line, no source and no claim, and the folder no evidence."""
    model = model_of(folder.name)
    sites = thaw(model.evidence)['sites']
    places = [tuple(name.split('.')) for name in model.inputs]
    places += [tuple(name.split('.')) if '.' in name else ('output:', name) for name in model.outputs]
    for place in places:
        record = sites.get(place)
        assert record is not None and 'name' not in record and record['kind'] in KINDS, place
    assert {record['kind'] for record in sites.values()} <= KINDS
    library = thaw(model.library)
    assert (library['sources'], library['claims'], library['assumptions']) == ([], [], [])
    assert vocabulary_path(folder / ENTRY) is None
    assert not (folder / 'evidence').exists()


# ---- piano_tuners ---------------------------------------------------------------------------------

PIANO = EXAMPLES / 'piano_tuners'
# A unit as the file writes it: after a number (`3 tuner`), or as the type of a value (`: tunings =`).
UNIT = r'[A-Za-z_]\w*(?:[/-][A-Za-z_]\w*|\^\d+)*'
WRITTEN = re.compile(rf'\b\d[\d.]*(?:e[+-]?\d+)? +({UNIT})|: +({UNIT}) +=')


# The words of the language that can follow a number without a unit: `0.6 size 1`, `1 if c else 0`.
WORDS = {'in', 'to', 'size', 'if', 'else', 'and', 'or', 'versus'}


def written_units(text):
    """The units that a model file writes, outside its texts and its comments."""
    code = re.sub(r'"[^"]*"', '', re.sub(r'(?m)^\s*#.*$', '', text))
    return {unit for pair in WRITTEN.findall(code) for unit in pair if unit and unit not in WORDS}


def unit_parts(unit):
    """The declared units that a unit name is made of: `tunings/tuner-year` is tunings, tuner and year."""
    return set(re.split(r'[/-]', re.sub(r'\^\d+', '', unit)))


def test_piano_tuners_declares_exactly_the_units_that_it_uses():
    """Each unit that the file writes is a declared unit or made of them; the parts that the prelude
    does not hold are the package's own units, and the package declares no other. Without its units
    file, the model does not compile."""
    text = (PIANO / ENTRY).read_text(encoding='utf-8')
    parts = set().union(*(unit_parts(unit) for unit in written_units(text)))
    own = json.loads((PIANO / 'units.json').read_text(encoding='utf-8'))
    assert parts - set(PRELUDE) == set(own)
    model = model_of('piano_tuners')
    assert set(own) <= set(thaw(model.library)['units'])


def test_piano_tuners_does_not_compile_without_its_units(tmp_path):
    shutil.copytree(PIANO, tmp_path / 'piano_tuners', ignore=shutil.ignore_patterns('units.json'))
    with pytest.raises(ModelError) as caught:
        load_scenario(tmp_path / 'piano_tuners' / ENTRY)
    own = json.loads((PIANO / 'units.json').read_text(encoding='utf-8'))
    messages = ' '.join(item['message'] for item in caught.value.diagnostics)
    assert any(f"unknown unit '{name}" in messages for name in own)


def test_the_rate_of_the_tuners_is_in_a_composed_unit_with_no_entry():
    model = model_of('piano_tuners')
    unit = model.inputs['tuners.rate']['unit']
    own = json.loads((PIANO / 'units.json').read_text(encoding='utf-8'))
    assert unit == 'tunings/tuner-year' and unit not in own and unit not in PRELUDE
    assert unit_parts(unit) == {'tunings', 'tuner', 'year'}


def tunings_done(values, horizon):
    """The closed form of the tunings done by `horizon` hours: the rate times the tuners times the time,
    in years, until the tunings that the pianos need run out."""
    return min(values['tuners.need'], values['tuners.rate'] * values['tuners.staff'] * horizon / YEAR)


@pytest.mark.parametrize(
    'body',
    [
        None,
        {'set': {'tuners.staff': 2, 'tuners.rate': 700}},
        {'set': {'tuners.staff': 8, 'tuners.need': 3000}},
    ],
    ids=['default', 'fewer tuners', 'the tunings run out'],
)
def test_the_tunings_done_are_the_rate_times_the_tuners_times_the_time(body):
    model = model_of('piano_tuners')
    study = evaluate_study(model, edits_for(model, body) if body else None)
    assert study.admissible, study.diagnostics
    values = study.runs['base']['resolved'].parameter_values
    horizon = model.time['horizon']
    done = points(study, 'base', [horizon / 2])
    for t in (horizon / 2, horizon):
        assert done[t]['tunings_done'] == pytest.approx(tunings_done(values, t), rel=1e-9)
    # The tunings that the pianos still need and those done add up to the need.
    trajectory = study.runs['base']['trajectory']
    end = trajectory.env_at(horizon)
    assert end['tuners.due'] + end['tuners.done'] == pytest.approx(values['tuners.need'], rel=1e-12)


def test_each_sample_of_the_tuners_draws_its_rate_and_holds_the_closed_form():
    """The rate is a distribution: each of 8 samples draws its own rate within the support of the
    distribution, and each sample's total is its closed form."""
    model = model_of('piano_tuners')
    support = model.inputs['tuners.rate']['distribution']['args']
    result = evaluate_uncertainty(model, None, SamplingSettings(8, seed=7))
    assert result.admissible, result.diagnostics
    sampled = result.samples['base']
    rates = [values['tuners.rate'] for values in sampled['values']]
    assert len(set(rates)) == 8 and all(support['min'] <= rate <= support['max'] for rate in rates)
    for values, completed in zip(sampled['values'], sampled['runs']):
        trajectory = completed['trajectory']
        done = trajectory.env_at(trajectory.horizon)['tuners.done']
        assert done == pytest.approx(tunings_done(values, trajectory.horizon), rel=1e-9)


# ---- reservoir --------------------------------------------------------------------------------------


def operator_of(model):
    (operator,) = [actor for actor in actors(model) if actor['name'] == 'operator']
    return operator


def test_the_reservoir_is_one_run_with_an_operator_who_sees_and_chooses():
    """One run and no options, so `napkin play` needs no run; the operator's choice is what varies."""
    model = model_of('reservoir')
    assert len(model.runs) == 1 and not model.menu
    operator = operator_of(model)
    assert operator['sees'] and len(operator['choices']) == 1
    assert len(operator['choices'][0]['outcomes']) >= 2


def test_a_played_reservoir_waits_for_the_operator_with_what_the_operator_sees():
    model = model_of('reservoir')
    operator = operator_of(model)
    (run,) = model.runs
    study = evaluate_study(model, play={'run': run, 'control': {'operator': 'reader'}, 'picks': []})
    assert study.admissible, study.diagnostics
    decision = study.decision
    assert decision['event'] == operator['choices'][0]['event']
    assert set(decision['view']) == set(operator['sees'])
    assert all(outcome['available'] for outcome in decision['outcomes'])


def opened(trace, event, horizon):
    """The times in which the spillway is open: from the choice `event` with the outcome `open` to the
    end of the run, or none."""
    return [
        (entry['t'], horizon) for entry in trace if entry['rule'] == event and entry.get('outcome') == 'open'
    ]


def time_above(start, slope_of, breaks, level):
    """The hours in which a water level that starts at `start` and runs on straight lines between the
    times `breaks` (with the slope `slope_of(t)` on each) is at `level` or above."""
    total, water = 0.0, start
    for low, high in pairwise(breaks):
        slope = slope_of((low + high) / 2)
        end = water + slope * (high - low)
        if water >= level and end >= level:
            total += high - low
        elif slope and (water >= level) != (end >= level):
            crossing = low + (level - water) / slope
            total += (high - crossing) if slope > 0 else (crossing - low)
        water = end
    return total


def reservoir_study(model, body=None, picks=None):
    """(the study of the reservoir's run under the edits `body`, played with `picks` when they are
    given; its run; the water at the start and at the end; the outputs at the end, by their names)."""
    (run,) = model.runs
    play = None if picks is None else {'run': run, 'control': {'operator': 'reader'}, 'picks': picks}
    study = evaluate_study(model, edits_for(model, body) if body else None, play=play)
    assert study.admissible, study.diagnostics
    trajectory = study.runs[run]['trajectory']
    water = [trajectory.env_at(t)['reservoir.water'] for t in (0.0, trajectory.horizon)]
    final = points(study, run, [])[trajectory.horizon]
    outputs = {name.rpartition('.')[2]: final[key] for name, key in model.outputs.items()}
    return study, run, water, outputs


EDITS = [
    None,
    {'set': {'reservoir.inflow': 0.07, 'reservoir.spillway': 0.1, 'reservoir.risk': 0.7}},
    {'set': {'reservoir.inflow': 0.08, 'reservoir.spillway': 0.05, 'operator.level': 0.75}},
]


@pytest.mark.parametrize(
    'body', EDITS, ids=['default', 'a slower spillway', 'a spillway slower than the storm']
)
def test_the_water_of_the_reservoir_balances_and_follows_the_operator(body):
    """The storm's water (its inflow times the time) is the change of the water in the reservoir plus
    the water let out over the spillway; the spillway lets out its rate while it is open; the choice
    comes when the water reaches the operator's level; and the time above the risk level is that of
    the straight lines of the water before and after the choice."""
    model = model_of('reservoir')
    event = operator_of(model)['choices'][0]['event']
    study, run, (start, end), outputs = reservoir_study(model, body)
    values = study.runs[run]['resolved'].parameter_values
    inflow, spillway = values['reservoir.inflow'] / DAY, values['reservoir.spillway'] / DAY
    horizon = model.time['horizon']
    assert end - start + outputs['spilled'] == pytest.approx(inflow * horizon, rel=1e-9)
    spans = opened(study.runs[run]['trajectory'].trace, event, horizon)
    assert len(spans) == 1  # the model's operator opens the spillway at the level
    assert outputs['spilled'] == pytest.approx(spillway * sum(b - a for a, b in spans), rel=1e-9)
    assert spans[0][0] == pytest.approx((values['operator.level'] - start) / inflow, rel=1e-9)
    breaks = sorted({0.0, horizon, *(t for span in spans for t in span)})

    def slope_of(t):
        return inflow - (spillway if any(a <= t < b for a, b in spans) else 0.0)

    risk = time_above(start, slope_of, breaks, values['reservoir.risk'])
    assert outputs['risk_time'] == pytest.approx(risk, abs=1e-6)


def test_an_operator_who_waits_lets_no_water_out_and_is_at_risk_for_longer():
    """A pick to wait keeps the spillway closed: nothing goes over it, and the water rises with the
    storm alone, on one straight line. The spillway only lowers the water, so with a wait the water is
    above the risk level at least as long as when the spillway opens."""
    model = model_of('reservoir')
    event = operator_of(model)['choices'][0]['event']
    study, run, (start, end), waited = reservoir_study(model, picks=[{'event': event, 'outcome': 'wait'}])
    _, _, _, at_level = reservoir_study(model)
    values = study.runs[run]['resolved'].parameter_values
    inflow, horizon = values['reservoir.inflow'] / DAY, model.time['horizon']
    assert waited['spilled'] == 0
    assert end == pytest.approx(start + inflow * horizon, rel=1e-9)
    risk = time_above(start, lambda t: inflow, [0.0, horizon], values['reservoir.risk'])
    assert waited['risk_time'] == pytest.approx(risk, abs=1e-6)
    assert waited['risk_time'] >= at_level['risk_time'] - 1e-6
