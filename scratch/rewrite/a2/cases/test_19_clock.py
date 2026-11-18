"""Case 19: the clock at 3, 6 and 9 h; a cooldown: eligible at 3 h, fires at 4 h, next at 7 h."""
from ref import Model, N, add, after, event, set_, start, t, this, trigger, value
from ref.run import Run


def test_clock():
    inspect = event('inspect', triggers=[trigger(t >= 3, [start(this.inspect)], reset=('after', 3))],
                    steps=[after(0, [add(this.inspections, 1)])])
    m = Model()
    m.entity('pump', fields=[value('inspections', 0)], events=[inspect])
    r = Run(m, horizon=10).run()
    assert r.times('fire') == [3, 6, 9]
    assert r.read(N.pump.inspections, 10) == 3


def test_cooldown():
    alarm = event('alarm', triggers=[trigger(this.alarm_on, [start(this.alarm)], reset=('after', 3))])
    weather = event('weather', steps=[after(1, [set_(this.alarm_on, False)]), after(3, [set_(this.alarm_on, True)])])
    m = Model()
    m.entity('pump', fields=[value('alarm_on', True)], events=[alarm, weather])
    m.setup = [start(N.pump.weather)]
    r = Run(m, horizon=11).run()
    # fires at 0; eligible again at 3 while the alarm is off; fires at 4 when it comes on; next eligible at 7
    assert r.times('fire') == [0, 4, 7, 10]
