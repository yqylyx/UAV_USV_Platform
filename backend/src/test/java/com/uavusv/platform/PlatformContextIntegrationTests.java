package com.uavusv.platform;

import com.uavusv.platform.module.monitoring.integration.RosPoseWebSocketClient;
import com.uavusv.platform.module.runtimecontrol.service.RuntimeControlService;
import org.junit.jupiter.api.Test;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.context.bean.override.mockito.MockitoBean;

import static org.assertj.core.api.Assertions.assertThat;

@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.MOCK)
class PlatformContextIntegrationTests {

    @MockitoBean
    private RosPoseWebSocketClient rosPoseWebSocketClient;

    @MockitoBean
    private RuntimeControlService runtimeControlService;

    @Test
    void contextLoadsWithFlywayAndJpaMappings() {
        assertThat(rosPoseWebSocketClient).isNotNull();
        assertThat(runtimeControlService).isNotNull();
    }
}
