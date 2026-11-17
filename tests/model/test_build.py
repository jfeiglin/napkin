"""Model files built for the engine (model/lower/ and model.py), with closed forms.

Most tests build MODELTEST (tests/model/modeltest.py), a small synthetic model. An attacker switches a
service off at t = 0. The service is repaired `repair_time` after it goes down, and settles
`settle_time` after that. While the service is up, waiting users are served at `service_rate` times
the number still waiting. When the repair is done, the attacker starts to jam the switch: an event
that waits, and changes the switch after `reaction_time` if the attacker keeps its access and the
service has not settled. Responders remove the attacker `removal_time` after the first move. The
other tests build the analytic transfer and the small systems of tests/build.py.

Every expectation comes from these inputs, read from the model or given as values, and from closed
forms or from an exhaustive search of small synthetic structures. None comes from a run.
"""

from __future__ import annotations

import copy
import json
import math
import random
import re

import pytest
from jsonschema import Draft202012Validator

from napkin.core.expr import read
from napkin.core.expr import text as written
from napkin.engine import edits_for, evaluate_study, sample_result
from napkin.engine.report import evaluate_outputs, evidence_trail
from napkin.engine.runtime import SimulationError
from napkin.expressions import UnitSystem
from napkin.model import ModelError
from napkin.model.compile import check_parameters
from napkin.model.evidence import claim_digest
from napkin.model.ir import basis_records
from napkin.model.language import front
from napkin.model.language.nodes import Event
from napkin.model.lower import Acting
from napkin.model.model import build_model
from napkin.model.structure import Resolved, thawed
from napkin.schema import FOLDER as SCHEMAS
from tests import build as fixtures
from tests.model.modeltest import FIXTURE, LIB, assert_located, build, located, run, times, value
from tools.publish import brief as styles

# ---- the numbers -----------------------------------------------------------------------------


def test_a_flow_with_while_follows_its_closed_form(tmp_path):
    model = build(tmp_path)
    rs, trajectory = run(model, 'slow')
    users = value(model, 'service.users', 'slow')
    k = value(model, 'service.service_rate', 'slow')
    repair = value(model, 'service.repair_time', 'slow')
    assert times(trajectory, model.events['service.repaired.done']) == pytest.approx([repair], abs=1e-9)
    grid = [0.0, repair / 2, repair, repair + 5, repair + 40, 200.0]
    rows = evaluate_outputs({'resolved': rs, 'trajectory': trajectory}, LIB, grid)
    served = model.outputs['service.served']
    for row in rows:
        expected = 0.0 if row['t'] <= repair else users * (1 - math.exp(-k * (row['t'] - repair)))
        assert row['values'][served] == pytest.approx(expected, rel=1e-6, abs=1e-6)


def test_a_response_option_sets_its_input_in_its_runs(tmp_path):
    model = build(tmp_path)
    repaired = model.events['service.repaired.done']
    for name in ('slow', 'fast'):
        _, trajectory = run(model, name)
        assert times(trajectory, repaired) == pytest.approx([value(model, 'service.repair_time', name)])
    assert value(model, 'service.repair_time', 'fast') != value(model, 'service.repair_time', 'slow')
    # The profile is the only value that the two runs' inputs differ in.
    slow, fast = model.run_values('slow'), model.run_values('fast')
    assert {k for k in slow if slow[k] != fast[k]} == {'service.repair_time'}


def test_elapsed_counts_from_entering_the_tested_state(tmp_path):
    model = build(tmp_path)
    _, trajectory = run(model, 'slow', {'service.settle_time': 7.5})
    (repaired,) = times(trajectory, model.events['service.repaired.done'])
    assert times(trajectory, model.events['service.settles.done']) == pytest.approx([repaired + 7.5])


def responders_watch(*events):
    """An edit step: the responders keep a report, "held", then "quiet" once released, then
    "reported", and a number of notes. `events` are their events."""
    return fixtures.member(
        'responders',
        fixtures.named('report', 'held', 'quiet', 'reported'),
        'var notes: fraction = 0  @ident',
        *events,
    )


def responders_event(name, when, *changes, transition=None):
    """An event of the responders that happens as soon as `when` holds: along its `transition`, or
    once, with the lines of its change."""
    return fixtures.event(
        name,
        when,
        *changes,
        once=transition is None,
        transition=transition,
        doc=f'Responders {name}.',
        records='@ident',
        do_records='@ident' if changes else None,
    )


def test_elapsed_reads_a_named_state_of_another_entity(tmp_path):
    """The service goes down at the first move, t = 0; the responders report 4 h after the service's
    state took its present value."""
    model = build(
        tmp_path,
        responders_watch(
            responders_event('releases', 'true', transition='report "held" -> "quiet"'),
            responders_event(
                'reports', 'elapsed(service.status) >= 4 h', transition='report "quiet" -> "reported"'
            ),
        ),
    )
    _, trajectory = run(model, 'slow')
    assert times(trajectory, model.events['service.fails.done']) == pytest.approx([0.0])
    assert times(trajectory, model.events['responders.reports.done']) == pytest.approx([4.0])


def test_a_step_that_sets_a_state_to_its_own_value_does_not_restart_elapsed(tmp_path):
    """At 10 h the responders set the service's state to "down", the value that it has had since
    t = 0: the repair still comes `repair_time` after the service went down."""
    model = build(
        tmp_path,
        responders_watch(
            responders_event(
                'confirms',
                'service.status is "down" and since(attacker.start) >= 10 h',
                'service.status = "down"',
            )
        ),
    )
    _, trajectory = run(model, 'slow')
    repair = value(model, 'service.repair_time', 'slow')
    assert repair > 10
    assert times(trajectory, model.events['responders.confirms.done']) == pytest.approx([10.0])
    assert times(trajectory, model.events['service.repaired.done']) == pytest.approx([repair])


def test_an_order_on_a_trigger_timed_from_another_state_holds(tmp_path):
    """At 5 h the responders release their report and take a note; their report, timed 2 h from the
    service's state (down since t = 0), is due as soon as it is released. The order of the lines puts
    the report before the note, so the note must wait for it at the same moment, though the report's
    own state is not yet the one that its condition tests when the moment begins."""
    model = build(
        tmp_path,
        responders_watch(
            responders_event(
                'releases', 'since(attacker.start) >= 5 h', transition='report "held" -> "quiet"'
            ),
            responders_event(
                'reports', 'elapsed(service.status) >= 2 h', transition='report "quiet" -> "reported"'
            ),
            responders_event('takes_note', 'since(attacker.start) >= 5 h', 'notes = 1'),
        ),
    )
    _, trajectory = run(model, 'slow')
    events = [model.events[f'responders.{name}.done'] for name in ('releases', 'reports', 'takes_note')]
    steps = [
        (entry['t'], entry['step'], entry['event']) for entry in trajectory.trace if entry['event'] in events
    ]
    assert [(t, event) for t, _, event in sorted(steps)] == [(5.0, event) for event in events]


def test_elapsed_reads_only_a_named_state(tmp_path):
    with pytest.raises(ModelError, match=r'elapsed\(\) measures a named state'):
        build(
            tmp_path,
            fixtures.replace('elapsed(status) >= settle_time', 'elapsed(repair_time) >= settle_time'),
        )


def test_a_bool_input_reads_true_and_false(tmp_path):
    backup = (
        fixtures.member('service', 'input backup = false  @ident\n    "Backup servers"'),
        fixtures.replace(
            'at service_rate * waiting while', 'at service_rate * waiting * (1 + (1 if backup else 0)) while'
        ),
    )
    model = build(tmp_path, *backup)
    assert (
        model.inputs['service.backup']['type'] == 'bool' and model.inputs['service.backup']['value'] is False
    )
    users = value(model, 'service.users', 'slow')
    k = value(model, 'service.service_rate', 'slow')
    repair = value(model, 'service.repair_time', 'slow')
    served = model.outputs['service.served']
    t = repair + 10
    for given, factor in ((False, 1), (True, 2), (0, 1), (1, 2)):
        rs, trajectory = run(model, 'slow', {'service.backup': given})
        (row,) = evaluate_outputs({'resolved': rs, 'trajectory': trajectory}, LIB, [t])
        expected = users * (1 - math.exp(-factor * k * (t - repair)))
        assert row['values'][served] == pytest.approx(expected, rel=1e-6)
    with pytest.raises(ModelError) as caught:
        model.resolve('slow', {'service.backup': 0.5})
    assert {d['code'] for d in caught.value.diagnostics} == {'binary_control'}


# ---- the three outcomes of an event that waits ---------------------------------------------------


