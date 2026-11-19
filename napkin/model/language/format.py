"""The formatter: a tree (`nodes.py`) written again as text, in the language's own spacing.

`format_text(text)` is `write(parse(text))`, and `parse(write(tree)) == tree`: the formatter writes
each node from its fields, so formatting a formatted text changes nothing. It writes four spaces for
each level, one logical line on one row, and the brackets that the levels of binding need and no
others. A unit is written as the spec writes it, `/` close and `*` spaced: `4 L/h`, `6 person * year`,
`tunings/(tuner * year)` in a type. A quantity that a bare name multiplies or divides keeps its
brackets, `(2 h) * hour`, because without them the name would continue its unit (D12).

Comments and empty rows stay above the line that they were above, and a comment that ends a row stays
at the end of its line (the comments of the other rows of a long line go above it). A text longer than
the row breaks at single spaces onto rows one level deeper, where a row break reads as a space.
"""

from __future__ import annotations

from . import nodes as n
from .parse import HEADER, RESERVED, parse

WIDTH = 110
TEST, OR, AND, NOT, CMP, ARITH, TERM, FACTOR, POWER, ATOM = range(1, 11)
LEVELS = {'+': ARITH, '-': ARITH, '*': TERM, '/': TERM, '**': POWER}


def format_text(text):
    """A model text in the language's own layout."""
    return write(parse(text))


def write(tree):
    """The text of a tree (`nodes.File`)."""
    rows = []
    for item in tree.items:
        rows += line_rows(item, 0)
    rows += _lead_rows(tree.trailing)
    while rows and not rows[-1]:
        rows.pop()
    return '\n'.join(rows) + '\n' if rows else ''


# ---- expressions -------------------------------------------------------------------------------------


def number_text(value):
    """A number as the language writes it: `repr` writes `1e-05` and `1e+16`, which the lexer reads."""
    return repr(value)


def text_text(value):
    """A text in quotes, with its two escapes."""
    return '"' + value.replace('\\', '\\\\').replace('"', '\\"') + '"'


def unit_run(unit):
    """The unit run of a quantity: `L/h`, `person * year`."""
    out = unit[0][1]
    for op, name in unit[1:]:
        out += f'/{name}' if op == '/' else f' * {name}'
    return out


def level_of(node):
    if isinstance(node, n.IfElse):
        return TEST
    if isinstance(node, n.BoolOp):
        return OR if node.op == 'or' else AND
    if isinstance(node, n.Unary):
        return NOT if node.op == 'not' else FACTOR
    if isinstance(node, (n.Compare, n.Within)):
        return CMP
    if isinstance(node, n.Binary):
        return LEVELS[node.op]
    return ATOM


def _bare(node):
    """Whether a node is written as a bare name that would continue the unit run before it."""
    return isinstance(node, n.Name) and node.name not in RESERVED


