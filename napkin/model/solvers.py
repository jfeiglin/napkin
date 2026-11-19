"""The declared decisions of a program: what a solver may say about what it determines.

A solver (spec, "An entity owns its solver") determines the fields that its `solve_for` names (stored
numbers, the rates of flows and routes, served fractions) and its new unknowns. Its constraints and
its objectives are the language of a convex problem: affine `==`, `<=` and `>=` relations, their
conjunction (`and`, `all(...)`), and objectives that are affine, or that are sums of positive parts
(`max(0 W, request - actual_rate)`) to minimize. The front end checks this on the program that the
lowering made, after the program's own checks, because the program says plainly what each read
reaches (`check.Resolver`). Each refusal is a `check.Diagnostic` at the origin of the part:

- **A form that the language leaves out** (`solver_form`): a strict inequality, `!=`, a
  disjunction, `any(...)` or `not` of a relation, a relation under a condition (`C and rel`, a
  chain with a known pair, `rel if C else ...`), a choice whose test reads an unknown, a lookup keyed
  by an unknown, and a domain, a preferred value or a scale that reads one.
- **A nonlinear problem** (`nonlinear`): a product of two unknowns, a division by an unknown, a
  power or a function of one other than `max`, `min` of one, and a positive part that is negated,
  subtracted, scaled by a negative number written in place, nested in another, on the large side of
  a relation or maximized. (A yes/no unknown, the yes-or-no problem, is refused where it is declared,
  in `semantic.py`.)
- **A missing participant** (`participant`): a rate that a constraint or an objective reads (the
  `actual_rate` of a flow, a route, a leg or an endpoint, a served fraction) and that its solver
  does not determine; and a constraint or an objective that reads nothing that its solver
  determines. A rate of the instant is the decision's own or no part of it.
- **Two solvers in one connected set** (`two_solvers`): two solvers, or the solvers of two members of
  one template, whose determined rates lie in one connected set of flows and stores (flows that share
  a store, as far as they reach) would choose rates that compete, so the model is refused with both
  named: one coordinating solver must own the joint decision. This is the oracle's rule of one
  solver for each calculation. The flows of entities and of events count, with ends resolved member
  by member through links; an end through an event's parameter is known only at a start, and the run
  refuses two solvers that such a flow joins.

What a read is for a solve: an unknown of the solver, or a stored value or a rate that it determines,
is affine; anything else is known, a coefficient read at each solve (another solver's results are
known: they settle first, in dependency order). A formula is read through, its template's body and
each member's own, in the scope of its owner. The classes are per template, not per member, so a
check of participants is conservative: a rate of one member stands for the same rate of every member.
"""

from __future__ import annotations

from ..core import expr as nodes
from ..program import check
from ..program import parts as p
from ..program.refs import (
    By,
    Expr,
    Formula,
    Instances,
    Literal,
    Local,
    Lookup,
    Named,
    Path,
    Reduce,
    Root,
    This,
    Where,
    spelled,
)

# What an expression is for a solve, in rising order: known for the solve; affine in what the solver
# determines; affine with positive parts (convex); a conjunction of affine relations (a constraint).
KNOWN, AFFINE, CONVEX, RELATION = range(4)
RATES = ('actual_rate', 'served_fraction')


class _Refused(Exception):
    def __init__(self, code, message):
        super().__init__(message)
        self.code, self.message = code, message


def problems(program):
    """The refusals of the declared decisions of a program, each a `check.Diagnostic`, in the order
    of its templates and solvers."""
    found = []
    checker = _Checker(program)
    for template in program.templates:
        for solver in template.solvers:
            found.extend(_Decision(checker, template, solver).problems())
    found.extend(_connected(program))
    return found


