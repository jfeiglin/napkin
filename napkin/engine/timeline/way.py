"""What an installed set publishes and reports when the timeline reaches a moment."""

from ...core import expr as nodes
from ...core.units import rational
from ..continuous.transfers import ClockLeg, HeldAmounts, certified_amount
from .stocks import RestingAmounts, RestingRates


class Way:
    """An engine supplies its answers on its installed trajectory and the contacts it located."""

    sample_on_read = False
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
            opening = self.run.opening_levels if t == self.run.now else {}
            level = opening[donor[1]] if donor[1] in opening else self.incoming_level(donor[1], t)
            if 0 <= level < donor[2] / 2:
                value = rational(donor[2]) - rational(level)
        if self.resting_rates is not None and (offset := self.resting_rates.offsets.get(name)) is not None:
            since, adjustment = offset
            value += adjustment * (rational(t) - rational(since))
        changes = getattr(self, 'adjustments', None)
        return value + changes.get(name, 0) if changes else value

    def resting_value(self, name, t):
        if self.resting_rates is not None:
            side = self.resting_rates.sides.get(self.place[name])
            if side is not None:
                return self.run.bounds[name][side]
        if self.resting is not None and name in self.resting.rows:
            return self.resting.rows[name][0]
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

    def watch_leg(self, name, start):
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
            return lambda a, b: ((rational(b) - rational(a)) * speed, 0)
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
                lambda t: abs(run.value(rate, t)), a, b, f'{name}: cannot certify the frozen transfer'
            )

        return measured

    def contacts_at(self, t, through):
        for event in self.timing_events(through):
            if self.run.clock.within(event[0], t):
                yield event

    def crossed_operands(self, t, through):
        """Operands of physical switches located in the moment's closed time window."""
        return ()

    def incoming_level(self, name, t):
        """The incoming trajectory, including its continuation to a coalesced moment."""
        return self.level_at(name, t)

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
