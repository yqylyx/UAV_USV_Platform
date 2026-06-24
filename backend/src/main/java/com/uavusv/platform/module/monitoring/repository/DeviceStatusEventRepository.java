package com.uavusv.platform.module.monitoring.repository;

import com.uavusv.platform.module.monitoring.entity.DeviceStatusEvent;
import org.springframework.data.jpa.repository.JpaRepository;

public interface DeviceStatusEventRepository extends JpaRepository<DeviceStatusEvent, Long> {
}
