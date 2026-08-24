import unittest

from app.capture.containment_contract import (
    allowed_containment_gap_deg,
    assess_containment,
)


class ContainmentContractTests(unittest.TestCase):
    def test_gap_threshold_is_dynamic_and_strict(self):
        self.assertAlmostEqual(48.6, allowed_containment_gap_deg(10), places=2)
        self.assertAlmostEqual(60.75, allowed_containment_gap_deg(8), places=2)
        self.assertAlmostEqual(81.0, allowed_containment_gap_deg(6), places=2)
        self.assertEqual(120.0, allowed_containment_gap_deg(3))

    def test_open_horseshoe_is_not_containment(self):
        assessment = assess_containment(
            [(10, 0, 0), (0, 10, 0), (-10, 0, 0), (0, -10, 0)],
            (0, 0, 0),
            minimum_radius_m=5,
            maximum_radius_m=20,
            maximum_radial_spread_m=5,
        )
        self.assertTrue(assessment.ready)

        open_ring = assess_containment(
            [
                (10, 0, 0),
                (7.66, 6.43, 0),
                (1.74, 9.85, 0),
                (-10, 0, 0),
                (-7.66, -6.43, 0),
            ],
            (0, 0, 0),
            minimum_radius_m=5,
            maximum_radius_m=20,
            maximum_radial_spread_m=5,
        )
        self.assertFalse(open_ring.ready)
        self.assertEqual("ANGULAR_GAP", open_ring.blocker)

    def test_every_assigned_member_must_participate(self):
        assessment = assess_containment(
            [(10, 0, 0), (0, 10, 0), (-10, 0, 0), (0, -10, 0)],
            (0, 0, 0),
            required_count=5,
            participating=4,
            minimum_radius_m=5,
            maximum_radius_m=20,
            maximum_radial_spread_m=5,
        )
        self.assertFalse(assessment.ready)
        self.assertEqual("INCOMPLETE_PARTICIPATION", assessment.blocker)

    def test_radial_outlier_is_rejected(self):
        assessment = assess_containment(
            [(10, 0, 0), (0, 10, 0), (-10, 0, 0), (0, -30, 0)],
            (0, 0, 0),
            minimum_radius_m=5,
            maximum_radius_m=40,
            maximum_radial_spread_m=10,
        )
        self.assertFalse(assessment.ready)
        self.assertEqual("RADIAL_SPREAD", assessment.blocker)

    def test_contract_requires_type_layers_and_sector_coverage(self):
        assessment = assess_containment(
            [(10, 0, 0), (0, 10, 0), (-10, 0, 0), (0, -10, 0)],
            (0, 0, 0),
            required_count=4,
            device_types=["UAV", "UAV", "UAV", "UAV"],
            minimum_type_counts={"UAV": 1, "USV": 1},
            minimum_radius_m=5,
            maximum_radius_m=20,
            maximum_radial_spread_m=5,
        )
        self.assertFalse(assessment.ready)
        self.assertEqual("TYPE_LAYER", assessment.blocker)

        sparse = assess_containment(
            [(10, 0, 0), (4.23, 9.06, 0), (-6.42, 7.66, 0), (-9.66, -2.59, 0), (-0.17, -10, 0)],
            (0, 0, 0),
            required_count=5,
            device_types=["UAV", "UAV", "USV", "USV", "USV"],
            minimum_type_counts={"UAV": 1, "USV": 1},
            sector_count=4,
            minimum_radius_m=5,
            maximum_radius_m=20,
            maximum_radial_spread_m=5,
        )
        self.assertFalse(sparse.ready)
        self.assertEqual("SECTOR_COVERAGE", sparse.blocker)

    def test_contract_rejects_unsafe_or_invalid_members(self):
        assessment = assess_containment(
            [(10, 0, 0), (10, 0.17, 0), (0, 10, 0), (-10, 0, 0), (0, -10, 0)],
            (0, 0, 0),
            required_count=5,
            device_types=["UAV", "USV", "UAV", "USV", "USV"],
            minimum_type_counts={"UAV": 1, "USV": 1},
            minimum_radius_m=5,
            maximum_radius_m=20,
            maximum_radial_spread_m=5,
            minimum_pairwise_separation_m=7,
        )
        self.assertFalse(assessment.ready)
        self.assertEqual("MINIMUM_SEPARATION", assessment.blocker)

        invalid = assess_containment(
            [(10, 0, 0), (0, 10, 0), (-10, 0, 0), (0, -10, 0)],
            (0, 0, 0),
            required_count=4,
            device_types=["UAV", "UAV", "USV", "USV"],
            minimum_type_counts={"UAV": 1, "USV": 1},
            minimum_radius_m=5,
            maximum_radius_m=20,
            maximum_radial_spread_m=5,
            valid=[True, True, False, True],
        )
        self.assertFalse(invalid.ready)
        self.assertEqual("INVALID_PARTICIPANT", invalid.blocker)


if __name__ == "__main__":
    unittest.main()
