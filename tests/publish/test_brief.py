"""A scenario's brief settings (`brief.toml`): their keys, their defaults and the checks that name the
file and the key. The model and its runs never read the brief settings or the stylesheet
(`style.toml`, the picture), and the pages never read the stylesheet.

The model of the test writes its own outputs, inputs, profiles, runs and things, and each expectation
follows from them and from the rule of the reader that it names.
"""

from __future__ import annotations

import json

import pytest

from napkin.draw import style
from napkin.draw.style import StyleError
from napkin.engine import edits_for, evaluate_study
from napkin.model.model import build_model
from tests.acceptance.helpers import LIBRARY
from tools.publish import brief as settings
from tools.publish import runs
from tools.publish.pages import pages

MODEL = """\
scenario "A test"
    summary "A file for tests only."
    horizon 10 h
    scope "The test."

north:  @counts
    "A district."
    role community
    input x = 2 h in 1 h to 5 h  @counts
        "X"
    var people: people = 10 people  @counts
        "People"
    output people

Ward:  @counts
    "A ward."
    role community
    input y = 1 h in 0 h to 3 h  @counts
        "Y"

Depot:  @counts
    "A template that no thing is made of."
    role operator

east: Ward

west: Ward

attacker:  @counts
    "An attacker."
    role adversary
    var access: "none" | "kept" = "none"
    event enters once when access is "kept":  @counts
        "The attacker gets in."
    event start when t >= 0 h:  @counts
        "The attacker gets in."
        access = "kept"

output total: people = north.people  @counts
    "Total"

options "Response":
    "Fast":
        "Fast."
        west.y = 2 h  @counts
    "Slow":
        "Slow."
        north.x = 4 h  @counts

options "Attacker":
    "AI":
        "AI."
    "Human":
        "Human."
        east.y = 3 h  @counts

runs:
    fast = "Fast" + "AI"
    slow = "Slow" + "AI"
    slow_human = "Slow" + "Human" versus slow
        "The slow response against a human team"

record counts: identity "The test counts."
"""

BRIEF = """\
# What the pages show first.
show = ["total", "north.people"]
drivers = ["east.y", "north.x"]
featured = ["slow", "slow_human"]
"""

STYLE = """\
# The picture of the map.
[layout]
hide = ["Ward"]

[icon]
house = ["north"]
"""

# Two rows of the run table, the second with its values in a table of their own.
SWEEPS = """\

[[sweep]]
id = "late"
description = "The slow response comes later"
run = "slow"
set = {"north.x" = 5, "east.y" = 0.5}

[[sweep]]
id = "early"
description = "The fast response comes earlier"
run = "fast"
[sweep.set]
"north.x" = 1.0
"""
# One valid sweep, which each case of a problem changes in one place.
SWEEP = '[[sweep]]\nid = "late"\ndescription = "Later"\nrun = "slow"\nset = {"north.x" = 5}\n'


def built(tmp_path, brief=None, picture=None):
    """The model of MODEL, with its brief settings and its stylesheet beside it when they are given."""
    (tmp_path / 'model.scn').write_text(MODEL, encoding='utf-8')
    for name, text in ((settings.BRIEF_FILE, brief), (style.STYLE_FILE, picture)):
        if text is not None:
            (tmp_path / name).write_text(text, encoding='utf-8')
    return build_model(tmp_path / 'model.scn', LIBRARY)


def test_without_the_file_each_key_takes_its_default(tmp_path):
    model = built(tmp_path)
    brief = settings.brief_of(model)
    assert brief == settings.Brief()
    # Every output, in the order of the model file: the outputs of the entities, then the top level.
    assert settings.shown(brief, model) == ['north.people', 'total']
    # The inputs that the profiles set, in menu order: Fast, then Slow, then AI and Human.
    assert settings.controls(model) == ['west.y', 'north.x', 'east.y']
    assert settings.drivers(brief, model) == settings.controls(model)
    assert settings.featured(brief, model) == ['fast']


