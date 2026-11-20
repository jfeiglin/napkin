"""The only writer of scenario claims and sources from evidence packs, with two read-only modes: the
check of the library against its sources (--check) and the evidence coverage report (--coverage).

    python -m tools.evidence.integrate [--packs .work/packs] [--cache .evidence-cache] [--write]
    python -m tools.evidence.integrate --check --complete --report evidence-check.json
    python -m tools.evidence.integrate --coverage

Packs are validated against tools/evidence/evidence-pack.schema.json and applied in sorted path
order. A pack names the owner of the folder that it writes (`scenario`: a scenario, a family's folder
of modules, or a variant `package:variant`; tools/catalogue.py). Every quote is re-matched against a
fresh extraction of cached bytes that still hash
to the recorded sha256, never a stored .extracted.txt, and status follows rules, never the
pack's say-so:

- verified: the pass opened the document; a retrieval in the pack has cached bytes matching
  its sha256 whose re-extraction by the recorded extractor reproduces its text sha256 (a
  changed extractor needs --reextract, which records the new one); every quote re-matches
  (at least one); the checked fields include shows, limits and quotes (and data when
  present); no field verdict is a mismatch; and the method is primary_full_text.
- partial: opened, but any of those fails. third_party_primary_retrieval is never verified.
- unverified with method access_attempt: not opened.

Records are upserted by id (existing ones keep their position, new ones append in pack
order), digests are recomputed with napkin.model.evidence.claim_digest for every claim
a pack writes, and the result must pass the compiler's library checks (schema and references)
before anything is written. Re-applying the same packs is a no-op. Dry run by default;
--write updates one scenario folder; the publisher, an optional tool, makes its dossier again.
A report goes to .work/reports/integrate.json.

--check reproduces library excerpts from the original cached source bytes. With --complete
it checks retrieval records, raw hashes, fresh extraction algorithms, text digests and excerpt
matches for every source and claim. Run it by hand with the acquired source cache, in the
extraction environment the records name (see scenarios/docs/evidence/README.md); no automatic check runs it.

--coverage prints the read-only evidence coverage report. It answers questions that
`tools.check` deliberately does not fail on: what each entity and template rests on, which claims
of a folder its model does not reach, and which machine red-team judgements the scenarios use. It
reads the uses of the records of each declared model (`trail.py`); the front end checks every
reference. What a value rests on is the caller's question, since the caller selects the values that
a report reads (D10): `python -m tools.evidence.trail MODEL PATH...` answers it for one run.

Each mode refuses the options of the other modes.
"""

import argparse
import copy
import hashlib
import json
import re
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from jsonschema import Draft202012Validator
from referencing import Registry, Resource

from napkin.model import load_json
from napkin.model.evidence import basis_errors, claim_digest, dependencies, library_checks
from napkin.model.library import (
    catalogue_root,
    folder_records,
    library_folders,
    load_library,
    shared_library,
)
from napkin.model.load import dump_json, schema_document

from .. import catalogue
from ..catalogue import ROOT
from .fetch import CACHE, extract_bytes
from .normalize import NORMALIZATION, match_quotes
from .trail import built, entities, package_document, summary, uses

# Pack integration.

# The schema of an evidence pack: a tool's file, which the compiler does not read.
PACK_SCHEMA = Path(__file__).with_name('evidence-pack.schema.json')
RANK = {'unverified': 0, 'partial': 1, 'verified': 2}
REQUIRED_FIELDS = {'shows', 'limits', 'quotes'}
CONTENT = ('locator', 'evidence_type', 'shows', 'limits', 'data', 'valid_for', 'related', 'quotes')
CLAIM_ORDER = (
    'id',
    'source',
    'locator',
    'evidence_type',
    'shows',
    'limits',
    'data',
    'valid_for',
    'related',
    'legacy_ids',
    'quotes',
)
PRIOR = re.compile(r' Previously (verified|partial) \([^)]*\)\.$')


class IntegrationError(ValueError):
    def __init__(self, problems):
        self.problems = list(problems)
        super().__init__('\n'.join(self.problems))


def dump(value):
    """The library's exact on-disk format (a load and re-dump is byte-identical): UTF-8 text."""
    return dump_json(value, indent=2, ensure_ascii=False) + '\n'


def load_packs(directory):
    return [(str(path), load_json(path, evidence=True)) for path in sorted(Path(directory).rglob('*.json'))]


def cached_bytes(sha256, cache=CACHE):
    found = [
        p for p in (Path(cache) / 'sha256' / sha256[:2]).glob(f'{sha256}.*') if '.extracted.' not in p.name
    ]
    return sorted(found)[0] if found else None


