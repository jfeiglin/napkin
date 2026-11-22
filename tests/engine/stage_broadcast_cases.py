"""Broadcast starts read the selector and the ordering keys after earlier writes in the stage."""

from random import Random

from napkin.engine.timeline import read, run
from napkin.model.compile import compile_text
from napkin.program.config import Configuration, Request
from napkin.program.record import Key
from tests.reference.from_program import run_of, value_at

FAMILIES = ('selection', 'ordering')
CONFIG = Configuration(Request(1))
UNITS = {'h': {'time': 1}}


def _case(seed, family):
    """The initial ranks, the write, and the independently ordered recipients and final winner."""
    rng = Random(seed)
    ranks = [1, 2] if seed == 0 else rng.sample(range(1, 24), rng.randint(2, 5))
    members = range(len(ranks))
    by_rank = sorted(members, key=ranks.__getitem__)
    threshold = 0
    if family == 'selection':
        cutoff = rng.choice(by_rank[1:])
        if seed % 2:
            threshold, new_threshold = ranks[cutoff], min(ranks)
        else:
            new_threshold = ranks[cutoff]
        statement = f'this.threshold = {new_threshold}'
        # A filter on the default (entity-number) key preserves creation order.
        kept = [k for k in members if ranks[k] >= new_threshold]
        winner = ranks[kept[-1]]
    elif family == 'ordering':
        fresh = ranks.copy()
        if seed % 2:
            changed = by_rank[-1]
            fresh[changed] = min(ranks) - 1
        else:
            changed = by_rank[0]
            fresh[changed] = max(ranks) + 1
        statement = f'm{changed}.rank = {fresh[changed]}'
        kept = sorted(members, key=fresh.__getitem__)
        winner = fresh[kept[-1]]
    else:
        raise ValueError(f'unknown broadcast family {family!r}')
    return ranks, threshold, statement, tuple(f'm{k}.act#0' for k in kept), winner


def broadcast_source(seed, family, split=False):
    ranks, threshold, statement, _, _ = _case(seed, family)
    rank = 'input rank' if family == 'selection' else 'rank'
    receivers = 'where(rank >= this.threshold)' if family == 'selection' else 'by(rank)'
    members = '\n'.join(f'm{k}: Machine\n    rank = {value}' for k, value in enumerate(ranks))
    next_stage = '        after 0 h:\n' if split else ''
    return f"""Machine:
    {rank} = 0
    act = event():
        after 0 h:
            dispatcher.winner = this.rank

{members}

dispatcher:
    threshold = {threshold}
    winner = 0
    send = event():
        after 1 h:
            {statement}
{next_stage}            Machine.instances.{receivers}.act.start()

dispatcher.send.start()
"""


def check_broadcast_stage(seed, family):
    """Check the receiver identities, their exact start order, and their observable last write."""
    _, _, _, receivers, winner = _case(seed, family)
    expected = receivers, winner
    key = Key('dispatcher', ('winner',))
    for split in (True, False):
        program = compile_text(broadcast_source(seed, family, split), UNITS).program
        oracle, failure = run_of(program, CONFIG)
        assert failure is None, (seed, family, split, 'reference', failure)
        oracle_starts = tuple(
            entry.label for entry in oracle.trace if entry.kind == 'start' and entry.origin == 'Machine.act'
        )
        oracle_result = oracle_starts, value_at(oracle, program, key, 1)
        assert oracle_result == expected, (seed, family, split, 'reference', oracle_result, expected)
        record = run(program, CONFIG)
        assert record.failure is None, (seed, family, split, 'engine', record.failure)
        engine_starts = tuple(entry.owner for entry in record.entries('start', 'Machine.act'))
        engine_result = engine_starts, read(record, program, [key], [1])[0].values[0]
        assert engine_result == expected, (seed, family, split, 'engine', engine_result, expected)
