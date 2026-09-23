package com.uavusv.platform.module.voiceintelligence;

import static org.junit.jupiter.api.Assertions.assertEquals;

import org.h2.jdbcx.JdbcDataSource;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.core.io.ClassPathResource;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.datasource.init.ResourceDatabasePopulator;

import java.time.Instant;
import java.util.UUID;

class AsrAcceptanceStoreTests {
    AsrAcceptanceStore store;

    @BeforeEach
    void setup() {
        var ds = new JdbcDataSource();
        ds.setURL("jdbc:h2:mem:" + UUID.randomUUID() + ";MODE=MySQL;DB_CLOSE_DELAY=-1");
        new ResourceDatabasePopulator(
                        new ClassPathResource("db/migration/V20__create_voice_asr_acceptance.sql"))
                .execute(ds);
        store = new AsrAcceptanceStore(new JdbcTemplate(ds));
    }

    @Test
    void survivesStoreRecreationAndSeparatesUsers() {
        Instant now = Instant.parse("2026-09-23T00:00:00Z");
        assertEquals(AsrAcceptanceStore.Reservation.NEW, store.reserve(1, "id", "hash", now));
        assertEquals(AsrAcceptanceStore.Reservation.MATCH, store.reserve(1, "id", "hash", now));
        assertEquals(AsrAcceptanceStore.Reservation.NEW, store.reserve(2, "id", "hash", now));
    }

    @Test
    void changedContentConflicts() {
        Instant now = Instant.parse("2026-09-23T00:00:00Z");
        store.reserve(1, "id", "hash-a", now);
        assertEquals(
                AsrAcceptanceStore.Reservation.CONFLICT,
                store.reserve(1, "id", "hash-b", now.plusSeconds(1)));
    }

    @Test
    void sevenDayExpiryOpensNewAcceptanceWindow() {
        Instant now = Instant.parse("2026-09-23T00:00:00Z");
        store.reserve(1, "id", "hash", now);
        assertEquals(
                AsrAcceptanceStore.Reservation.MATCH,
                store.reserve(1, "id", "hash", now.plusSeconds(604799)));
        assertEquals(
                AsrAcceptanceStore.Reservation.NEW,
                store.reserve(1, "id", "hash", now.plusSeconds(604800)));
    }

    @Test
    void cleanupRemovesOnlyExpiredRows() {
        Instant now = Instant.parse("2026-09-23T00:00:00Z");
        store.reserve(1, "expired", "a", now);
        store.reserve(1, "active", "b", now.plusSeconds(1));
        store.cleanup(now.plusSeconds(604800));
        assertEquals(
                AsrAcceptanceStore.Reservation.NEW,
                store.reserve(1, "expired", "a", now.plusSeconds(604800)));
        assertEquals(
                AsrAcceptanceStore.Reservation.MATCH,
                store.reserve(1, "active", "b", now.plusSeconds(604800)));
    }
}