def check_retrieval(retrieval, cache=CACHE, reextract=False):
    """{'ok', 'text', 'extracted', 'problems', 'missing'}: text is always a fresh extraction of cached bytes.

    The bytes must hash to sha256; a stored .extracted.txt is never read. The same extractor must
    reproduce the recorded text sha256. A changed extractor (another Ghostscript or Python) is a
    problem unless reextract, which adopts the fresh text and returns its {extractor, sha256}.
    """
    sha, recorded = retrieval['sha256'], retrieval['text']

    def failed(problem, missing=False):
        return {'ok': False, 'text': None, 'problems': [problem], 'missing': missing}

    raw = cached_bytes(sha, cache)
    if raw is None:
        return failed(f'bytes {sha[:12]} not in the cache', True)
    content = raw.read_bytes()
    if hashlib.sha256(content).hexdigest() != sha or len(content) != retrieval['bytes']:
        return failed(f'cached bytes {sha[:12]} do not match the recorded sha256/size')
    try:
        extractor, text = extract_bytes(content, raw.suffix.lstrip('.').lower(), retrieval['media_type'])
    except Exception as exc:
        return failed(f'extraction failed: {exc}')
    extracted = {'extractor': extractor, 'sha256': hashlib.sha256(text.encode('utf-8')).hexdigest()}
    if extractor != recorded['extractor'] and not reextract:
        return failed(
            f'extractor changed: {recorded["extractor"]} recorded, {extractor} now (rerun integrate with --reextract)'
        )
    if extractor == recorded['extractor'] and extracted['sha256'] != recorded['sha256']:
        return failed(
            f'text sha256 differs from the record: the text does not derive from the cached bytes by {extractor}'
        )
    return {'ok': True, 'text': text, 'extracted': extracted, 'problems': [], 'missing': False}


def _ordered(record, order):
    return {
        **{k: record[k] for k in order if k in record},
        **{k: v for k, v in record.items() if k not in order},
    }


def _prior(existing, status):
    """Carry a downgrade note forward so re-application reproduces the same notes."""
    if not existing:
        return ''
    old = existing['verification']
    found = PRIOR.search(old.get('notes', ''))
    if found:
        return found.group(0) if RANK[found.group(1)] > RANK[status] else ''
    if RANK[old['status']] > RANK[status]:
        return f' Previously {old["status"]} ({old["method"]}, {old["date"]}).'
    return ''


def assess(claim, content, retrievals):
    """(status, method, reasons, retrieval sha or None, (matched, total) or None) by rule."""
    check = claim['check']
    if not check['opened']:
        return 'unverified', 'access_attempt', ['document not opened by this pass'], None, None
    method, reasons = check.get('method', 'primary_full_text'), []
    chosen = [
        r
        for r in retrievals
        if check.get('retrieval_sha256') in (r['record']['sha256'], r['record']['text']['sha256'])
    ]
    if not check.get('retrieval_sha256') and len(retrievals) == 1:
        chosen = retrievals
    retrieval = chosen[0] if chosen else None
    if retrieval is None:
        reasons.append('no retrieval in this pack matches check.retrieval_sha256')
    elif not retrieval['ok']:
        reasons.extend(retrieval['problems'])
    counts = (
        match_quotes(content.get('quotes', []), retrieval['text']) if retrieval and retrieval['ok'] else None
    )
    total = len(content.get('quotes', []))
    if not total:
        reasons.append('no quotes')
    elif counts and counts[0] < total:
        reasons.append(f'{counts[0]}/{total} quotes re-matched')
    missing = REQUIRED_FIELDS | ({'data'} if content.get('data') else set())
    if missing - set(check['checked_fields']):
        reasons.append('unchecked ' + ', '.join(sorted(missing - set(check['checked_fields']))))
    bad = sorted(f for f, verdict in check['field_verdicts'].items() if verdict.startswith('mismatch'))
    if bad:
        reasons.append('mismatch in ' + ', '.join(bad))
    if method != 'primary_full_text':
        reasons.append(f'method {method}')
    sha = (
        check.get('retrieval_sha256', retrieval['record']['sha256'] if retrieval else None)
        if retrieval and retrieval['ok']
        else None
    )
    return ('partial' if reasons else 'verified'), method, reasons, sha, counts


def _content(claim, existing, source_id, problems, where):
    if claim['action'] == 'reverify':
        if existing['verification'].get('content_sha256') != claim_digest(existing):
            problems.append(
                f'{where}: changed by hand since its review (stale content_sha256); use action revise with the full content'
            )
        base = {k: v for k, v in existing.items() if k != 'verification'}
        changed = [k for k in CONTENT if k in claim and claim[k] != existing.get(k)]
        if changed:
            problems.append(f'{where}: reverify changes {", ".join(changed)}; use action revise')
        return base
    base = {
        'id': claim['id'],
        'source': source_id,
        **{k: copy.deepcopy(claim[k]) for k in CONTENT if k in claim},
    }
    if existing and existing.get('legacy_ids'):
        base['legacy_ids'] = existing['legacy_ids']
    return _ordered(base, CLAIM_ORDER)


