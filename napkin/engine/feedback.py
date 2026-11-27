"""Feedback between switch choices, read from a plan before a run. A report, never a refusal: nothing
here changes what a run does.

A *switch* is a comparison in the settings of a flow, or in a formula that they read, of which one
side moves (`integrate.surfaces_of`): `x if this.tank > 5 L else y`. Where its two sides meet, a run
picks the side that the state leaves on (`integrate.far_sides`). A min, max, clip or abs also has
switches (kinks), but at the meeting point both of its arms have the same value, so its choice
changes no rate there, only how fast a rate changes after it: a kink feeds back only at an exact
tangency, which only a run can see.

The choice of a side of switch A can change a flow's request or capacity, so the flow's rate, which
moves a store, which switch B reads: an *influence* of A on B, with a sign. The sign is + when the
choice of A's upper side (`a > b`) makes B's gap `a - b` rise faster, and - when it makes it fall.
Choosing the upper side of "the tank is full" turns its inflow off, so the tank's gap falls: a
negative influence of the switch on itself, which works against the choice. At most one side holds
there, or none (which a run refuses as chattering).

A *circuit* of influences whose signs multiply to + is positive feedback: a choice that, once made,
keeps itself. Two outcomes can then both satisfy the model: A rises and B falls, or A falls and B
rises. A discrete network whose circuits are all negative has at most one consistent choice
(Thomas's rule; Richard and Comet, 2007). So the check flags each strongly connected set of switches
with a positive circuit, or with a circuit of an unknown sign, and clears the others. It is
conservative: a sign it cannot tell is either sign, and it never reads magnitudes, so a flagged
circuit can still have one outcome at run time.

The signs come from the expressions alone, with the values of the inputs: a stock with a lower bound
of 0 is not negative, a directed flow's rate is not negative, a request raises its flow's rate, and
a flow that shares a store or an endpoint with another can lower the other's rate when they share
too little (an influence of sign - that only a run with a shortage shows)."""

from dataclasses import dataclass, field
from itertools import pairwise, product

from ..core import expr as nodes
from .continuous import integrate
from .timeline import plan as p
from .timeline.reads import lazily

POSITIVE, ZERO, NEGATIVE = 1, 0, -1
ANY = frozenset((NEGATIVE, ZERO, POSITIVE))
NONE = frozenset((ZERO,))
STEP, KINK = 'step', 'kink'


def _add(a, b):
    found = set()
    for x, y in product(a, b):
        found |= {x} if y == ZERO or x == y else {y} if x == ZERO else ANY
    return frozenset(found)


def _neg(a):
    return frozenset(-x for x in a)


def _mul(a, b):
    return frozenset(x * y for x, y in product(a, b))


def _div(a, b):
    return ANY if ZERO in b else _mul(a, b)


def _extreme(signs, pick):
    return frozenset(pick(choice) for choice in product(*signs)) if signs else ANY


@dataclass(frozen=True)
class Switch:
    """A switch: its pair of operands, the value whose expression holds it, and its kind."""

    pair: tuple
    owner: str
    kind: str

    @property
    def text(self):
        a, b = self.pair
        return f'{nodes.notation(a)} against {nodes.notation(b)}'


@dataclass(frozen=True)
class Influence:
    """How a choice of `source` moves the gap of `target`: its signs, and the flows and stores (or the
    nesting) that carry it, for the modeller's chain."""

    source: Switch
    target: Switch
    signs: frozenset
    via: tuple
    shortage: bool = False  # it only acts when flows share too little (run time)


@dataclass
class Report:
    """What the check finds in one plan."""

    switches: list = field(default_factory=list)
    influences: list = field(default_factory=list)
    flagged: list = field(default_factory=list)  # [(component, circuit, reason)]
    cleared: list = field(default_factory=list)  # [(component, reason)]
    runtime: list = field(default_factory=list)  # what only a run can tell


