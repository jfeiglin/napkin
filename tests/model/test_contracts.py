"""Independent contract tests: malformed models must never reach numerical execution.

Every case is a small analytic model file from tests/build.py with one deliberate fault, checked
by the code and the place of the diagnostic that rejects it, or a valid neighbour that must compile.
The reader and the builder report a fault in the structure of a file with the codes `syntax`,
`structure` and `build`: a fault of a line's form at its line, any other at the place of its line.
"""

import ast
import copy
import dataclasses
import hashlib
import json
import math
import random
import shutil
import subprocess
import sys

import pytest

import napkin.engine as engine
import napkin.model.compile as compile_module
import napkin.model.evidence as evidence_module
import napkin.model.model as model_module
import napkin.schema as schemas
from napkin import SCHEMA_VERSION
from napkin.core import expr as nodes
from napkin.core import intervals
from napkin.engine import evaluate_study
from napkin.expressions import (
    BOOLEAN,
    ExpressionError,
    UnitSystem,
    compile_expression,
    compile_program,
    domain_prover,
    evaluate,
    infer,
    names_in,
    stock_face_dependencies,
    validate_domains,
)
from napkin.model import ModelError
from napkin.model.analysis import values as value_analysis
from napkin.model.evidence import claim_digest, references
from napkin.model.language import front
from napkin.model.runs import Runs
from napkin.model.semantic import MAIN
from tests.build import (
    block,
    check,
    compiled,
    edit,
    entity,
    event,
    evidence_library,
    flow,
    formula,
    in_place,
    library,
    lowered,
    member,
    output,
    parameter,
    rejected,
    replace,
    sc99,
    scenario,
    share,
    stock,
    system,
)
from tests.build import run as run_of

# The lines of the analytic transfer (`tests.build.scenario`) that the cases change.
N = 'input n: people = 10 people in 1 people to 100 people  @fixture'
END = 'input end: h = 12 h in 1 h to 24 h  @fixture'
STATE = 'var state: "on" | "off" = "on"'
STOCK = 'var stock: people = n size 10 people  @fixture'
SERVED = 'var served: people = 0 size 10 people  @fixture'
DELIVERY = 'let delivery: people/h = rate if state is "on" else 0 people/h  @fixture'
SERVE = 'flow serve: stock -> served at delivery  @fixture'
ALWAYS = 'assert stock + served is n  @fixture'
REQUIRE = 'assert service.end <= 24 h  @fixture'
DELIVERED = 'output delivered: people = service.served  @fixture'
HALF_RATE = 'service.rate = 12 people/day  @fixture'


def serve_at(rate):
    """An edit step: the service serves at `rate`."""
    return replace(SERVE, f'flow serve: stock -> served at {rate}  @fixture')


def transfer(*members):
    """The analytic transfer with more members of its service."""
    return edit(scenario(), member('service', *members))


def with_entity(thing):
    """The analytic transfer with another entity after its service."""
    return edit(scenario(), replace(REQUIRE, f'{thing}\n\n{REQUIRE}'))


def with_outputs(*outputs):
    """The analytic transfer with more top-level outputs after its output `delivered`."""
    delivered = f'{DELIVERED}\n    "Delivered"'
    return edit(scenario(), replace(delivered, '\n'.join([delivered, *outputs])))


def located(text, lib=None):
    """The (code, place) of every diagnostic that rejects a text compiled with `lib`."""
    return rejected(text, lib or library())


def lines_of(text, lib=None):
    """The (code, line) of every diagnostic that rejects a text compiled with `lib`."""
    with pytest.raises(ModelError) as raised:
        compiled(text, lib or library())
    return [(d['code'], d.get('line')) for d in raised.value.diagnostics]


def line_of(text, row):
    """The line number of the row `row` of a text."""
    return text.split('\n').index(row) + 1


def edits(model, **parts):
    """An edit document for the model's revision."""
    return {'schema_version': SCHEMA_VERSION, 'model_hash': model.model_hash, **parts}


def resolve_edits(model, document, runs=None):
    """{run: resolved structure} under one edit document: the admission of a study, which simulates
    nothing. The document's own checks always apply; with no `runs` it resolves every run, with
    `runs` only those runs."""
    return engine.resolve_edits(model, document, runs)


def edit_errors(model, document, lib=None, model_hash=None):
    """The problems of an edit document in the run table of a model, read from its semantic model
    with `lib` (by default the model's library)."""
    runs = Runs.from_scenario(model.scenario, model.library if lib is None else lib)
    return runs.errors(document, model_hash)


# ---- expressions ---------------------------------------------------------------------------------


def formulas(written):
    """{name: node} of formulas that a test writes as texts."""
    return {name: nodes.read(text) for name, text in written.items()}


class Counted(dict):
    """Formulas, {name: node}, that count each read of a formula: a read more than `most` times is
    an assertion that names it."""

    def __init__(self, written, most, why):
        super().__init__(formulas(written))
        self.most, self.why, self.counts = most, why, {}

    def __getitem__(self, name):
        self.counts[name] = self.counts.get(name, 0) + 1
        assert self.counts[name] <= self.most, f'{name!r} {self.why}'
        return super().__getitem__(name)


def test_each_entry_of_the_expressions_takes_a_node_or_a_number_and_refuses_a_text():
    """A text is a TypeError at each entry, and in each place of an entry that takes an expression;
    the node of the same text and a number are taken."""
    units = UnitSystem(library()['units'])
    node, fraction = nodes.read('x + 1'), units.dimension('fraction')
    entries = {
        'compile_expression': lambda source: compile_expression(source, {'x': fraction}, units),
        'an assignment of compile_program': lambda source: compile_program([('y', source)], [], units=units),
        'an output of compile_program': lambda source: compile_program([], [source], units=units),
        'evaluate': lambda source: evaluate(source, {'x': 1.0}, units),
        'names_in': names_in,
        'infer': lambda source: infer(source, {'x': 'fraction'}, units),
        'stock_face_dependencies': lambda source: stock_face_dependencies(
            source, {'x'}, set(), {}, {}, units
        ),
        'a formula of stock_face_dependencies': lambda source: stock_face_dependencies(
            nodes.read('f'), {'x'}, set(), {'f': source}, {}, units
        ),
        'validate_domains': lambda source: validate_domains(source, {'x': (0.0, 1.0)}, units),
        'a formula of validate_domains': lambda source: validate_domains(
            nodes.read('f'), {'x': (0.0, 1.0)}, units, {'f': source}
        ),
        'a formula of domain_prover': lambda source: domain_prover({'x': (0.0, 1.0)}, units, {'f': source}),
        'the function of domain_prover': domain_prover({'x': (0.0, 1.0)}, units),
    }
    for name, entry in entries.items():
        try:
            entry('x + 1')
        except TypeError:
            pass
        else:
            pytest.fail(f'{name} takes a text')
        for taken in (node, 2.5):
            entry(taken)  # neither is an error
    # What each entry gives of a node is what the parts of the language give of it.
    assert names_in(node) == {'x'} and evaluate(node, {'x': 1.5}, units) == 2.5
    assert validate_domains(node, {'x': (0.0, 1.0)}, units) == (1.0, 2.0)
    assert domain_prover({'x': (0.0, 1.0)}, units, {'f': node})(nodes.read('f * 2')) == (2.0, 4.0)


