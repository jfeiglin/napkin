"""Long chains of values in the front end (the audit's row 15): 300 top-level formulas in a chain failed
to compile, with a RecursionError in the resolution of names (`semantic.py`: `path`, `name`, `value`,
`initializer`, `expression`).

The rule: a model whose values form a chain of 5,000 links compiles with Python's recursion limit
lowered to 400, in each form that the front end resolves: formulas of the top level, of an entity and
of an event, links between entities and between members of a table, keyed reads, collection values
(each a where of the next, or the next itself: a named collection is the collection that it names),
stored values whose initializers follow their dependencies, an assertion over the chain, and the
lowering of each; and the run of two of them, a chain of collections and formulas each as deep as
the language admits, over arrays. A chain closed on itself is still a cycle, reported with its chain. What each
compiled model reads is checked from the program, against the chain as written.
"""

import sys

import pytest

from napkin.model.compile import compile_text
from napkin.model.language.problems import LanguageError
from napkin.program.refs import spelled
from tests.program.examples import UNITS

LINKS = 5000
LIMIT = 400
HEAD = 'scenario "Chain"\n    horizon 2 h\n\n'


def top(n):
    """Formulas of the top level, each reading the next, the last an input."""
    rows = ['input base: L = 1 L'] + [f'v{k} = formula(v{k + 1} + 1 L)' for k in range(n - 1)]
    return HEAD + '\n'.join([*rows, f'v{n - 1} = formula(base)']) + '\n'


def entity(n):
    """Formulas of one entity, each reading the next through `this`."""
    rows = [f'    v{k} = formula(this.v{k + 1} + 1 L)' for k in range(n - 1)]
    return HEAD + 'plant:\n' + '\n'.join([*rows, f'    v{n - 1} = formula(1 L)']) + '\n'


def linked(n):
    """Entities written once, each linked to the next, whose formula reads the next one's."""
    rows = []
    for k in range(n - 1):
        rows += [f'e{k}:', f'    next = e{k + 1}', '    v = formula(this.next.v + 1 L)']
    return HEAD + '\n'.join([*rows, f'e{n - 1}:', '    v = formula(1 L)']) + '\n'


def local(n):
    """Formulas of the locals of one event, each reading the next (a formula may read below)."""
    rows = [f'        v{k} = formula(v{k + 1} + 1 L)' for k in range(n - 1)]
    return (
        HEAD
        + 'm:\n    go = event():\n'
        + '\n'.join([*rows, f'        v{n - 1} = formula(1 L)', '        after 1 h'])
        + '\n'
    )


def stored(n):
    """Stored values whose initializers read the next, written against their order of dependency."""
    rows = [f'v{k}: L = v{k + 1} + 1 L' for k in range(n - 1)]
    return HEAD + '\n'.join([*rows, f'v{n - 1}: L = 1 L']) + '\n'


def asserted(n):
    """An assertion over the head of a chain of formulas that end at an input: over inputs only."""
    return top(n) + 'assert v0 >= 0 L\n'


def keyed(n):
    """Members written by hand, each replacing its template's formula with one that reads the next
    member by a key fixed when the model compiles."""
    rows = ['Node:', '    total: formula(L) = formula(1 L)']
    for k in range(n - 1):
        rows += [f'm{k}: Node', f'    total = formula(Node.instances.at({k + 1}).total + 1 L)']
    return HEAD + '\n'.join([*rows, f'm{n - 1}: Node']) + '\n'


def collections(n):
    """Collection values of the top level, each a where of the next, the last the instances."""
    rows = ['Node:', '    input flag: bool = true', 'a: Node', 'b: Node']
    rows += [f'c{k}: <Node> = c{k + 1}.where(flag)' for k in range(n - 1)]
    rows += [f'c{n - 1}: <Node> = Node.instances', 'total = formula(count(c0))']
    return HEAD + '\n'.join(rows) + '\n'


def aliases(n):
    """Collection values of the top level, each naming the next (a named collection is the collection
    that it names), the last the instances, read by a formula and by a solver's input."""
    rows = ['Node:', '    input cap: L/h = 1 L/h', 'a: Node', 'b: Node']
    rows += [f'c{k} = c{k + 1}' for k in range(n - 1)]
    rows += [f'c{n - 1} = Node.instances', 'total = formula(count(c0))']
    rows += [
        'plant:',
        '    water: L = 0 L in [0,]',
        '    flow fill: SOURCE -> this.water',
        '        request = 5 L/h',
        '    choose = solver:',
        '        inputs:',
        '            nodes = c0',
        '        solve_for:',
        '            this.fill.actual_rate',
        '        constraints:',
        '            this.fill.actual_rate <= sum(nodes.cap)',
    ]
    return HEAD + '\n'.join(rows) + '\n'


