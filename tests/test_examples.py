"""Run both example packages and compare their public readings with independent calculations."""

import json
import math
import re
import shutil
import tomllib
from fractions import Fraction
from itertools import product
from pathlib import Path

import pytest

import napkin
from napkin.engine import SamplingSettings
from napkin.model.language.format import format_text
from napkin.model.language.problems import LanguageError
from napkin.model.library import vocabulary_path
from napkin.paths import ENTRY
from napkin.program.checkpoint import Breakpoint

ROOT = Path(__file__).resolve().parents[1]
EXAMPLES = ROOT / 'examples'
FOLDERS = sorted(folder for folder in EXAMPLES.iterdir() if (folder / ENTRY).is_file())
PRELUDE = json.loads((ROOT / 'napkin/std/units.json').read_text())
YEAR = PRELUDE['year']['scale']
OUTPUTS = {
    'piano_tuners': ('tunings_done',),
    'reservoir': ('reservoir.spilled', 'reservoir.risk_time'),
}
PIANO = EXAMPLES / 'piano_tuners'
RESERVOIR = EXAMPLES / 'reservoir'
SWITCH = 'operator.decide.step[0].do[1]'
ORDER = 'operator.decide#0.order'


def configure(model, settings):
    if not settings:
        return model.configuration
    return model.configure(
        edits={'schema_version': napkin.SCHEMA_VERSION, 'model_hash': model.model_hash, 'set': settings}
    )


def test_the_examples_are_found():
    assert {folder.name for folder in FOLDERS} >= OUTPUTS.keys()


@pytest.mark.parametrize('folder', FOLDERS, ids=lambda folder: folder.name)
def test_an_example_compiles_and_its_default_study_finishes_with_finite_outputs(folder):
    models = napkin.load_package(folder)
    assert tuple(models) == (folder.name,)
    model = models[folder.name]
    assert not model.reports
    records = napkin.study(model)
    assert len(records) == 1
    for record in records.values():
        assert record.failure is None and record.end == model.configuration.request.horizon
        reported = napkin.report(
            record, model.program, model.configuration, OUTPUTS[folder.name], [record.end], table=model.table
        )
        assert all(math.isfinite(row.values[0]) for row in reported.values)


@pytest.mark.parametrize('folder', FOLDERS, ids=lambda folder: folder.name)
def test_an_example_is_its_own_formatted_text(folder):
    text = (folder / ENTRY).read_text()
    assert format_text(text) == text


@pytest.mark.parametrize('folder', FOLDERS, ids=lambda folder: folder.name)
def test_each_input_and_output_rests_on_a_record_written_in_place_and_no_source(folder):
    model = napkin.load_scenario(folder)
    paths = [
        value.origin
        for template in model.program.templates
        for value in template.values
        if value.kind == 'input'
    ]
    for path in [*paths, *OUTPUTS[folder.name]]:
        (basis,) = model.table.evidence(path)
        assert not basis.name and not basis.claims and not basis.rests_on and basis.explanation, path
        assert basis.kind in {'assumption', 'identity', 'convention'}, path
    assert all(
        e.kind in {'assumption', 'identity', 'convention'}
        for loc in model.table.locations
        for e in loc.evidence
    )
    assert vocabulary_path(folder / ENTRY) is None
    assert not (folder / 'evidence').exists()


def test_piano_tuners_declares_exactly_the_units_that_it_uses():
    model = napkin.load_scenario(PIANO)
    custom = json.loads((PIANO / 'units.json').read_text())
    parts = {part for unit in model.program.units for part in re.findall(r'[A-Za-z_]\w*', unit.name)}
    assert parts - PRELUDE.keys() == custom.keys()
    for name, declaration in custom.items():
        assert dict(model.program.unit(name).dimension) == declaration['dimensions']


def test_piano_tuners_does_not_compile_without_its_units(tmp_path):
    shutil.copytree(PIANO, tmp_path / 'piano_tuners', ignore=shutil.ignore_patterns('units.json'))
    with pytest.raises(LanguageError) as caught:
        napkin.load_scenario(tmp_path / 'piano_tuners')
    assert any(p.code == 'unit' and 'tuner' in p.message for p in caught.value.problems)


def test_the_rate_of_the_tuners_is_in_a_composed_unit_with_no_entry():
    model = napkin.load_scenario(PIANO)
    template, _ = model.program.member('tuners')
    rate = next(v for v in template.values if v.name == 'rate')
    custom = json.loads((PIANO / 'units.json').read_text())
    assert rate.type.unit == 'tunings/tuner/year' and rate.type.unit not in custom | PRELUDE
    assert model.program.unit(rate.type.unit).scale == Fraction(1, YEAR)


def tunings_done(need, rate, staff, hours):
    return min(need, rate * staff * hours / YEAR)


@pytest.mark.parametrize(
    'settings',
    [{}, {'tuners.staff': 2, 'tuners.rate': 700}, {'tuners.staff': 8, 'tuners.need': 3000}],
    ids=['default', 'fewer tuners', 'the tunings run out'],
)
def test_the_tunings_done_are_the_rate_times_the_tuners_times_the_time(settings):
    model = napkin.load_scenario(PIANO)
    record = napkin.run(model.program, configure(model, settings))
    assert record.failure is None and record.end == YEAR
    times = [YEAR / 2, YEAR]
    need, rate, staff, done, due, total = napkin.read(
        record,
        model.program,
        ['tuners.need', 'tuners.rate', 'tuners.staff', 'tuners.done', 'tuners.due', 'tunings_done'],
        times,
    )
    for i, t in enumerate(times):
        expected = tunings_done(need.values[i], rate.values[i], staff.values[i], t)
        assert total.values[i] == pytest.approx(expected, rel=1e-9)
        assert due.values[i] + done.values[i] == pytest.approx(need.values[i], rel=1e-12)


