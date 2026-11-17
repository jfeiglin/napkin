"""`napkin play`: run one run step by step; you, or a program with `--json`, pick the decisions
(docs/cli.md).

The command plays one run with a `napkin.session.Session`. `--control THING` gives the decisions of
THING to a reader (`{THING: "reader"}`), at the terminal and with `--json` alike, so that a log goes on
in either. Each decision is answered while the run is simulated, in one simulation, and the answer
goes into the log before the engine takes it. When the input ends, the run stops at the decision that
waits, and the command exits 3.

`--json` is protocol 0.0.1, one JSON object on each line:

- the command writes `{"type": "decision", "schema_version": "0.0.1", ...}` with the fields of the
  decision (docs/engine.md, "Play");
- it reads `{"pick": OUTCOME, "reason": TEXT}` lines, strict JSON (`reason` can be left out or null;
  blank lines are skipped). A line that is not such an object, or whose outcome cannot happen now,
  gives `{"type": "error", "schema_version": "0.0.1", "message": ...}`, and then the same decision again;
- a refusal of the engine gives `{"type": "error", ..., "diagnostics": [...]}`;
- the last line is `{"type": "result", "schema_version": "0.0.1", "finished": ..., "report": ...,
  "picks": [...]}`: the report is the compact document of `napkin run --json` (`common.compact`) when
  the run is finished, else null, and an unfinished run adds the `decision` that waits.
"""

import json
import sys
from pathlib import Path

from .. import SCHEMA_VERSION
from . import common

SUMMARY = 'run one run step by step; you (or a program, with --json) pick the decisions'

DESCRIPTION = """\
Run one run, stopping at each decision of a controlled actor (or one event, actor.event) for your
pick; the model decides the rest. The model is checked for that run only; `napkin compile` checks
every run. Exit 0 ok, 1 diagnostics, 3 when the input ends before the run does."""

EXAMPLES = """\
example:
  napkin play examples/reservoir --control operator"""

# The exit code when the input ends before the run does.
UNFINISHED = 3
# How the terminal shows an outcome that has no value.
STATUSES = {'unestimated': 'not estimated', 'not_applicable': 'does not apply'}


def configure(parser):
    """The description, the example and the arguments of `napkin play`: `args.variant` and `args.run`
    (None when not given); `args.control` (a list, at least one); `args.option` and `args.set` (lists,
    empty when not given); `args.edits`, `args.picks` and `args.save` (Paths, or None); `args.json`
    (True or False); and `args.target`."""
    parser.description = DESCRIPTION
    parser.epilog = EXAMPLES
    common.add_variant(parser)
    parser.add_argument('--run', metavar='NAME', help='the run to play (default: the only run)')
    parser.add_argument(
        '--control',
        action='append',
        required=True,
        metavar='THING',
        help='an actor or actor.event whose decisions you pick (repeatable)',
    )
    parser.add_argument(
        '--option',
        action='append',
        default=[],
        metavar='[GROUP=]OPTION',
        help="put this option into the run in place of its group's choice (repeatable)",
    )
    parser.add_argument(
        '--set',
        action='append',
        default=[],
        metavar='NAME=VALUE',
        help='give an input a value in its own unit (a word is text; otherwise JSON)',
    )
    parser.add_argument('--edits', type=Path, metavar='FILE', help='apply an edit document (docs/cli.md)')
    parser.add_argument(
        '--picks',
        type=Path,
        metavar='FILE',
        help='continue a play log; refused if its context differs, so a log replays exactly',
    )
    parser.add_argument(
        '--save',
        type=Path,
        metavar='FILE',
        help='write the play log: model and implementation hashes, run, options, control, edits, numerical '
        'settings, and each pick with its reason',
    )
    parser.add_argument(
        '--json',
        action='store_true',
        help='JSON lines instead of prompts (protocol 0.0.1): writes {"type":"decision",…}, reads '
        '{"pick":…,"reason":…}, ends with {"type":"result",…}. Wrap it in any server.',
    )
    common.add_target(parser)


# --- The control and the session ------------------------------------------------------------------


def control_of(things):
    """{THING: 'reader'} of the `--control` items, each once, in the order given."""
    return dict.fromkeys((thing.strip() for thing in things), 'reader')


def hinted(model, diagnostics):
    """The diagnostics of a refusal and, after a refusal of the play request (code `play`), a note that
    names the actors of the model and their choices (`napkin.model.views.actors`)."""
    from ..model.views import actors

    diagnostics = list(diagnostics)
    if not any(item.get('code') == 'play' for item in diagnostics):
        return diagnostics
    found = actors(model)
    if found:
        listed = '; '.join(
            f'{actor["name"]} ({", ".join(choice["event"] for choice in actor["choices"]) or "no choices"})'
            for actor in found
        )
        message = f'the actors that --control can name, with their choices: {listed}'
    else:
        message = 'the model has no actors: no thing sees, so no decision waits for a pick'
    return [*diagnostics, {'code': 'hint', 'severity': 'note', 'path': '', 'message': message}]