class _Checker:
    """What every decision of a program shares: its resolver, the template of each event, and the
    incidence of each endpoint (the rate of each flow incident there, for an endpoint's total)."""

    def __init__(self, program):
        self.program = program
        self.resolver = check.Resolver(program)
        self.event_template = {}
        self.incidence = {}  # (store key, side) -> [(rate key, reversible)]
        for template in program.templates:
            scope = check.Scope(template)
            for flow in template.flows:
                self.incident(flow, template.name, scope)
            for event in template.events:
                self.event_template[id(event)] = template
                inner = check.Scope(template, event)
                for local in event.locals:
                    if isinstance(local, p.Flow):
                        self.incident(local, event.origin, inner)

    def incident(self, flow, owner, scope):
        rate = ('rate', owner, flow.name)
        reversible = flow.kind == p.REVERSIBLE
        for connection in flow.legs if flow.kind == p.LEGS else (flow,):
            sides = (('outflow', connection.source), ('inflow', connection.sink))
            if reversible:  # a route takes from and gives to both of its ends
                sides += (('inflow', connection.source), ('outflow', connection.sink))
            for side, end in sides:
                if not isinstance(end, Path):
                    continue
                store = self.resolver.resolve(end, scope, '')
                if store is not None and store.kind == 'value':
                    key = ('value', check.owner_key(store.owner), store.part.name)
                    self.incidence.setdefault((key, side), []).append((rate, reversible))