@pytest.mark.parametrize(
    ('wait', 'removal_after_repair', 'settle', 'ending'),
    [
        # The service is repaired at R. The jam triggers at R and fires W later, at R + W, when it takes
        # its outcome; responders remove the attacker at R + X; the service settles at R + N. Done when
        # the attacker still keeps its access and the service has not settled at R + W.
        (10, 100, 20, 'done'),
        # Removed while it waits: stopped when it fires.
        (40, 20, 30, 'stopped'),
        # The service settled first: skipped when it fires.
        (40, 100, 20, 'skipped'),
        # Removal at the moment the wait ends: the responders' line comes before the attacker's, so the
        # removal goes first and the jam is stopped.
        (20, 20, 30, 'stopped'),
    ],
)
def test_a_waiting_method_ends_in_one_of_three_ways(tmp_path, wait, removal_after_repair, settle, ending):
    model = build(tmp_path)
    repair = value(model, 'service.repair_time', 'slow_kept')
    removal = repair + removal_after_repair
    values = {
        'responders.removal_time': removal,
        'service.settle_time': settle,
        'attacker.reaction_time': wait,
    }
    _, trajectory = run(model, 'slow_kept', values)
    assert times(trajectory, model.events['attacker.jam_on_repair']) == pytest.approx([repair])
    endings = {model.events[f'attacker.jam_on_repair.{x}']: x for x in ('done', 'stopped', 'skipped')}
    seen = [(endings[e['event']], e['t']) for e in trajectory.trace if e['event'] in endings]
    assert seen == [(ending, pytest.approx(repair + wait))]
    final = trajectory.env_at(200.0)['switch.position']
    assert final == ('jammed' if ending == 'done' else 'off')


def test_two_triggers_that_call_one_waiting_method_each_wait_on_their_own(tmp_path):
    later = 5
    second = fixtures.member(
        'attacker',
        fixtures.event(
            'jam_late',
            f'since(service.repaired) >= {later} h and access is "kept"',
            'switch.position = "jammed"',
            after='reaction_time',
            keep='access is "kept"',
            condition='service.status is "back"',
            records='@ident',
            do_records='@ident',
        ),
    )
    model = build(tmp_path, second)
    repair = value(model, 'service.repair_time', 'slow_kept')
    wait = 10
    values = {
        'responders.removal_time': repair + 100,
        'service.settle_time': 50,
        'attacker.reaction_time': wait,
    }
    _, trajectory = run(model, 'slow_kept', values)
    done = {
        e['event']: e['t']
        for e in trajectory.trace
        if e['event'].startswith('attacker.jam') and e['event'].endswith('.done')
    }
    assert done == {
        model.events['attacker.jam_on_repair.done']: pytest.approx(repair + wait),
        model.events['attacker.jam_late.done']: pytest.approx(repair + later + wait),
    }


def test_a_trigger_that_reads_a_removed_access_never_fires(tmp_path):
    model = build(tmp_path)
    _, trajectory = run(model, 'slow_kept', {'responders.removal_time': 20})
    assert times(trajectory, model.events['responders.clean_up.done']) == pytest.approx([20])
    assert not [e for e in trajectory.trace if e['event'].startswith('attacker.jam')]


def test_a_sum_check_rejects_a_flow_that_leaves_its_stocks(tmp_path):
    leak = fixtures.member(
        'service',
        fixtures.stock('lost', 0, minimum=None, size=None, doc='Users lost', records='@ident'),
        fixtures.flow('leak', 'waiting -> lost', 'service_rate * waiting', records='@ident'),
    )
    model = build(tmp_path, leak)
    with pytest.raises(SimulationError) as caught:
        run(model, 'slow')
    assert 'partition_failed' in {d.get('code') for d in caught.value.diagnostics}


# ---- structures, names and values --------------------------------------------------------------


def test_one_structure_for_each_set_of_start_state_options(tmp_path):
    model = build(tmp_path)
    # Only `Keeps access` sets a start state; `Fast repair` sets an input.
    assert model.start_options == ('Keeps access',)
    assert set(model.structures) == {(), ('Keeps access',)}
    assert model.runs['fast']['starts'] == model.runs['slow']['starts'] == ()
    assert model.structure_of('slow_kept').modes['attacker.access'].initial == 'kept'
    assert model.structure_of('slow').modes['attacker.access'].initial == 'none'


def test_the_parts_that_cannot_act_are_left_out(tmp_path):
    model = build(tmp_path)
    left = model.left_out[()]
    # Without the access the attacker's jam and the removal can never fire.
    assert {'attacker.jam_on_repair', 'responders.clean_up'} <= set(left['rules'])
    assert all(isinstance(why, str) and why for section in left.values() for why in section.values())
    slow, kept = model.structure_of('slow'), model.structure_of('slow_kept')
    assert 'attacker.jam_on_repair' not in slow.rules
    assert 'attacker.jam_on_repair' in kept.rules
    assert not any(model.left_out[('Keeps access',)].values())
    # Every input stays: every run accepts every input.
    assert slow.parameters.keys() == kept.parameters.keys() == model.inputs.keys()
    _, trajectory = run(model, 'slow')
    assert not [e for e in trajectory.trace if e['event'].startswith(('attacker.jam', 'responders.'))]


def test_the_whole_structure_keeps_the_evidence_of_the_parts_left_out(tmp_path):
    model = build(tmp_path)
    left, whole, slow = model.left_out[()], model.whole[()], model.structure_of('slow')
    # The whole structure is the run's structure with the parts left out put back.
    for section, names in left.items():
        assert set(names) <= set(whole.section(section)), section
        assert not set(names) & set(slow.section(section)), section
    for section in ('rules', 'modes', 'quantities', 'flows', 'entities'):
        every, ran = thawed(whole.section(section)), thawed(slow.section(section))
        assert all(every[name] == item for name, item in ran.items()), section
    kept = model.structure_of('slow_kept')
    assert thawed(model.whole[('Keeps access',)].rules) == thawed(kept.rules)
    # Without the access the jam never fires, and the responders never remove the attacker. Over the
    # whole structure the run's trail shows them, and the inputs that only they read, as possible
    # and never as exercised. What the run exercised is the same over both structures.
    rs, trajectory = run(model, 'slow')
    units, served = UnitSystem(LIB['units']), model.outputs['service.served']
    pruned = evidence_trail(rs, trajectory, LIB, units)['outcomes'][served]
    merged = Resolved.of({**rs.plain(), **whole.plain()})
    full = evidence_trail(merged, trajectory, LIB, units)['outcomes'][served]
    idle = {'attacker.jam_on_repair', 'responders.clean_up'}
    idle |= {'attacker.reaction_time', 'responders.removal_time'}
    assert idle <= set(full['possible'])
    assert not idle & set(full['exercised'])
    assert not idle & set(pruned['possible'])
    assert full['exercised'] == pruned['exercised']
    assert {'service.serve', 'switch.position'} <= set(full['exercised'])


def test_without_hidden_access_the_attacker_s_later_moves_are_possible_evidence_only(tmp_path):
    model = build(tmp_path)
    repair = value(model, 'service.repair_time', 'slow_kept')
    # The removal comes before the repair, so the jam never starts, though it could.
    edits = edits_for(model, {'set': {'responders.removal_time': repair / 2}})
    report = sample_result(evaluate_study(model, edits))
    served = model.outputs['service.served']
    trails = {name: run['evidence']['outcomes'][served] for name, run in report['runs'].items()}
    assert 'attacker.reaction_time' in trails['slow']['possible']
    assert 'attacker.reaction_time' in trails['slow_kept']['exercised']


def test_a_part_that_every_run_leaves_out_is_still_checked_and_indexed(tmp_path):
    def jam_when(extra):
        # Only the jam sets the switch to "jammed": the jam can never happen, in any run.
        return fixtures.replace(
            'when count(service.repaired) > 0 and access is "kept":',
            'when count(service.repaired) > 0 and switch.position is "jammed"' + extra + ':',
        )

    # The jam's outcome `done` also fires an event of the switch, which nothing else fires.
    alarm = (
        fixtures.member('switch', fixtures.named_event('alarms', records='@ident')),
        fixtures.member('attacker/jam_on_repair/done', 'switch.alarms'),
    )
    model = build(tmp_path, jam_when(''), *alarm)
    assert all('attacker.jam_on_repair' in left['rules'] for left in model.left_out.values())
    assert not any('switch.alarms' in s.rules for s in model.structures.values())
    # The jam's outcome fires the switch's event: the index still says who fires it.
    assert list(model.index['callers']['switch.alarms']) == ['attacker.jam_on_repair.done']
    with pytest.raises(ModelError) as caught:
        build(tmp_path, jam_when(' and reaction_time > service.users'))
    (error,) = caught.value.diagnostics
    assert error['code'] == 'expression'
    assert error['path'] == 'attacker/jam_on_repair/when:'


def test_the_index_says_who_reaches_each_part_of_another_thing():
    """In sc99 the service watches the state of the control system (`compromised`) and the start of
    the attacker (`stop`), and the first change of the attacker sets that state. The index gives each
    part that a thing reaches in another thing, with each thing that reaches it."""
    model = fixtures.compiled(fixtures.sc99(), fixtures.evidence_library())
    assert thawed(model.index['readers']) == {
        'attacker.start': ['service.attacker.start'],
        'control.state': ['attacker.control.state', 'service.control.state'],
    }


