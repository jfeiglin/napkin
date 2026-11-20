"""What an installed set publishes and reports when the timeline reaches a moment."""


class Way:
    """An engine supplies its answers on its installed trajectory and the contacts it located."""

    sample_on_read = False
    recorded_through = None  # end of the last dense span already given to the recorder

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
