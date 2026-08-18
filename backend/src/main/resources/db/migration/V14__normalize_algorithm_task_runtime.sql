-- Python-backed algorithm experiments run in the dedicated Task Center Unity
-- scope. They must not inherit the ROS/hardware readiness rules used by the
-- system-overview runtime.
UPDATE mission_task
SET execution_mode = 'UNITY_STANDALONE'
WHERE code IN ('MT-20260624-001', 'MT-20260624-002')
  AND algorithm_code IN ('GB_SFLA_CS', 'ESCORT_GUARD');
