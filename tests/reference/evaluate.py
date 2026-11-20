"""Reading an expression against a state.

One evaluator serves four readers:

- a stage, a guard or an initializer reads plain values at the present instant;
- a report reads the same way from a recorded frame;
- the assembly of a solve reads its own unknowns as symbols (`Lin`), so that a constraint or an
  objective comes out as rows;
- the search for the next moment reads `t`, each moving store and each moving rate as a polynomial
  in the time since the moment (mode 'germ'). A comparison then answers for the instants just
  after the moment, and notes the first time at which its answer can change.

There is no absent value (decision D4). A field declared without a value fails when it is read; a
setting of a flow or an endpoint that the model left out reads as its default (a request of zero,
proportional sharing) or fails (a capacity, which then sets no limit). A computed result read in a
stage after its inputs changed in the round fails too (decision D5): `Run.check_stale`.
"""

from dataclasses import dataclass, field
from fractions import Fraction
from types import SimpleNamespace

from .errors import Diagnostic, NotCovered, RunFailed
from .model import E, show
from .order import Lin, Rel, relation
from .poly import Poly, plain, poly

# --- what an expression can name while a model runs -------------------------------------------------


@dataclass(eq=False)
class Ent:
    """One entity of the run."""

    id: str
    template: object
    number: int


@dataclass(eq=False)
class Occ:
    """One occurrence: one start of a bound event."""

    number: int
    ent: Ent
    event: object
    ordinal: int  # 1 for the first start of this bound event, 2 for the second
    args: tuple
    step: int = 0
    due: object = None  # the time of its next stage, when one is scheduled
    waiting: bool = False  # at an `until` gate

    @property
    def label(self):
        """The name of the occurrence, such as `grinder.refill#2`."""
        return f'{self.ent.id}.{self.event.name}#{self.ordinal}'


@dataclass(frozen=True)
class Cell:
    """A stored value: a field of an entity, a local of an occurrence, a setting of a flow."""

    owner: object
    name: str


@dataclass(frozen=True)
class End:
    """`store.outflow` or `store.inflow`."""

    cell: Cell
    side: str


@dataclass(frozen=True)
class Res:
    """A computed result: ('rate', flow), ('frac', flow), ('cell', cell) or ('local', solver, name)."""

    var: tuple


@dataclass(frozen=True)
class Sol:
    """A solver declared on an entity."""

    ent: Ent
    name: str


@dataclass(eq=False)
class Bound:
    """An event bound to its receiver."""

    ent: Ent
    event: object


@dataclass(eq=False)
class FlowRT:
    """A flow of the run. kind: 'directed', 'reversible' or 'legs'."""

    number: int
    decl: object
    owner: object
    scope: object
    kind: str
    src: object = None  # a Cell, or None for SOURCE
    dst: object = None  # a Cell, or None for SINK
    legs: dict = field(default_factory=dict)
    label: str = ''


@dataclass(eq=False)
class LegRT:
    """One leg: `forward` or `backward` of a reversible flow, or a named leg."""

    number: int
    flow: FlowRT
    name: str
    src: object
    dst: object
    decl: object = None

    @property
    def label(self):
        """The name of the leg, such as `net.link.forward`."""
        return f'{self.flow.label}.{self.name}'


@dataclass
class Scope:
    """Where names resolve: the receiver, the occurrence, and extra names (captures, solver inputs)."""

    this: object = None
    occ: object = None
    extra: dict = field(default_factory=dict)


@dataclass(eq=False)
class FormulaV:
    """A retained calculation with the scope that it was written in."""

    expr: E
    scope: Scope


@dataclass(eq=False)
class Pending:
    """A starting value that setup has not computed yet."""

    compute: object
    busy: bool = False


class Unset:
    """What a field declared without a value holds. It is no model value: a read of it fails."""

    def __repr__(self):
        return 'unset'


UNSET = Unset()