def test_the_check_of_an_expression_has_the_limits_of_size_of_the_text_of_its_node():
    """`compile_expression` refuses a node over a limit of size with the reason of `expr.limited`,
    and the expression that it gives holds the node itself."""
    units = UnitSystem(library()['units'])
    for count, refused in ((996, False), (997, True)):
        # Python's tree of `max(1, 1, …)` has the call, its name and the context of that name, and one
        # part for each argument: 1,000 parts with the tree of the whole text, and 1,001.
        node = nodes.call('max', [nodes.const(1)] * count)
        written = nodes.text(node)
        assert sum(1 for _ in ast.walk(ast.parse(written, mode='eval'))) == count + 4
        if refused:
            with pytest.raises(ExpressionError, match='complexity budget'):
                compile_expression(node, {}, units)
        else:
            assert compile_expression(node, {}, units).source is node
    deep = nodes.ref('a')
    for _ in range(nodes.DEEPEST):
        deep = nodes.unary('neg', deep)
    with pytest.raises(ExpressionError, match='complexity budget'):
        compile_expression(deep, {'a': units.dimension('fraction')}, units)
    # A number is the node of its text: a number below zero is the negation of the number above it.
    for number in (-1.5, 2, True, -0.0):
        assert compile_expression(number, {}, units).source is nodes.read(repr(number))


def test_lazy_execution_and_dimensional_quantities():
    units = UnitSystem(library()['units'])
    expr = compile_expression(
        nodes.read("q(3,'days') if ok else q(1,'h') / zero"),
        {'ok': BOOLEAN, 'zero': units.dimension('fraction')},
        units,
        units.dimension('h'),
    )
    assert expr.evaluate({'ok': True, 'zero': 0}) == 72
    assert compile_expression(nodes.read('False and 1 / 0 > 0'), {}, units).evaluate({}) is False
    assert names_in(nodes.read("max(x, service.state == 'on')")) == {'x', 'service.state'}


@pytest.mark.parametrize(
    'source',
    [
        "q(1,'people') + q(1,'h')",
        "q(1,'people') == q(1,'episodes')",
        "q(1,'USD2024') + q(1,'USD2025')",
        "exp(q(1,'h'))",
        'sqrt(True)',
        "__import__('os')",
        'max(1, ignore=2)',
        "q(2,'h',3)",
        '1/0',
        'ln(-1)',
        "2 ** q(1,'h')",
        '[x for x in (1,2)]',
        "clip('a', 'b', 'c')",
    ],
)
def test_invalid_expressions_fail(source):
    with pytest.raises(ExpressionError):
        compile_expression(nodes.read(source), {}, UnitSystem(library()['units']))


def test_a_negative_literal_exponent_keeps_the_unit_arithmetic_and_the_magnitude_limit():
    units = UnitSystem(library()['units'])
    per_hour = compile_expression(nodes.read("q(2, 'h') ** -1"), {}, units, units.parse_unit('per_h'))
    assert per_hour.evaluate({}) == 0.5
    with pytest.raises(ExpressionError, match='magnitude'):
        compile_expression(nodes.read('x ** -2000'), {'x': units.dimension('fraction')}, units)


@pytest.mark.parametrize(
    ('source', 'ranges', 'aliases'),
    [
        # A computed value that a guard narrows keeps the interval of its definition: c = x >= 1.
        ('sqrt(c) if c < 10 else 0', {'x': (1.0, 2.0)}, {'c': 'x'}),
        # `0 < x` guards as `x > 0` does.
        ('1 / x if 0 < x else 0', {'x': (0.0, 5.0)}, {}),
    ],
)
def test_a_guard_proves_the_branch_that_it_guards(source, ranges, aliases):
    validate_domains(nodes.read(source), ranges, UnitSystem(library()['units']), formulas(aliases))


def test_an_indeterminate_interval_proves_nothing():
    # 1/x - 1/x is inf - inf at the edge of the range: no bound, so the square root is not proven.
    with pytest.raises(ExpressionError, match='sqrt'):
        validate_domains(
            nodes.read('sqrt((1 / x - 1 / x) - 1) if x > 0 else 0'),
            {'x': (0.0, 5e-324)},
            UnitSystem(library()['units']),
        )


@pytest.mark.parametrize(
    ('step', 'low'),
    [
        # Interval addition doubles both bounds: a_k lies in [2^k, 2^(k+1)] for x in [1, 2].
        ('a{p} + a{p}', 2.0**40),
        # A mode test narrows no range, so each branch reads the chain as the ranges give it: the
        # hull of [2L, 2H] and [L, H] is [L, 2H], and a_k lies in [1, 2^(k+1)].
        ("a{p} + a{p} if m == 'open' else a{p}", 1.0),
    ],
)
def test_a_prover_proves_each_formula_once(step, low):
    # a_40 reads a_39 twice, and so on down the chain: proved by expansion alone, it reads a_0 2^40
    # times. The prover reads each formula a few times at most.
    written = {'a0': 'x', **{f'a{k}': step.format(p=k - 1) for k in range(1, 41)}}
    aliases = Counted(written, 3, 'is proved again for each chain that reads it')
    prove = intervals.prover({'x': (1.0, 2.0)}, UnitSystem(library()['units']), aliases)
    assert prove(nodes.read('a40')) == (low, 2.0**41)
    assert aliases.counts.get('a0')  # the counts are those of the proof


def test_a_branch_proves_a_formula_that_does_not_read_its_condition_once():
    # The branch narrows y. The chain over x does not read y, so in the branch it has its interval over
    # the ranges, which the prover proves once: by expansion alone it reads a_0 2^40 times.
    written = {'a0': 'x', **{f'a{k}': f'a{k - 1} + a{k - 1}' for k in range(1, 41)}}
    aliases = Counted(written, 3, 'is proved again in each branch that reads it')
    prove = intervals.prover({'x': (1.0, 2.0), 'y': (-1.0, 1.0)}, UnitSystem(library()['units']), aliases)
    assert prove(nodes.read('a40 + y if y > 0 else 0')) == (0.0, 2.0**41 + 1)
    assert aliases.counts.get('a0')


