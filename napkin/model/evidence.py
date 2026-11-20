"""The shared evidence library: its checks, its digests and the references a document makes.

A scenario cites library claims, assumptions and conventions by ID in its records, the records of its
notes among them. Every reference must resolve. A claim's verification record pins a digest of the claim's content,
so a claim changed without a new review fails. A value whose record cites an exact datum of a
claim (`datum`) must equal it after unit conversion.
"""

from __future__ import annotations

import copy
import hashlib
import math
from collections.abc import Mapping

from ..core.units import rational
from ..expressions import ExpressionError, UnitSystem
from .ir import basis_records, diagnostic, thaw
from .load import dump_json, schema_errors, schema_identity


def canonical(value):
    return dump_json(value, sort_keys=True, separators=(',', ':'), allow_nan=False)


def digest(value):
    return hashlib.sha256(canonical(value).encode()).hexdigest()


def basis_content(record):
    """Authored content only; resolver aliases and use locations do not change its identity."""
    return {
        key: value
        for key, value in thaw(record).items()
        if key not in ('name', 'location', 'path', 'line', 'file')
    }


def basis_digest(record):
    return digest(basis_content(record))


def claim_digest(claim):
    """SHA-256 of every claim field except its verification record (canonical ASCII JSON)."""
    content = {key: value for key, value in claim.items() if key not in ('verification', 'verified')}
    return hashlib.sha256(
        dump_json(content, sort_keys=True, separators=(',', ':'), ensure_ascii=True).encode()
    ).hexdigest()


def citations(document):
    """Each claim, assumption and convention that a document names, in the order of the document:
    (`claim`, `assumption` or `convention`, its ID, the path of the mapping that names it).

    Any mapping whose `claim`, `assumption` or `convention` is a string names one.
    """

    def walk(value, path):
        if isinstance(value, Mapping):
            for kind in ('claim', 'assumption', 'convention'):
                if isinstance(value.get(kind), str):
                    yield kind, value[kind], path
            for key, child in value.items():
                yield from walk(child, (*path, key))
        elif isinstance(value, (list, tuple)):
            for i, child in enumerate(value):
                yield from walk(child, (*path, i))

    yield from walk(document, ())


def referenced(named, assumptions=None, conventions=None):
    """Claim and assumption IDs of citations (`citations`), each in first-seen order. Given the
    records of the assumptions and of the conventions, the claims that support the cited ones are
    reachable too."""
    claims, cited, ruled = {}, {}, {}
    for kind, name, _ in named:
        {'claim': claims, 'assumption': cited, 'convention': ruled}[kind][name] = None
    for records, names in ((assumptions, cited), (conventions, ruled)):
        supports = {item['id']: item.get('supports', ()) for item in records or ()}
        for name in names:
            claims.update((link['claim'], None) for link in supports.get(name, ()))
    return list(claims), list(cited)


def references(document, assumptions=None):
    """Claim and assumption IDs a document cites, each in first-seen order (`citations`). Given
    assumption records, their supporting claims are reachable too. Use ``dependencies`` when the
    library is available to follow related claims and sources."""
    return referenced(citations(document), assumptions)


def dependencies(document, library):
    """The complete evidence dependency closure, preserving first-seen order.

    Missing IDs are retained for validation. Each related edge is followed once, including
    cycles; sources are selected from every reached claim. Hashes, validation, integration and
    publication share this traversal rather than maintaining different definitions of use.
    """
    return dependencies_of(citations(document), library)


def dependencies_of(named, library):
    """The dependency closure (`dependencies`) of citations (`citations`): the claims, the assumptions,
    the sources and the conventions that they reach."""
    named = list(named)
    conventions = list(dict.fromkeys(name for kind, name, _ in named if kind == 'convention'))
    claims, assumptions = referenced(named, library.get('assumptions', ()), library.get('conventions', ()))
    indexed = {record['id']: record for record in library.get('claims', ())}
    found, sources = dict.fromkeys(claims), {}
    cursor = 0
    while cursor < len(claims):
        record = indexed.get(claims[cursor], {})
        cursor += 1
        if isinstance(record.get('source'), str):
            sources.setdefault(record['source'], None)
        for link in record.get('related', ()):
            name = link.get('claim')
            if isinstance(name, str) and name not in found:
                found[name] = None
                claims.append(name)
    return {
        'claims': claims,
        'assumptions': assumptions,
        'sources': list(sources),
        'conventions': conventions,
    }


def datum_matches(value, unit, datum, units):
    """A value in `unit` equals a cited datum after unit conversion."""
    declared, cited = units.parse_unit(unit), units.parse_unit(datum['unit'])
    return declared.compatible(cited) and (
        rational(value) * units.exact_scale(unit)
        == rational(datum['value']) * units.exact_scale(datum['unit'])
    )


