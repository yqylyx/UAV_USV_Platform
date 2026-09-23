package com.uavusv.platform.module.voiceintelligence;

import static org.mockito.Mockito.*;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.*;
import static org.springframework.security.test.web.servlet.setup.SecurityMockMvcConfigurers.springSecurity;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.*;

import com.uavusv.platform.module.voicecontrol.RuntimeContextRegistry;

import org.junit.jupiter.api.*;
import org.springframework.context.annotation.*;
import org.springframework.mock.web.MockServletContext;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.setup.MockMvcBuilders;
import org.springframework.web.context.support.AnnotationConfigWebApplicationContext;

class IntentHttpTests {
    @Configuration
    @Import({AsrHttpTests.Config.class, IntentService.class})
    static class Config {
        @Bean
        RuntimeContextRegistry runtimes() {
            return mock(RuntimeContextRegistry.class);
        }
    }

    AnnotationConfigWebApplicationContext context;
    MockMvc mvc;

    @BeforeEach
    void setup() {
        context = new AnnotationConfigWebApplicationContext();
        context.setServletContext(new MockServletContext());
        context.register(Config.class);
        context.refresh();
        mvc =
                MockMvcBuilders.webAppContextSetup(context)
                        .apply(springSecurity())
                        .build();
    }

    @AfterEach
    void close() {
        context.close();
    }

    org.springframework.test.web.servlet.request.MockHttpServletRequestBuilder request(String id) {
        return post("/api/voice/intelligence/interpretations")
                .contentType("application/json")
                .header("X-Request-ID", id)
                .header("Idempotency-Key", id)
                .content(
                        """
                        {"requestId":"%s","text":"暂停当前任务","locale":"zh-CN",
                         "allowedActions":["START","PAUSE","RESUME","STOP"],
                         "availableDeviceCodes":[],"runtimeContext":null}
                        """
                                .formatted(id));
    }

    @Test
    void loginAndCsrfAreRequired() throws Exception {
        String id = java.util.UUID.randomUUID().toString();
        mvc.perform(request(id)).andExpect(status().isUnauthorized());
        mvc.perform(request(id).with(user("admin").roles("ADMIN")))
                .andExpect(status().isForbidden())
                .andExpect(jsonPath("$.code").value("CSRF_INVALID"));
    }

    @Test
    void candidateUsesContractEnvelopeAndRequestId() throws Exception {
        String id = java.util.UUID.randomUUID().toString();
        mvc.perform(request(id).with(user("admin").roles("ADMIN")).with(csrf().asHeader()))
                .andExpect(status().isOk())
                .andExpect(header().string("Cache-Control", "no-store"))
                .andExpect(header().string("X-Request-ID", id))
                .andExpect(jsonPath("$.code").value("SUCCESS"))
                .andExpect(jsonPath("$.data.status").value("CANDIDATE"))
                .andExpect(jsonPath("$.data.action").value("PAUSE"))
                .andExpect(jsonPath("$.data.intent").value("MISSION_PAUSE"))
                .andExpect(jsonPath("$.data.provider").value("local-rules"));
    }

    @Test
    void idMismatchAndUnknownFieldAreRejected() throws Exception {
        String id = java.util.UUID.randomUUID().toString();
        mvc.perform(
                        request(id)
                                .header("X-Request-ID", java.util.UUID.randomUUID().toString())
                                .with(user("admin").roles("ADMIN"))
                                .with(csrf().asHeader()))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.code").value("VOICE_INVALID_REQUEST"));
    }
}
