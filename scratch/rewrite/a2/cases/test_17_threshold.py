"""Case 17: 11 L at -1 L/h fires `<= 10 L` at 1 h; a strict continuous threshold is refused."""
import pytest

from ref import Diagnostic, Model, SINK, add, after, event, flow, start, this, trigger, value
from ref.run import Run


def build(cond):
    alarm = event('alarm', triggers=[trigger(cond(this.water), [start(this.alarm)], reset=('when', __import__('ref').model.lit(False)))],
                  steps=[after(0, [add(this.alarms, 1)])])
    m = Model()
    m.entity('tank', fields=[value('water', 11, 0, 100), value('alarms', 0)],
             flows=[flow('drain', this.water, SINK, request=1)], events=[alarm])
    return m


def test_fires_at_one_hour():
    r = Run(build(lambda w: w <= 10), horizon=5).run()
    assert r.times('fire') == [1]
    assert r.read(this.water, 1, owner='tank') == 10


def test_strict_threshold_is_refused():
    with pytest.raises(Diagnostic, match='strict threshold'):
        Run(build(lambda w: w < 10), horizon=5).run()
