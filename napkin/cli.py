"""The `napkin` command (docs/cli.md): `napkin COMMAND [ARGS] [TARGET]`.

Each command is a module of `napkin.commands`, which gives its line in the list of commands, its
arguments and its `main`. `main` here parses the command line and runs the command. Exit codes: 0 ok,
1 diagnostics (`common.Failed`), 2 usage (argparse, and `common.UsageError`), 3 when the input of
`napkin play` ends before the run does. `napkin --help` loads no engine: the command modules import
it in their `main`.
"""

from __future__ import annotations

import argparse
import sys

from .commands import common, modules

DESCRIPTION = 'Compile and run evidence-based simulation models written in .scn files.'

CLOSING = """\
TARGET is a scenario folder (its model.scn starts with `scenario`) or that file; default `.`.
Pick a variant with --variant NAME. Run `napkin COMMAND --help` for examples."""


def parsers():
    """(the parser of `napkin`, {command: its parser}). Each command's parser has its module's
    arguments (`configure`), and its `main` as `handler`."""
    from . import __version__

    commands = modules()
    width = max(len(name) for name in commands)
    listed = '\n'.join(f'  {name:<{width}}   {module.SUMMARY}' for name, module in commands.items())
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


def json_forms(argv):
    """`argv` with the `--json` of `napkin run` in one word, so the flag never takes the TARGET: `--json
    full` is `--json=full`, and a bare `--json` is `--json=compact`. Other commands' `--json` is a plain
    flag, and nothing after `--` changes."""
    argv = list(argv)
    at = next((k for k, word in enumerate(argv) if not word.startswith('-')), None)
    if at is None or argv[at] != 'run':
        return argv
    out, k = argv[: at + 1], at + 1
    while k < len(argv):
        word = argv[k]
        if word == '--':
            out += argv[k:]
            break
        if word == '--json':
            full = k + 1 < len(argv) and argv[k + 1] == 'full'
            out.append('--json=full' if full else '--json=compact')
            k += 2 if full else 1
            continue
        out.append(word)
        k += 1
    return out


def parse(argv):
    """The parsed arguments of a command line (without the program's name)."""
    return parsers()[0].parse_args(json_forms(argv))


def main(argv=None):
    """Run the command that `argv` (by default the program's arguments) names, and give its exit
    code. A `common.UsageError` prints the command's usage and the message (exit 2); a `common.Failed`
    prints its diagnostics (exit 1)."""
    argv = sys.argv[1:] if argv is None else list(argv)
    top, found = parsers()
    args = top.parse_args(json_forms(argv))
    try:
        return args.handler(args)
    except common.UsageError as exc:
        parser = found[args.command]
        parser.print_usage(sys.stderr)
        sys.stderr.write(f'{parser.prog}: error: {exc}\n')
        return 2
    except common.Failed as exc:
        if exc.message:
            sys.stderr.write(f'{exc.message}\n')
        common.show_diagnostics(exc.diagnostics, sys.stderr)
        return 1
