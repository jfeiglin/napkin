"""The files of one model: its entry file, the files that it reads, and their merge
(docs/language.md, §2.12).

A file's role is its first declaration: `scenario "Title"` is the main file of a package,
`<package>/model.scn`; `variant "Title"` is a variant, `<package>/variants/<name>/model.scn`; any other
file is a module. A line `use a.b` makes the declarations of the module `<package>/a/b.scn` part of the
model: a name is read from the folder of the package, so nothing outside the package resolves. A
variant's implicit first dependency is its package's main file.

`read` reads the files of a model, dependencies first in the order of the `use` lines and the entry
file last, each file once, and merges them into one `File`, as if one file held them in that order
(`merge`). The scenario line of a variant overlays its main file's: each line that the variant writes
replaces the main file's (`overlay_scenario`). Then each `change` block gives its lines to a thing of an
earlier file (`apply`).
"""

from __future__ import annotations

import dataclasses
import re
from pathlib import Path

from ...paths import ENTRY, VARIANTS
from ..ir import ModelError, close_names, diagnostic
from ..semantic import path_text
from . import parse, tables
from .lex import SyntaxProblem
from .nodes import Change, File, LinkBind, Output, Status, Value

NAME = r'[A-Za-z_][A-Za-z0-9_]*'
USE = re.compile(rf'^use ({NAME}(?:\.{NAME})*)[ \t]*$', re.M)
# The first declaration of a file, which gives it its role: its first line at the top level that is
# not a comment.
FIRST = re.compile(r'^(?![#\s])(\S+)(?: (.))?', re.M)
# The lines of a variant's scenario line that replace the main file's.
OVERLAID = ('summary', 'horizon', 'timescales', 'resolution', 'scope')


def role_of(text):
    """`main`, `variant` or `module`: the role that a file's first declaration gives it."""
    found = FIRST.search(text)
    if found is None or found.group(2) != '"':
        return 'module'
    return {'scenario': 'main', 'variant': 'variant'}.get(found.group(1), 'module')


def package_of(path, role):
    """The folder of the package of a model whose entry file is `path`, with the role `role`: the
    folder of a main file, and for a variant the folder that holds its `variants/` folder. None for a
    variant that is not the entry file of a folder of a package's `variants/`."""
    path = Path(path)
    if role != 'variant':
        return path.parent
    if path.name == ENTRY and path.parent.parent.name == VARIANTS:
        return path.parent.parent.parent
    return None


def module_path(name, package):
    """The file of the module `name` in the folder of the package: `a.b` is `a/b.scn`."""
    *folders, stem = name.split('.')
    return Path(package, *folders, f'{stem}.scn')


def name_of(path, package):
    """A file of a package as a `use` line names it, `a.b` for `a/b.scn`, or the path of an entry file
    from the package's folder."""
    path = Path(path)
    try:
        relative = path.resolve().relative_to(Path(package).resolve())
    except ValueError:
        return path.as_posix()
    if path.name == ENTRY:
        return relative.as_posix()
    return '.'.join((*relative.parent.parts, path.stem))


def modules_of(package):
    """The names of the modules of the package in the folder `package`, as a `use` line names them:
    each `.scn` file of the package that is not an entry file, outside the folders of its tests."""
    return [
        name_of(path, package)
        for path in sorted(Path(package).rglob('*.scn'))
        if path.name != ENTRY and 'tests' not in path.relative_to(package).parts
    ]


def problem(origin, message, line=None, place=(), column=None):
    """The diagnostic of a problem of the files of a model: its file, and its line and column when it
    has them."""
    item = {**diagnostic('modules', path_text(place) if place else '', message), 'file': origin}
    if not line:
        return item
    return {**item, 'line': line, **({'column': column} if column else {})}


