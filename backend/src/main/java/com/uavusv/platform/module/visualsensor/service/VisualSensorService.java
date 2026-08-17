package com.uavusv.platform.module.visualsensor.service;

import com.fasterxml.jackson.databind.JsonNode;
import com.uavusv.platform.module.visualsensor.dto.VisualSensorOverviewResponse;
import com.uavusv.platform.module.visualsensor.dto.VisualSensorResponse;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.stereotype.Service;

import java.time.Clock;
import java.util.ArrayList;
import java.util.Base64;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Optional;

@Service
public class VisualSensorService {

    private static final Logger log = LoggerFactory.getLogger(VisualSensorService.class);
    private static final long FRESH_FRAME_MILLIS = 3_500;
    private static final long DROP_LOG_INTERVAL_MILLIS = 5_000;
    private static final List<SensorDefinition> DEFINITIONS = List.of(
            new SensorDefinition("uav_01", "UAV-01", "UAV", "DOWN", "UAV-01 · 下视相机"),
            new SensorDefinition("uav_02", "UAV-02", "UAV", "DOWN", "UAV-02 · 下视相机"),
            new SensorDefinition("uav_03", "UAV-03", "UAV", "DOWN", "UAV-03 · 下视相机"),
            new SensorDefinition("usv_01", "USV-01", "USV", "FORWARD", "USV-01 · 前视相机"),
            new SensorDefinition("usv_02", "USV-02", "USV", "FORWARD", "USV-02 · 前视相机"),
            new SensorDefinition("usv_03", "USV-03", "USV", "FORWARD", "USV-03 · 前视相机")
    );

    private final Clock clock;
    private final Map<String, FrameState> frames = new LinkedHashMap<>();
    private final Map<String, Long> dropLogTimes = new LinkedHashMap<>();
    private volatile boolean gatewayConnected;
    private volatile String gatewayDetail = "等待视觉传感器网关";
    private volatile String focusedCameraId = "uav_01";

    public VisualSensorService() {
        this(Clock.systemUTC());
    }

    VisualSensorService(Clock clock) {
        this.clock = clock;
        for (SensorDefinition definition : DEFINITIONS) {
            frames.put(definition.cameraId(), new FrameState());
        }
    }

    public synchronized void observeFrame(JsonNode frame) {
        String cameraId = normalizeCameraId(frame.path("camera_id").asText(""));
        FrameState state = frames.get(cameraId);
        if (state == null || !"jpeg".equalsIgnoreCase(frame.path("encoding").asText("jpeg"))) {
            return;
        }

        String encoded = frame.path("jpeg_base64").asText("");
        if (encoded.isBlank()) {
            return;
        }

        byte[] jpeg;
        try {
            jpeg = Base64.getDecoder().decode(encoded);
        } catch (IllegalArgumentException exception) {
            return;
        }
        if (jpeg.length < 4) {
            return;
        }

        long now = clock.millis();
        if (state.receivedAtMillis > 0 && now > state.receivedAtMillis) {
            double instantFps = 1000.0 / (now - state.receivedAtMillis);
            state.fps = state.fps <= 0 ? instantFps : state.fps * 0.78 + instantFps * 0.22;
        }
        state.jpeg = jpeg;
        state.width = frame.path("width").asInt(0);
        state.height = frame.path("height").asInt(0);
        state.timestampMillis = frame.path("timestamp_ms").asLong(now);
        state.receivedAtMillis = now;
        state.source = frame.path("source").asText("ROS / Gazebo");
    }

    public synchronized boolean observeJpegFrame(
            String cameraId,
            String jpegBase64,
            int width,
            int height,
            long timestampMillis,
            double ageSeconds
    ) {
        String rawCameraId = cameraId;
        cameraId = normalizeCameraId(cameraId);
        if (!frames.containsKey(cameraId)) {
            logDroppedFrame(rawCameraId, "EMPTY_OR_UNMAPPED_CAMERA_ID");
            return false;
        }
        if (jpegBase64 == null || jpegBase64.isBlank()) {
            logDroppedFrame(rawCameraId, "EMPTY_JPEG");
            return false;
        }
        byte[] jpeg;
        try {
            jpeg = Base64.getDecoder().decode(jpegBase64);
        } catch (IllegalArgumentException exception) {
            logDroppedFrame(rawCameraId, "BASE64_DECODE_FAILED");
            return false;
        }
        if (jpeg.length < 4) {
            logDroppedFrame(rawCameraId, "JPEG_TOO_SHORT");
            return false;
        }
        long now = clock.millis();
        FrameState state = frames.get(cameraId);
        if (state.receivedAtMillis > 0 && now > state.receivedAtMillis) {
            double instantFps = 1000.0 / (now - state.receivedAtMillis);
            state.fps = state.fps <= 0 ? instantFps : state.fps * 0.78 + instantFps * 0.22;
        }
        state.jpeg = jpeg;
        state.width = width;
        state.height = height;
        state.timestampMillis = timestampMillis > 0
                ? timestampMillis
                : now - Math.max(0, Math.round(ageSeconds * 1000));
        state.receivedAtMillis = now;
        state.source = "ROS / Gazebo";
        return true;
    }