@pytest.mark.parametrize('condition', ['y * y >= 0', 'y != 0', 'x > 1', 'x * x > 1', 'x != 0'])
def test_refined_branches_prove_a_shared_alias_graph_once(condition):
    # Independent interval arithmetic: repeatedly adding [1, 2] to itself gives [2^40, 2^41].
    # A guarded/nonzero fact, including one relevant to x, must not turn this DAG into 2^40 proofs.
    written = {'a0': 'x', **{f'a{k}': f'a{k - 1} + a{k - 1}' for k in range(1, 41)}}
    aliases = Counted(written, 8, 'is expanded for each path through the alias graph')
    prove = intervals.prover({'x': (1.0, 2.0), 'y': (-1.0, 1.0)}, UnitSystem(library()['units']), aliases)
    low = 2.0**40 if condition == 'x != 0' else 0.0  # x is positive: its false branch is empty.
    assert prove(nodes.read(f'a40 if {condition} else 0')) == (low, 2.0**41)
    assert aliases.counts.get('a0')


def test_refined_alias_memo_keeps_effective_bounds_nonzero_facts_and_failures_separate():
    prove = domain_prover(
        {'x': (-2.0, 2.0), 'y': (-1.0, 1.0)},
        UnitSystem(library()['units']),
        formulas({'twice': 'x + x', 'ratio': '1 / x', 'root': 'sqrt(x)', 'log': 'ln(x)'}),
    )
    assert prove(nodes.read('twice if x >= 1 else 0')) == (0.0, 4.0)
    assert prove(nodes.read('twice if x <= -1 else 0')) == (-4.0, 0.0)
    assert prove(nodes.read('twice')) == (-4.0, 4.0)
    assert prove(nodes.read('ratio if x != 0 else 0')) == (-math.inf, math.inf)
    assert prove(nodes.read('root if x >= 0 else 0')) == (0.0, math.sqrt(2.0))
    assert prove(nodes.read('log if x >= 1 else 0')) == (0.0, math.log(2.0))
    for source in ('ratio', 'ratio if y != 0 else 0', 'root', 'log'):
        with pytest.raises(ExpressionError):
            prove(nodes.read(source))
    # A cached root-domain failure cannot poison a later safe branch either.
    assert prove(nodes.read('ratio if x >= 1 else 0')) == (0.0, 1.0)


def test_refined_alias_memo_keeps_expression_guards_and_impossible_branches():
    prove = domain_prover(
        {'x': (0.0, 2.0), 'y': (0.0, 2.0)},
        UnitSystem(library()['units']),
        formulas({'ratio': '1 / (x - y)', 'twice': 'x + x'}),
    )
    assert prove(nodes.read('ratio if x - y >= 1 else 0')) == (0.0, 1.0)
    assert prove(nodes.read('ratio if x - y != 0 else 0')) == (-math.inf, math.inf)
    with pytest.raises(ExpressionError, match='nonzero denominator'):
        prove(nodes.read('ratio if x + y >= 1 else 0'))
    assert prove(nodes.read('twice if x > 3 else 0')) == (0.0, 0.0)
    assert prove(nodes.read('twice')) == (0.0, 4.0)


@pytest.mark.parametrize('chain', [{'d': 'y'}, {'d': 'e + 0', 'e': 'y'}])
def test_a_branch_narrows_the_formulas_that_read_its_condition(chain):
    # x / d divides by y, through one formula or two. Over the ranges y can be 0, so x / d alone is not
    # proved; in the branch where y > 0 it is, because every formula that reads y reads its narrowed
    # interval there.
    units = UnitSystem(library()['units'])
    prove = domain_prover({'x': (1.0, 2.0), 'y': (0.0, 10.0)}, units, formulas({**chain, 'r': 'x / d'}))
    with pytest.raises(ExpressionError, match='nonzero denominator'):
        prove(nodes.read('r'))
    low, high = prove(nodes.read('r if y > 0 else 0'))
    assert low == 0.0 and high == math.inf


def test_a_formula_met_again_on_its_own_chain_has_no_bound_on_that_chain():
    # From a: a = min(b, 5), b = max(a, 1), and a again has no bound, so b is [1, inf] and a is
    # [1, 5]. From b, a is [-inf, 5] and b is [1, 5]. The sum is [2, 10]; with the interval of b
    # read on the chain from a, it would be [2, inf].
    prove = domain_prover({}, UnitSystem(library()['units']), formulas({'a': 'min(b, 5)', 'b': 'max(a, 1)'}))
    assert prove(nodes.read('a + b')) == (2.0, 10.0)


def test_a_formula_that_fails_its_proof_fails_each_expression_that_reads_it():
    prove = domain_prover({'x': (0.0, 1.0)}, UnitSystem(library()['units']), formulas({'d': '1 / x'}))
    for source in ('d + 1', '2 * d'):
        with pytest.raises(ExpressionError, match='nonzero denominator'):
            prove(nodes.read(source))


# ---- the compiled model --------------------------------------------------------------------------


def test_immutability_content_hash_and_canonical_values():
    lib = library()
    model = compiled(scenario(), lib)
    with pytest.raises(TypeError):
        model.inputs['service.n']['value'] = 100
    assert model.resolve('a').values['service.n'] == 10
    # Execution units: 24 people/day is one person an hour; run b's profile, 12 people/day, is half.
    assert model.resolve('a').values['service.rate'] == 1
    assert model.resolve('b').values['service.rate'] == 0.5
    resolved = model.resolve('a')
    # The run cannot change. It shares the parts of the structure with every resolution of it, so
    # they cannot change either: a caller that wants to change a copy makes one (`plain`).
    assert resolved.parameters is model.structure_of('a').parameters
    with pytest.raises(dataclasses.FrozenInstanceError):
        resolved.parameters['service.n'].value = 13
    with pytest.raises(TypeError):
        del resolved.rules[next(iter(resolved.rules))]
    with pytest.raises(TypeError):
        resolved.rules['service.new'] = None
    own = resolved.plain()
    own['parameters']['service.n']['value'] = 13
    own['rules'].clear()
    assert resolved.parameters['service.n'].value == 10 and resolved.rules
    assert resolved.plain()['parameters']['service.n']['value'] == 10
    assert model.resolve('a').values['service.n'] == 10
    # The hash covers the units that the model uses: people/day, not days.
    lib['units']['days']['scale'] = 25
    assert compiled(scenario(), lib).model_hash == model.model_hash
    lib['units']['people/day']['scale'] = 1 / 25
    assert compiled(scenario(), lib).model_hash != model.model_hash


def test_implementation_identity_names_loaded_code_and_keeps_saved_inputs_valid(tmp_path, monkeypatch):
    """Implementation bytes have their own identity; authored input identity survives code edits."""
    before = compiled(scenario())
    shutil.copytree(compile_module.PACKAGE / 'model', tmp_path / 'model')
    shutil.copytree(compile_module.PACKAGE / 'engine', tmp_path / 'engine')
    (tmp_path / 'engine/runtime.py').write_text('# not the code that runs\n', encoding='utf-8')
    monkeypatch.setattr(compile_module, 'PACKAGE', tmp_path)
    assert compiled(scenario()).model_hash == before.model_hash
    assert compiled(scenario()).implementation_hash == before.implementation_hash
    monkeypatch.setitem(compile_module.CODE_DIGEST, 'engine/runtime.py', '0' * 64)
    changed = compiled(scenario())
    assert changed.model_hash == before.model_hash
    assert changed.implementation_hash != before.implementation_hash
    assert edit_errors(changed, edits(before), model_hash=changed.model_hash) == []


