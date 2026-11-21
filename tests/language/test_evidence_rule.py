"""The owner's evidence rule (item 16 of the plan's changes after G0, `napkin/model/support.py`): a
warning, code `no_record`, for each part that rests on no record, of the kinds for which the
compiler before the rewrite refused a model, at the part's line. A value that an option or a
`change` sets keeps its error (R-A5-05). Then what the evidence tools need of the front end: the
records of a value for a member and a run (`DeclaredModel.evidence`), the document of a whole
package (`library.model_document`), and a record's error at its file and line. The lines below are
counted by hand in the texts."""

import json
import textwrap
from fractions import Fraction
from pathlib import Path

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from napkin.model.compile import compile_text, load_scenario
from napkin.model.ir import ModelError
from napkin.model.language.problems import LanguageError
from napkin.model.library import model_document
from napkin.model.support import DATUM
from tests.evidence.support import datum_package, evidence_library, fixture_claim, write_package
from tests.program.examples import UNITS

TEXT = """\
record fixture: assumption "A fixture of a test."
plant:
    input rate: L/h = 2 L/h
    input name: text = "north"
    input cited: L/h = 1 L/h  @fixture
    water: L = 8 L
    safe: bool = true
    mode: enum[ON, OFF] = ON
    share = formula(this.water / 8 L)
    fill = event():
        after 1 h:
            this.water += 1 L
    assert this.water >= 0 L
    status ok when this.safe
    status degraded
quiet:
    "A thing with a record, on which its yes/no and its status rest."
    @fixture
    on: bool = true
    status ok when this.on
    status failed
Utility:
    capacity: L = 5 L  @fixture
north: Utility
    capacity = 7 L
south: Utility
    capacity = 6 L  @fixture
top = 3
"""


def warned(text, tables=None):
    found = compile_text(textwrap.dedent(text), UNITS, tables=tables).reports
    return [(item.message.split(':')[0], item.message.split(': ')[1], item.line, item.file) for item in found]


def test_each_part_of_a_kind_that_needs_a_record_and_has_none_is_a_warning_at_its_line():
    """An input but a text, a stored number or yes/no, a timed event, an assertion, a case of a
    status display, a member's own value and a stored value of the top level; a yes/no and a status
    rest on their thing's records."""
    assert warned(TEXT) == [
        ('plant.rate', 'an input rests on no record', 3, ''),
        ('plant.water', 'a stored value rests on no record', 6, ''),
        ('plant.safe', 'a stored value rests on no record', 7, ''),
        ('plant.fill', 'an event that acts at a time rests on no record', 10, ''),
        ('plant.assert[0]', 'an assertion rests on no record', 13, ''),
        ('plant.status.case[0]', 'a case of a status display rests on no record', 14, ''),
        ('plant.status.case[1]', 'a case of a status display rests on no record', 15, ''),
        ('north.capacity', "a member's own value rests on no record", 25, ''),
        ('top', 'a stored value rests on no record', 28, ''),
    ]
    (first,) = [item for item in compile_text(TEXT, UNITS).reports if item.line == 3]
    assert first.code == 'no_record'


def test_a_record_on_each_part_leaves_no_warning():
    cited = TEXT.replace('= 2 L/h\n', '= 2 L/h  @fixture\n').replace('plant:\n', 'plant:\n    @fixture\n')
    for line in (
        'water: L = 8 L',
        'fill = event():',
        'assert this.water >= 0 L',
        'capacity = 7 L',
        'top = 3',
    ):
        cited = cited.replace(f'{line}\n', f'{line}  @fixture\n')
    assert warned(cited) == []


def test_a_column_of_a_table_rests_on_the_records_of_its_header():
    text = 'record fixture: assumption "A fixture."\nSite:\n    level: L = 0 L  @fixture\nsites: Site from "sites.csv"\n'
    assert warned(text, {'sites.csv': 'id,level: L\na,1\nb,2\n'}) == [
        ('sites.level', 'a column of a table rests on no record', 1, 'sites.csv')
    ]
    assert warned(text, {'sites.csv': 'id,level: L @fixture\na,1\nb,2\n'}) == []