def test_the_keys_give_what_the_pages_show(tmp_path):
    model = built(tmp_path, BRIEF, STYLE)
    brief = settings.brief_of(model)
    assert settings.shown(brief, model) == ['total', 'north.people']
    assert settings.drivers(brief, model) == ['east.y', 'north.x']
    assert settings.featured(brief, model) == ['slow', 'slow_human']


def test_a_file_of_comments_only_gives_the_defaults():
    assert settings.read_brief('# Nothing yet.\n', 'brief.toml') == settings.Brief(origin='brief.toml')


def test_each_sweep_is_one_run_with_the_values_of_its_inputs_as_the_file_writes_them(tmp_path):
    """The sweeps keep the order of the file, and so do the values of each; a value keeps its type,
    a whole number or a number with a point, as an edit document holds it."""
    model = built(tmp_path, BRIEF + SWEEPS)
    sweeps = settings.brief_of(model).sweeps
    assert [(sweep.id, sweep.run) for sweep in sweeps] == [('late', 'slow'), ('early', 'fast')]
    assert all(sweep.description for sweep in sweeps)
    assert [list(sweep.edits) for sweep in sweeps] == [['set'], ['set']]
    assert [
        [(name, type(value), value) for name, value in sweep.edits['set'].items()] for sweep in sweeps
    ] == [
        [('north.x', int, 5), ('east.y', float, 0.5)],
        [('north.x', float, 1.0)],
    ]
    # Without sweeps, the scenario has none.
    assert settings.read_brief(BRIEF, 'brief.toml').sweeps == ()


@pytest.mark.parametrize(
    ('text', 'key', 'match'),
    [
        ('sweep = 1\n', 'sweep', 'holds tables'),
        ('[sweep]\nid = "late"\n', 'sweep', 'holds tables'),
        (SWEEP + 'edits = {}\n', 'sweep[0].edits', 'not a key'),
        (SWEEP.replace('id = "late"\n', ''), 'sweep[0].id', 'lowercase letters'),
        (SWEEP.replace('"late"', '"Late one"'), 'sweep[0].id', 'lowercase letters'),
        (SWEEP + SWEEP, 'sweep[1].id', 'entry above'),
        (SWEEP.replace('description = "Later"\n', ''), 'sweep[0].description', 'nonempty text'),
        (SWEEP.replace('"Later"', '" "'), 'sweep[0].description', 'nonempty text'),
        (SWEEP.replace('run = "slow"\n', ''), 'sweep[0].run', 'nonempty text'),
        (SWEEP.replace('set = {"north.x" = 5}\n', ''), 'sweep[0].set', 'table of inputs'),
        (SWEEP.replace('{"north.x" = 5}', '{}'), 'sweep[0].set', 'table of inputs'),
        # An input's name is one key, in quotes: without them, TOML reads a table of tables.
        (SWEEP.replace('"north.x"', 'north.x'), 'sweep[0].set', 'in quotes'),
        (SWEEP.replace('= 5}', '= "5 h"}'), 'sweep[0].set', 'finite number'),
        (SWEEP.replace('= 5}', '= inf}'), 'sweep[0].set', 'finite number'),
        (SWEEP.replace('= 5}', '= [5]}'), 'sweep[0].set', 'finite number'),
    ],
)
def test_a_sweep_has_an_id_a_description_a_run_and_the_values_of_its_inputs(text, key, match):
    with pytest.raises(StyleError, match=match) as caught:
        settings.read_brief(text, 'brief.toml')
    assert [(d['file'], d['key'], d.get('line')) for d in caught.value.diagnostics] == [
        ('brief.toml', key, None)
    ]


