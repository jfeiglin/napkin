"""`napkin play`: run one run of a model, stop at breakpoints, show each stop, edit live stored values
there, save a stop to a file, and go on (docs/design/decisions.md, change 15).

The command plays one run with a `napkin.session.Session`: the model's default run, or the run of
`--run NAME`, under the edits of `--edits FILE`, as `napkin run` makes it. Each `--break AT` is a
location of the compiled program: an event (`depot.request_pump`, before the first step of each of
its occurrences), a stage (`depot.request_pump.step[0]`) or a statement
(`depot.request_pump.step[0].do[1]`, `setup[0]`), for every occurrence, or `AT@OWNER` for one member
or one occurrence (`...@depot.request_pump#0`). At each stop the command prints the stop's number,
its time, the location with its kind and its place in the source, the occurrence and what runs next,
then the values of `--value` (by default those of the stop's member and occurrence), each in its
declared unit, with what an edit can give it (the members of an enum) and its label. Wherever a line
names a member that has a title (`title "DC Water"`), the title follows it in brackets: `dc (DC
Water)`, `dc.demand (DC Water)`. Then it reads lines:

- `PATH = VALUE` edits a live stored value: a number in the value's declared unit, an enum member,
  `true` or `false`, or a text. The engine checks it, and a refusal is printed with its reason;
- `save FILE` writes the stop, with its edits, to a checkpoint file;
- `go` goes on to the next stop or to the end;
- `quit`, or the end of the input, stops there: the command exits 3.

`--from FILE` goes on from a checkpoint file, in this process or a fresh one, with the breakpoints
that it was saved with (so `--break` is refused with it); a checkpoint of another program, engine or
run is refused by name. At the end the command prints the values of `--value` (by default every
named value of the model) at the start and at the horizon, as `napkin run` does, then each edit that
the run took. Presentation is this command's: the engine knows no player (`napkin/session.py`).
"""

import sys
from decimal import Decimal
from fractions import Fraction

from . import common
from . import run as running

SUMMARY = 'run one run, stopping at breakpoints to show and edit its values'

DESCRIPTION = """\
Run one run of a model (its default run, or the run --run names, under the edits of --edits FILE)
and stop before each location of --break. At a stop, edit a stored value with PATH = VALUE, write
the stop to a file with save FILE, go on with go, or stop with quit. --from FILE goes on from a
saved stop. Exit 0 at the end, 1 diagnostics, 2 usage, 3 when the input ends before the run."""

EXAMPLES = """\
examples:
  napkin play examples/reservoir --break operator.decide
  napkin play examples/reservoir --break 'operator.decide.step[0]@operator' --value reservoir.water
  napkin play examples/reservoir --from stop.checkpoint"""

# The exit code when the input ends before the run does.
UNFINISHED = 3
HELP = 'Edit with PATH = VALUE, or: save FILE, go, quit.'


def configure(parser):
    """The description, the examples and the arguments of `napkin play`: `args.run` and `args.edits`
    (None when not given), `args.breaks` and `args.value` (lists of texts, empty when not given),
    `args.source` (a checkpoint file, or None) and `args.model`."""
    parser.description = DESCRIPTION
    parser.epilog = EXAMPLES
    parser.add_argument('--run', metavar='NAME', help='the named run (default: the default run)')
    parser.add_argument('--edits', metavar='FILE', help='an edit document of the inputs (JSON)')
    parser.add_argument(
        '--break',
        dest='breaks',
        action='append',
        default=[],
        metavar='AT[@OWNER]',
        help='stop before this event, stage or statement, for every occurrence or for one member or '
        'occurrence: --break "operator.decide.step[0]@operator" (repeatable)',
    )
    parser.add_argument(
        '--value',
        action='append',
        default=[],
        metavar='PATHS',
        help='the values to show at each stop and at the end: --value reservoir.water,reservoir.gate '
        "(default: at a stop, its member's and its occurrence's; at the end, every named value)",
    )
    parser.add_argument(
        '--from', dest='source', metavar='FILE', help='go on from a stop saved with `save FILE`'
    )
    common.add_model(parser)


def main(args):
    """Play the run; give 0 at its end, 3 when the input ends first. Raises UsageError and Failed
    (`cli.main`)."""
    entry = common.entry_of(args.model)
    model = common.compiled(entry)
    edits = common.edits_of(model, args.edits)
    configuration = common.configured(model, args.run, edits, args.edits)
    paths = [piece.strip() for text in args.value for piece in text.split(',')] or None
    for path in paths or ():
        known(model.program, path)
    session = session_of(args, model, configuration, entry)
    print(running.heading(model, args, float(configuration.request.horizon)))
    found = session.checkpoint if args.source is not None else advanced(session, entry)
    while found is not None:
        show(session, paths)
        if not answered(session, args):
            print(f'The run stops at its stop {session.checkpoint.stop.hit}, before its end.')
            return UNFINISHED
        found = advanced(session, entry)
    ended(model, args, session, configuration, paths, entry)
    return 0


# ---- the session ----------------------------------------------------------------------------------


