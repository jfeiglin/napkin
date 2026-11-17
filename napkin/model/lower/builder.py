"""Build the flat structures that the engine runs from the semantic model of a scenario.

The builder reads only the semantic model (`model/semantic.py`), which the front end fills from a
model file (`model/language/resolve.py`): the entities with their values, statuses, checks, flows,
shares and events. It writes the engine's flat structure, under the names of the file:

- one structure for each set of options that set start states, with those start values;
- each event is a rule: its trigger, its delay, whether it triggers once, its rank in the order of
  one moment, and its outcomes, each with its chance, its flat step and its event;
- the lines of an outcome are one flat step: its changes, its moves, and the events that it fires;
- a flow whose one pair fills a tally from outside the model is the tally's rate;
- expressions are typed nodes with the structure's names (`lower/expressions.py`), and the structure
  holds the text of each;
- the parts that a set of start-state options leaves out are found by `lower/starts.py`.

Names (docs/python-api.md): an entity is its name in the file, and a copy `set.k` is `set_k` in the
structure, because names in expressions are identifiers. Values are `entity.value`, events and
their rules `entity.event`, an outcome's event `entity.event.outcome`, a flow is
`entity.flow` (`entity.flow.k` for pair k of a flow of several pairs), an allocation
`entity.allocation`, a check `Template.i` (`Template.i.entity` when the template has several
entities, `simulate.i` at the top level), and an output `entity.value` (`entity.value.output` when
the value is also a stock, tally or number state) or the name of an output of the top level.
"""

from __future__ import annotations

import copy
from collections import Counter

from ...core import expr as nodes
from ...expressions import NUMBER, ExpressionError, UnitSystem, compile_expression, evaluate, names_in
from .. import resolved
from ..ir import (
    basis_records,
    close_names,
    rule_events,
    thaw,
)
from ..semantic import (
    MAIN,
    AnalysisError,
    Assign,
    EventRef,
    Expression,
    Fire,
    Move,
    Problem,
    as_list,
    flat_entity,
    flat_key,
    path_text,
    split_key,
)
from ..structure import Parameter
from ..types import BOOL, UnitProblem, engine_number, hours, is_number, number_in, time_units, written_unit
from ..types import QUANTITY_KINDS as KINDS
from ..types import quantity as written_quantity
from ..uncertain import DistributionProblem, is_distribution, plain, point_values
from .expressions import Context, Firing, Reads, RewriteError, Typing, desugared, source_node, typed
from .starts import idle_parts, read_events, remove, settled

SECTIONS = (
    'entities',
    'parameters',
    'quantities',
    'modes',
    'computed',
    'labels',
    'rates',
    'flows',
    'allocation',
    'coupling',
    'rules',
    'events',
    'input_checks',
    'state_checks',
    'partitions',
    'outcomes',
    'links',
)


def as_number(expression, value):
    """`expression`, or a number that the builder reads in its place (the 0/1 of a bool), at its
    place."""
    return Expression(value, None, expression.where) if is_number(value) else expression


def transaction():
    """An empty flat step: its sets, its moves and the events that it fires."""
    return {'set': {}, 'transfer': [], 'fire': []}


def written(source):
    """A source of an expression as it is written: the text of a typed node; a number or a text as it
    is."""
    return nodes.text(source) if isinstance(source, nodes.Node) else source


# What the builder says of a list that is too deep for a flat structure.
TOO_DEEP = (
    f'the expression has more than {nodes.DEEPEST} operations one inside the other: a flat structure '
    'writes a list member by member, so a sum over many instances is too deep for it. The hybrid core '
    'takes such a list as one node when a table makes the instances (napkin.model.hybrid.compile)'
)


def flat_node(source, path, unit=None):
    """The node that a structure holds of an expression (a typed node, a number or a text): its
    engine's form (`expressions.desugared`: `count`, `since` and `elapsed`), with a bare number in a
    typed field as a quantity of its unit. A node that is deeper than the readers of an expression
    go (`core.expr.DEEPEST`) is refused at its place: the builder makes one from a list of many
    members."""
    if isinstance(source, nodes.Node) and nodes.height(source) > nodes.DEEPEST:
        # Before any reader goes down the node: its height is found with no call for each level.
        raise RewriteError(path_text(path), TOO_DEEP, 'expression')
    if unit is not None:
        # Whether it is a bare number is a question of how it is written.
        was = written(source)
        now = typed(was, unit)
        source = source if now is was else now
    return desugared(source_node(source, path_text(path)), path_text(path))