def expression(node, level=TEST, bare_in=True, tail=False):
    """An expression with the brackets that its level needs. `bare_in` false: an `in` outside
    brackets would start a range, so a membership test is bracketed. `tail`: a bare name follows
    after `*` or `/`, so a quantity that ends the text is bracketed."""
    if level_of(node) < level:
        return f'({expression(node)})'
    if isinstance(node, n.Number):
        return node.written or number_text(node.value)
    if isinstance(node, n.Quantity):
        written = f'{node.written or number_text(node.value)} {unit_run(node.unit)}'
        return f'({written})' if tail else written
    if isinstance(node, n.Text):
        return text_text(node.value)
    if isinstance(node, n.Bool):
        return 'true' if node.value else 'false'
    if isinstance(node, n.Name):
        return node.name
    if isinstance(node, (n.Member, n.Method)):
        base = expression(node.base, ATOM)
        if isinstance(node.base, (n.Number, n.Quantity)):
            base = f'({base})'
        if isinstance(node, n.Member):
            return f'{base}.{node.name}'
        return f'{base}.{node.name}({", ".join(expression(arg) for arg in node.args)})'
    if isinstance(node, n.Call):
        if node.named:
            return (
                f'{node.function}({", ".join(f"{name}: {expression(value)}" for name, value in node.named)})'
            )
        return f'{node.function}({", ".join(expression(arg) for arg in node.args)})'
    if isinstance(node, n.Formula):
        return f'formula({expression(node.body)})'
    if isinstance(node, n.Unary):
        if node.op == 'not':
            return f'not {expression(node.operand, NOT, bare_in)}'
        return node.op + expression(node.operand, FACTOR, tail=tail)
    if isinstance(node, n.Binary):
        own = LEVELS[node.op]
        if node.op == '**':
            return f'{expression(node.left, ATOM)} ** {expression(node.right, FACTOR, tail=tail)}'
        # A quantity on the right of `*` or `/` is bracketed, as the spec writes `x / (2 h)`, and so is
        # one on the left of another quantity, `(3 person) * (2 year)`, or of a bare name, which would
        # continue its unit.
        product = node.op in ('*', '/')
        before = product and (_bare(node.right) or isinstance(node.right, n.Quantity))
        left = expression(node.left, own, tail=before)
        right = expression(node.right, own + 1, tail=tail or (product and isinstance(node.right, n.Quantity)))
        return f'{left} {node.op} {right}'
    if isinstance(node, n.Compare):
        written = expression(node.operands[0], ARITH)
        for op, operand in zip(node.ops, node.operands[1:]):
            written += f' {op} {expression(operand, ARITH)}'
        return written
    if isinstance(node, n.Within):
        written = f'{expression(node.value, ARITH)} in {interval(node.low, node.high)}'
        return written if bare_in else f'({written})'
    if isinstance(node, n.BoolOp):
        own = level_of(node)
        return f' {node.op} '.join(expression(value, own + 1, bare_in) for value in node.values)
    if isinstance(node, n.IfElse):
        return (
            f'{expression(node.body, OR, bare_in)} if {expression(node.test, OR, bare_in)} '
            f'else {expression(node.orelse, TEST, bare_in)}'
        )
    if isinstance(node, n.Collection):
        return '<' + ', '.join(expression(item, ATOM) for item in node.items) + '>'
    raise TypeError(f'no text for {type(node).__name__}')


def interval(low, high):
    """`[lo, hi]`, with a side left empty as the spec writes it: `[0,]`, `[, 10 L]`."""
    if high is None:
        return f'[{expression(low)},]'
    if low is None:
        return f'[, {expression(high)}]'
    return f'[{expression(low)}, {expression(high)}]'


def unit_text(unit):
    """The unit of a type: `L/h`, `person * year`, `tunings/(tuner * year)`."""
    if isinstance(unit, str):
        return unit
    right = f'({unit_text(unit.right)})' if isinstance(unit.right, n.UnitOp) else unit.right
    return f'{unit_text(unit.left)}/{right}' if unit.op == '/' else f'{unit_text(unit.left)} * {right}'


def type_text(node):
    if isinstance(node, n.WordType):
        return node.word
    if isinstance(node, n.NamedType):
        return node.name
    if isinstance(node, n.UnitType):
        return unit_text(node.unit)
    if isinstance(node, n.EnumType):
        return f'enum[{", ".join(node.members)}]'
    if isinstance(node, n.FormulaType):
        return f'formula({type_text(node.of)})'
    if isinstance(node, n.DistributionType):
        return f'distribution({type_text(node.of)})'
    if isinstance(node, n.CollectionType):
        return f'<{type_text(node.of)}>'
    raise TypeError(f'no type text for {type(node).__name__}')


# ---- lines ------------------------------------------------------------------------------------------


def _indent(depth):
    return ' ' * (4 * depth)


def _lead_rows(lead):
    return [f'{_indent(depth)}{text}' if text else '' for depth, text in lead]


def _cites(cites):
    return ''.join(f' @{cite.name}' for cite in cites)


def _escaped(piece):
    return piece.replace('\\', '\\\\').replace('"', '\\"')


