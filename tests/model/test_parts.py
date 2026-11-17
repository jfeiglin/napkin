"""The parts of the language that the scenarios use besides those of test_build.py: numbers with
units, bool inputs, bool states, sum checks, output lags, outputs that add people, hidden
entities, the brief settings, milestones, several entities of one template, list links, sum() and
move.

They use MODELTEST (tests/model/modeltest.py): a service that an attacker switches off at t = 0 is
repaired `repair_time` later, and then serves waiting users at `service_rate` times the number still
waiting. Every expectation comes from inputs read from the model or given as values, and from closed
forms.
"""

from __future__ import annotations

import math
import re

import pytest

from napkin.core.expr import text as written
from napkin.draw import style as styles
from napkin.draw.style import StyleError
from napkin.engine import edits_for, evaluate_study, sample_result
from napkin.engine.report import evaluate_outputs
from napkin.model import ModelError
from napkin.model.types import literal_quantities
from tests.build import block, member, replace, status
from tests.model.modeltest import BRIEF, FIXTURE, LIB, build, located, run, times
from tests.owned import block_at
from tools.publish.pages import pages


def things(*blocks):
    """An edit step: things and templates after those of the fixture, before its options."""
    return replace('options "Response":', '\n\n'.join(blocks) + '\n\noptions "Response":')


def top(*blocks):
    """An edit step: checks and outputs at the top level, before the options."""
    return replace('options "Response":', '\n\n'.join(blocks) + '\n\noptions "Response":')


def inputs(model, name, values=None):
    """The input values of a run: its own, with `values` over them."""
    return {**model.run_values(name), **(values or {})}


def served(model, name, t, values=None):
    """Users served by time t, from the closed form of the fixture: none while the service is down,
    then users * (1 - exp(-k (t - repair)))."""
    v = inputs(model, name, values)
    users, k, repair = v['service.users'], v['service.service_rate'], v['service.repair_time']
    if t <= repair:
        return 0.0
    return users * (1 - math.exp(-k * (t - repair)))


def samples(model, name, grid, values=None):
    """[(t, {output of the file: value})] of a run at the times of `grid`."""
    rs, trajectory = run(model, name, values)
    rows = evaluate_outputs({'resolved': rs, 'trajectory': trajectory}, LIB, grid)
    outputs = {oid: key for key, oid in model.outputs.items()}
    return [(row['t'], {outputs[o]: v for o, v in row['values'].items() if o in outputs}) for row in rows]


def rejected_codes(model, edits):
    """The codes of the errors that reject a study of every run under the edits."""
    study = evaluate_study(model, edits_for(model, edits))
    return {d.get('code') for d in study.diagnostics if d.get('severity', 'error') == 'error'}


# ---- numbers with units -----------------------------------------------------------------------------


@pytest.mark.parametrize(
    ('text', 'read'),
    [
        ('0 L/h', "q(0, 'L/h')"),
        ('max(0 people/h, x)', "max(q(0, 'people/h'), x)"),
        ('0.01 person-hours', "q(0.01, 'person-hours')"),
        ('3 USD2025/terminal-hour', "q(3, 'USD2025/terminal-hour')"),
        # The longest unit that the names spell: the rest divides or subtracts as written.
        ('48 h/2', "q(48, 'h')/2"),
        ('48 h/self.x', "q(48, 'h')/self.x"),
        ('1 h-self.y', "q(1, 'h')-self.y"),
        ('2 people/hx', "q(2, 'people')/hx"),
    ],
)
def test_a_number_with_a_compound_unit_is_that_quantity(text, read):
    units = {'h', 'L/h', 'people', 'people/h', 'person-hours', 'USD2025/terminal-hour'}
    assert literal_quantities(text, units) == read


LIMIT = block('input limit = 5 L/h in 0 L/h to 10 L/h  @ident', '"Most fluid the service draws"')


