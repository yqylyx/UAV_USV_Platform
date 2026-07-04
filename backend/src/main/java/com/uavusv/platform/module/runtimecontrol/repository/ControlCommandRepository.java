package com.uavusv.platform.module.runtimecontrol.repository;

import com.uavusv.platform.module.runtimecontrol.entity.ControlCommand;
import org.springframework.data.jpa.repository.JpaRepository;

import java.util.List;

public interface ControlCommandRepository extends JpaRepository<ControlCommand, Long> {
    List<ControlCommand> findTop100ByOrderByRequestedAtDesc();
}
