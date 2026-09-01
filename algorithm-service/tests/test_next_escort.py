import math
import unittest

from app.adapters.adaptive_escort import (
    AdaptiveEscortAdapter,
    BREACH_DISTANCE_M,
    CONVOY_GUARD_MARGIN_M,
    CONVOY_TARGET_SPACING_M,
    CONTAINMENT_STANDOFF_M,
    POST_CAPTURE_CONVOY_CLEARANCE_M,
    POST_MISSION_OUTER_GUARD_GAP_M,
    PROTECTED_SAFE_GATE_OFFSET_M,
    TARGET_SEPARATION_M,
)


class NextEscortAcceptanceTests(unittest.TestCase):
    def run_frames(self, adapter, count):
        frame = None
        for _ in range(count):
            frame = adapter.step()
        return frame

    def test_detection_automatically_starts_capture(self):
        adapter = AdaptiveEscortAdapter(9001, {"uavCount": 3, "usvCount": 3, "seed": 8})
        frame = self.run_frames(adapter, 650)
        self.assertTrue(any(threat.forced for threat in adapter.threats))
        self.assertTrue(any(agent.role in {"CAPTURE", "INTERCEPTOR", "CONTAINMENT"} for agent in frame.agents))
        self.assertTrue(any(target.state not in {"APPROACHING", "WAITING"} for target in frame.targets if target.type == "THREAT_TARGET"))

    def test_generated_threats_start_outside_guard_area(self):
        for count in (3, 5, 10, 20, 30):
            with self.subTest(count=count):
                adapter = AdaptiveEscortAdapter(9050 + count, {
                    "uavCount": count,
                    "usvCount": count,
                    "seed": 20260814,
                    "threatMinDistanceM": 120,
                })
                for threat in adapter.threats:
                    protected = adapter.protected[threat.protected_index]
                self.assertGreaterEqual(
                    math.hypot(threat.x - protected.x, threat.y - protected.y),
                    112.0,
                )

    def test_multi_convoy_response_craft_are_separated_before_first_frame(self):
        for uav_count, usv_count in ((20, 25), (25, 25), (30, 30)):
            with self.subTest(uav_count=uav_count, usv_count=usv_count):
                adapter = AdaptiveEscortAdapter(9100 + uav_count + usv_count, {
                    "uavCount": uav_count,
                    "usvCount": usv_count,
                    "seed": 20260814,
                })
                usvs = [item for item in adapter.vehicles if item.kind == "USV"]
                self.assertGreaterEqual(min(
                    math.hypot(left.x - right.x, left.y - right.y)
                    for index, left in enumerate(usvs)
                    for right in usvs[index + 1:]
                ), adapter.safety.required_separation("USV", "USV") - 0.02)

    def test_active_capture_keeps_mixed_close_guards(self):
        for count in (3, 4, 10, 20, 30):
            with self.subTest(count=count):
                adapter = AdaptiveEscortAdapter(9100 + count, {"uavCount": count, "usvCount": count, "seed": 12})
                adapter.step()
                selected = adapter.activate_capture()
                frame = self.run_frames(adapter, 10)
                guards = [agent for agent in frame.agents if agent.role == "CLOSE_GUARD"]
                self.assertGreaterEqual(sum(agent.type == "UAV" for agent in guards), adapter.plan.protected_count)
                self.assertGreaterEqual(sum(agent.type == "USV" for agent in guards), adapter.plan.protected_count)
                assigned = [agent for agent in frame.agents if agent.assignedTargetCode == selected]
                self.assertGreaterEqual(sum(agent.type == "UAV" for agent in assigned), 2)
                self.assertGreaterEqual(sum(agent.type == "USV" for agent in assigned), 2)

    def test_multi_protected_targets_hold_compact_common_heading(self):
        adapter = AdaptiveEscortAdapter(9150, {
            "uavCount": 20, "usvCount": 20, "seed": 20260814,
        })
        adapter.step()
        adapter.activate_capture()
        saw_threat_response = False
        for _ in range(420):
            adapter.step()
            left, right = adapter.protected
            self.assertAlmostEqual(
                math.hypot(left.x - right.x, left.y - right.y),
                CONVOY_TARGET_SPACING_M,
                delta=0.05,
            )
            self.assertEqual(left.state, right.state)
            heading_delta = abs((left.heading - right.heading + 180.0) % 360.0 - 180.0)
            self.assertLessEqual(heading_delta, 0.1)
            saw_threat_response = saw_threat_response or left.state in {
                "THREAT_DETECTED", "EVADING", "BYPASSING_CONTAINMENT",
            }
        self.assertTrue(saw_threat_response)

    def test_multi_protected_convoy_has_square_mixed_close_guard(self):
        adapter = AdaptiveEscortAdapter(9151, {
            "uavCount": 20, "usvCount": 20, "seed": 20260814,
        })
        guards = [item for item in adapter.vehicles if item.role == "CLOSE_GUARD"]
        self.assertTrue(guards)
        self.assertEqual({item.group_id for item in guards}, {"CONVOY-GUARD"})
        self.assertEqual({item.kind for item in guards}, {"UAV", "USV"})
        center_x, center_y = adapter._convoy_center()
        protected_extent = max(
            max(abs(offset[0]), abs(offset[1]))
            for offset in adapter._protected_formation_offsets.values()
        )
        half_extent = protected_extent + CONVOY_GUARD_MARGIN_M
        offsets = [(item.x - center_x, item.y - center_y) for item in guards]
        self.assertEqual(len({(round(x, 3), round(y, 3)) for x, y in offsets}), len(guards))
        self.assertTrue(all(
            abs(max(abs(x), abs(y)) - half_extent) <= 0.05
            for x, y in offsets
        ))
        self.assertLessEqual(min(x for x, _ in offsets), -half_extent + 0.05)
        self.assertGreaterEqual(max(x for x, _ in offsets), half_extent - 0.05)
        self.assertLessEqual(min(y for _, y in offsets), -half_extent + 0.05)
        self.assertGreaterEqual(max(y for _, y in offsets), half_extent - 0.05)
        nearest_guard_clearance = min(
            math.hypot(guard.x - target.x, guard.y - target.y)
            for guard in guards
            for target in adapter.protected
        )
        self.assertGreaterEqual(nearest_guard_clearance, 13.9)
        self.assertLessEqual(nearest_guard_clearance, 15.1)

    def test_eighteen_plus_eighteen_has_eight_square_close_guards(self):
        adapter = AdaptiveEscortAdapter(91511, {
            "uavCount": 18, "usvCount": 18, "seed": 20260814,
        })
        guards = [item for item in adapter.vehicles if item.role == "CLOSE_GUARD"]
        self.assertEqual(8, len(guards))
        self.assertEqual(4, sum(item.kind == "UAV" for item in guards))
        self.assertEqual(4, sum(item.kind == "USV" for item in guards))
        center_x, center_y = adapter._convoy_center()
        offsets = [(item.x - center_x, item.y - center_y) for item in guards]
        self.assertEqual(8, len({
            (round(x, 3), round(y, 3))
            for x, y in offsets
        }))
        self.assertTrue(all(
            abs(max(abs(x), abs(y)) - CONVOY_GUARD_MARGIN_M) <= 0.05
            for x, y in offsets
        ))

    def test_thirty_plus_thirty_returns_all_surplus_to_outer_guard(self):
        adapter = AdaptiveEscortAdapter(91512, {
            "uavCount": 30, "usvCount": 30, "seed": 20260814,
        })
        adapter.step()
        for threat in adapter.threats:
            threat.state = "CAPTURED"
            threat.forced = True
        adapter._redeploy_surplus_to_convoy()

        support = adapter._convoy_support_members()
        watch = adapter._post_watch_members()
        self.assertEqual(20, len(support))
        self.assertEqual(10, sum(item.kind == "UAV" for item in support))
        self.assertEqual(10, sum(item.kind == "USV" for item in support))
        self.assertEqual([], watch)
        self.assertTrue(all(item.assigned_threat is None for item in support))
        self.assertEqual(20, len(adapter._convoy_support_route_by_code))
        status = adapter._post_mission_formation_status()
        self.assertEqual(20, status["requiredCount"])
        self.assertFalse(status["ready"])
        self.assertTrue(status["blockerCode"])

    def test_multi_protected_convoy_keeps_guards_while_rest_respond(self):
        adapter = AdaptiveEscortAdapter(9152, {
            "uavCount": 20, "usvCount": 20, "seed": 20260814,
        })
        guard_codes = {
            item.code for item in adapter.vehicles if item.role == "CLOSE_GUARD"
        }
        adapter.step()
        adapter.activate_capture()
        frame = adapter.step()
        guards = [item for item in adapter.vehicles if item.code in guard_codes]
        self.assertTrue(all(
            item.role == "CLOSE_GUARD" and item.assigned_threat is None
            for item in guards
        ))
        self.assertFalse(any(
            item.role == "RECON"
            for item in adapter.vehicles
            if item.code not in guard_codes
        ))
        self.assertTrue(any(item.role == "CAPTURE_RESERVE" for item in adapter.vehicles))
        self.assertFalse(any(item.role == "OUTER_INTERCEPT" for item in adapter.vehicles))
        reserves = adapter._convoy_reserve_members()
        self.assertTrue(reserves)
        for position, item in enumerate(reserves):
            desired = adapter._desired_position(item)
            rear_slot = adapter._convoy_support_point(position, len(reserves))
            self.assertAlmostEqual(rear_slot[0], desired[0], places=6)
            self.assertAlmostEqual(rear_slot[1], desired[1], places=6)
        self.assertEqual(len(frame.metrics["captureGroups"]), len(adapter.threats))
        self.assertTrue(all(
            group["uavCount"] >= 2 and group["usvCount"] >= 2
            for group in frame.metrics["captureGroups"]
        ))

    def test_thirty_plus_thirty_keeps_all_twenty_surplus_craft_in_outer_escort_square(self):
        adapter = AdaptiveEscortAdapter(91521, {
            "uavCount": 30, "usvCount": 30, "seed": 20260814,
        })
        frame = adapter.step()

        guards = [item for item in adapter.vehicles if item.role == "CLOSE_GUARD"]
        assigned = [item for item in adapter.vehicles if item.assigned_threat is not None]
        reserves = adapter._convoy_reserve_members()
        self.assertEqual(8, len(guards))
        self.assertEqual(32, len(assigned))
        self.assertEqual(20, len(reserves))
        self.assertEqual(10, sum(item.kind == "UAV" for item in reserves))
        self.assertEqual(10, sum(item.kind == "USV" for item in reserves))
        self.assertFalse(any(item.role == "OUTER_INTERCEPT" for item in adapter.vehicles))
        desired = [adapter._desired_position(item) for item in reserves]
        self.assertEqual(20, len({
            (round(point[0], 3), round(point[1], 3))
            for point in desired
        }))
        self.assertEqual(8, frame.metrics["closeGuardCount"])
        self.assertEqual(32, frame.metrics["captureAssignedCount"])
        self.assertEqual(20, frame.metrics["mobileSupportCount"])

    def test_parallel_team_arrival_can_handoff_after_visible_escape_run(self):
        adapter = AdaptiveEscortAdapter(91522, {
            "uavCount": 30, "usvCount": 30, "seed": 20260814,
        })
        adapter.step()
        threat = adapter.threats[2]
        threat.travelled_distance = (
            threat.capture_start_travel_distance
            + threat.required_pursuit_distance * 0.50
        )
        members = adapter._capture_members(2)
        for _ in range(4):
            slots = adapter._capture_slots(members, threat)
            center_x, center_y = adapter._capture_center(threat, members)
            for item, slot in zip(members, slots):
                item.x, item.y, item.z = slot.point((center_x, center_y, 0.0))

        adapter._assess_threats()

        self.assertEqual(1, threat.capture_stage)
        self.assertIn(threat.mission_stage, {"INTERCEPT", "ENCIRCLEMENT"})
        self.assertNotEqual("ESCAPE_PURSUIT", threat.state)
        ring_slots = adapter._capture_slots(members, threat)
        ring_angles = sorted(slot.angle % (2.0 * math.pi) for slot in ring_slots)
        maximum_slot_gap = max(
            (ring_angles[(index + 1) % len(ring_angles)] - ring_angles[index])
            % (2.0 * math.pi)
            for index in range(len(ring_angles))
        )
        self.assertLessEqual(math.degrees(maximum_slot_gap), 61.0)

        # Slot arrival temporarily drops while the team leaves the pursuit fan.
        # The hand-off must remain latched instead of returning to PURSUIT.
        adapter._assess_threats()
        self.assertEqual(1, threat.capture_stage)
        self.assertNotIn(threat.mission_stage, {"ESCAPE", "PURSUIT"})

    def test_twenty_six_parallel_team_does_not_wait_for_full_odometer_in_fan(self):
        adapter = AdaptiveEscortAdapter(91524, {
            "uavCount": 26, "usvCount": 26, "seed": 20260814,
            "uavSpeedMps": 15, "usvSpeedMps": 4,
        })
        stage_one_frame = None
        stage_two_frame = None
        for _ in range(1200):
            frame = adapter.step()
            group = next(
                item for item in frame.metrics["captureGroups"]
                if item["threatCode"] == "THREAT-003"
            )
            if group["stage"] == 1 and stage_one_frame is None:
                stage_one_frame = frame.sequence
            if group["stage"] >= 2:
                stage_two_frame = frame.sequence
                break

        self.assertIsNotNone(stage_one_frame)
        self.assertIsNotNone(stage_two_frame)
        self.assertLessEqual(stage_two_frame - stage_one_frame, 250)

    def test_global_progress_is_capped_while_any_threat_is_still_in_pursuit(self):
        adapter = AdaptiveEscortAdapter(91523, {
            "uavCount": 30, "usvCount": 30, "seed": 20260814,
        })
        frame = None
        for _ in range(1200):
            frame = adapter.step()
            if frame.metrics["missionStage"] == "PURSUIT":
                break
        self.assertIsNotNone(frame)
        self.assertEqual("PURSUIT", frame.metrics["missionStage"])
        self.assertLessEqual(frame.metrics["missionProgress"], 0.69)
        self.assertTrue(frame.metrics["stageSubjectThreatCode"])

    def test_three_parallel_response_groups_keep_fixed_members(self):
        adapter = AdaptiveEscortAdapter(91525, {
            "uavCount": 20, "usvCount": 20, "seed": 20260814,
        })
        initial = adapter.step()
        initial_assignments = {
            item.code: item.assigned_threat
            for item in adapter.vehicles
            if item.assigned_threat is not None
        }
        self.assertEqual(24, len(initial_assignments))
        self.assertEqual(
            {0: 8, 1: 8, 2: 8},
            {
                threat_index: sum(
                    assigned == threat_index
                    for assigned in initial_assignments.values()
                )
                for threat_index in range(3)
            },
        )
        self.assertTrue(all(
            group["uavCount"] == 4 and group["usvCount"] == 4
            for group in initial.metrics["captureGroups"]
        ))

        for _ in range(80):
            adapter.step()

        self.assertEqual(
            initial_assignments,
            {
                item.code: item.assigned_threat
                for item in adapter.vehicles
                if item.assigned_threat is not None
            },
        )
        self.assertTrue(all(
            item.assigned_threat is None
            for item in adapter.vehicles
            if item.role == "CLOSE_GUARD"
        ))

    def test_four_parallel_response_groups_keep_fixed_members_at_larger_scales(self):
        for count in (25, 30):
            with self.subTest(count=count):
                adapter = AdaptiveEscortAdapter(91525 + count, {
                    "uavCount": count, "usvCount": count, "seed": 20260814,
                })
                initial = adapter.step()
                initial_assignments = {
                    item.code: item.assigned_threat
                    for item in adapter.vehicles
                    if item.assigned_threat is not None
                }
                self.assertEqual(32, len(initial_assignments))
                self.assertEqual(
                    {0: 8, 1: 8, 2: 8, 3: 8},
                    {
                        threat_index: sum(
                            assigned == threat_index
                            for assigned in initial_assignments.values()
                        )
                        for threat_index in range(4)
                    },
                )
                self.assertTrue(all(
                    group["uavCount"] == 4 and group["usvCount"] == 4
                    for group in initial.metrics["captureGroups"]
                ))

                for _ in range(80):
                    adapter.step()

                self.assertEqual(
                    initial_assignments,
                    {
                        item.code: item.assigned_threat
                        for item in adapter.vehicles
                        if item.assigned_threat is not None
                    },
                )
                self.assertTrue(all(
                    item.assigned_threat is None
                    for item in adapter.vehicles
                    if item.role == "CLOSE_GUARD"
                ))

    def test_large_convoy_support_slots_form_unique_outer_square(self):
        adapter = AdaptiveEscortAdapter(91586, {
            "uavCount": 30, "usvCount": 30, "seed": 20260814,
        })
        for protected in adapter.protected:
            protected.x = adapter._protected_formation_offsets[protected.code][0]
        center_x, center_y = adapter._convoy_center()
        points = [adapter._convoy_support_point(index, 20) for index in range(20)]
        self.assertEqual(20, len({
            (round(x, 3), round(y, 3)) for x, y in points
        }))
        half_extent = max(
            max(
                max(abs(offset[0]), abs(offset[1]))
                for offset in adapter._protected_formation_offsets.values()
            ) + CONVOY_GUARD_MARGIN_M + POST_MISSION_OUTER_GUARD_GAP_M,
            40.0,
        )
        self.assertTrue(all(
            abs(max(abs(x - center_x), abs(y - center_y)) - half_extent) <= 0.05
            for x, y in points
        ))

    def test_resolved_multi_convoy_recalls_surplus_into_outer_guard_square(self):
        adapter = AdaptiveEscortAdapter(9153, {
            "uavCount": 20, "usvCount": 20, "seed": 20260814,
        })
        for threat_index, threat in enumerate(adapter.threats):
            threat.state = "CAPTURED"
            threat.forced = True
            # Reproduce the live retargeting case that previously left the
            # second protected target with no per-target completion hazard.
            threat.protected_index = 0
            # Keep every completed ring clear of the terminal gate. The gate
            # contract now correctly rejects a destination that is still
            # inside a captured threat's physical safety envelope.
            threat.x = adapter.safe_bounds[0] + 18.0
            threat.y = (threat_index - 1) * 72.0
        for protected in adapter.protected:
            start_x = adapter.protected_start_x[protected.code]
            protected.x = start_x + (protected.destination_x - start_x) * 0.40

        for kind in ("UAV", "USV"):
            free = [
                item for item in adapter.vehicles
                if item.role != "CLOSE_GUARD" and item.kind == kind
            ]
            for position, item in enumerate(free[:12]):
                item.assigned_threat = position % len(adapter.threats)
                item.role = "CONTAINMENT"
                item.group_id = f"CAPTURE-{item.assigned_threat + 1:03d}"
            for position, item in enumerate(free[12:]):
                item.assigned_threat = None
                item.role = "CAPTURE_RESERVE" if position % 2 else "OUTER_INTERCEPT"
                item.group_id = f"RESERVE-{position % len(adapter.threats) + 1:03d}"

        adapter._redeploy_surplus_to_convoy()
        support = adapter._convoy_support_members()
        self.assertEqual(8, len(support))
        self.assertEqual({item.group_id for item in support}, {"CONVOY-SUPPORT"})
        self.assertTrue(all(item.assigned_threat is None for item in support))
        center_x, center_y = adapter._convoy_center()
        desired = [
            adapter._convoy_support_point(position, len(support))
            for position in range(len(support))
        ]
        self.assertEqual(len(desired), len({
            (round(x, 3), round(y, 3)) for x, y in desired
        }))
        outer_half_extent = max(
            max(
                max(abs(offset[0]), abs(offset[1]))
                for offset in adapter._protected_formation_offsets.values()
            ) + CONVOY_GUARD_MARGIN_M + POST_MISSION_OUTER_GUARD_GAP_M,
            len(support) * 2.0,
        )
        self.assertTrue(all(
            abs(max(abs(x - center_x), abs(y - center_y)) - outer_half_extent) <= 0.05
            for x, y in desired
        ))
        for item, (x, y) in zip(support, desired):
            item.x, item.y = x, y
        self.assertTrue(adapter._convoy_support_ready())
        self.assertTrue(all(
            0.39 <= adapter._escort_route_progress(item) <= 0.42
            for item in adapter.protected
        ))
        self.assertFalse(any(
            adapter._protected_reached_safe_gate(item)
            for item in adapter.protected
        ))
        for item in adapter.protected:
            item.x = item.destination_x - PROTECTED_SAFE_GATE_OFFSET_M
            item.y = item.destination_y
        self.assertTrue(all(
            adapter._protected_reached_safe_gate(item)
            for item in adapter.protected
        ))

    def test_terminal_frame_does_not_force_incomplete_escort_route_to_one(self):
        adapter = AdaptiveEscortAdapter(91531, {
            "uavCount": 10, "usvCount": 10, "seed": 20260814,
        })
        adapter.step()
        protected = adapter.protected[0]
        start_x = adapter.protected_start_x[protected.code]
        gate_x = protected.destination_x - PROTECTED_SAFE_GATE_OFFSET_M
        protected.x = start_x + (gate_x - start_x) * 0.48
        adapter._display_escort_progress = 0.0
        adapter._terminal_status = "COMPLETED"

        frame = adapter.step()

        self.assertAlmostEqual(0.48, frame.metrics["escortProgress"], places=3)
        self.assertFalse(adapter._protected_reached_safe_gate(protected))

    def test_convoy_support_assignment_minimizes_crossing_routes(self):
        adapter = AdaptiveEscortAdapter(9154, {
            "uavCount": 20, "usvCount": 20, "seed": 20260814,
        })
        members = sorted(
            [item for item in adapter.vehicles if item.role != "CLOSE_GUARD"][:8],
            key=lambda item: item.code,
        )
        points = [
            adapter._convoy_support_point(position, len(members))
            for position in range(len(members))
        ]
        for item, point in zip(members, reversed(points)):
            item.x, item.y = point

        adapter._assign_convoy_support_slots(members)

        self.assertEqual(
            list(reversed(range(len(members)))),
            [adapter._convoy_support_slot_by_code[item.code] for item in members],
        )

    def test_active_threat_visibly_moves_and_evades(self):
        adapter = AdaptiveEscortAdapter(9201, {"uavCount": 3, "usvCount": 3, "seed": 21, "usvSpeedMps": 1.5})
        adapter.step()
        code = adapter.activate_capture()
        start = next(item for item in adapter.threats if item.code == code)
        start_point = (start.x, start.y)
        headings = []
        for _ in range(160):
            adapter.step()
            threat = next(item for item in adapter.threats if item.code == code)
            headings.append(threat.heading)
        travelled = math.hypot(threat.x - start_point[0], threat.y - start_point[1])
        self.assertGreater(travelled, 8.0)
        self.assertGreater(max(headings) - min(headings), 1.0)

    def test_capture_escape_corridor_points_away_from_protected_target(self):
        adapter = AdaptiveEscortAdapter(9202, {
            "uavCount": 5, "usvCount": 6, "seed": 20260814,
            "uavSpeedMps": 5, "usvSpeedMps": 2,
        })
        adapter.step()
        adapter.activate_capture()
        threat = adapter.threats[0]
        protected = adapter.protected[threat.protected_index]
        distance = math.hypot(threat.x - protected.x, threat.y - protected.y)
        away_x = (threat.x - protected.x) / distance
        away_y = (threat.y - protected.y) / distance
        self.assertGreaterEqual(
            threat.escape_dir_x * away_x + threat.escape_dir_y * away_y,
            0.3,
        )

    def test_capture_waits_for_a_visible_escape_run_before_forming_ring(self):
        adapter = AdaptiveEscortAdapter(9221, {
            "uavCount": 3, "usvCount": 3, "seed": 20260814,
            "uavSpeedMps": 5, "usvSpeedMps": 1,
        })
        adapter.step()
        adapter.activate_capture()
        frame = self.run_frames(adapter, 500)
        threat = adapter.threats[0]
        pursuit_distance = threat.travelled_distance - threat.capture_start_travel_distance
        self.assertGreater(pursuit_distance, 35.0)
        self.assertLess(pursuit_distance, threat.required_pursuit_distance)
        self.assertEqual(threat.capture_stage, 0)
        self.assertEqual(threat.state, "ESCAPE_PURSUIT")
        group = frame.metrics["captureGroups"][0]
        self.assertAlmostEqual(group["pursuitDistanceM"], pursuit_distance, delta=0.2)
        self.assertEqual(group["requiredPursuitDistanceM"], 100.0)

    def test_late_active_capture_gets_a_fresh_deadline_and_completes(self):
        adapter = AdaptiveEscortAdapter(9251, {
            "uavCount": 3, "usvCount": 3, "seed": 20260814,
            "uavSpeedMps": 5, "usvSpeedMps": 1,
        })
        self.run_frames(adapter, 401)
        activation_sequence = adapter.sequence
        adapter.activate_capture()
        terminal = None
        # Automatic capture may already be active before this compatibility
        # command. The convoy then needs its independent escort window to
        # reach the safe destination after containment is complete.
        for _ in range(12000):
            frame = adapter.step()
            terminal = frame.terminalStatus
            if terminal:
                break
        self.assertEqual(terminal, "COMPLETED")
        self.assertGreater(frame.sequence, activation_sequence)
        self.assertNotEqual(frame.metrics["terminalReason"], "active capture time limit reached")
        self.assertEqual(frame.metrics["missionProgress"], 1.0)

    def test_completed_escort_keeps_the_enemy_contained(self):
        adapter = AdaptiveEscortAdapter(9253, {
            "uavCount": 5, "usvCount": 6, "seed": 20260814,
            "uavSpeedMps": 5, "usvSpeedMps": 2,
        })
        frame = None
        minimum_after_capture = math.inf
        minimum_member_clearance = math.inf
        for _ in range(12000):
            frame = adapter.step()
            threat = adapter.threats[0]
            protected = adapter.protected[0]
            if threat.state == "CAPTURED":
                minimum_after_capture = min(
                    minimum_after_capture,
                    math.hypot(threat.x - protected.x, threat.y - protected.y),
                )
                for member in adapter._capture_members(0):
                    minimum_member_clearance = min(
                        minimum_member_clearance,
                        math.hypot(member.x - protected.x, member.y - protected.y),
                    )
            if frame.terminalStatus:
                break
        self.assertEqual(frame.terminalStatus, "COMPLETED")
        self.assertEqual(adapter.threats[0].state, "CAPTURED")
        members = adapter._capture_members(0)
        self.assertGreaterEqual(sum(item.kind == "UAV" for item in members), 2)
        self.assertGreaterEqual(sum(item.kind == "USV" for item in members), 2)
        self.assertTrue(all(item.role == "CONTAINMENT" for item in members))
        self.assertGreaterEqual(
            minimum_after_capture,
            POST_CAPTURE_CONVOY_CLEARANCE_M - 1.0,
        )
        self.assertGreaterEqual(minimum_member_clearance, 38.0)

    def test_multi_threat_capture_uses_fixed_balanced_mixed_groups(self):
        adapter = AdaptiveEscortAdapter(9252, {"uavCount": 10, "usvCount": 10, "seed": 20260814})
        adapter.step()
        adapter.activate_capture()
        frame = adapter.step()
        groups = frame.metrics["captureGroups"]
        self.assertEqual(len(groups), 2)
        self.assertTrue(all(group["uavCount"] >= 2 and group["usvCount"] >= 2 for group in groups))
        self.assertLessEqual(max(group["memberCount"] for group in groups) - min(group["memberCount"] for group in groups), 1)
        assigned_codes = [item.code for item in adapter.vehicles if item.assigned_threat is not None]
        self.assertEqual(len(assigned_codes), len(set(assigned_codes)))
        self.assertIn("escortProgress", frame.metrics)
        self.assertIn("captureProgress", frame.metrics)
        self.assertNotIn("captureRemainingFrames", frame.metrics)

    def test_ten_plus_ten_two_threats_attack_then_get_independent_intercepts(self):
        adapter = AdaptiveEscortAdapter(9254, {
            "uavCount": 10, "usvCount": 10, "seed": 20260814,
            "uavSpeedMps": 5, "usvSpeedMps": 3,
        })
        attack_alignment_frames = {item.code: 0 for item in adapter.threats}
        blocker_groups_seen = set()
        observer_groups_seen = set()
        maximum_target_speed = 0.0
        frame = None
        for _ in range(1800):
            frame = adapter.step()
            maximum_target_speed = max(
                maximum_target_speed,
                max(math.hypot(item.vx, item.vy) for item in adapter.protected),
            )
            blocker_groups_seen.update(
                item.group_id for item in adapter.vehicles if item.role == "BLOCKER"
            )
            observer_groups_seen.update(
                item.group_id for item in adapter.vehicles if item.role == "CONFRONT"
            )
            for threat in adapter.threats:
                if threat.detected_frame is None or threat.forced:
                    continue
                protected = adapter.protected[threat.protected_index]
                ux, uy = (
                    (protected.x - threat.x) / max(1e-6, math.hypot(protected.x - threat.x, protected.y - threat.y)),
                    (protected.y - threat.y) / max(1e-6, math.hypot(protected.x - threat.x, protected.y - threat.y)),
                )
                speed = math.hypot(threat.vx, threat.vy)
                if speed > 0.5 and (threat.vx * ux + threat.vy * uy) / speed > 0.45:
                    attack_alignment_frames[threat.code] += 1
            if all(item.forced for item in adapter.threats):
                break
        self.assertIsNotNone(frame)
        self.assertTrue(all(item.forced for item in adapter.threats))
        self.assertTrue(all(value >= 18 for value in attack_alignment_frames.values()))
        self.assertEqual(blocker_groups_seen, {"BLOCK-001", "BLOCK-002"})
        self.assertEqual(observer_groups_seen, {"WATCH-001", "WATCH-002"})
        self.assertGreater(maximum_target_speed, 1.4)
        self.assertGreater(frame.metrics["attackClosingDistanceM"], 8.0)
        groups = frame.metrics["captureGroups"]
        self.assertEqual(len(groups), 2)
        self.assertTrue(all(group["uavCount"] >= 2 and group["usvCount"] >= 2 for group in groups))
        guards = [item for item in adapter.vehicles if item.role == "CLOSE_GUARD"]
        self.assertGreaterEqual(sum(item.kind == "UAV" for item in guards), 2)
        self.assertGreaterEqual(sum(item.kind == "USV" for item in guards), 2)

    def test_ten_plus_ten_two_threats_complete_capture_and_safe_arrival(self):
        adapter = AdaptiveEscortAdapter(9256, {
            "uavCount": 10, "usvCount": 10, "seed": 20260814,
            "uavSpeedMps": 5, "usvSpeedMps": 3,
        })
        frame = None
        for _ in range(3200):
            frame = adapter.step()
            if frame.terminalStatus:
                break
        self.assertIsNotNone(frame)
        self.assertEqual("COMPLETED", frame.terminalStatus, frame.metrics)
        self.assertTrue(all(item.state == "CAPTURED" for item in adapter.threats))
        self.assertEqual(2, frame.metrics["capturedThreatCount"])
        self.assertEqual(1.0, frame.metrics["escortProgress"])

    def test_surface_and_target_speeds_use_the_raised_dynamic_profile(self):
        adapter = AdaptiveEscortAdapter(9255, {
            "uavCount": 10, "usvCount": 10, "seed": 20260814,
            "uavSpeedMps": 5, "usvSpeedMps": 3,
        })
        maximum_threat_speed = 0.0
        maximum_usv_speed = 0.0
        maximum_target_speed = 0.0
        for _ in range(260):
            adapter.step()
            maximum_threat_speed = max(
                maximum_threat_speed,
                max(math.hypot(item.vx, item.vy) for item in adapter.threats),
            )
            maximum_usv_speed = max(
                maximum_usv_speed,
                max(math.hypot(item.vx, item.vy) for item in adapter.vehicles if item.kind == "USV"),
            )
            maximum_target_speed = max(
                maximum_target_speed,
                max(math.hypot(item.vx, item.vy) for item in adapter.protected),
            )
        self.assertGreater(maximum_threat_speed, 1.7)
        self.assertLessEqual(maximum_threat_speed, 2.41)
        self.assertGreater(maximum_usv_speed, 2.1)
        # Interceptors may accelerate above cruise but remain under the 4 m/s
        # physical surface limit advertised by the simulation UI.
        self.assertLessEqual(maximum_usv_speed, 4.05)
        self.assertGreater(maximum_target_speed, 1.4)
        self.assertLessEqual(maximum_target_speed, 2.26)

    def test_urgent_threats_receive_independent_mixed_response_pairs(self):
        adapter = AdaptiveEscortAdapter(9300, {
            "uavCount": 15, "usvCount": 15, "seed": 20260814,
        })
        for threat in adapter.threats[:3]:
            target = adapter.protected[threat.protected_index]
            threat.x = target.x - 82.0
            threat.y = target.y
            threat.vx = 2.0
            threat.vy = 0.0
            threat.detected_frame = 1
            threat.state = "DETECTED"
        adapter._synchronize_guard_roles()
        for index in range(3):
            blockers = [
                item for item in adapter.vehicles
                if item.group_id == f"BLOCK-{index + 1:03d}"
            ]
            observers = [
                item for item in adapter.vehicles
                if item.group_id == f"WATCH-{index + 1:03d}"
            ]
            self.assertGreaterEqual(len(blockers), 2)
            self.assertGreaterEqual(len(observers), 2)
            desired = [adapter._desired_position(item) for item in blockers]
            self.assertGreater(math.hypot(
                desired[0][0] - desired[1][0],
                desired[0][1] - desired[1][1],
            ), 10.0)

    def test_capture_allocation_preserves_quick_response_reserve(self):
        adapter = AdaptiveEscortAdapter(9302, {
            "uavCount": 15, "usvCount": 15, "seed": 20260814,
        })
        adapter._start_capture_for([adapter.threats[0]], "TEST")
        for kind in ("UAV", "USV"):
            reserve = [
                item for item in adapter.vehicles
                if item.kind == kind and item.role == "RECON"
                and item.assigned_threat is None
            ]
            self.assertGreaterEqual(len(reserve), 2)

    def test_protected_target_moves_and_evades_after_detection(self):
        adapter = AdaptiveEscortAdapter(9301, {"uavCount": 3, "usvCount": 3, "seed": 4})
        start = (adapter.protected[0].x, adapter.protected[0].y)
        states = set()
        for _ in range(900):
            adapter.step()
            states.add(adapter.protected[0].state)
        target = adapter.protected[0]
        self.assertGreater(math.hypot(target.x - start[0], target.y - start[1]), 4.0)
        self.assertTrue(states.intersection({"THREAT_DETECTED", "EVADING"}))

    def test_target_safety_and_water_margin_hold_across_scales(self):
        for count in (3, 4, 10, 20, 30):
            with self.subTest(count=count):
                adapter = AdaptiveEscortAdapter(9400 + count, {"uavCount": count, "usvCount": count, "seed": 31})
                adapter.step()
                adapter.activate_capture()
                frame = self.run_frames(adapter, 500)
                self.assertNotEqual(frame.terminalStatus, "FAILED")
                distance = frame.metrics["minProtectedThreatDistanceM"]
                self.assertIsNotNone(distance)
                self.assertGreaterEqual(distance, BREACH_DISTANCE_M)
                self.assertGreaterEqual(frame.metrics["minShoreDistanceM"], -1e-6)

    def test_mission_has_no_wall_clock_forced_terminal(self):
        adapter = AdaptiveEscortAdapter(9501, {"uavCount": 3, "usvCount": 3, "seed": 2})
        adapter.timeout_frames = 3
        frame = self.run_frames(adapter, 4)
        self.assertIsNone(frame.terminalStatus)
        self.assertNotEqual(frame.phase, "TIMEOUT")

    def test_active_capture_has_no_fixed_deadline(self):
        adapter = AdaptiveEscortAdapter(9502, {"uavCount": 3, "usvCount": 3, "seed": 2})
        self.run_frames(adapter, 50)
        adapter.activate_capture()
        adapter.capture_timeout_frames = 3
        frame = self.run_frames(adapter, 3)
        self.assertIsNone(frame.terminalStatus)
        self.assertEqual(frame.metrics["captureElapsedFrames"], 3)


if __name__ == "__main__":
    unittest.main()
