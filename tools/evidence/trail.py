"""What the values of a model rest on: the records of its declared model, and the evidence of the
values that a report reads (`napkin/engine/report.py`), resolved in the model's library.

    python -m tools.evidence.trail MODEL PATH... [--run NAME]

- **A use** (`Use`) is one record at one place of the declared model: the path of the part that it
  supports, the option that writes it (for a setting of an option), the record's name (None for a
  record written in place), its kind, the claims that it names and the assumptions and conventions
  that it rests on. `uses(declared)` gives every use in written order: of the entities and the
  templates and each of their parts (values, flows and legs, events and each part of them, solvers
  and their unknowns, the cases of a status display), of the members written by hand and their own
  values and links, of the columns of the tables, once for all their rows, of the values and
  assertions of the top level, of the options and their settings, of the named runs and of the
  notes, which the calculation never reads.
- **What an entity rests on** (`entities`): the uses written in its declaration and its parts, and
  for a template those of its members' own lines and of its tables' columns, so the rows of a table
  never count as separate evidence. `summary` counts the kinds and lists the claims and the
  assumptions that the uses name.
- **What a value rests on** (`rests_on`): the uses of every part that it can read in a run
  (`napkin.program.proofs.reads`): a part's own records; a value's, also those of the own line of
  the member that runs it and of every option that sets it; a stage's, also those of the cases of
  its switches; a trigger's, those of its captures; a solver's, those of its unknowns; a leg's,
  those of its flow; a status display's, those of its cases.
- **The evidence of a report** (`evidence`): for each value that a report reads, each part of its
  evidence trail with its uses and whether the run exercised it, then what the records of the parts
  that the run exercised reach in the library (`napkin.model.evidence.dependencies`): the claims with
  their verification status, the assumptions with their review status, the sources and the
  conventions. `possible` holds what only the parts that the run did not exercise reach. A
  disclosure names each claim that is not verified and each assumption that is not confirmed, of the
  exercised parts (`disclosures`).

`built(path, library)` declares a package as `napkin.model.compile.load_scenario` does, with the
library that the caller reads, so the coverage report (`integrate --coverage`) reads a model whose
folder holds records that it does not cite yet; pack integration reads the records that a package
cites before its library holds them (`package_document`). `load_scenario` takes no library, and
`napkin.model.library.model_document` reads the entry file alone, without the package's modules.
"""

from __future__ import annotations

import argparse
import sys
from collections import Counter
from dataclasses import dataclass, field, replace
from pathlib import Path

from napkin.engine.report import report
from napkin.engine.timeline import run
from napkin.engine.timeline.record import key_of
from napkin.model import semantic as s
from napkin.model.compile import library_units, load_scenario, merged
from napkin.model.evidence import dependencies
from napkin.model.language import nodes as n
from napkin.model.language.evidence import content, document
from napkin.model.language.modules import files as package_files
from napkin.model.language.parse import parse
from napkin.model.language.problems import LanguageError, SyntaxProblem
from napkin.model.language.tables import in_folder
from napkin.model.library import load_library
from napkin.program.proofs import Proofs

# The kinds of a record, in the order in which a summary counts them.
KINDS = ('source', 'source_transfer', 'assumption', 'convention', 'identity')


@dataclass(frozen=True)
class Use:
    """One record at one place: the path of the declared part that it supports (for a setting of an
    option, the input that it sets, and '' for the option's own line; for a note, `notes.key.key`),
    the option that writes it (None elsewhere), the record's name (None for a record written in
    place), its kind, the claims that it names, the assumptions and conventions that it rests on, and
    its content as the library's walkers read it (`language.evidence.content`)."""

    path: str
    name: str | None
    kind: str
    claims: tuple[str, ...] = ()
    assumptions: tuple[str, ...] = ()
    conventions: tuple[str, ...] = ()
    option: str | None = None
    content: dict = field(default_factory=dict, compare=False, repr=False)


@dataclass(frozen=True)
class Reached:
    """What records reach in a library: each claim with its verification status, each assumption with
    its review status, in the order in which they are reached, and the sources and the conventions."""

    claims: dict
    assumptions: dict
    sources: tuple[str, ...] = ()
    conventions: tuple[str, ...] = ()


