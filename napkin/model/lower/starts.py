"""The parts that a set of start-state options leaves out of a structure.

A run takes some options that set start states. With those start values some parts of the model can
never act: a rule whose condition cannot hold, a quantity that starts at zero and that nothing fills, a
named state that nothing changes and nothing reads, an entity that neither acts nor is read. The
structure of those runs leaves them out, each with its reason (`WHY`).

- `settled` gives an expression with the named states at their start values and the stocks that are
  left out at zero of their unit.
- `Acting` finds, as a fixed point over the rules, the values that each named state can take and the
  events that can happen.
- `idle_parts` gives the parts that cannot act, with every part that goes with them; `remove` takes
  them out of a structure.
- The other functions give the names that a part reads.

Every expression here is a typed node (`napkin/core/expr.py`) or a number: the mappings of the
builder hold nodes, and a caller that has plain data reads it into typed parts first.
"""

from __future__ import annotations

from ...core import expr as nodes
from ...expressions import names_in
from ..ir import COUNT, ENTERED, TIME, extra_sources, lag_delays, rule_steps
from ..semantic import MAIN


def _tree(source):
    """The typed node of an expression that a mapping of the builder holds: its node, or the node of
    a number or a yes/no as its text reads. A text is a TypeError."""
    if isinstance(source, nodes.Node):
        return source
    if isinstance(source, str):
        raise TypeError('an expression of a mapping of the builder is a node or a number, not a text')
    return nodes.parse(str(source))


def _expression(source):
    """Whether a value of a structure is an expression and no bare number. A text is one, so that
    `names_in` refuses it."""
    return isinstance(source, (str, nodes.Node))


def _named(node):
    """The name that a node is a reference to, or None."""
    return node.name if isinstance(node, nodes.Ref) else None


def _settled(node):
    return isinstance(node, nodes.Const) and isinstance(node.value, bool)


class Settled:
    """An expression in the runs of one structure: comparisons of the named states in `starts` with a
    text, at their start values, and the stocks in `zeros` at zero of their unit; `and`, `or`, `not`
    and `a if c else b` simplified around the settled values. `visit` gives the node of a node."""

    def __init__(self, starts, zeros):
        self.starts, self.zeros, self.changed = starts, zeros, False

    def compared(self, node):
        """The yes/no of a test of a named state with a text that these runs settle, or None."""
        if len(node.ops) == 1 and node.ops[0] in ('eq', 'ne'):
            name, other = _named(node.operands[0]), node.operands[1]
            if name in self.starts and isinstance(other, nodes.Const) and isinstance(other.value, str):
                self.changed = True
                return nodes.const((self.starts[name] == other.value) == (node.ops[0] == 'eq'))
        return None

    def visit(self, node):
        if isinstance(node, nodes.Ref):
            # A stock is `entity.member`: a name with no dot is none.
            if '.' in node.name and node.name in self.zeros:
                self.changed = True
                return nodes.call('q', [nodes.const(0), nodes.const(self.zeros[node.name])])
            return node
        if isinstance(node, nodes.Compare):
            found = self.compared(node)
            if found is not None:
                return found
            return nodes.compare(node.ops, [self.visit(side) for side in node.operands])
        if isinstance(node, nodes.Unary):
            operand = self.visit(node.operand)
            if node.op == 'not' and _settled(operand):
                return nodes.const(not operand.value)
            return nodes.unary(node.op, operand)
        if isinstance(node, nodes.IfElse):
            test, body, orelse = self.visit(node.test), self.visit(node.body), self.visit(node.orelse)
            if _settled(test):
                return body if test.value else orelse
            return nodes.if_else(test, body, orelse)
        if isinstance(node, nodes.BoolOp):
            decides = node.op == 'or'  # the value that settles the whole: True for or
            values = []
            for value in map(self.visit, node.values):
                if _settled(value):
                    if value.value == decides:
                        return nodes.const(decides)
                    continue
                values.append(value)
            if not values:
                return nodes.const(not decides)
            if len(values) == 1:
                return values[0]
            return nodes.boolean(node.op, values)
        if isinstance(node, nodes.Binary):
            return nodes.binary(node.op, self.visit(node.left), self.visit(node.right))
        if isinstance(node, nodes.Call):
            return nodes.call(node.function, [self.visit(arg) for arg in node.args])
        return node


