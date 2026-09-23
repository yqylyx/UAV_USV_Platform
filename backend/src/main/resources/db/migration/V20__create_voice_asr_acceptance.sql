-- D1 ASR idempotency tombstones. Audio and transcript text are deliberately not stored.
CREATE TABLE voice_asr_acceptance (
 user_id BIGINT NOT NULL,
 endpoint_key VARCHAR(64) NOT NULL,
 request_id VARCHAR(36) NOT NULL,
 content_hash VARCHAR(160) NOT NULL,
 accepted_at VARCHAR(32) NOT NULL,
 expires_at VARCHAR(32) NOT NULL,
 PRIMARY KEY(user_id,endpoint_key,request_id),
 INDEX ix_voice_asr_acceptance_expiry(expires_at)
);
