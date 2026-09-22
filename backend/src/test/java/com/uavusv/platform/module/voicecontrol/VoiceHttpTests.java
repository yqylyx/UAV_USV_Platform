package com.uavusv.platform.module.voicecontrol;

import static org.junit.jupiter.api.Assertions.*;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.*;
import static org.springframework.security.test.web.servlet.setup.SecurityMockMvcConfigurers.springSecurity;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.*;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.*;

import com.fasterxml.jackson.databind.ObjectMapper;
import com.uavusv.platform.config.SecurityConfig;

import org.h2.jdbcx.JdbcDataSource;
import org.junit.jupiter.api.*;
import org.springframework.context.annotation.*;
import org.springframework.core.io.ClassPathResource;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.datasource.DataSourceTransactionManager;
import org.springframework.jdbc.datasource.init.ResourceDatabasePopulator;
import org.springframework.mock.web.MockServletContext;
import org.springframework.security.config.annotation.web.configuration.EnableWebSecurity;
import org.springframework.security.core.context.SecurityContextHolder;
import org.springframework.security.core.userdetails.*;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.setup.MockMvcBuilders;
import org.springframework.web.context.support.AnnotationConfigWebApplicationContext;
import org.springframework.web.servlet.config.annotation.EnableWebMvc;

import javax.sql.DataSource;

class VoiceHttpTests {
    @Configuration
    @EnableWebMvc
    @EnableWebSecurity
    @Import({
        SecurityConfig.class,
        VoiceJson.class,
        VoiceTime.class,
        VoiceAccess.class,
        VoiceStore.class,
        RuntimeContextRegistry.class,
        VoiceCommandApplicationService.class,
        VoicePresentationService.class,
        VoiceController.class,
        VoiceExceptionHandler.class,
        VoiceMvcErrors.class
    })
    static class Config {
        @Bean
        ObjectMapper mapper() {
            return new ObjectMapper().findAndRegisterModules();
        }

        @Bean
        VoiceSettings settings() {
            return new VoiceSettings(true);
        }

        @Bean
        DataSource ds() {
            var ds = new JdbcDataSource();
            ds.setURL("jdbc:h2:mem:" + VoiceJson.uuid() + ";MODE=MySQL;DB_CLOSE_DELAY=-1");
            new ResourceDatabasePopulator(
                            new ClassPathResource("db/migration/V19__create_voice_control_p0.sql"))
                    .execute(ds);
            var j = new JdbcTemplate(ds);
            j.execute(
                    "CREATE TABLE app_user(id BIGINT PRIMARY KEY,username VARCHAR(64),role"
                        + " VARCHAR(32),enabled BOOLEAN)");
            j.update(
                    "INSERT INTO app_user VALUES"
                        + " (1,'alice','ADMIN',true),(2,'viewer','VIEWER',true)");
            return ds;
        }

        @Bean
        JdbcTemplate jdbc(DataSource ds) {
            return new JdbcTemplate(ds);
        }

        @Bean
        DataSourceTransactionManager tm(DataSource ds) {
            return new DataSourceTransactionManager(ds);
        }

        @Bean
        UserDetailsService users() {
            return new InMemoryUserDetailsManager(
                    User.withUsername("alice").password("unused").roles("ADMIN").build());
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
                        .addFilters(
                                new VoiceHttpFilter(
                                        context.getBean(VoiceJson.class),
                                        context.getBean(VoiceTime.class)))
                        .build();
    }

    @AfterEach
    void close() {
        SecurityContextHolder.clearContext();
        context.close();
    }

    @Test
    void unauthenticatedGetAndPostAre401() throws Exception {
        mvc.perform(get("/api/voice/contexts")).andExpect(status().isUnauthorized())
                .andExpect(jsonPath("$.message").value("请先登录或登录状态已失效"));
        mvc.perform(
                        post("/api/voice/commands/proposals")
                                .servletPath("/api/voice/commands/proposals")
                                .contentType("application/json")
                                .content("{}"))
                .andExpect(status().isUnauthorized())
                .andExpect(jsonPath("$.code").value("UNAUTHORIZED"))
                .andExpect(jsonPath("$.message").value("请先登录或登录状态已失效"));
    }

    @Test
    void authenticatedPostRequiresCsrf() throws Exception {
        mvc.perform(
                        post("/api/voice/commands/proposals")
                                .with(user("alice").roles("ADMIN"))
                                .contentType("application/json")
                                .header("Idempotency-Key", VoiceJson.uuid())
                                .content("{}"))
                .andExpect(status().isForbidden())
                .andExpect(jsonPath("$.code").value("CSRF_INVALID"));
    }

    @Test
    void readHasNoStoreAndNoInstancesIsEmpty() throws Exception {
        mvc.perform(get("/api/voice/contexts").with(user("alice").roles("ADMIN")))
                .andExpect(status().isOk())
                .andExpect(header().string("Cache-Control", "no-store"))
                .andExpect(jsonPath("$.data").isEmpty());
    }

    @Test
    void nonAdminDeniedAtProxiedServiceAndHttp() throws Exception {
        mvc.perform(
                        post("/api/voice/commands/proposals")
                                .with(user("viewer").roles("VIEWER"))
                                .with(csrf())
                                .header("Idempotency-Key", VoiceJson.uuid())
                                .contentType("application/json")
                                .content("{}"))
                .andExpect(status().isForbidden())
                .andExpect(jsonPath("$.code").value("FORBIDDEN"));
        VoiceControlTests.login("viewer");
        assertThrows(
                org.springframework.security.access.AccessDeniedException.class,
                () ->
                        context.getBean(VoiceCommandApplicationService.class)
                                .createProposal(
                                        VoiceJson.uuid(),
                                        context.getBean(VoiceJson.class).object()));
    }

    @Test
    void malformedAndUnknownFieldsReturn400() throws Exception {
        for (String body : new String[] {"{", "null", "{\"ownerUserId\":1}", "{\"x\":1,\"x\":2}"})
            mvc.perform(
                            post("/api/voice/commands/proposals")
                                    .with(user("alice").roles("ADMIN"))
                                    .with(csrf())
                                    .contentType("application/json")
                                    .header("Idempotency-Key", VoiceJson.uuid())
                                    .content(body))
                    .andExpect(status().isBadRequest())
                    .andExpect(jsonPath("$.code").value("INVALID_REQUEST"));
    }

    @Test
    void rejectsOversizedStreamAndWrongMediaType() throws Exception {
        mvc.perform(
                        post("/api/voice/commands/proposals")
                                .servletPath("/api/voice/commands/proposals")
                                .with(user("alice").roles("ADMIN"))
                                .with(csrf())
                                .contentType("application/json")
                                .header("Idempotency-Key", VoiceJson.uuid())
                                .content("x".repeat(16385)))
                .andExpect(status().isPayloadTooLarge())
                .andExpect(jsonPath("$.code").value("PAYLOAD_TOO_LARGE"));
        mvc.perform(
                        post("/api/voice/commands/proposals")
                                .servletPath("/api/voice/commands/proposals")
                                .with(user("alice").roles("ADMIN"))
                                .with(csrf())
                                .contentType("text/plain")
                                .header("Idempotency-Key", VoiceJson.uuid())
                                .content("{}"))
                .andExpect(status().isUnsupportedMediaType());
    }
}
