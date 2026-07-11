UPDATE mission_device
SET name = '协同无人机 1',
    ros_namespace = '/uav_01',
    description = '一号协同无人机，执行起飞、侦察、补盲和围捕任务',
    deleted = FALSE,
    deleted_at = NULL
WHERE code = 'uav-01';

UPDATE mission_device
SET name = '协同无人艇 1',
    ros_namespace = '/usv_01',
    description = '一号协同无人艇，执行目标接近、拦截和合围任务',
    deleted = FALSE,
    deleted_at = NULL
WHERE code = 'usv-01';

INSERT INTO mission_device (
    code, name, type, status, host, port, ros_namespace, description, deleted, deleted_at
)
VALUES
    ('uav-02', '协同无人机 2', 'UAV', 'UNKNOWN', '127.0.0.1', NULL, '/uav_02', '二号协同无人机，执行目标跟踪和空中补盲任务', FALSE, NULL),
    ('uav-03', '协同无人机 3', 'UAV', 'UNKNOWN', '127.0.0.1', NULL, '/uav_03', '三号协同无人机，执行目标跟踪和空中补盲任务', FALSE, NULL),
    ('usv-02', '协同无人艇 2', 'USV', 'UNKNOWN', '127.0.0.1', NULL, '/usv_02', '二号协同无人艇，执行侧翼封控和合围任务', FALSE, NULL),
    ('usv-03', '协同无人艇 3', 'USV', 'UNKNOWN', '127.0.0.1', NULL, '/usv_03', '三号协同无人艇，执行侧翼封控和合围任务', FALSE, NULL)
ON DUPLICATE KEY UPDATE
    name = VALUES(name),
    type = VALUES(type),
    host = VALUES(host),
    port = VALUES(port),
    ros_namespace = VALUES(ros_namespace),
    description = VALUES(description),
    deleted = FALSE,
    deleted_at = NULL;

INSERT INTO device_runtime_status (device_id, status, source)
SELECT device.id, 'UNKNOWN', 'REGISTRY'
FROM mission_device device
LEFT JOIN device_runtime_status runtime_status ON runtime_status.device_id = device.id
WHERE device.code IN ('uav-01', 'uav-02', 'uav-03', 'usv-01', 'usv-02', 'usv-03')
  AND device.deleted = FALSE
  AND runtime_status.id IS NULL;

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
       '三机三艇协同围捕编组'
FROM mission_task task
JOIN mission_device device
  ON device.code IN ('uav-01', 'uav-02', 'uav-03', 'usv-01', 'usv-02', 'usv-03')
LEFT JOIN mission_task_device binding
  ON binding.mission_id = task.id
 AND binding.device_id = device.id
WHERE task.code = 'MT-20260624-001'
  AND task.deleted = FALSE
  AND device.deleted = FALSE
  AND binding.id IS NULL;

UPDATE mission_task_parameter parameter_item
JOIN mission_task task ON task.id = parameter_item.mission_id
SET parameter_item.param_value = '18',
    parameter_item.param_unit = 'm',
    parameter_item.description = 'USV 目标捕获半径，与 Unity captureRadius 保持一致'
WHERE task.code = 'MT-20260624-001'
  AND parameter_item.param_key = 'encirclement_radius';

INSERT INTO mission_task_parameter (
    mission_id, param_key, param_value, param_unit, description
)
SELECT task.id, parameter_item.param_key, parameter_item.param_value, parameter_item.param_unit, parameter_item.description
FROM mission_task task
JOIN (
    SELECT 'uav_count' AS param_key, '3' AS param_value, '架' AS param_unit, '参与围捕的无人机数量' AS description
    UNION ALL
    SELECT 'usv_count', '3', '艘', '参与围捕的无人艇数量'
    UNION ALL
    SELECT 'uav_defense_radius', '30', 'm', 'UAV 空中防御半径，与 Unity defenseRadius 保持一致'
) parameter_item
WHERE task.code = 'MT-20260624-001'
ON DUPLICATE KEY UPDATE
    param_value = VALUES(param_value),
    param_unit = VALUES(param_unit),
    description = VALUES(description);

UPDATE mission_task
SET description = '三架无人机与三艘无人艇协同围捕主任务，覆盖任务配置、六设备编组、状态监控和 Unity 态势观察闭环。'
WHERE code = 'MT-20260624-001';

INSERT INTO mission_event (
    mission_id, event_type, stage, level, title, message, source, occurred_at
)
SELECT id,
       'CONFIG',
       'PREPARE',
       'INFO',
       '设备编组升级为三机三艇',
       '系统已补齐 UAV-01 至 UAV-03、USV-01 至 USV-03，并同步 Unity 捕获与防御半径参数。',
       'platform-migration',
       NOW(6)
FROM mission_task
WHERE code = 'MT-20260624-001';
