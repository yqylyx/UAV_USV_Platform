package com.uavusv.platform.module.system.repository;

import com.uavusv.platform.module.system.entity.PlatformComponent;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.stereotype.Repository;

@Repository
public interface PlatformComponentRepository extends JpaRepository<PlatformComponent, Long> {
}
