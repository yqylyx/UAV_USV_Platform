UPDATE control_command
SET status = 'SUCCEEDED'
WHERE status = 'ACKNOWLEDGED';
