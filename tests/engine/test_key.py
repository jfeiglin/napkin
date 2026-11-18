"""The key of a stored run (`napkin.store.key`, R-A4a-08): the canonical bytes of the program and of
the configuration without its request, the engine code and the environment."""

from __future__ import annotations

import dataclasses

from napkin import store
from napkin.program.build import SINK, Builder, flow, named, q, value
from napkin.program.config import SAMPLED, Configuration, Numerics, Request
from napkin.program.record import Key


def program(water=8):
    b = Builder({'L': {'volume': 1}, 'h': {'time': 1}})
    b.entity('tank', value('water', 'L', water, lower=0, upper=20))
    b.entity('clinic', flow('delivery', named('tank').water, SINK, request=q(3, 'L/h')))
    return b.finish()


def test_two_builds_of_one_run_have_one_key_and_the_request_is_no_part_of_it():
    first = store.key(program(), Configuration(Request(3)))
    assert len(first) == 64 and int(first, 16) >= 0
    assert store.key(program(), Configuration(Request(3))) == first
    keys = (Key('tank', ('water',)),)
    assert store.key(program(), Configuration(Request(48, everything=False, keys=keys))) == first


def test_what_a_run_computes_from_is_in_the_key():
    base = Configuration(Request(3))
    found = {
        store.key(program(), base),
        store.key(program(water=9), base),
        store.key(program(), dataclasses.replace(base, numerics=Numerics(max_step=0.5))),
        store.key(program(), Configuration(Request(3), mode=SAMPLED, seed=1)),
        store.key(program(), Configuration(Request(3), mode=SAMPLED, seed=2)),
    }
    assert len(found) == 5


def test_the_code_of_a_run_is_the_closure_of_its_entry_and_holds_no_compiler():
    files = [path.relative_to(store.PACKAGE).as_posix() for path in store.closure()]
    assert 'engine/timeline/__init__.py' in files and 'program/record.py' in files
    assert not [name for name in files if name.startswith('model/')]