def test_a_value_that_an_option_sets_with_no_record_stays_an_error():
    text = TEXT + 'options "Pace":\n    "Fast":\n        "Faster."\n        plant.rate = 4 L/h\n'
    with pytest.raises(LanguageError) as caught:
        compile_text(text, UNITS)
    assert caught.value.codes == ['record']


# A template value with its record, a member's own value with another, a row whose column cites a
# third, and an option that sets the value of every member with a fourth.
TRAIL = """\
record base: assumption "The capacity of a pump."
record own: source "The north pump, measured."
record column: source "The table of the pumps."
record big: assumption "Big pumps."
Pump:
    input capacity: L = 5 L  @base
north: Pump
    capacity = 7 L  @own
rows: Pump from "rows.csv"
options "Size":
    "Big":
        "Every pump is big."
        Pump.instances.capacity = 9 L  @big
"""


def test_the_evidence_of_a_value_for_a_member_and_a_run_takes_its_own_lines_and_its_options():
    """The trail of a member's value cites the template's records, the member's own line or its
    table's column, and the settings of the options that the run takes (`DeclaredModel.evidence`)."""
    declared = compile_text(TRAIL, UNITS, tables={'rows.csv': 'id,capacity: L @column\na,6\n'}).declared

    def names(member, options=()):
        return [item.name for item in declared.evidence('Pump.capacity', member, options)]

    assert names('north') == ['base', 'own']
    assert names('rows.a') == ['base', 'column']
    assert names('north', ('Big',)) == ['base', 'own', 'big']
    assert names('') == ['base']


SERVICE = """\
service:
    water: L = 8 L
        @assumption "A guess of a test."
            assumption A-NOWHERE
    status ok when this.water > 1 L
        @fixture
    status failed

record fixture: assumption "A fixture of a test."
"""


def service_package(tmp_path):
    """A package whose main file uses the module `common`, which writes the service."""
    folder = tmp_path / 'service'
    folder.mkdir()
    (folder / 'units.json').write_text(json.dumps({'L': {'dimensions': {'volume': 1}, 'scale': 1}}))
    (folder / 'model.scn').write_text('scenario "Service"\n    horizon 2 h\nuse common\n', encoding='utf-8')
    (folder / 'common.scn').write_text(SERVICE, encoding='utf-8')
    return folder / 'model.scn'


def test_the_document_of_a_package_reads_its_modules_and_names_parts_as_the_model_does(tmp_path):
    """`library.model_document` reads each file that the model reads, and names a case of a status
    display by the path that the declared model gives it, not by its place in a list."""
    found = model_document(service_package(tmp_path))
    assert {'service.water', 'service.status.case[0]', 'record fixture'} <= set(found)


def test_a_record_that_names_no_assumption_is_refused_at_its_file_and_line(tmp_path):
    entry = service_package(tmp_path)
    with pytest.raises(ModelError) as caught:
        load_scenario(entry)
    (item,) = caught.value.diagnostics
    assert (item['code'], Path(item['file']).name, item['line']) == ('provenance', 'common.scn', 2)
    assert 'A-NOWHERE' in item['message']


# ---- a value and the datum that its record cites (the audit's row 17) ------------------------------


def data_warnings(path):
    return [(item.message, item.line) for item in load_scenario(path).reports if item.code == DATUM]


@pytest.mark.parametrize(
    ('rate', 'datum', 'end', 'delay'),
    [
        ('2 people/h', (2, 'people/h'), '34 h', (34, 'h')),
        ('2 people/h', (48, 'people/day'), '1 days + 10 h', (34.0, 'h')),
        ('2.0 people/h', (2.0, 'people/h'), '36 h', (1.5, 'days')),
        ('0.5 people/h * 4', (48, 'people/day'), '0.25 days * 4 + 10 h', (34, 'h')),
    ],
)
def test_a_value_equal_to_its_cited_datum_however_spelled_is_no_warning(tmp_path, rate, datum, end, delay):
    """A datum states a number and a unit: a value that cites it is that number, read in dimension
    and scale and exactly, however either is spelled (a unit, a decimal, a sum or product of such
    numbers). A float of the library is the decimal that writes it (`core.units.rational`)."""
    path = datum_package(tmp_path, rate=rate, datum=datum, end=end, delay=delay)
    assert data_warnings(path) == []


