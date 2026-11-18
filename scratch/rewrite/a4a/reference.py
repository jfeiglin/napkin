"""A second, slow implementation of the run of `lines.py`, to check it. It shares no code with it.

At each moment it finds every rate again from nothing: each flow starts from what it asks, and
the stores on their bound lower their outflows to what comes in, all at once, until nothing
changes. Then it moves every store to the next moment. `lines.py` instead brings up to date only
what a change reaches. Both follow one rule (the stand-in rule of `lines.py`), so they must agree
to roundoff.
"""

from __future__ import annotations

import numpy as np
import scipy.sparse as sp


def run(net, y, want, horizon, moves=(), times=()):
    """{time: the stores} at each of `times`, and the count of the moments. `moves`: (time, source,
    target, amount), in the order in which they happen."""
    S, F = net.stores.count, net.count
    src, dst = net.src, net.dst
    flows = np.arange(F)
    out, into = src >= 0, dst >= 0
    b_out = sp.csr_array((np.ones(out.sum()), (src[out], flows[out])), shape=(S, F))
    b_in = sp.csr_array((np.ones(into.sum()), (dst[into], flows[into])), shape=(S, F))
    y = np.array(y, dtype=float)
    want = np.asarray(want, dtype=float)
    asked = b_out @ want
    source = np.maximum(src, 0)
    scale = 1e-13 * max(float(want.max(initial=0.0)), 1e-300)

    def rates(on):
        a = want.copy()
        for _ in range(100_000):
            coming = b_in @ a
            short = on & (asked > coming)
            fraction = np.ones(S)
            fraction[short] = coming[short] / asked[short]
            new = np.where(out, want * fraction[source], want)
            if np.abs(new - a).max(initial=0.0) <= scale:
                a = new
                break
            a = new
        else:
            raise RuntimeError('the reference does not settle')
        rate = b_in @ a - b_out @ a
        coming = b_in @ a
        rate[on & (asked > coming)] = 0.0
        return rate

    moves = sorted(moves, key=lambda item: item[0])
    times = sorted(times)
    found, t, k, moments = {}, 0.0, 0, 0
    on = y <= 0.0
    rate = rates(on)
    while True:
        falling = (rate < 0) & (y > 0)
        ahead = np.full(S, np.inf)
        ahead[falling] = y[falling] / -rate[falling]
        s = int(np.argmin(ahead)) if S else 0
        deplete = t + ahead[s] if S else np.inf
        move = moves[k][0] if k < len(moves) else np.inf
        nxt = min(deplete, move, horizon)
        while times and times[0] <= nxt:
            at = times.pop(0)
            found[at] = y + rate * (at - t)
        if nxt >= horizon:
            break
        y = y + rate * (nxt - t)
        t = nxt
        if move <= deplete:
            while k < len(moves) and moves[k][0] == t:
                _, a, b, amount = moves[k]
                y[a] -= amount
                y[b] += amount
                k += 1
        else:
            y[s] = 0.0
        y[(y < 0) & (y > -1e-9)] = 0.0  # what roundoff leaves below the bound
        on = y <= 0.0
        rate = rates(on)
        moments += 1
    for at in times:
        found[at] = y + rate * (min(at, horizon) - t)
    return found, moments
