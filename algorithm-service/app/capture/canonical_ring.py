from __future__ import annotations

from dataclasses import dataclass
from math import asin, atan2, cos, degrees, hypot, pi, sin
from typing import Iterable, Mapping, Sequence


@dataclass(frozen=True)
class RingMember:
    code: str
    kind: str
    x: float
    y: float
    z: float = 0.0
    heading: float | None = None


@dataclass(frozen=True)
class RingSlot:
    index: int
    angle: float
    radius: float
    altitude: float

    def point(self, target: Sequence[float]) -> tuple[float, float, float]:
        return (
            float(target[0]) + cos(self.angle) * self.radius,
            float(target[1]) + sin(self.angle) * self.radius,
            float(target[2]) + self.altitude,
        )


@dataclass(frozen=True)
class RingAssessment:
    ready: bool
    blocker: str
    member_count: int
    arrived_count: int
    arrival_ratio: float
    maximum_slot_error_m: float
    maximum_gap_deg: float
    allowed_gap_deg: float
    minimum_separation_m: float
    radial_spread_m: float
    target_inside: bool
    inward_oriented_usv_count: int
    usv_count: int
    maximum_usv_heading_error_deg: float


def required_ring_members(radius_m: float, maximum_slot_spacing_m: float) -> int:
    """Smallest useful team for a readable collision-safe ring."""
    radius = max(1.0, float(radius_m))
    spacing = max(1.0, float(maximum_slot_spacing_m))
    return max(6, int((2.0 * pi * radius) / spacing + 0.999999))


def ring_radius(member_count: int, minimum_spacing_m: float = 14.0) -> float:
    """One horizontal ring whose chord distance remains physically readable."""
    count = max(3, int(member_count))
    spacing = max(7.5, float(minimum_spacing_m))
    chord_radius = spacing / (2.0 * sin(pi / count))
    return max(24.0, min(72.0, chord_radius))


def _minimum_pairwise_distance(points: Sequence[Sequence[float]]) -> float:
    minimum = float("inf")
    for index, left in enumerate(points):
        for right in points[index + 1:]:
            minimum = min(
                minimum,
                hypot(float(left[0]) - float(right[0]), float(left[1]) - float(right[1])),
            )
    return minimum


def _maximum_gap_deg(points: Sequence[Sequence[float]], target: Sequence[float]) -> float:
    if len(points) < 2:
        return 360.0
    angles = sorted(
        atan2(float(point[1]) - float(target[1]), float(point[0]) - float(target[0]))
        % (2.0 * pi)
        for point in points
    )
    return degrees(max(
        (angles[(index + 1) % len(angles)] - angles[index]) % (2.0 * pi)
        for index in range(len(angles))
    ))


def _balanced_kinds(members: Sequence[RingMember]) -> list[str]:
    """Spread an asymmetric UAV/USV mix around the full circumference."""
    counts: dict[str, int] = {}
    for member in members:
        kind = member.kind.upper()
        counts[kind] = counts.get(kind, 0) + 1
    remaining = dict(counts)
    ordered: list[str] = []
    total = len(members)
    debt = {kind: 0.0 for kind in counts}
    for _ in range(total):
        for kind, count in counts.items():
            debt[kind] += count / total
        available = [kind for kind, count in remaining.items() if count > 0]
        chosen = max(available, key=lambda kind: (debt[kind], remaining[kind], kind))
        ordered.append(chosen)
        remaining[chosen] -= 1
        debt[chosen] -= 1.0
    return ordered


def build_canonical_slots(
    members: Sequence[RingMember],
    target: Sequence[float],
    *,
    phase: float = 0.0,
    minimum_spacing_m: float = 14.0,
) -> dict[str, RingSlot]:
    """Assign stable, evenly distributed slots without crossing trajectories.

    Device types are distributed around one horizontal circle. Within each
    type, angular order is preserved, and the best cyclic rotation is selected
    to minimise travel. This is deterministic and remains inexpensive at 128+
    devices because assignment happens only when group membership changes.
    """
    if not members:
        return {}
    count = len(members)
    radius = ring_radius(count, minimum_spacing_m)
    target_x, target_y = float(target[0]), float(target[1])
    kind_pattern = _balanced_kinds(members)
    slots_by_kind: dict[str, list[RingSlot]] = {}
    for index, kind in enumerate(kind_pattern):
        angle = (float(phase) + 2.0 * pi * index / count) % (2.0 * pi)
        slots_by_kind.setdefault(kind, []).append(RingSlot(
            index=index,
            angle=angle,
            radius=radius,
            altitude=25.0 + (index % 3) * 2.5 if kind == "UAV" else 0.0,
        ))
    result: dict[str, RingSlot] = {}
    for kind, kind_slots in slots_by_kind.items():
        kind_members = sorted(
            (member for member in members if member.kind.upper() == kind),
            key=lambda member: atan2(member.y - target_y, member.x - target_x) % (2.0 * pi),
        )
        kind_slots = sorted(kind_slots, key=lambda slot: slot.angle)
        size = len(kind_members)
        best_cost = float("inf")
        best_rotation = 0
        for rotation in range(size):
            cost = 0.0
            for index, member in enumerate(kind_members):
                slot = kind_slots[(index + rotation) % size]
                px, py, _ = slot.point(target)
                cost += hypot(member.x - px, member.y - py)
            if cost < best_cost:
                best_cost = cost
                best_rotation = rotation
        for index, member in enumerate(kind_members):
            result[member.code] = kind_slots[(index + best_rotation) % size]
    return result


