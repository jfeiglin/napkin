"""What holds of a structure whatever the values of its inputs are.

`structure_facts` gives the diagnostics of one structure, and never stops at the first: the names,
the units, the shape of every trigger, the accounting groups, the outcomes and the bases of the
information links. The other functions answer the questions that these checks, the checks of a
resolved run (`values`) and the engine ask of a structure: what an expression reads through the
formulas, which names move between moments, the class of a trigger. Each function reads the typed
parts of the structure (`structure.Structure`), never a mapping of the builder. `checked` gives
the diagnostics of a structure and the structure with what its checks found.
"""

from __future__ import annotations

import ast
import math

from ...core import expr as nodes
from ...distributions import FAMILIES
from ...expressions import (
    BOOLEAN,
    NUMBER,
    STRING,
    ExpressionError,
    Unit,
    compile_expression,
    names_in,
)
from ..ir import COUNT, ENTERED, TIME, ModelError, delays_of_lag, diagnostic
from ..structure import Trigger, node

TIME_UNIT = Unit((('time', 1),))
HEALTH = ('ok', 'degraded', 'failed', 'inactive')


def topological(graph, path):
    result, visiting, visited = [], set(), set()

    def visit(key):
        if key in visiting:
            raise ModelError([diagnostic('cycle', path, f'Dependency cycle involving {key}')])
        if key in visited:
            return
        visiting.add(key)
        for dependency in sorted(graph[key]):
            if dependency in graph:
                visit(dependency)
        visiting.remove(key)
        visited.add(key)
        result.append(key)

    for key in sorted(graph):
        visit(key)
    return result


def symbol_units(s, units, errors=None):
    """Unit of every name an expression may read in a structure."""
    symbols = {'t': TIME_UNIT}

    def unit(name, path):
        try:
            return units.dimension(name)
        except ExpressionError as exc:
            if errors is not None:
                errors.append(diagnostic('unit', path, exc))
            return None

    for pid, p in s.parameters.items():
        symbols[pid] = unit(p.unit, p.path)
    for qid, q in s.quantities.items():
        symbols[qid] = unit(q.unit, q.path)
    for cid, c in s.computed.items():
        symbols[cid] = unit(c.unit, c.path)
    for mid in s.modes:
        symbols[mid] = STRING
        symbols[mid + ENTERED] = TIME_UNIT
    for lid in s.labels:
        symbols[lid] = STRING
    for event in s.events:
        symbols[event + COUNT] = NUMBER
        symbols[event + TIME] = TIME_UNIT
    return {name: value for name, value in symbols.items() if value is not None}


def expanded(s, source):
    """The names that an expression reads, through the formulas and the statuses. A formula gives
    the names that its expression reads, and a status those of the conditions of its cases. The
    names of the formulas and of the statuses on the way are not in the result. The structure keeps
    what each formula gives (`Structure.expanded`), so a formula is expanded once."""
    return s.expanded(source, labels=True)


def evolving_parts(structure):
    """The quantities that move between moments: each one with a rate that is not zero, and each end
    of a flow."""
    found = {name for name, rate in structure.rates.items() if str(rate.expr) not in ('0', '0.0')}
    found.update(
        end for flow in structure.flows.values() for end in (flow.source, flow.target) if end is not None
    )
    return found


def discrete_names(s):
    """Names that change only at moments."""
    moving = evolving_parts(s) | {'t'}
    names = set(s.parameters) | set(s.modes) | {q for q in s.quantities if q not in moving}
    names |= {e + COUNT for e in s.events}
    for cid, c in s.computed.items():
        if not expanded(s, c.expr) & moving:
            names.add(cid)
    for lid, label in s.labels.items():
        if not any(expanded(s, case.when) & moving for case in label.cases):
            names.add(lid)
    return names


# ---- triggers -----------------------------------------------------------------------------------


def _name(node):
    """The name that a node is a reference to, or None."""
    return node.name if isinstance(node, nodes.Ref) else None


def _conjuncts(node):
    if isinstance(node, nodes.BoolOp) and node.op == 'and':
        return [part for value in node.values for part in _conjuncts(value)]
    return [node]


def _all(parts):
    """The `and` of some conditions, none of which is an `and`: the node that they make together.
    Its text is written as every expression of a structure is, and reads back to the node."""
    return parts[0] if len(parts) == 1 else nodes.boolean('and', parts)


