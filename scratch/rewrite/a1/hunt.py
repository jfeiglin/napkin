"""The hunt for ambiguities (brief A1, method 4): for each item, the grammar rule, the inputs that
tell the alternatives apart, and what the parser does with each.

    python hunt.py            checks each case against what is written here, and writes ambiguities.md
    python hunt.py --show     prints what the parser gives for each case, and checks nothing

A case is (kind, notation, what the parser must give). The kinds are those of `corpus/inline.txt`.
What the parser gives is written as a tree in brackets for an expression, and as the nodes of the
tree for a line. A case that must be refused starts with `!!` and holds a part of the message.
"""

from __future__ import annotations

import sys
from pathlib import Path

import parser as P

HERE = Path(__file__).resolve().parent


def render(kind, text):
    """What the parser gives for one piece of notation, on one line."""
    found = P.parse_inline(kind, text)
    if kind == 'expression':
        return P.sexpr(found)
    if kind == 'type':
        return f'{type(found).__name__} {P.type_text(found)}'
    if kind == 'range':
        return f'Range {P.show(found)}'
    return ' | '.join(' '.join(row.split()) for row in P.dump(found))


def comments(text):
    """The comments that the tokenizer keeps for a text, by row."""
    return [comment for line in P.lines(text) if line.kind == 'line' for comment in line.trailing]


