"""Synthetic model files for tests: small analytic scenarios and libraries, no catalogue data.

A fixture here is the text of a model file (docs/language.md). The helpers write its lines and
own their indentation: a helper of a member gives its declaration and the lines under it, `entity`
puts members under their entity and `document` writes the whole file, with the start in its entity. `edit` changes a text as a
test's edit. `compiled` builds the model of a text with the front end (docs/python-api.md),
and `run` resolves one run with `model.resolve` and gives it to the engine's runtime.

Every line that needs records cites `@fixture`, the identity record that `document` writes, unless a
test gives it others.
"""

from __future__ import annotations

import copy
import hashlib
import json
import re

import pytest

from napkin.engine.runtime import simulate
from napkin.model import ModelError
from napkin.model.ir import thaw
from napkin.model.language import front
from napkin.model.library import prelude_units
from napkin.model.semantic import path_text
from napkin.schema import FOLDER as SCHEMAS

# The library's own format version, as its schema states it.
LIBRARY_VERSION = json.loads((SCHEMAS / 'library.schema.json').read_text(encoding='utf-8'))['properties'][
    'schema_version'
]['const']

# The record that every line of a fixture cites, and its line at the end of the file.
BASIS = '@fixture'
FIXTURE_RECORD = 'record fixture: identity "Analytic contract fixture."'

# The units of the test library. The prelude's units are its own, as every model's library has them
# (`napkin/std/units.json`).
PRELUDE = prelude_units()
UNITS = {
    'fraction': PRELUDE['fraction'],
    'h': PRELUDE['h'],
    'days': PRELUDE['days'],
    'per_h': {'dimensions': {'time': -1}, 'scale': 1},
    'people': PRELUDE['people'],
    'episodes': {'dimensions': {'episodes': 1}, 'scale': 1},
    'people/h': {'dimensions': {'people': 1, 'time': -1}, 'scale': 1},
    'people/day': {'dimensions': {'people': 1, 'time': -1}, 'scale': 1 / 24},
    'USD2025': {'dimensions': {'USD2025': 1}, 'scale': 1},
    'USD2024': {'dimensions': {'USD2024': 1}, 'scale': 1},
    'USD2025/h': {'dimensions': {'USD2025': 1, 'time': -1}, 'scale': 1},
}


def library():
    return {
        'schema_version': LIBRARY_VERSION,
        'id': 'test',
        'title': 'Test library',
        'sources': [],
        'claims': [],
        'assumptions': [],
        'units': copy.deepcopy(UNITS),
    }


def toml(settings):
    """The TOML text of brief settings or of a stylesheet: a key for each list of names, `{key:
    [name, …]}`, or for a text, `{key: "text"}`, then a table for each `{table: {key: [name, …]}}`,
    such as `{'icon': {'house': ['north']}}`. A JSON text or list of texts is a TOML one."""
    rows = [
        f'{key} = {json.dumps(names if isinstance(names, str) else list(names))}'
        for key, names in settings.items()
        if not isinstance(names, dict)
    ]
    for name, keys in settings.items():
        if isinstance(keys, dict):
            rows += [f'[{name}]', *(f'{key} = {json.dumps(list(names))}' for key, names in keys.items())]
    return ''.join(f'{row}\n' for row in rows)


# ---- lines ---------------------------------------------------------------------------------------


def indent(text, levels=1):
    """`text` with each line that is not empty `levels` levels deeper."""
    pad = '    ' * levels
    return '\n'.join(pad + row if row.strip() else row for row in text.split('\n'))


def block(head, *under):
    """A line and the lines under it, one level deeper. A part that is empty or None is left out."""
    return '\n'.join([head, *(indent(part) for part in under if part)])


def cites(records):
    """The end of a line that cites `records` (`@a @b`), or nothing."""
    return f'  {records}' if records else ''


def quote(words):
    """A text in quotes."""
    return '"' + words + '"'


