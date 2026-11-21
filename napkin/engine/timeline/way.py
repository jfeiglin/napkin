"""What an installed set publishes and reports when the timeline reaches a moment."""

from ...core import expr as nodes
from ...core.units import rational
from ..continuous.transfers import ClockLeg, HeldAmounts, certified_amount


class Way:
    """An engine supplies its answers on its installed trajectory and the contacts it located."""

    sample_on_read = False
    recorded_through = None  # end of the last dense span already given to the recorder

    def transferred(self, name, t):
        """Cumulative physical amount on an accepted prefix, including precision-certified legs."""
        certified = getattr(self, 'certified', None)
        if certified is not None:
            entry = certified.get(name)
            if entry is not None and t == entry[0] and t <= self.run.now:
                return entry[1]
        value = self._transferred(name, t)
        changes = getattr(self, 'adjustments', None)
        return value + changes.get(name, 0) if changes else value

    def correct(self, name, amount):
        if not hasattr(self, 'adjustments'):
            self.adjustments = {}
        self.adjustments[name] = self.adjustments.get(name, 0) + amount
        if name in getattr(self, 'certified', {}):
            t, total = self.certified[name]
            self.certified[name] = t, total + amount

    def certify(self, name, start, end, amount):
        """Retain a higher-precision prefix at the time accepted for both ends of this leg."""
        base = self.transferred(name, start)
        if not hasattr(self, 'certified'):
            self.certified = {}
        self.certified[name] = end, base + amount

    def watch_leg(self, name, start):
        """Integrate the actual directed rate for a boundary-sensitive stock. Separate an exact
        rectangle or clock primitive from a measured contribution to its physical allowance."""
        run, plan = self.run, self.run.plan
        rate = f'{name}.actual_rate'
        if isinstance(self.amounts, HeldAmounts) or rate in getattr(self, 'held_rates', ()):
            speed = rational(run.value(rate, start))
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
