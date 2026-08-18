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
    @Query(value = """
            select telemetry.*
            from device_telemetry telemetry
            join (
                select device_id, max(id) as latest_id
                from device_telemetry
                where device_id in (:deviceIds)
                group by device_id
            ) latest on latest.latest_id = telemetry.id
            """, nativeQuery = true)
    List<DeviceTelemetry> findLatestByDeviceIds(@Param("deviceIds") Collection<Long> deviceIds);

    @Modifying
    @Query("delete from DeviceTelemetry telemetry where telemetry.recordedAt < :cutoff")
    int deleteOlderThan(LocalDateTime cutoff);
}