# ---- invalid models ------------------------------------------------------------------------------


@pytest.mark.parametrize(
    'mutate,expected',
    [
        (
            lambda t: edit(t, replace(STOCK, 'var stock: unregistered = n size 10 people  @fixture')),
            ('build', 'service/stock'),
        ),
        (
            lambda t: edit(t, replace(N, 'input n: people = -1 people in 1 people to 100 people  @fixture')),
            ('bounds', 'values/service.n'),
        ),
        (
            lambda t: edit(t, replace(HALF_RATE, 'service.rate = 1000 people/day  @fixture')),
            ('bounds', 'values/service.rate'),
        ),
        # Options of two groups never set one input.
        (
            lambda t: edit(t, member('options:/Response/Default', 'service.rate = 20 people/day  @fixture')),
            ('structure', 'options:/Response/Default/service.rate'),
        ),
        (
            lambda t: edit(
                t, replace(N, 'input n: people = 10 people in 200 people to 100 people  @fixture')
            ),
            ('bounds', 'service/n/adjust'),
        ),
        (
            lambda t: edit(t, replace(STATE, 'var state: "on" | "off" = "missing"')),
            ('build', 'service/state'),
        ),
    ],
)
def test_invalid_models_fail(mutate, expected):
    assert expected in located(mutate(scenario()))


@pytest.mark.parametrize('written', ['nan', '1e999 people'], ids=['nan', 'inf'])
def test_nonfinite_authored_value_is_a_model_error(written):
    """A number that is not finite is rejected with diagnostics: a file writes no NaN, and a number
    too large to be finite is an error of its line."""
    with pytest.raises(ModelError):
        compiled(
            edit(scenario(), replace(N, f'input n: people = {written} in 1 people to 100 people  @fixture')),
            library(),
        )


def test_independent_faults_are_all_reported():
    """Checks collect every independent fault of one phase instead of stopping at the first."""
    text = edit(
        scenario(),
        replace(DELIVERY, 'let delivery: people/h = n + end  @fixture'),
        replace(SERVED, 'var served: people = 0 in 5 people to 1 people size 10 people  @fixture'),
    )
    found = located(text)
    assert ('expression', 'service/delivery/expr') in found
    assert ('bounds', 'service/served') in found


def test_computed_and_outcome_cycles_rejected_but_rate_feedback_allowed():
    text = edit(scenario(), replace(DELIVERY, 'let delivery: people/h = delivery  @fixture'))
    assert ('cycle', 'computed') in located(text)
    text = edit(scenario(), replace(DELIVERED, 'output delivered: people = delivered  @fixture'))
    assert ('cycle', 'outcomes') in located(text)
    # A number whose rate reads itself is an ODE, not a cycle.
    level = stock('level', 1, 'fraction', minimum=None, size=1)
    compiled(edit(scenario(), member('service', level, flow('decay', 'level ->', 'level / 2 h'))), library())


def test_delays_and_initial_bounds():
    text = edit(scenario(), member('output:/delivered', 'lag uniform(2 h, 1 h)'))
    assert ('lag', 'outcomes/delivered') in located(text)
    text = edit(scenario(), replace(STOCK, 'var stock: people = -n size 10 people  @fixture'))
    assert ('initial_bound', 'service/stock') in located(text)
    # A stock never goes below 0. A number state, which no flow or move joins, has no such bound:
    # it can start below zero.
    compiled(transfer(stock('mark', -5, 'people', minimum=None, size=10, kind='state')), library())


def test_an_output_with_a_lag_is_read_as_any_number_from_zero_and_not_as_its_formula():
    """An output with a reporting lag has the value 0 until its lag has passed, whatever its formula
    gives. `waited` is `t + 5 h`, which is never below 5 h, so an output that divides by it is
    proved. With a lag of 2 h, `waited` is 0 for the first 2 h: the same division has no proof, and
    the model is refused at that output."""

    def reading(lag):
        text = scenario()
        waited = output('waited', 't + 5 h', 'h', doc='Waited', under=(('lag 2 h',) if lag else ()))
        share = output('share', '5 h / waited', 'fraction', 'level', doc='Share')
        assert text.count('\noptions "Response":') == 1
        return text.replace('\noptions "Response":', f'\n{waited}\n\n{share}\n\noptions "Response":')

    compiled(reading(False), library())
    assert ('output_domain', 'outcomes/share/expr') in located(reading(True))


# ---- level triggers ------------------------------------------------------------------------------


def milestone(name, when):
    """An event of the service that changes nothing and happens once, when `when` first holds."""
    return event(name, when, doc=name.capitalize())


def test_crossing_classes_admit_constant_rates_and_reject_unproven_fields():
    # The stock and the served count move at a constant rate in each state: affine crossings.
    milestones = (milestone('empty', 'stock <= 0'), milestone('half', 'served >= 5 people'))
    compiled(transfer(*milestones), library())
    # A source-proportional flow decays exponentially, but the stock only falls and the tally only
    # rises between moments: monotone crossings.
    decaying = compiled(edit(transfer(*milestones), serve_at('stock / 2 h')), library()).resolve('a')
    assert list(decaying.proven_monotone_crossings) == ['service.empty', 'service.half']
    # A second flow fills the stock at a rate that reads it: no proof says which way it moves.
    refill = flow('refill', '-> stock', 'served / 4 h')
    text = edit(transfer(*milestones, refill), serve_at('stock / 2 h'))
    assert ('unsupported_condition', 'service/empty/when:') in located(text)
    # One event may watch only one evolving number.
    text = transfer(milestone('both', 'stock <= 5 people and served >= 5 people'))
    assert ('unsupported_condition', 'service/both/when:') in located(text)


def test_held_numeric_quantity_is_a_discrete_rule_input():
    notice = milestone('notice', 'flag is 1')
    compiled(transfer(stock('flag', 0, 'fraction', minimum=None, size=1, kind='state'), notice), library())
    # Once the flag evolves, an equality on it is no crossing the compiler can locate.
    flag = stock('flag', 0, 'fraction', minimum=None, size=1, kind='state', rate='1 / 1 h')
    assert ('unsupported_condition', 'service/notice/when:') in located(transfer(flag, notice))


# ---- parts that every run leaves out, and names --------------------------------------------------


def spare(log, *more):
    """The analytic transfer with an entity that no run can use: none of its parts can act, and
    nothing that acts reads it. Its formula `log` reads the service's input."""
    return with_entity(
        entity('spare', formula('log', log, 'fraction'), *more, doc='A spare record that no run uses.')
    )


