"""What the migration scripts read of a model in the language of now, with the compiler of now.

It runs with the checkout's own `napkin` (no PYTHONPATH), never beside the old compiler, which has
the same package name: `translate.py` calls it in a process of its own, and `check.py` imports it.

- `compiled(entry)`: the compile of an entry file (`napkin.model.compile.load_scenario`), as the
  problems that refuse it, each with its code, file and line, and the setup's reports, among them
  the warnings of the evidence rule (`no_record`, change 16).
- `facts(entry, proven)`: what `check.py` compares of a model: each number with its unit as a value
  in base units and a dimension, each text, the kind and dimension of each declared name, the ends
  of each flow, the events, and for each path in `proven` (a value that the old compiler proved
  cumulative) whether `napkin/program/proofs.py` proves that it never falls under each run.

    /home/user/napkin/.venv/bin/python newmodel.py --compile ENTRY.scn...    # JSON on stdout
"""

from __future__ import annotations

import collections
import dataclasses
import json
import sys
from fractions import Fraction
from pathlib import Path

from napkin.model import semantic as s
from napkin.model.compile import load_scenario
from napkin.model.ir import ModelError
from napkin.model.language import nodes as n
from napkin.model.language.problems import LanguageError
from napkin.program.proofs import Proofs
from napkin.program.record import Key


def compiled(entry):
    """{'ok', 'problems', 'reports'} of the compile of an entry file: the problems as dicts with their
    code, file, line and message."""

    def plain(problem):
        return {'code': problem.code, 'file': problem.file, 'line': problem.line, 'message': problem.message}

    try:
        found = load_scenario(entry)
    except LanguageError as error:
        return {'ok': False, 'problems': [plain(item) for item in error.problems], 'reports': []}
    except ModelError as error:
        # The library's refusals (its records, its units) come as diagnostics.
        return {'ok': False, 'problems': [library_problem(item) for item in error.diagnostics], 'reports': []}
    except FileNotFoundError as error:
        return {
            'ok': False,
            'problems': [{'code': 'missing', 'file': str(entry), 'line': 0, 'message': str(error)}],
            'reports': [],
        }
    return {'ok': True, 'problems': [], 'reports': [plain(item) for item in found.reports]}


def library_problem(item):
    """A diagnostic of the library (`napkin.model.ir.diagnostic`) as a problem of the compile."""
    return {
        'code': f'library.{item.get("code", "")}',
        'file': item.get('path', ''),
        'line': 0,
        'message': item['message'],
    }


# ---- the facts of a model -------------------------------------------------------------------------------


def dims_text(dimension):
    """A dimension as the check compares it (the same text as `oldmodel._unit`)."""
    return json.dumps(sorted([str(k), float(v)] for k, v in dimension))


def number_key(value, scale, dimension):
    """A number as the check compares it: its value in base units with 12 significant digits and its
    dimension, so that `12 h` and `0.5 day` are one number; a zero has no dimension, since a bare zero
    takes the unit of its place (`oldmodel.number_key`)."""
    base = float(Fraction(str(value)) * Fraction(scale))
    return f'{base:.12g}', dims_text(() if base == 0 else dimension)


def normal_text(text):
    """A text as the check compares it: its words with one space between them."""
    return ' '.join(str(text).split())


