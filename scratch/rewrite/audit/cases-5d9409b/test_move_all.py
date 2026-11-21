"""Moving the full contents of an occurrence-owned batch must allow it to retire empty."""
from textwrap import dedent

import napkin


def test_move_the_whole_batch_including_its_carried_balance(tmp_path):
    (tmp_path / 'units.json').write_text('{"L":{"dimensions":{"volume":1},"scale":1}}')
    path = tmp_path / 'model.scn'
    path.write_text(dedent("""\
        scenario "Retire a batch"
            horizon 2 h
        plant:
            cash: L = 1 L in [0,]
            bulk: L = 0 L in [0,]
            work = event():
                batch: L = 4000000 L in [0,]
                after 0 h:
                    move (2 L / 3) from this.cash to batch
                after 1 h:
                    move batch from batch to this.bulk
        plant.work.start()
    """))
    model = napkin.load_scenario(path)
    record = napkin.run(model.program, model.configuration)
    assert record.failure is None, record.failure
    batch, done = napkin.read(record, model.program, ['plant.work#0.batch', 'plant.work#0.done'], [1])
    assert batch.values == (0,)
    assert done.values == (True,)