def assess_canonical_ring(
    members: Sequence[RingMember],
    target: Sequence[float],
    slots: Mapping[str, RingSlot],
    *,
    slot_tolerance_m: float = 3.5,
    minimum_separation_m: float = 7.0,
    require_inward_usv_heading: bool = False,
    usv_heading_tolerance_deg: float = 8.0,
) -> RingAssessment:
    """The sole visual completion contract, evaluated on emitted positions."""
    if len(members) < 3 or len(slots) != len(members):
        return RingAssessment(
            False, "INCOMPLETE_ASSIGNMENT", len(members), 0, 0.0,
            float("inf"), 360.0, 0.0, 0.0, float("inf"), False,
            0, sum(member.kind.upper() == "USV" for member in members),
            180.0,
        )
    points = [(member.x, member.y, member.z) for member in members]
    errors = []
    radii = []
    for member in members:
        expected = slots[member.code].point(target)
        errors.append(hypot(member.x - expected[0], member.y - expected[1]))
        radii.append(hypot(member.x - float(target[0]), member.y - float(target[1])))
    arrived = sum(error <= slot_tolerance_m for error in errors)
    max_error = max(errors, default=float("inf"))
    max_gap = _maximum_gap_deg(points, target)
    ideal_gap = 360.0 / len(members)
    allowed_gap = min(120.0, ideal_gap * 1.25)
    minimum_separation = _minimum_pairwise_distance(points)
    spread = max(radii) - min(radii)
    target_inside = max_gap < 180.0 - 1e-6
    usv_heading_errors = []
    for member in members:
        if member.kind.upper() != "USV":
            continue
        if member.heading is None:
            usv_heading_errors.append(180.0)
            continue
        inward_heading = degrees(atan2(
            float(target[1]) - member.y,
            float(target[0]) - member.x,
        )) % 360.0
        error = abs((float(member.heading) - inward_heading + 180.0) % 360.0 - 180.0)
        usv_heading_errors.append(error)
    oriented_usvs = sum(
        error <= float(usv_heading_tolerance_deg)
        for error in usv_heading_errors
    )
    max_usv_heading_error = max(usv_heading_errors, default=0.0)
    if arrived != len(members):
        blocker = "SLOT_ARRIVAL"
    elif max_gap > allowed_gap + 0.25:
        blocker = "ANGULAR_GAP"
    elif spread > max(4.0, slot_tolerance_m * 1.5):
        blocker = "RADIAL_SPREAD"
    elif minimum_separation < minimum_separation_m:
        blocker = "MINIMUM_SEPARATION"
    elif not target_inside:
        blocker = "TARGET_OUTSIDE_RING"
    elif (
        require_inward_usv_heading
        and oriented_usvs != len(usv_heading_errors)
    ):
        blocker = "USV_HEADING_ALIGNMENT"
    else:
        blocker = "NONE"
    return RingAssessment(
        ready=blocker == "NONE",
        blocker=blocker,
        member_count=len(members),
        arrived_count=arrived,
        arrival_ratio=arrived / len(members),
        maximum_slot_error_m=round(max_error, 3),
        maximum_gap_deg=round(max_gap, 3),
        allowed_gap_deg=round(allowed_gap, 3),
        minimum_separation_m=round(minimum_separation, 3),
        radial_spread_m=round(spread, 3),
        target_inside=target_inside,
        inward_oriented_usv_count=oriented_usvs,
        usv_count=len(usv_heading_errors),
        maximum_usv_heading_error_deg=round(max_usv_heading_error, 3),
    )


def allocate_balanced_groups(
    codes: Iterable[str],
    target_count: int,
    positions: Mapping[str, Sequence[float]] | None = None,
    targets: Sequence[Sequence[float] | None] | None = None,
) -> list[list[str]]:
    """Stable capacity-balanced allocation with travel distance as the cost."""
    groups = max(1, int(target_count))
    result: list[list[str]] = [[] for _ in range(groups)]
    unassigned = set(codes)
    positions = positions or {}
    targets = targets or [None] * groups

    def distance(code: str, target_index: int) -> float:
        point = positions.get(code)
        target = targets[target_index] if target_index < len(targets) else None
        if point is None or target is None:
            return 0.0
        return hypot(float(point[0]) - float(target[0]), float(point[1]) - float(target[1]))

    quotas = [len(unassigned) // groups + (1 if index < len(unassigned) % groups else 0)
              for index in range(groups)]
    while unassigned:
        best: tuple[float, str, int] | None = None
        for code in sorted(unassigned):
            for target_index in range(groups):
                if len(result[target_index]) >= quotas[target_index]:
                    continue
                fill = len(result[target_index]) / max(1, quotas[target_index])
                candidate = (distance(code, target_index) + fill * 25.0, code, target_index)
                if best is None or candidate < best:
                    best = candidate
        if best is None:
            break
        _, code, target_index = best
        result[target_index].append(code)
        unassigned.remove(code)
    return result
