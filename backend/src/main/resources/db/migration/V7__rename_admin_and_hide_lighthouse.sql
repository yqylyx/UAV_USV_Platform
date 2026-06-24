UPDATE app_user
SET username = 'admin',
    display_name = '系统管理员'
WHERE username = 'root'
  AND NOT EXISTS (
      SELECT 1
      FROM (SELECT id FROM app_user WHERE username = 'admin') existing_admin
  );

UPDATE app_user
SET enabled = FALSE
WHERE username = 'root';

UPDATE mission_device
SET deleted = TRUE,
    deleted_at = COALESCE(deleted_at, NOW(6)),
    status = 'UNKNOWN'
WHERE code = 'lighthouse-01'
  AND deleted = FALSE;
