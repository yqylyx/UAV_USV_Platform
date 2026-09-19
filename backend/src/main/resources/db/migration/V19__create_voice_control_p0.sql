-- P0 standalone control. Payloads are private server snapshots; indexed IDs enforce deduplication.
CREATE TABLE voice_control_lock (id INT PRIMARY KEY);
INSERT INTO voice_control_lock(id) VALUES (1);
CREATE TABLE voice_runtime_context (
 id VARCHAR(36) PRIMARY KEY, owner_id BIGINT NOT NULL, generation VARCHAR(36) NOT NULL UNIQUE,
 algorithm_run_id VARCHAR(19) NOT NULL, data_json LONGTEXT NOT NULL,
 INDEX ix_voice_context_owner(owner_id), INDEX ix_voice_context_run(algorithm_run_id)
);
CREATE TABLE voice_proposal (
 id VARCHAR(36) PRIMARY KEY, owner_id BIGINT NOT NULL, runtime_ref VARCHAR(36) NOT NULL, data_json LONGTEXT NOT NULL,
 INDEX ix_voice_proposal_runtime(runtime_ref), FOREIGN KEY(runtime_ref) REFERENCES voice_runtime_context(id)
);
CREATE TABLE voice_execution (
 id VARCHAR(36) PRIMARY KEY, proposal_id VARCHAR(36) NOT NULL UNIQUE, command_id VARCHAR(36) NOT NULL UNIQUE,
 runtime_ref VARCHAR(36) NOT NULL, owner_id BIGINT NOT NULL, state VARCHAR(24) NOT NULL, data_json LONGTEXT NOT NULL,
 INDEX ix_voice_execution_state(state),
 INDEX ix_voice_execution_runtime(runtime_ref), FOREIGN KEY(proposal_id) REFERENCES voice_proposal(id),
 FOREIGN KEY(runtime_ref) REFERENCES voice_runtime_context(id)
);
CREATE TABLE voice_outbox (
 execution_id VARCHAR(36) PRIMARY KEY, status VARCHAR(16) NOT NULL, claimed_at VARCHAR(32),
 FOREIGN KEY(execution_id) REFERENCES voice_execution(id)
);
CREATE TABLE voice_idempotency (
 user_id BIGINT NOT NULL, operation_key VARCHAR(64) NOT NULL, idempotency_key VARCHAR(36) NOT NULL,
 body_hash VARCHAR(64) NOT NULL, resource_id VARCHAR(36) NOT NULL,
 PRIMARY KEY(user_id,operation_key,idempotency_key)
);
CREATE TABLE voice_command_event (
 execution_id VARCHAR(36) NOT NULL, event_sequence BIGINT NOT NULL, body_hash VARCHAR(64) NOT NULL,
 data_json LONGTEXT NOT NULL, received_at VARCHAR(32) NOT NULL,
 PRIMARY KEY(execution_id,event_sequence), FOREIGN KEY(execution_id) REFERENCES voice_execution(id)
);
CREATE TABLE voice_audit (
 id VARCHAR(36) PRIMARY KEY, runtime_ref VARCHAR(36) NOT NULL, kind VARCHAR(64) NOT NULL,
 detail VARCHAR(512) NOT NULL, created_at VARCHAR(32) NOT NULL, INDEX ix_voice_audit_runtime(runtime_ref)
);
