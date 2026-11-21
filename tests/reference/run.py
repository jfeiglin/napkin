"""Running a description: what happens at one time, and between two times.

The run goes from moment to moment. A moment is a time at which something discrete can happen.

At a time, rounds (`Run._moment`). One round is:

1. *Stages.* The stages that are due when the round begins commit one after the other (decision
   D5), the stage of the occurrence that started first going first. A later stage sees what an
   earlier one committed: from 20 g, a stage that sets 8 g and then one that adds 4 g leave 12 g.
   A commit publishes the stage's writes and registers the occurrences that it queued; an
   occurrence that has no step left finishes, and its record freezes (decision D7). A write to a
   finished occurrence fails the run (PLAN, change 24 b): an assignment to its field, a move of an
   authored nonzero amount into or out of its store, or a computed flow whose cumulative amount
   in either direction exceeds the store’s allowance (`_frozen_transfer`).
2. *Settle.* Each affected solver shares its results once (`network.settle`). Until then stages
   read the previous settlement's rates and results at this time, also through a formula. A flow
   that joined reads zero. A flow that left keeps its rate until the settlement.
3. *Delays.* A next delay that reads a computed result is finished with the settled result.
4. *Conditions.* Triggers, resets and gates are all read on the settled state; then the firings
   and the released gates take effect, in a fixed order.

A further round follows when anything is due at the same time or was registered in step 4. Setup
is round zero: its statements commit as one stage, then the rates settle and the triggers get their
first check. Three limits protect a run (decision D6): `max_occurrences`, `max_active` and
`max_rounds`, each a field of `Config`.

A breakpoint (`Config.breakpoints`, item 15 of the plan's changes after G0) stops the run before a
statement of a stage, before a stage, or before the first stage of an occurrence of an event, and
`Run.edit` then changes live stored values: of the type and in the range of the value, never of a
finished occurrence, each edit in `edit_log` and in the trace, and a store's edit in the books as a
transfer from or to outside. `Run.resume` runs the paused stage again from its start with the draws
that it made, and applies the edits of each stop of that stage at the stop, in order: an edit inside
a stage joins that stage's writes (the stage sees it, the others when it commits), so two stops in
one stage neither lose the first edit nor apply it twice. An edit before a stage, between two
commits, commits at once. Untouched, the run is the run with no breakpoint: one draw, one child, one
transfer. (The oracle runs the paused stage again from its start, on the state that the stop left
unchanged and with its kept draws, which is the same as going on in place.)

Between two moments every rate is constant, or a known polynomial in time, and each store is
integrated exactly (`network.motion`). The next moment is the earliest of: a stage that is due,
a reset timer, the first contact of a watched condition with its boundary, a store that meets a
bound, and the horizon.
"""

import dataclasses
import hashlib
import itertools
from collections import Counter
from fractions import Fraction
from statistics import NormalDist
from typing import NamedTuple

from . import network
from .errors import Diagnostic, FrozenTransfer, NotCovered, Paused, RunFailed
from .evaluate import (
    SINK,
    SOURCE,
    UNSET,
    Bound,
    Cell,
    Coll,
    End,
    Ent,
    Ev,
    Failed,
    FlowRT,
    FormulaV,
    LegRT,
    NeedsSettle,
    Occ,
    Pending,
    Res,
    Scope,
    View,
    label,
)
from .exact import solve_affine
from .model import Assign, Branch, Config, E, Flow, Move, Start, Switch, Until, lit, number, scale_of, show
from .poly import Irrational, Poly, plain

_MISSING = object()
BUILTIN = ('started', 'done', 'active')


class Entry(NamedTuple):
    """One entry of the trace: its kind ('start', 'done', 'stage' for a stage that ran its body,
    'skip' for one whose guard was false, 'fire', 'solve', 'draw', 'move', 'release',
    'edit', 'moment'), the time, the occurrence, member, trigger or solver that it is about, the step of a
    stage, the round of its time (0 is the setup), and the origin of its part in a program."""

    kind: str
    t: Fraction
    label: str
    step: object = None
    round: int = 0
    origin: str = ''


def _allowance_root(volume, remaining, lo, hi):
    """A rational point or enclosing interval for the first excess of a positive amount."""
    if not remaining:
        return lo, lo
    residual = volume - (volume(lo) + remaining)
    if len(residual.c) <= 3:
        root = residual(Poly([lo, 1])).first_root()
        if isinstance(root, Fraction):
            return lo + root, lo + root
    # Higher degrees can have an irrational root. Keep both bounds so a nearby
    # crossing-window edge cannot accidentally select or omit a violation.
    while hi - lo > Fraction(1, 10**18):
        middle = (lo + hi) / 2
        sign = residual(middle)
        if not sign:
            return middle, middle
        if sign > 0:
            hi = middle
        else:
            lo = middle
    return lo, hi


class Tx:
    """The uncommitted work of one stage: its writes, its moves and the starts that it queued."""

    def __init__(self, occ=None):
        self.occ = occ
        self.writes = {}
        self.moves = []
        self.starts = []
        self.edited = Counter()  # what the edits of a breakpoint added to a store, which is no write


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
    firings: int = 0

    @property
    def label(self):
        """The name of the trigger, such as `grinder.refill.when[0]`."""
        return f'{self.ent.id}.{self.event.name}.when[{self.index}]'


class Unavailable:
    """What a report shows for a read that has no value at that time: the reason, and no value."""

    def __init__(self, reason):
        self.reason = reason

    def __repr__(self):
        return f'unavailable ({self.reason})'

    def __eq__(self, other):
        return isinstance(other, Unavailable)

    __hash__ = None


