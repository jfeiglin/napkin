"""`napkin draw`: draw a static picture of the model as SVG (docs/cli.md, docs/draw.md)."""

from pathlib import Path

from . import common

SUMMARY = 'draw a static picture of the model as SVG'

DESCRIPTION = """\
Draw a static picture of the model as SVG:
  - each thing as a box, with its stocks and the flows between them
  - each named-state var as a small state machine, its events on the transitions
  - arrows for what each thing reads, follows, changes, fires and moves of the others, and a legend
The style.toml of the variant, else of the package (or --style FILE), places, groups, hides and
labels things, sets their icons, where each state machine goes, the looks of the arrows and the
events that a card shows. Everything else lays itself out, the same way every time. --latex FILE
also writes the equations, symbols and references of the stylesheet's [equations] as a LaTeX
fragment (amsmath, longtable, hyperref)."""

EXAMPLES = """\
example:
  napkin draw scenarios/water_controls_wipe --variant juneau -o juneau.svg"""


def configure(parser):
    """The description, the example and the arguments of `napkin draw`: `args.variant` and `args.run`
    (None when not given); `args.style`, `args.output` (`-o`) and `args.latex` (Paths, or None); and
    `args.target`."""
    parser.description = DESCRIPTION
    parser.epilog = EXAMPLES
    common.add_variant(parser)
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
        help='the SVG to write (default: <name>.svg in the current folder)',
    )
    parser.add_argument(
        '--latex',
        type=Path,
        metavar='FILE',
        help='also write the equations, symbols and references as a LaTeX fragment',
    )
    common.add_target(parser)


def output_name(target, run=None):
    """The default file of `napkin draw`: `<package>[.<variant>][.<run>].svg`, in the current folder;
    `run` is the run that `--run` names."""
    return Path(target.name.replace(':', '.') + (f'.{run}' if run is not None else '') + '.svg')


def stylesheet(model, path=None):
    """The stylesheet of a model (`napkin.draw.style.of`): the file at `path`, else the variant's or the
    package's `style.toml`, else none. A file with a problem is a `common.Failed` with its
    diagnostics."""
    from ..draw import style as styles

    try:
        return styles.of(model, path)
    except styles.StyleError as exc:
        raise common.Failed(exc.diagnostics) from None


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


def main(args):
    """Draw the model of the TARGET: load it (with `--run`, checked for that run only, as `napkin run`
    loads it: a run that the model does not have is a usage error), read its stylesheet (`--style
    FILE`, else the variant's or the package's `style.toml`), make its picture, lay it out and write
    the SVG. The run is `--run`, else the only run of a model that has one; a model with several runs
    and no `--run` is drawn with every run joined. A stylesheet with a problem gives its diagnostics
    (exit 1). With `--latex FILE`, it also writes the LaTeX fragment of the picture's panels
    (`panels.latex`, D-57); a stylesheet whose `[equations] things` names nothing gives a fragment of
    comments only, and a note says so. A picture taller than a PDF page holds gets a note
    (`height_note`)."""
    from ..draw import layout as layouts
    from ..draw import model_map, panels
    from ..draw import svg as svgs
    from .run import load

    target = common.one_target(args.target, args.variant)
    model = load(target, [args.run] if args.run is not None else None)
    style = stylesheet(model, args.style)
    run = args.run if args.run is not None or len(model.runs) != 1 else next(iter(model.runs))
    picture = model_map.picture(model, style, run=run)
    found = layouts.layout(picture, style)
    text = svgs.svg(picture, found)
    output = args.output if args.output is not None else output_name(target, args.run)
    try:
        Path(output).write_text(text, encoding='utf-8')
    except OSError as exc:
        raise common.Failed([common.os_diagnostic(exc, output)]) from None
    if args.latex is not None:
        try:
            Path(args.latex).write_text(panels.latex(picture), encoding='utf-8')
        except OSError as exc:
            raise common.Failed([common.os_diagnostic(exc, args.latex)]) from None
    note = common.scope_note(model)
    if note:
        print(f'note: {note}')
    if found.height > layouts.PAGE_HEIGHT:
        print(f'note: {height_note(output, found.height)}')
    cards, routes = len(found.cards), len(found.routes)
    print(
        f'{output}: {cards} {"thing" if cards == 1 else "things"}, {routes} {"arrow" if routes == 1 else "arrows"}'
    )
    if args.latex is not None:
        print(latex_line(args.latex, picture['panels']))
    return 0