def _timer(node, discrete):
    """`t >= X` or `t - S >= d` (or the same reversed) as the absolute time X or S + d: the node of
    that time, or None when the condition is no such clock."""
    if not isinstance(node, nodes.Compare) or len(node.ops) != 1:
        return None
    (left, right), op = node.operands, node.ops[0]
    if op == 'le':
        left, right = right, left
    elif op != 'ge':
        return None
    if _name(left) == 't':
        time = right
    elif (
        isinstance(left, nodes.Binary)
        and left.op == 'sub'
        and _name(left.left) == 't'
        and _name(left.right) is not None
        and _name(left.right).endswith((TIME, ENTERED))
    ):
        time = nodes.binary('add', left.right, right)
    else:
        return None
    read = names_in(time)
    clock = {name for name in read if name.endswith((TIME, ENTERED))}
    return time if read - clock <= discrete else None


def _crossing(node, s, discrete, moving):
    """`q >= v` or `q <= v` with q an evolving quantity and v changing only at moments: the quantity
    (`var`), the comparison (`op`) and the node of the level (`value`), or None."""
    if not isinstance(node, nodes.Compare) or len(node.ops) != 1:
        return None
    (left, right), op = node.operands, node.ops[0]
    if _name(right) in moving and _name(left) not in moving:
        left, right = right, left
        op = {'ge': 'le', 'le': 'ge'}.get(op, op)
    var = _name(left)
    if var not in moving or var not in s.quantities or op not in ('ge', 'le'):
        return None
    if expanded(s, right) - discrete:
        return None
    return {'var': var, 'op': '>=' if op == 'ge' else '<=', 'value': right}


def classify(rule, s, discrete, moving):
    """The trigger of a rule with the kind of its `when`: discrete, timer, crossing or stock face.
    The result is a `Trigger` with the condition, its place and what its kind has. A condition that
    has no kind is a ValueError.

    A `when` is an `and` of conditions. A gate reads only values that change at moments. A clock is
    `t >= X` or `t - S >= d`, where the anchor `S` (an event's time or a state's entry time) and `d`
    change only at moments. A crossing is `q >= v` or `q <= v`, where `q` changes between moments and
    `v` changes only at moments. A face is any other condition on values that change between moments.

    A crossing goes with gates and with clocks, which give it `times`. The engine finds the first
    moment when such a `when` holds:
    - between two moments, every gate, anchor, duration and threshold is constant, so the clocks
      together are false before one time T, the latest `S + d`, and true from T until the next moment;
    - the crossing can change only where `q - v` changes sign, and `q` is continuous between moments;
    - so the condition first holds at T, when the crossing holds there, or else at the first root of
      `q - v` after T, in the direction that makes the crossing true;
    - the engine ends a segment at T, as for a timer, reads the rule there, and watches the root of
      the crossing from T;
    - a moment before T can change an anchor, a threshold or a gate; the engine reads a rule again
      after each step that writes a value that the rule reads, so no change is missed.
    Two crossings, a crossing with a face, or a clock with a face stay out: no such argument holds."""
    trigger = rule.trigger
    gate, times, crossings, faces = [], [], [], []
    for part in _conjuncts(node(trigger.when)):
        if not expanded(s, part) - discrete:
            gate.append(part)
            continue
        time = _timer(part, discrete)
        if time is not None:
            times.append(time)
            continue
        crossing = _crossing(part, s, discrete, moving)
        if crossing is not None:
            crossings.append(crossing)
            continue
        faces.append(part)
    if crossings and (faces or len(crossings) > 1):
        raise ValueError('a level rule may watch one evolving quantity; split it into two rules')
    if times and faces:
        raise ValueError('a level rule may not mix a clock with a condition on evolving quantities')
    found = {'when': trigger.when, 'gate': _all(gate) if gate else nodes.const(True)}
    if crossings:
        found.update(kind='crossing', **crossings[0])
        if times:
            # The clocks: the crossing is watched from the latest of them.
            found['times'] = times
    elif times:
        found.update(kind='timer', times=times)
    elif faces:
        found.update(kind='face', face=_all(faces))
    else:
        found.update(kind='discrete')
    # The trigger keeps the place of its condition for the checks of the structures: its own, or
    # that of its rule for an event with no condition.
    found['path'] = rule.path if trigger.path is None else trigger.path
    # The record is read from these keys (`Part.of`), so its plain data has them in this order.
    return Trigger.of(found)


