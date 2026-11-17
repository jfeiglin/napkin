"""The evidence of a model file (docs/language.md, §2.10) and what the model hash covers.

A record has the content that the evidence library reads (docs/language.md, §2.10): its `kind`, the
assumption ID that it names (`assumption`), its `explanation` and its claims (`links`, each a `claim`
and a `datum`). A named record cited at a line is written out there, with its `name`.

`projection` is what the evidence walkers of `model/evidence.py` and `model/identity.py` read: each
line's evidence, by the text of its place (named records by name, records written in place as they
are), each named record and the units that the file writes. A walker's path is then the place of the
line. The records of the notes are lines' evidence too; the notes' other values cite nothing.

`identity` is what the model hash covers of the file: its meaning, with the order of its members, and
without its spacing, comments, lines and the path of its library. It leaves out the order of the named
records, of the options, of the lines of each option and of the runs, because none of them changes a
result.
"""

from __future__ import annotations

import dataclasses

from ..ir import close_names, freeze, thaw
from ..semantic import Citation, Note, Record, Site, path_text
from .lex import Token
from .nodes import Change as ChangeNode
from .nodes import Cite, Expr, Text
from .nodes import Note as NoteNode
from .nodes import Record as RecordNode


def content(record):
    """The content of a record (`nodes.Record`), as the evidence library reads it. The ID of a
    `convention` record names a convention of the library; the ID of any other record, an assumption."""
    out = {'kind': record.kind}
    if record.id is not None:
        out['convention' if record.kind == 'convention' else 'assumption'] = record.id
    out['explanation'] = record.text
    if record.claims:
        out['links'] = [
            {'claim': claim.id, **({'datum': claim.datum} if claim.datum is not None else {})}
            for claim in record.claims
        ]
    return out


class Evidence:
    """The records of a parsed file (`nodes.File`): the named records, and each line's support, written
    out (`resolved`) or as written (`written`)."""

    def __init__(self, file):
        self.file = file
        self.named = {record.name: record for record in file.records}
        self.sites = []  # (place, support), in the order of the file
        self.noted = set()
        self.problems = []  # (place, message) of names that no record has

    def collect(self):
        """Note the evidence of every line of the file, in the order of the file; and the units that the
        file writes (`units`)."""
        self.units = set()

        def walk(value):
            if isinstance(value, Token):
                if value.kind == 'unit':
                    self.units.add(value.value)
                return
            if isinstance(value, (list, tuple)):
                for item in value:
                    walk(item)
                return
            if isinstance(value, dict):
                for item in value.values():
                    walk(item)
                return
            if not dataclasses.is_dataclass(value) or isinstance(value, (RecordNode, Cite)):
                return
            support = getattr(value, 'support', None)
            if isinstance(support, list) and support and not isinstance(value, NoteNode):
                self.note(value.place, support)
            if getattr(value, 'together_support', None):
                self.note(value.together_place, value.together_support)
            if isinstance(value, ChangeNode) and value.together:
                self.note((*value.place, 'together:'), value.together)
            kind_type = getattr(value, 'type', None)
            if isinstance(kind_type, str) and not isinstance(value, Text):
                self.units.add(kind_type)
            for field in dataclasses.fields(value):
                if field.name not in ('support', 'together_support', 'place', 'line'):
                    walk(getattr(value, field.name))

        walk([self.file.scenario, self.file.things, self.file.checks])
        walk([self.file.outputs, self.file.profiles, self.file.runs])
        return self

    def record_of(self, item):
        """A record of a support, written out: a named record with its `name`, or a record in place."""
        if isinstance(item, Cite):
            found = self.named.get(item.name)
            if found is None:
                return {'name': item.name}
            return {**content(found), 'name': item.name}
        return content(item)

    def resolved(self, support):
        """The basis of a support, as the semantic model holds it: None, one record, or a list."""
        if not support:
            return None
        records = [self.record_of(item) for item in support]
        return freeze(records[0] if len(records) == 1 else records)

    @staticmethod
    def written(support):
        """The basis of a support as the file writes it: names, and records written in place."""
        items = [item.name if isinstance(item, Cite) else content(item) for item in support]
        return items[0] if len(items) == 1 else items

    def note(self, place, support):
        """Record that the line at `place` holds `support`, once: a template's line is one line of the
        file for all its instances."""
        if support and place not in self.noted:
            self.noted.add(place)
            self.sites.append((place, support))
            for item in support:
                if isinstance(item, Cite) and item.name not in self.named:
                    message = f'Unknown named basis {item.name!r}' + close_names(item.name, self.named)
                    self.problems.append((item.place, message))

    # ---- what the semantic model holds -------------------------------------------------------------

    def records(self):
        return tuple(
            Record(record.name, freeze(content(record)), record.place) for record in self.file.records
        )

    def semantic_sites(self):
        return tuple(Site(place, place, self.resolved(support)) for place, support in self.sites)

    def citations(self):
        """The claims, assumptions and conventions that the file names, in the order of the file: each
        record's assumption or convention, then its claims (the records of the notes among them); then
        the named records."""
        out = []

        def of(record, where):
            if record.id is not None:
                out.append(
                    Citation('convention' if record.kind == 'convention' else 'assumption', record.id, where)
                )
            for claim in record.claims:
                out.append(Citation('claim', claim.id, where))

        for place, support in self.sites:
            for item in support:
                if isinstance(item, RecordNode):
                    of(item, place)
        for record in self.file.records:
            of(record, record.place)
        return tuple(out)

    def projection(self, units):
        """What the evidence walkers read (see the module's text). The records of the notes are sites,
        at the places of their notes."""
        out = {path_text(place): self.written(support) for place, support in self.sites}
        for record in self.file.records:
            out[path_text(record.place)] = content(record)
        out['units'] = [{'unit': unit} for unit in sorted(units)]
        return out