@pytest.mark.parametrize('zero', ['0 L/h'])
def test_a_compound_literal_reads_as_its_q_form(tmp_path, zero):
    """A check of an input in L/h against zero: the literal is one quantity, q(0, 'L/h')."""
    model = build(
        tmp_path,
        member('service', LIMIT),
        top(block(f'assert service.limit > {zero}  @ident', '"The service draws some fluid."')),
    )
    for name in model.runs:
        (check,) = (
            c
            for c in model.structure_of(name).input_checks.values()
            if c.message == 'The service draws some fluid.'
        )
        assert written(check.expr) == "service.limit > q(0, 'L/h')"
    assert not rejected_codes(model, {'set': {'service.limit': 5}})
    assert rejected_codes(model, {'set': {'service.limit': 0}})


def test_a_number_in_another_unit_of_its_dimension_converts(tmp_path):
    """A cubic metre is 1000 L, so numbers written in m3 build the model that the same amounts in
    litres build: an input's value, its range and an option's value, and a var's size, each in the
    unit of its value."""

    def written(value, low, option, size):
        return (
            member(
                'service',
                block(f'input reserve: L = {value} in {low} to 4000 L  @ident', '"Water in reserve"'),
                block(f'var water: L = reserve size {size}  @ident', '"Water held"'),
            ),
            member('options:/Response/Fast repair', f'service.reserve = {option}  @ident'),
        )

    cubic = build(tmp_path, *written('2.5 m3', '0.5 m3', '1.5 m3', '1 m3'))
    litres = build(tmp_path, *written('2500 L', '500 L', '1500 L', '1000 L'))
    info = cubic.inputs['service.reserve']
    assert (info['value'], *info['range'], info['options']['Fast repair']['value']) == (2500, 500, 4000, 1500)
    assert cubic.structure_of('slow').quantities['service.water'].size == 1000
    assert cubic.structures == litres.structures
    assert all(cubic.run_values(name) == litres.run_values(name) for name in cubic.runs)


# ---- bool inputs -------------------------------------------------------------------------------


def with_auto_repair(value='true'):
    """A yes/no input that gates the repair and the rate of the serving. A value that does not show
    its type has the type bool."""
    typed = '' if value in ('true', 'false') else ': bool'
    return (
        member(
            'service', block(f'input auto_repair{typed} = {value}  @ident', '"Repairs start by themselves"')
        ),
        replace(
            'elapsed(status) >= repair_time:  @ident',
            'elapsed(status) >= repair_time and auto_repair:  @ident',
        ),
        replace(
            'at service_rate * waiting while', 'at (1 if auto_repair else 0) * service_rate * waiting while'
        ),
    )


def test_a_bool_input_gates_a_trigger_and_a_rate(tmp_path):
    model = build(tmp_path, *with_auto_repair())
    grid = [0.0, 20.0, 45.0, 120.0]
    for t, values in samples(model, 'slow', grid):
        assert values['service.served'] == pytest.approx(served(model, 'slow', t), rel=1e-6, abs=1e-6)
    off = {'service.auto_repair': False}
    assert all(values['service.served'] == 0 for _, values in samples(model, 'slow', grid, off))
    _, trajectory = run(model, 'slow', off)
    assert not times(trajectory, model.events['service.repaired.done'])


def test_a_bool_input_reads_as_the_engine_s_0_1_number(tmp_path):
    """As a condition a bool input reads `x == 1`, and `1 if x else 0` is the number itself."""
    s = build(tmp_path, *with_auto_repair()).structure_of('slow')
    assert 'service.auto_repair == 1' in written(s.rules['service.repaired'].trigger.when)
    assert written(s.flows['service.serve'].rate).startswith('service.auto_repair * ')


def test_a_response_option_keeps_the_bool_default_that_it_does_not_set(tmp_path):
    """A bool input runs at its default in the runs of a Response option that leaves it alone, and
    at the option's value in the runs of an option that sets it."""
    model = build(
        tmp_path,
        *with_auto_repair(),
        member('options:/Response/Fast repair', 'service.auto_repair = false  @ident'),
    )
    assert model.run_values('slow')['service.auto_repair'] is True
    assert model.run_values('fast')['service.auto_repair'] is False
    grid = [0.0, 45.0, 120.0]
    for t, values in samples(model, 'slow', grid):
        assert values['service.served'] == pytest.approx(served(model, 'slow', t), rel=1e-6, abs=1e-6)
    assert all(values['service.served'] == 0 for _, values in samples(model, 'fast', grid))


