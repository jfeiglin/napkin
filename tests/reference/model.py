"""The description of a model for the oracle: plain records, and nothing that runs.

A model is built in Python (there is no parser here). Everything in this file is data: an
expression is a tree of `E` nodes, a statement is a small record, and a template lists its fields,
flows, events and solvers. `run.py` and its helpers run a description; they add nothing to it.

Numbers are exact (`fractions.Fraction`) and stand in one canonical unit for each dimension: L for
volume, h for time, g for mass, W for power, Wh (= W * h) for energy, and one for each count.
`q(4, 'kW')` converts a written quantity to that unit when the model is built, and a reader
converts a result back (`Run.read(..., unit='kW')`). So every rate of the least-distance step is
divided by one canonical unit of its dimension, whatever unit the model was written in. The oracle
checks no dimension: that is the compiler's work.

There is no `none`: a field declared without a value fails when it is read (decision D4).

A model that `from_program.py` makes from a program of `napkin.program` also keeps the origin of
each event, step, trigger, solver and statement, the declared unit of each field, the program's table
of units and the site of each draw, so that the trace and the messages of a run name the
parts of the program, and a breakpoint names the place where a run stops (`Config.breakpoints`).
"""

from dataclasses import dataclass, field
from fractions import Fraction


def number(x):
    """An exact number from an int, a Fraction, or a float such as 0.5 (read as its decimal text).
    Anything else, such as a text or an enum member, is returned unchanged."""
    if isinstance(x, bool):
        return x
    if isinstance(x, (int, Fraction)):
        return Fraction(x)
    if isinstance(x, float):
        return Fraction(str(x))
    return x


class E:
    """One node of an expression: a kind and its arguments. Operators build larger nodes."""

    __slots__ = ('_a', '_k')

    def __init__(self, kind, *args):
        object.__setattr__(self, '_k', kind)
        object.__setattr__(self, '_a', args)

    def __setattr__(self, name, value):
        raise AttributeError('an expression node does not change')

    def __getattr__(self, name):
        if name.startswith('_'):
            raise AttributeError(name)
        return E('attr', self, name)

    def __call__(self, *args):
        if self._k != 'attr':
            raise TypeError('only a method of a path can be called')
        return E('call', self._a[0], self._a[1], tuple(lit(a) for a in args))

    def __repr__(self):
        return show(self)

    def __bool__(self):
        raise TypeError('an expression has no truth value while a model is built: use & | ~ and if_()')

    __hash__ = object.__hash__

    def _op(sym):
        return lambda a, b: E('op', sym, a, lit(b))

    def _rop(sym):
        return lambda a, b: E('op', sym, lit(b), a)

    __add__, __radd__ = _op('+'), _rop('+')
    __sub__, __rsub__ = _op('-'), _rop('-')
    __mul__, __rmul__ = _op('*'), _rop('*')
    __truediv__, __rtruediv__ = _op('/'), _rop('/')
    __eq__, __ne__ = _op('=='), _op('!=')
    __le__, __ge__, __lt__, __gt__ = _op('<='), _op('>='), _op('<'), _op('>')
    __and__, __or__ = _op('and'), _op('or')

    del _op, _rop

    def __neg__(self):
        return E('neg', self)

    def __invert__(self):
        return E('not', self)


def lit(x):
    """A Python value as an expression node."""
    return x if isinstance(x, E) else E('const', number(x))


