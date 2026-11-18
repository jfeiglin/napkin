"""The records of a small program: templates, stores, flows, events with their steps and triggers.

They stand for `napkin/program/parts.py` of the plan (step B1), cut down to what the spike needs.
The engine of the spike (`engine.py`) runs them, and the proofs (`proofs.py`) read them. Both read
the same records, so a proof is about the program that runs.

Paths. In an entity, `this.x` is a field or a store of the member, and `this.link.x` one of the
member that its link names. In an event, a bare name is a parameter, a local, a local store or a
local flow of the occurrence, and `this` is the receiver. `SOURCE` and `SINK` are the outside.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

SOURCE, SINK = 'SOURCE', 'SINK'


@dataclass
class Store:
    """A stored quantity. `tally`: it only receives (the language's accumulated value)."""

    name: str
    start: object = 0.0  # a number or an expression (an occurrence reads its parameters)
    lower: object = 0.0
    upper: object = math.inf
    out_capacity: object = math.inf  # `outflow.capacity`
    in_capacity: object = math.inf  # `inflow.capacity`
    tally: bool = False


@dataclass
class Flow:
    """A directed flow. `request` and `capacity` are numbers or expressions that change only at
    moments; `rank` is the key of `priority(...)` at its source, None for an unlisted flow."""

    name: str
    source: str
    sink: str
    request: object = 0.0
    capacity: object = math.inf
    rank: object = None


@dataclass
class Assign:
    target: str  # `this.x`, `this.link.x`, or a parameter or a local of the occurrence
    op: str  # '=', '+=' or '-='
    value: object


@dataclass
class Move:
    """`move amount from source to dest`."""

    amount: object
    source: str
    dest: str


@dataclass
class Start:
    """`event.start(args)`: `event` is `this.name` or `this.link.name`."""

    event: str
    args: tuple = ()


@dataclass
class SetFlow:
    """`flow.request = value` or `flow.capacity = value` in a stage."""

    flow: str
    prop: str
    value: object


@dataclass
class After:
    """`after delay [when guard]:` with the statements of its stage."""

    delay: object
    body: tuple = ()
    guard: object = None


@dataclass
class Until:
    cond: object


@dataclass
class Trigger:
    """`when C: event.start(args)` with its reset: None (the condition must become false),
    ('when', C2), ('after', D) or ('never',) for `reset when false`."""

    when: object
    args: tuple = ()
    reset: tuple | None = None


@dataclass
class Event:
    name: str
    params: tuple = ()  # (name, low, high): the declared range of each
    locals: tuple = ()  # (name, start expression), in written order
    stores: tuple = ()
    flows: tuple = ()
    steps: tuple = ()
    triggers: tuple = ()


@dataclass
class Template:
    name: str
    fields: dict = field(default_factory=dict)  # name -> start value
    ranges: dict = field(default_factory=dict)  # name -> (low, high) of a field, for the proofs
    formulas: dict = field(default_factory=dict)  # name -> expression of the member
    stores: tuple = ()
    flows: tuple = ()  # owned by the entity: connected for the whole run
    events: tuple = ()
    links: dict = field(default_factory=dict)  # link name -> template name

    def event(self, name):
        return next(event for event in self.events if event.name == name)
