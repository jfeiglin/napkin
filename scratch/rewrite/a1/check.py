"""The checks of the prototype parser. Each one is behind a claim of FINDINGS.md.

    python check.py                  runs every check and prints one line for each
    python -m pytest check.py -q     the same checks under pytest

1. `test_copied_pieces`: the pieces of `lex.py` that `parser.py` says it copies unchanged are the
   text of the base commit.
2. `test_catalogue_tokens`: the new tokenizer against the present one, on each logical line of the
   present models. It counts the lines that give the same tokens, and names why the others differ.
3. `test_corpus`: each block of the spec parses where the manifest says it stands.
4. `test_inline` and `test_refused`: the inline notation parses, and each refused piece gets its
   message.
5. `test_hunt`: the cases of the ambiguity hunt are as `hunt.py` writes them.
6. `test_round_trip_corpus` and `test_round_trip_random`: `write` gives a text that reads back to
   the same node. The random trees come from `hypothesis`.
7. `test_core`: an expression of the parser, lowered, goes through the unit rules and the evaluator of
   `napkin.core` at the base commit.
8. `test_catalogue_expressions`: each expression of the present models, read by today's route (Python
   text and `ast`) and by the new parser, is the same node of `napkin.core.expr`.
9. `test_python_keywords`: what `napkin.core` does with a name that Python keeps.
"""

from __future__ import annotations

import inspect
import re
import sys
from collections import Counter
from dataclasses import fields, is_dataclass
from pathlib import Path

import parser as P
from napkin.core import evaluation, expr, units
from napkin.core.errors import ExpressionError

HERE = Path(__file__).resolve().parent
BASE = Path(P.BASE)
CORPUS = HERE / 'corpus'


# ---- 1. the copied pieces ------------------------------------------------------------------------------


def test_copied_pieces():
    old = (BASE / 'napkin/model/language/lex.py').read_text(encoding='utf-8')
    for piece in (P.SyntaxProblem, P.Token, P.Line, P.fold, P.tree):
        source = inspect.getsource(piece)
        assert source in old, f'{piece.__name__} is not the text of lex.py at the base commit'
    return 'SyntaxProblem, Token, Line, fold and tree are the text of lex.py at the base commit'


# ---- 2. the present models, token by token ----------------------------------------------------------------


def catalogue_tokens():
    """(logical lines, lines with the same tokens, {why a line differs: count}, {why: an example})."""
    from napkin.model.language import lex as old

    files = sorted([*(BASE / 'examples').rglob('*.scn'), *(BASE / 'scenarios').rglob('*.scn')])
    total = same = 0
    why, examples = Counter(), {}
    for path in files:
        text = path.read_text(encoding='utf-8')
        rows = text.split('\n')
        for line in old.lines(text):
            if line.kind != 'line':
                continue
            total += 1
            source = '\n'.join(rows[line.number - 1 : line.end])
            want = [(token.kind, token.value) for token in line.tokens]
            try:
                got = [(t.kind, t.value) for found in P.lines(source) if found.kind == 'line' for t in found.tokens]
            except P.SyntaxProblem as problem:
                if '|' in problem.message[:3]:
                    key = 'refused: `|` between named values (`"a" | "b"`), now `enum[A, B]`'
                elif 'starts with ->' in problem.message or 'ends with ->' in problem.message:
                    key = 'refused: a flow with one end left out (`-> tally`, `stock ->`), now `SOURCE` and `SINK`'
                else:
                    key = f'refused: {problem.message}'
                why[key] += 1
                examples.setdefault(key, f'{path.relative_to(BASE)}:{line.number}')
                continue
            if got == want:
                same += 1
                continue
            changed = [(a, b) for a, b in zip(want, got) if a != b]
            if changed and all(a == ('name', 'size') and b == ('unit', 'size') for a, b in changed):
                key = 'differs: `size` after a bare number (`= 0.6 size 1`) is read as its unit'
            else:
                key = f'differs: {changed[:2]}'
            why[key] += 1
            examples.setdefault(key, f'{path.relative_to(BASE)}:{line.number}')
    return len(files), total, same, why, examples


def test_catalogue_tokens():
    count, total, same, why, _ = catalogue_tokens()
    known = ('refused: `|`', 'refused: a flow with one end', 'differs: `size`')
    assert all(key.startswith(known) for key in why), why
    assert total == same + sum(why.values())
    return f'{count} present files, {total} logical lines: {same} give the same tokens, {total - same} differ for 3 known reasons'


# ---- 3 and 4. the corpus ----------------------------------------------------------------------------------


