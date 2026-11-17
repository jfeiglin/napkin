"""A template's name is the list of its instances (docs/language.md, §2.3): a model that reads its
lists through a template's name builds the structure of the same lists written out, and runs the
same, bit for bit. A template with no instances, or a slot bound to `[]`, gives an empty list, whose
names are still checked."""

import pytest

from napkin.engine.runtime import simulate
from napkin.model import ModelError
from napkin.model.ir import thaw
from tests.build import compiled
from tests.model.test_modules import plain_structures, stripped

HEAD = """scenario "Tanks"
    summary "Tanks. A synthetic fixture for tests only."
    horizon 12 h
    scope "Fixture"
"""

TANK = """Tank:  @fixture
    "A tank that takes water from the pool."
    role environment
    input ask: people/h = 1 people/h in 0 people/h to 10 people/h  @fixture
        "Ask"
    var got: people = 0 people size 100 people  @fixture
        "Taken"
    var bumps: people = 0 people size 100 people  @fixture
        "Bumps"
    flow take: pool.water -> got at ask  @fixture
    event bump:
        "The tank is bumped."
        bumps += 1 people
"""

REST = """
options "Response":
    "Default":
        "The defaults."

runs:
    a = "Default"

record fixture: identity "Analytic contract fixture."
"""


def tanks(tanks, order, terms):
    """A model whose pool shares its water among tanks: `tanks` is how its link names them, `order`
    how its share serves them, and `terms` how its sum check adds what they took."""
    return f"""{HEAD}
{TANK}
pool:  @fixture
    "The pool that the tanks share."
    role environment
    let tanks = {tanks}
    input start_water: people = 20 people in 1 people to 100 people  @fixture
        "Water at the start"
    var water: people = start_water size 100 people  @fixture
        "Water"
    let asked: people/h = sum(tanks.ask)  @fixture
    share water limit 2 people/h order {order}  @fixture
    event stop once when t >= 1 h:  @fixture
        "The pool bumps the tanks."
        Tank.bump

a1: Tank  @fixture
    ask = 1 people/h  @fixture

a2: Tank  @fixture
    ask = 2 people/h  @fixture

assert pool.water + {terms} is pool.start_water within 0.001 people  @fixture
    "Water is in the pool or taken."

output total: people = sum(Tank.got)  @fixture
    "Water taken"
    level
{REST}"""


def run(model):
    trajectory = simulate(model.resolve('a'), thaw(model.library), None)
    end = trajectory.env_at(trajectory.horizon)
    return [(e['t'], e['event']) for e in trajectory.trace], {k: repr(v) for k, v in end.items()}


def test_a_template_s_name_builds_and_runs_as_its_instances_written_out():
    by_name = compiled(tanks('Tank', 'Tank.take', 'Tank.got'))
    written = compiled(
        tanks('[a1, a2]', 'a1.take, a2.take', 'a1.got + a2.got').replace(
            '        Tank.bump', '        tanks.bump'
        )
    )
    assert stripped(plain_structures(by_name)) == stripped(plain_structures(written))
    trace, end = run(by_name)
    assert (trace, end) == run(written)
    # Each instance's event fires, in the order of the instances.
    assert [event for t, event in trace if event.endswith('bump.done')] == ['a1.bump.done', 'a2.bump.done']


EMPTY = f"""{HEAD}
{TANK.replace('pool.water -> got', '-> got')}
Holder:  @fixture
    "A holder of tanks."
    role environment
    let tanks: [Tank]
    let held: people = sum(tanks.got)  @fixture
    event ping once when t >= 1 h:  @fixture
        "The holder bumps its tanks."
        tanks.bump
        Tank.bump

holder: Holder  @fixture
    let tanks = []

output total: people = sum(Tank.got)  @fixture
    "Water taken"
    level

output held: people = holder.held  @fixture
    "Water that the holder's tanks took"
    level
{REST}"""


def test_a_template_with_no_instances_gives_empty_lists():
    model = compiled(EMPTY)
    trace, _ = run(model)
    assert [event for t, event in trace] == ['holder.ping.done']
    assert model.scenario.templates == ('Tank', 'Holder')


@pytest.mark.parametrize(
    ('old', 'new', 'misspelt'),
    [
        ('sum(Tank.got)  @', 'sum(Tank.gott)  @', 'gott'),
        ('sum(tanks.got)', 'sum(tanks.gott)', 'gott'),
        ('        Tank.bump\n', '        Tank.bumpp\n', 'bumpp'),
        (
            '    "Default":\n        "The defaults."\n',
            '    "Default":\n        "The defaults."\n        Tank.askk = 1 people/h  @fixture\n',
            'askk',
        ),
    ],
)
def test_an_empty_list_still_checks_its_names(old, new, misspelt):
    assert EMPTY.count(old) == 1
    with pytest.raises(ModelError) as raised:
        compiled(EMPTY.replace(old, new))
    assert any(misspelt in item['message'] for item in raised.value.diagnostics), raised.value.diagnostics


def test_an_empty_list_takes_its_type_from_a_slot():
    text = EMPTY.replace(
        'holder: Holder  @fixture\n    let tanks = []\n',
        'holder: Holder  @fixture\n    let tanks = []\n\nloose:  @fixture\n    "A thing with no slot."\n    role environment\n    let things = []\n',
    )
    with pytest.raises(ModelError, match='takes the type of its slot'):
        compiled(text)
