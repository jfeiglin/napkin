"""The `napkin` command (docs/cli.md): `napkin COMMAND [ARGS]`.

Each command is a module of `napkin.commands`, which gives its line in the list of commands, its
arguments and its `main`. `main` here parses the command line and runs the command. Exit codes: 0
ok, 1 diagnostics (`common.Failed`), 2 usage (argparse and a `common.UsageError`); a command may give
its own (`napkin play` exits 3 when its input ends before its run). `napkin --help` and
`napkin --version` load no compiler and no engine: the command modules import them in their `main`.
"""

from __future__ import annotations

import argparse
import sys

from .commands import common, modules

DESCRIPTION = 'Compile and run simulation models written in .scn files.'

CLOSING = """\
MODEL is a package folder (its model.scn starts with `scenario`) or that file.
Run `napkin COMMAND --help` for its arguments and an example."""


def parsers():
    """(the parser of `napkin`, {command: its parser}). Each command's parser has its module's
    arguments (`configure`) and its `main` as `handler`."""
    from . import __version__

    commands = modules()
    lines = {name: module.SUMMARY for name, module in commands.items()}
    width = max(len(name) for name in lines)
    listed = '\n'.join(f'  {name:<{width}}   {line}' for name, line in lines.items())
    top = argparse.ArgumentParser(
        prog='napkin',
        usage='%(prog)s [-h] [--version] COMMAND ...',
        description=DESCRIPTION,
        epilog=f'commands:\n{listed}\n\n{CLOSING}',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        allow_abbrev=False,
    )
    top.add_argument('--version', action='version', version=__version__)
    chosen = top.add_subparsers(dest='command', metavar='COMMAND', required=True, help=argparse.SUPPRESS)
    found = {}
    for name, module in commands.items():
        parser = chosen.add_parser(
            name,
            prog=f'napkin {name}',
            help=module.SUMMARY,
            formatter_class=argparse.RawDescriptionHelpFormatter,
            allow_abbrev=False,
        )
        module.configure(parser)
        parser.set_defaults(handler=module.main)
        found[name] = parser
    return top, found


def main(argv=None):
    """Run the command that `argv` (by default the program's arguments) names, and give its exit
    code. A `common.UsageError` prints the command's usage and the message (exit 2); a
    `common.Failed` prints its diagnostics (exit 1)."""
    argv = sys.argv[1:] if argv is None else list(argv)
    top, found = parsers()
    args = top.parse_args(argv)
    try:
        return args.handler(args)
    except common.UsageError as exc:
        parser = found[args.command]
        parser.print_usage(sys.stderr)
        sys.stderr.write(f'{parser.prog}: error: {exc}\n')
        return 2
    except common.Failed as exc:
        sys.stdout.flush()
        common.show(exc.problems, sys.stderr)
        return 1