def corpus_files():
    known = P.contexts(CORPUS)
    return [(path, known[path.name]) for path in sorted(CORPUS.glob('*.scn'))]


def rows_of(name):
    """(line of the file, columns) for each line of a hand-written list of the corpus."""
    for number, row in enumerate((CORPUS / name).read_text(encoding='utf-8').split('\n'), 1):
        if row.strip() and not row.startswith('#'):
            yield number, row.split('\t')


def test_corpus():
    found = corpus_files()
    assert len(found) == 27
    for path, context in found:
        P.parse(path.read_text(encoding='utf-8'), context)
    return f'{len(found)} blocks of the spec parse'


def test_inline():
    count = 0
    for number, columns in rows_of('inline.txt'):
        kind, _, text = columns[:3]
        try:
            P.parse_inline(kind, text)
        except P.SyntaxProblem as problem:
            raise AssertionError(f'inline.txt:{number}: {text!r}: {problem.message}') from None
        count += 1
    return f'{count} pieces of inline notation parse'


def test_refused():
    count = 0
    for number, (kind, _, text, part) in rows_of('refused.txt'):
        try:
            P.parse_inline(kind, text)
        except P.SyntaxProblem as problem:
            assert part in problem.message, f'refused.txt:{number}: {text!r}: {problem.message}'
            count += 1
            continue
        raise AssertionError(f'refused.txt:{number}: {text!r} parsed')
    return f'{count} pieces are refused, each with its message'


# ---- 5. the hunt ------------------------------------------------------------------------------------------


def test_hunt():
    import hunt

    _, count, wrong = hunt.run()
    assert not wrong, wrong
    return f'{count} cases of the ambiguity hunt are as written'


# ---- 6. an expression reads back --------------------------------------------------------------------------


def expressions(node, place='value'):
    """(expression, its place) for each expression of a tree of the parser. The place is `after =`
    (the value of a declaration or of an assignment), `start` (the line that starts an event) or
    `value` (anywhere else)."""
    if isinstance(node, expr.Node):
        yield node, place
    elif isinstance(node, (list, tuple)):
        for item in node:
            yield from expressions(item)
    elif is_dataclass(node):
        for item in fields(node):
            value = getattr(node, item.name)
            if item.name == 'value' and isinstance(node, P.AFTER_EQUALS):
                yield from expressions(value, 'after =')
            elif isinstance(node, P.Start):
                yield from expressions(value, 'start')
            else:
                yield from expressions(value)


def reads_back(node, place='value'):
    bare_in = place != 'after ='
    written = P.write(node, bare_in=bare_in)
    again = P.parse_expression(written, bare_in=bare_in, statement=place == 'start')
    assert again is node, f'{written!r} reads back as {P.sexpr(again)}, not {P.sexpr(node)}'


def test_round_trip_corpus():
    count = 0
    for path, context in corpus_files():
        tree = P.parse(path.read_text(encoding='utf-8'), context)
        for node, place in expressions(tree.items):
            reads_back(node, place)
            count += 1
    for _, columns in rows_of('inline.txt'):
        found = P.parse_inline(columns[0], columns[2])
        for node, place in expressions(found):
            reads_back(node, place)
            count += 1
    return f'{count} expressions of the corpus read back from their text to the same node'


