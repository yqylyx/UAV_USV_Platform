ALTER TABLE mission_task
    ADD COLUMN algorithm_code VARCHAR(64) NOT NULL DEFAULT 'UNITY_SIMPLE_ENCIRCLEMENT' AFTER execution_mode,
    ADD COLUMN algorithm_version VARCHAR(32) NOT NULL DEFAULT '1.0.0' AFTER algorithm_code,
    ADD KEY idx_mission_task_algorithm (algorithm_code);

CREATE TABLE algorithm_definition (
    id BIGINT NOT NULL AUTO_INCREMENT,
    code VARCHAR(64) NOT NULL,
    name VARCHAR(120) NOT NULL,
    version VARCHAR(32) NOT NULL,
    mission_type VARCHAR(40) NOT NULL,
    adapter_type VARCHAR(40) NOT NULL,
    device_scale VARCHAR(40) NOT NULL DEFAULT '3 UAV + 3 USV',
    enabled BOOLEAN NOT NULL DEFAULT TRUE,
    default_for_type BOOLEAN NOT NULL DEFAULT FALSE,
    description VARCHAR(500) NULL,
    created_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    updated_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6),
    PRIMARY KEY (id),
    UNIQUE KEY uk_algorithm_definition_code (code),
    KEY idx_algorithm_definition_type_enabled (mission_type, enabled)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

INSERT INTO algorithm_definition (code, name, version, mission_type, adapter_type, device_scale, enabled, default_for_type, description) VALUES
('GB_SFLA_CS', 'GB-SFLA-CS 协同围捕', '1.0.0', 'COOPERATIVE_ENCIRCLEMENT', 'PYTHON_PROCESS', '3 UAV + 3 USV + 1 目标', TRUE, TRUE, '粒球、SFLA 与 CS 混合分配及围捕算法。'),
('ESCORT_GUARD', '混合 UAV/USV 护航守卫', '1.0.0', 'COOPERATIVE_ESCORT', 'PYTHON_PROCESS', '3 UAV + 3 USV + 护航目标 + 威胁目标', TRUE, TRUE, '移动护航目标、威胁方向阻断与动态重编队算法。'),
('UNITY_SIMPLE_ENCIRCLEMENT', 'Unity 默认简单围捕', '1.0.0', 'COOPERATIVE_ENCIRCLEMENT', 'UNITY_NATIVE', '3 UAV + 3 USV + 1 目标', TRUE, FALSE, '保留现有 Unity 内置简单围捕能力。');

UPDATE mission_task
SET name = '三机三艇协同围捕演示任务',
    type = 'COOPERATIVE_ENCIRCLEMENT',
    algorithm_code = 'GB_SFLA_CS',
    algorithm_version = '1.0.0',
    target_name = '海面机动目标',
    target_behavior = '低速机动',
    description = '三机三艇执行 GB-SFLA-CS 协同围捕，二维轨迹与任务中心 Unity 使用同一算法帧。'
WHERE code = 'MT-20260624-001';

UPDATE mission_task
SET name = '三机三艇协同护航演示任务',
    type = 'COOPERATIVE_ESCORT',
    status = 'READY',
    execution_mode = 'UNITY_STANDALONE',
    algorithm_code = 'ESCORT_GUARD',
    algorithm_version = '1.0.0',
    target_name = '护航目标-01',
    target_behavior = '沿预设航线低速航行',
    description = '三机三艇保护移动护航目标并根据威胁方向动态部署守卫。'
WHERE code = 'MT-20260624-002';

-- Algorithm tasks use payload vehicles only. Infrastructure nodes are not
-- part of the 3 UAV + 3 USV algorithm composition.
DELETE binding
FROM mission_task_device binding
JOIN mission_task task ON task.id = binding.mission_id
WHERE task.code IN ('MT-20260624-001', 'MT-20260624-002');

INSERT INTO mission_task_device (
    mission_id, device_id, role, call_sign, required, assigned_at, notes
)
SELECT task.id,
       device.id,
       CASE
           WHEN device.code = 'uav-01' THEN 'UAV_RECON'
           WHEN device.type = 'UAV' THEN 'UAV_TRACK'
           WHEN device.code = 'usv-01' THEN 'USV_INTERCEPT'
           ELSE 'USV_BLOCKADE'
       END,
       device.code,
       TRUE,
       NOW(6),
       '3 UAV + 3 USV algorithm payload'
FROM mission_task task
JOIN mission_device device
  ON device.code IN ('uav-01', 'uav-02', 'uav-03', 'usv-01', 'usv-02', 'usv-03')
WHERE task.code IN ('MT-20260624-001', 'MT-20260624-002')
  AND task.deleted = FALSE
  AND device.deleted = FALSE;

INSERT INTO mission_task_parameter (mission_id, param_key, param_value, param_unit, description)
SELECT task.id, defaults.param_key, defaults.param_value, defaults.param_unit, defaults.description
FROM mission_task task
JOIN (
    SELECT 'uav_count' AS param_key, '3' AS param_value, 'unit' AS param_unit, 'Required UAV count' AS description
    UNION ALL SELECT 'usv_count', '3', 'unit', 'Required USV count'
) defaults
WHERE task.code IN ('MT-20260624-001', 'MT-20260624-002')
ON DUPLICATE KEY UPDATE
    param_value = VALUES(param_value),
    param_unit = VALUES(param_unit),
    description = VALUES(description);

INSERT INTO mission_task_parameter (mission_id, param_key, param_value, param_unit, description)
SELECT task.id, defaults.param_key, defaults.param_value, defaults.param_unit, defaults.description
FROM mission_task task
JOIN (
    SELECT 'escort_route' AS param_key, '-22,-12|-10,-12|4,-7|18,-3|28,4' AS param_value, 'scene' AS param_unit, 'Protected-vessel route' AS description
    UNION ALL SELECT 'escort_speed', '0.09', 'scene/s', 'Protected-vessel cruise speed'
    UNION ALL SELECT 'threat_frame', '24', 'frame', 'Automatic threat activation frame'
) defaults
WHERE task.code = 'MT-20260624-002'
ON DUPLICATE KEY UPDATE
    param_value = VALUES(param_value),
    param_unit = VALUES(param_unit),
    description = VALUES(description);
