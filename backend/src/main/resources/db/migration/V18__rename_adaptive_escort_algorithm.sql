UPDATE algorithm_definition
SET name = 'SeaShield-ACG 海空异构集群智能护航围控',
    version = '1.2.0-20260908',
    device_scale = '3-30 UAV + 3-30 USV + 1 护航目标 + 多威胁目标',
    description = '基于意图识别、稳定护航编队、海空协同拦截、动态追逃与严格闭环验收的自适应护航围控算法。'
WHERE code = 'ESCORT_GUARD';

UPDATE mission_task
SET algorithm_version = '1.2.0-20260908'
WHERE algorithm_code = 'ESCORT_GUARD';