def breakpoints_of(model, items):
    """The breakpoints of the `--break` items: `AT`, or `AT@OWNER` for one member or occurrence. A
    location that the program does not have is a UsageError, with the closest."""
    from ..program.checkpoint import Breakpoint

    origins = [location.origin for location in model.table.executable()]
    found = []
    for item in items:
        at, _, owner = (piece.strip() for piece in item.partition('@'))
        if at not in origins:
            raise common.UsageError(
                f'--break {item}: no event, stage or statement of the model' + common.close(at, origins)
            )
        found.append(Breakpoint(at, owner))
    return found


def session_of(args, model, configuration, entry):
    """A new session at the breakpoints of `--break`, or the session that goes on from the checkpoint
    of `--from`. A breakpoint that the engine refuses (one in a trigger's body) is a UsageError; a
    part that it does not run, and a checkpoint that does not go on here, are a Failed."""
    from ..engine.timeline import Outside
    from ..program.checkpoint import CheckpointError
    from ..program.config import ConfigurationError
    from ..session import Session

    if args.source is not None and args.breaks:
        raise common.UsageError('--from goes on at the breakpoints of its checkpoint: give no --break')
    if args.source is None and not args.breaks:
        raise common.UsageError('give a --break, or a checkpoint with --from')
    try:
        if args.source is not None:
            return Session.load(args.source, model.program, configuration=configuration, table=model.table)
        breakpoints = breakpoints_of(model, args.breaks)
        try:
            return Session(model.program, configuration, breakpoints, table=model.table)
        except CheckpointError as error:
            raise common.UsageError(f'--break: {error}') from None
    except CheckpointError as error:
        raise common.Failed([common.problem('checkpoint', error, args.source)]) from None
    except OSError as error:
        raise common.Failed([common.problem('file', error.strerror or error, args.source)]) from None
    except Outside as error:
        raise common.Failed(
            [common.problem('engine', f'the engine does not run this: {error}', entry)]
        ) from None
    except ConfigurationError as error:
        raise common.Failed([common.problem('configuration', error, entry)]) from None


def advanced(session, entry):
    """The session gone on to its next stop (its checkpoint) or to the end (None)."""
    from ..engine.errors import SimulationError

    try:
        return session.advance()
    except SimulationError as error:
        raise common.Failed([common.problem('engine', error, entry)]) from None


def known(program, path):
    """Check that a path of `--value` names a value of the program as the reader checks it
    (`napkin.engine.timeline.record.named`), else a UsageError with why: what the reader says where
    it says more than that the program has no such value, else the closest names of its members' and
    its root's values."""
    from ..engine.timeline.record import key_of, named

    try:
        named(program, key_of(program, path))
    except KeyError as error:
        reason = str(error.args[0]).removeprefix(f'{path}: ')
        if not reason.startswith('no value of'):
            raise common.UsageError(f'--value {path}: {reason}') from None
        names = [
            f'{member.id}.{value.name}'
            for template in program.templates
            for member in template.members
            for value in template.values
        ]
        names += [value.name for value in program.root]
        raise common.UsageError(
            f'--value {path}: no value of the model' + common.close(path, names)
        ) from None


# ---- a stop ---------------------------------------------------------------------------------------


def show(session, paths):
    """Print a stop (see the module)."""
    view = session.view(paths)
    stop = view.stop
    where = ''
    if view.where is not None:
        place = common.shown(view.where.file) if view.where.file else ''
        where = f' ({view.where.kind}' + (f' at {place}:{view.where.line})' if place else ')')
    owner = f'in {stop.owner} of {titled(stop.member, view.title)}' if stop.owner else 'in the setup'
    print()
    print(f'Stop {stop.hit} at {common.number(stop.t)} h: before {stop.at}{where}, {owner}.')
    print(f'Next: {following(view.next)}.')
    for entry in view.drawn:
        print(f'Drawn in this stage before the stop: {entry.part} = {shown(entry.detail("value"))}.')
    rows = [
        [titled(item.path, item.title), shown(item.value, item.unit), offered(item), item.label or '']
        for item in view.values
    ]
    for line in common.table(rows) if rows else ():
        print(f'  {line}')
    for edit in view.edits:
        target = edit.target if isinstance(edit.target, str) else path_of(edit.target)
        owner = edit.target.owner if not isinstance(edit.target, str) else target.rpartition('.')[0]
        print(f'  edited here: {titled(target, session.title(owner))} = {shown(edit.value)}')
    print(HELP)


def titled(name, title):
    """A name of a member, or a path through one, with the member's title in brackets after it."""
    return f'{name} ({title})' if title else name


def following(pending):
    """What runs next: the stage that runs from its start, then the others due in the round."""
    if not pending or pending[0] == ('', 'setup'):
        return 'the setup, from its start'
    named = [f'{stage} of {owner}' for owner, stage in pending]
    text = f'{named[0]}, from its start'
    if len(named) > 1:
        text += f', then {len(named) - 1} more {"stage" if len(named) == 2 else "stages"} of this round'
    return text