def show(e):
    """The text of an expression, for messages."""
    if not isinstance(e, E):
        return repr(e)
    k, a = e._k, e._a
    if k == 'const':
        return str(a[0]).lower() if isinstance(a[0], bool) else str(a[0])
    if k in ('this', 't'):
        return k
    if k == 'name':
        return a[0]
    if k == 'attr':
        return f'{show(a[0])}.{a[1]}'
    if k == 'call':
        return f'{show(a[0])}.{a[1]}({", ".join(show(x) for x in a[2])})'
    if k == 'op':
        return f'({show(a[1])} {a[0]} {show(a[2])})'
    if k == 'neg':
        return f'-{show(a[0])}'
    if k == 'not':
        return f'not {show(a[0])}'
    if k == 'if':
        return f'({show(a[1])} if {show(a[0])} else {show(a[2])})'
    if k == 'in':
        return f'({show(a[0])} in [{show(a[1])}, {show(a[2])}])'
    if k == 'fn':
        return f'{a[0]}({", ".join(show(x) for x in a[1])})'
    if k == 'coll':
        return f'<{", ".join(show(x) for x in a[0])}>'
    if k == 'formula':
        return f'formula({show(a[0])})'
    if k == 'categorical':
        return f'categorical({", ".join(f"{m}: {show(p)}" for m, p in a[0])})'
    return f'{k}({", ".join(show(x) if isinstance(x, E) else repr(x) for x in a)})'


# --- units ---------------------------------------------------------------------------------------

# The scale of each unit name in the canonical unit of its dimension. A compound unit is written
# with `*` and `/` (decision D12): 'L/h', 'Wh/L', 'person*year'.
UNITS = {
    'h': 1,
    'min': Fraction(1, 60),
    's': Fraction(1, 3600),
    'day': 24,
    'days': 24,
    'year': 8760,
    'L': 1,
    'mL': Fraction(1, 1000),
    'g': 1,
    'kg': 1000,
    'W': 1,
    'kW': 1000,
    'Wh': 1,
    'kWh': 1000,
    'person': 1,
    'crew_h': 1,
    'work_unit': 1,
}


def scale_of(unit):
    """The size of one `unit` in canonical units: 'kW' is 1000, 'L/h' is 1, 'person*year' is 8760."""
    total, sign, word = Fraction(1), 1, ''
    for ch in unit.replace(' ', '') + '*':
        if ch in '*/':
            if word not in UNITS:
                raise KeyError(f'the oracle knows no unit {word!r} (in {unit!r})')
            total *= Fraction(UNITS[word]) ** sign
            sign, word = (1 if ch == '*' else -1), ''
        else:
            word += ch
    return total


def q(value, unit):
    """A written quantity, such as `q(4, 'kW')`, as a constant in canonical units."""
    return E('const', number(value) * scale_of(unit))


# --- names that an expression starts from -----------------------------------------------------------

this = E('this')  # the owning or receiving entity
t = E('t')  # the time of the run


class _Names:
    """`N.amount` is the bare name `amount`: a parameter, a local, an input of a solver, a capture of
    a trigger, or a top-level entity, template or table."""

    def __getattr__(self, name):
        return E('name', name)


N = _Names()
SOURCE = E('name', 'SOURCE')
SINK = E('name', 'SINK')


def fn(name, *args):
    """A call of a built-in function."""
    return E('fn', name, tuple(lit(a) for a in args))


def fmax(*args):
    """`max(...)` of scalars and collections."""
    return fn('max', *args)


def fmin(*args):
    """`min(...)` of scalars and collections."""
    return fn('min', *args)


def fsum(c):
    """`sum(c)`: zero in its unit over an empty collection."""
    return fn('sum', c)


def count(c):
    """`count(c)`: the members, or the true values of a Boolean projection."""
    return fn('count', c)


def any_(c):
    """`any(c)`: false over an empty collection."""
    return fn('any', c)


def all_(c):
    """`all(c)`: true over an empty collection."""
    return fn('all', c)


def since(event):
    """`since(e)`: the time since the latest start of a bound event."""
    return fn('since', event)


def elapsed(state):
    """`elapsed(s)`: the time since a stored state took its present value."""
    return fn('elapsed', state)


def if_(cond, then, other):
    """The conditional expression `then if cond else other`."""
    return E('if', lit(cond), lit(then), lit(other))


def in_(x, lo, hi):
    """`x in [lo, hi]`, both ends included."""
    return E('in', lit(x), lit(lo), lit(hi))