def _source_notes(pack, primary):
    parts = []
    if primary:
        r = primary['record']
        parts.append(
            f'Retrieved {r["final_url"]} at {r["retrieved_at"]} ({r["tool"]}, HTTP {r["http_status"]}, {r["bytes"]} bytes,'
            f' sha256 {r["sha256"]}); text by {primary["extracted"]["extractor"]}, sha256 {primary["extracted"]["sha256"]}.'
        )
    for failure in pack['access_failures']:
        parts.append(
            f'Access failed: {failure["url"]} via {failure["tool"]} (HTTP {failure["http_status"]}): {failure["error"]}.'
        )
    return ' '.join(parts) or 'No retrieval recorded.'


def _apply_source(lib, pack, sources, report):
    spec, sid = pack['source'], pack['source']['id']
    csl = spec.get('csl', {})
    source = sources.get(sid)
    if source is None:
        source = {'id': sid, **copy.deepcopy(csl), 'custom': {}}
        lib['sources'].append(source)
        sources[sid] = source
        report['new_sources'].append(sid)
    else:
        source.update(copy.deepcopy(csl))
    custom = source['custom']
    if 'title' in csl:
        custom.pop('title_status', None)
    if 'URL' in csl:
        custom.pop('url_precision', None)
    if 'metadata_status' in spec:
        custom['metadata_status'] = spec['metadata_status']
    return spec, source


def _finish_source(lib, pack, spec, source, retrievals, used):
    ok = [r for r in retrievals if r['ok']]
    primary = next((r for r in ok if r['record']['sha256'] in used), ok[0] if ok else None)
    claims = [c for c in lib['claims'] if c['source'] == spec['id']]
    if primary is None:
        status, method = 'unverified', 'access_attempt'
    else:
        method = spec.get('method', 'primary_full_text')
        status = (
            'verified'
            if method == 'primary_full_text'
            and claims
            and all(c['verification']['status'] == 'verified' for c in claims)
            else 'partial'
        )
    url = (
        primary['record']['final_url']
        if primary
        else source.get('URL')
        or next((f['url'] for f in pack['access_failures']), None)
        or source.get('custom', {}).get('verification', {}).get('url')
    )
    verification = {
        'status': status,
        'date': pack['date'],
        'method': method,
        'url': url,
        'notes': spec.get('notes') or _source_notes(pack, primary),
        'access': spec['access'],
    }
    if primary:
        r = primary['record']
        verification['retrieval'] = {
            **{
                k: r[k]
                for k in (
                    'requested_url',
                    'final_url',
                    'archived_url',
                    'http_status',
                    'retrieved_at',
                    'tool',
                    'media_type',
                    'bytes',
                    'sha256',
                )
                if k in r
            },
            'text': dict(primary['extracted']),
        }
    source['custom']['verification'] = verification


def _apply_assumptions(lib, path, pack, seen, problems):
    index = {a['id']: i for i, a in enumerate(lib['assumptions'])}
    upserts, retires = [r['id'] for r in pack['upsert']], [r['id'] for r in pack['retire']]
    for aid in upserts + retires:
        if aid in seen:
            problems.append(f'{path}: assumption {aid} also in {seen[aid]}')
        seen[aid] = path
    if set(upserts) & set(retires):
        problems.append(f'{path}: upserts and retires {sorted(set(upserts) & set(retires))}')
    for record in pack['upsert']:
        old = lib['assumptions'][index[record['id']]] if record['id'] in index else None
        if record.get('review', {}).get('status') != 'unreviewed':
            problems.append(
                f'{path}: assumption {record["id"]} must be unreviewed; packs never review, and only retire mark_replaced sets replaced'
            )
        if old is not None and record.get('origin') != old.get('origin'):
            problems.append(
                f'{path}: assumption {record["id"]} cannot change origin {old.get("origin")} to {record.get("origin")}'
            )
        if old is not None:
            lib['assumptions'][index[record['id']]] = copy.deepcopy(record)
        else:
            index[record['id']] = len(lib['assumptions'])
            lib['assumptions'].append(copy.deepcopy(record))
    for item in pack['retire']:
        position = next((i for i, a in enumerate(lib['assumptions']) if a['id'] == item['id']), None)
        if item['mode'] == 'delete':
            if position is not None:
                del lib['assumptions'][position]
        elif position is None:
            problems.append(f'{path}: cannot mark unknown assumption {item["id"]} replaced')
        else:
            review = lib['assumptions'][position].setdefault('review', {})
            review['status'] = 'replaced'
            if item.get('replaced_by'):
                review['replaced_by'] = item['replaced_by']