def walk(path, read):
    """([(path, what `read` gives for it, its role)] of the files of the model of the entry file
    `path`, dependencies first and `path` last, each file once; the folder of its package; the problems
    of the files and of their uses). `read(path)` gives a file's parts, its role and its uses,
    [(name, line, place, column)]. A variant reads its package's main file first."""
    path = Path(path)
    parts, problems, done, trail = [], [], set(), []
    parsed, role, uses = read(path)
    package = package_of(path, role)
    if package is None:
        message = f'a variant is the file {VARIANTS}/<name>/{ENTRY} of its package'
        problems.append(problem(path.as_posix(), message))
        return [(path, parsed, role)], path.parent, problems

    def visit(current, known=None):
        key = current.resolve()
        if key in done:
            return
        if key in trail:
            cycle = ' -> '.join(name_of(p, package) for p in [*trail[trail.index(key) :], key])
            problems.append(problem(current.as_posix(), f'the uses form a circle: {cycle}'))
            return
        trail.append(key)
        found, kind, wanted = known or read(current)
        for name, line, place, column in wanted:
            target = module_path(name, package)
            if target.name == ENTRY:
                message = f'use {name}: {ENTRY} is the main file of a package or of a variant, not a module'
                problems.append(problem(current.as_posix(), message, line, place, column))
                continue
            if not target.is_file():
                where = target.relative_to(package).as_posix()
                message = f'use {name}: the package {package.name} has no module {where}'
                message += close_names(name, modules_of(package))
                problems.append(problem(current.as_posix(), message, line, place, column))
                continue
            visit(target)
        trail.pop()
        done.add(key)
        parts.append((current, found, kind))

    if role == 'variant':
        main = package / ENTRY
        if not main.is_file():
            message = f'a variant reads the main file of its package: {package.name} has no {ENTRY}'
            problems.append(problem(path.as_posix(), message))
            return [(path, parsed, role)], package, problems
        visit(main)
    visit(path, (parsed, role, uses))
    return parts, package, problems


def paths(path):
    """The files of the model of the entry file `path`, dependencies first and `path` last, found from
    their first declarations and their `use` lines only. A file that is missing or that closes a circle
    is left out; its build says why."""

    def uses(current):
        try:
            text = current.read_text(encoding='utf-8')
        except OSError:
            return None, 'module', []
        return None, role_of(text), [(name, None, (), None) for name in USE.findall(text)]

    return [current for current, _, _ in walk(path, uses)[0]]


def library_line(path):
    """(the main file of the model of the entry file `path`, the folder that its `library "PATH"` line
    names, relative to the main file, or None without the line): a variant reads its package's."""
    path = Path(path)
    role = role_of(path.read_text(encoding='utf-8'))
    main = path if role != 'variant' else (package_of(path, role) or path.parent) / ENTRY
    try:
        block = parse.parse(main.read_text(encoding='utf-8')).scenario
    except (OSError, SyntaxProblem):
        return main, None
    return main, (block.library.value if block is not None and block.library is not None else None)


def read(path):
    """(the `File` of the model of the entry file `path`, {place: path} of each line of a model of
    several files, else {}). Raises ModelError with the file and line of each problem."""
    counts = None

    def parsed(current):
        nonlocal counts
        try:
            file, counts = parse.parse_counted(current.read_text(encoding='utf-8'), counts)
        except SyntaxProblem as exc:
            item = {**diagnostic('syntax', '', exc.message), 'line': exc.line, 'file': current.as_posix()}
            raise ModelError([{**item, 'column': exc.column} if exc.column else item]) from None
        return (
            file,
            file.role,
            [(use.name, use.line, use.place, file.columns.get(use.place)) for use in file.uses],
        )

    parts, package, problems = walk(path, parsed)
    if problems:
        raise ModelError(problems)
    entry = parts[-1][2]
    for current, file, role in parts[:-1]:
        # A variant reads its package's main file; every other file that a model reads is a module.
        main = entry == 'variant' and current.resolve() == (package / ENTRY).resolve()
        if main and role != 'main':
            where = file.scenario.place if file.scenario is not None else ()
            message = 'the main file of a package starts with its scenario line: scenario "Title"'
            problems.append(
                problem(current.as_posix(), message, file.lines.get(where), where, file.columns.get(where))
            )
        elif not main and role != 'module':
            where = file.scenario.place
            message = f'{name_of(current, package)} is the main file of a package or a variant, not a module'
            problems.append(
                problem(current.as_posix(), message, file.lines.get(where), where, file.columns.get(where))
            )
    # The tables of the model (`tables`): each is read from the folder of the package, and its columns
    # and rows are lines of its own file.
    table_files = {}
    for current, file, _ in parts:
        found, wrong = tables.fill(file, package, current.as_posix())
        table_files.update(found)
        problems += wrong
    if problems:
        raise ModelError(problems)
    if len(parts) == 1 and not parts[0][1].changes:
        return parts[0][1], table_files
    file, files, problems = merge([(current, file) for current, file, _ in parts], package)
    if problems:
        raise ModelError(problems)
    # `merge` gives each line of a file to that file; the lines of a table are its table's.
    files.update(table_files)
    return file, files


