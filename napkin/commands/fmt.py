"""`napkin fmt`: format .scn files (docs/cli.md).

Each PATH is a `.scn` file, or a folder whose `.scn` files the command finds below it, outside the
folders and files whose names start with a dot. Without a PATH, it formats the package that holds the
current folder: its main file, its modules and its variants. The formatter is the language's own
(`napkin.model.language.format.format_text`): it writes each line again from its tokens, so a file
that it formatted stays the same. The command writes only the files that change, and lists them.
`--check` writes nothing: it lists the files that the formatter would change.

Exit codes: 0 when every file is formatted (or, without `--check`, is now), 1 when `--check` finds a
file to change or a file does not read (`file:line:column: error: message`), 2 for a PATH that is no
`.scn` file or folder.
"""

import os
import sys
from pathlib import Path

from .. import paths
from . import common

SUMMARY = 'format .scn files'

DESCRIPTION = """\
Format .scn files in place (default: the scenario in .); --check only reports, exit 1 if any differ."""

EXAMPLES = """\
example:
  napkin fmt --check examples/piano_tuners"""

SUFFIX = '.scn'


def configure(parser):
    """The description, the example and the arguments of `napkin fmt`: `args.check` (True or False)
    and `args.paths` (a list of Paths, empty when not given)."""
    parser.description = DESCRIPTION
    parser.epilog = EXAMPLES
    parser.add_argument(
        '--check', action='store_true', help='only report the files that differ; exit 1 if any'
    )
    parser.add_argument(
        'paths', nargs='*', type=Path, metavar='PATH', help='a .scn file, or a scenario folder (default: .)'
    )


def main(args):
    """Format the files that the arguments name, or report those that differ; give the exit code."""
    from ..model.language.format import format_text
    from ..model.language.lex import SyntaxProblem

    files = scn_files(args.paths)
    changed, problems = [], []
    for path in files:
        try:
            text = path.read_text(encoding='utf-8')
            formatted = format_text(text)
        except SyntaxProblem as exc:
            problems.append(problem(path, exc.message, exc.line, exc.column))
            continue
        except UnicodeDecodeError as exc:
            problems.append(problem(path, f'not UTF-8 text: {exc.reason} at byte {exc.start}'))
            continue
        except ValueError as exc:  # a text that the language cannot write on several lines
            problems.append(problem(path, str(exc)))
            continue
        except OSError as exc:
            problems.append(problem(path, exc.strerror or str(exc)))
            continue
        if formatted == text:
            continue
        if not args.check:
            try:
                path.write_text(formatted, encoding='utf-8')
            except OSError as exc:
                problems.append(problem(path, exc.strerror or str(exc)))
                continue
        changed.append(path)
    for path in changed:
        print(shown(path))
    sys.stdout.flush()
    common.show_diagnostics(problems, sys.stderr)
    done = len(files) - len(problems)
    counted = f'{done} file' + ('' if done == 1 else 's')
    if args.check:
        summary = (
            f'{len(changed)} of {counted} would change' if changed else f'{counted} checked, all formatted'
        )
    else:
        summary = f'formatted {len(changed)} of {counted}'
    sys.stderr.write(summary + '\n')
    return 1 if problems or (args.check and changed) else 0


def scn_files(given):
    """The `.scn` files of the PATHs, each once, in order: a file as it is given, and the files below a
    folder, sorted, outside the folders and files whose names start with a dot. No PATH is the folder
    of the package that holds the current folder. Raises UsageError for a PATH that is neither a `.scn`
    file nor a folder, and for no PATH outside a package."""
    if not given:
        package = paths.package_of(Path.cwd())
        if package is None:
            raise common.UsageError(
                f'. is in no scenario folder (none above it holds a {paths.ENTRY}): give a PATH'
            )
        given = [package]
    found = {}
    for path in given:
        if path.is_dir():
            for file in below(path):
                found.setdefault(os.path.abspath(file), file)
        elif path.is_file() and path.suffix == SUFFIX:
            found.setdefault(os.path.abspath(path), path)
        elif path.exists():
            raise common.UsageError(f'{path} is not a {SUFFIX} file or a folder')
        else:
            raise common.UsageError(f'{path} does not exist')
    return list(found.values())


def below(folder):
    """The `.scn` files below `folder`, sorted, outside the folders and files whose names start with a
    dot."""
    out = []
    for top, folders, files in os.walk(folder):
        folders[:] = sorted(name for name in folders if not name.startswith('.'))
        out += [
            Path(top) / name
            for name in sorted(files)
            if name.endswith(SUFFIX) and not name.startswith('.') and (Path(top) / name).is_file()
        ]
    return out


def problem(path, message, line=None, column=None):
    """A diagnostic of a file that does not format: `file:line:column: error: message`."""
    item = {'code': 'format', 'severity': 'error', 'file': str(path), 'message': message}
    if line:
        item['line'] = line
        if column:
            item['column'] = column
    return item


def shown(path):
    """A path as the command lists it: relative to the current folder when it is inside it."""
    absolute = Path(os.path.abspath(path))
    try:
        return str(absolute.relative_to(Path.cwd()))
    except ValueError:
        return str(absolute)