def basis_errors(document, library, root=''):
    """Every claim, assumption, convention and datum reference in a document resolves, those of the
    records of the notes included. Verification status is read from the library, so a copied `verification_status` is
    rejected wherever it appears. (`datum_errors` checks the values that cite a datum.)
    """
    errors = []
    claims = {item['id']: item for item in library['claims']}
    assumptions = {item['id'] for item in library['assumptions']}
    conventions = {item['id'] for item in library.get('conventions', ())}

    def walk(value, path):
        if isinstance(value, Mapping):
            if 'verification_status' in value:
                errors.append(
                    diagnostic(
                        'verification_copy',
                        f'{path}/verification_status',
                        'Verification status is read from the library; a copy goes stale',
                    )
                )
            if isinstance(value.get('assumption'), str) and value['assumption'] not in assumptions:
                errors.append(diagnostic('provenance', path, f'Unknown assumption {value["assumption"]}'))
            if isinstance(value.get('convention'), str) and value['convention'] not in conventions:
                errors.append(diagnostic('provenance', path, f'Unknown convention {value["convention"]}'))
            if isinstance(value.get('claim'), str):
                if value['claim'] not in claims:
                    errors.append(diagnostic('provenance', path, f'Unknown claim {value["claim"]}'))
                elif 'datum' in value and not (
                    isinstance(value['datum'], str)
                    and value['datum'] in claims[value['claim']].get('data', {})
                ):
                    errors.append(diagnostic('provenance', path, f'Unknown datum {value["datum"]}'))
            for key, child in value.items():
                walk(child, f'{path}/{key}' if path else key)
        elif isinstance(value, (list, tuple)):
            for index, child in enumerate(value):
                walk(child, f'{path}/{index}' if path else str(index))

    walk(document, root)
    # The traversal above supplies precise paths for language-defined references. The shared
    # dependency closure also covers transitive evidence dependencies.
    reached = dependencies(document, library)
    known = {
        collection: {record['id'] for record in library.get(collection, ())}
        for collection in ('claims', 'assumptions', 'sources', 'conventions')
    }
    reported = {item['message'] for item in errors}
    for collection, names in reached.items():
        singular = {
            'claims': 'claim',
            'assumptions': 'assumption',
            'sources': 'source',
            'conventions': 'convention',
        }[collection]
        for name in names:
            message = f'Unknown {singular} {name}'
            if name not in known[collection] and message not in reported:
                errors.append(diagnostic('provenance', root or 'evidence', message))
                reported.add(message)
    return errors


def datum_errors(document, library, root=''):
    """A value with a unit whose record cites an exact datum of a claim (`datum`) equals it after
    unit conversion; any other value needs a derivation, a transfer or an assumption. A diagnostic
    names the part's own `path` when it has one. A link that is not a record is the shape check's to
    report.
    """
    errors = []
    claims = {item['id']: item for item in library['claims']}
    units = UnitSystem(library['units'])

    def walk(value, path):
        if isinstance(value, Mapping):
            records = [r for r in basis_records(value.get('basis')) if isinstance(r, Mapping)]
            if records and 'value' in value and 'unit' in value:
                where = value.get('path') if isinstance(value.get('path'), str) else path
                links = [
                    link
                    for record in records
                    for link in record.get('links') or []
                    if isinstance(link, Mapping)
                ]
                for link in links:
                    claim = claims.get(link.get('claim'))
                    data = claim.get('data', {}) if isinstance(claim, Mapping) else {}
                    datum = data.get(link.get('datum')) if isinstance(link.get('datum'), str) else None
                    if datum is not None:
                        try:
                            if not datum_matches(value['value'], value['unit'], datum, units):
                                errors.append(
                                    diagnostic(
                                        'evidence_value',
                                        where,
                                        'Reported parameter differs from its cited datum',
                                    )
                                )
                        except (KeyError, ExpressionError) as exc:
                            errors.append(diagnostic('evidence_value', where, exc))
            for key, child in value.items():
                walk(child, f'{path}/{key}' if path else key)
        elif isinstance(value, (list, tuple)):
            for index, child in enumerate(value):
                walk(child, f'{path}/{index}' if path else str(index))

    walk(document, root)
    return errors


def finite_errors(value, path):
    errors = []
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        if not math.isfinite(value):
            errors.append(diagnostic('nonfinite', path, 'Finite numbers are required'))
    elif isinstance(value, Mapping):
        for key, child in value.items():
            errors.extend(finite_errors(child, f'{path}/{key}'))
    elif isinstance(value, (list, tuple)):
        for index, child in enumerate(value):
            errors.extend(finite_errors(child, f'{path}/{index}'))
    return errors


def validate_library(library):
    """Semantic diagnostics of a schema-valid library."""
    errors = []
    for collection in ('sources', 'claims', 'assumptions', 'conventions'):
        ids = [item['id'] for item in library.get(collection, ())]
        if len(ids) != len(set(ids)):
            errors.append(diagnostic('duplicate_id', collection, 'Duplicate IDs'))
    sources = {item['id'] for item in library['sources']}
    for claim in library['claims']:
        verification = claim.get('verification', {})
        if 'content_sha256' in verification and claim_digest(claim) != verification['content_sha256']:
            errors.append(
                diagnostic(
                    'evidence_digest',
                    f'claims/{claim["id"]}',
                    'Claim changed since its evidence verification record',
                )
            )
        if claim['source'] not in sources:
            errors.append(
                diagnostic('provenance', f'claims/{claim["id"]}', f'Unknown source {claim["source"]}')
            )
    errors.extend(basis_errors(library, library, 'library') + datum_errors(library, library, 'library'))
    try:
        units = UnitSystem(library['units'])
    except ExpressionError as exc:
        errors.append(diagnostic('units', 'library/units', exc))
        return errors
    for claim in library['claims']:
        for name, datum in claim.get('data', {}).items():
            try:
                units.parse_unit(datum['unit'])
            except (ExpressionError, KeyError) as exc:
                errors.append(diagnostic('units', f'claims/{claim["id"]}/data/{name}', exc))
    return errors


_CHECKED = {}


def library_checks(library):
    """(diagnostics, digest) of a library, computed once per content and library schema."""
    try:
        library_digest = digest(library)
    except ValueError:
        return finite_errors(library, 'library') + schema_errors(library, 'library'), None
    key = (library_digest, schema_identity('library'))
    if key not in _CHECKED:
        errors = finite_errors(library, 'library') + schema_errors(library, 'library')
        if not errors:
            errors = validate_library(library)
        while len(_CHECKED) >= 8:
            _CHECKED.pop(next(iter(_CHECKED)))
        _CHECKED[key] = errors
    return copy.deepcopy(_CHECKED[key]), library_digest
