"""The text front end and builder author the same typed program, or both refuse it."""

from collections.abc import Callable
from dataclasses import dataclass
from fractions import Fraction
from hashlib import sha256
from random import Random

from napkin.model.compile import compile_text
from napkin.model.language.problems import LanguageError
from napkin.program import build as b
from napkin.program.canonical import program_bytes
from napkin.program.check import ProgramError
from napkin.program.parts import Program

UNITS = {'L': {'volume': 1}, 'mL': ({'volume': 1}, Fraction(1, 1000)), 'h': {'time': 1}}
HEADER = 'scenario "Authoring parity"\n    horizon 1 h\n'


@dataclass
class Example:
    name: str
    accepted: bool
    body: str
    build: Callable[[], Program]
    tables: dict | None = None

    @property
    def source(self):
        return HEADER + self.body


@dataclass(frozen=True)
class Names:
    owner: str
    template: str
    param: str
    open: str
    closed: str
    other: str
    amount: int


def _names(seed):
    if seed == 0:
        return Names('yard', 'Valve', 'amount', 'OPEN', 'CLOSED', 'OTHER', 8)
    rng = Random(seed)
    suffix = str(rng.randrange(1, 10_000))
    return Names(
        'yard' + suffix,
        'Valve' + suffix,
        'amount' + suffix,
        'OPEN' + suffix,
        'CLOSED' + suffix,
        'OTHER' + suffix,
        rng.randint(1, 50),
    )


def _start(names, unit, shadow, stage):
    name, param, amount = names.owner, names.param, names.amount
    arg = 'true' if unit == 'bool' else f'{amount} {unit}'
    prefix = ''
    tables = None
    if shadow == 'entity':
        prefix = f'{param}:\n    weight: h = 1 h\n'
    elif shadow == 'table':
        prefix = f'{names.template}:\n    weight: h = 1 h\n{param}: {names.template} from "rows.csv"\n'
        tables = {'rows.csv': 'id,weight\na,2\n'}
    body = (
        prefix
        + f"""{name}:
    received: L = 0 L
    deliver = event({param}: L):
        after 0 h:
            this.received = {param}
"""
    )
    if stage:
        body += f'    launch = event():\n        after 0 h:\n            this.deliver.start({arg})\n{name}.launch.start()\n'
    else:
        body += f'{name}.deliver.start({arg})\n'

    def build():
        builder = b.Builder(UNITS)
        if shadow == 'entity':
            builder.entity(param, b.value('weight', 'h', 1))
        elif shadow == 'table':
            template = builder.template(names.template, b.value('weight', 'h', 1))
            builder.table(param, template, [{'id': 'a', 'weight': 2}])
        parts = [
            b.value('received', 'L', 0),
            b.event(
                'deliver',
                b.param(param, 'L'),
                b.after(b.q(0, 'h'), b.assign(b.this.received, getattr(b.local, param))),
            ),
        ]
        argument = True if unit == 'bool' else b.q(amount, unit)
        if stage:
            parts.append(b.event('launch', b.after(b.q(0, 'h'), b.start(b.this.deliver, argument))))
        entity = builder.entity(name, *parts)
        builder.setup(b.start(entity.launch) if stage else b.start(entity.deliver, argument))
        return builder.finish()

    return Example(
        f'start.{unit}.{shadow}.{"stage" if stage else "setup"}', unit in ('L', 'mL'), body, build, tables
    )


def _occurrence(names, field, local):
    decl = f'{field}: L' if not local else ''
    local_line = f'        {field}: L = {names.amount} L\n' if local else ''
    body = f'{names.owner}:\n    deliver = event({decl}):\n{local_line}        after 0 h\n'

    def build():
        builder = b.Builder(UNITS)
        part = b.value(field, 'L', names.amount) if local else b.param(field, 'L')
        builder.entity(names.owner, b.event('deliver', part, b.after(b.q(0, 'h'))))
        return builder.finish()

    return Example(
        f'occurrence.{"local" if local else "parameter"}.{field}', field == names.param, body, build
    )


def _enum(names, *, collision, override):
    # The extra template has the name of the first enum value only in the collision transform.
    extra = names.open if collision else 'Fixture'
    decl = f'enum[{names.open}, {names.closed}]'
    body = f'{extra}:\n    weight: L = 1 L\nspare: {extra}\n'
    if override:
        body += (
            f'{names.template}:\n    state: formula({decl}) = formula({names.closed})\n'
            f'{names.owner}: {names.template}\n    state = formula({names.open})\n'
        )
    else:
        body += f'{names.owner}:\n    state: {decl} = {names.open}\n'

    def build():
        builder = b.Builder(UNITS)
        kind = builder.enum(decl, names.open, names.closed)
        extra_template = builder.template(extra, b.value('weight', 'L', 1))
        builder.member(extra_template, 'spare')
        opened = getattr(kind, names.open)
        if override:
            template = builder.template(
                names.template, b.value('state', kind, b.formula(getattr(kind, names.closed)))
            )
            builder.member(template, names.owner, state=b.formula(opened))
        else:
            builder.entity(names.owner, b.value('state', kind, opened))
        return builder.finish()

    return Example(
        f'enum.{"override" if override else "value"}.{"shadow" if collision else "clear"}', True, body, build
    )


