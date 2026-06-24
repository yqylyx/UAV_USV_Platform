package com.uavusv.platform.module.monitoring.repository;

import com.uavusv.platform.module.monitoring.entity.DeviceTelemetry;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.Modifying;
import org.springframework.data.jpa.repository.Query;

import java.time.LocalDateTime;

public interface DeviceTelemetryRepository extends JpaRepository<DeviceTelemetry, Long> {
    @Modifying
    @Query("delete from DeviceTelemetry telemetry where telemetry.recordedAt < :cutoff")
    int deleteOlderThan(LocalDateTime cutoff);
}