def formula(expr):
    """A retained calculation: read again at each use."""
    return E('formula', lit(expr))


def coll(*items):
    """The literal collection `<a, b>`."""
    return E('coll', tuple(lit(i) for i in items))


def priority(*items):
    """`priority(a, b, ...)`: the named connections served first to last."""
    return E('priority', tuple(lit(i) for i in items))


def proportional():
    """`proportional()`: the default sharing by fraction of each claim."""
    return E('proportional')


def uniform(lo, hi):
    """`uniform(min, max)`."""
    return E('dist', 'uniform', (lit(lo), lit(hi)))


def normal(mean, std):
    """`normal(mean, sd)`."""
    return E('dist', 'normal', (lit(mean), lit(std)))


def categorical(**outcomes):
    """`categorical(FIXED: 0.7, FAILED: 0.3)`, written `categorical(FIXED=0.7, FAILED=0.3)`. The
    order of the outcomes is their declared order."""
    return E('categorical', tuple((member, lit(p)) for member, p in outcomes.items()))


def minimize(expr):
    """An objective line `minimize(expr)`."""
    return ('min', lit(expr))


def maximize(expr):
    """An objective line `maximize(expr)`."""
    return ('max', lit(expr))


# --- declarations --------------------------------------------------------------------------------


@dataclass
class Endpoint:
    """The settings of `store.outflow` or `store.inflow`. A setting left out is not declared."""

    capacity: object = None
    request: object = None
    allocation: object = None  # priority(...) or proportional(); left out, it is proportional()


@dataclass
class Field:
    """A named value of an entity, or a local of an event.

    kind: 'value' (stored, captured once), 'input' (fixed for the run, may be overridden),
    'formula' (a retained calculation), 'link' (a reference to an entity). A field with no `init`
    has no value until a stage assigns one. A stored number becomes a store when a flow or a `move`
    names it. `lo` or `hi` may be left out: `in [0,]` has no upper bound (decision D8)."""

    name: str
    init: object = None
    lo: object = None
    hi: object = None
    kind: str = 'value'
    readonly: bool = False
    scale: object = None  # a declared scale of a solver unknown
    outflow: Endpoint = None
    inflow: Endpoint = None
    unit: str = ''  # the spelling of its declared unit, for messages


def _opt(x):
    return None if x is None else lit(x)


def value(name, init=None, lo=None, hi=None, **kw):
    """A stored field: `name = init in [lo, hi]`."""
    return Field(name, _opt(init), _opt(lo), _opt(hi), **kw)


def inp(name, init=None, lo=None, hi=None, **kw):
    """An input: fixed for the run, and a run may override it."""
    return Field(name, _opt(init), _opt(lo), _opt(hi), kind='input', **kw)


def calc(name, expr, **kw):
    """`name = formula(expr)`."""
    return Field(name, lit(expr), kind='formula', **kw)


def link(name, target=None):
    """A reference to an entity, given by its id."""
    return Field(name, target, kind='link')


@dataclass
class Leg:
    """One named transfer of a flow with several legs."""

    name: str
    source: E
    sink: E
    request: object = None
    capacity: object = None


@dataclass
class Flow:
    """`flow name: source -> sink`, `flow name: a <-> b` (reversible), or a flow with legs."""

    name: str
    source: E = None
    sink: E = None
    capacity: object = None
    request: object = None
    reversible: bool = False
    legs: tuple = ()


def flow(name, source, sink, capacity=None, request=None):
    """`flow name: source -> sink` with its capacity and request."""
    return Flow(name, source, sink, _opt(capacity), _opt(request))


def route(name, a, b, capacity=None, request=None):
    """`flow name: a <-> b`, one signed rate."""
    return Flow(name, a, b, _opt(capacity), _opt(request), reversible=True)


def legs(name, *the_legs):
    """A flow with several legs, each with its own request."""
    return Flow(name, legs=tuple(the_legs))