class Signs:
    """The sign rules over one plan's expressions, with memos."""

    def __init__(self, plan):
        self.plan = plan
        self.values = plan.values
        self.formulas = {
            name: value.node
            for name, value in plan.values.items()
            if value.kind == p.FORMULA and value.node is not None
        }
        self.stores = set(plan.moving)
        self.rates = {name for name, value in plan.values.items() if value.kind == p.RATE}
        self._sign, self._number = {}, {}
        self._effect, self._slope, self._inside, self._leaves = {}, {}, {}, {}

    def inside(self, name):
        """The switch pairs in a formula and in the formulas that it reads."""
        found = self._inside.get(name)
        if found is None:
            self._inside[name] = found = set()
            for part in nodes.breadth_first(self.formulas[name]):
                found.update(integrate.switch_pairs(part))
                if isinstance(part, nodes.Ref) and part.name in self.formulas:
                    found |= self.inside(part.name)
        return found

    def leaves(self, name):
        """The stores and rates that a formula reads, through formulas."""
        found = self._leaves.get(name)
        if found is None:
            found = self._leaves[name] = set(self.plan.expanded(name).leaves) & (self.stores | self.rates)
        return found

    # ---- values ------------------------------------------------------------------------------

    def number(self, node):
        """The value of an expression that reads no moving quantity, or None."""
        if node in self._number:
            return self._number[node]
        self._number[node] = None

        def read(name):
            value = self.values.get(name)
            if value is None or value.kind not in (p.INPUT, p.CAPTURE, p.FORMULA) or value.node is None:
                raise LookupError(name)
            found = self.number(value.node)
            if found is None:
                raise LookupError(name)
            return found

        try:
            found = lazily(node, read, self.plan.units, 0.0)
            found = float(found) if not isinstance(found, bool | str) else None
        except Exception:
            found = None
        self._number[node] = found
        return found

    def fixed_truth(self, node):
        """The truth of a test that reads only fixed values (inputs), or None."""

        def read(name):
            value = self.values.get(name)
            if value is None or value.kind not in (p.INPUT, p.CAPTURE) or value.node is None:
                raise LookupError(name)
            return lazily(value.node, read, self.plan.units, 0.0)

        try:
            found = lazily(node, read, self.plan.units, 0.0)
        except Exception:
            return None
        return found if isinstance(found, bool) else None

    def sign(self, node):
        """The signs that an expression's value can have."""
        if node in self._sign:
            return self._sign[node]
        self._sign[node] = ANY  # a formula that reads itself
        found = self._sign_of(node)
        self._sign[node] = found
        return found

    def _sign_of(self, node):
        number = self.number(node)
        if number is not None:
            return frozenset((POSITIVE if number > 0 else NEGATIVE if number < 0 else ZERO,))
        if isinstance(node, nodes.Ref):
            value = self.values.get(node.name)
            if value is None:
                return ANY
            if value.kind == p.STATE:
                low = self.number(value.lower) if value.lower is not None else None
                if low is not None and low >= 0:
                    return frozenset((ZERO, POSITIVE))
                if node.name not in self.stores and value.node is not None:
                    # A stored value that only stages change: the signs of its start value (an
                    # assumption of this report; a stage could write another sign).
                    return self.sign(value.node)
                return ANY
            if value.kind == p.RATE:
                flow = self.plan.flows.get(node.name.rpartition('.')[0])
                directed = flow is not None and flow.kind == p.DIRECTED
                return frozenset((ZERO, POSITIVE)) if directed else ANY
            if value.kind == p.FORMULA and value.node is not None:
                return self.sign(value.node)
            return ANY
        if isinstance(node, nodes.Unary) and node.op == 'neg':
            return _neg(self.sign(node.operand))
        if isinstance(node, nodes.Binary):
            a, b = self.sign(node.left), self.sign(node.right)
            if node.op == 'add':
                return _add(a, b)
            if node.op == 'sub':
                return _add(a, _neg(b))
            if node.op == 'mul':
                return _mul(a, b)
            if node.op == 'div':
                return _div(a, b)
            return ANY
        if isinstance(node, nodes.IfElse):
            test = self.fixed_truth(node.test)
            if test is not None:
                return self.sign(node.body if test else node.orelse)
            return self.sign(node.body) | self.sign(node.orelse)
        if isinstance(node, nodes.Call):
            if node.function == 'q' and node.args:
                return self.sign(node.args[0])
            if node.function in ('min', 'max'):
                return _extreme([self.sign(arg) for arg in node.args], min if node.function == 'min' else max)
            if node.function in ('abs', 'sqrt', 'exp'):
                return frozenset((ZERO, POSITIVE)) if node.function != 'exp' else frozenset((POSITIVE,))
        return ANY

    def difference(self, a, b):
        """The signs of a - b: by value where both are fixed; x - min(x, ...) and max(x, ...) - x are
        not negative."""
        x, y = self.number(a), self.number(b)
        if x is not None and y is not None:
            return frozenset((POSITIVE if x > y else NEGATIVE if x < y else ZERO,))
        if nodes.text(a) == nodes.text(b):
            return NONE

        def among(call, function, other):
            return (
                isinstance(call, nodes.Call)
                and call.function == function
                and any(nodes.text(arg) == nodes.text(other) for arg in call.args)
            )

        if among(b, 'min', a) or among(a, 'max', b):
            return frozenset((ZERO, POSITIVE))
        if among(a, 'min', b) or among(b, 'max', a):
            return frozenset((ZERO, NEGATIVE))
        # A clip lies between its bounds.
        for value, clipped, sign in ((x, b, 1), (y, a, -1)):
            if (
                value is not None
                and isinstance(clipped, nodes.Call)
                and clipped.function == 'clip'
                and len(clipped.args) == 3
            ):
                low, high = self.number(clipped.args[1]), self.number(clipped.args[2])
                if high is not None and value >= high:
                    return frozenset((ZERO, POSITIVE)) if sign > 0 else frozenset((ZERO, NEGATIVE))
                if low is not None and value <= low:
                    return frozenset((ZERO, NEGATIVE)) if sign > 0 else frozenset((ZERO, POSITIVE))
        return _add(self.sign(a), _neg(self.sign(b)))

    # ---- what a choice changes --------------------------------------------------------------

    def effect(self, node, switch, seen=()):
        """The signs of the change of an expression's value when `switch` goes from its lower side
        (a < b) to its upper side (a > b). A kink changes no value where its sides meet."""
        if switch.kind == KINK:
            return NONE
        if isinstance(node, nodes.Ref):
            if node.name not in self.formulas or switch.pair not in self.inside(node.name):
                return NONE
            key = (node.name, switch.pair)
            if key not in self._effect:
                self._effect[key] = ANY  # a formula that reads itself
                self._effect[key] = self.effect(self.formulas[node.name], switch, seen)
            return self._effect[key]
        if isinstance(node, nodes.IfElse):
            # Where the choice turns the test, the value goes from one arm to the other: their
            # difference, whose signs hold in every state. Where it leaves the test as it is, the arm
            # in use changes by itself. The change is one of these, never both.
            truth = self.truth(node.test, switch, seen)
            jump = (
                _mul(truth - {ZERO}, self.difference(node.body, node.orelse))
                if truth - {ZERO}
                else frozenset()
            )
            if ZERO not in truth:
                return jump
            steady = self.steady(node.test, switch)
            arms = (
                [node.body]
                if steady == 'body'
                else [node.orelse]
                if steady == 'orelse'
                else [node.body, node.orelse]
            )
            found = set(jump)
            for arm in arms:
                found |= self.effect(arm, switch, seen)
            return frozenset(found)
        if isinstance(node, nodes.Unary) and node.op == 'neg':
            return _neg(self.effect(node.operand, switch, seen))
        if isinstance(node, nodes.Binary):
            da, db = self.effect(node.left, switch, seen), self.effect(node.right, switch, seen)
            if da == NONE and db == NONE:
                return NONE
            if node.op == 'add':
                return _add(da, db)
            if node.op == 'sub':
                return _add(da, _neg(db))
            if node.op == 'mul':
                return _add(_mul(da, self.sign(node.right)), _mul(self.sign(node.left), db))
            if node.op == 'div' and db == NONE:
                return _div(da, self.sign(node.right))
            return ANY
        if isinstance(node, nodes.Call):
            changes = [self.effect(arg, switch, seen) for arg in node.args]
            if all(change == NONE for change in changes):
                return NONE
            if node.function == 'q':
                return changes[0]
            if node.function in ('min', 'max', 'clip', 'sqrt', 'exp', 'ln'):
                # Rising in each argument: the change has the signs of the arguments' changes.
                found = set()
                for change in changes:
                    found |= change
                return frozenset(found) if found <= {ZERO, POSITIVE} or found <= {ZERO, NEGATIVE} else ANY
            return ANY
        if nodes.names(node) and any(self.contains(child, switch) for child in node.children):
            return ANY
        return NONE

    def truth(self, node, switch, seen=()):
        """The signs of the change of a condition's truth (true = 1) when the switch goes up."""
        if isinstance(node, nodes.Compare):
            found = NONE
            for left, op, right in zip(node.operands, node.ops, node.operands[1:], strict=False):
                if (left, right) == switch.pair:
                    if op in ('gt', 'ge'):
                        found = _add(
                            found,
                            frozenset((ZERO, POSITIVE)) if len(node.ops) > 1 else frozenset((POSITIVE,)),
                        )
                    elif op in ('lt', 'le'):
                        found = _add(
                            found,
                            frozenset((ZERO, NEGATIVE)) if len(node.ops) > 1 else frozenset((NEGATIVE,)),
                        )
                    else:
                        found = ANY
                elif self.contains(left, switch) or self.contains(right, switch):
                    # The choice moves an operand: the test can turn only the way its operands move.
                    move = _add(self.effect(left, switch, seen), _neg(self.effect(right, switch, seen)))
                    if op in ('gt', 'ge'):
                        found = _add(found, move | {ZERO})
                    elif op in ('lt', 'le'):
                        found = _add(found, _neg(move) | {ZERO})
                    else:
                        found = ANY
            return found
        if isinstance(node, nodes.BoolOp):
            found = set()
            for value in node.values:
                found |= self.truth(value, switch, seen)
            # A conjunct or disjunct changes the whole only when the others let it.
            return frozenset(found | {ZERO}) if found != {ZERO} else NONE
        if isinstance(node, nodes.Unary) and node.op == 'not':
            return _neg(self.truth(node.operand, switch, seen))
        if isinstance(node, nodes.Ref):
            if node.name in self.formulas and switch.pair in self.inside(node.name):
                return (
                    self.truth(self.formulas[node.name], switch, (*seen, node.name))
                    if node.name not in seen
                    else ANY
                )
            return NONE
        membership = nodes.membership(node)
        if membership is not None:
            return self.truth(membership[0], switch, seen)
        return ANY if self.contains(node, switch) else NONE

    def from_zero(self, flow, switch, plan):
        """Whether every leg of a flow with legs asks 0 on the switch's lower side: the switch turns the
        flow on, so no leg's rate can fall."""
        return all(
            connection.request in self.formulas
            and self.sign_below(nodes.ref(connection.request), switch, ()) == NONE
            for connection in flow.connections
        )

    def sign_below(self, node, switch, seen):
        """The signs of a value on the switch's lower side (a < b): an if whose test is the switch's
        own comparison takes its arm there."""
        if isinstance(node, nodes.Ref):
            if node.name in self.formulas and switch.pair in self.inside(node.name) and node.name not in seen:
                return self.sign_below(self.formulas[node.name], switch, (*seen, node.name))
            return self.sign(node)
        if isinstance(node, nodes.IfElse):
            test = node.test
            if (
                isinstance(test, nodes.Compare)
                and len(test.ops) == 1
                and (test.operands[0], test.operands[1]) == switch.pair
            ):
                arm = node.body if test.ops[0] in ('lt', 'le') else node.orelse
                return self.sign_below(arm, switch, seen)
            return self.sign_below(node.body, switch, seen) | self.sign_below(node.orelse, switch, seen)
        if not self.contains(node, switch):
            return self.sign(node)
        if isinstance(node, nodes.Binary):
            a, b = self.sign_below(node.left, switch, seen), self.sign_below(node.right, switch, seen)
            if node.op == 'add':
                return _add(a, b)
            if node.op == 'sub':
                return _add(a, _neg(b))
            if node.op == 'mul':
                return _mul(a, b)
            if node.op == 'div':
                return _div(a, b)
            return ANY
        if isinstance(node, nodes.Call):
            args = [self.sign_below(arg, switch, seen) for arg in node.args]
            if node.function == 'q':
                return args[0]
            if node.function in ('min', 'max'):
                return _extreme(args, min if node.function == 'min' else max)
        return ANY

    def steady(self, test, switch):
        """Which arm of an if is in use on both sides when the choice does not turn its test: in
        `x or c`, where the switch is x, the test stays only while c is true ('body'); in `x and c`,
        only while c is false ('orelse'). None where either can be."""
        if isinstance(test, nodes.BoolOp):
            direct = [
                value
                for value in test.values
                if isinstance(value, nodes.Compare)
                and len(value.ops) == 1
                and (value.operands[0], value.operands[1]) == switch.pair
            ]
            others = [value for value in test.values if value not in direct]
            if direct and not any(self.contains(value, switch) for value in others):
                return 'body' if test.op == 'or' else 'orelse'
        return None

    def contains(self, node, switch):
        for part in nodes.breadth_first(node):
            if switch.pair in integrate.switch_pairs(part):
                return True
            if (
                isinstance(part, nodes.Ref)
                and part.name in self.formulas
                and switch.pair in self.inside(part.name)
            ):
                return True
        return False

    # ---- how a gap reads stores and rates ---------------------------------------------------

    def slope(self, node, name, seen=()):
        """The signs of the change of an expression's value when the store or rate `name` rises."""
        if isinstance(node, nodes.Ref):
            if node.name == name:
                return frozenset((POSITIVE,))
            if node.name not in self.formulas or name not in self.leaves(node.name):
                return NONE
            key = (node.name, name)
            if key not in self._slope:
                self._slope[key] = ANY  # a formula that reads itself
                self._slope[key] = self.slope(self.formulas[node.name], name, seen)
            return self._slope[key]
        if isinstance(node, nodes.Unary) and node.op == 'neg':
            return _neg(self.slope(node.operand, name, seen))
        if isinstance(node, nodes.Binary):
            da, db = self.slope(node.left, name, seen), self.slope(node.right, name, seen)
            if da == NONE and db == NONE:
                return NONE
            if node.op == 'add':
                return _add(da, db)
            if node.op == 'sub':
                return _add(da, _neg(db))
            if node.op == 'mul':
                return _add(_mul(da, self.sign(node.right)), _mul(self.sign(node.left), db))
            if node.op == 'div' and db == NONE:
                return _div(da, self.sign(node.right))
            return ANY
        if isinstance(node, nodes.IfElse):
            return self.slope(node.body, name, seen) | self.slope(node.orelse, name, seen)
        if isinstance(node, nodes.Call):
            changes = [self.slope(arg, name, seen) for arg in node.args]
            if all(change == NONE for change in changes):
                return NONE
            if node.function == 'q':
                return changes[0]
            if node.function in ('min', 'max', 'clip', 'sqrt', 'exp', 'ln'):
                found = set()
                for change in changes:
                    found |= change
                return frozenset(found) if found <= {ZERO, POSITIVE} or found <= {ZERO, NEGATIVE} else ANY
            return ANY
        return ANY if name in nodes.names(node) else NONE