ITEMS = [
    {
        'title': '`<` and `>`: a comparison, the brackets of a collection, a type',
        'rule': """
comparison := sum ( ('<' | '<=' | '>' | '>=' | '==' | '!=') sum )*     a chain points one way
primary    := '<' [ path (',' path)* [','] ] '>'                        a collection literal
type       := '<' type '>'                                               after a colon only
path       := primary ( '.' NAME [ '(' arguments ')' ] )*
""",
        'decides': (
            'The place decides. Where a value starts, `<` opens a collection. After a value, `<` compares. '
            'After the colon of a declaration, `<` opens a type. Inside a collection literal each member is '
            'a path with no operator, so the first `>` closes it. A chain of comparisons must point one way, '
            'so no chain looks like a pair of brackets.'
        ),
        'cases': [
            ('expression', 'low < high', '(compare low lt high)'),
            ('expression', '<this.primary, this.backup>', '(collection this.primary this.backup)'),
            ('expression', '<>', '(collection)'),
            ('expression', 'count(<a, b>) > 0', '(compare (call count (collection a b)) gt 0)'),
            ('expression', '<a, b>.where(critical)', '(method (collection a b) where critical)'),
            ('expression', 'lo <= x < hi', '(compare lo le x lt hi)'),
            ('expression', 'a < b > c', '!! a chain of comparisons points one way'),
            ('expression', '<a + b, c>', '!! a member with an operator needs brackets'),
            ('expression', '<(a if c else b), d>', '(collection (if c a b) d)'),
            ('declaration', 'pumps: <Pump> = <this.primary, this.backup>', 'Declare name=pumps type=<Pump> value=<this.primary, this.backup>'),
            ('declaration', 'idle: <Pump>= <>', 'Declare name=idle type=<Pump> value=<>'),
            ('declaration', 'ready = low < high', 'Declare name=ready value=low < high'),
            ('type', '<<Pump>>', 'CollectionType <<Pump>>'),
        ],
        'notes': [
            'A line can now end with `>` (`idle: <Pump> = <>`). The present tokenizer refuses a line that '
            'ends with an operator (`lex.py:203`); the rule keeps every other operator.',
            '`<Pump>= <>` has no space before `=`, so the tokenizer reads `>=`. Where a type closes, the '
            'parser reads it as `>` and then `=`.',
            'The tokenizer cannot know that `<` opens a bracket. So a collection literal goes on to the next '
            'row only inside `( ... )`, as any expression does.',
            'The parser reads `<<Pump>>`, a collection of collections. The type rules refuse it (types.md).',
        ],
    },
    {
        'title': 'A trailing `in [lo, hi]`: a range, against a membership test',
        'rule': """
declaration := [modifier] NAME [':' type] ['=' value] ['in' interval] evidence*
value       := expression with no `in` outside brackets
comparison  := sum 'in' interval                    in an assert, a guard, or inside brackets
interval    := '[' expression ',' expression ']'
""",
        'decides': (
            'After the `=` of a declaration, an `in` outside brackets ends the value and starts the range. '
            'After the `=` of an assignment it is refused, because the two readings differ. Everywhere else '
            '`in` is the membership test. It binds as a comparison and never chains.'
        ),
        'cases': [
            ('declaration', 'ok = samples.draw() in [lo, hi]', 'Declare name=ok value=samples.draw() range=[lo, hi]'),
            ('declaration', 'ok = (samples.draw() in [lo, hi])', 'Declare name=ok value=(samples.draw() in [lo, hi])'),
            ('declaration', 'care: h in [0 h, available]', 'Declare name=care type=h range=[0 h, available]'),
            ('declaration', 'assert total in [initial - tolerance, initial + tolerance]', 'Check condition=total in [initial - tolerance, initial + tolerance]'),
            ('statement', 'ok = (samples.draw() in [lo, hi])', 'Assign target=ok op== value=(samples.draw() in [lo, hi])'),
            ('statement', 'ok = samples.draw() in [lo, hi]', '!! put the whole test in brackets'),
            ('declaration', 'ok = a if x in [lo, hi] else b', '!! put the whole test in brackets'),
            ('declaration', 'ok = max(0, x) in [0, 5]', 'Declare name=ok value=max(0, x) range=[0, 5]'),
            ('declaration', 'ok = (x in [0, 5]) in [0, 1]', 'Declare name=ok value=(x in [0, 5]) range=[0, 1]'),
            ('expression', 'not x in [lo, hi]', '(not (within x lo hi))'),
            ('expression', 'a + b in [lo, hi] and ready', '(and (within (add a b) lo hi) ready)'),
            ('expression', 'a < b in [lo, hi]', '!! not chained with a comparison'),
            ('expression', 'x not in [lo, hi]', '!! there is no `not in`'),
            ('step', 'after 2 h when this.water in [0 L, 10 L]:', 'Stage delay=2 h guard=this.water in [0 L, 10 L]'),
        ],
        'notes': [
            'The first two cases differ by one pair of brackets and give different models: a number with a '
            'range, or a yes/no. The spec agrees this rule. The type check catches the slip only when the '
            'declaration writes `: bool` (a bool has no range).',
            'The range can stand on a line of its own under the declaration (`corpus/02-range-and-assert.scn`).',
        ],
    },
    {
        'title': '`->` and `<->`, against a comparison with a minus sign',
        'rule': """
tokens      := '<->' | '->' | '<=' | '<' | '-' | ...        the longest one that matches; `<-` is no token
flow        := 'flow' NAME ':' end ('->' | '<->') end
end         := 'SOURCE' | 'SINK' | NAME ('.' NAME)*
""",
        'decides': (
            'An arrow stands only between the two ends of a flow line, and an end is a path, never an '
            'expression. In an expression `<`, `-` and `>` in a row never make sense as an arrow: `-` needs '
            'a value after it, and `>` starts none. So the longest match is safe.'
        ),
        'cases': [
            ('expression', 'a < -b', '(compare a lt (neg b))'),
            ('expression', 'a<-b', '(compare a lt (neg b))'),
            ('expression', 'a>-b', '(compare a gt (neg b))'),
            ('expression', 'a<->b', '!! joins the two ends of a flow'),
            ('expression', 'a -> b', '!! joins the two ends of a flow'),
            ('expression', 'a - > b', '!! a value is missing before >'),
            ('declaration', 'flow link: west.water <-> east.water', 'FlowDecl name=link kind=reversible source=west.water sink=east.water'),
            ('declaration', 'flow fill: SOURCE -> tank.water', 'FlowDecl name=fill kind=directed source=SOURCE sink=tank.water'),
            ('declaration', 'flow f: a.x -> b.at(t).y', '!! it holds no call'),
            ('declaration', 'flow f: a <-> SINK', '!! a reversible route joins two stocks'),
        ],
        'notes': [],
    },
    {
        'title': 'Unit arithmetic',
        'rule': """
quantity := NUMBER ' ' unit                         exactly one space
unit     := factor ( ('/' | '-') factor )*          no space inside; '-' multiplies and binds tighter than '/'
factor   := NAME [ '^' ['-'] DIGITS ]
after a unit: a space, ',' , ')' , ']' , ':' or the end of the line
power    := path [ '**' signed ]                    `^` only inside a unit
""",
        'decides': (
            'A unit is one word that follows its number after one space. Inside the word `/` divides, `-` '
            'multiplies and `^` is a whole power. The word must end at a space, a comma, a closing bracket '
            'or a colon: an operator directly after a unit is refused. A number, a space and a name is '
            'always a quantity; a reserved word is never a unit.'
        ),
        'cases': [
            ('expression', '48 h / 2', '(div (q 48 h) 2)'),
            ('expression', '48 h/2', '!! Write a space on each side of an operator'),
            ('expression', '5 L/h^2', '(q 5 L/h^2)'),
            ('expression', '0.5 Wh/L', '(q 0.5 Wh/L)'),
            ('expression', 'this.water / (2 h)', '(div this.water (q 2 h))'),
            ('expression', 'this.water / 2 h', '(div this.water (q 2 h))'),
            ('expression', '10 L / 5 L/h', '(div (q 10 L) (q 5 L/h))'),
            ('expression', 'x ** 2', '(pow x 2)'),
            ('expression', 'x ^ 2', '!! a power of a value is a ** b'),
            ('expression', '(2 m) ** 2', '(pow (q 2 m) 2)'),
            ('expression', '2 m^2', '(q 2 m^2)'),
            ('expression', '3 person-years', '(q 3 person-years)'),
            ('expression', '3 person - years', '(sub (q 3 person) years)'),
            ('expression', '3 h-2 h', '!! Write a space on each side of an operator'),
            ('expression', '2 g', '(q 2 g)'),
            ('expression', '2 * g', '(mul 2 g)'),
            ('expression', '2 if c else 3 h', '(if c 2 (q 3 h))'),
            ('expression', '48h', '!! a unit follows its number after one space'),
            ('expression', '1e-3 s^-1', '(q 0.001 s^-1)'),
            ('type', 'L/h^2', 'UnitType L/h^2'),
            ('type', 'tunings/tuner-year', 'UnitType tunings/tuner-year'),
            ('type', 'g', 'NameType g'),
            ('step', 'after 0.5 h:', 'Stage delay=0.5 h'),
        ],
        'notes': [
            '`2 g` is 2 grams also when a value `g` is in scope; `2 * g` multiplies by that value. The spec '
            'itself has a field `hour` beside the unit `hour` of the prelude.',
            'A quantity is one value: `x / 2 h` is `x / (2 h)`, as today. The formatter writes the brackets.',
        ],
    },
    {
        'title': '`=`: a declaration or an assignment, against `==`',
        'rule': """
declaration := NAME [':' type] '=' value ...        in an entity, at the start of an event, in `inputs:`, at the top level
property    := path '=' value                       under a value or a flow, or by its full path
assignment  := path ('=' | '+=' | '-=') value       in a stage
capture     := NAME '=' value                       in the body of a trigger
comparison  := sum '==' sum                         inside any expression
""",
        'decides': (
            'The place of the line decides what `name = value` does. A line has one `=`. Inside an '
            'expression equality is `==`, and a second `=` is refused with that message.'
        ),
        'cases': [
            ('declaration', 'up = true', 'Declare name=up value=true'),
            ('statement', 'up = true', 'Assign target=up op== value=true'),
            ('trigger', 'shift = this.shift', 'Capture name=shift value=this.shift'),
            ('setup', 'clinic.delivery.request = 3 L/h', 'Property path=clinic.delivery.request value=3 L/h'),
            ('declaration', 'same = a == b', 'Declare name=same value=a == b'),
            ('declaration', 'same = a = b', '!! equality inside an expression is =='),
            ('expression', 'a = b', '!! equality inside an expression is =='),
            ('statement', 'this.beans += amount', 'Assign target=this.beans op=+= value=amount'),
            ('declaration', 'this.beans += amount', '!! belongs to a stage of an event'),
            ('statement', 'x: h = 2 h', '!! a stage declares no value'),
            ('expression', 'a is b', '!! equality is =='),
        ],
        'notes': [
            'A misspelled target of an assignment is an error of the resolver, not of the parser: in a stage '
            '`name = value` never declares.',
        ],
    },
    {
        'title': 'Bare enum members, with and without an expected type',
        'rule': """
NAME of a value            := [a-z_][A-Za-z0-9_]*
NAME of a template or case := [A-Z][A-Za-z0-9_]*
primary := CASE                 a capital word with no dot after it: a member of an enum
         | TEMPLATE '.' NAME    a capital word before a dot: a template (`Route.instances`)
""",
        'decides': (
            'The first letter decides. A word with a capital first letter and no dot after it is a member '
            'of an enum; before a dot it is a template. A name of a value starts with a small letter. So '
            '`OPEN` can never be a field, and the parser gives it a node of its own (`case`). Which enum it '
            'belongs to is the type checker\'s: it needs an expected type (R-A1-04).'
        ),
        'cases': [
            ('expression', 'this.gate == OPEN', '(compare this.gate eq (case OPEN))'),
            ('expression', 'this.gate == open', '(compare this.gate eq open)'),
            ('declaration', 'gate: enum[OPEN, CLOSED] = OPEN', 'Declare name=gate type=enum[OPEN, CLOSED] value=OPEN'),
            ('declaration', 'gate = OPEN', 'Declare name=gate value=OPEN'),
            ('expression', 'OPEN if ready else CLOSED', '(if ready (case OPEN) (case CLOSED))'),
            ('expression', 'Route.instances', 'Route.instances'),
            ('declaration', 'Gate: enum[OPEN, CLOSED] = OPEN', '!! the name of a value starts with a small letter'),
            ('declaration', 'gate: enum[open, closed] = open', '!! a member of an enum starts with a capital letter'),
            ('type', 'enum[OPEN, OPEN]', '!! an enum lists each member once'),
        ],
        'notes': [
            '`gate = OPEN` parses. With no declared type the checker has no enum for `OPEN` and refuses it.',
            'The census finds no present name of a value with a capital first letter, and no template '
            'with a small one (census.md).',
        ],
    },
    {
        'title': '`status`: a field of an occurrence, against the status display',
        'rule': """
status case := 'status' RATING ['when' expression] evidence*      RATING := ok | degraded | failed | inactive
declaration := 'status' (':' | '=') ...                           `status` is a name here
""",
        'decides': (
            '`status` is not reserved. The second token decides: a name after `status` makes a case of the '
            'status display, and `:` or `=` makes `status` a name. A status display belongs to an entity, so '
            'the body of an event refuses a case.'
        ),
        'cases': [
            ('declaration', 'status ok when this.work_state == DONE', 'StatusCase rating=ok condition=this.work_state == DONE'),
            ('declaration', 'status degraded', 'StatusCase rating=degraded'),
            ('step', 'status: enum[WEIGHING, ADDED] = WEIGHING', 'Declare name=status type=enum[WEIGHING, ADDED] value=WEIGHING'),
            ('statement', 'status = ADDED', 'Assign target=status op== value=ADDED'),
            ('expression', 'grinder.refill.occurrences.at(t).status', '(member (method grinder.refill.occurrences at t) status)'),
            ('declaration', 'status: enum[UP, DOWN] = UP', 'Declare name=status type=enum[UP, DOWN] value=UP'),
            ('step', 'status ok when this.done', '!! a status display belongs to an entity'),
            ('declaration', 'status fine when this.done', '!! a status case rates ok, degraded, failed or inactive'),
            ('declaration', 'status ok = 3', '!! one = on a line'),
        ],
        'notes': [
            'An entity can have a field `status` and a status display. The field is read as `clinic.status`. '
            'How a report names the display is brief A5\'s.',
            'The parser also refuses a case that follows the case with no condition: that one is the last.',
        ],
    },
    {
        'title': '`when`: the guard of a stage, a trigger, a reset',
        'rule': """
stage   := 'after' expression ['when' expression] ':' actions      on one line, then the block
wait    := 'after' expression                                      no colon, no block: a wait with no action
gate    := 'until' expression                                      no colon, no block
trigger := 'when' expression ':' captures* starts+ [reset]
reset   := 'reset' ('when' expression | 'after' expression)       the last line of a trigger
""",
        'decides': (
            'The first word of the line decides: `after` starts a step, `when` starts a trigger, `reset` '
            'ends a trigger. `when` is reserved, so the duration before it ends there. A guard does not '
            'go on to a row of its own, so a `when` under `after D` is never a guard.'
        ),
        'cases': [
            ('step', 'after delay when this.safe:', 'Stage delay=delay guard=this.safe'),
            ('step', 'when this.low_on_beans:', 'Trigger condition=this.low_on_beans'),
            ('trigger', 'reset when false', 'Reset kind=when value=false'),
            ('trigger', 'reset after 3 h', 'Reset kind=after value=3 h'),
            ('step', 'after 2 h', 'Stage delay=2 h'),
            ('step', 'after x if c else y when ready:', 'Stage delay=x if c else y guard=ready'),
            ('step', 'after 2 h when this.safe', '!! a stage is `after D:` or `after D when C:`'),
            ('step', 'until this.ready:', '!! until C is a gate with no body'),
            ('statement', 'when this.safe:', '!! a timing step stands at the level of the event'),
            ('step', 'reset when false', '!! reset is the last line of a trigger'),
            ('trigger', 'reset when a\nreset after 3 h', '!! reset is the last line of a trigger, and a trigger has one'),
        ],
        'notes': [
            '`after 2 h` with no colon is a wait with no action. The spec has no such line; without it an '
            'event that only takes time needs an empty stage (R-A1-14).',
        ],
    },
    {
        'title': '`formula(bool)` where a type stands, `formula(expression)` where a value stands',
        'rule': """
type    := 'formula' '(' type ')'              after the colon of a declaration or of a parameter
primary := 'formula' '(' expression ')'        where a value stands
""",
        'decides': (
            'The colon and the `=` of the declaration decide: a type stands after the colon, a value after '
            'the `=`. `formula` and `bool` are reserved, so `formula(bool)` where a value stands is refused. '
            'A unit and a value can share a name: the place says which one is meant.'
        ),
        'cases': [
            ('declaration', 'ready: formula(bool) = formula(this.water >= this.minimum)', 'Declare name=ready type=formula(bool) value=formula(this.water >= this.minimum)'),
            ('declaration', 'rate: formula(L/h) = formula(this.water / (2 h))', 'Declare name=rate type=formula(L/h) value=formula(this.water / (2 h))'),
            ('declaration', 'twice: formula(g) = formula(g)', 'Declare name=twice type=formula(g) value=formula(g)'),
            ('declaration', 'ready = formula(bool)', '!! bool is a word of the language'),
            ('declaration', 'ready: formula(this.water >= 2 L) = true', '!! this is a word of the language, not a type'),
            ('type', 'formula(formula(bool))', 'FormulaType formula(formula(bool))'),
            ('expression', 'formula', '!! formula keeps a calculation'),
        ],
        'notes': ['The parser reads `formula(formula(bool))`. The type rules refuse it (types.md).'],
    },
    {
        'title': 'Comments, `#` in a text, escaped quotes, wrapped clauses',
        'rule': """
row      := tokens ['#' comment]                  a `#` outside a text ends the row
text     := '"' ( any character but " and \\ | '\\"' | '\\\\' )* '"'     it can go on over rows that are indented deeper
logical line := one row, or more rows while '(' or '[' is open
wrapped clauses of a declaration: `in [lo, hi]` and `@record` on rows of their own under it
""",
        'decides': (
            'The tokenizer reads a text to its closing quote before it looks for `#`, so a `#` inside a text '
            'is a character of the text. A backslash writes a quote or a backslash, and nothing else. An '
            'expression goes on to the next row only inside round or square brackets.'
        ),
        'cases': [
            ('declaration', 'x = 3  # a note', 'Declare name=x value=3'),
            ('expression', '"a # b"', '"a # b"'),
            ('expression', '"say \\"hi\\""', '"say \\"hi\\""'),
            ('expression', '"C:\\\\data"', '"C:\\\\data"'),
            ('expression', '"a \\n b"', '!! a backslash writes a quote'),
            ('declaration', 'delay: h = 3\n    in [0.5, 12]  # hours\n    @timing', 'Declare name=delay type=h value=3 range=[0.5, 12] evidence=[@timing]'),
            ('declaration', 'total = sum(  # all of them\n    a,\n    # the second\n    b\n)', 'Declare name=total value=sum(a, b)'),
            ('declaration', 'total = a +\n    b', '!! the line ends with +'),
            ('declaration', 'note = "one\n    two"', 'Declare name=note value="one two"'),
            ('declaration', 'x = 3 # in [0, 5]', 'Declare name=x value=3'),
        ],
        'notes': [
            'The tokenizer keeps each comment with its row (`Line.trailing`), for the formatter.',
            'No text of the present models holds a backslash or a `#` (census.md), so the two escapes '
            'change no present text.',
        ],
    },
]