def table(n):
    """Rows of a table, each linked to the next, whose template's formula reads the next row's; the
    last row links to a member written by hand, whose own formula ends the chain."""
    rows = [
        'Place:',
        '    next: Place',
        '    own: L = 1 L',
        '    total: formula(L) = formula(this.own + this.next.total)',
        'places: Place from "places.csv"',
        'last: Place',
        '    next = last',
        '    total = formula(this.own)',
    ]
    cells = ['id,next'] + [f'p{k},{f"places.p{k + 1}" if k < n - 1 else "last"}' for k in range(n)]
    return HEAD + '\n'.join(rows) + '\n', {'places.csv': '\n'.join(cells) + '\n'}


def solved(n):
    """A solver whose constraint reads the head of a chain of formulas of the top level, which the
    check of what a solver may say reads through (`model/solvers.py`)."""
    rows = [f'v{k} = formula(v{k + 1} + 0 L/h)' for k in range(n - 1)] + [f'v{n - 1} = formula(1 L/h)']
    rows += [
        'plant:',
        '    water: L = 0 L in [0,]',
        '    flow fill: SOURCE -> this.water',
        '        request = 1 L/h',
        '    choose = solver:',
        '        inputs:',
        '            cap = v0',
        '        solve_for:',
        '            this.fill.actual_rate',
        '        constraints:',
        '            this.fill.actual_rate <= cap',
    ]
    return HEAD + '\n'.join(rows) + '\n'


FORMS = {
    'top': top,
    'solved': solved,
    'entity': entity,
    'linked': linked,
    'local': local,
    'stored': stored,
    'asserted': asserted,
    'keyed': keyed,
    'collections': collections,
    'aliases': aliases,
    'table': table,
}


@pytest.fixture
def shallow():
    """Python's recursion limit lowered to `LIMIT` while the test runs."""
    before = sys.getrecursionlimit()
    sys.setrecursionlimit(LIMIT)
    yield
    sys.setrecursionlimit(before)


def compiled(form, n=LINKS):
    found = FORMS[form](n)
    text, tables = found if isinstance(found, tuple) else (found, None)
    return compile_text(text, UNITS, tables=tables)


def reads(expression):
    """The spellings of what an expression of the program reads."""
    return sorted(spelled(read) for _, read in expression.reads)


@pytest.mark.parametrize('form', sorted(FORMS))
def test_a_chain_of_five_thousand_links_compiles_with_the_recursion_limit_at_400(form, shallow):
    program = compiled(form).program
    # What the head of each chain reads, from the program: the next link, as the text writes it.
    if form in ('top', 'asserted'):
        values = {value.name: value for value in program.root}
        assert len([name for name in values if name.startswith('v')]) == LINKS
        assert reads(values['v0'].init.expr) == ['v1']
        assert reads(values[f'v{LINKS - 1}'].init.expr) == ['base']
    elif form == 'entity':
        values = {value.name: value for value in program.template('plant').values}
        assert len(values) == LINKS and reads(values['v0'].init.expr) == ['this.v1']
    elif form == 'linked':
        assert len(program.templates) == LINKS
        (value,) = [value for value in program.template('e0').values if value.name == 'v']
        assert reads(value.init.expr) == ['this.next.v']
    elif form == 'local':
        (event,) = program.template('m').events
        assert len(event.locals) == LINKS and reads(event.locals[0].init.expr) == ['v1']
    elif form == 'stored':
        values = {value.name: value for value in program.root}
        assert len(values) == LINKS and reads(values['v0'].init) == ['v1']
    elif form == 'keyed':
        members = program.template('Node').members
        assert len(members) == LINKS
    elif form == 'solved':
        (solver,) = program.template('plant').solvers
        assert len(solver.constraints) == 1 and len(program.root) == LINKS
    elif form == 'collections':
        values = {value.name: value for value in program.root}
        assert len([name for name in values if name.startswith('c')]) == LINKS
    elif form == 'aliases':
        values = {value.name: value for value in program.root}
        assert len([name for name in values if name.startswith('c')]) == LINKS
        assert (
            spelled(values['c0'].init) == 'c1' and spelled(values[f'c{LINKS - 1}'].init) == 'Node.instances'
        )
    else:
        assert len(program.template('Place').members) == LINKS + 1


