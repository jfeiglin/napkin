"""Authored edit overrides and input names for independent catalogue oracles."""

import json
from functools import cache

from napkin.model.runs import options_of
from tests.helpers import ROOT
from tools import catalogue


def reaching(model, edits, run):
    """{input: value} of the edits of an edit body that reach one run, by the documented precedence:
    every run, then the run's options, then the run itself; a narrower level wins
    (napkin/schema/edits.schema.json)."""
    values = dict(edits.get('set') or {})
    for option in options_of(model.declared, run):
        values.update((edits.get('options') or {}).get(option) or {})
    values.update((edits.get('runs') or {}).get(run) or {})
    return values


@cache
def oracle_manifest(scenario_id):
    """The independent oracle-input map owned by one scenario."""
    path = catalogue.locate(scenario_id, ROOT).folder / 'tests' / 'oracle-inputs.json'
    return json.loads(path.read_text(encoding='utf-8'))


@cache
def oracle_names(scenario_id):
    """{oracle name: entity.field} of one scenario, over every module of the table."""
    names = {}
    for module in oracle_manifest(scenario_id).values():
        for name, inputs in module['parameters'].items():
            if scenario_id in inputs:
                assert names.setdefault(name, inputs[scenario_id]) == inputs[scenario_id], name
    return names


def oracle_inputs(scenario_id, values):
    """A run's input values (`entity.field`, as the resolved run or the report gives them) under the
    names that the oracles read."""
    return {name: values[input_] for name, input_ in oracle_names(scenario_id).items()}