class _Decision:
    """One solver of a template: the keys of what it determines (in the form of the program's check
    of `solve_for`), and the class of each of its expressions."""

    def __init__(self, checker, template, solver):
        self.checker, self.solver = checker, solver
        self.resolver = checker.resolver
        self.scope = check.Scope(template, solver=solver)
        self.rates, self.values = set(), set()
        for entry in solver.solve_for:
            found = self.resolver.resolve(entry, self.scope, '')
            if found is None:
                continue
            if found.kind == 'value':
                self.values.add(('value', check.owner_key(found.owner), found.part.name))
            elif found.kind == 'property' and found.of.kind == 'flow' and found.of.part is not None:
                self.rates.add(('rate', check.owner_key(found.of.owner), found.of.part.name))
        self.formulas, self.open = {}, set()

    def problems(self):
        """The refusals of this solver's domains, constraints and objectives."""
        out = []

        def classified(expression, origin):
            try:
                return self.expr(expression, self.scope)
            except _Refused as refused:
                out.append(check.Diagnostic(refused.code, origin, refused.message))
                return None

        for unknown in self.solver.unknowns:
            for what, expression in (
                ('domain', unknown.lower),
                ('domain', unknown.upper),
                ('preferred value', unknown.init),
                ('scale', unknown.scale),
            ):
                if classified(expression, unknown.origin) not in (KNOWN, None):
                    out.append(
                        check.Diagnostic(
                            'solver_form',
                            unknown.origin,
                            f'the {what} of {unknown.name} reads what the solver determines: write the '
                            'relation under constraints',
                        )
                    )
        for constraint in self.solver.constraints:
            if classified(constraint.test, constraint.origin) == KNOWN:
                out.append(
                    check.Diagnostic(
                        'participant',
                        constraint.origin,
                        'the constraint reads nothing that its solver determines, so it constrains no '
                        'answer: relate what solve_for names',
                    )
                )
        for objective in self.solver.objective:
            found = classified(objective.expr, objective.origin)
            if found == KNOWN:
                out.append(
                    check.Diagnostic(
                        'participant',
                        objective.origin,
                        'the objective reads nothing that its solver determines, so it ranks no answer',
                    )
                )
            elif found == CONVEX and objective.sense == 'maximize':
                out.append(
                    check.Diagnostic(
                        'nonlinear',
                        objective.origin,
                        'maximize of a positive part is not convex: minimize the shortfall instead, as '
                        'minimize(max(0 W, request - actual_rate))',
                    )
                )
        return out

    # ---- expressions ----------------------------------------------------------------------------

    def expr(self, expression, scope):
        """The class of an expression of the program in a scope: KNOWN, AFFINE, CONVEX or RELATION."""
        if not isinstance(expression, Expr):
            return KNOWN
        return self.node(expression.node, expression, scope)

    def node(self, node, expression, scope):
        if isinstance(node, nodes.Ref):
            return self.read(expression.read(node.name), scope)
        if isinstance(node, nodes.Unary):
            found = self.node(node.operand, expression, scope)
            if node.op == 'not' and found == RELATION:
                raise _Refused(
                    'solver_form', 'not of a relation is left out: a solver enforces each relation'
                )
            if node.op == 'neg' and found == CONVEX:
                raise _Refused('nonlinear', 'the negative of a positive part is not convex')
            return found
        if isinstance(node, nodes.Binary):
            return self.binary(node, expression, scope)
        if isinstance(node, nodes.Compare):
            return self.compare(node, expression, scope)
        if isinstance(node, nodes.BoolOp):
            found = [self.node(value, expression, scope) for value in node.values]
            return self.joined(node.op, found)
        if isinstance(node, nodes.IfElse):
            if self.node(node.test, expression, scope) != KNOWN:
                raise _Refused(
                    'solver_form',
                    'a choice whose test reads what the solver determines is left out: the test of an '
                    'if in a solver is known',
                )
            found = [self.node(item, expression, scope) for item in (node.body, node.orelse)]
            if RELATION in found:
                raise _Refused(
                    'solver_form', 'a relation under a condition is left out: a solver enforces each relation'
                )
            return max(found)
        if isinstance(node, nodes.Call):
            return self.call(node, expression, scope)
        return KNOWN

    def binary(self, node, expression, scope):
        left, right = (self.node(item, expression, scope) for item in (node.left, node.right))
        if node.op in ('add', 'sub'):
            if node.op == 'sub' and right == CONVEX:
                raise _Refused('nonlinear', 'a positive part that is subtracted is not convex')
            return max(left, right)
        if node.op == 'mul':
            if left != KNOWN and right != KNOWN:
                raise _Refused(
                    'nonlinear', 'a product of two values that the solver determines is not affine'
                )
            known = node.left if left == KNOWN else node.right
            if CONVEX in (left, right) and _sign(known) < 0:
                raise _Refused('nonlinear', 'a positive part times a negative number is not convex')
            return max(left, right)
        if node.op == 'div':
            if right != KNOWN:
                raise _Refused('nonlinear', 'a division by a value that the solver determines is not affine')
            if left == CONVEX and _sign(node.right) < 0:
                raise _Refused('nonlinear', 'a positive part divided by a negative number is not convex')
            return left
        if left != KNOWN or right != KNOWN:
            raise _Refused('nonlinear', 'a power of a value that the solver determines is not affine')
        return KNOWN

    def compare(self, node, expression, scope):
        found = [self.node(item, expression, scope) for item in node.operands]
        return self.chain(node.ops, found)

    def chain(self, ops, found):
        """A chain of comparisons (`ops` between the classes `found` of its operands): KNOWN, or the
        conjunction of the relation of each pair."""
        if RELATION in found:
            raise _Refused('solver_form', 'a comparison of a relation is left out: write the relations apart')
        if max(found) == KNOWN:
            return KNOWN
        for op, left, right in zip(ops, found, found[1:]):
            if max(left, right) == KNOWN:
                raise _Refused(
                    'solver_form',
                    'a relation under a condition is left out: a chain of comparisons in a solver relates '
                    'what it determines in each pair',
                )
            if op in ('lt', 'gt'):
                raise _Refused('solver_form', 'a strict inequality is left out of a solver: write <= or >=')
            if op == 'ne':
                raise _Refused('solver_form', '!= is left out of a solver: it enforces ==, <= and >=')
            if (
                (op == 'le' and right == CONVEX)
                or (op == 'ge' and left == CONVEX)
                or (op == 'eq' and CONVEX in (left, right))
            ):
                raise _Refused(
                    'nonlinear',
                    'a positive part on the large side of a relation, or in an equality, is not convex',
                )
        return RELATION

    def joined(self, op, found):
        """`and` or `or` of values, or `all(...)` (`and`) of the members of a projection."""
        if RELATION not in found:
            return KNOWN
        if op == 'or':
            raise _Refused('solver_form', 'a disjunction is left out of a solver: it enforces each relation')
        if KNOWN in found:
            raise _Refused(
                'solver_form', 'a relation under a condition is left out: a solver enforces each relation'
            )
        return RELATION

    def call(self, node, expression, scope):
        if node.function == 'q':
            return KNOWN
        found = [self.node(arg, expression, scope) for arg in node.args]
        if max(found, default=KNOWN) == KNOWN:
            return KNOWN
        if node.function == 'within':
            # `x in [lo, hi]`: the chain `lo <= x <= hi`, a relation of each pair; the ends that a
            # solve knows are checked when it reads them (`ops.REVERSED`).
            return self.chain(('le', 'le'), [found[1], found[0], found[2]])
        if node.function == 'max':
            return self.positive(found)
        if node.function == 'sum':
            return max(found)
        if node.function in ('all', 'any'):
            if node.function == 'any' and RELATION in found:
                raise _Refused('solver_form', 'any(...) of relations is left out: a solver enforces each one')
            return self.joined('and', found)
        if node.function == 'min':
            raise _Refused('nonlinear', 'min of a value that the solver determines is not convex')
        raise _Refused('nonlinear', f'{node.function} of a value that the solver determines is not affine')

    def positive(self, found):
        """`max(...)` of values of which one at least is affine: a positive part, which is convex."""
        if CONVEX in found:
            raise _Refused('nonlinear', 'a positive part of a positive part is left out of a solver')
        return CONVEX

    # ---- reads ----------------------------------------------------------------------------------

    def read(self, read, scope):
        if isinstance(read, Path):
            self.keys(read, scope)
            return self.found(self.resolver.resolve(read, scope, ''), read)
        if not isinstance(read, Reduce):
            return KNOWN  # the time, a member of an enum, a history read: known for a solve
        self.keys(read.source, scope)
        element = self.found(self.resolver.resolve(read.source, scope, ''), read.source)
        if read.op == 'count' or element == KNOWN:
            return KNOWN
        if read.op == 'sum':
            return element
        if read.op == 'max':
            return self.positive([element])
        if read.op == 'min':
            raise _Refused('nonlinear', 'min of values that the solver determines is not convex')
        if read.op == 'any':
            raise _Refused('solver_form', 'any(...) of relations is left out: a solver enforces each one')
        return element  # all(...): the conjunction of the relations of the members

    def keys(self, path, scope):
        """A lookup on the way of a path is keyed by a known value."""
        start = path.start
        if isinstance(start, Lookup):
            if self.expr(start.key, scope) != KNOWN:
                raise _Refused(
                    'solver_form', 'a lookup keyed by a value that the solver determines is left out'
                )
            self.keys(start.source, scope)
        elif isinstance(start, (Where, By)):
            self.keys(start.source, scope)
        elif isinstance(start, Literal):
            for item in start.items:
                self.keys(item, scope)

    def found(self, found, path):
        """The class of what a path names (one member's, or each member's of a projection)."""
        if found is None:
            return KNOWN
        if found.kind == 'unknown':
            return AFFINE if found.owner is self.solver else KNOWN
        if found.kind == 'value':
            if found.part.kind == p.FORMULA:
                return self.formula(found)
            key = ('value', check.owner_key(found.owner), found.part.name)
            return AFFINE if key in self.values else KNOWN
        if found.kind == 'property' and found.name in RATES:
            return self.rate(found.of, path)
        return KNOWN

    def formula(self, found):
        """A formula read through: its template's body and each member's own, in its owner's scope."""
        owner, name = found.owner, found.part.name
        if isinstance(owner, p.Template):
            scope = check.Scope(owner)
            bodies = [found.part.init, *(member.value(name) for member in owner.members)]
        elif isinstance(owner, p.Event):
            scope = check.Scope(self.checker.event_template.get(id(owner)), owner)
            bodies = [found.part.init]
        else:
            scope = check.Scope()
            bodies = [found.part.init]
        result = KNOWN
        for body in {id(body): body for body in bodies if isinstance(body, Formula)}.values():
            key = (id(body), check.owner_key(owner))
            if key not in self.formulas:
                if key in self.open:
                    continue  # a formula that reads itself: the run refuses it, and it adds nothing here
                self.open.add(key)
                try:
                    self.formulas[key] = self.expr(body.expr, scope)
                finally:
                    self.open.discard(key)
            result = max(result, self.formulas[key])
        return result

    def rate(self, of, path):
        """A rate of the instant, which the solver must determine: of a flow, a route or a flow with
        legs (affine), of a leg of a route (the positive part of the route's rate), of a leg of a flow
        with legs (its fraction times its request), or the total of an endpoint over its flows."""
        if of.kind == 'leg':
            self.need(('rate', check.owner_key(of.owner), of.part.name), path)
            return CONVEX
        if of.kind == 'flow' and of.part is None:
            return self.endpoint(of.of, path)
        if of.kind == 'flow':
            parent = of.of if of.of is not None and of.of.kind == 'flow' else of
            self.need(('rate', check.owner_key(parent.owner), parent.part.name), path)
            return AFFINE
        if of.kind == 'endpoint':
            return self.endpoint(of, path)
        return KNOWN

    def endpoint(self, end, path):
        store = ('value', check.owner_key(end.owner), end.part.name)
        incident = self.checker.incidence.get((store, end.name), [])
        for rate, _ in incident:
            self.need(rate, path)
        if not incident:
            return KNOWN
        return CONVEX if any(reversible for _, reversible in incident) else AFFINE

    def need(self, rate, path):
        if rate not in self.rates:
            raise _Refused(
                'participant',
                f'`{spelled(path)}` takes part in the decision of {self.solver.origin}, which does not '
                f'determine {rate[1]}.{rate[2]}: name its rate under solve_for',
            )


