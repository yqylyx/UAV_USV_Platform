package com.uavusv.platform.module.monitoring.repository;

import com.uavusv.platform.module.monitoring.entity.DeviceTelemetry;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.Modifying;
import org.springframework.data.jpa.repository.Query;
import org.springframework.data.repository.query.Param;

import java.time.LocalDateTime;
import java.util.Collection;
import java.util.List;

public interface DeviceTelemetryRepository extends JpaRepository<DeviceTelemetry, Long> {
    @Query("""
            select telemetry
            from DeviceTelemetry telemetry
            where telemetry.deviceId in :deviceIds
              and telemetry.recordedAt = (
                select max(candidate.recordedAt)
                from DeviceTelemetry candidate
                where candidate.deviceId = telemetry.deviceId
              )
            """)
    List<DeviceTelemetry> findLatestByDeviceIds(@Param("deviceIds") Collection<Long> deviceIds);

    @Modifying
    @Query("delete from DeviceTelemetry telemetry where telemetry.recordedAt < :cutoff")
    int deleteOlderThan(LocalDateTime cutoff);
}