def pack_validator():
    """The schema of an evidence pack (`PACK_SCHEMA`, beside this tool), which reads the library's closed
    vocabulary of relations from the compiler's library schema (`napkin/schema/`): a pack with another
    relation fails before anything is applied."""

    def schema(path):
        return json.loads(path.read_text(encoding='utf-8'))

    library = Resource.from_contents(schema_document('library'))
    return Draft202012Validator(
        schema(PACK_SCHEMA),
        registry=Registry().with_resource('library.schema.json', library),
    )


def integrate(library, packs, cache=CACHE, reextract=False, *, scenario=None):
    """Pure core: (new library, report) from a library and [(path, pack)] in application order."""
    validator = pack_validator()
    problems = [
        f'{path}: {"/".join(map(str, e.path))} {e.message}'
        for path, pack in packs
        for e in validator.iter_errors(pack)
    ]
    if problems:
        raise IntegrationError(problems)
    targets = {pack['scenario'] for _, pack in packs}
    if len(targets) > 1 or (scenario is not None and targets - {scenario}):
        raise IntegrationError(['A pack batch must target one scenario folder'])
    lib = copy.deepcopy(library)
    sources = {s['id']: s for s in lib['sources']}
    claims = {c['id']: c for c in lib['claims']}
    before = {cid: c['verification']['status'] for cid, c in claims.items()}
    report = {
        'packs': [p for p, _ in packs],
        'new_sources': [],
        'new_claims': [],
        'upgrades': [],
        'downgrades': [],
        'mismatches': [],
        'retrieval_problems': [],
        'claims': {},
    }
    seen_sources, seen_claims, seen_assumptions, written = {}, {}, {}, set()
    for path, pack in packs:
        if pack.get('kind') == 'assumptions':
            _apply_assumptions(lib, path, pack, seen_assumptions, problems)
            continue
        sid = pack['source']['id']
        if sid in seen_sources:
            problems.append(f'{path}: source {sid} also in {seen_sources[sid]}')
        seen_sources[sid] = path
        if pack['source']['action'] == 'reverify' and sid not in sources:
            problems.append(f'{path}: reverify of unknown source {sid}')
            continue
        retrievals = [{'record': r, **check_retrieval(r, cache, reextract)} for r in pack['retrievals']]
        report['retrieval_problems'].extend(
            {'pack': path, 'sha256': r['record']['sha256'], 'problems': r['problems']}
            for r in retrievals
            if not r['ok']
        )
        spec, source = _apply_source(lib, pack, sources, report)
        used = set()
        for claim in pack['claims']:
            cid, where, existing = claim['id'], f'{path}: claim {claim["id"]}', claims.get(claim['id'])
            if cid in seen_claims:
                problems.append(f'{where} also in {seen_claims[cid]}')
                continue
            seen_claims[cid] = path
            if claim['action'] != 'new' and existing is None:
                problems.append(f'{where}: {claim["action"]} of unknown claim')
                continue
            if existing and existing['source'] != sid:
                problems.append(f'{where}: belongs to source {existing["source"]}, not {sid}')
                continue
            content = _content(claim, existing, sid, problems, where)
            status, method, reasons, sha, counts = assess(claim, content, retrievals)
            if sha:
                used.add(
                    next(
                        r['record']['sha256']
                        for r in retrievals
                        if sha in (r['record']['sha256'], r['record']['text']['sha256'])
                    )
                )
            check = claim['check']
            notes = (
                check['notes']
                + (f' Integration: partial because {"; ".join(reasons)}.' if status == 'partial' else '')
                + _prior(existing, status)
            )
            verification = {'status': status, 'date': pack['date'], 'method': method}
            if check.get('locator_checked'):
                verification['locator_checked'] = check['locator_checked']
            verification.update(
                checked_fields=list(check['checked_fields']) if check['opened'] else [],
                notes=notes,
                content_sha256=claim_digest(content),
            )
            if sha:
                verification.update(
                    retrieval_sha256=sha,
                    quote_match={'normalization': NORMALIZATION, 'matched': counts[0], 'total': counts[1]},
                )
            record = {**content, 'verification': verification}
            if existing is None:
                lib['claims'].append(record)
                claims[cid] = record
                report['new_claims'].append(cid)
            else:
                lib['claims'][lib['claims'].index(existing)] = record
                claims[cid] = record
            written.add(cid)
            bad = sorted(f for f, v in check['field_verdicts'].items() if v.startswith('mismatch'))
            if bad:
                report['mismatches'].append(
                    {'claim': cid, 'fields': {f: check['field_verdicts'][f] for f in bad}}
                )
            report['claims'][cid] = {
                'status': status,
                'method': method,
                'reasons': reasons,
                'quote_match': list(counts) if counts else None,
            }
            if cid in before and RANK[status] != RANK[before[cid]]:
                report['upgrades' if RANK[status] > RANK[before[cid]] else 'downgrades'].append(
                    {'claim': cid, 'from': before[cid], 'to': status}
                )
        if len(used) > 1:
            problems.append(
                f'{path}: claims cite {len(used)} different retrievals; the library records one per source'
            )
        _finish_source(lib, pack, spec, source, retrievals, used)
    known = set(claims)
    for cid in sorted(written):
        problems.extend(
            f'claim {cid}: related claim {r["claim"]} is not a library claim'
            for r in claims[cid].get('related', [])
            if r['claim'] not in known
        )
    for assumption in lib['assumptions']:
        if assumption['id'] in seen_assumptions:
            problems.extend(
                f'assumption {assumption["id"]}: supports unknown claim {s["claim"]}'
                for s in assumption.get('supports', [])
                if s['claim'] not in known
            )
    for claim in lib['claims']:
        if claim['id'] not in written and claim['verification'].get('content_sha256') != claim_digest(claim):
            problems.append(
                f'claim {claim["id"]}: content changed outside the pipeline; its digest is stale and is not recomputed here'
            )
    problems.extend(f'library {d["path"]}: {d["message"]}' for d in library_checks(lib)[0])
    if problems:
        raise IntegrationError(problems)
    return lib, report