# ---- structure ----------------------------------------------------------------------------------


def checked(structure, library, units):
    """(the diagnostics, the structure with the facts) of one structure (`structure.Structure`): the
    checks of `structure_facts`, and the copy of the structure with what they found
    (`Structure.with_facts`)."""
    errors, facts = structure_facts(structure, library, units)
    return errors, structure.with_facts(facts)


def structure_facts(s, library, units):
    """(the diagnostics of one structure, what the checks find of it). `s` is the typed parts of the
    structure (`structure.Structure`), which cannot change: `Structure.with_facts` gives the
    structure with the facts.

    The facts: `computed_order`, the formulas in an order in which each comes after those that it
    reads (empty when they form a circle), and `triggers`, the classified trigger of each rule whose
    condition has a class (`classify`), as a `Trigger`."""
    errors = []
    triggers = {}
    symbols = symbol_units(s, units, errors)
    # Each expression that the checks read, with its place (`_written_out_errors`).
    read = []

    def check(source, path, expected=None, available=None):
        try:
            found = compile_expression(source, symbols if available is None else available, units, expected)
        except (ExpressionError, SyntaxError, RecursionError) as exc:
            errors.append(diagnostic('expression', path, exc))
            return None
        read.append((found.source, path))
        return found

    def unit_of(name):
        return symbols.get(name)

    for pid, p in s.parameters.items():
        control = (p.metadata or {}).get('control')
        if control == 'binary' and (
            symbols[pid] is None or symbols[pid].dimensions or units.scale(p.unit) != 1
        ):
            errors.append(
                diagnostic(
                    'binary_control',
                    f'{p.path}/unit',
                    'A binary control has an unscaled dimensionless unit',
                )
            )
        if control == 'choice' and p.unit != 'fraction':
            errors.append(
                diagnostic('choice_control', f'{p.path}/unit', 'A choice is a code with the unit fraction')
            )
    for qid, q in s.quantities.items():
        path = q.path
        low, high = q.minimum, q.maximum
        check(q.initial, f'{path}/initial', unit_of(qid))
        for bound, limit in (('min', low), ('max', high)):
            if isinstance(limit, nodes.Node):
                check(limit, f'{path}/{bound}', unit_of(qid), {n: symbols[n] for n in s.parameters})
        if isinstance(low, (int, float)) and isinstance(high, (int, float)) and low > high:
            errors.append(diagnostic('bounds', path, 'Minimum exceeds maximum'))
        # A stock with no minimum has the minimum 0.
        floor = 0 if low is None else low
        if q.kind == 'stock' and isinstance(floor, (int, float)) and floor < 0:
            errors.append(diagnostic('bounds', path, 'Physical stock minimum cannot be negative'))
        if q.binary and (q.unit != 'fraction' or q.kind != 'variable' or low != 0 or high != 1):
            errors.append(
                diagnostic('binary_state', path, 'A binary quantity is a fraction variable bounded by [0, 1]')
            )
    graph = {}
    for cid, c in s.computed.items():
        expression = check(c.expr, f'{c.path}/expr', unit_of(cid))
        graph[cid] = set(expression.dependencies) & s.computed.keys() if expression else set()
    try:
        computed_order = topological(graph, 'computed')
    except ModelError as exc:
        errors.extend(exc.diagnostics)
        computed_order = []
    for lid, label in s.labels.items():
        for i, case in enumerate(label.cases):
            check(case.when, f'{case_path(case.path, label.path, i)}/when', BOOLEAN)
        if lid.endswith('.health'):
            for value in [case.value for case in label.cases] + [label.default.value]:
                if value not in HEALTH:
                    errors.append(
                        diagnostic('health', label.path, f'Health is one of {HEALTH}, not {value!r}')
                    )
    for qid, rate in s.rates.items():
        if qid in symbols:
            check(rate.expr, rate.path, symbols[qid].multiply(TIME_UNIT, divide=True))
    for flow in s.flows.values():
        ends = [end for end in (flow.source, flow.target) if end is not None]
        if (
            len(ends) == 2
            and ends[0] in symbols
            and ends[1] in symbols
            and not symbols[ends[0]].compatible(symbols[ends[1]])
        ):
            errors.append(diagnostic('unit', flow.path, 'Flow ends have different dimensions'))
        if ends[0] in symbols:
            check(flow.rate, f'{flow.path}/rate', symbols[ends[0]].multiply(TIME_UNIT, divide=True))
        if flow.allocation is not None and flow.allocation not in s.allocation:
            errors.append(diagnostic('reference', flow.path, f'Unknown allocation group {flow.allocation}'))
    errors.extend(_withdrawal_errors(s))
    errors.extend(_group_errors(s, symbols, check))
    discrete, moving = discrete_names(s), evolving_parts(s)
    for rule in s.rules.values():
        for item in rule.extras or ():
            symbols[item.name] = _extra_unit(item, rule.path, check)
    binary = {q for q, d in s.quantities.items() if d.binary}
    for rid, rule in s.rules.items():
        found, trigger = _rule_errors(rid, rule, s, symbols, check, discrete, moving, binary)
        errors.extend(found)
        if trigger is not None:
            triggers[rid] = trigger
    static = {
        n: symbols[n]
        for n in symbols
        if n in s.parameters
        or (n in s.computed and not expanded(s, s.computed[n].expr) - s.parameters.keys())
    }
    for item in s.input_checks.values():
        check(item.expr, item.path, BOOLEAN, static)
    for item in s.state_checks.values():
        check(item.expr, item.path, BOOLEAN)
    for partition in s.partitions.values():
        units_of = [symbols.get(part) for part in partition.parts]
        if any(u is None for u in units_of) or any(not units_of[0].compatible(u) for u in units_of[1:]):
            errors.append(diagnostic('unit', partition.path, 'Partition parts need one unit'))
        elif units_of:
            check(partition.total, f'{partition.path}/total', units_of[0])
            if partition.tolerance:
                check(partition.tolerance, f'{partition.path}/tolerance', units_of[0])
    errors.extend(_outcome_errors(s, symbols, check, units))
    errors.extend(_link_basis_errors(s))
    errors.extend(_written_out_errors(s, read, computed_order))
    return errors, {'computed_order': computed_order, 'triggers': triggers}


