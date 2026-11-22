"""The places of the package, which are its variants, and the parts of each place: its water systems,
their homes, their hospitals and the sales between them. Each part is found from the template that makes it,
and its system from what it reads in the model's structure.

The package's tests read every value from the model or from a run, never from this module."""

from functools import cache

from tests.helpers import ROOT, catalogue_model
from tests.selection import selected
from tools import catalogue

FAMILY = 'water_controls_wipe'


@cache
def places():
    """The name of each place of the package that the session checks (`pytest --scenario`), in the order
    of the catalogue: each variant of the package, `water_controls_wipe:<place>`, whose model reads the package's main
    file and its module. The variants are the readers of the package's folder (`tools.catalogue.readers`),
    because the package runs as its variants."""
    return selected(catalogue.readers(ROOT).get(FAMILY, ()))


def made_by(model, template):
    """The entities of a model that a template makes, in the order of the file."""
    return [member.path for member in model.declared.members if member.template == template]


def links(model, entity):
    """The member links supplied by this instance in its variant."""
    member = next(member for member in model.declared.members if member.path == entity)
    return {given.name: given.init for given in member.links}


def systems(sid):
    return made_by(catalogue_model(sid), 'Utility')


def homes(sid):
    """{system: its homes} for each system that serves people."""
    model = catalogue_model(sid)
    return {links(model, home)['utility']: home for home in made_by(model, 'Households')}


def hospitals(sid):
    """{system: its hospitals} for each system that supplies hospitals."""
    model = catalogue_model(sid)
    return {links(model, h)['utility']: h for h in made_by(model, 'Hospitals')}


def ties(sid):
    """{tie: (seller, buyer)}."""
    model = catalogue_model(sid)
    return {t: (links(model, t)['seller'], links(model, t)['buyer']) for t in made_by(model, 'Tie')}