# ---- one solver for each connected set -----------------------------------------------------------


def _connected(program):
    """`two_solvers`: the solvers whose determined rates lie in one connected set of flows and stores,
    member by member. Nothing to do with fewer than two solvers on members."""
    instances = [
        (template, row, solver)
        for template in program.templates
        for solver in template.solvers
        for row in range(len(template.members))
    ]
    if len(instances) < 2:
        return []
    rows = _Rows(program)
    parent = {}

    def find(node):
        parent.setdefault(node, node)
        while parent[node] != node:
            parent[node] = parent[parent[node]]
            node = parent[node]
        return node

    for template in program.templates:
        for row in range(len(template.members)):
            for flow in template.flows:
                rows.join(flow, flow.name, (template.name, row), find, parent)
            for event in template.events:
                for local in event.locals:
                    if isinstance(local, p.Flow):
                        rows.join(local, f'{event.name}.{local.name}', (template.name, row), find, parent)
    owners, out = {}, []
    for template in program.templates:
        for solver in template.solvers:
            # An entry that names the same places at every member is walked once.
            shared = {entry: None for entry in solver.solve_for if not _own(entry, solver)}
            for row in range(len(template.members)):
                name, places = f'{template.members[row].id}.{solver.name}', []
                for entry in solver.solve_for:
                    if entry not in shared:
                        places += rows.walk(entry, (template.name, row), solver)
                        continue
                    if shared[entry] is None:
                        shared[entry] = rows.walk(entry, (template.name, row), solver)
                    places += shared[entry]
                sets = {find(('flow', *place[1:])) for place in places if place[0] == 'rate'}
                other = next(
                    (found for found in (owners.setdefault(each, name) for each in sets) if found != name),
                    None,
                )
                if other is not None:
                    out.append(
                        check.Diagnostic(
                            'two_solvers',
                            solver.origin,
                            f'{other} and {name} would choose rates that compete in one connected set '
                            'of flows and stores: one coordinating solver must own the joint decision',
                        )
                    )
                    break  # one refusal for each solver
    return out


