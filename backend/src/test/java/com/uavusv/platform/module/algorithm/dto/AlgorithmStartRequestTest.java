package com.uavusv.platform.module.algorithm.dto;

import com.uavusv.platform.module.algorithm.entity.AlgorithmType;
import jakarta.validation.Validation;
import jakarta.validation.Validator;
import jakarta.validation.ValidatorFactory;
import org.junit.jupiter.api.AfterAll;
import org.junit.jupiter.api.BeforeAll;
import org.junit.jupiter.api.Test;

import java.util.List;
import java.util.Map;

import static org.assertj.core.api.Assertions.assertThat;

class AlgorithmStartRequestTest {

    private static ValidatorFactory validatorFactory;
    private static Validator validator;

    @BeforeAll
    static void setUpValidator() {
        validatorFactory = Validation.buildDefaultValidatorFactory();
        validator = validatorFactory.getValidator();
    }

    @AfterAll
    static void closeValidator() {
        validatorFactory.close();
    }

    @Test
    void captureWithCompleteTargetPositionPassesValidation() {
        AlgorithmStartRequest request = request(
                AlgorithmType.CAPTURE,
                position(10.0, 20.0, 0.0, 90.0),
                null
        );

        assertThat(validator.validate(request)).isEmpty();
    }

    @Test
    void captureWithoutTargetPositionFailsValidation() {
        AlgorithmStartRequest request = request(AlgorithmType.CAPTURE, null, null);

        assertThat(validator.validate(request)).isNotEmpty();
    }

    @Test
    void escortDefenseWithCompleteTargetAndThreatPositionsPassesValidation() {
        AlgorithmStartRequest request = request(
                AlgorithmType.ESCORT_DEFENSE,
                position(10.0, 20.0, 0.0, 90.0),
                position(30.0, 40.0, 0.0, 180.0)
        );

        assertThat(validator.validate(request)).isEmpty();
    }

    @Test
    void escortDefenseWithoutThreatPositionFailsValidation() {
        AlgorithmStartRequest request = request(
                AlgorithmType.ESCORT_DEFENSE,
                position(10.0, 20.0, 0.0, 90.0),
                null
        );

        assertThat(validator.validate(request)).isNotEmpty();
    }

    @Test
    void coordinateNullFieldFailsValidation() {
        AlgorithmStartRequest request = request(
                AlgorithmType.CAPTURE,
                position(null, 20.0, 0.0, 90.0),
                null
        );

        assertThat(validator.validate(request)).isNotEmpty();
    }

    @Test
    void coordinateNanFailsValidation() {
        AlgorithmStartRequest request = request(
                AlgorithmType.CAPTURE,
                position(Double.NaN, 20.0, 0.0, 90.0),
                null
        );

        assertThat(validator.validate(request)).isNotEmpty();
    }

    @Test
    void coordinateInfinityFailsValidation() {
        AlgorithmStartRequest request = request(
                AlgorithmType.CAPTURE,
                position(Double.POSITIVE_INFINITY, 20.0, 0.0, 90.0),
                null
        );

        assertThat(validator.validate(request)).isNotEmpty();
    }

    @Test
    void legalNegativeCoordinatesPassValidation() {
        AlgorithmStartRequest request = request(
                AlgorithmType.CAPTURE,
                position(-10.0, -20.0, -5.0, 90.0),
                null
        );

        assertThat(validator.validate(request)).isEmpty();
    }

    @Test
    void finiteHeadingOutsideCompassRangePassesValidation() {
        AlgorithmStartRequest negativeHeading = request(
                AlgorithmType.CAPTURE,
                position(10.0, 20.0, 0.0, -45.0),
                null
        );
        AlgorithmStartRequest overFullCircleHeading = request(
                AlgorithmType.CAPTURE,
                position(10.0, 20.0, 0.0, 450.0),
                null
        );

        assertThat(validator.validate(negativeHeading)).isEmpty();
        assertThat(validator.validate(overFullCircleHeading)).isEmpty();
    }

    @Test
    void nullPositionSourceKeepsRealtimeCompatibility() {
        AlgorithmStartRequest request = request(
                AlgorithmType.CAPTURE,
                position(10.0, 20.0, 0.0, 90.0),
                null
        );

        assertThat(request.resolvedPositionSource()).isEqualTo(AlgorithmStartRequest.PositionSource.REALTIME);
        assertThat(validator.validate(request)).isEmpty();
    }

    @Test
    void explicitRealtimeDoesNotRequireManualVehiclePositions() {
        AlgorithmStartRequest request = request(
                AlgorithmType.CAPTURE,
                position(10.0, 20.0, 0.0, 90.0),
                null,
                AlgorithmStartRequest.PositionSource.REALTIME,
                null
        );

        assertThat(validator.validate(request)).isEmpty();
    }