def test_a_value_that_differs_from_its_cited_datum_is_a_warning_with_both_numbers(tmp_path):
    """The audit's row 17: an input of 99 h whose record cites a datum of 34 h compiled silently. It
    warns now at the value's line, with both numbers; so does a value near its datum, since a datum
    states no precision (a value of 2.4 people/h is not the datum 2 people/h, nor 34.04 h the datum
    34.0 h: such a value needs a derivation or an assumption), a datum of another dimension, and an
    option's setting whose record cites the datum."""
    path = datum_package(tmp_path / 'a', end='99 h')
    line = next(k for k, row in enumerate(path.read_text().split('\n'), 1) if 'input end' in row)
    assert data_warnings(path) == [
        ('service.end: @timing cites the datum delay of C-ACTION, 34 h, and 99 h differs from it', line)
    ]
    (rate,) = data_warnings(datum_package(tmp_path / 'b', rate='2.4 people/h'))
    assert rate[0].endswith('the datum rate of C-ACCESS, 2 people/h, and 2.4 people/h differs from it')
    (near,) = data_warnings(datum_package(tmp_path / 'c', end='34.04 h', delay=(34.0, 'h')))
    assert near[0].endswith('the datum delay of C-ACTION, 34.0 h, and 34.04 h differs from it')
    (other,) = data_warnings(datum_package(tmp_path / 'd', delay=(34, 'people')))
    assert other[0].endswith('34 people, and 34 h is of another dimension')
    (option,) = data_warnings(datum_package(tmp_path / 'e', half='@access'))
    assert option[0].startswith(
        'service.rate: @access cites the datum rate of C-ACCESS, 2 people/h, and 1 people/h'
    )


# ---- the compiler's own folding of a cited value (the audit's row 17 again) --------------------------

# Each leaf: its text and its exact value in hours, worked by hand from the prelude's units (a day is
# 24 h and a week 168 h), and a plain multiplier with its value.
HOURS = [
    ('2 h', Fraction(2)),
    ('0.5 h', Fraction(1, 2)),
    ('1.25 h', Fraction(5, 4)),
    ('0.25 days', Fraction(6)),
    ('1 days', Fraction(24)),
    ('0.125 week', Fraction(21)),
]
PLAIN = [('2', Fraction(2)), ('0.5', Fraction(1, 2)), ('3', Fraction(3))]


def folded(data, depth):
    """A random expression of hours that the compiler fixes when the model compiles, built from every
    operation that it folds exactly (a sum, a difference, a product or a quotient by a plain number,
    `min`, `max`, `abs`, `clip`, a conditional whose condition is fixed, a square root of an exact
    square, a whole power, a unit conversion), and its exact value in hours, worked here."""
    if depth == 0 or data.draw(st.integers(0, 3)) == 0:
        return data.draw(st.sampled_from(HOURS))
    a, b = folded(data, depth - 1), folded(data, depth - 1)
    form = data.draw(
        st.sampled_from(['add', 'sub', 'scale', 'divide', 'min', 'max', 'abs', 'clip', 'if', 'sqrt', 'power'])
    )
    if form == 'add':
        return f'({a[0]} + {b[0]})', a[1] + b[1]
    if form == 'sub':
        return f'({a[0]} - {b[0]})', a[1] - b[1]
    if form == 'scale':
        k = data.draw(st.sampled_from(PLAIN))
        return f'({k[0]} * {a[0]})', k[1] * a[1]
    if form == 'divide':
        k = data.draw(st.sampled_from(PLAIN))
        return f'({a[0]} / {k[0]})', a[1] / k[1]
    if form in ('min', 'max'):
        return f'{form}({a[0]}, {b[0]})', (min if form == 'min' else max)(a[1], b[1])
    if form == 'abs':
        return f'abs({a[0]} - {b[0]})', abs(a[1] - b[1])
    if form == 'clip':
        c = folded(data, depth - 1)
        low, high = sorted((b, c), key=lambda item: item[1])
        return f'clip({a[0]}, {low[0]}, {high[0]})', min(max(a[1], low[1]), high[1])
    if form == 'if':
        p, q = folded(data, depth - 1), folded(data, depth - 1)
        test, holds = data.draw(
            st.sampled_from(
                [
                    (f'{p[0]} < {q[0]}', p[1] < q[1]),
                    (f'{p[0]} >= {q[0]}', p[1] >= q[1]),
                    (f'not ({p[0]} == {q[0]})', p[1] != q[1]),
                    (f'({p[0]} <= {q[0]} and true)', p[1] <= q[1]),
                    (f'({p[0]} > {q[0]} or false)', p[1] > q[1]),
                    (
                        f'({p[0]} in [{min(p, q, key=lambda i: i[1])[0]}, {max(p, q, key=lambda i: i[1])[0]}])',
                        True,
                    ),
                ]
            )
        )
        return f'({a[0]} if {test} else {b[0]})', a[1] if holds else b[1]
    if form == 'sqrt':
        return f'sqrt({a[0]} * {a[0]})', abs(a[1])
    # A whole power: the square of a time over a time.
    if b[1] == 0:
        return a
    return f'(({a[0]}) ** 2 / {b[0]})', a[1] ** 2 / b[1]


