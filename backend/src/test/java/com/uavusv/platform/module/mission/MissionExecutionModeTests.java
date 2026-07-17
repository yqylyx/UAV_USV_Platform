package com.uavusv.platform.module.mission;

import com.uavusv.platform.module.mission.entity.MissionExecutionMode;
import com.uavusv.platform.module.mission.entity.MissionStage;
import com.uavusv.platform.module.mission.entity.MissionStatus;
import com.uavusv.platform.module.mission.entity.MissionTask;
import com.uavusv.platform.module.mission.entity.MissionType;
import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;

class MissionExecutionModeTests {

    @Test
    void shouldStoreAndReadExecutionMode() {
        MissionTask task = new MissionTask("MT-TEST");
        task.update("MT-TEST", "test", MissionType.COOPERATIVE_ENCIRCLEMENT,
                MissionExecutionMode.ROS_GAZEBO, MissionStatus.DRAFT, MissionStage.PREPARE,
                1, null, null, null, null, null, null);

        assertEquals(MissionExecutionMode.ROS_GAZEBO, task.getExecutionMode());
    }
}
