package com.uavusv.platform.module.mission.repository;

import com.uavusv.platform.module.mission.entity.MissionEvent;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.stereotype.Repository;

import java.util.List;
import com.uavusv.platform.module.mission.entity.MissionEventLevel;
import org.springframework.data.domain.Pageable;

@Repository
public interface MissionEventRepository extends JpaRepository<MissionEvent, Long> {

    List<MissionEvent> findTop20ByMissionIdOrderByOccurredAtDesc(Long missionId);

    List<MissionEvent> findByMissionIdAndRunIdAndLevelOrderByOccurredAtDesc(
            Long missionId, Long runId, MissionEventLevel level, Pageable pageable);

    List<MissionEvent> findByMissionIdAndRunIdOrderByOccurredAtDesc(
            Long missionId, Long runId, Pageable pageable);

    List<MissionEvent> findByMissionIdAndLevelOrderByOccurredAtDesc(
            Long missionId, MissionEventLevel level, Pageable pageable);

    List<MissionEvent> findByMissionIdOrderByOccurredAtDesc(Long missionId, Pageable pageable);
}
