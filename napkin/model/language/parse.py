"""The parser (docs/language.md): the logical lines of a file (`lex.py`) as the parts of the file
(`nodes.py`), each with its place, and the line map {place: line}.

The parser reads the form of each line. What a name means, whether a value has its unit and which
records a line needs are the resolver's to check (`resolve.py`).
"""

from __future__ import annotations

import re

from . import lex
from .lex import SyntaxProblem
from .nodes import (
    Allocate,
    Assign,
    Change,
    Check,
    Cite,
    Claim,
    Event,
    Expr,
    File,
    Fire,
    Flow,
    Keyed,
    Lag,
    LinkBind,
    LinkDecl,
    Move,
    Note,
    Outcome,
    Output,
    OutputLines,
    Pair,
    Profile,
    Profiles,
    Record,
    Run,
    ScenarioBlock,
    Setting,
    Status,
    StatusLine,
    Table,
    Text,
    Thing,
    Use,
    Value,
)

FIELD_KINDS = ('input', 'var', 'let')
RECORD_KINDS = ('source', 'source_transfer', 'assumption', 'identity', 'convention')
HEALTH = ('ok', 'degraded', 'failed', 'inactive')
DISTRIBUTIONS = (
    'uniform',
    'triangular',
    'pert',
    'loguniform',
    'normal',
    'lognormal',
    'beta',
    'bernoulli',
    'categorical',
)
# The tokens that end a word with no space inside it.
WORD_ENDS = {',', '(', ')', '[', ']', ':', '=', '|'}
TEXT_PLACE = '""'  # the place of the text under a line: no name or key is written so
COPY = re.compile(r'[1-9][0-9]*')  # the number of a copy, after the name of its set
EVIDENCE = '@'  # the place of the evidence lines under a line, with their numbers
TOP = (
    'a line at the top level starts a declaration: scenario, variant, use, a thing (`name:`), change, '
    'assert, output, options, runs:, notes: or record'
)
# The lines under the first line of a main file or of a variant, in the order of the language page;
# only the main file names its library.
HEADER = ('summary', 'horizon', 'timescales', 'resolution', 'scope', 'library')
HEADS = {'scenario': 'main', 'variant': 'variant'}
MEMBER = (
    'a line of a thing is its text, evidence, title, role, sees, a field (input, var, let), a flow, a '
    'share, an event, an assert, an output or a status'
)


def closing(tokens):
    """The place of the bracket that closes the bracket that opens `tokens`."""
    depth = 0
    for j, token in enumerate(tokens):
        if token.kind == 'op' and token.value in ('(', '['):
            depth += 1
        elif token.kind == 'op' and token.value in (')', ']'):
            depth -= 1
            if depth == 0:
                return j
    return None


def column_of(line):
    """The column where a logical line starts: the column of its first token, from 1."""
    return line.tokens[0].column if line.tokens else line.depth * lex.INDENT + 1


class Cursor:
    """The tokens of one line (`tokens`, from `start`), read in order."""

    def __init__(self, line, tokens=None, start=0):
        self.line = line
        self.tokens = line.tokens if tokens is None else tokens
        self.i = start

    def peek(self, k=0):
        i = self.i + k
        return self.tokens[i] if i < len(self.tokens) else None

    def take(self):
        token = self.peek()
        if token is None:
            self.fail('the line ends too soon')
        self.i += 1
        return token

    def done(self):
        return self.i >= len(self.tokens)

    def fail(self, message, token=None):
        token = token or self.peek()
        if token is None:
            last = self.tokens[-1] if self.tokens else None
            raise SyntaxProblem(message, last.line if last else self.line.number)
        raise SyntaxProblem(message, token.line, token.column)

    def op(self, value, message):
        token = self.peek()
        if token is None or not token.is_op(value):
            self.fail(message)
        self.i += 1
        return token

    def at_op(self, *values):
        token = self.peek()
        return token is not None and token.is_op(*values)

    def name(self, message):
        token = self.peek()
        if token is None or token.kind != 'name':
            self.fail(message)
        self.i += 1
        return token.value

    def text(self, message):
        token = self.peek()
        if token is None or token.kind != 'text':
            self.fail(message)
        self.i += 1
        return token.value

    def end(self, message='nothing more belongs on this line'):
        if not self.done():
            self.fail(message)

    def word(self, message):
        """A word with no space inside it, such as an ID, a unit or a path (`A-DEMO-RESPONSE`, `L/h`,
        `{item}/h`): its tokens, joined."""
        token = self.peek()
        if token is None or token.kind in ('text', 'at') or (token.kind == 'op' and token.value in WORD_ENDS):
            self.fail(message)
        parts = [self.take()]
        while True:
            token = self.peek()
            if (
                token is None
                or token.space
                or token.kind in ('text', 'at')
                or (token.kind == 'op' and token.value in WORD_ENDS)
            ):
                break
            token.joined = True
            parts.append(self.take())
        return ''.join(part.source for part in parts)

    def chain(self, message, star=False):
        """A dotted name, `a`, `a.b` or `a.b.c`. A copy's number can follow the name of its set
        (`waves.2`); with `star`, a part can be `*` (`waves.*.arrive`)."""
        parts = [self.name(message)]
        while self.at_op('.'):
            self.i += 1
            token = self.peek()
            if star and token is not None and token.is_op('*'):
                self.i += 1
                parts.append('*')
                continue
            if (
                len(parts) == 1
                and token is not None
                and token.kind == 'number'
                and COPY.fullmatch(token.value)
            ):
                self.i += 1
                parts.append(token.value)
                continue
            parts.append(self.name(message))
        return '.'.join(parts)

    def until_evidence(self):
        """The tokens up to the evidence at the end of the line (outside brackets), and the evidence:
        the names that it cites."""
        depth, start = 0, self.i
        while not self.done():
            token = self.peek()
            if token.kind == 'op' and token.value in lex.OPENS:
                depth += 1
            elif token.kind == 'op' and token.value in lex.CLOSES:
                depth -= 1
            elif token.kind == 'at' and depth == 0:
                break
            self.i += 1
        content = self.tokens[start : self.i]
        return content, self.cites()

    def cites(self):
        """`@a @b` at the end of the line."""
        names = []
        while not self.done():
            at = self.take()
            if at.kind != 'at':
                self.fail('evidence at the end of a line names records: @name', at)
            token = self.peek()
            if token is None or token.kind != 'name':
                self.fail('@ names a record: @name, or writes one on its own line: @kind "explanation"', at)
            self.i += 1
            names.append((token.value, at.line))
        return names