def test_parts_that_every_run_leaves_out_are_validated():
    """Every structure leaves the spare entity out; its parts are still checked, and the diagnostic
    names the line of the faulty part."""
    valid = compiled(spare('ln(service.n / 1 people)'), library())
    assert all('spare' in left['entities'] for left in valid.left_out.values())
    text = spare('ln(service.n / 1 people)', formula('bad', 'typo', 'people'))
    assert ('build', 'spare/bad') in located(text)
    found = located(spare('ln(-service.n / 1 people)'))
    assert ('dynamic_domain', 'spare/log') in found


@pytest.mark.parametrize(
    'declaration',
    [
        'let n = [service]',
        block('event n:', 'state = "off"'),
        'event n once when t >= end:  @fixture',
    ],
    ids=[
        'links-Service-classes/Service/fields/n',
        'methods-member1-classes/Service/methods/n',
        'policy-member2-classes/Service/policy/n',
    ],
)
def test_a_name_is_declared_once_in_its_class(declaration):
    """A value, a link and an event (one that a line names, or one with a `when`) of one entity never
    share a name: the line that declares the name a second time is rejected."""
    text = edit(scenario(), member('service', declaration))
    assert ('syntax', line_of(text, '    ' + declaration.split('\n')[0])) in lines_of(text)


def test_another_class_declares_its_own_fields():
    """Names are qualified by their entity: the same definition in another entity is another input."""
    other = entity('other', parameter('n', 10, 'people', 1, 100, doc='People'), doc='Another part.')
    assert {'service.n', 'other.n'} <= set(compiled(with_entity(other), library()).inputs)


# ---- edits ---------------------------------------------------------------------------------------


def test_edit_bounds_and_revision_are_checked_for_every_run():
    model = compiled(scenario(), library())
    document = edits(model, set={'service.n': 20}, runs={'b': {'service.rate': 48}})
    resolved = resolve_edits(model, document)
    assert resolved['a'].values['service.n'] == 20
    assert resolved['b'].values['service.rate'] == 2
    document['runs']['b']['service.rate'] = 49
    with pytest.raises(ModelError) as raised:
        resolve_edits(model, document, ['a'])
    # Diagnostics name the edit's location in the edit document, which names the run it reaches.
    assert [(d['code'], d['path']) for d in raised.value.diagnostics] == [
        ('bounds', 'edits/runs/b/service.rate')
    ]
    with pytest.raises(ModelError) as raised:
        resolve_edits(model, {'schema_version': SCHEMA_VERSION, 'model_hash': 'stale'})
    assert {d['code'] for d in raised.value.diagnostics} == {'model_hash'}
    # An edit changes inputs only: the start value of a stock is for a profile to set.
    with pytest.raises(ModelError) as raised:
        resolve_edits(model, edits(model, set={'service.stock': 1}))
    assert {(d['code'], d['path']) for d in raised.value.diagnostics} == {
        ('input', 'edits/set/service.stock')
    }


def test_edited_initial_domains_are_validated_for_a_hidden_run():
    log_rate = formula('log_rate', 'ln((rate - 12 people/day) / 1 people/day)', 'fraction')
    text = edit(transfer(log_rate), replace(HALF_RATE, 'service.rate = 24 people/day  @fixture'))
    model = compiled(text, library())
    document = edits(model, runs={'b': {'service.rate': 12}})
    with pytest.raises(ModelError) as raised:
        resolve_edits(model, document)
    assert ('dynamic_domain', 'service/log_rate', 'b') in {
        (d['code'], d['path'], d.get('run')) for d in raised.value.diagnostics
    }
    # The edit is one transaction over every run; a study of the untouched run alone resolves that run
    # only, and admits it.
    assert set(resolve_edits(model, document, ['a'])) == {'a'}


def test_a_fixed_value_is_locked_at_every_level():
    """A fixed value is its own effective value: a run's own value is no change and another value
    changes a locked value; no profile sets it, and no edit changes it, even to its own value."""
    text = edit(scenario(), replace(END, 'let end: h = 6 h  @fixture'))
    model = compiled(text, library())
    assert model.resolve('a', {'service.end': 6}).parameter_values['service.end'] == 6
    with pytest.raises(ModelError) as raised:
        model.resolve('a', {'service.end': 12})
    assert {(d['code'], d['path']) for d in raised.value.diagnostics} == {('locked', 'values/service.end')}
    for level, path in (
        ({'set': {'service.end': 6}}, 'edits/set/service.end'),
        ({'options': {'Half rate': {'service.end': 6}}}, 'edits/options/Half rate/service.end'),
        ({'runs': {'a': {'service.end': 6}}}, 'edits/runs/a/service.end'),
    ):
        with pytest.raises(ModelError) as raised:
            resolve_edits(model, edits(model, **level))
        assert [(d['code'], d['path']) for d in raised.value.diagnostics] == [('locked', path)]
    profiled = edit(text, member('options:/Rate/Half rate', 'service.end = 6 h  @fixture'))
    assert ('structure', 'options:/Rate/Half rate/service.end') in located(profiled)


def class_option():
    """The analytic transfer whose service is an instance of the template Service, and the name of an
    option line that sets a value of every instance of the template."""
    text = edit(
        scenario(),
        replace('\nservice:  @fixture', '\nService:  @fixture'),
        replace(REQUIRE, f'service: Service\n\n{REQUIRE}'),
    )
    return text, 'Service'


def entity_option():
    """The analytic transfer, and the name of an option line that sets a value of the service."""
    return scenario(), 'service'


@pytest.mark.parametrize(
    'option,path',
    [
        (class_option, 'options:/Rate/Half rate/Service.unknown_parameter'),
        (entity_option, 'options:/Rate/Half rate/service.unknown_parameter'),
    ],
    ids=[
        'class_option-classes/Service/options/Half rate',
        'entity_option-simulate/entities/service/options/Half rate',
    ],
)
def test_unknown_field_of_an_authored_option_has_structured_diagnostic(option, path):
    text, owner = option()
    text = edit(text, member('options:/Rate/Half rate', f'{owner}.unknown_parameter = 1  @fixture'))
    assert ('structure', path) in located(text)


def test_default_resolutions_are_validated_once_and_handed_out_as_copies(monkeypatch):
    calls = []
    original = model_module.resolve_structure

    def counted(structure, source, lib, values, context, **options):
        calls.append(context)
        return original(structure, source, lib, values, context, **options)

    monkeypatch.setattr(model_module, 'resolve_structure', counted)
    model = compiled(scenario(), library())
    # Each run is resolved once with its authored values; run b takes the rate of its profile.
    assert sorted(calls) == ['runs/a', 'runs/b']
    calls.clear()
    first = model.resolve('a')
    # The run cannot change. A caller can write only to the plain data that the run writes for it.
    with pytest.raises(TypeError):
        first.parameter_values['service.rate'] = -1
    first.plain()['parameter_values']['service.rate'] = -1
    assert first.parameter_values['service.rate'] == 24
    assert model.resolve('a').parameter_values['service.rate'] == 24
    assert resolve_edits(model, edits(model))['b'].parameter_values['service.rate'] == 12
    assert calls == []
    changed = resolve_edits(model, edits(model, set={'service.n': 20}))
    assert changed['a'].parameter_values['service.n'] == 20 and sorted(calls) == ['runs/a', 'runs/b']


