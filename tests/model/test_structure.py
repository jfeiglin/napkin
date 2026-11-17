"""The typed parts of a compiled model (`napkin/model/structure.py`).

A structure and a resolved run go through the typed parts and back with nothing lost, on the fixture
that writes every construct of the language once and on the synthetic scenarios. The mappings that
`Structure.of` reads here are those that the lowering itself writes (`tests.build.lowered`), as they
are before the checks and with the facts of the checks written into them. The lowering writes each
expression as its node; the plain data of a structure writes it as its text (`texts`), and the typed
parts read both. What a rule reads and
writes, and what an expression reads through the formulas, are those of a plain walk over the
mappings, and of the walkers that the consumers have today. A mapping that the
typed parts cannot take whole is an error that names the part and the key. A record cannot change. The
order of each kind of part is the builder's order, and each query gives what a count over the builder's
mappings gives.
"""

import copy
import dataclasses

import pytest

from napkin.core import expr as nodes
from napkin.core.expr import text as written
from napkin.engine.continuous.system import System
from napkin.engine.runtime import NumericalSettings
from napkin.expressions import UnitSystem, evaluate, names_in
from napkin.model import ir
from napkin.model import structure as typed
from napkin.model.analysis import structure as checks
from napkin.model.ir import thaw
from tests import build as b
from tests.acceptance.helpers import LIBRARY, fixture


@pytest.fixture(scope='module')
def every_construct():
    return b.compiled(fixture('F5'), LIBRARY)


@pytest.fixture(scope='module')
def transfer():
    return b.compiled(b.scenario())


# The mappings of the lowering of each fixture (`tests.build.lowered`): (structures, whole structures).
LOWERED = {'every_construct': (lambda: (fixture('F5'), LIBRARY)), 'transfer': (lambda: (b.scenario(), None))}


