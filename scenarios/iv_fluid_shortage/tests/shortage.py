"""Finite-stock shortage arithmetic, release clocks and the retained-access ledger."""

from itertools import pairwise


def causal_shortage(
    *,
    receipt_h,
    buffer_days=15,
    p_death=0.02,
    course_volume=2,
    independent_supply=480,
    permanent_loss_fraction=0.15,
    restoration_resources=12,
):
    """Independent finite-stock formula, all quantities in approved units.

    Each pool starts with buffer_days x 600 L. Unaffected supply (independent_supply L/day,
    below the 600 L/day resuscitation demand) all goes to resuscitation, so that pool drains
    at the 600 - independent_supply L/day deficit and runs out after 600 x buffer_days / deficit
    days. From then until receipt the deficit goes unmet, one complete course per course_volume
    litres; p_death of those patients die and 5% become eventual serious survivors. Affected
    output (USD 2 million/day) is lost at permanent_loss_fraction until receipt; restoration
    (restoration_resources) and logistics (1) add USD millions.
    """
    deficit = 600 - independent_supply
    exhaustion_h = 24 * 600 * buffer_days / deficit
    delayed = deficit / 24 / course_volume * max(0, receipt_h - exhaustion_h)
    return {
        'delayed_patients': delayed,
        'deaths': p_death * delayed,
        'eventual_serious_survivors': 0.05 * delayed,
        'loss_bn': (2e6 * permanent_loss_fraction * receipt_h / 24 + restoration_resources * 1e6 + 1e6) / 1e9,
    }


# Operational rebuild references.
"""Analytical reference for finite qualification work and fluid rectangles."""


def receipt_hour(work, rate, extra, activate, contain, lead=24):
    return max(activate, (work + extra) / rate, contain) + lead


def deficits(t, receipt, buffer_days, resus_day=600, other_day=600, independent_day=480, course_litres=2):
    held = min(t, receipt)
    net = (resus_day - independent_day) / 24
    exhausted = buffer_days * resus_day / net
    resus = max(0, held - exhausted) * net
    other = max(0, held - buffer_days * 24) * other_day / 24
    return {
        'resus_deficit_L': resus,
        'other_deficit_L': other,
        'unmet_complete_courses': resus / course_litres,
    }


def ai_clocks(p, *, persistent):
    """Release, intruder and defender clocks of one pathway, derived from its inputs alone (hours).

    One crew does the release work at qualification_rate: the ordinary work first, then each
    reconciliation once it exists. The single strike folds its extra work into the ordinary work.
    With retained access the intruder alters the shipment records when procurement starts (act_h),
    unless the foothold was removed first or at that moment (containment_h); that adds extra_delay_h
    of reconciliation, which the crew starts once the ordinary work is done and the change exists.
    Release restarts once procurement, the work, the foothold's removal and the qualified release
    channel are all in place; fluid arrives one release_lead_h later.

    Then two clocks race from the restart: the intruder alters the records of the lots being
    released ai_retask_h later, and the manufacturer resets the record systems' credentials reset_h
    later; an exact tie goes to the reset. Altered records are found suspect_h after the change:
    every lot released since the restart is held, deliveries stop and the crew reconciles the records
    against the product (deep_reconcile_h of work); release restarts when that work is done and fluid
    arrives one lead later. Events at the end of the study period still happen; later ones do not.
    """
    rate, lead, horizon = p['qualification_rate'], p['release_lead_h'], p['recovery_h']
    act, contain = p['act_h'], p['containment_h']

    def within(t):
        return t if t is not None and t <= horizon else None

    tampered = persistent and act < contain
    if persistent:
        ready = max(p['qualification_work_h'] / rate, act) + (p['extra_delay_h'] if tampered else 0) / rate
    else:
        ready = (p['qualification_work_h'] + p['extra_delay_h']) / rate
    release = within(max(ready, act, contain)) if p['independent_release_enabled'] == 1 else None
    clocks = {
        'first_tampering': act if tampered else None,
        'first_cancelled': act if persistent and not tampered else None,
        'release': release,
        'receipt': within(release + lead) if release is not None else None,
        'reset': None,
        'altered': None,
        'cancelled': None,
        'held': None,
        'rework_done': None,
        're_receipt': None,
    }
    if not persistent or release is None:
        return clocks
    tempo, reset = p['ai_retask_h'], p['reset_h']
    clocks['reset'] = within(release + reset)
    if tempo < reset:
        clocks['altered'] = within(release + tempo)
    else:
        clocks['cancelled'] = clocks['reset']
    if clocks['altered'] is not None:
        clocks['held'] = within(clocks['altered'] + p['suspect_h'])
    if clocks['held'] is not None:
        clocks['rework_done'] = within(clocks['held'] + p['deep_reconcile_h'] / rate)
    if clocks['rework_done'] is not None:
        clocks['re_receipt'] = within(clocks['rework_done'] + lead)
    return clocks