def tail(gap):
    """A sum that adds `gap` hours exactly: its numerator in hours over its denominator."""
    gap = Fraction(gap)
    return f'({gap.numerator} h) / {gap.denominator}'


@settings(derandomize=True, max_examples=40, deadline=None)
@given(st.data())
def test_a_cited_value_is_the_number_that_the_compilers_folding_gives_it(tmp_path_factory, data):
    """The rule (the audit's row 17): a value whose record cites a datum is that number. The value
    compared is what the compiler's own folding of constants gives (`semantic.exact_value`), every
    operation folded exactly: for random expressions of every operation, made equal to the datum (34
    h) or 10^-18 h from it, the datum warns exactly when the value differs, as worked here."""
    expression, value = folded(data, data.draw(st.integers(1, 3)))
    near = data.draw(st.booleans())
    end = f'({expression}) + {tail(34 - value)}' + (' + (1 h) / 1000000000000000000' if near else '')
    path = datum_package(tmp_path_factory.mktemp('fold'), end=end)
    found = data_warnings(path)
    if near:
        (warning,) = found
        assert warning[0].startswith(
            'service.end: @timing cites the datum delay of C-ACTION, 34 h, and 34.000000000000000001 h'
        )
        assert warning[0].endswith('differs from it')
    else:
        assert found == [], (end, found)


def test_a_cited_value_that_the_compiler_cannot_fix_is_a_warning(tmp_path):
    """A value that cites a datum and that only a run knows (a draw, or a value that reads another
    input, which a configuration may set) is a `datum` warning, never a silent pass: it is computed
    when the model runs, and a datum names a number."""
    for k, end in enumerate(('uniform(30 h, 40 h).draw()', 'this.n * 34 h / (20 people)')):
        (warning,) = data_warnings(datum_package(tmp_path / str(k), end=end))
        assert warning[0] == (
            'service.end: @timing cites the datum delay of C-ACTION, 34 h, and it is computed when the model '
            'runs, and a datum names a number'
        )


def test_a_number_token_is_the_exact_decimal_that_it_writes(tmp_path):
    """A number token is the decimal that it writes, never read through a float: 34.000000000000000001
    h is not the datum 34 h (a float holds both as 34.0), and 33.999999999999999999 h +
    0.000000000000000001 h is."""
    (warning,) = data_warnings(datum_package(tmp_path / 'a', end='34.000000000000000001 h'))
    assert warning[0].endswith('34 h, and 34.000000000000000001 h differs from it')
    assert (
        data_warnings(datum_package(tmp_path / 'b', end='33.999999999999999999 h + 0.000000000000000001 h'))
        == []
    )
    assert data_warnings(datum_package(tmp_path / 'c', end='34.000000000000000000 h')) == []


# A package whose every kind of value cites the datum delay of C-ACTION (34 h).
CITING = """\
scenario "Citing"
    horizon 10 h
    library "../library"

Crew:
    input wait: h = 34 h  @timing
    late = formula(this.wait + 0 h)  @timing
    kept = formula(17 h * 2)  @timing
    odd = formula(35 h)  @timing
    pick: distribution(h) = uniform(30 h, 40 h)  @timing
    go = event():  @fixture
        pause: h = 34 h  @timing
        after 1 h
north: Crew
    wait = 1 days + 10 h  @timing
crews: Crew from "crews.csv"

record timing: source "The time before the service stops."
    claims:
        C-ACTION
            datum: delay
record fixture: assumption "The crew goes at once."
    assumption RT-FIXTURE
"""


