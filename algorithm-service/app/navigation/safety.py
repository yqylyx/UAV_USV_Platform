from __future__ import annotations

from dataclasses import dataclass
from math import cos, hypot, pi, sin
from typing import Dict, Iterable, List, Mapping, Sequence, Tuple


DEFAULT_SCENE_MAP: Dict[str, object] = {
    "bounds": [-36.0, 36.0, -30.0, 30.0],
    "obstacles": [
        {"id": "shore-base", "label": "停机坪与岸基平台", "shape": "rect", "bounds": [-35.0, -20.0, -8.5, 8.5], "height": 8.0},
        {"id": "lighthouse", "label": "灯塔安全区", "shape": "circle", "center": [-6.0, 15.5], "radius": 2.4, "height": 28.0},
        {"id": "north-shore", "label": "北侧岸线", "shape": "rect", "bounds": [-36.0, 36.0, 25.5, 30.0], "height": 15.0},
    ],
}


@dataclass(frozen=True)
class SafePoint:
    x: float
    y: float
    z: float
    adjusted: bool
    reason: str = ""


class SceneSafetyFilter:
    """Deterministic final safety layer shared by both algorithm adapters.

    USVs and water targets are constrained to navigable water. UAVs may overfly
    an obstacle only when their altitude clears the obstacle plus a margin.
    The filter also keeps pairwise separation without inventing a second motion
    model in Unity.
    """

    def __init__(self, scene_map: Dict[str, object] | None = None) -> None:
        self.scene_map = scene_map or DEFAULT_SCENE_MAP
        self.bounds = tuple(float(value) for value in self.scene_map["bounds"])
        self.obstacles = list(self.scene_map.get("obstacles", []))
        # Unity's USV hull is roughly six world units long after root scaling.
        # These are visual footprints, not algorithm capture radii.
        self.footprint_radius = {
            "UAV": 2.35,
            "USV": 3.25,
            "TARGET": 3.65,
            "CAPTURE_TARGET": 3.65,
            "ESCORT_TARGET": 3.65,
            "THREAT_TARGET": 3.25,
        }
        self.clearance_margin = 0.75
        # Numerical guard band for the projected solver.  The public safety
        # distance stays unchanged; this absorbs the tiny residual created
        # when shoreline projection and pair separation alternate.
        self.solver_guard_band = 0.12

    def constrain(
        self,
        previous: Sequence[float],
        proposed: Sequence[float],
        kind: str,
        occupied: Iterable[Sequence[float]] = (),
        separation: float = 1.4,
    ) -> SafePoint:
        px, py, pz = (float(value) for value in previous)
        x, y, z = (float(value) for value in proposed)
        min_x, max_x, min_y, max_y = self.bounds
        water_bound = kind.upper() in {"USV", "TARGET", "ESCORT_TARGET", "THREAT_TARGET"}
        footprint = self.radius_for(kind) if water_bound else 0.5
        x = min(max(x, min_x + footprint + 0.35), max_x - footprint - 0.35)
        y = min(max(y, min_y + footprint + 0.35), max_y - footprint - 0.35)

        for obstacle in self.obstacles:
            height = float(obstacle.get("height", 999.0))
            blocked = water_bound or z < height + 2.0
            obstacle_margin = footprint + 0.55 if water_bound else 0.8
            if not blocked or not self._contains(obstacle, x, y, margin=obstacle_margin):
                continue
            x, y = self._detour(obstacle, px, py, x, y, margin=obstacle_margin + 0.4)
            z = 0.0 if water_bound else z
            return self._separate(SafePoint(x, y, z, True, str(obstacle.get("id", "obstacle"))), occupied, separation)

        return self._separate(SafePoint(x, y, 0.0 if water_bound else z, False), occupied, separation)

    def radius_for(self, kind: str) -> float:
        return float(self.footprint_radius.get(kind.upper(), 2.0))

    def required_separation(self, first_kind: str, second_kind: str, first_z: float = 0.0, second_z: float = 0.0) -> float:
        first = first_kind.upper()
        second = second_kind.upper()
        first_air = first == "UAV"
        second_air = second == "UAV"
        # Air and surface craft are physically separated by altitude.
        if first_air != second_air and abs(first_z - second_z) >= 3.0:
            return 0.0
        return self.radius_for(first) + self.radius_for(second) + self.clearance_margin

    def resolve_group(
        self,
        proposals: Mapping[str, Tuple[str, Sequence[float]]],
        previous: Mapping[str, Sequence[float]] | None = None,
        fixed: Mapping[str, Tuple[str, Sequence[float]]] | None = None,
        iterations: int = 48,
    ) -> Dict[str, SafePoint]:
        """Resolve a whole fleet simultaneously against fixed targets.

        The old one-pass ordered projection could move a craft away from the
        last neighbour and back into an earlier one. Projected iterations make
        the final frame satisfy every pair, while fixed mission targets remain
        authoritative instead of being pushed around by their guards.
        """
        previous = previous or {}
        fixed = fixed or {}
        kinds = {code: kind.upper() for code, (kind, _) in proposals.items()}
        raw = {code: tuple(float(value) for value in point) for code, (_, point) in proposals.items()}
        positions: Dict[str, List[float]] = {}
        reasons: Dict[str, str] = {}

        for code, point in raw.items():
            old = tuple(float(value) for value in previous.get(code, point))
            candidate = self._limit_step(old, point, kinds[code]) if code in previous else point
            projected = self.constrain(old, candidate, kinds[code], (), 0.0)
            positions[code] = [projected.x, projected.y, projected.z]
            if projected.adjusted or candidate != point:
                reasons[code] = projected.reason or "motion-limit"

        fixed_points = {
            code: (kind.upper(), tuple(float(value) for value in point))
            for code, (kind, point) in fixed.items()
        }
        codes = list(positions)
        for _ in range(max(1, iterations)):
            largest_correction = 0.0
            for left_index, left_code in enumerate(codes):
                for right_code in codes[left_index + 1:]:
                    correction = self._project_pair(
                        left_code, positions[left_code], kinds[left_code],
                        right_code, positions[right_code], kinds[right_code],
                        move_first=True, move_second=True,
                    )
                    largest_correction = max(largest_correction, correction)
                    if correction > 0.0:
                        reasons[left_code] = reasons.get(left_code, "agent-separation")
                        reasons[right_code] = reasons.get(right_code, "agent-separation")
                for fixed_code, (fixed_kind, fixed_point) in fixed_points.items():
                    correction = self._project_pair(
                        left_code, positions[left_code], kinds[left_code],
                        fixed_code, list(fixed_point), fixed_kind,
                        move_first=True, move_second=False,
                    )
                    largest_correction = max(largest_correction, correction)
                    if correction > 0.0:
                        reasons[left_code] = reasons.get(left_code, "target-separation")

            # Pair projections can push a craft into shore or outside bounds;
            # re-project static constraints on every iteration.
            for code in codes:
                point = positions[code]
                before_static = tuple(point)
                old = tuple(float(value) for value in previous.get(code, raw[code]))
                projected = self.constrain(old, point, kinds[code], (), 0.0)
                positions[code] = [projected.x, projected.y, projected.z]
                static_correction = hypot(
                    projected.x - before_static[0],
                    projected.y - before_static[1],
                )
                largest_correction = max(largest_correction, static_correction)
                if projected.adjusted:
                    reasons[code] = projected.reason or reasons.get(code, "scene-boundary")
            if largest_correction < 1e-3:
                break

        result: Dict[str, SafePoint] = {}
        for code, point in positions.items():
            changed = hypot(point[0] - raw[code][0], point[1] - raw[code][1]) > 1e-4 or abs(point[2] - raw[code][2]) > 1e-4
            result[code] = SafePoint(point[0], point[1], point[2], changed, reasons.get(code, ""))
        return result

    def public_obstacles(self) -> List[Dict[str, object]]:
        return [{key: value for key, value in item.items() if key != "height"} for item in self.obstacles]

    def _separate(self, point: SafePoint, occupied: Iterable[Sequence[float]], separation: float) -> SafePoint:
        x, y, z = point.x, point.y, point.z
        adjusted = point.adjusted
        reason = point.reason
        for other in occupied:
            ox, oy = float(other[0]), float(other[1])
            dx, dy = x - ox, y - oy
            distance = hypot(dx, dy)
            if distance >= separation:
                continue
            if distance < 1e-6:
                dx, dy, distance = 1.0, 0.0, 1.0
            push = separation - distance
            x += dx / distance * push
            y += dy / distance * push
            adjusted = True
            reason = reason or "agent-separation"
        return SafePoint(x, y, z, adjusted, reason)

    def _limit_step(self, previous: Sequence[float], proposed: Sequence[float], kind: str) -> Tuple[float, float, float]:
        px, py, pz = (float(value) for value in previous)
        x, y, z = (float(value) for value in proposed)
        distance = hypot(x - px, y - py)
        max_step = 2.2 if kind.upper() == "UAV" else 1.35
        if distance <= max_step or distance < 1e-8:
            return x, y, z
        scale = max_step / distance
        return px + (x - px) * scale, py + (y - py) * scale, z

    def _project_pair(
        self,
        first_code: str,
        first: List[float],
        first_kind: str,
        second_code: str,
        second: List[float],
        second_kind: str,
        move_first: bool,
        move_second: bool,
    ) -> float:
        required = self.required_separation(first_kind, second_kind, first[2], second[2])
        if required <= 0.0:
            return 0.0
        required += self.solver_guard_band
        dx, dy = first[0] - second[0], first[1] - second[1]
        distance = hypot(dx, dy)
        overlap = required - distance
        if overlap <= 0.0:
            return 0.0
        if distance < 1e-6:
            # Stable across runs and independent of Python's randomized hash.
            seed = sum(ord(char) for char in first_code + "|" + second_code)
            angle = (seed % 360) * pi / 180.0
            dx, dy, distance = cos(angle), sin(angle), 1.0
        ux, uy = dx / distance, dy / distance
        movers = int(move_first) + int(move_second)
        share = overlap / max(1, movers)
        if move_first:
            first[0] += ux * share
            first[1] += uy * share
        if move_second:
            second[0] -= ux * share
            second[1] -= uy * share
        return overlap

    def _contains(self, obstacle: Dict[str, object], x: float, y: float, margin: float) -> bool:
        if obstacle.get("shape") == "circle":
            cx, cy = obstacle["center"]
            return hypot(x - float(cx), y - float(cy)) <= float(obstacle["radius"]) + margin
        left, right, bottom, top = (float(value) for value in obstacle["bounds"])
        return left - margin <= x <= right + margin and bottom - margin <= y <= top + margin

    def _detour(self, obstacle: Dict[str, object], px: float, py: float, x: float, y: float, margin: float) -> Tuple[float, float]:
        if obstacle.get("shape") == "circle":
            cx, cy = (float(value) for value in obstacle["center"])
            dx, dy = x - cx, y - cy
            distance = hypot(dx, dy) or 1.0
            radius = float(obstacle["radius"]) + margin
            return cx + dx / distance * radius, cy + dy / distance * radius
        left, right, bottom, top = (float(value) for value in obstacle["bounds"])
        candidates = [
            (left - margin, y),
            (right + margin, y),
            (x, bottom - margin),
            (x, top + margin),
        ]
        return min(candidates, key=lambda point: hypot(point[0] - px, point[1] - py))
