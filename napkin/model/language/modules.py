"""The files of one model: its entry file, the files that it reads, and the library that it names.

A file's role is its first declaration: `scenario "Title"` is the main file of a package,
`<package>/model.scn`; `variant "Title"` is a variant, `<package>/variants/<name>/model.scn`; any
other file is a module. A line `use a.b` names the module `<package>/a/b.scn`, read from the folder
of the package, and a variant reads its package's main file first. This slice lowers a model of one
file; `use` and variants parse, and their lowering comes with slice S6.
"""

from __future__ import annotations

import re
from pathlib import Path

from ...paths import ENTRY, VARIANTS
from .parse import parse
from .problems import SyntaxProblem

NAME = r'[A-Za-z_][A-Za-z0-9_]*'
USE = re.compile(rf'^use ({NAME}(?:\.{NAME})*)[ \t]*(?:#.*)?$', re.M)
# The first declaration of a file, which gives it its role: its first row at the top level that is
# not a comment.
FIRST = re.compile(r'^(?![#\s])(\S+)(?: (.))?', re.M)


def role_of(text):
    """`main`, `variant` or `module`: the role that a file's first declaration gives it."""
    found = FIRST.search(text)
    if found is None or found.group(2) != '"':
        return 'module'
    return {'scenario': 'main', 'variant': 'variant'}.get(found.group(1), 'module')


def package_of(path, role):
    """The folder of the package of a model whose entry file is `path`, with the role `role`: the
    folder of a main file or a module, and for a variant the folder that holds its `variants/`
    folder. None for a variant that is not the entry file of a folder of a package's `variants/`."""
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


def paths(path):
    """The files of the model of the entry file `path`: the files that its `use` lines name,
    dependencies first, and `path` last, each once; a variant's main file first. A file that is
    missing or that closes a circle is left out: the build of the model says why."""
    path = Path(path)

    def text(current):
        try:
            return current.read_text(encoding='utf-8')
        except OSError:
            return None

    found = text(path)
    role = role_of(found) if found is not None else 'module'
    package = package_of(path, role) or path.parent
    out, done, trail = [], set(), set()

    def visit(current):
        key = current.resolve()
        if key in done or key in trail:
            return
        trail.add(key)
        written = text(current)
        for name in USE.findall(written or ''):
            target = module_path(name, package)
            if target.name != ENTRY and target.is_file():
                visit(target)
        trail.discard(key)
        done.add(key)
        out.append(current)

    if role == 'variant' and (package / ENTRY).is_file():
        visit(package / ENTRY)
    visit(path)
    return out


def library_line(path):
    """(the main file of the model of the entry file `path`, the folder that its `library "PATH"`
    line names, relative to the main file, or None without the line): a variant reads its
    package's."""
    path = Path(path)
    role = role_of(path.read_text(encoding='utf-8'))
    main = path if role != 'variant' else (package_of(path, role) or path.parent) / ENTRY
    try:
        scenario = parse(main.read_text(encoding='utf-8')).scenario
    except (OSError, SyntaxProblem):
        return main, None
    return main, (scenario.library if scenario is not None else None)
