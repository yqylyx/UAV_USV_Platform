package com.uavusv.platform.module.mission;

import com.uavusv.platform.module.mission.entity.MissionRun;
import com.uavusv.platform.module.mission.entity.MissionRunStatus;
import com.uavusv.platform.module.mission.entity.MissionStage;
import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertNull;

class MissionRunTests {

    @Test
    void shouldKeepOneRunAcrossPauseResumeAndCompletion() {
        MissionRun run = new MissionRun(10L, 20L, 2, MissionStage.TARGET_DETECTED, "admin");

        assertEquals(MissionRunStatus.PENDING, run.getStatus());
        assertEquals(2, run.getRunNo());
        assertNotNull(run.getRunKey());

        run.activate(MissionStage.TARGET_DETECTED);
        assertEquals(MissionRunStatus.RUNNING, run.getStatus());

        run.pause(MissionStage.TRACKING);
        assertEquals(MissionRunStatus.PAUSED, run.getStatus());
        assertNotNull(run.getPausedAt());

        run.resume(MissionStage.ENCIRCLEMENT);
        assertEquals(MissionRunStatus.RUNNING, run.getStatus());
        assertNull(run.getPausedAt());

        run.complete(MissionStage.EVALUATION);
        assertEquals(MissionRunStatus.COMPLETED, run.getStatus());
        assertEquals(MissionStage.EVALUATION, run.getStage());
        assertNotNull(run.getEndedAt());
    }

    @Test
    void shouldRetainFailureReason() {
        MissionRun run = new MissionRun(10L, null, 1, MissionStage.TRACKING, "operator");

        run.fail(MissionStage.TRACKING, "ROS heartbeat timeout");

        assertEquals(MissionRunStatus.FAILED, run.getStatus());
        assertEquals("ROS heartbeat timeout", run.getFailureReason());
        assertNotNull(run.getEndedAt());
    }

    @Test
    void shouldRetainMissionCenterRuntimeAndAlgorithmIdentity() {
        MissionRun run = new MissionRun(
                10L,
                20L,
                3,
                MissionStage.TARGET_DETECTED,
                "operator",
                "mission-unity-test",
                "encirclement-v2",
                "2.1.0"
        );

        assertEquals("mission-unity-test", run.getRuntimeInstanceId());
        assertEquals("encirclement-v2", run.getAlgorithmCode());
        assertEquals("2.1.0", run.getAlgorithmVersion());
    }
}
