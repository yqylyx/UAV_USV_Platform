package com.uavusv.platform.module.sensor.service;

import com.fasterxml.jackson.databind.JsonNode;
import com.uavusv.platform.module.sensor.dto.RadarItemResponse;
import com.uavusv.platform.module.sensor.dto.RadarOverviewResponse;
import org.springframework.stereotype.Service;

import java.time.Clock;
import java.util.ArrayList;
import java.util.Comparator;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

@Service
public class SensorRuntimeService {

    private static final long FRESH_RADAR_MILLIS = 5_000;

    private final Clock clock;
    private final Map<String, RadarState> radars = new LinkedHashMap<>();

    public SensorRuntimeService() {
        this(Clock.systemUTC());
    }

    SensorRuntimeService(Clock clock) {
        this.clock = clock;
    }

    public synchronized void observeRadarFrame(JsonNode frame) {
        String deviceId = text(frame, "device_id", text(frame, "deviceId", "radar"));
        long now = clock.millis();
        long timestampMs = timestampMs(frame, now);
        List<RadarItemResponse> obstacles = parseItems(frame.path("obstacles"), deviceId, "OBSTACLE", timestampMs);
        List<RadarItemResponse> detections = parseItems(frame.path("detections"), deviceId, "DETECTION", timestampMs);
        if (detections.isEmpty()) {
            detections = parseItems(frame.path("targets"), deviceId, "DETECTION", timestampMs);
        }
        radars.put(deviceId, new RadarState(now, timestampMs, obstacles, detections));
    }

    public synchronized void observePointCloudFrame(JsonNode frame) {
        JsonNode data = frame.has("data") ? frame.path("data") : frame;
        String streamId = text(data, "stream_id", text(data, "streamId", "pointcloud"));
        String deviceId = text(data, "vehicle_id", text(data, "vehicleId", streamId));
        long now = clock.millis();
        long timestampMs = timestampMs(data, timestampMs(frame, now));
        List<RadarItemResponse> points = parsePointCloud(data.path("xyz"), streamId, deviceId, timestampMs);
        radars.put(deviceId, new RadarState(now, timestampMs, List.of(), points));
    }

    public synchronized RadarOverviewResponse radarOverview() {
        long now = clock.millis();
        List<RadarState> freshStates = radars.values().stream()
                .filter(state -> now - state.receivedAtMs <= FRESH_RADAR_MILLIS)
                .toList();
        List<RadarItemResponse> items = new ArrayList<>();
        freshStates.forEach(state -> {
            items.addAll(state.obstacles);
            items.addAll(state.detections);
        });
        Double nearest = items.stream()
                .filter(item -> ("OBSTACLE".equals(item.kind()) || "POINTCLOUD".equals(item.kind())) && item.range() != null)
                .map(RadarItemResponse::range)
                .min(Comparator.naturalOrder())
                .orElse(null);
        String latestTargetId = freshStates.stream()
                .flatMap(state -> state.detections.stream())
                .max(Comparator.comparingLong(RadarItemResponse::timestampMs))
                .map(RadarItemResponse::id)
                .orElse("");
        long updatedAt = freshStates.stream()
                .mapToLong(state -> state.timestampMs)
                .max()
                .orElse(0);
        return new RadarOverviewResponse(
                !freshStates.isEmpty(),
                freshStates.size(),
                radars.size(),
                updatedAt,
                (int) items.stream().filter(item -> "OBSTACLE".equals(item.kind())).count(),
                (int) items.stream().filter(item -> "DETECTION".equals(item.kind()) || "POINTCLOUD".equals(item.kind())).count(),
                nearest,
                latestTargetId,
                items
        );
    }

    private List<RadarItemResponse> parseItems(JsonNode array, String deviceId, String kind, long timestampMs) {
        if (!array.isArray()) {
            return List.of();
        }
        List<RadarItemResponse> items = new ArrayList<>();
        int index = 1;
        for (JsonNode item : array) {
            items.add(new RadarItemResponse(
                    text(item, "id", kind.toLowerCase() + "-" + index),
                    deviceId,
                    kind,
                    optionalNumber(item, "range"),
                    optionalNumber(item, "bearing"),
                    optionalNumber(item, "x"),
                    optionalNumber(item, "y"),
                    optionalNumber(item, "z"),
                    optionalNumber(item, "confidence"),
                    number(item, "timestamp_ms", timestampMs).longValue()
            ));
            index++;
        }
        return items;
    }

    private List<RadarItemResponse> parsePointCloud(JsonNode xyz, String streamId, String deviceId, long timestampMs) {
        if (!xyz.isArray()) {
            return List.of();
        }
        List<RadarItemResponse> points = new ArrayList<>();
        int pointCount = xyz.size() / 3;
        for (int index = 0; index < pointCount; index++) {
            double x = xyz.get(index * 3).asDouble();
            double y = xyz.get(index * 3 + 1).asDouble();
            double z = xyz.get(index * 3 + 2).asDouble();
            points.add(new RadarItemResponse(
                    streamId + "-" + (index + 1),
                    deviceId,
                    "POINTCLOUD",
                    Math.sqrt(x * x + y * y),
                    null,
                    x,
                    y,
                    z,
                    null,
                    timestampMs
            ));
        }
        return points;
    }

    private static String text(JsonNode node, String field, String fallback) {
        String value = node.path(field).asText("");
        return value.isBlank() ? fallback : value;
    }

    private static Number number(JsonNode node, String field, Number fallback) {
        JsonNode value = node.path(field);
        return value.isNumber() ? value.numberValue() : fallback;
    }

    private static long timestampMs(JsonNode node, Number fallback) {
        Number value = number(node, "timestamp_ms", number(node, "timestampMs", number(node, "timestamp", fallback)));
        double timestamp = value.doubleValue();
        return timestamp < 10_000_000_000D ? Math.round(timestamp * 1000D) : Math.round(timestamp);
    }

    private static Double optionalNumber(JsonNode node, String field) {
        JsonNode value = node.path(field);
        return value.isNumber() ? value.asDouble() : null;
    }

    private record RadarState(
            long receivedAtMs,
            long timestampMs,
            List<RadarItemResponse> obstacles,
            List<RadarItemResponse> detections
    ) {
    }
}