def test_a_model_that_resolved_other_values_before_gives_what_checks_that_keep_nothing_give(monkeypatch):
    """A model keeps the proofs of a structure from one set of values to the next
    (`analysis.values.Proofs`). The definition of each resolution is the same resolution with
    nothing kept: the same result or the same diagnostics. The second model of the test is that
    definition: while it resolves, no prover is kept from the resolutions before.

    The formulas of the fixture read two inputs through one another, so that a change of one input
    changes a part of the proofs. `room` is 0 where the two inputs are equal (the division is
    refused) and below 0 where `load` is above `cap` (the logarithm is refused). An event writes a
    held value from a formula, and an event reads a value of the past."""
    text = transfer(
        parameter('cap', 30, 'people', 1, 100, doc='Places'),
        parameter('load', 5, 'people', 0, 100, doc='Places taken'),
        formula('room', 'cap - load', 'people'),
        formula('pace', 'rate * 10 people / room', 'people/h'),
        formula('depth', 'ln(n / 1 people)', 'fraction'),
        formula('spread', 'ln(room / 1 people) + depth', 'fraction'),
        stock('mark', 0, 'people', minimum=None, size=10, kind='state'),
        stock('seen', 0, 'people', minimum=None, size=10, kind='state'),
        event('note', 't >= 2 h', 'mark = pace * 1 h + spread * 1 people'),
        event('look', 't >= 6 h', 'seen = delayed(served, 3 h) + mark'),
    )
    keeping, plain = compiled(text, library()), compiled(text, library())

    def answer(model, run, values):
        try:
            return model.resolve(run, values).plain()
        except ModelError as exc:
            return exc.diagnostics

    rng = random.Random(20261115)
    names = ('service.cap', 'service.load', 'service.n', 'service.rate')
    lows, highs = (1, 0, 1, 1), (100, 100, 100, 48)
    outcomes = {'resolved': 0, 'refused': 0}
    for k in range(40):
        values = {}
        for name, low, high in zip(names, lows, highs):
            if rng.random() < 0.5:
                values[name] = rng.randrange(low, high + 1)
        if k % 5 == 0:
            values['service.load'] = values['service.cap'] = rng.randrange(1, 101)
        run = rng.choice('ab')
        found = answer(keeping, run, values)
        with monkeypatch.context() as patch:
            patch.setattr(value_analysis.Proofs, 'kept', lambda self, aliases, library: None)
            assert found == answer(plain, run, values), (run, values)
        outcomes['resolved' if isinstance(found, dict) else 'refused'] += 1
    assert outcomes['resolved'] >= 10 and outcomes['refused'] >= 10, outcomes


# ---- checks --------------------------------------------------------------------------------------


def test_checks_before_a_run_read_static_values_only():
    # An assert that reads only inputs and the formulas of inputs is a check before the run.
    static = formula('static', 'n / 1 people', 'fraction')
    model = compiled(
        edit(transfer(static), replace(REQUIRE, 'assert service.static > 0  @fixture')), library()
    )
    assert list(model.structure_of('a').input_checks) == [f'{MAIN}.0']


def rationing(name):
    return share('stock', 'rate')


def test_competing_withdrawals_need_one_allocation_policy():
    second = flow('second', 'stock ->', 'rate')
    assert ('allocation', 'service/stock') in located(transfer(second))
    # Two shares still leave the scarce stock without one policy: each one covers every flow that
    # draws on the stock, and the second is rejected at its line.
    text = transfer(second, rationing('one'), rationing('two'))
    rows = [k + 1 for k, row in enumerate(text.split('\n')) if row.strip() == rationing('two')]
    assert ('syntax', rows[1]) in lines_of(text)
    compiled(transfer(second, rationing('shared')), library())


def test_source_proportional_competing_hazards_need_no_allocation_policy():
    # Each rate vanishes with its source, so the stock can never be overdrawn.
    text = edit(transfer(flow('second', 'stock ->', 'stock / 3 h')), serve_at('stock / 2 h'))
    compiled(text, library())


# ---- outcome proofs ------------------------------------------------------------------------------


def ratio(expression):
    # The ratio claims no sign: an output says `signed` unless it is never negative.
    return with_outputs(
        output(
            'ratio',
            expression,
            'fraction',
            'instantaneous',
            doc='Ratio',
            under=('scope "Contract"', 'signed'),
        )
    )


@pytest.mark.parametrize(
    'unsafe,guarded',
    [
        ('service.n / service.stock', 'service.n / service.stock if service.stock > 0 else 0'),
        ('ln(service.stock / 1 people)', 'ln(service.stock / 1 people) if service.stock > 0 else 0'),
    ],
    ids=[
        'service.n / service.stock-service.n / service.stock if service.stock > 0 else 0',
        "ln(service.stock / q(1, 'people'))-ln(service.stock / q(1, 'people')) if service.stock > 0 else 0",
    ],
)
def test_outcome_domains_are_proved_between_samples_and_lazy_guards_are_supported(unsafe, guarded):
    # The stock empties at 10 h, between the reporting samples at 0 h and 24 h.
    assert ('output_domain', 'outcomes/ratio/expr') in located(ratio(unsafe))
    compiled(ratio(guarded), library())


def test_nonnegative_annotation_cannot_hide_negative_interior():
    # An output that does not say `signed` claims that it is never negative.
    bad = output(
        'bad',
        '(t / 1 h - 5) * (t / 1 h - 6)',
        'fraction',
        'instantaneous',
        doc='Invalid sign',
        under=('scope "Sign proof"',),
    )
    # Positive at both endpoints, negative between hours 5 and 6.
    assert ('nonnegative_proof', 'outcomes/bad') in located(with_outputs(bad))


def test_cumulative_annotation_rejects_depleting_stock_and_negative_effect():
    text = edit(scenario(), replace(DELIVERED, 'output delivered: people = service.stock  @fixture'))
    assert ('cumulative_proof', 'outcomes/delivered') in located(text)
    text = edit(scenario(), member('service/stop', 'served = served - 1 people'))
    assert ('cumulative_proof', 'outcomes/delivered') in located(text)


@pytest.mark.parametrize(('fills', 'takes'), [(2, 1), (1, 2), (3, 3)])
def test_an_output_that_adds_and_takes_away_filled_tallies_is_cumulative_by_the_sign_of_its_rate(
    fills, takes
):
    """The output `a - b` of two tallies that fill from outside, `a` at `fills` people an hour and `b`
    at `takes`: its rate is fills - takes. It never falls when that rate is not negative, and the
    claim that it is cumulative is refused otherwise."""
    text = system(
        stock('a', 0, kind='tally', rate=f'{fills} people/h'),
        stock('b', 0, kind='tally', rate=f'{takes} people/h'),
        outputs=(output('net', 's.a - s.b', 'people', under=('signed',)),),
    )
    if fills >= takes:
        assert 'net' in compiled(text, library()).resolve('a').proven_cumulative_outcomes
    else:
        assert ('cumulative_proof', 'outcomes/net') in located(text)