def strategies():
    from hypothesis import strategies as st

    word = st.from_regex(r'[a-z_][A-Za-z0-9_]{0,6}', fullmatch=True).filter(lambda name: name not in P.RESERVED)
    capital = st.from_regex(r'[A-Z][A-Za-z0-9_]{0,6}', fullmatch=True).filter(lambda name: name not in P.RESERVED)
    field = word.map(expr.ref)
    dotted = st.builds(
        lambda first, rest: expr.ref('.'.join([first, *rest])),
        st.one_of(word, capital, st.just('this'), st.just('t')),
        st.lists(word, min_size=1, max_size=3),
    )
    refs = st.one_of(field, dotted, st.just(expr.ref('this')), st.just(expr.ref('t')))
    numbers = st.one_of(
        st.integers(min_value=0, max_value=10**12),
        st.floats(min_value=0, allow_nan=False, allow_infinity=False),
    )
    unit_words = st.sampled_from(['h', 'L/h', 'L/h^2', 'Wh/L', 'person-years', 's^-1', 'tunings/tuner-year', 'g'])
    texts = st.text(st.characters(blacklist_characters='\n\t', blacklist_categories=('Cs',)), max_size=8)
    leaves = st.one_of(
        refs,
        numbers.map(expr.const),
        st.booleans().map(expr.const),
        texts.map(expr.const),
        capital.map(P.case),
        st.just(P.absent()),
        st.builds(P.quantity, numbers, unit_words),
    )
    monotone = st.one_of(
        st.lists(st.sampled_from(['lt', 'le']), min_size=1, max_size=3),
        st.lists(st.sampled_from(['gt', 'ge']), min_size=1, max_size=3),
        st.sampled_from(['eq', 'ne']).map(lambda op: [op]),
    )

    def compare(children):
        return monotone.flatmap(
            lambda ops: st.lists(children, min_size=len(ops) + 1, max_size=len(ops) + 1).map(
                lambda operands: expr.compare(ops, operands)
            )
        )

    def filters(children):
        one = st.one_of(
            field,
            field.map(lambda node: expr.unary('not', node)),
            st.builds(lambda op, left, right: expr.compare([op], [left, right]), st.sampled_from(sorted(P.COMPARISONS.values())), field, children),
        )
        return st.one_of(one, st.lists(one, min_size=2, max_size=3).map(lambda values: expr.boolean('and', values)))

    def based(children):
        # A member of an enum has no member: the parser reads `Open.x` as a dotted name.
        return children.filter(lambda node: not isinstance(node, P.Case))

    def extend(children):
        return st.one_of(
            st.builds(expr.unary, st.sampled_from(['neg', 'pos', 'not']), children),
            st.builds(expr.binary, st.sampled_from(['add', 'sub', 'mul', 'div', 'pow']), children, children),
            compare(children),
            st.builds(P.within, children, children, children),
            st.builds(expr.boolean, st.sampled_from(['and', 'or']), st.lists(children, min_size=2, max_size=3)),
            st.builds(expr.if_else, children, children, children),
            st.builds(expr.call, st.sampled_from(sorted(P.FUNCTIONS | P.DISTRIBUTIONS)), st.lists(children, max_size=3)),
            children.map(P.formula),
            st.lists(children, max_size=3).map(P.collection),
            st.builds(P.member, based(children), word),
            st.builds(lambda base, test: P.method(base, 'where', [test]), based(children), filters(children)),
            st.builds(lambda base, key: P.method(base, 'by', [key]), based(children), field),
            st.builds(lambda base, key: P.method(base, 'at', [key]), based(children), children),
            st.builds(lambda base: P.method(base, 'draw', []), based(children)),
            st.builds(lambda base, by: P.method(base, 'diff', [by]), based(children), refs),
        )

    return st.recursive(leaves, extend, max_leaves=12)


def test_round_trip_random(examples=3000):
    from hypothesis import HealthCheck, given, settings

    count = Counter()

    @settings(max_examples=examples, deadline=None, suppress_health_check=list(HealthCheck), database=None)
    @given(strategies())
    def reads(node):
        reads_back(node)
        reads_back(node, 'after =')
        count['trees'] += 1
        count['nodes'] += sum(1 for _ in expr.walk(node))

    reads()
    return f'{count["trees"]} random trees ({count["nodes"]} nodes) read back from their text to the same node, in both places'


# ---- 7. the unit rules and the evaluator of napkin.core ---------------------------------------------------


def lower(node):
    """An expression of the parser as nodes of `napkin.core.expr` only, where the kinds of the parser
    have a scalar meaning there: a quantity is `q(number, unit)`, and a membership test is the chain
    `lo <= x <= hi`, which reads `x` once. Any other kind of the parser has no node there."""
    if isinstance(node, P.Quantity):
        return node.lowered()
    if isinstance(node, P.Within):
        return expr.compare(['le', 'le'], [lower(node.low), lower(node.value), lower(node.high)])
    if isinstance(node, P.Own):
        raise TypeError(f'{type(node).__name__} has no node in napkin.core.expr')
    if isinstance(node, expr.Unary):
        return expr.unary(node.op, lower(node.operand))
    if isinstance(node, expr.Binary):
        return expr.binary(node.op, lower(node.left), lower(node.right))
    if isinstance(node, expr.Compare):
        return expr.compare(node.ops, map(lower, node.operands))
    if isinstance(node, expr.BoolOp):
        return expr.boolean(node.op, map(lower, node.values))
    if isinstance(node, expr.IfElse):
        return expr.if_else(lower(node.test), lower(node.body), lower(node.orelse))
    if isinstance(node, expr.Call):
        return expr.call(node.function, map(lower, node.args))
    return node


