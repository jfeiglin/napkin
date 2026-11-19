"""The commands of `napkin` (napkin/cli.py), in the order that `napkin --help` lists them.

Each command is a module of this package with three names:

- `SUMMARY`: its line in `napkin --help`;
- `configure(parser)`: its description, its examples and its arguments, on its own parser;
- `main(args) -> int`: the command, which reads the parsed arguments and gives the exit code: 0 ok,
  1 diagnostics, 2 usage.

A command module imports only the standard library and `common` when it is imported, so
`napkin --help` loads no compiler and no engine. Its `main` imports them.

The commands of `LATER` come back in a later stage of the rewrite: `napkin --help` lists them, and
each refuses to run with exit 2, naming its stage. `napkin play` becomes a client of the checkpoints
of slice S7 (breakpoints, checkpoints and edits replace the player's picks: scratch/rewrite/PLAN.md,
change 15). Its module (`play.py`) reads the old compiled form, and nothing imports it until then.
"""

import importlib

# The command modules, in order.
NAMES = ('compile', 'run', 'sample', 'fmt', 'draw', 'new')
# The commands that a later stage brings back: {name: (its line in `napkin --help`, the stage)}.
LATER = {'play': ('run one run step by step from its checkpoints', 'S7')}


def modules():
    """{name: module} of each command, in order."""
    return {name: importlib.import_module(f'{__name__}.{name}') for name in NAMES}
