package com.uavusv.platform.module.algorithm.repository;

import com.uavusv.platform.module.algorithm.entity.AlgorithmRun;
import com.uavusv.platform.module.algorithm.entity.AlgorithmRunStatus;
import org.springframework.data.jpa.repository.JpaRepository;

import java.time.LocalDateTime;
import java.util.Collection;
import java.util.List;
import java.util.Optional;

public interface AlgorithmRunRepository extends JpaRepository<AlgorithmRun, Long> {
    Optional<AlgorithmRun> findByCommandId(String commandId);

    List<AlgorithmRun> findTop50ByOrderByStartedAtDesc();

    List<AlgorithmRun> findAllByStatusInAndStartedAtBefore(Collection<AlgorithmRunStatus> statuses, LocalDateTime cutoff);
}
