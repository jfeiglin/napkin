"""Parts of the language that scenarios use, run to their closed forms: numbers in another unit of their
dimension, a yes/no input that gates a trigger and a rate, and several members of one template that a
collection lists, sums and starts an event on, with a move and a write into another entity.

The service of the fixture is down from t = 0 and is repaired at `repair` hours when its yes/no input
lets it; then it serves the waiting users at `k` times the number still waiting, so
`served(t) = users (1 - exp(-k (t - repair)))` after the repair and 0 before. Two queues of 300 and
700 users are members of one template; at 10 h a dispatcher moves a share of each into its handled
store and credits a tenth of the users that the queues hold before the move.

The yes/no type is in `tests/language/test_yes_no.py`; the old outputs, lags, scopes, statuses with
braces, milestones, hidden entities and brief settings went with the old language, its pages and its
outputs (D10), and the reports' lags are in `tests/engine/test_report.py`.
"""

from __future__ import annotations

import math

import pytest

from napkin import SCHEMA_VERSION
from napkin.engine import read, run
from napkin.model.compile import compile_text
from napkin.model.language.problems import LanguageError
from tests.program.examples import UNITS

USERS, K, REPAIR = 1000, 0.05, 10

SERVICE = """\
scenario "Service"
    horizon 120 h

options "Repair":
    "Automatic":
        "Repairs start by themselves."
    "Manual":
        "No one repairs the service."
        service.auto_repair = false  @ident

runs:
    automatic = "Automatic"
    manual = "Manual"

service:
    "A service that serves the users who wait, once it is repaired."
    input auto_repair: bool = true  @ident
        "Repairs start by themselves"
    input repair: h = 10 h
    input users: person = 1000 person
    input k = 0.05
    up: bool = false
    waiting: person = this.users in [0 person,]
    served: person = 0 person in [0 person,]
    flow serve: this.waiting -> this.served
        request = formula(this.k * this.waiting / 1 h if this.up else 0 person/h)
    fix = event():
        when t >= this.repair and this.auto_repair:
            this.fix.start()
            reset when false
        after 0 h:
            this.up = true

record ident: identity "Analytic contract fixture."
"""
TIMES = (5, 20, 45, 120)


def served(t):
    return 0.0 if t <= REPAIR else USERS * (1 - math.exp(-K * (t - REPAIR)))


def run_of(text, run_name=None, edits=None):
    """(the compiled model of `text`, the record of its run `run_name` under the edits `edits`)."""
    model = compile_text(text, UNITS)
    configuration = model.configuration
    if run_name is not None or edits is not None:
        document = edits and {'schema_version': SCHEMA_VERSION, 'model_hash': model.model_hash, **edits}
        configuration = model.configure(run_name, document)
    record = run(model.program, configuration)
    assert record.failure is None, record.failure.detail('message')
    return model, record


# ---- numbers in another unit ---------------------------------------------------------------------


def test_a_number_in_another_unit_of_its_dimension_converts():
    """A cubic metre is 1000 L, so numbers written in m3 configure and run as the same amounts in
    litres do: an input's value, an option's value, a value outside the input's range and a store's
    start and bound. The program keeps each number in the unit that its line writes."""

    def tank(value, low, option, start, high):
        return f"""\
scenario "Reserve"
    horizon 2 h

options "Reserve":
    "Small reserve":
        "The reserve is small."
        tank.reserve = {option}  @ident

runs:
    small = "Small reserve"

tank:
    input reserve: L = {value} in [{low}, 4000 L]
    water: L = {start} in [0 L, {high}]
    flow fill: SOURCE -> this.water
        request = 500 L/h

record ident: identity "Analytic contract fixture."
"""

    units = {**UNITS, 'm3': ({'volume': 1}, 1000)}
    cubic = compile_text(tank('2.5 m3', '0.5 m3', '1.5 m3', '0.25 m3', '1 m3'), units)
    litres = compile_text(tank('2500 L', '500 L', '1500 L', '250 L', '1000 L'), units)
    for run_name in (None, 'small'):
        assert cubic.configure(run_name) == litres.configure(run_name)
    (reserve,) = cubic.configure('small').inputs
    assert (reserve.name, reserve.value.number, reserve.value.unit) == ('reserve', 1500, 'L')
    # The store fills at 500 L an hour from 250 L and is held at 1000 L from 1.5 h.
    found = [
        read(run(model.program, model.configuration), model.program, ['tank.water'], [1, 2])[0].values
        for model in (cubic, litres)
    ]
    assert found == [pytest.approx((750, 1000))] * 2
    edits = {'schema_version': SCHEMA_VERSION, 'model_hash': cubic.model_hash, 'set': {'tank.reserve': 100}}
    with pytest.raises(LanguageError) as raised:
        cubic.configure(edits=edits)
    assert raised.value.codes == ['range']


