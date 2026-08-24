from __future__ import annotations

from dataclasses import dataclass
from math import atan2, ceil, degrees, hypot, pi
from typing import Mapping, Sequence


@dataclass(frozen=True)
class ContainmentAssessment:
    ready: bool
    target_inside: bool
    max_gap_deg: float
    allowed_gap_deg: float
    minimum_radius_m: float
    maximum_radius_m: float
    radial_spread_m: float
    participating: int
    required: int
    blocker: str
    sector_count: int
    covered_sectors: int
    minimum_separation_m: float
    required_separation_m: float
    uav_count: int
    usv_count: int
    invalid: int
    stationary: int
    detached: int


def allowed_containment_gap_deg(count: int) -> float:
    """Return the strict, count-aware maximum opening for a containment ring."""
    count = max(1, int(count))
    if count <= 3:
        return 120.0
    ideal_gap = 360.0 / count
    return min(120.0, max(42.0, ideal_gap * 1.35))


def _angles(points: Sequence[Sequence[float]], target: Sequence[float]) -> list[float]:
    return sorted(
        atan2(float(point[1]) - float(target[1]), float(point[0]) - float(target[0]))
        % (2.0 * pi)
        for point in points
    )


def _max_gap_deg(points: Sequence[Sequence[float]], target: Sequence[float]) -> float:
    angles = _angles(points, target)
    if len(angles) < 2:
        return 360.0
    return degrees(max(
        (angles[(index + 1) % len(angles)] - angles[index]) % (2.0 * pi)
        for index in range(len(angles))
    ))


def _sector_coverage(
    points: Sequence[Sequence[float]],
    target: Sequence[float],
    sector_count: int,
) -> tuple[int, int]:
    if sector_count <= 0:
        return 0, 0
    occupied = set()
    for point in points:
        angle = atan2(float(point[1]) - float(target[1]), float(point[0]) - float(target[0]))
        sector = int((angle % (2.0 * pi)) / (2.0 * pi) * sector_count)
        occupied.add(min(sector_count - 1, sector))
    return len(occupied), sector_count


def _minimum_pairwise_distance(points: Sequence[Sequence[float]]) -> float:
    minimum = float("inf")
    for index, left in enumerate(points):
        for right in points[index + 1:]:
            minimum = min(
                minimum,
                hypot(float(left[0]) - float(right[0]), float(left[1]) - float(right[1])),
            )
    return minimum


def assess_containment(
    positions: Sequence[Sequence[float]],
    target: Sequence[float],
    *,
    required_count: int | None = None,
    minimum_radius_m: float = 0.0,
    maximum_radius_m: float = float("inf"),
    maximum_radial_spread_m: float | None = None,
    participating: int | None = None,
    tolerance_deg: float = 0.0,
    device_types: Sequence[str] | None = None,
    minimum_type_counts: Mapping[str, int] | None = None,
    sector_count: int | None = None,
    minimum_pairwise_separation_m: float = 0.0,
    valid: Sequence[bool] | None = None,
    stationary: Sequence[bool] | None = None,
    detached: Sequence[bool] | None = None,
) -> ContainmentAssessment:
    """Evaluate the single authoritative geometric containment contract."""
    required = max(3, int(required_count if required_count is not None else len(positions)))
    actual_participating = len(positions) if participating is None else int(participating)
    radii = [
        hypot(float(point[0]) - float(target[0]), float(point[1]) - float(target[1]))
        for point in positions
    ]
    minimum = min(radii, default=0.0)
    maximum = max(radii, default=0.0)
    spread = maximum - minimum if radii else float("inf")
    max_gap = _max_gap_deg(positions, target)
    allowed_gap = allowed_containment_gap_deg(len(positions))
    types = [str(value).upper() for value in device_types or []]
    uav_count = sum(value == "UAV" for value in types)
    usv_count = sum(value == "USV" for value in types)
    # An asymmetric two-layer fleet has a hard geometric floor: the denser
    # layer's own chord gap cannot be filled by fewer members in the other
    # layer. Keep the contract strict, while avoiding an impossible threshold
    # for valid 4+5, 3+6, etc. assignments.
    if uav_count and usv_count and uav_count != usv_count:
        allowed_gap = max(allowed_gap, 360.0 / max(uav_count, usv_count))
    target_inside = len(positions) >= 3 and max_gap < 180.0 - 1e-6
    requested_sectors = max(
        3,
        min(
            len(positions),
            int(sector_count) if sector_count is not None
            else ceil(360.0 / max(1.0, allowed_gap)),
        ),
    ) if positions else 0
    covered_sectors, _ = _sector_coverage(positions, target, requested_sectors)
    minimum_separation = _minimum_pairwise_distance(positions)
    invalid_count = sum(value is False for value in (valid or []))
    stationary_count = sum(value is True for value in (stationary or []))
    detached_count = sum(value is True for value in (detached or []))
    type_counts_ok = all(
        (uav_count if str(kind).upper() == "UAV" else usv_count) >= int(required)
        for kind, required in (minimum_type_counts or {}).items()
    )
    validity_ok = invalid_count == 0 and stationary_count == 0 and detached_count == 0

    if len(positions) < 3:
        blocker = "INSUFFICIENT_AGENTS"
    elif actual_participating != required:
        blocker = "INCOMPLETE_PARTICIPATION"
    elif not target_inside:
        blocker = "TARGET_OUTSIDE_HULL"
    elif max_gap > allowed_gap + tolerance_deg:
        blocker = "ANGULAR_GAP"
    elif not type_counts_ok:
        blocker = "TYPE_LAYER"
    elif covered_sectors < requested_sectors:
        blocker = "SECTOR_COVERAGE"
    elif minimum < minimum_radius_m:
        blocker = "INNER_RADIUS"
    elif maximum > maximum_radius_m:
        blocker = "OUTER_RADIUS"
    elif maximum_radial_spread_m is not None and spread > maximum_radial_spread_m:
        blocker = "RADIAL_SPREAD"
    elif minimum_separation < float(minimum_pairwise_separation_m):
        blocker = "MINIMUM_SEPARATION"
    elif not validity_ok:
        blocker = "INVALID_PARTICIPANT"
    else:
        blocker = "NONE"

    return ContainmentAssessment(
        ready=blocker == "NONE",
        target_inside=target_inside,
        max_gap_deg=round(max_gap, 2),
        allowed_gap_deg=round(allowed_gap, 2),
        minimum_radius_m=round(minimum, 2),
        maximum_radius_m=round(maximum, 2),
        radial_spread_m=round(spread, 2),
        participating=actual_participating,
        required=required,
        blocker=blocker,
        sector_count=requested_sectors,
        covered_sectors=covered_sectors,
        minimum_separation_m=round(minimum_separation, 2),
        required_separation_m=round(float(minimum_pairwise_separation_m), 2),
        uav_count=uav_count,
        usv_count=usv_count,
        invalid=invalid_count,
        stationary=stationary_count,
        detached=detached_count,
    )