def _distribution(names, form, place):
    enums = form.startswith('enum')
    number = names.amount
    first, second, other = names.open, names.closed, names.other
    group = f'enum[{first}, {second}]'
    target = group if enums else 'L'
    foreign = f'enum[{first}, {other}]'
    valid = form in ('unit-ok', 'enum-ok')
    template = names.template if place == 'member' else names.owner
    extra = f'    other: {foreign} = {other}\n' if form == 'enum-foreign' else ''
    if enums:
        baseline = f'categorical({first}: 1, {second}: {number})'
        literal = f'categorical({first}: 1, {second if valid else other}: {number})'
    else:
        unit = 'L' if valid else 'h'
        baseline = f'uniform({number} L, {number + 2} L)'
        literal = f'uniform({number} {unit}, {number + 2} {unit})'
    body = f'{template}:\n{extra}    odds: distribution({target}) = {literal if place == "initial" else baseline}\n'
    if place == 'member':
        body += f'{names.owner}: {template}\n    odds = {literal}\n'
    elif place == 'stage':
        body += f'    change = event():\n        after 0 h:\n            this.odds = {literal}\n{names.owner}.change.start()\n'

    def build():
        builder = b.Builder(UNITS)
        parts = []
        if enums:
            kind = builder.enum(group, first, second)
            actual = kind
            if form == 'enum-foreign':
                actual = builder.enum(foreign, first, other)
                parts.append(b.value('other', actual, getattr(actual, other)))
            initial = b.categorical(kind, **{first: 1, second: number})
            written = b.categorical(actual, **{first: 1, second if valid else other: number})
        else:
            kind = 'L'
            initial = b.uniform(number, number + 2, 'L')
            written = b.uniform(number, number + 2, 'L' if valid else 'h')
        parts.append(b.value('odds', b.dist_of(kind), written if place == 'initial' else initial))
        if place == 'member':
            template_handle = builder.template(template, *parts)
            builder.member(template_handle, names.owner, odds=written)
        elif place == 'stage':
            entity = builder.entity(
                template, *parts, b.event('change', b.after(b.q(0, 'h'), b.assign(b.this.odds, written)))
            )
            builder.setup(b.start(entity.change))
        else:
            builder.entity(template, *parts)
        return builder.finish()

    return Example(f'distribution.{form}.{place}', valid, body, build)


def authoring_cases(seed):
    names = _names(seed)
    for unit in ('L', 'mL', 'bool', 'h'):
        for shadow in (
            ('plain', 'entity', 'table') if seed == 0 else (('plain', 'entity', 'table')[seed % 3],)
        ):
            for stage in (False, True) if not seed else (bool(seed % 2),):
                yield _start(names, unit, shadow, stage)
    for field in ('started', 'done', 'active', names.param):
        for local in (False, True):
            yield _occurrence(names, field, local)
    for collision in (False, True):
        for override in (False, True):
            yield _enum(names, collision=collision, override=override)
    for form in ('unit-ok', 'unit-wrong', 'enum-ok', 'enum-outcome', 'enum-foreign'):
        for place in (
            ('initial', 'member', 'stage') if seed == 0 else (('initial', 'member', 'stage')[seed % 3],)
        ):
            yield _distribution(names, form, place)


def check_authoring_parity(seed):
    failures = {}
    for case in authoring_cases(seed):
        statuses, programs, errors = {}, {}, {}
        for side, author in (
            ('text', lambda case=case: compile_text(case.source, UNITS, tables=case.tables).program),
            ('builder', case.build),
        ):
            try:
                programs[side] = author()
                statuses[side] = 'accepted'
            except (LanguageError, ProgramError) as error:
                statuses[side] = 'refused'
                errors[side] = str(error)
            except Exception as error:
                statuses[side] = 'exception'
                errors[side] = f'{type(error).__name__}: {error}'
        expected = 'accepted' if case.accepted else 'refused'
        differences = {side: (expected, status) for side, status in statuses.items() if status != expected}
        if statuses == {'text': 'accepted', 'builder': 'accepted'}:
            source, built = (program_bytes(programs[side]) for side in ('text', 'builder'))
            if source != built:
                differences['canonical program'] = (sha256(source).hexdigest(), sha256(built).hexdigest())
        if differences:
            failures[case.name] = {
                'differences': differences,
                'statuses': statuses,
                'diagnostics': errors,
                'source': case.source,
                'tables': case.tables,
                'builder': (
                    f'from tests.engine.authoring_parity_cases import authoring_cases; '
                    f'next(c for c in authoring_cases({seed}) if c.name == {case.name!r}).build()'
                ),
            }
    assert not failures, (seed, failures)