class Parser:
    def __init__(self, text, counts=None):
        self.flat = lex.lines(text)
        self.top = lex.tree(self.flat)
        self.places = {}
        self.columns = {}  # {place: the column where the line of the place starts}
        # The numbers of the top-level asserts and of the change blocks, which go on from one file of a
        # model to the next (`parse_counted`), so that each line of a model has a place of its own.
        self.counts = dict(counts or {'assert': 0, 'change': 0})

    # ---- places and evidence ---------------------------------------------------------------------

    def mark(self, place, line, what='this line'):
        """Give a line its place. Two lines never have one place."""
        if place in self.places:
            raise SyntaxProblem(
                f'{what} is written twice; the first is at line {self.places[place]}',
                line.number,
                line.depth * lex.INDENT + 1,
            )
        self.places[place] = line.number
        self.columns[place] = column_of(line)
        return place

    def cited(self, names, place):
        return [Cite(place, line, name) for name, line in names]

    def text_line(self, line):
        """The text of a line that is a text, or a list of texts; None for any other line."""
        tokens = line.tokens
        if len(tokens) == 1 and tokens[0].kind == 'text':
            return tokens[0].value
        if tokens and tokens[0].kind == 'text':
            raise SyntaxProblem(
                'a text ends at its second double quote: write “ and ” inside a text',
                tokens[1].line,
                tokens[1].column,
            )
        if tokens and tokens[0].is_op('['):
            cursor = Cursor(line)
            values = self.text_list(cursor)
            if cursor.done() and values is not None:
                return values
        return None

    def text_list(self, cursor):
        """`["a", "b"]`, or None when the brackets hold something other than texts."""
        start = cursor.i
        cursor.op('[', 'a list opens with [')
        values = []
        while True:
            token = cursor.peek()
            if token is None or token.kind != 'text':
                cursor.i = start
                return None
            values.append(cursor.take().value)
            if cursor.at_op(','):
                cursor.i += 1
                continue
            if cursor.at_op(']'):
                cursor.i += 1
                return values
            cursor.i = start
            return None

    def record_line(self, line, place):
        """A line that starts with `@`: a record written in place, `@kind [ID] "explanation"` with its
        claims, or names, `@a @b`."""
        cursor = Cursor(line)
        cursor.take()
        token = cursor.peek()
        follows = cursor.peek(1)
        if (
            token is not None
            and token.kind == 'name'
            and token.value in RECORD_KINDS
            and follows is not None
            and follows.kind != 'at'
        ):
            cursor.i += 1
            identifier = None
            if cursor.peek() is not None and cursor.peek().kind != 'text':
                identifier = cursor.word('a record names an assumption ID, then its explanation in quotes')
            text = cursor.text('a record has its explanation in quotes: @kind "explanation"')
            cursor.end('a record is @kind [ID] "explanation"; its claims go under it')
            record = Record(place, line.number, token.value, identifier, text)
            self.record_lines(record, line, place)
            return [record]
        cursor.i = 0
        names = cursor.cites()
        if line.under:
            raise SyntaxProblem(
                'the lines under a record belong to a record written in place', line.under[0].number
            )
        return self.cited(names, place)

    def record_lines(self, record, line, place):
        for child in line.under:
            cursor = Cursor(child)
            key = cursor.name('under a record: claims:')
            cursor.op(':', 'under a record: claims:')
            cursor.end()
            if key == 'claims':
                where = self.mark((*place, 'claims:'), child, 'claims:')
                for i, item in enumerate(child.under):
                    claim_cursor = Cursor(item)
                    claim = claim_cursor.word('a claim is listed by its ID')
                    claim_cursor.end(
                        'a claim is listed by its ID; the explanation says how it supports the line'
                    )
                    claim_place = self.mark((*where, i), item)
                    datum = None
                    for sub in item.under:
                        sub_cursor = Cursor(sub)
                        if sub_cursor.name('under a claim: datum: key') != 'datum':
                            sub_cursor.fail('under a claim: datum: key')
                        sub_cursor.op(':', 'under a claim: datum: key')
                        if datum is not None:
                            raise SyntaxProblem('a claim names one datum', sub.number)
                        datum = sub_cursor.word('datum: names a key of the claim data')
                        sub_cursor.end()
                        self.mark((*claim_place, 'datum:'), sub)
                    record.claims.append(Claim(claim_place, item.number, claim, datum))
            else:
                cursor.fail('under a record: claims:')

    # ---- the lines under a declaration ---------------------------------------------------------

    def under(self, line, place):
        """The lines under a declaration, read in order: `('text', Text)`, `('evidence', [Cite or
        Record])`, `('key', key, Cursor after the colon, line)` or `('line', line)`."""
        evidence = 0
        for child in line.under:
            first = child.first
            if first.kind == 'at':
                where = self.mark((*place, EVIDENCE, evidence), child)
                evidence += 1
                yield 'evidence', self.record_line(child, where)
                continue
            value = self.text_line(child)
            if value is not None:
                if child.under:
                    raise SyntaxProblem('nothing goes under a text', child.under[0].number)
                yield (
                    'text',
                    Text(
                        self.mark((*place, TEXT_PLACE), child, 'the text of this line'), child.number, value
                    ),
                )
                continue
            second = child.tokens[1] if len(child.tokens) > 1 else None
            if first.kind == 'name' and second is not None and second.is_op(':'):
                yield 'key', first.value, Cursor(child, start=2), child
                continue
            yield 'line', child

    def keyed(self, cursor, line, place, key, texts=False, evidence=True, why=''):
        """A key with an expression and the evidence that ends its line, and its text and evidence
        lines under it when `texts`. A key that takes no `evidence` says `why`."""
        tokens, names = cursor.until_evidence()
        where = self.mark((*place, f'{key}:'), line, f'{key}:')
        if not tokens:
            cursor.fail(f'{key}: has a value')
        if names and not evidence:
            raise SyntaxProblem(f'{key}: takes no evidence: {why}', names[0][1])
        found = Keyed(where, line.number, Expr(where, line.number, tokens), self.cited(names, where))
        self.lines_under(line, where, found, texts=texts, evidence=evidence)
        return found

    def lines_under(self, line, place, holder, texts=True, evidence=True):
        """The text and the evidence lines under a line that holds nothing else."""
        for kind, *item in self.under(line, place):
            if kind == 'text' and texts and holder.text is None:
                holder.text = item[0]
            elif kind == 'evidence' and evidence:
                holder.support += item[0]
            else:
                raise SyntaxProblem('this line does not belong here', self.line_of(kind, item))

    @staticmethod
    def line_of(kind, item):
        if kind == 'key':
            return item[2].number
        if kind == 'line':
            return item[0].number
        if kind == 'text':
            return item[0].line
        return item[0][0].line if item[0] else 0

    def flag(self, cursor, key):
        token = cursor.take()
        if not token.is_name('true', 'false'):
            cursor.fail(f'{key}: is true or false', token)
        cursor.end()
        return token.value == 'true'

    # ---- small readers ---------------------------------------------------------------------------

    @staticmethod
    def until_words(cursor, words, what):
        """The tokens up to a name of `words` outside brackets, the evidence (`@`) or the end of the
        line; at least one."""
        start, depth = cursor.i, 0
        while not cursor.done():
            token = cursor.peek()
            if token.kind == 'op' and token.value in lex.OPENS:
                depth += 1
            elif token.kind == 'op' and token.value in lex.CLOSES:
                depth -= 1
            elif depth == 0 and token.kind == 'at':
                break
            elif depth == 0 and token.kind == 'name' and token.value in words:
                # A word that starts the value, or follows an operator, is a name of the value:
                # `= size size 10 h`, `= 2 * size`.
                before = cursor.tokens[cursor.i - 1] if cursor.i > start else None
                if before is not None and not (before.kind == 'op' and before.value not in lex.CLOSES):
                    break
            cursor.i += 1
        tokens = cursor.tokens[start : cursor.i]
        if not tokens:
            cursor.fail(what)
        return tokens

    @staticmethod
    def head(cursor, what):
        """The tokens of a line up to its closing colon, and the names that its evidence cites."""
        tokens, names = cursor.until_evidence()
        if not tokens or not tokens[-1].is_op(':'):
            cursor.fail(what)
        return tokens[:-1], names

    @staticmethod
    def ends_with_colon(line):
        """Whether a line, before its evidence, ends with a colon: a line that opens a block."""
        depth, last = 0, None
        for token in line.tokens:
            if token.kind == 'op' and token.value in lex.OPENS:
                depth += 1
            elif token.kind == 'op' and token.value in lex.CLOSES:
                depth -= 1
            elif token.kind == 'at' and depth == 0:
                break
            last = token
        return last is not None and last.is_op(':')

    @staticmethod
    def split_at(tokens, word):
        """The index of the name `word` outside brackets in `tokens`, or None."""
        depth = 0
        for i, token in enumerate(tokens):
            if token.kind == 'op' and token.value in lex.OPENS:
                depth += 1
            elif token.kind == 'op' and token.value in lex.CLOSES:
                depth -= 1
            elif depth == 0 and token.is_name(word):
                return i
        return None

    @staticmethod
    def comma_parts(tokens):
        """`tokens` split at the commas outside brackets."""
        parts, current, depth = [], [], 0
        for token in tokens:
            if token.kind == 'op' and token.value in lex.OPENS:
                depth += 1
            elif token.kind == 'op' and token.value in lex.CLOSES:
                depth -= 1
            if depth == 0 and token.is_op(','):
                parts.append(current)
                current = []
                continue
            current.append(token)
        if current:
            parts.append(current)
        return parts

    def list_items(self, line, cursor):
        """The items of a list: after its keyword on the line, and on each line under it, separated by
        commas. Each item is (its tokens, its line)."""
        out = [(part, line) for part in self.comma_parts(cursor.tokens[cursor.i :])]
        for child in line.under:
            if child.under:
                raise SyntaxProblem(
                    'the lines of a list hold its items, and nothing goes under them', child.number
                )
            out += [(part, child) for part in self.comma_parts(child.tokens)]
        for tokens, at in out:
            if not tokens:
                raise SyntaxProblem('an item of a list is missing between two commas', at.number)
        return out

    def text_and_evidence(self, line, place, holder, also=None):
        """The text and the evidence lines under a line, and the lines that `also(child)` reads (it
        returns False for a line that it does not read)."""
        evidence = 0
        for child in line.under:
            first = child.first
            if first.kind == 'at':
                where = self.mark((*place, EVIDENCE, evidence), child)
                evidence += 1
                holder.support += self.record_line(child, where)
                continue
            value = self.text_line(child)
            if value is not None:
                if child.under:
                    raise SyntaxProblem('nothing goes under a text', child.under[0].number)
                if holder.text is not None:
                    raise SyntaxProblem('a line has one text under it', child.number)
                holder.text = Text(
                    self.mark((*place, TEXT_PLACE), child, 'the text of this line'), child.number, value
                )
                continue
            if also is not None and also(child) is not False:
                continue
            raise SyntaxProblem('this line does not belong here', child.number)

    # ---- the file ----------------------------------------------------------------------------------

    def parse(self):
        out = File()
        declared = False  # a declaration other than the scenario line came before
        for k, line in enumerate(self.top):
            cursor = Cursor(line)
            first = cursor.peek()
            if first.kind != 'name':
                cursor.fail(TOP)
            word = first.value
            second = cursor.peek(1)
            if word in HEADS and second is not None and second.kind in ('name', 'text'):
                if second.kind == 'name':
                    cursor.fail(
                        f'{word} "Title": the folders name the scenario, so the line has no ID', second
                    )
                if k:
                    # A file's role is its first declaration (docs/language.md, §2.12).
                    cursor.fail(
                        f'the {word} line is the first declaration of its file: a file that starts with '
                        'another declaration is a module'
                    )
                out.scenario = self.scenario(line, HEADS[word])
                continue
            if word == 'use' and second is not None and second.kind == 'name':
                if declared:
                    cursor.fail('the use lines come first in a file, after its scenario line')
                out.uses.append(self.use(line))
                continue
            declared = True
            if word == 'change' and second is not None and second.kind == 'name':
                out.changes.append(self.thing(line, change=self.counts['change']))
                self.counts['change'] += 1
            elif word == 'assert' and second is not None and not second.is_op(':'):
                out.checks.append(self.check(line, ('assert:', self.counts['assert'])))
                self.counts['assert'] += 1
            elif word == 'output' and second is not None and second.kind == 'name':
                out.outputs.append(self.output(line, ('output:',)))
            elif word == 'options' and second is not None and second.kind == 'text':
                out.profiles.append(self.options(line))
            elif word == 'runs' and second is not None and second.is_op(':'):
                if out.runs_place is not None:
                    cursor.fail('a file has one runs: block')
                out.runs_place, out.runs = self.runs(line)
            elif word == 'notes' and second is not None and second.is_op(':'):
                if out.notes is not None:
                    cursor.fail('a file has one notes: block')
                out.notes = self.notes_block(line)
            elif word == 'record' and second is not None and second.kind == 'name':
                out.records.append(self.named_record(line))
            elif second is not None and second.is_op(':'):
                out.things.append(self.thing(line))
            else:
                cursor.fail(TOP)
        links(out)
        out.lines = dict(self.places)
        out.columns = dict(self.columns)
        return out

    def use(self, line):
        """`use a.b`: the module `<package>/a/b.scn`, named by its folders and its file from the folder
        of the package."""
        cursor = Cursor(line, start=1)
        parts = [cursor.name('use names a module: use file, or use folder.file')]
        while cursor.at_op('.'):
            cursor.i += 1
            parts.append(cursor.name('use names a module by its folders and its file: use folder.file'))
        cursor.end('use names one module: use file, or use folder.file')
        name = '.'.join(parts)
        return Use(self.mark(('use:', name), line, f'use {name}'), line.number, name)

    # ---- the scenario line -------------------------------------------------------------------------

    def scenario(self, line, role):
        """The first line of a main file, `scenario "Title"`, or of a variant, `variant "Title"`, with
        the scenario's lines under it (`HEADER`)."""
        word = line.tokens[0].value
        cursor = Cursor(line, start=1)
        place = self.mark(('scenario:',), line, word)
        block = ScenarioBlock(place, line.number, role)
        title = cursor.text(f'{word} "Title"')
        block.title = Text(self.mark((*place, 'title:'), line, 'the title'), line.number, title)
        cursor.end(f'{word} "Title"; its other lines go under it')
        lines = [key for key in HEADER if key != 'library' or role == 'main']
        for child in line.under:
            child_cursor = Cursor(child)
            key = child_cursor.name(f'the lines of the {word} are {", ".join(lines)}')
            if key not in lines:
                if key == 'library':
                    child_cursor.fail('a variant reads the library of its package: its main file names it')
                child_cursor.fail(f'the {word} has no line {key}; its lines are {", ".join(lines)}')
            where = self.mark((*place, f'{key}:'), child, key)
            if key in ('summary', 'scope', 'library'):
                setattr(
                    block, key, Text(where, child.number, child_cursor.text(f'{key} is a text in quotes'))
                )
                child_cursor.end()
            elif key == 'horizon':
                tokens = child_cursor.tokens[child_cursor.i :]
                if not tokens:
                    child_cursor.fail('horizon is a time: horizon 720 h')
                block.horizon = Expr(where, child.number, tokens)
            elif key == 'resolution':
                tokens = child_cursor.tokens[child_cursor.i :]
                if not tokens:
                    child_cursor.fail('resolution is a time: resolution 7 days')
                block.resolution = Expr(where, child.number, tokens)
            elif key == 'timescales':
                block.timescales = [
                    Expr((*where, i), at.number, tokens)
                    for i, (tokens, at) in enumerate(self.list_items(child, child_cursor))
                ]
            if key != 'timescales' and child.under:
                raise SyntaxProblem(f'nothing goes under {key}', child.under[0].number)
        return block

    # ---- things ------------------------------------------------------------------------------------

    def thing(self, line, change=None):
        """A thing, or with `change` (its number) a block `change name:`, whose lines are an instance's
        lines over the thing `name` of an earlier file."""
        cursor = Cursor(line, start=0 if change is None else 1)
        name = cursor.name(
            'a thing is `name:`, `Template:`, `name: Template`, `name: Template * k` or '
            '`name: Template from "file.csv"`'
        )
        cursor.op(':', f'{name}: ends with a colon')
        template = copies = table = None
        tokens, names = cursor.until_evidence()
        if tokens and change is not None:
            cursor.fail(f'change {name}: names the thing that it changes, and its evidence')
        if tokens:
            sub = Cursor(line, tokens)
            template = sub.name(f'{name}: Template')
            if sub.at_op('*'):
                sub.i += 1
                token = sub.take()
                if token.kind != 'number' or not token.value.isdigit() or int(token.value) < 1:
                    sub.fail(f'{name}: {template} * k makes k copies: k is a whole number, 1 or more', token)
                copies = int(token.value)
            elif sub.peek() is not None and sub.peek().is_name('from'):
                sub.i += 1
                table = sub.text(f'{name}: {template} from "file.csv" names the file of its table, in quotes')
            sub.end(f'{name}: {template}, {name}: {template} * k or {name}: {template} from "file.csv"')
        kind = 'template' if name[:1].isupper() and template is None else 'entity'
        if change is not None:
            kind = 'change'
            place = self.mark(('change:', change, name), line, f'change {name}')
        else:
            place = self.mark((name,), line, f'{name}')
        thing = Thing(place, line.number, kind, name, template, support=self.cited(names, place))
        # An instance's lines, and those of a change block, change members: they add none.
        instance = template is not None or change is not None
        if copies is not None:
            thing.copies = copies
            thing.copies_place = self.mark((*place, 'copies:'), line, 'the copies')
        if table is not None:
            thing.table = Table(self.mark((*place, 'table:'), line, 'the table'), line.number, table)
        counts = {'assert': 0, 'status': 0}
        status = None
        evidence = 0
        for child in line.under:
            first = child.first
            if first.kind == 'at':
                where = self.mark((*place, EVIDENCE, evidence), child)
                evidence += 1
                thing.support += self.record_line(child, where)
                continue
            value = self.text_line(child)
            if value is not None:
                if child.under:
                    raise SyntaxProblem('nothing goes under a text', child.under[0].number)
                if thing.text is not None:
                    raise SyntaxProblem('a thing has one text: its description', child.number)
                thing.text = Text(self.mark((*place, TEXT_PLACE), child), child.number, value)
                continue
            child_cursor = Cursor(child)
            word = first.value if first.kind == 'name' else None
            second = child_cursor.peek(1)
            if word == 'title' and second is not None and second.kind == 'text':
                child_cursor.i += 1
                thing.title = Text(
                    self.mark((*place, 'title:'), child, 'title'), child.number, child_cursor.text('')
                )
                child_cursor.end()
            elif word == 'role' and second is not None and second.kind == 'name' and not instance:
                child_cursor.i += 1
                thing.role = child_cursor.word('role names who acts')
                child_cursor.end()
                self.mark((*place, 'role:'), child, 'role')
            elif word == 'sees' and second is not None and not instance:
                child_cursor.i += 1
                thing.sees_place = self.mark((*place, 'sees:'), child, 'sees')
                thing.sees = []
                for tokens, at in self.list_items(child, child_cursor):
                    sub = Cursor(at, tokens)
                    fact = sub.chain('sees lists fields and events: sees a, b.c')
                    sub.end('sees lists fields and events, separated by commas')
                    thing.sees.append((fact, (*thing.sees_place, len(thing.sees))))
            elif word == 'status' and second is not None and second.kind == 'name':
                if status is None:
                    status = Status(self.mark((*place, 'status:'), child, 'the status'), child.number, [])
                    thing.members.append(status)
                status.lines.append(self.status_line(child, status, counts['status']))
                counts['status'] += 1
            elif word == 'assert' and not instance:
                thing.members.append(self.check(child, (*place, 'assert:', counts['assert'])))
                counts['assert'] += 1
            elif instance:
                thing.members.append(self.change(child, place))
            else:
                thing.members.append(self.member(child, place))
        self.value_outputs(thing, instance=instance)
        return thing

    def member(self, line, place):
        cursor = Cursor(line)
        first, second = cursor.peek(), cursor.peek(1)
        if first.kind != 'name' or second is None or second.kind != 'name':
            cursor.fail(MEMBER)
        word = first.value
        if word in FIELD_KINDS:
            return self.field(line, place)
        if word == 'event':
            return self.event(line, place)
        if word == 'flow':
            return self.flow(line, place)
        if word == 'share':
            return self.share(line, place)
        if word == 'output':
            return self.output(line, place)
        cursor.fail(MEMBER)

    def value_outputs(self, thing, instance=False):
        """`output x` with no expression makes the field `x` of the thing an output: its lines go to the
        field. In an instance, they are new lines of the output of member `x`: they go to the change of
        `x`, which gives nothing else when the instance has no other line for `x`."""
        fields = {m.name: m for m in thing.members if isinstance(m, Value)}
        changes = {m.name: m for m in thing.members if isinstance(m, Change)}
        kept = []
        for member in thing.members:
            if instance and isinstance(member, Output):
                if member.expr is not None or member.type is not None:
                    raise SyntaxProblem(
                        'an instance changes the lines of an output, not its unit or expression: output x',
                        member.line,
                    )
                change = changes.get(member.name)
                if change is None:
                    lines = Value(member.place[:-1], member.line, None, member.name)
                    change = changes[member.name] = Change(lines.place, member.line, member.name, None, lines)
                    kept.append(change)
                change.lines.output = member.lines
                continue
            if isinstance(member, Output) and member.expr is None and member.type is None:
                found = fields.get(member.name)
                if found is None:
                    raise SyntaxProblem(
                        f'output {member.name} names a field of this thing, or gives its expression: '
                        f'output {member.name} = E',
                        member.line,
                    )
                found.output = member.lines
                continue
            kept.append(member)
        thing.members = kept

    # ---- fields --------------------------------------------------------------------------------------

    def field(self, line, place):
        cursor = Cursor(line)
        kind = cursor.take().value
        node = self.field_head(cursor, line, place, kind)
        if isinstance(node, LinkDecl):
            return node
        self.text_and_evidence(line, node.place, node)
        return node

    def field_head(self, cursor, line, place, kind):
        """`name[: type] = value [in low to high] [size s]  @evidence`, from the name; a `let` with a
        template for its type and no value is a link that each instance binds."""
        name = cursor.name(f'{kind} name = value')
        where = self.mark((*place, name), line, name)
        node = Value(where, line.number, kind, name)
        if cursor.at_op(':'):
            cursor.i += 1
            node.type_place = (*where, ':')
            token = cursor.peek()
            if token is not None and token.kind == 'text':
                values = [cursor.take().value]
                while cursor.at_op('|'):
                    cursor.i += 1
                    values.append(cursor.text('named values are texts: "low" | "high"'))
                node.type = values
            elif kind == 'let' and cursor.at_op('['):
                cursor.i += 1
                target = cursor.name('let name: [Template]')
                cursor.op(']', 'a list of a template closes with ]')
                cursor.end('a link that each instance binds takes no evidence')
                return LinkDecl(where, line.number, name, target, True)
            else:
                node.type = cursor.word('a type is a unit, or named values: "low" | "high"')
                if kind == 'let' and cursor.done() and node.type[:1].isupper():
                    return LinkDecl(where, line.number, name, node.type, False)
        cursor.op('=', f'{kind} {name} = value')
        tokens = self.until_words(cursor, ('in', 'size'), '= is followed by the value')
        node.value = Expr(where, line.number, tokens)
        if cursor.peek() is not None and cursor.peek().is_name('in'):
            cursor.i += 1
            low = self.until_words(cursor, ('to',), 'in low to high')
            if cursor.peek() is None or not cursor.peek().is_name('to'):
                cursor.fail('in low to high')
            cursor.i += 1
            high = self.until_words(cursor, ('size',), 'in low to high')
            node.min = Keyed(
                self.mark((*where, 'min:'), line, 'the low end'),
                line.number,
                Expr((*where, 'min:'), line.number, low),
            )
            node.max = Keyed(
                self.mark((*where, 'max:'), line, 'the high end'),
                line.number,
                Expr((*where, 'max:'), line.number, high),
            )
        if cursor.peek() is not None and cursor.peek().is_name('size'):
            if kind != 'var':
                cursor.fail('size gives the solver the size of a var')
            cursor.i += 1
            size = self.until_words(cursor, (), 'size is followed by a number with its unit')
            node.size = Keyed(
                self.mark((*where, 'size:'), line, 'the size'),
                line.number,
                Expr((*where, 'size:'), line.number, size),
            )
        rest, names = cursor.until_evidence()
        if rest:
            cursor.fail(f'{kind} name = value [in low to high]' + (' [size s]' if kind == 'var' else ''))
        node.support = self.cited(names, where)
        node.kind = self.kind_of(kind, node)
        return node

    @staticmethod
    def kind_of(kind, node):
        """The kind of a field as the resolver reads it: `input`, `text` (an input that is words),
        `fixed` (a `let` of one value or one distribution), `formula` (any other `let`), `state` (a
        named or yes/no `var`), or `var` (a number that changes; the resolver finds what moves it)."""
        tokens = node.value.tokens if node.value is not None else []
        if kind == 'input':
            # A text input: words that braces show.
            words = len(tokens) == 1 and tokens[0].kind == 'text'
            return 'text' if words and node.type is None else 'input'
        if kind == 'let':
            return 'fixed' if Parser.literal(tokens) else 'formula'
        named = isinstance(node.type, list) or (len(tokens) == 1 and tokens[0].kind == 'text')
        yes_no = len(tokens) == 1 and tokens[0].is_name('true', 'false')
        return 'state' if named or yes_no else 'var'

    @staticmethod
    def literal(tokens):
        """Whether an expression is one value: a number with its unit, true or false, a text, or one
        distribution."""
        body = tokens[1:] if tokens and tokens[0].is_op('-') else tokens
        if len(body) in (1, 2) and body[0].kind == 'number' and (len(body) == 1 or body[1].kind == 'unit'):
            return True
        if len(tokens) == 1 and (tokens[0].kind == 'text' or tokens[0].is_name('true', 'false')):
            return True
        return (
            len(tokens) >= 3
            and tokens[0].is_name(*DISTRIBUTIONS)
            and tokens[1].is_op('(')
            and closing(tokens[1:]) == len(tokens) - 2
        )

    def change(self, line, place):
        """A line of an instance: `m = v`, `m:` with new evidence, a line with a kind (`input m = v`),
        or `output m` and the other lines of a thing that it changes."""
        cursor = Cursor(line)
        first, follows = cursor.peek(), cursor.peek(1)
        if (
            first.kind == 'name'
            and first.value == 'output'
            and follows is not None
            and follows.kind == 'name'
        ):
            # New lines of the output of a member: `value_outputs` gives them to the member's change.
            return self.output(line, place)
        if (
            first.kind == 'name'
            and first.value in FIELD_KINDS
            and follows is not None
            and follows.kind == 'name'
        ):
            kind = cursor.take().value
            node = self.field_head(cursor, line, place, kind)
            if isinstance(node, LinkDecl):
                raise SyntaxProblem('an instance binds the links of its template: name = thing', line.number)
            change = Change(node.place, line.number, node.name, node.kind, node)
            self.text_and_evidence(line, node.place, node)
            return change
        name = cursor.name('an instance changes a member of its template: `m = v`, or `m:` with new evidence')
        where = self.mark((*place, name), line, name)
        node = Value(where, line.number, None, name)
        if cursor.at_op('='):
            cursor.i += 1
            tokens = self.until_words(cursor, ('in',), '= is followed by the value')
            node.value = Expr(where, line.number, tokens)
            if cursor.peek() is not None and cursor.peek().is_name('in'):
                cursor.i += 1
                low = self.until_words(cursor, ('to',), 'in low to high')
                cursor.i += 1
                high = self.until_words(cursor, (), 'in low to high')
                node.min = Keyed(
                    self.mark((*where, 'min:'), line), line.number, Expr((*where, 'min:'), line.number, low)
                )
                node.max = Keyed(
                    self.mark((*where, 'max:'), line), line.number, Expr((*where, 'max:'), line.number, high)
                )
            rest, names = cursor.until_evidence()
            if rest:
                cursor.fail('m = v [in low to high]')
        else:
            cursor.op(':', 'an instance changes a member: `m = v`, or `m:` with new evidence')
            names = cursor.cites()
        node.support = self.cited(names, where)
        change = Change(node.place, line.number, node.name, None, node)
        self.text_and_evidence(line, where, node)
        return change

    # ---- events --------------------------------------------------------------------------------------

    def event(self, line, place):
        form = 'event name [once] [after D] [each W] [when C] [while K]:'
        cursor = Cursor(line, start=1)
        tokens, names = self.head(cursor, f'{form} ends with a colon')
        if not tokens or tokens[0].kind != 'name':
            cursor.fail(form)
        name = tokens[0].value
        where = self.mark((*place, name), line, name)
        node = Event(where, line.number, name, support=self.cited(names, where))
        rest = tokens[1:]
        if rest and rest[0].is_name('once'):
            node.once = True
            rest = rest[1:]
        # Each part runs to the next part's word, in the order of the form.
        words = ('after', 'each', 'when', 'while')
        for k, word in enumerate(words):
            if not rest or not rest[0].is_name(word):
                continue
            ends = [self.split_at(rest, later) for later in words[k + 1 :]]
            end = min((i for i in ends if i is not None), default=len(rest))
            if end == 1:
                cursor.fail(
                    {
                        'after': 'after is followed by the delay: after 2 h',
                        'each': 'each is followed by the values of a window: each timeline.beat',
                        'when': 'when is followed by the condition',
                        'while': 'while is followed by the condition under which the event still waits',
                    }[word]
                )
            mark = self.mark((*where, f'{word}:'), line, word)
            if word == 'each':
                node.each = [Expr(mark, line.number, part) for part in self.comma_parts(rest[1:end])]
            else:
                setattr(node, {'while': 'keep'}.get(word, word), Expr(mark, line.number, rest[1:end]))
            rest = rest[end:]
        if rest:
            Cursor(line, rest).fail(form)
        statements = []
        node.outcomes = []
        evidence = 0
        for child in line.under:
            first = child.first
            if first.kind == 'at':
                at = self.mark((*where, EVIDENCE, evidence), child)
                evidence += 1
                node.support += self.record_line(child, at)
                continue
            value = self.text_line(child)
            if value is not None:
                if child.under:
                    raise SyntaxProblem('nothing goes under a text', child.under[0].number)
                if node.text is not None:
                    raise SyntaxProblem('an event has one text, or a list of texts', child.number)
                node.text = Text(self.mark((*where, TEXT_PLACE), child), child.number, value)
                continue
            if self.role_line(child, where, node):
                continue
            if self.choice_line(child, where, node):
                continue
            if self.ends_with_colon(child):
                if statements:
                    raise SyntaxProblem(
                        'an event has its lines, or outcomes with their lines: not both', child.number
                    )
                node.outcomes.append(self.outcome(child, where))
                continue
            if node.outcomes:
                raise SyntaxProblem(
                    'an event has its lines, or outcomes with their lines: not both', child.number
                )
            statements.append(child)
        if statements:
            done = (*where, 'done')
            outcome = Outcome(done, statements[0].number, 'done')
            outcome.lines = [
                self.statement(Cursor(child), child, self.mark((*done, k), child))
                for k, child in enumerate(statements)
            ]
            node.outcomes = [outcome]
        return node

    def role_line(self, child, where, holder):
        """`role name` under an event or an outcome."""
        tokens = child.tokens
        if len(tokens) == 2 and tokens[0].is_name('role') and tokens[1].kind == 'name':
            if child.under:
                raise SyntaxProblem('nothing goes under role', child.under[0].number)
            holder.role = tokens[1].value
            self.mark((*where, 'role:'), child, 'role')
            return True
        return False

    def choice_line(self, child, where, event):
        """`choice` under an event: a person or an agent can choose its outcome in a run."""
        tokens = child.tokens
        if len(tokens) == 1 and tokens[0].is_name('choice'):
            if child.under:
                raise SyntaxProblem('nothing goes under choice', child.under[0].number)
            if event.choice:
                raise SyntaxProblem('an event says choice once', child.number)
            event.choice = True
            self.mark((*where, 'choice:'), child, 'choice')
            return True
        return False

    def outcome(self, line, place):
        cursor = Cursor(line)
        tokens, names = self.head(cursor, 'an outcome is `name [chance] [when C]:`')
        if not tokens or tokens[0].kind != 'name':
            cursor.fail('an outcome is `name [chance] [when C]:`')
        name = tokens[0].value
        where = self.mark((*place, name), line, f'the outcome {name}')
        node = Outcome(where, line.number, name, support=self.cited(names, where))
        chance = tokens[1:]
        cut = self.split_at(chance, 'when')
        if cut is not None:
            if cut == len(chance) - 1:
                cursor.fail('when is followed by the condition under which the outcome can happen')
            node.when = Expr(self.mark((*where, 'when:'), line, 'when'), line.number, chance[cut + 1 :])
            chance = chance[:cut]
        if len(chance) == 1 and chance[0].is_name('else'):
            node.is_else = True
        elif chance:
            node.chance = Expr((*where, 'chance'), line.number, chance)
        evidence = 0
        for child in line.under:
            first = child.first
            if first.kind == 'at':
                at = self.mark((*where, EVIDENCE, evidence), child)
                evidence += 1
                node.support += self.record_line(child, at)
                continue
            value = self.text_line(child)
            if value is not None:
                if node.text is not None:
                    raise SyntaxProblem('an outcome has one text', child.number)
                node.text = Text(self.mark((*where, TEXT_PLACE), child), child.number, value)
                continue
            if self.role_line(child, where, node):
                continue
            node.lines.append(
                self.statement(Cursor(child), child, self.mark((*where, len(node.lines)), child))
            )
        return node

    def statement(self, cursor, line, place):
        if line.under:
            raise SyntaxProblem('nothing goes under a line of a change', line.under[0].number)
        first = cursor.peek()
        if first.is_name('move'):
            cursor.i += 1
            amount = self.until_words(cursor, ('from',), 'move A from S to D')
            if cursor.done():
                cursor.fail('move A from S to D')
            cursor.i += 1
            source = cursor.chain('move A from S to D')
            token = cursor.peek()
            if token is None or not token.is_name('to'):
                cursor.fail('move A from S to D')
            cursor.i += 1
            target = cursor.chain('move A from S to D')
            cursor.end('a line of a change takes no evidence: it goes on the event or the outcome')
            return Move(place, line.number, Expr(place, line.number, amount), source, target)
        chain = cursor.chain(
            'a line of a change sets a value (x = v), moves an amount (move A from S to D), or names an event'
        )
        if cursor.done():
            return Fire(place, line.number, chain)
        token = cursor.peek()
        if not token.is_op('=', '+=', '-='):
            cursor.fail('a line of a change sets a value: x = v, x += v or x -= v; or it names an event')
        cursor.i += 1
        tokens, names = cursor.until_evidence()
        if names:
            cursor.fail('a line of a change takes no evidence: it goes on the event or the outcome')
        if not tokens:
            cursor.fail(f'{token.value} is followed by the value')
        return Assign(place, line.number, chain, token.value, Expr(place, line.number, tokens))

    # ---- flows and shares ----------------------------------------------------------------------------

    def pair(self, cursor, line, place):
        """`a -> b`, `-> b` (from outside the model) or `a ->` (out of it)."""
        source = 'outside' if cursor.at_op('->') else cursor.chain('a pair is a -> b, -> b or a ->')
        cursor.op('->', 'a pair is a -> b, -> b or a ->')
        token = cursor.peek()
        if token is None or token.kind == 'at' or token.is_name('at', 'while') or token.is_op(':'):
            target = 'outside'
        else:
            target = cursor.chain('a pair is a -> b, -> b or a ->')
        if source == 'outside' and target == 'outside':
            cursor.fail('a pair joins at least one value of the model')
        return Pair(place, line.number, source, target)

    def rate_and_while(self, cursor, line, where, holder):
        """`at RATE [while C]` of a flow or a pair."""
        if cursor.peek() is None or not cursor.peek().is_name('at'):
            cursor.fail('a flow moves at its rate: at RATE')
        cursor.i += 1
        rate = self.until_words(cursor, ('while',), 'at is followed by the rate')
        rate_at = self.mark((*where, 'rate:'), line, 'the rate')
        holder.rate = Keyed(rate_at, line.number, Expr(rate_at, line.number, rate))
        if cursor.peek() is not None and cursor.peek().is_name('while'):
            cursor.i += 1
            keep = self.until_words(cursor, (), 'while is followed by the condition')
            keep_at = self.mark((*where, 'while:'), line, 'while')
            holder.keep = Keyed(keep_at, line.number, Expr(keep_at, line.number, keep))

    def flow(self, line, place):
        cursor = Cursor(line, start=1)
        name = cursor.name('flow name: a -> b at RATE, or flow name at RATE: with its pairs under it')
        where = self.mark((*place, name), line, name)
        node = Flow(where, line.number, name)
        if cursor.at_op(':'):
            cursor.i += 1
            pair_at = (*where, 0)
            self.places[pair_at] = line.number
            self.columns[pair_at] = column_of(line)
            node.pair = self.pair(cursor, line, pair_at)
            self.rate_and_while(cursor, line, where, node)
            rest, names = cursor.until_evidence()
            if rest:
                cursor.fail('flow name: a -> b at RATE [while C]')
            node.support = self.cited(names, where)
            self.text_and_evidence(line, where, node)
            return node
        tokens, names = self.head(
            cursor, 'flow name at RATE [while C]: ends with a colon, its pairs under it'
        )
        sub = Cursor(line, tokens)
        self.rate_and_while(sub, line, where, node)
        sub.end('flow name at RATE [while C]:')
        node.support = self.cited(names, where)
        node.together_place = self.mark((*where, 'together:'), line, 'the pairs')
        node.together = []

        def pair_line(child):
            if child.first.kind == 'at' or self.text_line(child) is not None:
                return False
            pair_cursor = Cursor(child)
            pair_at = self.mark((*node.together_place, len(node.together)), child)
            pair = self.pair(pair_cursor, child, pair_at)
            if pair_cursor.peek() is not None and pair_cursor.peek().is_name('at'):
                pair_cursor.i += 1
                rate = self.until_words(pair_cursor, (), 'at is followed by the rate of the pair')
                rate_at = self.mark((*pair_at, 'rate:'), child, 'the rate')
                pair.rate = Keyed(rate_at, child.number, Expr(rate_at, child.number, rate))
            pair.support = self.cited(pair_cursor.cites(), pair_at)
            for sub_child in child.under:
                if sub_child.first.kind != 'at':
                    raise SyntaxProblem('under a pair, only its evidence', sub_child.number)
                pair.support += self.record_line(
                    sub_child, self.mark((*pair_at, EVIDENCE, len(pair.support)), sub_child)
                )
            node.together.append(pair)
            return True

        self.text_and_evidence(line, where, node, also=pair_line)
        if not node.together:
            raise SyntaxProblem('a flow with no pair on its line has its pairs under it', line.number)
        return node

    def share(self, line, place):
        cursor = Cursor(line, start=1)
        stock = cursor.chain('share VAR limit RATE [order f, g]')
        name = 'share_' + stock.replace('.', '_')
        where = self.mark((*place, name), line, f'the share of {stock}')
        node = Allocate(where, line.number, name, stock=stock, stock_place=(*where, 'stock:'))
        self.places[node.stock_place] = line.number
        self.columns[node.stock_place] = column_of(line)
        if cursor.peek() is None or not cursor.peek().is_name('limit'):
            cursor.fail('share VAR limit RATE [order f, g]: the most that VAR gives out each hour')
        cursor.i += 1
        limit = self.until_words(cursor, ('order',), 'limit is followed by a rate')
        limit_at = self.mark((*where, 'limit:'), line, 'the limit')
        node.limit = Keyed(limit_at, line.number, Expr(limit_at, line.number, limit))
        node.serve = None
        if cursor.peek() is not None and cursor.peek().is_name('order'):
            cursor.i += 1
            node.serve_place = self.mark((*where, 'serve:'), line, 'the order')
            tokens, names = cursor.until_evidence()
            node.serve = []
            for part in self.comma_parts(tokens):
                sub = Cursor(line, part)
                flow = sub.chain('order names flows: order f, g')
                sub.end('order names flows, separated by commas')
                node.serve.append((flow, (*node.serve_place, len(node.serve))))
        else:
            rest, names = cursor.until_evidence()
            if rest:
                cursor.fail('share VAR limit RATE [order f, g]')
        node.support = self.cited(names, where)
        self.text_and_evidence(line, where, node)
        return node

    # ---- asserts, status and outputs -----------------------------------------------------------------

    def check(self, line, place):
        """`assert C [within TOL]`. One that adds values and says how close the sum holds,
        `assert a + b is T within TOL`, is a sum."""
        cursor = Cursor(line, start=1)
        tokens, names = cursor.until_evidence()
        if not tokens:
            cursor.fail('assert is followed by its condition')
        where = self.mark(place, line, 'assert')
        node = Check(where, line.number, 'assert', support=self.cited(names, where))
        cut = self.split_at(tokens, 'within')
        within = None
        if cut is not None:
            within = tokens[cut + 1 :]
            tokens = tokens[:cut]
            if not within or not tokens:
                cursor.fail('assert C within TOL')
            within_at = self.mark((*where, 'within:'), line, 'within')
            node.within = Keyed(within_at, line.number, Expr(within_at, line.number, within))
        split = self.split_at(tokens, 'is') if within is not None else None
        terms = None
        if split is not None:
            head = tokens[:split]
            if head and head[0].is_op('(') and closing(head) == len(head) - 1:
                head = head[1:-1]
            part = Cursor(line, head)
            terms = []
            try:
                while True:
                    terms.append(part.chain(''))
                    if part.at_op('+'):
                        part.i += 1
                        continue
                    part.end('')
                    break
            except SyntaxProblem:
                terms = None
        if terms is not None:
            node.kind = 'conserve'
            node.terms = [(term, where) for term in terms]
            node.total = Expr(where, line.number, tokens[split + 1 :])
        else:
            node.expr = Expr(where, line.number, tokens)
        self.text_and_evidence(line, where, node)
        return node

    def status_line(self, line, status, k):
        """`status value [when C]`, with its text under it. The last line has no condition."""
        cursor = Cursor(line, start=1)
        value = cursor.name('status ok, status failed when C, …')
        if value not in HEALTH:
            cursor.fail(f'a status is {", ".join(HEALTH)}')
        place = self.mark((*status.place, k), line)
        node = StatusLine(place, line.number, value)
        if cursor.peek() is not None and cursor.peek().is_name('when'):
            cursor.i += 1
            tokens, names = cursor.until_evidence()
            if not tokens:
                cursor.fail('when is followed by the condition')
            node.condition = Expr(place, line.number, tokens)
        else:
            _, names = cursor.until_evidence()
            if _:
                cursor.fail('status value [when C]')
        status.support += self.cited(names, place)
        self.text_and_evidence(line, place, node)
        # The records under the line support the status, once: they move to it.
        status.support += node.support
        node.support = []
        return node

    def output(self, line, place):
        """`output name [: unit] [= E]`: a result, with its lines under it. Inside a thing, `output x`
        alone makes its field `x` an output."""
        cursor = Cursor(line, start=1)
        name = cursor.name('output name: unit = E')
        follows = cursor.peek()
        # `output x` in a thing makes its field x an output: its lines have the place of the field's.
        bare = place != ('output:',) and (follows is None or follows.kind == 'at')
        where = self.mark((*place, name, 'output:') if bare else (*place, name), line, f'the output {name}')
        node = Output(where, line.number, name)
        if cursor.at_op(':'):
            cursor.i += 1
            node.type = cursor.word('an output has its unit: output name: unit = E')
        if cursor.at_op('='):
            cursor.i += 1
            tokens, names = cursor.until_evidence()
            if not tokens:
                cursor.fail('= is followed by the expression of the output')
            node.expr = Expr(where, line.number, tokens)
        else:
            tokens, names = cursor.until_evidence()
            if tokens:
                cursor.fail('output name: unit = E')
        node.lines = self.output_lines(line, where)
        node.lines.support = self.cited(names, where) + node.lines.support
        return node

    def output_lines(self, line, place):
        node = OutputLines(place, line.number)

        def key_line(child):
            cursor = Cursor(child)
            key = cursor.name(
                'the lines of an output: its text, about, scope, category, level, signed, distinct, lag, unestimated'
            )
            where = (*place, f'{key}:')
            if key in node.keys:
                cursor.fail(f'{key} is written once')
            if key in ('about', 'unestimated'):
                self.mark(where, child, key)
                setattr(node, key, Text(where, child.number, cursor.text(f'{key} is a text in quotes')))
                cursor.end()
            elif key == 'scope':
                self.mark(where, child, 'scope')
                node.scope = Text(
                    where, child.number, cursor.text('scope is a text in quotes: whom it covers')
                )
                cursor.end()
            elif key == 'category':
                self.mark(where, child, 'category')
                node.category = cursor.name('category names its kind')
                cursor.end()
            elif key == 'level':
                self.mark(where, child, 'level')
                cursor.end('level stands alone: the output can fall')
                node.measure = 'level'
            elif key == 'signed':
                self.mark(where, child, 'signed')
                cursor.end('signed stands alone: the output can be below zero')
                node.signed = True
            elif key == 'lag':
                self.mark(where, child, 'lag')
                node.lag = self.lag(cursor, child, where)
            elif key == 'distinct':
                # The records that say why the counts of people that the output adds are of different
                # people.
                self.mark(where, child, 'distinct')
                rest, names = cursor.until_evidence()
                if rest:
                    cursor.fail('distinct stands alone, with its evidence: distinct  @record')
                node.distinct = Keyed(where, child.number, None, self.cited(names, where))
                self.lines_under(child, where, node.distinct, texts=False)
                node.keys[key] = where
                return True
            else:
                cursor.fail(f'an output has no line {key}')
            if child.under:
                raise SyntaxProblem(f'nothing goes under {key}', child.under[0].number)
            node.keys[key] = where
            return True

        self.text_and_evidence(line, place, node, also=key_line)
        return node

    # ---- options and runs ----------------------------------------------------------------------------

    def options(self, line):
        cursor = Cursor(line, start=1)
        name = cursor.text('options "Group":')
        cursor.op(':', f'options "{name}": ends with a colon')
        cursor.end()
        place = self.mark(('options:', name), line, f'the group "{name}"')
        node = Profiles(place, line.number, name)
        for child in line.under:
            child_cursor = Cursor(child)
            choice = child_cursor.text('a group of options holds its options: "Name":')
            child_cursor.op(':', f'"{choice}": ends with a colon')
            child_cursor.end()
            where = self.mark((*place, choice), child, f'the option "{choice}"')
            profile = Profile(where, child.number, choice)
            for item in child.under:
                value = self.text_line(item)
                if value is not None and not item.under:
                    if profile.text is not None:
                        raise SyntaxProblem('an option has one text: its line in the menu', item.number)
                    profile.text = Text(self.mark((*where, TEXT_PLACE), item), item.number, value)
                    continue
                item_cursor = Cursor(item)
                target = item_cursor.chain('a line of an option sets a value: thing.field = v')
                item_cursor.op('=', 'a line of an option sets a value: thing.field = v')
                tokens, names = item_cursor.until_evidence()
                if not tokens:
                    item_cursor.fail('= is followed by the value')
                setting_place = self.mark((*where, target), item, target)
                setting = Setting(
                    setting_place,
                    item.number,
                    target,
                    Expr(setting_place, item.number, tokens),
                    self.cited(names, setting_place),
                )
                self.lines_under(item, setting_place, setting, texts=False)
                profile.settings.append(setting)
            node.profiles.append(profile)
        return node

    def runs(self, line):
        cursor = Cursor(line, start=2)
        cursor.end('runs: has its runs under it')
        place = self.mark(('runs:',), line, 'runs:')
        out = []
        for child in line.under:
            child_cursor = Cursor(child)
            name = child_cursor.word('a run is `name = "Option" + "Option"`')
            child_cursor.op('=', 'a run is `name = "Option" + "Option"`')
            profiles = [child_cursor.text('a run names its options in quotes, joined by +')]
            while child_cursor.at_op('+'):
                child_cursor.i += 1
                profiles.append(child_cursor.text('a run names its options in quotes, joined by +'))
            where = self.mark((*place, name), child, f'the run {name}')
            run = Run(where, child.number, name, profiles)
            if child_cursor.peek() is not None and child_cursor.peek().is_name('versus'):
                child_cursor.i += 1
                run.versus = child_cursor.word('versus names a run')
                run.versus_place = self.mark((*where, 'versus:'), child, 'versus')
            child_cursor.end('name = "Option" + "Option" [versus run]')
            for item in child.under:
                value = self.text_line(item)
                if value is None or item.under or run.text is not None:
                    raise SyntaxProblem('under a run: its text', item.number)
                run.text = Text(self.mark((*where, TEXT_PLACE), item), item.number, value)
            out.append(run)
        return place, out

    # ---- lags --------------------------------------------------------------------------------------

    def lag(self, cursor, line, place):
        token = cursor.peek()
        follows = cursor.peek(1)
        if (
            token is not None
            and token.is_name('uniform', 'mixture')
            and follows is not None
            and follows.is_op('(')
        ):
            kind = cursor.take().value
            cursor.op('(', f'lag: {kind}(…)')
            node = Lag(place, line.number, kind)
            while True:
                if kind == 'mixture':
                    cursor.op('[', 'lag: mixture([share, delay], …)')
                    share = cursor.take()
                    if share.kind != 'number':
                        cursor.fail('a part of a mixture is [share, delay]: its share is a number', share)
                    cursor.op(',', 'a part of a mixture is [share, delay]')
                    node.shares.append(share.value)
                    node.delays.append(Expr((*place, len(node.delays)), line.number, self.until(cursor, ']')))
                    cursor.op(']', 'a part of a mixture is [share, delay]')
                else:
                    node.delays.append(
                        Expr((*place, len(node.delays)), line.number, self.until(cursor, ',', ')'))
                    )
                if cursor.at_op(','):
                    cursor.i += 1
                    continue
                break
            cursor.op(')', f'lag: {kind}(…) closes with )')
            cursor.end()
            if kind == 'uniform' and len(node.delays) != 2:
                cursor.fail('lag: uniform(min, max)')
            return node
        tokens = cursor.tokens[cursor.i :]
        if not tokens:
            cursor.fail('lag: is a time, uniform(a, b) or mixture([share, delay], …)')
        return Lag(place, line.number, 'fixed', [Expr(place, line.number, tokens)])

    @staticmethod
    def until(cursor, *ends):
        """The tokens up to one of `ends` outside brackets."""
        start, depth = cursor.i, 0
        while not cursor.done():
            token = cursor.peek()
            if depth == 0 and token.is_op(*ends):
                break
            if token.kind == 'op' and token.value in lex.OPENS:
                depth += 1
            elif token.kind == 'op' and token.value in lex.CLOSES:
                if depth == 0:
                    break
                depth -= 1
            cursor.i += 1
        tokens = cursor.tokens[start : cursor.i]
        if not tokens:
            cursor.fail('a value is missing here')
        return tokens

    # ---- notes and records -----------------------------------------------------------------------

    def notes_block(self, line):
        """`notes:`: notes of any keys, each with its value, its evidence and the notes under it. The
        calculation never reads them, and the language gives no key a meaning."""
        cursor = Cursor(line, start=2)
        cursor.end('notes: has its notes under it')
        place = self.mark(('notes:',), line, 'notes:')
        notes, support = self.notes(line, place)
        if support:
            raise SyntaxProblem('evidence under notes: belongs to a note', support[0].line)
        return notes

    def notes(self, line, place):
        """The notes under a line of `notes:`, and the evidence lines among them."""
        out, support, evidence = [], [], 0
        for child in line.under:
            cursor = Cursor(child)
            if cursor.peek().kind == 'at':
                where = self.mark((*place, EVIDENCE, evidence), child)
                evidence += 1
                support += self.record_line(child, where)
                continue
            key = cursor.word('a note is `key: value`')
            cursor.op(':', 'a note is `key: value`')
            where = self.mark((*place, f'{key}:'), child, f'{key}:')
            value = None
            if not cursor.done() and cursor.peek().kind != 'at':
                value = self.note_value(cursor)
            note = Note(where, child.number, key, value, self.cited(cursor.cites(), where))
            note.under, more = self.notes(child, where)
            note.support += more
            out.append(note)
        return out, support

    def note_value(self, cursor):
        token = cursor.peek()
        if token.kind == 'text':
            return Text(None, token.line, cursor.take().value)
        if token.is_op('['):
            cursor.i += 1
            values = []
            while not cursor.at_op(']'):
                values.append(self.note_value(cursor))
                if cursor.at_op(','):
                    cursor.i += 1
            cursor.op(']', 'a list closes with ]')
            return values
        if token.kind == 'number' and (
            cursor.peek(1) is None or cursor.peek(1).space or cursor.peek(1).is_op(',', ']')
        ):
            if cursor.peek(1) is not None and cursor.peek(1).kind == 'unit':
                cursor.fail(
                    'a number of a note has no unit: the notes are not values of the model', cursor.peek(1)
                )
            return cursor.take()
        return cursor.word('a note holds a text, a number, a word or a list')

    def named_record(self, line):
        cursor = Cursor(line, start=1)
        name = cursor.name('record name: kind "explanation"')
        cursor.op(':', f'record {name}: kind "explanation"')
        kind = cursor.name('record name: kind "explanation"')
        if kind not in RECORD_KINDS:
            cursor.fail(f'the kind of a record is one of {", ".join(RECORD_KINDS)}')
        identifier = None
        if cursor.peek() is not None and cursor.peek().kind != 'text':
            identifier = cursor.word('a record names an assumption ID, then its explanation in quotes')
        text = cursor.text('a record has its explanation in quotes')
        cursor.end('a record is `record name: kind [ID] "explanation"`; its claims go under it')
        place = self.mark(('record:', name), line, f'the record {name}')
        record = Record(place, line.number, kind, identifier, text, name=name)
        self.record_lines(record, line, place)
        return record


