-- Replace only this UUID with the target runtimeRef. Dedicated local database only.
SET @runtime_ref = CONVERT('REPLACE_WITH_RUNTIME_UUID' USING utf8mb4) COLLATE utf8mb4_unicode_ci;
START TRANSACTION READ ONLY;
SELECT id AS runtimeRef, generation AS runtimeGeneration, algorithm_run_id,
 JSON_EXTRACT(data_json,'$.state') AS runtimeState,
 JSON_EXTRACT(data_json,'$.lastHeartbeatReceivedAt') AS heartbeat,
 JSON_EXTRACT(data_json,'$._binding') AS bindingId,
 JSON_EXTRACT(data_json,'$._challenge.requestId') AS challengeId,
 JSON_EXTRACT(data_json,'$._challenge.executionId') AS challengeExecutionId,
 JSON_EXTRACT(data_json,'$._challenge') AS currentChallenge
FROM voice_runtime_context WHERE id=@runtime_ref;
SELECT p.id AS proposalId,e.id AS executionId,e.command_id AS commandId,e.state,
 JSON_EXTRACT(p.data_json,'$._source') AS proposalSource,
 JSON_EXTRACT(e.data_json,'$.action') AS action,
 JSON_EXTRACT(e.data_json,'$.outcome') AS outcome,
 JSON_EXTRACT(e.data_json,'$.presentationStatus') AS presentationStatus,
 JSON_EXTRACT(e.data_json,'$._plan.explicitDeviceCodes') AS devices
FROM voice_proposal p LEFT JOIN voice_execution e ON e.proposal_id=p.id
WHERE p.runtime_ref=@runtime_ref ORDER BY JSON_EXTRACT(p.data_json,'$.createdAt');
SELECT v.execution_id,v.event_sequence,v.received_at,v.data_json
FROM voice_command_event v JOIN voice_execution e ON e.id=v.execution_id
WHERE e.runtime_ref=@runtime_ref ORDER BY v.received_at,v.event_sequence;
SELECT kind,detail,created_at FROM voice_audit WHERE runtime_ref=@runtime_ref ORDER BY created_at;
COMMIT;

