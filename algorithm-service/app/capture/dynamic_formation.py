from __future__ import annotations

from dataclasses import dataclass
from math import asin, atan2, cos, degrees, hypot, pi, sin
from typing import Iterable, Sequence


@dataclass(frozen=True)
class FormationSlot:
    radius: float
    angle: float
    altitude: float
    ring: int

    def point(self, target: Sequence[float]) -> tuple[float, float, float]:
        return (
            float(target[0]) + self.radius * cos(self.angle),
            float(target[1]) + self.radius * sin(self.angle),
            float(target[2]) + self.altitude,
        )


@dataclass(frozen=True)
class CaptureAssessment:
    capability: str
    ready: bool
    target_inside: bool
    combined_max_gap_deg: float
    radial_error: float
    participating: int
    required: int


def maximum_capture_gap_deg(count: int) -> float:
    """Maximum visually credible opening for an executed containment ring.

    The limit tightens as more members are available.  A three-member ring
    needs 120 degrees even when it is a perfect equilateral triangle, while
    four or more members are never allowed a gap wider than 90 degrees.
    Dense teams converge toward a 45-degree ceiling.  This keeps sparse valid
    rings achievable without letting a broad arc or horseshoe count as a
    completed encirclement.
    """
    count = max(1, int(count))
    if count <= 3:
        return 120.0
    ideal_gap = 360.0 / count
    return min(90.0, max(45.0, ideal_gap * 1.8))


def _ring_capacity(radius: float, spacing: float) -> int:
    if radius <= spacing / 2.0:
        return 2
    return max(3, int(pi / asin(min(0.999, spacing / (2.0 * radius)))))


def build_formation_slots(
    count: int,
    *,
    kind: str,
    phase: float,
    minimum_radius: float,
    minimum_spacing: float,
    altitude: float = 0.0,
) -> list[FormationSlot]:
    """Build deterministic concentric rings without a fleet-size ceiling.

    A single ring grows beyond the available water very quickly.  Filling
    concentric rings to their chord-spacing capacity keeps adjacent rendered
    hulls clear and lets 100+ craft remain a valid input instead of silently
    truncating the fleet.
    """
    count = max(0, int(count))
    if count == 0:
        return []
    spacing = max(0.1, float(minimum_spacing))
    radius = max(float(minimum_radius), spacing)
    radial_step = spacing * (1.22 if kind.upper() == "USV" else 1.08)
    remaining = count
    ring = 0
    slots: list[FormationSlot] = []
    while remaining:
        capacity = _ring_capacity(radius, spacing)
        ring_count = min(remaining, capacity)
        # Alternate half a slot between rings so radial neighbours do not
        # form collision-prone spokes.
        ring_phase = phase + (pi / ring_count if ring % 2 else 0.0)
        for index in range(ring_count):
            slots.append(FormationSlot(
                radius=radius,
                angle=ring_phase + 2.0 * pi * index / ring_count,
                altitude=altitude + (ring * 2.4 if kind.upper() == "UAV" else 0.0),
                ring=ring,
            ))
        remaining -= ring_count
        ring += 1
        radius += radial_step
    return slots


def _max_angular_gap(points: Sequence[Sequence[float]], target: Sequence[float]) -> float:
    if len(points) < 2:
        return 2.0 * pi
    angles = sorted(
        atan2(float(point[1]) - float(target[1]), float(point[0]) - float(target[0]))
        % (2.0 * pi)
        for point in points
    )
    return max(
        (angles[(index + 1) % len(angles)] - angles[index]) % (2.0 * pi)
        for index in range(len(angles))
    )


def _target_inside_convex_hull(points: Sequence[Sequence[float]], target: Sequence[float]) -> bool:
    """For a point-centred polar set, no empty half-plane means containment."""
    return len(points) >= 3 and _max_angular_gap(points, target) < pi - 1e-6


def assess_capture(
    positions: Sequence[Sequence[float]],
    assigned_slots: Sequence[FormationSlot],
    target: Sequence[float],
    *,
    radial_tolerance: float,
) -> CaptureAssessment:
    total = len(positions)
    capability = "INTERCEPT_ONLY" if total < 3 else "ENCIRCLEMENT"
    if total == 0 or len(assigned_slots) != total:
        return CaptureAssessment(capability, False, False, 360.0, float("inf"), 0, max(3, total))

    errors = []
    for point, slot in zip(positions, assigned_slots):
        expected = slot.point(target)
        errors.append(hypot(float(point[0]) - expected[0], float(point[1]) - expected[1]))
    participating = sum(error <= radial_tolerance for error in errors)
    max_gap = _max_angular_gap(positions, target)
    inside = _target_inside_convex_hull(positions, target)
    ready = (
        total >= 3
        and participating == total
        and inside
        and degrees(max_gap) <= maximum_capture_gap_deg(total) + 1e-6
    )
    return CaptureAssessment(
        capability=capability,
        ready=ready,
        target_inside=inside,
        combined_max_gap_deg=max_gap * 180.0 / pi,
        radial_error=max(errors, default=0.0),
        participating=participating,
        required=max(3, total),
    )