def write_owned(model_path, library, *, folder=None):
    """Validate and write one folder's independent records, preserving shared vocabulary and the records
    of the other folders that the model reads (the folders of its modules, or of the scenario), which
    a pack of this folder cannot change. `folder` is the folder to write, by default the model's."""
    path = Path(model_path)
    target = (Path(folder) if folder is not None else path.parent).resolve()
    # The checkout of the model's catalogue, whose shared vocabulary each folder of it reads, and the
    # owner of the folder (a package, a variant `package:variant` or a folder of modules).
    root = catalogue_root(path)
    owner = catalogue.owner_of(target, root) or target.name
    shared = copy.deepcopy(shared_library(path))
    for other in library_folders(path):
        if other == target:
            continue
        owned = folder_records(other)
        shared['units'].update(owned['units'])
        for kind in ('sources', 'claims', 'assumptions'):
            shared[kind] = [*shared[kind], *owned[kind]]
    for name, unit in shared['units'].items():
        if library['units'].get(name) != unit:
            raise IntegrationError([f'Shared unit {name} cannot be changed by a pack of {owner}'])
    for kind in ('sources', 'claims', 'assumptions'):
        index = {record['id']: record for record in library[kind]}
        for record in shared[kind]:
            if index.get(record['id']) != record:
                raise IntegrationError(
                    [f'Shared record {record["id"]} cannot be changed by a pack of {owner}']
                )
    errors, _ = library_checks(library)
    if errors:
        raise IntegrationError([f'{error["path"]}: {error["message"]}' for error in errors])
    documents = {}
    for kind in ('sources', 'claims', 'assumptions'):
        shared_ids = {record['id'] for record in shared[kind]}
        documents[target / 'evidence' / f'{kind}.json'] = dump(
            [record for record in library[kind] if record['id'] not in shared_ids]
        )
    documents[target / 'units.json'] = dump(
        {key: value for key, value in library['units'].items() if key not in shared['units']}
    )
    previous = {target: target.read_bytes() if target.exists() else None for target in documents}
    try:
        for target, content in documents.items():
            if previous[target] != content.encode('utf-8'):
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_text(content, encoding='utf-8', newline='')
    except OSError:
        for target, content in previous.items():
            if content is None:
                target.unlink(missing_ok=True)
            else:
                target.write_bytes(content)
        raise


# Source reproduction (--check).


def extraction_environment_problems(library):
    """Mismatches between this environment and the extractors the library's records name."""
    from .fetch import GS, gs_version

    recorded = {
        extractor
        for source in library['sources']
        if (
            extractor := source.get('custom', {})
            .get('verification', {})
            .get('retrieval', {})
            .get('text', {})
            .get('extractor')
        )
    }
    problems = []
    python = f'{sys.version_info.major}.{sys.version_info.minor}'
    for name in sorted(recorded):
        if m := re.match(r'html\.parser-py(\d+\.\d+) ', name):
            if m.group(1) != python:
                problems.append(
                    f'records name Python {m.group(1)} for HTML extraction; this is Python {python}'
                )
        elif m := re.match(r'gs-(\S+) ', name):
            try:
                found = gs_version(GS)
            except (OSError, subprocess.CalledProcessError):
                found = 'not installed'
            if found != m.group(1):
                problems.append(f'records name Ghostscript {m.group(1)} for PDF extraction; found {found}')
    return problems


class RematchRows(list):
    """Claim rows with per-source reproduction results for complete coverage."""

    def __init__(self):
        super().__init__()
        self.source_checks = {}