def text_rows(prefix, value, depth):
    """The rows of `prefix` (a row's start, with its indentation) and a text that ends the row. A line
    break of the text is an empty row, and its next piece goes one level deeper; a text that is too
    long for the row breaks at single spaces onto rows one level deeper, since a row break inside a
    text reads as a space."""
    deeper = _indent(depth + 1)
    pieces = value.split('\n')
    if len(pieces) > 1:
        rows = [f'{prefix}"{_escaped(pieces[0])}']
        for k, piece in enumerate(pieces[1:], 1):
            rows.append('')
            if piece or k == len(pieces) - 1:
                rows.append(deeper + _escaped(piece))
        rows[-1] += '"'
        return rows
    words = [_escaped(word) for word in value.split(' ')]
    if len(prefix) + len(value) + 2 <= WIDTH or '' in words:
        return [prefix + text_text(value)]
    rows, current = [], f'{prefix}"{words[0]}'
    for word in words[1:]:
        if len(current) + 1 + len(word) > WIDTH:
            rows.append(current)
            current = deeper + word
        else:
            current += ' ' + word
    return [*rows, current + '"']


def _rows(node, depth, head, under=(), text=None):
    """The rows of a line: its lead, its head (and a text that ends it) with its comment, then the
    rows under it. The comments of the other rows of a long line go above it."""
    rows = _lead_rows(node.lead)
    comments = list(node.tail)
    rows += [f'{_indent(depth)}{comment}' for comment in comments[:-1]]
    written = [_indent(depth) + head] if text is None else text_rows(_indent(depth) + head, text, depth)
    if comments:
        written[-1] += f'  {comments[-1]}'
    return rows + written + list(under)


def _described(node, depth):
    """The rows of the text and the evidence of a line, one level under it."""
    rows = [] if node.text is None else text_rows(_indent(depth + 1), node.text, depth + 1)
    return rows + evidence_rows(node.evidence, depth + 1)


def evidence_rows(evidence, depth):
    rows, cites = [], []
    for item in evidence:
        if isinstance(item, n.Cite):
            cites.append(f'@{item.name}')
            continue
        if cites:
            rows.append(_indent(depth) + ' '.join(cites))
            cites = []
        rows += text_rows(f'{_indent(depth)}@{item.kind} ', item.text, depth)
        rows += _record_lines(item, depth + 1)
    if cites:
        rows.append(_indent(depth) + ' '.join(cites))
    return rows


def _record_lines(record, depth):
    rows = [f'{_indent(depth)}{kind} {identifier}' for kind, identifier in record.relations]
    if record.claims:
        rows.append(f'{_indent(depth)}claims:')
        for claim in record.claims:
            rows.append(f'{_indent(depth + 1)}{claim.id}')
            if claim.datum:
                rows.append(f'{_indent(depth + 2)}datum: {claim.datum}')
    return rows


def _block(items, depth):
    return [row for item in items for row in line_rows(item, depth)]


def _params(params):
    out = []
    for param in params:
        written = f'{param.name}: {type_text(param.type)}'
        if param.range is not None:
            written += f' in {interval(param.range.low, param.range.high)}'
        out.append(written)
    return ', '.join(out)


def _declaration_head(node):
    head = f'{node.modifier} ' if node.modifier else ''
    head += node.name
    if node.type is not None:
        head += f': {type_text(node.type)}'
    if node.value is not None:
        head += f' = {expression(node.value, bare_in=False)}'
    if node.range is not None and not node.range_row:
        head += f' in {interval(node.range.low, node.range.high)}'
    if node.scale is not None:
        head += f' scale {expression(node.scale, bare_in=False)}'
    return head + _cites(node.cites)


def _note_value(value):
    if isinstance(value, n.Text):
        return text_text(value.value)
    if isinstance(value, n.Number):
        return number_text(value.value)
    if isinstance(value, tuple):
        return '[' + ', '.join(_note_value(item) for item in value) + ']'
    return value