def settled(source, starts, zeros):
    """An expression (a typed node or a number) with the named states of `starts` at their
    start values and the stocks of `zeros` at zero of their unit: the source itself when they change
    nothing, else True or False when it is settled, else its typed node."""
    settle = Settled(starts, zeros)
    found = settle.visit(_tree(source))
    if not settle.changed:
        return source
    return found.value if _settled(found) else found


# ---- the parts that cannot act ------------------------------------------------------------------
#
# A structure leaves out the parts that cannot act in any of its runs, from its start values: the rules
# that cannot fire, the stocks and tallies that
# start at zero and that no part that stays changes or reads (outputs and checks read them as zero),
# the named states that no part that stays changes or reads, and the entities none of whose parts can
# act and that no part that stays reads, with their flows. Every part that stays keeps what it names
# (`quantity_names`, `flow_names`, `partition_names`, the steps of its rules), also a flow whose rate is
# zero in every state that the runs reach; an event that a part that stays counts or times stays too
# (`read_events`). Inputs stay: every run accepts every input.

WHY = {
    'rules': 'It cannot fire: its trigger needs a value of a named state or an event that these runs never reach, and no event that can happen names it.',
    'quantities': 'It starts at zero, and nothing that acts changes or reads it; outputs and checks read zero.',
    'modes': 'Nothing that acts changes or reads it.',
    'entities': 'None of its parts can act, and nothing that acts reads it.',
}


def _count(node):
    """The event of `x__count`, or None."""
    name = _named(node)
    return name[: -len(COUNT)] if name and name.endswith(COUNT) else None


_COMPARE = {
    'eq': lambda a, b: a == b,
    'ne': lambda a, b: a != b,
    'lt': lambda a, b: a < b,
    'le': lambda a, b: a <= b,
    'gt': lambda a, b: a > b,
    'ge': lambda a, b: a >= b,
}


# A condition in disjunctive form: a list of terms, each a list of atoms that must all hold. An atom is
# ('in', state, values), ('count', event, test, number), ('const', bool) or ('other',), which can hold.
TERMS = 256


def _atom(node, values):
    """The atom of one comparison, or ('other',)."""
    if _settled(node):
        return ('const', node.value)
    if not (isinstance(node, nodes.Compare) and len(node.ops) == 1):
        return ('other',)
    (left, right), op = node.operands, node.ops[0]
    if op in ('eq', 'ne'):
        name, value = (_named(right), left) if isinstance(left, nodes.Const) else (_named(left), right)
        if name in values and isinstance(value, nodes.Const) and isinstance(value.value, str):
            allowed = {value.value} if op == 'eq' else set(values[name]) - {value.value}
            return ('in', name, frozenset(allowed))
    for side, other, first in ((left, right, True), (right, left, False)):
        event = _count(side)
        number = isinstance(other, nodes.Const) and isinstance(other.value, (int, float))
        if event and number and not isinstance(other.value, bool):
            return ('count', event, op, other.value, first)
    return ('other',)


def terms_of(node, values):
    """The disjunctive form of a condition, or one term of an unknown atom when it would be too long."""
    if isinstance(node, nodes.BoolOp) and node.op == 'and':
        out = [[]]
        for value in node.values:
            out = [a + b for a in out for b in terms_of(value, values)]
            if len(out) > TERMS:
                return [[('other',)]]
        return out
    if isinstance(node, nodes.BoolOp):
        out = [term for value in node.values for term in terms_of(value, values)]
        return out if len(out) <= TERMS else [[('other',)]]
    if isinstance(node, nodes.Unary) and node.op == 'not':
        atom = _atom(node.operand, values)
        if atom[0] == 'in':
            return [[('in', atom[1], frozenset(set(values[atom[1]]) - atom[2]))]]
        if atom[0] == 'const':
            return [[('const', not atom[1])]]
        return [[('other',)]]
    return [[_atom(node, values)]]


