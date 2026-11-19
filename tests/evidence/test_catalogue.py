"""The evidence tools and the texts of the pages on the catalogue itself. The catalogue is in the old
language until stage M, and the publisher is ported in M (PLAN, change 13), so this file waits in
`tests/dormant.txt` and runs once both are.

- Every evidence file of every owner is in the format that pack integration writes.
- The coverage report covers every scenario of the catalogue, and the source manifest every owner.
- The publisher's source dossiers render every owned verification record, and count the retained
  excerpt records without claiming a fresh check.
- A role of an entity is one of the actors that the pages name, or an entity of its scenario.
"""

from __future__ import annotations

import json
from functools import cache

import pytest

from napkin.model import load_json
from napkin.model.compile import load_scenario
from tests.selection import selected
from tools import catalogue
from tools.evidence.integrate import coverage_report, dump
from tools.evidence.manifest import PATH, artifacts

ROOT = catalogue.ROOT
SCENARIO_IDS = selected(tuple(catalogue.entries(ROOT)))


def test_the_library_on_disk_is_in_the_format_integration_writes():
    # The records of each owner: each scenario's and variant's folder, and each folder of modules.
    paths = [path for owner in catalogue.owners(ROOT).values() for path in owner.evidence.glob('*.json')]
    assert paths
    for path in paths:
        text = path.read_text(encoding='utf-8')
        assert dump(json.loads(text)) == text


def test_the_coverage_report_and_the_manifest_cover_the_catalogue():
    lines = coverage_report(ROOT).splitlines()
    top = [line.split(':')[0].strip() for line in lines if line.startswith('  ') and line[2] != ' ']
    assert top == list(catalogue.entries(ROOT))
    document = json.loads(artifacts(ROOT)[PATH])
    assert {row['scenario'] for row in document['scenarios']} == set(catalogue.owners(ROOT))
    for row in document['scenarios']:
        for source in row['sources']:
            if source.get('retrieval'):
                assert f'--scenario {row["scenario"]} --import {source["id"]}=' in source['import_command']


@cache
def rendered_dossiers():
    """{scenario: its source dossier} as the publication builder renders them, each in the scenario's
    results folder; tests only read them."""
    from tools.publish import Context
    from tools.publish.dossier import artifacts as dossiers

    outputs = dossiers(Context(ROOT))
    assert set(outputs) == {
        catalogue.result(sid, 'source-verification.json') for sid in catalogue.entries(ROOT)
    }
    return {
        sid: json.loads(outputs[catalogue.result(sid, 'source-verification.json')])
        for sid in catalogue.entries(ROOT)
    }


def test_dossier_renders_every_owned_verification_record():
    owned = {
        sid: {
            name: load_json(catalogue.locate(sid, ROOT).evidence / f'{name}.json')
            for name in ('sources', 'claims')
        }
        for sid in catalogue.entries(ROOT)
    }
    rendered = rendered_dossiers()
    sources = {
        (row['scenario'], row['source_id']): row
        for dossier in rendered.values()
        for row in dossier['sources']
    }
    claims = {
        (row['scenario'], claim['id']): (row['source_id'], claim)
        for dossier in rendered.values()
        for row in dossier['sources']
        for claim in row['claims']
    }
    assert sources.keys() == {
        (sid, source['id']) for sid, records in owned.items() for source in records['sources']
    }
    assert claims.keys() == {
        (sid, claim['id']) for sid, records in owned.items() for claim in records['claims']
    }
    for sid, records in owned.items():
        for claim in records['claims']:
            source, row = claims[sid, claim['id']]
            assert source == claim['source']
            assert {
                key: value
                for key, value in row.items()
                if key not in ('id', 'scenario', 'reachable_from_scenarios')
            } == claim['verification']
        for source in records['sources']:
            row = sources[sid, source['id']]
            verification = source['custom']['verification']
            assert (row['title'], row['url'], row['status'], row['method'], row['notes']) == (
                source['title'],
                verification['url'],
                verification['status'],
                verification['method'],
                verification['notes'],
            )
        # Each dossier is its own folder's: its rows name its scenario, and it counts its folder's records.
        assert rendered[sid]['scenario'] == sid
        assert {row['scenario'] for row in rendered[sid]['sources']} <= {sid}
        assert rendered[sid]['summary']['sources'] == len(records['sources'])
        assert rendered[sid]['summary']['claims'] == len(records['claims'])


def test_dossier_counts_retained_excerpt_records_without_claiming_a_fresh_check():
    rendered = rendered_dossiers()
    for sid in catalogue.entries(ROOT):
        claims = load_json(catalogue.locate(sid, ROOT).evidence / 'claims.json')
        retained = sum(
            verification.get('quote_match', {}).get('total', 0) > 0
            and verification['quote_match']['matched'] == verification['quote_match']['total']
            for verification in (claim['verification'] for claim in claims)
        )
        assert rendered[sid]['summary']['claim_quote_match_records'] == retained
        assert 'complete_source_reproduction' not in rendered[sid]


@pytest.mark.scenario_contract
@pytest.mark.parametrize('sid', SCENARIO_IDS)
def test_every_role_is_an_actor_or_an_entity(sid):
    """A card's actor reads the role of its entity: one of the actors that the pages name, or an
    entity of the scenario, whose name the card shows."""
    from napkin.draw.model_map import ACTOR_NAMES

    declared = load_scenario(catalogue.scenario_path(ROOT, sid)).declared
    names = {entity.path for entity in declared.entities} | {member.path for member in declared.members}
    roles = {entity.role for entity in declared.entities if entity.role}
    assert roles <= set(ACTOR_NAMES) | names
