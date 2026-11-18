"""The commands of `napkin` (napkin/cli.py), in the order that `napkin --help` lists them.

Each command of this stage of the rewrite is a module of this package with three names:

- `SUMMARY`: its line in `napkin --help`;
- `configure(parser)`: its description, its examples and its arguments, on its own parser;
- `main(args) -> int`: the command, which reads the parsed arguments and gives the exit code: 0 ok,
  1 diagnostics, 2 usage.

A command module imports only the standard library and `common` when it is imported, so
`napkin --help` loads no compiler and no engine. Its `main` imports them.

The commands of `LATER` come back in a later stage of the rewrite: `napkin --help` lists them, and
each refuses to run with exit 2. Their modules (`play.py`, `sample.py`, `draw.py`, `new.py`) read
the old compiled form, and nothing imports them until that stage ports them.
"""

import importlib

# The command modules of this stage, in order.
NAMES = ('compile', 'run', 'fmt')
# The commands that a later stage brings back: {name: its line in `napkin --help`}.
LATER = {
    'play': 'run one run step by step and pick its decisions',
    'sample': 'run one run many times with drawn inputs',
    'draw': 'draw a static picture of the model as SVG',
    'new': 'start a scenario that compiles and runs as written',
}
# The stage of the rewrite that brings them back: results and consumers (scratch/rewrite/PLAN.md).
STAGE = 'C'


def modules():
    """{name: module} of each command of this stage, in order."""
    return {name: importlib.import_module(f'{__name__}.{name}') for name in NAMES}