def _written_height(node, formulas):
    """The height of the tree of a node with each formula of `formulas` (name -> the height of its
    own tree, written out) in the place of its name: a name or a number is 1, as in `expr.height`.
    It goes down with a list and not with calls."""
    if not isinstance(node, nodes.Node):
        return 1
    found, pending = {}, [node]
    while pending:
        part = pending[-1]
        if isinstance(part, nodes.Ref):
            found[part] = formulas.get(part.name, 1)
            pending.pop()
            continue
        waiting = [child for child in part.children if child not in found]
        if waiting:
            pending += waiting
            continue
        found[part] = 1 + max((found[child] for child in part.children), default=0)
        pending.pop()
    return found[node]


def _written_out_errors(s, read, order):
    """An expression whose tree is deeper than the readers of an expression go (`expr.DEEPEST`) when
    each formula that it reads is written in the place of its name, as the engine writes it
    (`timeline.plan`): each formula and each other expression of the structure, at its place. Each
    one alone can be within the limit (D-75): a chain of formulas that read one another is not."""
    formulas = {}
    for name in order:  # each formula after those that it reads
        formulas[name] = _written_height(s.computed[name].expr, formulas)
    errors = []
    for source, path in read:
        if _written_height(source, formulas) > nodes.DEEPEST:
            errors.append(
                diagnostic(
                    'expression',
                    path,
                    f'with the formulas that it reads written in the place of their names, the '
                    f'expression has more than {nodes.DEEPEST} operations one inside the other',
                )
            )
    return errors


