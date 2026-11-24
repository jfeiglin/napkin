"""Synthetic comparison inputs expressed in multiples of the configured band."""


def band_samples(configuration, scale, multiples=(0.5, 2)):
    """By default, return gaps half a band and two bands from zero."""
    numerics = configuration.numerics
    width = max(numerics.rtol, numerics.atol_factor) * scale
    return tuple(multiple * width for multiple in multiples)
