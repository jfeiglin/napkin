"""Evidence required to compare a physical contact with a firing that stopped its stock inside the band."""

from bisect import bisect_left, bisect_right
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from difflib import SequenceMatcher
from math import inf, isfinite, nextafter, ulp

from numpy.polynomial.chebyshev import chebder, chebval

from napkin.core import expr as nodes
from napkin.engine.timeline.reads import lazily


def compared_fire_details(entry):
    """A band marker annotates rows of the firing's existing near evidence."""
    rows = entry.detail('band_entry')
    if rows is None:
        return entry.details
    if entry.kind != 'fire' or not rows:
        raise ValueError(f'band_entry without a firing: {entry!r}')
    for row in rows:
        origin, _, raw_gap, raw_band = row
        try:
            gap, band = Decimal(str(raw_gap)), Decimal(str(raw_band))
        except InvalidOperation as exc:
            raise ValueError(f'invalid band_entry: {row!r}') from exc
        if not (
            row in (entry.detail('near') or ())
            and origin == entry.part
            and gap.is_finite()
            and band.is_finite()
            and 0 < gap.copy_abs() <= band
        ):
            raise ValueError(f'invalid band_entry: {row!r}')
    return tuple((k, value) for k, value in entry.details if k != 'band_entry')


def paired_fire_details(left, right):
    """Compare common near evidence and all other fields. A new marker may add its own near row."""

    def comparable(entry, other):
        fields = dict(compared_fire_details(entry))
        marked = entry.detail('band_entry') or ()
        other_origins = {row[:2] for row in other.detail('near') or ()}
        if marked:
            rows = tuple(row for row in fields['near'] if row not in marked or row[:2] in other_origins)
            if rows:
                fields['near'] = rows
            else:
                del fields['near']
        return tuple(fields.items())

    return comparable(left, right), comparable(right, left)


def decision_identity(entry):
    """Include the physical contact surface even when two contacts share an owner and part."""
    surfaces = ()
    if entry.kind == 'contact':
        surfaces = tuple(
            (row[0], row[1].rsplit(' and the moment at ', 1)[0]) for row in entry.detail('near') or ()
        )
    return entry.kind, entry.owner, entry.part, entry.round, surfaces


@dataclass(frozen=True)
class BandPreemption:
    contact_side: str
    contact_indices: tuple
    fire_indices: tuple
    stock: str
    bound: str
    target: float
    switches: tuple
    firing: str
    fire_time: float
    contact_time: float
    remainder: float
    band: float

    @property
    def marked_side(self):
        return 'after' if self.contact_side == 'before' else 'before'


def _surface(node, stock, bound):
    """Compare a single named stock directly to its declared bound, in either operand order."""
    if isinstance(node, nodes.Compare) and len(node.ops) == 1:
        left, right = node.operands
        if left == nodes.ref(stock) and right == bound:
            return node.ops[0], 1
        if right == nodes.ref(stock) and left == bound:
            inverse = {'ge': 'le', 'le': 'ge', 'lt': 'gt', 'gt': 'lt', 'eq': 'eq', 'ne': 'ne'}
            return inverse[node.ops[0]], -1
    return None


def _fire_surface(reader, fire, stock, bound, side):
    """The marked comparison must be the model's completion condition on this stock's bound."""
    valid = {row[1]: row for row in fire.detail('band_entry') or ()}
    pending = [tr.test for tr in reader.plan.triggers if (tr.origin, tr.member) == (fire.part, fire.owner)]
    while pending:
        node = pending.pop()
        surface = _surface(node, stock, bound)
        if surface and nodes.notation(node) in valid:
            op, sign = surface
            _, _, gap, band = valid[nodes.notation(node)]
            residue = sign * float(gap)
            if (side == 'lower' and op in ('le', 'eq') and residue > 0) or (
                side == 'upper' and op in ('ge', 'eq') and residue < 0
            ):
                return residue, float(band)
        pending.extend(node.children)
    return None


def _held(history, start, end):
    """Check every recorded piece on the interval, including its landed right edge."""
    pieces = history.pieces
    times = [p.t for p in pieces]
    i = bisect_right(times, start) - 1
    if i < 0:
        return False
    value = pieces[i].at(start)
    return all(
        p.rate == 0 and (p.curve is None or not any(p.curve.coefficients[1:])) and p.value == value
        for p in pieces[i : bisect_right(times, end)]
    )


def _approaches(history, at, side):
    """Use the left-hand derivative. A stock already resting here cannot lose a future contact."""
    i = bisect_left([p.t for p in history.pieces], at) - 1
    if i < 0:
        return False
    p = history.pieces[i]
    rate = p.rate
    if p.curve is not None:
        length = p.curve.length
        u = 2 * (at - p.t) / length - 1
        rate = 2 * chebval(u, chebder(p.curve.coefficients)) / length
    return rate < 0 if side == 'lower' else rate > 0


