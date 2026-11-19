"""The records of a model text as the evidence walkers of `napkin/model/evidence.py` read them.

A record has its `kind`, its `explanation`, the IDs of the library that it rests on (`rests_on`:
`{'assumption': 'A-TIMING'}`, `{'convention': ...}`) and its claims (`links`, each a `claim` and a
`datum`). `document` gives each line's evidence by the path of the line (a record written in place
as its content, a named record as `{'record': name}`) and each named record by `record <name>`; a
walker's path is then the path of the line, and a part with no name is named as the declared model
names it (`service.status.case[0]`, `assert[0]`). `lines` gives the line of each path, so that a
diagnostic of the library about a record is placed at the line that writes or cites it.
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


def _walk(node, path, out, lines):
    found = _evidence(node)
    if found:
        out[path] = found
        lines[path] = node.line
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
        'options',
        'settings',
        'runs',
    ):
        counts = {}
        for k, child in enumerate(getattr(node, key, ()) or ()):
            name = (
                getattr(child, 'name', None) or getattr(child, 'key', None) or _unnamed(child, key, k, counts)
            )
            if isinstance(child, n.Property):
                name = '.'.join(child.path)
            _walk(child, f'{path}.{name}', out, lines)


def _unnamed(child, key, k, counts):
    """The path of a part with no name, as the declared model names it: a status line is a case of
    the display (`status.case[0]`), an assertion `assert[0]`, each counted among its own kind; any
    other part its place in its list (`steps[1]`)."""
    for kind, label in ((n.Status, 'status.case'), (n.Assert, 'assert')):
        if isinstance(child, kind):
            counts[label] = counts.get(label, -1) + 1
            return f'{label}[{counts[label]}]'
    return f'{key}[{k}]'


def _walked(tree):
    out, lines, counts = {}, {}, {}
    for k, item in enumerate(tree.items):
        if isinstance(item, n.Record):
            out[f'record {item.name}'] = content(item)
            lines[f'record {item.name}'] = item.line
            continue
        name = getattr(item, 'name', None) or _unnamed(item, type(item).__name__.lower(), k, counts)
        _walk(item, '.'.join(item.path) if isinstance(item, n.Property) else name, out, lines)
    return out, lines


def document(tree):
    """What the evidence walkers read of a parsed text (`nodes.File`)."""
    return _walked(tree)[0]


def lines(tree):
    """The line of each path of the `document` of a parsed text, for a diagnostic about it."""
    return _walked(tree)[1]
