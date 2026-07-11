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
import com.uavusv.platform.module.mission.dto.response.MissionActionResponse;
import com.uavusv.platform.module.mission.dto.response.MissionDeviceResponse;
import com.uavusv.platform.module.mission.dto.response.MissionEventResponse;
import com.uavusv.platform.module.mission.dto.response.MissionParameterResponse;
import com.uavusv.platform.module.mission.dto.response.MissionResponse;
import com.uavusv.platform.module.mission.entity.MissionEvent;
import com.uavusv.platform.module.mission.entity.MissionEventLevel;
import com.uavusv.platform.module.mission.entity.MissionEventType;
import com.uavusv.platform.module.mission.entity.MissionRun;
import com.uavusv.platform.module.mission.entity.MissionRunStatus;
import com.uavusv.platform.module.mission.entity.MissionStage;
import com.uavusv.platform.module.mission.entity.MissionStatus;
import com.uavusv.platform.module.mission.entity.MissionTask;
import com.uavusv.platform.module.mission.entity.MissionTaskDevice;
import com.uavusv.platform.module.mission.entity.MissionTaskParameter;
import com.uavusv.platform.module.mission.entity.MissionType;
import com.uavusv.platform.module.mission.repository.MissionEventRepository;
import com.uavusv.platform.module.mission.repository.MissionRunRepository;
import com.uavusv.platform.module.mission.repository.MissionTaskDeviceRepository;
import com.uavusv.platform.module.mission.repository.MissionTaskParameterRepository;
import com.uavusv.platform.module.mission.repository.MissionTaskRepository;
import com.uavusv.platform.module.mission.service.MissionService;
import com.uavusv.platform.module.runtimecontrol.entity.SimulationStatus;
import com.uavusv.platform.module.runtimecontrol.dto.RuntimeCommandRequest;
import com.uavusv.platform.module.runtimecontrol.dto.RuntimeCommandResponse;
import com.uavusv.platform.module.runtimecontrol.entity.CommandType;
import com.uavusv.platform.module.runtimecontrol.repository.SimulationSessionRepository;
import com.uavusv.platform.module.runtimecontrol.service.RuntimeControlService;
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
import java.util.EnumSet;
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
    private final MissionRunRepository missionRunRepository;
    private final DeviceRepository deviceRepository;
    private final SimulationSessionRepository simulationSessionRepository;
    private final RuntimeControlService runtimeControlService;

    public MissionServiceImpl(
            MissionTaskRepository missionTaskRepository,
            MissionTaskDeviceRepository missionTaskDeviceRepository,
            MissionTaskParameterRepository missionTaskParameterRepository,
            MissionEventRepository missionEventRepository,
            MissionRunRepository missionRunRepository,
            DeviceRepository deviceRepository,
            SimulationSessionRepository simulationSessionRepository,
            RuntimeControlService runtimeControlService
    ) {
        this.missionTaskRepository = missionTaskRepository;
        this.missionTaskDeviceRepository = missionTaskDeviceRepository;
        this.missionTaskParameterRepository = missionTaskParameterRepository;
        this.missionEventRepository = missionEventRepository;
        this.missionRunRepository = missionRunRepository;
        this.deviceRepository = deviceRepository;
        this.simulationSessionRepository = simulationSessionRepository;
        this.runtimeControlService = runtimeControlService;
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
        ensureConfigurableStatus(request.status());
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
        ensureStatus(mission, "编辑任务", MissionStatus.DRAFT, MissionStatus.READY,
                MissionStatus.COMPLETED, MissionStatus.FAILED, MissionStatus.CANCELLED);
        ensureConfigurableStatus(request.status());
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
        ensureStatus(mission, "删除任务", MissionStatus.DRAFT, MissionStatus.READY,
                MissionStatus.COMPLETED, MissionStatus.FAILED, MissionStatus.CANCELLED);
        mission.softDelete();
        missionEventRepository.save(new MissionEvent(
                mission.getId(),
                MissionEventType.STATUS,
                "任务已隐藏",
                "任务从任务控制列表中隐藏，历史事件和编组记录保留。",
                "platform"
        ));
    }

    @Override
    @Transactional
    public MissionActionResponse markReady(Long id, String operator) {
        MissionTask mission = findMission(id);
        ensureStatus(mission, "进入待执行", MissionStatus.DRAFT, MissionStatus.COMPLETED,
                MissionStatus.FAILED, MissionStatus.CANCELLED);
        mission.prepareForRun();
        recordStatusEvent(mission, "任务进入待执行", "任务配置已确认，可以进入协同围捕启动链路。", operator);
        return new MissionActionResponse(buildDetail(mission), null);
    }

    @Override
    @Transactional
    public MissionActionResponse startMission(Long id, String operator) {
        MissionTask mission = findMission(id);
        ensureStatus(mission, "启动任务", MissionStatus.READY);
        ensureNoOpenRun(mission.getId());
        MissionStage stage = nextRunningStage(mission.getStage());
        Long sessionId = currentSimulationSessionId();
        MissionRun run = missionRunRepository.save(new MissionRun(
                mission.getId(),
                sessionId,
                missionRunRepository.findMaxRunNo(mission.getId()) + 1,
                stage,
                operator
        ));
        recordStatusEvent(mission, run, "任务启动请求已提交", "已创建第 " + run.getRunNo() + " 次执行批次，等待控制指令确认。", operator);
        RuntimeCommandResponse command = issueMissionCommand(run, CommandType.START_MISSION, operator, "启动任务：" + mission.getName());
        return new MissionActionResponse(buildDetail(mission), command);
    }

    @Override
    @Transactional
    public MissionActionResponse pauseMission(Long id, String operator) {
        MissionTask mission = findMission(id);
        ensureStatus(mission, "暂停任务", MissionStatus.RUNNING);
        MissionRun run = findActiveRun(mission.getId(), MissionRunStatus.RUNNING);
        recordStatusEvent(mission, run, "暂停请求已提交", "等待控制指令确认，确认前任务保持运行状态。", operator);
        RuntimeCommandResponse command = issueMissionCommand(run, CommandType.PAUSE_MISSION, operator, "暂停任务：" + mission.getName());
        return new MissionActionResponse(buildDetail(mission), command);
    }

    @Override
    @Transactional
    public MissionActionResponse resumeMission(Long id, String operator) {
        MissionTask mission = findMission(id);
        ensureStatus(mission, "恢复任务", MissionStatus.PAUSED);
        MissionRun run = findActiveRun(mission.getId(), MissionRunStatus.PAUSED);
        recordStatusEvent(mission, run, "恢复请求已提交", "等待控制指令确认，确认前任务保持暂停状态。", operator);
        RuntimeCommandResponse command = issueMissionCommand(run, CommandType.RESUME_MISSION, operator, "恢复任务：" + mission.getName());
        return new MissionActionResponse(buildDetail(mission), command);
    }

    @Override
    @Transactional
    public MissionActionResponse completeMission(Long id, String operator) {
        MissionTask mission = findMission(id);
        ensureStatus(mission, "完成任务", MissionStatus.RUNNING, MissionStatus.PAUSED);
        MissionRun run = findActiveRun(mission.getId(), MissionRunStatus.RUNNING, MissionRunStatus.PAUSED);
        recordStatusEvent(mission, run, "完成请求已提交", "等待控制指令确认后进入评估阶段。", operator);
        RuntimeCommandResponse command = issueMissionCommand(run, CommandType.COMPLETE_MISSION, operator, "完成任务：" + mission.getName());
        return new MissionActionResponse(buildDetail(mission), command);
    }

    @Override
    @Transactional
    public MissionActionResponse failMission(Long id, String operator) {
        MissionTask mission = findMission(id);
        ensureStatus(mission, "标记异常", MissionStatus.RUNNING, MissionStatus.PAUSED);
        MissionRun run = findActiveRun(mission.getId(), MissionRunStatus.RUNNING, MissionRunStatus.PAUSED);
        recordStatusEvent(mission, run, MissionEventLevel.WARNING, "异常终止请求已提交", "等待控制指令确认后标记任务异常。", operator);
        RuntimeCommandResponse command = issueMissionCommand(run, CommandType.FAIL_MISSION, operator, "异常终止任务：" + mission.getName());
        return new MissionActionResponse(buildDetail(mission), command);
    }

    @Override
    @Transactional
    public MissionActionResponse cancelMission(Long id, String operator) {
        MissionTask mission = findMission(id);
        ensureNotTerminal(mission, "取消任务");
        MissionRun run = findOptionalActiveRun(mission.getId());
        if (run == null) {
            mission.updateStatus(MissionStatus.CANCELLED, MissionStage.EVALUATION);
            recordStatusEvent(mission, "任务已取消", "任务尚未开始，无需向外部组件下发停止指令。", operator);
            return new MissionActionResponse(buildDetail(mission), null);
        }
        recordStatusEvent(mission, run, "取消请求已提交", "等待控制指令确认后取消当前任务。", operator);
        RuntimeCommandResponse command = issueMissionCommand(run, CommandType.CANCEL_MISSION, operator, "取消任务：" + mission.getName());
        return new MissionActionResponse(buildDetail(mission), command);
    }

    private void applyMissionFields(MissionTask mission, MissionSaveRequest request) {
        mission.update(
                request.code(),
                request.name(),
                request.type(),
                request.status(),
                MissionStage.PREPARE,
                request.priority() == null ? 3 : request.priority(),
                request.targetName(),
                request.targetBehavior(),
                request.missionArea(),
                request.plannedStartAt(),
                request.plannedEndAt(),
                request.description()
        );
    }

    private void ensureConfigurableStatus(MissionStatus status) {
        if (status != MissionStatus.DRAFT && status != MissionStatus.READY) {
            throw new BusinessException(ErrorCode.BAD_REQUEST, "新建或编辑任务时，状态只能是草稿或待执行");
        }
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

    private void ensureStatus(MissionTask mission, String action, MissionStatus... allowedStatuses) {
        for (MissionStatus allowedStatus : allowedStatuses) {
            if (mission.getStatus() == allowedStatus) {
                return;
            }
        }
        throw new BusinessException(
                ErrorCode.BAD_REQUEST,
                action + "失败：当前任务状态为 " + mission.getStatus()
        );
    }

    private void ensureNotTerminal(MissionTask mission, String action) {
        if (mission.getStatus() == MissionStatus.COMPLETED
                || mission.getStatus() == MissionStatus.CANCELLED
                || mission.getStatus() == MissionStatus.FAILED) {
            throw new BusinessException(
                    ErrorCode.BAD_REQUEST,
                    action + "失败：任务已结束，不能继续变更状态"
            );
        }
    }

    private MissionStage nextRunningStage(MissionStage currentStage) {
        if (currentStage == MissionStage.PREPARE) {
            return MissionStage.TARGET_DETECTED;
        }
        if (currentStage == MissionStage.EVALUATION) {
            return MissionStage.TRACKING;
        }
        return currentStage;
    }

    private void recordStatusEvent(MissionTask mission, String title, String message, String operator) {
        recordStatusEvent(mission, null, MissionEventLevel.INFO, title, message, operator);
    }

    private void recordStatusEvent(MissionTask mission, MissionRun run, String title, String message, String operator) {
        recordStatusEvent(mission, run, MissionEventLevel.INFO, title, message, operator);
    }

    private void recordStatusEvent(
            MissionTask mission,
            MissionRun run,
            MissionEventLevel level,
            String title,
            String message,
            String operator
    ) {
        missionEventRepository.save(new MissionEvent(
                mission.getId(),
                run == null ? null : run.getId(),
                MissionEventType.STATUS,
                mission.getStage(),
                level,
                title,
                message,
                StringUtils.hasText(operator) ? operator : "platform"
        ));
    }

    private MissionRun findActiveRun(Long missionId, MissionRunStatus... statuses) {
        return missionRunRepository.findFirstByMissionIdAndStatusInOrderByStartedAtDesc(
                        missionId,
                        EnumSet.copyOf(List.of(statuses))
                )
                .orElseThrow(() -> new BusinessException(ErrorCode.BAD_REQUEST, "任务执行记录不存在或状态不匹配"));
    }

    private MissionRun findOptionalActiveRun(Long missionId) {
        return missionRunRepository.findFirstByMissionIdAndStatusInOrderByStartedAtDesc(
                        missionId,
                        EnumSet.of(MissionRunStatus.PENDING, MissionRunStatus.RUNNING, MissionRunStatus.PAUSED)
                )
                .orElse(null);
    }

    private void ensureNoOpenRun(Long missionId) {
        if (findOptionalActiveRun(missionId) != null) {
            throw new BusinessException(ErrorCode.BAD_REQUEST, "该任务已有待确认或运行中的执行批次");
        }
    }

    private RuntimeCommandResponse issueMissionCommand(
            MissionRun run,
            CommandType commandType,
            String operator,
            String detail
    ) {
        return runtimeControlService.issueCommand(
                new RuntimeCommandRequest(commandType, run.getId(), null, null, detail),
                operator
        );
    }

    private Long currentSimulationSessionId() {
        return simulationSessionRepository.findFirstByStatusInOrderByCreatedAtDesc(EnumSet.of(
                        SimulationStatus.STARTING,
                        SimulationStatus.RUNNING,
                        SimulationStatus.PARTIAL
                ))
                .map(session -> session.getId())
                .orElse(null);
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
        List<com.uavusv.platform.module.mission.dto.response.MissionRunResponse> runs = missionRunRepository
                .findTop10ByMissionIdOrderByStartedAtDesc(mission.getId())
                .stream()
                .map(com.uavusv.platform.module.mission.dto.response.MissionRunResponse::from)
                .toList();
        return new MissionDetailResponse(
                MissionResponse.from(mission, devices.size()),
                devices,
                parameters,
                events,
                runs.isEmpty() ? null : runs.get(0),
                runs
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
