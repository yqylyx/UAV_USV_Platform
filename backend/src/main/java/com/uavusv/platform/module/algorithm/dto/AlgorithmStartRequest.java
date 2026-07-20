package com.uavusv.platform.module.algorithm.dto;

import com.uavusv.platform.module.algorithm.entity.AlgorithmType;
import jakarta.validation.Valid;
import jakarta.validation.constraints.AssertTrue;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.Size;

import java.util.List;
import java.util.Map;

public record AlgorithmStartRequest(
        @NotNull AlgorithmType algorithmType,
        @Size(max = 64) String targetId,
        @Valid PositionRequest targetPosition,
        @Valid PositionRequest threatPosition,
        List<String> uavIds,
        List<String> usvIds,
        PositionSource positionSource,
        @Valid List<ManualVehiclePositionRequest> manualVehiclePositions,
        Map<String, Object> parameters
) {
    @AssertTrue(message = "targetPosition is required for algorithm start")
    public boolean hasRequiredTargetPosition() {
        return algorithmType == null || targetPosition != null;
    }

    @AssertTrue(message = "threatPosition is required for escort defense")
    public boolean hasRequiredThreatPosition() {
        return algorithmType != AlgorithmType.ESCORT_DEFENSE || threatPosition != null;
    }

    @AssertTrue(message = "manualVehiclePositions is required for manual position source")
    public boolean hasRequiredManualVehiclePositions() {
        return resolvedPositionSource() != PositionSource.MANUAL
                || manualVehiclePositions != null && !manualVehiclePositions.isEmpty();
    }

    public PositionSource resolvedPositionSource() {
        return positionSource == null ? PositionSource.REALTIME : positionSource;
    }

    public enum PositionSource {
        REALTIME,
        MANUAL
    }

    public record ManualVehiclePositionRequest(
            @NotBlank String vehicleId,
            @NotNull @Valid PositionRequest position
    ) {
    }

    public record PositionRequest(
            @NotNull Double x,
            @NotNull Double y,
            @NotNull Double z,
            @NotNull Double heading
    ) {
        @AssertTrue(message = "position values must be finite numbers")
        public boolean hasFiniteValues() {
            return isFinite(x) && isFinite(y) && isFinite(z) && isFinite(heading);
        }

        private static boolean isFinite(Double value) {
            return value != null && Double.isFinite(value);
        }
    }
}