class Builder:
    """The flat structures of one scenario, from its semantic model."""

    def __init__(self, scenario, run_table, library, listed=False):
        self.scenario = scenario
        self.run_table = run_table
        # Whether a reduction over a list is written as one node (`sum(a, b)`), as the hybrid core
        # reads it (`model/hybrid.py`), and not as the chain of the flat structure (`a + b`).
        self.listed = listed
        self.time_units = time_units(library['units'])
        self.units = UnitSystem(library['units'])
        self.link_reads = {}
        self.inlining = set()  # the inline fields being read, (entity, path): one that reads itself fails
        # The arguments of each distribution that read other values, compiled with the structure's
        # names: {parameter: {its text: {argument: expression}}}.
        self.arguments = {}
        self.entity_named = {entity.name: entity for entity in scenario.entities}
        self.names()

    def fail(self, path, message):
        raise AnalysisError(path, message)

    def names(self):
        """The structure's names of the scenario's entities and values: each entity's host, and the
        kind of each value (`field_kind`), with the name of its input, stock, tally, number state or
        output; the bool inputs and bool states, which the engine reads as 0/1 numbers; and the named
        inputs, each with its values."""
        self.entity_class = {entity.name: entity.template for entity in self.scenario.entities}
        self.hosts = {e: flat_entity(e) for e in self.entity_class}
        self.copy_number = {e.name: e.copy for e in self.scenario.entities if e.copy is not None}
        self.field_kind, self.parameter_of, self.quantity_of, self.outcome_of = {}, {}, {}, {}
        typed = {}
        for entity in self.scenario.entities:
            for value in entity.values:
                key = f'{entity.name}.{value.name}'
                kind = field_kind(value)
                self.field_kind[key] = kind
                typed[key] = value.type
                if kind == 'parameter':
                    self.parameter_of[key] = flat_key(key)
                elif kind == 'quantity':
                    self.quantity_of[key] = flat_key(key)
                if value.output is not None:
                    # A stock, tally or number state that is also an output holds its value as
                    # `entity.field`, and its output as `entity.field.output`.
                    held = value.kind in KINDS
                    self.outcome_of[key] = f'{flat_key(key)}.output' if held else flat_key(key)
        for output in self.scenario.outputs:
            self.outcome_of[output.name] = output.name
        self.parameter_ids = set(self.parameter_of.values())
        self.flags = {pid for key, pid in self.parameter_of.items() if typed[key] == 'bool'}
        self.bool_states = {qid for key, qid in self.quantity_of.items() if typed[key] == 'bool'}
        self.choices = {
            pid: tuple(thaw(typed[key]))
            for key, pid in self.parameter_of.items()
            if isinstance(typed[key], tuple)
        }

    def rule_id(self, key):
        """The rule of an event (`entity.event`)."""
        return flat_key(key)

    def event_name(self, kind, key, ending):
        """The event of the structure that an event of the file names (`event_target`): the event, or
        one of its outcomes."""
        rid = self.rule_id(key)
        return rid if ending is None else f'{rid}.{ending}'

    def event_owner(self, event):
        """The entity whose event an event of the structure is."""
        return event.split('.')[0]

    def value(self, entity, member, ctx, path):
        """What member `member` of `entity` reads, or the output `member` of the main when `entity` is
        None."""
        if entity is None:
            return ('outcome', self.outcome_of[member])
        if member == 'copy':
            # A copy's number, written into each copy's expressions.
            if entity not in self.copy_number:
                self.fail(path, f'{entity} is not one of a set of copies, so it has no number (copy)')
            return ('number', self.copy_number[entity])
        return self.value_of(entity, member, ctx, path)

    def value_of(self, entity, member, ctx, path):
        key = symbol = f'{entity}.{member}'
        kind = self.field_kind.get(key)
        if kind == 'parameter':
            return ('parameter', self.parameter_of[key])
        if kind == 'quantity':
            return ('quantity', self.quantity_of[key])
        if kind in ('mode', 'computed'):
            return (kind, flat_key(key))
        if kind == 'inline':
            return ('inline', entity, self.entity_named[entity].value(member).formula)
        if kind == 'output':
            return ('outcome', self.outcome_of[key])
        if kind in ('cosmetic', 'text'):
            self.fail(
                path,
                f'{symbol} is a text: it names a unit or fills a doc, and the calculation never reads it',
            )
        self.fail(path, f'{symbol} is not a value')

    def expression_text(self, expression, ctx, reads):
        """An expression of the semantic model with the structure's names (`Typing`), as a typed
        node: a number stays a number."""
        written = expression.written
        if isinstance(written, (int, float)) and not isinstance(written, bool):
            return written
        return self.tree_of(expression, ctx, reads)

    def tree_of(self, expression, ctx, reads):
        """The typed node of an expression of the semantic model, with the structure's names
        (`Typing`)."""
        return Typing(self, ctx, reads, expression.where).visit(expression.node)

    def unit_of(self, value, entity):
        """The library unit of a value or an output (`unit_in`)."""
        return self.unit_in(value.type, value.unit_where, entity, value.name)

    def unit_in(self, written, holder, entity, name):
        """The library unit of a written type (`types.written_unit`): the unit of input `name` of `entity`
        as the run table reads it, else the written type (a bound's unit has no `name`). Braces name a
        text value of the entity, so that one template counts prescriptions in one entity and claims in
        another: `{item}/h`. `holder` is where a problem of the unit is reported."""
        item = self.run_table.data['inputs'].get(f'{entity}.{name}') if entity and name else None
        if item is not None and item['unit'] is not None:
            return item['unit']
        unit = thaw(written)
        if unit == 'bool':
            return 'fraction'  # a bool state is the engine's 0/1 quantity
        if isinstance(unit, str):
            if '{' in unit and entity is None:
                self.fail(holder, 'a unit with braces belongs to a value of an entity')

            def text(member):
                if self.field_kind.get(f'{entity}.{member}') not in ('text', 'cosmetic'):
                    self.fail(holder, f'{member} is not a text value')
                return str(thaw(self.entity_named[entity].value(member).value))

            try:
                unit = written_unit(unit, text)
            except ValueError as exc:
                self.fail(holder, str(exc))
        # A unit is declared, or composed of declared units (`expressions.UnitRegistry`).
        if not isinstance(unit, str) or unit not in self.units:
            close = close_names(unit, self.units.suggestions(unit)) if isinstance(unit, str) else ''
            self.fail(holder, f'unknown unit {thaw(written)!r}{close}')
        return unit

    def hours(self, value, path):
        """The hours of a time of the file, as the reader reads them (`read.hours`)."""
        found = hours(value, self.time_units)
        if found is None:
            self.fail(path, f'a time is written with its unit of time, such as 24 h, not {value!r}')
        return found

    def parameter(self, key, field):
        """The input or fixed value of a value (`field`, of the semantic model), in the engine's form: a
        bool value is the 0/1 number of a binary control, and a named value the code of a choice, 0 to
        n - 1. The value of a distribution is None here: the builder sets its central value once every
        input is known."""
        flag = field.type == 'bool'
        e, _ = split_key(key)
        names = self.choices.get(self.parameter_of[key])
        unit = 'fraction' if names else self.unit_of(field, e)
        # The run table reads each number with its unit, in the unit of the input (`model/runs.py`).
        item = self.run_table.data['inputs'][key]
        value = item['value']
        unread = self.table_problem(item['path'], None)
        for where, text, arguments in field.arguments:
            self.distribution_arguments(key, text, arguments, where)
        if is_distribution(value):
            value = None
        elif flag and isinstance(value, bool):
            value = engine_number(value)
        elif names and value in names:
            value = names.index(value)
        if unread is not None or (
            value is not None and (isinstance(value, bool) or not isinstance(value, (int, float)))
        ):
            self.fail(field.value_at, unread or 'an input or fixed value is a number')
        if field.records is None:
            self.fail(field.where, 'an input or a fixed value has its record')
        # Each option value carries its own support, and the input keeps the support of its own value
        # and of every value that an option sets.
        settings = [thaw(setting.written) for setting in field.settings]
        parameter = {
            'label': field.label or key,
            'value': value,
            'unit': unit,
            'basis': joined(thaw(field.records), *(s.get('basis') for s in settings if isinstance(s, dict))),
        }
        r = written_range(field.range)
        limits = item['range']
        if limits is not None:
            for (edge, number), where in zip(zip(('min', 'max'), limits), field.edges_at):
                if number is not None and not isinstance(number, (int, float)):
                    self.fail(
                        where, self.table_problem(path_text(where), f'the {edge} of a range is a number')
                    )
                r = {**r, edge: number} if number is not None else r
        if flag and field.kind == 'input':
            r = {**r, 'min': 0, 'max': 1}
        if names and field.kind == 'input':
            r = {**r, 'min': 0, 'max': len(names) - 1}
        if field.kind == 'input':
            if 'min' not in r or 'max' not in r:
                self.fail(field.range_at, 'an input has its bounds: min: and max:')
            parameter['adjust'] = {'mode': 'range', 'min': r['min'], 'max': r['max']}
        else:
            parameter['adjust'] = {'mode': 'locked'}
        # A range's support: its range note (the range rationale) and the records that support its
        # limits (`adjust.basis`).
        support = [] if r.get('basis') is None else as_list(r['basis'])
        note = next((x for x in support if isinstance(x, dict) and 'status' in x), None)
        records = [x for x in support if x is not note]
        if records:
            parameter['adjust']['basis'] = joined(*records)
        if note:
            # Every note has one shape: `status` says who set the limits, the scenario
            # (`selected_sensitivity_domain`) or the mechanism and its sources; `rationale` says what the
            # range is for; and each limit keeps the note's own text. The range's records support the
            # limits.
            rationale = {
                'mode': parameter['adjust']['mode'],
                'status': 'declared_model_domain'
                if note['status'] == 'declared'
                else 'selected_sensitivity_domain',
                'review': 'unreviewed',
                **({'rationale': note['rationale']} if 'rationale' in note else {}),
            }
            for edge in ('min', 'max'):
                if edge in r:
                    rationale[edge] = {'value': r[edge]} | (
                        {'explanation': note[edge]} if note.get(edge) else {}
                    )
            parameter['metadata'] = {'review_status': 'unreviewed', 'range_rationale': rationale}
        if flag:
            parameter.setdefault('metadata', {})['control'] = 'binary'
        if names:
            parameter.setdefault('metadata', {}).update(control='choice', values=list(names))
        return parameter

    def distribution_arguments(self, key, text, arguments, path):
        """Compile the arguments of a distribution (its `text`) that read other values, each an
        expression read in the entity of its input: each reads inputs and fixed values only, which exist
        before the run."""
        e = split_key(key)[0]
        compiled = {}
        for name, source in arguments:
            expression = self.expression_text(source, Context(e), Reads(self, e))
            for symbol in names_in(expression):
                if symbol not in self.parameter_ids:
                    self.fail(
                        path,
                        f'{text}: {name} reads {symbol}; a distribution reads inputs and '
                        'fixed values, which exist before the run',
                    )
            compiled[name] = expression
        if compiled:
            self.arguments.setdefault(self.parameter_of[key], {})[text] = compiled

    def table_problem(self, where, default):
        """The message of the run table's problem with the unit of the value written at `where`, else
        `default`: the table holds such a value as it is written."""
        for problem in self.run_table.data['problems']:
            if problem['path'] == where and problem['code'] in ('unit', 'distribution'):
                return problem['message']
        return default

    def profile_settings(self, option):
        """[(entity, setting)] of the settings of one option, in every entity that has it."""
        return [
            (entity.name, setting)
            for entity in self.scenario.entities
            for setting in entity.settings
            if setting.profile == option
        ]

    def option_values(self, option):
        """{(entity, field): (value, basis)} that one option sets, in every entity that has it."""
        values = {}
        for e, setting in self.profile_settings(option):
            value = thaw(setting.value)
            if self.parameter_of.get(f'{e}.{setting.target}') in self.flags and isinstance(value, bool):
                value = engine_number(value)
            values[(e, setting.target)] = (value, thaw(setting.records))
        return values

    # ---- names -------------------------------------------------------------------------------

    def text_of(self, expression, host, outcome=False):
        """(typed node, reads) of an expression of the semantic model with the structure's names
        (`Analysis.expression_text`): a number stays a number. Reads of other entities' members are
        links of `host`."""
        local = Reads(self, host)
        text = self.expression_text(expression, Context(None, outcome=outcome), local)
        self.note(host, local.reads)
        return text, local.reads

    def note(self, host, targets):
        if host is not None:
            self.reads.setdefault(host, {}).update(dict.fromkeys(sorted(targets)))

    def flat(self, source, path, unit=None):
        """The node that a structure holds of an expression (`flat_node`)."""
        return flat_node(source, path, unit)

    def resolved(self, basis):
        """A copy of a basis resolved before analysis and entity expansion."""
        return copy.deepcopy(basis)

    # ---- the structure -------------------------------------------------------------------------

    def distribution_problems(self):
        """The run table's problems of the distributions of the file: one that its input cannot read
        (`distribution`), and one whose support leaves the input's range (`bounds`)."""
        places = {
            path
            for item in self.run_table.data['inputs'].values()
            for path, value in (
                (item['path'], item['value']),
                *((f'{s["path"]}/value', s['value']) for s in item['options'].values()),
            )
            if is_distribution(value)
        }
        return [
            thaw(problem)
            for problem in self.run_table.data['problems']
            if problem['code'] == 'distribution'
            or (problem['path'] in places and problem['code'] == 'bounds')
        ]

    def central_defaults(self, parameters):
        """The value of each input whose default is a distribution: its central value, with the
        defaults of the inputs that it reads (`model/uncertain.py`). Each argument that reads other
        values has the unit of its parameter, or is a plain number."""
        symbols = {pid: self.units.parse_unit(p['unit']) for pid, p in parameters.items()}
        by_parameter = {pid: key for key, pid in self.parameter_of.items()}
        for pid, compiled in self.arguments.items():
            item = self.run_table.data['inputs'][by_parameter[pid]]
            unit = self.units.parse_unit(parameters[pid]['unit']).canonical()
            for text, sources in compiled.items():
                family = next(
                    v['family']
                    for v in (item['value'], *(s['value'] for s in item['options'].values()))
                    if is_distribution(v) and v['text'] == text
                )
                for name, source in sources.items():
                    try:
                        compile_expression(
                            source, symbols, self.units, NUMBER if plain(name, family) else unit
                        )
                    except ExpressionError as exc:
                        self.fail(tuple(item['path'].split('/')), f'{text}: {name}: {exc}')
        defaults = {
            pid: self.run_table.data['inputs'][key]['value'] for key, pid in self.parameter_of.items()
        }
        try:
            # The functions of a distribution read the record of an input (`structure.Parameter`).
            records = {pid: Parameter.of(item, f'parameters/{pid}') for pid, item in parameters.items()}
            points = point_values(defaults, self.arguments, records, self.units)
        except DistributionProblem as exc:
            where = self.run_table.data['inputs'][by_parameter[exc.name]]['path'] if exc.name else 'simulate'
            self.fail(tuple(where.split('/')), str(exc))
        for pid, parameter in parameters.items():
            if parameter['value'] is None:
                value = points[pid]
                names = (parameter.get('metadata') or {}).get('values')
                parameter['value'] = (
                    engine_number(value)
                    if isinstance(value, bool)
                    else names.index(value)
                    if names
                    else value
                )

    def own_values(self, e, value, unit):
        """The default of an input and the value of each option that sets it, each with its own basis:
        a value that cites a datum must equal that datum."""
        flag = value.type == BOOL
        # The numbers as the run table reads them, in the input's unit.
        item = self.run_table.data['inputs'][f'{e}.{value.name}']
        if is_distribution(item['value']) or any(
            is_distribution(s['value']) for s in item['options'].values()
        ):
            # A distribution reports no single value: its basis supports its spread, and no datum of a
            # source can equal it.
            for record in basis_records(thaw(value.records)):
                for link in (record.get('links') or []) if isinstance(record, dict) else []:
                    if isinstance(link, dict) and link.get('datum'):
                        self.fail(
                            value.records_at,
                            'a distribution reports no single value: cite the source of its spread, not the '
                            f'datum {link["datum"]!r} of {link.get("claim")}',
                        )
            return []
        values = [{'value': item['value'], 'basis': thaw(value.records), 'path': value.where}]
        for setting in value.settings:
            written = thaw(setting.written)
            if isinstance(written, dict) and 'basis' in written:
                values.append(
                    {
                        'value': item['options'][setting.profile]['value'],
                        'basis': written['basis'],
                        'path': setting.where,
                    }
                )
        return [
            {
                'value': engine_number(item['value'])
                if flag and isinstance(item['value'], bool)
                else item['value'],
                'unit': unit,
                'basis': self.resolved(item['basis']),
                'path': path_text(item['path']),
            }
            for item in values
        ]

    def build(self):
        """The structure that every set of start states shares, before its start values."""
        self.reads = {}
        self.written_modes = set()
        self.firing = (
            None  # the event whose draws and delayed values `Typing` collects (`expressions.Firing`)
        )
        self.link_reads = {}
        self.qunits = {}
        self.flow_members = {}
        self.check_owner = {}
        self.outcome_where = {}
        self.left_out = {}
        self.whole = {}
        self.datum_values = []
        for e in self.entity_class:
            for value in self.entity_named[e].values:
                if self.field_kind[f'{e}.{value.name}'] == 'quantity':
                    self.qunits[self.quantity_of[f'{e}.{value.name}']] = self.unit_of(value, e)
        s = {section: {} for section in SECTIONS}
        for e in self.entity_class:
            for value in self.entity_named[e].values:
                key = f'{e}.{value.name}'
                if self.field_kind[key] == 'parameter':
                    parameter = self.parameter(key, value)
                    parameter['basis'] = self.resolved(parameter['basis'])
                    if 'basis' in parameter['adjust']:
                        parameter['adjust']['basis'] = self.resolved(parameter['adjust']['basis'])
                    s['parameters'][self.parameter_of[key]] = {
                        **parameter,
                        'entity': self.hosts[e],
                        'path': path_text(value.where),
                    }
                    self.datum_values += self.own_values(e, value, parameter['unit'])
        self.central_defaults(s['parameters'])
        # The solver keeps the order of the structure's values and flows, and a residue at zero can
        # depend on it. The entities go by name, each with its stocks, states and rules in the order
        # its class declares them; the flows go by name.
        hosts = {self.hosts[e]: e for e in self.entity_class}
        for host in sorted(hosts):
            self.entity_part(s, hosts[host])
        s['flows'] = dict(sorted(s['flows'].items()))
        self.rationing_part(s)
        self.fire_cycles(s)
        self.partitions, self.check_items = self.check_part(s)
        self.outcome_texts = self.outcome_part(s)
        self.time = self.time_part()
        self.initiation = self.initiation_part()
        return s

    def entity_part(self, s, e):
        entity = self.entity_named[e]
        host = self.hosts[e]
        basis = thaw(entity.records)
        s['entities'][host] = {
            'label': entity.title,
            'kind': thaw(entity.role) if entity.role is not None else 'environment',
            'metadata': {},
            'basis': self.resolved(basis) if basis is not None else None,
            'origin': entity.entry,
            'copy': entity.copy,
            'modes': sorted(
                f'{host}.{value.name}'
                for value in entity.values
                if self.field_kind[f'{e}.{value.name}'] == 'mode'
            ),
            'health': f'{host}.health' if entity.status is not None else None,
            # What an actor sees, or None for a thing of the world.
            'sees': [self.fact_part(e, fact) for fact in entity.sees] if entity.sees is not None else None,
        }
        for value in entity.values:
            kind = self.field_kind[f'{e}.{value.name}']
            if kind == 'quantity':
                self.quantity_part(s, e, value)
            elif kind == 'mode':
                values = thaw(value.type)
                if thaw(value.value) not in values:
                    self.fail(value.value_at, f'the start value is one of {values}')
                mode = {'values': values, 'initial': thaw(value.value)}
                if value.text is not None:
                    mode['label'] = value.text
                if value.records is not None:
                    mode['basis'] = self.resolved(thaw(value.records))
                s['modes'][f'{host}.{value.name}'] = {**mode, 'entity': host, 'path': path_text(value.where)}
        for value in entity.values:
            if self.field_kind[f'{e}.{value.name}'] == 'computed':
                if value.records is None:
                    self.fail(value.where, 'a formula that the model reads has its record')
                text, _ = self.text_of(value.formula, host)
                computed = {
                    'expr': self.flat(text, value.formula.where),
                    'unit': self.unit_of(value, e),
                    'basis': self.resolved(thaw(value.records)),
                }
                if value.text is not None:
                    computed['label'] = value.text
                s['computed'][f'{host}.{value.name}'] = {
                    **computed,
                    'entity': host,
                    'path': path_text(value.where),
                }
        if entity.status is not None:
            self.status_part(s, e)
        for flow in entity.flows:
            self.flow_part(s, e, flow)
        for event in entity.events:
            self.event_part(s, e, event)

    def quantity_part(self, s, e, value):
        key = f'{e}.{value.name}'
        qid = self.quantity_of[key]
        host = self.hosts[e]
        path = value.where
        kind = KINDS[value.kind]
        if value.records is None:
            self.fail(path, 'a stock, a tally or a number state has its record')
        unit = self.unit_of(value, e)
        if value.initial is None:
            self.fail(path, 'a stock, tally or number state has a start value')
        flag = value.type == BOOL
        start = self.start_value(thaw(value.initial.written), unit, flag, value.initial.where)
        initial, _ = self.text_of(as_number(value.initial, start), host)
        quantity = {
            'kind': kind,
            'unit': unit,
            'initial': self.flat(initial, value.initial.where, unit),
            'basis': self.resolved(thaw(value.records)),
        }
        if flag:
            # A bool state is the engine's 0/1 quantity, which reads Yes or No.
            quantity.update(min=0, max=1, binary=True)
        if value.minimum is not None:
            quantity['min'] = self.bound(value.minimum, unit, e)
        elif kind != 'variable':
            quantity['min'] = 0
        if value.maximum is not None:
            quantity['max'] = self.bound(value.maximum, unit, e)
        for name, bound in (('min', value.minimum), ('max', value.maximum)):
            if isinstance(quantity.get(name), str):
                text, _ = self.text_of(bound.expression, host)
                quantity[name] = self.flat(text, bound.expression.where)
        if value.size is not None:
            quantity['size'] = self.bound(value.size, unit, e)
        if value.text is not None:
            quantity['label'] = value.label
        s['quantities'][qid] = {**quantity, 'entity': host, 'path': path_text(path)}

    def start_value(self, value, unit, flag, path):
        """A start value of a stock, tally or state as an expression: a bool state is true (1) or false
        (0), and a bare number is 0 or a number of a dimensionless unit; `100 people` is a quantity."""
        if flag:
            if not isinstance(value, bool):
                self.fail(path, f'a bool state starts true or false, not {value!r}')
            return engine_number(value)
        if is_number(value) and value != 0 and self.units.parse_unit(unit).dimensions:
            self.fail(path, f'write the unit of the number: {value} {unit}')
        return value

    def bound(self, bound, unit, e):
        """A minimum, maximum or size: a number in the quantity's unit when the file writes a number
        (`100 people`, `0`), else the expression that the file writes."""
        written = thaw(bound.expression.written)
        if is_number(written) or written_quantity(written) is not None:
            try:
                return number_in(
                    written,
                    unit,
                    self.units,
                    lambda text: self.unit_in(text, bound.unit_where, e, None),
                )
            except UnitProblem as exc:
                self.fail(bound.expression.where, str(exc))
        return written

    def status_part(self, s, e):
        """The status of an entity: its cases in order, the last when no other applies. It rests on its
        class's basis and on each case's, in that order."""
        entity = self.entity_named[e]
        host = self.hosts[e]
        status = entity.status
        own = thaw(status.records) if status.records is not None else thaw(entity.records)
        basis = joined(own, *(thaw(case.records) for case in status.cases))
        if not basis:
            self.fail(status.where, 'a status rests on the records of its entity or of its lines')
        cases = []
        for case in status.cases[:-1]:
            text, _ = self.text_of(case.condition, host)
            cases.append(
                {
                    'when': self.flat(text, case.condition.where),
                    'value': thaw(case.value),
                    'text': self.filled(case.text),
                    # The case of the file: the diagnostics of its condition name `shows/i/when`.
                    'path': path_text(case.where),
                }
            )
        last = status.cases[-1]
        s['labels'][f'{host}.health'] = {
            'cases': cases,
            'default': {'value': thaw(last.value), 'text': self.filled(last.text)},
            'basis': self.resolved(basis),
            'label': None,
            'entity': host,
            'path': path_text(status.where),
        }

    def filled(self, words):
        """The text of `words`, or its problem."""
        if words.problem is not None:
            self.fail(words.where, words.problem)
        return words.text

    def flow_part(self, s, e, flow):
        """One flow for each pair it moves, all of the entity that declares it: `entity.flow`, or
        `entity.flow.k` for pair k of a flow of several pairs, which move together."""
        host = self.hosts[e]
        # The stocks or tallies that each pair moves material between: `from` and `to`, without an end
        # outside the model.
        plan = []
        for pair in flow.pairs:
            ends = {}
            for end, ref in pair.ends:
                if isinstance(ref, Problem):
                    self.fail(pair.where, ref.message)
                if self.field_kind.get(f'{ref.entity}.{ref.member}') != 'quantity':
                    self.fail(pair.where, f'{ref.written} is not a stock or tally')
                ends[end] = self.quantity_of[f'{ref.entity}.{ref.member}']
            plan.append(ends)
        if len(plan) == 1 and list(plan[0]) == ['to']:
            target = next(ref for end, ref in flow.pairs[0].ends if end == 'to')
            if self.entity_named[target.entity].value(target.member).kind == 'tally':
                self.rate_part(s, e, flow, plan[0]['to'])
                return
        names = (
            [f'{host}.{flow.name}']
            if len(plan) == 1
            else [f'{host}.{flow.name}.{i}' for i in range(len(plan))]
        )
        for i, (pair, ends) in enumerate(zip(flow.pairs, plan)):
            local = Reads(self, host)
            # A pair takes the flow's rate or gives its own; `while` applies to every pair.
            rate = self.tree_of(pair.rate if pair.rate is not None else flow.rate, Context(e), local)
            if flow.condition is not None:
                test = self.tree_of(flow.condition, Context(e), local)
                rate = nodes.if_else(test, rate, nodes.const(0))
            self.note(host, local.reads)
            where = pair.where if pair.own else flow.where
            record = {
                'rate': self.flat(rate, where),
                'basis': self.resolved(thaw(pair.records if pair.records is not None else flow.records)),
            }
            for end, qid in ends.items():
                record[end] = qid
                if split_key(qid)[0] != host:
                    self.note(host, [qid])
            if flow.text is not None and i == 0:
                record['label'] = flow.text
            s['flows'][names[i]] = {**record, 'entity': host, 'path': path_text(where)}
        self.flow_members[f'{e}.{flow.name}'] = [(names[i], ends.get('from')) for i, ends in enumerate(plan)]
        if len(plan) > 1:
            # The pairs move together, by one fraction.
            s['coupling'][f'{host}.{flow.name}'] = {
                'flows': names,
                'basis': self.resolved(thaw(flow.together.value)),
            }

    def rate_part(self, s, e, flow, qid):
        """A flow that fills a tally from outside the model is the tally's rate: the sum of the rates
        of every such flow, each while its condition holds."""
        host = self.hosts[e]
        local = Reads(self, host)
        pair = flow.pairs[0]
        rate = self.tree_of(pair.rate if pair.rate is not None else flow.rate, Context(e), local)
        if flow.condition is not None:
            test = self.tree_of(flow.condition, Context(e), local)
            rate = nodes.if_else(test, rate, nodes.const(0))
        self.note(host, local.reads)
        if split_key(qid)[0] != host:
            self.note(host, [qid])
        text = self.flat(rate, flow.where)
        basis = self.resolved(thaw(pair.records if pair.records is not None else flow.records))
        found = s['rates'].get(qid)
        # The flows that the rate holds, which the pages draw as flows.
        name = f'{host}.{flow.name}'
        if found is None:
            s['rates'][qid] = {'expr': text, 'basis': basis, 'path': path_text(flow.where), 'flows': [name]}
        else:
            found['expr'] = nodes.binary('add', found['expr'], text)
            found['basis'] = joined(found['basis'], basis)
            found['flows'].append(name)

    def rationing_part(self, s):
        """An allocation group for each rationing entry, over every flow (every pair) that draws on its
        stock, served in the listed order or in proportion, up to its limit."""
        fed_by = {}  # the flows that draw on each quantity, in the order of the flows
        for pairs in self.flow_members.values():
            for name, source in pairs:
                fed_by.setdefault(source, []).append(name)
        for e in self.entity_class:
            for allocation in self.entity_named[e].allocations:
                path = allocation.where
                stock = allocation.stock
                if isinstance(stock, Problem):
                    self.fail(path, stock.message)
                ref = stock.written
                key = f'{stock.entity}.{stock.member}'
                if (
                    self.field_kind.get(key) != 'quantity'
                    or self.entity_named[stock.entity].value(stock.member).kind != 'stock'
                ):
                    self.fail(allocation.stock_where, f'{ref} is not a stock')
                qid = self.quantity_of[key]
                members = list(fed_by.get(qid, ()))
                # One flow is enough: a list of a template's instances can have one member, and the limit
                # then caps that flow.
                if not members:
                    self.fail(
                        allocation.stock_where,
                        f'a rationing entry shares a stock that flows draw on; no flow draws on {ref}',
                    )
                capacity, _ = self.text_of(allocation.limit, None)
                group = {
                    'policy': 'proportional' if allocation.serve is None else 'priority',
                    'capacity': self.flat(capacity, allocation.limit.where),
                    # The rationing entry: the diagnostics of the group name it and its line.
                    'path': path_text(path),
                }
                if allocation.serve is not None:
                    order = []
                    for flow_ref, flow_owner, flow_name, where in allocation.serve:
                        if isinstance(flow_owner, Problem):
                            self.fail(where, flow_owner.message)
                        drawing = [
                            name
                            for name, source in self.flow_members.get(f'{flow_owner}.{flow_name}', [])
                            if source == qid
                        ]
                        if len(drawing) != 1:
                            self.fail(where, f'{flow_ref} is not a flow that draws on {ref}')
                        order.append(drawing[0])
                    if sorted(order) != sorted(members):
                        self.fail(
                            allocation.serve_where,
                            f'serve lists each flow that draws on {ref} once: {sorted(members)}',
                        )
                    group['order'] = order
                group['basis'] = self.resolved(thaw(allocation.records))
                name = f'{self.hosts[e]}.{allocation.name}'
                for member_id in members:
                    if 'allocation' in s['flows'][member_id]:
                        self.fail(path, f'{ref} has one rationing entry')
                    s['flows'][member_id]['allocation'] = name
                s['allocation'][name] = group

    # ---- events ------------------------------------------------------------------------------------

    def fact_part(self, e, fact):
        """A fact that actor `e` sees, with the structure's names: an event, or a value as an expression,
        with how a decision shows it (`kind`): a named state's value, a named input's, a yes/no, or a
        number in its unit."""
        if isinstance(fact, EventRef):
            return {'name': fact.written, 'event': self.event_name(fact.kind, fact.key, fact.ending)}
        where = self.entity_named[e].where
        ref = self.value(fact.entity, fact.member, Context(e), where)
        found = {'name': fact.written}
        if ref[0] == 'parameter' and ref[1] in self.choices:
            return found | {'expr': nodes.ref(ref[1]), 'kind': 'choice', 'values': list(self.choices[ref[1]])}
        typed_fact = Typing(self, Context(e), Reads(self, None), where).visit(resolved.of_tree(fact))
        found['expr'] = self.flat(typed_fact, where)
        if ref[0] == 'mode':
            return found | {'kind': 'state'}
        if (ref[0] == 'parameter' and ref[1] in self.flags) or (
            ref[0] == 'quantity' and ref[1] in self.bool_states
        ):
            return found | {'kind': 'bool'}
        value = self.entity_named[fact.entity].value(fact.member)
        unit = self.unit_of(value, fact.entity) if value is not None and value.type is not None else None
        return found | {'kind': 'number', 'unit': unit}

    def raise_fault(self, fault):
        """Raise a problem that the front end found, at the place where the builder reports it."""
        self.fail(fault.where, fault.message)

    def event_part(self, s, e, event):
        """An event as the engine's rule: its trigger (`when`, or `False` for an event that only a line
        that names it fires), its delay, its rank and its outcomes. Each outcome has its chance, its
        flat step and its event, `entity.event.outcome`; the rule's own event is the trigger."""
        host = self.hosts[e]
        path = event.where
        rid = self.rule_id(f'{e}.{event.name}')
        if event.doc_problem is not None:
            self.raise_fault(event.doc_problem)
        if event.records is None and (event.when is not None or event.after is not None):
            self.fail(path, 'an event has its records on its line: event name when C:  @record')
        local = Reads(self, host)
        # An event with no condition fires when a line names it, or, with a window, once in each window.
        when = 'True' if event.each else 'False'
        if event.when is not None:
            when = self.tree_of(event.when, Context(e), local)
        each = [self.flat(self.tree_of(item, Context(e), local), item.where) for item in event.each]
        keep = None
        if event.keep is not None:
            keep = self.flat(self.tree_of(event.keep, Context(e), local), event.keep.where)
        delay = None
        # A distribution written in the event is drawn, and `delayed()` read, as it triggers (its delay)
        # or as it fires (its chances, conditions and lines).
        firing = self.firing = Firing(rid)
        try:
            if event.after is not None:
                firing.stage = 'trigger'
                text, reads = self.text_of(event.after, host)
                local.reads |= set(reads)
                delay = self.flat(text, event.after.where, 'h')
            firing.stage = 'fire'
            self.note(host, local.reads)
            records = thaw(event.records)
            self.link_reads.setdefault(host, []).append((set(local.reads), records, path))
            outcomes = [self.branch_part(e, rid, event, outcome) for outcome in event.outcomes]
        finally:
            self.firing = None
        if not outcomes:
            # A milestone: one outcome that changes nothing.
            outcomes = [
                {
                    'name': 'done',
                    'chance': None,
                    'available': None,
                    'label': None,
                    'basis': self.resolved(records) if records is not None else None,
                    'path': path_text(path),
                    'do': transaction(),
                    'emits': [f'{rid}.done'],
                }
            ]
        # The event's text with its braces filled, as its cards read it.
        label = self.filled(event.label) if event.label is not None else None
        record = {
            'id': rid,
            'entity': host,
            'label': label,
            'basis': self.resolved(records) if records is not None else None,
            'metadata': {},
            'path': path_text(path),
            'rank': list(event.rank),
            'once': bool(event.once),
            'named': event.when is None and not event.each,
            'trigger': {'when': self.flat(when, event.when_where)},
            'delay': delay,
            'outcomes': outcomes,
            'emits': [rid],
        }
        if event.when is not None:
            record['trigger']['path'] = path_text(event.when_where)
        if event.after is not None:
            record['delay_path'] = path_text(event.after.where)
        if each:
            record['each'] = each
            record['each_path'] = path_text(event.each[0].where)
        if keep is not None:
            record['keep'] = keep
            record['keep_path'] = path_text(event.keep.where)
        if event.role is not None:
            record['role'] = thaw(event.role)
        if firing.items:
            record['extras'] = []
            for collected in firing.items:
                item = dict(collected)
                for key in ('expr', 'delay'):
                    if key in item:
                        item[key] = self.flat(item[key], path)
                if 'args' in item:
                    item['args'] = {name: self.flat(text, path) for name, text in item['args'].items()}
                record['extras'].append(item)
        if event.choice:
            record['choice'] = True  # a person or an agent can choose its outcome in a run
        s['rules'][rid] = record

    def branch_part(self, e, rid, event, outcome):
        """One outcome of an event: its chance (an expression, None for 1, or `else`), its step and its
        event."""
        host = self.hosts[e]
        chance = outcome.chance
        if chance is not None and chance != 'else':
            local = Reads(self, host)
            tree = self.tree_of(chance, Context(e), local)
            self.note(host, local.reads)
            chance = self.flat(tree, chance.where)
        available = outcome.available
        if available is not None:
            local = Reads(self, host)
            tree = self.tree_of(available, Context(e), local)
            self.note(host, local.reads)
            available = self.flat(tree, available.where)
        records = thaw(outcome.records) if outcome.records is not None else thaw(event.records)
        found = {
            'name': outcome.name,
            'chance': chance,
            'available': available,
            'label': self.filled(outcome.label) if outcome.label is not None else None,
            'basis': self.resolved(records) if records is not None else None,
            'path': path_text(outcome.where),
            'do': self.steps(e, outcome.lines),
            'emits': [f'{rid}.{outcome.name}'],
        }
        if outcome.role is not None:
            found['role'] = thaw(outcome.role)
        return found

    # ---- the lines of an outcome ---------------------------------------------------------------------

    def steps(self, e, lines):
        """The flat step of the lines of an outcome, read in entity `e`: the values that it sets, of
        any entity, its moves, and the events that it fires, in order."""
        host = self.hosts[e]
        step = transaction()
        for line in lines:
            where = line.where
            if isinstance(line, Assign):
                if isinstance(line.target, Problem):
                    self.fail(where, line.target.message)
                owner, member = line.target.entity, line.target.member
                key = f'{owner}.{member}'
                kind = self.field_kind.get(key)
                if kind not in ('mode', 'quantity'):
                    self.fail(where, f'{line.written} is not a var')
                if line.augmented and line.operator not in ('Add', 'Sub'):
                    self.fail(where, 'a line adds (+=) or takes away (-=)')
                if kind == 'mode':
                    self.written_modes.add(key)
                if owner != e:
                    self.note(host, [self.quantity_of[key] if kind == 'quantity' else flat_key(key)])
                self.assign(step, key, kind, line.value, e, where)
            elif isinstance(line, Move):
                step['transfer'].append(self.transfer(e, line))
            elif isinstance(line, Fire):
                if isinstance(line.targets, Problem):
                    self.fail(where, line.targets.message)
                for owner, name in line.targets:
                    target = self.rule_id(f'{owner}.{name}')
                    if self.hosts[owner] != host:
                        self.note(host, [target])
                    step['fire'].append(target)
            else:
                raise TypeError(line)
        return step

    def assign(self, step, key, kind, value, e, where):
        target = self.quantity_of[key] if kind == 'quantity' else flat_key(key)
        if target in step['set']:
            self.fail(where, f'{target} is written twice in one outcome')
        if kind == 'mode':
            values = thaw(self.entity_named[split_key(key)[0]].value(split_key(key)[1]).type)
            if isinstance(value, nodes.Const) and isinstance(value.value, str):
                if value.value not in values:
                    self.fail(where, f'{value.value!r} is not one of the states {values}')
                step['set'][target] = {'mode': value.value}
                return
            found, tree = self.state_source(value, e, where)
            missing = sorted(found - set(values))
            if missing:
                self.fail(where, f'it can take {missing}, which are not among the states {values}')
            local = Reads(self, self.hosts[e])
            tree = Typing(self, Context(e), local, where).visit(tree)
            self.note(self.hosts[e], local.reads)
            step['set'][target] = {
                'expr': self.flat(tree, where),
                'values': list(values),
                'path': path_text(where),
            }
            return
        if target in self.bool_states:
            if isinstance(value, resolved.Word):
                step['set'][target] = {'expr': nodes.const(1 if value.value else 0), 'path': path_text(where)}
                return
            # A condition: the state holds it as the engine's 0/1 number.
            local = Reads(self, self.hosts[e])
            test = Typing(self, Context(e), local, where).visit(value)
            self.note(self.hosts[e], local.reads)
            held = nodes.if_else(test, nodes.const(1), nodes.const(0))
            step['set'][target] = {'expr': self.flat(held, where), 'path': path_text(where)}
            return
        if isinstance(value, nodes.Const) and is_number(value.value):
            if value.value != 0 and self.units.parse_unit(self.qunits[target]).dimensions:
                self.fail(where, f'write the unit of the number: {value.value} {self.qunits[target]}')
            text = value.value
        else:
            local = Reads(self, self.hosts[e])
            text = Typing(self, Context(e), local, where).visit(value)
            self.note(self.hosts[e], local.reads)
        step['set'][target] = {'expr': self.flat(text, where, self.qunits[target]), 'path': path_text(where)}

    def state_source(self, node, e, where):
        """(the states that it can give, its expression) of a value that sets a named state: one of
        the states, another named state, a named input, or `a if C else b` of these. A named input
        reads as a test of each of its values."""
        if isinstance(node, nodes.Const) and isinstance(node.value, str):
            return {node.value}, node
        if isinstance(node, nodes.IfElse):
            body, first = self.state_source(node.body, e, where)
            orelse, second = self.state_source(node.orelse, e, where)
            return body | orelse, nodes.if_else(node.test, first, second)
        if isinstance(node, resolved.Ref) and node.entity is not None:
            ref = self.value(node.entity, node.member, Context(e), where)
            if ref[0] == 'mode':
                return set(thaw(self.entity_named[node.entity].value(node.member).type)), node
            if ref[0] == 'parameter' and ref[1] in self.choices:
                names = self.choices[ref[1]]
                tree = nodes.const(names[-1])
                for name in reversed(names[:-1]):
                    test = nodes.compare(['eq'], [node, nodes.const(name)])
                    tree = nodes.if_else(test, nodes.const(name), tree)
                return set(names), tree
        self.fail(
            where,
            'a named state is set to one of its states, to another named state or a named input, or to '
            '`a if C else b` of these',
        )

    def transfer(self, e, line):
        """A move: an amount taken out of one stock and put into another, of this entity or of others."""
        where = line.where
        host = self.hosts[e]
        ends = []
        for written, end in line.ends:
            if end == 'outside':
                self.fail(
                    where,
                    'a move joins two values of the model; to add from outside the model, write `x += amount`',
                )
            if isinstance(end, Problem):
                self.fail(where, end.message)
            key = f'{end.entity}.{end.member}'
            if self.field_kind.get(key) != 'quantity':
                self.fail(where, f'{written} is not a number var')
            qid = self.quantity_of[key]
            if end.entity != e:
                self.note(host, [qid])
            ends.append(qid)
        given = line.amount
        if isinstance(given, nodes.Const) and is_number(given.value) and given.value != 0:
            unit = self.qunits[ends[0]]
            if self.units.parse_unit(unit).dimensions:
                self.fail(where, f'write the unit of the number: {given.value} {unit}')
        local = Reads(self, host)
        amount = Typing(self, Context(e), local, where).visit(given)
        self.note(host, local.reads)
        return {
            'from': ends[0],
            'to': ends[1],
            'amount': self.flat(amount, where, self.qunits[ends[0]]),
            'path': path_text(where),
        }

    def fire_cycles(self, s):
        """An event that fires itself at once, through the events that its outcomes name, would fire
        again and again at one moment."""
        graph = {
            rid: {
                target
                for outcome in rule['outcomes']
                for target in outcome['do']['fire']
                if s['rules'].get(target, {}).get('delay') is None
            }
            for rid, rule in s['rules'].items()
        }
        for rid in graph:
            seen, pending = set(), list(graph[rid])
            while pending:
                item = pending.pop()
                if item == rid:
                    self.fail(
                        tuple(s['rules'][rid]['path'].split('/')),
                        f'{rid} fires itself at once, through the events that it names',
                    )
                if item not in seen:
                    seen.add(item)
                    pending.extend(graph.get(item, ()))

    # ---- checks, outputs, orders and the start -------------------------------------------------

    def check_part(self, s):
        """Sum checks are partitions of every structure; other checks are placed in each structure where
        they apply, from the start values of its named states."""
        # A check is named by the template of its entity, or by the entity made without one.
        owners = {e: template if template is not None else e for e, template in self.entity_class.items()}
        counts = Counter(owners.values())
        sources = []
        for e, cls_name in owners.items():
            for i, check in enumerate(self.entity_named[e].checks):
                name = f'{cls_name}.{i}' if counts[cls_name] == 1 else f'{cls_name}.{i}.{self.hosts[e]}'
                sources.append((name, check))
        for i, check in enumerate(self.scenario.checks):
            sources.append((f'{MAIN}.{i}', check))
        partitions, items = {}, []
        for name, check in sources:
            path = check.where
            self.check_owner[name] = None if check.entity is None else self.hosts[check.entity]
            if check.records is None:
                self.fail(path, 'a check has its record')
            if check.kind == 'sum':
                parts = []
                for part in check.parts:
                    if isinstance(part, Problem):
                        self.fail(check.parts_where, part.message)
                    if self.field_kind.get(f'{part.entity}.{part.member}') != 'quantity':
                        self.fail(check.parts_where, f'{part.written} is not a stock')
                    parts.append(self.quantity_of[f'{part.entity}.{part.member}'])
                total, _ = self.text_of(check.total, None)
                partition = {
                    'label': thaw(check.message),
                    'total': self.flat(total, check.total.where),
                    'parts': parts,
                    'basis': self.resolved(thaw(check.records)),
                    'tolerance': None,
                    'path': path_text(path),
                }
                if check.within is not None:
                    tolerance, _ = self.text_of(check.within, None)
                    partition['tolerance'] = self.flat(tolerance, check.within.where)
                partitions[name] = partition
                continue
            text, _ = self.text_of(check.condition, None)
            item = {
                'expr': text,
                'message': thaw(check.message),
                'basis': self.resolved(thaw(check.records)),
            }
            if check.kind == 'check':
                item['severity'] = thaw(check.severity)
            items.append((name, item, path))
        return partitions, items

    def outcome_part(self, s):
        """The outputs: fields marked `output` and the outputs of the main. Returns each one's
        first-stage expression, which a structure that lacks a stock reads at zero. An output's scope is
        its own, or the scenario's (`scope` on the scenario line); an output with neither has none."""
        scope = thaw(self.scenario.scope)
        main = {output.name: output for output in self.scenario.outputs}
        texts = {}
        for key, oid in self.outcome_of.items():
            output = (
                self.entity_named[split_key(key)[0]].value(split_key(key)[1]).output
                if '.' in key
                else main[key]
            )
            path = output.where
            if output.records is None or output.text is None:
                self.fail(path, 'an output has its text and its record')
            self.outcome_where[oid] = output.formula_where
            outcome = {
                'label': output.label,
                'unit': self.unit_in(output.type, output.unit_where, output.entity, output.name),
                'kind': thaw(output.measure),
                'status': 'unestimated' if output.not_estimated is not None else 'estimated',
                'scope': thaw(output.scope) or scope,
                'basis': self.resolved(thaw(output.records)),
                'nonnegative': not output.signed,
            }
            if outcome['scope'] is None:
                del outcome['scope']
            if output.about is not None:
                outcome['description'] = output.about
            if output.reports is not None:
                # The output's category: a tag as the file writes it, which the language does not read.
                outcome['category'] = output.reports
            if output.not_estimated is not None:
                outcome['reason'] = output.not_estimated
            elif self.field_kind.get(key) == 'quantity':
                texts[oid] = nodes.ref(self.quantity_of[key])
            elif output.formula is not None:
                texts[oid] = self.text_of(output.formula, None, outcome=True)[0]
            else:
                self.fail(
                    path, 'an output is a formula (is), a stock or tally, or says what is not estimated'
                )
            if oid in texts:
                outcome['expr'] = self.flat(texts[oid], output.formula_where)
            if output.lag is not None:
                outcome['lag'] = self.lag_part(output.lag)
            if output.distinct is not None:
                outcome['additive'] = self.resolved(thaw(output.distinct.value))
            s['outcomes'][oid] = outcome
        return texts

    def lag_part(self, lag):
        """A reporting lag: fixed, uniform or a mixture; each delay is an expression in hours."""

        def delay(expression):
            text, _ = self.text_of(expression, None, outcome=True)
            return self.flat(text, expression.where, 'h')

        if lag.kind == 'uniform':
            low, high = lag.delays
            return {'type': 'uniform', 'min': delay(low), 'max': delay(high)}
        if lag.kind == 'mixture':
            return {
                'type': 'mixture',
                'components': [
                    {'weight': thaw(share), 'delay': delay(item)}
                    for share, item in zip(lag.weights, lag.delays)
                ],
            }
        return {'type': 'fixed', 'delay': delay(lag.delays[0])}

    def time_part(self):
        out = {'horizon': self.hours(thaw(self.scenario.horizon.written), self.scenario.horizon.where)}
        if self.scenario.timescales is not None:
            # The shortest physical times, from inputs alone: the limit on the solver's step.
            out['timescales'] = [written(self.text_of(x, None)[0]) for x in self.scenario.timescales]
        if self.scenario.resolution is not None:
            # The longest step of the solver for this scenario, in hours (docs/engine.md, Steps).
            out['resolution'] = self.hours(
                thaw(self.scenario.resolution.written), self.scenario.resolution.where
            )
        return out

    def initiation_part(self):
        """The start: its rule, which fires first at t = 0, its event, the entity that it acts as, and
        the start's basis."""
        start = self.scenario.start
        if start is None:
            return None
        rid = self.rule_id(f'{start.entity}.start')
        return {
            'rule': rid,
            'effect': f'{rid}.done',
            'entity': self.hosts[start.entity],
            'basis': self.resolved(thaw(start.records)) if start.records is not None else None,
        }

    # ---- one set of start states ---------------------------------------------------------------

    def start_states(self):
        """The options that set start states (a named state, or the start value of a stock, tally or
        number state), in menu order."""
        return [
            profile.name
            for group in self.scenario.groups
            for profile in group.profiles
            if any(
                self.field_kind.get(f'{e}.{f}') in ('mode', 'quantity')
                for e, f in self.option_values(profile.name)
            )
        ]

    def run_starts(self, options):
        """The start-state options of a run, sorted: the key of its structure."""
        states = set(self.start_states())
        return tuple(sorted(p for p in options if p in states))

    def start_sets(self):
        """The sets of start-state options that the runs use, in the order of the runs."""
        out = []
        for run in self.scenario.runs:
            starts = self.run_starts(run.profiles)
            if starts not in out:
                out.append(starts)
        return out

    def derive(self, base, starts):
        """The structure of one set of start-state options: their start values, without the parts that
        cannot act from those values, and with the checks that apply from them. `whole[starts]` keeps
        the structure with every part, its events, orders and links, and without the checks."""
        s = copy.deepcopy(base)
        for option in starts:
            for e, setting in self.profile_settings(option):
                key = f'{e}.{setting.target}'
                kind = self.field_kind.get(key)
                value, basis = thaw(setting.value), thaw(setting.records)
                if kind == 'mode':
                    mode = s['modes'][flat_key(key)]
                    mode['initial'] = value
                    if basis is not None:
                        mode['basis'] = self.resolved(basis)
                    mode['path'] = path_text(setting.where)
                elif kind == 'quantity':
                    qid = self.quantity_of[key]
                    quantity = s['quantities'][qid]
                    flag = qid in self.bool_states
                    start = self.start_value(value, quantity['unit'], flag, setting.value_at)
                    text, _ = self.text_of(as_number(setting.start, start), self.hosts[e])
                    quantity['initial'] = self.flat(text, setting.value_at, quantity['unit'])
                    if basis is not None:
                        quantity['basis'] = self.resolved(basis)
                    quantity['path'] = path_text(setting.where)
        for name, partition in self.partitions.items():
            s['partitions'][name] = copy.deepcopy(partition)
        checks = [item['expr'] for _, item, _ in self.check_items]
        option_states = {
            self.quantity_of[f'{e}.{f}']
            if self.field_kind[f'{e}.{f}'] == 'quantity'
            else flat_key(f'{e}.{f}')
            for group in self.scenario.groups
            for profile in group.profiles
            for e, f in self.option_values(profile.name)
            if self.field_kind.get(f'{e}.{f}') in ('mode', 'quantity')
        }
        dead = self.left_out[starts] = idle_parts(s, self.check_owner, checks, option_states)
        zeros = {qid: s['quantities'][qid]['unit'] for qid in dead['quantities']}
        # Every part, for the evidence of the parts left out: they show as possible but not used.
        whole = self.whole[starts] = copy.deepcopy(s)
        remove(s, dead)
        for name in [n for n in s['partitions'] if self.check_owner.get(n) in dead['entities']]:
            s['partitions'].pop(name)
        start = {name: mode['initial'] for name, mode in s['modes'].items()}
        written = {flat_key(key) for key in self.written_modes}
        for name, item, path in self.check_items:
            if self.check_owner.get(name) in dead['entities']:
                continue
            states = set(start) if 'severity' in item else set(start) - written
            text = settled(item['expr'], {n: v for n, v in start.items() if n in states}, zeros)
            if isinstance(text, (str, nodes.Node)) and not names_in(text):
                # Once the stocks that these runs leave out read zero, it reads no state, input or time.
                text = bool(evaluate(text, {}, self.units))
            if text is True:
                continue  # it holds at the start for certain: these runs do not have it
            if text is False:
                self.fail(
                    path,
                    f'the check fails at the start of every run with {list(starts) or "no start profiles"}',
                )
            target = s['input_checks' if 'severity' in item else 'state_checks']
            target[name] = {**item, 'expr': self.flat(text, path), 'path': path_text(path)}
        for oid, text in self.outcome_texts.items():
            # An output reads zero for a stock or tally that these runs leave out.
            zeroed = settled(text, {}, zeros)
            if zeroed != text:
                s['outcomes'][oid]['expr'] = self.flat(zeroed, self.outcome_where[oid])
        for each in (s, whole):
            self.finish_events(each)
            self.link_part(each)
        return s

    def finish_events(self, s):
        """Every event with the rules that emit it, as the compiler registers them, and every event whose
        count or time a part of the structure reads. An event whose rules the structure leaves out stays
        with no rule: it never happens in these runs, so its count stays 0."""
        for rid, rule in s['rules'].items():
            for event in rule_events(rule):
                s['events'].setdefault(event, {'sources': []})
                s['events'][event]['sources'].append(rid)
        for event in sorted(read_events(s)):
            s['events'].setdefault(event, {'sources': []})

    def link_part(self, s):
        """Each entity's links: the members of other entities that its parts read, move or call. A
        link that a trigger reads carries the bases of the triggers that read it: how the entity knows."""
        kinds = (
            ('quantities', 'quantity'),
            ('modes', 'mode'),
            ('computed', 'computed'),
            ('labels', 'label'),
            ('rules', 'rule'),
            ('events', 'event'),
        )
        for host in s['entities']:
            bases = {}
            for reads, basis, _ in self.link_reads.get(host, []):
                for target in sorted(reads):
                    for item in as_list(basis):
                        if item not in bases.setdefault(target, []):
                            bases[target].append(copy.deepcopy(item))
            links = {}
            for target in self.reads.get(host, {}):
                kind = next((k for section, k in kinds if target in s[section]), None)
                if kind is None:
                    continue  # a part that this structure lacks
                found = bases.get(target)
                basis = None if not found else self.resolved(found[0] if len(found) == 1 else found)
                links[target] = {'to': target, 'kind': kind, 'basis': basis}
            s['links'][host] = links


