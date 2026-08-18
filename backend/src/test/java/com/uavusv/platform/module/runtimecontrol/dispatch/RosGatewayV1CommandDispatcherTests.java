package com.uavusv.platform.module.runtimecontrol.dispatch;

import com.uavusv.platform.module.runtimecontrol.dto.RuntimeCommandRequest;
import com.uavusv.platform.module.gateway.v1.DeviceCodeMapper;
import com.uavusv.platform.module.mission.entity.MissionRun;
import com.uavusv.platform.module.mission.repository.MissionRunRepository;
import com.uavusv.platform.module.runtimecontrol.entity.CommandType;
import com.uavusv.platform.module.runtimecontrol.entity.RuntimeScope;
import org.junit.jupiter.api.Test;
import uavusv.gateway.v1.UavUsvGatewayV1;

import java.time.Instant;
import java.util.Optional;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.when;

class RosGatewayV1CommandDispatcherTests {

    private final RosGatewayV1CommandDispatcher dispatcher = new RosGatewayV1CommandDispatcher(null, new DeviceCodeMapper());

    @Test
    void shouldBuildControlCommandEnvelope() {
        RuntimeCommandRequest request = new RuntimeCommandRequest(
                CommandType.UAV_HOVER,
                12L,
                "uav_01",
                "{\"altitudeM\":50}",
                "hold position",
                RuntimeScope.MISSION_CENTER,
                "mission-unity-1"
        );

        UavUsvGatewayV1.GatewayEnvelope envelope = dispatcher.buildEnvelope(
                "command-1",
                request,
                7,
                Instant.parse("2026-08-09T10:04:16Z")
        );

        assertEquals("1.0", envelope.getSpecVersion());
        assertEquals("control.command", envelope.getMessageType());
        assertEquals(dispatcher.controlStreamId(), envelope.getStreamId());
        assertEquals(7, envelope.getSequence());
        assertEquals("uav-usv-platform-backend", envelope.getSource());
        assertEquals("12", envelope.getRunId());
        assertEquals("uav_01", envelope.getDeviceCode());

        UavUsvGatewayV1.ControlCommand command = envelope.getControlCommand();
        assertEquals("command-1", command.getCommandId());
        assertEquals("command-1", command.getClientRequestId());
        assertEquals("UAV_HOVER", command.getCommand());
        assertEquals(UavUsvGatewayV1.Priority.MISSION, command.getPriority());
        assertEquals(UavUsvGatewayV1.TargetScope.DEVICE, command.getTarget().getScope());
        assertEquals("uav_01", command.getTarget().getDeviceCodes(0));
        assertEquals("{\"altitudeM\":50}", command.getParametersOrThrow("payload").getStringValue());
        assertEquals("hold position", command.getParametersOrThrow("detail").getStringValue());
        assertEquals("mission-unity-1", command.getParametersOrThrow("runtimeInstanceId").getStringValue());
    }

    @Test
    void shouldIncludeMissionIdForMissionScopedCommand() {
        MissionRunRepository missionRunRepository = mock(MissionRunRepository.class);
        MissionRun run = mock(MissionRun.class);
        when(run.getMissionId()).thenReturn(99L);
        when(missionRunRepository.findById(12L)).thenReturn(Optional.of(run));
        RosGatewayV1CommandDispatcher missionDispatcher = new RosGatewayV1CommandDispatcher(
                null,
                new DeviceCodeMapper(),
                missionRunRepository
        );
        RuntimeCommandRequest request = new RuntimeCommandRequest(
                CommandType.START_MISSION,
                12L,
                null,
                "{}",
                "start mission",
                RuntimeScope.MISSION_CENTER,
                null
        );

        UavUsvGatewayV1.GatewayEnvelope envelope = missionDispatcher.buildEnvelope(
                "command-1",
                request,
                8,
                Instant.parse("2026-08-09T10:04:16Z")
        );

        assertEquals("99", envelope.getMissionId());
        assertEquals("12", envelope.getRunId());
        assertEquals("MISSION.START", envelope.getControlCommand().getCommand());
    }

    @Test
    void shouldUseNewStreamIdentityForEachBackendBoot() {
        RosGatewayV1CommandDispatcher nextBoot = new RosGatewayV1CommandDispatcher(null, new DeviceCodeMapper());
        org.junit.jupiter.api.Assertions.assertNotEquals(
                dispatcher.controlStreamId(), nextBoot.controlStreamId());
        org.junit.jupiter.api.Assertions.assertTrue(dispatcher.controlStreamId().startsWith("platform.control."));
    }
}
