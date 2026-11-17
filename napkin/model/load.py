"""Read the JSON files of a scenario (its library, units, edits and packages), and check a document
against the schemas of the package (`napkin/schema/`): duplicate keys and non-finite numbers are
rejected."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from .. import schema as schemas


class SourceError(ValueError):
    """A file that is not valid source text, with the line it is about."""

    def __init__(self, path, line, message):
        self.path, self.line = str(path), line
        super().__init__(f'{path}:{line}: {message}' if line else f'{path}: {message}')


def load_json(path):
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
        Path(path).read_text(encoding='utf-8'), object_pairs_hook=pairs, parse_constant=bad_constant
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