@dataclass(frozen=True)
class Evidence:
    """The evidence of one value of a report: its path, each part of its trail (`report.Used`) with the
    uses of its records, what the records of the exercised parts reach (`reached`), and what only the
    parts that the run did not exercise reach (`possible`)."""

    path: str
    parts: tuple
    reached: Reached
    possible: Reached


# ---- the uses of a declared model ---------------------------------------------------------------------


def _used(declared, path, evidence, option=None):
    """The uses of the records of one place: each record that it cites by name (`nodes.Cite`), and each
    written in place (`nodes.Inline`)."""
    named = {record.name: record for record in declared.records}
    found = []
    for item in evidence:
        record = named.get(item.name) if isinstance(item, n.Cite) else item
        if record is None:
            continue
        relations = getattr(record, 'relations', ())
        found.append(
            Use(
                path,
                item.name if isinstance(item, n.Cite) else None,
                record.kind,
                tuple(claim.id for claim in record.claims),
                tuple(identifier for kind, identifier in relations if kind == 'assumption'),
                tuple(identifier for kind, identifier in relations if kind == 'convention'),
                option,
                content(record),
            )
        )
    return found


def _parts(entity):
    """(path, evidence) of an entity or a template and of each of its parts, in written order."""
    yield entity.path, entity.evidence
    for part in entity.parts:
        yield part.path, getattr(part, 'evidence', ())
        inner = ()
        if isinstance(part, s.DeclaredLegs):
            inner = part.legs
        elif isinstance(part, s.DeclaredEvent):
            inner = s.event_parts(part)
        elif isinstance(part, s.DeclaredSolver):
            inner = s.solver_parts(part)
        for each in inner:
            yield each.path, getattr(each, 'evidence', ())
    for case in entity.status.cases if entity.status is not None else ():
        yield case.path, case.evidence


def _member(member):
    """(path, evidence) of a member written by hand and of its own values and links; a row of a table
    has no line of its own, and its cells cite the records of their columns (`_table`)."""
    if member.table is not None:
        return
    yield member.path, member.evidence
    for given in (*member.values, *member.links):
        yield f'{member.path}.{given.name}', given.evidence


def _table(table):
    """(path, evidence) of a table and of each column, which cites its records once for every row."""
    yield table.path, table.evidence
    for column in table.columns:
        yield f'{table.path}.{column.name}', tuple(n.Cite(name) for name in column.cites)


def _notes(notes, path):
    """(path, evidence) of each note and of the notes under it."""
    for note in notes:
        here = f'{path}.{note.key}'
        yield here, (*note.cites, *note.evidence)
        yield from _notes(note.notes, here)


def uses(declared):
    """Every use of a record in a declared model, in written order (see the module)."""
    found = []
    for entity in declared.entities:
        for path, evidence in _parts(entity):
            found += _used(declared, path, evidence)
    for member in declared.members:
        for path, evidence in _member(member):
            found += _used(declared, path, evidence)
    for table in declared.tables:
        for path, evidence in _table(table):
            found += _used(declared, path, evidence)
    for part in (*declared.root, *declared.asserts):
        found += _used(declared, part.path, part.evidence)
    for option in declared.options:
        found += _used(declared, '', option.evidence, option.name)
        for setting in option.settings:
            found += _used(declared, setting.path, setting.evidence, option.name)
    for item in declared.runs:
        found += _used(declared, f'runs.{item.name}', item.evidence)
    for path, evidence in _notes(declared.notes, 'notes'):
        found += _used(declared, path, evidence)
    return found


def summary(found):
    """The kinds of the records of uses counted by use, and the claims and the assumptions that they
    name, each sorted."""
    kinds = Counter(use.kind for use in found)
    return {
        'kinds': {kind: kinds[kind] for kind in KINDS if kinds[kind]},
        'claims': sorted({claim for use in found for claim in use.claims}),
        'assumptions': sorted({name for use in found for name in use.assumptions}),
    }


def entities(declared):
    """{entity or template: the summary of its uses} (see the module), in written order."""
    found = {}
    for entity in declared.entities:
        found[entity.path] = [use for path, ev in _parts(entity) for use in _used(declared, path, ev)]
    for member in declared.members:
        found[member.template] += [use for path, ev in _member(member) for use in _used(declared, path, ev)]
    for table in declared.tables:
        found[table.template] += [use for path, ev in _table(table) for use in _used(declared, path, ev)]
    return {path: summary(each) for path, each in found.items()}


