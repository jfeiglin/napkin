"""Publish acquisition records and restore hash-matching evidence bytes.

    python -m tools.evidence.manifest --check
    python -m tools.evidence.manifest --restore-project
    python -m tools.evidence.manifest --acquire SOURCE_ID
    python -m tools.evidence.manifest --acquire-all
    python -m tools.evidence.manifest --import SOURCE_ID=/path/to/raw-document

Acquisition verifies the recorded SHA-256 and size before placing raw bytes in
the selected cache. The library retains its reviewed acquisition provenance.
"""

import argparse
import hashlib
import json
import sys
from pathlib import Path

from .. import catalogue
from ..catalogue import ROOT
from .fetch import CACHE, curl, sniff, store
from .integrate import cached_bytes

# The manifest of the catalogue, in its evidence guides, as a path of the checkout.
PATH = f'{catalogue.DOCS}/evidence/source-manifest.json'
# The project's own documents that the repository holds, by the ID of their source: their bytes are
# the acquired bytes (`--restore-project`). The repository holds none now.
BUNDLED = {}


def manifest(library, scenario=None):
    sources = []
    for source in library['sources']:
        retrieval = source['custom']['verification'].get('retrieval')
        item = {
            'id': source['id'],
            'title': source.get('title'),
            'publication_url': source.get('URL'),
            'retrieval': retrieval,
            'claims': [c['id'] for c in library['claims'] if c['source'] == source['id']],
        }
        if source['id'] in BUNDLED:
            item['project_document'] = BUNDLED[source['id']]
        if retrieval:
            item['acquisition_url'] = retrieval.get('archived_url', retrieval['final_url'])
            item['import_command'] = (
                'python -m tools.evidence.manifest '
                + (f'--scenario {scenario} ' if scenario else '')
                + f'--import {source["id"]}=/path/to/raw-document'
            )
        sources.append(item)
    return {
        'manifest_version': '1.0',
        'library_source_count': len(sources),
        'normalization': 'nfkc-lig-v2',
        'extractors': sorted({s['retrieval']['text']['extractor'] for s in sources if s['retrieval']}),
        'sources': sources,
    }


def artifacts(root=ROOT):
    """Deterministic generated manifest for release artifact verification."""
    root = Path(root)
    shared = manifest(catalogue.vocabulary(root))
    scenarios = [
        {'scenario': name, **manifest(owner.collections(), name)}
        for name, owner in catalogue.owners(root).items()
    ]
    document = {
        'manifest_version': '2.0',
        'shared': shared,
        'scenarios': scenarios,
        'library_source_count': shared['library_source_count']
        + sum(row['library_source_count'] for row in scenarios),
    }
    return {PATH: json.dumps(document, indent=2, ensure_ascii=True) + '\n'}


def recorded(item):
    """The retrieval record of a manifest item, which acquired bytes must match. A source without one
    has nothing to match: it is a problem to report, not bytes to accept."""
    if not item.get('retrieval'):
        raise ValueError(f'{item["id"]}: no retrieval record to verify acquired bytes against')
    return item['retrieval']


def restore(item, content, cache):
    record = recorded(item)
    sha = hashlib.sha256(content).hexdigest()
    if sha != record['sha256'] or len(content) != record['bytes']:
        raise ValueError(
            f'{item["id"]}: acquired sha256={sha}, bytes={len(content)}; expected sha256={record["sha256"]}, bytes={record["bytes"]}'
        )
    _, extension = sniff(content, record['media_type'], record['final_url'])
    _, path = store(content, extension, cache)
    return path


def acquire(item, cache, root=ROOT):
    """Reuse validated raw bytes or acquire a matching recorded publication."""
    record = recorded(item)
    existing = cached_bytes(record['sha256'], cache)
    if existing:
        content = existing.read_bytes()
        if len(content) == record['bytes'] and hashlib.sha256(content).hexdigest() == record['sha256']:
            return restore(item, content, cache)
    if item.get('project_document'):
        content = (Path(root) / item['project_document']).read_bytes()
    else:
        import tempfile

        with tempfile.TemporaryDirectory() as staging:
            fetched = curl(item['acquisition_url'], cache=staging)
            content = Path(fetched['cache_path']).read_bytes()
    return restore(item, content, cache)


