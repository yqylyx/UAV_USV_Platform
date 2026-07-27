package com.uavusv.platform.module.mission.repository;

import com.uavusv.platform.module.mission.entity.AlgorithmDefinition;
import com.uavusv.platform.module.mission.entity.MissionType;
import org.springframework.data.jpa.repository.JpaRepository;

import java.util.List;
import java.util.Optional;

public interface AlgorithmDefinitionRepository extends JpaRepository<AlgorithmDefinition, Long> {
    List<AlgorithmDefinition> findAllByOrderByMissionTypeAscNameAsc();
    Optional<AlgorithmDefinition> findByCode(String code);
    List<AlgorithmDefinition> findAllByMissionType(MissionType missionType);
}
