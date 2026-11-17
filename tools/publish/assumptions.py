"""Render scenario-owned assumption inventories with their authored review status: one inventory in the
results folder of each scenario of the catalogue (`results/assumption-review.json`). No inventory covers
the catalogue as a whole."""

from __future__ import annotations

import json
from collections import Counter
from hashlib import sha256

from napkin.model.evidence import dependencies_of
from napkin.model.semantic import path_text

from .. import catalogue


def assumption_locations(citations, assumption_ids):
    """Locate the authored uses of assumptions selected by the dependency rule: the place of each line
    of the file that names one (`semantic.Citation`), as its text (`semantic.path_text`)."""
    for citation in citations:
        if citation.kind == 'assumption' and citation.id in assumption_ids:
            yield citation.id, path_text(citation.where)


def counts(records):
    return {
        'assumptions': len(records),
        'origin': dict(sorted(Counter(item.get('origin') or 'undeclared' for item in records).items())),
        'authoritative_review_status': dict(
            sorted(Counter(item['review_status'] for item in records).items())
        ),
        'reachable_in_current_scenarios': sum(bool(item['places']) for item in records),
        'retained_without_current_scenario_reference': sum(not item['places'] for item in records),
    }


def inventory(assumptions, citations, library, *, scenario=None):
    """The inventory of `assumptions`, with the places of the file that name each one that its
    citations (`semantic.Citation`) reach."""
    used = set(dependencies_of(((c.kind, c.id, c.where) for c in citations), library)['assumptions'])
    locations = {}
    for identifier, path in assumption_locations(citations, used):
        locations.setdefault(identifier, []).append(path)
    return [
        {
            'scenario': scenario,
            'id': item['id'],
            'title': item.get('title', item['id']),
            'origin': item.get('origin'),
            'origin_declared': 'origin' in item,
            'selection_status': item.get('status'),
            'review_status': item['review']['status'],
            'authoritative_review': item['review'],
            'decided': item.get('decided'),
            'places': sorted(set(locations.get(item['id'], []))),
            'cited_claims': sorted(
                (
                    {'claim': link['claim'], 'relation': link.get('relation')}
                    for link in item.get('supports', [])
                    if 'claim' in link
                ),
                key=lambda link: link['claim'],
            ),
        }
        for item in sorted(assumptions, key=lambda record: record['id'])
    ]


def artifacts(ctx):
    # Compilation validates ownership, references and every retained authoritative review.
    models = ctx.models
    outputs = {}
    for sid in ctx.paths:
        owner = catalogue.locate(sid, ctx.root)
        records = owner.collections()
        path = owner.evidence / 'assumptions.json'
        entries = inventory(
            records['assumptions'], models[sid].scenario.citations, models[sid].library, scenario=sid
        )
        payload = {
            'schema_version': '2',
            'record_kind': 'scenario_assumption_inventory',
            'scenario': sid,
            'authoritative_basis': {
                'path': path.relative_to(ctx.root).as_posix(),
                'sha256': sha256(path.read_bytes()).hexdigest(),
            },
            'status_policy': 'Each assumption retains its authored review status. This inventory adds no review.',
            'counts': counts(entries),
            'assumptions': entries,
        }
        outputs[catalogue.result(sid, 'assumption-review.json')] = (
            json.dumps(payload, indent=2, ensure_ascii=False) + '\n'
        )
    return outputs