def switches_of(plan, signs):
    """Every switch of the plan's flow settings, with the value whose expression holds it."""
    moving_names = signs.stores | signs.rates

    def moving(node):
        found = plan.expansion(node)
        return found.time or bool(set(found.leaves) & moving_names)

    found, seen, owners = {}, set(), []
    for flow in plan.flows.values():
        for name in plan.settings_of(flow):
            value = plan.values.get(name)
            if value is not None and value.node is not None and value.kind == p.FORMULA:
                owners.append(name)
    while owners:
        name = owners.pop()
        if name in seen:
            continue
        seen.add(name)
        node = signs.formulas.get(name)
        if node is None:
            continue
        for part in nodes.breadth_first(node):
            if isinstance(part, nodes.Ref) and part.name in signs.formulas:
                owners.append(part.name)
            for pair in integrate.switch_pairs(part):
                if pair not in found and (moving(pair[0]) or moving(pair[1])):
                    kind = (
                        STEP
                        if isinstance(part, nodes.Compare) or nodes.membership(part) is not None
                        else KINK
                    )
                    found[pair] = Switch(pair, name, kind)
    return list(found.values())


def sharing_of(plan, signs):
    """{flow: [(another flow, the sign of its rate's change when this one's rises)]} where they share a
    bound: outflows of a store with a lower bound share what comes in when it is empty (one's rise lowers
    the others', and an inflow's rise raises the outflows'); inflows of a store with an upper bound share
    its room when it is full. Only a run in which the store reaches the bound shows it."""
    sides = {}
    for name, flow in plan.flows.items():
        for connection in flow.connections:
            if connection.source:
                sides.setdefault((connection.source, 'out'), set()).add(name)
            if connection.sink:
                sides.setdefault((connection.sink, 'in'), set()).add(name)
    found = {}
    for store in signs.stores:
        value = plan.values.get(store)
        if value is None:
            continue
        outs, ins = sides.get((store, 'out'), set()), sides.get((store, 'in'), set())
        if value.lower is not None:
            for a in outs:
                found.setdefault(a, []).extend(
                    (b, frozenset((NEGATIVE,)), store, value.lower) for b in outs if b != a
                )
            for a in ins:
                found.setdefault(a, []).extend(
                    (b, frozenset((POSITIVE,)), store, value.lower) for b in outs if b != a
                )
        if value.upper is not None:
            for a in ins:
                found.setdefault(a, []).extend(
                    (b, frozenset((NEGATIVE,)), store, value.upper) for b in ins if b != a
                )
            for a in outs:
                found.setdefault(a, []).extend(
                    (b, frozenset((POSITIVE,)), store, value.upper) for b in ins if b != a
                )
    return found


