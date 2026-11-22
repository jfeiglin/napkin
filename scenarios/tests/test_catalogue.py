"""Catalogue entry points, evidence, completed studies and independently authored run orders."""

import itertools
import json
import math
from dataclasses import asdict

import pytest

from napkin import read, report, store
from napkin.draw.style import origin_of
from napkin.model.library import unused_shared_records
from napkin.model.runs import options_of
from napkin.program.reach import reach
from scenarios.tests.sources import reaching
from tests.helpers import (
    ALL_SCENARIO_IDS,
    ROOT,
    SCENARIO_IDS,
    catalogue_default,
    catalogue_model,
    catalogue_study,
    example_edit_sets,
)
from tools import catalogue, check
from tools.publish.brief import brief_of, reported_paths, shown, value_note


def test_every_scenario_file_is_a_catalogue_case():
    scenarios = ROOT / 'scenarios'
    variants = sorted(scenarios.glob('*/variants/*/model.scn'))
    varied = {path.parents[2] for path in variants}
    packages = [path for path in scenarios.glob('*/model.scn') if path.parent not in varied]
    files = sorted([*packages, *variants])
    assert files and files == sorted(catalogue.entries(ROOT).values())


@pytest.mark.parametrize('scenario_id', SCENARIO_IDS)
@pytest.mark.scenario_contract
def test_scenario_runs(scenario_id):
    model = catalogue_model(scenario_id)
    assert catalogue.name_of(origin_of(model)) == scenario_id
    assert check.catalogue_problems(model) == []
    for name, record in catalogue_default(scenario_id).items():
        config = model.configure(name)
        assert record.stop is None and record.end == config.request.horizon
        allowed = reach(model.program, config).events
        assert all(allowed[entry.part][0] for entry in record.entries('start'))
        assert store.key(model.program, config)

        paths = list(dict.fromkeys([*(reported_paths(model) or ()), *shown(brief_of(model), model, record)]))
        measured = [p for p in paths if value_note(model, 'not_estimated', p, 'reason') is None]
        outcome = report(
            record,
            model.program,
            config,
            measured,
            [record.end],
            table=model.table,
            options=options_of(model.declared, name),
        )
        json.dumps(asdict(outcome), allow_nan=False)
        damage = {}
        for reading in outcome.values:
            category = value_note(model, 'reporting', reading.path, 'category')
            if category in ('deaths', 'casualties', 'loss'):
                value = reading.values[0]
                assert math.isfinite(value) and value >= 0, (name, reading.path, value)
                damage[category] = value
        if {'deaths', 'casualties'} <= damage.keys():
            assert damage['deaths'] <= damage['casualties'] + 1e-6, name


def expected_orders(scenario_id):
    """Use the entry's own expectation or its family's shared expectation."""
    owner = catalogue.locate(scenario_id, ROOT)
    path = owner.folder / 'tests' / 'expected-orders.json'
    if not path.exists() and ':' in scenario_id:
        path = catalogue.locate(owner.package, ROOT).folder / 'tests' / 'expected-orders.json'
    return json.loads(path.read_text(encoding='utf-8'))


def test_every_case_has_its_expected_orders():
    assert ALL_SCENARIO_IDS
    for sid in ALL_SCENARIO_IDS:
        assert isinstance(expected_orders(sid), list), sid


def assert_expected_orders(scenario_id, records, edits):
    model = catalogue_model(scenario_id)
    for runs, outputs in expected_orders(scenario_id):
        assert len(runs) >= 2 and outputs, (scenario_id, runs, outputs)
        assert set(runs) <= records.keys(), (scenario_id, 'missing runs', set(runs) - records.keys())
        if any(reaching(model, edits, run) != reaching(model, edits, runs[0]) for run in runs[1:]):
            continue
        values = {
            run: [row.values[0] for row in read(records[run], model.program, outputs, [records[run].end])]
            for run in runs
        }
        for i, output in enumerate(outputs):
            observed = [values[run][i] for run in runs]
            assert all(isinstance(value, (int, float)) and math.isfinite(value) for value in observed)
            for a, b in itertools.pairwise(observed):
                assert a - b <= 1e-9 * max(1.0, abs(a), abs(b)), (runs, output, observed)


@pytest.mark.parametrize('scenario_id', SCENARIO_IDS)
@pytest.mark.scenario_contract
def test_the_standard_runs_keep_their_expected_orders(scenario_id):
    assert_expected_orders(scenario_id, catalogue_default(scenario_id), {})


@pytest.mark.parametrize('path', sorted(example_edit_sets()))
@pytest.mark.scenario_contract
def test_example_edit_set_runs_and_keeps_the_orders_it_binds(path):
    scenario_id, edits = example_edit_sets()[path]
    assert_expected_orders(scenario_id, catalogue_study(scenario_id, edits), edits)


def test_every_record_of_a_folder_of_modules_is_used_by_a_scenario_that_reads_it():
    packages = {owner.folder for owner in catalogue.owners(ROOT).values() if owner.variant is None}
    assert [item for package in sorted(packages) for item in unused_shared_records(package)] == []