def test_names_follow_the_file(tmp_path):
    """The names of the structure follow the file: each input, fixed value and named state is
    `entity.value`, each event `entity.event` and each of its outcomes `entity.event.outcome`."""
    model = build(tmp_path)
    kept = model.structure_of('slow_kept')
    entity = None
    for row in FIXTURE.splitlines():
        head = re.match(r'(\w+):', row)
        if head or re.match(r'\S', row):
            entity = head.group(1) if head else None
            continue
        member = re.match(r'    (input|let|var|event) (\w+)(.*)', row)
        if entity is None or member is None:
            continue
        kind, name, rest = member.groups()
        # An input of a text, `input actor = "The AI"`, is a text value, not a parameter.
        if kind in ('input', 'let') and not rest.startswith(' = "'):
            assert f'{entity}.{name}' in kept.parameters
        elif kind == 'var' and rest.startswith(': "'):
            assert f'{entity}.{name}' in kept.modes
        elif kind == 'event':
            assert f'{entity}.{name}' in kept.rules
    # An event that waits is one rule, with its delay, whose outcomes are the engine's events.
    jam = kept.rules['attacker.jam_on_repair']
    assert jam.delay is not None and list(jam.emits) == ['attacker.jam_on_repair']
    for outcome in jam.outcomes:
        name = f'attacker.jam_on_repair.{outcome.name}'
        assert list(outcome.emits) == [name] and model.events[name] == name
    assert model.events['attacker.jam_on_repair.done'] == 'attacker.jam_on_repair.done'
    # The start is the event `start` of the attacker.
    assert model.events['attacker.start'] == 'attacker.start' and 'attacker.start' in kept.rules
    # A flow of one pair keeps its name; an output of a stock is not the stock.
    assert 'service.serve' in kept.flows
    assert model.outputs['service.served'] != 'service.served'
    assert written(kept.outcomes[model.outputs['service.served']].expr) == 'service.served'
    assert model.initiation['rule'] == 'attacker.start'


def test_the_first_move_is_the_first_event_of_every_run(tmp_path):
    model = build(tmp_path)
    for name in model.runs:
        _, trajectory = run(model, name)
        # The start's firing is the first step of the trace, at t = 0: the story tells it first, also
        # when the start has no text of its own.
        first = trajectory.trace[0]
        assert (first['t'], first['rule'], first['outcome']) == (0.0, model.initiation['rule'], 'done')
        assert times(trajectory, model.initiation['effect']) == [0.0]


def test_resolve_checks_the_values(tmp_path):
    model = build(tmp_path)

    def codes(values):
        with pytest.raises(ModelError) as caught:
            model.resolve('slow', values)
        return {d['code'] for d in caught.value.diagnostics}

    low, high = model.inputs['service.repair_time']['range']
    assert codes({'service.repair_time': high + 1}) == {'bounds'}
    assert codes({'service.users': model.inputs['service.users']['value'] + 1}) == {'locked'}
    assert codes({'service.no_such_input': 1}) == {'input'}
    assert model.resolve('slow') == model.resolve('slow')
    rs = model.resolve('slow', {'service.repair_time': low + 2})
    assert rs.parameter_values['service.repair_time'] == low + 2
    assert rs.run == 'slow' and rs.model_hash == model.model_hash


def test_the_checks_of_the_values_read_each_kind_of_input():
    """`check_parameters` reads the inputs of a structure: a number is inside the range of its input,
    a yes/no input is 0 or 1, and a named input is the code of one of its three values, 0 to 2.
    The values of the file give no diagnostic; each value outside gives one of its kind under the
    name of its input; a name that is no input, and a value that is no number, give one too."""
    source = fixtures.system(
        fixtures.parameter('n', 10, 'people', 1, 20, doc='People'),
        f'input on = true  {fixtures.BASIS}\n    "On"',
        f'input level: "low" | "high" | "severe" = "high"  {fixtures.BASIS}\n    "Level"',
        fixtures.stock('held', 'n if on and level is "high" else 0 people', doc='Held'),
        outputs=(fixtures.output('held', 's.held', 'people', 'level', doc='Held'),),
    )
    definitions = fixtures.compiled(source).structure_of('a').parameters

    def found(values):
        errors = []
        check_parameters(definitions, values, 'values', errors)
        return {(item['code'], item['path']) for item in errors}

    assert found({'s.n': 10, 's.on': 1, 's.level': 1}) == set()
    assert found({'s.n': 1, 's.on': 0, 's.level': 2}) == set()
    assert ('bounds', 'values/s.n') in found({'s.n': 21})
    assert ('binary_control', 'values/s.on') in found({'s.on': 2})
    assert ('choice_control', 'values/s.level') in found({'s.level': 3})
    assert found({'s.other': 1}) == {('parameter', 'values/s.other')}
    assert found({'s.n': math.nan}) == {('parameter', 'values/s.n')}


def test_a_resolution_checks_the_value_that_its_structure_has_for_each_input():
    """A resolution first checks each input of its structure with the value that the structure
    has for it. A structure whose own value of the people is above the range of that input (set
    after the compilation) is refused under the name of the input, with the values of a run that
    the structure of the file resolves."""
    model = fixtures.compiled(fixtures.scenario())
    structure = model.structures[()]
    people = structure.parameters['service.n']
    numbers, problems = model.numbers(model.run_values('a'))
    assert not problems and model.resolve_in(structure, numbers, 'the file').values
    above = people.changed(value=people.adjust.maximum + 1)
    with pytest.raises(ModelError) as refused:
        model.resolve_in(structure.with_part('parameters', 'service.n', above), numbers, 'changed')
    assert [(item['code'], item['path']) for item in refused.value.diagnostics] == [
        ('bounds', 'changed/parameters/service.n')
    ]


def test_the_evidence_index_names_the_parts_of_the_file(tmp_path):
    """The index names each part that cites a record by its place in the file, at its line: the
    record at the end of an event's line supports the event."""
    model = build(tmp_path)
    rows = (tmp_path / 'MODELTEST.scn').read_text(encoding='utf-8').splitlines()
    uses = [u for u in model.index['uses'] if u['part'] == 'service/repaired']
    assert [u['name'] for u in uses] == ['ident']
    line = next(i for i, row in enumerate(rows, 1) if row.startswith('    event repaired '))
    assert uses[0]['line'] == line
    # A profile's value carries its own support.
    assert any(u['part'] == 'options:/Access/Keeps access/attacker.access' for u in model.index['uses'])


def test_the_model_hash_follows_the_document(tmp_path):
    first = build(tmp_path)
    assert build(tmp_path).model_hash == first.model_hash
    changed = build(tmp_path, fixtures.replace('let users = 1000 people', 'let users = 999 people'))
    assert changed.model_hash != first.model_hash


WAVES = '\n\n'.join(
    (
        fixtures.template(
            'Wave',
            fixtures.parameter('size', 10, 'people', doc='Users in the wave', records='@ident'),
            fixtures.parameter(
                'arrival_rate', 0.1, 'per_h', doc='Share of the wave that arrives each hour', records='@ident'
            ),
            fixtures.stock(
                'pending', 'size', minimum=None, size=None, doc='Users not yet in', records='@ident'
            ),
            fixtures.stock('arrived', 0, minimum=None, size=None, doc='Users in', records='@ident'),
            fixtures.stock(
                'counted', 0, minimum=None, size=None, kind='tally', doc='Users counted', records='@ident'
            ),
            fixtures.flow(
                'arrive',
                ['pending -> arrived', fixtures.move(None, 'counted')],
                'arrival_rate * pending',
                records='@ident',
                together='@ident',
            ),
            doc='A wave of users who arrive later.',
            role='community',
            records='@ident',
        ),
        fixtures.entity('waves', template='Wave', records=None, copies=2),
    )
)


def test_a_copy_is_set_k_and_a_flow_of_two_pairs_moves_together(tmp_path):
    model = build(tmp_path, fixtures.replace('options "Response":', WAVES + '\n\noptions "Response":'))
    kept = model.structure_of('slow')
    assert model.entities['waves_2'] == 'waves.2'
    assert {'waves_1.arrive.0', 'waves_1.arrive.1', 'waves_2.arrive.0'} <= set(kept.flows)
    assert list(kept.coupling['waves_1.arrive'].flows) == ['waves_1.arrive.0', 'waves_1.arrive.1']
    _, trajectory = run(model, 'slow')
    size = value(model, 'waves_1.size', 'slow')
    k = value(model, 'waves_1.arrival_rate', 'slow')
    env = trajectory.env_at(20.0)
    # pending(t) = size·e^(-k t); what leaves pending arrives, and the tally counts the same.
    assert env['waves_1.pending'] == pytest.approx(size * math.exp(-k * 20.0), rel=1e-6)
    assert env['waves_1.arrived'] == pytest.approx(size - env['waves_1.pending'], rel=1e-6)
    assert env['waves_2.counted'] == pytest.approx(env['waves_2.arrived'], rel=1e-6)


# ---- each misuse where it is ---------------------------------------------------------------------


def line_of(text, needle):
    return next(i for i, line in enumerate(text.splitlines(), 1) if needle in line)


class Row(str):
    """The text of the row, without its indentation, where the reader rejects a line of the wrong form.
    Such a diagnostic names the line of the file, and no place in it."""


def where(text, diagnostic):
    """(code, place) of a diagnostic of `text`; for a line of the wrong form, (code, its `Row`)."""
    if diagnostic['code'] == 'syntax':
        return diagnostic['code'], Row(text.splitlines()[diagnostic['line'] - 1].strip())
    return diagnostic['code'], diagnostic['path']


