package com.uavusv.platform.module.algorithm.repository;

import com.uavusv.platform.module.algorithm.entity.AlgorithmEvent;
import org.springframework.data.jpa.repository.JpaRepository;

import java.util.List;

public interface AlgorithmEventRepository extends JpaRepository<AlgorithmEvent, Long> {
    List<AlgorithmEvent> findTop100ByOrderByOccurredAtDesc();

    List<AlgorithmEvent> findTop100ByCommandIdOrderByOccurredAtDesc(String commandId);
}
