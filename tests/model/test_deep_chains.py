"""Long chains of values in the front end (the audit's row 15): 300 top-level formulas in a chain failed
to compile, with a RecursionError in the resolution of names (`semantic.py`: `path`, `name`, `value`,
`initializer`, `expression`).

The rule: a model whose values form a chain of 5,000 links compiles with Python's recursion limit
lowered to 400, in each form that the front end resolves: formulas of the top level, of an entity and
of an event, links between entities and between members of a table, keyed reads, collection values,
stored values whose initializers follow their dependencies, an assertion over the chain, and the
lowering of each. A chain closed on itself is still a cycle, reported with its chain. What each
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
    return HEAD + 'm:\n    go = event():\n' + '\n'.join([*rows, f'        v{n - 1} = formula(1 L)', '        after 1 h']) + '\n'


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


FORMS = {
    'top': top,
    'entity': entity,
    'linked': linked,
    'local': local,
    'stored': stored,
    'asserted': asserted,
    'keyed': keyed,
    'collections': collections,
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
    elif form == 'collections':
        values = {value.name: value for value in program.root}
        assert len([name for name in values if name.startswith('c')]) == LINKS
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
