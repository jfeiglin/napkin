"""The methods pages of the catalogue's scenarios link files that exist, from each owner's results folder."""

import re

import pytest

from tests.helpers import ROOT, SCENARIO_IDS, catalogue_model
from tools import catalogue
from tools.publish import Context
from tools.publish.methods import artifacts, scenario_methods
from tools.publish.pages import Pages


@pytest.mark.scenario_contract
@pytest.mark.parametrize('sid', SCENARIO_IDS)
def test_saved_methods_links_resolve_from_the_owned_result(sid):
    ctx = Context(ROOT, scenario_ids=[sid])
    ctx.models = {sid: catalogue_model(sid)}
    path, text = next(iter(artifacts(ctx).items()))
    assert path == catalogue.result(sid, 'methods.md')
    links = re.findall(r'\]\(([^)]+)\)', text)
    assert links
    for target in links:
        assert not target.startswith(('http:', 'https:'))
        assert ((ROOT / path).parent / target).resolve().exists(), target


def test_methods_renderer_uses_the_supplied_link_context():
    targets = []

    def link(target):
        targets.append(target)
        return 'https://example.test/' + target

    # The first scenario whose notes name its research record (`verification: research:`).
    sid = next(
        sid
        for sid in catalogue.entries(ROOT)
        if Pages(catalogue_model(sid)).review().get('verification', {}).get('research')
    )
    text = scenario_methods(catalogue_model(sid), link=link)
    assert (catalogue.locate(sid, ROOT).evidence / 'research.md').relative_to(ROOT).as_posix() in targets
    assert 'tests' in targets
    assert all('https://example.test/' + target in text for target in targets)
