"""`napkin new`: start a scenario that compiles and runs as written (docs/cli.md).

`napkin new DIR` writes `DIR/model.scn`, the main file of a package. It holds one entity with a
stock, the people who wait, which a flow moves at a rate into a tally, the people served; a value of
the top level that follows the people served, for a caller to report (D10); and one assumption
record, which every value cites. It uses the prelude's units only and names no library, so it
compiles in any folder. It also writes the package's picture, `DIR/style.toml`, which says who plays
the service (`[role]`): the model has no role (PLAN.md, change 23 after G0). With `--variants
east,west`, it also writes `variants/NAME/model.scn` for each NAME: a variant that changes the rate,
each to a value of its own.

Each model file is its own formatted text (`format_text`). The command writes no file when one of them
is there already. Then it prints what to replace next: the title, the inputs and the record.
"""

import re
import shlex
import sys
from pathlib import Path

from .. import paths
from . import common

SUMMARY = 'start a scenario that compiles and runs as written'

DESCRIPTION = """\
Write DIR/model.scn: a model that compiles and runs as written (a stock, a flow, a value that follows
what it serves, one assumption record), its picture DIR/style.toml, plus variants/NAME/model.scn for
each variant. Prints what to replace next."""

EXAMPLES = """\
example:
  napkin new demo
  napkin run demo"""

# The title of the scenario when --title gives none.
TITLE = 'A new scenario'
# The name of a variant, which is the name of its folder: a lowercase letter, then lowercase letters,
# digits and `_`.
VARIANT = re.compile(r'[a-z][a-z0-9_]*', re.ASCII)
# The rate of the main file, and the step between the rates of the variants: the k-th variant (from 1)
# serves (k + 1) × STEP people in a day. The range of the rate holds each of them, and at least 10 ×
# STEP.
STEP = 10

# The main file. `{title}` is the title, `{rate}` the rate and `{high}` the high end of its range.
MODEL = """\
# Written by `napkin new`. It compiles and runs as written: replace the title, the texts, the values
# and the record `guess` with your own (docs/language.md).
scenario "{title}"
    summary "A service serves the people who wait for it at a steady rate. How many people does it serve?"
    horizon 30 days
    scope "The people who wait for the service."

service:
    "The service and the people who wait for it."
    input rate: people/day = {rate} people/day in [0 people/day, {high} people/day] @guess
        "People that the service serves in a day"
    waiting: people = 1000 people in [0,] scale 1000 people @guess
        "People who wait"
    served: people = 0 people in [0,] scale 1000 people @guess
        "People served"
    flow serve: this.waiting -> this.served @guess
        request = formula(this.rate)

people_served: formula(people) = formula(service.served) in [0,] @guess
    "People served"

record guess: assumption "An example value that napkin new writes. Replace each value that cites this record
    with your own value and its evidence."
"""

# The picture of the main file: who plays the service, which gives its card the icon of its role.
STYLE = """\
# The picture of the model, which `napkin draw` reads and the calculation never does (docs/draw.md).
# [role]: who plays each thing, such as operator = ["service"]; a thing has the icon of its role.
[role]
operator = ["service"]
"""

# A variant's file. `{name}` is its name, `{rate}` its rate.
VARIANT_MODEL = """\
# A variant of the package: it reads the main file, ../../model.scn, and changes one input.
variant "{name}"

change service:
    rate = {rate} people/day @guess
"""

# What the user replaces next, as the main file names them: its inputs and its records.
INPUTS = ('service.rate',)
RECORDS = ('guess',)


def configure(parser):
    """The description, the example and the arguments of `napkin new`: `args.dir` (a Path),
    `args.title` and `args.variants` (the text of the names, or None)."""
    parser.description = DESCRIPTION
    parser.epilog = EXAMPLES
    parser.add_argument('--title', metavar='TEXT', help='the title of the scenario')
    parser.add_argument('--variants', metavar='NAME,…', help='also write a variant for each NAME')
    parser.add_argument('dir', type=Path, metavar='DIR', help='the folder of the new scenario')