def forced(plan, signs, switches):
    """{switch: (low, high)} for each switch between a store and a fixed value whose store's rate has
    one sign whatever every switch chooses: each flow's rate lies between the least and the largest
    value its request can take (all of it from an unlimited source, from 0 up where a store can run
    short). Its direction is then decided, so it cannot carry feedback."""

    def values_of(node, seen=()):
        number = signs.number(node)
        if number is not None:
            return {number}
        if isinstance(node, nodes.IfElse):
            body, orelse = values_of(node.body, seen), values_of(node.orelse, seen)
            return None if body is None or orelse is None else body | orelse
        if isinstance(node, nodes.Ref) and node.name in signs.formulas and node.name not in seen:
            return values_of(signs.formulas[node.name], (*seen, node.name))
        return None

    rate = {}
    for name, flow in plan.flows.items():
        if flow.kind != p.DIRECTED or len(flow.connections) != 1:
            continue
        (connection,) = flow.connections
        request = plan.values.get(connection.request)
        options = values_of(request.node) if request is not None and request.node is not None else None
        if options is None or connection.capacity is not None:
            continue
        ends = (plan.ends.get((connection.source, 'outflow')), plan.ends.get((connection.sink, 'inflow')))
        if any(end is not None and plan.settled(end) for end in ends):
            continue
        low = min(options) if connection.source is None else 0.0
        rate[name] = (connection.source, connection.sink, low, max(options))
    found = {}
    fills = {c.sink for flow in plan.flows.values() for c in flow.connections if c.sink}
    drains = {c.source for flow in plan.flows.values() for c in flow.connections if c.source}

    def pool(node, seen=()):
        """The stores of a sum of stores, each not below 0 (through formulas), or None."""
        if isinstance(node, nodes.Ref):
            if node.name in signs.stores:
                low = plan.values[node.name].lower
                return {node.name} if low is not None and signs.number(low) == 0 else None
            if node.name in signs.formulas and node.name not in seen:
                return pool(signs.formulas[node.name], (*seen, node.name))
            return None
        if isinstance(node, nodes.Binary) and node.op == 'add':
            left, right = pool(node.left, seen), pool(node.right, seen)
            return None if left is None or right is None else left | right
        return None

    for switch in switches:
        a, b = switch.pair
        for side, fixed in ((a, b), (b, a)):
            # A pool of stores at 0 that no flow fills from outside it stays empty.
            members = pool(side) if signs.number(fixed) == 0 else None
            if (
                members
                and len(members) > 1
                and not any(
                    c.sink in members and c.source not in members
                    for flow in plan.flows.values()
                    for c in flow.connections
                )
            ):
                found[switch] = (0.0, 0.0)
        if switch in found:
            continue
        for store, fixed in ((a, b), (b, a)):
            # At its own bound, a store that no flow can move off it stays there: no flow fills a store
            # whose lower bound this is, or drains one whose upper bound this is. Its side is decided.
            if (
                isinstance(store, nodes.Ref)
                and store.name in signs.stores
                and signs.number(fixed) is not None
            ):
                value = plan.values[store.name]
                at = signs.number(fixed)
                lower = signs.number(value.lower) if value.lower is not None else None
                upper = signs.number(value.upper) if value.upper is not None else None
                if (lower == at and store.name not in fills) or (upper == at and store.name not in drains):
                    found[switch] = (0.0, 0.0)
        if switch in found:
            continue
        for store, fixed, sign in ((a, b, 1), (b, a, -1)):
            if (
                isinstance(store, nodes.Ref)
                and store.name in signs.stores
                and signs.number(fixed) is not None
            ):
                low = high = 0.0
                known = True
                for flow in (
                    f
                    for f, flow in plan.flows.items()
                    if any(store.name in (c.source, c.sink) for c in flow.connections)
                ):
                    if flow not in rate:
                        known = False
                        break
                    source, sink, lo, hi = rate[flow]
                    if sink == store.name:
                        low, high = low + lo, high + hi
                    if source == store.name:
                        low, high = low - hi, high - lo
                if known and (low > 0 or high < 0):
                    found[switch] = (sign * low, sign * high) if sign > 0 else (sign * high, sign * low)
    return found


