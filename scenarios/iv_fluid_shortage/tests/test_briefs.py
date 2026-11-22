"""The current cumulative readings page and the original publication have distinct identities."""

from pathlib import Path

import pytest

import napkin
from scenarios.iv_fluid_shortage.tests.clinical_industrial_damage_support import model, record
from tools.publish.brief import brief_of
from tools.publish.readings import display, render


@pytest.fixture(scope='module')
def published():
    return render(model())


def test_checked_page_uses_the_current_program_and_the_two_selected_lot_conditions(published):
    package = Path(__file__).resolve().parents[1]
    assert published == (package / 'results/readings.md').read_text()
    assert published.startswith('# ' + model().declared.scenario.title + '\n')
    assert model().declared.scenario.summary in published
    assert model().declared.scenario.scope in published
    assert model().model_hash in published
    assert '8488047' in (package / 'README.md').read_text()
    brief = brief_of(model())
    assert [line[3:] for line in published.splitlines() if line.startswith('## ')][:2] == list(brief.featured)


def test_every_reported_reading_credits_evidence_and_matches_the_original_order(published):
    m = model()
    brief = brief_of(m)
    ids = [*dict.fromkeys([*brief.featured, *(r.name for r in m.declared.runs)])]
    headings = [line[3:] for line in published.splitlines() if line.startswith('## ')]
    assert headings == [*ids, 'Evidence']
    for run in ids:
        section = published.split(f'## {run}\n')[1].split('\n## ')[0]
        rows = [line.split(' | ') for line in section.splitlines() if line.startswith('| ')][1:]
        times = [0, 1440]
        assert len(rows) == len(brief.show) * len(times)
        r = record(run)
        values = napkin.read(r, m.program, brief.show, times)
        for i, at in enumerate(times):
            for row, v in zip(rows[i * len(values) : (i + 1) * len(values)], values, strict=True):
                path, t, number, unit, evidence = row
                assert (path[2:], t, number, unit) == (v.path, str(at), display(v.values[i]), v.unit)
                assert evidence.removesuffix(' |').strip()
