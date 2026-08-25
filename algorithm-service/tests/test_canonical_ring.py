import math
import unittest

from app.capture import (
    RingMember,
    allocate_balanced_groups,
    assess_canonical_ring,
    build_canonical_slots,
)


class CanonicalRingTest(unittest.TestCase):
    def _members(self, uav_count: int, usv_count: int) -> list[RingMember]:
        members: list[RingMember] = []
        total = uav_count + usv_count
        for index in range(total):
            angle = 2.0 * math.pi * index / max(1, total)
            kind = "UAV" if index < uav_count else "USV"
            ordinal = index + 1 if kind == "UAV" else index - uav_count + 1
            members.append(RingMember(
                f"{kind}-{ordinal:03d}", kind,
                math.cos(angle) * 70.0, math.sin(angle) * 70.0,
                25.0 if kind == "UAV" else 0.0,
            ))
        return members

    def test_balanced_allocator_never_starves_a_target(self):
        groups = allocate_balanced_groups(
            [f"UAV-{index:03d}" for index in range(1, 31)],
            4,
        )
        self.assertEqual(30, sum(map(len, groups)))
        self.assertLessEqual(max(map(len, groups)) - min(map(len, groups)), 1)
        self.assertEqual(30, len({code for group in groups for code in group}))

    def test_exact_ring_passes_for_asymmetric_and_dense_groups(self):
        for uav_count, usv_count in ((3, 3), (4, 6), (7, 8), (10, 10), (15, 15), (18, 12)):
            with self.subTest(uav=uav_count, usv=usv_count):
                target = (12.0, -8.0, 0.0)
                members = self._members(uav_count, usv_count)
                slots = build_canonical_slots(members, target, phase=0.31)
                executed = [
                    RingMember(
                        member.code, member.kind,
                        *slots[member.code].point(target),
                    )
                    for member in members
                ]
                assessment = assess_canonical_ring(executed, target, slots)
                self.assertTrue(assessment.ready, assessment)
                self.assertEqual(1.0, assessment.arrival_ratio)
                self.assertLessEqual(
                    assessment.maximum_gap_deg,
                    assessment.allowed_gap_deg,
                )

    def test_scattered_hull_cannot_be_reported_as_captured(self):
        target = (0.0, 0.0, 0.0)
        members = self._members(5, 5)
        slots = build_canonical_slots(members, target)
        scattered = []
        for index, member in enumerate(members):
            x, y, z = slots[member.code].point(target)
            if index == 0:
                x += 24.0
                y += 18.0
            scattered.append(RingMember(member.code, member.kind, x, y, z))
        assessment = assess_canonical_ring(scattered, target, slots)
        self.assertFalse(assessment.ready)
        self.assertNotEqual("NONE", assessment.blocker)
        self.assertLess(assessment.arrival_ratio, 1.0)

    def test_slots_are_one_horizontal_circle(self):
        target = (4.0, 9.0, 0.0)
        members = self._members(11, 7)
        slots = build_canonical_slots(members, target)
        radii = {round(slot.radius, 6) for slot in slots.values()}
        self.assertEqual(1, len(radii))
        angles = sorted(round(slot.angle, 8) for slot in slots.values())
        gaps = [
            (angles[(index + 1) % len(angles)] - angles[index]) % (2.0 * math.pi)
            for index in range(len(angles))
        ]
        self.assertLess(max(gaps) - min(gaps), 1e-6)

    def test_usv_bow_must_face_target_when_orientation_is_required(self):
        target = (0.0, 0.0, 0.0)
        members = self._members(3, 3)
        slots = build_canonical_slots(members, target)
        executed = []
        for member in members:
            x, y, z = slots[member.code].point(target)
            inward = math.degrees(math.atan2(-y, -x)) % 360.0
            executed.append(RingMember(
                member.code, member.kind, x, y, z,
                inward if member.kind == "USV" else 0.0,
            ))
        ready = assess_canonical_ring(
            executed, target, slots,
            require_inward_usv_heading=True,
        )
        self.assertTrue(ready.ready, ready)

        wrong = list(executed)
        usv_index = next(
            index for index, member in enumerate(wrong)
            if member.kind == "USV"
        )
        member = wrong[usv_index]
        wrong[usv_index] = RingMember(
            member.code, member.kind, member.x, member.y, member.z,
            (float(member.heading) + 90.0) % 360.0,
        )
        rejected = assess_canonical_ring(
            wrong, target, slots,
            require_inward_usv_heading=True,
        )
        self.assertFalse(rejected.ready)
        self.assertEqual("USV_HEADING_ALIGNMENT", rejected.blocker)


if __name__ == "__main__":
    unittest.main()