class Acting:
    """What the runs of a structure can reach from its start values: the rules that can fire, the
    values of each named state, the values that two named states that a condition tests together
    can take at once, and the events that can happen.

    Every condition on a stock, a time or anything else counts as possible, so nothing that can
    happen is missed. A rule fires where its trigger can hold, or where a line of an outcome that can
    happen names it; an outcome happens where its chance can be above 0."""

    def __init__(self, s):
        self.s = s
        self.values = {name: tuple(mode['values']) for name, mode in s['modes'].items()}
        self.reach = {name: {mode['initial']} for name, mode in s['modes'].items()}
        self.events, self.fired, self.committed, self.named = set(), set(), set(), set()
        self.terms, self.chances = {}, {}
        for rid, rule in s['rules'].items():
            self.terms[rid] = terms_of(_tree(rule['trigger']['when']), self.values)
            for k, outcome in enumerate(rule['outcomes']):
                chance = outcome['chance']
                # The chance as a condition: `else`, and a number that is no expression, can happen.
                can = _tree(chance) if _expression(chance) and chance != 'else' else nodes.const(True)
                if outcome.get('available'):
                    can = nodes.boolean('and', [can, _tree(outcome['available'])])
                self.chances[(rid, k)] = terms_of(can, self.values)
        self.pairs = {}
        for terms in [*self.terms.values(), *self.chances.values()]:
            for term in terms:
                states = sorted({atom[1] for atom in term if atom[0] == 'in'})
                for i, a in enumerate(states):
                    for b in states[i + 1 :]:
                        self.pairs.setdefault((a, b), {(s['modes'][a]['initial'], s['modes'][b]['initial'])})
        self.run()

    def holds(self, term):
        """Whether one term can hold in a state that the runs reach."""
        allowed = {}
        for atom in term:
            if atom[0] == 'const' and not atom[1]:
                return False
            if atom[0] == 'in':
                allowed[atom[1]] = allowed.get(atom[1], frozenset(self.values[atom[1]])) & atom[2]
            if atom[0] == 'count' and atom[1] not in self.events:
                _, _, op, number, first = atom
                if not (_COMPARE[op](0, number) if first else _COMPARE[op](number, 0)):
                    return False
        if any(not values & self.reach[name] for name, values in allowed.items()):
            return False
        names = sorted(allowed)
        for i, a in enumerate(names):
            for b in names[i + 1 :]:
                pair = self.pairs.get((a, b))
                if pair is not None and not any(x in allowed[a] and y in allowed[b] for x, y in pair):
                    return False
        return True

    def can(self, terms):
        return any(self.holds(term) for term in terms)

    def effect(self, step, name, value):
        """The values that one step can give a named state that holds `value` before it."""
        if name in step['set']:
            found = step['set'][name]
            return {found['mode']} if 'mode' in found else set(self.values[name])
        return {value}

    def run(self):
        while True:
            size = (
                len(self.fired),
                len(self.committed),
                len(self.events),
                sum(map(len, self.reach.values())),
                sum(map(len, self.pairs.values())),
            )
            for rid, rule in self.s['rules'].items():
                if not (self.can(self.terms[rid]) or rid in self.named):
                    continue
                self.fired.add(rid)
                self.events.update(rule['emits'])
                for k, outcome in enumerate(rule['outcomes']):
                    if not self.can(self.chances[(rid, k)]):
                        continue
                    self.committed.add((rid, k))
                    self.events.update(outcome['emits'])
                    step = outcome['do']
                    self.named.update(step['fire'])
                    changed = set(step['set']) & self.reach.keys()
                    for name in changed:
                        for value in list(self.reach[name]):
                            self.reach[name] |= self.effect(step, name, value)
                    terms = self.terms[rid] if rid not in self.named else [[]]
                    for (a, b), pair in self.pairs.items():
                        if a not in changed and b not in changed:
                            continue
                        for x, y in list(pair):
                            fixed = [('in', a, frozenset({x})), ('in', b, frozenset({y}))]
                            if any(self.holds(t + fixed) for t in terms):
                                for x2 in self.effect(step, a, x):
                                    for y2 in self.effect(step, b, y):
                                        pair.add((x2, y2))
            if size == (
                len(self.fired),
                len(self.committed),
                len(self.events),
                sum(map(len, self.reach.values())),
                sum(map(len, self.pairs.values())),
            ):
                return