def assert_where(tmp_path, steps, place, words):
    """`assert_located`, or, for a `Row`, the reader's one diagnostic of the file with the steps, which
    says `words` and names the line that holds the row."""
    if not isinstance(place, Row):
        assert_located(tmp_path, steps, place, words)
        return
    diagnostics = located(tmp_path, *steps)
    text = (tmp_path / 'MODELTEST.scn').read_text(encoding='utf-8')
    assert [where(text, d) for d in diagnostics] == [('syntax', place)], diagnostics
    assert words in diagnostics[0]['message']


# Each case keeps the id that it had in the earlier language, which named the parts by other paths.
MISUSES = [
    pytest.param(
        (fixtures.replace('let users = 1000 people', 'let input users = 1000 people'),),
        Row('let input users = 1000 people  @ident'),
        'let input = value',
        id='<lambda>-classes/Service/fields/users-one job',
    ),
    # A type is a unit, `bool` or named values.
    pytest.param(
        (fixtures.replace('let users = 1000 people', 'let users: true = 1000 people'),),
        'service/users',
        'unknown unit',
        id='<lambda>-classes/Service/fields/users/fixed-holds its type',
    ),
    pytest.param(
        (fixtures.replace('let users = 1000 people', 'let users: people = 1000'),),
        'service/users',
        'write the unit of the number',
        id='<lambda>-classes/Service/fields/users/value-write the unit of the number',
    ),
    pytest.param(
        (fixtures.replace('let users = 1000 people', 'let users: people = 1000 h'),),
        'service/users',
        'is not in a unit of people',
        id='<lambda>-classes/Service/fields/users/value-is not in a unit of people',
    ),
    pytest.param(
        (fixtures.replace('let users = 1000 people', 'let users: yes = 1000 people'),),
        'service/users',
        'unknown unit',
        id='<lambda>-classes/Service/fields/users/fixed-unknown unit',
    ),
    pytest.param(
        (fixtures.member('scenario:', 'timescales'),),
        'scenario:/timescales:',
        'shortest physical times',
        id='<lambda>-timescales-shortest physical times',
    ),
    pytest.param(
        (fixtures.member('attacker/jam_on_repair/done', 'switch.position = "off"'),),
        'attacker/jam_on_repair/done/1',
        'written twice',
        id='<lambda>-classes/Service/methods/repair/do/1-written twice',
    ),
    pytest.param(
        (fixtures.member('options:/Access/Keeps access', 'service.repair_time = 5 h  @ident'),),
        'options:/Response/Fast repair/service.repair_time',
        'options of two groups',
        id='<lambda>-classes/Service/options/Fast repair/repair_time-options of two groups',
    ),
    pytest.param(
        (fixtures.member('runs:', 'both = "Slow repair" + "No access" + "Keeps access"'),),
        'runs:/both',
        'not two of',
        id='<lambda>-simulate/runs/both-not two of',
    ),
    pytest.param(
        (fixtures.replace('service.repair_time = 10 h  @ident', 'service.repair_time  @ident'),),
        Row('service.repair_time  @ident'),
        'a line of an option sets a value',
        id="<lambda>-classes/Service/options/Fast repair/repair_time-has 'value'",
    ),
    pytest.param(
        (fixtures.replace('service.repair_time = 10 h  @ident', 'service.repair_tim = 10 h  @ident'),),
        'options:/Response/Fast repair/service.repair_tim',
        'is not a value of',
        id='<lambda>-classes/Service/options/Fast repair/repair_tim-not a field',
    ),
    pytest.param(
        (fixtures.member('options:/Response/Fast repair', 'service.users = 10 people  @ident'),),
        'options:/Response/Fast repair/service.users',
        'sets an input',
        id='<lambda>-classes/Service/options/Fast repair/users-sets an input',
    ),
    pytest.param(
        (fixtures.replace('flow serve: waiting -> served at', 'flow serve: waiting at'),),
        Row('flow serve: waiting at service_rate * waiting while status is not "down"  @ident'),
        'a pair is a -> b',
        id='<lambda>-classes/Service/policy/serve/move-a flow moves `from -> to`',
    ),
    pytest.param(
        (
            fixtures.append(
                fixtures.check(
                    'service.waiting + service.users is service.users',
                    'Every user waits or is served.',
                    records='@ident',
                    within='0.001 people',
                )
            ),
        ),
        'assert:/0',
        'is not a number var',
        id='<lambda>-simulate/checks/0/sum-stock or tally',
    ),
    pytest.param(
        (
            fixtures.replace(
                '    status failed when status is "down"',
                '    status ok\n        "Fine"\n    status failed when status is "down"',
            ),
        ),
        'service/status:/0',
        'but the last has a condition',
        id='<lambda>-classes/Service/shows/0-has a `when`',
    ),
]


@pytest.mark.parametrize(('steps', 'place', 'words'), MISUSES)
def test_the_reader_rejects_each_misuse_where_it_is(tmp_path, steps, place, words):
    assert_where(tmp_path, steps, place, words)


@pytest.mark.parametrize(
    ('steps', 'place'),
    [
        # The memory of an event: the state that it fires from.
        pytest.param(
            (
                fixtures.replace(
                    'event repaired when status is "down"', 'event repaired when status is "dwon"'
                ),
            ),
            'service/repaired/when:',
            id='edit-classes/Service/policy/repaired/when',
        ),
        # A gate on the entity's own state, and on another entity's.
        pytest.param(
            (
                fixtures.replace(
                    'when count(service.repaired) > 0 and access is "kept":',
                    'when count(service.repaired) > 0 and access is "kpt":',
                ),
            ),
            'attacker/jam_on_repair/when:',
            id='edit-classes/Attacker/policy/jam_on_repair/when',
        ),
        pytest.param(
            (fixtures.replace('when attacker.access is "kept" and', 'when attacker.access is "kpt" and'),),
            'responders/clean_up/when:',
            id='edit-classes/Responders/policy/clean_up/when',
        ),
        # What keeps the jam going: the chance of its outcome `done`.
        pytest.param(
            (fixtures.replace('done access is "kept" and', 'done access is "kpt" and'),),
            'attacker/jam_on_repair/done/chance',
            id='edit-classes/Attacker/methods/jam/keep',
        ),
        pytest.param(
            (fixtures.replace('while status is not "down"', 'while status is not "dwon"'),),
            'service/serve/while:',
            id='edit-classes/Service/policy/serve/while',
        ),
        pytest.param(
            (fixtures.replace('status failed when status is "down"', 'status failed when status is "dwon"'),),
            'service/status:/0',
            id='edit-classes/Service/shows/0/when',
        ),
        pytest.param(
            (
                fixtures.member(
                    'service',
                    fixtures.check('switch.position is not "of"', 'The switch is not off.', records='@ident'),
                ),
            ),
            'service/assert:/1',
            id='_check-classes/Service/checks/1',
        ),
    ],
)
def test_a_test_of_a_named_state_names_one_of_its_values(tmp_path, steps, place):
    """A misspelt value never matches: its test would always be false, or true with `is not`, so the
    parts that it guards could never act, or always would. Before, every case here built."""
    assert_located(tmp_path, steps, place, 'is not a value of the named state')


def output_total(*lines):
    """An edit step: an output of the users served at the top level, with `lines` under it."""
    return fixtures.append(
        fixtures.output(
            'total', 'service.served', 'people', doc='Total served', records='@ident', under=lines
        )
    )


def repair_time_range(low, high):
    """An edit step: the range of `repair_time` written `in low to high`."""
    return fixtures.replace(
        'input repair_time = 30 h in 1 h to 90 h', f'input repair_time = 30 h in {low} to {high}'
    )


