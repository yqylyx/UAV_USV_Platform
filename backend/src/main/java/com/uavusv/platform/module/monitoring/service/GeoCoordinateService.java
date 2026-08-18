package com.uavusv.platform.module.monitoring.service;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Component;

/**
 * Converts Unity's local scene coordinates to WGS84 coordinates when a
 * calibrated scene origin is configured. With the default disabled setting
 * callers receive no coordinate instead of fabricated demo data.
 */
@Component
public class GeoCoordinateService {

    private static final double EARTH_RADIUS_METERS = 6_378_137.0;

    private final boolean enabled;
    private final double originLatitude;
    private final double originLongitude;
    private final String eastAxis;
    private final String northAxis;

    public GeoCoordinateService(
            @Value("${app.runtime.geo-origin.enabled:false}") boolean enabled,
            @Value("${app.runtime.geo-origin.latitude:0}") double originLatitude,
            @Value("${app.runtime.geo-origin.longitude:0}") double originLongitude,
            @Value("${app.runtime.geo-origin.east-axis:X}") String eastAxis,
            @Value("${app.runtime.geo-origin.north-axis:Z}") String northAxis
    ) {
        this.enabled = enabled;
        this.originLatitude = originLatitude;
        this.originLongitude = originLongitude;
        this.eastAxis = normalizeAxis(eastAxis, "X");
        this.northAxis = normalizeAxis(northAxis, "Z");
    }

    public GeoCoordinate fromLocal(Double x, Double y, Double z) {
        if (!enabled || x == null || y == null || z == null) {
            return null;
        }

        double east = axisValue(eastAxis, x, y, z);
        double north = axisValue(northAxis, x, y, z);
        double latitudeRadians = Math.toRadians(originLatitude);
        double latitude = originLatitude + Math.toDegrees(north / EARTH_RADIUS_METERS);
        double longitude = originLongitude + Math.toDegrees(
                east / (EARTH_RADIUS_METERS * Math.max(0.000001, Math.cos(latitudeRadians)))
        );
        return new GeoCoordinate(latitude, longitude);
    }

    private static String normalizeAxis(String axis, String fallback) {
        if (axis == null || axis.isBlank()) {
            return fallback;
        }
        String normalized = axis.trim().toUpperCase();
        return switch (normalized) {
            case "X", "-X", "Y", "-Y", "Z", "-Z" -> normalized;
            default -> fallback;
        };
    }

    private static double axisValue(String axis, double x, double y, double z) {
        double sign = axis.startsWith("-") ? -1.0 : 1.0;
        String component = axis.startsWith("-") ? axis.substring(1) : axis;
        return sign * switch (component) {
            case "Y" -> y;
            case "Z" -> z;
            default -> x;
        };
    }

    public record GeoCoordinate(double latitude, double longitude) {
    }
}