def rematch(library, cache=CACHE, *, jobs=1, checked_sources=None):
    """Rows {claim, status, matched, total, problem, missing} for claims whose source has a retrieval."""
    texts, rows = {}, RematchRows()
    if jobs < 1:
        raise ValueError('jobs must be a positive integer')
    sources = [source for source in library['sources'] if source['custom']['verification'].get('retrieval')]

    def inspect(source):
        retrieval = source['custom']['verification']['retrieval']
        key = (str(cache), json.dumps(retrieval, sort_keys=True))
        if checked_sources is not None and key in checked_sources:
            return checked_sources[key]
        checked = check_retrieval(retrieval, cache)
        if checked_sources is not None:
            checked_sources[key] = checked
        return checked

    def retain(checks):
        for source, checked in zip(sources, checks):
            texts[source['id']] = checked
            rows.source_checks[source['id']] = {k: checked[k] for k in ('ok', 'missing', 'problems')}

    if jobs > 1:
        with ThreadPoolExecutor(max_workers=jobs) as executor:
            retain(executor.map(inspect, sources))
    else:
        retain(map(inspect, sources))
    for claim in library['claims']:
        found = texts.get(claim['source'])
        if found is None:
            continue
        v = claim['verification']
        row = {
            'claim': claim['id'],
            'status': v['status'],
            'matched': None,
            'total': len(claim.get('quotes', [])),
            'problem': '',
            'missing': found['missing'],
        }
        if not found['ok']:
            row['problem'] = '; '.join(found['problems'])
        else:
            row['matched'], row['total'] = match_quotes(claim.get('quotes', []), found['text'])
            recorded = v.get('quote_match')
            if recorded and (
                recorded['normalization'] == NORMALIZATION
                and [recorded['matched'], recorded['total']] != [row['matched'], row['total']]
            ):
                row['problem'] = f'recorded {recorded["matched"]}/{recorded["total"]}'
            elif v['status'] == 'verified' and (row['total'] == 0 or row['matched'] < row['total']):
                row['problem'] = 'verified claim does not fully re-match'
        rows.append(row)
    return rows


def retrieval_coverage(library, rows):
    """Full library coverage, including every source and claim retrieval record."""
    recorded = {s['id'] for s in library['sources'] if s['custom']['verification'].get('retrieval')}
    checked = {r['claim'] for r in rows}
    return {
        'sources': len(library['sources']),
        'sources_with_retrieval': len(recorded),
        'sources_without_retrieval': [s['id'] for s in library['sources'] if s['id'] not in recorded],
        'claims': len(library['claims']),
        'claims_checked': len(rows),
        'claims_without_retrieval': [c['id'] for c in library['claims'] if c['id'] not in checked],
        'claims_missing_bytes': sum(r['missing'] for r in rows),
        'claims_with_problems': sum(bool(r['problem']) for r in rows),
        'sources_checked': len(getattr(rows, 'source_checks', {})),
        'sources_missing_bytes': sum(r['missing'] for r in getattr(rows, 'source_checks', {}).values()),
        'sources_with_problems': sum(not r['ok'] for r in getattr(rows, 'source_checks', {}).values()),
    }


# The evidence coverage report (--coverage).


def _line(name, found):
    kinds = ', '.join(f'{kind} {count}' for kind, count in found['kinds'].items())
    return (
        f'{name}: {kinds or "no record"}; claims {", ".join(found["claims"]) or "none"}; '
        f'assumptions {", ".join(found["assumptions"]) or "none"}'
    )


def coverage_report(root=ROOT):
    """The evidence coverage report of the catalogue at `root`: for each owner that runs as a model of
    its own, the summary of its uses of records, the number of claims that its records reach, the
    summary of each entity and template (`trail.entities`), the claims of its own folder that it does not
    reach and the machine red-team records of its folder. A model is read with every record of its
    folder, cited or not (`allow_unused`)."""
    root = Path(root)
    lines = ['Evidence coverage by scenario and record ID']
    for sid, path in catalogue.entries(root).items():
        found = package_document(path)
        library = load_library(path, document=found, allow_unused=True)
        declared = built(path, library)
        reached = dependencies(found, library)
        owned = catalogue.locate(sid, root).collections()
        lines.append(f'  {_line(sid, summary(uses(declared)))}')
        lines.append(f'      claims reached {len(reached["claims"])}')
        lines.append('      entities')
        lines += [f'        {_line(name, each)}' for name, each in entities(declared).items()]
        orphans = sorted({record['id'] for record in owned['claims']} - set(reached['claims']))
        if orphans:
            lines.append('      unused claims: ' + ', '.join(orphans))
        for assumption in owned['assumptions']:
            if assumption.get('origin') == 'model_redteam':
                lines.append(f'      machine red-team record: {sid}:{assumption["id"]}')
    return '\n'.join(lines)


# The command.

