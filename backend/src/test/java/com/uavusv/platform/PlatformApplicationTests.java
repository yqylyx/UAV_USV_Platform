package com.uavusv.platform;

import org.junit.jupiter.api.Test;

import static org.assertj.core.api.Assertions.assertThat;

class PlatformApplicationTests {

    @Test
    void projectUsesJava17OrNewer() {
        assertThat(Runtime.version().feature()).isGreaterThanOrEqualTo(17);
    }
}
