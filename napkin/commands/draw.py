"""`napkin draw`: draw a static picture of the model as SVG (docs/cli.md, docs/draw.md).

The command compiles the model (`common.compiled`), reads its stylesheet (`--style FILE`, else the
`style.toml` of the variant, else of its package: `napkin.draw.style.of`), makes its picture
(`napkin.draw.model_map.picture`), lays it out and writes the SVG. A stylesheet with a problem gives
its diagnostics, each with its file and its key, and the command writes no file (exit 1).

The runs of a model are its named runs, else its default run (`napkin.draw.things.Things.runs`).
`--run NAME` draws one run: the events that reachability proves cannot start in it are left out, with
their lines and arrows (D16). A model with one named run is drawn as that run; a model with several,
and no `--run`, is drawn with its runs joined, each event drawn when it can start in one of them.

The default file is `<package>[.<variant>][.<run>].svg` in the current folder. `--latex FILE` also
writes the equations, symbols and references of the stylesheet's `[equations]` as a LaTeX fragment
(`napkin.draw.panels.latex`); a stylesheet whose `[equations] things` names nothing gives a fragment
of comments only, and a note says so. A picture taller than a PDF page holds gets a note.
"""

from pathlib import Path

from . import common

SUMMARY = 'draw a static picture of the model as SVG'

DESCRIPTION = """\
Draw a static picture of the model as SVG:
  - each thing as a card, with its stocks and the flows between them
  - each enum state of a thing as a small state machine, its events on the transitions
  - arrows for what each thing reads, follows, changes, starts and moves of the others, and a legend
The style.toml of the variant, else of the package (or --style FILE), places, groups, hides and
labels things, sets their icons, where each state machine goes, the looks of the arrows and the
events that a card shows. Everything else lays itself out, the same way every time. --latex FILE
also writes the equations, symbols and references of the stylesheet's [equations] as a LaTeX
fragment (amsmath, longtable, hyperref). Exit 0 ok, 1 diagnostics, 2 usage."""

EXAMPLES = """\
example:
  napkin draw examples/piano_tuners -o tuners.svg"""


def configure(parser):
    """The description, the example and the arguments of `napkin draw`: `args.run` (None when not
    given); `args.style`, `args.output` (`-o`) and `args.latex` (Paths, or None); and `args.model`."""
    parser.description = DESCRIPTION
    parser.epilog = EXAMPLES
    parser.add_argument(
        '--run', metavar='NAME', help='draw that run: leave out the parts that cannot act in it'
    )
    parser.add_argument(
        '--style', type=Path, metavar='FILE', help='the stylesheet to use in place of style.toml'
    )
    parser.add_argument(
        '-o',
        dest='output',
        type=Path,
        metavar='FILE',
        help='the SVG to write (default: <package>[.<variant>][.<run>].svg in the current folder)',
    )
    parser.add_argument(
        '--latex',
        type=Path,
        metavar='FILE',
        help='also write the equations, symbols and references as a LaTeX fragment',
    )
    common.add_model(parser)


def output_name(entry, run=None):
    """The default file of `napkin draw`: `<package>[.<variant>][.<run>].svg`, in the current folder,
    by the folders of the entry file (`napkin.package.name_of`); `run` is the run that `--run`
    names."""
    from ..package import name_of

    return Path(name_of(entry).replace(':', '.') + (f'.{run}' if run is not None else '') + '.svg')


def stylesheet(model, path=None):
    """The stylesheet of a compiled model (`napkin.draw.style.of`): the file at `path`, else the
    variant's or the package's `style.toml`, else none. A file with a problem is a `common.Failed`
    with its diagnostics (`style_problems`)."""
    from ..draw import style as styles

    try:
        return styles.of(model, path)
    except styles.StyleError as error:
        raise common.Failed(style_problems(error)) from None


def style_problems(error):
    """The diagnostics of a `StyleError`, as the front end writes them: each with its file and, for
    a text that is not TOML, its line; the message starts with the key."""
    return [
        common.problem(item.get('code', 'style'), item['message'], item['file'], item.get('line') or 0)
        for item in error.diagnostics
    ]


def latex_line(path, found):
    """The line that `napkin draw --latex FILE` prints for its fragment: what it holds, or a note that
    the stylesheet names no thing in `[equations] things`."""
    if not found:
        return f'note: {path}: the stylesheet names no thing in [equations] things, so it holds no equation'

    def counted(number, word):
        return f'{number} {word}' + ('' if number == 1 else 's')

    parts = [
        counted(len(found['equations']), 'block'),
        counted(len(found['symbols']), 'symbol'),
        counted(len(found['references']), 'reference'),
    ]
    return f'{path}: ' + ', '.join(parts)


def height_note(path, height):
    """The note of a picture taller than a PDF page holds (`layout.PAGE_HEIGHT`)."""
    from ..draw import layout as layouts

    return (
        f'{path} is {height:,.0f} px tall, more than a PDF page holds ({layouts.PAGE_HEIGHT:,.0f} px); '
        'show fewer things in [equations] things, or use --latex'
    )


def written(path, text):
    """Write a text file, or raise Failed with the file."""
    try:
        Path(path).write_text(text, encoding='utf-8')
    except OSError as error:
        raise common.Failed([common.problem('file', error.strerror or str(error), path)]) from None


def main(args):
    """Draw the model of MODEL (see the module) and write its SVG, then its LaTeX with `--latex`;
    give the exit code. A run that the model does not have is a usage error."""
    from ..draw import layout as layouts
    from ..draw import model_map, panels
    from ..draw import svg as svgs
    from ..draw import style as styles

    entry = common.entry_of(args.model)
    model = common.compiled(entry)
    runs = [name for name in styles.things_of(model).runs if name is not None]
    if args.run is not None and args.run not in runs:
        known = f'; its runs are {common.listed(runs)}' if runs else '; it has no named run'
        raise common.UsageError(f'--run {args.run}: no run of the model' + (common.close(args.run, runs) or known))
    style = stylesheet(model, args.style)
    run = args.run if args.run is not None or len(runs) != 1 else runs[0]
    picture = model_map.picture(model, style, run=run)
    found = layouts.layout(picture, style)
    output = args.output if args.output is not None else output_name(entry, args.run)
    written(output, svgs.svg(picture, found))
    if args.latex is not None:
        written(args.latex, panels.latex(picture))
    if found.height > layouts.PAGE_HEIGHT:
        print(f'note: {height_note(output, found.height)}')
    cards, routes = len(found.cards), len(found.routes)
    print(
        f'{output}: {cards} {"thing" if cards == 1 else "things"}, {routes} {"arrow" if routes == 1 else "arrows"}'
    )
    if args.latex is not None:
        print(latex_line(args.latex, picture['panels']))
    return 0