def test_a_chain_of_five_thousand_links_closed_on_itself_is_a_cycle_with_its_chain(shallow):
    """The last formula of the chain reads the first: a cycle, reported once with its chain."""
    text = top(LINKS).replace(f'v{LINKS - 1} = formula(base)', f'v{LINKS - 1} = formula(v0)')
    with pytest.raises(LanguageError) as caught:
        compile_text(text, UNITS)
    (problem,) = [item for item in caught.value.problems if item.code == 'cycle']
    chain = ' reads '.join(f'v{k}' for k in range(LINKS))
    assert problem.message.startswith(f'{chain} reads v0')


def test_a_wide_expression_of_values_written_after_it_is_resolved_once(shallow):
    """A formula that reads 3,000 values declared after it, each resolved inside its reader's
    resolution (a few deep at most) and so once: it compiles in a few seconds at the recursion
    limit of 400, and reads every value."""
    rows = ['total = formula(' + ' + '.join(f'v{k}' for k in range(3000)) + ')']
    rows += [f'v{k} = formula({k} L)' for k in range(3000)]
    program = compile_text(HEAD + '\n'.join(rows) + '\n', UNITS).program
    (total,) = [value for value in program.root if value.name == 'total']
    assert reads(total.init.expr) == sorted(f'v{k}' for k in range(3000))


def test_formulas_each_as_deep_as_the_language_admits_run_in_a_chain_over_arrays(shallow):
    """Six formulas of a template, each nesting 140 choices (the language admits 150) over the one
    before, the first over `this.a`, and a flow of each of two members that drains its tank at the
    last: the members' flows run together over arrays (`core/arrays`), which reach each formula's
    parts with a list and not with calls, so the run goes at the recursion limit of 400, where it
    went 2 calls a level deep until then (and failed at Python's default of 1,000). No test holds (k is
    1, every test is `this.k > 10` or more), so each formula is the one before, and each tank drains
    at a = 1 L/h: 100 L - 4 h x 1 L/h = 96 L at 4 h."""
    from napkin.engine import read, run

    def nested(before):
        return ' else '.join(f'{j + 1} L/h if this.k > {j + 10}' for j in range(140)) + f' else {before}'

    rows = ['Valve:', '    k: number = 1', '    a: L/h = 1 L/h', '    tank: L = 100 L in [0,]']
    rows += [f'    r{m} = formula({nested(f"this.r{m - 1}" if m else "this.a")})' for m in range(6)]
    rows += [
        '    flow drain: this.tank -> SINK',
        '        request = formula(this.r5)',
        '',
        'east: Valve',
        'west: Valve',
    ]
    model = compile_text(HEAD.replace('2 h', '4 h') + '\n'.join(rows) + '\n', UNITS)
    record = run(model.program, model.configuration)
    assert record.failure is None
    found = read(record, model.program, ['east.tank', 'west.tank'], [4])
    assert [reading.values for reading in found] == [(pytest.approx(96),), (pytest.approx(96),)]


def test_a_chain_of_five_thousand_collections_each_naming_the_next_runs_at_the_recursion_limit_of_400(
    shallow,
):
    """Each collection of the chain is the one that it names, down to the instances a and b (a named
    collection names a collection, re-audit 15): the head counts 2 members, and the solver whose
    input names the head caps the fill at the sum of their caps, 2 L/h, so the plant holds 3 L at
    1.5 h (2 L/h x 1.5 h, by hand). Compiled, run and read with the limit at 400."""
    from napkin.engine import read, run

    model = compiled('aliases')
    record = run(model.program, model.configuration)
    assert record.failure is None
    found = read(record, model.program, ['total', 'plant.fill.actual_rate', 'plant.water'], [1.5])
    assert [reading.values for reading in found] == [(2,), (pytest.approx(2),), (pytest.approx(3),)]


def test_a_part_and_a_value_of_the_root_are_found_by_their_names_not_by_a_walk():
    """A program of thousands of parts is read part by part (the engine's plan, the proofs, the
    checker), so each lookup by name is one step: finding every part of a template of 8,000 values
    and every value of a root of 8,000 takes about 8 times as long as for 1,000 (a walk would take
    64 times; the best of three runs, against a bound of 24)."""
    import time

    from napkin.program.build import Builder, value

    def lookups(n):
        b = Builder(UNITS)
        b.entity('plant', *(value(f'v{k}', 'L', 1) for k in range(n)))
        for k in range(n):
            b.root(value(f'r{k}', 'L', 1))
        program = b.finish()
        template = program.template('plant')
        best = float('inf')
        for _ in range(3):
            start = time.perf_counter()
            for k in range(n):
                assert template.part(f'v{k}').name == f'v{k}' and program.root_value(f'r{k}').name == f'r{k}'
            best = min(best, time.perf_counter() - start)
        return best

    assert lookups(8000) / lookups(1000) < 24