REGISTRY = units.UnitSystem(
    {
        'h': {'dimensions': {'time': 1}, 'scale': 1},
        'day': {'dimensions': {'time': 1}, 'scale': 24},
        'L': {'dimensions': {'volume': 1}, 'scale': 1},
        'm': {'dimensions': {'length': 1}, 'scale': 1},
        'g': {'dimensions': {'mass': 1}, 'scale': 1},
        'W': {'dimensions': {'power': 1}, 'scale': 1},
        'Wh': {'dimensions': {'power': 1, 'time': 1}, 'scale': 1},
    }
)
CORE_CASES = [
    # (expression, {name: (value, unit)}, value in execution units, unit of the result)
    ('48 h / 2', {}, 24.0, 'h'),
    ('this.water / (2 h)', {'this.water': (8, 'L')}, 4.0, 'L/h'),
    ('this.water / 2 h', {'this.water': (8, 'L')}, 4.0, 'L/h'),
    ('10 L / 5 L/h', {}, 2.0, 'h'),
    ('(2 m) ** 2', {}, 4.0, 'm^2'),
    ('2 m^2', {}, 2.0, 'm^2'),
    ('2 * this.delay', {'this.delay': (3, 'h')}, 6.0, 'h'),
    ('max(0, need - use_rate)', {'need': (5, 'L/h'), 'use_rate': (8, 'L/h')}, 0, 'L/h'),
    ('max(0 W, request - actual)', {'request': (6, 'W'), 'actual': (4, 'W')}, 2.0, 'W'),
    ('fill * (0.5 Wh/L)', {'fill': (2, 'L/h')}, 1.0, 'W'),
    ('min(6 W, (10 Wh - energy) / (1 h))', {'energy': (7, 'Wh')}, 3.0, 'W'),
    ('1 day + 12 h', {}, 36.0, 'h'),
    ('1 if ready else 0', {'ready': (True, None)}, 1, None),
    ('lo <= x and x < hi', {'lo': (1, 'h'), 'x': (2, 'h'), 'hi': (2, 'h')}, False, 'bool'),
    ('x in [lo, hi]', {'lo': (1, 'h'), 'x': (2, 'h'), 'hi': (2, 'h')}, True, 'bool'),
    ('total in [initial - 1 L, initial + 1 L]', {'total': (9.5, 'L'), 'initial': (10, 'L')}, True, 'bool'),
]
CORE_REFUSED = [
    ('3 L + 2 h', {}, 'Incompatible quantities'),
    ('x in [0 L, 5 h]', {'x': (1, 'L')}, 'Incompatible quantities'),
    ('this.water / (2 h) + 1 L', {'this.water': (8, 'L')}, 'Incompatible quantities'),
]


def test_core():
    def unit(name):
        if name is None:
            return units.NUMBER
        return units.BOOLEAN if name == 'bool' else REGISTRY.parse_unit(name)

    for text, names, value, expected in CORE_CASES:
        node = lower(P.parse_expression(text))
        symbols = {name: units.BOOLEAN if isinstance(v, bool) else unit(u) for name, (v, u) in names.items()}
        found, _ = units.unit_of(node, symbols, REGISTRY)
        want = unit(expected).canonical()
        assert found == units.ZERO or found.compatible(want), f'{text}: unit {found}, not {want}'
        environment = {name: v if u is None else REGISTRY.normalize(v, u) for name, (v, u) in names.items()}
        got = evaluation.value(node, environment, REGISTRY)
        assert got == value and type(got) is type(value), f'{text}: {got!r}, not {value!r}'
    for text, names, part in CORE_REFUSED:
        node = lower(P.parse_expression(text))
        symbols = {name: unit(u) for name, (v, u) in names.items()}
        try:
            units.unit_of(node, symbols, REGISTRY)
        except ExpressionError as problem:
            assert part in str(problem), f'{text}: {problem}'
            continue
        raise AssertionError(f'{text}: the unit rules of napkin.core accept it')
    for text in ('<this.primary, this.backup>', 'formula(this.water / (2 h))', 'c.at(t).price', 'OPEN', 'none'):
        try:
            lower(P.parse_expression(text))
        except TypeError:
            continue
        raise AssertionError(f'{text}: lowered')
    return (
        f'{len(CORE_CASES)} expressions go through the unit rules and the evaluator of napkin.core with the '
        f'expected unit and value; {len(CORE_REFUSED)} are refused by its unit rules'
    )


# ---- 8. the expressions of the present models, by both routes -----------------------------------------------


