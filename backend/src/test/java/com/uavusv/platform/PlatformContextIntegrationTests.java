package com.uavusv.platform;

import com.uavusv.platform.module.monitoring.integration.RosPoseWebSocketClient;
import com.uavusv.platform.module.runtimecontrol.service.RuntimeControlService;
import org.junit.jupiter.api.AfterAll;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.condition.EnabledIfEnvironmentVariable;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.context.DynamicPropertyRegistry;
import org.springframework.test.context.DynamicPropertySource;
import org.springframework.test.context.bean.override.mockito.MockitoBean;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.datasource.DriverManagerDataSource;

import static org.assertj.core.api.Assertions.assertThat;

/**
 * MySQL-dialect application-context smoke test. H2 is intentionally not used here:
 * the Flyway baseline contains MySQL-only DDL. This test creates and drops only a
 * randomly named database dedicated to this run and is opt-in via VOICE_TEST_MYSQL_URL.
 */
@EnabledIfEnvironmentVariable(named = "VOICE_TEST_MYSQL_URL", matches = ".+")
@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.MOCK)
class PlatformContextIntegrationTests {

    private static String database;
    private static JdbcTemplate admin;
    private static boolean created;

    @MockitoBean
    private RosPoseWebSocketClient rosPoseWebSocketClient;

    @MockitoBean
    private RuntimeControlService runtimeControlService;

    @DynamicPropertySource
    static void configureIsolatedMysql(DynamicPropertyRegistry properties) {
        String root = System.getenv("VOICE_TEST_MYSQL_URL");
        String user = System.getenv("VOICE_TEST_MYSQL_USER");
        String password = System.getenv("VOICE_TEST_MYSQL_PASSWORD");
        if (root == null || !root.matches("jdbc:mysql://[^/]+/\\?.*")) {
            throw new IllegalArgumentException("VOICE_TEST_MYSQL_URL must target the MySQL server root");
        }
        database = "uav_usv_context_test_" + java.util.UUID.randomUUID().toString().replace("-", "");
        admin = new JdbcTemplate(new DriverManagerDataSource(root, user, password));
        admin.execute("CREATE DATABASE " + database + " CHARACTER SET utf8mb4");
        created = true;
        String isolatedUrl = root.replace("/?", "/" + database + "?");
        properties.add("spring.datasource.url", () -> isolatedUrl);
        properties.add("spring.datasource.username", () -> user);
        properties.add("spring.datasource.password", () -> password);
        properties.add("spring.datasource.driver-class-name", () -> "com.mysql.cj.jdbc.Driver");
        properties.add("app.security.bootstrap-admin.username", () -> "isolated-test-admin");
        properties.add("app.security.bootstrap-admin.password", () -> "isolated-test-only-password");
        properties.add("app.integration.token", () -> "isolated-test-integration-token");
    }

    @AfterAll
    static void dropOwnedDatabase() {
        if (created && database != null && database.matches("uav_usv_context_test_[0-9a-f]{32}")) {
            admin.execute("DROP DATABASE " + database);
            created = false;
        }
    }

    @Test
    void contextLoadsWithFlywayAndJpaMappings() {
        assertThat(rosPoseWebSocketClient).isNotNull();
        assertThat(runtimeControlService).isNotNull();
    }
}
