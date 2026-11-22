"""The catalogue's library and its owned evidence resolve every reference, and the source manifest covers them."""

import json

import pytest

from napkin.model.evidence import validate_library
from napkin.model.library import load_library
from tests.helpers import ROOT, SCENARIO_IDS
from tools import catalogue


@pytest.mark.scenario_contract
def test_the_catalogue_library_resolves_every_reference():
    for sid in SCENARIO_IDS:
        lib = load_library(catalogue.scenario_path(ROOT, sid))
        assert validate_library(lib) == []
        assert all('elicitation' in a for a in lib['assumptions'] if a.get('origin') == 'model_redteam')


def test_the_manifest_counts_each_owned_library():
    from tools.evidence.manifest import PATH, artifacts

    document = json.loads(artifacts(ROOT)[PATH])
    for row in document['scenarios']:
        expected = catalogue.locate(row['scenario'], ROOT).collections()['sources']
        assert row['library_source_count'] == len(expected)


def test_the_manifest_covers_every_folder_that_owns_evidence():
    # A family folder of modules owns its records once; the scenarios that read it do not.
    from napkin.model.library import library_folders
    from tools.evidence.manifest import PATH, artifacts

    document = json.loads(artifacts(ROOT)[PATH])
    listed = {row['scenario'] for row in document['scenarios']}
    folders = {
        catalogue.owner_of(folder)
        for path in catalogue.entries(ROOT).values()
        for folder in library_folders(path)
    }
    assert None not in folders and folders <= listed
    assert len(listed) == len(document['scenarios'])