class Reached(Settled):
    """An expression with each test of a named state settled where the values it can take decide it."""

    def __init__(self, reach):
        super().__init__({}, {})
        self.reach = reach

    def compared(self, node):
        if len(node.ops) == 1 and node.ops[0] in ('eq', 'ne'):
            name, other = _named(node.operands[0]), node.operands[1]
            if name in self.reach and isinstance(other, nodes.Const) and isinstance(other.value, str):
                equal = node.ops[0] == 'eq'
                if other.value not in self.reach[name]:
                    return nodes.const(not equal)
                if self.reach[name] == {other.value}:
                    return nodes.const(equal)
        return None


def is_zero(node):
    """A constant zero: `0`, `q(0, unit)`, a product with a zero factor, or a choice of two zeros."""
    if isinstance(node, nodes.Const):
        return isinstance(node.value, (int, float)) and not isinstance(node.value, bool) and node.value == 0
    if isinstance(node, nodes.Call) and node.function == 'q' and node.args:
        return is_zero(node.args[0])
    if isinstance(node, nodes.Binary) and node.op == 'mul':
        return is_zero(node.left) or is_zero(node.right)
    if isinstance(node, nodes.IfElse):
        return is_zero(node.body) and is_zero(node.orelse)
    return False


def zero(text, reach=None):
    node = _tree(text)
    if reach is not None:
        node = Reached(reach).visit(node)
    return is_zero(node)


def step_names(step):
    """The names that a flat step reads."""
    found = set()
    for value in step['set'].values():
        if 'expr' in value:
            found |= names_in(value['expr'])
    for transfer in step['transfer']:
        found |= names_in(transfer['amount'])
    return found


def step_changes(step):
    """The values that a flat step changes: the targets of its `set` and the ends of its moves."""
    return set(step['set']) | {transfer[end] for transfer in step['transfer'] for end in ('from', 'to')}


def texts_names(*texts):
    """The names that some expressions read; a number reads nothing."""
    return set().union(*(names_in(text) for text in texts if _expression(text)))


# ---- what each part of a structure names ---------------------------------------------------------
#
# One reader for every part: what a part reads, and what it moves. A part that a structure keeps keeps
# every part that it names (`idle_parts`), and a run reads what its parts name (`run_reads`).


def quantity_names(s, qid):
    """The names that a stock, tally or number state reads: its start value, its bounds and its rate."""
    quantity = s['quantities'][qid]
    rate = s['rates'].get(qid, {}).get('expr')
    return texts_names(*(quantity.get(key) for key in ('initial', 'min', 'max')), rate)


def flow_names(flow):
    """The names that a flow reads or moves: what its rate reads, and its ends. A flow whose rate is
    zero in every state that the runs reach still names them."""
    return names_in(flow['rate']) | {flow[end] for end in ('from', 'to') if end in flow}


def partition_names(partition):
    """The names that a sum check reads: its stocks and tallies, its total and its tolerance."""
    return set(partition['parts']) | texts_names(partition['total'], partition.get('tolerance'))


def outcome_names(outcome):
    """The names that an output reads: its expression and the delays of its lag."""
    return texts_names(outcome.get('expr'), *lag_delays(outcome.get('lag')))


def run_reads(s, rules, checks):
    """The names that a run of a structure reads: in `rules` (their triggers and steps), and in every
    part that the engine evaluates whether or not a rule fires: start values and bounds, rates,
    formulas, statuses, flows, rationing limits, outputs and their lags, partitions and `checks`."""
    found = texts_names(*checks, *(rule['trigger']['when'] for rule in rules))
    found |= texts_names(*(rule['delay'] for rule in rules if rule.get('delay')))
    found |= texts_names(*(item for rule in rules for item in rule.get('each', ())))
    found |= texts_names(*(rule['keep'] for rule in rules if rule.get('keep')))
    found |= texts_names(*(source for rule in rules for source in extra_sources(rule)))
    found |= texts_names(
        *(o['chance'] for rule in rules for o in rule['outcomes'] if o['chance'] not in (None, 'else'))
    )
    found |= texts_names(*(o['available'] for rule in rules for o in rule['outcomes'] if o.get('available')))
    for qid in s['quantities']:
        found |= quantity_names(s, qid)
    found |= texts_names(*(item['expr'] for item in s['computed'].values()))
    found |= texts_names(*(case['when'] for label in s['labels'].values() for case in label['cases']))
    for flow in s['flows'].values():
        found |= flow_names(flow)
    found |= texts_names(*(group['capacity'] for group in s['allocation'].values()))
    for outcome in s['outcomes'].values():
        found |= outcome_names(outcome)
    for partition in s['partitions'].values():
        found |= partition_names(partition)
    for rule in rules:
        for step in rule_steps(rule):
            found |= step_names(step)
    return found