def influences_of(plan, signs, switches, *, sharing=False):
    """The influences between the switches: through flow settings, stores and rates, and nesting;
    with `sharing`, also through flows that share a store at its bound (`sharing_of`)."""
    flows = plan.flows
    settings = {
        name: [s for s in plan.settings_of(flow) if s in signs.formulas] for name, flow in flows.items()
    }
    moved = {}
    for name, flow in flows.items():
        stores = {}
        for connection in flow.connections:
            for store, sign in ((connection.source, NEGATIVE), (connection.sink, POSITIVE)):
                if store:
                    stores[store] = stores.get(store, frozenset()) | {sign}
        directed = flow.kind in (p.DIRECTED, p.LEGS)
        moved[name] = {store: (frozenset(s) if directed else ANY) for store, s in stores.items()}
    rivals = sharing_of(plan, signs) if sharing else {}
    gaps = {}
    for target in switches:
        a, b = target.pair
        gaps[target] = (a, b)

    def gap_slope(target, name):
        a, b = gaps[target]
        return _add(signs.slope(a, name), _neg(signs.slope(b, name)))

    found = []
    for source in switches:
        if source.kind == KINK:
            continue
        rate_change = {}
        for name, flow in flows.items():
            change = NONE
            for setting in settings[name]:
                effect = signs.effect(nodes.ref(setting), source)
                if effect != NONE:
                    change = _add(change, effect)  # a request or a capacity raises its flow's rate
            if change != NONE and flow.kind == p.LEGS and not signs.from_zero(flow, source, plan):
                change = ANY  # one leg's rise can lower the fraction that every leg is served
            if change != NONE:
                rate_change[name] = (change, False)
        held = {}
        a, b = source.pair
        for store, fixed in ((a, b), (b, a)):
            if isinstance(store, nodes.Ref) and signs.number(fixed) is not None:
                held[store.name] = signs.number(fixed)  # where the switch meets, the store is there
        for name, (change, _) in list(rate_change.items()):
            for rival, sign, store, bound in rivals.get(name, ()):
                if store in held and signs.number(bound) != held[store]:
                    continue  # the store is off its bound where this switch meets
                if rival not in rate_change:
                    rate_change[rival] = (_mul(_mul(change, sign), frozenset((ZERO, POSITIVE))), True)
        for target in switches:
            total, via, shortage = NONE, [], False
            for name, (change, shared) in rate_change.items():
                part = NONE
                for store, direction in moved[name].items():
                    slope = gap_slope(target, store)
                    if slope != NONE:
                        part = _add(part, _mul(_mul(change, direction), slope))
                        via.append((name, store))
                rate = gap_slope(target, f'{name}.actual_rate')
                if rate != NONE:
                    part = _add(part, _mul(change, rate))
                    via.append((name, f'{name}.actual_rate'))
                if part != NONE:
                    total = _add(total, part)
                    shortage = shortage or shared
            a, b = target.pair
            nested = _add(signs.effect(a, source), _neg(signs.effect(b, source)))
            if nested != NONE:
                total = _add(total, nested)
                via.append(('nested', source.owner))
            if total != NONE:
                found.append(Influence(source, target, total, tuple(via), shortage))
    return found


