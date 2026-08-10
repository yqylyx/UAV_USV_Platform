package com.uavusv.platform.module.gateway.v1;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.databind.node.ArrayNode;
import com.fasterxml.jackson.databind.node.ObjectNode;
import com.google.protobuf.InvalidProtocolBufferException;
import com.google.protobuf.Timestamp;
import org.springframework.stereotype.Component;
import uavusv.gateway.v1.UavUsvGatewayV1;

import java.time.Instant;

@Component
public class GatewayProtobufDecoder {

    private final ObjectMapper objectMapper;

    public GatewayProtobufDecoder(ObjectMapper objectMapper) {
        this.objectMapper = objectMapper;
    }

    public GatewayEnvelope decode(byte[] protobufBytes) {
        if (protobufBytes == null || protobufBytes.length == 0) {
            throw new IllegalArgumentException("Gateway protobuf payload must not be empty");
        }
        try {
            UavUsvGatewayV1.GatewayEnvelope envelope =
                    UavUsvGatewayV1.GatewayEnvelope.parseFrom(protobufBytes);
            GatewayMessageType type = GatewayMessageType.fromWireName(envelope.getMessageType());
            return new GatewayEnvelope(
                    envelope.getSpecVersion(),
                    type,
                    envelope.getSource(),
                    readTimestamp(envelope.hasTimestamp() ? envelope.getTimestamp() : null),
                    blankToNull(envelope.getRunId()),
                    streamId(envelope, type),
                    envelope.getSequence(),
                    payload(envelope)
            );
        } catch (InvalidProtocolBufferException exception) {
            throw new IllegalArgumentException("Invalid gateway protobuf envelope", exception);
        }
    }

    private JsonNode payload(UavUsvGatewayV1.GatewayEnvelope envelope) {
        return switch (envelope.getBodyCase()) {
            case GATEWAY_HELLO -> gatewayHello(envelope.getGatewayHello());
            case GATEWAY_HEARTBEAT -> gatewayHeartbeat(envelope.getGatewayHeartbeat());
            case POSE_BATCH -> poseBatch(envelope.getPoseBatch());
            case MISSION_STATUS -> missionStatus(envelope.getMissionStatus());
            case CONTROL_ACK -> controlAck(envelope.getControlAck());
            case CONTROL_FEEDBACK -> controlFeedback(envelope.getControlFeedback());
            case CONTROL_RESULT -> controlResult(envelope.getControlResult());
            default -> objectMapper.createObjectNode();
        };
    }

    private ObjectNode gatewayHello(UavUsvGatewayV1.GatewayHello message) {
        ObjectNode node = objectMapper.createObjectNode();
        node.put("instanceId", message.getInstanceId());
        node.set("supportedVersions", strings(message.getSupportedVersionsList()));
        ArrayNode runtimeModes = objectMapper.createArrayNode();
        message.getRuntimeModesList().forEach(mode -> runtimeModes.add(mode.name()));
        node.set("runtimeModes", runtimeModes);
        node.set("capabilities", strings(message.getCapabilitiesList()));
        node.put("binaryTelemetry", message.getBinaryTelemetry());
        node.put("bootId", message.getBootId());
        return node;
    }

    private ObjectNode gatewayHeartbeat(UavUsvGatewayV1.GatewayHeartbeat message) {
        ObjectNode node = objectMapper.createObjectNode();
        node.put("instanceId", message.getInstanceId());
        node.put("bootId", message.getBootId());
        node.put("uptimeMs", message.getUptimeMs());
        node.put("cpuPercent", message.getCpuPercent());
        node.put("memoryPercent", message.getMemoryPercent());
        return node;
    }

    private ObjectNode poseBatch(UavUsvGatewayV1.PoseBatch message) {
        ObjectNode node = objectMapper.createObjectNode();
        node.put("snapshotMode", message.getSnapshotMode().name());
        if (message.hasSnapshotTime()) {
            node.put("snapshotTime", readTimestamp(message.getSnapshotTime()).toString());
        }
        node.put("complete", message.getComplete());
        node.set("expectedDeviceCodes", strings(message.getExpectedDeviceCodesList()));
        node.set("missingDeviceCodes", strings(message.getMissingDeviceCodesList()));
        node.set("staleDeviceCodes", strings(message.getStaleDeviceCodesList()));
        ArrayNode vehicles = objectMapper.createArrayNode();
        message.getVehiclesList().forEach(vehicle -> vehicles.add(vehicle(vehicle)));
        node.set("vehicles", vehicles);
        node.put("freshnessThresholdMs", message.getFreshnessThresholdMs());
        return node;
    }

