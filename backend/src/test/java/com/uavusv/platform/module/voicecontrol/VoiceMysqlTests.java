package com.uavusv.platform.module.voicecontrol;

import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.condition.EnabledIfEnvironmentVariable;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.datasource.DriverManagerDataSource;

import javax.sql.DataSource;

/**
 * Opt-in suite: creates and removes only its own random database, never the application database.
 */
@EnabledIfEnvironmentVariable(named = "VOICE_TEST_MYSQL_URL", matches = ".+")
class VoiceMysqlTests extends VoiceControlTests {
    String database;
    JdbcTemplate admin;
    boolean created;

    @Override
    DataSource dataSource() {
        String root = System.getenv("VOICE_TEST_MYSQL_URL");
        String user = System.getenv("VOICE_TEST_MYSQL_USER");
        String password = System.getenv("VOICE_TEST_MYSQL_PASSWORD");
        if (!root.matches("jdbc:mysql://[^/]+/\\?.*"))
            throw new IllegalArgumentException("Test URL must target server root, not a database");
        database = "uav_usv_p0_test_" + java.util.UUID.randomUUID().toString().replace("-", "");
        admin = new JdbcTemplate(new DriverManagerDataSource(root, user, password));
        admin.execute("CREATE DATABASE " + database + " CHARACTER SET utf8mb4");
        created = true;
        return new DriverManagerDataSource(
                root.replace("/?", "/" + database + "?"), user, password);
    }

    @AfterEach
    void removeOnlyOwnedDatabase() {
        if (created && database.matches("uav_usv_p0_test_[0-9a-f]{32}"))
            admin.execute("DROP DATABASE " + database);
    }
}
