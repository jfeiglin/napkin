"""Read the JSON files of a scenario (its library, units, edits and packages), and check a document
against the schemas of the package (`napkin/schema/`): duplicate keys and non-finite numbers are
rejected."""

from __future__ import annotations

import hashlib
import json
from decimal import Decimal
from pathlib import Path

from .. import schema as schemas


class SourceError(ValueError):
    """A file that is not valid source text, with the line it is about."""

    def __init__(self, path, line, message):
        self.path, self.line = str(path), line
        super().__init__(f'{path}:{line}: {message}' if line else f'{path}: {message}')


def _evidence_number(token):
    """Keep a decimal exactly, using a float only when its JSON spelling preserves the datum."""
    exact = Decimal(token)
    value = float(token)
    return value if Decimal(str(value)) == exact else exact


def dump_json(value, *, sort_keys=False, indent=None, ensure_ascii=True, separators=None, allow_nan=False):
    """Write JSON, including evidence numbers too precise to round-trip through a float."""
    options = dict(
        sort_keys=sort_keys,
        indent=indent,
        ensure_ascii=ensure_ascii,
        allow_nan=allow_nan,
        separators=separators,
    )
    try:
        return json.dumps(value, **options)
    except TypeError:
        # The standard encoder accepts no Decimal. Preserve its exact JSON number spelling.
        pass
    comma, colon = separators or ((',', ': ') if indent is not None else (', ', ': '))

    def write(item, depth):
        if isinstance(item, Decimal):
            if not item.is_finite():
                raise ValueError(f'non-finite JSON number {item}')
            return str(item)
        if isinstance(item, dict):
            keys = sorted(item) if sort_keys else item
            parts = [
                json.dumps(key, ensure_ascii=ensure_ascii) + colon + write(item[key], depth + 1)
                for key in keys
            ]
            left, right = '{', '}'
        elif isinstance(item, (tuple, list)):
            parts = [write(child, depth + 1) for child in item]
            left, right = '[', ']'
        else:
            return json.dumps(item, **options)
        if not parts or indent is None:
            return left + comma.join(parts) + right
        pad = '\n' + ' ' * (indent * (depth + 1))
        return left + pad + (comma + pad).join(parts) + '\n' + ' ' * (indent * depth) + right

    return write(value, 0)


def load_json(path, *, evidence=False):
    """A JSON document (library, edits, package): duplicate keys and non-finite numbers rejected."""

    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                raise SourceError(path, 0, f'duplicate key {key!r}')
            result[key] = value
        return result

    def bad_constant(value):
        raise SourceError(path, 0, f'non-finite number {value!r}')

    return json.loads(
        Path(path).read_text(encoding='utf-8'),
        object_pairs_hook=pairs,
        parse_constant=bad_constant,
        parse_float=_evidence_number if evidence else float,
    )


SCHEMAS = ('library', 'scenario-units', 'edits', 'report')
SCHEMA_BYTES = {name: schemas.path(name).read_bytes() for name in SCHEMAS}
_SCHEMA_DOCUMENTS = {name: json.loads(content) for name, content in SCHEMA_BYTES.items()}
_VALIDATORS = {}


def schema_identity(name):
    """The imported schema bytes used by every validator in this process."""
    return name, hashlib.sha256(SCHEMA_BYTES[name]).hexdigest()


def schema_document(name):
    """The schema `name` as this process imported it (`SCHEMA_BYTES`)."""
    return _SCHEMA_DOCUMENTS[name]


def schema_errors(document, name):
    """Structural diagnostics of a document against the schema `name` (`napkin/schema/`)."""
    from jsonschema import Draft202012Validator

    key = schema_identity(name)
    if key not in _VALIDATORS:
        _VALIDATORS[key] = Draft202012Validator(_SCHEMA_DOCUMENTS[name])
    out = []
    for error in sorted(_VALIDATORS[key].iter_errors(document), key=lambda item: str(list(item.path))):
        out.append(
            {
                'code': 'schema',
                'path': '/'.join(map(str, error.path)),
                'message': error.message,
                'severity': 'error',
            }
        )
    return out
