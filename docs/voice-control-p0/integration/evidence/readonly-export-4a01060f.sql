-- Read-only evidence export for the 2026-09-22 P0 browser run.
-- Target database: uav_usv_p0_integration
-- This script contains SELECT statements only and does not require elevated write privileges.
SET @runtime_ref = '4a01060f-515c-49c6-87b6-7e99a4eb3447';

SELECT id AS runtime_ref, owner_id, generation AS runtime_generation,
       algorithm_run_id, JSON_PRETTY(CAST(data_json AS JSON)) AS context_json
FROM voice_runtime_context
WHERE id = @runtime_ref;

SELECT id AS proposal_id, owner_id, runtime_ref,
       JSON_PRETTY(CAST(data_json AS JSON)) AS proposal_json
FROM voice_proposal
WHERE runtime_ref = @runtime_ref
ORDER BY id;

SELECT id AS execution_id, proposal_id, command_id, runtime_ref, owner_id, state,
       JSON_PRETTY(CAST(data_json AS JSON)) AS execution_json
FROM voice_execution
WHERE runtime_ref = @runtime_ref
ORDER BY id;

SELECT event.execution_id, event.event_sequence, event.body_hash, event.received_at,
       JSON_PRETTY(CAST(event.data_json AS JSON)) AS event_json
FROM voice_command_event event
JOIN voice_execution execution ON execution.id = event.execution_id
WHERE execution.runtime_ref = @runtime_ref
ORDER BY event.execution_id, event.event_sequence;

SELECT audit.id AS audit_id, audit.runtime_ref, audit.kind, audit.detail, audit.created_at
FROM voice_audit audit
WHERE audit.runtime_ref = @runtime_ref
ORDER BY audit.created_at, audit.id;

SELECT outbox.execution_id, outbox.status, outbox.claimed_at
FROM voice_outbox outbox
JOIN voice_execution execution ON execution.id = outbox.execution_id
WHERE execution.runtime_ref = @runtime_ref
ORDER BY outbox.execution_id;
