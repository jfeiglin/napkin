"""Running a description: what happens at one time, and between two times.

The run goes from moment to moment. A moment is a time at which something discrete can happen.

At a time, rounds (`Run._moment`). One round is:

1. *Stages.* The stages that are due at this time when the round begins run and commit, one after
   the other, the older occurrence first. A commit publishes the writes of the stage and registers
   the occurrences that it queued; an occurrence that has no step left finishes.
2. *Settle.* Rates and each affected solver, once (`ref.network.settle`).
3. *Delays.* A next delay that reads a computed result is finished with the settled result.
4. *Conditions.* Triggers, resets and gates are all read on the settled state; then the firings
   and the released gates take effect, in a fixed order.

A further round follows when anything is due at the same time or was registered in step 4.

Between two moments every rate is constant, or a known polynomial in time, and each store is
integrated exactly (`ref.network.motion`). The next moment is the earliest of: a stage that is due,
a reset timer, the first contact of a watched condition with its boundary, a store that meets a
bound, a key time of an `.at(t)` read, and the horizon.
"""

import dataclasses
import hashlib
import itertools
from collections import Counter
from fractions import Fraction
from statistics import NormalDist

from . import network
from .errors import Diagnostic, NotCovered, Paused, RunFailed
from .evaluate import Alloc, Bound, Cell, Coll, End, Ent, Ev, FlowRT, FormulaV, LegRT, NeedsSettle, Occ, Pending, Res, Scope, View, label
from .model import After, Assign, Config, E, Field, Flow, Move, Start, Switch, Until, lit, number, show
from .poly import Irrational, plain

_MISSING = object()
BUILTIN = ('started', 'done', 'active')


class Tx:
    """The uncommitted work of one stage: its writes, its moves and the starts that it queued."""

    def __init__(self, occ=None):
        self.occ = occ
        self.writes = {}
        self.changed = set()  # cells whose value some write of this stage changed
        self.kinds = {}  # cell -> 'set' or 'delta', for the alternative that isolates stages
        self.moves = []
        self.starts = []


@dataclasses.dataclass(eq=False)
class Trig:
    """The state of one trigger on one receiver."""

    ent: Ent
    event: object
    decl: object
    index: int
    armed: bool = True
    rearm_at: object = None
    caps: dict = dataclasses.field(default_factory=dict)
    blocked_at: object = None
    fired_at: object = None
    firings: int = 0

    @property
    def label(self):
        return f'{self.ent.id}.{self.event.name}.when[{self.index}]'


class Unavailable:
    """What a report shows for a read that has no value at that time."""

    def __init__(self, reason):
        self.reason = reason

    def __repr__(self):
        return f'unavailable ({self.reason})'

    def __eq__(self, other):
        return isinstance(other, Unavailable)

    __hash__ = None


