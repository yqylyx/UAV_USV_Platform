UPDATE algorithm_definition
SET version = '1.1.0-20260727',
    device_scale = '3 UAV + 3 USV + 1 目标',
    description = '2026-07-27 版粒球、SFLA 与 CS 混合分配及围捕算法；含统一场景坐标、安全间距与平滑轨迹适配。'
WHERE code = 'GB_SFLA_CS';

UPDATE algorithm_definition
SET version = '1.1.0-20260727',
    device_scale = '3 UAV + 3 USV + 护航目标 + 1 威胁目标',
    description = '2026-07-27 版混合 UAV/USV 护航守卫算法；含移动护航航线、单威胁响应、安全间距与平滑轨迹适配。'
WHERE code = 'ESCORT_GUARD';

UPDATE mission_task
SET algorithm_version = '1.1.0-20260727'
WHERE algorithm_code IN ('GB_SFLA_CS', 'ESCORT_GUARD');