def test_an_output_whose_coefficient_overflows_is_not_proved_cumulative():
    """`1e200 * (1e200 * a)` has the factor 1e400 on a tally that fills: no float holds it, so the
    proof has no number for it and proves nothing."""
    text = system(
        stock('a', 0, kind='tally', rate='1 people/h'),
        outputs=(output('big', '1e200 * (1e200 * s.a)', 'people'),),
    )
    assert ('cumulative_proof', 'outcomes/big') in located(text)


def test_a_tally_that_flows_fill_from_outside_has_the_sum_of_their_rates():
    """Three flows fill one tally from outside: 1 and 2 people an hour, and 0.5 from 2 h. After 10 h
    it holds 1 * 10 + 2 * 10 + 0.5 * 8 = 34 people."""
    text = system(
        stock('served', 0, kind='tally', size=100),
        flow('one', '-> served', '1 people/h'),
        flow('two', '-> served', '2 people/h'),
        flow('late', '-> served', '0.5 people/h', condition='t >= 2 h'),
        horizon=10,
    )
    _, trajectory = run_of(text)
    assert trajectory.env_at(10)['s.served'] == pytest.approx(34, rel=1e-9)


def copied(name, count, watched='w'):
    """A system whose event copies the greatest of `count` reads of the stock `name` into `y` when
    the stock `watched` is above zero: the step reads the condition and the value."""
    reads = ', '.join([name] * count)
    return system(
        stock(name, 5, size=10),
        stock(watched, 5, size=10),
        stock('y', 0, size=10),
        event('grab', f'{watched} > 0 people', f'y = max({reads})', once=True),
        horizon=4,
    )


def guarded_text(text):
    """The text of the step of `grab` under its condition, `(condition) and (value)`, from the texts
    of the two expressions of the lowering, and the texts of the two."""
    (mapping,) = lowered(text, library())[0].values()
    rule = mapping['rules']['s.grab']
    (outcome,) = rule['outcomes']
    when, value = (
        nodes.text(source) for source in (rule['trigger']['when'], outcome['do']['set']['s.y']['expr'])
    )
    return f'({when}) and ({value})', when, value


def size(written):
    """The characters of a text, and the parts of Python's tree of it with the tree of the whole text."""
    return len(written), sum(1 for _ in ast.walk(ast.parse(written, mode='eval')))


def guard_problems(text):
    try:
        compiled(text, library())
    except ModelError as exc:
        return [d['message'] for d in exc.diagnostics if d['code'] == 'rule_domain']
    return []


def test_a_step_under_its_condition_has_the_limits_of_size_of_one_expression():
    """A step of an event that fires at once is proved where its condition holds: the proof reads
    the condition and the value as one expression, `(condition) and (value)`, with the limits of
    size of one expression. Here each of the two is inside the limits, and their text together is on
    one side or the other of the limit of the parts of Python's tree, or of the characters."""
    # The parts: the value reads the stock 248 times, or 240 times.
    for count, over in ((248, True), (240, False)):
        together, when, value = guarded_text(copied('x', count))
        assert all(
            found <= limit for alone in (when, value) for found, limit in zip(size(alone), (10000, 1000))
        )
        # `read` counts the parts of the tree of the expression, without the tree of the whole text.
        assert (size(together)[1] - 1 > 1000) is over and size(together)[0] < 10000
        problems = guard_problems(copied('x', count))
        assert problems == (['Expression exceeds complexity budget'] if over else [])
    # The characters: a long name read 39 times, and a stock in the condition whose name has as many
    # letters as take the text together to 10,001 characters, or to 10,000.
    name = 'x' * 240
    _, when, value = guarded_text(copied(name, 39))
    room = 10000 - len(f'({when}) and ({value})')
    assert room > 0
    for extra, over in ((room + 1, True), (room, False)):
        text = copied(name, 39, 'w' * (1 + extra))
        together, when, value = guarded_text(text)
        assert all(
            found <= limit for alone in (when, value) for found, limit in zip(size(alone), (10000, 1000))
        )
        assert len(together) == (10001 if over else 10000) and size(together)[1] < 1000
        assert guard_problems(text) == (['Expression exceeds 10000 characters'] if over else [])


def test_cumulative_quantity_cannot_disable_its_contract():
    # A tally never falls; the language has no key that turns its contract off.
    text = edit(scenario(), member('service/served', 'non_decreasing: false'))
    assert ('syntax', line_of(text, '        non_decreasing: false')) in lines_of(text)


def capped(expression):
    # The capped terms exercise the monotonicity proof; they are not a head count of distinct people.
    distinct = block('distinct', in_place('identity', 'Proof fixture, not a head count.'))
    return edit(
        scenario(),
        replace(DELIVERED, f'output delivered: people = {expression}  @fixture'),
        member('output:/delivered', distinct),
    )


def test_sum_of_capped_cumulative_quantities_is_proved():
    compiled(capped('min(service.served, 3 people) + max(service.served, 2 people)'), library())


@pytest.mark.parametrize(
    'expression',
    (
        'min(service.served, 3 people) + min(service.stock, 2 people)',
        'min(service.served, 3 people) - max(service.served, 2 people)',
        'min(service.served, 3 people) + min(-service.served, 2 people)',
    ),
    ids=[
        "min(service.served, q(3, 'people')) + min(service.stock, q(2, 'people'))",
        "min(service.served, q(3, 'people')) - max(service.served, q(2, 'people'))",
        "min(service.served, q(3, 'people')) + min(-service.served, q(2, 'people'))",
    ],
)
def test_capped_cumulative_composition_rejects_decreasing_operand(expression):
    assert ('cumulative_proof', 'outcomes/delivered') in located(capped(expression))


def test_scaled_and_named_caps_of_cumulative_quantities_are_proved():
    # A fixed nonnegative factor keeps a nondecreasing term nondecreasing, and a formula stands for its
    # expression.
    compiled(capped('2 * max(service.served, 2 people) + service.served'), library())
    worst = member('service', formula('worst', 'max(served, 2 people)', 'people'))
    compiled(edit(capped('service.worst / 2 + service.served'), worst), library())


@pytest.mark.parametrize(
    'expression',
    (
        '-2 * max(service.served, 2 people) + service.served',
        'max(service.served, 2 people) * service.stock / 1 people',
    ),
    ids=['negative factor', 'factor that moves'],
)
def test_a_factor_that_can_reverse_a_cap_is_rejected(expression):
    assert ('cumulative_proof', 'outcomes/delivered') in located(capped(expression))


def test_pending_fatal_mass_proved_nonnegative_without_claiming_monotonicity():
    delayed = output('delayed', 'delivered', 'people', doc='Delayed', under=('lag 2 h',))
    compiled(
        with_outputs(delayed, output('pending', 'delivered - delayed', 'people', 'level', doc='Pending')),
        library(),
    )
    pending = output('pending', 'delivered - delayed', 'people', doc='Pending')
    assert ('cumulative_proof', 'outcomes/pending') in located(with_outputs(delayed, pending))