class Run:
    def __init__(self, model, config=None, **options):
        self.model = model
        self.config = config or Config(**options)
        if self.config.horizon is not None:
            self.config.horizon = number(self.config.horizon)
        self.rules = self.config.rules
        self.view = View()
        self.ents, self.tables = {}, set()
        self.flow_at = {}  # (owner, name) -> FlowRT, for every flow ever made
        self.fields = {}  # Cell -> its declaration
        self.stores = set()  # cells that hold stock: an end of a flow or of a move
        self.triggers, self.scheduled, self.awaiting = [], [], []
        self.ledger, self.trace, self.frames, self.draws, self.decisions = [], [], [], [], []
        self.reported = {}
        self.solves, self.cache = Counter(), {}
        self.components, self.component_of, self.solved_cells, self.settling = [], {}, set(), None
        self.moving, self.stops = [], []
        self.flow_numbers, self.occ_numbers, self.sequence = itertools.count(1), itertools.count(1), itertools.count(1)
        self.stream = itertools.count(1)
        self.sites = _sites(model)
        self.error = self.paused = None
        self.phase = 'setup'
        self.round_written = set()
        self._setup()

    # --- setup -----------------------------------------------------------------------------------

    def _setup(self):
        m, cells = self.model, self.view.cells
        for i, inst in enumerate(m.instances, 1):
            if inst.id in self.ents:
                raise Diagnostic(f'two instances are named {inst.id}')
            self.ents[inst.id] = Ent(inst.id, m.templates[inst.template], i)
            if '.' in inst.id:
                self.tables.add(inst.id.split('.')[0])
        for inst in m.instances:  # starting values follow their dependencies, not the written order
            ent = self.ents[inst.id]
            for f in ent.template.fields:
                self.fields[Cell(ent, f.name)] = f
                cells[Cell(ent, f.name)] = Pending(lambda ent=ent, inst=inst, f=f: self._start_value(ent, inst, f))
        for c in list(cells):
            self.force(c)
        for ent in self.ents.values():
            for decl in ent.template.flows:
                self._make_flow(decl, ent, Scope(ent))
        for ent in self.ents.values():
            for f in ent.template.fields:
                for side in ('outflow', 'inflow'):
                    ep = getattr(f, side)
                    if ep is not None:
                        end = End(Cell(ent, f.name), side)
                        cells[Cell(end, 'capacity')] = self._prop(ep.capacity, Scope(ent))
                        cells[Cell(end, 'request')] = self._prop(ep.request, Scope(ent))
                        cells[Cell(end, 'allocation')] = None if ep.allocation is None else FormulaV(ep.allocation, Scope(ent))
            for ev in ent.template.events:
                self.view.occs[ent, ev.name] = []
                self.triggers += [Trig(ent, ev, tr, i) for i, tr in enumerate(ev.triggers)]

    def _start_value(self, ent, inst, f):
        scope = Scope(ent)
        ev = Ev(self, self.view, scope, may_draw=True)
        given = inst.values.get(f.name, _MISSING)
        cell = Cell(ent, f.name)
        if f.kind == 'link':
            target = f.init if given is _MISSING else given
            return self.ents[target] if isinstance(target, str) else None if target is None else ev.val(target)
        if f.kind == 'formula':
            return FormulaV(lit(f.init if given is _MISSING else given), scope)
        key = f'{ent.id}.{f.name}'
        if f.kind == 'input' and key in self.config.inputs:
            v = number(self.config.inputs[key])  # an override: the default is not evaluated, and draws nothing
        elif given is not _MISSING:
            v = ev.val(lit(given))
        else:
            v = None if f.init is None else ev.val(f.init)
        self._range(cell, f, ev, v)
        return v

    def _range(self, cell, f, ev, v):
        lo = None if f.lo is None else ev.num(f.lo)
        hi = None if f.hi is None else ev.num(f.hi)
        if lo is None and hi is None:
            return
        if lo is not None and hi is not None and lo > hi:
            raise Diagnostic(f'{label(cell)}: the range [{lo}, {hi}] is reversed')
        self.view.bounds[cell] = (lo, hi)
        self._in_range(cell, v)

    def _in_range(self, cell, v):
        lo, hi = self.view.bounds.get(cell, (None, None))
        if isinstance(v, Fraction) and ((lo is not None and v < lo) or (hi is not None and v > hi)):
            raise RunFailed(f'{label(cell)} = {v} is outside its range [{lo}, {hi}] at t = {self.view.t} h')

    def force(self, cell):
        """The starting value of a cell, computed on first need. A cycle is an error."""
        p = self.view.cells[cell]
        if not isinstance(p, Pending):
            return p
        if p.busy:
            raise Diagnostic(f'a cycle among starting values: {label(cell)} needs itself')
        p.busy = True
        self.view.cells[cell] = v = p.compute()
        self.view.entered[cell] = self.view.t
        return v

    def _prop(self, expr, scope):
        """A setting of a flow or of an endpoint: a captured value, or a formula that stays live."""
        return None if expr is None else Ev(self, self.view, scope, may_draw=True).val(expr)

    def _make_flow(self, decl, owner, scope):
        ev = Ev(self, self.view, scope)
        cells = self.view.cells

        def end(path):
            x = ev.ref(path)
            if isinstance(x, Cell):
                d = self.fields.get(x)
                if isinstance(cells.get(x), FormulaV) or (d is not None and d.kind != 'value') or not isinstance(cells.get(x), Fraction):
                    raise Diagnostic(f'{label(x)} cannot be an end of the flow {decl.name}: it is not a stored quantity')
                return x
            if x in (network.Ev and None,) or getattr(x, 'name', None) in ('SOURCE', 'SINK'):
                return None
            raise Diagnostic(f'{show(path)} cannot be an end of the flow {decl.name}')

        f = FlowRT(next(self.flow_numbers), decl, owner, scope, 'directed', label=f'{label(owner)}.{decl.name}')
        if decl.legs:
            f.kind = 'legs'
            for l in decl.legs:
                leg = LegRT(next(self.flow_numbers), f, l.name, end(l.source), end(l.sink), l)
                f.legs[l.name] = leg
                cells[Cell(leg, 'request')] = self._prop(l.request, scope)
                cells[Cell(leg, 'capacity')] = self._prop(l.capacity, scope)
        else:
            f.src, f.dst = end(decl.source), end(decl.sink)
            if decl.reversible:
                if f.src is None or f.dst is None:
                    raise Diagnostic(f'{f.label}: SOURCE and SINK cannot be an end of a reversible flow')
                f.kind = 'reversible'
                f.legs['forward'] = LegRT(next(self.flow_numbers), f, 'forward', f.src, f.dst)
                f.legs['backward'] = LegRT(next(self.flow_numbers), f, 'backward', f.dst, f.src)
            cells[Cell(f, 'capacity')] = self._prop(decl.capacity, scope)
            cells[Cell(f, 'request')] = self._prop(decl.request, scope)
        for c in network.connections(f):
            for cell in (c.src, c.dst):
                if cell is not None:
                    self._note_store(cell)
        self.flow_at[owner, decl.name] = f
        self.view.live.append(f)
        return f

    def _note_store(self, cell):
        """A cell becomes a store. What it holds at that time came from outside the flows: it is
        recorded as an opening balance."""
        if cell in self.stores:
            return
        amount = self.view.cells[cell]
        if amount != 0:
            if self.rules.opening == 'refuse' and isinstance(cell.owner, Occ):
                raise Diagnostic(f'{label(cell)} starts with {amount} that no flow or move brought: a store of an '
                                 'occurrence must start empty and be filled by a move or a flow')
            self.ledger.append(('opening', self.view.t, cell, amount))
        self.stores.add(cell)

    # --- the run ---------------------------------------------------------------------------------

    def run(self, until=None):
        """Run to the horizon (or to `until`). A failure raises; `self.error` keeps it. A choice
        that nobody gave stops the run with `self.paused` set."""
        horizon = self.config.horizon if until is None else number(until)
        try:
            if not self.frames:
                self._moment(setup=True)
            while True:
                nxt = self._next_time(horizon)
                if nxt is None:
                    break
                self._advance(nxt)
                self._moment()
        except Paused as p:
            self.paused = p.decision
        except (RunFailed, NotCovered) as e:
            self.error = e
            raise
        return self

    def _next_time(self, horizon):
        t = self.view.t
        if horizon is not None and t >= horizon:
            return None
        times = [t + s for s in self.stops if s > 0] + [o.due for o in self.scheduled]
        times += [tr.rearm_at for tr in self.triggers if not tr.armed and tr.rearm_at is not None and tr.rearm_at > t]
        if self.rules.report == 'in_run':
            times += [number(x) for _, _, at in self.config.report for x in at if number(x) > t]
        if horizon is not None:
            times.append(horizon)
        if not times:
            return None
        first = min(times, key=float)
        if isinstance(first, Irrational):
            raise NotCovered(f'the next moment after t = {t} h is a contact at an irrational time (about {float(first):.6g} h)')
        return first

    def _advance(self, nxt):
        """Move every store exactly to the time `nxt`, and account for what each flow carried."""
        view = self.view
        tau = nxt - view.t
        for src, dst, p, name in self.moving:
            self.ledger.append(('flow', view.t, nxt, name, src, dst, p.integral()(tau)))
        for cell, p in view.levels.items():
            view.cells[cell] = p(tau)
            self._in_range(cell, view.cells[cell])
        for var, p in view.rates.items():
            view.results[var] = p(tau)
        view.t, view.levels, view.rates = nxt, {}, {}

    def _moment(self, setup=False):
        t = self.view.t
        self.trace.append(('moment', t))
        self.rounds = 0
        self.hold_triggers = setup and self.rules.setup == 'starts_first'
        if setup:
            self.phase = 'stages'
            tx = Tx()
            self._execute(self.model.setup, tx, Scope())
            self._commit(tx)
            if self.rules.setup == 'round_zero':  # round zero: settle, then the first trigger check
                network.settle(self)
                self._finish_delays()
                self.phase = 'conditions'
                self._conditions()
                self._asserts(first=True)
        while True:
            self.rounds += 1
            if self.rounds > self.config.max_rounds:
                raise RunFailed(self._round_budget())
            self.phase, self.again, self.round_written = 'stages', False, set()
            due = [o for o in self.scheduled if o.due == t]
            due.sort(key=(lambda o: o.number) if self.rules.stage_order == 'age' else (lambda o: o.seq))
            if self.rules.round_writes == 'isolated' and len(due) > 1:
                self._stages_isolated(due)
            else:
                for occ in due:
                    self._stage(occ)
            network.settle(self)
            self._finish_delays()
            self.phase = 'conditions'
            self._conditions()
            self._asserts(first=setup and self.rounds == 1)
            if self.again or self.awaiting or any(o.due == t for o in self.scheduled):
                continue
            if self.hold_triggers:
                self.hold_triggers = False
                continue
            break
        if self.rules.report == 'in_run':
            for name, expr, at in self.config.report:
                if any(number(x) == t for x in at):
                    self.reported.setdefault(name, []).append(plain(Ev(self, self.view, Scope()).val(lit(expr))))
        self.stops = self._stops()
        self.frames.append(self.view.copy())

    def _round_budget(self):
        t = self.view.t
        fired = [f'{tr.label} ({n} times)' for tr, n in self._count('fire').items() if n > 1]
        return (f'the run does not settle at t = {t} h: more than {self.config.max_rounds} rounds at one time. '
                + ('Triggers that fired again and again: ' + ', '.join(fired) + ' (a reset cycle: the reset holds while the '
                   'condition still holds). ' if fired else '')
                + f'Occurrences started at this time: {sum(1 for e in self.trace if e[0] == "start" and e[1] == t)}.')

    def _count(self, kind):
        t, out = self.view.t, Counter()
        for e in self.trace:
            if e[0] == kind and e[1] == t:
                out[e[2]] += 1
        return {tr: out[tr.label] for tr in self.triggers if out[tr.label]} if kind == 'fire' else out

    # --- step 1: stages ----------------------------------------------------------------------------

    def scope_of(self, owner):
        if isinstance(owner, Occ):
            return Scope(owner.ent, owner)
        if isinstance(owner, (FlowRT, LegRT)):
            return (owner.flow if isinstance(owner, LegRT) else owner).scope
        return Scope(owner)

    def _stage(self, occ, commit=True):
        step = occ.event.steps[occ.step]
        self.scheduled.remove(occ)
        occ.due = None
        scope = self.scope_of(occ)
        tx = Tx(occ)
        ran = step.guard is None or Ev(self, self.view, scope).truth(step.guard)  # the guard is read once, now
        if ran:
            try:
                self._execute(step.body, tx, scope)
            except RunFailed as e:
                raise type(e)(f'{e} [stage {occ.step + 1} of {occ.label}, t = {self.view.t} h]') from None
        self.trace.append(('stage', self.view.t, occ.label, occ.step, ran))
        if commit:
            self._commit(tx)
            self._reach(occ, occ.step + 1)
        return tx

    def _stages_isolated(self, due):
        """The alternative for conflicting writes: every stage of a round reads the state from the
        start of the round, and two stages that assign one value differently fail the run."""
        txs = [(occ, self._stage(occ, commit=False)) for occ in due]
        merged = Tx()
        for occ, tx in txs:
            for cell, v in tx.writes.items():
                kind = tx.kinds.get(cell, 'set')
                if cell in merged.writes:
                    if kind == 'delta' and merged.kinds[cell] == 'delta':
                        merged.writes[cell] += v - self.view.cells[cell]
                        continue
                    if merged.writes[cell] != v or kind != merged.kinds[cell]:
                        raise RunFailed(f'conflicting writes to {label(cell)} from two stages of one round at t = {self.view.t} h '
                                        f'(the second is {occ.label})')
                merged.writes[cell], merged.kinds[cell] = v, kind
            merged.changed |= tx.changed
            merged.moves += tx.moves
            merged.starts += tx.starts
        self._commit(merged)
        for occ, _ in txs:
            self._reach(occ, occ.step + 1)

    def _execute(self, statements, tx, scope):
        for s in statements:
            ev = Ev(self, self.view, scope, tx=tx, may_draw=True)
            if isinstance(s, Assign):
                self._assign(s, ev, tx, scope)
            elif isinstance(s, Start):
                target = ev.val(s.event)
                args = [ev.val(a) for a in s.args]  # once, at the caller, left to right
                if isinstance(target, Coll):
                    members = [(k, self.key_of(m, self.view), ev.deref(v)) for k, m, v in target.items]
                    members.sort(key=(lambda x: (x[0], x[1])) if self.rules.broadcast == 'key' else (lambda x: x[1]))
                    target = [b for _, _, b in members]
                else:
                    target = [target]
                for b in target:
                    if not isinstance(b, Bound):
                        raise RunFailed(f'{show(s.event)}.start(...): not an event')
                    tx.starts.append((b, args))
            elif isinstance(s, Move):
                self._move(s, ev, tx)
            elif isinstance(s, Switch):
                chosen = ev.val(s.selector)
                if chosen is None:
                    raise RunFailed(f'the selector {show(s.selector)} has no value (none)')
                body = next((b for k, b in s.cases.items() if k == chosen), s.default)
                self._execute(body or [], tx, scope)
            else:
                raise RunFailed(f'{s!r} is not a statement')

    def _assign(self, s, ev, tx, scope):
        target = ev.ref(s.target)
        if isinstance(target, Res):
            raise Diagnostic(f'{show(s.target)} is a computed result and has its own writer')
        if not isinstance(target, Cell) or not (target in self.view.cells or target in tx.writes):
            raise RunFailed(f'{show(s.target)} is not a declared, writable value')
        d = self.fields.get(target)
        if d is not None and (d.readonly or d.kind == 'input'):
            raise Diagnostic(f'{label(target)} is {"readonly" if d.readonly else "an input"}: it cannot be assigned')
        if isinstance(target.owner, Occ) and target.name in BUILTIN or target in self.solved_cells:
            raise Diagnostic(f'{label(target)} cannot be assigned')
        value = ev.val(s.value)
        if s.op != '=':
            current = ev.cell(target)
            if current is None or value is None:
                value = ev.none(f'{show(s.target)} {s.op} {show(s.value)}')
            else:
                value = current + value if s.op == '+=' else current - value
        if isinstance(value, Occ) and self.rules.saved_occurrence == 'follows':
            value = FormulaV(s.value, scope)  # the alternative: a saved reference is read again each time
        self._in_range(target, value)
        if tx.writes.get(target, self.view.cells.get(target)) != value:
            tx.changed.add(target)
        tx.kinds[target] = 'delta' if s.op != '=' and tx.kinds.get(target, 'delta') == 'delta' else 'set'
        tx.writes[target] = value

    def _move(self, s, ev, tx):
        amount = ev.val(s.amount)
        if not isinstance(amount, Fraction) or amount < 0:
            raise RunFailed(f'move {show(s.amount)}: the amount must be a number that is not negative, and is {amount!r}')
        src, dst = ev.ref(s.source), ev.ref(s.destination)
        for c in (src, dst):
            d = self.fields.get(c) if isinstance(c, Cell) else None
            if not isinstance(c, Cell) or not isinstance(ev.cell(c), Fraction) or (d is not None and d.kind != 'value') \
                    or isinstance(self.view.cells.get(c), FormulaV):
                raise Diagnostic(f'move: {show(s.source if c is src else s.destination)} is not a stored quantity')
            if d is not None and d.readonly and self.rules.move_readonly == 'refused':
                raise Diagnostic(f'move: {label(c)} is readonly')
        after = {src: ev.cell(src) - amount, dst: ev.cell(dst) + amount}
        for c, v in after.items():  # both inventories are checked before anything changes
            lo, hi = self.view.bounds.get(c, (None, None))
            if (lo is not None and v < lo) or (hi is not None and v > hi):
                raise RunFailed(f'move of {amount} from {label(src)} to {label(dst)} fails: {label(c)} would hold {v}, '
                                f'outside its range [{lo}, {hi}]; nothing is moved')
        tx.writes.update(after)
        tx.changed |= set(after)
        tx.kinds.update({src: 'delta', dst: 'delta'})
        tx.moves.append((src, dst, amount))

    def _commit(self, tx):
        """Publish the writes of a stage and register the occurrences that it queued."""
        view, t = self.view, self.view.t
        moved = Counter()
        for src, dst, amount in tx.moves:
            self._note_store(src)
            self._note_store(dst)
            moved[src] -= amount
            moved[dst] += amount
            self.ledger.append(('move', t, src, dst, amount))
        for cell, value in tx.writes.items():
            old = view.cells.get(cell)
            if cell in self.stores and isinstance(old, Fraction) and isinstance(value, Fraction) and value - old != moved[cell]:
                self.ledger.append(('write', t, cell, value - old - moved[cell]))  # a direct write: from or to outside
            changed = (old != value) if self.rules.elapsed == 'net' else cell in tx.changed
            view.cells[cell] = value
            if changed:
                view.entered[cell] = t
        self.round_written |= set(tx.writes)
        starts, tx.starts, tx.writes, tx.moves = tx.starts, [], {}, []
        for bound, args in starts:
            self._register(bound, args)

    def _register(self, bound, args):
        """A start becomes an occurrence: its copies of the arguments, its locals, its flows."""
        view, t, ent, event = self.view, self.view.t, bound.ent, bound.event
        occs = view.occs[ent, event.name]
        running = [o for o in occs if view.cells[Cell(o, 'active')]]
        if self.config.max_active is not None and len(running) >= self.config.max_active:
            oldest = running[0]
            where = oldest.event.steps[oldest.step]
            raise RunFailed(
                f'budget: {len(running)} occurrences of {ent.id}.{event.name} run at once at t = {t} h and one more starts '
                f'(the limit is {self.config.max_active}). The oldest, {oldest.label}, started at '
                f'{view.cells[Cell(oldest, "started")]} h and waits at step {oldest.step + 1}'
                + (f': until {show(where.condition)}' if isinstance(where, Until) else '') + '.')
        if len(args) != len(event.params):
            raise RunFailed(f'{ent.id}.{event.name}.start: {len(event.params)} arguments are declared and {len(args)} are given')
        occ = Occ(next(self.occ_numbers), ent, event, len(occs) + 1, tuple(args))
        for name, v in (('started', t), ('done', False), ('active', True), *zip(event.params, args)):
            view.cells[Cell(occ, name)] = v
            view.entered[Cell(occ, name)] = t
        scope = Scope(ent, occ)
        decls = list(event.locals) + list(event.flows)
        if self.rules.local_order == 'flows_last':  # every local exists before a flow reads one
            decls = [d for d in decls if isinstance(d, Field)] + [d for d in decls if isinstance(d, Flow)]
        for i, d in enumerate(decls):
            if isinstance(d, Flow):
                self._make_flow(d, occ, scope)
                continue
            cell = Cell(occ, d.name)
            self.fields[cell] = d
            ev = Ev(self, view, scope, may_draw=True)
            if d.kind == 'formula':
                later = {x.name for x in decls[i + 1:]}
                if self.rules.local_order == 'written' and later & _names(d.init):
                    raise Diagnostic(f'{occ.label}.{d.name}: the formula names {sorted(later & _names(d.init))}, declared below it')
                view.cells[cell] = FormulaV(d.init, scope)
            else:
                view.cells[cell] = None if d.init is None else ev.val(d.init)
                self._range(cell, d, ev, view.cells[cell])
            view.entered[cell] = t
        occs.append(occ)
        self.trace.append(('start', t, occ.label))
        if self.phase == 'conditions':
            self.again = True
        self._reach(occ, 0)
        return occ

    def _reach(self, occ, i):
        """The occurrence comes to its step i: a delay is captured, a gate waits, or it finishes."""
        occ.step, occ.waiting, occ.due = i, False, None
        if i >= len(occ.event.steps):
            return self._complete(occ)
        step = occ.event.steps[i]
        if self.phase == 'conditions':
            self.again = True
        if isinstance(step, Until):
            occ.waiting = True
            return
        try:  # ordinary inputs of the delay are captured now; a computed result waits for the settlement
            delay = Ev(self, self.view, self.scope_of(occ), may_draw=True, defer=True).val(step.delay)
        except NeedsSettle:
            self.awaiting.append((occ, self.view.copy()))
        else:
            self._schedule(occ, delay, step)

    def _schedule(self, occ, delay, step):
        if not isinstance(delay, Fraction) or delay < 0:
            raise RunFailed(f'the delay {show(step.delay)} of {occ.label} must be a duration that is not negative, and is {delay!r}')
        occ.due, occ.seq = self.view.t + delay, next(self.sequence)
        self.scheduled.append(occ)

    def _finish_delays(self):
        waiting, self.awaiting = self.awaiting, []
        for occ, snapshot in waiting:
            snapshot.results = self.view.results  # the state as captured, the results as just settled
            step = occ.event.steps[occ.step]
            self._schedule(occ, Ev(self, snapshot, self.scope_of(occ), may_draw=True).val(step.delay), step)

    def _complete(self, occ):
        """Normal completion. A store of the occurrence must be empty (the retirement rule); its
        flows leave their endpoints and keep their last request."""
        view, t = self.view, self.view.t
        for cell in sorted((c for c in self.stores if c.owner is occ), key=lambda c: c.name):
            left = view.cells[cell]
            if left != 0:
                if self.rules.retirement != 'dispose':
                    raise RunFailed(f'{occ.label} cannot finish at t = {t} h: its store {label(cell)} still holds {left}. '
                                    'Wait for it to drain, move the rest to a named stock, or send it to SINK.')
                self.ledger.append(('disposed', t, cell, left))
                view.cells[cell] = Fraction(0)
        for (owner, _), f in list(self.flow_at.items()):
            if owner is occ and f in view.live:
                ev = Ev(self, view, f.scope)
                for holder in [f] + list(f.legs.values()):
                    c = Cell(holder, 'request')
                    if c in view.cells:
                        view.cells[c] = ev.cell(c)  # frozen, also when it was a formula
                view.live.remove(f)
        for cell, v in list(view.cells.items()):
            if cell.owner is occ and isinstance(v, FormulaV):
                view.cells[cell] = Ev(self, view, v.scope).cell(cell)
        view.cells[Cell(occ, 'done')], view.cells[Cell(occ, 'active')] = True, False
        self.trace.append(('done', t, occ.label))
        if self.phase == 'conditions':
            self.again = True

    def gone_when_finished(self, occ):
        """Under the alternative for a finished occurrence: its arguments, stores and formulas."""
        return set(occ.event.params) | {c.name for c in self.stores if c.owner is occ} | \
            {d.name for d in occ.event.locals if isinstance(d, Field) and d.kind == 'formula'}

    # --- step 4: conditions ------------------------------------------------------------------------

    def _conditions(self):
        """Read every trigger, reset and gate on the settled state. Then act, in a fixed order:
        firings by receiver and declaration, then released gates by the age of the occurrence."""
        view, t = self.view, self.view.t
        fires = []
        for trig in ([] if self.hold_triggers else self.triggers):
            ev = Ev(self, view, Scope(trig.ent, None, trig.caps))
            reset = trig.decl.reset
            if not trig.armed:
                if reset is None:  # no reset written: the condition must become false first
                    if not ev.truth(trig.decl.when):
                        trig.armed = True
                    elif not self._after(trig.decl.when, ev.scope):
                        trig.armed, trig.blocked_at = True, t  # false just after: armed for a later visit
                elif reset[0] == 'when':
                    trig.armed = ev.truth(reset[1])
                elif trig.rearm_at is not None and t >= trig.rearm_at:
                    trig.armed = True
            if trig.armed and trig.blocked_at != t and ev.truth(trig.decl.when):
                fires.append(trig)
        releases = [o for o in self._gates() if Ev(self, view, self.scope_of(o)).truth(o.event.steps[o.step].condition)]
        for trig in fires:
            self._fire(trig)
        for occ in releases:
            self.trace.append(('release', t, occ.label, occ.step))
            self._reach(occ, occ.step + 1)

    def _gates(self):
        return sorted((o for occs in self.view.occs.values() for o in occs if o.waiting), key=lambda o: o.number)

    def _after(self, condition, scope):
        """The truth of a condition just after this instant."""
        network.motion(self)
        return Ev(self, self.view, scope, mode='germ').truth(condition)

    def _fire(self, trig):
        t = self.view.t
        if self.rules.refire == 'once' and trig.fired_at == t:
            raise RunFailed(f'reset cycle: {trig.label} fires a second time at t = {t} h')
        caps = {}
        for name, expr in trig.decl.captures:
            ev = Ev(self, self.view, Scope(trig.ent, None, dict(caps)), may_draw=True)
            ev.shared.context = f'{trig.label}!{trig.firings + 1}'
            caps[name] = ev.val(expr)
        tx = Tx()
        self._execute(trig.decl.starts, tx, Scope(trig.ent, None, caps))
        trig.caps, trig.armed, trig.fired_at, trig.firings = caps, False, t, trig.firings + 1
        if trig.decl.reset is not None and trig.decl.reset[0] == 'after':  # the duration is captured at firing
            trig.rearm_at = t + Ev(self, self.view, Scope(trig.ent, None, caps), may_draw=True).num(trig.decl.reset[1])
        self.trace.append(('fire', t, trig.label))
        self.again = True
        self._commit(tx)

    def _asserts(self, first):
        if self.rules.asserts == 'start' and not first:
            return
        for a in self.model.asserts:
            scope = Scope(self.ents[a.owner]) if a.owner else Scope()
            if not Ev(self, self.view, scope).truth(a.condition):
                raise RunFailed(f'assert {a.text or show(a.condition)} fails at t = {self.view.t} h')

    def _stops(self):
        """The times after this moment at which something can happen without a scheduled stage."""
        view = self.view
        stops = network.motion(self)

        def watch(expr, scope, strict):
            ev = Ev(self, view, scope, mode='germ')
            ev.shared.strict = strict
            v = ev.val(expr)
            stops.extend(ev.shared.stops)
            return v

        for trig in self.triggers:
            scope = Scope(trig.ent, None, trig.caps)
            watch(trig.decl.when, scope, True)
            if not trig.armed and trig.decl.reset is not None and trig.decl.reset[0] == 'when':
                watch(trig.decl.reset[1], scope, True)
        for occ in self._gates():
            watch(occ.event.steps[occ.step].condition, self.scope_of(occ), True)
        if self.rules.asserts == 'always':
            for a in self.model.asserts:
                if watch(a.condition, Scope(self.ents[a.owner]) if a.owner else Scope(), False) is False:
                    raise RunFailed(f'assert {a.text or show(a.condition)} fails just after t = {view.t} h')
        return stops

    # --- what the evaluator asks of the run ----------------------------------------------------------

    def pull(self, var):
        network.pull(self, var)

    def incident(self, view, end):
        return network.incident(view, end)

    def scale(self, dim):
        """One canonical unit of a dimension, in the working units of the model."""
        return Fraction(self.model.scales.get(dim, 1)) if self.rules.flow_scale == 'canonical' else Fraction(1)

    def key_of(self, member, view):
        return view.cells[Cell(member, 'started')] if isinstance(member, Occ) else member.number

    def check_dirty(self, var, tx):
        """A stage reads a computed result. After the stage changed an input of that result, the
        read is dirty: the result is settled only after the commit."""
        comp = self.component_of.get(var)
        deps = comp.deps if comp is not None else set()
        if deps & set(tx.writes):
            raise Diagnostic(f'dirty read: {label(var)} is read in the stage that changed '
                             f'{", ".join(sorted(label(c) for c in deps & set(tx.writes)))}; '
                             'read it after the stage commits and the solver settles')
        if self.rules.stale_result == 'error' and deps & self.round_written:
            raise RunFailed(f'{label(var)} is read after another stage of this round changed its inputs')

    def entered(self, cell, tx, view):
        """The time at which a state took its present value."""
        if tx is not None and cell in tx.writes:
            fresh = cell in tx.changed if self.rules.elapsed == 'every_write' else tx.writes[cell] != view.cells.get(cell)
            if fresh:
                return view.t
        return view.entered.get(cell, Fraction(0))

    def read_past(self, expr, delay, ev):
        """`delayed(x, D)`: x as the run recorded it D ago. With D = 0 inside a stage that is the
        committed value, not a value that the stage itself has written and not yet committed."""
        if not isinstance(delay, Fraction) or delay < 0:
            raise RunFailed(f'delayed({show(expr)}, ...): the delay must be a duration that is not negative')
        if delay == 0:
            own = self.rules.delayed_zero == 'own_writes'
            return plain(Ev(self, self.view, ev.scope, tx=ev.tx if own else None).val(expr))
        return self.read(expr, max(self.view.t - delay, Fraction(0)), scope=ev.scope)

    # --- draws and choices ---------------------------------------------------------------------------

    def _key(self, node, ev):
        """The key of a draw: its site in the model, its owner, and its occurrence or firing."""
        s = ev.scope
        who = s.occ.label if s.occ is not None else getattr(ev.shared, 'context', None) or (s.this.id if s.this is not None else 'model')
        return f'{self.sites.get(id(node), show(node))}|{who}'

    def _uniform(self, key):
        if self.rules.draws == 'stream':  # the alternative: the k-th executed draw takes the k-th number
            key = f'#{next(self.stream)}'
        digest = hashlib.sha256(f'{self.config.seed}|{key}'.encode()).digest()
        return Fraction(int.from_bytes(digest[:8], 'big') * 2 + 1, 2**65)

    def draw(self, dist, node, ev):
        key = self._key(node, ev)
        if self.config.mode == 'median':
            value = self.describe(dist, 'median')
        else:
            u = self._uniform(key)
            if dist.kind == 'uniform':
                value = dist.params[0] + (dist.params[1] - dist.params[0]) * u
            elif dist.kind == 'normal':
                value = dist.params[0] + dist.params[1] * Fraction(NormalDist().inv_cdf(float(u))).limit_denominator(10**9)
            else:
                raise NotCovered(f'the distribution {dist.kind}')
        self.draws.append((key, value))
        return value

    def describe(self, dist, name, ev=None):
        if dist.kind == 'uniform':
            lo, hi = dist.params
            if name in ('mean', 'median'):
                return (lo + hi) / 2
        elif dist.kind == 'normal':
            if name in ('mean', 'median'):
                return dist.params[0]
            if name == 'std':
                return dist.params[1]
        raise NotCovered(f'{name} of the distribution {dist.kind}')

    def chance(self, node, name, eligible, ev):
        if not eligible or sum(p for _, p in eligible) != 1:
            raise RunFailed(f'the chances of {name} must add up to one over the eligible outcomes')
        if self.config.mode == 'median':  # the most likely eligible outcome; the first declared on a tie
            return max(eligible, key=lambda vp: vp[1])[0]
        key = self._key(node, ev)
        u, total = self._uniform(key), Fraction(0)
        for value, p in eligible:
            total += p
            if u < total:
                self.draws.append((key, value))
                return value

    def decide(self, node, name, available, ev):
        """An actor's choice. With no answer the run pauses: inside the stage, before its commit."""
        s = ev.scope
        key = f'{name}@{s.occ.label if s.occ is not None else s.this.id if s.this is not None else "model"}'
        answer = self.config.choices.get(key, self.config.choices.get(name, _MISSING))
        if answer is not _MISSING:
            if answer not in available:
                raise RunFailed(f'the choice {key}: {answer} is not available (available: {available})')
            self.decisions.append((self.view.t, key, answer))
            return answer
        sees = {show(e): plain(ev.fork(Scope(s.this)).val(e)) for e in (s.this.template.sees if s.this is not None else [])}
        decision = {'key': key, 'time': self.view.t, 'options': available, 'sees': sees}
        if self.rules.pause == 'split' and ev.tx is not None:
            self._commit(ev.tx)  # the alternative: what the stage did so far is committed at the pause
        raise Paused(decision)

    # --- what a caller reads -------------------------------------------------------------------------

    def read(self, expr, at=None, owner=None, scope=None):
        """The value of an expression at a time of the run, from the record. A read changes nothing."""
        at = self.view.t if at is None else number(at)
        frames = [f for f in self.frames if f.t <= at]
        if not frames or at > self.view.t:
            raise RunFailed(f'the run has no record at t = {at} h')
        frame = frames[-1].copy()
        tau = at - frame.t
        if tau > 0:
            for cell, p in frame.levels.items():
                frame.cells[cell] = p(tau)
            for var, p in frame.rates.items():
                frame.results[var] = p(tau)
            frame.t, frame.levels, frame.rates = at, {}, {}
        if scope is None:
            scope = Scope(self.ents[owner]) if owner else Scope()
        ev = Ev(self, frame, scope)
        v = ev.val(lit(expr))
        if isinstance(v, Coll):  # a projection: each member's value, read on the same frame
            return Coll((k, m, x if isinstance(x, (Ent, Occ, FlowRT, LegRT)) else plain(ev.deref(x))) for k, m, x in v.items)
        return v if isinstance(v, (Coll, Ent, Occ, FlowRT, LegRT, Alloc)) else plain(v)

    def report(self, expr, times, owner=None):
        """What a report shows: the value at each time, or `Unavailable` with the reason. An invalid
        read is the report's affair: it cannot fail the run, which is over."""
        out = []
        for at in times:
            try:
                out.append(self.read(expr, at, owner))
            except RunFailed as e:
                out.append(Unavailable(str(e)))
        return out

    def times(self, kind, name=None):
        """The times of the trace entries of one kind (and one label)."""
        return [e[1] for e in self.trace if e[0] == kind and (name is None or e[2] == name)]

    def conservation(self):
        """The account of every store: what is held equals what came in less what went out."""
        held = sum((self.view.cells[c] for c in self.stores), Fraction(0))
        tot = Counter()
        for e in self.ledger:
            if e[0] == 'flow':
                tot['from_source'] += e[6] if e[4] is None and e[5] is not None else 0
                tot['to_sink'] += e[6] if e[5] is None and e[4] is not None else 0
            elif e[0] in ('opening', 'write', 'disposed'):
                tot[e[0]] += e[3]
        expected = tot['opening'] + tot['write'] + tot['from_source'] - tot['to_sink'] - tot['disposed']
        return {'held': held, **{k: tot[k] for k in ('opening', 'write', 'from_source', 'to_sink', 'disposed')},
                'balanced': held == expected}


def _names(e):
    """The bare names that an expression reads."""
    if isinstance(e, E):
        return ({e._a[0]} if e._k == 'name' else set()).union(*(_names(a) for a in e._a))
    if isinstance(e, (tuple, list)):
        return set().union(*(_names(a) for a in e)) if e else set()
    return set()


def _sites(model):
    """A stable name for each place of the model where a draw, a chance or a choice is written."""
    sites = {}

    def walk(x, path):
        if isinstance(x, E):
            if x._k in ('choose', 'chance') or (x._k == 'call' and x._a[1] == 'draw'):
                sites[id(x)] = path
            for i, a in enumerate(x._a):
                walk(a, f'{path}/{i}')
        elif isinstance(x, (list, tuple)):
            for i, a in enumerate(x):
                walk(a, f'{path}/{getattr(a, "name", i)}')
        elif isinstance(x, dict):
            for k, a in x.items():
                walk(a, f'{path}/{k}')
        elif dataclasses.is_dataclass(x):
            for f in dataclasses.fields(x):
                walk(getattr(x, f.name), f'{path}.{f.name}')

    walk(model.templates, 'template')
    walk(model.setup, 'setup')
    for inst in model.instances:
        walk(inst.values, f'instance/{inst.id}')
    return sites
