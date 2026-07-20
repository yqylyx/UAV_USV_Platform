package com.uavusv.platform.module.algorithm.dto;

import java.util.List;

public record AlgorithmAssignmentsResponse(
        String commandId,
        String targetId,
        List<AlgorithmAssignmentItemResponse> assignments
) {
}
