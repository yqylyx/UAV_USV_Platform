package com.uavusv.platform.module.monitoring;

import com.uavusv.platform.common.exception.GlobalExceptionHandler;
import com.uavusv.platform.module.monitoring.integration.IntegrationController;
import com.uavusv.platform.module.monitoring.service.RuntimeStateService;
import com.uavusv.platform.module.runtimecontrol.service.RuntimeControlService;
import org.junit.jupiter.api.Test;
import org.springframework.test.web.servlet.setup.MockMvcBuilders;
import static org.mockito.Mockito.*;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

class IntegrationHeartbeatErrorTests {
    @Test
    void wrongTokenReturns401WithoutUpdatingHeartbeat() throws Exception {
        var runtime = mock(RuntimeStateService.class);
        var controller = new IntegrationController(runtime, mock(RuntimeControlService.class), "test-only");
        var mvc = MockMvcBuilders.standaloneSetup(controller)
                .setControllerAdvice(new GlobalExceptionHandler()).build();
        mvc.perform(post("/api/integration/heartbeat").contentType("application/json")
                .header("X-Platform-Token", "wrong")
                .content("{\"componentCode\":\"unity-client-01\",\"instanceId\":\"overview-test\",\"state\":\"ONLINE\",\"detail\":\"test\",\"rosConnectionStatus\":\"OFFLINE\"}"))
                .andExpect(status().isUnauthorized());
        verifyNoInteractions(runtime);
    }
}