class Run:
    """One run of a model: `Run(model, config).run()`, then read its record with `read`."""

    def __init__(self, model, config=None, **options):
        self.model = model
        self.config = config or Config(**options)
        if self.config.horizon is not None:
            self.config.horizon = number(self.config.horizon)
        self.view = View()
        self.ents, self.tables = {}, set()
        self.flow_at = {}  # (owner, name) -> FlowRT, for every flow ever made
        self.fields = {}  # Cell -> its declaration
        self.transferred, self.own_scales = {}, {}
        self.stores = set()  # cells that hold stock: an end of a flow or of a move
        self.triggers, self.scheduled, self.awaiting = [], [], []
        self.ledger, self.trace, self.frames, self.draws = [], [], [], []
        self.cache = {}
        self.components, self.component_of, self.solved_cells, self.settling = [], {}, set(), None
        self.moving, self.stops = [], []
        self.contacts, self.bound_contacts, self.contact_levels = [], [], {}
        self.flow_numbers, self.occ_numbers = itertools.count(1), itertools.count(1)
        self.sites = _sites(model)
        self.error = self.paused = None
        self.held = None  # the rest of a round that a prompt paused, its paused stage first
        self.kept_draws, self.stage_draws = {}, {}
        # Breakpoints: the live list, which a caller may change at a stop; where the run stopped,
        # with the stage's work then (None before a stage) and the edits made there; each stop that
        # the stage that runs again has passed, by (occurrence, step, origin), with its edits.
        self.breakpoints = list(self.config.breakpoints)
        self.stopped, self.stop_edits, self.passed = None, [], {}
        self.edit_log = []
        self.phase = 'setup'
        self.rounds, self.again = 0, False
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
                cells[Cell(ent, f.name)] = Pending(
                    lambda ent=ent, inst=inst, f=f: self._start_value(ent, inst, f)
                )
        for c in list(cells):
            self.force(c)
        for ent in self.ents.values():
            for decl in ent.template.flows:
                self._make_flow(decl, ent, Scope(ent))
        for ent in self.ents.values():
            for f in ent.template.fields:
                self._endpoints(Cell(ent, f.name), f, Scope(ent))
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
            if target is None:
                return UNSET
            return self.ents[target] if isinstance(target, str) else ev.val(target)
        if f.kind == 'formula':
            return FormulaV(lit(f.init if given is _MISSING else given), scope)
        key = f'{ent.id}.{f.name}'
        if f.kind == 'input' and key in self.config.inputs:
            v = ev.val(
                lit(self.config.inputs[key])
            )  # an override: the default is not evaluated, and draws nothing
        elif given is not _MISSING:
            v = ev.val(lit(given))
        else:
            v = UNSET if f.init is None else ev.val(f.init)
        return self._range(cell, f, ev, v, admission=f.kind == 'input')

    def _range(self, cell, f, ev, v, *, admission=False):
        lo = None if f.lo is None else ev.num(f.lo)
        hi = None if f.hi is None else ev.num(f.hi)
        scale = ev.num(f.scale) if f.scale is not None else self.model.units.get(f.unit)
        self.own_scales[cell] = (
            abs(scale) if scale is not None else scale_of(f.unit) if f.unit else Fraction(1)
        )
        if lo is None and hi is None:
            return v
        if lo is not None and hi is not None and lo > hi:
            band = max(self.config.rtol, self.config.atol_factor) * max(
                self.own_scales[cell], abs(lo), abs(hi)
            )
            if lo - hi > band:
                raise Diagnostic(f'{label(cell)}: the range [{lo}, {hi}] is reversed')
            lo = hi = (hi + lo) / 2
            if abs(v - lo) <= band:
                v = lo
        self.view.bounds[cell] = (lo, hi)
        self._in_range(cell, v, admission=admission)
        return v

    def _in_range(self, cell, v, *, admission=False):
        if not isinstance(v, Fraction):
            return
        lo, hi = self.view.bounds.get(cell, (None, None))
        if (lo is None or lo <= v) and (hi is None or v <= hi):
            return
        edge = lo if lo is not None and v < lo else hi
        factor = max(self.config.rtol, self.config.atol_factor) if admission else self.config.atol_factor
        if abs(v - edge) > factor * max(self.own_scales[cell], abs(v), abs(edge)):
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
        """A setting of a flow or of an endpoint: a captured value, or a formula that stays live.
        None when the model left it out."""
        return None if expr is None else Ev(self, self.view, scope, may_draw=True).val(expr)

    def _endpoints(self, cell, decl, scope):
        """The settings of `outflow` and `inflow` written under a store, of a member or of an
        occurrence alike: a capacity and a request as `_prop` gives them, and an allocation that
        stays live (left out, it is proportional)."""
        for side in ('outflow', 'inflow'):
            ep = getattr(decl, side)
            if ep is None:
                continue
            end = End(cell, side)
            settings = {
                'capacity': self._prop(ep.capacity, scope),
                'request': self._prop(ep.request, scope),
                'allocation': None if ep.allocation is None else FormulaV(ep.allocation, scope),
            }
            for name, v in settings.items():
                self.view.cells[Cell(end, name)] = v
                self.view.entered[Cell(end, name)] = self.view.t

    def _make_flow(self, decl, owner, scope):
        ev = Ev(self, self.view, scope)
        cells = self.view.cells

        def end(path):
            x = ev.ref(path)
            if isinstance(x, Cell):
                d = self.fields.get(x)
                held = ev.raw(x)
                if (
                    isinstance(held, FormulaV)
                    or (d is not None and d.kind != 'value')
                    or not isinstance(held, Fraction)
                ):
                    raise Diagnostic(
                        f'{label(x)} cannot be an end of the flow {decl.name}: it is not a stored quantity'
                    )
                return x
            if x is SOURCE or x is SINK:
                return None
            raise Diagnostic(f'{show(path)} cannot be an end of the flow {decl.name}')

        f = FlowRT(
            next(self.flow_numbers), decl, owner, scope, 'directed', label=f'{label(owner)}.{decl.name}'
        )
        if decl.legs:
            f.kind = 'legs'
            for spec in decl.legs:
                leg = LegRT(next(self.flow_numbers), f, spec.name, end(spec.source), end(spec.sink), spec)
                f.legs[spec.name] = leg
                cells[Cell(leg, 'request')] = self._prop(spec.request, scope)
                cells[Cell(leg, 'capacity')] = self._prop(spec.capacity, scope)
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
        for cell in network.stores_of(f):
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
            self.ledger.append(('opening', self.view.t, cell, amount))
        self.stores.add(cell)

    # --- the run ---------------------------------------------------------------------------------

    def run(self, until=None):
        """Run to the horizon (or to `until`). A failure raises; `self.error` keeps it. A breakpoint
        stops the run with `self.paused` set: call `resume()`."""
        horizon = self.config.horizon if until is None else number(until)
        if self.paused is not None:
            raise RunFailed(f'the run waits at {self.paused["key"]}: go on with resume()')
        try:
            if self.held is not None:
                self._moment()  # the paused moment goes on
            elif not self.frames:
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

    def resume(self):
        """Run on from a breakpoint, with the edits made there. The paused stage commits once."""
        if self.paused is None:
            raise RunFailed('the run waits for nothing')
        self.passed[self.stopped[0]] = self.stop_edits
        self.stopped, self.stop_edits, self.paused = None, [], None
        return self.run()

    def edit(self, owner, name, value):
        """At a breakpoint, change the stored value `name` of a member (its id) or of a live
        occurrence (its label, `depot.request_pump#0`) to `value`, in canonical units or an enum
        member: a value of the same type, in its range. Gives the value that it replaces."""
        if self.paused is None:
            raise RunFailed('a value is edited at a breakpoint')
        view, t = self.view, self.view.t
        cell = self._editable(owner, name)
        tx = self.stopped[1]
        old = next(
            (new for each, new in reversed(self.stop_edits) if each == cell),
            tx.writes.get(cell, view.cells[cell]) if tx is not None else view.cells[cell],
        )
        value = number(value)
        if type(value) is not type(old):
            raise RunFailed(
                f'{owner}.{name}: an edit keeps the type of the value, {old!r}, and {value!r} is another'
            )
        lo, hi = view.bounds.get(cell, (None, None))
        if isinstance(value, Fraction) and (
            (lo is not None and value < lo) or (hi is not None and value > hi)
        ):
            raise RunFailed(
                f'{owner}.{name} = {value} is outside its range [{lo}, {hi}]: an edit keeps the range'
            )
        self.edit_log.append(
            {
                'time': t,
                'breakpoint': self.paused['at'],
                'owner': owner,
                'name': name,
                'old': old,
                'new': value,
            }
        )
        self._note('edit', owner, origin=self.paused['at'])
        if cell in self.stores and isinstance(old, Fraction):
            self.ledger.append(('edit', t, cell, value - old))  # a transfer from or to outside
        if tx is None:  # before a stage, between two commits: the edit commits at once
            view.cells[cell] = value
            if old != value:
                view.entered[cell] = t
        else:
            self.stop_edits.append((cell, value))
        return old

    def _editable(self, owner, name):
        """The cell of a live stored value, or a refusal that says why it is none."""
        holder = self.ents.get(owner)
        if holder is None:
            holder = next((o for occs in self.view.occs.values() for o in occs if o.label == owner), None)
        if holder is None:
            raise RunFailed(f'{owner} names no member and no occurrence of the run')
        cell = Cell(holder, name)
        declared = self.fields.get(cell)
        if isinstance(holder, Occ) and not self.view.cells[Cell(holder, 'active')]:
            raise RunFailed(f'{owner} has finished: a finished occurrence stays frozen')
        if cell not in self.view.cells or declared is None or declared.kind != 'value':
            what = declared.kind if declared is not None else 'no stored value'
            raise RunFailed(f'{owner}.{name}: an edit changes a live stored value, and this is {what}')
        return cell

    def _stop(self, occ, origin, tx=None, first=False):
        """Before the part `origin` of a stage of `occ` runs (the stage itself with `tx` None, or a
        statement of its work `tx`): stop when a breakpoint names it, or the event at its first
        stage (`first`), unless the stage that runs again has passed this stop, whose edits then
        join the stage's writes."""
        position = (occ.number, occ.step, origin)
        if position in self.passed:
            for cell, value in self.passed[position]:
                old = tx.writes.get(cell, self.view.cells[cell])
                tx.writes[cell] = value
                if isinstance(old, Fraction) and isinstance(value, Fraction):
                    tx.edited[cell] += value - old
            return
        names = (origin, occ.event.origin) if first else (origin,)
        hit = next(
            (at for at, who in self.breakpoints if at in names and (who is None or who == occ.label)), None
        )
        if hit is None:
            return
        self.kept_draws = dict(self.stage_draws) if tx is not None else {}  # the stage's draws so far
        self.stopped, self.stop_edits = (position, tx), []
        raise Paused(
            {
                'why': 'breakpoint',
                'key': hit,
                'at': hit,
                'time': self.view.t,
                'member': occ.ent.id,
                'occurrence': occ.label,
                'next': origin,
                'inside': tx is not None,
            }
        )

    def _next_time(self, horizon):
        t = self.view.t
        if horizon is not None and t >= horizon:
            return None
        known = [o.due for o in self.scheduled]
        known += [
            tr.rearm_at
            for tr in self.triggers
            if not tr.armed and tr.rearm_at is not None and tr.rearm_at > t
        ]
        if horizon is not None:
            known.append(horizon)
        times = [t + s for s in self.stops if s > 0] + known
        if not times:
            return None
        first = min(times, key=float)
        if isinstance(first, Irrational):
            raise NotCovered(
                f'the next moment after t = {t} h is a contact at an irrational time (about {float(first):.6g} h)'
            )
        self.contact_levels = {}
        if known:
            moment = min(known)
            if moment - first <= self.config.crossing and self._grouped(moment):
                return moment
        return first

    def _grouped(self, moment):
        """A physical comparison and a scheduled instant in one window share the scheduled time.
        A single store takes its exact rational level at the root. A sum keeps the incoming
        trajectory and must satisfy the comparison band there."""
        view, delta = self.view, moment - self.view.t
        for root, cell, bound in self.bound_contacts:
            if not isinstance(root, Irrational) and abs(root - delta) <= self.config.crossing:
                self.contact_levels[cell] = bound, root
        grouped = bool(self.contact_levels)
        for root, scope, pair, condition in self.contacts:
            if isinstance(root, Irrational) or abs(root - delta) > self.config.crossing:
                continue
            at_root = view.copy()
            at_root.t += root
            at_root.cells.update((c, p(root)) for c, p in view.levels.items())
            at_root.results.update((v, p(root)) for v, p in view.rates.items())
            if condition is not None and not Ev(self, at_root, scope).truth(condition):
                continue
            ev = Ev(self, at_root, scope)
            cells = ev.shared.contact_reads = set()
            ev.num(pair[0])
            ev.num(pair[1])
            if not cells or 't' in cells:
                continue
            grouped = True
            if len(cells) == 1:
                (cell,) = cells
                level = at_root.cells[cell]
                existing, placement = self.contact_levels.get(cell, (None, root))
                if existing is not None:
                    band = max(self.config.rtol, self.config.atol_factor) * max(
                        self.own_scales[cell], abs(existing), abs(level)
                    )
                    if abs(existing - level) > band:
                        raise RunFailed(f'incompatible crossing levels of {label(cell)} at {moment} h')
                    level = existing
                self.contact_levels[cell] = level, placement
                continue
            at_root.t = moment
            at_root.cells.update((c, p(delta)) for c, p in view.levels.items())
            at_root.results.update((v, p(delta)) for v, p in view.rates.items())
            a, b = ev.num(pair[0]), ev.num(pair[1])
            band = ev.band(*pair, a, b)
            if abs(a - b) > band:
                names = ', '.join(sorted(label(c) for c in cells))
                raise RunFailed(
                    f'the crossing of {names} at {moment} h cannot be certified: '
                    f'residual {a - b} exceeds the comparison band {band}'
                )
        return grouped

    def _placements(self, tau):
        """Directed corrections for all single-store placements, using the incoming polynomials."""
        levels = self.view.levels
        residual = {cell: target - levels[cell](tau) for cell, (target, _) in self.contact_levels.items()}
        if not any(residual.values()):
            return self.moving, {}, {}
        rates = {name: poly for _, _, poly, name in self.moving}
        legs = sorted(
            (
                leg
                for flow in self.view.live
                for leg in (flow.legs.values() if flow.kind == 'legs' else (flow,))
            ),
            key=lambda leg: leg.number,
        )
        zero = Poly([0])
        moving = [(leg.src, leg.dst, rates.get(leg.label, zero), leg.label) for leg in legs]
        placements = dict(self.contact_levels)
        incidence = {}
        distributions = []
        pending = [cell for cell, difference in residual.items() if difference]
        while pending:
            cell = pending.pop()
            if cell in incidence:
                continue
            target, root = placements[cell]
            signs = incidence[cell] = [int(dst == cell) - int(src == cell) for src, dst, _, _ in moving]
            # The first nonzero derivative on the incoming side gives the direction even at a turn.
            derivative = levels.get(cell, zero)
            earlier = 1
            while not derivative.constant:
                derivative = Poly([i * term for i, term in enumerate(derivative.c) if i])
                direction = earlier * derivative(root)
                if direction:
                    break
                earlier = -earlier
            else:
                lower, upper = self.view.bounds.get(cell, (None, None))
                direction = -1 if target == lower else 1 if target == upper else 0
            speeds = [sign * poly(root) for sign, (_, _, poly, _) in zip(signs, moving)]
            weights = [abs(speed) if speed * direction > 0 else 0 for speed in speeds]
            if not any(weights):
                eligible = [i for i, sign in enumerate(signs) if sign * direction > 0]
                if not eligible:
                    eligible = [i for i, sign in enumerate(signs) if sign]
                weights[eligible[0]] = 1
            total = sum(weights)
            distributions.append([Fraction(weight * sign, total) for weight, sign in zip(weights, signs)])
            # The reference omits constant levels from its polynomial table. Follow only
            # adjusted legs to discover an exactly placed or stationary endpoint they can reopen.
            for weight, (src, dst, _, _) in zip(weights, moving):
                if not weight:
                    continue
                for other in (src, dst):
                    if other is None or other in incidence:
                        continue
                    if other not in placements:
                        level = self.view.cells[other]
                        if other in levels or level not in self.view.bounds.get(other, ()):
                            continue
                        placements[other], residual[other] = (level, tau), 0
                    pending.append(other)
        # A correction to a leg with two placed endpoints also moves the other endpoint.
        equations = [
            ([sum(s * w for s, w in zip(signs, shares)) for shares in distributions], residual[cell])
            for cell, signs in incidence.items()
        ]
        solution = solve_affine(equations, len(distributions))
        if solution is None:
            raise RunFailed('incompatible crossing levels of ' + ', '.join(map(label, residual)))
        amounts, changes = {}, Counter()
        for (src, dst, _, name), weights in zip(moving, zip(*distributions)):
            adjustment = sum(w * factor for w, factor in zip(weights, solution[0]))
            if adjustment:
                amounts[name] = adjustment
                if src is not None:
                    changes[src] -= adjustment
                if dst is not None:
                    changes[dst] += adjustment
        return moving, amounts, changes

    def _frozen_error(self, tau, violations):
        order = {c.label: c.number for f in self.view.live for c in network.connections(f)}
        names = sorted(violations, key=lambda v: (v[0], v[1] != 'outflow', order[v[2]]))
        return FrozenTransfer(self.view.t + tau, names)

    def _advance(self, nxt):
        """Move every store exactly to the time `nxt`, and account for what each flow carried."""
        view = self.view
        tau = nxt - view.t
        failure = self._frozen_transfer(tau)
        if failure is not None:
            tau, problem = failure
            nxt = view.t + tau
        moving, corrections, changes = (
            self._placements(tau) if self.contact_levels and failure is None else (self.moving, {}, {})
        )
        for src, dst, p, name in moving:
            if p.c != (0,) or name in corrections:
                self.ledger.append(
                    ('flow', view.t, nxt, name, src, dst, p.integral()(tau) + corrections.get(name, 0))
                )
        for cell, p in view.levels.items():
            view.cells[cell] = p(tau) + changes.get(cell, 0)
            self._in_range(cell, view.cells[cell])
        for cell in changes.keys() - view.levels.keys():
            view.cells[cell] += changes[cell]
            self._in_range(cell, view.cells[cell])
        for var, p in view.rates.items():
            view.results[var] = p(tau)
        view.t, view.levels, view.rates = nxt, {}, {}
        if failure is not None:
            raise problem

    def _moment(self, setup=False):
        t = self.view.t
        if self.held is None:
            self._note('moment', '')
            self.rounds = 0
            if setup:  # round zero: the setup statements commit as one stage, then settle and check
                if self.model.setup:
                    # A result may have the path of an ordinary field. Its initializer is no solve.
                    self.solved_cells = {
                        var[1]
                        for _, _, _, claimed in network.declarations(self)
                        for var in claimed
                        if var[0] == 'cell'
                    }
                self.phase = 'stages'
                tx = Tx()
                self._execute(self.model.setup, tx, Scope())
                self._commit(tx)
                self._settle_and_check()
            queue = None
        else:
            queue, self.held = self.held, None  # the rest of the paused round, its paused stage first
        while True:
            if queue is None:
                self.rounds += 1
                if self.rounds > self.config.max_rounds:
                    raise RunFailed(self._round_limit())
                self.again = False
                queue = sorted((o for o in self.scheduled if o.due == t), key=lambda o: o.number)
            self.phase = 'stages'
            while queue:
                try:
                    self._stage(queue[0])
                except Paused:
                    self.held = queue
                    raise
                queue.pop(0)
            queue = None
            self._settle_and_check()
            if not (self.again or self.awaiting or any(o.due == t for o in self.scheduled)):
                break
        self.phase = 'between'
        self.stops = self._stops()
        self.frames.append(self.view.copy())

    def _frozen_transfer(self, tau):
        """Count the material into and out of a retired store separately. The flow polynomials
        are exact between events. A reversible route splits the window where its rate changes sign."""
        groups = {}
        for src, dst, rate, name in self.moving:
            for cell, sign in ((dst, 1), (src, -1)):
                owner = _holder(cell.owner) if cell is not None else None
                if isinstance(owner, Occ) and not self.view.cells[Cell(owner, 'active')]:
                    groups.setdefault(cell, []).append((rate * sign, name, sign))
        if not groups:
            return None
        routes = {f.label for f in self.view.live if f.kind == 'reversible'}
        windows, segments = [], []
        running = self.transferred.copy()
        for cell, flows in groups.items():
            cuts = {Fraction(0), tau}
            for rate, _, _ in flows:
                past = Fraction(0)
                while not rate.constant:
                    root = rate(Poly([past, 1])).first_root()
                    if root is None or root >= tau - past:
                        break
                    if isinstance(root, Irrational):
                        raise NotCovered(
                            f'{label(cell)}: a frozen transfer changes direction at an irrational time'
                        )
                    past += root
                    cuts.add(past)
            allowance = self.config.atol_factor * self.own_scales[cell]
            for lo, hi in itertools.pairwise(sorted(cuts)):
                for sign, side in ((-1, 'outflow'), (1, 'inflow')):
                    carrying = []
                    for p, name, orientation in flows:
                        if p((lo + hi) / 2) * sign > 0:
                            directed = name
                            if name in routes:
                                leg = 'forward' if orientation == sign else 'backward'
                                directed = f'{name}.{leg}'
                            carrying.append((p * sign, directed))
                    if not carrying:
                        continue
                    volume = sum((p.integral() for p, _ in carrying), Poly([0]))
                    key = cell, side
                    previous = running.get(key, Fraction(0))
                    running[key] = previous + volume(hi) - volume(lo)
                    segments.append((key, volume, lo, hi))
                    if previous <= allowance < running[key]:
                        left, right = _allowance_root(volume, allowance - previous, lo, hi)
                        names = [(label(cell), side, name) for _, name in carrying]
                        windows.append((left, right, names))
        if not windows:
            self.transferred = running
            return None
        first_lower = min(left for left, _, _ in windows)
        first_upper = min(right for _, right, _ in windows)
        violations = []
        for left, right, names in windows:
            if right <= first_lower + self.config.crossing:
                violations.extend(names)
            elif left <= first_upper + self.config.crossing:
                raise NotCovered('a frozen crossing cannot be separated from the edge of its time group')
        for key, volume, lo, hi in segments:
            if first_upper > lo:
                amount = volume(min(first_upper, hi)) - volume(lo)
                self.transferred[key] = self.transferred.get(key, 0) + amount
        return first_upper, self._frozen_error(first_upper, violations)

    def _settle_and_check(self):
        self.phase = 'settle'
        network.settle(self)
        self._finish_delays()
        self.phase = 'conditions'
        self._conditions()

    def _round_limit(self):
        t, limit = self.view.t, self.config.max_rounds
        fired = Counter(e[2] for e in self.trace if e[0] == 'fire' and e[1] == t)
        started = Counter(e[2].split('#')[0] for e in self.trace if e[0] == 'start' and e[1] == t)
        again = ', '.join(f'{name} ({n} times)' for name, n in fired.items() if n > 1)
        events = ', '.join(f'{name} ({n} starts)' for name, n in started.items())
        return (
            f'more than {limit} rounds at t = {t} h: the limit max_rounds is {limit} rounds at one time. '
            + (f'Triggers that fired again and again: {again}. ' if again else '')
            + f'Events started at this time: {events or "none"}.'
        )

    # --- step 1: stages ----------------------------------------------------------------------------

    def _note(self, kind, label, step=None, origin=''):
        """Add an entry to the trace, at the time and in the round where the run is."""
        self.trace.append(Entry(kind, self.view.t, label, step, self.rounds, origin))

    def _quantity(self, cell, value):
        """A number of a cell in its declared unit, for a message: `8 L`."""
        declared = self.fields.get(cell)
        unit = declared.unit if declared is not None else ''
        if not unit or not isinstance(value, Fraction):
            return str(value)
        return f'{value / (self.model.units.get(unit) or scale_of(unit))} {unit}'

    def scope_of(self, owner):
        """The scope in which the cells of an owner are read."""
        if isinstance(owner, Occ):
            return Scope(owner.ent, owner)
        if isinstance(owner, (FlowRT, LegRT)):
            return (owner.flow if isinstance(owner, LegRT) else owner).scope
        return Scope(owner)

    def _stage(self, occ):
        """Run one stage and commit it. A prompt in it raises `Paused` and leaves the state as it was."""
        step = occ.event.steps[occ.step]
        if self.breakpoints or self.passed:
            self._stop(occ, step.origin, first=occ.step == 0)
        scope = self.scope_of(occ)
        tx = Tx(occ)
        self.stage_draws = {}
        ran = step.guard is None or Ev(self, self.view, scope, tx=tx).truth(
            step.guard
        )  # the guard is read once, now
        if ran:
            try:
                self._execute(step.body, tx, scope)
            except RunFailed as e:
                raise type(e)(f'{e} [stage {occ.step + 1} of {occ.label}, t = {self.view.t} h]') from None
        self.scheduled.remove(occ)
        occ.due, self.kept_draws = None, {}
        self.passed = {
            where: edits for where, edits in self.passed.items() if where[:2] != (occ.number, occ.step)
        }
        mark = len(self.trace)
        self._note('stage' if ran else 'skip', occ.label, occ.step, step.origin)
        self._commit(tx, mark)
        self._reach(occ, occ.step + 1)

    def _execute(self, statements, tx, scope, owner=None):
        """Run statements in written order into `tx`. `owner` names the firing of a trigger that
        runs its body; elsewhere the scope's occurrence or member owns the draws (R-A2-17)."""
        for s in statements:
            if tx.occ is not None and (self.breakpoints or self.passed):
                self._stop(tx.occ, s.origin, tx)
            ev = Ev(self, self.view, scope, tx=tx, may_draw=True, owner=owner)
            if isinstance(s, Assign):
                self._assign(s, ev, tx)
            elif isinstance(s, Start):
                self._queue(s, ev, tx)
            elif isinstance(s, Move):
                self._move(s, ev, tx)
            elif isinstance(s, Branch):  # decision D11
                self._execute(s.then if ev.truth(s.condition) else s.other, tx, scope, owner)
            elif isinstance(s, Switch):
                self._execute(self._select(s, ev), tx, scope, owner)
            else:
                raise RunFailed(f'{s!r} is not a statement')

    def _queue(self, s, ev, tx):
        """`.start(...)`: the arguments are read once, at the caller, left to right. On a collection
        the members start in the order of its keys, and equal keys in creation order."""
        target = ev.val(s.event)
        args = [ev.val(a) for a in s.args]
        if isinstance(target, Coll):
            members = sorted(
                ((k, self.key_of(m, self.view), ev.deref(v)) for k, m, v in target.items), key=lambda x: x[:2]
            )
            target = [b for _, _, b in members]
        else:
            target = [target]
        for b in target:
            if not isinstance(b, Bound):
                raise RunFailed(f'{show(s.event)}.start(...): not an event')
            tx.starts.append((b, args))

    def _select(self, s, ev):
        """The body that a `switch` runs (decision D1). The guards are read once, before the
        selector. A draw as the selector chooses among the eligible outcomes: those
        whose case has no false guard. With none eligible, the `else` body runs and nothing is drawn."""
        eligible = [c.guard is None or ev.truth(c.guard) for c in s.cases]
        node = s.selector
        if node._k == 'call' and node._a[1] == 'draw':
            dist = ev.producer(node)
            if dist.kind != 'categorical':
                raise RunFailed(f'switch {show(node)}: a switch draws from a categorical distribution')
            barred = {c.value for c, ok in zip(s.cases, eligible) if not ok}
            allowed = [m for m, _ in dist.params if m not in barred]
            if not allowed:
                return s.default or []
            chosen = ev.produce(node, allowed)
        else:
            chosen = ev.val(node)
        for c, ok in zip(s.cases, eligible):
            if ok and c.value == chosen:
                return c.body
        return s.default or []

    def _assign(self, s, ev, tx):
        target = ev.ref(s.target)
        if isinstance(target, Res):
            raise Diagnostic(f'{show(s.target)} is a computed result and has its own writer')
        if not isinstance(target, Cell) or not (target in self.view.cells or target in tx.writes):
            raise RunFailed(f'{show(s.target)} is not a declared, writable value')
        d = self.fields.get(target)
        if d is not None and (d.readonly or d.kind == 'input'):
            raise Diagnostic(
                f'{label(target)} is {"readonly" if d.readonly else "an input"}: it cannot be assigned'
            )
        holder = _holder(target.owner)
        if isinstance(holder, Occ) and not self.view.cells[Cell(holder, 'active')]:
            raise RunFailed(
                f'{label(target)} belongs to the finished occurrence {holder.label}, which is frozen'
            )
        if (isinstance(target.owner, Occ) and target.name in BUILTIN) or target in self.solved_cells:
            raise Diagnostic(f'{label(target)} cannot be assigned')
        value = ev.val(s.value)
        if s.op != '=':
            current = ev.cell(target)
            value = current + value if s.op == '+=' else current - value
        self._in_range(target, value)
        tx.writes[target] = value

    def _move(self, s, ev, tx):
        amount = ev.val(s.amount)
        if not isinstance(amount, Fraction) or amount < 0:
            raise RunFailed(
                f'move {show(s.amount)}: the amount must be a number that is not negative, and is {amount!r}'
            )
        src, dst = ev.ref(s.source), ev.ref(s.destination)
        for c in (src, dst):
            d = self.fields.get(c) if isinstance(c, Cell) else None
            if (
                not isinstance(c, Cell)
                or not isinstance(ev.cell(c), Fraction)
                or (d is not None and d.kind != 'value')
                or isinstance(self.view.cells.get(c), FormulaV)
            ):
                raise Diagnostic(
                    f'move: {show(s.source if c is src else s.destination)} is not a stored quantity'
                )
        for c in dict.fromkeys((src, dst)):
            holder = _holder(c.owner)
            if amount != 0 and isinstance(holder, Occ) and not self.view.cells[Cell(holder, 'active')]:
                raise RunFailed(
                    f'{label(c)} belongs to the finished occurrence {holder.label}, which is frozen'
                )
        if src == dst:
            # One store at both ends: the debit and the credit cancel, so the move writes nothing and
            # checks nothing (its resulting inventory is its own); the books still show it.
            tx.moves.append((src, dst, amount, s.origin))
            return
        after = {src: ev.cell(src) - amount, dst: ev.cell(dst) + amount}
        for c, v in after.items():  # both inventories are checked before anything changes
            lo, hi = self.view.bounds.get(c, (None, None))
            if (lo is not None and v < lo) or (hi is not None and v > hi):
                raise RunFailed(
                    f'move of {amount} from {label(src)} to {label(dst)} fails: {label(c)} would hold {v}, '
                    f'outside its range [{lo}, {hi}]; nothing is moved'
                )
        tx.writes.update(after)
        tx.moves.append((src, dst, amount, s.origin))

    def _commit(self, tx, mark=None):
        """Publish the writes of a stage and register the occurrences that it queued. A commit that
        fails is discarded whole, as the engine's: its writes, its moves and its children leave the
        state, and the trace loses what it noted from `mark` (the entry of its stage or firing) on;
        the run stops there, where a read sees what the earlier commits made."""
        view = self.view
        saved = view.copy(), len(self.ledger), len(self.trace) if mark is None else mark
        try:
            self._publish(tx)
        except RunFailed:
            frame, ledger, trace = saved
            view.__dict__.update(frame.__dict__)
            del self.ledger[ledger:], self.trace[trace:]
            raise

    def _publish(self, tx):
        """The writes, the moves and the starts of a commit."""
        view, t = self.view, self.view.t
        moved = Counter()
        for src, dst, amount, origin in tx.moves:
            self._note_store(src)
            self._note_store(dst)
            moved[src] -= amount
            moved[dst] += amount
            self.ledger.append(('move', t, src, dst, amount))
            self._note('move', tx.occ.label if tx.occ is not None else '', origin=origin)
        for cell, value in tx.writes.items():
            old = view.cells.get(cell)
            if (
                cell in self.stores
                and isinstance(old, Fraction)
                and isinstance(value, Fraction)
                and value - old != moved[cell] + tx.edited[cell]
            ):
                self.ledger.append(
                    ('write', t, cell, value - old - moved[cell] - tx.edited[cell])
                )  # a direct write: from or to outside
            view.cells[cell] = value
            if old != value:  # `elapsed` restarts only when the committed value differs
                view.entered[cell] = t
        starts, tx.starts, tx.writes, tx.moves = tx.starts, [], {}, []
        for bound, args in starts:
            self._register(bound, args)

    def _register(self, bound, args):
        """A start becomes an occurrence: its copies of the arguments, each within its parameter's
        declared range (spec.md:572), then its locals and flows in written order (decision D14)."""
        view, t, ent, event = self.view, self.view.t, bound.ent, bound.event
        occs = view.occs[ent, event.name]
        self._limits(ent, event, occs)
        if len(args) != len(event.params):
            raise RunFailed(
                f'{ent.id}.{event.name}.start: {len(event.params)} arguments are declared and {len(args)} are given'
            )
        occ = Occ(next(self.occ_numbers), ent, event, len(occs), tuple(args))  # numbered from 0
        for name, v in (('started', t), ('done', False), ('active', True), *zip(event.params, args)):
            view.cells[Cell(occ, name)] = v
            view.entered[Cell(occ, name)] = t
        scope = Scope(ent, occ)
        for name, v in zip(event.params, args):  # each argument within its parameter's range
            if name in event.ranges:
                cell = Cell(occ, name)
                view.cells[cell] = self._range(
                    cell, event.ranges[name], Ev(self, view, scope), v, admission=True
                )
        decls = event.locals
        for i, d in enumerate(decls):
            later = _forward(d, decls[i + 1 :])
            if later:
                raise Diagnostic(
                    f'{occ.label}.{d.name}: its initializer names {", ".join(sorted(later))}, declared below it; '
                    'only a formula(...) may name a later local'
                )
            if isinstance(d, Flow):
                self._make_flow(d, occ, scope)
                continue
            cell = Cell(occ, d.name)
            self.fields[cell] = d
            if d.kind == 'formula':
                view.cells[cell] = FormulaV(d.init, scope)
            else:
                ev = Ev(self, view, scope, may_draw=True)
                view.cells[cell] = UNSET if d.init is None else ev.val(d.init)
                view.cells[cell] = self._range(cell, d, ev, view.cells[cell])
            view.entered[cell] = t
            self._endpoints(cell, d, scope)  # an occurrence's own store has endpoints as a member's has
        occs.append(occ)
        self._note('start', occ.label, origin=event.origin)
        if self.phase == 'conditions':
            self.again = True
        self._reach(occ, 0)
        return occ

    def _limits(self, ent, event, occs):
        """`max_occurrences` and `max_active` (decision D6), checked before one more start."""
        view, t, cfg = self.view, self.view.t, self.config
        name = f'{ent.id}.{event.name}'
        if len(occs) >= cfg.max_occurrences:
            raise RunFailed(
                f'{name} would start {len(occs) + 1} times by t = {t} h: the limit max_occurrences is '
                f'{cfg.max_occurrences} starts of one event'
            )
        running = [o for o in occs if view.cells[Cell(o, 'active')]]
        if len(running) >= cfg.max_active:
            oldest = running[0]
            raise RunFailed(
                f'{len(running)} occurrences of {name} are active at once (max_active = {cfg.max_active}) and one more '
                f'starts at t = {t} h. The oldest, {oldest.label}, started at {view.cells[Cell(oldest, "started")]} h '
                f'and waits at {self._where(oldest)}.'
            )

    def _where(self, occ):
        """The step at which an occurrence waits, for a message."""
        step = occ.event.steps[occ.step]
        if isinstance(step, Until):
            return f'`until {show(step.condition)}` (step {occ.step + 1})'
        due = f', due at {occ.due} h' if occ.due is not None else ''
        return f'`after {show(step.delay)}` (step {occ.step + 1}{due})'

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
            return None
        try:  # ordinary inputs of the delay are captured now; a computed result waits for the settlement
            delay = Ev(self, self.view, self.scope_of(occ), may_draw=True, defer=True).val(step.delay)
        except NeedsSettle:
            self.awaiting.append((occ, self.view.copy()))
        else:
            self._schedule(occ, delay, step)
        return None

    def _schedule(self, occ, delay, step):
        if not isinstance(delay, Fraction) or delay < 0:
            raise RunFailed(
                f'the delay {show(step.delay)} of {occ.label} must be a duration that is not negative, and is {delay!r}'
            )
        occ.due = self.view.t + delay
        self.scheduled.append(occ)

    def _finish_delays(self):
        waiting, self.awaiting = self.awaiting, []
        for occ, snapshot in waiting:
            snapshot.results = self.view.results  # the state as captured, the results as just settled
            step = occ.event.steps[occ.step]
            self._schedule(occ, Ev(self, snapshot, self.scope_of(occ), may_draw=True).val(step.delay), step)

    def _complete(self, occ):
        """Normal completion. A store of the occurrence must be empty (the retirement rule). Each
        formula of the occurrence, its flows' settings included, keeps the result it has now, or
        the reason why it has none (decision D7); then its flows leave their endpoints."""
        view, t = self.view, self.view.t
        for cell in sorted((c for c in self.stores if c.owner is occ), key=lambda c: c.name):
            left = view.cells[cell]
            if abs(left) > self.config.atol_factor * max(self.own_scales[cell], abs(left)):
                raise RunFailed(
                    f'{occ.label} cannot finish at t = {t} h: its store {label(cell)} still holds {self._quantity(cell, left)}. '
                    'Wait for it to drain, move the rest to a named stock, or send it to SINK.'
                )
        retiring = [
            cell for cell, v in view.cells.items() if isinstance(v, FormulaV) and _holder(cell.owner) is occ
        ]
        frozen = {cell: self._frozen(cell, occ) for cell in retiring}
        for cell, (value, floor) in frozen.items():
            view.cells[cell] = value
            if floor is not None:
                view.frozen_scales[cell] = floor
        for (owner, _), f in list(self.flow_at.items()):
            if owner is occ and f in view.live:
                view.live.remove(f)
        view.cells[Cell(occ, 'done')], view.cells[Cell(occ, 'active')] = True, False
        self._note('done', occ.label, origin=occ.event.origin)
        if self.phase == 'conditions':
            self.again = True

    def _frozen(self, cell, occ):
        """The result that a formula of a finishing occurrence keeps, or the recorded reason."""
        try:
            evaluator = Ev(self, self.view, Scope())
            value = plain(evaluator.cell(cell))
            field = self.fields.get(cell)
            floor = None
            if type(value) in (int, Fraction) and (field is None or field.scale is None):
                formula = self.view.cells[cell]
                floor = evaluator.formula_scopes[cell].operand(formula.expr)[0]
            return value, floor
        except RunFailed as e:
            return Failed(
                f'{label(cell)} was not available when {occ.label} finished at t = {self.view.t} h: {e}'
            ), None

    # --- step 4: conditions ------------------------------------------------------------------------

    def _conditions(self):
        """Read every trigger, reset and gate on the settled state, and check every assertion over
        state there: a round's assertions read its settled state, before its firings start the
        consequences of the next round, which settles them again (spec: "New consequences due at
        the same timestamp start a further round"). Then act, in a fixed order: firings by receiver
        and declaration, then released gates by the age of the occurrence."""
        view, t = self.view, self.view.t
        fires = []
        for trig in self.triggers:
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
        releases = [
            o
            for o in self._gates()
            if Ev(self, view, self.scope_of(o)).truth(o.event.steps[o.step].condition)
        ]
        self._asserts()
        for trig in fires:
            self._fire(trig)
        for occ in releases:
            self._note('release', occ.label, occ.step)
            self._reach(occ, occ.step + 1)

    def _gates(self):
        return sorted(
            (o for occs in self.view.occs.values() for o in occs if o.waiting), key=lambda o: o.number
        )

    def _after(self, condition, scope):
        """The truth of a condition just after this instant."""
        network.motion(self)
        return Ev(self, self.view, scope, mode='germ').truth(condition)

    def _fire(self, trig):
        """One firing: its captures, its body, then a `reset after` duration, captured now. The
        firing owns their draws (R-A2-17): `pump.work.when[0]!2` is the second firing, from 1."""
        t = self.view.t
        firing = f'{trig.label}!{trig.firings + 1}'
        caps = {}
        for name, expr in trig.decl.captures:
            ev = Ev(self, self.view, Scope(trig.ent, None, dict(caps)), may_draw=True, owner=firing)
            caps[name] = ev.val(expr)
        tx = Tx()
        self._execute(trig.decl.starts, tx, Scope(trig.ent, None, caps), firing)
        trig.caps, trig.armed, trig.firings = caps, False, trig.firings + 1
        if trig.decl.reset is not None and trig.decl.reset[0] == 'after':
            ev = Ev(self, self.view, Scope(trig.ent, None, caps), may_draw=True, owner=firing)
            trig.rearm_at = t + ev.num(trig.decl.reset[1])
        mark = len(self.trace)
        self._note('fire', trig.label, origin=trig.decl.origin)
        self.again = True
        self._commit(tx, mark)

    def _asserts(self):
        for a in self.model.asserts:
            scope = Scope(self.ents[a.owner]) if a.owner else Scope()
            if not Ev(self, self.view, scope).truth(a.condition):
                raise RunFailed(f'assert {a.text or show(a.condition)} fails at t = {self.view.t} h')

    def _stops(self):
        """The times after this moment at which something can happen without a scheduled stage."""
        view = self.view
        stops = network.motion(self)
        self.contacts = [(*found, None) for found in self.switch_contacts]

        def watch(expr, scope, strict, armed=False):
            ev = Ev(self, view, scope, mode='germ')
            ev.shared.strict = strict
            v = ev.val(expr)
            stops.extend(ev.shared.stops)
            if armed:
                self.contacts.extend((*found, expr) for found in ev.shared.contacts)
            return v

        for trig in self.triggers:
            scope = Scope(trig.ent, None, trig.caps)
            watch(trig.decl.when, scope, True, trig.armed)
            if not trig.armed and trig.decl.reset is not None and trig.decl.reset[0] == 'when':
                watch(trig.decl.reset[1], scope, True)
        for occ in self._gates():
            watch(occ.event.steps[occ.step].condition, self.scope_of(occ), True, True)
        for a in self.model.asserts:  # an assertion on state is also checked just after each moment
            if watch(a.condition, Scope(self.ents[a.owner]) if a.owner else Scope(), False) is False:
                raise RunFailed(f'assert {a.text or show(a.condition)} fails just after t = {view.t} h')
        return stops

    # --- what the evaluator asks of the run ----------------------------------------------------------

    def pull(self, var):
        """Solve the calculation of a result that another calculation reads."""
        network.pull(self, var)

    def incident(self, flows, end):
        """The connections of an endpoint among the given flows."""
        return network.incident(flows, end)

    def key_of(self, member, view):
        """The natural key of a member: the start time of an occurrence, else its creation number."""
        return view.cells[Cell(member, 'started')] if isinstance(member, Occ) else member.number

    def entered(self, cell, tx, view):
        """The time at which a state took its present value. A write in the stage counts only when
        it differs from the committed value."""
        if tx is not None and cell in tx.writes and tx.writes[cell] != view.cells.get(cell):
            return view.t
        return view.entered.get(cell, Fraction(0))

    # --- draws ---------------------------------------------------------------------------------------

    def _site(self, node):
        """The site of a draw: its place in the model (in a program, the program's site)."""
        return self.sites.get(id(node), show(node))

    def _owner(self, ev):
        """Who executes a draw (R-A2-17): the occurrence (`pump.work#0`), the firing of
        a trigger (`pump.work.when[0]!1`), or the member; the setup belongs to the root, whose id
        is `''` as in a program."""
        s = ev.scope
        if s.occ is not None:
            return s.occ.label
        return ev.shared.owner or (s.this.id if s.this is not None else '')

    def _key(self, node, ev):
        """The key of a draw: its site and its owner, never its place in a stream."""
        return f'{self._site(node)}|{self._owner(ev)}'

    def _uniform(self, key):
        digest = hashlib.sha256(f'{self.config.seed}|{key}'.encode()).digest()
        return Fraction(int.from_bytes(digest[:8], 'big') * 2 + 1, 2**65)

    def draw(self, dist, node, ev, eligible=None):
        """An executed `.draw()`: the median in a median run, a keyed sample in a sampled run. A
        draw that a paused stage made is kept and given again when the stage resumes."""
        key = self._key(node, ev)
        if key in self.kept_draws:
            value = self.kept_draws[key]
        else:
            if dist.kind == 'categorical':
                value = self._outcome(dist, key, eligible)
            elif self.config.mode == 'median':
                value = self.describe(dist, 'median')
            elif dist.kind == 'uniform':
                lo, hi = dist.params
                value = lo + (hi - lo) * self._uniform(key)
            elif dist.kind == 'normal':  # the quantile is a float, made exact to within 1e-9
                mean, std = dist.params
                quantile = NormalDist().inv_cdf(float(self._uniform(key)))
                value = mean + std * Fraction(quantile).limit_denominator(10**9)
            else:
                raise NotCovered(f'a sampled draw of the distribution {dist.kind}')
            self.draws.append((key, value))
            self._note('draw', self._owner(ev), origin=self._site(node))
        self.stage_draws[key] = value
        return value

    def _outcome(self, dist, key, eligible):
        """A draw of a categorical distribution among the eligible outcomes, their probabilities
        scaled to sum to one. A median run takes the most likely, the first declared on a tie."""
        outcomes = [(m, p) for m, p in dist.params if eligible is None or m in eligible]
        total = sum(p for _, p in outcomes)
        if total == 0:
            raise RunFailed(
                f'no eligible outcome has a probability to draw: {", ".join(m for m, _ in outcomes)}'
            )
        if self.config.mode == 'median':
            return max(outcomes, key=lambda mp: mp[1])[0]
        u, reached = self._uniform(key), Fraction(0)
        for m, p in outcomes:
            reached += p / total
            if u < reached:
                return m
        return outcomes[-1][0]

    def describe(self, dist, name):
        """A read-only property of a distribution, which consumes no draw."""
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

    # --- what a caller reads -------------------------------------------------------------------------

    def read(self, expr, at=None, owner=None, unit=None):
        """The value of an expression at a time of the run, from the record, in `unit` if one is
        given (the run itself works in canonical units). A read changes nothing."""
        at = self.view.t if at is None else number(at)
        frames = [f for f in self.frames if f.t <= at]
        if (self.error is not None or self.paused is not None) and at == self.view.t:
            frame = self.view.copy()  # where the run stopped: what its rounds had committed
        elif not frames or at > self.view.t:
            raise RunFailed(f'the run has no record at t = {at} h')
        else:
            frame = frames[-1].copy()
        tau = at - frame.t
        if tau > 0:
            for cell, p in frame.levels.items():
                frame.cells[cell] = p(tau)
            for var, p in frame.rates.items():
                frame.results[var] = p(tau)
            frame.t, frame.levels, frame.rates = at, {}, {}
        ev = Ev(self, frame, Scope(self.ents[owner]) if owner else Scope())
        v = ev.val(lit(expr))
        size = Fraction(1) if unit is None else scale_of(unit)
        if isinstance(v, Coll):  # a projection: each member's value, read on the same frame
            return Coll((k, m, _in_unit(plain(ev.deref(x)), size)) for k, m, x in v.items)
        return _in_unit(plain(v), size)

    def report(self, expr, times, owner=None, unit=None):
        """What a report shows: the value at each time, or `Unavailable` with the reason. An invalid
        read is the report's affair: it cannot fail the run, which is over."""
        out = []
        for at in times:
            try:
                out.append(self.read(expr, at, owner, unit=unit))
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
            elif e[0] in ('opening', 'write'):
                tot[e[0]] += e[3]
        expected = tot['opening'] + tot['write'] + tot['from_source'] - tot['to_sink']
        return {
            'held': held,
            **{k: tot[k] for k in ('opening', 'write', 'from_source', 'to_sink')},
            'balanced': held == expected,
        }