    public void observeGateway(boolean connected, String detail) {
        gatewayConnected = connected;
        gatewayDetail = detail == null || detail.isBlank()
                ? (connected ? "视觉传感器网关在线" : "视觉传感器网关离线")
                : detail;
    }

    public synchronized VisualSensorOverviewResponse overview() {
        long now = clock.millis();
        List<VisualSensorResponse> sensors = new ArrayList<>(DEFINITIONS.size());
        int online = 0;
        for (SensorDefinition definition : DEFINITIONS) {
            FrameState state = frames.get(definition.cameraId());
            boolean fresh = state.receivedAtMillis > 0 && now - state.receivedAtMillis <= FRESH_FRAME_MILLIS;
            if (fresh) {
                online++;
            }
            long latency = state.timestampMillis > 0 ? Math.max(0, now - state.timestampMillis) : -1;
            sensors.add(new VisualSensorResponse(
                    definition.cameraId(),
                    definition.deviceCode(),
                    definition.deviceType(),
                    definition.viewType(),
                    definition.displayName(),
                    fresh ? "ONLINE" : state.receivedAtMillis > 0 ? "STALE" : "WAITING",
                    state.source,
                    state.width,
                    state.height,
                    Math.round(state.fps * 10.0) / 10.0,
                    latency,
                    state.timestampMillis,
                    definition.cameraId().equals(focusedCameraId)
            ));
        }
        return new VisualSensorOverviewResponse(
                gatewayConnected,
                gatewayDetail,
                online,
                DEFINITIONS.size(),
                focusedCameraId,
                sensors
        );
    }

    public void focus(String cameraId) {
        if (!frames.containsKey(cameraId)) {
            throw new IllegalArgumentException("未知视觉传感器: " + cameraId);
        }
        focusedCameraId = cameraId;
    }

    public String focusedCameraId() {
        return focusedCameraId;
    }

    public synchronized Optional<byte[]> latestFrame(String cameraId) {
        FrameState state = frames.get(cameraId);
        if (state == null || state.jpeg == null) {
            return Optional.empty();
        }
        return Optional.of(state.jpeg.clone());
    }

    public List<String> cameraIds() {
        return DEFINITIONS.stream().map(SensorDefinition::cameraId).toList();
    }

    static String normalizeCameraId(String cameraId) {
        if (cameraId == null || cameraId.isBlank()) {
            return "";
        }
        return switch (cameraId.trim()) {
            case "uav_01_down" -> "uav_01";
            case "uav_02_down" -> "uav_02";
            case "uav_03_down" -> "uav_03";
            case "usv_01_front" -> "usv_01";
            case "usv_02_front" -> "usv_02";
            case "usv_03_front" -> "usv_03";
            default -> cameraId.trim();
        };
    }

    private void logDroppedFrame(String cameraId, String reason) {
        String displayCameraId = cameraId == null || cameraId.isBlank() ? "<empty>" : cameraId.trim();
        String key = displayCameraId + ":" + reason;
        long now = clock.millis();
        Long previous = dropLogTimes.get(key);
        if (previous != null && now - previous < DROP_LOG_INTERVAL_MILLIS) {
            return;
        }
        dropLogTimes.put(key, now);
        log.warn("Dropped camera frame: cameraId={} reason={}", displayCameraId, reason);
    }

    private record SensorDefinition(
            String cameraId,
            String deviceCode,
            String deviceType,
            String viewType,
            String displayName
    ) {
    }

    private static final class FrameState {
        private byte[] jpeg;
        private int width;
        private int height;
        private double fps;
        private long timestampMillis;
        private long receivedAtMillis;
        private String source = "ROS / Gazebo";
    }
}