# The values that the reader checks, as the schema did: texts and names, times, ranges,
# sizes, the values of named states and the values that profiles give them.
VALUES = {
    'an option sets a named state to a value that it does not have': (
        (fixtures.replace('attacker.access = "kept"  @ident', 'attacker.access = "kepts"  @ident'),),
        'options:/Access/Keeps access/attacker.access',
        'starts in one of its states',
    ),
    'the horizon is not after the start': (
        (fixtures.replace('horizon 200 h', 'horizon 0 h'),),
        'scenario:/horizon:',
        'after the start',
    ),
    'an ID on the scenario line': (
        (fixtures.replace('scenario "Reader test"', 'scenario MODELTEST "Reader test"'),),
        Row('scenario MODELTEST "Reader test"'),
        'the line has no ID',
    ),
    'a line that the scenario does not have': (
        (fixtures.member('scenario:', 'swap "Response"'),),
        Row('swap "Response"'),
        'has no line swap',
    ),
    'a scope that is no text': (
        (fixtures.replace('scope "Synthetic users."', 'scope ""'),),
        'scenario:/scope:',
        'nonempty text',
    ),
    'a scenario line that is not the first declaration': (
        (fixtures.append('scenario "Second"'),),
        Row('scenario "Second"'),
        'first declaration',
    ),
    'repeated values of a named state': (
        (fixtures.replace('"on" | "off" | "jammed"', '"on" | "on" | "off" | "jammed"'),),
        'switch/position',
        'each value once',
    ),
    'a value of a named state that is not a name': (
        (fixtures.replace('"on" | "off" | "jammed"', '"on" | "off" | "jammed" | "out of order"'),),
        'switch/position',
        'is a name',
    ),
    'a doc of a field that is not text': (
        (fixtures.replace('"Time to repair"', '5'),),
        Row('5'),
        'does not belong here',
    ),
    'a doc of a field that is a list': (
        (fixtures.replace('"Time to repair"', '["Time", "Time again"]'),),
        'service/repair_time/""',
        'nonempty text',
    ),
    'a doc of a flow that is not text': (
        (fixtures.replace('"Waiting users are served."', '5'),),
        Row('5'),
        'does not belong here',
    ),
    'a doc of the start that is not text': (
        (fixtures.member('attacker/start', '5'),),
        Row('5'),
        'a line of a change sets a value',
    ),
    'a doc of a main output that is not text': (
        (fixtures.append('output total: people = service.served  @ident\n    5'),),
        Row('5'),
        'the lines of an output',
    ),
    'what an output counts that is not text': (
        (fixtures.member('service/served/output:', 'about 5'),),
        Row('about 5'),
        'about is a text in quotes',
    ),
    'a kind of a main output that the language does not have': (
        (output_total('bogus'),),
        Row('bogus'),
        'an output has no line bogus',
    ),
    'a negative share of a mixture lag': (
        (output_total('lag mixture([-0.5, 2 h], [1.5, 4 h])'),),
        Row('lag mixture([-0.5, 2 h], [1.5, 4 h])'),
        'its share is a number',
    ),
    'a line of the menu that is not text': (
        (fixtures.replace('        "The defaults."', '        5'),),
        Row('5'),
        'a line of an option sets a value',
    ),
    'a run name that an edit cannot name': (
        (fixtures.member('runs:', 'half rate = "Fast repair"'),),
        Row('half rate = "Fast repair"'),
        'a run is `name =',
    ),
    'a size of 0': (
        (
            fixtures.replace(
                'var waiting: people = users  @ident', 'var waiting: people = users size 0 people  @ident'
            ),
        ),
        'service/waiting/size:',
        'a number above 0',
    ),
    'a size that is not a number': (
        (
            fixtures.replace(
                'var waiting: people = users  @ident', 'var waiting: people = users size big  @ident'
            ),
        ),
        'service/waiting/size:',
        'a number above 0',
    ),
    'a range of texts': (
        (repair_time_range('"1"', '"90"'),),
        'service/repair_time/min:',
        'is a number with its unit',
    ),
    'a range whose limit is text': (
        (repair_time_range('"1"', '90 h'),),
        'service/repair_time/min:',
        'is a number with its unit',
    ),
    'a sum check of one stock': (
        (fixtures.replace('assert waiting + served is users within', 'assert waiting is users within'),),
        'service/assert:/0',
        'two or more',
    ),
    'a role that is not a name': (
        (fixtures.replace('    role operator\n    var position', '    role 5\n    var position'),),
        Row('role 5'),
        'a line of a thing is',
    ),
}


@pytest.mark.parametrize(('steps', 'place', 'words'), VALUES.values(), ids=VALUES)
def test_the_reader_checks_each_value_where_it_is(tmp_path, steps, place, words):
    """Each of these crashed, failed in every study, or built and ran with a value that the language does
    not have, until the reader checked it (local-P3-review H2)."""
    assert_where(tmp_path, steps, place, words)


def test_a_mistake_in_an_expression_is_located_at_its_line(tmp_path):
    misspelt = fixtures.replace('elapsed(status) >= repair_time', 'elapsed(status) >= repair_tim')
    with pytest.raises(ModelError) as caught:
        build(tmp_path, misspelt)
    bad = fixtures.edit(FIXTURE, misspelt)
    assert line_of(bad, 'elapsed(status) >= repair_tim:') in {d.get('line') for d in caught.value.diagnostics}


# ---- the support of each part -------------------------------------------------------------------


def names_of(basis):
    """The names of the records of a basis: one record or a list."""
    return [record['name'] for record in basis_records(basis)]


def test_a_method_an_option_and_the_first_move_keep_their_support(tmp_path):
    support = (
        fixtures.replace(
            'elapsed(status) >= repair_time:  @ident', 'elapsed(status) >= repair_time:  @ident @attack'
        ),
        fixtures.replace('service.repair_time = 10 h  @ident', 'service.repair_time = 10 h  @access'),
    )
    model = build(tmp_path, *support)
    s = model.structure_of('slow')
    # The support of when the event happens and of its change, on its line; the input's and its
    # profile's; the start's own, on its line.
    assert set(names_of(s.rules['service.repaired'].basis)) == {'ident', 'attack'}
    assert set(names_of(s.parameters['service.repair_time'].basis)) == {'ident', 'access'}
    start = next(row for row in FIXTURE.splitlines() if row.startswith('    event start '))
    assert names_of(model.initiation['basis']) == re.findall(r'@(\w+)', start)


def test_a_list_of_bases_records_one_use_per_record(tmp_path):
    two = fixtures.replace(
        'elapsed(status) >= repair_time:  @ident', 'elapsed(status) >= repair_time:  @ident @attack'
    )
    model = build(tmp_path, two)
    uses = [u for u in model.index['uses'] if u['part'] == 'service/repaired']
    assert sorted(u['name'] for u in uses) == ['attack', 'ident']


def test_a_list_of_bases_keeps_the_report_contract(tmp_path):
    two = (
        fixtures.replace(
            'elapsed(status) >= repair_time:  @ident', 'elapsed(status) >= repair_time:  @ident @attack'
        ),
        fixtures.replace('var served: people = 0  @ident', 'var served: people = 0  @ident @attack'),
    )
    model = build(tmp_path, *two)
    report = sample_result(evaluate_study(model))
    schema = json.loads((SCHEMAS / 'report.schema.json').read_text())
    Draft202012Validator(schema).validate(json.loads(json.dumps(report, allow_nan=False)))
    served = model.outputs['service.served']
    for run_report in report['runs'].values():
        step = next(e for e in run_report['trace'] if e['event'] == model.events['service.repaired.done'])
        assert names_of(step['basis']) == ['ident', 'attack']
        assert names_of(run_report['evidence']['outcomes'][served]['basis']) == ['ident', 'attack']


# ---- the analysis of what can act --------------------------------------------------------------


def rule(rid, when, mode=None, sources=None, to=None, sets=None):
    """A flat rule with one outcome, `done`, that sets the named states `sets`. With `mode`, it fires
    only from the `sources` of that named state, which its outcome sets to `to`: `when s is "a" and
    C:` with `s = "b"`."""
    sets = dict(sets or {})
    if mode is not None:
        when = '(' + ' or '.join(f'{mode} == {value!r}' for value in sources) + f') and ({when})'
        sets = {mode: to, **sets}
    return {
        'id': rid,
        'entity': 'e',
        'label': None,
        'basis': None,
        'path': rid,
        'rank': [0],
        'once': False,
        'named': False,
        'trigger': {'when': read(when)},
        'delay': None,
        'outcomes': [
            {
                'name': 'done',
                'chance': None,
                'label': None,
                'basis': None,
                'path': rid,
                'do': {'set': {k: {'mode': v} for k, v in sets.items()}, 'transfer': [], 'fire': []},
                'emits': [f'{rid}.done'],
            }
        ],
        'emits': [rid],
    }


def structure(modes, rules):
    return {
        'modes': {name: {'values': list(values), 'initial': values[0]} for name, values in modes.items()},
        'rules': {r['id']: r for r in rules},
    }


def test_two_states_that_change_together_are_followed_together():
    s = structure(
        {'e.a': ['x', 'y'], 'e.b': ['p', 'q']},
        [
            rule('e.both', 'True', 'e.a', ['x'], 'y', {'e.b': 'q'}),
            rule('e.never', "e.a == 'y' and e.b == 'p'"),
            rule('e.later', "e.a == 'y' and e.b == 'q'"),
            rule('e.after_never', 'e.never__count > 0'),
            rule('e.after_later', 'e.later__count > 0 and t - e.later__time >= 1'),
        ],
    )
    acting = Acting(s)
    assert acting.fired == {'e.both', 'e.later', 'e.after_later'}
    assert acting.pairs[('e.a', 'e.b')] == {('x', 'p'), ('y', 'q')}


def test_a_waiting_method_whose_keep_never_holds_never_starts():
    """An event that waits makes its change in its outcome `done`, whose chance is what keeps it going:
    where the access is never kept, that outcome never happens, and nor does what its change starts.
    The event still fires, and ends `stopped`."""
    s = structure({'e.access': ['none', 'kept'], 'e.target': ['clean', 'hit']}, [])
    act = rule('e.act', 'True', sets={'e.target': 'hit'})
    act['delay'] = read('1')
    act['outcomes'][0]['chance'] = read("e.access == 'kept'")
    stopped = {
        **copy.deepcopy(act['outcomes'][0]),
        'name': 'stopped',
        'chance': 'else',
        'emits': ['e.act.stopped'],
    }
    stopped['do']['set'] = {}
    act['outcomes'].append(stopped)
    hit = rule('e.hit', "e.target == 'hit'")
    for item in (act, hit):
        s['rules'][item['id']] = item
    acting = Acting(s)
    assert 'e.act' in acting.fired and ('e.act', 1) in acting.committed
    assert ('e.act', 0) not in acting.committed and 'e.hit' not in acting.fired
    # Once the access can be kept, everything can happen.
    s['modes']['e.access']['initial'] = 'kept'
    acting = Acting(s)
    assert ('e.act', 0) in acting.committed and 'e.hit' in acting.fired