def _switch_caused_by_bound(reader, entry, stock, bound, at, side):
    """A leg at this endpoint switches off at a request or capacity conditional on this very bound."""
    flow = reader.plan.flows.get(entry.part)
    if flow is None:
        return False
    before = nextafter(at, -inf)
    for leg in flow.connections:
        if stock not in (leg.source, leg.sink):
            continue
        for name in (leg.request, leg.capacity):
            if name is None:
                continue
            definition = reader._definition(name, before).node
            if not isinstance(definition, nodes.IfElse):
                continue
            surface = _surface(definition.test, stock, bound)
            if surface is None:
                continue
            op = surface[0]
            approached = op in (('gt', 'ge', 'ne') if side == 'lower' else ('lt', 'le', 'ne'))
            landed = op in ('eq', 'le', 'ge')
            if approached == landed:
                continue
            running = definition.body if approached else definition.orelse
            stopped = definition.body if landed else definition.orelse
            # Test the two branches in the same state to distinguish a change in some other input.
            read = lambda name: reader.at(name, before)  # noqa: E731
            if (
                lazily(running, read, reader.units, before) <= 0
                or lazily(stopped, read, reader.units, before) != 0
            ):
                continue
            rates = reader.record.history(reader.plan.values[f'{leg.name}.actual_rate'].key)
            if rates.at(before) != 0 and rates.at(at) == 0:
                return True
    return False


def _proof(contacts, paired_fire, fire, physical, marked, crossing):
    if not fire.detail('band_entry') or fire.kind != 'fire':
        return None
    compared_fire_details(fire)
    bounds, switches = [], []
    for entry in contacts:
        if entry.kind != 'contact' or (entry.t, entry.round) != (paired_fire.t, paired_fire.round):
            return None
        near = decision_identity(entry)[-1]
        if len(near) != 1 or near[0][0] != entry.part:
            return None
        description = near[0][1]
        if description == f'switch of {entry.part}':
            switches.append(entry)
        elif description in (f'lower bound of {entry.part}', f'upper bound of {entry.part}'):
            bounds.append((entry, description.split()[0]))
        else:
            return None
    if len(bounds) != 1:
        return None
    entry, side = bounds[0]
    if entry.detail('located') is None:
        return None
    stock, at = entry.part, float(entry.detail('located'))
    if not fire.t < at or abs(paired_fire.t - fire.t) > 1e-6 * float(physical.record.manifest.horizon):
        return None
    if any(e.detail('located') is None or abs(float(e.detail('located')) - at) > crossing for e in switches):
        return None
    declaration = physical.plan.values[stock]
    bound = getattr(declaration, side)
    evidence = _fire_surface(marked, fire, stock, bound, side)
    if evidence is None:
        return None
    residue, band = evidence
    target = float(lazily(bound, lambda name: marked.at(name, fire.t), marked.units, fire.t))
    old = physical.record.history(declaration.key)
    new = marked.record.history(marked.plan.values[stock].key)
    landed = float(new.at(fire.t))
    # The public physical stock and stored piece can differ in their last bits.
    eps = 64 * ulp(max(1.0, abs(landed), abs(target), marked.comparison_scales.get(stock, 0.0)))
    if not (isfinite(residue) and isfinite(band) and 0 < abs(landed - target) <= band):
        return None
    if abs((landed - target) - residue) > eps or abs(float(old.at(entry.t)) - target) > band:
        return None
    until = min(marked.record.end, max(at, float(paired_fire.t)) + crossing)
    if not (_approaches(new, fire.t, side) and _approaches(old, entry.t, side) and _held(new, fire.t, until)):
        return None
    for switch in switches:
        if not (
            _switch_caused_by_bound(physical, switch, stock, bound, entry.t, side)
            and _switch_caused_by_bound(marked, switch, stock, bound, fire.t, side)
        ):
            return None
    return stock, side, target, tuple(e.part for e in switches), fire.part, fire.t, at, residue, band


def band_preemptions(left_entries, right_entries, left_reader, right_reader, crossing):
    """Return proven omissions. Indices refer to the supplied remainder-filtered decision sequences.

    Every later decision identity must match in order. The caller compares the details and
    numerical observations of every remaining row with the usual trace acceptance rules.
    """
    a, b = tuple(map(decision_identity, left_entries)), tuple(map(decision_identity, right_entries))
    if a == b:
        return ()
    blocks = SequenceMatcher(a=a, b=b, autojunk=False).get_opcodes()
    result = []
    for tag, i, j, k, stop in blocks:
        if tag not in ('insert', 'delete') or a[j:] != b[stop:] or j == len(a):
            continue
        left_has_contacts = tag == 'delete'
        physical, marked = (left_reader, right_reader) if left_has_contacts else (right_reader, left_reader)
        contacts = left_entries[i:j] if left_has_contacts else right_entries[k:stop]
        for f, g in zip(range(j, len(a)), range(stop, len(b)), strict=True):
            x, y = left_entries[f], right_entries[g]
            ref, fire = (x, y) if left_has_contacts else (y, x)
            if ref.t != contacts[0].t:
                break
            try:
                found = _proof(contacts, ref, fire, physical, marked, crossing)
            except LookupError:
                # A selected-path record can omit the stock or its leg. There is no proof in that record.
                found = None
            if found:
                indices = range(i, j) if left_has_contacts else range(k, stop)
                result.append(
                    BandPreemption('before' if left_has_contacts else 'after', tuple(indices), (f, g), *found)
                )
                break
    return tuple(result)
