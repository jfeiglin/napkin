"""Case 14: `inspect` started with 3 h: stages at 3 h and 5 h; the guard is read once, when the stage is due."""
from ref import Model, N, after, event, set_, start, t, this, until, value
from ref.run import Run


def build(safe_at_five):
    weather = [after(4, [set_(this.safe, False)]),  # a temporary loss of safety before the due time
               after(F_half, [set_(this.safe, safe_at_five)]),  # t = 4.5
               after(1, [set_(this.safe, True)]),  # t = 5.5: too late, the guard was read at 5
               after(F_half, [set_(this.clearance_received, True)])]  # t = 6
    inspect = event('inspect', params=['delay'], steps=[
        after(N.delay, [set_(N.delay, 2)]),
        after(N.delay, [start(this.inspect_equipment)], when=this.safe),
        until(this.clearance_received),
        after(0, [start(this.record_clearance)])])
    m = Model()
    m.entity('site', fields=[value('safe', True), value('clearance_received', False)],
             events=[inspect, event('inspect_equipment'), event('record_clearance'), event('weather', steps=weather)])
    m.setup = [start(N.site.inspect, 3), start(N.site.weather)]
    return m


from fractions import Fraction  # noqa: E402

F_half = Fraction(1, 2)


def test_stages_at_three_and_five():
    r = Run(build(True), horizon=8).run()
    stages = [(e[1], e[3]) for e in r.trace if e[0] == 'stage' and e[2] == 'site.inspect#1']
    assert stages == [(3, 0), (5, 1), (6, 3)]
    assert r.times('start', 'site.inspect_equipment#1') == [5]
    assert r.times('start', 'site.record_clearance#1') == [6]
    assert r.times('done', 'site.inspect#1') == [6]


def test_guard_read_once():
    r = Run(build(False), horizon=8).run()
    assert r.times('start', 'site.inspect_equipment#1') == []  # false at 5: skipped, though true again at 5.5
    assert r.times('done', 'site.inspect#1') == [6]  # done is recorded although the guard skipped the action
    assert r.read(N.site.inspect.occurrences.at(t).done, 8) is True