def _withdrawal_errors(s):
    """Scarce stock is never shared out by dictionary or solver order: competing withdrawals
    from one finite stock need one allocation policy, unless each rate vanishes with its source."""
    errors = []

    def vanishes_at_source(rate, source, seen=frozenset()):
        def visit(node):
            if isinstance(node, nodes.Const):
                return node.value == 0 and not isinstance(node.value, bool)
            symbol = nodes.text(node)
            if symbol == source:
                return True
            if symbol in s.computed and symbol not in seen:
                return vanishes_at_source(s.computed[symbol].expr, source, seen | {symbol})
            if isinstance(node, nodes.Unary):
                return visit(node.operand)
            if isinstance(node, nodes.IfElse):
                return visit(node.body) and visit(node.orelse)
            if isinstance(node, nodes.Binary):
                if node.op in ('add', 'sub'):
                    return visit(node.left) and visit(node.right)
                if node.op == 'mul':
                    return visit(node.left) or visit(node.right)
                if node.op == 'div':
                    return visit(node.left)
                if node.op == 'pow' and isinstance(node.right, nodes.Const):
                    return node.right.value > 0 and visit(node.left)
            if isinstance(node, nodes.Call) and node.function == 'q':
                return len(node.args) == 2 and visit(node.args[0])
            if isinstance(node, nodes.Foreign):
                # A part outside the language, which the rules for units reject: read as it was.
                tree = node.tree
                if isinstance(tree, ast.UnaryOp):
                    return visit(nodes.of_tree(tree.operand))
                if isinstance(tree, ast.Call) and isinstance(tree.func, ast.Name) and tree.func.id == 'q':
                    return len(tree.args) == 2 and visit(nodes.of_tree(tree.args[0]))
            return False

        try:
            return visit(node(rate))
        except TypeError:
            return False

    leaving = {}  # the flows out of each quantity, in the order of the flows
    for fid, f in s.flows.items():
        if f.source is not None:
            leaving.setdefault(f.source, {})[fid] = f
    for qid, q in s.quantities.items():
        outgoing = leaving.get(qid, {})
        if len(outgoing) < 2 or (q.minimum is None and q.kind != 'stock'):
            continue
        # A quantity with no minimum is a stock here, and its minimum is 0.
        floor = 0 if q.minimum is None else q.minimum
        if floor == 0 and all(vanishes_at_source(f.rate, qid) for f in outgoing.values()):
            continue
        groups = {f.allocation for f in outgoing.values()}
        if None in groups or len(groups) != 1:
            errors.append(
                diagnostic(
                    'allocation',
                    q.path,
                    'Competing withdrawals require one explicit allocation policy',
                )
            )
    return errors


def case_path(own, status, i):
    """The path of case i of a status: its own (`own`: the file's `shows/i`), or `cases/i` of the
    status (`status`: the path of the status)."""
    return own or f'{status}/cases/{i}'


def group_path(gid, own, part=''):
    """The path of an allocation group's diagnostics: its own (`own`: the rationing entry that
    declares it), or `allocation/<group>` (with `part`)."""
    return own or f'allocation/{gid}{part}'


def _end(flow):
    """The quantity that a flow drains, or, for a flow from outside the model, the one that it fills."""
    return flow.target if flow.source is None else flow.source


def _group_errors(s, symbols, check):
    errors = []
    grouped = {}  # the flows of each group, in the order of the flows
    for fid, f in s.flows.items():
        if f.allocation is not None:
            grouped.setdefault(f.allocation, {})[fid] = f
    for gid, group in s.allocation.items():
        members = grouped.get(gid, {})
        if not members:
            errors.append(diagnostic('allocation', group_path(gid, group.path), 'Empty allocation group'))
            continue
        end = _end(next(iter(members.values())))
        if end in symbols:
            rate = symbols[end].multiply(TIME_UNIT, divide=True)
            check(group.capacity, group_path(gid, group.path, '/capacity'), rate)
            for flow in members.values():
                other = _end(flow)
                if other in symbols and not symbols[other].multiply(TIME_UNIT, divide=True).compatible(rate):
                    errors.append(
                        diagnostic(
                            'allocation', group_path(gid, group.path), 'Allocation members have unlike units'
                        )
                    )
        if group.policy == 'priority' and set(group.order or ()) != set(members):
            errors.append(
                diagnostic(
                    'allocation',
                    group_path(gid, group.path),
                    'Priority order must list each member exactly once',
                )
            )
    coupled = set()
    for gid, group in s.coupling.items():
        members = set(group.flows)
        if members & coupled:
            errors.append(
                diagnostic('coupling', f'coupling/{gid}', 'A flow can belong to only one coupling group')
            )
        coupled |= members
    return errors