def catalogue_expressions():
    """(expressions of the present models, those that both routes read to one node, {why not: count}).

    Today's route writes the tokens of an expression as Python text and reads it with `ast`
    (`expressions.tree`), then `expr.of_tree` gives the node. The new route reads the same tokens,
    written as one line with `is` as `==` and `is not` as `!=`, with the precedence parser, and
    `lower` gives the node. Today's route keeps `true` and `false` as names; they are compared as the
    constants that the new parser gives."""
    from napkin.model.language import expressions as reader
    from napkin.model.language import nodes, parse

    def found_in(node, seen):
        if isinstance(node, nodes.Expr):
            yield node
        elif isinstance(node, (list, tuple)):
            for item in node:
                yield from found_in(item, seen)
        elif is_dataclass(node) and id(node) not in seen:
            seen.add(id(node))
            for item in fields(node):
                yield from found_in(getattr(node, item.name), seen)

    def named(node, names):
        if isinstance(node, expr.Ref):
            name = names.get(node.name, node.name)
            return expr.const(name == 'true') if name in ('true', 'false') else expr.ref(name)
        if isinstance(node, expr.Unary):
            return expr.unary(node.op, named(node.operand, names))
        if isinstance(node, expr.Binary):
            return expr.binary(node.op, named(node.left, names), named(node.right, names))
        if isinstance(node, expr.Compare):
            return expr.compare(node.ops, [named(part, names) for part in node.operands])
        if isinstance(node, expr.BoolOp):
            return expr.boolean(node.op, [named(part, names) for part in node.values])
        if isinstance(node, expr.IfElse):
            return expr.if_else(named(node.test, names), named(node.body, names), named(node.orelse, names))
        if isinstance(node, expr.Call):
            return expr.call(node.function, [named(part, names) for part in node.args])
        return node

    def one_line(tokens):
        out, i = [], 0
        while i < len(tokens):
            token = tokens[i]
            if token.is_name('is'):
                if i + 1 < len(tokens) and tokens[i + 1].is_name('not'):
                    out.append(' != ')
                    i += 1
                else:
                    out.append(' == ')
            elif token.kind == 'text':
                out.append((' ' if token.space else '') + P.text_text(token.value))
            else:
                out.append((' ' if token.space else '') + token.source)
            i += 1
        return ''.join(out).strip()

    files = sorted([*(BASE / 'examples').rglob('*.scn'), *(BASE / 'scenarios').rglob('*.scn')])
    total = same = 0
    why = Counter()
    for path in files:
        parsed = parse.parse(path.read_text(encoding='utf-8'))
        for found in found_in(parsed, set()):
            if not found.tokens:
                continue
            tree, names = reader.tree(found.tokens)
            total += 1
            old = named(expr.of_tree(tree, reader.FUNCTIONS), names)
            try:
                new = lower(P.parse_expression(one_line(found.tokens)))
            except (P.SyntaxProblem, TypeError) as problem:
                why[f'{type(problem).__name__}: {problem}'] += 1
                continue
            if new is old:
                same += 1
            else:
                why[f'{path.relative_to(BASE)}:{found.line}: another node'] += 1
    return total, same, why


def test_catalogue_expressions():
    total, same, why = catalogue_expressions()
    assert total == same and total > 2000, why
    return f'{total} expressions of the present models are the same node by today\'s route and by the new parser'


# ---- 9. names that Python keeps ---------------------------------------------------------------------------


def python_keywords():
    """What `napkin.core` does with `class + 1`: (evaluates, has a size, reads back from its text)."""
    node = expr.binary('add', expr.ref('class'), expr.const(1))
    evaluates = evaluation.value(node, {'class': 2}, None) == 3
    program = evaluation.program([('lambda', node)], [expr.ref('lambda')])
    evaluates = evaluates and program({'class': 2}, None) == (3,)
    try:
        expr.limited(node)
        sized = True
    except ExpressionError:
        sized = False
    try:
        again = expr.read(expr.text(node)) is node
    except SyntaxError:
        again = False
    return evaluates, sized, again


def test_python_keywords():
    evaluates, sized, again = python_keywords()
    assert evaluates and not sized and not again
    parsed = P.parse('grinder:\n    class: enum[A, B] = A\n    for = this.class == A\n')
    assert [member.name for member in parsed.items[0].members] == ['class', 'for']
    return (
        'a name that Python keeps (`class`) evaluates in napkin.core (function and program); '
        '`expr.limited` and `expr.read` refuse it, because they read the text again with `ast`'
    )


TESTS = [
    test_copied_pieces,
    test_catalogue_tokens,
    test_corpus,
    test_inline,
    test_refused,
    test_hunt,
    test_round_trip_corpus,
    test_round_trip_random,
    test_core,
    test_catalogue_expressions,
    test_python_keywords,
]


def main(argv):
    failed = 0
    for test in TESTS:
        try:
            print(f'ok    {test.__name__}: {test()}')
        except AssertionError as problem:
            failed += 1
            print(f'FAIL  {test.__name__}: {problem}')
    return 1 if failed else 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
