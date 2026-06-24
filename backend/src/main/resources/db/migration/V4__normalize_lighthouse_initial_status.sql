UPDATE mission_device
SET status = 'UNKNOWN'
WHERE type = 'LIGHTHOUSE'
  AND status = 'ONLINE';
