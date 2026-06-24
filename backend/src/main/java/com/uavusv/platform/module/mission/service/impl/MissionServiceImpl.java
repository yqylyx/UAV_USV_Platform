package com.uavusv.platform.module.mission.service.impl;

import com.uavusv.platform.common.api.PageResponse;
import com.uavusv.platform.common.exception.BusinessException;
import com.uavusv.platform.common.exception.ErrorCode;
import com.uavusv.platform.module.device.entity.Device;
import com.uavusv.platform.module.device.repository.DeviceRepository;
import com.uavusv.platform.module.mission.dto.request.MissionDeviceBindingRequest;
import com.uavusv.platform.module.mission.dto.request.MissionParameterRequest;
import com.uavusv.platform.module.mission.dto.request.MissionSaveRequest;
import com.uavusv.platform.module.mission.dto.response.MissionDetailResponse;
import com.uavusv.platform.module.mission.dto.response.MissionDeviceResponse;
import com.uavusv.platform.module.mission.dto.response.MissionEventResponse;
import com.uavusv.platform.module.mission.dto.response.MissionParameterResponse;
import com.uavusv.platform.module.mission.dto.response.MissionResponse;
import com.uavusv.platform.module.mission.entity.MissionEvent;
import com.uavusv.platform.module.mission.entity.MissionEventType;
import com.uavusv.platform.module.mission.entity.MissionStatus;
import com.uavusv.platform.module.mission.entity.MissionTask;
import com.uavusv.platform.module.mission.entity.MissionTaskDevice;
import com.uavusv.platform.module.mission.entity.MissionTaskParameter;
import com.uavusv.platform.module.mission.entity.MissionType;
import com.uavusv.platform.module.mission.repository.MissionEventRepository;
import com.uavusv.platform.module.mission.repository.MissionTaskDeviceRepository;
import com.uavusv.platform.module.mission.repository.MissionTaskParameterRepository;
import com.uavusv.platform.module.mission.repository.MissionTaskRepository;
import com.uavusv.platform.module.mission.service.MissionService;
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
import java.util.Collections;
import java.util.HashMap;
import java.util.List;
import java.util.Map;

@Service
@Transactional(readOnly = true)
public class MissionServiceImpl implements MissionService {

    private static final int MAX_PAGE_SIZE = 100;

    private final MissionTaskRepository missionTaskRepository;
    private final MissionTaskDeviceRepository missionTaskDeviceRepository;
    private final MissionTaskParameterRepository missionTaskParameterRepository;
    private final MissionEventRepository missionEventRepository;
    private final DeviceRepository deviceRepository;

    public MissionServiceImpl(
            MissionTaskRepository missionTaskRepository,
            MissionTaskDeviceRepository missionTaskDeviceRepository,
            MissionTaskParameterRepository missionTaskParameterRepository,
            MissionEventRepository missionEventRepository,
            DeviceRepository deviceRepository
    ) {
        this.missionTaskRepository = missionTaskRepository;
        this.missionTaskDeviceRepository = missionTaskDeviceRepository;
        this.missionTaskParameterRepository = missionTaskParameterRepository;
        this.missionEventRepository = missionEventRepository;
        this.deviceRepository = deviceRepository;
    }

    @Override
    public PageResponse<MissionResponse> listMissions(
            String keyword,
            MissionType type,
            MissionStatus status,
            int page,
            int size
    ) {
        Pageable pageable = PageRequest.of(
                Math.max(page, 0),
                Math.min(Math.max(size, 1), MAX_PAGE_SIZE),
                Sort.by(Sort.Direction.DESC, "updatedAt")
        );
        Page<MissionResponse> responsePage = missionTaskRepository
                .findAll(buildSpecification(keyword, type, status), pageable)
                .map(mission -> MissionResponse.from(
                        mission,
                        Math.toIntExact(missionTaskDeviceRepository.countByMissionId(mission.getId()))
                ));
        return PageResponse.from(responsePage);
    }

    @Override
    public MissionDetailResponse getMission(Long id) {
        return buildDetail(findMission(id));
    }

    @Override
    @Transactional
    public MissionDetailResponse createMission(MissionSaveRequest request) {
        if (missionTaskRepository.existsByCode(request.code())) {
            throw new BusinessException(ErrorCode.DEVICE_CODE_EXISTS, "任务编号已存在");
        }
        MissionTask mission = new MissionTask(request.code());
        applyMissionFields(mission, request);
        MissionTask saved = missionTaskRepository.save(mission);
        replaceBindings(saved.getId(), request.devices());
        replaceParameters(saved.getId(), request.parameters());
        missionEventRepository.save(new MissionEvent(
                saved.getId(),
                MissionEventType.CONFIG,
                "任务已创建",
                "任务配置已写入平台，等待进入运行链路。",
                "platform"
        ));
        return buildDetail(saved);
    }