def q(value, unit):
    """A number as a file writes it, with its unit: `24 h`. 0 and a number of a dimensionless unit
    stay bare; any other value (an expression or a word) stays as it is."""
    if isinstance(value, bool):
        return 'true' if value else 'false'
    if not isinstance(value, (int, float)):
        return value
    if value == 0 or not UNITS.get(unit, {'dimensions': {'x': 1}})['dimensions']:
        return repr(value)
    return f'{value!r} {unit}'


def number_of(written):
    """The number of a value that a file writes with its unit (`10 h` is 10), read as the reader
    reads a number: an int without a point or an exponent, else a float. A bare number is itself."""
    if not isinstance(written, str):
        return written
    text = written.split()[0]
    return int(text) if re.fullmatch(r'-?(?:0|[1-9][0-9]*)', text) else float(text)


def move(source, target):
    """The pair of a flow; None is outside the model: `a -> b`, `-> b` or `a ->`."""
    return f'{source or ""} -> {target or ""}'.strip()


# ---- members --------------------------------------------------------------------------------------

# The keyword of each kind of field that a helper writes: a kind of the builder names the keyword
# that declares it (a stock, a tally and a number state are each a `var`).
KEYWORDS = {
    'input': 'input',
    'text': 'input',
    'fixed': 'let',
    'formula': 'let',
    'let': 'let',
    'stock': 'var',
    'tally': 'var',
    'state': 'var',
    'var': 'var',
}


def value(kind, name, initial, unit, *, doc=None, records=BASIS, under=(), bounds=None, size=None):
    """A field: `keyword name: unit = initial [in lo to hi] [size s]`, with its text and the lines
    under it. `bounds` is (lo, hi)."""
    head = f'{KEYWORDS[kind]} {name}: {unit}' + (f' = {q(initial, unit)}' if initial is not None else '')
    if bounds is not None:
        head += f' in {q(bounds[0], unit)} to {q(bounds[1], unit)}'
    if size is not None:
        head += f' size {q(size, unit)}'
    return block(head + cites(records), quote(doc) if doc else None, *under)


def parameter(name, initial, unit, lo=None, hi=None, *, doc=None, records=BASIS, under=()):
    """An input that a run can set from `lo` to `hi`, or a fixed value when `lo` is None. A yes/no
    value (`unit` 'bool') has no bounds."""
    if lo is None:
        return value('fixed', name, initial, unit, doc=doc, records=records, under=under)
    bounds = None if unit == 'bool' else (lo, hi)
    return value('input', name, initial, unit, doc=doc, records=records, under=under, bounds=bounds)


def stock(
    name, initial=0, unit='people', *, minimum=0, maximum=None, size=100, kind='stock', rate=None, **lines
):
    """A number that the run changes, a `var`: a stock, a tally (it never falls) or a number state,
    as its flows and events make it; with its bounds (a stock and a tally have 0 below) and its size
    (none when `size` is None: the engine sizes it). `rate` fills it from outside: a flow
    `add_<name>`."""
    bounds = None
    if maximum is not None:
        bounds = (minimum if minimum is not None else 0, maximum)
    elif minimum not in (None, 0):
        raise ValueError('a var with a minimum other than 0 has its maximum too: in lo to hi')
    text = value(kind, name, initial, unit, bounds=bounds, size=size, under=lines.pop('under', ()), **lines)
    if rate is not None:
        text += '\n' + f'flow add_{name}: -> {name} at {rate}' + cites(lines.get('records', BASIS))
    return text


def named(name, initial, *others, records=None, doc=None):
    """A named state with its start value first. Its entity's records support it unless it gives its
    own."""
    names = ' | '.join(quote(v) for v in (initial, *others))
    return block(f'var {name}: {names} = {quote(initial)}' + cites(records), quote(doc) if doc else None)


def formula(name, expression, unit, *, doc=None, records=BASIS):
    return block(f'let {name}: {unit} = {expression}' + cites(records), quote(doc) if doc else None)


def text_value(name, words):
    return f'input {name} = {quote(words)}'


