"""`napkin compile`: compile a model and give its diagnostics, or a short summary of its program
(docs/cli.md).

The front end reads the main file and the library of the package, declares the model and lowers it
to a program (`napkin.model.compile.load_scenario`), which the program's checker accepts. A model
that does not compile prints each problem, `file:line:column: error: message [code]`, and exits 1.
One that compiles prints a summary of its program: its default run, its named runs, its entities,
its inputs, stores, formulas and distributions, its flows with their ends, the units that it spells,
and its hash, which an edit document names (`model_hash`). `--json` prints the same as one JSON
document, with `diagnostics` empty or the problems.

The command also checks the file that only the picture reads: the stylesheet of the model
(`napkin.draw.style.of`: the variant's own `style.toml`, else its package's). A stylesheet with a
problem gives its diagnostics, each with its file and its key, after the summary.

Exit codes: 0 when the model compiles and its stylesheet holds, 1 for any diagnostic, 2 for a
command line that is wrong.
"""

import sys

from . import common

SUMMARY = 'compile a model; print its diagnostics or a summary of its program'

DESCRIPTION = """\
Compile a model: print each diagnostic with its place, or a summary of the program. Checks the
model's style.toml too. Exit 0 ok, 1 diagnostics."""

EXAMPLES = """\
example:
  napkin compile examples/piano_tuners"""

# The kinds of value of a program, as the summary groups them.
GROUPS = (
    ('input', 'inputs'),
    ('state', 'stores'),
    ('formula', 'formulas'),
    ('distribution', 'distributions'),
)


def configure(parser):
    """The description, the example and the arguments of `napkin compile`: `args.json` (True or
    False) and `args.model`."""
    parser.description = DESCRIPTION
    parser.epilog = EXAMPLES
    parser.add_argument('--json', action='store_true', help='print one JSON document')
    common.add_model(parser)


def main(args):
    """Compile the model that the arguments name and print its summary; give the exit code."""
    entry = common.entry_of(args.model)
    try:
        model = common.compiled(entry)
    except common.Failed as failed:
        if not args.json:
            raise
        common.write_json(
            {'model': common.shown(entry), 'diagnostics': list(map(common.problem_json, failed.problems))},
            sys.stdout,
        )
        return 1
    found = summary(model)
    problems = style_problems(model)
    if args.json:
        common.write_json(
            {'model': common.shown(entry), **found, 'diagnostics': list(map(common.problem_json, problems))},
            sys.stdout,
        )
        return 1 if problems else 0
    numerics = model.configuration.numerics
    print(f'{common.shown(entry)}: {found["title"]}')
    print(
        f'  run:           {model.configuration.mode}, to {common.number(found["horizon"])} h, '
        f'steps of at most {common.number(numerics.max_step)} h'
    )
    if found['runs']:
        print(f'  named runs:    {", ".join(found["runs"])}')
    print(f'  entities:      {", ".join(found["entities"]) or "none"}')
    for _, group in GROUPS:
        if found[group]:
            print(f'  {group + ":":<14} {", ".join(item["path"] for item in found[group])}')
    flows = [f'{item["path"]}: {item["source"]} -> {item["sink"]}' for item in found['flows']]
    if flows:
        print(f'  flows:         {", ".join(flows)}')
    print(f'  units:         {", ".join(found["units"]) or "none"}')
    print(f'  model hash:    {found["model_hash"]}')
    sys.stdout.flush()
    if problems:
        raise common.Failed(problems)
    return 0


def style_problems(model):
    """The diagnostics of the model's stylesheet (`napkin.draw.style.of`), or [] when it holds or the
    model has none."""
    from ..draw import style as styles
    from .draw import style_problems as problems_of

    try:
        styles.of(model)
    except styles.StyleError as error:
        return problems_of(error)
    return []


def summary(model):
    """The summary of a compiled model's program, as JSON: its title, the horizon of its default run
    in hours, the names of its named runs, its hash, its entities (each member's id), each value of
    each group of `GROUPS` with its unit, its flows with their ends and their unit, and the spellings
    of its table of units."""
    program = model.program
    found = {group: [] for _, group in GROUPS}
    entities, flows = [], []
    scopes = [(member.id, template) for template in program.templates for member in template.members]
    for owner, template in scopes:
        entities.append(owner)
        for value in template.values:
            found[dict(GROUPS)[value.kind]].append(value_json(f'{owner}.{value.name}', value))
        for flow in template.flows:
            ends = [end_text(end, owner) for end in (flow.source, flow.sink)]
            flows.append(
                {'path': f'{owner}.{flow.name}', 'source': ends[0], 'sink': ends[1], 'unit': flow.unit}
            )
    for value in program.root:
        found[dict(GROUPS)[value.kind]].append(value_json(value.name, value))
    return {
        'title': model.declared.scenario.title,
        'horizon': float(model.configuration.request.horizon),
        'runs': [run.name for run in model.declared.runs],
        'model_hash': model.model_hash,
        'entities': entities,
        **found,
        'flows': flows,
        'units': [unit.name for unit in program.units],
    }


def value_json(path, value):
    """A value of the summary: its path, and its unit (`''` for a plain number, `bool` for a yes/no)."""
    from ..program import parts as p

    kind = value.type.of if isinstance(value.type, p.DistributionType) else value.type
    return {'path': path, 'unit': getattr(kind, 'unit', 'bool' if isinstance(kind, p.Bool) else '')}


def end_text(end, owner):
    """An end of a flow as the summary writes it: `SOURCE`, `SINK`, or the path of its store."""
    from ..program import parts as p
    from ..program.refs import Named, This

    if isinstance(end, p.Outside):
        return end.name
    if isinstance(end.start, This):
        head = (owner,)
    elif isinstance(end.start, Named):
        head = (end.start.id,)
    else:
        head = ()
    return '.'.join((*head, *end.steps))