def reachable(s):
    """Every rule that fires in some state that the runs of a small structure reach: an exhaustive
    search over the values of its named states and the events that have happened."""
    names = sorted(s['modes'])
    start = (tuple(s['modes'][n]['initial'] for n in names), frozenset())
    seen, pending, fired = {start}, [start], set()
    while pending:
        values, events = pending.pop()
        env = dict(zip(names, values, strict=True))
        for rid, item in s['rules'].items():
            counts = {f'{e}__count': 1 if e in events else 0 for e in s['rules']}
            if not eval(written(item['trigger']['when']), {}, {**env, **counts}):
                continue
            fired.add(rid)
            after = dict(env)
            (outcome,) = item['outcomes']
            after.update({k: v['mode'] for k, v in outcome['do']['set'].items()})
            state = (tuple(after[n] for n in names), events | {rid})
            if state not in seen:
                seen.add(state)
                pending.append(state)
    return fired


def random_structure(rng):
    modes = {f'm{i}': [f'v{j}' for j in range(rng.randint(2, 3))] for i in range(3)}
    rules = []
    for r in range(rng.randint(3, 7)):
        terms = []
        for name in rng.sample(sorted(modes), rng.randint(0, 2)):
            op = rng.choice(['==', '!='])
            terms.append(f'{name} {op} {rng.choice(modes[name])!r}')
        if r and rng.random() < 0.4:
            terms.append(f'r{rng.randrange(r)}__count > 0')
        when = ' and '.join(terms) or 'True'
        if rng.random() < 0.3 and len(terms) > 1:
            when = f'({terms[0]}) or ({" and ".join(terms[1:])})'
        mode = rng.choice([None, *sorted(modes)])
        sources = rng.sample(modes[mode], rng.randint(1, len(modes[mode]))) if mode else None
        to = rng.choice(modes[mode]) if mode else None
        sets = {}
        for name in rng.sample([n for n in sorted(modes) if n != mode], rng.randint(0, 2)):
            sets[name] = rng.choice(modes[name])
        rules.append(rule(f'r{r}', when, mode, sources, to, sets))
    return structure({k: v for k, v in modes.items()}, rules)


def test_the_analysis_never_misses_a_rule_that_can_fire():
    rng = random.Random(20261015)
    tighter = 0
    for _ in range(300):
        s = random_structure(rng)
        fired = reachable(s)
        acting = Acting(s)
        assert fired <= acting.fired, (fired - acting.fired, s)
        tighter += len(set(s['rules']) - acting.fired)
    # The analysis leaves out some rules too: it is not everything.
    assert tighter > 0


def test_the_values_of_two_states_together_cover_every_reachable_pair():
    rng = random.Random(7)
    for _ in range(200):
        s = random_structure(rng)
        acting = Acting(s)
        names = sorted(s['modes'])
        start = tuple(s['modes'][n]['initial'] for n in names)
        seen, pending = {(start, frozenset())}, [(start, frozenset())]
        while pending:
            values, events = pending.pop()
            env = dict(zip(names, values, strict=True))
            for (a, b), pair in acting.pairs.items():
                assert (env[a], env[b]) in pair
            for name in names:
                assert env[name] in acting.reach[name]
            for rid, item in s['rules'].items():
                counts = {f'{e}__count': 1 if e in events else 0 for e in s['rules']}
                if not eval(written(item['trigger']['when']), {}, {**env, **counts}):
                    continue
                after = dict(env)
                (outcome,) = item['outcomes']
                after.update({k: v['mode'] for k, v in outcome['do']['set'].items()})
                state = (tuple(after[n] for n in names), events | {rid})
                if state not in seen:
                    seen.add(state)
                    pending.append(state)


def test_every_pair_of_runs_shares_one_menu(tmp_path):
    model = build(tmp_path)
    groups = {p: g for g, options in model.menu.items() for p in options}
    for name, info in model.runs.items():
        chosen = [groups[p] for p in info['options']]
        assert len(chosen) == len(set(chosen)), name
    assert all(info['comparison_of'] in (None, *model.runs) for info in model.runs.values())
    # The run that the pages show first is the brief's.
    assert styles.featured(styles.brief_of(model), model) == ['slow_kept']


# ---- the checks of a file: each in one place, in the model --------------------------------------


def test_the_version_is_checked_in_one_place(tmp_path):
    """A file with no scenario line is not a model file of the language: both entry points reject it,
    with one diagnostic."""
    text = fixtures.scenario().split('\n\n', 1)[1]
    with pytest.raises(ModelError) as by_text:
        fixtures.compiled(text)
    path = tmp_path / 'no_block.scn'
    path.write_text(text, encoding='utf-8')
    with pytest.raises(ModelError) as by_file:
        build_model(path, fixtures.library())
    found = [
        [(d['code'], d['path'], d['message']) for d in caught.value.diagnostics]
        for caught in (by_text, by_file)
    ]
    assert found[0] == found[1]
    ((code, place, _),) = found[0]
    assert (code, place) == ('version', 'scenario:')


def with_profiles(text, group, *members):
    """`text` with a group of profiles after its others."""
    return fixtures.edit(
        text, fixtures.replace('\nruns:\n', '\n' + fixtures.options(group, *members) + '\n\nruns:\n')
    )


def start_option(check):
    """The analytic transfer with a profile that no run names and that starts the service off, and a
    check that every run must hold."""
    text = fixtures.edit(
        fixtures.scenario(), fixtures.member('service', fixtures.check(check, 'The service runs'))
    )
    off = fixtures.option(
        'Off at start', 'The service starts off.', f'service.state = "off"  {fixtures.BASIS}'
    )
    return with_profiles(text, 'Start', off)


def test_an_option_that_no_run_names_is_checked_in_the_structure_of_its_start_states():
    """A profile that sets a start state and that no run names needs a structure that no run has: the
    model derives it, checks the profile there with the other profiles of each run, and keeps only the
    runs' structures."""
    model = fixtures.compiled(start_option('state is "on" or n > 0 people'))
    assert model.start_options == ('Off at start',) and set(model.structures) == {()}
    # With the service off at the start, the check fails at once: only the profile shows it.
    with pytest.raises(ModelError) as caught:
        fixtures.compiled(start_option('state is "on"'))
    found = caught.value.diagnostics
    assert found and all(d['options'][0] == 'Off at start' and 'run' not in d for d in found)


def late_stop(end, named):
    """The analytic transfer with a profile that stops the service at `end` hours, which the check of
    the inputs at the top level limits to 24 hours; run `c` names the profile when `named`."""
    text = fixtures.edit(
        fixtures.with_horizon(fixtures.scenario(), 48),
        fixtures.replace('input end: h = 12 h in 1 h to 24 h', 'input end: h = 12 h in 1 h to 48 h'),
    )
    late = fixtures.option('Late stop', 'The service stops late.', f'service.end = {end} h  {fixtures.BASIS}')
    text = with_profiles(text, 'Stop', late)
    return fixtures.edit(text, fixtures.member('runs:', 'c = "Default" + "Late stop"')) if named else text


@pytest.mark.parametrize('named', [False, True])
def test_an_option_that_breaks_a_check_of_the_inputs_is_rejected_whether_a_run_names_it_or_not(named):
    """One rule for every run and every choice of profiles: the build applies the blocking checks of the
    inputs to the values of each run, as it does to each choice that no run makes, so a model that
    builds has an admissible default study (local-P3-review M2)."""
    with pytest.raises(ModelError) as caught:
        fixtures.compiled(late_stop(30, named))
    found = [d for d in caught.value.diagnostics if d['code'] == 'check:simulate.0']
    assert found and all(d['path'] == 'assert:/0' for d in found), caught.value.diagnostics
    if named:
        assert {d.get('run') for d in found} == {'c'}
    else:
        assert all(d['options'][0] == 'Late stop' and 'run' not in d for d in found)
    model = fixtures.compiled(late_stop(20, named))
    assert evaluate_study(model).admissible
    if named:
        # The run's own values resolve as the build checked them.
        assert model.resolve('c').parameter_values['service.end'] == 20


def test_a_rationing_entry_names_its_policy_entry_and_its_line():
    text = fixtures.edit(
        fixtures.scenario(),
        fixtures.member(
            'service',
            fixtures.flow('spill', 'stock -> served', '0 people/h'),
            # A limit is a rate: people are not people an hour.
            fixtures.share('stock', '1 people'),
        ),
    )
    with pytest.raises(ModelError) as caught:
        fixtures.compiled(text)
    (found,) = caught.value.diagnostics
    assert found['path'] == 'service/share_stock'
    assert found['line'] == line_of(text, 'share stock limit')


def test_a_status_case_names_its_key_in_the_file():
    """A status line whose condition takes the logarithm of a negative number fails its domain check,
    and the diagnostic names the condition of the line as the file writes it: `status:/0/when`."""
    down = fixtures.status(('failed', 'ln(-n / 1 people) > 0', 'Down'), ('ok', None, 'Up'))
    text = fixtures.edit(fixtures.scenario(), fixtures.member('service', down))
    assert ('label_domain', 'service/status:/0/when') in fixtures.rejected(text, fixtures.library())