def title_of(text):
    """The title of `--title TEXT`, on one line: its words, each separated by one space; TITLE when
    `text` is None. Raises UsageError for a title with no words, and for a `"`, which ends a text of
    the language."""
    if text is None:
        return TITLE
    title = ' '.join(text.split())
    if not title:
        raise common.UsageError('--title takes a text with at least one word')
    if '"' in title:
        raise common.UsageError('a title has no ": use “ and ” inside it')
    return title


def variant_names(text):
    """The names of `--variants NAME,…`, in the order given: () when `text` is None. Raises UsageError
    for a name that is not a lowercase letter followed by lowercase letters, digits and `_`, and for a
    name given twice."""
    if text is None:
        return ()
    names = [name.strip() for name in text.split(',')]
    for name in names:
        if not VARIANT.fullmatch(name):
            raise common.UsageError(
                f'{name!r} is not a variant name: a lowercase letter, then lowercase letters, digits and _'
            )
    twice = sorted({name for name in names if names.count(name) > 1})
    if twice:
        raise common.UsageError(f'--variants gives {twice[0]} twice')
    return tuple(names)


def files(title=TITLE, variants=()):
    """{path in DIR: text} of the files of a new package: its main file, its picture (`STYLE`) and the
    file of each variant, each model file formatted (`format_text`). The k-th variant (from 1) sets the
    rate to (k + 1) × STEP people in a day, and the range of the main file's rate holds each of them."""
    from ..draw.style import STYLE_FILE
    from ..model.language.format import format_text

    high = STEP * max(10, len(variants) + 1)
    found = {paths.ENTRY: format_text(MODEL.format(title=title, rate=STEP, high=high)), STYLE_FILE: STYLE}
    for k, name in enumerate(variants, start=1):
        text = VARIANT_MODEL.format(name=name, rate=(k + 1) * STEP)
        found[f'{paths.VARIANTS}/{name}/{paths.ENTRY}'] = format_text(text)
    return found


def main(args):
    """Write the files of a new package in `args.dir` (`files`), and print what to replace next. Raises
    UsageError for a title or a variant name that is wrong, for a DIR that is a file and for a file of
    the package that is there already, before it writes any file; Failed when a file cannot be
    written."""
    title = title_of(args.title)
    variants = variant_names(args.variants)
    folder = Path(args.dir)
    if folder.exists() and not folder.is_dir():
        raise common.UsageError(f'{folder} is a file: give the folder of the new scenario')
    written = files(title, variants)
    for name in written:
        if (folder / name).exists():
            raise common.UsageError(f'{folder / name} is there already: give a new folder')
    for name, text in written.items():
        path = folder / name
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(text, encoding='utf-8')
        except OSError as error:
            raise common.Failed([common.problem('file', error.strerror or str(error), path)]) from None
    sys.stdout.write(next_steps(folder, title, variants))
    sys.stdout.flush()
    return 0


def next_steps(folder, title, variants):
    """What `napkin new` prints after it writes the package in `folder`: the files, the commands that
    run the model and its variants, and what to replace next."""
    from ..draw.style import STYLE_FILE

    main_file = folder / paths.ENTRY
    target = shlex.quote(str(folder))
    runs = [f'napkin run {target}'] + [
        f'napkin run {shlex.quote(str(folder / paths.VARIANTS / name))}' for name in variants
    ]
    wrote = f'Wrote {main_file} and its picture, {folder / STYLE_FILE}'
    if variants:
        kind = 'variants' if len(variants) > 1 else 'variant'
        wrote += f', and the {kind} {common.listed(variants)} in {folder / paths.VARIANTS}/'
    changed = ' (each variant changes its value)' if variants else ''
    return '\n'.join(
        [
            f'{wrote}.',
            f'It compiles and runs as written: {"; ".join(runs)}',
            '',
            f'Replace next, in {main_file}:',
            f'  - the title, "{title}", and the lines summary, horizon and scope under it;',
            f'  - the inputs, each with its value, its range and its text: {common.listed(INPUTS)}{changed};',
            f'  - the records, which each value cites: {common.listed(RECORDS)}. Give each value a record of its own.',
            f'After each change, `napkin compile {target}` checks the model (docs/language.md gives each line).',
            '',
        ]
    )
