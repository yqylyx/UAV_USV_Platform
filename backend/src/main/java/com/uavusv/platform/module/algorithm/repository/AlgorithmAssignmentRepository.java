package com.uavusv.platform.module.algorithm.repository;

import com.uavusv.platform.module.algorithm.entity.AlgorithmAssignment;
import org.springframework.data.jpa.repository.JpaRepository;

import java.util.List;

public interface AlgorithmAssignmentRepository extends JpaRepository<AlgorithmAssignment, Long> {
    List<AlgorithmAssignment> findByCommandIdOrderByIdAsc(String commandId);

    void deleteByCommandId(String commandId);
}