def main(argv=None):
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument('--root', type=Path, default=ROOT)
    parser.add_argument('--scenario', help='Select one owning scenario for source acquisition')
    parser.add_argument('--manifest', type=Path)
    parser.add_argument('--cache', default=str(CACHE))
    parser.add_argument('--write', action='store_true')
    parser.add_argument('--check', action='store_true')
    parser.add_argument('--restore-project', action='store_true')
    parser.add_argument('--acquire', action='append', default=[], metavar='SOURCE_ID')
    parser.add_argument(
        '--acquire-all',
        action='store_true',
        help='Restore every recorded source, reusing hash-matching cached bytes',
    )
    parser.add_argument('--import', dest='imports', action='append', default=[], metavar='SOURCE_ID=PATH')
    args = parser.parse_args(argv)
    if args.scenario and (args.write or args.check):
        parser.error('--scenario selects acquisition; manifest publication always covers the catalogue')
    if args.scenario:
        try:
            owned = catalogue.owners(args.root, scenario_ids=[args.scenario])[args.scenario].collections()
        except ValueError as exc:
            parser.error(str(exc))
        document = {'scenario': args.scenario, **manifest(owned, args.scenario)}
    else:
        aggregate = json.loads(artifacts(args.root)[PATH])
        document = aggregate

    encoded = json.dumps(document, indent=2, ensure_ascii=True) + '\n'
    path = args.manifest or args.root / PATH
    if args.write:
        path.write_text(encoded, encoding='utf-8', newline='')
    if args.check and (not path.exists() or path.read_bytes() != encoded.encode('utf-8')):
        print('Source manifest requires regeneration with --write', file=sys.stderr)
        return 1
    if args.scenario:
        selected = document['sources']
    else:
        selected = [
            *aggregate['shared']['sources'],
            *(source for row in aggregate['scenarios'] for source in row['sources']),
        ]
    index = {}
    for item in selected:
        identifier = item['id']
        if identifier in index and index[identifier] != item:
            if identifier in args.acquire or any(
                spec.split('=', 1)[0] == identifier for spec in args.imports
            ):
                parser.error(f'{identifier} differs across scenarios; select --scenario')
        else:
            index[identifier] = item

    try:
        if args.restore_project:
            for item in selected:
                if item.get('project_document'):
                    print(restore(item, (args.root / item['project_document']).read_bytes(), args.cache))
        for spec in args.imports:
            sid, raw_path = spec.split('=', 1)
            print(restore(index[sid], Path(raw_path).read_bytes(), args.cache))
        acquisition_failures = []
        requested = [(sid, index.get(sid)) for sid in dict.fromkeys(args.acquire)]
        if args.acquire_all:
            requested.extend((item['id'], item) for item in selected)
        for sid, item in requested:
            try:
                if item is None:
                    raise ValueError(f'Unknown source {sid}')
                print(f'{sid}: {acquire(item, args.cache, args.root)}', flush=True)
            except (ValueError, KeyError, OSError, RuntimeError) as exc:
                acquisition_failures.append({'source': sid, 'problem': str(exc)})
                print(f'{sid}: {exc}', file=sys.stderr, flush=True)
        if acquisition_failures:
            print(json.dumps({'acquisitions_required': acquisition_failures}, indent=2), file=sys.stderr)
            return 1
    except (ValueError, KeyError, OSError, RuntimeError) as exc:
        print(str(exc), file=sys.stderr)
        return 1
    if not any((args.write, args.check, args.restore_project, args.imports, args.acquire, args.acquire_all)):
        sys.stdout.write(encoded)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