# ---- the notes ---------------------------------------------------------------------------------


def note_value(value):
    """The value of a note: a text, a number, a word, or a list of them."""
    if isinstance(value, Text):
        return value.value
    if isinstance(value, Token):
        return number(value.value)
    if isinstance(value, list):
        return [note_value(item) for item in value]
    return value


def number(text):
    """A number as written: a whole number, or a number with a fraction or an exponent."""
    return float(text) if any(c in text for c in '.eE') else int(text)


def notes_of(notes, evidence):
    """The notes as the semantic model holds them (`semantic.Note`), in the order of the file: each
    with its key, its value, its records as written and the notes under it. The language gives no key
    a meaning; the readers of the notes check the keys that they read. The evidence of each note, at
    any depth, is a site of the file, which the evidence index counts as no use of a part."""
    out = []
    for note in notes or ():
        if note.support:
            evidence.note(note.place, note.support)
        out.append(
            Note(
                note.key,
                freeze(note_value(note.value)),
                freeze(Evidence.written(note.support)) if note.support else None,
                notes_of(note.under, evidence),
                note.place,
            )
        )
    return tuple(out)


# ---- what the model hash covers -----------------------------------------------------------------


def meaning(value):
    """A part of the file without its lines and spacing: each node by its fields, each token by its
    kind and value."""
    if isinstance(value, Token):
        return [value.kind, value.value]
    if isinstance(value, Expr):
        return ['expr', [meaning(token) for token in value.tokens]]
    if dataclasses.is_dataclass(value):
        fields = {
            f.name: meaning(getattr(value, f.name))
            for f in dataclasses.fields(value)
            if f.name not in ('line', 'place')
        }
        return [type(value).__name__, fields]
    if isinstance(value, (list, tuple)):
        return [meaning(item) for item in value]
    if isinstance(value, dict):
        return {str(key): meaning(item) for key, item in value.items()}
    return value


def identity(file):
    """What the model hash covers (see the module's text)."""
    payload = meaning(dataclasses.replace(file, lines={}))
    fields = payload[1]
    # The columns, like the lines, are places in the file, not its meaning.
    fields.pop('columns')
    # The uses and the change blocks of a model of several files are merged into its file (`modules`).
    fields.pop('uses')
    fields.pop('changes')
    scenario = fields.get('scenario')
    if isinstance(scenario, list):
        # A scenario block without a resolution line hashes as it did before the language had the line.
        if scenario[1].get('resolution') is None:
            scenario[1].pop('resolution', None)
        # The folder of the library is a path: the model hash covers the library's content that the
        # model reaches, never where the library is (`identity.reached`).
        scenario[1].pop('library', None)
    for thing in fields['things']:
        # A thing with no table hashes as it did before the language had tables. The name of the file
        # of a table is a path: the model hash covers what the table holds, never where it is.
        if thing[1].get('table') is None:
            thing[1].pop('table', None)
        else:
            thing[1]['table'][1].pop('file')
    fields['records'] = sorted(fields['records'], key=lambda item: item[1]['name'])
    profiles = []
    for group in fields['profiles']:
        group_fields = group[1]
        for profile in group_fields['profiles']:
            profile[1]['settings'] = sorted(profile[1]['settings'], key=lambda item: item[1]['target'])
        group_fields['profiles'] = sorted(group_fields['profiles'], key=lambda item: item[1]['name'])
        profiles.append(group)
    fields['profiles'] = sorted(profiles, key=lambda item: item[1]['name'])
    fields['runs'] = sorted(fields['runs'], key=lambda item: item[1]['name'])
    return thaw(freeze(payload))


__all__ = ['Evidence', 'content', 'identity', 'notes_of']
