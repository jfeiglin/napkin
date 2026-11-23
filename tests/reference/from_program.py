"""The programs of `napkin.program` as models of the oracle.

The oracle keeps its own description of a model (`model.py`) and its own evaluator. This module
reads the records of a program (`napkin.program.parts`, `refs` and `config`), walks the nodes of
`napkin.core.expr` as data, and makes the oracle's records from them. It calls no evaluation code
of napkin: no `napkin.core.evaluation`, no `napkin.expressions`, nothing of `napkin.engine`.

- `model_of(program)` gives the oracle's `Model`. The run's root is a member whose id is `''`, as a
  key of a record names it. Each event, step, trigger, solver and statement keeps its origin, and
  each draw its site, so that the oracle's trace names the parts of the program.
- `config_of(program, configuration)` gives the oracle's `Config`: the inputs, the mode and the
  seed, and the limits. Budgets and numerical settings do not apply to exact arithmetic.
- `run_of(program, configuration, stops)` runs it, and stops at each breakpoint of `stops` in turn,
  makes its edits and resumes (docs/design/decisions.md, change 15).
- `value_at(run, program, key, t)` reads the value at a key of the record (`record.Key`) at a time,
  stated in the declared unit of that value, and `traced(run, kind, part)` gives the times and the
  rounds of the trace entries of a kind (`commit`, `finish`, ...) for a part named by its origin.

Numbers become the oracle's canonical numbers: `q(n, unit)` is n times the scale that the program's
table gives the unit, and a float of a node is read as its decimal text (0.3 is 3/10), so a value
that a program writes in decimals stays exact.
"""

from fractions import Fraction

from napkin.core import expr as nodes
from napkin.program import parts as p
from napkin.program import refs
from napkin.program.config import Quantity

from .errors import NotCovered, RunFailed
from .evaluate import ITEM
from .model import (
    SINK,
    SOURCE,
    After,
    Assign,
    Branch,
    Case,
    Config,
    E,
    Endpoint,
    Event,
    Field,
    Flow,
    Leg,
    Model,
    Move,
    Solver,
    Start,
    Switch,
    Template,
    Trigger,
    Unknown,
    Until,
    coll,
    fn,
    priority,
    proportional,
)
from .run import Run

ROOT = ''  # the id of the run's root among the members of the oracle
SYMBOLS = {
    'add': '+',
    'sub': '-',
    'mul': '*',
    'div': '/',
    'eq': '==',
    'ne': '!=',
    'lt': '<',
    'le': '<=',
    'gt': '>',
    'ge': '>=',
}
KINDS = {  # a kind of the record's trace -> the kind of the oracle's trace
    'start': 'start',
    'finish': 'done',
    'commit': 'stage',
    'fire': 'fire',
    'solve': 'solve',
    'draw': 'draw',
    'move': 'move',
    'edit': 'edit',
}
FIELD_KINDS = {
    p.INPUT: 'input',
    p.STATE: 'value',
    p.FORMULA: 'formula',
    p.LINK: 'link',
    p.COLLECTION: 'value',
    p.DISTRIBUTION: 'value',
}


def _exact(value):
    """A constant of a node or a number of a record as an exact value."""
    if isinstance(value, bool) or not isinstance(value, (int, float, Fraction)):
        return value
    return Fraction(repr(value)) if isinstance(value, float) else Fraction(value)


def _number(e):
    """The number of a constant node, or None."""
    if e._k == 'const' and isinstance(e._a[0], Fraction):
        return e._a[0]
    return None


def _folded(sym, a, b):
    """`a sym b` of arithmetic, computed at once when both sides are numbers."""
    x, y = _number(a), _number(b)
    if x is None or y is None or (sym == '/' and y == 0):
        return E('op', sym, a, b)
    unit = (
        a._unit_size * b._unit_size
        if sym == '*'
        else a._unit_size / b._unit_size
        if sym == '/'
        else a._unit_size  # literal operands carry their units but contribute no comparison floor
    )
    return E(
        'const',
        x + y if sym == '+' else x - y if sym == '-' else x * y if sym == '*' else x / y,
        unit_size=unit,
    )


def _joined(sym, values):
    """The values joined from the left by `sym`: `+`, `and` or `or`."""
    joined = values[0]
    for value in values[1:]:
        joined = E('op', sym, joined, value)
    return joined