def flow(name, pairs, rate, *, doc=None, records=BASIS, condition=None, together=BASIS):
    """A flow that moves material along one pair (`a -> b`), or along a list of pairs together, at
    `rate` while `condition` holds."""
    keep = f' while {condition}' if condition else ''
    if isinstance(pairs, str):
        return block(f'flow {name}: {pairs} at {rate}{keep}' + cites(records), quote(doc) if doc else None)
    both = ' '.join(dict.fromkeys(part for part in (records, together) if part))
    return block(f'flow {name} at {rate}{keep}:' + cites(both), quote(doc) if doc else None, *pairs)


def event(
    name,
    when,
    *changes,
    once=True,
    transition=None,
    after=None,
    keep=None,
    condition=None,
    doc=None,
    role=None,
    records=BASIS,
    wait_records=None,
    do_records=None,
    done=None,
    stopped=None,
    skipped=None,
    stopped_role=None,
    skipped_role=None,
):
    """An event: it triggers when `when` becomes true, at most once (`once`), and with `transition`
    (`state "a" -> "b"`) only from the state "a", which it sets to "b". With `after` it fires that
    long after it triggers. `keep` (it fires `done` while it holds, else `stopped`) and `condition`
    (`done` when it holds, else `skipped`) give it outcomes, as do the texts `done`, `stopped` and
    `skipped`. `changes` are the lines of its change: of its outcome `done` when it has outcomes."""
    head = f'event {name}' + (' once' if once else '')
    if after is not None and str(after) != '0':
        head += f' after {after}'
    conditions = []
    if transition is not None:
        state, rest = transition.split(' ', 1)
        source, target = (part.strip() for part in rest.split('->'))
        sources = re.findall(r'"[^"]*"', source)
        conditions.append(
            f'{state} is {sources[0]}'
            if len(sources) == 1
            else '(' + ' or '.join(f'{state} is {v}' for v in sources) + ')'
        )
        changes = (f'{state} = {target}', *changes)
    if when is not None:
        conditions.append(f'({when})' if conditions and (' or ' in when or ' if ' in when) else when)
    if conditions:
        head += ' when ' + ' and '.join(conditions)
    outcomes = bool(done or stopped or skipped or keep or condition)
    names = [records, wait_records] + ([] if outcomes else [do_records])
    head += ':' + cites(' '.join(dict.fromkeys(part for part in names if part)))
    rows = [quote(doc) if doc else None, f'role {role}' if role else None]
    if not outcomes:
        return block(head, *rows, *changes)
    if keep and condition:
        chance = f' ({keep}) and ({condition})'
    else:
        chance = f' {keep or condition}' if keep or condition else ''
    rows.append(block(f'done{chance}:' + cites(do_records), quote(done) if done else None, *changes))
    if condition:
        skip = f' ({keep}) and not ({condition})' if keep else ' else'
        rows.append(
            block(
                f'skipped{skip}:',
                quote(skipped) if skipped else None,
                f'role {skipped_role}' if skipped_role else None,
            )
        )
    if keep:
        rows.append(
            block(
                'stopped else:',
                quote(stopped) if stopped else None,
                f'role {stopped_role}' if stopped_role else None,
            )
        )
    return block(head, *rows)


def once_at(name, time, *changes, records=BASIS, do_records=None, doc=None):
    """An event that happens one time, at a fixed time, with the lines of its change."""
    return event(name, f't >= {time}', *changes, records=records, do_records=do_records, doc=doc)


def named_event(name, *changes, doc=None, records=BASIS):
    """An event with no `when`: only a line that names it fires it (`x.name`), with its change."""
    return block(f'event {name}:' + cites(records), quote(doc) if doc else None, *changes)


def check(condition, message=None, *, records=BASIS, under=(), within=None):
    """An `assert` with its message: a check before the run when it reads inputs and named states
    only, else at every step; with `within`, its tolerance, a sum check (docs/language.md, §2.8)."""
    tolerance = f' within {within}' if within is not None else ''
    return block(
        f'assert {condition}{tolerance}' + cites(records), quote(message) if message else None, *under
    )


