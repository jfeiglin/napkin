"""Publication samples each run of a declared spread using its authored inputs and seed."""

import importlib

from tests.evidence.support import SERVICE, evidence_library, write_package
from tools.publish import Context, sample_spreads


def test_publish_samples_each_declared_run(tmp_path, monkeypatch):
    model = SERVICE.replace(
        '    input end: h = 8 h',
        '    input end_range = uniform(1 h, 2 h) @fixture\n    input end: h = this.end_range.draw()',
    )
    files = {
        'model.scn': model,
        'brief.toml': """[[spread]]
id = "timing"
runs = ["full", "half"]
outputs = ["service.served"]
samples = 3
seed = 17
""",
        'spreads/timing.json': '{"set":{"service.end_range":"uniform(4 h, 5 h)"}}',
    }
    write_package(tmp_path, files, evidence_library())
    sampling = importlib.import_module('napkin.spread')
    spread = sampling.spread
    observed = {}

    def collect(model, paths, **settings):
        result = spread(model, paths, **settings)
        assert paths == ['service.served']
        assert settings['seed'] == 17
        observed[settings['run']] = [sample.values[0][0] for sample in result.samples]
        return result

    monkeypatch.setattr(sampling, 'spread', collect)
    sample_spreads(Context(tmp_path))
    # Each draw uses the edited four-to-five-hour window. The full run serves two people/h.
    assert list(observed) == ['full', 'half']
    for name, rate in [('full', 2), ('half', 1)]:
        assert len(set(observed[name])) == len(observed[name]) == 3
        assert all(4 * rate <= served <= 5 * rate for served in observed[name])
