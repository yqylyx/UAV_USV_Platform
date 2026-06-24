package com.uavusv.platform.module.runtimecontrol.repository;

import com.uavusv.platform.module.runtimecontrol.entity.ControlCommand;
import org.springframework.data.jpa.repository.JpaRepository;

public interface ControlCommandRepository extends JpaRepository<ControlCommand, Long> {
}
