CREATE TABLE IF NOT EXISTS perception_sensor (
    id BIGINT NOT NULL AUTO_INCREMENT,
    created_at DATETIME(6) NOT NULL,
    updated_at DATETIME(6) NOT NULL,
    vehicle_id VARCHAR(64) NOT NULL,
    vehicle_code VARCHAR(64) NOT NULL,
    sensor_type VARCHAR(32) NOT NULL,
    online BIT NOT NULL,
    healthy BIT NOT NULL,
    frequency DOUBLE NULL,
    latency BIGINT NULL,
    image_url VARCHAR(500) NULL,
    detail VARCHAR(1000) NULL,
    last_update_time DATETIME(6) NOT NULL,
    PRIMARY KEY (id),
    UNIQUE KEY uk_perception_sensor_vehicle_type (vehicle_id, sensor_type),
    KEY idx_perception_sensor_vehicle_code (vehicle_code)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS perception_target (
    id BIGINT NOT NULL AUTO_INCREMENT,
    created_at DATETIME(6) NOT NULL,
    updated_at DATETIME(6) NOT NULL,
    target_id VARCHAR(64) NOT NULL,
    target_type VARCHAR(32) NOT NULL,
    source VARCHAR(32) NOT NULL,
    x DOUBLE NOT NULL,
    y DOUBLE NOT NULL,
    z DOUBLE NOT NULL,
    confidence DOUBLE NOT NULL,
    affiliation VARCHAR(32) NOT NULL,
    detected_by VARCHAR(64) NULL,
    last_update_time DATETIME(6) NOT NULL,
    PRIMARY KEY (id),
    UNIQUE KEY uk_perception_target_target_id (target_id),
    KEY idx_perception_target_last_update_time (last_update_time)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS algorithm_run (
    id BIGINT NOT NULL AUTO_INCREMENT,
    created_at DATETIME(6) NOT NULL,
    updated_at DATETIME(6) NOT NULL,
    command_id VARCHAR(64) NOT NULL,
    algorithm_type VARCHAR(32) NOT NULL,
    status VARCHAR(32) NOT NULL,
    target_id VARCHAR(64) NULL,
    stage VARCHAR(64) NULL,
    message VARCHAR(1000) NULL,
    request_json TEXT NULL,
    parameter_json TEXT NULL,
    started_at DATETIME(6) NOT NULL,
    last_ack_at DATETIME(6) NULL,
    completed_at DATETIME(6) NULL,
    error_message VARCHAR(1000) NULL,
    PRIMARY KEY (id),
    UNIQUE KEY uk_algorithm_run_command_id (command_id),
    KEY idx_algorithm_run_started_at (started_at),
    KEY idx_algorithm_run_status (status)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS algorithm_assignment (
    id BIGINT NOT NULL AUTO_INCREMENT,
    created_at DATETIME(6) NOT NULL,
    updated_at DATETIME(6) NOT NULL,
    command_id VARCHAR(64) NOT NULL,
    target_id VARCHAR(64) NULL,
    vehicle_id VARCHAR(64) NOT NULL,
    vehicle_code VARCHAR(64) NULL,
    role VARCHAR(32) NOT NULL,
    x DOUBLE NULL,
    y DOUBLE NULL,
    z DOUBLE NULL,
    heading DOUBLE NULL,
    detail VARCHAR(1000) NULL,
    PRIMARY KEY (id),
    KEY idx_algorithm_assignment_command_id (command_id),
    KEY idx_algorithm_assignment_vehicle_id (vehicle_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS algorithm_event (
    id BIGINT NOT NULL AUTO_INCREMENT,
    created_at DATETIME(6) NOT NULL,
    updated_at DATETIME(6) NOT NULL,
    command_id VARCHAR(64) NULL,
    algorithm_type VARCHAR(32) NULL,
    event_level VARCHAR(32) NOT NULL,
    stage VARCHAR(64) NULL,
    message VARCHAR(1000) NOT NULL,
    occurred_at DATETIME(6) NOT NULL,
    PRIMARY KEY (id),
    KEY idx_algorithm_event_command_id (command_id),
    KEY idx_algorithm_event_occurred_at (occurred_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
