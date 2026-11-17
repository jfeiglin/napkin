"""Every catalogue scenario builds and runs; every example edit set runs.

For each scenario: its folders name it, and each of its outputs says whom it covers; its default study is admissible; its standard runs keep
their expected orders; its report is finite and serializable; and each damage output it estimates is
finite and nonnegative, with deaths inside casualties. Each example edit set runs and keeps the
expected orders among the runs that it edits alike.
"""

import itertools
import json
import math

import pytest

import napkin.engine as engine
from napkin import store
from napkin.engine import evaluate_study, sample_result
from napkin.engine.report import firing_rules
from napkin.model.ir import thaw
from tests.helpers import (
    ALL_SCENARIO_IDS,
    ROOT,
    SCENARIO_IDS,
    catalogue_default,
    catalogue_model,
    example_edit_sets,
)
from tools import catalogue, check


def test_every_scenario_file_is_a_catalogue_case():
    """A model file of a package or of a variant whose folder is not named as the catalogue names
    them would be left out of the checks and the summaries. A package with variants runs as its
    variants, whose models read its main file."""
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
    # The folders name the model: its package, and its variant.
    assert catalogue.name_of(model.origin) == scenario_id
    # The catalogue's own rules, which the language leaves open: each output says whom it covers.
    assert check.catalogue_problems(model) == []
    study = catalogue_default(scenario_id)
    report = sample_result(study)
    assert report['admissible'] is True, report['diagnostics']
    json.dumps(report, allow_nan=False)
    # Every rule that a run fires is one that the evidence trail's static check lets fire.
    for name, item in study.runs.items():
        fired = {entry['rule'] for entry in item['trajectory'].trace}
        assert fired <= firing_rules(item['resolved']), name
        # Each run has a key in the run store: its resolved structure is plain data.
        store.key(item['resolved'], thaw(model.library))
    for name, item in report['runs'].items():
        final = item['reporting_points']['final']
        damage = {
            definition['category']: output
            for output, definition in item['outcomes'].items()
            if definition.get('category') in ('deaths', 'casualties', 'loss')
            and final['statuses'][output] == 'estimated'
        }
        for output in damage.values():
            assert math.isfinite(final['values'][output]) and final['values'][output] >= 0, (name, output)
        if {'deaths', 'casualties'} <= damage.keys():
            assert final['values'][damage['deaths']] <= final['values'][damage['casualties']] + 1e-6, name


def expected_orders(scenario_id):
    """The cross-run orders frozen by the scenario's own acceptance fixtures."""
    path = catalogue.locate(scenario_id, ROOT).folder / 'tests' / 'expected-orders.json'
    return json.loads(path.read_text(encoding='utf-8'))


def test_every_case_has_its_expected_orders():
    assert ALL_SCENARIO_IDS and all(
        (catalogue.locate(sid, ROOT).folder / 'tests' / 'expected-orders.json').is_file()
        for sid in ALL_SCENARIO_IDS
    )


def reaching(model, edits, run):
    """The edits of an edit document that reach one run, level by level: every run, the run's options,
    and the run itself."""
    options = {}
    for option in model.runs[run]['options']:
        options.update((edits.get('options') or {}).get(option) or {})
    own = (edits.get('runs') or {}).get(run) or {}
    return json.dumps([edits.get('set') or {}, options, own], sort_keys=True)


def edited_alike(model, edits, runs):
    """Whether an edit set gives every compared run the same edits.

    An expected order compares runs that differ only as their options make them differ. An edit to
    one compared run, to the defender response of one, or to the start states of one run's attack
    changes what is compared, so the order then binds nothing. Edits to every run reach every run alike.
    """
    return len({reaching(model, edits, run) for run in runs}) == 1


def broken_expected_orders(model, report, edits=None):
    """The expected orders of a scenario that a report breaks, among the runs its edits treat alike.

    Along each tuple of runs, best to worst, no listed output falls, within the engine's relative
    tolerance. A value that is not estimated breaks the order: it is not zero, and it cannot be
    compared.
    """
    edits = edits or {}
    broken = []
    for runs, outputs in expected_orders(catalogue.name_of(model.origin)):
        if not edited_alike(model, edits, runs):
            continue
        for name in outputs:
            values = [report['runs'][run]['reporting_points']['final']['values'][name] for run in runs]
            if any(value is None for value in values) or any(
                a - b > 1e-9 * max(1.0, abs(a), abs(b)) for a, b in itertools.pairwise(values)
            ):
                broken.append((runs, name, values))
    return broken


@pytest.mark.parametrize('scenario_id', SCENARIO_IDS)
@pytest.mark.scenario_contract
def test_the_standard_runs_keep_their_expected_orders(scenario_id):
    report = sample_result(catalogue_default(scenario_id))
    assert broken_expected_orders(catalogue_model(scenario_id), report) == []


@pytest.mark.parametrize('path', sorted(example_edit_sets()))
@pytest.mark.scenario_contract
def test_example_edit_set_runs_and_keeps_the_orders_it_binds(path):
    scenario_id, edits = example_edit_sets()[path]
    model = catalogue_model(scenario_id)
    study = evaluate_study(model, engine.edits_for(model, edits))
    assert study.admissible, study.diagnostics
    report = sample_result(study)
    assert report['admissible'] is True
    assert broken_expected_orders(model, report, edits) == []


def test_every_record_of_a_folder_of_modules_is_used_by_a_scenario_that_reads_it():
    from napkin.model.library import unused_shared_records

    packages = {owner.folder for owner in catalogue.owners(ROOT).values() if owner.variant is None}
    assert [item for package in sorted(packages) for item in unused_shared_records(package)] == []