def test_every_kind_of_value_that_cites_a_datum_is_that_number_or_a_warning(tmp_path):
    """Each value that cites the datum 34 h, of every kind: an input (34 h), a member's own value
    (1 days + 10 h) and a cell (34, in the column `wait`) are it; a formula that the compiler fixes
    is compared (`17 h * 2` is it, `35 h` differs); a formula that reads another value is computed
    when the model runs; a distribution is no number; an event's local is compared as any value."""
    library = evidence_library()
    library['claims'] = [fixture_claim('C-ACTION', data={'delay': {'value': 34, 'unit': 'h'}})]
    files = {'model.scn': CITING, 'crews.csv': 'id,wait: h  @timing\nfirst,34\nsecond,35\n'}
    path = write_package(tmp_path, files, library)
    found = sorted(message for message, _ in data_warnings(path))
    head = '@timing cites the datum delay of C-ACTION, 34 h, and'
    assert found == sorted(
        [
            f'Crew.late: {head} it is computed when the model runs, and a datum names a number',
            f'Crew.odd: {head} 35 h differs from it',
            f'Crew.pick: {head} it is a distribution, and a datum names a number',
            f'crews.second.wait: {head} 35 h differs from it',
        ]
    )


@pytest.mark.parametrize('shared', [False, True])
@pytest.mark.parametrize('token', ['34.0000000000000001', '340000000000000001e-16'])
def test_json_evidence_preserves_the_exact_decimal(tmp_path, shared, token):
    import json

    from napkin.model.evidence import claim_digest
    from napkin.model.library import folder_records

    path = datum_package(tmp_path, end='34.0000000000000001 h', delay=('EXACT', 'h'))
    owned = path.parent / 'evidence' / 'claims.json'
    claims = json.loads(owned.read_text())
    owned.write_text(owned.read_text().replace('"EXACT"', token))
    # Pin the claim that the reader consumes. The expected datum comparison below is independent.
    action = next(item for item in claims if item['id'] == 'C-ACTION')
    parsed = next(item for item in folder_records(path.parent)['claims'] if item['id'] == 'C-ACTION')
    action['verification']['content_sha256'] = claim_digest(parsed)
    if shared:
        vocab_path = next(tmp_path.rglob('vocabulary.json'))
        vocab = json.loads(vocab_path.read_text())
        sources = path.parent / 'evidence' / 'sources.json'
        vocab['sources'].extend(json.loads(sources.read_text()))
        sources.write_text('[]')
        vocab['claims'].append(action)
        claims.remove(action)
        vocab_path.write_text(json.dumps(vocab).replace('"EXACT"', token))
    owned.write_text(json.dumps(claims).replace('"EXACT"', token))
    assert data_warnings(path) == []
    path.write_text(path.read_text().replace('34.0000000000000001 h', '34 h'))
    (warning,) = data_warnings(path)
    assert '34.0000000000000001' in warning[0]
    from tools.evidence.integrate import dump

    assert '34.0000000000000001' in dump(parsed)


@pytest.mark.parametrize('exponent', [0.5, 0.1])
def test_fractional_exponents_agree_across_model_and_datum_unit_notations(tmp_path, exponent):
    library = evidence_library()
    library['units']['scaled'] = {'dimensions': {'time': exponent}, 'scale': 1, 'description': 'Time power.'}
    library['assumptions'] = []
    library['claims'] = [fixture_claim('C-ACCESS', data={'threshold': {'value': 1, 'unit': 'scaled^2'}})]
    text = """scenario "Time power"
    horizon 1 h
    library "../library"
site:
    input x: scaled*scaled = 1 scaled*scaled @meter
record meter: source "Measured threshold."
    claims:
        C-ACCESS
            datum: threshold
"""
    entry = write_package(tmp_path, {'model.scn': text}, library)
    assert data_warnings(entry) == []