def line_rows(node, depth):
    """The rows of a line and of the lines under it, at `depth`."""
    inner = _indent(depth + 1)
    if isinstance(node, n.Scenario):
        under = []
        for key in HEADER:
            value = getattr(node, key)
            if value is None or value == ():
                continue
            if key in ('summary', 'scope', 'library'):
                under += text_rows(f'{inner}{key} ', value, depth + 1)
            elif key == 'timescales':
                under.append(f'{inner}{key} {", ".join(expression(item) for item in value)}')
            else:
                under.append(f'{inner}{key} {expression(value)}')
        return _rows(node, depth, f'{node.role} {text_text(node.title)}', under)
    if isinstance(node, n.Use):
        return _rows(node, depth, f'use {node.name}')
    if isinstance(node, n.Record):
        return _rows(
            node, depth, f'record {node.name}: {node.kind} ', _record_lines(node, depth + 1), node.text
        )
    if isinstance(node, n.Entity):
        under = []
        if node.text is not None:
            under += text_rows(inner, node.text, depth + 1)
        if node.title is not None:
            under += text_rows(f'{inner}title ', node.title, depth + 1)
        if node.role is not None:
            under.append(f'{inner}role {node.role}')
        under += evidence_rows(node.evidence, depth + 1) + _block(node.members, depth + 1)
        return _rows(node, depth, f'{node.name}:{_cites(node.cites)}', under)
    if isinstance(node, n.Table):
        head = f'{node.name}: {node.template} from {text_text(node.file)}{_cites(node.cites)}'
        return _rows(node, depth, head, _described(node, depth))
    if isinstance(node, n.Declaration):
        under = []
        if node.range is not None and node.range_row:
            under.append(f'{inner}in {interval(node.range.low, node.range.high)}')
        under += _described(node, depth) + _block(node.properties, depth + 1)
        return _rows(node, depth, _declaration_head(node), under)
    if isinstance(node, n.Property):
        head = f'{".".join(node.path)} = {expression(node.value, bare_in=False)}{_cites(node.cites)}'
        return _rows(node, depth, head, _described(node, depth))
    if isinstance(node, n.Flow):
        head = f'flow {node.name}:'
        if node.arrow:
            head += f' {".".join(node.source)} {node.arrow} {".".join(node.sink)}'
        under = _described(node, depth) + _block(node.properties, depth + 1) + _block(node.legs, depth + 1)
        return _rows(node, depth, head + _cites(node.cites), under)
    if isinstance(node, n.Event):
        head = f'{node.modifier} ' if node.modifier else ''
        head += f'{node.name} = event({_params(node.params)}):{_cites(node.cites)}'
        under = _described(node, depth) + _block(node.locals, depth + 1)
        under += _block(node.triggers, depth + 1) + _block(node.steps, depth + 1)
        return _rows(node, depth, head, under)
    if isinstance(node, n.Trigger):
        under = _described(node, depth) + _block(node.captures, depth + 1) + _block(node.starts, depth + 1)
        if node.reset is not None:
            under += line_rows(node.reset, depth + 1)
        return _rows(node, depth, f'when {expression(node.test)}:{_cites(node.cites)}', under)
    if isinstance(node, n.Capture):
        return _rows(node, depth, f'{node.name} = {expression(node.value, bare_in=False)}')
    if isinstance(node, n.Reset):
        return _rows(node, depth, f'reset {node.kind} {expression(node.value)}')
    if isinstance(node, n.Stage):
        head = f'after {expression(node.delay)}'
        if node.wait:
            return _rows(node, depth, head)
        if node.guard is not None:
            head += f' when {expression(node.guard)}'
        under = _described(node, depth) + _block(node.body, depth + 1)
        return _rows(node, depth, f'{head}:{_cites(node.cites)}', under)
    if isinstance(node, n.Gate):
        return _rows(node, depth, f'until {expression(node.test)}')
    if isinstance(node, n.Assign):
        head = f'{expression(node.target, ATOM)} {node.op} {expression(node.value, bare_in=False)}'
        return _rows(node, depth, head + _cites(node.cites))
    if isinstance(node, n.Start):
        return _rows(node, depth, expression(node.call))
    if isinstance(node, n.Move):
        head = f'move {expression(node.amount)} from {expression(node.source, ATOM)} to '
        return _rows(node, depth, head + expression(node.destination, ATOM) + _cites(node.cites))
    if isinstance(node, n.If):
        rows = _rows(node, depth, f'if {expression(node.test)}:', _block(node.then, depth + 1))
        if node.orelse is not None:
            rows += [f'{_indent(depth)}else:', *_block(node.orelse, depth + 1)]
        return rows
    if isinstance(node, n.Switch):
        under = _block(node.cases, depth + 1)
        if node.orelse is not None:
            under += [f'{inner}else:', *_block(node.orelse, depth + 2)]
        return _rows(node, depth, f'switch {expression(node.selector)}:', under)
    if isinstance(node, n.Case):
        head = node.member + (f' when {expression(node.guard)}' if node.guard is not None else '')
        return _rows(
            node,
            depth,
            f'{head}:{_cites(node.cites)}',
            _described(node, depth) + _block(node.body, depth + 1),
        )
    if isinstance(node, n.Solver):
        head = f'{node.modifier} ' if node.modifier else ''
        under = _described(node, depth)
        for key in ('inputs', 'solve_for', 'constraints', 'objective'):
            items = getattr(node, key)
            if not items:
                continue
            under.append(f'{inner}{key}:')
            for item in items:
                if isinstance(item, n.Line):
                    under += line_rows(item, depth + 2)
                else:
                    under.append(f'{_indent(depth + 2)}{expression(item)}')
        return _rows(node, depth, f'{head}{node.name} = solver:{_cites(node.cites)}', under)
    if isinstance(node, n.Binding):
        return _rows(node, depth, f'{node.name} = {expression(node.value, bare_in=False)}')
    if isinstance(node, n.Unknown):
        head = f'{node.name}: {type_text(node.type)}'
        if node.value is not None:
            head += f' = {expression(node.value, bare_in=False)}'
        if node.range is not None:
            head += f' in {interval(node.range.low, node.range.high)}'
        if node.scale is not None:
            head += f' scale {expression(node.scale, bare_in=False)}'
        return _rows(node, depth, head)
    if isinstance(node, n.Objective):
        return _rows(node, depth, f'{node.sense}({expression(node.value)})')
    if isinstance(node, n.Status):
        head = f'status {node.rating}' + (f' when {expression(node.test)}' if node.test is not None else '')
        return _rows(node, depth, head + _cites(node.cites), _described(node, depth))
    if isinstance(node, n.Assert):
        return _rows(
            node, depth, f'assert {expression(node.test)}{_cites(node.cites)}', _described(node, depth)
        )
    if isinstance(node, n.Sees):
        return _rows(node, depth, f'sees {expression(node.path, ATOM)}')
    if isinstance(node, n.Change):
        under = [] if node.text is None else text_rows(inner, node.text, depth + 1)
        if node.title is not None:
            under += text_rows(f'{inner}title ', node.title, depth + 1)
        if node.role is not None:
            under.append(f'{inner}role {node.role}')
        under += evidence_rows(node.evidence, depth + 1) + _block(node.members, depth + 1)
        return _rows(node, depth, f'change {node.name}:{_cites(node.cites)}', under)
    if isinstance(node, n.Options):
        return _rows(node, depth, f'options {text_text(node.group)}:', _block(node.options, depth + 1))
    if isinstance(node, n.Option):
        under = _described(node, depth) + _block(node.settings, depth + 1)
        return _rows(node, depth, f'{text_text(node.name)}:', under)
    if isinstance(node, n.Runs):
        return _rows(node, depth, 'runs:', _block(node.runs, depth + 1))
    if isinstance(node, n.RunLine):
        head = f'{node.name} = {" + ".join(text_text(item) for item in node.options)}'
        return _rows(node, depth, head, _described(node, depth))
    if isinstance(node, n.Notes):
        return _rows(node, depth, 'notes:', _block(node.notes, depth + 1))
    if isinstance(node, n.Note):
        head = f'{node.key}:' + (f' {_note_value(node.value)}' if node.value is not None else '')
        under = evidence_rows(node.evidence, depth + 1) + _block(node.notes, depth + 1)
        return _rows(node, depth, head + _cites(node.cites), under)
    raise TypeError(f'no rows for {type(node).__name__}')