def run(show=False):
    """(the rows of ambiguities.md, the number of cases, the cases that are not as written)."""
    out = ['# The hunt for ambiguities', '']
    out.append('`hunt.py` makes this file. Each case is checked against what `hunt.py` writes for it.')
    out.append('A case that the parser refuses shows `refused:` and the message.')
    out.append('')
    count, wrong = 0, []
    for number, item in enumerate(ITEMS, 1):
        out.append(f'## {number}. {item["title"]}')
        out.append('')
        out.append('Grammar:')
        out.append('')
        out.append('```text')
        out += item['rule'].strip('\n').split('\n')
        out.append('```')
        out.append('')
        out.append(item['decides'])
        out.append('')
        out.append('| Where | Input | What the parser gives |')
        out.append('| --- | --- | --- |')
        for kind, text, expect in item['cases']:
            count += 1
            try:
                got = render(kind, text)
            except P.SyntaxProblem as problem:
                got = f'!! {problem.message}'
            if show:
                print(f'{kind:12} {text!r}\n             {got}')
            elif expect.startswith('!!'):
                if not got.startswith('!!') or expect[3:] not in got:
                    wrong.append((kind, text, expect, got))
            elif got != expect:
                wrong.append((kind, text, expect, got))
            shown = text.replace('\n', '<br>').replace('|', '\\|')
            given = ('refused: ' + got[3:]) if got.startswith('!!') else f'`{got}`'
            out.append(f'| {kind} | `{shown}` | {given.replace("|", chr(92) + "|")} |')
        out.append('')
        for note in item['notes']:
            out.append(f'- {note}')
        if item['notes']:
            out.append('')
    return out, count, wrong


def main(argv):
    if '--show' in argv:
        run(show=True)
        return 0
    out, count, wrong = run()
    for kind, text, expect, got in wrong:
        print(f'NOT AS WRITTEN [{kind}] {text!r}\n    wanted: {expect}\n    got:    {got}')
    (HERE / 'ambiguities.md').write_text('\n'.join(out), encoding='utf-8')
    print(f'{count} cases in {len(ITEMS)} items, {len(wrong)} not as written; wrote ambiguities.md')
    return 1 if wrong else 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
