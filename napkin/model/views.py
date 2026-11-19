"""What tooling reads of a compiled model (`compile.Compiled`), so that no tool retypes a model's names
(docs/python-api.md, "Views").

- `instances(compiled, template)`: each member of a template, in creation order, with the member
  that each of its links names.

It reads the program. (The view of actors, their sights and their choices left with the player
machinery: item 15 of the plan's changes after G0.)
"""

from __future__ import annotations

from ..program import parts as p


def instances(compiled, template):
    """[{name, links}] of each member of a template, in creation order. `links` maps each link to the
    id of the member that it names."""
    program = compiled.program
    found = program.template(template)
    targets = {value.name: value.type.template for value in found.values if value.kind == p.LINK}
    return [
        {
            'name': member.id,
            'links': {name: program.template(targets[name]).members[row].id for name, row in member.links},
        }
        for member in found.members
    ]
