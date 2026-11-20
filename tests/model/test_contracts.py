"""Independent contract tests: a malformed model never reaches a run, and what holds without a model.

Each model case is a small text with one deliberate fault, checked by the code and the line of the
problem that refuses it, or a valid neighbour that must compile and run to its closed form. The front
end reports every independent fault of a text, not the first only; a number that is not finite is no
number of a model; a rate that reads its own store is a differential equation, not a circle; and a
part that nothing reads is checked all the same. The entries of `napkin.expressions` and the interval
prover need no model. The checks of a library (`napkin/model/evidence.py`) refuse duplicate IDs and
links that are no web addresses, run once for each content, and reach the claims that support a used
assumption.

The edits of a run are in `tests/language/test_runs.py`, the never-falls proofs in
`tests/program/test_proofs.py`, sharing among competing flows in `tests/language/test_endpoints.py`
and `tests/engine/test_rationing.py`; the outputs, their lags and their proofs went with the outputs
(D10), and the identity of the implementation with the old compiler.
"""

import ast
import copy
import math

import pytest

from napkin.core import expr as nodes
from napkin.core import intervals
from napkin.engine import read, run
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
from napkin.model import evidence
from napkin.model.compile import compile_text
from napkin.model.language.evidence import document
from napkin.model.language.parse import parse
from napkin.model.language.problems import LanguageError
from tests.evidence.support import evidence_library
from tests.program.examples import UNITS
from tests.units import UNITS as LIBRARY_UNITS

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


@pytest.mark.parametrize(
    ('gate', 'ordered'), [((True, True), True), ((False, False), False), ((0, 1), False)]
)
def test_a_membership_proof_uses_the_scale_of_every_possible_selected_end(gate, ordered):
    """Both lower ends hold 2e-12. The coarse one compares equal to zero.
    The fine one exceeds zero, so its interval is reversed whenever it is selected."""
    units = UnitSystem({})
    units.comparisons.named = lambda name: (1, 1e-12 if name == 'fine' else 1)
    ranges = {'gate': gate, 'coarse': (2e-12, 2e-12), 'fine': (2e-12, 2e-12)}
    prove = domain_prover(ranges, units)
    test = nodes.read('within(0, coarse if gate else fine, 0)')
    if ordered:
        assert prove(test) == (0, 1)
    else:
        with pytest.raises(ExpressionError, match='ends of a membership test are ordered'):
            prove(test)


def test_each_entry_of_the_expressions_takes_a_node_or_a_number_and_refuses_a_text():
    """A text is a TypeError at each entry, and in each place of an entry that takes an expression;
    the node of the same text and a number are taken."""
    units = UnitSystem(LIBRARY_UNITS)
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
    units = UnitSystem(LIBRARY_UNITS)
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
    units = UnitSystem(LIBRARY_UNITS)
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
        compile_expression(nodes.read(source), {}, UnitSystem(LIBRARY_UNITS))


def test_a_negative_literal_exponent_keeps_the_unit_arithmetic_and_the_magnitude_limit():
    units = UnitSystem(LIBRARY_UNITS)
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
    validate_domains(nodes.read(source), ranges, UnitSystem(LIBRARY_UNITS), formulas(aliases))


