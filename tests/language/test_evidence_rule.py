"""The owner's evidence rule (item 16 of the plan's changes after G0, `napkin/model/support.py`): a
warning, code `no_record`, for each part that rests on no record, of the kinds for which the
compiler before the rewrite refused a model, at the part's line. A value that an option or a
`change` sets keeps its error (R-A5-05). Then what the evidence tools need of the front end: the
records of a value for a member and a run (`DeclaredModel.evidence`), the document of a whole
package (`library.model_document`), and a record's error at its file and line. The lines below are
counted by hand in the texts."""

import json
import textwrap
from pathlib import Path

import pytest

from napkin.model.compile import compile_text, load_scenario
from napkin.model.ir import ModelError
from napkin.model.language.problems import LanguageError
from napkin.model.library import model_document
from napkin.model.support import DATUM
from tests.evidence.support import datum_package
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
