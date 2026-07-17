package com.uavusv.platform.module.runtimecontrol.repository;

import com.uavusv.platform.module.runtimecontrol.entity.ControlCommand;
import com.uavusv.platform.module.runtimecontrol.entity.CommandStatus;
import org.springframework.data.jpa.repository.JpaRepository;

import java.util.List;
import java.util.Optional;
import java.time.LocalDateTime;
import java.util.Collection;
import org.springframework.data.domain.Pageable;

public interface ControlCommandRepository extends JpaRepository<ControlCommand, Long> {
    List<ControlCommand> findTop100ByOrderByRequestedAtDesc();

    List<ControlCommand> findByRunIdOrderByRequestedAtDesc(Long runId, Pageable pageable);

    List<ControlCommand> findAllByOrderByRequestedAtDesc(Pageable pageable);

    Optional<ControlCommand> findByCommandKey(String commandKey);

    List<ControlCommand> findAllByStatusAndDispatchedAtBefore(CommandStatus status, LocalDateTime cutoff);

    boolean existsByRunIdAndDeviceIdAndStatusIn(Long runId, Long deviceId, Collection<CommandStatus> statuses);

    boolean existsByRunIdAndDeviceIdIsNullAndStatusIn(Long runId, Collection<CommandStatus> statuses);
}
