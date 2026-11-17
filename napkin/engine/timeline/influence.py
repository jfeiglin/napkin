"""What a change of a name can change in a run of a plan: the graph of influence.

The graph follows from the plan alone, with no value of a run. A **place** of the graph is a name
that a run holds (an input, a value, a quantity, a list, the count and the time of an event, the
time at which a mode was entered), a rule (`('rule', index)`) or an output (`('output', name)`).
A place feeds another when the engine reads the first to make the second:

- what the start of a quantity reads, and what its rate reads (`Plan.rate_nodes`: its own parts,
  and for a flow with a limit, a coupling or a source that rests on its bound, each flow and limit
  that decides what it delivers), feed the quantity;
- what a member of a list reads feeds each part that reads the list: `Plan.reads` gives the
  reads of a node through the members of its lists, and each read below is such a read;
- what a rule reads (its condition, its clocks, its value, its delay, its `while`, its window, its
  drawn and past values, and the chance, the condition, the sets and the moves of each outcome)
  feeds the rule; the rule feeds what its steps write (each quantity and mode that an outcome sets
  or moves, the time at which a mode was entered, the count and the time of each event that it
  emits), and each rule that an outcome fires. A rule that a change reaches can happen at another
  time, or not at all, so everything that it writes is reached;
- a quantity that can rest on its bound feeds the fact that it rests (`Floor.flag`), which the
  rate of each quantity that its flows deliver to reads;
- what an output reads feeds the output.

`Influence.after(names)` is every place that a change of one of the names can reach. A place that
is not there cannot change: the derivative of an output by an input that does not reach it is
zero by the structure of the model, whatever the values are (`reports.derivatives`). The graph can
have a place too many (a part that the values of a run never use), never one too few: each read of
the engine is one of the reads above.

`Influence(plan, paths=True)` is the finer graph of a run whose outcomes are given
(`Run(outcomes=…)`), for the question whether an output is continuous in a name
(`engine/expectations.derivatives`). There the place of a rule stands for when the rule has a
step and whether it has one, and two kinds of read do not feed it:

- what the chance of an outcome reads: the chance decides nothing in such a run;
- what the value of a `set` or of a move reads: it changes the value that the step writes, and
  not the step. It feeds the names that the step writes.

`between(name, output)` gives the places on a way from a name to an output, and `breaks` what, on
such a way, can make the output jump when the name changes by a little.
"""

from __future__ import annotations

from ...core import expr
from ...model.ir import COUNT, ENTERED, TIME
from . import smooth
from .places import output_place, rule_place


def _nodes(nodes):
    return [node for node in nodes if node is not None and not isinstance(node, (bool, int, float, str))]


def chance_nodes(rule):
    """The chance of each outcome of a rule that has one as an expression."""
    return _nodes(outcome.chance for outcome in rule.outcomes if outcome.chance not in (None, 'else'))


def step_nodes(rule):
    """What decides when a rule has a step, whether it has one, and which outcomes it can take:
    every node that the rule reads but its chances and the values that its steps write."""
    nodes = [rule.gate, *rule.times, rule.value, rule.when, rule.delay, rule.keep, *rule.each]
    for extra in rule.extras:
        nodes += [extra.expr, extra.delay, *(node for _, node in extra.args)]
    return _nodes([*nodes, *(outcome.available for outcome in rule.outcomes)])


def written_nodes(rule):
    """[(the names that it changes, the node)] of the value of each `set` and of each move of the
    outcomes of a rule."""
    found = []
    for outcome in rule.outcomes:
        found += [((target,), node) for target, node, _ in outcome.sets]
        found += [((source, target), node) for source, target, node in outcome.moves]
    return [(names, node) for names, node in found if _nodes([node])]


def rule_nodes(rule):
    """Every node that a rule reads."""
    return step_nodes(rule) + [node for _, node in written_nodes(rule)] + chance_nodes(rule)


def rule_writes(plan, rule):
    """Every name that a step of a rule can write, and every rule that it can fire."""
    names, rules = set(), set()
    events = set(rule.emits)
    for outcome in rule.outcomes:
        events |= set(outcome.emits)
        for target, _, _ in outcome.sets:
            names.add(target)
            if target in plan.modes:
                names.add(target + ENTERED)
        for source, target, _ in outcome.moves:
            names |= {source, target}
        rules |= {plan.rule_index[target] for target in outcome.fires if target in plan.rule_index}
    for event in events:
        names |= {event + COUNT, event + TIME}
    return names, rules


def _closure(edges, places):
    found, pending = set(places), list(places)
    while pending:
        for target in edges.get(pending.pop(), ()):
            if target not in found:
                found.add(target)
                pending.append(target)
    return found