def release_work(p, t, *, persistent):
    """Release work at hour t: ordinary work left, reconciliation pending and not yet created, work done.

    One crew works one task at a time at qualification_rate: the ordinary work first (the single strike
    folds its extra work into it), then each reconciliation once it exists. With retained access the
    reconciliation not yet created holds the first tampering's reconciliation (extra_delay_h) and the
    reconciliation against the product (deep_reconcile_h); each is created when its tampering is found:
    at procurement start, and when the altered records are found after the restart.
    """
    rate = p['qualification_rate']
    ordinary = p['qualification_work_h'] + (0 if persistent else p['extra_delay_h'])
    left = max(ordinary - rate * t, 0.0)
    out = {'ordinary': left, 'pending': 0.0, 'potential': 0.0, 'completed': ordinary - left}
    if not persistent:
        return out
    clocks = ai_clocks(p, persistent=True)
    extra, deep = p['extra_delay_h'], p['deep_reconcile_h']
    out['potential'] = extra + deep
    burdens = []
    if clocks['first_tampering'] is not None:
        burdens.append((clocks['first_tampering'], extra))
    if clocks['held'] is not None:
        burdens.append((clocks['held'], deep))
    free = ordinary / rate
    for arrival, amount in burdens:
        start = max(free, arrival)
        free = start + amount / rate
        if t < arrival:
            continue
        done = min(max(rate * (t - start), 0.0), amount)
        out['potential'] -= amount
        out['pending'] += amount - done
        out['completed'] += done
    return out


def shortage_ledger(p, *, persistent, until=None):
    """Unmet litres, courses and clinical partition of one pathway from piecewise-linear reserves.

    Each reserve starts with buffer_days of demand. Without released fluid the resuscitation reserve
    gains other makers' supply and loses its demand, the other-care reserve only loses its demand; an
    empty reserve stays empty and its shortfall goes unmet. Released fluid meets both demands and keeps
    the reserves level. At a hold the hospitals set aside the lesser of each reserve and the released
    fluid it has received (oldest stock is used first, so what they still hold from released lots is
    their newest stock). Unmet resuscitation litres are courses; their fluid-dependent share is rescued
    up to rescue_capacity a day once procurement starts, and the rest is unresolved. A reserve is short
    when demand goes unmet over a positive interval before the end of the study period. Totals are
    accrued up to `until` (the horizon by default).
    """
    horizon = p['recovery_h']
    until = horizon if until is None else until
    clocks = ai_clocks(p, persistent=persistent)
    demand = {'resuscitation': p['resus_demand'] / 24, 'other_care': p['other_demand'] / 24}
    inflow = {'resuscitation': p['independent_supply'] / 24, 'other_care': 0.0}
    each = p['replacement_supply'] / 48
    supplied = []
    if clocks['receipt'] is not None:
        supplied.append((clocks['receipt'], clocks['held'] if clocks['held'] is not None else horizon))
    if clocks['re_receipt'] is not None:
        supplied.append((clocks['re_receipt'], horizon))
    held = clocks['held']
    marks = {0.0, p['act_h'], until} | {t for pair in supplied for t in pair}
    if held is not None:
        marks.add(held)
    breaks = sorted(t for t in marks if t <= until)
    rescue = p['rescue_capacity'] / 24
    result = {}
    for pool in ('resuscitation', 'other_care'):
        stock = p['buffer_days'] * 24 * demand[pool]
        empty, exhausted, unmet, high_risk, saved, set_aside, short = False, None, 0.0, 0.0, 0.0, 0.0, False
        # A hold exactly at `until` still sets stock aside, over a closing interval of zero length.
        for start, end in pairwise([*breaks, until] if breaks[-1] == held else breaks):
            if start == held:
                set_aside = min(stock, each * (held - clocks['receipt']))
                stock -= set_aside
                if stock <= 0 and not empty:
                    stock, empty, exhausted = 0.0, True, start
            if end <= start or any(first <= start < last for first, last in supplied):
                continue
            t, gap = start, demand[pool] - inflow[pool]
            if not empty and stock - gap * (end - start) <= 0:
                t = start + stock / gap
                stock, empty, exhausted = 0.0, True, t
            if empty:
                short = short or end > t
                unmet += gap * (end - t)
                if pool == 'resuscitation':
                    high = p['fluid_dependent_share'] * gap / p['course_volume']
                    high_risk += high * (end - t)
                    saved += (min(high, rescue) if start >= p['act_h'] else 0.0) * (end - t)
            else:
                stock -= gap * (end - start)
        result[pool] = {
            'unmet_L': unmet,
            'exhausted': exhausted,
            'short': short,
            'set_aside_L': set_aside,
            'stock_L': stock,
        }
        if pool == 'resuscitation':
            result['high_risk'], result['rescued'] = high_risk, saved
    result['unmet_courses'] = result['resuscitation']['unmet_L'] / p['course_volume']
    result['unresolved'] = result['high_risk'] - result['rescued']
    result['clocks'] = clocks
    return result