@dataclass(frozen=True)
class Failed:
    """The recorded reason why a formula of an occurrence could not be evaluated at its finish
    (decision D7). A read of the frozen field raises it again."""

    reason: str


@dataclass(frozen=True)
class Dist:
    """A distribution. For 'categorical', `params` holds (member, probability) pairs in declared order."""

    kind: str
    params: tuple


@dataclass(frozen=True)
class Alloc:
    """An allocation value: priority classes of connections, first class first."""

    classes: tuple


class Coll:
    """A collection: (key, member, value) for each member, in creation order.
    `value` is the member, or what a projection of a field gave for it."""

    __slots__ = ('items',)

    def __init__(self, items):
        self.items = tuple(items)


class _Boundary:
    def __init__(self, name):
        self.name = name

    def __repr__(self):
        return self.name


SOURCE, SINK = _Boundary('SOURCE'), _Boundary('SINK')
ITEM = '<item>'  # the bare name of the member that the test of a `where` is about; no model can spell it
# The failure of a membership whose interval is reversed when it is read, by the words that every
# evaluator of a program gives it.
REVERSED = 'the interval of a membership test is reversed'


class NeedsSettle(Exception):
    """A delay reads a computed result: its evaluation finishes after the round settles."""


class View:
    """The state that an expression reads: the live state of a run, or a recorded frame."""

    def __init__(self):
        self.t = Fraction(0)
        self.cells = {}  # Cell -> value
        self.results = {}  # var -> value of the last settlement
        self.occs = {}  # (Ent, event name) -> list of Occ
        self.live = []  # the flows that are connected now, in creation order
        self.entered = {}  # Cell -> the time at which it took its value
        self.bounds = {}  # Cell -> (lo, hi)
        self.levels = {}  # Cell -> Poly, the level of a moving store after this moment
        self.rates = {}  # var -> Poly, a rate after this moment

    def copy(self):
        """A copy that later changes of this view leave as it is: a frame of the record."""
        v = View()
        v.t, v.cells, v.results = self.t, dict(self.cells), dict(self.results)
        v.occs = {k: list(o) for k, o in self.occs.items()}
        v.live, v.entered, v.bounds = list(self.live), dict(self.entered), dict(self.bounds)
        v.levels, v.rates = dict(self.levels), dict(self.rates)
        return v


def label(x):
    """The name of a run object, for a message."""
    if isinstance(x, Cell):
        return f'{label(x.owner)}.{x.name}'
    if isinstance(x, End):
        return f'{label(x.cell)}.{x.side}'
    if isinstance(x, Sol):
        return f'{x.ent.id}.{x.name}'
    if isinstance(x, Ent):
        return x.id
    if isinstance(x, tuple):  # a var
        if x[0] == 'local':
            return f'{label(x[1])}.{x[2]}'
        return label(x[1]) + {'rate': '.actual_rate', 'frac': '.served_fraction', 'cell': ''}[x[0]]
    return getattr(x, 'label', None) or repr(x)