class Influence:
    """The graph of influence of a plan (the module)."""

    def __init__(self, plan, paths=False):
        self.plan = plan
        feeds = self.feeds = {}
        fed = self.fed = {}
        # The finer graph: the nodes of the values that the steps of the rules write to a name.
        self.set_nodes = {}

        def feed(sources, target):
            for source in sources:
                if source != 't':
                    feeds.setdefault(source, set()).add(target)
                    fed.setdefault(target, set()).add(source)

        for name, quantity in plan.quantities.items():
            starts = quantity.start if isinstance(quantity.start, tuple) else (quantity.start,)
            for node in set(starts):
                if node is not None and not isinstance(node, (bool, int, float)):
                    feed(plan.reads(node), name)
            if quantity.form != 'value':
                for node in plan.rate_nodes(name):
                    feed(plan.reads(node), name)
        for floor in getattr(plan, 'floors', {}).values():
            # Whether a quantity rests on its bound follows from the quantity and from its flows.
            feed({floor.name}, floor.flag)
            for node in plan.rate_nodes(floor.name):
                feed(plan.reads(node), floor.flag)
        for rule in plan.rules:
            place = rule_place(rule.index)
            if rule.var:
                feed({rule.var}, place)
            for node in step_nodes(rule) if paths else rule_nodes(rule):
                feed(plan.reads(node), place)
            for targets, node in written_nodes(rule) if paths else ():
                for target in targets:
                    feed(plan.reads(node), target)
                    self.set_nodes.setdefault(target, []).append(node)
            names, rules = rule_writes(plan, rule)
            for name in names:
                feed({place}, name)
            for other in rules:
                feed({place}, rule_place(other))
        for name, node in plan.outputs.items():
            feed(plan.reads(node), output_place(name))

    def after(self, places):
        """Every place that a change of one of `places` can reach, with those places."""
        return _closure(self.feeds, places)

    def before(self, places):
        """Every place whose change can reach one of `places`, with those places."""
        return _closure(self.fed, places)

    def between(self, name, output):
        """The places on a way from a name to an output, with the two; none when no way is."""
        return self.after({name}) & self.before({output_place(output)})

    def nodes_of(self, place):
        """The nodes that make a place: the node of an output; the start and the rate of a
        quantity, and in the finer graph the values that the steps of the rules write to it. A
        rule and a name that the model does not make (an input) have none here."""
        plan = self.plan
        if isinstance(place, tuple):
            return [plan.outputs[place[1]]] if place[0] == 'output' else []
        found = list(self.set_nodes.get(place, ()))
        quantity = plan.quantities.get(place)
        if quantity is None:
            return found
        starts = quantity.start if isinstance(quantity.start, tuple) else (quantity.start,)
        found += _nodes(dict.fromkeys(starts))
        if quantity.form != 'value':
            found += plan.rate_nodes(place)
        return found

    def comparisons(self, node, moved):
        """Whether a node has a comparison that reads one of the places `moved`, in itself or in
        a member of a list that it reads. The value of such a node can jump when one of those
        places changes by a little; a node with none is continuous in them (`min`, `max`, `clip`
        and `abs` have a bend and no jump)."""
        plan, seen, pending = self.plan, set(), [node]
        while pending:
            for part in smooth.walk(pending.pop()):
                if isinstance(part, expr.Compare) and plan.reads(part) & moved:
                    return True
                if (
                    isinstance(part, expr.Ref)
                    and plan.kind.get(part.name) == 'aggregate'
                    and part.name not in seen
                ):
                    seen.add(part.name)
                    pending += [term.node for term in plan.aggregates[part.name].terms]
        return False

    def breaks(self, name, output):
        """What, on a way from a name to an output, can make the output jump when the name changes
        by a little: a list of texts, empty when the output is continuous in the name. A rule on
        the way can happen at another time or not at all; a store that can rest on its bound
        changes what its flows deliver; a comparison changes the piece of an expression."""
        plan = self.plan
        moved, way = self.after({name}), self.between(name, output)
        rules = sorted(
            plan.rules[place[1]].name for place in way if isinstance(place, tuple) and place[0] == 'rule'
        )
        flags = {floor.flag: floor.name for floor in getattr(plan, 'floors', {}).values()}
        resting = sorted(flags[place] for place in way if place in flags)
        compared = sorted(
            str(place[1] if isinstance(place, tuple) else place)
            for place in way
            if any(self.comparisons(node, moved) for node in self.nodes_of(place))
        )
        found = []
        if rules:
            found.append(f'an event that the input can move or stop: {", ".join(rules)}')
        if resting:
            found.append(f'a store that can rest on its bound: {", ".join(resting)}')
        if compared:
            found.append(f'a comparison that the input can change, in {", ".join(compared)}')
        return found

    def outputs(self, places):
        """The outputs that a change of one of `places` can reach."""
        return {place[1] for place in self.after(places) if isinstance(place, tuple) and place[0] == 'output'}