# ---- what a value rests on ------------------------------------------------------------------------------


def part_uses(declared, part, options=None):
    """The uses of a part of a program as one member runs it (`proofs.Part`, or a part of a report's
    trail): see the module. `options` names the options of a run whose settings count (None: every
    option, as in any run)."""
    found = declared.part(part.origin)
    if found is None:
        return []
    places = [(found.path, getattr(found, 'evidence', ()))]
    if isinstance(found, s.DeclaredStatus):
        places = [(case.path, case.evidence) for case in found.cases]
    elif isinstance(found, s.DeclaredStage):
        places += [
            (item.path, item.evidence) for item in s.statements_of(found.body) if hasattr(item, 'evidence')
        ]
    elif isinstance(found, s.DeclaredTrigger):
        places += [(item.path, item.evidence) for item in found.captures]
    elif isinstance(found, s.DeclaredSolver):
        places += [(item.path, item.evidence) for item in found.unknowns]
    elif isinstance(found, s.DeclaredFlow):
        parent = declared.part(found.path.rpartition('.')[0])
        if isinstance(parent, s.DeclaredLegs):
            places.insert(0, (parent.path, parent.evidence))
    used = [use for path, evidence in places for use in _used(declared, path, evidence)]
    if isinstance(found, s.DeclaredValue):
        used += _own_line(declared, found, part.owner) + _settings(declared, found, part.owner, options)
    return used


def _template_of(value):
    """The entity or template that declares a value, '' for the top level."""
    return value.path[: -len(value.name)].rstrip('.')


def _own_line(declared, value, owner):
    """The uses of the own line of the member that runs a value of its template, and of the column of
    its table that gives it."""
    member = declared.part(owner) if owner else None
    if not isinstance(member, s.DeclaredMember) or member.template != _template_of(value):
        return []
    given = next((item for item in (*member.values, *member.links) if item.name == value.name), None)
    if given is None:
        return []
    if member.table is not None:
        return _used(declared, f'{member.table}.{value.name}', given.evidence)
    return _used(declared, f'{member.path}.{value.name}', given.evidence)


def _settings(declared, value, owner, options):
    """The uses of the settings of the options (every option for None) that set an input as one
    member runs it: a setting of that member, or of every member of its template."""
    if value.kind != s.INPUT:
        return []
    template = _template_of(value)
    found = []
    for option in declared.options:
        if options is not None and option.name not in options:
            continue
        for setting in option.settings:
            if setting.name != value.name:
                continue
            if setting.member == owner or (setting.instances is not None and setting.instances == template):
                found += _used(declared, setting.path, setting.evidence, option.name)
    return found


def rests_on(compiled, path):
    """The uses of every part that the value at `path` can read in any run of a compiled model (see
    the module), part by part, each once."""
    found = Proofs(compiled.program, None).reads(key_of(compiled.program, path))
    parts = sorted(found.edges, key=lambda part: (part.origin, part.owner, part.kind))
    return [use for part in parts for use in part_uses(compiled.declared, part)]


# ---- the evidence of a report -----------------------------------------------------------------------------


def reached(found, library):
    """What uses reach in a library (`Reached`)."""
    closure = dependencies([use.content for use in found], library)
    claims = {record['id']: record for record in library.get('claims', ())}
    assumptions = {record['id']: record for record in library.get('assumptions', ())}
    return Reached(
        {
            name: claims.get(name, {}).get('verification', {}).get('status', 'unverified')
            for name in closure['claims']
        },
        {
            name: assumptions.get(name, {}).get('review', {}).get('status', 'unreviewed')
            for name in closure['assumptions']
        },
        tuple(closure['sources']),
        tuple(closure['conventions']),
    )


def evidence(found, declared, library, options=()):
    """The evidence of each value of a report (`napkin.engine.report.Report`) of a run of a declared
    model that takes `options` (the names of the options of a named run; none for the default run), in
    the order of the report: see the module."""
    out = []
    for value in found.values:
        parts = tuple((used, tuple(part_uses(declared, used, options))) for used in value.trail)
        exercised = [use for used, each in parts if used.exercised for use in each]
        other = [use for used, each in parts if not used.exercised for use in each]
        held, could = reached(exercised, library), reached(other, library)
        possible = Reached(
            {name: status for name, status in could.claims.items() if name not in held.claims},
            {name: status for name, status in could.assumptions.items() if name not in held.assumptions},
            tuple(name for name in could.sources if name not in held.sources),
            tuple(name for name in could.conventions if name not in held.conventions),
        )
        out.append(Evidence(value.path, parts, held, possible))
    return out


