"""Shared test helpers: catalogue models, completed studies and the example edit sets. Result caches
have the session or test lifetime selected by pytest."""

import json
from decimal import Decimal
from functools import cache
from pathlib import Path

from napkin.engine import edits_for
from napkin.model import load_json, load_scenario
from napkin.model.load import dump_json
from tests.result_cache import result_cache
from tests.selection import selected
from tools import catalogue

ROOT = Path(__file__).resolve().parents[1]
# Every catalogue scenario (each owner with an entry file, `tools.catalogue.entries`), and the scenarios
# that this session checks: every one, or those that `--scenario` names (tests/selection.py). A test of
# one scenario at a time loops over SCENARIO_IDS; a test of the catalogue as a whole reads
# ALL_SCENARIO_IDS.
ALL_SCENARIO_IDS = tuple(catalogue.entries(ROOT))
SCENARIO_IDS = selected(ALL_SCENARIO_IDS)
# The example edit sets: each names its scenario, and `edits_for` binds it to the model revision.


@cache
def catalogue_model(scenario_id):
    return load_scenario(catalogue.scenario_path(ROOT, scenario_id))


@result_cache()
def catalogue_default(scenario_id):
    """The completed records of a catalogue scenario's named runs, or its single default run."""
    return catalogue.completed_study(catalogue_model(scenario_id))


def catalogue_study(scenario_id, edits=None, *, runs=None):
    """A catalogue study under an edit body (`set`, `options`, `runs`; `edits_for` binds it),
    cached by its canonical record. ``runs`` selects the named runs with or without edits."""
    if not edits and runs is None:
        return catalogue_default(scenario_id)
    return _cached_catalogue_study(
        scenario_id, dump_json(edits or {}, sort_keys=True), None if runs is None else tuple(runs)
    )


@result_cache(maxsize=48)
def _cached_catalogue_study(scenario_id, encoded, runs):
    model = catalogue_model(scenario_id)
    return catalogue.completed_study(model, runs, edits_for(model, json.loads(encoded, parse_float=Decimal)))


def example_edit_sets():
    """Selected saved edit sets in their scenario directories: {path: (scenario id, edits)}.

    The edits are the record without its `scenario`: the body of an edit document (`reason`, `set`,
    `options`, `runs`) that `edits_for` binds to the model revision. Any other key is left in,
    so that the edit document's schema rejects it."""
    examples = {}
    for path in sorted(
        edit
        for sid in catalogue.entries(ROOT)
        if sid in SCENARIO_IDS
        for edit in (catalogue.locate(sid, ROOT).folder / 'edits').glob('*.json')
    ):
        record = load_json(path, exact_numbers=True)
        examples[path.relative_to(ROOT).as_posix()] = (
            record['scenario'],
            {key: value for key, value in record.items() if key != 'scenario'},
        )
    return examples