def test_an_indeterminate_interval_proves_nothing():
    # 1/x - 1/x is inf - inf at the edge of the range: no bound, so the square root is not proven.
    with pytest.raises(ExpressionError, match='sqrt'):
        validate_domains(
            nodes.read('sqrt((1 / x - 1 / x) - 1) if x > 0 else 0'),
            {'x': (0.0, 5e-324)},
            UnitSystem(LIBRARY_UNITS),
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
    prove = intervals.prover({'x': (1.0, 2.0)}, UnitSystem(LIBRARY_UNITS), aliases)
    assert prove(nodes.read('a40')) == (low, 2.0**41)
    assert aliases.counts.get('a0')  # the counts are those of the proof


def test_a_branch_proves_a_formula_that_does_not_read_its_condition_once():
    # The branch narrows y. The chain over x does not read y, so in the branch it has its interval over
    # the ranges, which the prover proves once: by expansion alone it reads a_0 2^40 times.
    written = {'a0': 'x', **{f'a{k}': f'a{k - 1} + a{k - 1}' for k in range(1, 41)}}
    aliases = Counted(written, 3, 'is proved again in each branch that reads it')
    prove = intervals.prover({'x': (1.0, 2.0), 'y': (-1.0, 1.0)}, UnitSystem(LIBRARY_UNITS), aliases)
    assert prove(nodes.read('a40 + y if y > 0 else 0')) == (0.0, 2.0**41 + 1)
    assert aliases.counts.get('a0')


@pytest.mark.parametrize('condition', ['y * y >= 0', 'y != 0', 'x > 1', 'x * x > 1', 'x != 0'])
def test_refined_branches_prove_a_shared_alias_graph_once(condition):
    # Independent interval arithmetic: repeatedly adding [1, 2] to itself gives [2^40, 2^41].
    # A guarded/nonzero fact, including one relevant to x, must not turn this DAG into 2^40 proofs.
    written = {'a0': 'x', **{f'a{k}': f'a{k - 1} + a{k - 1}' for k in range(1, 41)}}
    aliases = Counted(written, 8, 'is expanded for each path through the alias graph')
    prove = intervals.prover({'x': (1.0, 2.0), 'y': (-1.0, 1.0)}, UnitSystem(LIBRARY_UNITS), aliases)
    low = 2.0**40 if condition == 'x != 0' else 0.0  # x is positive: its false branch is empty.
    assert prove(nodes.read(f'a40 if {condition} else 0')) == (low, 2.0**41)
    assert aliases.counts.get('a0')


def test_refined_alias_memo_keeps_effective_bounds_nonzero_facts_and_failures_separate():
    prove = domain_prover(
        {'x': (-2.0, 2.0), 'y': (-1.0, 1.0)},
        UnitSystem(LIBRARY_UNITS),
        formulas({'twice': 'x + x', 'ratio': '1 / x', 'root': 'sqrt(x)', 'log': 'ln(x)'}),
    )
    assert prove(nodes.read('twice if x >= 1 else 0')) == (0.0, 4.0)
    assert prove(nodes.read('twice if x <= -1 else 0')) == (-4.0, 0.0)
    assert prove(nodes.read('twice')) == (-4.0, 4.0)
    assert prove(nodes.read('ratio if x != 0 else 0')) == (-math.inf, math.inf)
    # The inclusive guards also admit x just below their thresholds (change 29).
    with pytest.raises(ExpressionError, match='sqrt argument is nonnegative'):
        prove(nodes.read('root if x >= 0 else 0'))
    assert prove(nodes.read('root if x > 0 else 0')) == (0.0, math.sqrt(2.0))
    lower = 1.0 - 1e-9
    assert prove(nodes.read('log if x >= 1 else 0')) == (math.log(lower), math.log(2.0))
    for source in ('ratio', 'ratio if y != 0 else 0', 'root', 'log'):
        with pytest.raises(ExpressionError):
            prove(nodes.read(source))
    # A cached root-domain failure cannot poison a later safe branch either.
    assert prove(nodes.read('ratio if x >= 1 else 0')) == (0.0, 1.0 / lower)


def test_refined_alias_memo_keeps_expression_guards_and_impossible_branches():
    prove = domain_prover(
        {'x': (0.0, 2.0), 'y': (0.0, 2.0)},
        UnitSystem(LIBRARY_UNITS),
        formulas({'ratio': '1 / (x - y)', 'twice': 'x + x'}),
    )
    # x-y as small as 1-1e-9 satisfies >= 1, so its reciprocal can exceed 1.
    assert prove(nodes.read('ratio if x - y >= 1 else 0')) == (0.0, 1.0 / (1.0 - 1e-9))
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
    units = UnitSystem(LIBRARY_UNITS)
    prove = domain_prover({'x': (1.0, 2.0), 'y': (0.0, 10.0)}, units, formulas({**chain, 'r': 'x / d'}))
    with pytest.raises(ExpressionError, match='nonzero denominator'):
        prove(nodes.read('r'))
    low, high = prove(nodes.read('r if y > 0 else 0'))
    assert low == 0.0 and high == math.inf


def test_a_formula_met_again_on_its_own_chain_has_no_bound_on_that_chain():
    # From a: a = min(b, 5), b = max(a, 1), and a again has no bound, so b is [1, inf] and a is
    # [1, 5]. From b, a is [-inf, 5] and b is [1, 5]. The sum is [2, 10]; with the interval of b
    # read on the chain from a, it would be [2, inf].
    prove = domain_prover({}, UnitSystem(LIBRARY_UNITS), formulas({'a': 'min(b, 5)', 'b': 'max(a, 1)'}))
    assert prove(nodes.read('a + b')) == (2.0, 10.0)


def test_a_formula_that_fails_its_proof_fails_each_expression_that_reads_it():
    prove = domain_prover({'x': (0.0, 1.0)}, UnitSystem(LIBRARY_UNITS), formulas({'d': '1 / x'}))
    for source in ('d + 1', '2 * d'):
        with pytest.raises(ExpressionError, match='nonzero denominator'):
            prove(nodes.read(source))


# ---- models with one fault ----------------------------------------------------------------------

TANK = """\
scenario "Tank"
    horizon 4 h

tank:
    "A tank that drains."
    input n: person = 10 person in [1 person, 100 person]
    water: L = 8 L in [0 L, 20 L]
    flow drain: this.water -> SINK
        request = 1 L/h
"""


def problems(text):
    with pytest.raises(LanguageError) as raised:
        compile_text(text, UNITS)
    return [(item.code, item.line) for item in raised.value.problems]


def line_of(text, words):
    return next(number for number, row in enumerate(text.split('\n'), 1) if words in row)


@pytest.mark.parametrize(
    ('written', 'code'), [('1e999 person', 'number'), ('nan', 'unknown_name')], ids=['inf', 'nan']
)
def test_a_number_that_is_not_finite_is_refused_at_its_line(written, code):
    """A file writes no NaN, and a number too large to be finite is an error of its line."""
    text = TANK.replace('input n: person = 10 person', f'input n: person = {written}')
    assert problems(text) == [(code, line_of(text, 'input n'))]


def test_independent_faults_are_all_reported():
    text = TANK.replace('water: L = 8 L in [0 L, 20 L]', 'water: L = 8 L in [20 L, 0 L]')
    text += '    seen = formula(this.missing)\n'
    assert problems(text) == [('range', line_of(text, 'water: L')), ('unknown_name', line_of(text, 'seen ='))]


VALUE = 'go: L = 1 L'
EVENT = 'go = event():\n        after 1 h'
FLOW = 'flow go: SOURCE -> this.spare\n        request = 1 L/h'


@pytest.mark.parametrize(
    ('first', 'second'),
    [
        pytest.param(EVENT, VALUE, id='an event, then a value'),
        pytest.param(FLOW, EVENT, id='a flow, then an event'),
        pytest.param(VALUE, EVENT, id='a value, then an event'),
        pytest.param(VALUE, FLOW, id='a value, then a flow'),
    ],
)
def test_a_name_is_declared_once_in_its_entity(first, second):
    """A value, an event and a flow of one entity never share a name: the line that declares the name
    a second time is refused."""
    text = TANK + '    spare: L = 0 L\n' + f'    {first}\n    {second}\n'
    lines = text.split('\n')
    assert problems(text) == [('duplicate_name', lines.index(f'    {second.splitlines()[0]}') + 1)]


def test_a_rate_that_reads_its_own_store_is_no_circle():
    """The level decays at half of itself an hour: level(t) = exp(-t / 2)."""
    text = (
        TANK
        + '    level = 1.0 in [0,]\n    flow decay: this.level -> SINK\n        request = formula(this.level / 2 h)\n'
    )
    model = compile_text(text, UNITS)
    (level,) = read(run(model.program, model.configuration), model.program, ['tank.level'], [1, 2, 4])
    assert level.values == pytest.approx([math.exp(-t / 2) for t in (1, 2, 4)], rel=1e-7)


def test_a_part_that_nothing_reads_is_checked_all_the_same():
    """No run reads the spare entity and no event starts; its parts are still checked."""
    spare = 'spare:\n    "A spare record."\n    log = formula(ln(tank.n / 1 person))\n'
    model = compile_text(TANK + spare, UNITS)
    assert [part.path for part in model.declared.part('spare').parts] == ['spare.log']
    text = TANK + spare + '    bad = formula(this.typo)\n'
    assert problems(text) == [('unknown_name', line_of(text, 'bad = formula'))]


# ---- the checks of a library ------------------------------------------------------------------


def checked(library):
    """The (code, path) of each problem of the checks of a library."""
    return [(item['code'], item['path']) for item in evidence.library_checks(library)[0]]


def test_a_library_names_each_record_once():
    library = evidence_library()
    assert checked(library) == []
    library['sources'].append(copy.deepcopy(library['sources'][0]))
    assert checked(library) == [('duplicate_id', 'sources')]


@pytest.mark.parametrize('url', ['javascript:alert(1)', 'data:text/html,x', 'https://example.org/a b'])
def test_library_links_are_web_addresses(url):
    library = evidence_library()
    library['sources'][0]['URL'] = url
    assert checked(library) == [('schema', 'sources/0/URL')]
    library['sources'][0]['URL'] = 'https://example.org/report.pdf'
    assert checked(library) == []


def test_the_checks_of_a_library_run_once_for_each_content(monkeypatch):
    calls = []
    original = evidence.validate_library
    monkeypatch.setattr(evidence, 'validate_library', lambda library: calls.append(1) or original(library))
    monkeypatch.setattr(evidence, '_CHECKED', {})
    library = evidence_library()
    evidence.library_checks(library)
    evidence.library_checks(copy.deepcopy(library))
    assert calls == [1]
    library['claims'][0]['shows'] = 'Another fact.'
    assert ('evidence_digest', 'claims/C-ACCESS') in checked(library) and calls == [1, 1]


def test_the_claims_that_support_a_used_assumption_are_reached():
    """A record of the model rests on the assumption RT-FIXTURE, which the claim C-ACTION supports:
    the model cites the assumption, and reaches the claim and its source."""
    text = 'tank:\n    input n: person = 1 person\n        @assumption "Fixture."\n            assumption RT-FIXTURE\n'
    found = document(parse(text))
    library = evidence_library()
    assert evidence.references(found) == ([], ['RT-FIXTURE'])
    assert evidence.references(found, library['assumptions']) == (['C-ACTION'], ['RT-FIXTURE'])
    reached = evidence.dependencies(found, library)
    assert (reached['claims'], reached['sources']) == (['C-ACTION'], ['src'])