class _Translation:
    """One program on its way to the oracle: the scales of its units and the sites of its draws."""

    def __init__(self, program):
        self.program = program
        self.scales = {unit.name: unit.scale for unit in program.units}
        self.sites = {}

    def scale(self, unit):
        """The scale of a unit's spelling; `''` is the plain number."""
        return Fraction(1) if unit == '' else Fraction(self.scales[unit])

    # --- expressions ----------------------------------------------------------------------------

    def expr(self, value):
        """An `Expr`, a `Formula`, a `Distribution`, a path or None as a node of the oracle."""
        if value is None:
            return None
        if isinstance(value, refs.Formula):
            return E('formula', self.expr(value.expr))
        if isinstance(value, refs.Expr):
            return self.node(value.node, value)
        if isinstance(value, refs.Distribution):
            return self.distribution(value)
        if isinstance(value, refs.Path):
            return self.path(value)
        raise NotCovered(f'no expression of a program: {value!r}')

    def node(self, n, expression):
        """A node of `napkin.core.expr`; its names are read through the reads of `expression`."""
        if isinstance(n, nodes.Const):
            return E('const', _exact(n.value))
        if isinstance(n, nodes.Ref):
            return self.read(expression.read(n.name))
        if isinstance(n, nodes.Unary):
            x = self.node(n.operand, expression)
            if n.op == 'pos':
                return x
            if n.op == 'neg' and _number(x) is not None:
                return E('const', -_number(x), unit_size=x._unit_size)
            return E('neg' if n.op == 'neg' else 'not', x)
        if isinstance(n, nodes.Binary):
            if n.op not in SYMBOLS:
                raise NotCovered(f'the operation {n.op}: the oracle computes in fractions')
            return _folded(SYMBOLS[n.op], self.node(n.left, expression), self.node(n.right, expression))
        if isinstance(n, nodes.Compare):
            operands = [self.node(x, expression) for x in n.operands]
            if tuple(n.ops) == ('le', 'le'):  # `lower <= x <= upper`: x is read once
                return E('in', operands[1], operands[0], operands[2])
            pairs = [E('op', SYMBOLS[op], a, b) for op, a, b in zip(n.ops, operands, operands[1:])]
            return _joined('and', pairs)
        if isinstance(n, nodes.BoolOp):
            return _joined(n.op, [self.node(x, expression) for x in n.values])
        if isinstance(n, nodes.IfElse):
            parts = (n.test, n.body, n.orelse)
            return E('if', *(self.node(x, expression) for x in parts))
        if isinstance(n, nodes.Call):
            return self.call(n, expression)
        raise NotCovered(f'a node {type(n).__name__} of napkin.core.expr')

    def call(self, n, expression):
        """A call of a function of the language. `q(n, unit)` is n in canonical units."""
        if n.function == 'q':
            number, unit = n.args
            size = self.scale(unit.value)
            amount = _folded('*', self.node(number, expression), E('const', size))
            return E(amount._k, *amount._a, unit_size=size)
        values = [self.node(x, expression) for x in n.args]
        if n.function in ('min', 'max', 'abs', 'clip'):
            return fn(n.function, *values)
        if n.function == 'within':
            return E('within', *values)  # `x in [lo, hi]`: its ends are checked when it is read
        if n.function in ('sum', 'any', 'all') and values:
            return _joined({'sum': '+', 'any': 'or', 'all': 'and'}[n.function], values)
        raise NotCovered(f'the function {n.function}: the oracle computes in fractions')

    def read(self, read):
        """What a name of a node reads."""
        if isinstance(read, refs.Time):
            return E('t')
        if isinstance(read, refs.Path):
            return self.path(read)
        if isinstance(read, refs.EnumValue):
            return E('const', read.member)
        if isinstance(read, refs.Reduce):
            return fn(read.op, self.path(read.source))
        if isinstance(read, refs.Since):
            return fn('since', self.path(read.event))
        if isinstance(read, refs.Elapsed):
            return fn('elapsed', self.path(read.value))
        if not isinstance(read, refs.Draw):
            raise NotCovered(f'no read of a program: {read!r}')
        node = E('call', self.source(read.source), 'draw', ())
        self.sites[id(node)] = read.site  # the oracle keys the draw by this site
        return node

    def source(self, source):
        """The distribution of a draw: written in place, or named by a path."""
        return self.distribution(source) if isinstance(source, refs.Distribution) else self.path(source)

    def distribution(self, d):
        """A distribution, its parameters in canonical units."""
        if d.family == 'categorical':
            return E('categorical', tuple((m, E('const', _exact(w))) for m, w in zip(d.outcomes, d.params)))
        if d.family not in ('uniform', 'normal') or len(d.params) != 2:
            raise NotCovered(f'the distribution {refs.spelled(d)}')
        size = self.scale(d.unit)
        return E('dist', d.family, tuple(E('const', _exact(x) * size) for x in d.params))

    def path(self, path):
        """A path: its start, then a step for each name, as the oracle resolves a dotted name."""
        start = path.start
        if isinstance(start, refs.This):
            node = E('this')
        elif isinstance(start, refs.Root):
            node = E('member', ROOT)
        elif isinstance(start, refs.Item):
            node = E('name', ITEM)
        elif isinstance(start, refs.Named):
            node = E('member', start.id)
        elif isinstance(start, refs.Local):
            node = E('name', start.name)
        elif isinstance(start, refs.Instances):
            node = E('instances', start.template)
        elif isinstance(start, refs.Literal):
            node = coll(*(self.path(each) for each in start.items))
        elif isinstance(start, refs.Where):
            node = E('where', self.path(start.source), self.expr(start.test))
        elif isinstance(start, refs.By):
            node = E('call', self.path(start.source), 'by', (E('name', start.key),))
        elif isinstance(start, refs.Lookup):
            node = E('call', self.path(start.source), 'at', (self.expr(start.key),))
        else:
            raise NotCovered(f'no start of a path: {start!r}')
        for step in path.steps:
            node = E('attr', node, step)
        return node

    # --- parts ----------------------------------------------------------------------------------

    def field(self, value):
        """A value of a template, the root or an event. A formula keeps its expression, which the
        oracle retains; a link has no initializer of its own (its member gives it)."""
        if value.kind == p.FORMULA:
            init = self.expr(value.init.expr)
        elif value.kind == p.LINK:
            init = None
        else:
            init = self.expr(value.init)
        return Field(
            value.name,
            init,
            self.expr(value.lower),
            self.expr(value.upper),
            kind=FIELD_KINDS[value.kind],
            readonly=value.readonly,
            scale=self.expr(value.scale),
            outflow=self.endpoint(value.outflow),
            inflow=self.endpoint(value.inflow),
            unit=value.type.unit if isinstance(value.type, p.Number) else '',
            refers_to=(
                (value.type.template, value.type.event)
                if isinstance(value.type, p.OccurrenceType)
                else (value.type.template,)
                if isinstance(value.type, p.EntityType)
                else ()
            ),
        )

    def endpoint(self, endpoint):
        if endpoint is None:
            return None
        return Endpoint(
            self.expr(endpoint.capacity), self.expr(endpoint.request), self.allocation(endpoint.allocation)
        )

    def allocation(self, allocation):
        """`priority(...)`, or None for `proportional()`, the default."""
        if isinstance(allocation, p.Priority):
            return priority(*(self.path(each) for each in allocation.items))
        return None

    def end(self, end):
        if isinstance(end, p.Outside):
            return SOURCE if end.name == 'SOURCE' else SINK
        return self.path(end)

    def flow(self, flow):
        if flow.kind == p.LEGS:
            legs = tuple(
                Leg(
                    each.name,
                    self.end(each.source),
                    self.end(each.sink),
                    self.expr(each.request),
                    self.expr(each.capacity),
                    self.scale(each.unit),
                )
                for each in flow.legs
            )
            return Flow(flow.name, legs=legs)
        return Flow(
            flow.name,
            self.end(flow.source),
            self.end(flow.sink),
            self.expr(flow.capacity),
            self.expr(flow.request),
            reversible=flow.kind == p.REVERSIBLE,
            unit_size=self.scale(flow.unit),
        )

    def statements(self, statements):
        return [self.statement(each) for each in statements]

    def statement(self, s):
        if isinstance(s, p.Assign):
            if isinstance(s.value, p.Priority):
                value = self.allocation(s.value)
            elif isinstance(s.value, p.Proportional):
                value = proportional()
            else:
                value = self.expr(s.value)
            return Assign(self.path(s.target), s.op, value, s.origin)
        if isinstance(s, p.Move):
            return Move(self.expr(s.amount), self.path(s.source), self.path(s.destination), s.origin)
        if isinstance(s, p.Start):
            return Start(self.path(s.event), tuple(self.expr(arg) for arg in s.args), s.origin)
        if isinstance(s, p.If):
            return Branch(self.expr(s.test), self.statements(s.then), self.statements(s.orelse), s.origin)
        if isinstance(s, p.Switch):
            cases = [Case(c.member, self.statements(c.body), self.expr(c.guard)) for c in s.cases]
            return Switch(self.expr(s.selector), cases, self.statements(s.orelse) or None, s.origin)
        raise NotCovered(f'no statement of a program: {s!r}')

    def step(self, step):
        if isinstance(step, p.After):
            return After(
                self.expr(step.delay), self.statements(step.body), self.expr(step.guard), step.origin
            )
        return Until(self.expr(step.test), step.origin)

    def trigger(self, trigger):
        reset = None if trigger.reset is None else (trigger.reset.kind, self.expr(trigger.reset.expr))
        captures = [(each.name, self.expr(each.init)) for each in trigger.captures]
        return Trigger(
            self.expr(trigger.test), self.statements(trigger.body), captures, reset, trigger.origin
        )

    def event(self, event):
        locals_ = [self.flow(x) if isinstance(x, p.Flow) else self.field(x) for x in event.locals]
        # A parameter's declared range, which each argument must lie in (spec.md:572).
        ranges = {
            each.name: self.field(each)
            for each in event.params
            if each.lower is not None or each.upper is not None
        }
        return Event(
            event.name,
            [each.name for each in event.params],
            locals_,
            [self.trigger(each) for each in event.triggers],
            [self.step(each) for each in event.steps],
            event.origin,
            ranges,
            {each.name: each.type.template for each in event.params if isinstance(each.type, p.EntityType)},
        )

    def solver(self, solver):
        """A solver: its new unknowns first, then the existing fields that it determines."""
        unknowns = [
            Unknown(
                u.name,
                self.expr(u.lower),
                self.expr(u.upper),
                self.expr(u.init),
                self.expr(u.scale),
                self.scale(u.type.unit),
            )
            for u in solver.unknowns
        ]
        return Solver(
            solver.name,
            {each.name: self.path(each.source) for each in solver.inputs},
            unknowns + [self.path(each) for each in solver.solve_for],
            [self.expr(each.test) for each in solver.constraints],
            [
                ('min' if each.sense == 'minimize' else 'max', self.expr(each.expr))
                for each in solver.objective
            ],
            solver.origin,
        )

    def template(self, template):
        return Template(
            template.name,
            [self.field(each) for each in template.values],
            [self.flow(each) for each in template.flows],
            [self.event(each) for each in template.events],
            [self.solver(each) for each in template.solvers],
        )


