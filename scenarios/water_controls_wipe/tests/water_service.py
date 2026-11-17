"""Water-service disruption: independent reference mathematics, written from the specification, for
every place of the family.

Every time is in hours from the first move (t = 0). Inputs arrive in a plain dict under this
module's own short names, in execution units (hours, litres, people, work hours and US dollars at
2025 prices). The module imports no engine code and accepts no engine trajectory or expression.

The mathematics, in the order of the specification:

* `store_empty_time`: a store that holds a volume of usable water and serves its customers in full while
  it holds any, loses a share of normal use from the pipes, sells water on and takes a steady inflow, is
  empty when the net drain has used it up.
* `empty_time`: a store of usable water that serves its customers in full while it holds any,
  loses a share of normal use from the pipes and sends water on, and takes an inflow that changes
  at known moments, is empty when the net drain has used it up. The store never rises above what
  it held at the start.
* `work_completion`: a crew of a capacity `c` does `min(load, c t)` of a load in `t` hours.
* `shared_completion_times`: a pool that gives every job the same share of its capacity while
  the job has work left (processor sharing) finishes the smallest job first, and each job's
  completion time is the previous one plus the remaining work of this job over the crews that
  are still shared.
* `relief_throughput`: emergency water moves at the smallest of the compatible capacities.
* `person_days`: people without their normal service summed over time, in person-days.
* `gross_loss` and `net_loss`: the value added lost while water is short, as the stated share of
  the region's value added times the share of activity lost, over the interruption and its
  recovery, and the part that businesses have not made up by a later time.
"""

import math


def empty_time(usable_hours, demand, loss_share, export, inflow_segments):
    """Hours until a store of `usable_hours` of normal use is empty.

    `demand`, `export` and each inflow are rates in the same unit an hour; `inflow_segments` is
    `[(until, inflow), ...]` in order, the last `until` being `math.inf`. The store serves demand,
    exports and the leakage `loss_share * demand` in full while it holds water, and never rises
    above its start. `math.inf` when it never empties.
    """
    stock = full = usable_hours * demand
    t = 0.0
    for until, inflow in inflow_segments:
        drain = demand + loss_share * demand + export - inflow
        if drain > 0 and stock / drain <= until - t:
            return t + stock / drain
        stock = min(full, stock - drain * (until - t))
        t = until
    return math.inf


def store_empty_time(volume, demand, loss_share, sales, inflow):
    """Hours until a store of `volume` is empty, when it serves `demand`, the leakage `loss_share *
    demand` and `sales` in full while it holds water and takes a steady `inflow` (all rates in the unit of
    `volume` an hour). `math.inf` when the inflow covers the drain."""
    drain = demand * (1 + loss_share) + sales - inflow
    return volume / drain if drain > 0 else math.inf


def work_completion(load, capacity, hours):
    """Work done on `load` by crews of `capacity` an hour over `hours`."""
    return min(load, max(0.0, capacity * hours))


def shared_completion_times(loads, capacity):
    """Completion time of each load when a pool of `capacity` an hour is shared equally among the
    loads that still have work (processor sharing). Returns the times in the order of the loads."""
    if capacity <= 0:
        return [math.inf for _ in loads]
    order = sorted(range(len(loads)), key=lambda i: loads[i])
    times = [0.0] * len(loads)
    t = 0.0
    done = 0.0
    remaining = len(loads)
    for i in order:
        t += (loads[i] - done) * remaining / capacity
        done = loads[i]
        times[i] = t
        remaining -= 1
    return times


def relief_throughput(*capacities):
    """Emergency water that can move in a day: the smallest compatible capacity."""
    return min(capacities)


def person_days(population, interrupted_hours):
    """Person-days without normal service for `population` people whose service, summed over
    time, was short by `interrupted_hours` hours of full service."""
    return population * interrupted_hours / 24


def gross_loss(va_rate, dependence, activity_kept, recovery_factor, interrupted_hours):
    """Value added lost over an interruption of `interrupted_hours` hours of full service and its
    recovery: the water-dependent share of the region's value added an hour, times the share of
    activity lost, times the ratio of interruption plus recovery to interruption."""
    return va_rate * dependence * (1 - activity_kept) * recovery_factor * interrupted_hours


def net_loss(gross, catch_up_share, catch_up_time, hours_after):
    """The loss not made up `hours_after` hours after the water is back for good, when businesses
    can make up `catch_up_share` of it and do so at the rate of what is left over
    `catch_up_time`."""
    permanent = (1 - catch_up_share) * gross
    banked = catch_up_share * gross
    return permanent + banked * math.exp(-hours_after / catch_up_time)
