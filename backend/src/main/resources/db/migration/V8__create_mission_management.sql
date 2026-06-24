CREATE TABLE mission_task (
    id BIGINT NOT NULL AUTO_INCREMENT,
    code VARCHAR(64) NOT NULL,
    name VARCHAR(120) NOT NULL,
    type VARCHAR(40) NOT NULL,
    status VARCHAR(32) NOT NULL,
    stage VARCHAR(40) NOT NULL,
    priority INT NOT NULL DEFAULT 3,
    target_name VARCHAR(120) NULL,
    target_behavior VARCHAR(255) NULL,
    mission_area VARCHAR(255) NULL,
    planned_start_at DATETIME(6) NULL,
    planned_end_at DATETIME(6) NULL,
    started_at DATETIME(6) NULL,
    completed_at DATETIME(6) NULL,
    description VARCHAR(1000) NULL,
    deleted BOOLEAN NOT NULL DEFAULT FALSE,
    deleted_at DATETIME(6) NULL,
    created_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    updated_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6),
    PRIMARY KEY (id),
    UNIQUE KEY uk_mission_task_code (code),
    KEY idx_mission_task_type (type),
    KEY idx_mission_task_status (status),
    KEY idx_mission_task_stage (stage),
    KEY idx_mission_task_deleted (deleted)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

CREATE TABLE mission_task_device (
    id BIGINT NOT NULL AUTO_INCREMENT,
    mission_id BIGINT NOT NULL,
    device_id BIGINT NOT NULL,
    role VARCHAR(40) NOT NULL,
    call_sign VARCHAR(80) NULL,
    required BOOLEAN NOT NULL DEFAULT TRUE,
    assigned_at DATETIME(6) NOT NULL,
    notes VARCHAR(500) NULL,
    created_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    updated_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6),
    PRIMARY KEY (id),
    UNIQUE KEY uk_mission_task_device_role (mission_id, device_id, role),
    KEY idx_mission_task_device_mission (mission_id),
    KEY idx_mission_task_device_device (device_id),
    CONSTRAINT fk_mission_task_device_mission FOREIGN KEY (mission_id) REFERENCES mission_task (id) ON DELETE CASCADE,
    CONSTRAINT fk_mission_task_device_device FOREIGN KEY (device_id) REFERENCES mission_device (id) ON DELETE RESTRICT
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

CREATE TABLE mission_task_parameter (
    id BIGINT NOT NULL AUTO_INCREMENT,
    mission_id BIGINT NOT NULL,
    param_key VARCHAR(80) NOT NULL,
    param_value VARCHAR(500) NULL,
    param_unit VARCHAR(40) NULL,
    description VARCHAR(255) NULL,
    created_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    updated_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6),
    PRIMARY KEY (id),
    UNIQUE KEY uk_mission_task_parameter_key (mission_id, param_key),
    KEY idx_mission_task_parameter_mission (mission_id),
    CONSTRAINT fk_mission_task_parameter_mission FOREIGN KEY (mission_id) REFERENCES mission_task (id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

CREATE TABLE mission_event (
    id BIGINT NOT NULL AUTO_INCREMENT,
    mission_id BIGINT NOT NULL,
    event_type VARCHAR(40) NOT NULL,
    title VARCHAR(120) NOT NULL,
    message VARCHAR(1000) NULL,
    source VARCHAR(80) NULL,
    occurred_at DATETIME(6) NOT NULL,
    created_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    updated_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6),
    PRIMARY KEY (id),
    KEY idx_mission_event_mission_time (mission_id, occurred_at),
    CONSTRAINT fk_mission_event_mission FOREIGN KEY (mission_id) REFERENCES mission_task (id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

INSERT INTO mission_task (
    code, name, type, status, stage, priority, target_name, target_behavior, mission_area,
    planned_start_at, planned_end_at, description
)
VALUES
    (
        'MT-20260624-001',
        '三机三艇协同围捕演示任务',
        'COOPERATIVE_ENCIRCLEMENT',
        'READY',
        'PREPARE',
        1,
        '海面机动目标',
        '沿既定航线低速航行，进入围捕区域后可能转向',
        '近岸试验海域 A 区',
        '2026-06-24 09:30:00.000000',
        '2026-06-24 10:10:00.000000',
        '面向 PPT 要求的协同围捕主任务，先完成任务配置、设备编组和状态监控闭环。'
    ),
    (
        'MT-20260624-002',
        'ROS-Unity 路径跟踪联调任务',
        'PATH_TRACKING',
        'DRAFT',
        'PREPARE',
        3,
        'Gazebo 同步目标',
        'UAV 与 USV 按 ROS 位姿同步推进',
        '仿真联调海域',
        '2026-06-24 14:00:00.000000',
        '2026-06-24 14:30:00.000000',
        '用于验证 ROS WebSocket、Unity 心跳和 Web 管理平台的数据链路。'
    );

INSERT INTO mission_task_device (mission_id, device_id, role, call_sign, required, assigned_at, notes)
SELECT task.id, device.id,
       CASE
           WHEN device.type = 'UAV' THEN 'UAV_RECON'
           WHEN device.type = 'USV' THEN 'USV_INTERCEPT'
           WHEN device.type = 'ROS_NODE' THEN 'ROS_BRIDGE'
           WHEN device.type = 'UNITY_NODE' THEN 'UNITY_CLIENT'
           ELSE 'LEADER'
       END,
       device.code,
       TRUE,
       NOW(6),
       '初始化任务编组'
FROM mission_task task
JOIN mission_device device ON device.code IN ('uav-01', 'usv-01', 'ros-bridge-01', 'unity-client-01')
WHERE task.code = 'MT-20260624-001'
  AND device.deleted = FALSE;

INSERT INTO mission_task_parameter (mission_id, param_key, param_value, param_unit, description)
SELECT id, 'encirclement_radius', '35', 'm', '目标围捕半径'
FROM mission_task
WHERE code = 'MT-20260624-001';

INSERT INTO mission_task_parameter (mission_id, param_key, param_value, param_unit, description)
SELECT id, 'heartbeat_timeout', '10', 's', '节点心跳超时阈值'
FROM mission_task
WHERE code = 'MT-20260624-001';

INSERT INTO mission_event (mission_id, event_type, title, message, source, occurred_at)
SELECT id, 'CONFIG', '任务已创建', '系统初始化协同围捕演示任务，等待用户确认设备编组。', 'platform', NOW(6)
FROM mission_task
WHERE code = 'MT-20260624-001';

INSERT INTO mission_event (mission_id, event_type, title, message, source, occurred_at)
SELECT id, 'CONFIG', '联调任务已创建', '用于 ROS 与 Unity 数据链路验证的路径跟踪任务。', 'platform', NOW(6)
FROM mission_task
WHERE code = 'MT-20260624-002';