def model_of(program):
    """The oracle's model of a program: its templates with their members, the root as the member
    `''`, the setup statements and the assertions."""
    tr = _Translation(program)
    m = Model(units=dict(tr.scales))
    for template in program.templates:
        m.templates[template.name] = tr.template(template)
        for member in template.members:
            values = {
                name: tr.expr(init.expr if isinstance(init, refs.Formula) else init)
                for name, init in member.values
            }
            for name, row in member.links:  # a link names a row of the link's template
                values[name] = program.template(template.part(name).type.template).members[row].id
            m.instance(member.id, template.name, **values)
            for each in template.asserts:
                m.check(tr.expr(each.test), owner=member.id, text=each.origin)
    m.template(ROOT, fields=[tr.field(each) for each in program.root])
    m.instance(ROOT, ROOT)
    m.setup = tr.statements(program.setup)
    for each in program.asserts:
        m.check(tr.expr(each.test), owner=ROOT, text=each.origin)
    m.sites = tr.sites
    return m


def _input(tr, value):
    """The value of an input as the oracle takes it, in canonical units."""
    if isinstance(value, Quantity):
        return E('const', _exact(value.number) * tr.scale(value.unit))
    if isinstance(value, refs.EnumValue):
        return value.member
    if isinstance(value, refs.Distribution):
        return tr.distribution(value)
    return value