    @Test
    void manualWithoutManualVehiclePositionsFailsValidation() {
        AlgorithmStartRequest request = request(
                AlgorithmType.CAPTURE,
                position(10.0, 20.0, 0.0, 90.0),
                null,
                AlgorithmStartRequest.PositionSource.MANUAL,
                null
        );

        assertThat(validator.validate(request)).isNotEmpty();
    }

    @Test
    void manualWithEmptyManualVehiclePositionsFailsValidation() {
        AlgorithmStartRequest request = request(
                AlgorithmType.CAPTURE,
                position(10.0, 20.0, 0.0, 90.0),
                null,
                AlgorithmStartRequest.PositionSource.MANUAL,
                List.of()
        );

        assertThat(validator.validate(request)).isNotEmpty();
    }

    @Test
    void manualVehicleIdBlankFailsValidation() {
        AlgorithmStartRequest request = manualRequest(List.of(manualPosition(" ", position(1.0, 2.0, 3.0, 0.5))));

        assertThat(validator.validate(request)).isNotEmpty();
    }

    @Test
    void manualPositionNullFailsValidation() {
        AlgorithmStartRequest request = manualRequest(List.of(manualPosition("uav_01", null)));

        assertThat(validator.validate(request)).isNotEmpty();
    }

    @Test
    void manualCoordinateNullFailsValidation() {
        AlgorithmStartRequest request = manualRequest(List.of(manualPosition("uav_01", position(null, 2.0, 3.0, 0.5))));

        assertThat(validator.validate(request)).isNotEmpty();
    }

    @Test
    void manualCoordinateNanFailsValidation() {
        AlgorithmStartRequest request = manualRequest(List.of(manualPosition("uav_01", position(Double.NaN, 2.0, 3.0, 0.5))));

        assertThat(validator.validate(request)).isNotEmpty();
    }

    @Test
    void manualCoordinateInfinityFailsValidation() {
        AlgorithmStartRequest request = manualRequest(List.of(manualPosition("uav_01", position(Double.NEGATIVE_INFINITY, 2.0, 3.0, 0.5))));

        assertThat(validator.validate(request)).isNotEmpty();
    }

    @Test
    void manualLegalNegativeCoordinatesPassValidation() {
        AlgorithmStartRequest request = manualRequest(List.of(manualPosition("uav_01", position(-1.0, -2.0, -3.0, 0.5))));

        assertThat(validator.validate(request)).isEmpty();
    }

    @Test
    void manualFiniteHeadingOutsideCompassRangePassesValidation() {
        AlgorithmStartRequest request = manualRequest(List.of(manualPosition("uav_01", position(1.0, 2.0, 3.0, -720.0))));

        assertThat(validator.validate(request)).isEmpty();
    }

    private static AlgorithmStartRequest request(
            AlgorithmType algorithmType,
            AlgorithmStartRequest.PositionRequest targetPosition,
            AlgorithmStartRequest.PositionRequest threatPosition
    ) {
        return request(algorithmType, targetPosition, threatPosition, null, null);
    }

    private static AlgorithmStartRequest request(
            AlgorithmType algorithmType,
            AlgorithmStartRequest.PositionRequest targetPosition,
            AlgorithmStartRequest.PositionRequest threatPosition,
            AlgorithmStartRequest.PositionSource positionSource,
            List<AlgorithmStartRequest.ManualVehiclePositionRequest> manualVehiclePositions
    ) {
        return new AlgorithmStartRequest(
                algorithmType,
                "target_01",
                targetPosition,
                threatPosition,
                List.of("uav_01"),
                List.of("usv_01"),
                positionSource,
                manualVehiclePositions,
                Map.of()
        );
    }

    private static AlgorithmStartRequest manualRequest(
            List<AlgorithmStartRequest.ManualVehiclePositionRequest> manualVehiclePositions
    ) {
        return request(
                AlgorithmType.CAPTURE,
                position(10.0, 20.0, 0.0, 90.0),
                null,
                AlgorithmStartRequest.PositionSource.MANUAL,
                manualVehiclePositions
        );
    }

    private static AlgorithmStartRequest.ManualVehiclePositionRequest manualPosition(
            String vehicleId,
            AlgorithmStartRequest.PositionRequest position
    ) {
        return new AlgorithmStartRequest.ManualVehiclePositionRequest(vehicleId, position);
    }

    private static AlgorithmStartRequest.PositionRequest position(
            Double x,
            Double y,
            Double z,
            Double heading
    ) {
        return new AlgorithmStartRequest.PositionRequest(x, y, z, heading);
    }
}
