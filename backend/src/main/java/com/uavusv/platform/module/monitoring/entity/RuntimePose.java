package com.uavusv.platform.module.monitoring.entity;

public record RuntimePose(
        double positionX,
        double positionY,
        double positionZ,
        double orientationX,
        double orientationY,
        double orientationZ,
        double orientationW
) {
}
