"""Identify the stock ledger's numerical remainder diagnostics in a recorded trace."""

from math import isfinite


def stock_remainders(entry):
    """Return (stock, target, signed remainder, band) for an in-band placement refusal."""
    if (entry.kind, entry.part, entry.owner) != ('settle', 'stock placement', ''):
        return None
    fields = dict(entry.details)
    if set(fields) not in ({'placements', 'near'}, {'placements', 'near', 'reason'}):
        return None
    placements, near = fields['placements'], fields['near']
    if not placements or len(placements) != len(near):
        return None
    targets = {}
    remainders = []
    for (stock, actual, target), (source, predicate, gap, band) in zip(placements, near, strict=True):
        if not all(map(isfinite, (actual, target, gap, band))):
            return None
        if (stock, f'{stock} == {target:.17g}') != (source, predicate):
            return None
        if gap != actual - target or abs(gap) > band or targets.setdefault(stock, target) != target:
            return None
        remainders.append((stock, target, gap, band))
    return tuple(remainders)


def decisions(trace):
    """Keep model events, their order, and their branch and allocation choices."""
    return tuple(entry for entry in trace if stock_remainders(entry) is None)