def leg(name, source, sink, request=None, capacity=None):
    """One leg of a flow with legs."""
    return Leg(name, source, sink, _opt(request), _opt(capacity))


# --- statements of a stage --------------------------------------------------------------------------


@dataclass
class Assign:
    """`target = value`, `target += value` or `target -= value`."""

    target: E
    op: str  # '=', '+=' or '-='
    value: E
    origin: str = ''


@dataclass
class Start:
    """`path.start(args)`: on one bound event, or on each member of a collection."""

    event: E
    args: tuple = ()
    origin: str = ''


@dataclass
class Move:
    """`move amount from source to destination`."""

    amount: E
    source: E
    destination: E
    origin: str = ''


@dataclass
class Branch:
    """`if condition:` with its body, and an optional `else:` body (decision D11)."""

    condition: E
    then: list
    other: list = field(default_factory=list)
    origin: str = ''


@dataclass
class Case:
    """One case of a `switch`: `VALUE:` or `VALUE when guard:`."""

    value: object
    body: list
    guard: E = None


@dataclass
class Switch:
    """Read the guards, then the selector once, and run the matching eligible case, or `default`."""

    selector: E
    cases: list
    default: list = None
    origin: str = ''


def set_(target, expr):
    """`target = expr`."""
    return Assign(target, '=', lit(expr))


def add(target, expr):
    """`target += expr`."""
    return Assign(target, '+=', lit(expr))


def sub(target, expr):
    """`target -= expr`."""
    return Assign(target, '-=', lit(expr))


def start(event, *args):
    """`event.start(args)`."""
    return Start(event, tuple(lit(a) for a in args))


def move(amount, source, destination):
    """`move amount from source to destination`."""
    return Move(lit(amount), source, destination)


def branch(condition, then, other=()):
    """`if condition:` then, `else:` other."""
    return Branch(lit(condition), list(then), list(other))


def case(value, body, when=None):
    """`VALUE:` or `VALUE when guard:` and its body."""
    return Case(value, list(body), None if when is None else lit(when))


def switch(selector, *cases, default=None):
    """`switch selector:` with its cases and an optional `else` body."""
    return Switch(lit(selector), list(cases), None if default is None else list(default))


# --- events ------------------------------------------------------------------------------------------


@dataclass
class After:
    """`after delay [when guard]:` and the statements of its stage."""

    delay: E
    body: list = field(default_factory=list)
    guard: E = None
    origin: str = ''


@dataclass
class Until:
    """`until condition`: a gate between stages."""

    condition: E
    origin: str = ''


def after(delay, body=(), when=None):
    """`after delay [when guard]:` and its stage."""
    return After(lit(delay), list(body), None if when is None else lit(when))


def until(condition):
    """`until condition`."""
    return Until(lit(condition))


@dataclass
class Trigger:
    """`when condition:` under an event. A firing takes its captures, then runs its starts.
    reset: None (the condition must become false), ('when', condition) or ('after', duration)."""

    when: E
    starts: list = field(default_factory=list)
    captures: list = field(default_factory=list)  # (name, expression) pairs
    reset: tuple = None
    origin: str = ''


def trigger(when, starts=(), captures=(), reset=None):
    """`when condition:` with its starts, captures and reset."""
    if reset is not None:
        reset = (reset[0], lit(reset[1]))
    return Trigger(lit(when), list(starts), [(n, lit(e)) for n, e in captures], reset)


@dataclass
class Event:
    """An event declared on a template. `locals` holds its local fields and flows in written order
    (decision D14)."""

    name: str
    params: list = field(default_factory=list)
    locals: list = field(default_factory=list)
    triggers: list = field(default_factory=list)
    steps: list = field(default_factory=list)
    origin: str = ''


def event(name, params=(), locals=(), triggers=(), steps=()):
    """An event with its parameters, its locals and flows in written order, its triggers and steps."""
    return Event(name, list(params), list(locals), list(triggers), list(steps))


