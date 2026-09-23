-- Read-only evidence export for the refresh/response-loss recovery run.
-- Target database: uav_usv_p0_integration
SET @runtime_ref = '67ed0e95-7ef5-4d41-80d0-25ea6332a36d';

SELECT id AS runtime_ref, owner_id, generation AS runtime_generation,
       algorithm_run_id, JSON_PRETTY(CAST(data_json AS JSON)) AS context_json
FROM voice_runtime_context WHERE id = @runtime_ref;

SELECT id AS proposal_id, owner_id, runtime_ref,
       JSON_PRETTY(CAST(data_json AS JSON)) AS proposal_json
FROM voice_proposal WHERE runtime_ref = @runtime_ref ORDER BY id;

SELECT id AS execution_id, proposal_id, command_id, runtime_ref, owner_id, state,
       JSON_PRETTY(CAST(data_json AS JSON)) AS execution_json
FROM voice_execution WHERE runtime_ref = @runtime_ref ORDER BY id;

SELECT event.execution_id, event.event_sequence, event.body_hash, event.received_at,
       JSON_PRETTY(CAST(event.data_json AS JSON)) AS event_json
FROM voice_command_event event
JOIN voice_execution execution ON execution.id = event.execution_id
WHERE execution.runtime_ref = @runtime_ref
ORDER BY event.execution_id, event.event_sequence;

SELECT id AS audit_id, runtime_ref, kind, detail, created_at
FROM voice_audit WHERE runtime_ref = @runtime_ref ORDER BY created_at, id;

SELECT outbox.execution_id, outbox.status, outbox.claimed_at
FROM voice_outbox outbox
JOIN voice_execution execution ON execution.id = outbox.execution_id
WHERE execution.runtime_ref = @runtime_ref ORDER BY outbox.execution_id;
