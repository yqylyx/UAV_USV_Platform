ALTER TABLE mission_device
    ADD COLUMN deleted BOOLEAN NOT NULL DEFAULT FALSE AFTER description,
    ADD COLUMN deleted_at DATETIME(6) NULL AFTER deleted,
    ADD KEY idx_mission_device_deleted (deleted);