# One person divided by a stock that can be empty, read where a step or a sum reads it.
SHARE = '1 people * 1 people / x'


def reading(part, share=SHARE):
    """A system with a stock `x` that drains into `y`, which reads `share` in one place: an event's
    `when`, the time that an event waits (`after`), the chance of the outcome `done` of an event that
    waits, a set of `z`, a move or the `within` of a sum."""
    when, changes, checks = 'true', (), ()
    go = {'transition': 'flag "no" -> "yes"'}
    if part == 'when':
        when = f'{share} > 0.5 people'
    elif part == 'after':
        when, changes = 'flag is "no"', ('flag = "yes"',)
        go = {'after': f'1 h * ({share}) / 1 people'}
    elif part == 'if':
        when, changes = 'flag is "no"', ('flag = "yes"',)
        go = {'after': '1 h', 'condition': f'{share} > 0.5 people', 'do_records': fixtures.BASIS}
    elif part == 'set':
        changes = (f'z = {share}',)
    elif part == 'move':
        changes = (f'move {share} from x to y',)
    else:
        checks = (fixtures.check('x + y is 1 people', 'The two stocks hold one person.', within=share),)
    return fixtures.system(
        fixtures.stock('x', 1),
        fixtures.stock('y'),
        fixtures.stock('z'),
        fixtures.named('flag', 'no', 'yes'),
        fixtures.event('go', when, *changes, **go),
        fixtures.flow('drain', fixtures.move('x', 'y'), '1 people/h'),
        *checks,
        horizon=2,
    )


@pytest.mark.parametrize(
    ('part', 'diagnostic'),
    [
        ('when', ('rule_domain', 's/go/when')),
        ('after', ('rule_domain', 's/go/after:')),
        ('if', ('rule_domain', 's/go/done/chance')),
        # The first line of `done` is the change of the state that `go` fires from.
        ('set', ('rule_domain', 's/go/done/1')),
        ('move', ('rule_domain', 's/go/done/1')),
        ('within', ('check_domain', 's/assert:/0/tolerance')),
    ],
)
def test_a_division_that_a_step_or_a_sum_check_reads_is_proven_at_build(part, diagnostic):
    assert diagnostic in fixtures.rejected(reading(part), fixtures.library())


def test_a_guard_on_a_sum_proves_a_division_by_that_sum():
    # The share of x in x + y, where both can be empty: the guard on the sum proves its denominator.
    guarded = 'x / (x + y) * 1 people if x + y > 0 people else 0 people'
    fixtures.compiled(reading('set', guarded))
    unguarded = 'x / (x + y) * 1 people'
    assert ('rule_domain', 's/go/done/1') in fixtures.rejected(reading('set', unguarded), fixtures.library())


@pytest.mark.parametrize(
    ('members', 'diagnostic'),
    [
        (
            (fixtures.parameter('k', 0, 'fraction'), fixtures.stock('x', 1, maximum='2 people / k')),
            ('bounds', 's/x/max'),
        ),
        (
            (
                fixtures.parameter('lo', 5, 'people'),
                fixtures.parameter('hi', 2, 'people'),
                fixtures.stock('x', 3, minimum='lo', maximum='hi'),
            ),
            ('bounds', 's/x'),
        ),
    ],
    ids=['undefined', 'inverted'],
)
def test_a_bound_that_an_expression_gives_is_a_number_no_greater_than_the_maximum(members, diagnostic):
    with pytest.raises(ModelError) as caught:
        fixtures.compiled(fixtures.system(*members, horizon=1))
    assert [(d['code'], d['path']) for d in caught.value.diagnostics] == [diagnostic]


@pytest.mark.parametrize('field', ['n', 'nobody'], ids=['number', 'unknown'])
def test_the_braces_of_a_trigger_doc_name_a_text_field(field):
    text = fixtures.edit(
        fixtures.scenario(),
        fixtures.replace('        "Stop"\n', f'        "{{{field}}} stops the service."\n'),
    )
    with pytest.raises(ModelError) as caught:
        fixtures.compiled(text)
    # The place of the text under the event's line.
    assert [(d['code'], d['path']) for d in caught.value.diagnostics] == [('build', 'service/stop/""')]


def gated_flow(members, condition):
    """A flow of one person an hour from x to y while `condition` holds."""
    return fixtures.system(
        *members,
        fixtures.stock('x', 1),
        fixtures.stock('y'),
        fixtures.flow('go', fixtures.move('x', 'y'), f'1 people/h if ({condition}) else 0 people/h'),
        horizon=1,
    )


def test_a_bool_condition_between_true_and_false_stays_a_condition():
    on = f'input on = true  {fixtures.BASIS}\n    "On"'
    fixtures.compiled(gated_flow([on], 'true if on else false'))


def test_a_bool_field_defined_through_itself_is_rejected_where_it_is_written():
    members = [fixtures.formula('a', 'b', 'bool'), fixtures.formula('b', 'a', 'bool')]
    with pytest.raises(ModelError) as caught:
        fixtures.compiled(gated_flow(members, 'a'))
    assert [(d['code'], d['path']) for d in caught.value.diagnostics] == [('build', 's/b')]


@pytest.mark.parametrize(
    ('steps', 'diagnostic'),
    [
        # A status line with no status.
        pytest.param(
            (fixtures.member('service', 'status when state is "off"\n    "Down"\nstatus ok\n    "Up"'),),
            ('syntax', 'status when state is "off"'),
            id='status_value',
        ),
        pytest.param(
            (fixtures.replace('in 1 people to 100 people  @fixture', 'in 1 people to 100 people  @nowhere'),),
            ('basis', 'service/n'),
            id='named_basis',
        ),
        # The records at the end of an event's line support when it happens.
        pytest.param(
            (fixtures.replace('t >= end:  @fixture', 't >= end:  @nowhere'),),
            ('basis', 'service/stop'),
            id='trigger_basis',
        ),
        pytest.param(
            (
                fixtures.replace(
                    '        "Stop"\n        state = "off"',
                    '        "Stop"\n        done:  @fixture @nowhere\n            state = "off"',
                ),
            ),
            ('basis', 'service/stop/done'),
            id='method_basis',
        ),
        # The file has no start.
        pytest.param(
            (fixtures.replace('t >= end:', 'since(start) >= end:'),),
            ('build', 'service/stop/when:'),
            id='start',
        ),
    ],
)
def test_a_missing_part_is_a_located_diagnostic(steps, diagnostic):
    text = fixtures.edit(fixtures.scenario(), *steps)
    with pytest.raises(ModelError) as caught:
        fixtures.compiled(text)
    assert diagnostic in [where(text, d) for d in caught.value.diagnostics]


def counting(unit):
    """A counter whose rate has the unit `unit`, with a text value `item` of its own, beside a holder
    that has one too."""
    return fixtures.document(
        'Counting',
        fixtures.entity('holder', fixtures.text_value('item', 'people'), doc='Names an item.'),
        fixtures.entity(
            'counter',
            fixtures.text_value('item', 'people'),
            fixtures.parameter('rate', f'1 {unit}', unit, 0, f'2 {unit}', doc='Rate'),
            doc='Counts.',
        ),
        fixtures.output('elapsed_time', 't', 'h', 'level', doc='Elapsed time'),
    )


def test_a_unit_names_a_text_field_of_its_own_entity():
    """The compiler and the runs' table read a unit alike: the entity's own text value is a unit, and
    a model that builds has an admissible default study. A text value of another entity is not."""
    model = fixtures.compiled(counting('{item}/h'))
    assert evaluate_study(model, edits_for(model)).admissible
    with pytest.raises(ModelError) as caught:
        fixtures.compiled(counting('{holder.item}/h'))
    assert [(d['code'], d['path']) for d in caught.value.diagnostics] == [('build', 'counter/rate')]


def with_record(record, value='10 people'):
    """The analytic transfer whose input `n` has the value `value`, supported by `record` alone, a
    record written in place."""
    return fixtures.edit(
        fixtures.scenario(),
        fixtures.replace(
            'input n: people = 10 people in 1 people to 100 people  @fixture',
            f'input n: people = {value} in 1 people to 100 people',
        ),
        fixtures.replace('        "People"\n', '        "People"\n' + fixtures.indent(record, 2) + '\n'),
    )


def test_a_basis_record_with_a_link_that_is_no_record_is_rejected_as_a_whole():
    """A record lists each claim by its ID: a line of its claims that says more is no claim, and the
    reader rejects the file at that line."""
    text = with_record(fixtures.in_place('source', 'Fixture.', 'C-ACTION: reports_value'))
    with pytest.raises(ModelError) as caught:
        fixtures.compiled(text, fixtures.evidence_library())
    assert [where(text, d) for d in caught.value.diagnostics] == [('syntax', 'C-ACTION: reports_value')]


def with_datum(lib, name, figure):
    """`lib` with the figure `name` of the claim C-ACTION."""
    claim = next(c for c in lib['claims'] if c['id'] == 'C-ACTION')
    claim['data'] = {name: figure}
    claim['verification']['content_sha256'] = claim_digest(claim)
    return lib


