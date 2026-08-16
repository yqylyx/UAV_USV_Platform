package com.uavusv.platform.config;

import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertDoesNotThrow;
import static org.junit.jupiter.api.Assertions.assertThrows;

class RosCommunicationPropertiesValidatorTests {
    @Test void acceptsV1AuthorityAndDispatch() {
        assertDoesNotThrow(() -> new RosCommunicationPropertiesValidator("v1", "v1", "ros-gateway-v1").validate());
    }
    @Test void acceptsDualTestWithSingleAuthority() {
        assertDoesNotThrow(() -> new RosCommunicationPropertiesValidator("dual-test", "v1", "ros-gateway-v1").validate());
    }
    @Test void rejectsAuthorityOutsideSelectedTransport() {
        assertThrows(IllegalStateException.class,
                () -> new RosCommunicationPropertiesValidator("v1", "legacy", "ros-gateway-v1").validate());
    }
    @Test void rejectsMismatchedCommandTransport() {
        assertThrows(IllegalStateException.class,
                () -> new RosCommunicationPropertiesValidator("legacy", "legacy", "ros-gateway-v1").validate());
    }
}
