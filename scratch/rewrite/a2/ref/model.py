"""The description of a model: plain records, and nothing that runs.

A model is built in Python (there is no parser here). Everything in this file is data: an
expression is a tree of `E` nodes, a statement is a small record, and a template lists its fields,
flows, events and solvers. `ref/run.py` and its helpers run a description; they add nothing to it.

Numbers are exact (`fractions.Fraction`). The interpreter has no unit algebra: a model is written
in one coherent set of working units (L, h, L/h, g, W, Wh in the cases). The one place where a unit
matters is the reference scale of the least-distance step, which `Model.scales` holds by dimension.
"""

from dataclasses import dataclass, field
from fractions import Fraction


def number(x):
    """An exact number from an int, a Fraction, or a decimal string or float such as 0.5."""
    if isinstance(x, bool):
        return x
    if isinstance(x, (int, Fraction)):
        return Fraction(x)
    if isinstance(x, float):
        return Fraction(str(x))
    return x


class E:
    """One node of an expression: a kind and its arguments. Operators build larger nodes."""

    __slots__ = ('_k', '_a')

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
        v = a[0]
        return 'none' if v is None else str(v).lower() if isinstance(v, bool) else str(v)
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
    return f'{k}({", ".join(show(x) if isinstance(x, E) else repr(x) for x in a)})'


# --- names that an expression starts from -----------------------------------------------------------

this = E('this')  # the owning or receiving entity
t = E('t')  # the time of the run
none = E('const', None)  # the absent value


class _Names:
    """`N.amount` is the bare name `amount`: a parameter, a local, an input of a solver, a capture of
    a trigger, or a top-level entity, template or table."""

    def __getattr__(self, name):
        return E('name', name)


N = _Names()
SOURCE = E('name', 'SOURCE')
SINK = E('name', 'SINK')


def fn(name, *args):
    return E('fn', name, tuple(lit(a) for a in args))


def fmax(*args):
    return fn('max', *args)


def fmin(*args):
    return fn('min', *args)


def fsum(c):
    return fn('sum', c)


def count(c):
    return fn('count', c)


def any_(c):
    return fn('any', c)


def all_(c):
    return fn('all', c)


def since(event):
    return fn('since', event)


def elapsed(state):
    return fn('elapsed', state)


def delayed(x, delay):
    return fn('delayed', x, delay)


def if_(cond, then, other):
    return E('if', lit(cond), lit(then), lit(other))


def in_(x, lo, hi):
    return E('in', lit(x), lit(lo), lit(hi))


def formula(expr):
    """A retained calculation: read again at each use."""
    return E('formula', lit(expr))


def coll(*items):
    """The literal collection `<a, b>`."""
    return E('coll', tuple(lit(i) for i in items))


def priority(*items):
    return E('priority', tuple(lit(i) for i in items))


def proportional():
    return E('proportional')


def uniform(lo, hi):
    return E('dist', 'uniform', (lit(lo), lit(hi)))


def normal(mean, std):
    return E('dist', 'normal', (lit(mean), lit(std)))


def choose(name, *options):
    """An actor's choice among `options`: each is a value, or a pair (value, guard)."""
    return E('choose', name, tuple((o[0], lit(o[1])) if isinstance(o, tuple) else (o, None) for o in options))


def chance(name, *outcomes):
    """A chance mechanism: each outcome is (value, probability) or (value, probability, guard)."""
    return E('chance', name, tuple((o[0], lit(o[1]), lit(o[2]) if len(o) > 2 else None) for o in outcomes))


def minimize(expr):
    return ('min', lit(expr))


def maximize(expr):
    return ('max', lit(expr))


# --- declarations --------------------------------------------------------------------------------


@dataclass
class Endpoint:
    """The settings of `store.outflow` or `store.inflow`."""

    capacity: object = None
    request: object = None
    allocation: object = None  # priority(...) or proportional(); None is proportional()


@dataclass
class Field:
    """A named value of an entity, or a local of an event.

    kind: 'value' (stored, captured once), 'input' (fixed for the run, may be overridden),
    'formula' (a retained calculation), 'link' (a reference to an entity).
    A stored number becomes a store when a flow or a `move` names it."""

    name: str
    init: object = None
    lo: object = None
    hi: object = None
    kind: str = 'value'
    readonly: bool = False
    dim: str = ''  # the dimension, for the reference scale of a solver unknown
    scale: object = None  # a declared scale of a solver unknown
    outflow: Endpoint = None
    inflow: Endpoint = None