@pytest.mark.parametrize(
    ('text', 'key', 'line', 'match'),
    [
        # The brief settings have no `controls`, and `hidden` is the stylesheet's `[layout] hide`.
        ('controls = ["north.x"]\n', 'controls', None, 'not a key'),
        ('hidden = ["Ward"]\n', 'hidden', None, 'not a key'),
        ('show = "total"\n', 'show', None, 'list of names'),
        ('show = [""]\n', 'show', None, 'list of names'),
        ('[show]\ntotal = true\n', 'show', None, 'list of names'),
        ('show = ["total", "total"]\n', 'show', None, 'twice'),
        ('featured = []\n', 'featured', None, 'one run, or a run and its comparison'),
        (
            'featured = ["fast", "slow", "slow_human"]\n',
            'featured',
            None,
            'one run, or a run and its comparison',
        ),
        # A name is a text in quotes.
        ('show = [total]\n', None, 1, 'not TOML'),
    ],
)
def test_brief_settings_have_their_keys_each_a_list_of_names(text, key, line, match):
    with pytest.raises(StyleError, match=match) as caught:
        settings.read_brief(text, 'brief.toml')
    assert [(d['file'], d['key'], d.get('line')) for d in caught.value.diagnostics] == [
        ('brief.toml', key, line)
    ]


@pytest.mark.parametrize(
    ('text', 'key', 'match'),
    [
        ('show = ["north.x"]\n', 'show', 'not an output'),
        ('drivers = ["attacker.access"]\n', 'drivers', 'not an input'),
        ('show = ["total"]\ndrivers = ["north.people"]\n', 'drivers', 'not an input'),
        ('featured = ["nowhere"]\n', 'featured', 'not a run'),
        # slow does not say `versus fast`.
        ('featured = ["fast", "slow"]\n', 'featured', 'versus'),
        (SWEEP.replace('run = "slow"', 'run = "nowhere"'), 'sweep[0].run', 'not a run'),
        # A variable is no input.
        (SWEEP.replace('"north.x"', '"north.people"'), 'sweep[0].set', 'not an input'),
        # The run table names each row once: a run's row by the run's name, a sweep's by its id.
        (SWEEP.replace('"late"', '"fast"'), 'sweep[0].id', 'name of a run'),
    ],
)
def test_the_brief_settings_name_what_their_model_declares(tmp_path, text, key, match):
    model = built(tmp_path, brief=text)
    with pytest.raises(StyleError, match=match) as caught:
        settings.brief_of(model)
    assert [(d['file'], d['key']) for d in caught.value.diagnostics] == [
        (str(tmp_path / settings.BRIEF_FILE), key)
    ]


def test_the_model_and_its_runs_never_read_the_files_and_the_pages_never_read_the_stylesheet(tmp_path):
    names = ('absent', 'present', 'broken', 'pictured')
    for name in names:
        (tmp_path / name).mkdir()
    absent, present, broken, pictured = (
        built(tmp_path / 'absent'),
        built(tmp_path / 'present', BRIEF + SWEEPS, STYLE),
        built(tmp_path / 'broken', 'show = ["nothing"]\n', '[icon]\nhouse = ["nowhere"]\n'),
        # A broken stylesheet beside brief settings that the model accepts.
        built(tmp_path / 'pictured', BRIEF, '[icon]\nhouse = ["nowhere"]\n'),
    )
    assert absent.model_hash == present.model_hash == broken.model_hash == pictured.model_hash
    with pytest.raises(StyleError):
        settings.brief_of(broken)
    with pytest.raises(StyleError):
        style.of(broken)
    with pytest.raises(StyleError):
        pages(broken)
    # The pages read only the brief settings: a broken stylesheet stops the map, not the pages.
    with pytest.raises(StyleError):
        style.of(pictured)
    assert pages(pictured) == pages(present)
    # Broken files stop the pages, never a study.
    study = evaluate_study(broken)
    assert study.admissible and set(study.runs) == set(broken.runs)


# ---- the brief settings of a variant (D-22) -------------------------------------------------------

# The package's brief settings, with a sweep and a spread, and one variant's own, with neither.
SPREAD = '\n[[spread]]\nid = "wide"\nruns = ["slow"]\nsamples = 4\nseed = 1\n'
PACKAGE_BRIEF = BRIEF + SWEEP + SPREAD
OWN_BRIEF = 'featured = ["fast"]\n'