def config_of(program, configuration):
    """The oracle's configuration of one run of a program."""
    tr = _Translation(program)
    c = configuration
    return Config(
        mode=c.mode,
        seed=c.seed or 0,
        horizon=_exact(c.request.horizon),
        inputs={f'{each.member}.{each.name}': _input(tr, each.value) for each in c.inputs},
        max_occurrences=c.limits.max_occurrences,
        max_active=c.limits.max_active,
        max_rounds=c.limits.max_rounds,
        crossing=_exact(c.numerics.crossing),
        rtol=_exact(c.numerics.rtol),
        atol_factor=_exact(c.numerics.atol_factor),
    )


def run_of(program, configuration, stops=()):
    """Run a program on the oracle: the run, and the failure that stopped it, or None. Each stop is
    (origin, occurrence or None, edits): the run stops at that breakpoint (`Config.breakpoints`),
    which then leaves the list, makes each edit, a `record.Key` of a stored value of a member or an
    occurrence and its new value in the value's declared unit, and resumes. A stop that the run
    never reaches is a RunFailed."""
    try:
        run = Run(model_of(program), config_of(program, configuration))
    except RunFailed as e:
        return None, e
    run.breakpoints = [(origin, occurrence) for origin, occurrence, _ in stops]
    try:
        run.run()
        for origin, occurrence, edits in stops:
            if run.paused is None:
                raise RunFailed(f'the run never stops at {origin}')
            run.breakpoints.remove((origin, occurrence))
            for key, value in edits:
                (name,) = key.steps
                exact = (
                    _exact(value) * scale_at(program, key)
                    if isinstance(value, int | float | Fraction)
                    else value
                )
                run.edit(key.owner, name, exact)
            run.resume()
    except RunFailed as e:
        return run, e
    return run, None