# --- solvers ---------------------------------------------------------------------------------------


@dataclass
class Unknown:
    """A new unknown declared on a solver: `care: h in [0 h, available]`."""

    name: str
    lo: object = None
    hi: object = None
    init: object = None  # a written initializer is the preferred value; without one it is zero
    scale: object = None


def unknown(name, lo=None, hi=None, init=None, scale=None):
    """A new unknown of a solver."""
    return Unknown(name, _opt(lo), _opt(hi), _opt(init), _opt(scale))


@dataclass
class Solver:
    """A solver: `inputs`, `solve_for`, `constraints` and an optional `objective`."""

    name: str
    inputs: dict = field(default_factory=dict)
    solve_for: list = field(default_factory=list)  # paths, or Unknown records
    constraints: list = field(default_factory=list)
    objective: list = field(default_factory=list)  # ('min' | 'max', expression), in written order
    origin: str = ''


def solver(name, inputs=None, solve_for=(), constraints=(), objective=()):
    """A solver; see `Solver`."""
    return Solver(
        name,
        {k: lit(v) for k, v in (inputs or {}).items()},
        list(solve_for),
        [lit(c) for c in constraints],
        list(objective),
    )


# --- templates, instances, the model ---------------------------------------------------------------


@dataclass
class Template:
    """The shared declarations of the entities of one kind."""

    name: str
    fields: list = field(default_factory=list)
    flows: list = field(default_factory=list)
    events: list = field(default_factory=list)
    solvers: list = field(default_factory=list)


@dataclass
class Instance:
    """One member of a template. `id` is its stable name (`tank`, or `sites.clinic` for a row)."""

    id: str
    template: str
    values: dict = field(default_factory=dict)  # inputs, start values and links of this member


@dataclass
class Assert:
    """An assertion on the state of the run."""

    condition: E
    owner: str = None  # the id of the instance that `this` names, if any
    text: str = ''


@dataclass
class Model:
    """A whole model: templates, instances, the setup statements and the assertions."""

    templates: dict = field(default_factory=dict)
    instances: list = field(default_factory=list)
    setup: list = field(default_factory=list)  # statements of the setup scope: writes and starts
    asserts: list = field(default_factory=list)
    units: dict = field(default_factory=dict)  # spelling -> scale, when the model came from a program
    sites: dict = field(default_factory=dict)  # id of a draw node -> its site in a program

    def template(self, name, fields=(), flows=(), events=(), solvers=()):
        """Declare a template."""
        self.templates[name] = Template(name, list(fields), list(flows), list(events), list(solvers))
        return self.templates[name]

    def instance(self, id, template, **values):
        """Declare a member of a template; returns its name as an expression."""
        self.instances.append(Instance(id, template, values))
        return E('name', id)

    def entity(self, name, fields=(), flows=(), events=(), solvers=()):
        """An entity written on its own: a template with one member of the same name."""
        self.template(name, fields, flows, events, solvers)
        return self.instance(name, name)

    def check(self, condition, owner=None, text=''):
        """Declare an assertion."""
        self.asserts.append(Assert(lit(condition), owner, text))


@dataclass
class Config:
    """One execution: the mode, the seed, the overrides, the limits and the breakpoints.

    The three limits protect a run (decision D6). Each breakpoint is (origin, occurrence): the run stops before the part of that origin (a statement
    in a stage, a stage, or an event, at the first stage of each of its occurrences) runs for that
    occurrence, or for any with None (`Run.resume`)."""

    mode: str = 'median'  # 'median' | 'sampled'
    seed: int = 0
    horizon: object = None
    inputs: dict = field(default_factory=dict)  # 'entity.field' -> value
    max_occurrences: int = 1_000_000  # starts of one bound event over the run
    max_active: int = 100_000  # occurrences of one bound event alive at once
    max_rounds: int = 1_000  # rounds at one time
    breakpoints: list = field(default_factory=list)  # (origin, occurrence or None)