def session_of(args, model, run, control, options, edits):
    """The session of the command: a new one, or the one that continues the log of `--picks`. Raises
    Failed for a log that cannot be read or that is of another context, and the engine's ModelError for
    options or edits that it refuses."""
    from ..model import ModelError, SourceError
    from ..session import Session

    context = {'control': control, 'options': options, 'edits': edits}
    if args.picks is None:
        return Session(model, run, **context)
    try:
        return Session.load(args.picks, model, run, **context)
    except ModelError:
        raise
    except SourceError as exc:
        raise common.Failed([common.source_diagnostic(exc)]) from None
    except json.JSONDecodeError as exc:
        item = {'code': 'play_log', 'path': '', 'message': exc.msg, 'severity': 'error'}
        raise common.Failed(
            [{**item, 'file': str(args.picks), 'line': exc.lineno, 'column': exc.colno}]
        ) from None
    except OSError as exc:
        raise common.Failed([common.os_diagnostic(exc, args.picks)]) from None
    except ValueError as exc:
        # The message names the file.
        raise common.Failed(
            [{'code': 'play_log', 'path': '', 'message': str(exc), 'severity': 'error'}]
        ) from None


def saved(session, path):
    """Write the log of `session` to `path`, when there is one. Raises Failed when it cannot."""
    if path is None or session is None:
        return
    try:
        session.save(path)
    except OSError as exc:
        raise common.Failed([common.os_diagnostic(exc, path)]) from None


def available(decision):
    return [item['name'] for item in decision['outcomes'] if item['available']]


# --- The terminal ---------------------------------------------------------------------------------


def shown(value):
    """A value of what an actor sees, as the terminal shows it."""
    if isinstance(value, bool):
        return 'yes' if value else 'no'
    return common.number(value) if isinstance(value, (int, float)) else str(value)


class Terminal:
    """A reader at the terminal: each decision is printed, and `input()` reads the pick."""

    def __init__(self, stream, save=None):
        self.stream, self.save = stream, save

    def write(self, text=''):
        self.stream.write(text + '\n')
        self.stream.flush()

    def note(self, text):
        if text:
            self.write(f'note: {text}')

    def show(self, decision):
        """The time, the thing and its question, what it sees, and the outcomes that it can pick, each
        that can happen now with its number."""
        units = decision.get('units') or {}
        self.write()
        self.write(f'At {common.number(decision["t"])} h, {decision["thing"]} decides ({decision["event"]}).')
        if decision.get('text'):
            self.write(f'  {decision["text"]}')
        if decision['view']:
            self.write('  It sees:')
            for name, value in decision['view'].items():
                unit = f' {units[name]}' if units.get(name) else ''
                self.write(f'    {name} = {shown(value)}{unit}')
            for item in decision['seen']:
                self.write(f'    at {common.number(item["t"])} h: {item["text"] or item["event"]}')
        self.write('  It can pick:')
        k = 0
        for item in decision['outcomes']:
            if item['available']:
                k += 1
                mark, tail = f'{k}.', ''
            else:
                mark, tail = '-', ' (cannot happen now)'
            self.write(f'    {mark:<3} {item["name"]}: {item["text"] or ""}{tail}'.rstrip())

    def read(self, prompt):
        """A line that the reader types, or None when the input ends. A line that does not come from a
        terminal is written after its prompt, as a terminal shows what the reader types."""
        try:
            text = input(prompt)
        except (EOFError, KeyboardInterrupt):
            self.write()
            return None
        if not sys.stdin.isatty():
            self.write(text)
        return text

    def asker(self, session):
        """The session's resolver: it writes the log (`--save`), shows the decision and reads the pick
        (its number or its name) and a reason. None, when the input ends, stops the run there."""

        def ask(decision):
            saved(session, self.save)
            self.show(decision)
            names = available(decision)
            prompt = f'Pick 1-{len(names)} or a name: ' if len(names) > 1 else 'Pick 1 or its name: '
            while True:
                text = self.read(prompt)
                if text is None:
                    return None
                text = text.strip()
                if text.isdigit() and 1 <= int(text) <= len(names):
                    outcome = names[int(text) - 1]
                elif text in names:
                    outcome = text
                else:
                    self.write(f'  {text!r} is not one of them: pick {", ".join(names)}.')
                    continue
                reason = (self.read('Why (optional): ') or '').strip()
                self.write(f'  {decision["thing"]} picks {outcome}.')
                return outcome, reason or None

        return ask

    def refused(self, failed, session):
        """The diagnostics go to the standard error (`cli.main`)."""

    def done(self, session, report, model):
        count = len(session.picks)
        picks = f'{count} pick' if count == 1 else f'{count} picks'
        where = f', saved in {self.save}' if self.save is not None else ''
        if report is None:
            then = (
                'Give --save FILE to keep the picks.'
                if self.save is None
                else f'Go on with --picks {self.save}.'
            )
            self.write(
                f'The input ended before the run did, at {session.decision["event"]}: {picks}{where}. {then}'
            )
            return
        run = report['runs'][session.run]
        final = run['reporting_points']['final']
        self.write()
        self.write(f'The run {session.run} ends at {common.number(final["t"])} h.')
        outcomes = run['outcomes']
        width = max((len(item['label']) for item in outcomes.values()), default=0)
        for key, outcome in outcomes.items():
            status = final['statuses'][key]
            if status == 'estimated':
                value = f'{common.number(final["values"][key])} {outcome["unit"]}'.rstrip()
            else:
                value = STATUSES.get(status, status)
            self.write(f'  {outcome["label"]:<{width}}  {value}')
        self.write(f'{picks}{where}.')