@pytest.mark.parametrize('value', [1, 'yes', 'no'])
def test_a_bool_input_takes_true_or_false_only(tmp_path, value):
    with pytest.raises(ModelError, match='true or false'):
        build(tmp_path, *with_auto_repair(value=value))


# ---- a state that is true or false ---------------------------------------------------------------


def with_repair_flag(flag=True, *lines):
    """A var that the repair sets: yes/no (`flag`), or a number from 0 to 1 with `lines` under it. The
    var is the last step, so that a line under it that the file rejects is in the file as written."""
    if flag:
        state = block('var repair_done = false  @ident', '"Repair finished"')
        change = 'repair_done = true'
    else:
        state = block('var repair_done: fraction = 0 in 0 to 1 size 1  @ident', '"Repair finished"', *lines)
        change = 'repair_done = 1'
    return member('service/repaired', change), member('service', state)


def test_a_bool_state_is_the_engine_s_binary_quantity(tmp_path):
    """A bool state is the engine's 0/1 number state, which the pages read Yes or No; a 0/1 number
    state is a number."""
    flag = build(tmp_path, *with_repair_flag()).structure_of('slow').quantities['service.repair_done']
    assert (flag.kind, flag.minimum, flag.maximum, flag.binary) == ('variable', 0, 1, True)
    plain = build(tmp_path, *with_repair_flag(False)).structure_of('slow').quantities
    assert plain['service.repair_done'].binary is None


def test_a_number_state_is_not_marked_binary(tmp_path):
    """A yes/no state is written `var x = false`; a number state has no line that marks it binary:
    the file is rejected at that line."""
    diagnostics = located(tmp_path, *with_repair_flag(False, 'binary: true'))
    rows = (tmp_path / 'MODELTEST.scn').read_text(encoding='utf-8').split('\n')
    (line,) = (number for number, row in enumerate(rows, 1) if row.strip() == 'binary: true')
    assert [d.get('line') for d in diagnostics] == [line]
    assert 'does not belong here' in diagnostics[0]['message']


# ---- sum checks ------------------------------------------------------------------------------------


def test_a_sum_check_can_list_a_tally_that_counts_what_left_a_stock(tmp_path):
    # Served users as a running total: only the flow `serve` fills `served`, so it is a tally, which
    # only rises and counts what leaves the waiting stock.
    model = build(tmp_path)
    s = model.structure_of('slow')
    assert s.quantities['service.served'].kind == 'cumulative'
    (partition,) = s.partitions.values()
    assert set(partition.parts) == {'service.waiting', 'service.served'}
    users = model.run_values('slow')['service.users']
    _, trajectory = run(model, 'slow')
    for t in (0.0, 45.0, 120.0):
        env = trajectory.env_at(t)
        assert env['service.waiting'] + env['service.served'] == pytest.approx(users)
        assert env['service.served'] == pytest.approx(served(model, 'slow', t), rel=1e-6, abs=1e-6)


def test_a_sum_check_lists_number_vars_only(tmp_path):
    # A value that never changes is no number var: a sum adds number vars (docs/language.md, 2.8).
    with pytest.raises(ModelError, match='level is not a number var'):
        build(
            tmp_path,
            member('service', 'let level = 0 people  @ident'),
            replace('assert waiting + served is users', 'assert waiting + served + level is users'),
        )


# ---- output lags ----------------------------------------------------------------------------------


def with_lag(lag):
    # A lag delays a count as it is reported, so the output counts cumulatively.
    return replace('    output served\n        level', f'    output served\n        lag {lag}')


def test_a_fixed_lag_reports_the_value_of_its_delay_earlier(tmp_path):
    model = build(tmp_path, with_lag('5 h'))
    for t, values in samples(model, 'slow', [10.0, 32.0, 40.0, 90.0]):
        assert values['service.served'] == pytest.approx(served(model, 'slow', t - 5), rel=1e-6, abs=1e-6)


