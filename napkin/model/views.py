"""What tooling reads of a compiled model (`compile.Compiled`), so that no tool retypes a model's names
(docs/python-api.md, "Views").

- `actors(compiled)`: each actor, a template (an entity is the template of its one member) whose
  human player is shown what it `sees` or is asked by a stage to `choose`. `sees` permits nothing
  (D1): it lists what the player is shown. Each choice is the site that a pick names (`config.Pick`),
  the event whose stage asks it, and its outcomes: each member of the forecast's enum, with the card
  (the text) of its case when the choice selects a `switch`. The language refuses `choose` and
  `sees` (item 15 of the plan's changes after G0), so a compiled text has no actor; the view goes
  when the program loses its choices.
- `instances(compiled, template)`: each member of a template, in creation order, with the member
  that each of its links names.

Both read the program, where each choice has its final site, and the declared model for the texts.
"""

from __future__ import annotations

from ..program import check
from ..program import parts as p
from ..program.refs import Choice, Distribution, Expr, Formula, spelled


def _expressions(statement):
    """The expressions of a statement, with the switch whose selector each one is (or None)."""
    if isinstance(statement, p.Assign):
        value = statement.value
        yield (value.expr if isinstance(value, Formula) else value), None
    elif isinstance(statement, p.Move):
        yield statement.amount, None
    elif isinstance(statement, p.Start):
        for arg in statement.args:
            yield arg, None
    elif isinstance(statement, p.If):
        yield statement.test, None
        for inner in (*statement.then, *statement.orelse):
            yield from _expressions(inner)
    elif isinstance(statement, p.Switch):
        yield statement.selector, statement
        for case in statement.cases:
            yield case.guard, None
            for inner in case.body:
                yield from _expressions(inner)
        for inner in statement.orelse:
            yield from _expressions(inner)


def _choices(program):
    """(template, event, the choice, the switch that it selects or None) of each choice of a program,
    in the order of the templates, their events and their stages."""
    for template in program.templates:
        for event in template.events:
            for step in event.steps:
                if not isinstance(step, p.After):
                    continue
                for statement in step.body:
                    for expression, switch in _expressions(statement):
                        if not isinstance(expression, Expr):
                            continue
                        for _, read in expression.reads:
                            if isinstance(read, Choice):
                                selects = switch if len(expression.reads) == 1 else None
                                yield template, event, read, selects


def _enum_of(resolver, scope, source):
    """The enum of a forecast: of a categorical written in place, or of the value that holds one."""
    if isinstance(source, Distribution):
        return source.enum
    found = resolver.resolve(source, scope, '')
    return found.part.type.of.enum


def actors(compiled):
    """[{name, members, sees, choices}] of each actor, in the order of the templates. `members` are
    the ids of the template's members; each choice is {site, event, outcomes: [{name, label}]}."""
    program, declared = compiled.program, compiled.declared
    resolver = check.Resolver(program)
    found = {
        template.name: {
            'name': template.name,
            'members': [member.id for member in template.members],
            'sees': [spelled(path) for path in template.sees],
            'choices': [],
        }
        for template in program.templates
    }
    for template, event, choice, switch in _choices(program):
        scope = check.Scope(template, event)
        actor = resolver.resolve(choice.actor, scope, '')
        enum = program.enum(_enum_of(resolver, scope, choice.source))
        labels = {}
        if switch is not None:
            for case in switch.cases:
                part = declared.part(case.origin)
                labels[case.member] = getattr(part, 'text', None)
        found[actor.part.name]['choices'].append(
            {
                'site': choice.site,
                'event': event.origin,
                'outcomes': [{'name': member, 'label': labels.get(member)} for member in enum.members],
            }
        )
    return [item for item in found.values() if item['sees'] or item['choices']]


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
