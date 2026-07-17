ALTER TABLE control_command
    ADD COLUMN runtime_scope VARCHAR(32) NULL AFTER device_id,
    ADD COLUMN runtime_instance_id VARCHAR(128) NULL AFTER runtime_scope,
    ADD KEY idx_control_command_scope_instance (runtime_scope, runtime_instance_id);

UPDATE control_command
SET runtime_scope = CASE
    WHEN run_id IS NULL THEN 'SYSTEM_OVERVIEW'
    ELSE 'MISSION_CENTER'
END
WHERE runtime_scope IS NULL;

ALTER TABLE control_command
    MODIFY COLUMN runtime_scope VARCHAR(32) NOT NULL DEFAULT 'SYSTEM_OVERVIEW';

ALTER TABLE mission_run
    ADD COLUMN runtime_instance_id VARCHAR(128) NULL AFTER session_id,
    ADD COLUMN algorithm_code VARCHAR(64) NOT NULL DEFAULT 'default' AFTER runtime_instance_id,
    ADD COLUMN algorithm_version VARCHAR(64) NOT NULL DEFAULT '1.0' AFTER algorithm_code,
    ADD KEY idx_mission_run_runtime_instance (runtime_instance_id);
