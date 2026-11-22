"""Render the source-verification dossier of each scenario of the catalogue from the library.

This is a pure renderer of each folder's owned sources, claims and verification records: one dossier in
the results folder of each scenario (`results/source-verification.json`). No dossier covers the
catalogue as a whole.
"""

from collections import Counter

from napkin import SCHEMA_VERSION
from napkin.model.compile import Compiled
from napkin.model.evidence import citations, dependencies_of
from napkin.model.language.evidence import document
from napkin.model.load import dump_json

from .. import catalogue

STATUSES = ('verified', 'partial', 'unverified')


def dossier(library, scenarios, *, effective_library=None):
    """The dossier of the library's sources and claims, each claim with the scenarios that reach it:
    `scenarios` maps names to compiled models or semantic models with citations. When claims
    reach shared records, the effective library supplies the entire dependency chain."""
    claims = {c['id']: c for c in library['claims']}
    reach = {cid: [] for cid in claims}
    for name, sc in sorted(scenarios.items()):
        named = (
            citations(document(sc.declared.tree))
            if isinstance(sc, Compiled)
            else ((c.kind, c.id, c.where) for c in sc.citations)
        )
        linked = dependencies_of(named, library if effective_library is None else effective_library)['claims']
        for cid in sorted(set(linked) & claims.keys()):
            reach[cid].append(name)
    by_source = {}
    for c in library['claims']:
        by_source.setdefault(c['source'], []).append(c)
    sources = []
    for s in library['sources']:
        custom = s['custom']
        v = custom['verification']
        entries = [
            {'id': c['id'], **c['verification'], 'reachable_from_scenarios': reach[c['id']]}
            for c in by_source.get(s['id'], [])
        ]
        entry = {
            'source_id': s['id'],
            'title': s['title'],
            'url': v['url'],
            'original_url': custom.get('original_url', custom.get('requested_url', s.get('URL', v['url']))),
        }
        entry.update(
            {k: v[k] for k in ('access', 'status', 'method', 'date', 'notes', 'retrieval') if k in v}
        )
        entry.update(
            claims=entries,
            reachable_from_scenarios=sorted({sid for e in entries for sid in e['reachable_from_scenarios']}),
        )
        sources.append(entry)
    verifications = [c['verification'] for c in library['claims']]

    def counts(values, order=None):
        found = Counter(values)
        return {k: found[k] for k in order} if order else dict(sorted(found.items()))

    summary = {
        'sources': len(sources),
        'claims': len(claims),
        'source_access': counts(
            s['custom']['verification'].get('access', 'unrecorded') for s in library['sources']
        ),
        'source_status': counts(
            (s['custom']['verification']['status'] for s in library['sources']), STATUSES
        ),
        'source_method': counts(s['custom']['verification']['method'] for s in library['sources']),
        'claim_status': counts((v['status'] for v in verifications), STATUSES),
        'claim_method': counts(v['method'] for v in verifications),
        'claim_method_status': counts(f'{v["method"]}/{v["status"]}' for v in verifications),
        'sources_with_retrieval': sum('retrieval' in s['custom']['verification'] for s in library['sources']),
        'claims_with_quotes': sum(bool(c.get('quotes')) for c in library['claims']),
        'claim_quote_match_records': sum(
            v.get('quote_match', {}).get('total', 0) > 0
            and v['quote_match']['matched'] == v['quote_match']['total']
            for v in verifications
        ),
        'claims_reachable': sum(bool(r) for r in reach.values()),
        'claims_reachable_from_no_scenario': sorted(cid for cid, r in reach.items() if not r),
    }
    review = library.get('metadata', {}).get('evidence_review', {})
    dates = [s['custom']['verification']['date'] for s in library['sources']] + [
        v['date'] for v in verifications
    ]
    return {
        'schema_version': SCHEMA_VERSION,
        'generated_by': 'tools.publish (dossier); edit the owned evidence records, never this file',
        'review_date': max(dates, default=None),
        'reviewer': 'Recorded machine primary-source review.',
        'method': 'Source entries preserve acquired bytes, extraction records and inspected source fields. Claim entries preserve substantive verification and supporting excerpts. Claims that rest on primary indexed extracts carry partial field coverage. Complete source reproduction (fresh byte, extraction and excerpt checks) is the evidence step of the release check.',
        'review_metadata': review,
        'quote_match_count_scope': 'Claims with a retained verification record storing a complete excerpt match.',
        'reachability': 'model.evidence.dependencies over the entry file of each owner (tools.catalogue.entries): basis links, the records that the notes cite, assumption supports and recursive related claims.',
        'summary': summary,
        'sources': sources,
    }


def artifacts(ctx):
    # Compilation checks each independent library before publication reads its owned records.
    _ = ctx.models
    outputs = {}
    for sid in ctx.paths:
        record = dossier(
            catalogue.locate(sid, ctx.root).collections(),
            {sid: ctx.models[sid]},
            effective_library=ctx.libraries[sid],
        )
        record['scenario'] = sid
        for source in record['sources']:
            source['scenario'] = sid
            for claim in source['claims']:
                claim['scenario'] = sid
        outputs[catalogue.result(sid, 'source-verification.json')] = (
            dump_json(record, indent=2, ensure_ascii=True) + '\n'
        )
    return outputs
