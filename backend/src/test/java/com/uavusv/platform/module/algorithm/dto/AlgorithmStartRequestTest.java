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

    private static AlgorithmStartRequest request(
            AlgorithmType algorithmType,
            AlgorithmStartRequest.PositionRequest targetPosition,
            AlgorithmStartRequest.PositionRequest threatPosition
    ) {
        return new AlgorithmStartRequest(
                algorithmType,
                "target_01",
                targetPosition,
                threatPosition,
                List.of("uav_01"),
                List.of("usv_01"),
                Map.of()
        );
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