# The options that each mode takes, by their argparse names. A mode refuses the options of the other
# modes, so no option has an argparse default: an option that is None was not given, and each mode
# applies its own defaults.
OPTIONS = {
    'pack integration': ('root', 'cache', 'scenario', 'report', 'packs', 'reextract', 'write', 'prune'),
    '--check': ('root', 'cache', 'scenario', 'report', 'jobs', 'complete', 'require_cache'),
    '--coverage': (),
}


def pack_mode(a):
    """The default mode: apply the packs of one scenario folder and write the report."""
    root = ROOT if a.root is None else a.root
    cache = str(CACHE) if a.cache is None else a.cache
    scenario = a.scenario[0] if a.scenario else None
    reextract, write, prune = bool(a.reextract), bool(a.write), bool(a.prune)
    try:
        packs = load_packs(a.packs or root / '.work/packs')
        problems = [
            f'{path}: {error.message}' for path, pack in packs for error in pack_validator().iter_errors(pack)
        ]
        if problems:
            raise IntegrationError(problems)
        targets = {pack['scenario'] for _, pack in packs}
        if len(targets) != 1:
            raise IntegrationError(['Supply packs for exactly one scenario folder'])
        owner = next(iter(targets))
        if scenario is not None and owner != scenario:
            raise IntegrationError(['Pack scenario does not match --scenario'])
        entries = catalogue.entries(root)
        folder = catalogue.locate(owner, root).folder.resolve()
        # The folder that the packs write: the folder of the owner that they name (a scenario, a variant
        # `package:variant`, or a folder of modules that scenarios use), read by the models of its readers
        # (`catalogue.readers`). A pack of a scenario reads the records of the folders of its modules and
        # changes none of them.
        names = catalogue.readers(root).get(owner, ())
        if not names:
            raise IntegrationError([f'Unknown scenario {owner}, or a folder that no scenario reads'])
        readers = [entries[name] for name in names]
        model_path = entries[owner] if owner in entries else readers[0]
        # The model may cite records that the packs add, so its references are checked on the library
        # that the packs make, below.
        original = load_library(model_path, allow_unused=True, references=False)
        lib, report = integrate(original, packs, cache, reextract, scenario=owner)
        # The records of the other folders that the readers read, which this pack cannot change.
        others = list(
            dict.fromkeys(other for path in readers for other in library_folders(path) if other != folder)
        )
        shared = copy.deepcopy(shared_library(model_path))
        for other in others:
            for kind, owned in folder_records(other).items():
                if kind != 'units':
                    shared[kind] = [*shared[kind], *owned]
        # A record of this folder is reached when a scenario that reads the folder reaches it, through
        # the records of every folder that the scenario reads.
        known = {kind: {r['id'] for r in lib[kind]} for kind in ('sources', 'claims', 'assumptions')}
        every = {
            kind: [*lib[kind], *(r for r in shared[kind] if r['id'] not in known[kind])]
            for kind in ('sources', 'claims', 'assumptions')
        }
        # Every record that a scenario that reads the folder cites exists once the packs apply.
        missing = [
            f'{name}: {problem["path"]}: {problem["message"]}'
            for name, path in zip(names, readers)
            for problem in basis_errors(package_document(path), {**lib, **every})
        ]
        if missing:
            raise IntegrationError(
                ['The model cites records that neither the library nor the packs hold', *missing]
            )
        reached = {kind: set() for kind in ('sources', 'claims', 'assumptions')}
        for path in readers:
            for kind, ids in dependencies(package_document(path), every).items():
                if kind in reached:
                    reached[kind] |= set(ids)
        report['scenario'] = owner
        report['orphans'] = {
            kind: sorted({r['id'] for r in lib[kind]} - set(reached[kind]) - {r['id'] for r in shared[kind]})
            for kind in ('sources', 'claims', 'assumptions')
        }
        if prune:
            # A record that no reader reaches goes, with the sources that only it reached: the orphans
            # are computed over everything that the readers reach, so one pass removes them all.
            gone = {kind: set(ids) for kind, ids in report['orphans'].items()}
            lib = {**lib, **{kind: [r for r in lib[kind] if r['id'] not in gone[kind]] for kind in gone}}
            report['pruned'], report['orphans'] = report['orphans'], {kind: [] for kind in gone}
        report['changed'] = lib != original
        report['written'] = bool(write and report['changed'])
        if report['written']:
            write_owned(model_path, lib, folder=folder)
        report_path = root / '.work/reports/integrate.json' if a.report is None else Path(a.report)
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text(dump(report), encoding='utf-8')
        print(
            f'{owner}: {len(packs)} packs; {"written" if report["written"] else "dry run"}; report {report_path}'
        )
        return 0
    except (IntegrationError, ValueError, OSError) as exc:
        print(str(exc), file=sys.stderr)
        return 1