def _transaction_errors(step, path, symbols, check, rules=None, binary=frozenset()):
    """Typing of one flat transaction; each item is reported where its author wrote it. A yes/no
    state (`binary`) is set to `1 if (C) else 0` with C a condition."""
    errors = []
    for target in step.fire:
        if rules is not None and target not in rules:
            errors.append(diagnostic('reference', path, f'Unknown event {target}'))
    for target, value in step.set.items():
        if value.expr is not None:
            where = f'{path}/set/{target}' if value.path is None else value.path
            if target in binary and isinstance(value.expr, nodes.IfElse):
                check(value.expr.test, where, BOOLEAN)
            check(value.expr, where, symbols.get(target))
    for transfer in step.transfer:
        a, b = symbols.get(transfer.source), symbols.get(transfer.target)
        where = transfer.path
        if a is not None and b is not None and not a.compatible(b):
            errors.append(diagnostic('unit', where, 'Transfer ends differ'))
        check(transfer.amount, where, a)
    return errors


# The parameters of a distribution of numbers that are plain numbers, whatever the unit of its
# values: those that its family says have no dimension.
PLAIN_PARAMETERS = {
    name: family.dimensionless
    for name, family in FAMILIES.items()
    if family.kind == 'number' and family.dimensionless
}


def _extra_unit(item, path, check):
    """The unit of a value that an event reads when it fires: a draw takes the unit of its distribution's
    parameters (every one that is not a plain number has it), a delayed value the unit of its value,
    and its delay is a time."""
    if item.kind == 'delayed':
        check(item.delay, path, TIME_UNIT)
        found = check(item.expr, path)
        return found.unit if found is not None else None
    plain = PLAIN_PARAMETERS.get(item.family, set())
    unit = NUMBER if item.family == 'beta' else None
    for name, source in (item.args or {}).items():
        if name in plain:
            check(source, path, NUMBER)
            continue
        found = check(source, path, unit)
        if unit is None and found is not None:
            unit = found.unit
    return unit


def _rule_errors(rid, rule, s, symbols, check, discrete, moving, binary):
    """(the diagnostics of one rule, its classified trigger or None when its condition has no class).
    `binary` names the quantities that hold a yes/no."""
    errors = []
    classified = None
    path = rule.path
    when = path if rule.trigger.path is None else rule.trigger.path
    if check(rule.trigger.when, when, BOOLEAN) is not None:
        try:
            classified = classify(rule, s, discrete, moving)
        except ValueError as exc:
            errors.append(diagnostic('unsupported_condition', when, exc))
    if rule.delay is not None:
        check(rule.delay, path if rule.delay_path is None else rule.delay_path, TIME_UNIT)
    each_path = path if rule.each_path is None else rule.each_path
    keep_path = path if rule.keep_path is None else rule.keep_path
    # A window and a waiting condition read only values that change at moments: the engine reads
    # them again after each step that writes one of those values, so none of their changes is missed.
    for source, where in [
        *((item, each_path) for item in rule.each or ()),
        *([(rule.keep, keep_path)] if rule.keep else []),
    ]:
        if expanded(s, source) - discrete:
            errors.append(
                diagnostic(
                    'unsupported_condition',
                    where,
                    'each W and while K read only values that change at moments',
                )
            )
    for item in rule.each or ():
        check(item, each_path)
    if rule.keep:
        check(rule.keep, keep_path, BOOLEAN)
    for outcome in rule.outcomes:
        if outcome.chance not in (None, 'else'):
            # A number from 0 to 1, or a condition: the engine reads it when the event fires.
            check(outcome.chance, f'{outcome.path}/chance')
        if outcome.available:
            # When the outcome can happen: a condition that the engine reads when the event fires.
            check(outcome.available, f'{outcome.path}/available', BOOLEAN)
        errors.extend(_transaction_errors(outcome.do, outcome.path, symbols, check, s.rules, binary))
    errors.extend(_rearm_errors(rid, rule, rule.trigger if classified is None else classified))
    return errors, classified


def _rearm_errors(rid, rule, trigger):
    """An event that can fire again and that watches a crossing must, when it fires, make its own
    condition false at that moment: it changes a value that its gate tests. The engine watches a
    crossing only while the event can fire, so it would miss the crossing falling back and rising
    again between two moments."""
    # A window spends the crossing too: the event fires again only in another window.
    if rule.once or rule.each or trigger.kind != 'crossing':
        return []
    gate = names_in(True if trigger.gate is None else trigger.gate)
    if all(gate & set(outcome.do.set) for outcome in rule.outcomes):
        return []
    return [
        diagnostic(
            'unsupported_condition',
            rule.path if trigger.path is None else trigger.path,
            f'{rid} watches a crossing and can fire again: mark it once, or let each of its outcomes '
            'change a named state that its condition tests',
        )
    ]