    @Override
    @Transactional
    public MissionDetailResponse updateMission(Long id, MissionSaveRequest request) {
        MissionTask mission = findMission(id);
        if (missionTaskRepository.existsByCodeAndIdNot(request.code(), id)) {
            throw new BusinessException(ErrorCode.DEVICE_CODE_EXISTS, "任务编号已存在");
        }
        applyMissionFields(mission, request);
        replaceBindings(mission.getId(), request.devices());
        replaceParameters(mission.getId(), request.parameters());
        missionEventRepository.save(new MissionEvent(
                mission.getId(),
                MissionEventType.CONFIG,
                "任务配置已更新",
                "任务基础信息、设备编组或参数已调整。",
                "platform"
        ));
        return buildDetail(mission);
    }

    @Override
    @Transactional
    public void deleteMission(Long id) {
        MissionTask mission = findMission(id);
        mission.softDelete();
        missionEventRepository.save(new MissionEvent(
                mission.getId(),
                MissionEventType.STATUS,
                "任务已隐藏",
                "任务从任务控制列表中隐藏，历史事件和编组记录保留。",
                "platform"
        ));
    }

    private void applyMissionFields(MissionTask mission, MissionSaveRequest request) {
        mission.update(
                request.code(),
                request.name(),
                request.type(),
                request.status(),
                request.stage(),
                request.priority() == null ? 3 : request.priority(),
                request.targetName(),
                request.targetBehavior(),
                request.missionArea(),
                request.plannedStartAt(),
                request.plannedEndAt(),
                request.description()
        );
    }

    private void replaceBindings(Long missionId, List<MissionDeviceBindingRequest> devices) {
        missionTaskDeviceRepository.deleteByMissionId(missionId);
        if (devices == null || devices.isEmpty()) return;

        List<MissionTaskDevice> bindings = devices.stream()
                .map(binding -> {
                    Device device = deviceRepository.findByIdAndDeletedFalse(binding.deviceId())
                            .orElseThrow(() -> new BusinessException(ErrorCode.DEVICE_NOT_FOUND));
                    return new MissionTaskDevice(
                            missionId,
                            device.getId(),
                            binding.role(),
                            StringUtils.hasText(binding.callSign()) ? binding.callSign() : device.getCode(),
                            binding.required() == null || binding.required(),
                            binding.notes()
                    );
                })
                .toList();
        missionTaskDeviceRepository.saveAll(bindings);
    }

    private void replaceParameters(Long missionId, List<MissionParameterRequest> parameters) {
        missionTaskParameterRepository.deleteByMissionId(missionId);
        if (parameters == null || parameters.isEmpty()) return;

        missionTaskParameterRepository.saveAll(parameters.stream()
                .map(parameter -> new MissionTaskParameter(
                        missionId,
                        parameter.key(),
                        parameter.value(),
                        parameter.unit(),
                        parameter.description()
                ))
                .toList());
    }

    private MissionTask findMission(Long id) {
        return missionTaskRepository.findByIdAndDeletedFalse(id)
                .orElseThrow(() -> new BusinessException(ErrorCode.NOT_FOUND, "任务不存在"));
    }

    private MissionDetailResponse buildDetail(MissionTask mission) {
        List<MissionTaskDevice> bindings = missionTaskDeviceRepository.findAllByMissionIdOrderByAssignedAtAsc(mission.getId());
        Map<Long, Device> deviceMap = loadDevices(bindings);
        List<MissionDeviceResponse> devices = bindings.stream()
                .map(binding -> MissionDeviceResponse.from(binding, deviceMap.get(binding.getDeviceId())))
                .toList();
        List<MissionParameterResponse> parameters = missionTaskParameterRepository.findAllByMissionIdOrderByKeyAsc(mission.getId())
                .stream()
                .map(MissionParameterResponse::from)
                .toList();
        List<MissionEventResponse> events = missionEventRepository.findTop20ByMissionIdOrderByOccurredAtDesc(mission.getId())
                .stream()
                .map(MissionEventResponse::from)
                .toList();
        return new MissionDetailResponse(
                MissionResponse.from(mission, devices.size()),
                devices,
                parameters,
                events
        );
    }

    private Map<Long, Device> loadDevices(List<MissionTaskDevice> bindings) {
        if (bindings.isEmpty()) return Collections.emptyMap();
        List<Long> ids = bindings.stream().map(MissionTaskDevice::getDeviceId).distinct().toList();
        Map<Long, Device> result = new HashMap<>();
        deviceRepository.findAllById(ids).forEach(device -> result.put(device.getId(), device));
        return result;
    }

    private Specification<MissionTask> buildSpecification(String keyword, MissionType type, MissionStatus status) {
        return (root, query, criteriaBuilder) -> {
            List<Predicate> predicates = new ArrayList<>();
            predicates.add(criteriaBuilder.isFalse(root.get("deleted")));

            if (StringUtils.hasText(keyword)) {
                String pattern = "%" + keyword.trim().toLowerCase() + "%";
                predicates.add(criteriaBuilder.or(
                        criteriaBuilder.like(criteriaBuilder.lower(root.get("code")), pattern),
                        criteriaBuilder.like(criteriaBuilder.lower(root.get("name")), pattern),
                        criteriaBuilder.like(criteriaBuilder.lower(root.get("targetName")), pattern),
                        criteriaBuilder.like(criteriaBuilder.lower(root.get("missionArea")), pattern)
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
