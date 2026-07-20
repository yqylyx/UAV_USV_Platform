package com.uavusv.platform.module.algorithm.dto;

import com.uavusv.platform.module.algorithm.entity.AlgorithmAssignmentRole;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Size;

public record AlgorithmAssignmentItemRequest(
        @NotBlank @Size(max = 64) String vehicleId,
        @Size(max = 64) String vehicleCode,
        AlgorithmAssignmentRole role,
        Double x,
        Double y,
        Double z,
        Double heading,
        @Size(max = 1000) String detail
) {
}
