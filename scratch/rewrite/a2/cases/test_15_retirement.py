"""Case 15: the retirement rule. 20 L in, 12 L out: the run fails and names the 8 L."""
import pytest

from ref import Model, N, RunFailed, SINK, SOURCE, after, event, flow, formula, set_, start, value
from ref.model import Config, Rules
from ref.run import Run


def build():
    batch = event('batch', locals=[value('stock', 0, 0, 100), value('fill', 20), value('out', 0)],
                  flows=[flow('in_', SOURCE, N.stock, request=formula(N.fill)), flow('deliver', N.stock, SINK, request=formula(N.out))],
                  steps=[after(1, [set_(N.fill, 0), set_(N.out, 12)]), after(1, [set_(N.out, 0)])])
    m = Model()
    m.entity('plant', events=[batch])
    m.setup = [start(N.plant.batch)]
    return m


def test_retirement_fails_and_names_8_l():
    r = Run(build(), horizon=5)
    with pytest.raises(RunFailed, match=r'plant\.batch#1\.stock still holds 8') as e:
        r.run()
    assert 't = 2 h' in str(e.value)


def test_alternative_disposes():
    r = Run(build(), Config(horizon=5, rules=Rules(retirement='dispose'))).run()
    assert ('disposed', 2) == r.ledger[-1][:2] and r.ledger[-1][3] == 8
    assert r.conservation()['balanced']