def pathway_outcomes(p, *, persistent):
    """Final deaths, casualties, economic loss (USD2025 bn) and shortage of one pathway.

    Deaths and serious survivors count courses unresolved by the horizon less clinical_delay_h; the
    manufacturer is unavailable for the whole horizon; logistics are paid once fluid first arrives;
    each postponed other-care procedure needs other_course_volume litres; the other-care shortage lasts
    one day for each day of other-care demand that goes unmet.
    """
    horizon = p['recovery_h']
    final = shortage_ledger(p, persistent=persistent)
    lagged = shortage_ledger(p, persistent=persistent, until=horizon - p['clinical_delay_h'])
    deaths = lagged['unresolved'] * (p['untreated_fatality'] - p['treated_fatality'])
    serious = lagged['unresolved'] * p['serious_survivor_fraction']
    procedures = final['other_care']['unmet_L'] / p['other_course_volume']
    loss = (
        horizon * p['supplier_value_added_rate']
        + p['restoration_cost']
        + (p['replacement_logistics_cost'] if final['clocks']['receipt'] is not None else 0)
        + procedures * p['cancelled_procedure_value_added']
    )
    return {
        'resus_deficit_L': final['resuscitation']['unmet_L'],
        'other_deficit_L': final['other_care']['unmet_L'],
        'shortage_days': final['other_care']['unmet_L'] / p['other_demand'],
        'unmet_complete_courses': final['unmet_courses'],
        'clinical_rescued_courses': final['rescued'],
        'clinical_unresolved_courses': final['unresolved'],
        'deaths': deaths,
        'casualties': deaths + serious,
        'loss_bn': loss / 1e9,
    }


def pathway_events(p, *, persistent):
    """The semantic events one pathway records, predicted from its clocks and reserves (sorted).

    A reserve's exhaustion is recorded when it first empties; its shortage when demand first goes unmet
    over a positive interval, so a reserve emptied exactly as fluid arrives, or as the study period
    ends, is exhausted but not short.
    """
    clocks = ai_clocks(p, persistent=persistent)
    ledger = shortage_ledger(p, persistent=persistent)
    events = [
        'attacker.initial_attack.executed',
        'manufacturer.disruption',
        'procurement.activate',
        'initial_access.initial_contained',
        'manufacturer.recovery',
    ]
    if persistent:
        events.append(
            'attacker.record_attack.executed'
            if clocks['first_tampering'] is not None
            else 'attacker.record_attack.cancelled'
        )
    if clocks['release'] is not None:
        events.append('replacement.qualified_release')
    if clocks['receipt'] is not None:
        events.append('replacement.receipt')
    if clocks['altered'] is not None:
        events.append('attacker.retamper.executed')
    if clocks['cancelled'] is not None:
        events.append('attacker.retamper.cancelled')
    if clocks['held'] is not None:
        events.append('access.lots_held')
    if clocks['re_receipt'] is not None:
        events.append('replacement.re_receipt')
    for pool, exhausted, short in (
        ('resuscitation', 'resuscitation.resus_exhausted', 'model.resus_shortage'),
        ('other_care', 'other_care.other_exhausted', 'model.other_shortage'),
    ):
        if ledger[pool]['exhausted'] is not None:
            events.append(exhausted)
        if ledger[pool]['short']:
            events.append(short)
    return sorted(events)
