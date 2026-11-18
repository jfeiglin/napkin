"""The records of a model text as the evidence walkers of `napkin/model/evidence.py` read them.

A record has its `kind`, its `explanation`, the IDs of the library that it rests on (`rests_on`:
`{'assumption': 'A-TIMING'}`, `{'convention': ...}`) and its claims (`links`, each a `claim` and a
`datum`). `document` gives each line's evidence by the path of the line (a record written in place
as its content, a named record as `{'record': name}`) and each named record by `record <name>`; a
walker's path is then the path of the line.
"""

from __future__ import annotations

from . import nodes as n


def content(record):
    """The content of a record (`nodes.Record` or `nodes.Inline`), as the evidence library reads it."""
    out = {'kind': record.kind, 'explanation': record.text}
    if record.relations:
        out['rests_on'] = [{kind: identifier} for kind, identifier in record.relations]
    if record.claims:
        out['links'] = [
            {'claim': claim.id, **({'datum': claim.datum} if claim.datum else {})} for claim in record.claims
        ]
    return out


def _evidence(node):
    items = (*getattr(node, 'cites', ()), *getattr(node, 'evidence', ()))
    return [content(item) if isinstance(item, n.Inline) else {'record': item.name} for item in items]


def _walk(node, path, out):
    found = _evidence(node)
    if found:
        out[path] = found
    for key in (
        'members',
        'properties',
        'legs',
        'locals',
        'triggers',
        'steps',
        'body',
        'then',
        'orelse',
        'cases',
        'notes',
    ):
        for k, child in enumerate(getattr(node, key, ()) or ()):
            name = getattr(child, 'name', None) or getattr(child, 'key', None) or f'{key}[{k}]'
            if isinstance(child, n.Property):
                name = '.'.join(child.path)
            _walk(child, f'{path}.{name}', out)


def document(tree):
    """What the evidence walkers read of a parsed text (`nodes.File`)."""
    out = {}
    for k, item in enumerate(tree.items):
        if isinstance(item, n.Record):
            out[f'record {item.name}'] = content(item)
            continue
        name = getattr(item, 'name', None) or f'{type(item).__name__.lower()}[{k}]'
        _walk(item, '.'.join(item.path) if isinstance(item, n.Property) else name, out)
    return out
