package com.uavusv.platform.module.device.service.impl;

import com.uavusv.platform.common.api.PageResponse;
import com.uavusv.platform.common.exception.BusinessException;
import com.uavusv.platform.common.exception.ErrorCode;
import com.uavusv.platform.module.device.dto.request.DeviceSaveRequest;
import com.uavusv.platform.module.device.dto.response.DeviceResponse;
import com.uavusv.platform.module.device.entity.Device;
import com.uavusv.platform.module.device.entity.DeviceStatus;
import com.uavusv.platform.module.device.entity.DeviceType;
import com.uavusv.platform.module.device.repository.DeviceRepository;
import com.uavusv.platform.module.device.service.DeviceService;
import jakarta.persistence.criteria.Predicate;
import org.springframework.data.domain.Page;
import org.springframework.data.domain.PageRequest;
import org.springframework.data.domain.Pageable;
import org.springframework.data.domain.Sort;
import org.springframework.data.jpa.domain.Specification;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.util.StringUtils;

import java.util.ArrayList;
import java.util.List;

@Service
@Transactional(readOnly = true)
public class DeviceServiceImpl implements DeviceService {

    private static final int MAX_PAGE_SIZE = 100;

    private final DeviceRepository deviceRepository;

    public DeviceServiceImpl(DeviceRepository deviceRepository) {
        this.deviceRepository = deviceRepository;
    }

    @Override
    public PageResponse<DeviceResponse> listDevices(
            String keyword,
            DeviceType type,
            DeviceStatus status,
            int page,
            int size
    ) {
        Pageable pageable = PageRequest.of(
                Math.max(page, 0),
                Math.min(Math.max(size, 1), MAX_PAGE_SIZE),
                Sort.by(Sort.Direction.DESC, "updatedAt")
        );
        Page<DeviceResponse> responsePage = deviceRepository
                .findAll(buildSpecification(keyword, type, status), pageable)
                .map(DeviceResponse::from);
        return PageResponse.from(responsePage);
    }

    @Override
    public DeviceResponse getDevice(Long id) {
        return DeviceResponse.from(findDevice(id));
    }

    @Override
    @Transactional
    public DeviceResponse createDevice(DeviceSaveRequest request) {
        if (deviceRepository.existsByCode(request.code())) {
            throw new BusinessException(ErrorCode.DEVICE_CODE_EXISTS);
        }

        Device device = new Device(
                request.code(),
                request.name(),
                request.type(),
                request.status(),
                request.host(),
                request.port(),
                request.rosNamespace(),
                request.description()
        );
        return DeviceResponse.from(deviceRepository.save(device));
    }

    @Override
    @Transactional
    public DeviceResponse updateDevice(Long id, DeviceSaveRequest request) {
        Device device = findDevice(id);
        if (deviceRepository.existsByCodeAndIdNot(request.code(), id)) {
            throw new BusinessException(ErrorCode.DEVICE_CODE_EXISTS);
        }

        device.update(
                request.code(),
                request.name(),
                request.type(),
                request.status(),
                request.host(),
                request.port(),
                request.rosNamespace(),
                request.description()
        );
        return DeviceResponse.from(device);
    }

    @Override
    @Transactional
    public void deleteDevice(Long id) {
        Device device = findDevice(id);
        device.softDelete();
    }

    private Device findDevice(Long id) {
        return deviceRepository.findByIdAndDeletedFalse(id)
                .orElseThrow(() -> new BusinessException(ErrorCode.DEVICE_NOT_FOUND));
    }

    private Specification<Device> buildSpecification(
            String keyword,
            DeviceType type,
            DeviceStatus status
    ) {
        return (root, query, criteriaBuilder) -> {
            List<Predicate> predicates = new ArrayList<>();
            predicates.add(criteriaBuilder.isFalse(root.get("deleted")));

            if (StringUtils.hasText(keyword)) {
                String pattern = "%" + keyword.trim().toLowerCase() + "%";
                predicates.add(criteriaBuilder.or(
                        criteriaBuilder.like(criteriaBuilder.lower(root.get("code")), pattern),
                        criteriaBuilder.like(criteriaBuilder.lower(root.get("name")), pattern),
                        criteriaBuilder.like(criteriaBuilder.lower(root.get("host")), pattern),
                        criteriaBuilder.like(criteriaBuilder.lower(root.get("rosNamespace")), pattern)
                ));
            }

            if (type != null) {
                predicates.add(criteriaBuilder.equal(root.get("type"), type));
            }

            if (status != null) {
                predicates.add(criteriaBuilder.equal(root.get("status"), status));
            }

            return criteriaBuilder.and(predicates.toArray(Predicate[]::new));
        };
    }
}
