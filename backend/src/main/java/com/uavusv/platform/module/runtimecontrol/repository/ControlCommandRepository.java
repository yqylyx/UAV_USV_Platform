package com.uavusv.platform.module.runtimecontrol.repository;

import com.uavusv.platform.module.runtimecontrol.entity.ControlCommand;
import com.uavusv.platform.module.runtimecontrol.entity.CommandStatus;
import org.springframework.data.jpa.repository.JpaRepository;

import java.util.List;
import java.util.Optional;
import java.time.LocalDateTime;
import java.util.Collection;

public interface ControlCommandRepository extends JpaRepository<ControlCommand, Long> {
    List<ControlCommand> findTop100ByOrderByRequestedAtDesc();

    Optional<ControlCommand> findByCommandKey(String commandKey);

    List<ControlCommand> findAllByStatusAndDispatchedAtBefore(CommandStatus status, LocalDateTime cutoff);

    boolean existsByRunIdAndStatusIn(Long runId, Collection<CommandStatus> statuses);
}
