"""Independent arithmetic of the archived finite-stock acceptance fixture."""


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