def read_events(s):
    """The events whose count or time a part of a structure reads: its rules, its checks and every part
    that a run evaluates."""
    checks = [item['expr'] for section in ('input_checks', 'state_checks') for item in s[section].values()]
    found = set()
    for name in run_reads(s, s['rules'].values(), checks):
        for suffix in (COUNT, TIME):
            if name.endswith(suffix):
                found.add(name[: -len(suffix)])
    return found


def idle_parts(s, check_owner, checks, option_states=frozenset()):
    """{section: {name: why}} of the parts of a structure that cannot act in any of its runs, each
    section in name order. `checks` are the expressions of the checks that the structure may place;
    `option_states` the named states, stocks and tallies that an option sets, which stay with their
    entity, as inputs do."""
    acting = Acting(s)
    reach = acting.reach
    dead = {
        section: {} for section in ('rules', 'flows', 'quantities', 'modes', 'computed', 'labels', 'entities')
    }
    for rid in s['rules']:
        if rid not in acting.fired:
            dead['rules'][rid] = WHY['rules']
    live = [rule for rid, rule in s['rules'].items() if rid not in dead['rules']]
    # The steps that can commit, and every step of a rule that stays: a rule that stays keeps every
    # part that its outcomes name, also an outcome whose chance is 0 in every run.
    steps = [
        outcome['do']
        for rule in live
        for k, outcome in enumerate(rule['outcomes'])
        if (rule['id'], k) in acting.committed
    ]
    named = [step for rule in live for step in rule_steps(rule)]
    # A flow whose rate is zero in every state that the runs reach moves nothing; it goes with its
    # entity, and otherwise the solver keeps it, with its ends and what its rate reads.
    still = {fid for fid, flow in s['flows'].items() if zero(flow['rate'], reach)}
    changing = set()
    for step in steps:
        changing |= step_changes(step)
    for fid, flow in s['flows'].items():
        if fid not in still:
            changing |= {flow[end] for end in ('from', 'to') if end in flow}
    changing |= {qid for qid, rate in s['rates'].items() if not zero(rate['expr'], reach)}
    always = set()  # names that the rules that stay, the groups and the flows that move read
    for rule in live:
        always |= names_in(rule['trigger']['when'])
        if rule.get('delay'):
            always |= names_in(rule['delay'])
        for item in (
            *rule.get('each', ()),
            *([rule['keep']] if rule.get('keep') else []),
            *extra_sources(rule),
        ):
            always |= names_in(item)
        for outcome in rule['outcomes']:
            if outcome['chance'] not in (None, 'else'):
                always |= names_in(outcome['chance'])
            if outcome.get('available'):
                always |= names_in(outcome['available'])
    for step in named:
        always |= step_names(step) | step_changes(step)
    # What an actor sees stays: its decisions show it.
    for entity in s['entities'].values():
        for fact in entity['sees'] or ():
            if 'expr' in fact:
                always |= names_in(fact['expr'])
    for group in s['allocation'].values():
        always |= names_in(group['capacity'])
    for fid, flow in s['flows'].items():
        if fid not in still:
            always |= names_in(flow['rate'])
    # Outputs and checks read a stock or tally that is left out as zero; they keep the named states,
    # formulas and statuses that they read.
    outputs = texts_names(*checks)
    holders = {parameter['entity'] for parameter in s['parameters'].values()}
    for outcome in s['outcomes'].values():
        outputs |= outcome_names(outcome)
    while True:
        before = sum(len(x) for x in dead.values())
        gone = set(dead['entities'])
        readers = {}  # name -> entities whose live parts read it (None: the structure as a whole)
        for name in always:
            readers.setdefault(name, set()).add(None)
        for qid, quantity in s['quantities'].items():
            if qid not in dead['quantities'] and quantity['entity'] not in gone:
                for name in quantity_names(s, qid):
                    readers.setdefault(name, set()).add(quantity['entity'])
        for section in ('computed', 'labels'):
            for item in s[section].values():
                if item['entity'] in gone:
                    continue
                texts = [item['expr']] if section == 'computed' else [case['when'] for case in item['cases']]
                for text in texts:
                    for name in names_in(text):
                        readers.setdefault(name, set()).add(item['entity'])
        for fid in sorted(still):
            flow = s['flows'][fid]
            if flow['entity'] not in gone:
                for name in flow_names(flow):
                    readers.setdefault(name, set()).add(flow['entity'])
        for pid, partition in s['partitions'].items():
            if check_owner.get(pid) not in gone:
                for name in partition_names(partition):
                    readers.setdefault(name, set()).add(check_owner.get(pid))
        for qid, quantity in s['quantities'].items():
            if qid in dead['quantities'] or qid in changing or qid in option_states:
                continue
            if zero(quantity['initial']) and not readers.get(qid):
                dead['quantities'][qid] = WHY['quantities']
        for mid in s['modes']:
            if mid in dead['modes'] or mid in changing or mid in option_states:
                continue
            if not readers.get(mid) and not readers.get(f'{mid}{ENTERED}') and mid not in outputs:
                dead['modes'][mid] = WHY['modes']
        for eid in s['entities']:
            if eid == MAIN or eid in gone or eid in holders:
                continue  # an entity that holds inputs stays with them
            members = {
                name
                for section in ('quantities', 'modes', 'computed', 'labels')
                for name, item in s[section].items()
                if item['entity'] == eid
            }
            acts = (
                any(rule['entity'] == eid for rule in live)
                or any(f['entity'] == eid for fid, f in s['flows'].items() if fid not in still)
                or members & changing
                or any(q['entity'] == eid and not zero(q['initial']) for q in s['quantities'].values())
            )
            read = any(
                readers.get(name, set()) - {eid} or (name in outputs and name not in s['quantities'])
                for name in members
            )
            if not acts and not read:
                dead['entities'][eid] = WHY['entities']
                for name in members:
                    for section in ('modes', 'quantities', 'computed', 'labels'):
                        if name in s[section]:
                            dead[section].setdefault(name, WHY['entities'])
                for fid, flow in s['flows'].items():
                    if flow['entity'] == eid:
                        dead['flows'].setdefault(fid, WHY['entities'])
        if sum(len(x) for x in dead.values()) == before:
            # In name order: the parts are found in the order of sets, which differs between processes.
            return {section: dict(sorted(parts.items())) for section, parts in dead.items()}