def test_positive_lag_does_not_make_occurrence_exceed_incidence():
    text = with_outputs(
        output('initial_incidence', 'service.n', 'people', doc='Delivered'),
        output('occurrence', 'initial_incidence', 'people', doc='Delivered', under=('lag 2 h',)),
        output('wrong_difference', 'occurrence - initial_incidence', 'people', 'level', doc='Delivered'),
    )
    assert ('nonnegative_proof', 'outcomes/wrong_difference') in located(text)


@pytest.mark.parametrize('leak', [False, True])
def test_balanced_transfers_prove_unique_cumulative_population(leak):
    """Served people fall ill at a rate proportional to the served stock. Every person is counted
    once, in one sum check; while the outflow stays inside the counted parts, their sum never
    decreases. Moving people to an uncounted part breaks the proof."""
    text = edit(
        scenario(),
        # The served people move on, so they are a stock, not a tally: the flow `recover` takes from them.
        replace(ALWAYS, 'assert stock + served + ill + left is n  @fixture'),
        member(
            'service',
            *(stock(name, 0, size=10) for name in ('ill', 'left')),
            flow('recover', f'served -> {"left" if leak else "ill"}', 'served / 2 h'),
            check(
                'stock + served + ill + left is n',
                'Every person is in one part.',
                within='0.001 people',
            ),
        ),
        replace(DELIVERED, 'output delivered: people = service.served + service.ill  @fixture'),
    )
    if leak:
        assert ('cumulative_proof', 'outcomes/delivered') in located(text)
    else:
        compiled(text, library())


# ---- evidence and the library --------------------------------------------------------------------


def test_evidence_content_digest_detects_changed_claim():
    lib = evidence_library()
    compiled(sc99(), lib)
    lib['claims'][0]['shows'] = 'A different fact.'
    assert ('evidence_digest', f'claims/{lib["claims"][0]["id"]}') in rejected(sc99(), lib)


def test_library_checks_run_once_per_content_and_edits_keep_the_imported_schema(monkeypatch, tmp_path):
    calls = []
    original = evidence_module.validate_library
    monkeypatch.setattr(evidence_module, 'validate_library', lambda lib: calls.append(1) or original(lib))
    monkeypatch.setattr(evidence_module, '_CHECKED', {})
    lib = library()
    compiled(scenario(), lib)
    compiled(scenario(), copy.deepcopy(lib))
    assert calls == [1]
    verification = {'status': 'unverified', 'date': '2026-09-17', 'method': 'fixture', 'notes': 'Fixture'}
    source = {'id': 's', 'title': 'Fixture', 'custom': {'verification': {**verification}}}
    lib['sources'] = [source, copy.deepcopy(source)]
    with pytest.raises(ModelError) as raised:
        compiled(scenario(), lib)
    assert {d['code'] for d in raised.value.diagnostics} == {'duplicate_id'}
    # Validators use the same imported bytes as the implementation identity.
    shutil.copytree(schemas.FOLDER, tmp_path / 'schema')
    monkeypatch.setattr(schemas, 'FOLDER', tmp_path / 'schema')
    model = compiled(scenario(), library())
    assert edit_errors(model, edits(model, set={'service.n': 20}), library()) == []
    path = tmp_path / 'schema/edits.schema.json'
    schema = json.loads(path.read_text())
    schema['required'] = [*schema['required'], 'absent_field']
    path.write_text(json.dumps(schema))
    found = edit_errors(model, edits(model, set={'service.n': 20}), library())
    assert found == []


def test_new_process_reads_and_hashes_the_edited_library_schema(tmp_path):
    """A restarted process validates the bytes named by its implementation identity."""
    lib = library()
    compiled(scenario(), lib)
    shutil.copytree(schemas.FOLDER, tmp_path / 'schema')
    path = tmp_path / 'schema/library.schema.json'
    schema = json.loads(path.read_text())
    schema['required'] = [*schema.get('required', []), 'absent_field']
    path.write_text(json.dumps(schema))
    # The running process retains its imported schema.
    compiled(scenario(), lib)
    script = """
import json, sys
from pathlib import Path
import napkin.schema as schemas
schemas.FOLDER = Path(sys.argv[1]) / 'schema'
from napkin.model.load import schema_errors
from napkin.model.compile import implementation_digest
print(json.dumps({'errors': schema_errors(json.loads(sys.argv[2]), 'library'),
                  'hash': implementation_digest()['schema/library']}))
"""
    result = subprocess.run(
        [sys.executable, '-c', script, str(tmp_path), json.dumps(lib)],
        check=True,
        capture_output=True,
        text=True,
    )
    result = json.loads(result.stdout)
    assert {d['code'] for d in result['errors']} == {'schema'}
    assert result['hash'] == hashlib.sha256(path.read_bytes()).hexdigest()


def test_claims_supporting_a_used_assumption_are_reachable_evidence():
    record = {'status': 'unverified', 'date': '2026-09-17', 'method': 'fixture', 'notes': 'Fixture'}
    lib = library()
    lib['sources'] = [{'id': 's', 'title': 'Fixture', 'custom': {'verification': {**record}}}]
    claim = {'id': 'c', 'source': 's', 'locator': 'Table 1', 'shows': 'Ten', 'limits': 'Fixture'}
    verification = {**record, 'checked_fields': [], 'content_sha256': claim_digest(claim)}
    lib['claims'] = [{**claim, 'verification': verification}]
    lib['assumptions'] = [
        {
            'id': 'a',
            'statement': 'Selected count',
            'rationale': 'Fixture',
            'review': {'status': 'unreviewed'},
            'supports': [{'claim': 'c', 'relation': 'consistent_with'}],
        }
    ]
    people = f'{N}\n        "People"'
    text = edit(
        scenario(),
        replace(
            people,
            'input n: people = 10 people in 1 people to 100 people\n        "People"\n        @assumption a "Fixture"',
        ),
    )
    # What the evidence walkers read of the file: its projection.
    document = front.projection(front.read(text, 'test.scn'))
    assert references(document) == ([], ['a'])
    assert references(document, lib['assumptions']) == (['c'], ['a'])
    model = compiled(text, lib)
    codes = {d['code'] for d in evaluate_study(model, engine.edits_for(model)).diagnostics}
    assert {'assumption:a', 'evidence:c'} <= codes


@pytest.mark.parametrize('url', ['javascript:alert(1)', 'data:text/html,x', 'https://example.org/a b'])
def test_library_links_are_web_addresses(url):
    lib = evidence_library()
    lib['sources'][0]['URL'] = url
    assert ('schema', 'sources/0/URL') in rejected(sc99(), lib)
    lib['sources'][0]['URL'] = 'https://example.org/report.pdf'
    compiled(sc99(), lib)
