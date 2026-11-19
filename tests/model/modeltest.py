"""MODELTEST, the model file that the tests of the language build, with closed forms.

The fixture is a small synthetic model. An attacker switches a service off at t = 0. The service is
repaired `repair_time` after it goes down, and settles `settle_time` after that. While the service is
up, waiting users are served at `service_rate` times the number still waiting. When the repair is
done, the attacker starts to jam the switch: an event that fires `reaction_time` later and changes
the switch if the attacker still keeps its access and the service has not settled (`done`), else it
is skipped or stopped. Responders remove the attacker `removal_time` after the first move; their line
comes before the attacker's, so at one moment the removal goes first. Its brief settings show the
users served and feature the run `slow_kept`.

`build` writes the file, with the steps of a test's edit (`tests.build.edit`), its brief settings
and its stylesheet, and builds it with `LIB`.
"""

from __future__ import annotations

import copy

import pytest

from napkin.engine.runtime import simulate
from napkin.model import ModelError
from napkin.model.evidence import claim_digest
from napkin.model.language import front
from napkin.model.model import build_model
from napkin.model.semantic import path_text
from tests.acceptance.helpers import LIBRARY
from tests.build import edit

FIXTURE = """\
scenario "Reader test"
    summary "A synthetic attacker switches a service off and jams its repair. A fixture for tests only."
    horizon 200 h
    scope "Synthetic users."

switch:  @ident @access
    "The switch that feeds the service."
    var position: "on" | "off" | "jammed" = "on"

service:  @ident
    "A service with users."
    let users = 1000 people  @ident
        "Users"
    let service_rate = 0.05 per_h  @ident
        "Share of waiting users served each hour"
    input repair_time = 30 h in 1 h to 90 h  @ident
        "Time to repair"
    input settle_time = 20 h in 1 h to 90 h  @ident
        "Time to settle after the repair"
    var status: "running" | "down" | "back" | "settled" = "running"
    var waiting: people = users  @ident
        "Users waiting"
    var served: people = 0  @ident
        "Users served"
    output served
        level
    status failed when status is "down"
        "Down"
    status ok
        "Running"
    event fails when status is "running" and switch.position is "off":  @ident
        "The service fails."
        status = "down"
    event repaired when status is "down" and elapsed(status) >= repair_time:  @ident
        "The service is repaired."
        status = "back"
    event settles when status is "back" and elapsed(status) >= settle_time:  @ident
        "The service settles."
        status = "settled"
    flow serve: waiting -> served at service_rate * waiting while status is not "down"  @ident
        "Waiting users are served."
    assert waiting + served is users within 0.001 people  @ident
        "Every user waits or is served."

responders:  @ident
    "Responders who remove the attacker."
    input removal_time = 60 h in 1 h to 150 h  @ident
        "Time to remove the attacker"
    event clean_up once when attacker.access is "kept" and since(attacker.start) >= removal_time:  @ident
        "Responders remove the attacker."
        attacker.access = "removed"

attacker:  @attack
    "A synthetic attacker. It switches the service off and then jams its repair."
    input actor = "The AI"
    var access: "none" | "kept" | "removed" = "none"
    input reaction_time = 10 h in 0.5 h to 80 h  @ident
        "Time to react"
    event jam_on_repair once after reaction_time when count(service.repaired) > 0 and access is "kept":
        @ident
        done access is "kept" and service.status is "back":  @ident
            switch.position = "jammed"
        skipped access is "kept" and not (service.status is "back"):
        stopped else:
    event start when t >= 0 h:  @access @attack
        switch.position = "off"

options "Response":
    "Slow repair":
        "The defaults."
    "Fast repair":
        "Repairs take 10 hours."
        service.repair_time = 10 h  @ident

options "Access":
    "No access":
        "The attacker strikes once."
    "Keeps access":
        "The attacker keeps its access."
        attacker.access = "kept"  @ident

runs:
    slow = "Slow repair"
    fast = "Fast repair"
    slow_kept = "Slow repair" + "Keeps access"

notes:
    premises:
        START: "The attacker holds access at the start."  @ident

record ident: identity "Synthetic test fixture."
record attack: source_transfer "Synthetic first move."
    claims:
        ATTACK-T9901
record access: assumption T_JOB "Synthetic access at the start."
"""

BRIEF = """\
show = ["service.served"]
featured = ["slow_kept"]
choice_group = "Response"
"""


def library():
    out = copy.deepcopy(LIBRARY)
    claim = copy.deepcopy(next(c for c in out['claims'] if c['id'] == 'T_DATUM'))
    claim.update(
        id='ATTACK-T9901', shows='MITRE ATT&CK for ICS technique T9901 Synthetic Command (fixture only).'
    )
    claim['verification']['content_sha256'] = claim_digest(claim)
    out['claims'].append(claim)
    return out


LIB = library()


# Who plays each part: the scenario's wrapper's, beside the model (PLAN, change 23), and no line of the
# model's.
ROLES = """\
[entities]
switch = "operator"
service = "operator"
responders = "responder"
attacker = "adversary"
"""


def write(tmp_path, *steps, text=FIXTURE, brief=BRIEF, style=None, roles=ROLES):
    """The path of the file `text` with the steps of an edit, written with its brief settings
    (`brief.toml`), its stylesheet (`style.toml`) and who plays each part (`roles.toml`); None writes
    no such file."""
    path = tmp_path / 'MODELTEST.scn'
    path.write_text(edit(text, *steps), encoding='utf-8')
    for name, written in (('brief.toml', brief), ('style.toml', style), ('roles.toml', roles)):
        if written is None:
            (tmp_path / name).unlink(missing_ok=True)
        else:
            (tmp_path / name).write_text(written, encoding='utf-8')
    return path


def build(tmp_path, *steps, text=FIXTURE, brief=BRIEF, style=None):
    """The model of the file `text` with the steps of an edit."""
    return build_model(write(tmp_path, *steps, text=text, brief=brief, style=style), LIB)


def run(model, name, values=None):
    rs = model.resolve(name, values)
    return rs, simulate(rs, LIB)


def times(trajectory, event):
    return [entry['t'] for entry in trajectory.trace if entry['event'] == event]


def value(model, name, run_name):
    """The value an input takes in a run: its own, or a profile's of the run."""
    return model.run_values(run_name)[name]


def located(tmp_path, *steps, text=FIXTURE):
    """The diagnostics that reject the file with the steps of an edit."""
    with pytest.raises(ModelError) as caught:
        build(tmp_path, *steps, text=text)
    return caught.value.diagnostics


def assert_located(tmp_path, steps, place, words, text=FIXTURE):
    """The file with the steps of an edit is rejected with a diagnostic at `place` that says `words`,
    on the line of that place, or of the nearest line that holds it."""
    diagnostics = located(tmp_path, *steps, text=text)
    hits = [d for d in diagnostics if d.get('path') == place]
    assert hits, diagnostics
    assert words in hits[0]['message']
    written = (tmp_path / 'MODELTEST.scn').read_text(encoding='utf-8')
    lines = {path_text(where): number for where, number in front.read(written, 'MODELTEST.scn').lines.items()}
    key = place
    while key and key not in lines:
        key = key.rpartition('/')[0]
    assert hits[0]['line'] == lines[key]