def family(tmp_path, package=PACKAGE_BRIEF, own=OWN_BRIEF):
    """{variant: (its entry file, its model)} of a package whose main file is MODEL, with the brief
    settings `package` in its folder, and two variants that change nothing: `plain`, with no brief
    settings of its own, and `briefed`, with `own` in its folder."""
    folder = tmp_path / 'family'
    folder.mkdir(parents=True)
    (folder / 'model.scn').write_text(MODEL, encoding='utf-8')
    if package is not None:
        (folder / settings.BRIEF_FILE).write_text(package, encoding='utf-8')
    found = {}
    for name, text in (('plain', None), ('briefed', own)):
        entry = folder / 'variants' / name / 'model.scn'
        entry.parent.mkdir(parents=True)
        entry.write_text('variant "A place"\n', encoding='utf-8')
        if text is not None:
            entry.with_name(settings.BRIEF_FILE).write_text(text, encoding='utf-8')
        found[name] = (entry, build_model(entry, LIBRARY))
    return found


def document(folder, model):
    """Write the edit document of the spread `wide` in the folder `spreads/` of `folder`; its path."""
    path = folder / 'spreads' / 'wide.json'
    path.parent.mkdir()
    path.write_text(json.dumps(edits_for(model)), encoding='utf-8')
    return path


def test_a_variant_without_brief_settings_takes_its_package_s_with_its_sweeps_and_spreads(tmp_path):
    (entry, model) = family(tmp_path)['plain']
    package = tmp_path / 'family' / settings.BRIEF_FILE
    document(package.parent, model)
    brief = settings.brief_of(model)
    assert brief.origin == str(package) and settings.featured(brief, model) == ['slow', 'slow_human']
    assert [sweep.id for sweep in brief.sweeps] == ['late'] and [s.id for s in brief.spreads] == ['wide']
    assert settings.brief_file(entry) == package and runs.declares_sweeps(entry)
    # The edit document of the package's spread is beside the package's brief settings.
    (spread,) = brief.spreads
    assert settings.spread_document(model, spread) == package.with_name('spreads') / 'wide.json'


def test_a_variant_s_own_brief_settings_replace_its_package_s_whole(tmp_path):
    """Nothing of the package's file merges into the variant's own: each key that the variant's file
    does not give takes its default, and the package's sweeps and spreads are not the variant's."""
    (entry, model) = family(tmp_path)['briefed']
    brief = settings.brief_of(model)
    assert brief == settings.read_brief(OWN_BRIEF, str(entry.with_name(settings.BRIEF_FILE)))
    assert settings.featured(brief, model) == ['fast'] and settings.shown(brief, model) == list(model.outputs)
    assert brief.sweeps == brief.spreads == () and not runs.declares_sweeps(entry)


def test_a_variant_s_spread_document_is_beside_its_own_brief_settings(tmp_path):
    """A variant whose own brief settings declare the package's spread needs the edit document beside
    its own file: the package's document is no document of the variant's."""
    # Only the package has the document: the variant's spread has none.
    (entry, model) = family(tmp_path / 'one', own=SPREAD)['briefed']
    document(tmp_path / 'one' / 'family', model)
    with pytest.raises(StyleError, match=r'spreads/wide\.json') as caught:
        settings.brief_of(model)
    assert [(d['file'], d['key']) for d in caught.value.diagnostics] == [
        (str(entry.with_name(settings.BRIEF_FILE)), 'spread[0].id')
    ]
    # The variant's own document beside its own file.
    (entry, model) = family(tmp_path / 'two', own=SPREAD)['briefed']
    document(tmp_path / 'two' / 'family', model)
    own = document(entry.parent, model)
    (spread,) = settings.brief_of(model).spreads
    assert settings.spread_document(model, spread) == own


def test_the_cache_names_the_brief_settings_that_each_model_read(tmp_path):
    """The two variants are one model hash; each reads its own file, and a problem in the package's file
    stops only the variant that reads it."""
    found = family(tmp_path, package='show = ["nothing"]\n')
    (_, plain), (_, briefed) = found['plain'], found['briefed']
    assert plain.model_hash == briefed.model_hash
    with pytest.raises(StyleError) as caught:
        settings.brief_of(plain)
    assert {d['file'] for d in caught.value.diagnostics} == {str(tmp_path / 'family' / settings.BRIEF_FILE)}
    assert settings.featured(settings.brief_of(briefed), briefed) == ['fast']
