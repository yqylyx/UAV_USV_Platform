package com.uavusv.platform.module.runtimecontrol.repository;

import com.uavusv.platform.module.runtimecontrol.entity.SimulationSession;
import com.uavusv.platform.module.runtimecontrol.entity.SimulationStatus;
import org.springframework.data.jpa.repository.JpaRepository;

import java.util.Collection;
import java.util.Optional;

public interface SimulationSessionRepository extends JpaRepository<SimulationSession, Long> {
    Optional<SimulationSession> findFirstByStatusInOrderByCreatedAtDesc(Collection<SimulationStatus> statuses);
    Optional<SimulationSession> findFirstByOrderByCreatedAtDesc();
}
