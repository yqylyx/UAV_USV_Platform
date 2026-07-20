package com.uavusv.platform.module.algorithm.dto;

import com.uavusv.platform.module.algorithm.entity.AlgorithmAssignment;
import com.uavusv.platform.module.algorithm.entity.AlgorithmAssignmentRole;

public record AlgorithmAssignmentItemResponse(
        String vehicleId,
        String vehicleCode,
        AlgorithmAssignmentRole role,
        Double x,
        Double y,
        Double z,
        Double heading,
        String detail
) {
    public static AlgorithmAssignmentItemResponse from(AlgorithmAssignment assignment) {
        return new AlgorithmAssignmentItemResponse(
                assignment.getVehicleId(),
                assignment.getVehicleCode(),
                assignment.getRole(),
                assignment.getX(),
                assignment.getY(),
                assignment.getZ(),
                assignment.getHeading(),
                assignment.getDetail()
        );
    }
}
