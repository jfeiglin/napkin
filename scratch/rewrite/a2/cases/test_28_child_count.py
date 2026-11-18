"""Case 28: `count(child.occurrences)` is 0 for the rest of the stage and 1 in the parent's next delay."""
from ref import Model, N, after, count, event, set_, start, this, value
from ref.run import Run


def test_child_count():
    parent = event('parent', steps=[after(1, [start(this.child), set_(this.seen, count(this.child.occurrences))]),
                                    after(count(this.child.occurrences) * 2, [])])
    m = Model()
    m.entity('unit', fields=[value('seen', -1)], events=[parent, event('child', steps=[after(5, [])])])
    m.setup = [start(N.unit.parent)]
    r = Run(m, horizon=10).run()
    assert r.read(N.unit.seen, 1) == 0
    assert r.times('done', 'unit.parent#1') == [3]  # the next delay read 1 (1 * 2 h after t = 1)
