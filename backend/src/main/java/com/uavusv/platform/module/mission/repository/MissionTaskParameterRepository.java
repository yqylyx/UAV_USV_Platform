package com.uavusv.platform.module.mission.repository;

import com.uavusv.platform.module.mission.entity.MissionTaskParameter;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.stereotype.Repository;

import java.util.List;

@Repository
public interface MissionTaskParameterRepository extends JpaRepository<MissionTaskParameter, Long> {

    List<MissionTaskParameter> findAllByMissionIdOrderByKeyAsc(Long missionId);

    void deleteByMissionId(Long missionId);
}