def test_a_link_names_a_claim_and_at_most_a_datum():
    """A record lists each claim that it rests on, and may name an exact figure of it (`datum:`). The
    library keeps its own links between claims and from assumptions to claims; a record writes no
    relation, and a claim with a relation or a note rejects the file at its line."""
    lib = with_datum(fixtures.evidence_library(), 'people', {'value': 10, 'unit': 'people'})

    def shape(*claims):
        text = with_record(fixtures.in_place('source', 'Fixture.', *claims))
        try:
            fixtures.compiled(text, lib)
        except ModelError as exc:
            return [where(text, d) for d in exc.diagnostics]
        return []

    assert shape('C-ACTION') == []
    assert shape('C-ACTION\n    datum: people') == []
    assert shape('C-ACTION\n    relation: mechanism_support') == [('syntax', 'relation: mechanism_support')]
    assert shape('C-ACTION\n    note: "Context."') == [('syntax', 'note: "Context."')]
    assert shape('datum: people') == [('syntax', 'datum: people')]


def test_each_reference_is_checked_once():
    """The references of the file are read once: an unknown claim of a record of a value (which also
    supports its range) is one diagnostic, at its claim. A value that differs from the datum that it
    reports names its value."""
    unknown = fixtures.in_place('source', 'Fixture.', 'C-TYPO')
    with pytest.raises(ModelError) as caught:
        fixtures.compiled(
            fixtures.edit(fixtures.scenario(), fixtures.member('service/n', unknown)),
            fixtures.evidence_library(),
        )
    # The record is the second of the value's records, after `@fixture`.
    assert [(d['code'], d['path']) for d in caught.value.diagnostics] == [
        ('provenance', 'service/n/1/links/0')
    ]
    lib = with_datum(fixtures.evidence_library(), 'people', {'value': 7, 'unit': 'people'})
    record = fixtures.in_place('source', 'Fixture.', 'C-ACTION\n    datum: people')
    with pytest.raises(ModelError) as caught:
        fixtures.compiled(with_record(record), lib)
    assert [(d['code'], d['path']) for d in caught.value.diagnostics] == [('evidence_value', 'service/n')]
    fixtures.compiled(with_record(record, '7 people'), lib)


def test_an_option_value_is_checked_against_the_datum_that_its_own_basis_reports():
    """A profile's value that reports a datum equals it, whatever the default of its input; a default
    that equals the datum does not admit a profile's value that differs from it."""
    figure = {'value': 12, 'unit': 'people/day'}
    lib = with_datum(fixtures.evidence_library(), 'rate', figure)
    record = fixtures.in_place('source', 'Fixture.', 'C-ACTION\n    datum: rate')

    def text(default, given):
        return fixtures.edit(
            fixtures.scenario(),
            fixtures.replace('input rate: people/day = 24 people/day', f'input rate: people/day = {default}'),
            fixtures.replace(
                f'service.rate = 12 people/day  {fixtures.BASIS}',
                f'service.rate = {given}\n' + fixtures.indent(record, 3),
            ),
        )

    model = fixtures.compiled(text('24 people/day', '12 people/day'), lib)
    # The profile's value is the datum, in the unit of the input, and the default is another value.
    assert model.run_values('b')['service.rate'] == figure['value']
    assert model.run_values('a')['service.rate'] != figure['value']
    with pytest.raises(ModelError) as caught:
        fixtures.compiled(text('12 people/day', '40 people/day'), lib)
    assert [(d['code'], d['path']) for d in caught.value.diagnostics] == [
        ('evidence_value', 'options:/Rate/Half rate/service.rate')
    ]


def gated(rate):
    """The smallest case of an event that waits and is stopped: `go` waits on a gate that stays shut
    (what keeps it going never holds), and a tally grows at `rate`."""
    return fixtures.system(
        fixtures.named('gate', 'shut', 'open'),
        fixtures.named('hit', 'no', 'yes'),
        fixtures.stock('since_go', 0, 'h', minimum=None, size=None, kind='tally', rate=rate),
        fixtures.event(
            'go', 't >= 0 h', 'hit = "yes"', after='1 h', keep='gate is "open"', do_records=fixtures.BASIS
        ),
        horizon=5,
    )


def test_a_stopped_waiting_trigger_stays_while_a_rate_reads_its_events():
    """A rate reads the count of `go`: the event stays, though it ends stopped, when its hour of waiting
    is over, and the tally grows at one hour an hour from t = 0, when the event triggers."""
    source = gated('1 if count(go) > 0 else 0')
    left = fixtures.compiled(source).left_out[()]
    assert 's.go' not in left['rules']
    _, trajectory = fixtures.run(source)
    assert times(trajectory, 's.go') == [0.0]
    assert times(trajectory, 's.go.stopped') == [1.0]
    assert trajectory.env_at(5.0)['s.since_go'] == pytest.approx(5.0)


def test_key_inputs_name_inputs():
    """The inputs that the brief lists (`drivers`) are inputs. The brief settings name them, and the
    pages check each name."""
    model = fixtures.compiled(fixtures.scenario())
    brief = styles.read_brief('drivers = ["service.n", "service.stock"]\n', 'brief.toml')
    problems = styles.check_brief(brief, model)
    assert [(p['code'], p['file'], p['key']) for p in problems] == [('style', 'brief.toml', 'drivers')]
    assert 'service.stock is not an input' in problems[0]['message']
    assert styles.check_brief(styles.read_brief('drivers = ["service.n", "service.rate"]\n'), model) == []


def test_a_profile_of_any_group_can_set_a_start_state():
    """No group of options has a role of its own in the language: a profile of the group that the pages
    show as the responses can set a start state, as a profile of any other group can, and each run that
    takes it starts from it."""
    text = fixtures.edit(
        fixtures.scenario(),
        fixtures.member('options:/Response/Default', f'service.state = "off"  {fixtures.BASIS}'),
    )
    model = fixtures.compiled(text)
    assert model.start_options == ('Default',)
    assert {tuple(run['starts']) for run in model.runs.values()} == {('Default',)}
    assert list(model.structures) == [('Default',)]


def with_role(text, role):
    """`text` with the attacker of the role `role`."""
    return fixtures.edit(text, fixtures.replace('    role adversary\n', f'    role {role}\n'))


def operation(role):
    """sc99 as an operation, with an attacker of the role `role`: the start changes nothing, and the
    attacker's own event, which happens when the start has, makes the first change."""
    strike = fixtures.event(
        'strike',
        'count(start) > 0',
        fixtures.in_place('source_transfer', 'Contract fixture.', 'C-ACTION', 'ATTACK-T0831'),
        'control.state = "compromised"',
        after=0,
        done='Unauthorized commands',
    )
    return fixtures.edit(
        with_role(fixtures.sc99(), role),
        fixtures.member('attacker', strike),
        fixtures.drop('attacker/start/""', 'attacker/start/@/0', 'attacker/start/done/0'),
        fixtures.replace('since(attacker.start) >= end', 'since(compromised) >= end'),
    )


def test_a_start_acts_as_the_entity_that_it_names():
    """A start acts as the thing whose event `start` it is, whether it makes the first change itself
    or an event of the thing makes it, and whatever the thing's role: with no entity of the role
    adversary, it builds."""
    for role in ('adversary', 'operator'):
        for source in (with_role(fixtures.sc99(), role), operation(role)):
            model = fixtures.compiled(source, fixtures.evidence_library())
            (named,) = [
                thing.name
                for thing in front.read(source, 'SC99.scn').things
                if any(isinstance(member, Event) and member.name == 'start' for member in thing.members)
            ]
            assert model.initiation['entity'] == named


def test_the_compiler_reads_no_role():
    """A role tags the cards of the pages, and the compiler gives it no meaning: a file with no
    entity of the role adversary builds, and so do the incident and the operation with two of them. The
    structure keeps each role as its entity's kind, for the pages."""
    sc = fixtures.scenario()
    assert 'role adversary' not in sc
    fixtures.compiled(sc)
    # The control system takes the role adversary too.
    both = fixtures.replace('    role environment\n', '    role adversary\n')
    for source in (fixtures.sc99(), operation('adversary')):
        model = fixtures.compiled(fixtures.edit(source, both), fixtures.evidence_library())
        kinds = {name: entity.kind for name, entity in model.whole[()].entities.items()}
        assert kinds['attacker'] == kinds['control'] == 'adversary'


@pytest.mark.parametrize('word', ['foo', 'other.bar'])
def test_a_call_of_a_word_that_is_no_function_names_the_word_as_the_file_writes_it(word):
    """The grammar reads a word that is no function as a name, and puts a placeholder in its place:
    the error names the word, not the placeholder. A function of the language in the same place is no
    error."""

    def model(call):
        return fixtures.system(
            fixtures.parameter('p', 1, 'h', 0, 5),
            fixtures.formula('f', call, 'h'),
            outputs=[fixtures.output('o', 's.f', 'h')],
        )

    with pytest.raises(ModelError) as raised:
        fixtures.compiled(model(f'{word}(p, 2 h)'))
    messages = [item['message'] for item in raised.value.diagnostics]
    assert any(word in message for message in messages), messages
    assert not any(re.search(r'\b_[0-9]+\b', message) for message in messages), messages
    assert fixtures.compiled(model('max(p, 2 h)')) is not None
