"""Start a package of the catalogue: python -m tools.new NAME [--title TEXT].

It makes the folder `scenarios/<NAME>/` with every file that a package of the catalogue has, each in
its shape and with no content of a scenario: the model file with its scenario block, which names the
catalogue's library (`library "../library"`), and an outline of the parts to write; an empty
stylesheet and empty brief settings; no local units; empty evidence lists; a research note and a
README with their headings; and the tests folder with no expected orders and no oracle inputs (the
root conftest.py rewrites the assertions of its test modules and helpers). Then it prints the list of
what to write, in order. The publisher writes `results/`.

NAME is the name of a real package (`tools/catalogue.py`): a lowercase letter, then lowercase letters,
digits and `_`, and not a folder of the catalogue's own (`docs`, `library`, `tests`). The tests'
reserved IDs (`SC97`) name synthetic packages, which only the tests write.

The catalogue finds the folder at once, and no central file names it. Until the package is complete,
`check --scenario NAME` shows what it still lacks; the full check fails while it is incomplete.
Sources and claims come only through `tools.evidence.integrate`, and records of another package
through `tools.evidence.adopt`, so this tool writes no evidence record. For a model outside the
catalogue, `napkin new DIR` writes a starter that compiles and runs as written.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

from napkin.commands import common
from napkin.commands.new import title_of

from . import catalogue

# The name of a real package: the catalogue's rule for the folder of a package, without the tests'
# reserved IDs.
NAME = re.compile(catalogue._NAMED, re.ASCII)

MODEL = """\
# {title}
scenario "{title}"
    summary "Write the story here in a few sentences. Its first sentence is the hook."
    horizon 720 h
    scope "Write here whom the outputs cover."
    library "../library"

# Write the model below. docs/modeling-guide.md says how, and docs/language.md gives each line.
# - A thing for each real thing or actor, with its inputs, vars, flows, events and records.
# - event start when t >= 0 h: the attacker's first move, an event of the attacker.
# - options "Response": the defenders' tiers. Another group gives the attacker: the AI agent, and
#   the human team that it is compared with (scenarios/docs/ai-operations.md).
# - runs: each run names one option of each group. The human team's run says `versus` its AI run.
# - Outputs with `category` deaths, casualties and loss, or `unestimated` with the reason.
# - notes: the premises, the limitations and the verification (scenarios/docs/catalogue.md).
# - The named records at the end of the file.
"""

STYLE = """\
# The picture of the model on the map of the system (docs/draw.md). The calculation never reads it.
# [icon]: the icon of a thing, one of twenty icons, such as factory = ["plant"].
# [layout]: hide = ["Thing"] names the templates and things that the map does not draw.
# [place] and [group]: the column and row of a thing, and labelled frames around things.
# [arrows]: the look of each kind of arrow ("full", "light" or "hidden"), and the kinds that bundle.
# [triggers]: the events that a card shows, such as rules = ["attacker"].
# [equations] and [references]: the equations, symbols and sources of things, such as
# things = ["plant"] and show = true; [symbol.plant] sets a symbol, such as level = "L".
"""

BRIEF = """\
# What the pages show first. The calculation never reads it.
# show: the outputs, the measures of the AI's edge first; drivers: the inputs that the brief lists;
# featured: the AI run and its matched comparison, such as featured = ["delayed", "delayed_human"].
# attack: the name of the attack on the pages, such as attack = "tampered dosing"; choice_group: the
# group of options that holds the responses of the defenders, such as choice_group = "Response".
"""

RESEARCH = """\
# Consequence research

Research date: YYYY-MM-DD. Executable definitions: {name}. Currency: USD2025.

## {name}: {title}

Write what the research found, and how the model uses each value (scenarios/docs/evidence/README.md).
"""

README = """\
# {name}

[Model](model.scn) · [Methods](results/methods.md)

This folder owns the model, evidence, units, tests and generated results. Shared mathematics and vocabulary remain central.

## Mechanism family

## Evidence and checks

[Research note](evidence/research.md) · [Sources](evidence/sources.json) · [Claims](evidence/claims.json) · [Assumptions](evidence/assumptions.json) · [Local units](units.json) · [Oracle inputs](tests/oracle-inputs.json)

## Consequences

## Run and publish

Run from the repository root:

```sh
napkin run scenarios/{name}
python -B -m tools.publish --write --scenario {name}
python -B -m tools.check --scenario {name}
```