def remove(s, dead):
    """Leave the idle parts out of a structure, with every group member and link to them, and every
    line that names a rule that it leaves out."""
    for rid in dead['rules']:
        s['rules'].pop(rid)
    for rule in s['rules'].values():
        for outcome in rule['outcomes']:
            outcome['do']['fire'] = [target for target in outcome['do']['fire'] if target in s['rules']]
    for section in ('flows', 'quantities', 'modes'):
        for name in dead[section]:
            s[section].pop(name, None)
            if section == 'quantities':
                s['rates'].pop(name, None)
    owned = {}  # the formulas and the labels of each entity that goes
    if dead['entities']:
        for section in ('computed', 'labels'):
            for name, item in s[section].items():
                owned.setdefault((section, item['entity']), []).append(name)
    for eid in dead['entities']:
        s['entities'].pop(eid)
        s['links'].pop(eid, None)
        for section in ('computed', 'labels'):
            for name in owned.get((section, eid), ()):
                s[section].pop(name)
    for entity in s['entities'].values():
        entity['modes'] = [m for m in entity['modes'] if m in s['modes']]
    used = {f.get('allocation') for f in s['flows'].values()}
    for gid in list(s['allocation']):
        group = s['allocation'][gid]
        if gid not in used:
            s['allocation'].pop(gid)
        elif 'order' in group:
            group['order'] = [f for f in group['order'] if f in s['flows']]
    for gid in list(s['coupling']):
        group = s['coupling'][gid]
        group['flows'] = [f for f in group['flows'] if f in s['flows']]
        if not group['flows']:
            s['coupling'].pop(gid)