    private ObjectNode vehicle(UavUsvGatewayV1.VehiclePoseSample message) {
        ObjectNode node = objectMapper.createObjectNode();
        node.put("deviceCode", message.getDeviceCode());
        if (message.hasSourceTimestamp()) {
            node.put("sourceTimestamp", readTimestamp(message.getSourceTimestamp()).toString());
        }
        node.put("sourceSequence", message.getSourceSequence());
        node.put("ageMs", message.getAgeMs());
        node.put("fresh", message.getFresh());
        node.put("positionValid", message.getPositionValid());
        if (message.hasLocalPositionEnuM()) {
            node.set("localPositionEnuM", vector(message.getLocalPositionEnuM()));
        }
        if (message.hasGlobalPosition()) {
            ObjectNode globalPosition = objectMapper.createObjectNode();
            globalPosition.put("latitudeDeg", message.getGlobalPosition().getLatitudeDeg());
            globalPosition.put("longitudeDeg", message.getGlobalPosition().getLongitudeDeg());
            globalPosition.put("altitudeMslM", message.getGlobalPosition().getAltitudeMslM());
            node.set("globalPosition", globalPosition);
        }
        if (message.hasOrientation()) {
            ObjectNode orientation = objectMapper.createObjectNode();
            orientation.put("x", message.getOrientation().getX());
            orientation.put("y", message.getOrientation().getY());
            orientation.put("z", message.getOrientation().getZ());
            orientation.put("w", message.getOrientation().getW());
            node.set("orientation", orientation);
        }
        if (message.hasLinearVelocityMps()) {
            node.set("linearVelocityMps", vector(message.getLinearVelocityMps()));
        }
        node.put("headingDeg", message.getHeadingDeg());
        return node;
    }

    private ObjectNode missionStatus(UavUsvGatewayV1.MissionStatus message) {
        ObjectNode node = objectMapper.createObjectNode();
        node.put("missionId", message.getMissionId());
        node.put("runId", message.getRunId());
        node.put("state", message.getState());
        node.put("phase", message.getPhase());
        node.put("progress", message.getProgress());
        node.put("activeCommandId", message.getActiveCommandId());
        node.set("activeDeviceCodes", strings(message.getActiveDeviceCodesList()));
        return node;
    }

    private ObjectNode controlAck(UavUsvGatewayV1.ControlAck message) {
        ObjectNode node = objectMapper.createObjectNode();
        node.put("commandId", message.getCommandId());
        node.put("status", message.getStatus().name());
        node.put("code", message.getCode());
        node.put("message", message.getMessage());
        node.put("retryable", message.getRetryable());
        return node;
    }

    private ObjectNode controlFeedback(UavUsvGatewayV1.ControlFeedback message) {
        ObjectNode node = objectMapper.createObjectNode();
        node.put("commandId", message.getCommandId());
        node.put("status", message.getStatus().name());
        node.put("progress", message.getProgress());
        node.put("phase", message.getPhase());
        node.put("message", message.getMessage());
        node.set("activeDeviceCodes", strings(message.getActiveDeviceCodesList()));
        return node;
    }

    private ObjectNode controlResult(UavUsvGatewayV1.ControlResult message) {
        ObjectNode node = objectMapper.createObjectNode();
        node.put("commandId", message.getCommandId());
        node.put("status", message.getStatus().name());
        node.put("code", message.getCode());
        node.put("message", message.getMessage());
        if (message.hasStartedAt()) {
            node.put("startedAt", readTimestamp(message.getStartedAt()).toString());
        }
        if (message.hasCompletedAt()) {
            node.put("completedAt", readTimestamp(message.getCompletedAt()).toString());
        }
        ObjectNode metrics = objectMapper.createObjectNode();
        message.getMetricsMap().forEach((key, value) -> metrics.set(key, parameterValue(value)));
        node.set("metrics", metrics);
        return node;
    }

    private JsonNode parameterValue(UavUsvGatewayV1.ParameterValue value) {
        return switch (value.getValueCase()) {
            case STRING_VALUE -> objectMapper.getNodeFactory().textNode(value.getStringValue());
            case INT_VALUE -> objectMapper.getNodeFactory().numberNode(value.getIntValue());
            case DOUBLE_VALUE -> objectMapper.getNodeFactory().numberNode(value.getDoubleValue());
            case BOOL_VALUE -> objectMapper.getNodeFactory().booleanNode(value.getBoolValue());
            default -> objectMapper.nullNode();
        };
    }

    private ObjectNode vector(UavUsvGatewayV1.Vector3 value) {
        ObjectNode node = objectMapper.createObjectNode();
        node.put("x", value.getX());
        node.put("y", value.getY());
        node.put("z", value.getZ());
        return node;
    }

    private ArrayNode strings(java.util.List<String> values) {
        ArrayNode node = objectMapper.createArrayNode();
        values.forEach(node::add);
        return node;
    }

    private Instant readTimestamp(Timestamp timestamp) {
        if (timestamp == null) {
            return Instant.now();
        }
        return Instant.ofEpochSecond(timestamp.getSeconds(), timestamp.getNanos());
    }

    private String streamId(UavUsvGatewayV1.GatewayEnvelope envelope, GatewayMessageType type) {
        String value = blankToNull(envelope.getStreamId());
        return value == null ? type.wireName() : value;
    }

    private String blankToNull(String value) {
        return value == null || value.isBlank() ? null : value;
    }
}
