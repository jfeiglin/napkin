"""The files of one model: its entry file, the files that it reads, and the library that it names.

A file's role is its first declaration: `scenario "Title"` is the main file of a package,
`<package>/model.scn`; `variant "Title"` is a variant, `<package>/variants/<name>/model.scn`; any
other file is a module. A line `use a.b` names the module `<package>/a/b.scn`, read from the folder
of the package, so no file of another package is read. A variant reads its package's main file
first. The files are read dependencies first: each file after the modules that it uses, in the
order of its `use` lines, and the entry file last; a module that two files use is read once.

`files` gives the files of a model with the problems of its `use` lines, each at its file and line:
a name with no module in the package, a file that is no module (an entry file, or a file whose first
declaration is a scenario or a variant line) and a circle of uses. The declared model of the files
is the front end's (`napkin/model/compile.py`).
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from ...paths import ENTRY, VARIANTS
from .parse import parse
from .problems import Problem, SyntaxProblem

NAME = r'[A-Za-z_][A-Za-z0-9_]*'
USE = re.compile(rf'^use ({NAME}(?:\.{NAME})*)[ \t]*(?:#.*)?$')
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


def uses(text):
    """(the name, the line) of each `use` line of a text, in written order."""
    out = []
    for number, row in enumerate(text.splitlines(), 1):
        found = USE.match(row)
        if found is not None:
            out.append((found.group(1), number))
    return out


@dataclass(frozen=True)
class Files:
    """The files of the model of an entry file: its role (`main` or `variant`), the folder of its
    package, each file with its text in the order in which they are read, and the problems of the
    files (each a `Problem` with its file)."""

    role: str
    package: Path
    files: tuple[tuple[Path, str], ...]
    problems: tuple[Problem, ...] = ()


def _read(path):
    try:
        return path.read_text(encoding='utf-8')
    except OSError:
        return None


def files(path):
    """The files of the model of the entry file `path` (`Files`). A missing entry file raises
    FileNotFoundError."""
    path = Path(path)
    text = path.read_text(encoding='utf-8')
    role, problems = role_of(text), []
    where = path.as_posix()
    if role == 'module':
        problems.append(
            Problem(
                'scenario',
                'a module is no model: a model starts with its scenario line, scenario "Title"',
                1,
                0,
                where,
            )
        )
    package = package_of(path, role)
    if package is None:
        problems.append(
            Problem(
                'scenario',
                f'a variant is the file {VARIANTS}/<name>/{ENTRY} of its package',
                1,
                0,
                where,
            )
        )
        package = path.parent
    out, done, trail = [], set(), []

    def visit(current, written):
        key = current.resolve()
        if key in done:
            return
        if key in trail:
            circle = ' -> '.join(item.name for item in [*trail[trail.index(key) :], key])
            problems.append(Problem('use', f'the uses close a circle: {circle}', 0, 0, current.as_posix()))
            return
        trail.append(key)
        for name, line in uses(written):
            target = module_path(name, package)
            found = _read(target) if target.is_file() else None
            if found is None:
                problems.append(
                    Problem(
                        'use',
                        f'use {name}: the package {package.name} has no module {"/".join(name.split("."))}.scn',
                        line,
                        0,
                        current.as_posix(),
                    )
                )
            elif target.name == ENTRY or role_of(found) != 'module':
                problems.append(
                    Problem(
                        'use',
                        f'use {name}: {target.name} is not a module: an entry file, or a file that starts with '
                        'its scenario or variant line, is a model of its own',
                        line,
                        0,
                        current.as_posix(),
                    )
                )
            else:
                visit(target, found)
        trail.pop()
        done.add(key)
        out.append((current, written))

    main = package / ENTRY
    if role == 'variant':
        if main.is_file():
            visit(main, _read(main) or '')
        else:
            problems.append(
                Problem('scenario', f"a variant reads its package's {ENTRY}, and there is none", 1, 0, where)
            )
    visit(path, text)
    return Files(role, package, tuple(out), tuple(problems))


def paths(path):
    """The files that the model of the entry file `path` reads, dependencies first and `path` last."""
    return [file for file, _ in files(path).files]


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
