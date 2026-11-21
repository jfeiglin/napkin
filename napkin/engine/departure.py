"""The net physical rate needed to release a stock on either bound."""

from fractions import Fraction

import numpy as np

from ..core.units import rational

FACTOR = 1e-12
EXACT_FACTOR = Fraction(1, 10**12)
SUM_ERROR = 32 * np.finfo(float).eps


def refined(incoming, outgoing, uncertainty=0):
    """Compare the individual accepted rates before cancellation. If numerical
    uncertainty still spans the strict boundary, retain the face and identify the tie."""
    inward = sum(map(rational, incoming))
    outward = sum(map(rational, outgoing))
    net, gross = inward - outward, inward + outward
    excess = abs(net) - gross * EXACT_FACTOR
    unresolved = bool(uncertainty and abs(excess) <= rational(uncertainty))
    return (float(net) if excess > 0 and not unresolved else 0.0), unresolved


def rate(net, traffic, terms):
    """The net after applying the traffic-relative comparison to one touched store."""
    band = FACTOR * traffic
    if traffic and abs(abs(net) - band) <= SUM_ERROR * traffic:
        return refined(*terms())[0]
    return net if abs(net) > band else 0.0


def rates(net, traffic, held, terms):
    """Vectorized ordinary decision; revisit individual physical legs only at the edge."""
    difference = np.abs(net) - FACTOR * traffic
    result = np.where(held & (difference <= 0), 0.0, net)
    near = held & (traffic > 0) & (np.abs(difference) <= SUM_ERROR * traffic)
    for i in np.flatnonzero(near).tolist():
        result[i] = refined(*terms(i))[0]
    return result


def record_tie(recorder, t, store, net, traffic, error):
    """Publish an unresolved decision once at its accepted stock and moment."""
    for entry in reversed(recorder.trace):
        if entry.t != t:
            break
        if entry.part == store and entry.detail('departure') is not None:
            return
    band = FACTOR * traffic
    recorder.entry(
        t,
        'settle',
        store,
        near=((store, 'stock departure', abs(float(net)) - float(band), float(error)),),
        departure=(float(net), float(traffic), float(band), float(error)),
    )