def test_a_mixture_lag_reports_the_shares_of_each_delay(tmp_path):
    model = build(tmp_path, with_lag('mixture([0.25, 0], [0.75, 12 h])'))
    for t, values in samples(model, 'slow', [35.0, 60.0, 150.0]):
        expected = 0.25 * served(model, 'slow', t) + 0.75 * served(model, 'slow', t - 12)
        assert values['service.served'] == pytest.approx(expected, rel=1e-6, abs=1e-6)


def test_a_uniform_lag_reports_the_mean_over_its_window(tmp_path):
    a, b = 4.0, 10.0
    model = build(tmp_path, with_lag(f'uniform({a!r} h, {b!r} h)'))
    for t, values in samples(model, 'slow', [50.0, 100.0]):
        # The mean of the closed form over delays in [a, b], by Simpson's rule on a fine grid.
        n = 2000
        h = (b - a) / n
        total = sum(
            (1 if i in (0, n) else 4 if i % 2 else 2) * served(model, 'slow', t - (a + i * h))
            for i in range(n + 1)
        )
        assert values['service.served'] == pytest.approx(total * h / 3 / (b - a), rel=1e-6)


# ---- outputs that add people ---------------------------------------------------------------------


def with_total(distinct):
    return (
        member('service', block('output waiting', 'level')),
        top(
            block(
                'output everyone: people = service.waiting + service.served + service.waiting  @ident',
                '"Users waiting or served"',
                'level',
                'distinct  @ident' if distinct else None,
            )
        ),
    )


def test_an_output_that_adds_people_twice_needs_a_distinct_basis(tmp_path):
    with pytest.raises(ModelError, match='different people'):
        build(tmp_path, *with_total(distinct=False))
    model = build(tmp_path, *with_total(distinct=True))
    assert model.structure_of('slow').outcomes[model.outputs['everyone']].additive['explanation']


# ---- pages: hidden entities and the brief settings ---------------------------------------------------


def health_entities(model):
    study = evaluate_study(model, edits_for(model), runs=['slow'])
    return set(sample_result(study, [10.0])['runs']['slow']['health'][0]['entities'])


def test_a_hidden_thing_leaves_only_the_map(tmp_path):
    """The stylesheet hides an entity: the map does not draw it. The pages read only the brief
    settings, so they are the same with the entity hidden and still show its status; the engine's
    report never reads either file."""
    for folder in ('shown', 'hidden'):
        (tmp_path / folder).mkdir()
    shown = build(tmp_path / 'shown')
    hidden = build(tmp_path / 'hidden', style='[layout]\nhide = ["service"]\n')
    assert 'service' in styles.drawn(styles.of(shown), shown)
    assert 'service' not in styles.drawn(styles.of(hidden), hidden)
    assert pages(hidden) == pages(shown)
    assert 'service' in pages(hidden)['statuses']
    assert 'service' in health_entities(shown)
    assert health_entities(hidden) == health_entities(shown)


def test_the_report_gives_no_status_text_of_its_own(tmp_path):
    """An entity that shows no status is inactive and has no text; an entity that shows one has the
    value and the text of one of its own cases. The engine writes no text."""
    model = build(tmp_path)
    s = model.structure_of('slow')
    study = evaluate_study(model, edits_for(model), runs=['slow'])
    rows = sample_result(study, [0.0, 100.0])['runs']['slow']['health']
    kinds = set()
    for row in rows:
        for e, item in row['entities'].items():
            binding = s.entities[e].health
            kinds.add(binding is None)
            if binding is None:
                assert (item['health'], item['label']) == ('inactive', None), e
            else:
                label = s.labels[binding]
                cases = [*label.cases, label.default]
                assert (item['health'], item['label']) in {(c.value, c.text) for c in cases}, e
    # The fixture has entities of both kinds.
    assert kinds == {True, False}


def test_the_brief_settings_name_no_main_controls(tmp_path):
    """The brief settings have no key for the main controls: the pages refuse a brief that writes
    one, as they refuse any key that they do not read."""
    model = build(tmp_path, brief=BRIEF + 'controls = ["responders.removal_time"]\n')
    with pytest.raises(StyleError, match='controls') as caught:
        pages(model)
    assert [d['key'] for d in caught.value.diagnostics] == ['controls']