def disclosures(found):
    """One line for each claim that is not verified and each assumption that is not confirmed, of the
    parts that the run exercised (`Evidence.reached`)."""
    lines = [
        f'the claim {name} is {status}'
        for name, status in found.reached.claims.items()
        if status != 'verified'
    ]
    lines += [
        f'the assumption {name} is {status}'
        for name, status in found.reached.assumptions.items()
        if status != 'confirmed'
    ]
    return lines


# ---- the files of a package ----------------------------------------------------------------------------


def package_tree(path):
    """(the tree of a package's files as one model, its files with their offsets, its folder), as
    `load_scenario` reads them. Raises LanguageError with the problems of the files."""
    found = package_files(Path(path))
    problems, trees, files, offset = list(found.problems), [], [], 0
    for file, text in found.files:
        files.append((file.as_posix(), offset))
        try:
            # The lines of each file are numbered after those of the files before it.
            trees.append(parse('\n' * offset + text))
        except SyntaxProblem as problem:
            name, line = s.Files(tuple(files)).place(problem.problem.line)
            problems.append(replace(problem.problem, file=name, line=line))
        offset += text.count('\n') + 1
    if problems:
        raise LanguageError(problems)
    tree, problems = merged(trees)
    if problems:
        place = s.Files(tuple(files)).place
        raise LanguageError(
            [replace(item, file=place(item.line)[0], line=place(item.line)[1]) for item in problems]
        )
    return tree, tuple(files), found.package


def package_document(path):
    """What the evidence walkers read of a package's files (`language.evidence.document`): the records
    of its main file, its modules and, for a variant, its own file."""
    return document(package_tree(path)[0])


def built(path, library):
    """The declared model of the entry file `path`, declared with the units of `library`
    (`napkin.model.library.load_library`), as `load_scenario` declares it."""
    tree, files, folder = package_tree(path)
    return s.declare(tree, library_units(library), in_folder(folder), files)


# ---- the command --------------------------------------------------------------------------------------------


def _record(use):
    """A use in words: its record's name or `@kind` in place, and what it names."""
    named = [*use.claims, *(f'assumption {name}' for name in use.assumptions)]
    named += [f'convention {name}' for name in use.conventions]
    where = f' (option {use.option})' if use.option else ''
    return f'{use.name or "@" + use.kind}{where}' + (f': {", ".join(named)}' if named else '')


def lines_of(found):
    """The lines of the evidence of one value (`Evidence`)."""
    lines = [found.path]
    for used, each in found.parts:
        records = '; '.join(_record(use) for use in each) or 'no record'
        lines.append(f'  {used.kind} {used.origin} ({used.owner or "top level"}): {used.why}; {records}')
    for title, held in (('rests on', found.reached), ('could rest on', found.possible)):
        claims = ', '.join(f'{name} ({status})' for name, status in held.claims.items())
        assumptions = ', '.join(f'{name} ({status})' for name, status in held.assumptions.items())
        if claims or assumptions:
            lines.append(f'  {title}: claims {claims or "none"}; assumptions {assumptions or "none"}')
    lines += [f'  disclosure: {line}' for line in disclosures(found)]
    return lines


def main(argv=None):
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument('model', type=Path, help='The main file or a variant of a package')
    parser.add_argument('paths', nargs='+', metavar='PATH', help='A value to report, as napkin run reads it')
    parser.add_argument('--run', help='A named run of the model (default: its default run)')
    args = parser.parse_args(argv)
    try:
        compiled = load_scenario(args.model, run=args.run)
        library = load_library(args.model, document=document(compiled.declared.tree))
        record = run(compiled.program, compiled.configuration)
        horizon = float(compiled.configuration.request.horizon)
        found = report(
            record, compiled.program, compiled.configuration, args.paths, [horizon], model=compiled.declared
        )
    except (LanguageError, KeyError, LookupError, ValueError, OSError) as exc:
        print(str(exc), file=sys.stderr)
        return 1
    options = compiled.declared.run(args.run).options if args.run else ()
    for each in evidence(found, compiled.declared, library, options):
        print('\n'.join(lines_of(each)))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