# --- JSON lines -----------------------------------------------------------------------------------


def answer_of(text, decision):
    """(outcome, reason) of a line `{"pick": OUTCOME, "reason": TEXT}` that answers `decision`. Raises
    ValueError for a line that is not strict JSON, not such an object, or whose outcome cannot happen
    now."""
    try:
        # The strict JSON of `--set`: no NaN, no number beyond a float, no key twice.
        doc = common.strict_json(text)
    except (ValueError, RecursionError) as exc:
        raise ValueError(f'The line is not strict JSON: {exc}') from None
    if not isinstance(doc, dict) or 'pick' not in doc or set(doc) - {'pick', 'reason'}:
        raise ValueError('Give one object, {"pick": OUTCOME, "reason": TEXT}; the reason can be left out')
    pick, reason = doc['pick'], doc.get('reason')
    if not isinstance(pick, str):
        raise ValueError('"pick" is the name of an outcome')
    if reason is not None and not isinstance(reason, str):
        raise ValueError('"reason" is a text or null')
    names = available(decision)
    if pick not in names:
        raise ValueError(f'{pick} cannot be picked now: pick one of {", ".join(names)}')
    return pick, reason


class Lines:
    """A program on JSON lines (protocol 0.0.1, in the module's docstring)."""

    def __init__(self, stdin, stdout, save=None):
        self.stdin, self.stdout, self.save = stdin, stdout, save

    def line(self, kind, **fields):
        common.write_json({'type': kind, 'schema_version': SCHEMA_VERSION, **fields}, self.stdout)

    def note(self, text):
        if text:
            sys.stderr.write(f'note: {text}\n')

    def asker(self, session):
        """The session's resolver: it writes the log (`--save`) and the decision, and reads lines until
        one answers it. None, at the end of the input, stops the run there."""

        def ask(decision):
            saved(session, self.save)
            self.line('decision', **decision)
            while True:
                text = self.stdin.readline()
                if not text:
                    return None
                if not text.strip():
                    continue
                try:
                    return answer_of(text, decision)
                except ValueError as exc:
                    self.line('error', message=str(exc))
                    self.line('decision', **decision)

        return ask

    def refused(self, failed, session):
        self.line('error', message='The engine refuses the play.', diagnostics=failed.diagnostics)
        self.line('result', finished=False, report=None, picks=[] if session is None else session.picks)

    def done(self, session, report, model):
        if report is None:
            self.line('result', finished=False, report=None, picks=session.picks, decision=session.decision)
        else:
            shown = common.compact(report, admitted=model.admission_runs)
            self.line('result', finished=True, report=shown, picks=session.picks)


# --- The command ----------------------------------------------------------------------------------


def main(args):
    """Play the run: 0 when it is finished, 3 when the input ends first (the log is saved with
    `--save`). Raises UsageError and Failed (`cli.main`)."""
    from ..model import ModelError

    settings = common.parse_set(args.set)
    target = common.one_target(args.target, args.variant)
    run = common.the_run(target, args.run)
    model = common.load(target, runs=[run])
    options = common.parse_options(model, args.option)
    edits = common.read_edits(model, args.edits, settings)
    control = control_of(args.control)
    common.use_store()
    face = Lines(sys.stdin, sys.stdout, args.save) if args.json else Terminal(sys.stdout, args.save)
    face.note(common.scope_note(model))
    session = report = None
    try:
        try:
            session = session_of(args, model, run, control, options, edits)
            session.resolver = face.asker(session)
            if session.advance() is None:
                report = session.result()
                if not report['admissible']:
                    raise common.Failed(report['diagnostics'])
        except ModelError as exc:
            raise common.Failed(hinted(model, exc.diagnostics)) from None
    except common.Failed as exc:
        face.refused(exc, session)
        raise
    finally:
        saved(session, args.save)
    face.done(session, report, model)
    return 0 if report is not None else UNFINISHED
