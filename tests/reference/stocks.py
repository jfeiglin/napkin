"""Find the cells that a declared move or flow can reach before its first transfer."""

from .errors import RunFailed
from .evaluate import Bound, Cell, Coll, Ent, Ev, Scope
from .model import Branch, Field, Flow, Move, Switch


def _targets(statements):
    for statement in statements:
        if isinstance(statement, Move):
            yield statement.source
            yield statement.destination
        elif isinstance(statement, Branch):
            yield from _targets(statement.then)
            yield from _targets(statement.other)
        elif isinstance(statement, Switch):
            for case in statement.cases:
                yield from _targets(case.body)
            yield from _targets(statement.default or ())


def _event_ends(event):
    for part in event.locals:
        if isinstance(part, Flow):
            for leg in part.legs or (part,):
                yield leg.source
                yield leg.sink
    for step in event.steps:
        yield from _targets(getattr(step, 'body', ()))
    for trigger in event.triggers:
        yield from _targets(trigger.starts)


def planned_stocks(run):
    """Concrete member cells and local field names to install at each occurrence's birth.

    A collection selector can change while the model is running. Enumerate its possible
    receivers without executing its filter, key or guard.
    """
    member_cells, locals_by_event = set(), {}
    members = {}
    for ent in run.ents.values():
        members.setdefault(ent.template.name, []).append(ent)

    def declaration(cell):
        if isinstance(cell.owner, Bound):
            return next((part for part in cell.owner.event.locals if part.name == cell.name), None)
        return run.fields.get(cell)

    def owners(target):
        if not isinstance(target, Cell):
            yield target
            return
        actual = run.view.cells.get(target)
        if isinstance(actual, Ent):
            yield actual
            return
        field = declaration(target)
        if isinstance(field, Field) and field.refers_to:
            template, *event = field.refers_to
            for ent in members.get(template, ()):
                if event:
                    yield from (Bound(ent, part) for part in ent.template.events if part.name == event[0])
                else:
                    yield ent

    def candidates(path, ev, bound):
        kind, args = path._k, path._a
        if kind in ('this', 'member'):
            yield ev.ref(path)
        elif kind == 'instances':
            yield from members.get(args[0], ())
        elif kind == 'name':
            name = args[0]
            if bound is not None and name in bound.event.params:
                template = bound.event.entity_params.get(name)
                # Native reference parameters can be untyped. Any member with the
                # required field is a possible argument to such a parameter.
                yield from run.ents.values() if template is None else members.get(template, ())
            elif bound is not None and any(part.name == name for part in bound.event.locals):
                yield Cell(bound, name)
            else:
                yield ev.ref(path)
        elif kind == 'coll':
            for item in args[0]:
                yield from candidates(item, ev, bound)
        elif kind == 'where' or (kind == 'call' and args[1] in ('at', 'by', 'where')):
            yield from candidates(args[0], ev, bound)
        elif kind == 'attr':
            base, name = args
            for owner in (
                owner for base_target in candidates(base, ev, bound) for owner in owners(base_target)
            ):
                if isinstance(owner, Bound):
                    if name == 'occurrences':
                        yield owner
                    elif any(part.name == name for part in owner.event.locals):
                        yield Cell(owner, name)
                else:
                    try:
                        target = ev.attr(owner, name)
                    except RunFailed:
                        # A possible receiver of an untyped argument can lack this field.
                        # The executing statement diagnoses its actual receiver.
                        continue
                    if isinstance(target, Coll):
                        yield from (member for _, member, _ in target.items)
                    else:
                        yield target

    def collect(paths, ev, bound):
        for path in paths:
            for cell in candidates(path, ev, bound):
                if not isinstance(cell, Cell):
                    continue
                field = declaration(cell)
                if not isinstance(field, Field) or field.kind != 'value':
                    continue
                owner = cell.owner
                if isinstance(owner, Bound):
                    locals_by_event.setdefault((owner.ent, owner.event.name), set()).add(cell.name)
                else:
                    member_cells.add(cell)

    collect(_targets(run.model.setup), Ev(run, run.view, Scope()), None)
    for ent in run.ents.values():
        ev = Ev(run, run.view, Scope(ent))
        for event in ent.template.events:
            collect(_event_ends(event), ev, Bound(ent, event))
    return member_cells, locals_by_event