class Collector:
    """The numbers and the texts of a declared model, from its typed parts: a number is a `Const` of
    a number type or a parameter of a distribution, and a text is a text field, a `Const` of text, a
    record's explanation, a note's text, an option's or a group's name."""

    def __init__(self, units):
        self.units = units
        self.numbers = collections.Counter()
        self.texts = collections.Counter()
        self.seen = set()

    def number(self, value, num):
        found = self.units.of(num.unit) if num.unit else ((), 1)
        if found is None:
            return
        dimension, scale = found
        self.numbers[number_key(value, scale, dimension)] += 1

    def text(self, value):
        if isinstance(value, str) and value:
            self.texts[normal_text(value)] += 1

    def scenario_lines(self, entry):
        """The texts and the numbers of the scenario line of each file of the model, as each file
        writes it: the declared model holds one line, merged from the main file's and the variant's."""
        from napkin.model.language.modules import files
        from napkin.model.language.parse import parse

        for _, text in files(Path(entry)).files:
            for item in parse(text).items:
                if not isinstance(item, n.Scenario):
                    continue
                for key in ('title', 'summary', 'scope', 'library'):
                    self.text(getattr(item, key, None))
                for node in (item.horizon, item.resolution, *(item.timescales or ())):
                    if isinstance(node, n.Quantity):
                        spelled = ''.join(op + name for op, name in node.unit)
                        found = self.units.of(spelled)
                        if found is not None:
                            self.numbers[number_key(node.value, found[1], found[0])] += 1
                    elif isinstance(node, n.Number):
                        self.numbers[number_key(node.value, 1, ())] += 1

    def walk(self, node, skip=('tree', 'units', 'scenario')):
        if isinstance(node, (list, tuple)):
            for item in node:
                self.walk(item)
            return
        if not dataclasses.is_dataclass(node) or isinstance(node, type):
            return
        if id(node) in self.seen:
            return
        self.seen.add(id(node))
        if isinstance(node, s.Const):
            if (
                isinstance(node.type, s.Num)
                and isinstance(node.value, (int, float, Fraction))
                and not isinstance(node.value, bool)
            ):
                self.number(node.value, node.type)
            elif node.type == s.TEXT:
                self.text(node.value)
            return
        if isinstance(node, s.Distribution):
            of = node.type.of
            for param in node.params:
                self.number(param, of if isinstance(of, s.Num) else s.PLAIN)
            return
        if isinstance(node, (n.Text, s.Scenario)):
            if isinstance(node, n.Text):
                self.text(node.value)
            return
        if isinstance(node, n.Number):
            # A number of a note, which has no unit.
            self.numbers[number_key(node.value, 1, ())] += 1
            return
        for item in dataclasses.fields(node):
            if item.name in skip:
                continue
            value = getattr(node, item.name)
            if isinstance(value, str):
                if item.name in ('text', 'title', 'summary', 'scope'):
                    self.text(value)
                continue
            self.walk(value)


def kinds(declared):
    """{path: (kind, dimension)} of each declared value of a model, with the kind of a stored number
    by its use (`stock`: a flow, a route or a move joins it and something takes from it; `tally`: one
    joins it and nothing takes from it; `state`: none joins it), and the other parts by their class."""
    ends, drained = set(), set()

    def end(read):
        return read.part if isinstance(read, s.Read) and read.part else None

    def flows(parts):
        for part in parts:
            if isinstance(part, s.DeclaredLegs):
                yield from part.legs
            elif isinstance(part, s.DeclaredFlow):
                yield part

    def statements(event):
        for step in event.steps:
            if isinstance(step, s.DeclaredStage):
                yield from s.statements_of(step.body)

    for entity in declared.entities:
        events = [part for part in entity.parts if isinstance(part, s.DeclaredEvent)]
        every = [*entity.parts, *(local for event in events for local in event.locals)]
        for flow in flows(every):
            source, sink = end(flow.source), end(flow.sink)
            ends.update(item for item in (source, sink) if item)
            if source:
                drained.add(source)
            if isinstance(flow, s.DeclaredRoute) and sink:
                drained.add(sink)
        for event in events:
            for statement in statements(event):
                if isinstance(statement, s.DeclaredMove):
                    for read in (statement.source, statement.destination):
                        if end(read):
                            ends.add(end(read))
                    if end(statement.source):
                        drained.add(end(statement.source))
                elif (
                    isinstance(statement, s.DeclaredAssign) and statement.op != '+=' and end(statement.target)
                ):
                    drained.add(end(statement.target))
    found = {}

    def dimension(type_):
        if isinstance(type_, s.Num):
            return dims_text(type_.dimension)
        if isinstance(type_, s.Dist) and isinstance(type_.of, s.Num):
            return dims_text(type_.of.dimension)
        return str(type_)

    def value(part):
        kind = part.kind
        if kind == s.STATE and isinstance(part.type, s.Num) and part.path in ends:
            kind = 'stock' if part.path in drained else 'tally'
        elif kind == s.STATE and part.readonly:
            kind = 'fixed'
        elif kind == s.STATE:
            kind = (
                'state'
                if isinstance(part.type, s.Num)
                else 'state.'
                + (
                    'bool'
                    if part.type == s.BOOL
                    else 'enum'
                    if isinstance(part.type, s.EnumOf)
                    else str(part.type)
                )
            )
        elif kind == s.INPUT:
            kind = 'input.' + (
                'bool'
                if part.type == s.BOOL
                else 'text'
                if part.type == s.TEXT
                else 'enum'
                if isinstance(part.type, s.EnumOf)
                else 'number'
            )
        found[part.path] = (kind, dimension(part.type))

    for entity in declared.entities:
        found[entity.path] = ('template' if isinstance(entity, s.DeclaredTemplate) else 'entity', '')
        for part in entity.parts:
            if isinstance(part, s.DeclaredValue):
                value(part)
            elif isinstance(part, (s.DeclaredFlow, s.DeclaredLegs)):
                found[part.path] = ('flow', '')
            elif isinstance(part, s.DeclaredEvent):
                found[part.path] = ('event', '')
    for part in declared.root:
        value(part)
    for member in declared.members:
        found[member.path] = ('member of ' + member.template, '')
    return found


