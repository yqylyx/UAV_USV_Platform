package com.uavusv.platform.module.device.repository;

import com.uavusv.platform.module.device.entity.Device;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.JpaSpecificationExecutor;
import org.springframework.stereotype.Repository;
import org.springframework.data.domain.Sort;

import java.util.List;
import java.util.Optional;

@Repository
public interface DeviceRepository extends JpaRepository<Device, Long>, JpaSpecificationExecutor<Device> {

    boolean existsByCode(String code);

    boolean existsByCodeAndIdNot(String code, Long id);

    Optional<Device> findByCode(String code);

    Optional<Device> findByIdAndDeletedFalse(Long id);

    List<Device> findAllByDeletedFalse(Sort sort);
}
