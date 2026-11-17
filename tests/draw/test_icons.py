"""The icons of the map (`draw/icons.py`): one for each icon that a stylesheet names, each a line
drawing on the 24-unit grid of its `viewBox`.

The tests read each icon as XML and check properties of its geometry: the shapes are SVG's basic
shapes, and every point that a line reaches lies inside the grid. The path data is read by the rules
of SVG 1.1 (section 8.3, and the arcs of appendix F.6.5), not by the module.
"""

from __future__ import annotations

import json
import math
import re
import xml.etree.ElementTree as ET
from pathlib import Path

import pytest

from napkin.draw import icons, style

SVG = 'http://www.w3.org/2000/svg'
NAMES = json.loads(Path(__file__).with_name('map-icons.json').read_text(encoding='utf-8'))['icons']
# The attributes of SVG's basic shapes that give their geometry: a shape sets nothing else, so the
# drawing attributes of its icon apply to it.
GEOMETRY = {
    'circle': ({'cx', 'cy', 'r'}, {'r'}),
    'ellipse': ({'cx', 'cy', 'rx', 'ry'}, {'rx', 'ry'}),
    'rect': ({'x', 'y', 'width', 'height', 'rx', 'ry'}, {'width', 'height'}),
    'path': ({'d'}, {'d'}),
}
# The commands of path data that the icons use, with the count of numbers of each.
ARITY = {'M': 2, 'L': 2, 'H': 1, 'V': 1, 'C': 6, 'S': 4, 'A': 7, 'Z': 0}
COMMAND = re.compile(r'([MmLlHhVvCcSsAaZz])([^MmLlHhVvCcSsAaZz]*)')
NUMBER = re.compile(r'[-+]?(?:\d+\.?\d*|\.\d+)(?:[eE][-+]?\d+)?')


def drawing(name):
    """The root of an icon's `<svg>` and its shapes, as (tag, {attribute: value})."""
    root = ET.fromstring(icons.svg(name))
    return root, [(child.tag, dict(child.attrib)) for child in root]


def commands(d):
    """(command, numbers) for each command of path data, a repeated command written out: the pairs
    after a moveto are lines."""
    found = COMMAND.findall(d)
    assert ''.join(command + text for command, text in found) == d.strip(), d
    # Path data starts with a moveto.
    assert found and found[0][0] in 'Mm', d
    for command, text in found:
        numbers = [float(number) for number in NUMBER.findall(text)]
        assert not NUMBER.sub('', text).strip(' ,\t\n'), (d, text)
        arity = ARITY[command.upper()]
        if not arity:
            assert not numbers, (d, text)
            yield command, []
            continue
        assert numbers and len(numbers) % arity == 0, (d, command, text)
        for i in range(0, len(numbers), arity):
            repeated = {'M': 'L', 'm': 'l'}.get(command, command) if i else command
            yield repeated, numbers[i : i + arity]


def arc(start, rx, ry, rotation, large, sweep, end, steps=720):
    """Points along an arc of an ellipse, from its centre (SVG 1.1, F.6.5): the conversion from its end
    points, with radii that are too small for the chord made just large enough (F.6.6)."""
    (x1, y1), (x2, y2) = start, end
    if start == end:
        return []
    rx, ry = abs(rx), abs(ry)
    if not rx or not ry:
        return [end]
    cos, sin = math.cos(math.radians(rotation)), math.sin(math.radians(rotation))
    hx, hy = (x1 - x2) / 2, (y1 - y2) / 2
    xp, yp = cos * hx + sin * hy, -sin * hx + cos * hy
    excess = xp**2 / rx**2 + yp**2 / ry**2
    if excess > 1:
        rx, ry = rx * math.sqrt(excess), ry * math.sqrt(excess)
    square = (rx**2 * ry**2 - rx**2 * yp**2 - ry**2 * xp**2) / (rx**2 * yp**2 + ry**2 * xp**2)
    root = math.sqrt(max(square, 0.0)) * (-1 if large == sweep else 1)
    cxp, cyp = root * rx * yp / ry, -root * ry * xp / rx
    cx, cy = cos * cxp - sin * cyp + (x1 + x2) / 2, sin * cxp + cos * cyp + (y1 + y2) / 2

    def between(ux, uy, vx, vy):
        return math.atan2(ux * vy - uy * vx, ux * vx + uy * vy)

    first = between(1, 0, (xp - cxp) / rx, (yp - cyp) / ry)
    turn = between((xp - cxp) / rx, (yp - cyp) / ry, (-xp - cxp) / rx, (-yp - cyp) / ry)
    if sweep and turn < 0:
        turn += 2 * math.pi
    elif not sweep and turn > 0:
        turn -= 2 * math.pi
    points = []
    for k in range(steps + 1):
        t = first + turn * k / steps
        px, py = rx * math.cos(t), ry * math.sin(t)
        points.append((cos * px - sin * py + cx, sin * px + cos * py + cy))
    # The centre is right only if the arc runs from one end point to the other.
    assert math.dist(points[0], start) < 1e-9 and math.dist(points[-1], end) < 1e-9, (start, end)
    return points