# ---- milestones ---------------------------------------------------------------------------------------


def with_milestone():
    """A milestone of the service, and one of the responders that reads the service's state."""
    return (
        member(
            'service',
            block(
                'event half_way once when since(fails) >= 0.5 * repair_time:  @ident',
                '"The repair is half done."',
            ),
        ),
        member(
            'responders',
            block('event back once when service.status is "back":  @ident', '"The service is back."'),
        ),
    )


def test_a_milestone_fires_once_at_its_time_and_changes_nothing(tmp_path):
    plain = build(tmp_path)
    model = build(tmp_path, *with_milestone())
    _, trajectory = run(model, 'slow')
    repair = model.run_values('slow')['service.repair_time']
    assert times(trajectory, model.events['service.half_way.done']) == pytest.approx([repair / 2])
    assert times(trajectory, model.events['responders.back.done']) == pytest.approx([repair])
    grid = [5.0, 40.0, 150.0]
    assert samples(model, 'slow', grid) == samples(plain, 'slow', grid)


# ---- several entities of one template, list links, sum() and move -----------------------------------
# Two queues of users, each an instance of one template with its own size. A dispatcher lists both: it
# reports their total with sum(), and when the service is repaired it moves a share of each queue's
# waiting users into its handled stock with one line that names the event of the list.


def with_queues(queues='[small, large]'):
    """The queues and the dispatcher, whose list names `queues`."""
    return (
        things(
            block(
                'Queue:  @ident',
                '"A queue of users."',
                'role community',
                block('let size = 300 people  @ident', '"Users in the queue"'),
                block('var pending: people = size  @ident', '"Users waiting"'),
                block('var handled: people = 0  @ident', '"Users dealt with"'),
                block(
                    'event serve_share:  @ident', 'move dispatcher.share * pending from pending to handled'
                ),
            ),
            'small: Queue',
            block('large: Queue', 'size = 700 people  @ident'),
            block(
                'dispatcher:  @ident',
                '"Sends users from the queues to the service."',
                'role operator',
                f'let queues = {queues}',
                block('let share: fraction = 0.4  @ident', '"Share of each queue served at the repair"'),
                'var stage: "waiting" | "sent" = "waiting"',
                block('let total: people = sum(queues.pending)  @ident', '"Users in the queues"'),
                block(
                    'output left: people = total  @ident',
                    '"Users still waiting in the queues"',
                    'level',
                ),
                block(
                    'event dispatch when stage is "waiting" and service.status is "back":  @ident',
                    '"The dispatcher sends a share of each queue."',
                    'stage = "sent"',
                    'queues.serve_share',
                ),
            ),
        ),
    )


def test_set_gives_one_entity_its_own_value(tmp_path):
    values = build(tmp_path, *with_queues()).run_values('slow')
    assert values['small.size'] != values['large.size']


# The status of a queue: (status, condition, text) of each of its lines.
QUEUE_STATUS = (('degraded', 'pending > 0 people', 'Users wait'), ('ok', None, 'No one waits'))
QUEUE_SCOPE = 'The users of the queue.'


def with_queue_outputs(waiting=QUEUE_STATUS[0][2]):
    """Each queue reports the users it has dealt with, and shows whether users still wait, in the
    text `waiting`."""
    return (
        *with_queues(),
        member(
            'Queue',
            block(
                'output dealt_with: people = handled  @ident',
                '"Users dealt with"',
                f'scope "{QUEUE_SCOPE}"',
                'level',
            ),
            status((*QUEUE_STATUS[0][:2], waiting), *QUEUE_STATUS[1:]),
        ),
    )


def test_set_changes_the_size_of_a_number_and_the_scope_of_an_output(tmp_path):
    """An instance changes the lines of its template's members: the size of a stock, and the scope of
    an output."""
    scope = 'The users of the large queue only.'
    model = build(
        tmp_path,
        *with_queue_outputs(),
        member(
            'large',
            'var pending: people = size size 1000 people  @ident',
            block('output dealt_with', f'scope "{scope}"'),
        ),
    )
    s = model.structure_of('slow')
    # The large queue's own size; the small queue writes none, so the engine sizes it.
    assert s.quantities['large.pending'].size == 1000 and s.quantities['small.pending'].size is None
    outcomes = s.outcomes
    assert outcomes[model.outputs['large.dealt_with']].scope == scope
    assert outcomes[model.outputs['small.dealt_with']].scope != scope