def _in_unit(x, size):
    """A canonical number in the unit of the given size; anything that is not a number unchanged."""
    return x / size if isinstance(x, Fraction) else x


def _holder(owner):
    """The entity or occurrence that holds a cell: a flow's settings belong to the flow's owner,
    an endpoint's settings to the holder of its store."""
    if isinstance(owner, LegRT):
        return owner.flow.owner
    if isinstance(owner, FlowRT):
        return owner.owner
    if isinstance(owner, End):
        return _holder(owner.cell.owner)
    return owner


def _plain_names(e):
    """The bare names that an expression reads, outside any `formula(...)`: a formula is read later."""
    if isinstance(e, E):
        if e._k == 'formula':
            return set()
        return ({e._a[0]} if e._k == 'name' else set()).union(*(_plain_names(a) for a in e._a))
    if isinstance(e, (tuple, list)):
        return set().union(*(_plain_names(a) for a in e))
    return set()


def _forward(d, later):
    """The later declarations of an event that the plain initializers of `d` read (decision D14):
    those of a flow, and of a local with the settings of its endpoints. A formula local, a formula
    setting, or an allocation (read when the rates settle) may name them."""
    if isinstance(d, Flow):
        parts = [d.source, d.sink, d.request, d.capacity]
        parts += [p for one in d.legs for p in (one.source, one.sink, one.request, one.capacity)]
    elif d.kind == 'formula':
        return set()
    else:
        parts = [d.init, d.lo, d.hi]
        parts += [p for ep in (d.outflow, d.inflow) if ep is not None for p in (ep.capacity, ep.request)]
    return {x.name for x in later} & _plain_names(parts)


def _sites(model):
    """A stable name for each place of the model where a draw is written: the site that a
    program gave it, or else its path in the model."""
    sites = dict(model.sites)

    def walk(x, path):
        if isinstance(x, E):
            if x._k == 'call' and x._a[1] == 'draw' and id(x) not in sites:
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