def value(name, init=None, lo=None, hi=None, **kw):
    return Field(name, None if init is None else lit(init), _opt(lo), _opt(hi), **kw)


def inp(name, init=None, lo=None, hi=None, **kw):
    return Field(name, None if init is None else lit(init), _opt(lo), _opt(hi), kind='input', **kw)


def calc(name, expr, **kw):
    """`name = formula(expr)`."""
    return Field(name, lit(expr), kind='formula', **kw)


def link(name, target=None):
    return Field(name, target, kind='link')


def _opt(x):
    return None if x is None else lit(x)


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
    dim: str = ''  # the dimension of the rate, for the reference scale


def flow(name, source, sink, capacity=None, request=None, dim=''):
    return Flow(name, source, sink, _opt(capacity), _opt(request), dim=dim)


def route(name, a, b, capacity=None, request=None, dim=''):
    return Flow(name, a, b, _opt(capacity), _opt(request), reversible=True, dim=dim)


def legs(name, *the_legs):
    return Flow(name, legs=tuple(the_legs))


def leg(name, source, sink, request=None, capacity=None):
    return Leg(name, source, sink, _opt(request), _opt(capacity))


# --- statements of a stage --------------------------------------------------------------------------


@dataclass
class Assign:
    target: E
    op: str  # '=', '+=' or '-='
    value: E


@dataclass
class Start:
    """`path.start(args)`: on one bound event, or on each member of a collection."""

    event: E
    args: tuple = ()


@dataclass
class Move:
    """`move amount from source to destination`."""

    amount: E
    source: E
    destination: E


@dataclass
class Switch:
    """Evaluate the selector once and run the matching case, or `default`."""

    selector: E
    cases: dict
    default: list = None


def set_(target, expr):
    return Assign(target, '=', lit(expr))


def add(target, expr):
    return Assign(target, '+=', lit(expr))


def sub(target, expr):
    return Assign(target, '-=', lit(expr))


def start(event, *args):
    return Start(event, tuple(lit(a) for a in args))


def move(amount, source, destination):
    return Move(lit(amount), source, destination)


def switch(selector, cases, default=None):
    return Switch(lit(selector), cases, default)


# --- events ------------------------------------------------------------------------------------------


@dataclass
class After:
    """`after delay [when guard]:` and the statements of its stage."""

    delay: E
    body: list = field(default_factory=list)
    guard: E = None


@dataclass
class Until:
    """`until condition`: a gate between stages."""

    condition: E


def after(delay, body=(), when=None):
    return After(lit(delay), list(body), None if when is None else lit(when))


def until(condition):
    return Until(lit(condition))


@dataclass
class Trigger:
    """`when condition:` under an event. A firing takes its captures, then runs its starts.
    reset: None (the condition must become false), ('when', condition) or ('after', duration)."""

    when: E
    starts: list = field(default_factory=list)
    captures: list = field(default_factory=list)  # (name, expression) pairs
    reset: tuple = None


def trigger(when, starts=(), captures=(), reset=None):
    if reset is not None:
        reset = (reset[0], lit(reset[1]))
    return Trigger(lit(when), list(starts), [(n, lit(e)) for n, e in captures], reset)


@dataclass
class Event:
    name: str
    params: list = field(default_factory=list)
    locals: list = field(default_factory=list)
    flows: list = field(default_factory=list)
    triggers: list = field(default_factory=list)
    steps: list = field(default_factory=list)


def event(name, params=(), locals=(), flows=(), triggers=(), steps=()):
    return Event(name, list(params), list(locals), list(flows), list(triggers), list(steps))


# --- solvers ---------------------------------------------------------------------------------------


@dataclass
class Unknown:
    """A new unknown declared on a solver: `care: h in [0 h, available]`."""

    name: str
    lo: object = None
    hi: object = None
    init: object = None  # a written initializer is the preferred value; without one it is zero
    dim: str = ''
    scale: object = None


def unknown(name, lo=None, hi=None, init=None, **kw):
    return Unknown(name, _opt(lo), _opt(hi), _opt(init), **kw)


@dataclass
class Solver:
    name: str
    inputs: dict = field(default_factory=dict)
    solve_for: list = field(default_factory=list)  # paths, or Unknown records
    constraints: list = field(default_factory=list)
    objective: list = field(default_factory=list)  # ('min' | 'max', expression), in written order


