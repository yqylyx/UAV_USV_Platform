package com.uavusv.platform.module.voiceintelligence;

import org.springframework.dao.DuplicateKeyException;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Component;

import java.time.Instant;

@Component
public class AsrAcceptanceStore {
    static final String ENDPOINT = "transcriptions";
    static final long RETENTION_SECONDS = 7L * 24 * 60 * 60;

    enum Reservation {
        NEW,
        MATCH,
        CONFLICT
    }

    private final JdbcTemplate jdbc;

    public AsrAcceptanceStore(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    public Reservation reserve(long user, String requestId, String hash, Instant now) {
        String instant = now.toString();
        jdbc.update(
                "DELETE FROM voice_asr_acceptance WHERE user_id=? AND endpoint_key=? AND"
                        + " request_id=? AND expires_at<=?",
                user,
                ENDPOINT,
                requestId,
                instant);
        try {
            jdbc.update(
                    "INSERT INTO voice_asr_acceptance"
                        + "(user_id,endpoint_key,request_id,content_hash,accepted_at,expires_at)"
                        + " VALUES (?,?,?,?,?,?)",
                    user,
                    ENDPOINT,
                    requestId,
                    hash,
                    instant,
                    now.plusSeconds(RETENTION_SECONDS).toString());
            return Reservation.NEW;
        } catch (DuplicateKeyException e) {
            var hashes =
                    jdbc.queryForList(
                            "SELECT content_hash FROM voice_asr_acceptance WHERE user_id=? AND"
                                    + " endpoint_key=? AND request_id=?",
                            String.class,
                            user,
                            ENDPOINT,
                            requestId);
            if (hashes.isEmpty()) throw e;
            return hash.equals(hashes.get(0)) ? Reservation.MATCH : Reservation.CONFLICT;
        }
    }

    public void cleanup(Instant now) {
        jdbc.update("DELETE FROM voice_asr_acceptance WHERE expires_at<=?", now.toString());
    }
}
