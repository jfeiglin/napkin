"""The runs of a model: the configuration of one run, under an edit document (D9, R-A5-03).

A model declares its options (`options "Group":`, each `"Option":` with the inputs that it sets: only
an input, by its full path, R-A5-04) and its named runs (`runs:`, each a choice of options, at most
one of each group). They are part of its declared model (`semantic.DeclaredOption`, `DeclaredRun`).
One run is one configuration of the model's one program (`napkin.program.config.Configuration`):
the values of its inputs beside its mode, its seed and its request. A variant or a `change` changes
the model, so it has a program of its own; an option or an edit only configures a run of it.

**Precedence.** The first of these that gives an input its value wins (R-A5-03, the spec's "How
templates compose into a run"):

1. an edit of the run in the edit document (`runs`);
2. an edit of one of the run's options (`options`);
3. an edit of every run (`set`);
4. an option of the run;
5. the program: a `change`, then a member's own line, then the template.

At each of the first four, a line of one member wins over a line of every member of its template
(`Pump.instances.rate`). Two options of one run that set one input are an error, and so are two edits
at the level of the options that meet in one run, even when they are equal: the order of the files or
of the document never decides.

**The edit document** (`napkin/schema/edits.schema.json`) is one transaction: it is checked whole,
in every run of the model, before any run takes its values: its shape, the revision of the model
that it was made for (`model_hash`), the options and the runs that it names, and each edit's input
and value. An edit of an option that no run names changes no run; it reaches a combination of
options that names that option (`configuration(..., options=...)`), which is checked when it is
asked for.

**Values** follow the declared type (D2). An option writes a constant of the input's type with its
unit (`semantic.Resolver.constant`), and an edit gives a JSON number in the input's own unit, true or
false for a yes/no, or a text: a number with its unit (`"3 days"`), a member of the input's enum, a
text for a text input, or a distribution written as in a model (`"pert(48 h, 96 h, 200 h)"`). Each
value is in the input's range when its bounds are numbers; the engine checks the others at setup. A
configuration holds each number in the unit of its input, so two equal values give one key of a
stored run.
"""

from __future__ import annotations

import math
from dataclasses import replace
from decimal import Decimal
from fractions import Fraction

from ..program.config import InputValue, Quantity
from ..program.refs import EnumValue
from . import semantic as s
from .language import nodes as n
from .language.parse import parse_expression
from .language.problems import LanguageError, Problem, SyntaxProblem
from .load import schema_errors

# The levels of an edit document, from the widest: every run, the runs of one option, one run.
LEVELS = ('set', 'options', 'runs')


def options_of(declared, run=None, options=None):
    """The options of a run, or of a combination: the named run's options (none without a run), with
    each option of `options` in place of the run's option of its group. Raises `LanguageError` for an
    unknown run or option, and for options that cannot make one run (`semantic.choice_problem`)."""
    problems = []
    if run is not None and declared.run(run) is None:
        names = [item.name for item in declared.runs]
        problems.append(Problem('run', f'{run!r} is no run of the model' + s.close(run, names)))
    if options is not None and (
        isinstance(options, str) or not all(isinstance(item, str) for item in options)
    ):
        problems.append(Problem('run', 'a combination names its options as a list of names'))
        options = ()
    names = [item.name for item in declared.options]
    for name in options or ():
        if declared.option(name) is None:
            problems.append(Problem('run', f'{name!r} is no option of the model' + s.close(name, names)))
    if problems:
        raise LanguageError(problems)
    chosen = [declared.option(name) for name in (declared.run(run).options if run is not None else ())]
    for name in options or ():
        option = declared.option(name)
        if option in chosen:
            continue
        # The option takes the place of the run's option of its group; two options of one group in
        # `options` stay two, which `choice_problem` refuses.
        place = next((k for k, item in enumerate(chosen) if item.group == option.group), None)
        if place is not None and chosen[place].name not in options:
            chosen[place] = option
        else:
            chosen.append(option)
    problem = s.choice_problem(chosen)
    if problem is not None:
        raise LanguageError([Problem('run', f'{" + ".join(item.name for item in chosen)}: {problem}')])
    return tuple(item.name for item in chosen)


