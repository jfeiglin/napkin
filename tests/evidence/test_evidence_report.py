"""The evidence report reads built models: what each entity and each output rests on, the cyber
first move, claim reachability and the red-team records in use."""

from napkin.model.model import build_model
from tests.build import (
    append,
    block,
    cited,
    compiled,
    edit,
    entity,
    evidence_library,
    fixture_claim,
    in_place,
    member,
    output,
    parameter,
    replace,
    sc99,
    scenario,
    stock,
    template,
)
from tests.evidence.support import resting, write_library
from tools.evidence.integrate import coverage_report, entity_view, outcome_view


def evidence_fixture():
    """The analytic transfer with cited evidence on its delivery path, and a set of two archive
    copies whose evidence, a named record used twice, no output reads."""
    text = resting(scenario(), 'service/rate', in_place('source_transfer', 'Contract fixture.', 'C-ACCESS'))
    text = resting(
        text, 'service/stop', in_place('assumption', 'The service stops.', assumption='RT-FIXTURE')
    )
    archive = template(
        'Archive',
        *(stock(name, 0, minimum=None, kind='state', records='@archived') for name in ('kept', 'seen')),
        doc='Archived records.',
        records=None,
    )
    copies = entity('archive', template='Archive', copies=2, records=None)
    text = edit(
        text,
        replace('\nassert service.end', f'\n{archive}\n\n{copies}\n\nassert service.end'),
        append(cited('archived', 'C-ACTION')),
    )
    return compiled(text, evidence_library())


def test_each_entity_counts_its_basis_uses_and_its_copies_once():
    view = entity_view(evidence_fixture())
    assert set(view) == {'service', 'archive'}
    # Each use of the named record is recorded; the two copies share one definition.
    assert view['archive'] == {'kinds': {'source_transfer': 2}, 'claims': ['C-ACTION'], 'assumptions': []}
    assert (view['service']['claims'], view['service']['assumptions']) == (['C-ACCESS'], ['RT-FIXTURE'])


def test_an_outcome_rests_on_the_parts_it_can_depend_on_and_no_others():
    # delivered reads served, which the flow at the delivery rate fills until the stop event switches
    # the service off: the rate's claim and the event's assumption, never the archive's claim.
    view = outcome_view(evidence_fixture())
    assert set(view) == {'delivered'}
    assert (view['delivered']['claims'], view['delivered']['assumptions']) == (['C-ACCESS'], ['RT-FIXTURE'])
    assert set(view['delivered']['kinds']) == {'identity', 'source_transfer', 'assumption'}


def test_an_outcome_rests_on_the_input_that_its_lag_reads():
    # `reported` is the delivered count after a delay that an input gives; only the input cites C-ACTION.
    text = edit(scenario(), member('service', parameter('report_delay', 2, 'h', 1, 4, doc='Report delay')))
    text = resting(text, 'service/report_delay', in_place('source_transfer', 'Contract fixture.', 'C-ACTION'))
    reported = output(
        'reported', 'service.served', 'people', doc='Reported', under=('lag service.report_delay',)
    )
    text = edit(text, replace('\noptions "Response":', f'\n{reported}\n\noptions "Response":'))
    view = outcome_view(compiled(text, evidence_library()))
    assert 'C-ACTION' in view['reported']['claims']
    assert 'C-ACTION' not in view['delivered']['claims']


def test_the_report_names_the_first_move_the_unreached_claims_and_the_red_team_users(tmp_path):
    library = evidence_library()
    # A claim reaches a scenario through its records, its review or an assumption it uses.
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
        {'id': 'RT-UNUSED', **{k: v for k, v in library['assumptions'][0].items() if k != 'id'}},
    ]
    limitation = block('RF: "Fixture."', in_place('source_transfer', 'Contract fixture.', 'C-FLAGGED'))
    attacked = edit(sc99(), member('notes:', block('limitations:', limitation)))
    write_library(tmp_path, 'SC99', library)
    effective = compiled(attacked, library).library
    path = tmp_path / 'scenarios/SC99/model.scn'
    path.write_text(attacked, encoding='utf-8')
    # The name of the attack is the pages': brief.toml beside the model's file.
    title = 'unauthorized control commands'
    path.with_name('brief.toml').write_text(f'attack = "{title}"\n', encoding='utf-8')
    (tmp_path / 'scenarios/fixture.scn').write_text('not a catalogue case', encoding='utf-8')
    lines = coverage_report(tmp_path).splitlines()
    top = [line.split(':')[0] for line in lines if line.startswith('  ') and line[2] != ' ']
    assert top == ['  SC99']
    # The first move: the attack's name (`attack` in brief.toml), the start's rule and its event, and
    # each claim that the records of the start event cite, once, with its status: the record at the
    # end of its line (`@access`, C-ACCESS), then the record under it (C-ACTION, ATTACK-T0831).
    initiation = build_model(path, effective).initiation
    assert lines[2] == (
        f'      claims reached 5; initiation cyber (incident): {title}; '
        f'{initiation["rule"]} -> {initiation["effect"]}; '
        'claims C-ACCESS (unverified), C-ACTION (unverified), ATTACK-T0831 (unverified)'
    )
    assert '      unused claims: C-ORPHAN' in lines
    assert '      machine red-team record: SC99:RT-FIXTURE' in lines
    assert '      machine red-team record: SC99:RT-UNUSED' in lines
