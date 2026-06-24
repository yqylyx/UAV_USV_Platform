package com.uavusv.platform.module.mission.repository;

import com.uavusv.platform.module.mission.entity.MissionTask;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.JpaSpecificationExecutor;
import org.springframework.stereotype.Repository;

import java.util.Optional;

@Repository
public interface MissionTaskRepository extends JpaRepository<MissionTask, Long>, JpaSpecificationExecutor<MissionTask> {

    boolean existsByCode(String code);

    boolean existsByCodeAndIdNot(String code, Long id);

    Optional<MissionTask> findByIdAndDeletedFalse(Long id);
}