# ---- the merge -----------------------------------------------------------------------------------


def overlay_scenario(main, variant):
    """The scenario line of a variant's model: its main file's, with each line that the variant writes
    in place of the main file's, and the variant's title beside the main file's."""
    if main is None or variant is None:
        return variant or main
    lines = {key: getattr(variant, key) for key in OVERLAID if getattr(variant, key) is not None}
    return dataclasses.replace(main, **lines, variant=variant.title)


def merge(parts, package):
    """(one `File` of the files of a model in their order, {place: path} of each line, problems): each
    thing, output, option, run and record is declared in one file; the options of one group from
    several files form one group; the runs, checks and records add up; the notes merge key by
    key (`merge_notes`); then each change block gives its lines to its thing (`apply`). The scenario
    line is the entry file's, over its main file's for a variant (`overlay_scenario`)."""
    *_, (_, last) = parts
    main = next((file for _, file in parts if file.role == 'main'), None)
    out = File(
        scenario=overlay_scenario(main.scenario, last.scenario)
        if last.role == 'variant' and main
        else last.scenario
    )
    files, owner, position, problems, groups = {}, {}, {}, [], {}

    def claim(kind, name, path, file, place):
        if (kind, name) in owner:
            message = f'{name} is declared in {owner[kind, name]} and in {name_of(path, package)}'
            problems.append(
                problem(path.as_posix(), message, file.lines.get(place), place, file.columns.get(place))
            )
            return False
        owner[kind, name] = name_of(path, package)
        return True

    for k, (path, file) in enumerate(parts):
        out.columns.update(file.columns)
        for place, line in file.lines.items():
            out.lines[place] = line
            # A later file's line of a place (a variant's line of its scenario line) moves the place to
            # its file, in the order of the files.
            files.pop(place, None)
            files[place] = path.as_posix()
        for thing in file.things:
            if claim('thing', thing.name, path, file, thing.place):
                out.things.append(thing)
                position[thing.name] = k
        out.checks += file.checks
        out.outputs += [o for o in file.outputs if claim('output', o.name, path, file, o.place)]
        for group in file.profiles:
            if group.name not in groups:
                groups[group.name] = dataclasses.replace(group, profiles=[])
                out.profiles.append(groups[group.name])
            groups[group.name].profiles += [
                option
                for option in group.profiles
                if claim(('option', group.name), option.name, path, file, option.place)
            ]
        out.runs += [run for run in file.runs if claim('run', run.name, path, file, run.place)]
        if out.runs_place is None:
            out.runs_place = file.runs_place
        if file.notes is not None:
            out.notes = merge_notes(out.notes, file.notes)
        out.records += [r for r in file.records if claim('record', r.name, path, file, r.place)]
    things = {thing.name: i for i, thing in enumerate(out.things)}
    for k, (path, file) in enumerate(parts):
        for change in file.changes:
            at = things.get(change.name)
            if at is None or position[change.name] >= k:
                message = f'change {change.name}: no earlier file of the model declares {change.name}'
                message += close_names(change.name, [name for name, i in position.items() if i < k])
                column = file.columns.get(change.place)
                problems.append(problem(path.as_posix(), message, change.line, change.place, column))
                continue
            thing = out.things[at] = dataclasses.replace(out.things[at], members=list(out.things[at].members))
            for wrong in apply(thing, change):
                line, column = file.lines.get(wrong[0]), file.columns.get(wrong[0])
                problems.append(problem(path.as_posix(), wrong[1], line, wrong[0], column))
    parse.links(out, set(things))
    return out, files, problems