def configuration(declared, base, run=None, edits=None, options=None, model_hash=None, file=''):
    """The configuration of a run of a declared model: `base` (the model's default run, with its
    request and its numerics) with the values that the run's options and the edit document `edits`
    give its inputs (see the module). `run` names a run of the model, or None for the run of the
    defaults; `options` makes a combination (`options_of`). The document is checked whole first
    (`check`), against `model_hash` when it is given. Raises `LanguageError`."""
    chosen = options_of(declared, run, options)
    found = check(declared, edits, model_hash, file)
    if not found and edits:
        found = _meetings(declared, edits, {run or '': chosen}, file)
    if found:
        raise LanguageError(found, file)
    table = _Targets(declared)
    values = {}
    layers = [
        ('option', [setting for name in chosen for setting in declared.option(name).settings]),
        ('set', _edited(declared, (edits or {}).get('set'), table)),
        (
            'options',
            [
                item
                for name in chosen
                for item in _edited(declared, _level(edits, 'options').get(name), table)
            ],
        ),
        ('runs', _edited(declared, _level(edits, 'runs').get(run), table) if run is not None else []),
    ]
    for _, settings in layers:
        # A line of every member of a template first, so that a line of one member wins over it.
        for setting in sorted(settings, key=lambda item: item.instances is None):
            given = _given(setting)
            for member in table.members(setting):
                values[(member, setting.name)] = given
    inputs = tuple(InputValue(member, name, values[(member, name)]) for member, name in sorted(values))
    return replace(base, inputs=inputs)


def check(declared, edits, model_hash=None, file=''):
    """The problems of an edit document (None for none) in every run of the model, each a `Problem`
    whose message starts with the place in the document (`runs/fast/tank.rate`): its shape, the
    model's revision, the options and runs that it names, each input and value, and edits of the
    options of one run that meet."""
    if edits is None:
        return ()
    if not isinstance(edits, dict):
        return (Problem('schema', 'an edit document is an object of edits', 0, 0, file),)
    found = [
        Problem('schema', f'{item["path"] or "the document"}: {item["message"]}', 0, 0, file)
        for item in schema_errors(edits, 'edits')
    ]
    if found:
        return tuple(found)
    if model_hash is not None and edits['model_hash'] != model_hash:
        found.append(Problem('model_hash', 'the edits are for another revision of the model', 0, 0, file))
    for level, names, what in (
        ('options', [item.name for item in declared.options], 'option'),
        ('runs', [item.name for item in declared.runs], 'run'),
    ):
        for name in edits.get(level, {}):
            if name not in names:
                found.append(
                    Problem(
                        'reference',
                        f'{level}/{name}: is no {what} of the model' + s.close(name, names),
                        0,
                        0,
                        file,
                    )
                )
    table = _Targets(declared)
    for place, values in _places(edits):
        for path, value in values.items():
            try:
                _edit(declared, path, value, table)
            except s.Refused as refused:
                found.append(Problem(refused.code, f'{place}/{path}: {refused.message}', 0, 0, file))
    if found:
        return tuple(found)
    runs = {item.name: options_of(declared, item.name) for item in declared.runs}
    return tuple(_meetings(declared, edits, runs, file))


def _level(edits, level):
    return (edits or {}).get(level) or {}


def _places(edits):
    """(the place in the document, its edits) of each level of an edit document."""
    if edits.get('set'):
        yield 'set', edits['set']
    for level in ('options', 'runs'):
        for name, values in (edits.get(level) or {}).items():
            yield f'{level}/{name}', values


def _meetings(declared, edits, runs, file):
    """Two edits of the options of one run that set one input (R-A5-03), in each of `runs` (its
    name: its options)."""
    found, edited = [], _level(edits, 'options')
    for run, chosen in runs.items():
        seen = {}
        for name in chosen:
            for path in edited.get(name, {}):
                first = seen.setdefault(path, name)
                if first != name:
                    found.append(
                        Problem(
                            'meeting',
                            f'options/{name}/{path}: the run {run or "of the defaults"} takes the options '
                            f'{first} and {name}, whose edits both set {path}',
                            0,
                            0,
                            file,
                        )
                    )
    return found


