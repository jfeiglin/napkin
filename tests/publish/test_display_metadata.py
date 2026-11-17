"""Display-only parts change what the pages show, never the calculation.

The pages give one input group for each entity, the brief settings name the inputs that the brief
lists (`drivers`), and the stylesheet gives the icons of the map (`[icon]`). The calculation and the
model's identity never read either file.
"""

import json

from napkin.draw import style
from napkin.engine.report import evaluate_outputs
from napkin.engine.runtime import simulate
from napkin.model.model import build_model
from tests.build import library, scenario
from tools.publish import brief as settings

TIMES = [0, 6, 12, 24]

# Key inputs of the fixture's own, in an order that is not the entity's.
DRIVERS = ['service.end', 'service.n']


def built(folder, lib, files=None):
    """The analytic fixture, built from its file, with the files `files` ({name: text}) beside it."""
    folder.mkdir()
    path = folder / 'model.scn'
    path.write_text(scenario(), encoding='utf-8')
    for name, text in (files or {}).items():
        (folder / name).write_text(text, encoding='utf-8')
    return build_model(path, lib)


def results(model, run, lib):
    """The trace of one run and its outputs at the sample times and at the end of the run."""
    rs = model.resolve(run)
    trajectory = simulate(rs, lib)
    times = sorted({*TIMES, trajectory.horizon})
    return trajectory.trace, evaluate_outputs({'resolved': rs, 'trajectory': trajectory}, lib, times)


def test_the_brief_settings_and_the_stylesheet_change_only_what_the_pages_show(tmp_path):
    """The key inputs are a setting of the brief, and an icon a key of the stylesheet: the pages show
    them, and the model's identity leaves them out."""
    lib = library()
    brief, picture = f'drivers = {json.dumps(DRIVERS)}\n', '[icon]\nfactory = ["service"]\n'
    plain = built(tmp_path / 'plain', lib)
    styled = built(tmp_path / 'styled', lib, {'brief.toml': brief, 'style.toml': picture})
    drivers = [settings.drivers(settings.brief_of(model), model) for model in (plain, styled)]
    assert drivers[1] == DRIVERS != drivers[0]
    icons = [style.icon_of(style.of(model), model)['service'] for model in (plain, styled)]
    assert icons[1] == 'factory' != icons[0]
    assert plain.model_hash == styled.model_hash
    assert list(plain.runs) == list(styled.runs)
    for run in plain.runs:
        assert results(plain, run, lib) == results(styled, run, lib)
