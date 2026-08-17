package com.uavusv.platform.module.runtimecontrol.dispatch;

import com.google.protobuf.Timestamp;
import com.uavusv.platform.module.gateway.v1.RosGatewayV1WebSocketClient;
import com.uavusv.platform.module.gateway.v1.DeviceCodeMapper;
import com.uavusv.platform.module.mission.entity.MissionRun;
import com.uavusv.platform.module.mission.repository.MissionRunRepository;
import com.uavusv.platform.module.runtimecontrol.dto.RuntimeCommandRequest;
import com.uavusv.platform.module.runtimecontrol.entity.CommandType;
import com.uavusv.platform.module.runtimecontrol.entity.RuntimeScope;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.stereotype.Component;
import uavusv.gateway.v1.UavUsvGatewayV1;

import java.time.Instant;
import java.util.UUID;
import java.util.concurrent.atomic.AtomicLong;

@Component
@ConditionalOnProperty(name = "app.control.command-dispatch-mode", havingValue = "ros-gateway-v1")
public class RosGatewayV1CommandDispatcher implements RuntimeCommandDispatcher {

    private static final Logger log = LoggerFactory.getLogger(RosGatewayV1CommandDispatcher.class);
    private static final String SPEC_VERSION = "1.0";
    private static final String SOURCE = "uav-usv-platform-backend";

    private final RosGatewayV1WebSocketClient rosGatewayV1WebSocketClient;
    private final AtomicLong sequence = new AtomicLong();
    private final String controlStreamId;
    private final DeviceCodeMapper deviceCodeMapper;
    private final MissionRunRepository missionRunRepository;

    public RosGatewayV1CommandDispatcher(
            RosGatewayV1WebSocketClient rosGatewayV1WebSocketClient,
            DeviceCodeMapper deviceCodeMapper,
            MissionRunRepository missionRunRepository
    ) {
        this.rosGatewayV1WebSocketClient = rosGatewayV1WebSocketClient;
        this.deviceCodeMapper = deviceCodeMapper;
        this.missionRunRepository = missionRunRepository;
        this.controlStreamId = "platform.control." + UUID.randomUUID().toString().substring(0, 8);
        log.info("ROS Gateway control stream initialized: {}", controlStreamId);
    }

    RosGatewayV1CommandDispatcher(
            RosGatewayV1WebSocketClient rosGatewayV1WebSocketClient,
            DeviceCodeMapper deviceCodeMapper
    ) {
        this(rosGatewayV1WebSocketClient, deviceCodeMapper, null);
    }

    @Override
    public CommandDispatchResult dispatch(String commandKey, RuntimeCommandRequest request) {
        log.info("[runtime-control-dispatcher] mode=ros-gateway-v1 commandKey={} commandType={} deviceCode={} scope={}",
                commandKey, request.commandType(), request.deviceCode(), request.runtimeScope());
        UavUsvGatewayV1.GatewayEnvelope envelope = buildEnvelope(
                commandKey,
                request,
                sequence.incrementAndGet(),
                Instant.now()
        );
        rosGatewayV1WebSocketClient.sendBinaryEnvelope(envelope.toByteArray());
        log.info("[runtime-control-dispatcher] mode=ros-gateway-v1 sent commandKey={} messageType={} streamId={} sequence={}",
                commandKey, envelope.getMessageType(), envelope.getStreamId(), envelope.getSequence());
        return CommandDispatchResult.dispatched("Command sent to ROS Gateway v1");
    }

    UavUsvGatewayV1.GatewayEnvelope buildEnvelope(
            String commandKey,
            RuntimeCommandRequest request,
            long sequence,
            Instant now
    ) {
        UavUsvGatewayV1.ControlCommand.Builder command = UavUsvGatewayV1.ControlCommand.newBuilder()
                .setCommandId(commandKey)
                .setClientRequestId(commandKey)
                .setCommand(request.commandType().name())
                .setPriority(priority(request))
                .setTarget(target(request));

        putStringParameter(command, "payload", request.payload());
        putStringParameter(command, "detail", request.detail());
        putStringParameter(command, "runtimeInstanceId", request.runtimeInstanceId());

        UavUsvGatewayV1.GatewayEnvelope.Builder envelope = UavUsvGatewayV1.GatewayEnvelope.newBuilder()
                .setSpecVersion(SPEC_VERSION)
                .setMessageType("control.command")
                .setMessageId(UUID.randomUUID().toString().replace("-", ""))
                .setTimestamp(timestamp(now))
                .setStreamId(controlStreamId)
                .setSequence(sequence)
                .setSource(SOURCE)
                .setControlCommand(command);

        if (request.runId() != null) {
            envelope.setRunId(String.valueOf(request.runId()));
            Long missionId = resolveMissionId(request.runId());
            if (missionId != null) {
                envelope.setMissionId(String.valueOf(missionId));
            }
        }
        if (request.deviceCode() != null && !request.deviceCode().isBlank()) {
            envelope.setDeviceCode(deviceCodeMapper.toRos(request.deviceCode()));
        }
        return envelope.build();
    }

    String controlStreamId() {
        return controlStreamId;
    }

    private UavUsvGatewayV1.CommandTarget target(RuntimeCommandRequest request) {
        UavUsvGatewayV1.CommandTarget.Builder target = UavUsvGatewayV1.CommandTarget.newBuilder();
        if (request.deviceCode() != null && !request.deviceCode().isBlank()) {
            return target
                    .setScope(UavUsvGatewayV1.TargetScope.DEVICE)
                    .addDeviceCodes(deviceCodeMapper.toRos(request.deviceCode()))
                    .build();
        }
        if (request.runId() != null || request.runtimeScope() == RuntimeScope.MISSION_CENTER) {
            return target.setScope(UavUsvGatewayV1.TargetScope.MISSION_SCOPE).build();
        }
        return target.setScope(UavUsvGatewayV1.TargetScope.SYSTEM).build();
    }

    private UavUsvGatewayV1.Priority priority(RuntimeCommandRequest request) {
        if (isEmergency(request.commandType())) {
            return UavUsvGatewayV1.Priority.EMERGENCY;
        }
        if (request.runId() != null || request.runtimeScope() == RuntimeScope.MISSION_CENTER) {
            return UavUsvGatewayV1.Priority.MISSION;
        }
        return UavUsvGatewayV1.Priority.MANUAL;
    }

    private boolean isEmergency(CommandType commandType) {
        return commandType.name().contains("EMERGENCY");
    }

    private Long resolveMissionId(Long runId) {
        if (missionRunRepository == null || runId == null) {
            return null;
        }
        return missionRunRepository.findById(runId)
                .map(MissionRun::getMissionId)
                .orElse(null);
    }

    private void putStringParameter(
            UavUsvGatewayV1.ControlCommand.Builder command,
            String key,
            String value
    ) {
        if (value == null || value.isBlank()) {
            return;
        }
        command.putParameters(
                key,
                UavUsvGatewayV1.ParameterValue.newBuilder().setStringValue(value).build()
        );
    }

    private Timestamp timestamp(Instant instant) {
        return Timestamp.newBuilder()
                .setSeconds(instant.getEpochSecond())
                .setNanos(instant.getNano())
                .build();
    }
}