def merge_notes(base, more):
    """The notes of `base` with those of `more`: a note of `more` replaces the note of the same
    key, and the notes under a key that both hold merge the same way."""
    if base is None:
        return list(more)
    out = list(base)
    index = {note.key: i for i, note in enumerate(out)}
    for note in more:
        if note.key not in index:
            index[note.key] = len(out)
            out.append(note)
            continue
        old = out[index[note.key]]
        if note.value is None and old.value is None and note.under and old.under:
            out[index[note.key]] = dataclasses.replace(
                old, under=merge_notes(old.under, note.under), support=[*old.support, *note.support]
            )
        else:
            out[index[note.key]] = note
    return out


VALUE_PARTS = ('value', 'text', 'min', 'max', 'bounds', 'size', 'rate', 'output')


def overlay(lines, change):
    """`lines` (a Value) with the parts that a change writes: its value, text, range, size, rate and
    output lines, its records, and a new kind and type."""
    updates = {
        part: getattr(change.lines, part) for part in VALUE_PARTS if getattr(change.lines, part) is not None
    }
    if change.lines.support:
        updates['support'] = change.lines.support
    if change.kind:
        updates['kind'] = change.kind
        if change.lines.type is not None:
            updates['type'] = change.lines.type
    return dataclasses.replace(lines, **updates)


def apply(thing, change):
    """Give `thing` (an entity, an instance or a template) the lines of a change block, as an instance's
    lines over its template's members; [(place, problem)] of the lines that name nothing that it has."""
    if change.text is not None:
        thing.text = change.text
    if change.title is not None:
        thing.title = change.title
    if change.support:
        thing.support = change.support
    members, wrong = thing.members, []
    for member in change.members:
        if isinstance(member, Status):
            found = next((i for i, m in enumerate(members) if isinstance(m, Status)), None)
            if found is None:
                members.append(member)
            else:
                members[found] = member
            continue
        if isinstance(member, LinkBind):
            found = next(
                (i for i, m in enumerate(members) if isinstance(m, LinkBind) and m.name == member.name), None
            )
            if found is not None:
                members[found] = member
            elif thing.template is not None:
                members.append(member)
            else:
                wrong.append(
                    (member.place, f'change {thing.name}: {member.name} is not a link of {thing.name}')
                )
            continue
        if not isinstance(member, Change):
            wrong.append((member.place, f'change {thing.name}: a change gives the lines of an instance'))
            continue
        if member.lines.value is not None and not member.lines.support:
            wrong.append((member.place, f'{thing.name}.{member.name}: a new value needs a record of its own'))
            continue
        if thing.template is not None:
            # An instance: the change goes over the instance's own change of the member.
            found = next(
                (i for i, m in enumerate(members) if isinstance(m, Change) and m.name == member.name), None
            )
            if found is None:
                members.append(member)
            else:
                old = members[found]
                members[found] = dataclasses.replace(
                    member, kind=member.kind or old.kind, lines=overlay(old.lines, member)
                )
            continue
        found = next(
            (i for i, m in enumerate(members) if isinstance(m, (Value, Output)) and m.name == member.name),
            None,
        )
        if found is None or not isinstance(members[found], Value):
            wrong.append((member.place, f'change {thing.name}: {member.name} is not a value of {thing.name}'))
            continue
        members[found] = overlay(members[found], member)
    return wrong


__all__ = ['library_line', 'merge', 'module_path', 'name_of', 'paths', 'read', 'role_of']
