"""At one moment the events go in the order of their lines: a removal as the jam's wait ends goes
first and stops the jam. Options that set the start value of a stock; options of another group that
set inputs; and a condition names only an outcome that its event has.

They use MODELTEST (tests/model/modeltest.py): the attacker switches a service off at t = 0; after
the repair it jams the switch unless the responders remove it first.
"""

from __future__ import annotations

import re

import pytest

from napkin.core.expr import text as written
from napkin.model import ModelError
from tests.build import block, drop, member, replace
from tests.model.modeltest import build, run, times

# The fixture's tie: the service is repaired at 30 h, the jam waits 20 h, and the responders remove
# the attacker at 50 h, the moment the wait ends.
TIE = {'responders.removal_time': 50, 'service.settle_time': 30, 'attacker.reaction_time': 20}


def test_at_one_moment_the_removal_goes_first_and_stops_the_jam(tmp_path):
    model = build(tmp_path)
    assert (
        model.run_values('slow_kept')['service.repair_time'] + TIE['attacker.reaction_time']
        == (TIE['responders.removal_time'])
    )
    _, trajectory = run(model, 'slow_kept', TIE)
    # The responders' line comes before the attacker's, so the removal goes first: the jam fires as
    # its wait ends, finds the access removed, and is stopped at the removal.
    removal = TIE['responders.removal_time']
    assert times(trajectory, model.events['responders.clean_up.done']) == pytest.approx([removal])
    assert times(trajectory, model.events['attacker.jam_on_repair.stopped']) == pytest.approx([removal])
    assert not times(trajectory, model.events['attacker.jam_on_repair.done'])


# ---- options that set the start value of a stock -------------------------------------------------


WITH_BACKLOG = (
    member(
        'service',
        'var backlog: people = 0  @ident',
        # A flow takes from the backlog, so it is a stock.
        'flow clear: backlog -> at service_rate * backlog  @ident',
    ),
    member('options:/Access/Keeps access', 'service.backlog = users / 4  @access'),
)


def test_an_option_sets_the_start_value_of_a_stock_in_its_runs(tmp_path):
    model = build(tmp_path, *WITH_BACKLOG)
    users = model.run_values('slow')['service.users']
    for name, expected in (('slow', 0), ('slow_kept', users / 4)):
        _, trajectory = run(model, name)
        assert trajectory.env_at(0.0)['service.backlog'] == pytest.approx(expected)
    backlog = model.structure_of('slow_kept').quantities['service.backlog']
    assert backlog.kind == 'stock'
    assert written(backlog.initial) == 'service.users / 4'
    # The option line's own record replaces the var's in the structure of its start states.
    assert backlog.basis['name'] == 'access'


# ---- options of another group that set inputs only -----------------------------------------------


WITH_LOAD = (
    member('service', block('input load: fraction = 1 in 0.5 to 3  @ident', '"Load on the service"')),
    replace(
        'runs:',
        block(
            'options "Load":',
            block('"Usual load":', '"The defaults."'),
            block('"Heavy load":', '"Twice the load."', 'service.load = 2  @ident'),
        )
        + '\n\nruns:',
    ),
    member('runs:', 'slow_heavy = "Slow repair" + "Heavy load"'),
)


def test_an_option_that_sets_an_input_sets_it_in_the_runs_that_name_it(tmp_path):
    model = build(tmp_path, *WITH_LOAD)
    written = model.inputs['service.load']['options']['Heavy load']['value']
    for name, expected in (('slow', model.inputs['service.load']['value']), ('slow_heavy', written)):
        assert model.resolve(name).parameter_values['service.load'] == expected
    # It sets no start state, so the two runs share one structure.
    assert model.runs['slow']['starts'] == model.runs['slow_heavy']['starts'] == ()


# ---- the outcomes that a condition can name --------------------------------------------------------
# The fixture's jam has the outcomes done, skipped and stopped. Without its outcome skipped it jams
# while the attacker keeps its access, and is stopped otherwise.


def without_skipped():
    """The jam with no outcome skipped."""
    return (
        replace('done access is "kept" and service.status is "back":', 'done access is "kept":'),
        drop('attacker/jam_on_repair/skipped'),
    )


def with_reader_of(ending):
    """An event of the responders that reads one outcome of the jam. It runs their removal, which is
    now an event that both of their events name."""
    return (
        replace('        attacker.access = "removed"', '        remove'),
        member(
            'responders',
            block(
                f'event notice once when count(attacker.jam_on_repair.{ending}) > 0:  @ident',
                '"Responders notice the jam."',
                'remove',
            ),
            block('event remove:  @ident', 'attacker.access = "removed"'),
        ),
    )


def test_only_an_ending_that_the_method_can_have_is_named(tmp_path):
    build(tmp_path, *with_reader_of('skipped'))
    with pytest.raises(ModelError, match=re.escape('attacker.jam_on_repair has no outcome skipped')):
        build(tmp_path, *without_skipped(), *with_reader_of('skipped'))