class _Targets:
    """The members of the model by id and by template, for the paths of edits and the lines of every
    member of a template."""

    def __init__(self, declared):
        self.template = {entity.path: entity.path for entity in declared.entities}
        self.of = {}
        for member in declared.members:
            self.template[member.path] = member.template
            self.of.setdefault(member.template, []).append(member.path)
        self.templates = {
            entity.path for entity in declared.entities if isinstance(entity, s.DeclaredTemplate)
        }

    def members(self, setting):
        """The ids of the members that a setting reaches."""
        if setting.instances is not None:
            return self.of.get(setting.instances, ())
        return (setting.member,)


def _edited(declared, values, table):
    """The edits of one level as settings (`semantic.DeclaredSetting`), checked already."""
    return [_edit(declared, path, value, table) for path, value in (values or {}).items()]


def _edit(declared, path, value, table):
    """One edit as a setting: the input that its path names and the constant that it gives, or
    `semantic.Refused`."""
    *owner, name = path.split('.')
    member = instances = None
    if len(owner) == 2 and owner[1] == 'instances' and owner[0] in table.templates:
        key, instances = f'{owner[0]}.{name}', owner[0]
    elif not owner:
        key, member = name, ''
    else:
        member = '.'.join(owner)
        if member not in table.template or member in table.templates:
            raise s.Refused('input', f'{member} names no member of the model')
        key = f'{table.template[member]}.{name}'
    found = declared.part(key)
    if not isinstance(found, s.DeclaredValue) or (not owner and found not in declared.root):
        raise s.Refused('input', f'{path} names no input of the model')
    if found.kind != s.INPUT:
        raise s.Refused('input', f'{path} is a {found.kind} value: an edit sets an input')
    return s.DeclaredSetting(path, name, _value(declared, found, value), member, instances)


def _value(declared, found, value):
    """The constant that an edit's JSON value gives an input of the type of `found` (D2)."""
    if found.type == s.BOOL:
        if not isinstance(value, bool):
            raise s.Refused('bool', f'{found.name} is a yes/no: it takes true or false, not {value!r}')
        return s.Const(value, s.BOOL)
    if isinstance(value, bool):
        raise s.Refused('value', f'{found.name} is {found.type}: it takes no true or false')
    if isinstance(value, (int, float, Decimal)):
        if not math.isfinite(value) or not isinstance(found.type, s.Num):
            raise s.Refused(
                'value', f'{found.name} is {found.type}: a finite number is in its unit, not {value!r}'
            )
        if isinstance(value, Decimal):
            exact = Fraction(value)
            number = int(exact) if exact.denominator == 1 else float(exact)
            node = n.Number(abs(number), exact=abs(exact))
        else:
            node = n.Number(abs(value))
        return s.constant(found, n.Unary('-', node) if value < 0 else node, declared.units)
    if found.type == s.TEXT:
        return s.Const(value, s.TEXT)
    if isinstance(found.type, s.EnumOf):
        if value not in found.type.members:
            raise s.Refused('value', f'{found.name} is {found.type}: {value!r} is no member of it')
        return s.Const(value, found.type)
    try:
        node = parse_expression(value)
    except SyntaxProblem as problem:
        raise s.Refused('value', f'{value!r} is no value: {problem.problem.message}') from None
    return s.constant(found, node, declared.units)


def _given(setting):
    """The value of a configuration for a setting's constant: a number in the unit of its input, a
    yes/no, a text, a member of an enum, or a distribution."""
    from .lowering import distribution

    value = setting.value
    if isinstance(value, s.Distribution):
        return distribution(value)
    if isinstance(value.type, s.EnumOf):
        return EnumValue(str(value.type), value.value)
    if isinstance(value.type, s.Num):
        # The constant is in the input's own unit already (`semantic.Resolver.constant`).
        return Quantity(value.value, value.type.unit)
    return value.value