The publisher owns files in `results/`. Evidence changes go through `tools.evidence.integrate`; local tests and prose remain authored files.

[Shared testing rules](../../CONTRIBUTING.md#testing)
"""

CHECKLIST = """\
Write {name} in this order. After each step, `napkin compile {folder}` gives each diagnostic
with its file, line and column, and `napkin run {folder}` the outcomes of each run.

1. The model, {folder}/model.scn: the scenario block, the things, the first move, the options
   with the group "Response", the AI agent and its matched human team, the runs, the outputs, the
   notes and the records (docs/modeling-guide.md, docs/language.md, scenarios/docs/conventions.md,
   scenarios/docs/ai-operations.md).
2. The evidence, {folder}/evidence/: sources and claims only through
   `python -m tools.evidence.integrate --scenario {name} --write`; a record of another
   package through `python -m tools.evidence.adopt --from OTHER --to {name} --id RECORD --write`;
   the research note in research.md (scenarios/docs/evidence/README.md).
3. The local units, {folder}/units.json, for each unit that the shared vocabulary does not have.
4. The brief settings, {folder}/brief.toml: show, drivers, featured, attack and choice_group. The
   picture, {folder}/style.toml: [icon], and [layout] with hide. `napkin compile {folder}` checks the
   stylesheet, and `napkin draw {folder}` draws the picture.
5. The tests, {folder}/tests/: the expected orders of the standard runs (expected-orders.json), the
   oracle inputs (oracle-inputs.json), and owned tests with independent mathematics (CONTRIBUTING.md, "Testing").
6. The summaries: `python -B -m tools.publish --write --scenario {name}`. Then
   `python -B -m tools.check --scenario {name}` until it passes.

Until then, the full check fails: the catalogue finds the folder at once.
"""


def files(name, title):
    """{path in the folder: text} of a new package."""
    values = {'name': name, 'title': title}
    empty = json.dumps([]) + '\n'
    return {
        'model.scn': MODEL.format(**values),
        'style.toml': STYLE,
        'brief.toml': BRIEF,
        'units.json': json.dumps({}) + '\n',
        'README.md': README.format(**values),
        'evidence/sources.json': empty,
        'evidence/claims.json': empty,
        'evidence/assumptions.json': empty,
        'evidence/research.md': RESEARCH.format(**values),
        'tests/expected-orders.json': empty,
        'tests/oracle-inputs.json': json.dumps({}) + '\n',
    }


def create(root, name, title):
    """Write the folder of a new package, `scenarios/<name>/` of the checkout `root`, and give its
    path. The title is on one line, as `napkin new` writes it (`title_of`). Raises ValueError for a name
    that is not the name of a real package, for a folder that is there already, and for a title with
    no words or with a `"`."""
    try:
        title = title_of(title)
    except common.UsageError as exc:
        raise ValueError(str(exc)) from None
    if not NAME.fullmatch(name):
        raise ValueError(
            f'{name!r} is not a package name: a lowercase letter, then lowercase letters, digits and _, '
            f'and not {", ".join(catalogue.RESERVED)}'
        )
    folder = Path(root) / catalogue.SCENARIOS / name
    if folder.exists():
        raise ValueError(f'{folder} is there already: give a new name')
    for part, text in files(name, title).items():
        path = folder / part
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding='utf-8')
    return folder


def main(argv=None):
    parser = argparse.ArgumentParser(
        prog='python -m tools.new',
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
        allow_abbrev=False,
    )
    parser.add_argument('name', metavar='NAME', help='the name of the new package, such as water_wipe')
    parser.add_argument(
        '--title',
        metavar='TEXT',
        default='Title of the scenario',
        help='the title, which the model and the pages show',
    )
    # The checkout whose catalogue gets the package: by default this one.
    parser.add_argument('--root', type=Path, default=catalogue.ROOT, help=argparse.SUPPRESS)
    args = parser.parse_args(argv)
    try:
        folder = create(args.root, args.name, args.title)
    except ValueError as exc:
        parser.error(str(exc))
    shown = folder.relative_to(args.root) if folder.is_relative_to(args.root) else folder
    print(f'Made {shown.as_posix()}/ with {len(files(args.name, args.title))} files.\n')
    print(CHECKLIST.format(name=args.name, folder=shown.as_posix()))
    return 0


if __name__ == '__main__':
    sys.exit(main())