def _components(switches, influences):
    """The strongly connected sets of switches (Tarjan), with the influences inside each."""
    edges = {s: [] for s in switches}
    for influence in influences:
        edges[influence.source].append(influence)
    index, low, stack, on, result = {}, {}, [], set(), []
    counter = [0]

    def visit(v):
        work = [(v, iter(edges[v]))]
        index[v] = low[v] = counter[0]
        counter[0] += 1
        stack.append(v)
        on.add(v)
        while work:
            node, children = work[-1]
            advanced = False
            for edge in children:
                w = edge.target
                if w not in index:
                    index[w] = low[w] = counter[0]
                    counter[0] += 1
                    stack.append(w)
                    on.add(w)
                    work.append((w, iter(edges[w])))
                    advanced = True
                    break
                if w in on:
                    low[node] = min(low[node], index[w])
            if advanced:
                continue
            work.pop()
            if work:
                low[work[-1][0]] = min(low[work[-1][0]], low[node])
            if low[node] == index[node]:
                part = []
                while True:
                    w = stack.pop()
                    on.discard(w)
                    part.append(w)
                    if w == node:
                        break
                result.append(part)

    for v in switches:
        if v not in index:
            visit(v)
    return result


def _positive_circuit(part, influences, limit=20_000):
    """A circuit of the set whose signs can multiply to + (the shortest found), or None when every
    circuit is negative. Elementary circuits are listed up to `limit`; past it, the set is reported
    as undecided (a positive closed walk is then shown)."""
    members = set(part)
    inside = [i for i in influences if i.source in members and i.target in members]
    out = {s: [i for i in inside if i.source == s] for s in part}
    order = {s: k for k, s in enumerate(part)}
    best, count = None, 0
    # Johnson-style listing of elementary circuits, each from its least member.
    for start in part:
        path, signs_on, stack = [start], [frozenset((POSITIVE,))], [iter(out[start])]
        on = {start}
        while stack:
            for edge in stack[-1]:
                w = edge.target
                if order[w] < order[start]:
                    continue
                sign = _mul(signs_on[-1], edge.signs)
                if w == start:
                    count += 1
                    if POSITIVE in sign and (best is None or len(path) < len(best[0])):
                        best = ([*path, start], [*edges_of(path, out), edge], sign)
                    if count >= limit:
                        return best, False
                    continue
                if w in on:
                    continue
                path.append(w)
                signs_on.append(sign)
                stack.append(iter(out[w]))
                on.add(w)
                break
            else:
                stack.pop()
                on.discard(path.pop())
                signs_on.pop()
    return best, True


