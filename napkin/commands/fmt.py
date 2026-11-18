"""`napkin fmt`: format .scn files in the language's own layout (docs/cli.md).

Each FILE is a `.scn` file, or a folder whose `.scn` files the command finds below it, outside the
folders and files whose names start with a dot. The formatter is the language's own
(`napkin.model.language.format.format_text`): it writes each line again from its parsed form, so a
file that it formatted stays the same. The command writes only the files that change and lists
them; `--check` writes nothing and lists the files that the formatter would change.

Exit codes: 0 when every file is formatted (or, without `--check`, is now), 1 when `--check` finds a
file to change or a file does not read (`file:line:column: error: message [code]`), 2 for a FILE
that is no `.scn` file or folder.
"""

import os
import sys
from pathlib import Path

from . import common

SUMMARY = 'format .scn files'

DESCRIPTION = """\
Format .scn files in place; --check only lists the files that would change, exit 1 if any."""

EXAMPLES = """\
example:
  napkin fmt --check examples/piano_tuners"""


def configure(parser):
    """The description, the example and the arguments of `napkin fmt`: `args.check` (True or False)
    and `args.files` (a list of Paths, at least one)."""
    parser.description = DESCRIPTION
    parser.epilog = EXAMPLES
    parser.add_argument('--check', action='store_true', help='only list the files that differ; exit 1 if any')
    parser.add_argument(
        'files', nargs='+', type=Path, metavar='FILE', help='a .scn file, or a folder of them'
    )


def main(args):
    """Format the files that the arguments name, or list those that differ; give the exit code."""
    from ..model.language.format import format_text
    from ..model.language.problems import SyntaxProblem

    files = scn_files(args.files)
    changed, problems = [], []
    for path in files:
        try:
            text = path.read_text(encoding='utf-8')
            formatted = format_text(text)
            if formatted != text and not args.check:
                path.write_text(formatted, encoding='utf-8')
        except SyntaxProblem as error:
            found = error.problem
            problems.append(common.problem(found.code, found.message, path, found.line, found.column))
            continue
        except UnicodeDecodeError as error:
            problems.append(
                common.problem('source', f'not UTF-8 text: {error.reason} at byte {error.start}', path)
            )
            continue
        except OSError as error:
            problems.append(common.problem('file', error.strerror or str(error), path))
            continue
        if formatted != text:
            changed.append(path)
    for path in changed:
        print(common.shown(path))
    sys.stdout.flush()
    common.show(problems, sys.stderr)
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
    """The `.scn` files of the FILEs, each once, in order: a file as it is given, and the files below
    a folder, sorted, outside the folders and files whose names start with a dot. A FILE that is
    neither a `.scn` file nor a folder is a UsageError."""
    found = {}
    for path in given:
        if path.is_dir():
            for file in below(path):
                found.setdefault(os.path.abspath(file), file)
        elif path.is_file() and path.suffix == common.SUFFIX:
            found.setdefault(os.path.abspath(path), path)
        elif path.exists():
            raise common.UsageError(f'{path} is not a {common.SUFFIX} file or a folder')
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
            if name.endswith(common.SUFFIX) and not name.startswith('.') and (Path(top) / name).is_file()
        ]
    return out
