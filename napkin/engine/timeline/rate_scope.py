"""The time-dependent requests and capacities of one installed physical network."""

from .collections import node_of
from .plan import CAPTURE, FIXED, FORMULA

_PARAMETERS = (*FIXED, CAPTURE)


def rate_node(run, name):
    """The arithmetic of one eligible input, including the installed members of a reduction."""
    reduction = run.plan.reductions.get(name)
    if reduction is not None:
        return node_of(reduction, run.kept_of(name))
    return run.plan.values[name].node


def clock_rates(run, flows, stores, *, observe=False):
    """Map an eligible setting to the stocks at the ends of its connections.

    Follow the current definitions, membership and arithmetic rates. A lookup,
    changing collection or state read is outside the explicit-time guard, even
    when the stock or selected member happens to hold still. Captured parameters
    are fixed for this installation. Settlement replaces it when a parameter changes.
    """
    plan = run.plan
    accounts = {}
    for flow in flows:
        for connection in plan.flows[flow].connections:
            for name in plan.connection_settings(connection):
                if plan.values[name].kind == FORMULA:
                    accounts.setdefault(name, set()).update((connection.source, connection.sink))

    eligible = {}
    for name, adjacent in accounts.items():
        found = plan.inputs_now(plan.expanded(name))
        if not (found.time or found.stepped):
            continue
        if found.stepped or any(
            leaf not in plan.draws and (leaf not in plan.values or plan.values[leaf].kind not in _PARAMETERS)
            for leaf in found.leaves
        ):
            if observe:
                run.unchecked_time_rates.setdefault(name, run.accepted)
        else:
            eligible[name] = tuple(store for store in stores if store in adjacent)
    return eligible