def _key_node(key):
    """A key of a record as a path of the oracle: from a member (the root is `''`) or from an
    occurrence (`tank.receive#0`: the receiver, the event and the start number from 0)."""
    if '#' in key.owner:
        head, number = key.owner.rsplit('#', 1)
        receiver, event = head.rsplit('.', 1)
        node = E('occurrence', receiver, event, int(number))
    else:
        node = E('member', key.owner)
    for step in key.steps:
        node = E('attr', node, step)
    return node


def _names(template):
    """The values, flows, events and solvers of a template, by name."""
    groups = (template.values, template.flows, template.events, template.solvers)
    return {part.name: part for group in groups for part in group}


def scale_at(program, key):
    """The scale of the declared unit of the value at a key: of a value its type's unit, of a flow's
    rate, request or capacity the flow's unit, of an endpoint's its store's unit per hour (time is in
    hours, at scale 1), of a solver's unknown its type's unit; 1 for a plain number or no number."""

    def scale(unit):
        return Fraction(1) if unit == '' else Fraction(program.unit(unit).scale)

    owner = key.owner
    if '#' in owner:
        receiver, event = owner.rsplit('#', 1)[0].rsplit('.', 1)
        found = next(e for e in program.member(receiver)[0].events if e.name == event)
        names = {part.name: part for part in (*found.params, *found.locals)}
    elif owner == ROOT:
        names = {value.name: value for value in program.root}
    else:
        names = _names(program.member(owner)[0])
    at = None  # the part that the steps so far name
    for step in key.steps:
        if at is None or (isinstance(at, p.Value) and at.kind == p.LINK):
            if at is not None:  # a link goes on to the member that it names
                names = _names(program.template(at.type.template))
            at = names.get(step)
            if at is None:  # a built-in field of an occurrence: `started` is a time
                return Fraction(1)
        elif isinstance(at, p.Value) and step in ('outflow', 'inflow'):
            at = scale(at.type.unit)
        elif isinstance(at, p.Flow) and at.kind == p.LEGS:
            at = (
                Fraction(1) if step == 'served_fraction' else next(leg for leg in at.legs if leg.name == step)
            )
        elif isinstance(at, p.Flow) and step in ('actual_rate', 'request', 'capacity'):
            at = scale(at.unit)
        elif isinstance(at, p.Solver):
            at = next(u for u in at.unknowns if u.name == step)
    if isinstance(at, p.Value):
        return scale(at.type.unit) if isinstance(at.type, p.Number) else Fraction(1)
    return at if isinstance(at, Fraction) else Fraction(1)


def value_at(run, program, key, t):
    """The value at a key of the record at time t, after the last round at that time, stated in the
    declared unit of that value."""
    value = run.read(_key_node(key), at=t)
    return value / scale_at(program, key) if isinstance(value, Fraction) else value


def values_at(run, program, keys, times):
    """One series per record key, in its declared unit, preserving the order of the times."""
    columns = {key: [] for key in keys}
    if not columns:
        return columns
    nodes = [_key_node(key) for key in columns]
    scales = [scale_at(program, key) for key in columns]
    for at in times:
        for column, value, scale in zip(columns.values(), run.read_many(nodes, at), scales, strict=True):
            column.append(value / scale if isinstance(value, Fraction) else value)
    return columns


def traced(run, kind, part):
    """The (time, round) of each entry of the trace of a kind of the record (`commit`, `finish`, ...)
    for a part that its origin names, in order."""
    mine = KINDS[kind]
    return [(entry.t, entry.round) for entry in run.trace if entry.kind == mine and entry.origin == part]