def output(name, expression, unit, measure=None, *, doc='Fixture output', records=BASIS, under=()):
    """An output: at the top level it reads entities by name, inside an entity its own values. A
    `measure` other than cumulative makes it a `level`."""
    head = f'output {name}: {unit}' + (f' = {expression}' if expression is not None else '')
    return block(
        head + cites(records),
        quote(doc) if doc else None,
        'level' if measure not in (None, 'cumulative') else None,
        *under,
    )


def share(stock, limit, order='proportional', *, doc=None, records=BASIS):
    """The share of `stock` among the flows that take from it, at most `limit` an hour: `order` is
    `proportional` or a list of flows, first served first. Its name in the structure is
    `share_<stock>`."""
    served = '' if isinstance(order, str) else ' order ' + ', '.join(order)
    return block(f'share {stock} limit {limit}{served}' + cites(records), quote(doc) if doc else None)


def status(*cases, records=None):
    """The status lines, each `(status, condition, text)`; the last one has no condition."""
    rows = []
    for k, (health, condition, words) in enumerate(cases):
        head = f'status {health}' + (f' when {condition}' if condition else '')
        rows.append(block(head + (cites(records) if k == 0 else ''), quote(words) if words else None))
    return '\n'.join(rows)


class Start(str):
    """The start: the event `start` of the entity `entity`, which `document` writes into that entity."""

    def __new__(cls, text, entity):
        found = super().__new__(cls, text)
        found.entity = entity
        return found


def start(name, *changes, doc=None, records=BASIS, do_records=None):
    """The start: the event `start` of entity `name`, at t = 0, with its first change (`changes`). The
    start of an operation changes nothing: its events wait on `count(name.start)`."""
    both = ' '.join(dict.fromkeys(part for part in (records, do_records) if part))
    text = block('event start when t >= 0 h:' + cites(both), quote(doc) if doc else None, *changes)
    return Start(text, name)


# ---- things and files -----------------------------------------------------------------------------


def entity(
    name,
    *members,
    template=None,
    doc='A numerical fixture.',
    role='environment',
    records=BASIS,
    title=None,
    copies=None,
):
    """An entity with its members, or an instance of `template` (`copies` of it) with its changes."""
    if template is not None:
        head = f'{name}: {template}' + (f' * {copies}' if copies else '')
        return block(head + cites(records), *members)
    return block(
        f'{name}:' + cites(records),
        quote(doc) if doc else None,
        f'title {quote(title)}' if title else None,
        f'role {role}' if role else None,
        *members,
    )


def template(name, *members, doc='A template of a fixture.', role='environment', records=BASIS):
    """A template: its name starts with a capital letter."""
    assert name[:1].isupper(), f'a template is named with a capital letter: {name}'
    return block(
        f'{name}:' + cites(records),
        quote(doc) if doc else None,
        f'role {role}' if role else None,
        *members,
    )


def option(name, doc, *settings):
    """An option with its text and the values that it sets: `entity.field = v  @record`."""
    return block(f'{quote(name)}:', quote(doc), *settings)


def options(group, *members):
    return block(f'options {quote(group)}:', *members)


DEFAULT_OPTIONS = options('Response', option('Default', 'The defaults.'))


def runs(**named_runs):
    """`runs:`, one line for each run: its name and the names of its options."""
    return block(
        'runs:', *(f'{name} = {" + ".join(quote(p) for p in names)}' for name, names in named_runs.items())
    )


def with_start(declarations):
    """The declarations with the start written into its entity."""
    starts = [part for part in declarations if isinstance(part, Start)]
    if not starts:
        return list(declarations)
    assert len(starts) == 1, 'a file has one start'
    found = starts[0]
    out, placed = [], False
    for part in declarations:
        if part is found:
            continue
        if isinstance(part, str) and part.split('\n', 1)[0].split(':', 1)[0] == found.entity:
            out.append(part + '\n' + indent(str(found)))
            placed = True
            continue
        out.append(part)
    assert placed, f'no entity {found.entity} for the start'
    return out


