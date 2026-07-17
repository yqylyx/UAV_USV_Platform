ALTER TABLE mission_task
    ADD COLUMN execution_mode VARCHAR(32) NOT NULL DEFAULT 'HYBRID_MIRROR' AFTER type,
    ADD KEY idx_mission_task_execution_mode (execution_mode);

UPDATE mission_task
SET execution_mode = 'HYBRID_MIRROR'
WHERE execution_mode IS NULL OR execution_mode = '';