# ---- a yes/no input ------------------------------------------------------------------------------


def test_a_yes_no_input_gates_a_trigger_and_a_rate():
    model, record = run_of(SERVICE)
    (found,) = read(record, model.program, ['service.served'], list(TIMES))
    assert found.values == pytest.approx([served(t) for t in TIMES], rel=1e-6, abs=1e-6)
    for run_name, edits in (('manual', None), (None, {'set': {'service.auto_repair': False}})):
        model, record = run_of(SERVICE, run_name, edits)
        (found,) = read(record, model.program, ['service.served'], list(TIMES))
        assert found.values == (0, 0, 0, 0)
        assert not [entry for entry in record.trace if entry.kind == 'start' and entry.part == 'service.fix']


def test_a_yes_no_input_takes_true_or_false():
    for value in ('1', '"yes"'):
        with pytest.raises(LanguageError) as raised:
            compile_text(SERVICE.replace('auto_repair: bool = true', f'auto_repair: bool = {value}'), UNITS)
        assert raised.value.codes == ['type']


# ---- members of one template, a collection, a move and a write into another entity -------------

QUEUES = """\
scenario "Queues"
    horizon 20 h

Queue:
    "A queue of users."
    input size: person = 300 person
    pending: person = this.size in [0 person,]
    handled: person = 0 person in [0 person,]
    serve_share = event():
        after 0 h:
            move dispatcher.share * this.pending from this.pending to this.handled

small: Queue

large: Queue
    size = 700 person

dispatcher:
    "Sends a share of the users of each queue to the service."
    queues = <{members}>
    input share = 0.4
    total = formula(sum(this.queues.pending))
    credited: person = 0 person
    dispatch = event():
        when t >= 10 h:
            this.dispatch.start()
            reset when false
        after 0 h:
            this.credited += 0.1 * this.total
            this.queues.serve_share.start()
"""


def test_a_collection_sums_its_members_and_starts_an_event_on_each_one():
    model, record = run_of(QUEUES.format(members='small, large'))
    names = ['dispatcher.total', 'dispatcher.credited', 'small.pending', 'small.handled', 'large.pending']
    total, credited, small, small_handled, large = read(record, model.program, names, [5, 10, 20])
    # 1000 users wait; at 10 h a share of 0.4 of each queue is handled: 600 still wait.
    assert total.values == pytest.approx((1000, 600, 600))
    assert large.values == pytest.approx((700, 420, 420))
    # The members keep their users: what leaves the pending users of a queue is handled.
    assert [p + h for p, h in zip(small.values, small_handled.values)] == pytest.approx([300] * 3)
    # The credit is worked out from the values before the stage's moves: a tenth of 1000 users.
    assert credited.values == pytest.approx((0, 100, 100))
    starts = [entry.part for entry in record.trace if entry.kind == 'start']
    assert starts.count('Queue.serve_share') == 2


def test_a_collection_lists_members_of_one_template():
    text = QUEUES.format(members='small, dispatcher')
    with pytest.raises(LanguageError) as raised:
        compile_text(text, UNITS)
    assert raised.value.codes == ['collection']