def document(
    title,
    *declarations,
    horizon=24,
    summary=None,
    timescales=None,
    option_groups=(DEFAULT_OPTIONS,),
    run_lines=None,
    scope='Fixture',
    library='../library',
    notes=None,
    records=(),
):
    """A model file: its scenario line (with the scope of its outputs, `scope`, and the folder of its
    library, `library`, which the main file of a package `scenarios/<package>/` finds in
    `scenarios/library/`, as the fixture writers of `tests/owned.py` write it), its declarations,
    its options (one group, Response, with its option Default, unless `option_groups` says otherwise),
    its runs (`a`, which takes Default, unless `run_lines` says otherwise), its notes and its records,
    `@fixture` first. A `start` goes into its entity."""
    declarations = with_start([part for part in declarations if part])
    head = block(
        f'scenario {quote(title)}',
        f'summary {quote(summary or f"{title}. A synthetic fixture for tests only.")}',
        f'horizon {q(horizon, "h")}',
        f'timescales {", ".join(timescales)}' if timescales else None,
        f'scope {quote(scope)}' if scope else None,
        f'library {quote(library)}' if library else None,
    )
    parts = [
        head,
        *declarations,
        *option_groups,
        run_lines if run_lines is not None else runs(a=['Default']),
        block('notes:', notes) if notes else None,
        '\n'.join([FIXTURE_RECORD, *records]),
    ]
    return '\n\n'.join(part for part in parts if part) + '\n'


def system(*members, horizon=10, outputs=None, checks=(), timescales=None, records=()):
    """A one-entity file around entity `s`, titled System, for numerical tests, with its members and
    the top-level `outputs` (by default the elapsed time) and `checks`. A value is `s.<name>`, and so
    are its events and flows. Events at one moment go in the order of their lines."""
    outputs = (output('elapsed_time', 't', 'h', 'level', doc='Elapsed time'),) if outputs is None else outputs
    return document(
        'Numerical fixture',
        entity('s', *members, title='System'),
        *checks,
        *outputs,
        horizon=horizon,
        timescales=timescales,
        records=records,
    )


def with_horizon(text, hours):
    """A text that runs for `hours`."""
    return re.sub(r'(?m)^    horizon .*$', f'    horizon {q(hours, "h")}', text, count=1)


# ---- edits ----------------------------------------------------------------------------------------


def places(text):
    """{place: (first row, end row)} of the lines of a model text: each line with the lines under
    it, and the rows of a bracket or a text that it opens."""
    lines = front.read(text, 'edit.scn').lines
    rows = text.split('\n')
    out = {}
    for where, number in lines.items():
        start = number - 1
        out[path_text(where)] = (start, block_end(rows, start))
    return out


def block_end(rows, start):
    """The row after the block of the line at row `start`."""
    state = {'depth': 0, 'text': False}

    def depth(row):
        return len(row) - len(row.lstrip(' '))

    def scan(row):
        if not state['text'] and row.lstrip().startswith('#'):
            return
        for char in row:
            if char == '"':
                state['text'] = not state['text']
            elif not state['text'] and char in '([{':
                state['depth'] += 1
            elif not state['text'] and char in ')]}':
                state['depth'] -= 1

    scan(rows[start])
    end = start + 1
    while end < len(rows) and (
        state['depth'] > 0 or state['text'] or not rows[end].strip() or depth(rows[end]) > depth(rows[start])
    ):
        scan(rows[end])
        end += 1
    while end > start + 1 and not rows[end - 1].strip():
        end -= 1
    return end


def member(owner, *blocks):
    """An edit step: the blocks go at the end of the lines under the line at place `owner`, one level
    deeper than it: `member('service', flow(...))`, `member('service/stop', 'role operator')`. The notes
    (`member('notes:', …)`) are written as a block of their own at the end of a file that has none."""
    return ('member', owner, blocks)


def drop(*names):
    """An edit step: the lines at these places go, with the lines under them."""
    return ('drop', names)


def replace(old, new):
    """An edit step: the text `old`, which occurs once, becomes `new`."""
    return ('replace', old, new)


def append(*blocks):
    """An edit step: the blocks go at the end of the file, at the top level."""
    return ('append', blocks)


