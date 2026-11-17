"""The icons of the map of the system: twenty line drawings on a 24-unit grid, as SVG.

`SHAPES` holds the SVG elements of each icon, by its name in the stylesheet (`style.ICONS`), in the
same order. A drawing can put them into an `<svg>` of its own. `ATTRIBUTES` are the drawing attributes
that every icon shares: the 24-unit grid (`viewBox`), and lines of width 1.6 in `currentColor`, with
no fill and with round ends and joins. `svg(name)` gives one icon as a standalone `<svg>`.
"""

from __future__ import annotations

NAMESPACE = 'http://www.w3.org/2000/svg'
# The drawing attributes that every icon shares.
ATTRIBUTES = {
    'viewBox': '0 0 24 24',
    'fill': 'none',
    'stroke': 'currentColor',
    'stroke-width': '1.6',
    'stroke-linecap': 'round',
    'stroke-linejoin': 'round',
}
# The SVG elements of each icon, in the order of the stylesheet's icons.
SHAPES = {
    'target': (
        '<circle cx="12" cy="12" r="8"/>'
        '<circle cx="12" cy="12" r="3.5"/>'
        '<path d="M12 2v4M12 18v4M2 12h4M18 12h4"/>'
    ),
    'server': (
        '<rect x="4" y="4" width="16" height="6.5" rx="1.5"/>'
        '<rect x="4" y="13.5" width="16" height="6.5" rx="1.5"/>'
        '<path d="M7.5 7.25h.01M7.5 16.75h.01M11 7.25h5M11 16.75h5"/>'
    ),
    'shield': '<path d="M12 3 4.5 6v5.5c0 4.6 3.2 8 7.5 9.5 4.3-1.5 7.5-4.9 7.5-9.5V6L12 3Z"/>',
    'hospital': '<path d="M4 21V8h16v13M2 21h20"/><path d="M12 10.5v6M9 13.5h6"/><path d="M9 8V4h6v4"/>',
    'people': (
        '<circle cx="9" cy="8" r="3"/>'
        '<path d="M3.5 20c0-3.3 2.5-6 5.5-6s5.5 2.7 5.5 6"/>'
        '<circle cx="16.5" cy="9" r="2.5"/>'
        '<path d="M15.5 14.2c2.8-.5 5 1.8 5 4.8"/>'
    ),
    'gauge': (
        '<path d="M3.5 17a8.5 8.5 0 1 1 17 0"/><path d="m12 17 4-5.5"/><circle cx="12" cy="17" r="1.2"/>'
    ),
    'factory': '<path d="M3 21V10l5 3v-3l5 3v-3l5 3V4h3v17H3Z"/><path d="M7 17h2M11.5 17h2M16 17h2"/>',
    'tank': (
        '<ellipse cx="12" cy="6" rx="7" ry="2.5"/>'
        '<path d="M5 6v12c0 1.4 3.1 2.5 7 2.5s7-1.1 7-2.5V6"/>'
        '<path d="M5 12c0 1.4 3.1 2.5 7 2.5s7-1.1 7-2.5"/>'
    ),
    'pipe': (
        '<path d="M2 10h6M16 10h6M2 15h6M16 15h6"/>'
        '<path d="m8 9 8 7M8 16l8-7"/>'
        '<path d="M12 12.5V6M9.5 6h5"/>'
    ),
    'bolt': '<path d="M13 2 5 13.5h6L10 22l9-12.5h-6L13 2Z"/>',
    'drop': '<path d="M12 3c3.5 4.5 6 8 6 11a6 6 0 0 1-12 0c0-3 2.5-6.5 6-11Z"/>',
    'wrench': (
        '<path d="M14.5 3.5a5 5 0 0 0-5.8 6.6L3.5 15.3a2.2 2.2 0 0 0 3.1 3.1l5.3-5.2a5 5 0 0 0 6.6-5.8l-3.1 3.1-2.9-.8-.8-2.9 3.1-3.1Z"/>'
    ),
    'truck': (
        '<path d="M2 6h11v10H2zM13 9h4.5l3.5 3.5V16h-8"/>'
        '<circle cx="6" cy="17.5" r="1.8"/>'
        '<circle cx="17" cy="17.5" r="1.8"/>'
    ),
    'box': (
        '<path d="M12 2.5 3.5 7v10L12 21.5 20.5 17V7L12 2.5Z"/><path d="M3.5 7 12 11.5 20.5 7M12 11.5v10"/>'
    ),
    'document': '<path d="M6 2.5h8l4.5 4.5v14.5H6z"/><path d="M14 2.5V7h4.5M9 12h6.5M9 15.5h6.5M9 19h4"/>',
    'money': (
        '<rect x="2.5" y="6" width="19" height="12" rx="1.5"/>'
        '<circle cx="12" cy="12" r="2.8"/>'
        '<path d="M6 9.5v5M18 9.5v5"/>'
    ),
    'house': '<path d="M3 11 12 3.5 21 11"/><path d="M5.5 9v11.5h13V9"/><path d="M10 20.5v-6h4v6"/>',
    'shop': (
        '<path d="M3.5 9.5 5 4h14l1.5 5.5"/>'
        '<path d="M3.5 9.5c0 1.5 1.3 2.5 2.9 2.5s2.9-1 2.9-2.5c0 1.5 1.3 2.5 2.7 2.5s2.7-1 2.7-2.5c0 1.5 1.3 2.5 2.9 2.5s2.9-1 2.9-2.5"/>'
        '<path d="M5 12v8.5h14V12M10 20.5v-5h4v5"/>'
    ),
    'sun': (
        '<circle cx="12" cy="12" r="4"/>'
        '<path d="M12 2v2.5M12 19.5V22M2 12h2.5M19.5 12H22M4.9 4.9l1.8 1.8M17.3 17.3l1.8 1.8M4.9 19.1l1.8-1.8M17.3 6.7l1.8-1.8"/>'
    ),
    'alert': '<path d="M12 3 2 20.5h20L12 3Z"/><path d="M12 9.5v5.5M12 17.8h.01"/>',
}


def svg(name):
    """The icon `name` as one standalone SVG document: its shapes (`SHAPES`) in an `<svg>` with the
    drawing attributes that every icon shares (`ATTRIBUTES`). A name that is not an icon raises
    ValueError, so that a misspelt name shows."""
    if name not in SHAPES:
        raise ValueError(f'{name} is not an icon; the icons are {", ".join(SHAPES)}')
    attributes = ' '.join(f'{key}="{value}"' for key, value in {'xmlns': NAMESPACE, **ATTRIBUTES}.items())
    return f'<svg {attributes}>{SHAPES[name]}</svg>'


__all__ = ['ATTRIBUTES', 'NAMESPACE', 'SHAPES', 'svg']
