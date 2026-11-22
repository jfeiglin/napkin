"""Reproducibility and centering of workforce planning uncertainty."""

import pytest

from napkin.engine import SamplingSettings, edits_for, monte_carlo


def test_staffing_reserve_is_centered_and_reproducible(workforce_model):
    enabled = edits_for(workforce_model, {'set': {'uncertainty.enabled': True}})
    config = workforce_model.configure('no_ai', edits=enabled)
    path = 'uncertainty.reserve_weight'
    settings = SamplingSettings(samples=4, seed=7)

    def sampled():
        return monte_carlo(
            workforce_model.program,
            config,
            [path],
            [0, config.request.horizon],
            settings,
            model=workforce_model.table,
        )

    first = sampled()
    assert first.refused is None, first.refused
    assert first == sampled()
    assert len(first.samples) == settings.samples
    assert first.spread(path, 0).summary.central == pytest.approx(0.1)
    values = []
    for sample in first.samples:
        start, end = sample.values[0]
        assert 0.05 <= start <= 0.15 and start == end
        values.append(start)
    assert len(set(values)) > 1
