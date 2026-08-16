package com.uavusv.platform.module.gateway.v1;

import org.springframework.stereotype.Component;

import java.util.Locale;
import java.util.regex.Matcher;
import java.util.regex.Pattern;

@Component
public class DeviceCodeMapper {
    private static final Pattern PLATFORM = Pattern.compile("^(uav|usv)-(\\d{2})$");
    private static final Pattern ROS = Pattern.compile("^(uav|usv)_(\\d{2})$");

    public String toPlatform(String value) {
        return map(value, ROS, '-');
    }

    public String toRos(String value) {
        return map(value, PLATFORM, '_');
    }

    private String map(String value, Pattern alternate, char separator) {
        if (value == null || value.isBlank()) throw new IllegalArgumentException("Device code is required");
        String normalized = value.trim().toLowerCase(Locale.ROOT);
        Matcher platform = PLATFORM.matcher(normalized);
        Matcher ros = ROS.matcher(normalized);
        Matcher match = platform.matches() ? platform : (ros.matches() ? ros : null);
        if (match == null) throw new IllegalArgumentException("Unsupported device code: " + value);
        return match.group(1) + separator + match.group(2);
    }
}