def links(out, names=None):
    """A `let` whose value names a thing, a list of things or `[]` is a link, and so is an instance's
    line, or a change block's line, that binds a slot of its template. `names` are the things that a
    link can name: by default the file's own; the merged file of a model names them all."""
    names = {thing.name for thing in out.things} if names is None else names

    def targets(expr):
        tokens = expr.tokens
        many = bool(tokens) and tokens[0].is_op('[') and tokens[-1].is_op(']')
        if many and len(tokens) == 2:
            return [], True  # `[]`: a list of no things, whose slot gives its type
        cursor = Cursor(None, tokens[1:-1] if many else tokens)
        found = []
        try:
            while True:
                chain = cursor.chain('')
                if chain.split('.')[0] not in names:
                    return None
                found.append(chain)
                if cursor.done():
                    break
                if not many or not cursor.at_op(','):
                    return None
                cursor.i += 1
        except SyntaxProblem:
            return None
        return (found if many else found[0]), many

    for thing in [*out.things, *out.changes]:
        for k, member in enumerate(thing.members):
            value = member.lines if isinstance(member, Change) else member
            if not isinstance(value, Value) or value.value is None:
                continue
            # `let` reads as `fixed` or `formula` (`kind_of`).
            if isinstance(member, Change) and member.kind not in (None, 'fixed', 'formula'):
                continue
            if not isinstance(member, Change) and value.kind not in ('fixed', 'formula'):
                continue
            # A `let` with a type is a value; a link has none.
            if value.type is not None:
                continue
            found = targets(value.value)
            if found is None:
                continue
            bound, many = found
            thing.members[k] = LinkBind(value.place, value.line, value.name, bound, many)


def parse(text):
    """The parts of a model file (`nodes.File`). Raises `SyntaxProblem`."""
    return Parser(text).parse()


def parse_counted(text, counts=None):
    """(the parts of one file of a model, the counts that the next file of the model starts from):
    its top-level asserts and change blocks are numbered on from `counts`."""
    parser = Parser(text, counts)
    return parser.parse(), parser.counts