def check_mode(a, p):
    """--check: reproduce the library excerpts of the shared vocabulary and of each selected owner from
    the cached source bytes, in the extraction environment that the records name."""
    root = ROOT if a.root is None else a.root
    cache = str(CACHE) if a.cache is None else a.cache
    jobs = 4 if a.jobs is None else a.jobs
    complete, require_cache = bool(a.complete), bool(a.require_cache)
    try:
        libraries = {
            name: owner.collections()
            for name, owner in catalogue.owners(root, scenario_ids=a.scenario).items()
        }
    except ValueError as exc:
        p.error(str(exc))
    libraries = {'shared': catalogue.vocabulary(root), **libraries}
    reports, checked_sources = {}, {}
    failed = 0
    for owner, library in libraries.items():
        problems = extraction_environment_problems(library)
        if problems:
            print('Source reproduction needs the recorded extraction environment: ' + '; '.join(problems))
            return 1
        rows = rematch(library, cache, jobs=jobs, checked_sources=checked_sources)
        count = 0
        for row in rows:
            print(
                f'{owner}:{row["claim"]} {"-" if row["matched"] is None else row["matched"]}/{row["total"]} {row["status"]}'
                + (f' ({row["problem"]})' if row['problem'] else '')
            )
            count += bool(row['problem']) and (not row['missing'] or require_cache or complete)
        totals = retrieval_coverage(library, rows)
        if complete:
            count += len(totals['sources_without_retrieval']) + len(totals['claims_without_retrieval'])
            count += sum(
                not row['ok']
                for sid, row in rows.source_checks.items()
                if not any(c['source'] == sid for c in library['claims'])
            )
        totals['failures'] = count
        reports[owner] = {'coverage': totals, 'sources': rows.source_checks, 'claims': rows}
        failed += count
    result = {
        'mode': 'complete' if complete else 'recorded_retrievals',
        'failures': failed,
        'scenarios': reports,
    }
    if a.report:
        Path(a.report).write_text(json.dumps(result, indent=2) + '\n', encoding='utf-8')
    print(json.dumps({'failures': failed, 'scenarios': len(libraries) - 1}, sort_keys=True), file=sys.stderr)
    return 1 if failed else 0


def coverage_mode():
    """--coverage: print the evidence coverage report of this checkout."""
    try:
        print(coverage_report(ROOT))
    except (ValueError, OSError) as exc:
        print(str(exc), file=sys.stderr)
        return 1
    return 0


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    modes = p.add_mutually_exclusive_group()
    modes.add_argument(
        '--check',
        action='store_true',
        default=None,
        help='Reproduce the library excerpts from the cached source bytes; apply no pack',
    )
    modes.add_argument(
        '--coverage',
        action='store_true',
        default=None,
        help='Print the evidence coverage report; apply no pack. It takes no other option',
    )
    common = p.add_argument_group('pack integration and --check')
    common.add_argument('--root', type=Path)
    common.add_argument('--cache')
    common.add_argument(
        '--scenario',
        action='append',
        help='Pack integration: require every pack to target this scenario (one only). '
        '--check: check only these owning folders (repeatable)',
    )
    common.add_argument(
        '--report',
        help='Write the report as JSON to this file (pack integration: by default '
        '.work/reports/integrate.json; --check: only when given)',
    )
    checks = p.add_argument_group('--check')
    checks.add_argument('--jobs', type=int, help='Bound the concurrent fresh source extractions (default 4)')
    checks.add_argument(
        '--complete',
        action='store_true',
        default=None,
        help='Require raw bytes, retrieval records and successful re-extraction for every library source and claim',
    )
    checks.add_argument(
        '--require-cache',
        action='store_true',
        default=None,
        help='Fail when a recorded retrieval is not cached locally',
    )
    packing = p.add_argument_group('pack integration')
    packing.add_argument('--packs', type=Path, help='The folder of packs (default: .work/packs)')
    packing.add_argument(
        '--reextract',
        action='store_true',
        default=None,
        help='Accept a changed extractor and record it with its fresh text',
    )
    packing.add_argument(
        '--write', action='store_true', default=None, help='Write this scenario folder (default: dry run)'
    )
    packing.add_argument(
        '--prune',
        action='store_true',
        default=None,
        help='Also remove the records of this folder that no scenario that reads it reaches',
    )
    a = p.parse_args(argv)
    mode = '--check' if a.check else '--coverage' if a.coverage else 'pack integration'
    refused = [
        '--' + name.replace('_', '-')
        for name, value in vars(a).items()
        if value is not None and name not in ('check', 'coverage', *OPTIONS[mode])
    ]
    if refused:
        p.error(f'{mode} does not take {", ".join(refused)}')
    if mode == 'pack integration' and a.scenario is not None and len(a.scenario) > 1:
        p.error('pack integration takes one --scenario')
    if mode == '--check':
        return check_mode(a, p)
    if mode == '--coverage':
        return coverage_mode()
    return pack_mode(a)


if __name__ == '__main__':
    raise SystemExit(main())