def shown(value, unit=''):
    """A value as the command prints it: a number with six significant figures and its unit, a
    yes/no as `true` or `false`, an enum member or a text as it is, and the reason of a value that is
    unavailable."""
    from ..program.record import Unavailable

    if isinstance(value, bool):
        return 'true' if value else 'false'
    if isinstance(value, Unavailable):
        return f'unavailable ({value.reason})'
    if isinstance(value, int | float | Fraction | Decimal):
        return f'{common.number(value)} {unit}'.rstrip()
    return str(value)


def offered(item):
    """What an edit can give a value at a stop, or `''` for a value that no edit changes."""
    if not item.editable:
        return ''
    if item.choices is not None:
        return f'edit: {common.listed(item.choices).replace(" and ", " or ")}'
    if isinstance(item.value, bool):
        return 'edit: true or false'
    return 'edit: a number' if isinstance(item.value, int | float) else 'edit: a text'


def path_of(key):
    """The path of a record key."""
    return '.'.join((key.owner, *key.steps) if key.owner else key.steps)


# ---- the reader ---------------------------------------------------------------------------------------


def line():
    """A line that the reader types, or None at the end of the input. A line that does not come from
    a terminal is written after its prompt, as a terminal shows what is typed."""
    sys.stdout.write('> ')
    sys.stdout.flush()
    try:
        text = sys.stdin.readline()
    except KeyboardInterrupt:
        text = ''
    if not text:
        sys.stdout.write('\n')
        return None
    if not sys.stdin.isatty():
        sys.stdout.write(text if text.endswith('\n') else text + '\n')
    return text.strip()


def answered(session, args):
    """Read lines at a stop until one goes on (True) or the input ends or quits (False)."""
    from ..program.checkpoint import CheckpointError

    while (text := line()) is not None:
        word, _, rest = text.partition(' ')
        if text == 'go':
            return True
        if text == 'quit':
            return False
        if word == 'save' and rest.strip():
            try:
                session.save(rest.strip())
            except OSError as error:
                print(f'  error: {rest.strip()}: {error.strerror or error}')
                continue
            print(f'  saved; go on with: napkin play {args.model} --from {rest.strip()}')
        elif '=' in text:
            path, _, written = (piece.strip() for piece in text.partition('='))
            try:
                item, new = edited(session, path, written)
            except (CheckpointError, KeyError, ValueError) as error:
                print(f'  error: {error.args[0] if error.args else error}')
                continue
            print(f'  {titled(path, item.title)}: {shown(item.value, item.unit)} -> {shown(new, item.unit)}')
        elif text:
            print(f'  {text!r} is no command. {HELP}')
    return False


def edited(session, path, written):
    """Edit a value at the stop from the text of its new value, read by the value's type there:
    (the value at the stop as a view shows it, its new value). Raises KeyError for a path of no
    value, ValueError for a text that is no value of its type, and CheckpointError for an edit that
    the engine refuses."""
    (item,) = session.view([path]).values
    value = item.value
    if isinstance(value, bool):
        if written not in ('true', 'false'):
            raise ValueError(f'{path} is true or false, not {written!r}')
        new = written == 'true'
    elif isinstance(value, int | float):
        from ..core.units import authored_decimal

        try:
            new = authored_decimal(written)
        except ValueError:
            raise ValueError(f'{path} takes a number in its unit, not {written!r}') from None
    else:
        new = written[1:-1] if len(written) > 1 and written[0] == written[-1] == '"' else written
    session.edit(path, new)
    return item, new


# ---- the end ----------------------------------------------------------------------------------------


def ended(model, args, session, configuration, paths, entry):
    """Print the values at the start and at the horizon (`napkin run`'s table): those of `paths`, each
    as the record reads it (`unavailable` with the reason where it has none, as of an occurrence that
    never started), or every named value; then each edit that the run took. A run that failed raises
    Failed after its table."""
    from ..engine.timeline.record import key_of, unit_of

    record = session.record
    horizon = float(configuration.request.horizon)
    times = common.times_of(model, [], horizon)
    chosen = paths if paths else running.named(model, record)
    options = running.options_of(model, args.run)
    found = running.reported(model, record, configuration, chosen, times, {}, options)
    times = [(text, t) for text, t in times if t <= found.end]
    print()
    print(f'The run ends at {common.number(found.end)} h.')
    full_list = (
        'For every entry, replay the same stops and edits in Python and read session.record.near_ties().'
    )
    for row in running.lines(model, record, configuration, times, found, full_list=full_list):
        print(row)
    for edit in record.entries('edit'):
        # The trace holds an edit in canonical units: the line gives it in the value's own.
        target = edit.detail('target')
        key = key_of(model.program, target)
        unit, scale = unit_of(model.program, key)
        old, new = (edit.detail(name) for name in ('old', 'new'))
        if isinstance(old, int | float) and not isinstance(old, bool):
            old, new = old / scale, new / scale
        named = titled(target, session.title(key.owner))
        print(
            f'edit at {common.number(edit.t)} h, before {edit.part}: {named} '
            f'{shown(old, unit)} -> {shown(new, unit)}'
        )
    if found.stopped is not None:
        raise common.Failed([common.problem('run', found.stopped, entry)])
