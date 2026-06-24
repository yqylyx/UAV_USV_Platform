package com.uavusv.platform.module.runtimecontrol.dto;

import com.uavusv.platform.module.runtimecontrol.entity.SimulationSession;
import com.uavusv.platform.module.runtimecontrol.entity.SimulationStatus;

import java.time.LocalDateTime;

public record RuntimeControlResponse(
        String sessionKey,
        SimulationStatus status,
        boolean rosOnline,
        boolean unityOnline,
        boolean rosManaged,
        boolean unityManaged,
        boolean controllable,
        LocalDateTime startedAt,
        String message
) {
    public static RuntimeControlResponse from(SimulationSession session, boolean rosOnline,
                                              boolean unityOnline, String message) {
        return new RuntimeControlResponse(
                session.getSessionKey(), session.getStatus(), rosOnline, unityOnline,
                session.isRosManaged(), session.isUnityManaged(),
                session.isRosManaged() || session.isUnityManaged(), session.getStartedAt(), message
        );
    }
}