def path_points(d):
    """Every point that path data reaches: the end of each segment, the control points of each curve,
    whose hull holds the curve, and points along each arc."""
    x = y = 0.0
    start, control, out = (0.0, 0.0), None, []
    for command, n in commands(d):
        kind = command.upper()
        # A command in lower case is relative to the current point.
        base = (x, y) if command.islower() else (0.0, 0.0)
        at = [(n[i] + base[0], n[i + 1] + base[1]) for i in range(0, len(n) - 1, 2)]
        if kind == 'H':
            at = [(n[0] + base[0], y)]
        elif kind == 'V':
            at = [(x, n[0] + base[1])]
        elif kind == 'S':
            # The first control point is the last one reflected about the current point.
            at = [(2 * x - control[0], 2 * y - control[1]) if control else (x, y), *at]
        elif kind == 'A':
            end = (n[5] + base[0], n[6] + base[1])
            at = [*arc((x, y), *n[:5], end), end]
        elif kind == 'Z':
            at = [start]
        out += at
        x, y = at[-1]
        control = at[-2] if kind in 'CS' else None
        if kind == 'M':
            start = (x, y)
    return out


def extent(tag, a):
    """The points that bound a shape: each point that its lines reach, or the corners of its box."""
    number = {key: float(value) for key, value in a.items() if key != 'd'}
    if tag == 'path':
        return path_points(a['d'])
    if tag == 'rect':
        x, y = number.get('x', 0.0), number.get('y', 0.0)
        return [(x, y), (x + number['width'], y + number['height'])]
    rx, ry = (number['r'], number['r']) if tag == 'circle' else (number['rx'], number['ry'])
    cx, cy = number.get('cx', 0.0), number.get('cy', 0.0)
    return [(cx - rx, cy - ry), (cx + rx, cy + ry)]


def test_the_icons_are_the_stylesheet_s_icons_in_its_order():
    assert tuple(icons.SHAPES) == style.ICONS == tuple(NAMES)


@pytest.mark.parametrize('name', NAMES)
def test_each_icon_is_an_svg_line_drawing_on_a_24_unit_grid(name):
    root, shapes = drawing(name)
    assert root.tag == f'{{{SVG}}}svg'
    assert [float(number) for number in root.get('viewBox').split()] == [0, 0, 24, 24]
    # Lines in the colour of what holds the icon, with no fill.
    assert (root.get('fill'), root.get('stroke')) == ('none', 'currentColor')
    assert float(root.get('stroke-width')) > 0
    assert shapes
    for tag, attributes in shapes:
        namespace, _, shape = tag.removeprefix('{').partition('}')
        assert namespace == SVG and shape in GEOMETRY, tag
        allowed, needed = GEOMETRY[shape]
        assert needed <= set(attributes) <= allowed, (tag, attributes)
    # The shapes alone are the same markup that a drawing of several icons holds.
    alone = ET.fromstring(f'<g xmlns="{SVG}">{icons.SHAPES[name]}</g>')
    assert [(child.tag, dict(child.attrib)) for child in alone] == shapes


@pytest.mark.parametrize('name', NAMES)
def test_every_line_of_each_icon_lies_inside_its_grid(name):
    root, shapes = drawing(name)
    left, top, width, height = (float(number) for number in root.get('viewBox').split())
    # A line has half its width on each side of its path, so its path keeps that far from each edge.
    margin = float(root.get('stroke-width')) / 2
    for tag, attributes in shapes:
        points = extent(tag.removeprefix(f'{{{SVG}}}'), attributes)
        assert points, (tag, attributes)
        for x, y in points:
            assert left + margin <= x <= left + width - margin, (tag, attributes, x)
            assert top + margin <= y <= top + height - margin, (tag, attributes, y)
        if tag != f'{{{SVG}}}path':
            (x0, y0), (x1, y1) = points
            assert x1 > x0 and y1 > y0, (tag, attributes)


def test_no_two_icons_draw_the_same_picture():
    pictures = [tuple((tag, tuple(sorted(a.items()))) for tag, a in drawing(name)[1]) for name in NAMES]
    assert len(set(pictures)) == len(NAMES)


def test_a_name_that_is_not_an_icon_raises():
    assert 'lamp' not in style.ICONS
    with pytest.raises(ValueError, match='not an icon'):
        icons.svg('lamp')


def test_the_path_reader_of_these_tests_finds_each_point_of_a_known_path():
    # A unit square drawn with each kind of line, then a half circle of radius 2 from (5, 1) to (9, 1)
    # that bends down to (7, 3): the y axis of the screen points down.
    points = path_points('M1 1h1v1H1zm4 0a2 2 0 0 0 4 0')
    assert points[:5] == [(1, 1), (2, 1), (2, 2), (1, 2), (1, 1)]
    half = points[5:]
    assert half[0] == (5, 1) and half[-1] == (9, 1)
    assert max(y for _, y in half) == pytest.approx(3)
    assert all(math.dist(point, (7, 1)) == pytest.approx(2) for point in half)
    # An arc can leave the grid between two end points inside it: the lower half of the circle of
    # radius 8.5 through (3.5, 17) and (20.5, 17) goes down to 17 + 8.5.
    assert max(y for _, y in path_points('M3.5 17a8.5 8.5 0 1 0 17 0')) == pytest.approx(25.5)
    # A curve after a curve reflects its last control point about the current point.
    assert path_points('M0 0c1 1 2 1 3 0s2-1 3 0')[4:] == [(4, -1), (5, -1), (6, 0)]
