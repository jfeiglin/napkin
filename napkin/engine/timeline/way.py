"""What an installed set publishes and reports when the timeline reaches a moment."""

from bisect import bisect_right
from math import inf

from ...core import expr as nodes
from ...core.units import rational
from ..continuous.transfers import ClockLeg, HeldAmounts, certified_amount, clock_primitive, held_elapsed
from .stocks import RestingAmounts, RestingRates


class MovingTransfers:
    """Read one directed connection's accepted prefix using the installed method's dense output."""

    @staticmethod
    def held_settings(plan, names):
        """Captured settings are fixed for the whole installation, including a capped pipe."""
        return all(plan.values[name].kind == 'capture' for name in names)

    def capacity_turns(self, relations=()):
        """The times when an affine-clock request meets an individual hard limit.
        Even a continuous allocation can have a kink. Ending Radau's smooth step
        there prevents its later, clipped samples from changing the incoming curve."""
        plan = self.run.plan
        limits = list(relations)
        for name in self.leg_rows:
            flow = plan.flows.get(name)
            if flow is None or flow.kind != 'directed':
                continue
            if flow.capacity is not None:
                limits.append((flow.request, nodes.ref(flow.capacity)))
            for key in ((flow.source, 'outflow'), (flow.sink, 'inflow')):
                end = plan.ends.get(key)
                if end and end.capacity is not None and len(plan.incident(*key)) == 1:
                    limits.append((flow.request, nodes.ref(end.capacity)))

        def affine(node, expansion):
            if isinstance(node, nodes.Ref) and node.name in self.run.env and not expansion.time:
                value = plan.values[node.name]
                if value.kind == 'capture':
                    return rational(self.run.env[node.name]), 0
            if expansion.leaves or expansion.stepped:
                return None
            integral = clock_primitive(node, plan, expansion)
            if integral is not None and len(integral) <= 3:
                return integral[1], 2 * integral[2] if len(integral) == 3 else 0
            return None

        roots = set()
        for request, capacity in limits:
            req = nodes.ref(request)
            left, right = plan.expansion(req), plan.expansion(capacity)
            if not (left.time or right.time):
                continue
            a, b = affine(req, left), affine(capacity, right)
            if a is not None and b is not None and a[1] != b[1]:
                roots.add(float((a[0] - b[0]) / (b[1] - a[1])))
        return sorted(roots)

    def smooth_until(self, start, end):
        if self.cap_turns:
            after = bisect_right(self.cap_turns, start)
            if after < len(self.cap_turns):
                return min(end, self.cap_turns[after])
        return end

    def _pending_end(self):
        return self.pending.end

    @property
    def probe_until(self):
        """A just-after read can follow a prepared trajectory only through its endpoint."""
        return self._pending_end() if self.pending is not None else inf

    def _transferred(self, name, t):
        row = self.leg_rows[name]
        if t == self.amounts.through:
            return self.amounts.amount(row)
        arrival = getattr(self, 'arrival_amounts', None)
        if arrival is not None and t == arrival.through:
            return arrival.amount(row)
        if self.pending is None or not self.amounts.through < t <= min(
            self.run.clock.apart(self._pending_end()), self.run.now
        ):
            raise ValueError('transfer requested outside the accepted interval')
        leg = self.amounts.clocks.get(row)
        mode = leg.selection(*self._clock_bounds()) if leg is not None else None
        return self.amounts.prefix(row, t, mode, lambda: self._pending_amount(row, t))


