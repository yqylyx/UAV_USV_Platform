package com.uavusv.platform.module.mission.repository;

import com.uavusv.platform.module.mission.entity.MissionEvent;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.stereotype.Repository;

import java.util.List;

@Repository
public interface MissionEventRepository extends JpaRepository<MissionEvent, Long> {

    List<MissionEvent> findTop20ByMissionIdOrderByOccurredAtDesc(Long missionId);
}