def texts(value):
    """A mapping of the lowering as plain data: each expression, which the lowering writes as its
    node, as the text of the node. It is what `plain()` of the typed parts writes."""
    if isinstance(value, nodes.Node):
        return nodes.text(value)
    if isinstance(value, dict):
        return {key: texts(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [texts(item) for item in value]
    return value


@pytest.fixture(scope='module')
def as_lowered():
    """{fixture: the mappings of its lowering, as the lowering writes them}, each made once."""
    return {name: b.lowered(*source()) for name, source in LOWERED.items()}


@pytest.fixture(scope='module')
def lowerings(as_lowered):
    """{fixture: the mappings of its lowering, as plain data (`texts`)}."""
    return {name: tuple(texts(part) for part in parts) for name, parts in as_lowered.items()}


def checked(mapping, structure):
    """The builder's mapping of a structure with the facts that the checks found (`structure`, the
    model's typed structure, has them): the order of the formulas after the other keys, and each
    classified trigger as its plain data. The model kept this mapping before it kept only the typed
    parts."""
    out = copy.deepcopy(mapping)
    out['computed_order'] = list(structure.computed_order)
    for name, rule in structure.rules.items():
        if rule.trigger.kind is not None:
            out['rules'][name]['trigger'] = rule.trigger.plain()
    return out


def unchecked(mapping):
    """What the typed parts of a mapping of the lowering write: the mapping, with an order of the
    formulas that is empty, as the checks have not yet found one."""
    return {**copy.deepcopy(mapping), 'computed_order': []}


def same(a, b_):
    """Whether two plain values are the same, with their types (1, 1.0 and True are three values) and
    with the keys of each mapping in the same order."""
    if type(a) is not type(b_):
        return False
    if isinstance(a, dict):
        return list(a) == list(b_) and all(same(a[key], b_[key]) for key in a)
    if isinstance(a, list):
        return len(a) == len(b_) and all(same(x, y) for x, y in zip(a, b_))
    return a == b_


def models(request):
    return [request.getfixturevalue(name) for name in LOWERED]


def with_lowerings(request):
    """(model, its mappings of the lowering, its mappings of the whole structures) of each fixture."""
    lowerings = request.getfixturevalue('lowerings')
    return [(request.getfixturevalue(name), *lowerings[name]) for name in LOWERED]


def test_a_structure_goes_through_the_typed_parts_and_back_with_nothing_lost(request):
    seen, forms = set(), 0
    for model, lowered, whole in with_lowerings(request):
        for starts, mapping in lowered.items():
            # As the lowering writes it, and with the facts that the checks find.
            kept = (model.structures[starts], model.whole[starts])
            for raw, structure in zip((mapping, whole[starts]), kept):
                for written_form, expected in (
                    (thaw(raw), unchecked(raw)),
                    (checked(raw, structure), checked(raw, structure)),
                ):
                    assert same(typed.Structure.of(written_form).plain(), expected)
                    forms += 1
                seen |= {section for section in typed.SECTIONS if raw[section]}
    # The fixtures have each kind of part, so each class of record is read and written.
    assert seen == set(typed.SECTIONS) and forms == 8


def test_a_resolved_run_goes_through_the_typed_parts_and_back_with_nothing_lost(request):
    for model, lowered, _ in with_lowerings(request):
        for run, info in model.runs.items():
            # The mapping of the run as a copy of everything writes it: from the builder's mapping
            # of its structure (`copied`, below).
            structure = model.structure_of(run)
            mapping = copied(model, checked(lowered[info['starts']], structure), model.resolve(run))
            resolved = typed.Resolved.of(mapping)
            assert same(resolved.plain(), mapping)
            assert resolved.run == run and resolved.model_hash == model.model_hash
            assert resolved.time.horizon == mapping['time']['horizon']
            assert dict(resolved.values) == mapping['values']
            # A resolved run is a structure too: the same parts, in the same order.
            assert list(resolved.quantities) == list(mapping['quantities'])


# ---- an expression of a part is its typed node ------------------------------------------------------


def expressions_of(part, mapping):
    """(the value of a record, the value of the builder's mapping) of each place where the two hold
    different things: the record holds something that the mapping writes in another way."""
    if isinstance(part, typed.Part):
        for key, text in mapping.items():
            yield from expressions_of(getattr(part, typed.RENAMES.get(key, key)), text)
    elif isinstance(mapping, dict):
        for key, text in mapping.items():
            yield from expressions_of(part[key], text)
    elif isinstance(mapping, list):
        for item, text in zip(part, mapping, strict=True):
            yield from expressions_of(item, text)
    elif isinstance(part, nodes.Node) or type(part) is not type(mapping) or part != mapping:
        yield part, mapping


def test_each_expression_of_a_part_is_the_node_that_the_builder_writes(request, as_lowered):
    """A record holds each expression as its node: the very node that the lowering wrote into its
    mapping. The text of the node is the text that the plain data of the structure writes, and
    that text reads back to the same node: so a reader of the node and a reader of the text read
    one expression. Nothing else of a record differs from the mapping. A number and a yes/no are
    what they are, and the chance of the outcome that takes the rest is the word `else`."""
    seen, words = 0, 0
    for name in LOWERED:
        model, own = request.getfixturevalue(name), as_lowered[name][0]
        for starts, structure in model.structures.items():
            mapping = texts(own[starts])
            for section in typed.SECTIONS:
                parts = dict(getattr(structure, section))
                found = list(expressions_of(parts, mapping[section]))
                written = [node for node, _ in expressions_of(parts, own[starts][section])]
                assert len(written) == len(found)
                for (part, text), node in zip(found, written):
                    assert isinstance(part, nodes.Node) and type(text) is str
                    assert part is node
                    assert str(part) == nodes.text(part) == text
                    assert nodes.read(text) is part and nodes.read(part) is part
                    seen += 1
            # The typed parts of the plain data are the typed parts of the lowering's own mapping.
            assert typed.Structure.of(mapping) == typed.Structure.of(own[starts])
            for rule in structure.rules.values():
                words += sum(outcome.chance == 'else' for outcome in rule.outcomes)
    assert seen >= 50 and words > 0


def test_a_text_that_is_no_expression_is_an_error_that_names_its_place(lowerings):
    mapping = thaw(next(iter(lowerings['transfer'][0].values())))
    flow = next(iter(mapping['flows']))
    mapping['flows'][flow]['rate'] = 'rate +* 2'
    with pytest.raises(typed.StructureError, match=f'flows/{flow}/rate.*is no expression'):
        typed.Structure.of(mapping)


# ---- a resolution shares the parts of its structure ------------------------------------------------

# The transfer of `b.scenario()` with a quantity whose upper bound reads an input.
BOUND = (
    'var served: people = 0 size 10 people  @fixture',
    'var served: people = 0 in 0 people to 4 * n size 10 people  @fixture',
)


def bounded_text():
    text = b.scenario()
    assert text.count(BOUND[0]) == 1
    return text.replace(*BOUND)


@pytest.fixture(scope='module')
def bounded():
    return b.compiled(bounded_text())


def copied(model, structure, resolved):
    """The mapping of a resolution as a copy of everything writes it: the mapping of the structure
    (`structure`, the builder's mapping with the facts of the checks), with the number of each bound
    that is written as an expression, and then what the run has of its own. The number of a bound is
    its expression with the values of the run, in the unit of the quantity."""
    units = UnitSystem(thaw(model.library['units']))
    mapping = copy.deepcopy(structure)
    for quantity in mapping['quantities'].values():
        for key in ('min', 'max'):
            if isinstance(quantity.get(key), str):
                quantity[key] = evaluate(
                    nodes.read(quantity[key]), dict(resolved.values), units
                ) / units.scale(quantity['unit'])
    mapping.update(
        values=dict(resolved.values),
        parameter_values=dict(resolved.parameter_values),
        time=resolved.time.plain(),
        initiation=typed.thawed(resolved.initiation),
        proven_zero_stock_faces=list(resolved.proven_zero_stock_faces),
        proven_monotone_crossings=list(resolved.proven_monotone_crossings),
        proven_cumulative_outcomes=list(resolved.proven_cumulative_outcomes),
        run=resolved.run,
        options=list(resolved.options),
        starts=list(resolved.starts),
        model_hash=model.model_hash,
    )
    return mapping


def test_a_resolved_run_has_the_parts_of_its_structure_themselves(request, bounded):
    """A resolution makes no part again: each part of the run is the part of its structure, the same
    object, but for a quantity with a bound that is written as an expression. What its typed parts
    write is the mapping that a copy of everything writes, with the keys in the same order."""
    bounds = 0
    every = [*with_lowerings(request), (bounded, texts(b.lowered(bounded_text())[0]), None)]
    for model, lowered, _ in every:
        for run, info in model.runs.items():
            structure = model.structures[info['starts']]
            for values in (None, {'service.n': 20} if model is bounded else None):
                resolved = model.resolve(run, values)
                for section in typed.SECTIONS:
                    if section != 'quantities':
                        assert getattr(resolved, section) is getattr(structure, section)
                assert resolved.links is structure.links
                for name, quantity in resolved.quantities.items():
                    of_structure = structure.quantities[name]
                    bounds_written = [
                        f for f in ('minimum', 'maximum') if isinstance(getattr(of_structure, f), nodes.Node)
                    ]
                    bounds += len(bounds_written)
                    if not bounds_written:
                        assert quantity is of_structure
                    else:
                        assert quantity == of_structure.changed(
                            **{f: getattr(quantity, f) for f in bounds_written}
                        )
                expected = copied(model, checked(lowered[info['starts']], structure), resolved)
                assert same(resolved.plain(), expected)
                assert same(typed.Resolved.of(expected).plain(), expected)
    # The bound of the third model is 4 * n people: 40 with the n of the file and 80 with n = 20.
    assert bounds == 4
    assert bounded.resolve('a').quantities['service.served'].maximum == 40.0
    assert bounded.resolve('a', {'service.n': 20}).quantities['service.served'].maximum == 80.0
    # The structure keeps the expression: the number is of the run.
    assert written(bounded.structures[()].quantities['service.served'].maximum) == '4 * service.n'


def test_resolutions_with_other_values_leave_the_structure_and_one_another_as_they_are(bounded):
    """The checks of every resolution read the parts of the structure, which the resolutions share.
    They write nothing into them: after resolutions with other values, a resolution gives what the
    first one gave, and the parts of each run that are not of its own are those of the structure."""
    structure = bounded.structures[()]
    before = structure.plain()
    first = bounded.resolve('a', {'service.n': 30})
    kept = first.plain()
    others = []
    for n in (5, 60, 12):
        other = bounded.resolve('b', {'service.n': n})
        assert other.values['service.n'] == n and other.quantities['service.served'].maximum == 4 * n
        others.append(other)
    again = bounded.resolve('a', {'service.n': 30})
    assert again == first and same(again.plain(), kept) and same(first.plain(), kept)
    assert same(structure.plain(), before)
    sections = {key: value for key, value in kept.items() if key in typed.SECTIONS and key != 'quantities'}
    assert same(sections, {key: before[key] for key in sections})
    # The runs share the parts of the structure: each section but the quantities is one object, in
    # the structure and in each run, and each quantity with no bound to work out is one object too.
    for run in (first, again, *others):
        for section in typed.SECTIONS:
            if section != 'quantities':
                assert getattr(run, section) is getattr(structure, section)
        assert run.quantities['service.stock'] is structure.quantities['service.stock']
    # No reader can write into what the runs share: not into a section, not into a part, not into
    # what a part holds, and not into the run. Each run has its own values, which cannot change.
    flow = first.flows['service.serve']
    with pytest.raises(TypeError):
        first.flows['service.serve'] = flow.changed(rate=0)
    with pytest.raises(TypeError):
        del first.flows['service.serve']
    with pytest.raises(dataclasses.FrozenInstanceError):
        flow.rate = 0
    with pytest.raises(TypeError):
        flow.basis['kind'] = 'source'
    with pytest.raises(dataclasses.FrozenInstanceError):
        first.flows = {}
    with pytest.raises(TypeError):
        first.values['service.n'] = 5
    assert first.values is not again.values and first.values == again.values
    # The quantities are the one section that a resolution makes, for the number of a bound: that
    # section and the quantity with the number cannot change either.
    served = first.quantities['service.served']
    with pytest.raises(TypeError):
        first.quantities['service.served'] = served.changed(maximum=1.0)
    with pytest.raises(dataclasses.FrozenInstanceError):
        served.maximum = 1.0
    assert served.maximum == again.quantities['service.served'].maximum == 4 * 30
    assert structure.flows['service.serve'] is flow and same(structure.plain(), before)
    assert same(first.plain(), kept)


def test_a_run_takes_more_of_its_own_at_the_end_of_its_keys(bounded):
    """`adding` gives a run the luck of a sample or its distributions. The copy shares the parts, and
    what it writes has the new key after the keys that the run had. What a run with both writes reads
    back to that run. A key that is no key of a run is an error."""
    resolved = bounded.resolve('a')
    lucky = resolved.adding(luck={'seed': 3, 'sample': 7})
    assert lucky.luck == {'seed': 3, 'sample': 7} and resolved.luck is None
    assert lucky.flows is resolved.flows and lucky.quantities is resolved.quantities
    assert list(lucky.plain()) == [*resolved.plain(), 'luck']
    assert same(lucky.plain(), {**resolved.plain(), 'luck': {'seed': 3, 'sample': 7}})
    assert 'luck' not in resolved.plain()
    both = lucky.adding(distributions={'service.n': {'family': 'uniform'}})
    assert both.luck == lucky.luck and both.distributions == {'service.n': {'family': 'uniform'}}
    assert set(both.plain()) == {*resolved.plain(), 'luck', 'distributions'}
    assert typed.Resolved.of(both.plain()) == both and same(
        typed.Resolved.of(both.plain()).plain(), both.plain()
    )
    # What a run takes cannot change, and it is the run's own: the caller's data stays the caller's.
    luck = {'seed': 3, 'sample': 7}
    taken = resolved.adding(luck=luck)
    with pytest.raises(TypeError):
        taken.luck['seed'] = 4
    luck['seed'] = 4
    assert taken.luck == {'seed': 3, 'sample': 7} and taken == lucky
    with pytest.raises(typed.StructureError, match="'values'"):
        resolved.adding(values={})


def test_the_order_of_each_kind_of_part_is_the_order_of_the_builder(every_construct, lowerings):
    for starts, mapping in lowerings['every_construct'][0].items():
        # The structure that the model keeps, with the facts of its checks, and the lowering's mapping.
        structure = every_construct.structures[starts]
        assert structure == typed.Structure.of(thaw(mapping)).with_facts(
            checks.structure_facts(
                typed.Structure.of(thaw(mapping)),
                thaw(every_construct.library),
                UnitSystem(thaw(every_construct.library['units'])),
            )[1]
        )
        for section in typed.SECTIONS:
            assert list(structure.section(section)) == list(mapping[section])
        # The order of the formulas, which the checks find: each one after each formula that it reads.
        order = list(structure.computed_order)
        assert sorted(order) == sorted(mapping['computed']) and len(order) > 1
        for at, name in enumerate(order):
            read = names_in(nodes.read(mapping['computed'][name]['expr'])) & set(mapping['computed'])
            assert read <= set(order[:at]), name
        ranks = [tuple(mapping['rules'][rule.id]['rank']) for rule in structure.moment_order()]
        assert ranks == sorted(ranks) and len(ranks) == len(mapping['rules']) > 1
        # The order of the lines of an outcome is the order in which they act.
        for name, rule in mapping['rules'].items():
            for outcome, record in zip(rule['outcomes'], structure.rules[name].outcomes):
                assert list(record.do.set) == list(outcome['do']['set'])


def test_the_four_renamed_fields_hold_the_keys_that_are_words_of_python(lowerings):
    (mapping,) = (thaw(m) for m in list(lowerings['every_construct'][0].values())[:1])
    structure = typed.Structure.of(mapping)
    moved = [name for name, flow in mapping['flows'].items() if 'from' in flow and 'to' in flow]
    assert moved
    for name in moved:
        flow = structure.flows[name]
        assert (flow.source, flow.target) == (mapping['flows'][name]['from'], mapping['flows'][name]['to'])
    bounded = [name for name, item in mapping['quantities'].items() if 'min' in item]
    assert bounded
    for name in bounded:
        assert structure.quantities[name].minimum == mapping['quantities'][name]['min']
        assert structure.quantities[name].maximum == mapping['quantities'][name].get('max')
    # A flow from outside has no source, and the mapping has no key for it.
    outside = [name for name, flow in mapping['flows'].items() if 'from' not in flow]
    for name in outside:
        assert structure.flows[name].source is None and 'from' not in structure.flows[name].plain()


def test_the_queries_give_what_a_count_over_the_mappings_gives(lowerings):
    for mapping in map(thaw, lowerings['every_construct'][0].values()):
        structure = typed.Structure.of(mapping)
        drained = filled = 0
        for quantity in mapping['quantities']:
            out = [name for name, flow in mapping['flows'].items() if flow.get('from') == quantity]
            into = [name for name, flow in mapping['flows'].items() if flow.get('to') == quantity]
            assert list(structure.flows_from(quantity)) == out
            assert list(structure.flows_into(quantity)) == into
            drained += bool(out)
            filled += bool(into)
            assert structure.owner(quantity) == mapping['quantities'][quantity]['entity']
        assert drained and filled
        for name, rule in mapping['rules'].items():
            assert structure.owner(name) == rule['entity']
        assert structure.owner('no such part') is None
        with pytest.raises(typed.StructureError, match='no section'):
            structure.section('values')


def test_a_key_that_no_field_takes_is_an_error_that_names_the_part_and_the_key(transfer, lowerings):
    (mapping,) = (thaw(m) for m in lowerings['transfer'][0].values())
    typed.Structure.of(mapping)
    # A key of a part, of a part inside a part, of the structure, and of a resolved run.
    part = copy.deepcopy(mapping)
    flow = next(iter(part['flows']))
    part['flows'][flow]['speed'] = 3
    with pytest.raises(typed.StructureError, match=f"flows/{flow}: Flow has no field for 'speed'"):
        typed.Structure.of(part)
    inner = copy.deepcopy(mapping)
    rule = next(iter(inner['rules']))
    inner['rules'][rule]['trigger']['mood'] = 'calm'
    with pytest.raises(typed.StructureError, match=f"rules/{rule}/trigger: Trigger has no field for 'mood'"):
        typed.Structure.of(inner)
    with pytest.raises(typed.StructureError, match="no part for 'weather'"):
        typed.Structure.of({**mapping, 'weather': {}})
    run = transfer.resolve('a').plain()
    with pytest.raises(typed.StructureError, match="no part for 'weather'"):
        typed.Resolved.of({**run, 'weather': {}})
    # A resolved run's own keys are no keys of a structure.
    with pytest.raises(typed.StructureError, match="no part for 'values'"):
        typed.Structure.of(run)


def test_a_field_that_must_be_there_is_an_error_when_it_is_not(lowerings):
    (mapping,) = (thaw(m) for m in lowerings['transfer'][0].values())
    quantity = next(iter(mapping['quantities']))
    del mapping['quantities'][quantity]['unit']
    with pytest.raises(typed.StructureError, match=f'quantities/{quantity}: Quantity lacks unit'):
        typed.Structure.of(mapping)
    (mapping,) = (thaw(m) for m in lowerings['transfer'][0].values())
    del mapping['flows']
    with pytest.raises(typed.StructureError, match='the section flows'):
        typed.Structure.of(mapping)
    with pytest.raises(typed.StructureError, match='a Flow is a mapping'):
        typed.Flow.of('water -> out')


def test_a_record_and_what_it_holds_cannot_change(lowerings):
    structure = typed.Structure.of(thaw(next(iter(lowerings['every_construct'][0].values()))))
    quantity = next(iter(structure.quantities.values()))
    with pytest.raises(dataclasses.FrozenInstanceError):
        quantity.unit = 'h'
    with pytest.raises(dataclasses.FrozenInstanceError):
        structure.flows = {}
    with pytest.raises(TypeError):
        structure.quantities['new'] = quantity
    rule = next(rule for rule in structure.rules.values() if rule.outcomes)
    assert isinstance(rule.outcomes, tuple) and isinstance(rule.emits, tuple) and isinstance(rule.rank, tuple)
    with pytest.raises(TypeError):
        rule.outcomes[0].do.set['x'] = None
    with pytest.raises(TypeError):
        rule.basis['kind'] = 'source'
    # A step that changes a part makes a new record, and the structure keeps the old one.
    larger = quantity.changed(size=7.5)
    assert larger.size == 7.5 and next(iter(structure.quantities.values())) is quantity
    assert larger.plain() == {**quantity.plain(), 'size': 7.5}
    # The copy keeps the order of the keys of the record, with a new key after them, and a key whose
    # value is taken away is gone.
    assert [key for key in larger.plain() if key != 'size'] == [
        key for key in quantity.plain() if key != 'size'
    ]
    renamed = quantity.changed(unit='h')
    assert list(renamed.plain()) == list(quantity.plain()) and renamed.plain()['unit'] == 'h'
    bare_quantity = quantity.changed(minimum=None)
    assert 'min' not in bare_quantity.plain() and bare_quantity.minimum is None


def test_the_typed_parts_are_read_from_a_mapping_and_give_it_back(transfer, lowerings):
    ((starts, mapping),) = lowerings['transfer'][0].items()
    structure = typed.Structure.of(thaw(mapping))
    assert isinstance(structure, typed.Structure)
    # The model gives the typed parts. Its structure was read from the builder's mapping, and it
    # writes that mapping with the facts of its checks.
    given = transfer.structures[starts]
    assert same(given.plain(), checked(mapping, given))
    resolved = transfer.resolve('a')
    assert isinstance(resolved, typed.Resolved) and resolved.run == 'a'
    # The plain data that the run writes is its other form, and it gives a typed run too: the same run.
    run = resolved.plain()
    read = typed.Resolved.of(run)
    assert isinstance(read, typed.Resolved) and read.run == 'a'
    assert read == resolved and same(read.plain(), run)
    # No structure and no resolved run keeps a mapping of the builder, however it was made (by the
    # model, from a mapping, from plain data, over a structure, with more of its own): a reader reads
    # its parts, or the plain data that it writes.
    own = {key: value for key, value in resolved.own().items() if key in typed.Resolved.ALWAYS}
    over = typed.Resolved.over(given, own)
    assert same(over.plain(), {**checked(mapping, given), **own})
    for made in (structure, given, resolved, read, over, over.adding(luck={'seed': 3, 'sample': 1})):
        assert not hasattr(made, 'mapping') and not hasattr(made, '_mapping')
    # A changed copy writes its change. So no function reads, through a copy, what was true of the
    # run that the copy was made from; and the run writes what it wrote before.
    longer = dataclasses.replace(resolved, time=resolved.time.changed(horizon=99.0))
    assert longer.plain()['time']['horizon'] == 99.0
    assert run['time']['horizon'] != 99.0 and same(resolved.plain(), run)
    # A copy writes its own values: two runs that differ never write the same mapping. (A run store
    # keys a run by what it writes.)
    other = dataclasses.replace(resolved, values={**resolved.values, next(iter(resolved.values)): -1.0})
    assert other.plain()['values'] != resolved.plain()['values']
    assert set(resolved.plain()) == set(longer.plain()) == set(other.plain())
    sample = dataclasses.replace(resolved, luck={'seed': 3, 'sample': 1})
    assert sample.plain()['luck'] == {'seed': 3, 'sample': 1} and 'luck' not in resolved.plain()
    # What a played run asks is no part of a resolved run: it is an argument of the run.
    assert not {'control', 'picks'} & set(sample.plain())
    quantity = next(iter(resolved.quantities))
    sized = resolved.quantities[quantity].changed(size=7.5)
    changed = dataclasses.replace(resolved, quantities={**resolved.quantities, quantity: sized})
    assert changed.plain()['quantities'][quantity]['size'] == 7.5
    assert changed.expanded(nodes.read(quantity)) == resolved.expanded(nodes.read(quantity)) == {quantity}


def test_the_structures_of_a_model_are_the_typed_parts_of_its_mappings(request):
    """The model reads each mapping that the lowering writes into typed parts, and keeps those parts
    with what the checks find of them (`structure_facts`): the order of the formulas and the class of
    each trigger. They write the lowering's mapping back with those facts, and a structure says what
    it leaves out."""
    left_out = 0
    idle = b.system(b.stock('w', 5), b.stock('idle', 0))
    for model, lowered, whole in [*with_lowerings(request), (b.compiled(idle), *map(texts, b.lowered(idle)))]:
        library = thaw(model.library)
        units = UnitSystem(library['units'])
        for name, mappings, left in (('structures', lowered, model.left_out), ('whole', whole, {})):
            kept = getattr(model, name)
            assert list(kept) == list(mappings)
            for starts, mapping in mappings.items():
                structure = kept[starts]
                bare = typed.Structure.of(thaw(mapping))
                errors, facts = checks.structure_facts(bare, library, units)
                assert errors == [] and structure == bare.with_facts(facts)
                assert same(structure.plain(), checked(mapping, structure))
                assert set(structure.computed_order) == set(mapping['computed'])
                assert all(rule.trigger.kind is not None for rule in structure.rules.values())
                assert typed.thawed(structure.left_out) == thaw(left.get(starts, {}))
                left_out += sum(map(len, structure.left_out.values()))
    # The last model leaves a stock out, so one structure says so.
    assert left_out == 1


def test_a_trigger_holds_what_the_builder_writes_before_the_checks():
    """The builder writes the condition of an event, and the place of the condition when the file
    writes one: an event that only a line fires has none. The record holds what the mapping has,
    with no class, and writes it back."""
    for mapping in ({'when': 'False'}, {'when': 't >= limit', 'path': 'e/r/when:'}):
        trigger = typed.Trigger.of(mapping)
        assert same(trigger.plain(), mapping)
        assert (trigger.path, trigger.kind, trigger.gate) == (mapping.get('path'), None, None)
        assert trigger.when is nodes.read(mapping['when'])


def test_an_output_says_distinct_with_its_records_or_with_none():
    """The line `distinct` of an output: the builder writes the key `additive` with the records of
    the line, and with no value for a line with no record. The record says which of the three its
    mapping has, and writes the mapping back."""
    basis = {'kind': 'assumption', 'explanation': 'An output of a test.'}
    base = {'label': 'People', 'kind': 'cumulative', 'unit': 'people', 'status': 'estimated'}
    base.update({'basis': basis, 'nonnegative': True, 'expr': 'east + west'})
    towns = {'kind': 'assumption', 'explanation': 'Two towns.'}
    for more, distinct in (({}, False), ({'additive': None}, True), ({'additive': towns}, True)):
        outcome = typed.Outcome.of({**base, **more})
        assert outcome.distinct() is distinct and same(outcome.plain(), {**base, **more})
        # A copy with another field says the same.
        assert outcome.changed(label='Others').distinct() is distinct
    # A record that was not read from a mapping says it by its records.
    made = typed.Outcome('People', 'cumulative', 'people', 'estimated', True, typed.frozen(basis))
    assert not made.distinct() and dataclasses.replace(made, additive=typed.frozen(towns)).distinct()


# ---- what a part reads and writes -------------------------------------------------------------------------

# A rule with an expression in each role, as the builder writes it. Each name is read in one role only.
RULE = {
    'id': 'r',
    'entity': 'e',
    'label': None,
    'basis': {'kind': 'assumption', 'explanation': 'A rule of a test.'},
    'metadata': {},
    'path': 'e/r',
    'rank': [1, 0, 0],
    'once': False,
    'named': False,
    'trigger': {'when': 'gate_name == 1 and t >= time_name', 'path': 'e/r/when:'},
    'delay': 'delay_name + drawn__draw0',
    'each': ['each_name'],
    'keep': 'keep_name > 0',
    'extras': [
        {'name': 'drawn__draw0', 'kind': 'draw', 'stage': 'trigger', 'family': 'uniform'}
        | {'args': {'min': 'low_name', 'max': 'high_name'}},
        {
            'name': 'past__delayed0',
            'kind': 'delayed',
            'stage': 'fire',
            'expr': 'past_name',
            'delay': 'back_name',
        },
    ],
    'outcomes': [
        {
            'name': 'first',
            'chance': 'chance_name',
            'available': 'available_name > 0',
            'label': None,
            'basis': {'kind': 'assumption', 'explanation': 'An outcome of a test.'},
            'path': 'e/r/first',
            'do': {
                'set': {
                    'number_target': {'expr': 'set_name + past__delayed0', 'path': 'e/r/first/0'},
                    'state_target': {'mode': 'on'},
                },
                'transfer': [
                    {'from': 'from_end', 'to': 'to_end', 'amount': 'amount_name', 'path': 'e/r/first/1'}
                ],
                'fire': ['fired_event'],
            },
            'emits': ['e.r.first'],
        },
        {
            'name': 'second',
            'chance': 'else',
            'available': None,
            'label': None,
            'basis': {'kind': 'assumption', 'explanation': 'An outcome of a test.'},
            'path': 'e/r/second',
            'do': {'set': {'other_target': {'expr': 7}}, 'transfer': [], 'fire': []},
            'emits': ['e.r.second'],
        },
    ],
    'emits': ['e.r'],
}
BY_ROLE = {
    'when': {'gate_name', 't', 'time_name'},
    'delay': {'delay_name', 'drawn__draw0'},
    'each': {'each_name'},
    'keep': {'keep_name'},
    'extra': {'low_name', 'high_name', 'past_name', 'back_name'},
    'chance': {'chance_name'},
    'available': {'available_name'},
    'set': {'set_name', 'past__delayed0'},
    'amount': {'amount_name'},
}


def bare(**sections):
    """A structure with only the sections that a test gives."""
    empty = {section: {} for section in typed.SECTIONS}
    return typed.Structure.of({**empty, 'links': {}, 'computed_order': [], **sections})


def test_a_rule_reads_the_names_of_each_role_and_writes_what_its_outcomes_change():
    structure = bare(rules={'r': RULE})
    rule = structure.rules['r']
    assert [role for role, _ in rule.sources()] == [
        *('when', 'delay', 'each', 'keep', 'extra', 'extra', 'extra', 'extra'),
        *('chance', 'available', 'set', 'amount', 'set'),
    ]
    for role, names in BY_ROLE.items():
        assert structure.reads(rule, {role}) == names
    assert structure.reads(rule) == set().union(*BY_ROLE.values())
    assert structure.reads(rule, {'when', 'amount'}) == BY_ROLE['when'] | BY_ROLE['amount']
    # What it changes: each value that an outcome sets, and the two ends of each move. No event.
    assert structure.writes(rule) == {'number_target', 'state_target', 'other_target', 'from_end', 'to_end'}
    assert rule.events() == ('e.r', 'e.r.first', 'e.r.second')
    assert [step.fire for step in rule.steps()] == [('fired_event',), ()]
    # The outcome that takes what is left has no chance to read, and a number is no name.
    assert ('chance', 'else') not in rule.sources() and ('set', 7) in rule.sources()
    assert structure.names(7) == structure.names(True) == frozenset()
    # The events are those of the model's helper.
    assert list(rule.events()) == ir.rule_events(RULE)


def test_the_events_of_each_rule_of_a_model_are_those_of_the_model_s_helper(request):
    seen = 0
    for _, _, whole in with_lowerings(request):
        for mapping in map(thaw, whole.values()):
            structure = typed.Structure.of(mapping)
            for name, rule in mapping['rules'].items():
                assert list(structure.rules[name].events()) == ir.rule_events(rule)
                seen += 1
    # The fixture of every construct has rules with a delay, a window, chances, moves and fired events.
    assert seen == 10


def formula(expr):
    basis = {'kind': 'assumption', 'explanation': 'A formula of a test.'}
    return {'entity': 'e', 'expr': expr, 'unit': 'ratio', 'basis': basis, 'path': 'e/f'}


def status(*whens):
    cases = [
        {'when': when, 'value': f'v{k}', 'text': 'A case.', 'path': 'e/s'} for k, when in enumerate(whens)
    ]
    default = {'value': 'none', 'text': 'No case.'}
    basis = {'kind': 'assumption', 'explanation': 'A status of a test.'}
    return {'entity': 'e', 'cases': cases, 'default': default, 'basis': basis, 'path': 'e/s', 'label': None}


def walked(mapping, source, labels, keep, seen=frozenset()):
    """The names that an expression reads through the formulas, by a plain walk with no memory."""
    out = set()
    for name in names_in(nodes.read(source)) if isinstance(source, str) else ():
        if name in mapping['computed']:
            texts = [mapping['computed'][name]['expr']]
        elif labels and name in mapping['labels']:
            texts = [case['when'] for case in mapping['labels'][name]['cases']]
        else:
            out.add(name)
            continue
        if keep or name in seen:
            out.add(name)
        if name not in seen:
            for text in texts:
                out |= walked(mapping, text, labels, keep, seen | {name})
    return out


GRAPH = {
    'computed': {
        'base': formula('p + w'),
        'left': formula('base * 2'),
        'right': formula('base + q'),
        'top': formula('left + right + level'),
        # A circle of two formulas, and a formula that reaches it.
        'round_a': formula('round_b + p'),
        'round_b': formula('round_a + q'),
        'reaches': formula('round_a + w'),
    },
    'labels': {'level': status('left > 1', 'flag == 1 and right > 0')},
}


@pytest.mark.parametrize('labels', [False, True])
@pytest.mark.parametrize('keep', [False, True])
def test_the_names_through_the_formulas_are_those_of_a_plain_walk(labels, keep):
    structure = bare(**GRAPH)
    expected = {
        (False, False): {'p', 'w', 'q', 'level'},
        (False, True): {'p', 'w', 'q', 'level', 'left', 'right', 'base'},
        (True, False): {'p', 'w', 'q', 'flag'},
        (True, True): {'p', 'w', 'q', 'flag', 'level', 'left', 'right', 'base'},
    }
    assert structure.expanded(nodes.read('top'), labels=labels, keep=keep) == expected[labels, keep] | (
        {'top'} if keep else set()
    )
    # Each source twice: the second answer comes from what the structure kept, and is the same.
    for source in ('top + reaches', 'round_a', 'round_b * left', 'reaches', 'level + p', 'unknown + 3', 4):
        node = nodes.read(source) if isinstance(source, str) else source
        for _ in range(2):
            assert structure.expanded(node, labels=labels, keep=keep) == walked(GRAPH, source, labels, keep)
    # A formula on a circle keeps its name, with `keep` or without it.
    assert {'round_a', 'p', 'q'} <= structure.expanded(nodes.read('round_a'), labels=labels, keep=keep)
    # From inside a formula, that formula is not followed again.
    inside = structure.expanded(nodes.read('left + base'), labels=labels, keep=keep, seen={'base'})
    assert inside == walked(GRAPH, 'left + base', labels, keep, frozenset({'base'})) and 'base' in inside


def test_the_names_of_an_expression_of_a_structure_are_those_of_its_node_and_a_text_is_refused():
    structure = bare(**GRAPH)
    node = nodes.read('round_a + w * 2')
    assert structure.names(node) == {'round_a', 'w'} and structure.names(2.5) == frozenset()
    assert structure.names(None) == frozenset()
    for read in (structure.names, structure.expanded):
        with pytest.raises(TypeError):
            read('round_a + w * 2')


def test_the_names_through_the_formulas_are_those_of_the_checks_and_of_the_engine(request):
    """What the two consumers ask, on each expression of the fixtures. The checks follow the statuses
    and drop the names on the way: the plain walk of this file gives those names. The engine's system
    follows the statuses too (a status is a formula there) and keeps them: its own walker gives them."""
    seen = 0
    for model, lowered, _ in with_lowerings(request):
        for run, info in model.runs.items():
            # The typed run of the model, and the builder's mapping of its structure for the checks.
            resolved = model.resolve(run)
            mapping = thaw(lowered[info['starts']])
            system = System(resolved, thaw(model.library), NumericalSettings())
            sources = [flow['rate'] for flow in mapping['flows'].values()]
            sources += [item['expr'] for item in mapping['computed'].values()]
            sources += [item['expr'] for item in mapping['outcomes'].values() if 'expr' in item]
            sources += [source for rule in resolved.rules.values() for _, source in rule.sources()]
            sources += list(mapping['labels']) + list(mapping['computed'])
            for source in sources:
                if not isinstance(source, str):
                    continue
                node = nodes.read(source)
                assert resolved.expanded(node, labels=True) == walked(mapping, source, True, False)
                assert checks.expanded(resolved, node) == walked(mapping, source, True, False)
                assert resolved.expanded(node, labels=True, keep=True) == system.expanded_names(node)
                seen += 1
    assert seen > 50


def test_a_structure_says_which_parts_it_leaves_out_and_why():
    """Two stocks start at zero, and nothing changes or reads them: no run can make them act."""
    members = [
        b.stock('w', 5, 'people'),
        b.stock('took', 0, 'people'),
        b.stock('idle', 0, 'people'),
        b.stock('spare', 0, 'people'),
        b.flow('drain', b.move('w', 'took'), b.q(1, 'people/h')),
    ]
    model = b.compiled(b.system(*members))
    lowered, every_part = map(texts, b.lowered(b.system(*members)))
    ((starts, mapping),) = lowered.items()
    reasons = thaw(model.left_out[starts])
    structure = typed.Structure.of(thaw(mapping), left_out=reasons)
    whole = typed.Structure.of(thaw(every_part[starts]))
    assert set(structure.left('quantities')) == {'s.idle', 's.spare'}
    assert set(structure.quantities) == {'s.w', 's.took'} and set(whole.quantities) == {
        's.w',
        's.took',
        's.idle',
        's.spare',
    }
    for section, parts in reasons.items():
        assert dict(structure.left(section)) == parts
        for name, why in parts.items():
            # A part that is left out is in the whole structure, and not in the structure.
            assert name not in structure.section(section) and name in whole.section(section)
            assert isinstance(why, str) and why
    assert dict(structure.left('partitions')) == {} == dict(whole.left('quantities'))
    # The reasons are no part of the builder's mapping, and a structure cannot change them.
    assert same(structure.plain(), unchecked(mapping))
    # The model's structure has the same reasons, and keeps them with the facts of its checks.
    assert typed.thawed(model.structures[starts].left_out) == reasons
    with pytest.raises(TypeError):
        structure.left('quantities')['s.w'] = 'It is not needed.'


# ---- the constructs that few models have -------------------------------------------------------------------

# No fixture and no model of the catalogue has these, so the mappings are written here as the builder
# writes them (`lower/builder.py`: `fact_part`, the range of an input, a sum with no tolerance).
SIGHTS = [
    {'name': 'world.ring', 'event': 'world.ring'},
    {'name': 'world.door', 'expr': 'world.door', 'kind': 'choice', 'values': ['open', 'shut']},
    {'name': 'world.alarm', 'expr': 'world.alarm', 'kind': 'state'},
    {'name': 'world.late', 'expr': 'world.late', 'kind': 'bool'},
    {'name': 'world.level', 'expr': 'world.level', 'kind': 'number', 'unit': 'people'},
    # A number that has no type has no unit, and the builder still writes the key.
    {'name': 'world.count', 'expr': 'world.count', 'kind': 'number', 'unit': None},
]


@pytest.mark.parametrize(
    'sight', SIGHTS, ids=lambda sight: sight.get('kind', 'event') + str(sight.get('unit', ''))
)
def test_each_kind_of_thing_that_an_actor_sees_goes_there_and_back(sight):
    record = typed.Sight.of(sight)
    assert same(record.plain(), sight)
    assert record.values == (tuple(sight['values']) if 'values' in sight else None)
    assert record.unit == sight.get('unit') and record.event == sight.get('event')


def test_a_model_whose_actor_sees_a_named_input_has_typed_parts():
    """An actor sees a named state, a named input, a number and an event. The sight of the named input
    has the input's values; the first form of the typed parts had no field for them."""
    world = b.entity(
        'world',
        b.named('alarm', 'off', 'on'),
        b.block('input door: "open" | "shut" = "open"' + b.cites(b.BASIS)),
        b.stock('level', 0, 'fraction', maximum=1, size=None),
        b.block('event ring once when t >= 1 h:' + b.cites(b.BASIS), 'alarm = "on"'),
    )
    guard = b.entity(
        'guard',
        'sees world.alarm, world.door, world.level, world.ring',
        b.named('order', 'none', 'shut', 'wait'),
        b.block(
            'event decide once when world.alarm is "on":' + b.cites(b.BASIS),
            'choice',
            b.block('shut 0.5:', 'order = "shut"'),
            b.block('wait else:', 'order = "wait"'),
        ),
        role='operator',
    )
    text = b.document('Sight fixture', world, guard)
    model = b.compiled(text)
    (lowered,) = texts(b.lowered(text)[0]).values()
    mapping = checked(lowered, model.structures[()])
    structure = typed.Structure.of(mapping)
    assert same(structure.plain(), mapping) and structure == model.structures[()]
    seen = {sight.name: sight for sight in structure.entities['guard'].sees}
    assert seen['world.door'].kind == 'choice' and seen['world.door'].values == ('open', 'shut')
    assert seen['world.alarm'].kind == 'state' and seen['world.alarm'].values is None
    assert seen['world.level'].unit == 'fraction' and seen['world.ring'].event == 'world.ring'
    # Each value that the actor sees is an expression that reads the value that the file names.
    for name in ('world.alarm', 'world.door', 'world.level'):
        assert nodes.names(seen[name].expr) == {name}
    assert seen['world.ring'].expr is None
    for run in model.runs:
        first = copied(model, mapping, model.resolve(run))
        assert same(typed.Resolved.of(first).plain(), first)
        assert same(model.resolve(run).plain(), first)


def test_a_range_with_records_of_its_own_a_sum_with_no_tolerance_and_a_size_that_is_an_expression():
    basis = {'kind': 'source', 'explanation': 'The limits of the range.', 'name': 'limits'}
    ranged = {'mode': 'range', 'min': 0, 'max': 2.5, 'basis': basis}
    for adjust in (ranged, {'mode': 'range', 'min': 0, 'max': 1}, {'mode': 'locked'}):
        assert same(typed.Adjust.of(adjust).plain(), adjust)
    assert dict(typed.Adjust.of(ranged).basis) == basis and typed.Adjust.of({'mode': 'locked'}).basis is None
    partition = {
        'label': None,
        'parts': ['a', 'b'],
        'total': 'c',
        'tolerance': None,
        'basis': {'kind': 'identity', 'explanation': 'A sum of a test.'},
        'path': 'assert:/0',
    }
    record = typed.Partition.of(partition)
    assert same(record.plain(), partition) and record.tolerance is None and record.label is None
    quantity = {
        'entity': 'e',
        'kind': 'stock',
        'unit': 'people',
        'initial': "q(5, 'people')",
        'basis': {'kind': 'assumption', 'explanation': 'A stock of a test.'},
        'path': 'e/w',
        'min': 0,
        'size': 'e.capacity',
    }
    record = typed.Quantity.of(quantity)
    assert same(record.plain(), quantity) and written(record.size) == 'e.capacity' and record.maximum is None


def test_a_key_that_the_builder_never_writes_is_no_field():
    """The fields are those that the builder can write, and no others: a key of another kind of part,
    or of an older form, is an error."""
    for kind, mapping in (
        (typed.Sight, {'name': 'x', 'path': 'e/x'}),
        (typed.Adjust, {'mode': 'range', 'values': ['a']}),
        (typed.Extra, {'name': 'x', 'kind': 'draw', 'stage': 'fire', 'path': 'e/x'}),
    ):
        with pytest.raises(typed.StructureError, match='has no field'):
            kind.of(mapping)


def test_a_status_as_one_expression_has_the_value_of_its_first_case_that_holds():
    """The engine reads a status as one expression (`label_expression`). For each of the eight ways
    in which three conditions can hold, its value is the value of the first case whose condition
    holds, or the value of the default: the first match is found here by hand."""
    import itertools

    from napkin.engine.continuous.system import label_expression

    cases = [('a.level > 2', 'failed'), ("a.mode == 'slow'", 'degraded'), ('a.level > 1', 'degraded')]
    label = typed.Label.of(
        {
            'entity': 'a',
            'cases': [{'when': when, 'value': value, 'text': value, 'path': 'a'} for when, value in cases],
            'default': {'value': 'ok', 'text': 'ok'},
            'basis': None,
            'path': 'a',
            'label': None,
        }
    )
    status = label_expression(label)
    # One node, whose text reads back to it: a reader of the node and a reader of its text read
    # one expression.
    assert isinstance(status, nodes.Node) and nodes.read(nodes.text(status)) is status
    units = UnitSystem(b.library()['units'])
    seen = set()
    for level, mode in itertools.product((0.5, 1.5, 2.5), ('slow', 'fast')):
        holds = [level > 2, mode == 'slow', level > 1]
        expected = next((value for (_, value), held in zip(cases, holds) if held), 'ok')
        assert evaluate(status, {'a.level': level, 'a.mode': mode}, units) == expected
        seen.add((tuple(holds), expected))
    assert {expected for _, expected in seen} == {'failed', 'degraded', 'ok'} and len(seen) >= 5