def test_each_sample_of_the_tuners_draws_its_rate_and_holds_the_closed_form():
    model = napkin.load_scenario(PIANO)
    samples = napkin.monte_carlo(
        model.program,
        model.configuration,
        ['tuners.need', 'tuners.rate', 'tuners.staff', 'tuners.done'],
        [YEAR],
        SamplingSettings(8, 7),
    ).samples
    rates = []
    for sample in samples:
        assert sample.stopped is None
        (need,), (rate,), (staff,), (done,) = sample.values
        assert 600 <= rate <= 1200
        assert done == pytest.approx(tunings_done(need, rate, staff, YEAR), rel=1e-9)
        rates.append(rate)
    assert len(set(rates)) == 8


def test_the_reservoir_is_one_run_with_an_operator_who_sees_and_chooses():
    model = napkin.load_scenario(RESERVOIR)
    assert not model.declared.options and not model.declared.runs
    assert tomllib.loads((RESERVOIR / 'roles.toml').read_text())['entities']['operator'] == 'operator'
    assert 'operator' in tomllib.loads((RESERVOIR / 'style.toml').read_text())['role']['operator']
    session = napkin.Session(model.program, model.configuration, [Breakpoint(SWITCH)], table=model.table)
    session.advance()
    observed = session.view(['reservoir.water', ORDER])
    assert observed.stop.at == SWITCH and observed.stop.t == pytest.approx(40)
    level, choice = observed.values
    assert (level.path, level.unit, level.value) == ('reservoir.water', 'fraction', pytest.approx(0.7))
    assert choice.editable and choice.choices == ('OPEN', 'WAIT') and choice.value == 'OPEN'


def hours_at_risk(start, slope, hours, threshold):
    if not slope:
        return hours if start >= threshold else 0
    crossing = min(hours, max(0, (threshold - start) / slope))
    return hours - crossing if slope > 0 else crossing


# The three published example configurations plus the migration sweep.
SETTINGS = [
    ('0.06', '0.15', '0.8', '0.7'),
    ('0.07', '0.1', '0.7', '0.7'),
    ('0.08', '0.05', '0.8', '0.75'),
    *(
        (a, b, c, '0.7')
        for a, b, c in product(('0.03', '0.06'), ('0.06', '0.15'), ('0.6', '0.7', '0.8'))
        if (a, b, c) != ('0.06', '0.15', '0.8')
    ),
]


@pytest.mark.parametrize('inflow,spillway,risk,level', SETTINGS)
def test_the_water_of_the_reservoir_balances_and_follows_the_operator(inflow, spillway, risk, level):
    model = napkin.load_scenario(RESERVOIR)
    edits = dict(
        zip(
            ('reservoir.inflow', 'reservoir.spillway', 'reservoir.risk', 'operator.level'),
            map(float, (inflow, spillway, risk, level)),
            strict=True,
        )
    )
    record = napkin.run(model.program, configure(model, edits))
    assert record.failure is None and record.end == 120
    incoming, release = Fraction(inflow) / 24, Fraction(spillway) / 24
    threshold, opening_level, start = Fraction(risk), Fraction(level), Fraction('0.6')
    opens = (opening_level - start) / incoming
    assert [e.t for e in record.entries('fire', 'operator.decide.when[0]')] == pytest.approx(
        [float(opens)], rel=1e-9
    )
    times = (0, 24, 40, 60, 80, 96, 120)
    water, spilled, risk_time = napkin.read(
        record, model.program, ['reservoir.water', 'reservoir.spilled', 'reservoir.risk_time'], times
    )
    for i, at in enumerate(times):
        closed = min(opens, at)
        opened = at - closed
        level_now = start + incoming * at - release * opened
        duration = hours_at_risk(start, incoming, closed, threshold) + hours_at_risk(
            opening_level, incoming - release, opened, threshold
        )
        assert water.values[i] == pytest.approx(float(level_now), rel=1e-9)
        assert spilled.values[i] == pytest.approx(float(release * opened), rel=1e-9)
        assert water.values[i] + spilled.values[i] == pytest.approx(float(start + incoming * at), rel=1e-9)
        assert risk_time.values[i] == pytest.approx(float(duration), abs=1e-6)


def test_an_operator_who_waits_lets_no_water_out_and_is_at_risk_for_longer():
    model = napkin.load_scenario(RESERVOIR)
    session = napkin.Session(model.program, model.configuration, [Breakpoint(SWITCH)])
    session.advance()
    session.edit(ORDER, 'WAIT')
    session.advance()
    waited = session.record
    default = napkin.run(model.program, model.configuration)
    assert waited.failure is None and default.failure is None and waited.end == default.end == 120
    times = (40, 80, 120)
    water, spilled, risk = napkin.read(
        waited, model.program, ['reservoir.water', 'reservoir.spilled', 'reservoir.risk_time'], times
    )
    assert water.values == pytest.approx((0.7, 0.8, 0.9))
    assert spilled.values == (0, 0, 0)
    assert risk.values == pytest.approx((0, 0, 40), abs=1e-6)
    (usual_risk,) = napkin.read(default, model.program, ['reservoir.risk_time'], times)
    assert all(a <= b + 1e-6 for a, b in zip(usual_risk.values, risk.values, strict=True))
