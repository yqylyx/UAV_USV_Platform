package com.uavusv.platform.module.mission.repository;

import com.uavusv.platform.module.mission.entity.MissionTaskDevice;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.stereotype.Repository;

import java.util.List;

@Repository
public interface MissionTaskDeviceRepository extends JpaRepository<MissionTaskDevice, Long> {

    List<MissionTaskDevice> findAllByMissionIdOrderByAssignedAtAsc(Long missionId);

    long countByMissionId(Long missionId);

    void deleteByMissionId(Long missionId);
}