def joined(*bases):
    """One basis from several: each record once, in order. One record stays a record."""
    out = []
    for basis in bases:
        for item in as_list(basis):
            if item is not None and item not in out:
                out.append(copy.deepcopy(item))
    return out[0] if len(out) == 1 else out


def written_range(found):
    """The range of a value (`semantic.Range`) as written: {min, max, basis}, with the edges that it
    writes."""
    if found is None:
        return {}
    out = {edge: thaw(item[0]) for edge, item in zip(('min', 'max'), found.edges) if item is not None}
    if found.basis is not None:
        out['basis'] = thaw(found.basis)
    return out


def field_kind(value):
    """The kind of a value as the builder reads it: `parameter` (an input or a fixed value), `mode` (a
    named state), `quantity` (a stock, tally, number state or bool state), `computed` (a formula),
    `inline` (a bool formula, written into each expression that reads it), `output`, or `text`."""
    if value.kind == 'text':
        return 'text'
    if value.kind in ('input', 'fixed'):
        return 'parameter'
    if value.kind in KINDS:
        return 'mode' if isinstance(value.type, tuple) else 'quantity'
    if value.formula is not None:
        if value.output is not None:
            return 'output'
        return 'inline' if value.type == 'bool' else 'computed'
    return 'output' if value.output is not None else None