def edges_of(path, out):
    found = []
    for a, b in pairwise(path):
        found.append(next(i for i in out[a] if i.target == b))
    return found


def check(plan):
    """The report of one plan (see the module). Influences through sharing at a bound are judged
    after the others: a circuit that needs one is a question only a run with a shortage asks."""
    signs = Signs(plan)
    switches = switches_of(plan, signs)
    direct = influences_of(plan, signs, switches)
    shared = influences_of(plan, signs, switches, sharing=True)
    report = Report(switches, shared)
    report.forced = forced(plan, signs, switches)
    flagged = set()
    for influences, through_sharing in ((direct, False), (shared, True)):
        kept = [i for i in influences if i.target not in report.forced]
        for part in _components(switches, influences):
            members = frozenset(part)
            if members & flagged or not any(i.source in members and i.target in members for i in influences):
                continue
            circuit, complete = _positive_circuit(part, kept)
            if circuit is None and complete:
                if through_sharing:
                    continue
                held = [s for s in part if s in report.forced]
                if held and _positive_circuit(part, influences)[0] is not None:
                    reason = 'a direction that the rates decide: ' + '; '.join(
                        f'{s.text} moves at {report.forced[s][0]:g} to {report.forced[s][1]:g} per hour '
                        'whatever the switches choose'
                        for s in held
                    )
                else:
                    reason = 'every circuit is negative: each choice works against itself'
                report.cleared.append((part, reason))
                continue
            unknown = circuit is not None and any(len(e.signs - {ZERO}) > 1 for e in circuit[1])
            reason = (
                'too many circuits to list'
                if circuit is None
                else 'only when a store runs short and flows share what is left'
                if through_sharing
                else 'a sign that only a run can tell'
                if unknown
                else 'positive feedback'
            )
            report.flagged.append((part, circuit, reason))
            flagged |= members
    report.cleared = [(part, reason) for part, reason in report.cleared if not set(part) & flagged]
    report.runtime.extend(sorted({s.owner for s in switches if s.kind == KINK}))
    return report
