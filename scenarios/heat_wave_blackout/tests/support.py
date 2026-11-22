"""Public records and input values for the civilian response checks."""

import json
from functools import cache
from pathlib import Path

import napkin
from tests.helpers import catalogue_model, catalogue_study

SID = 'heat_wave_blackout'
FOLDER = Path(__file__).resolve().parents[1]


@cache
def model():
    return catalogue_model(SID)


def study(name='standard', edits=None):
    record = catalogue_study(SID, {'set': edits} if edits else None, runs=[name])[name]
    assert record.failure is None, record.failure
    return record


def readings(record, paths, times):
    return {r.path: r.values for r in napkin.read(record, model().program, tuple(paths), times)}


def oracle_values(record):
    manifest = json.loads((FOLDER / 'tests/oracle-inputs.json').read_text())
    names = next(iter(manifest.values()))['parameters']
    paths = {k: spec[SID] for k, spec in names.items()}
    observations = napkin.read(record, model().program, tuple(paths.values()), [0])
    out = {}
    for (name, _), row in zip(paths.items(), observations, strict=True):
        scale = model().program.unit(row.unit).scale if row.unit else 1
        out[name] = float(row.values[0]) * float(scale)
    return out