def solver(name, inputs=None, solve_for=(), constraints=(), objective=()):
    return Solver(name, {k: lit(v) for k, v in (inputs or {}).items()}, list(solve_for),
                  [lit(c) for c in constraints], list(objective))


# --- templates, instances, the model ---------------------------------------------------------------


@dataclass
class Template:
    name: str
    fields: list = field(default_factory=list)
    flows: list = field(default_factory=list)
    events: list = field(default_factory=list)
    solvers: list = field(default_factory=list)
    sees: list = field(default_factory=list)  # what a human player of this actor is shown


@dataclass
class Instance:
    """One member of a template. `id` is its stable name (`tank`, or `sites.clinic` for a row)."""

    id: str
    template: str
    values: dict = field(default_factory=dict)  # inputs, start values and links of this member


@dataclass
class Assert:
    condition: E
    owner: str = None  # the id of the instance that `this` names, if any
    text: str = ''


@dataclass
class Model:
    templates: dict = field(default_factory=dict)
    instances: list = field(default_factory=list)
    setup: list = field(default_factory=list)  # statements of the setup scope: writes and starts
    asserts: list = field(default_factory=list)
    scales: dict = field(default_factory=dict)  # dimension -> one canonical unit, in working units

    def template(self, name, fields=(), flows=(), events=(), solvers=(), sees=()):
        self.templates[name] = Template(name, list(fields), list(flows), list(events), list(solvers), list(sees))
        return self.templates[name]

    def instance(self, id, template, **values):
        self.instances.append(Instance(id, template, values))
        return E('name', id)

    def entity(self, name, fields=(), flows=(), events=(), solvers=(), sees=()):
        """An entity written on its own: a template with one member of the same name."""
        self.template(name, fields, flows, events, solvers, sees)
        return self.instance(name, name)

    def check(self, condition, owner=None, text=''):
        self.asserts.append(Assert(lit(condition), owner, text))


@dataclass
class Rules:
    """The rule taken for each open item. The default of each switch is the proposed rule; the
    other value is the alternative of its ruling in FINDINGS.md."""

    stage_order: str = 'age'  # 'age' | 'scheduled'
    broadcast: str = 'key'  # 'key' | 'creation'
    round_writes: str = 'sequential'  # 'sequential' | 'isolated'
    refire: str = 'budget'  # 'budget' | 'once'
    setup: str = 'round_zero'  # 'round_zero' | 'starts_first'
    none: str = 'propagate'  # 'propagate' | 'strict'
    empty_minmax: str = 'none'  # 'none' | 'error'
    elapsed: str = 'net'  # 'net' | 'every_write'
    delayed_zero: str = 'committed'  # 'committed' | 'own_writes'
    finished: str = 'frozen'  # 'frozen' | 'builtin'
    saved_occurrence: str = 'pinned'  # 'pinned' | 'follows'
    tiers: str = 'waits'  # 'waits' | 'latest' | 'earliest'
    pause: str = 'before_commit'  # 'before_commit' | 'split'
    asserts: str = 'always'  # 'always' | 'rounds' | 'start'
    report: str = 'record'  # 'record' | 'in_run'
    draws: str = 'keyed'  # 'keyed' | 'stream'
    opening: str = 'record'  # 'record' | 'refuse'
    retirement: str = 'fail'  # 'fail' | 'dispose'
    move_readonly: str = 'allowed'  # 'allowed' | 'refused'
    local_order: str = 'flows_last'  # 'flows_last' | 'written'
    stale_result: str = 'last_settled'  # 'last_settled' | 'error'
    flow_scale: str = 'canonical'  # 'canonical' | 'working'


@dataclass
class Config:
    """One execution: the mode, the seed, the overrides, the choices and the limits."""

    mode: str = 'median'  # 'median' | 'sampled'
    seed: int = 0
    horizon: object = None
    inputs: dict = field(default_factory=dict)  # 'entity.field' -> value
    choices: dict = field(default_factory=dict)  # the key of a decision -> the chosen value
    report: list = field(default_factory=list)  # (label, expression, times) that a caller asks for
    max_rounds: int = 100  # rounds at one time
    max_active: int = 1000  # occurrences of one bound event that run at once
    rules: Rules = field(default_factory=Rules)
