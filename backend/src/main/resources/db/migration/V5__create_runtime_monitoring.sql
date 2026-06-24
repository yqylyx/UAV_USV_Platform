CREATE TABLE simulation_session (
    id BIGINT NOT NULL AUTO_INCREMENT,
    session_key VARCHAR(64) NOT NULL,
    status VARCHAR(32) NOT NULL,
    requested_by VARCHAR(64) NULL,
    ros_managed BOOLEAN NOT NULL DEFAULT FALSE,
    unity_managed BOOLEAN NOT NULL DEFAULT FALSE,
    ros_process_id BIGINT NULL,
    unity_process_id BIGINT NULL,
    started_at DATETIME(6) NULL,
    stopped_at DATETIME(6) NULL,
    error_message VARCHAR(1000) NULL,
    created_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    updated_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6),
    PRIMARY KEY (id),
    UNIQUE KEY uk_simulation_session_key (session_key),
    KEY idx_simulation_session_status (status)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

CREATE TABLE device_runtime_status (
    id BIGINT NOT NULL AUTO_INCREMENT,
    device_id BIGINT NOT NULL,
    status VARCHAR(32) NOT NULL DEFAULT 'UNKNOWN',
    source VARCHAR(32) NOT NULL DEFAULT 'REGISTRY',
    session_id BIGINT NULL,
    instance_id VARCHAR(128) NULL,
    last_heartbeat_at DATETIME(6) NULL,
    last_message_at DATETIME(6) NULL,
    last_sequence BIGINT NULL,
    host VARCHAR(128) NULL,
    port INT NULL,
    position_x DOUBLE NULL,
    position_y DOUBLE NULL,
    position_z DOUBLE NULL,
    orientation_x DOUBLE NULL,
    orientation_y DOUBLE NULL,
    orientation_z DOUBLE NULL,
    orientation_w DOUBLE NULL,
    detail VARCHAR(500) NULL,
    created_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    updated_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6),
    PRIMARY KEY (id),
    UNIQUE KEY uk_device_runtime_status_device (device_id),
    KEY idx_device_runtime_status_status (status),
    CONSTRAINT fk_device_runtime_status_device FOREIGN KEY (device_id) REFERENCES mission_device (id) ON DELETE CASCADE,
    CONSTRAINT fk_device_runtime_status_session FOREIGN KEY (session_id) REFERENCES simulation_session (id) ON DELETE SET NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

CREATE TABLE device_status_event (
    id BIGINT NOT NULL AUTO_INCREMENT,
    device_id BIGINT NOT NULL,
    previous_status VARCHAR(32) NULL,
    current_status VARCHAR(32) NOT NULL,
    source VARCHAR(32) NOT NULL,
    message VARCHAR(500) NULL,
    occurred_at DATETIME(6) NOT NULL,
    created_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    updated_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6),
    PRIMARY KEY (id),
    KEY idx_device_status_event_device_time (device_id, occurred_at),
    CONSTRAINT fk_device_status_event_device FOREIGN KEY (device_id) REFERENCES mission_device (id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

CREATE TABLE device_telemetry (
    id BIGINT NOT NULL AUTO_INCREMENT,
    device_id BIGINT NOT NULL,
    recorded_at DATETIME(6) NOT NULL,
    sequence_no BIGINT NULL,
    position_x DOUBLE NOT NULL,
    position_y DOUBLE NOT NULL,
    position_z DOUBLE NOT NULL,
    orientation_x DOUBLE NULL,
    orientation_y DOUBLE NULL,
    orientation_z DOUBLE NULL,
    orientation_w DOUBLE NULL,
    created_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    updated_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6),
    PRIMARY KEY (id),
    KEY idx_device_telemetry_device_time (device_id, recorded_at),
    CONSTRAINT fk_device_telemetry_device FOREIGN KEY (device_id) REFERENCES mission_device (id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

CREATE TABLE control_command (
    id BIGINT NOT NULL AUTO_INCREMENT,
    session_id BIGINT NULL,
    command_type VARCHAR(32) NOT NULL,
    status VARCHAR(32) NOT NULL,
    requested_by VARCHAR(64) NULL,
    requested_at DATETIME(6) NOT NULL,
    completed_at DATETIME(6) NULL,
    detail VARCHAR(1000) NULL,
    created_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    updated_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6),
    PRIMARY KEY (id),
    KEY idx_control_command_session (session_id),
    KEY idx_control_command_requested_at (requested_at),
    CONSTRAINT fk_control_command_session FOREIGN KEY (session_id) REFERENCES simulation_session (id) ON DELETE SET NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

INSERT INTO device_runtime_status (device_id, status, source)
SELECT id, 'UNKNOWN', 'REGISTRY'
FROM mission_device
WHERE type IN ('UAV', 'USV', 'ROS_NODE', 'UNITY_NODE');

UPDATE mission_device
SET status = 'UNKNOWN'
WHERE type IN ('UAV', 'USV', 'ROS_NODE', 'UNITY_NODE');
