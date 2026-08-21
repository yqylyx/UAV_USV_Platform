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

# Task Center experiments use a dedicated open-water coordinate frame.  It is
# intentionally independent from the decorative shore, lighthouse and dock in
# the System Overview Unity scene: those props must neither appear in the
# experiment view nor act as invisible collision obstacles.
TASK_CENTER_SCENE_MAP: Dict[str, object] = {
    # The virtual fleet view needs enough open water for 100 UAVs and 100
    # USVs to remain visually separable before the mission converges.
    "bounds": [-65.0, 65.0, -55.0, 55.0],
    "obstacles": [],
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
        # These radii describe the rendered Unity footprints, not point-agent
        # math.  The current USV hull is about nine metres long and the escort
        # vessel about 13.5 metres, so the former 3.25/3.65 values could still
        # produce visibly intersecting meshes even though the centres passed
        # the old numerical check.
        self.footprint_radius = {
            "UAV": 3.0,
            # The 1.50 x 1.10 m USV has a 0.93 m circumscribed radius in
            # Unity. At the 0.18 presentation scale that is 5.17 scene metres;
            # 4.8 underestimated diagonal approaches and left only a few
            # centimetres of visible clearance.
            "USV": 5.2,
            # Capture/escort targets render the 13.5 m workboat at the same
            # presentation scale and therefore need its full hull radius.
            "TARGET": 7.3,
            "CAPTURE_TARGET": 7.3,
            "ESCORT_TARGET": 7.3,
            "THREAT_TARGET": 8.2,
        }
        self.clearance_margin = 1.4
        # Virtual UAVs are rendered in several altitude layers.  A layer gap
        # of 2 m is treated as vertically clear for horizontal planning; this
        # prevents a 100-aircraft fleet from being forced into one flat grid.
        self.airborne_layer_clearance = 2.0
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
        # The algorithm view is frequently inspected from directly overhead.
        # Even when altitude makes an air/surface pair physically valid, a
        # zero horizontal clearance renders both models on top of one another
        # and makes the result look like a collision.  Keep the full rendered
        # footprint separation for every pair in this presentation layer.
        if first_air != second_air and abs(first_z - second_z) >= 3.0:
            return self.radius_for(first) + self.radius_for(second) + self.clearance_margin
        return self.radius_for(first) + self.radius_for(second) + self.clearance_margin

    def _horizontal_required_separation(
        self,
        first_kind: str,
        second_kind: str,
        first_z: float,
        second_z: float,
    ) -> float:
        """Return the horizontal clearance needed after using altitude.

        Surface craft keep the existing 2-D footprint rule.  UAV pairs use
        their full 3-D clearance budget, so altitude separation reduces the
        horizontal distance required by the safety solver instead of forcing
        every aircraft into a flat plane.
        """
        required = self.required_separation(
            first_kind,
            second_kind,
            first_z,
            second_z,
        )
        if required <= 0.0:
            return 0.0
        if first_kind.upper() == "UAV" and second_kind.upper() == "UAV":
            # Keep a visible horizontal footprint even across altitude layers.
            # Vertical-only clearance is physically valid but makes aircraft
            # overlap in the global camera and hides the containment shape.
            return required
        return required

    def resolve_group(
        self,
        proposals: Mapping[str, Tuple[str, Sequence[float]]],
        previous: Mapping[str, Sequence[float]] | None = None,
        fixed: Mapping[str, Tuple[str, Sequence[float]]] | None = None,
        iterations: int = 48,
        max_steps: Mapping[str, float] | None = None,
    ) -> Dict[str, SafePoint]:
        """Resolve a whole fleet simultaneously against fixed targets.

        The old one-pass ordered projection could move a craft away from the
        last neighbour and back into an earlier one. Projected iterations make
        the final frame satisfy every pair, while fixed mission targets remain
        authoritative instead of being pushed around by their guards.
        """
        previous = previous or {}
        fixed = fixed or {}
        max_steps = {str(kind).upper(): float(value) for kind, value in (max_steps or {}).items()}
        kinds = {code: kind.upper() for code, (kind, _) in proposals.items()}
        raw = {code: tuple(float(value) for value in point) for code, (_, point) in proposals.items()}
        positions: Dict[str, List[float]] = {}
        reasons: Dict[str, str] = {}

        for code, point in raw.items():
            old = tuple(float(value) for value in previous.get(code, point))
            candidate = self._limit_step(old, point, kinds[code], max_steps.get(kinds[code])) if code in previous else point
            projected = self.constrain(old, candidate, kinds[code], (), 0.0)
            positions[code] = [projected.x, projected.y, projected.z]
            if projected.adjusted or candidate != point:
                reasons[code] = projected.reason or "motion-limit"

        fixed_points = {
            code: (kind.upper(), tuple(float(value) for value in point))
            for code, (kind, point) in fixed.items()
        }
        codes = list(positions)
        effective_iterations = min(
            iterations,
            12 if len(codes) >= 64 else 24 if len(codes) >= 32 else iterations,
        )
        self._project_all_constraints(
            codes,
            positions,
            kinds,
            previous,
            raw,
            fixed_points,
            reasons,
            effective_iterations,
            max_steps,
        )

        # Endpoint-only separation is insufficient: two craft may exchange
        # sides between frames while both endpoints remain legal.  Reject that
        # swept crossing and keep the previous safe pose for this frame.  The
        # planner receives the executed pose back and chooses a new route on
        # the next step, producing a visible slow/hold response instead of
        # tunnelling through another model.
        swept_adjusted = self._guard_swept_paths(
            codes,
            positions,
            kinds,
            previous,
            fixed_points,
            reasons,
        )
        if swept_adjusted:
            self._project_all_constraints(
                codes,
                positions,
                kinds,
                previous,
                raw,
                fixed_points,
                reasons,
                effective_iterations,
                max_steps,
            )

        result: Dict[str, SafePoint] = {}
        for code, point in positions.items():
            changed = hypot(point[0] - raw[code][0], point[1] - raw[code][1]) > 1e-4 or abs(point[2] - raw[code][2]) > 1e-4
            result[code] = SafePoint(point[0], point[1], point[2], changed, reasons.get(code, ""))
        return result

    def _project_all_constraints(
        self,
        codes: Sequence[str],
        positions: Dict[str, List[float]],
        kinds: Mapping[str, str],
        previous: Mapping[str, Sequence[float]],
        raw: Mapping[str, Sequence[float]],
        fixed_points: Mapping[str, Tuple[str, Sequence[float]]],
        reasons: Dict[str, str],
        iterations: int,
        max_steps: Mapping[str, float],
    ) -> None:
        for _ in range(max(1, iterations)):
            largest_correction = 0.0
            for left_code, right_code in self._nearby_pairs(codes, positions):
                    correction = self._project_pair(
                        left_code, positions[left_code], kinds[left_code],
                        right_code, positions[right_code], kinds[right_code],
                        move_first=True, move_second=True,
                    )
                    largest_correction = max(largest_correction, correction)
                    if correction > 0.0:
                        reasons[left_code] = reasons.get(left_code, "agent-separation")
                        reasons[right_code] = reasons.get(right_code, "agent-separation")
            for left_code in codes:
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
                if code in previous:
                    limited = self._limit_step(
                        previous[code],
                        positions[code],
                        kinds[code],
                        max_steps.get(kinds[code]),
                    )
                    motion_correction = hypot(
                        limited[0] - positions[code][0],
                        limited[1] - positions[code][1],
                    )
                    if motion_correction > 1e-6:
                        positions[code] = [limited[0], limited[1], limited[2]]
                        largest_correction = max(largest_correction, motion_correction)
                        reasons[code] = reasons.get(code, "motion-limit")
            if largest_correction < 1e-3:
                break

    def _nearby_pairs(
        self,
        codes: Sequence[str],
        positions: Mapping[str, Sequence[float]],
    ) -> Iterable[Tuple[str, str]]:
        """Yield only pairs that can overlap using a deterministic hash grid."""
        if len(codes) < 24:
            for left_index, left_code in enumerate(codes):
                for right_code in codes[left_index + 1:]:
                    yield left_code, right_code
            return
        cell_size = 14.5
        buckets: Dict[Tuple[int, int], List[str]] = {}
        for code in codes:
            point = positions[code]
            cell = (int(point[0] // cell_size), int(point[1] // cell_size))
            buckets.setdefault(cell, []).append(code)
        order = {code: index for index, code in enumerate(codes)}
        seen: set[Tuple[str, str]] = set()
        for cell, members in buckets.items():
            candidates: List[str] = []
            for dx in (-1, 0, 1):
                for dy in (-1, 0, 1):
                    candidates.extend(buckets.get((cell[0] + dx, cell[1] + dy), ()))
            for left_code in members:
                for right_code in candidates:
                    if order[left_code] >= order[right_code]:
                        continue
                    pair = (left_code, right_code)
                    if pair not in seen:
                        seen.add(pair)
                        yield pair

    def _guard_swept_paths(
        self,
        codes: Sequence[str],
        positions: Dict[str, List[float]],
        kinds: Mapping[str, str],
        previous: Mapping[str, Sequence[float]],
        fixed_points: Mapping[str, Tuple[str, Sequence[float]]],
        reasons: Dict[str, str],
    ) -> bool:
        adjusted = False
        for left_code, right_code in self._nearby_pairs(codes, positions):
            if left_code not in previous:
                continue
            left_previous = tuple(float(value) for value in previous[left_code])
            if right_code not in previous:
                continue
            right_previous = tuple(float(value) for value in previous[right_code])
            required = self._horizontal_required_separation(
                kinds[left_code],
                kinds[right_code],
                positions[left_code][2],
                positions[right_code][2],
            )
            if required > 0.0:
                start_distance = hypot(
                    left_previous[0] - right_previous[0],
                    left_previous[1] - right_previous[1],
                )
                end_distance = hypot(
                    positions[left_code][0] - positions[right_code][0],
                    positions[left_code][1] - positions[right_code][1],
                )
                swept = self.swept_distance(
                    left_previous,
                    positions[left_code],
                    right_previous,
                    positions[right_code],
                )
                if swept + 1e-4 < required:
                    # If a previous frame is already inside the numerical
                    # guard band, reverting every outward proposal recreates
                    # that invalid frame forever. Permit only a strict escape
                    # move; approaches and side swaps remain rejected.
                    if start_distance + 1e-4 < required and end_distance > start_distance + 1e-4:
                        continue
                    positions[left_code][:] = list(left_previous)
                    positions[right_code][:] = list(right_previous)
                    reasons[left_code] = "swept-agent-separation"
                    reasons[right_code] = "swept-agent-separation"
                    adjusted = True

        for left_code in codes:
            if left_code not in previous:
                continue
            left_previous = tuple(float(value) for value in previous[left_code])
            for fixed_code, (fixed_kind, fixed_point) in fixed_points.items():
                fixed_previous = tuple(
                    float(value)
                    for value in previous.get(fixed_code, fixed_point)
                )
                required = self._horizontal_required_separation(
                    kinds[left_code],
                    fixed_kind,
                    positions[left_code][2],
                    float(fixed_point[2]),
                )
                if required <= 0.0:
                    continue
                start_distance = hypot(
                    left_previous[0] - fixed_previous[0],
                    left_previous[1] - fixed_previous[1],
                )
                end_distance = hypot(
                    positions[left_code][0] - float(fixed_point[0]),
                    positions[left_code][1] - float(fixed_point[1]),
                )
                swept = self.swept_distance(
                    left_previous,
                    positions[left_code],
                    fixed_previous,
                    fixed_point,
                )
                if swept + 1e-4 >= required:
                    continue
                if start_distance + 1e-4 < required and end_distance > start_distance + 1e-4:
                    continue
                positions[left_code][:] = list(left_previous)
                reasons[left_code] = "swept-target-separation"
                adjusted = True
        return adjusted

    @staticmethod
    def swept_distance(
        first_start: Sequence[float],
        first_end: Sequence[float],
        second_start: Sequence[float],
        second_end: Sequence[float],
    ) -> float:
        """Minimum horizontal distance between two linear frame segments."""
        rx = float(first_start[0]) - float(second_start[0])
        ry = float(first_start[1]) - float(second_start[1])
        vx = (
            float(first_end[0]) - float(first_start[0])
            - float(second_end[0]) + float(second_start[0])
        )
        vy = (
            float(first_end[1]) - float(first_start[1])
            - float(second_end[1]) + float(second_start[1])
        )
        denominator = vx * vx + vy * vy
        if denominator <= 1e-12:
            return hypot(rx, ry)
        closest = max(0.0, min(1.0, -(rx * vx + ry * vy) / denominator))
        return hypot(rx + vx * closest, ry + vy * closest)

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

    def _limit_step(
        self,
        previous: Sequence[float],
        proposed: Sequence[float],
        kind: str,
        configured_max_step: float | None = None,
    ) -> Tuple[float, float, float]:
        px, py, pz = (float(value) for value in previous)
        x, y, z = (float(value) for value in proposed)
        distance = hypot(x - px, y - py)
        # Backend emits ten frames per second. These limits correspond to
        # about 3.5 m/s for UAVs and 3.2 m/s for surface craft. The previous
        # 1.8 m/s hard cap silently overrode the UI's 3 m/s cruise setting and
        # left large USV rings circling in transit lanes for several minutes.
        max_step = (
            max(0.0, float(configured_max_step))
            if configured_max_step is not None
            else (0.35 if kind.upper() == "UAV" else 0.32)
        )
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
        required = self._horizontal_required_separation(
            first_kind,
            second_kind,
            first[2],
            second[2],
        )
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
