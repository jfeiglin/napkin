"""The commands of `napkin` (napkin/cli.py), in the order that `napkin --help` lists them.

Each command is a module of this package with three names:

- `SUMMARY`: its line in `napkin --help`;
- `configure(parser)`: its description, its examples and its arguments, on its own parser;
- `main(args) -> int`: the command, which reads the parsed arguments and gives the exit code: 0 ok,
  1 diagnostics, 2 usage.

A command module imports only the standard library and `common` when it is imported, so
`napkin --help` loads no compiler and no engine. Its `main` imports them.

`napkin play` is a client of the engine's checkpoints (`napkin/session.py`): breakpoints, checkpoints
and edits replace the player's picks (docs/design/decisions.md, change 15).
"""

import importlib

# The command modules, in order.
NAMES = ('compile', 'run', 'sample', 'play', 'fmt', 'draw', 'new')


def modules():
    """{name: module} of each command, in order."""
    return {name: importlib.import_module(f'{__name__}.{name}') for name in NAMES}
