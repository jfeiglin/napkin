"""Evidence coverage, verification records and display roles for the current catalogue."""

from __future__ import annotations

import json
import tomllib
from functools import cache

import pytest

from napkin.draw import style
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
    top = [line.split(': ', 1)[0].strip() for line in lines if line.startswith('  ') and line[2] != ' ']
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
    assert set(outputs) == {catalogue.result(sid, 'source-dossier.json') for sid in catalogue.entries(ROOT)}
    return {
        sid: json.loads(outputs[catalogue.result(sid, 'source-dossier.json')])
        for sid in catalogue.entries(ROOT)
    }


def test_dossier_renders_every_owned_verification_record():
    owned = {sid: catalogue.locate(sid, ROOT).collections() for sid in catalogue.entries(ROOT)}
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
        claims = catalogue.locate(sid, ROOT).collections()['claims']
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

    model = load_scenario(catalogue.scenario_path(ROOT, sid))
    found = style.things_of(model)
    roles = set(style.roles_of(style.of(model), found).values())
    path = style.lookup(catalogue.scenario_path(ROOT, sid), 'roles.toml')
    if path:
        with path.open('rb') as stream:
            wrapper = tomllib.load(stream)
        roles.update(wrapper.get('entities', {}).values())
        roles.update(wrapper.get('events', {}).values())
    assert roles <= set(ACTOR_NAMES) | set(found.cards)
