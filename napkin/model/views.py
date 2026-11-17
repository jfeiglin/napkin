"""What tooling reads of a model, so that no tool retypes a model's names (docs/python-api.md, "Views").

- `actors(model)`: each thing that sees, with what it sees and its choices (the events marked
  `choice`, which a run can give to a person or an agent) with their outcomes.
- `instances(model, template)`: each instance of a template, with its title, copy and links.
"""

from __future__ import annotations

from .ir import thaw
from .semantic import EventRef, Ref, flat_key


def _text(words):
    return words.text if words is not None else None


def _seen(fact):
    if isinstance(fact, (Ref, EventRef)):
        return fact.written
    return None


def actors(model):
    """[{name, title, role, template, copy, sees, choices}] of each actor, in the order of the file.
    Each choice is {event, label, outcomes: [{name, label}]}: `event` is the event of the structure,
    `entity.event`."""
    found = []
    for entity in model.scenario.entities:
        if entity.sees is None:
            continue
        choices = [
            {
                'event': flat_key(f'{entity.name}.{event.name}'),
                'label': _text(event.label),
                'outcomes': [{'name': o.name, 'label': _text(o.label)} for o in event.outcomes],
            }
            for event in entity.events
            if event.choice
        ]
        found.append(
            {
                'name': entity.name,
                'title': entity.title,
                'role': thaw(entity.role),
                'template': entity.template,
                'copy': entity.copy,
                'sees': [name for name in (_seen(fact) for fact in entity.sees) if name is not None],
                'choices': choices,
            }
        )
    return found


def instances(model, template):
    """[{name, title, copy, links}] of each instance of a template, copies included, in the order of the
    file. `links` maps each link to the entity, or the list of entities, that the instance binds."""
    return [
        {'name': entity.name, 'title': entity.title, 'copy': entity.copy, 'links': thaw(entity.links)}
        for entity in model.scenario.entities
        if entity.template == template
    ]