def _own(path, solver):
    """Whether what a path names depends on the member that reads it: it starts at `this`, or a
    collection, a key or an input of the solver on its way does."""
    start = path.start
    if isinstance(start, This):
        return True
    if isinstance(start, Local) and solver is not None:
        return any(_own(item.source, None) for item in solver.inputs if item.name == start.name)
    if isinstance(start, (Where, By, Lookup)):
        return _own(start.source, solver)
    if isinstance(start, Literal):
        return any(_own(item, solver) for item in start.items)
    return False


class _Rows:
    """The places that a path names at one member: members as ('member', template, row), stored
    values as ('value', template, row, name) (the root's at row 0 of ''), flows as ('flow', template,
    row, name, flow), and their rates as ('rate', template, row, name). A `where`, a `by` and a
    lookup stand for every member of their source."""

    def __init__(self, program):
        self.program = program
        self.templates = {template.name: template for template in program.templates}

    def join(self, flow, name, at, find, parent):
        """Join a flow of a member with the stores at its ends."""
        node = find(('flow', *at, name))
        for connection in flow.legs if flow.kind == p.LEGS else (flow,):
            for end in (connection.source, connection.sink):
                if isinstance(end, Path):
                    for place in self.walk(end, at):
                        if place[0] == 'value':
                            parent[find(place)] = node

    def walk(self, path, at, solver=None):
        current = self.start(path.start, at, solver)
        for step in path.steps:
            current = [found for place in current for found in self.step(place, step)]
        return current

    def start(self, start, at, solver):
        if isinstance(start, This):
            return [('member', *at)] if at is not None else []
        if isinstance(start, Root):
            return [('root',)]
        if isinstance(start, Named):
            try:
                template, row = self.program.member(start.id)
            except KeyError:
                return []
            return [('member', template.name, row)]
        if isinstance(start, Instances):
            template = self.templates.get(start.template)
            return (
                [('member', template.name, row) for row in range(len(template.members))] if template else []
            )
        if isinstance(start, Literal):
            return [place for item in start.items for place in self.walk(item, at, solver)]
        if isinstance(start, (Where, By, Lookup)):
            return self.walk(start.source, at, solver)
        if isinstance(start, Local) and solver is not None:
            for binding in solver.inputs:
                if binding.name == start.name:
                    return self.walk(binding.source, at)
        # An unknown of a solver, or a parameter or a local of an occurrence: no place of a member.
        return []

    def step(self, place, name):
        kind = place[0]
        if kind == 'root':
            value = self.program.root_value(name)
            if value is None:
                return []
            if value.kind == p.COLLECTION:
                return self.walk(value.init, None) if isinstance(value.init, Path) else []
            return [('value', '', 0, name)]
        if kind == 'member':
            _, template_name, row = place
            template = self.templates[template_name]
            part, member = template.part(name), template.members[row]
            if isinstance(part, p.Value):
                if part.kind == p.LINK:
                    target = member.link(name)
                    return [] if target is None else [('member', part.type.template, target)]
                if part.kind == p.COLLECTION:
                    init = member.value(name) or part.init
                    return self.walk(init, (template_name, row)) if isinstance(init, Path) else []
                return [('value', template_name, row, name)]
            if isinstance(part, p.Flow):
                return [('flow', template_name, row, name, part)]
            if isinstance(part, p.Event):
                return [('event', template_name, row, part)]
            return []
        if kind == 'flow':
            _, template_name, row, flow_name, flow = place
            if name in RATES:
                return [('rate', template_name, row, flow_name)]
            legs = [leg.name for leg in flow.legs] if flow.kind == p.LEGS else ['forward', 'backward']
            if flow.kind != p.DIRECTED and name in legs:
                return [('leg', template_name, row, flow_name)]
            return []
        if kind == 'leg':
            return [('rate', *place[1:])] if name == 'actual_rate' else []
        if kind == 'event':
            return [('occurrences', *place[1:])] if name == 'occurrences' else []
        if kind == 'occurrences':
            _, template_name, row, event = place
            for part in (*event.params, *event.locals):
                if part.name == name:
                    if isinstance(part, p.Flow):
                        return [('flow', template_name, row, f'{event.name}.{name}', part)]
                    return [('value', template_name, row, f'{event.name}.{name}')]
        return []


def _sign(node):
    """The sign of a number written in place (`-2`, `q(-2, 'W')`, `1/2`), or 0 for any other node."""
    if (
        isinstance(node, nodes.Const)
        and isinstance(node.value, (int, float))
        and not isinstance(node.value, bool)
    ):
        return (node.value > 0) - (node.value < 0)
    if isinstance(node, nodes.Call) and node.function == 'q' and node.args:
        return _sign(node.args[0])
    if isinstance(node, nodes.Unary) and node.op == 'neg':
        return -_sign(node.operand)
    if isinstance(node, nodes.Binary) and node.op == 'div':
        return _sign(node.left) * _sign(node.right)
    return 0