def lag_delays(lag):
    """The delay expressions of the lag of an output, in order (`ir.delays_of_lag`): what the checks
    of a structure, the checks of a run and the reports ask of the typed part."""
    shares = [(part.weight, part.delay) for part in lag.components or ()]
    return delays_of_lag(lag.type, lag.delay, lag.minimum, lag.maximum, shares)


def _outcome_errors(s, symbols, check, units):
    errors = []
    outcome_symbols = dict(symbols)
    for name, outcome in s.outcomes.items():
        path = f'outcomes/{name}'
        try:
            outcome_symbols[name] = units.dimension(outcome.unit)
        except ExpressionError as exc:
            errors.append(diagnostic('unit', path, exc))
    graph = {}
    for name, outcome in s.outcomes.items():
        dependencies = set()
        if outcome.expr is not None and name in outcome_symbols:
            expression = check(outcome.expr, f'outcomes/{name}', outcome_symbols[name], outcome_symbols)
            if expression:
                dependencies = set(expression.dependencies)
        graph[name] = dependencies & s.outcomes.keys()
        lag = outcome.lag
        if lag is not None:
            if outcome.kind != 'cumulative':
                errors.append(
                    diagnostic('lag', f'outcomes/{name}', 'A reporting lag needs a cumulative count')
                )
            for i, delay in enumerate(lag_delays(lag)):
                check(
                    delay,
                    f'outcomes/{name}/lag/{i}',
                    TIME_UNIT,
                    {n: symbols[n] for n in s.parameters if n in symbols},
                )
            if lag.type == 'mixture' and not math.isclose(
                sum(part.weight for part in lag.components or ()), 1.0, rel_tol=0, abs_tol=1e-12
            ):
                errors.append(diagnostic('lag', f'outcomes/{name}', 'Mixture weights must sum to one'))
        errors.extend(_additive_errors(name, outcome, s, units))
    try:
        topological(graph, 'outcomes')
    except ModelError as exc:
        errors.extend(exc.diagnostics)
    return errors


def _additive_errors(name, outcome, s, units):
    """An outcome that adds counts of people adds different people: one partition's parts, or an
    explicit `additive` basis. Counts of episodes may be added freely."""
    if outcome.expr is None or outcome.distinct():
        return []
    try:
        people = units.dimension(outcome.unit).dimensions == (('people', 1),)
    except ExpressionError:
        return []
    if not people:
        return []
    terms = []

    def walk(n, seen):
        if isinstance(n, nodes.Binary) and n.op == 'add':
            walk(n.left, seen)
            walk(n.right, seen)
        elif _name(n) in s.outcomes and _name(n) not in seen and s.outcomes[_name(n)].expr is not None:
            # Another outcome counts the parts it adds.
            walk(node(s.outcomes[_name(n)].expr), seen | {_name(n)})
        else:
            terms.append(n)

    walk(node(outcome.expr), {name})
    if len(terms) < 2:
        return []
    symbols = [_name(term) for term in terms]
    for partition in s.partitions.values():
        if None not in symbols and len(set(symbols)) == len(symbols) and set(symbols) <= set(partition.parts):
            return []
    return [
        diagnostic(
            'additive',
            f'outcomes/{name}',
            'Adding counts of people needs their terms from one partition, or an `additive` basis that says they are different people',
        )
    ]


def _link_basis_errors(s):
    """Information an entity acts on needs a basis: a link that a rule's trigger reads."""
    errors = []
    for rid, rule in s.rules.items():
        eid = rule.entity
        links = s.links.get(eid, {})
        read = names_in(rule.trigger.when)
        for name, link in links.items():
            target = link.target
            used = target in read or any(
                r.startswith(target + '__') or r.startswith(target + '.') for r in read
            )
            if used and not link.basis:
                errors.append(
                    diagnostic(
                        'link_basis',
                        f'entities/{eid}/links/{name}',
                        f'{name} is information that rule {rid} acts on; give the link a basis',
                    )
                )
    return list({e['path']: e for e in errors}.values())
