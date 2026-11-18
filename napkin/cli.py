"""The `napkin` command (docs/cli.md): `napkin COMMAND [ARGS]`.

Each command of this stage of the rewrite is a module of `napkin.commands`, which gives its line in
the list of commands, its arguments and its `main`. `main` here parses the command line and runs the
command. A command that a later stage brings back (`commands.LATER`) is listed, and refused whatever
its arguments. Exit codes: 0 ok, 1 diagnostics (`common.Failed`), 2 usage (argparse, a
`common.UsageError`, and a refused command). `napkin --help` and `napkin --version` load no compiler
and no engine: the command modules import them in their `main`.
"""

from __future__ import annotations

import argparse
import sys

from .commands import LATER, STAGE, common, modules

DESCRIPTION = 'Compile and run simulation models written in .scn files.'

CLOSING = """\
MODEL is a package folder (its model.scn starts with `scenario`) or that file.
Run `napkin COMMAND --help` for its arguments and an example."""


def refused(name):
    """The handler of a command that a later stage brings back: it says so and gives exit 2."""

    def handler(args):
        sys.stderr.write(
            f'napkin {name} comes back in a later stage of the rewrite of the language (stage {STAGE})\n'
        )
        return 2

    return handler


def parsers():
    """(the parser of `napkin`, {command: its parser}). Each command's parser has its module's
    arguments (`configure`) and its `main` as `handler`; a command of `LATER` has a handler that
    refuses it, whatever follows it."""
    from . import __version__

    commands = modules()
    lines = {name: module.SUMMARY for name, module in commands.items()}
    lines.update({name: f'{line} (a later stage brings it back)' for name, line in LATER.items()})
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
    for name in LATER:
        # No argument and no `--help`: whatever follows the command is left over, and refused.
        parser = chosen.add_parser(name, prog=f'napkin {name}', add_help=False)
        parser.set_defaults(handler=refused(name))
        found[name] = parser
    return top, found


def main(argv=None):
    """Run the command that `argv` (by default the program's arguments) names, and give its exit
    code. A `common.UsageError` prints the command's usage and the message (exit 2); a
    `common.Failed` prints its diagnostics (exit 1)."""
    argv = sys.argv[1:] if argv is None else list(argv)
    top, found = parsers()
    args, rest = top.parse_known_args(argv)
    if rest and args.command not in LATER:
        top.error(f'unrecognized arguments: {" ".join(rest)}')
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