class Ev:
    """An evaluator: one state, one scope, one mode."""

    def __init__(
        self,
        run,
        view,
        scope,
        mode='instant',
        tx=None,
        unknowns=None,
        shared=None,
        may_draw=False,
        defer=False,
        owner=None,
    ):
        self.run, self.view, self.scope, self.mode, self.tx = run, view, scope or Scope(), mode, tx
        self.unknowns = unknowns
        self.shared = shared or SimpleNamespace(
            stops=[],
            reads=set(),
            results=set(),
            strict=False,
            positive=True,
            busy=[],
            may_draw=may_draw,
            defer=defer,
            in_formula=0,
            owner=owner,  # the firing of a trigger that executes this evaluation, if any (R-A2-17)
        )

    def fork(self, scope):
        """The same evaluator in another scope."""
        return Ev(self.run, self.view, scope, self.mode, self.tx, self.unknowns, self.shared)

    # --- the three ways to read ------------------------------------------------------------------

    def ref(self, e):
        """What an expression names: a cell, a flow, a collection, or a plain value."""
        if e._k == 'call':  # a call needs its node: it is the site of a draw
            return self._call(e, *e._a)
        return getattr(self, '_' + e._k)(*e._a)

    def val(self, e):
        """The value of an expression."""
        return self.deref(self.ref(e))

    def num(self, e):
        """The value of an expression that must be a number."""
        v = e if not isinstance(e, E) else self.val(e)
        if isinstance(v, (bool, str)) or not isinstance(v, (Fraction, Poly, Lin, int)):
            raise RunFailed(f'{show(e)} must be a number, and is {v!r}')
        return v

    def truth(self, e):
        """A condition that decides something: it must be yes or no."""
        v = self.val(e)
        if not isinstance(v, bool):
            raise RunFailed(f'the condition {show(e)} is not yes or no: {v!r}')
        return v

    def deref(self, x):
        """The value that a reference names: a cell read, a result read, or itself."""
        if isinstance(x, Cell):
            return self.cell(x)
        if isinstance(x, Res):
            return self.result(x.var)
        return x

    def raw(self, c):
        """What a cell holds, as stored: a value, a formula, or None for a setting left out."""
        if self.tx is not None and c in self.tx.writes:
            v = self.tx.writes[c]
        elif c in self.view.cells:
            v = self.view.cells[c]
        else:
            raise RunFailed(f'{label(c)} does not exist')
        return self.run.force(c) if isinstance(v, Pending) else v

    def cell(self, c):
        """The value of a cell: a stored value, a formula evaluated now, or an unknown of the solve."""
        if self.unknowns is not None and ('cell', c) in self.unknowns:
            return Lin.var(('cell', c))
        if c in self.run.solved_cells:
            return self.result(('cell', c))
        v = self.raw(c)
        self.shared.reads.add(c)
        if v is None:  # a setting of a flow or an endpoint that the model left out
            if c.name == 'request':
                return Fraction(0)
            if c.name == 'allocation':
                return Alloc(())
            raise RunFailed(f'{label(c)} is not declared: it sets no limit and has no value to read')
        if v is UNSET:
            raise RunFailed(f'{label(c)} is read before it has a value')
        if isinstance(v, Failed):
            raise RunFailed(v.reason)
        if isinstance(v, FormulaV):
            if c in self.shared.busy:
                raise Diagnostic(f'the formula {label(c)} reads itself')
            self.shared.busy.append(c)
            self.shared.in_formula += 1
            try:
                return self.fork(v.scope).val(v.expr)
            finally:
                self.shared.busy.pop()
                self.shared.in_formula -= 1
        if self.mode == 'germ' and c in self.view.levels:
            return plain(self.view.levels[c])
        return v

    def setting(self, c):
        """A setting of a flow or an endpoint as the network reads it: None when it was left out.
        Either way it is an input of the calculation that reads it."""
        self.shared.reads.add(c)
        if c not in self.view.cells and not (self.tx is not None and c in self.tx.writes):
            return None
        return None if self.raw(c) is None else self.cell(c)

    def result(self, var):
        """A computed result: a rate, a served fraction, or an unknown of a solver."""
        if self.unknowns is not None and var in self.unknowns:
            return Lin.var(var)
        if self.shared.defer:
            raise NeedsSettle()
        if var[0] in ('rate', 'frac') and var[1] not in self.view.live:
            return Fraction(0)  # a flow of a finished occurrence
        if self.view is self.run.view and self.run.phase in ('stages', 'conditions'):
            self.run.check_stale(var, self.tx)
        if self.run.settling:
            self.run.pull(var)
        if self.unknowns is not None:
            self.shared.results.add(var)  # a result of another calculation: its inputs are ours too
        if self.mode == 'germ' and var in self.view.rates:
            return plain(self.view.rates[var])
        if var in self.view.results:
            return self.view.results[var]
        if var[0] == 'cell':
            return self.view.cells[var[1]]
        raise RunFailed(f'{label(var)} is read before its first solve')

    # --- leaves ----------------------------------------------------------------------------------

    def _const(self, v):
        return v

    def _this(self):
        if self.scope.this is None:
            raise RunFailed('`this` has no entity here')
        return self.scope.this

    def _t(self):
        return Poly([self.view.t, 1]) if self.mode == 'germ' else self.view.t

    def _name(self, n):
        s, run = self.scope, self.run
        if n in s.extra:
            return s.extra[n]
        if s.occ is not None:
            c = Cell(s.occ, n)
            if c in self.view.cells or (self.tx is not None and c in self.tx.writes):
                return c
            if (s.occ, n) in run.flow_at:
                return run.flow_at[s.occ, n]
        if n in run.ents:
            return run.ents[n]
        if n in run.model.templates:
            return ('template', n)
        if n in run.tables:
            return ('table', n)
        if n == 'SOURCE':
            return SOURCE
        if n == 'SINK':
            return SINK
        raise RunFailed(f'the name {n} is not known here')

    def _attr(self, base, name):
        return self.attr(self.ref(base), name)

    def _member(self, id):
        """A member named by its id (`sites.clinic`), whatever names the scope has."""
        if id not in self.run.ents:
            raise RunFailed(f'no member is named {id!r}')
        return self.run.ents[id]

    def _instances(self, template):
        """`Template.instances`, keyed by creation number."""
        return Coll((x.number, x, x) for x in self.run.ents.values() if x.template.name == template)

    def _occurrence(self, receiver, event, n):
        """The start number n, from 0, of an event on a receiver: `tank.receive#0` in a key."""
        occs = self.view.occs.get((self._member(receiver), event), [])
        if n >= len(occs):
            raise RunFailed(f'{receiver}.{event}#{n} has not started by t = {self.view.t} h')
        return occs[n]

    def _where(self, source, test):
        """`source.where(test)`: the members for which the test holds, with their keys. The test
        reads the member as the bare name `ITEM`, and the enclosing scope as it is."""
        c = self.val(source)
        if not isinstance(c, Coll):
            raise RunFailed(f'{show(source)}.where(...) needs a collection')
        kept = []
        for item in c.items:
            scope = Scope(self.scope.this, self.scope.occ, {**self.scope.extra, ITEM: item[1]})
            if self.fork(scope).truth(test):
                kept.append(item)
        return Coll(kept)

    def attr(self, obj, name):
        """The field, flow, event, solver or setting called `name` of what `obj` names."""
        run, view = self.run, self.view
        if isinstance(obj, Cell):
            if name in ('outflow', 'inflow'):
                return End(obj, name)
            obj = self.cell(obj)
        if isinstance(obj, Res):
            obj = self.result(obj.var)
        if isinstance(obj, Coll):
            return Coll((k, m, self.attr(v, name)) for k, m, v in obj.items)
        if isinstance(obj, Ent):
            c = Cell(obj, name)
            if c in view.cells:
                return c
            if (obj, name) in run.flow_at:
                return run.flow_at[obj, name]
            for ev in obj.template.events:
                if ev.name == name:
                    return Bound(obj, ev)
            if any(s.name == name for s in obj.template.solvers):
                return Sol(obj, name)
        elif isinstance(obj, Occ):
            c = Cell(obj, name)
            if c in view.cells or (self.tx is not None and c in self.tx.writes):
                return c
            if (obj, name) in run.flow_at:
                return run.flow_at[obj, name]
        elif isinstance(obj, Bound):
            if name == 'occurrences':
                return Coll(
                    (view.cells[Cell(o, 'started')], o, o)
                    for o in view.occs.get((obj.ent, obj.event.name), ())
                )
        elif isinstance(obj, FlowRT):
            if name in obj.legs:
                return obj.legs[name]
            if obj.kind == 'legs':
                if name == 'served_fraction':
                    return Res(('frac', obj))
                raise Diagnostic(
                    f'{obj.label}.{name}: a flow with legs has no {name}; read a leg, or served_fraction'
                )
            if name == 'actual_rate':
                return Res(('rate', obj))
            if name in ('capacity', 'request'):
                return Cell(obj, name)
            if name in ('source', 'sink'):
                end = obj.src if name == 'source' else obj.dst
                return end if end is not None else (SOURCE if name == 'source' else SINK)
        elif isinstance(obj, LegRT):
            if name == 'actual_rate':
                return self.leg_rate(obj)
            if name == 'request':
                if obj.decl is not None:
                    return Cell(obj, 'request')
                q = self.cell(Cell(obj.flow, 'request'))  # a leg view of a reversible flow
                return self.pos(q if obj.name == 'forward' else -q)
            if name == 'capacity':
                return Cell(obj if obj.decl is not None else obj.flow, 'capacity')
            if name in ('source', 'sink'):
                return obj.src if name == 'source' else obj.dst
        elif isinstance(obj, End):
            if name == 'flows':
                return Coll((x.number, x, x) for x, _ in run.incident(view, obj))
            if name == 'actual_rate':
                return sum((self.leg_rate(x) for x, _ in run.incident(view, obj)), Fraction(0))
            if name in ('capacity', 'request', 'allocation'):
                c = Cell(obj, name)
                if c not in view.cells and not (self.tx is not None and c in self.tx.writes):
                    view.cells[c] = None  # a setting that the model left out, until a stage writes one
                return c
        elif isinstance(obj, Sol):
            return Res(('local', obj, name))
        elif isinstance(obj, Dist):
            return run.describe(obj, name)
        elif isinstance(obj, tuple) and obj[0] == 'template' and name == 'instances':
            return Coll((x.number, x, x) for x in run.ents.values() if x.template.name == obj[1])
        elif isinstance(obj, tuple) and obj[0] == 'table' and f'{obj[1]}.{name}' in run.ents:
            return run.ents[f'{obj[1]}.{name}']
        raise RunFailed(f'{label(obj)} has no {name}')

    def leg_rate(self, x):
        """The nonnegative rate of one connection: a directed flow, or one leg."""
        if isinstance(x, FlowRT):
            return self.result(('rate', x))
        if x.decl is None:
            rate = self.result(('rate', x.flow))
            return self.pos(rate if x.name == 'forward' else -rate)
        if x.flow not in self.view.live:
            return Fraction(0)
        return self.result(('frac', x.flow)) * self.cell(Cell(x, 'request'))

    def pos(self, x):
        """max(x, 0) in the mode of this evaluator."""
        if isinstance(x, Lin):
            return collapse(x.positive())
        if isinstance(x, Poly):
            return x if self.sign(x) > 0 else Fraction(0)
        return max(x, Fraction(0))

    def sign(self, d):
        """The sign of a difference. For a moving value: the sign just after the moment, and the
        first time at which it can change is noted as a stop."""
        d = plain(d)
        if not isinstance(d, Poly):
            return (d > 0) - (d < 0)
        root = d.first_root()
        if root is not None:
            self.shared.stops.append(root)
        return d.sign_after()

    # --- operators -------------------------------------------------------------------------------

    def _op(self, sym, a, b):
        if sym in ('and', 'or'):
            return self.logic(sym, a, b)
        x, y = self.val(a), self.val(b)
        if sym in ('==', '!=', '<=', '>=', '<', '>'):
            return self.compare(sym, x, y, (a, b))
        x, y = self.same_kind(x, y)
        try:
            if sym == '+':
                return collapse(x + y)
            if sym == '-':
                return collapse(x - y)
            if sym == '*':
                return collapse(x * y)
            return collapse(x / y)
        except ZeroDivisionError:
            raise RunFailed(f'a division by zero in {show(a)} / {show(b)}') from None
        except TypeError:
            raise RunFailed(f'{show(a)} {sym} {show(b)} cannot be computed from {x!r} and {y!r}') from None

    def same_kind(self, x, y):
        """Refuse to mix an unknown of a solve with a value that moves between moments."""
        if (isinstance(x, Lin) and isinstance(y, Poly)) or (isinstance(x, Poly) and isinstance(y, Lin)):
            raise NotCovered('a coefficient of a solve that moves between two moments')
        return x, y

    def compare(self, sym, x, y, texts):
        """A comparison: a relation of a solve, a yes or no, or the sign just after a moment."""
        if isinstance(x, Lin) or isinstance(y, Lin):
            self.same_kind(x, y)
            return relation(x, sym, y)
        plain_kinds = (bool, str, Ent, Occ, FlowRT, LegRT)
        if isinstance(x, plain_kinds) or isinstance(y, plain_kinds):
            if sym not in ('==', '!='):
                raise RunFailed(
                    f'{show(texts[0])} {sym} {show(texts[1])}: only == and != compare these values'
                )
            return (x is y or x == y) == (sym == '==')
        d = plain(poly(x) - poly(y)) if isinstance(x, Poly) or isinstance(y, Poly) else x - y
        if isinstance(d, Poly) and self.shared.strict:
            closed = sym in ('<=', '>=', '==')
            if closed != self.shared.positive:
                raise Diagnostic(
                    f'a strict threshold on a value that changes continuously: {show(texts[0])} {sym} '
                    f'{show(texts[1])} has no first instant; use an inclusive threshold'
                )
        s = self.sign(d)
        return {'==': s == 0, '!=': s != 0, '<=': s <= 0, '>=': s >= 0, '<': s < 0, '>': s > 0}[sym]

    def logic(self, sym, a, b):
        """`and` and `or`, read left to right; in a solve, a conjunction of relations."""
        x = self.val(a)
        if isinstance(x, (Rel, list)):
            if sym == 'or':
                raise Diagnostic('unsupported in a solver: a disjunction')
            return _rows(x) + _rows(self.val(b))
        if x is (sym == 'or'):
            return x  # true or ..., false and ...: the right side is not read
        y = self.val(b)
        if isinstance(y, (Rel, list)):
            if sym == 'or' or x is not True:
                raise Diagnostic('unsupported in a solver: a relation under a condition')
            return _rows(y)
        if not isinstance(x, bool) or not isinstance(y, bool):
            raise RunFailed(f'{show(a)} {sym} {show(b)} needs two yes-or-no values')
        return y

    def _neg(self, a):
        return collapse(-self.val(a))

    def _not(self, a):
        self.shared.positive = not self.shared.positive
        try:
            x = self.val(a)
        finally:
            self.shared.positive = not self.shared.positive
        if isinstance(x, (Rel, list)):
            raise Diagnostic('unsupported in a solver: not')
        return not x

    def _if(self, cond, then, other):
        c = self.val(cond)
        if isinstance(c, (Rel, list)):
            raise Diagnostic('unsupported in a solver: a choice that reads an unknown')
        return self.ref(then if c else other)

    def _in(self, x, lo, hi):
        """`lo <= x <= hi`, a chain of two comparisons that reads x once."""
        return self.between(self.val(x), self.val(lo), self.val(hi), x, lo, hi)

    def _within(self, x, lo, hi):
        """`x in [lo, hi]`, a membership (spec, "Units, comparisons and layout"): x and each end are
        read once, and an interval that is reversed when it is read fails the run by name, as reversed
        bounds are an error. Ends that move are compared just after the moment, and the first time at
        which they can cross is a stop, as for any comparison."""
        v, low, high = self.val(x), self.val(lo), self.val(hi)
        # Ends that are unknowns of a solve are relations, which no interval orders.
        if isinstance(low, (Fraction, Poly, int)) and isinstance(high, (Fraction, Poly, int)):
            moving = isinstance(low, Poly) or isinstance(high, Poly)
            gap = plain(poly(low) - poly(high)) if moving else low - high
            if self.sign(gap) > 0:
                raise RunFailed(f'{REVERSED}: {show(E("within", x, lo, hi))} reads [{low}, {high}]')
        return self.between(v, low, high, x, lo, hi)

    def between(self, v, low, high, x, lo, hi):
        first = self.compare('>=', v, low, (x, lo))
        second = self.compare('<=', v, high, (x, hi))
        if isinstance(first, Rel) or isinstance(second, Rel):
            return _rows(first) + _rows(second)
        return first and second

    def _formula(self, expr):
        return FormulaV(expr, self.scope)

    def _coll(self, items):
        members = [self.val(i) for i in items]
        return Coll((self.run.key_of(m, self.view), m, m) for m in members)

    def _dist(self, kind, params):
        return Dist(kind, tuple(self.num(p) for p in params))

    def _categorical(self, outcomes):
        """`categorical(FIXED: 1, FAILED: 3)`: nonnegative weights, scaled by their sum to the
        probabilities 1/4 and 3/4. Weights that are all zero stay as they are: a draw from them
        fails, as for eligible outcomes whose total is zero (`Run._outcome`), and a person may still
        pick an eligible outcome, since eligibility and probability are independent (D1)."""
        params = tuple((member, self.num(p)) for member, p in outcomes)
        if any(p < 0 for _, p in params):
            raise Diagnostic(
                f'categorical({", ".join(f"{m}: {p}" for m, p in params)}): the weights must be nonnegative'
            )
        total = sum(p for _, p in params)
        if total > 0:
            params = tuple((member, p / total) for member, p in params)
        return Dist('categorical', params)

    def _priority(self, items):
        classes = []
        for i in items:
            v = self.val(i)
            if isinstance(v, Coll):  # a keyed projection: lower keys first, equal keys share a class
                for key in sorted({k for k, _, _ in v.items}):
                    classes.append(tuple(self.deref(x) for k, _, x in v.items if k == key))
            else:
                classes.append((v,))
        return Alloc(tuple(classes))

    def _proportional(self):
        return Alloc(())

    # --- the producer of a value for a branch: a draw --------------------------------------------------

    def producer(self, node):
        """The distribution of `d.draw()`."""
        dist = self.val(node._a[0])
        if not isinstance(dist, Dist):
            raise RunFailed(f'{show(node)} needs a distribution, and reads {dist!r}')
        return dist

    def produce(self, node, eligible=None):
        """Execute a draw. `eligible` lists the outcomes that the guards of a `switch` allow; anywhere
        else every outcome is eligible."""
        if self.shared.in_formula or not self.shared.may_draw:
            raise Diagnostic(f'{show(node)}: a formula, a condition or a report cannot draw')
        return self.run.draw(self.producer(node), node, self, eligible)

    # --- methods of a path ---------------------------------------------------------------------------

    def _call(self, node, base, method, args):
        if method == 'draw':
            return self.produce(node)
        c = self.val(base)
        if not isinstance(c, Coll):
            raise RunFailed(f'{show(base)}.{method}(...) needs a collection')
        if method == 'where':
            name = args[0]._a[0]
            if len(args) == 1:
                keep = [self.deref(self.attr(m, name)) is True for _, m, _ in c.items]
            else:
                rhs = self.val(args[2])
                keep = [
                    self.compare(args[1]._a[0], self.deref(self.attr(m, name)), rhs, (args[0], args[2]))
                    for _, m, _ in c.items
                ]
            return Coll(i for i, k in zip(c.items, keep) if k)
        if method == 'by':
            return Coll((self.num(self.deref(self.attr(m, args[0]._a[0]))), m, v) for _, m, v in c.items)
        if method == 'at':
            x = self.num(args[0])
            found = None
            for item in c.items:  # the greatest key at or below x; of equal keys the later-created member
                gap = poly(x) - item[0] if isinstance(x, Poly) else x - item[0]
                if self.sign(gap) >= 0 and (found is None or item[0] >= found[0]):
                    found = item
            if found is None:
                at = x(0) if isinstance(x, Poly) else x
                empty = ' (the collection is empty)' if not c.items else ''
                raise RunFailed(f'{show(base)}.at({show(args[0])}): no member at or below {at}{empty}')
            return found[2]
        raise RunFailed(f'{show(base)}.{method}(...) is not a method of a collection')

    # --- functions ---------------------------------------------------------------------------------

    def _fn(self, name, args):
        if name in ('max', 'min'):
            return self.extreme(name, args)
        if name in ('sum', 'count', 'any', 'all'):
            return self.reduce(name, args[0])
        if name == 'since':
            b = self.val(args[0])
            occs = self.view.occs.get((b.ent, b.event.name), ()) if isinstance(b, Bound) else None
            if not occs:
                raise RunFailed(f'since({show(args[0])}) is read before the first occurrence')
            return self._t() - self.view.cells[Cell(occs[-1], 'started')]
        if name == 'elapsed':
            c = self.ref(args[0])
            if not isinstance(c, Cell):
                raise RunFailed(f'elapsed({show(args[0])}) needs a stored state')
            return self._t() - self.run.entered(c, self.tx, self.view)
        if name == 'abs':
            x = self.num(args[0])
            return x if self.sign(x) >= 0 else -x
        if name == 'clip':
            x, lo, hi = (self.num(a) for a in args)
            return lo if self.sign(x - lo) < 0 else hi if self.sign(x - hi) > 0 else x
        raise RunFailed(f'the function {name} is not known')

    def values(self, arg):
        """The values of a collection, or a scalar alone."""
        v = self.val(arg)
        return [self.deref(x) for _, _, x in v.items] if isinstance(v, Coll) else [v]

    def extreme(self, name, args):
        """`min` or `max` over scalars and the members of collections."""
        vs = [v for a in args for v in self.values(a)]
        if not vs:  # an empty collection and no scalar beside it: there is no value to give (D4)
            raise RunFailed(f'{name}({", ".join(show(a) for a in args)}) reads an empty collection')
        best = vs[0]
        for v in vs[1:]:
            if isinstance(best, Lin) or isinstance(v, Lin):
                if name == 'min':
                    raise Diagnostic('unsupported in a solver: min of an unknown (not convex)')
                best = collapse(best + (lin_of(v) - best).positive())
            elif (self.sign(plain(poly(v) - poly(best))) > 0) == (name == 'max'):
                best = v
        return best

    def reduce(self, name, arg):
        """`sum`, `count`, `any` or `all` over a collection."""
        c = self.val(arg)
        if not isinstance(c, Coll):
            raise RunFailed(f'{name}({show(arg)}) needs a collection')
        vs = [self.deref(x) for _, _, x in c.items]
        if name == 'count':
            if any(isinstance(v, (Fraction, int, Poly, Lin)) and not isinstance(v, bool) for v in vs):
                raise Diagnostic(f'count({show(arg)}) counts members or true values; use sum for a total')
            return Fraction(sum(1 for v in vs if v is not False))
        if name == 'sum':
            return collapse(sum(vs, Fraction(0)))  # zero over nothing
        if any(isinstance(v, (Rel, list)) for v in vs):
            if name == 'any':
                raise Diagnostic('unsupported in a solver: any(...)')
            return [r for v in vs if v is not True for r in _rows(v)]
        return any(vs) if name == 'any' else all(vs)  # false and true over nothing


def collapse(x):
    """A symbolic value that holds no unknown, or a constant polynomial, as its plain number."""
    if isinstance(x, Lin) and x.known:
        return x.k
    return plain(x)


def lin_of(x):
    """A number as a constant `Lin`; a `Lin` unchanged."""
    return x if isinstance(x, Lin) else Lin(k=x)


def _rows(x):
    """The relations of a constraint value. A plain `false` can never hold."""
    if isinstance(x, list):
        return x
    if isinstance(x, Rel):
        return [x]
    if x is True:
        return []
    return [Rel(Lin(k=1), '<=')]
