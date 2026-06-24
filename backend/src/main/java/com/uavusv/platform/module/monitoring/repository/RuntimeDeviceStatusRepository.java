package com.uavusv.platform.module.monitoring.repository;

import com.uavusv.platform.module.monitoring.entity.RuntimeDeviceStatus;
import org.springframework.data.jpa.repository.JpaRepository;

import java.util.Collection;
import java.util.List;
import java.util.Optional;

public interface RuntimeDeviceStatusRepository extends JpaRepository<RuntimeDeviceStatus, Long> {
    Optional<RuntimeDeviceStatus> findByDeviceId(Long deviceId);
    List<RuntimeDeviceStatus> findAllByDeviceIdIn(Collection<Long> deviceIds);
}
