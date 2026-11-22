"""Public observations for the IV-fluid recovery tests."""

import napkin
from tests.helpers import catalogue_model, catalogue_study

SCENARIO = 'iv_fluid_shortage'


def model():
    return catalogue_model(SCENARIO)


def record(run='subpar', **values):
    edits = {'runs': {run: values}} if values else None
    return catalogue_study(SCENARIO, edits, runs=[run])[run]


def readings(record, keys, hours):
    return {row.path: row.values for row in napkin.read(record, model().program, keys, hours)}


def starts(record):
    return {entry.owner.split('#')[0]: entry.t for entry in record.entries('start')}