def edit(text, *steps):
    """A text with the steps of a test's edit applied, in order (`member`, `drop`, `replace`,
    `append`)."""
    for step in steps:
        kind = step[0]
        if kind == 'replace':
            _, old, new = step
            assert text.count(old) == 1, f'{old!r} occurs {text.count(old)} times'
            text = text.replace(old, new)
        elif kind == 'append':
            text = text.rstrip('\n') + '\n\n' + '\n\n'.join(step[1]) + '\n'
        elif kind == 'member':
            _, owner, blocks = step
            found = places(text)
            if owner == 'notes:' and owner not in found:
                text = text.rstrip('\n') + '\n\n' + block('notes:', *blocks) + '\n'
                continue
            assert owner in found, f'no line at {owner!r}'
            start, end = found[owner]
            rows = text.split('\n')
            pad = len(rows[start]) - len(rows[start].lstrip(' '))
            added = indent('\n'.join(blocks), pad // 4 + 1).split('\n')
            text = '\n'.join(rows[:end] + added + rows[end:])
        elif kind == 'drop':
            for name in step[1]:
                found = places(text)
                assert name in found, f'no line at {name!r}'
                start, end = found[name]
                rows = text.split('\n')
                text = '\n'.join(rows[:start] + rows[end:])
        else:
            raise ValueError(f'unknown edit step {kind!r}')
    return text


# ---- models and runs ------------------------------------------------------------------------------


def compiled(text, lib=None, origin='test.scn'):
    """The model of a model text, built with `lib` (by default the test library)."""
    return front.compile_file(front.read(text, origin), origin, thaw(lib or library()))


def lowered(text, lib=None, origin='test.scn'):
    """({start-state options: mapping}, {start-state options: mapping of the whole structure}) of a
    model text, as the lowering writes them (`napkin.model.lower.Builder`), before the build reads
    them into typed parts (`napkin.model.model.typed_of`) and before any check. Each expression is
    its node. A test of `Structure.of` reads these: they are the real input of the typed parts."""
    from napkin.model.language.resolve import arguments, resolve
    from napkin.model.lower import Builder
    from napkin.model.runs import Runs

    lib = thaw(lib or library())
    scenario, resolver = resolve(front.read(text, origin), lib)
    table = Runs.from_scenario(scenario, lib).table
    builder = Builder(arguments(scenario, table, resolver), table, lib)
    builder.base = builder.build()
    structures = {starts: builder.derive(builder.base, starts) for starts in builder.start_sets()}
    return structures, dict(builder.whole)


def resolved(text, name='a', lib=None):
    """The resolved structure of one run of a text, ready for a direct run."""
    return compiled(text, lib).resolve(name)


def run(text, name='a', lib=None, settings=None, values=None):
    """(resolved structure, trajectory) of one run, with `values` for some inputs, run directly."""
    lib = lib or library()
    rs = compiled(text, lib).resolve(name, values)
    return rs, simulate(rs, lib, settings)


def rejected(text, lib=None):
    """The (code, place) of every diagnostic that rejects a text."""
    with pytest.raises(ModelError) as raised:
        compiled(text, lib or evidence_library())
    return {(d['code'], d['path']) for d in raised.value.diagnostics}


# ---- the analytic transfer ------------------------------------------------------------------------


def service(*members, stop='t >= end', stop_records=BASIS):
    """The entity `service` of the analytic transfer, with more `members` before its check, and the
    condition and the records of its event `stop`."""
    return entity(
        'service',
        parameter('n', 10, 'people', 1, 100, doc='People'),
        parameter('rate', 24, 'people/day', 1, 48, doc='Delivery rate'),
        parameter('end', 12, 'h', 1, 24, doc='Stop time'),
        named('state', 'on', 'off'),
        stock('stock', 'n', size=10, doc='People waiting'),
        stock('served', 0, size=10, kind='tally', doc='People served'),
        formula('delivery', 'rate if state is "on" else 0 people/h', 'people/h'),
        event('stop', stop, once=False, transition='state "on" -> "off"', doc='Stop', records=stop_records),
        flow('serve', 'stock -> served', 'delivery'),
        *members,
        check('stock + served is n', 'Conserve people'),
        doc='A service that moves people out of a stock.',
        role='operator',
    )


# The options and the runs of the analytic transfer.
RATE_OPTIONS = (
    DEFAULT_OPTIONS,
    options('Rate', option('Half rate', 'Half the delivery rate.', f'service.rate = 12 people/day  {BASIS}')),
)
RATE_RUNS = runs(a=['Default'], b=['Default', 'Half rate'])


def scenario():
    """An analytic transfer: `n` people move from a stock at `rate` until the service stops at `end`.
    The served total is min(n, rate * end). Run `a` takes the defaults; run `b` also takes the option
    `Half rate`, which sets the rate to 12 people a day."""
    return document(
        'Analytic transfer',
        service(),
        check('service.end <= 24 h', 'Within horizon'),
        output('delivered', 'service.served', 'people', doc='Delivered'),
        option_groups=RATE_OPTIONS,
        run_lines=RATE_RUNS,
    )


# ---- a timer with uncertain inputs ------------------------------------------------------------------


def uncertain(name, unit, low, high, written):
    """An input of `unit` from `low` to `high` whose value is the distribution `written`."""
    return parameter(name, written, unit, low, high)


def timer(rate='uniform(1 people/h, 3 people/h)', end='pert(2 h, 6 h, 20 h)', *members):
    """People arrive at `rate` until the service stops at `end`: served(24 h) = rate * end. `members`
    go into the entity `s` after its tally."""
    return system(
        uncertain('rate', 'people/h', 0.5, 4, rate),
        uncertain('end', 'h', 1, 22, end),
        named('state', 'on', 'off'),
        stock('served', 0, kind='tally', size=100),
        *members,
        event('stops', 't >= end', once=False, transition='state "on" -> "off"'),
        flow('serve', move(None, 'served'), 'rate if state is "on" else 0 people/h'),
        horizon=24,
        outputs=(
            output('served', 's.served', 'people'),
            output('elapsed_time', 't', 'h', 'level', doc='Elapsed time'),
        ),
    )


# ---- evidence -------------------------------------------------------------------------------------


def cited(name, *claims, explanation='Contract fixture.'):
    """A named record that cites `claims`, for the end of a file: cite it as `@name`."""
    return block(f'record {name}: source_transfer {quote(explanation)}', block('claims:', *claims))


def fixture_claim(identifier, **fields):
    claim = {
        'id': identifier,
        'source': 'src',
        'locator': 'p. 1',
        'shows': f'{identifier} fixture fact.',
        'limits': 'Synthetic.',
        **fields,
    }
    digest = hashlib.sha256(
        json.dumps(claim, sort_keys=True, separators=(',', ':'), ensure_ascii=True).encode()
    ).hexdigest()
    return {
        **claim,
        'verification': {
            'status': 'unverified',
            'date': '2026-09-18',
            'method': 'access_attempt',
            'notes': 'Synthetic.',
            'checked_fields': [],
            'content_sha256': digest,
        },
    }


TECHNIQUE = 'MITRE ATT&CK for ICS technique T0831 Manipulation of Control (fixture only).'


def evidence_library():
    lib = library()
    lib['sources'] = [
        {
            'id': 'src',
            'title': 'Fixture source',
            'custom': {
                'verification': {
                    'status': 'unverified',
                    'date': '2026-09-18',
                    'method': 'access_attempt',
                    'notes': 'Synthetic.',
                }
            },
        }
    ]
    lib['claims'] = [
        fixture_claim('C-ACCESS'),
        fixture_claim('C-ACTION'),
        fixture_claim('ATTACK-T0831', shows=TECHNIQUE),
    ]
    lib['assumptions'] = [
        {
            'id': 'RT-FIXTURE',
            'statement': 'The cyber effect stops service.',
            'rationale': 'Fixture.',
            'review': {'status': 'unreviewed'},
            'origin': 'model_redteam',
            'supports': [{'claim': 'C-ACTION', 'relation': 'mechanism_precedent'}],
            'elicitation': {
                'method': 'machine_redteam',
                'elicited': 'fixture',
                'date': '2026-09-18',
                'question': 'Does it?',
                'argument': 'Precedent.',
                'dissent': 'None cited.',
                'falsifier': 'A counterexample.',
            },
        }
    ]
    return lib


# The event of the first change: the engine's name of the start's outcome, `attacker.start.done`.
X = 'attacker.start.done'
# The record of the cyber-to-service step, cited `@cyber_step`.
CYBER_STEP = 'record cyber_step: assumption RT-FIXTURE "Cyber-to-service step."'


def in_place(kind, explanation, *claims, assumption=None):
    """A record written in place, under a line: `@kind "explanation"` with its claims."""
    head = f'@{kind}' + (f' {assumption}' if assumption else '') + f' {quote(explanation)}'
    return block(head, block('claims:', *claims) if claims else None)


def sc99():
    """The analytic transfer started by a cyber incident. The first change, at t = 0, sends
    unauthorized commands that compromise the control system; the service notices the compromise and
    stops `end` hours after the first change."""
    first_effect = event('compromised', 'control.state is "compromised"', records='@cyber_step')
    control = entity(
        'control',
        named('state', 'trusted', 'compromised'),
        doc='The control system of the service, reached through pre-positioned access.',
        records='@access',
    )
    attacker = block(
        'attacker:',
        quote('An attacker who sends unauthorized commands.'),
        in_place('source_transfer', 'Contract fixture.', 'C-ACTION'),
        'role adversary',
    )
    first = start(
        'attacker',
        in_place('source_transfer', 'Contract fixture.', 'C-ACTION', 'ATTACK-T0831'),
        'control.state = "compromised"',
        doc='Unauthorized commands',
        records='@access',
    )
    return document(
        'Analytic transfer',
        service(first_effect, stop='since(attacker.start) >= end', stop_records='@cyber_step'),
        control,
        attacker,
        first,
        check('service.end <= 24 h', 'Within horizon'),
        output('delivered', 'service.served', 'people', doc='Delivered'),
        option_groups=RATE_OPTIONS,
        run_lines=RATE_RUNS,
        notes=block('premises:', 'START: "Fixture: the claims establish the mechanism only."'),
        records=(CYBER_STEP, cited('access', 'C-ACCESS')),
    )


# ---- a played run ---------------------------------------------------------------------------------

PLAY_WORLD = entity(
    'world',
    named('alarm', 'off', 'on'),
    stock('level', 0, 'fraction', maximum=2, size=None, rate='0.1 per_h'),
    parameter('delay', 2, 'days', 1, 4),
    block('event ring once when t >= 1 h:  @fixture', 'alarm = "on"'),
    block('event hum once when t >= 2 h:  @fixture', quote('A hum that the guard does not see.')),
    block('event late once when t >= 8 h:  @fixture', quote('Too late for the first decision.')),
)


def play_guard(shut='0.3', wait='else'):
    """An operator that sees the alarm, the level, the delay and two events of the world (not its hum),
    and decides at 3 h (`first`) and at 6 h (`second`) to shut or to wait, with these chances."""

    def decision(name, at):
        return block(
            f'event {name} once when t >= {at}:  @fixture',
            'choice',
            block(f'shut {shut}:', quote('The guard shuts.'), f'{name}_choice = "shut"'),
            block(f'wait {wait}:', quote('The guard waits.'), f'{name}_choice = "wait"'),
        )

    return entity(
        'guard',
        'sees world.alarm, world.level, world.delay, world.ring, world.late',
        named('first_choice', 'none', 'shut', 'wait'),
        named('second_choice', 'none', 'shut', 'wait'),
        decision('first', '3 h'),
        decision('second', '6 h'),
        role='operator',
    )


def play_scenario(**chances):
    """A file with the world and the guard, an actor that a reader or an agent can play."""
    return document('Play fixture', PLAY_WORLD, play_guard(**chances), horizon=10)
