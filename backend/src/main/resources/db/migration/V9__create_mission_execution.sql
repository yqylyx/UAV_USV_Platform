CREATE TABLE mission_run (
    id BIGINT NOT NULL AUTO_INCREMENT,
    mission_id BIGINT NOT NULL,
    session_id BIGINT NULL,
    run_key VARCHAR(64) NOT NULL,
    run_no INT NOT NULL,
    status VARCHAR(32) NOT NULL,
    stage VARCHAR(40) NOT NULL,
    requested_by VARCHAR(64) NULL,
    started_at DATETIME(6) NOT NULL,
    paused_at DATETIME(6) NULL,
    ended_at DATETIME(6) NULL,
    failure_reason VARCHAR(1000) NULL,
    created_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    updated_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6),
    PRIMARY KEY (id),
    UNIQUE KEY uk_mission_run_key (run_key),
    UNIQUE KEY uk_mission_run_number (mission_id, run_no),
    KEY idx_mission_run_status (status),
    KEY idx_mission_run_started_at (started_at),
    CONSTRAINT fk_mission_run_mission FOREIGN KEY (mission_id) REFERENCES mission_task (id) ON DELETE RESTRICT,
    CONSTRAINT fk_mission_run_session FOREIGN KEY (session_id) REFERENCES simulation_session (id) ON DELETE SET NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

ALTER TABLE control_command
    ADD COLUMN run_id BIGINT NULL AFTER session_id,
    ADD COLUMN device_id BIGINT NULL AFTER run_id,
    ADD COLUMN command_key VARCHAR(64) NULL AFTER device_id,
    ADD COLUMN payload_json TEXT NULL AFTER command_key,
    ADD COLUMN dispatched_at DATETIME(6) NULL AFTER requested_at,
    ADD COLUMN acknowledged_at DATETIME(6) NULL AFTER dispatched_at,
    ADD COLUMN error_code VARCHAR(64) NULL AFTER detail,
    ADD UNIQUE KEY uk_control_command_key (command_key),
    ADD KEY idx_control_command_run (run_id),
    ADD KEY idx_control_command_device (device_id),
    ADD CONSTRAINT fk_control_command_run FOREIGN KEY (run_id) REFERENCES mission_run (id) ON DELETE SET NULL,
    ADD CONSTRAINT fk_control_command_device FOREIGN KEY (device_id) REFERENCES mission_device (id) ON DELETE SET NULL;

UPDATE control_command
SET command_key = CONCAT('legacy-', id),
    acknowledged_at = completed_at,
    status = CASE WHEN status = 'SUCCEEDED' THEN 'ACKNOWLEDGED' ELSE status END
WHERE command_key IS NULL;

ALTER TABLE control_command
    MODIFY COLUMN command_key VARCHAR(64) NOT NULL;

ALTER TABLE device_telemetry
    ADD COLUMN run_id BIGINT NULL AFTER device_id,
    ADD COLUMN session_id BIGINT NULL AFTER run_id,
    ADD COLUMN speed DOUBLE NULL AFTER orientation_w,
    ADD COLUMN heading DOUBLE NULL AFTER speed,
    ADD COLUMN battery_level DOUBLE NULL AFTER heading,
    ADD COLUMN source VARCHAR(40) NOT NULL DEFAULT 'ROS' AFTER battery_level,
    ADD KEY idx_device_telemetry_run_time (run_id, recorded_at),
    ADD CONSTRAINT fk_device_telemetry_run FOREIGN KEY (run_id) REFERENCES mission_run (id) ON DELETE SET NULL,
    ADD CONSTRAINT fk_device_telemetry_session FOREIGN KEY (session_id) REFERENCES simulation_session (id) ON DELETE SET NULL;

ALTER TABLE mission_event
    ADD COLUMN run_id BIGINT NULL AFTER mission_id,
    ADD COLUMN stage VARCHAR(40) NULL AFTER event_type,
    ADD COLUMN level VARCHAR(20) NOT NULL DEFAULT 'INFO' AFTER stage,
    ADD COLUMN event_data_json JSON NULL AFTER message,
    ADD KEY idx_mission_event_run_time (run_id, occurred_at),
    ADD CONSTRAINT fk_mission_event_run FOREIGN KEY (run_id) REFERENCES mission_run (id) ON DELETE SET NULL;