def test_a_change_of_a_value_output_keeps_the_lines_that_it_does_not_give(tmp_path):
    """The handled users of a queue are an output that reports its level: the large queue changes
    its scope only, and keeps the template's measure."""
    scope = 'The users of the large queue only.'
    reported = replace(
        '    var handled: people = 0  @ident\n        "Users dealt with"\n',
        '    var handled: people = 0  @ident\n        "Users dealt with"\n    output handled\n'
        f'        level\n        scope "{QUEUE_SCOPE}"\n',
    )
    model = build(
        tmp_path,
        *with_queues(),
        reported,
        member('large', block('output handled', f'scope "{scope}"')),
    )
    outcomes = model.structure_of('slow').outcomes
    large, small = (outcomes[model.outputs[f'{queue}.handled']] for queue in ('large', 'small'))
    assert (large.scope, small.scope) == (scope, QUEUE_SCOPE)
    assert large.kind == small.kind != 'cumulative'


@pytest.mark.parametrize(
    ('change', 'match'),
    [
        # An instance changes the lines of an output, and the template gives its expression.
        ('dealt_with = 2 * handled  @ident', 'not its expression'),
        # The text of the change is the label of the output.
        (block('output dealt_with', '"Users of the large queue"'), 'the label of the output'),
        ('output dealt_with  @ident', 'records of a change go on its line'),
        (block('output dealt_with', 'levle'), 'an output has no line levle'),
    ],
    ids=['expression', 'text', 'records', 'measure'],
)
def test_a_change_of_an_output_gives_its_lines(tmp_path, change, match):
    with pytest.raises(ModelError, match=match):
        build(tmp_path, *with_queue_outputs(), member('large', change))


def statuses(model, name, t):
    """{entity: status label} of a run at time t."""
    study = evaluate_study(model, edits_for(model), runs=[name])
    health = sample_result(study, [t])['runs'][name]['health'][0]['entities']
    return {e: item['label'] for e, item in health.items()}


def test_an_entity_can_show_a_status_of_its_own(tmp_path):
    own = (('failed', 'pending > 100 people', 'A long queue'), ('ok', None, 'A short queue'))
    # The records of the large queue's own status: the template's, and its own.
    model = build(tmp_path, *with_queue_outputs(), member('large', status(*own, records='@ident @attack')))
    labels = model.structure_of('slow').labels
    large, small = labels['large.health'], labels['small.health']
    assert [c.text for c in large.cases] + [large.default.text] == [text for *_, text in own]
    assert [c.text for c in small.cases] + [small.default.text] == [text for *_, text in QUEUE_STATUS]
    # The status reads each entity's own cases in the run: before the repair every queue still waits.
    repair = model.run_values('slow')['service.repair_time']
    found = statuses(model, 'slow', repair / 2)
    assert (found['small'], found['large']) == (QUEUE_STATUS[0][2], own[0][2])
    # The status of the large queue rests on the records of its own status line.
    assert [record['name'] for record in large.basis] == ['ident', 'attack']


# The customers of each queue, which a text value names.
WHO = {'small': 'Small customers', 'large': 'Large customers'}


def with_named_status(text):
    """Each queue names its customers in a text value, which the large queue changes, and its status
    names them."""
    return (
        *with_queue_outputs(waiting=text),
        member('Queue', f'input who = "{WHO["small"]}"'),
        member('large', f'who = "{WHO["large"]}"'),
    )


def test_a_status_text_can_name_a_text_field_of_its_entity(tmp_path):
    model = build(tmp_path, *with_named_status('{who} wait'))
    repair = model.run_values('slow')['service.repair_time']
    found = statuses(model, 'slow', repair / 2)
    for queue in ('small', 'large'):
        assert found[queue] == f'{WHO[queue]} wait'


