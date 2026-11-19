"""The evidence coverage report and the views that it reads (`tools/evidence/trail.py`): what each
entity and template rests on, what a value rests on, the claims that a model reaches and those of its
folder that it does not, and the red-team records of its folder.

The models are the synthetic service of `tests/evidence/support.py`; each expected count is the
records written on its lines, counted by hand.
"""

import textwrap

from napkin.model.compile import compile_text, library_units
from tests.evidence.support import SERVICE, evidence_library, fixture_claim, write_package
from tools.evidence.integrate import coverage_report
from tools.evidence.trail import entities, rests_on, summary

# A table of three archives, whose column `kept` cites its record once for every row.
ROWS = 'id,kept: people @fixture\nfirst,1\nsecond,2\nthird,3\n'


def compiled(text=SERVICE, tables=None):
    return compile_text(textwrap.dedent(text), library_units(evidence_library()), tables=tables)


def test_each_entity_counts_its_uses_and_a_template_its_members_lines_and_its_columns_once():
    # The service: five identities (n, end, waiting, served, serve), the rate's transfer and the stop's
    # assumption. The archive: its two values' transfers; north's own line and the table's column add
    # one identity each, and the table's three rows none.
    text = SERVICE.replace(
        'north: Archive\n', 'north: Archive\n    kept = 1 people  @fixture\n\nrows: Archive from "rows.csv"\n'
    )
    view = entities(compiled(text, {'rows.csv': ROWS}).declared)
    assert view == {
        'service': {
            'kinds': {'source_transfer': 1, 'assumption': 1, 'identity': 5},
            'claims': ['C-ACCESS'],
            'assumptions': ['RT-FIXTURE'],
        },
        'Archive': {
            'kinds': {'source_transfer': 2, 'identity': 2},
            'claims': ['C-ACTION'],
            'assumptions': [],
        },
    }


def test_a_value_rests_on_the_parts_that_it_can_read_and_no_others():
    # served reads the flow that fills it from the people waiting, at the rate while the service is
    # open, which the stop closes at its end: the identities of n, end, waiting, served and serve, the
    # rate's transfer, the stop's assumption and the option that halves the rate, which rests on the
    # same assumption. The archive's claim is no part of it.
    model = compiled()
    assert summary(rests_on(model, 'service.served')) == {
        'kinds': {'source_transfer': 1, 'assumption': 2, 'identity': 5},
        'claims': ['C-ACCESS'],
        'assumptions': ['RT-FIXTURE'],
    }
    halved = [use for use in rests_on(model, 'service.served') if use.option is not None]
    assert [(use.path, use.name, use.option) for use in halved] == [('service.rate', 'halved', 'Half rate')]
    # A member of a template rests on its template's records.
    assert summary(rests_on(model, 'north.kept')) == {
        'kinds': {'source_transfer': 1},
        'claims': ['C-ACTION'],
        'assumptions': [],
    }


def test_a_member_rests_on_its_own_line_and_a_row_on_its_column():
    text = SERVICE.replace('north: Archive\n', 'north: Archive\n    kept = 1 people  @fixture\n')
    model = compiled(text.replace('south: Archive\n', 'rows: Archive from "rows.csv"\n'), {'rows.csv': ROWS})
    for path, place in (('north.kept', 'north.kept'), ('rows.second.kept', 'rows.kept')):
        found = rests_on(model, path)
        assert [(use.path, use.name) for use in found] == [('Archive.kept', 'archived'), (place, 'fixture')]
    assert [(use.path, use.name) for use in rests_on(model, 'north.seen')] == [('Archive.seen', 'archived')]


def test_the_report_names_the_reached_and_unused_claims_and_the_red_team_records(tmp_path):
    library = evidence_library()
    # A claim reaches a scenario through its records, its notes or an assumption that it rests on.
    library['claims'] += [fixture_claim(c) for c in ('C-SUPPORT', 'C-FLAGGED', 'C-ORPHAN')]
    library['assumptions'][0]['supports'].append({'claim': 'C-SUPPORT', 'relation': 'bounds'})
    library['assumptions'] += [
        {
            'id': 'A-AUTHOR',
            'statement': 's',
            'rationale': 'r',
            'review': {'status': 'unreviewed'},
            'origin': 'author',
        },
        {**library['assumptions'][0], 'id': 'RT-UNUSED'},
    ]
    note = textwrap.dedent(
        """
        notes:
            limitations:
                RF: "Fixture."
                    @source_transfer "Contract fixture."
                        claims:
                            C-FLAGGED
        """
    )
    write_package(tmp_path, {'model.scn': SERVICE + note}, library)
    (tmp_path / 'scenarios/fixture.scn').write_text('not a catalogue case', encoding='utf-8')
    # The uses: the service's seven, the archive's two, the option's assumption and the note's
    # transfer. The claims reached: the three that the records name and C-SUPPORT, through RT-FIXTURE.
    assert coverage_report(tmp_path).splitlines() == [
        'Evidence coverage by scenario and record ID',
        '  SC99: source_transfer 4, assumption 2, identity 5; claims C-ACCESS, C-ACTION, C-FLAGGED; '
        'assumptions RT-FIXTURE',
        '      claims reached 4',
        '      entities',
        '        service: source_transfer 1, assumption 1, identity 5; claims C-ACCESS; assumptions RT-FIXTURE',
        '        Archive: source_transfer 2; claims C-ACTION; assumptions none',
        '      unused claims: C-ORPHAN',
        '      machine red-team record: SC99:RT-FIXTURE',
        '      machine red-team record: SC99:RT-UNUSED',
    ]
