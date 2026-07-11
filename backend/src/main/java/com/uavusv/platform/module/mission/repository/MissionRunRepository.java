package com.uavusv.platform.module.mission.repository;

import com.uavusv.platform.module.mission.entity.MissionRun;
import com.uavusv.platform.module.mission.entity.MissionRunStatus;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.Query;
import org.springframework.data.repository.query.Param;
import org.springframework.stereotype.Repository;

import java.util.Collection;
import java.util.List;
import java.util.Optional;

@Repository
public interface MissionRunRepository extends JpaRepository<MissionRun, Long> {

    Optional<MissionRun> findFirstByMissionIdAndStatusInOrderByStartedAtDesc(
            Long missionId,
            Collection<MissionRunStatus> statuses
    );

    List<MissionRun> findTop10ByMissionIdOrderByStartedAtDesc(Long missionId);

    Optional<MissionRun> findFirstByStatusInOrderByStartedAtDesc(Collection<MissionRunStatus> statuses);

    @Query("select coalesce(max(run.runNo), 0) from MissionRun run where run.missionId = :missionId")
    int findMaxRunNo(@Param("missionId") Long missionId);
}