@pytest.mark.parametrize(
    ('text', 'match'),
    [
        ('{size} wait', 'name a text value'),
        ('{who.x} wait', 'who is not an entity or a link'),
    ],
    ids=['edit-name a text field', 'edit-braces name one field'],
)
def test_the_braces_of_a_status_text_are_checked(tmp_path, text, match):
    with pytest.raises(ModelError, match=match):
        build(tmp_path, *with_named_status(text))


def test_a_text_fills_braces_anywhere_in_a_sentence_as_written(tmp_path):
    # A text value keeps its letters wherever its braces are: a capital letter of a name is its own.
    model = build(
        tmp_path,
        *with_queue_outputs(waiting='Users of {who} wait'),
        member('Queue', f'input who = "{WHO["small"]}"'),
        member('large', f'who = "{WHO["large"]}"'),
    )
    repair = model.run_values('slow')['service.repair_time']
    found = statuses(model, 'slow', repair / 2)
    for queue in ('small', 'large'):
        assert found[queue] == f'Users of {WHO[queue]} wait'


def test_a_text_has_no_type_of_its_own(tmp_path):
    # `name` is not a type of the language: a text input is its words in quotes.
    with pytest.raises(ModelError, match='name'):
        build(tmp_path, *with_queue_outputs(), member('Queue', f'input who: name = "{WHO["small"]}"'))


def test_a_status_text_names_no_field_that_changes_with_the_options(tmp_path):
    holds = member('attacker', status(('ok', None, '{actor} holds access')))
    with pytest.raises(ModelError, match='changes with the options'):
        build(tmp_path, holds, member('options:/Access/Keeps access', 'attacker.actor = "The human team"'))
    # A text that no option changes reads its value.
    model = build(tmp_path, holds)
    actor = block_at(FIXTURE, 'attacker/actor').split('"')[1]
    for structure in model.whole.values():
        assert structure.labels['attacker.health'].default.text == f'{actor} holds access'


def test_sum_adds_a_field_over_a_list_link_and_a_list_call_moves_each_member(tmp_path):
    model = build(tmp_path, *with_queues())
    v = model.run_values('slow')
    small, large, share, repair = (
        v['small.size'],
        v['large.size'],
        v['dispatcher.share'],
        v['service.repair_time'],
    )
    left = {t: values['dispatcher.left'] for t, values in samples(model, 'slow', [repair / 2, repair + 1])}
    assert left[repair / 2] == pytest.approx(small + large)
    assert left[repair + 1] == pytest.approx((1 - share) * (small + large))
    # One event moves both queues.
    _, trajectory = run(model, 'slow')
    assert times(trajectory, model.events['dispatcher.dispatch.done']) == pytest.approx([repair])


def test_a_move_out_of_an_empty_share_conserves_people(tmp_path):
    model = build(tmp_path, *with_queues())
    v = model.run_values('slow')
    _, trajectory = run(model, 'slow')
    env = trajectory.env_at(v['service.repair_time'] + 1)
    for queue in ('small', 'large'):
        assert env[f'{queue}.pending'] + env[f'{queue}.handled'] == pytest.approx(v[f'{queue}.size'])


def test_a_list_link_names_entities_of_its_class(tmp_path):
    # The service is no queue: the dispatcher's total cannot add its waiting users.
    with pytest.raises(ModelError, match=re.escape('service.pending is not a value')):
        build(tmp_path, *with_queues('[small, service]'))


# ---- a calculated write into another entity --------------------------------------------------------


def test_a_method_writes_a_calculated_value_into_another_entity(tmp_path):
    model = build(
        tmp_path,
        *with_queues(),
        # The dispatcher also credits the service with a tenth of the users in the queues.
        member('service', block('var credited: people = 0  @ident', '"Users credited to the service"')),
        member('dispatcher/dispatch', 'service.credited += 0.1 * total'),
    )
    v = model.run_values('slow')
    _, trajectory = run(model, 'slow')
    env = trajectory.env_at(v['service.repair_time'])
    # The value is worked out from the values before the step: a tenth of both full queues.
    assert env['service.credited'] == pytest.approx(0.1 * (v['small.size'] + v['large.size']))
