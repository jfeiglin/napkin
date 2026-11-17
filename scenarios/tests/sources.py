"""Authored catalogue files for tests that read or edit them (one model file per scenario), the
edits of an edit body that reach a run, and the names under which the independent oracles read a
run's inputs."""

import json
from functools import cache

from napkin.model.ir import thaw
from tests.helpers import ROOT
from tools import catalogue
from tools.publish.brief import brief_of


def source(scenario_id):
    """A catalogue scenario's model file, as authored, and its name."""
    path = catalogue.scenario_path(ROOT, scenario_id)
    return path.read_text(encoding='utf-8'), str(path)


def written_type(model, name):
    """The type that the file writes for the value `entity.member`: its unit, `duration`, …"""
    entity, _, member = name.rpartition('.')
    return thaw(model.scenario.entity(entity).value(member).type)


def response_of(model, run):
    """The run's option of the group that `choice_group` names in brief.toml: its defender response."""
    (option,) = (p for p in model.runs[run]['options'] if p in model.menu[brief_of(model).choice_group])
    return option


def reaching(model, edits, run):
    """{input: value} of the edits of an edit body that reach one run, by the documented precedence:
    every run, then the run's options, then the run itself; a narrower level wins
    (napkin/schema/edits.schema.json)."""
    values = dict(edits.get('set') or {})
    for option in model.runs[run]['options']:
        values.update((edits.get('options') or {}).get(option) or {})
    values.update((edits.get('runs') or {}).get(run) or {})
    return values


def numbers(values):
    """Input values as an expression reads them: a bool value is 1 or 0."""
    return {name: int(value) if isinstance(value, bool) else value for name, value in values.items()}


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