class Way:
    """An engine supplies its answers on its installed trajectory and the contacts it located."""

    sample_on_read = False
    probe_until = inf  # a held value or outgoing line supports the full just-after probe
    resting_rates = None
    resting = None
    recorded_through = None  # end of the last dense span already given to the recorder

    def transferred(self, name, t):
        """Cumulative physical amount on an accepted prefix, including precision-certified legs."""
        value = self.raw_transferred(name, t)
        if self.resting is not None:
            value += self.resting.amount(self, name, t)
        return value

    def raw_transferred(self, name, t):
        certified = getattr(self, 'certified', None)
        if certified is not None:
            entry = certified.get(name)
            if entry is not None and t == entry[0] and t <= self.run.now:
                return entry[1]
        value = self._transferred(name, t)
        donor = getattr(self, 'donor', None)
        if donor is not None and name == donor[0]:
            # When almost all of a single pipe's source has left, its remaining stock
            # is better conditioned than subtracting an integral nearly as large as its start.
            level = self.accepted_level(donor[1], t)
            if 0 <= level < donor[2] / 2:
                value = rational(donor[2]) - rational(level)
        if self.resting_rates is not None and (offset := self.resting_rates.offsets.get(name)) is not None:
            since, adjustment = offset
            if since != t:
                value += adjustment * held_elapsed(since, t)
        changes = getattr(self, 'adjustments', None)
        return value + changes.get(name, 0) if changes else value

    def held_region(self):
        """The branches that the present segment runs on (`region.Region`), or None for a way that
        holds none. Inside a segment only a located switch changes a branch."""
        return getattr(self, 'region', None)

    def held_value(self, name, t):
        """A value at t on the branches of the present segment (`integrate.branch_expression`), as
        this way applied it there. A check over the segment's accepted window reads what the segment
        ran on, never a comparison decided again at each time: near a located switch the raw
        comparison can flip inside its band before the switch."""
        region = self.held_region()
        return self.run.value(name, t) if region is None else self.run.in_region(name, t, region)

    def resting_value(self, name, t):
        if self.resting_rates is not None:
            side = self.resting_rates.sides.get(self.place[name])
            if side is not None:
                return float(self.y[self.place[name]])
        if self.resting is not None and name in self.resting.rows:
            bound = self.resting.rows[name][0]
            return bound
        return None

    def set_resting(self, levels, t):
        if not levels and self.resting is None:
            return
        if self.resting is None:
            self.resting = RestingAmounts()
        self.resting.update(self, levels, t)
        if not self.resting.rows:
            self.resting = None

    def balance_rates(self, changed, rates, t):
        if changed:
            if self.resting_rates is None:
                self.resting_rates = RestingRates()
            self.resting_rates.update(self, changed, rates, t)

    def single_donor(self, values):
        if len(self.leg_rows) == 1 and not self.amounts.clocks:
            name = next(iter(self.leg_rows))
            leg = self.run.plan.connections[name]
            if leg.source is not None and leg.source != leg.sink and values[leg.source] > 0:
                self.donor = name, leg.source, float(values[leg.source])

    def correct(self, name, amount):
        if self.resting is not None:
            self.resting.invalidate()
        if not hasattr(self, 'adjustments'):
            self.adjustments = {}
        self.adjustments[name] = self.adjustments.get(name, 0) + amount
        if name in getattr(self, 'certified', {}):
            t, total = self.certified[name]
            self.certified[name] = t, total + amount

    def accept_amounts(self, start, end, amounts):
        self.amounts.accept(start, end, amounts)
        if self.resting is not None:
            self.resting.invalidate()

    def certify(self, name, start, end, amount):
        """Retain a higher-precision prefix at the time accepted for both ends of this leg."""
        base = self.transferred(name, start)
        if not hasattr(self, 'certified'):
            self.certified = {}
        self.certified[name] = end, base + amount
        if self.resting is not None:
            self.resting.invalidate()

    def watch_leg(self, name, start, *, label=None):
        """Integrate the actual directed rate for a boundary-sensitive stock. Separate an exact
        rectangle or clock primitive from a measured contribution to its physical allowance."""
        run, plan = self.run, self.run.plan
        rate = f'{name}.actual_rate'
        if isinstance(self.amounts, HeldAmounts) or rate in getattr(self, 'held_rates', ()):
            speed = rational(run.value(rate, start))
            if (
                self.resting_rates is not None
                and (offset := self.resting_rates.offsets.get(name)) is not None
            ):
                speed += offset[1]
            return lambda a, b: (held_elapsed(a, b) * speed, 0)
        row = self.leg_rows[name]
        leg = self.amounts.clocks.get(row)
        flow = plan.flows.get(name)
        if leg is None and flow is not None and flow.kind == 'directed' and name not in plan.solved_flows:
            ends = (flow.source, 'outflow'), (flow.sink, 'inflow')
            local = not any(key in plan.ends and plan.settled(plan.ends[key]) for key in ends)
            settings = [nodes.ref(n) for n in (flow.request, flow.capacity) if n]
            if local and not run.triggers.moving_reads(*settings):
                speed = rational(run.value(rate, start))
                leg = ClockLeg.of((0, speed), start, flow, self.place, plan)
        if leg is not None:
            mode = leg.selection(*self._clock_bounds())
            if mode == leg.REQUEST:
                return lambda a, b: (leg.integral(a, b), 0)
            if mode == leg.STOPPED:
                return lambda a, b: (0, 0)

        def measured(a, b):
            if b == a:
                return 0, 0
            return 0, certified_amount(
                lambda t: abs(run.value(rate, t)),
                a,
                b,
                label or f'{name}: cannot certify the frozen transfer',
            )

        return measured

    def separate_contacts(self, t, through):
        """Located bounds and thresholds outside their physical comparison bands at t."""
        for at, name, kind in self.timing_events(through):
            if at != t and self.run.clock.within(at, t) and kind in ('lower bound', 'upper bound'):
                target = self.run.bounds[name][kind == 'upper bound']
                actual = self.incoming_level(name, t)
                if abs(actual - target) > self.run.comparison_band(name, actual, target):
                    yield at
        for located, pair in self.crossed_operands(t, through):
            if located != t and not self.run.triggers.anchor(None, *pair, t, located):
                yield located

    def contacts_at(self, t, through):
        for event in self.timing_events(through):
            if self.run.clock.within(event[0], t):
                yield event

    def crossed_operands(self, t, through):
        """Operands of physical switches located in the moment's closed time window."""
        return (
            (at, pair)
            for at, pair in self.detected_switches()
            if at <= through and self.run.clock.within(at, t)
        )

    def detected_switches(self):
        return ()

    def incoming_level(self, name, t):
        """The incoming trajectory, including its continuation to a coalesced moment."""
        return self.level_at(name, t)

    def accepted_level(self, name, t):
        opening = self.run.opening_levels if t == self.run.now else {}
        return opening[name] if name in opening else self.incoming_level(name, t)

    def incoming_rates(self, t):
        """The physical directed rates on the already installed trajectory."""
        return lambda name: self.run.value(f'{name}.actual_rate', t)

    def arrive(self, t, through):
        """Close the incoming segment after the stages and give the names the re-share needs."""
        if self.peek() <= t or any(self.contacts_at(t, through)):
            changed, met = self.snap(t, through)
            yield from changed
            yield from met
        yield from self.cut(t) or ()

    def lookahead(self, t, through):
        """Inspect the rest of this time band when a prepared step ends inside it."""

    def switched_at(self, t):
        """The flows whose switches this segment reached at t."""
        return ()

    def publish(self, t, incoming=False, flows=None):
        """Publish the segment's numeric answers and the totals of the endpoints it serves."""
        whole = flows is None
        if whole:
            flows = self.flows
        answers = self.answers_at(t, incoming, flows)
        run = self.run
        run.published.update(answers)
        ends = {}
        for flow in flows:
            for connection in run.plan.flows[flow].connections:
                amount = run.published.get(f'{connection.name}.actual_rate', 0.0)
                for store, side in ((connection.source, 'outflow'), (connection.sink, 'inflow')):
                    if store is not None:
                        ends[store, side] = ends.get((store, side), 0.0) + amount
        for (store, side), installed in ends.items():
            # The installed connections still carry the round's opening answer after a stage
            # changes membership. A partial refresh of fixed rows needs their unchanged neighbours.
            total = (
                installed
                if whole
                else sum(run.published.get(f'{c}.actual_rate', 0.0) for c in run.plan.incident(store, side))
            )
            run.published[f'{store}.{side}.actual_rate'] = total
        if self.sample_on_read:
            run.ways.sampled[self.key] = t