def flow_ends(declared):
    """{path of a flow: its legs (one for a flow of one pair) as [source, sink], sorted}, each end the
    path of a store, or SOURCE or SINK."""

    def end(read):
        if isinstance(read, s.Read):
            return read.part or '?'
        return str(read)

    found = {}
    for entity in declared.entities:
        for part in entity.parts:
            if isinstance(part, s.DeclaredLegs):
                found[part.path] = sorted([end(leg.source), end(leg.sink)] for leg in part.legs)
            elif isinstance(part, s.DeclaredFlow):
                found[part.path] = [[end(part.source), end(part.sink)]]
    return found


def keys_of(path, compiled_):
    """The record keys of a reported path, member by member: `name` at the top level, `thing.x` of an
    entity, `Template.instances.x` of each member of a template."""
    head, _, name = path.rpartition('.')
    if not head:
        return [Key('', (name,))]
    if head.endswith('.instances'):
        template = compiled_.program.template(head.removesuffix('.instances'))
        return [Key(member.id, (name,)) for member in template.members] if template is not None else []
    return [Key(head, (name,))]


def proofs(compiled_, paths, runs):
    """{path: {run: [holds, reason]}} for each path, under the default run ('') and each named run that
    `runs` lists."""
    out = {path: {} for path in paths}
    for run in ['', *runs]:
        try:
            configuration = compiled_.configuration if not run else compiled_.configure(run)
        except LanguageError as error:
            for path in paths:
                out[path][run] = [False, f'the run does not configure: {error.problems[0].message}']
            continue
        proving = Proofs(compiled_.program, configuration)
        for path in paths:
            keys = keys_of(path, compiled_)
            if not keys:
                out[path][run] = [False, f'{path} names no value of the program']
                continue
            reasons = []
            for key in keys:
                try:
                    proof = proving.never_falls(key)
                except (KeyError, AttributeError, ValueError) as error:
                    out[path][run] = [
                        False,
                        f'{key.owner}.{".".join(key.steps)}: {type(error).__name__} {error}',
                    ]
                    break
                if not proof.holds:
                    out[path][run] = [False, f'{key.owner or "the top level"}: {proof.reason}']
                    break
                reasons.append(proof.reason)
            else:
                out[path][run] = [True, '; '.join(dict.fromkeys(reasons))]
    return out


def facts(entry, proven=(), runs=()):
    """What `check.py` compares of a model in the language of now (see the module), or the problems
    that refuse its compile."""
    try:
        found = load_scenario(entry)
    except LanguageError as error:
        return {'problems': [[item.code, item.file, item.line, item.message] for item in error.problems]}
    except ModelError as error:
        return {'problems': [list(library_problem(item).values()) for item in error.diagnostics]}
    declared = found.declared
    collector = Collector(declared.units)
    collector.walk(declared)
    collector.scenario_lines(entry)
    for group in dict.fromkeys(option.group for option in declared.options):
        collector.text(group)
    for option in declared.options:
        collector.text(option.name)
    for run in declared.runs:
        for name in run.options:
            collector.text(name)
    return {
        'problems': [],
        'numbers': [[*key, total] for key, total in collector.numbers.items()],
        'texts': dict(collector.texts),
        'kinds': {path: list(value) for path, value in kinds(declared).items()},
        'flows': flow_ends(declared),
        'runs': [run.name for run in declared.runs],
        'warnings': [[item.code, item.file, item.line, item.message] for item in found.reports],
        'proofs': proofs(
            found, list(proven), [run.name for run in declared.runs if run.name in runs or not runs]
        ),
    }


def main(argv):
    if argv[:1] == ['--compile']:
        json.dump({path: compiled(Path(path)) for path in argv[1:]}, sys.stdout)
        return 0
    print(__doc__)
    return 2


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
