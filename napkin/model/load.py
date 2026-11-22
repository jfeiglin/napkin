"""Read the JSON files of a scenario (its library, units, edits and packages), and check a document
against the schemas of the package (`napkin/schema/`): duplicate keys and non-finite numbers are
rejected."""

from __future__ import annotations

import hashlib
import json
from decimal import Decimal
from pathlib import Path

from .. import schema as schemas
from ..core.units import authored_decimal


class SourceError(ValueError):
    """A file that is not valid source text, with the line it is about."""

    def __init__(self, path, line, message):
        self.path, self.line = str(path), line
        super().__init__(f'{path}:{line}: {message}' if line else f'{path}: {message}')


def _json_number(exact):
    """Keep a decimal exactly, using a float only when its JSON spelling preserves the datum."""
    value = float(exact)
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


def load_json(path, *, evidence=False, exact_numbers=False):
    """A JSON document (library, edits, package): duplicate keys and non-finite numbers rejected."""
    return parse_json(Path(path).read_text(encoding='utf-8'), path, exact_numbers=evidence or exact_numbers)


def load_unit_document(path, *, vocabulary=False):
    """Read the authored scales of a units file or a vocabulary's units. Other numbers (including
    claim data) retain the exact JSON reader's representation and canonical digest."""

    def evidence(item):
        if isinstance(item, Decimal):
            return _json_number(item)
        if isinstance(item, dict):
            return {key: evidence(value) for key, value in item.items()}
        if isinstance(item, list):
            return [evidence(value) for value in item]
        return item

    document = _parse_json(
        Path(path).read_text(encoding='utf-8'), path, lambda token: authored_decimal(token, execution=False)
    )
    if vocabulary and isinstance(document, dict):
        return {key: value if key == 'units' else evidence(value) for key, value in document.items()}
    return document


def parse_json(text, path, *, exact_numbers=False):
    """Read captured UTF-8 text under the same rules as a file, with its path in diagnostics."""

    def exact(token):
        return _json_number(authored_decimal(token, execution=False))

    return _parse_json(text, path, exact if exact_numbers else float)


def _parse_json(text, path, read_number):
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
        text,
        object_pairs_hook=pairs,
        parse_constant=bad_constant,
        parse_float=read_number,
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
