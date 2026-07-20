package com.uavusv.platform.module.algorithm.service;

import com.fasterxml.jackson.core.JsonProcessingException;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.uavusv.platform.common.exception.BusinessException;
import com.uavusv.platform.common.exception.ErrorCode;
import com.uavusv.platform.module.algorithm.dto.AlgorithmAckRequest;
import com.uavusv.platform.module.algorithm.dto.AlgorithmAssignmentItemResponse;
import com.uavusv.platform.module.algorithm.dto.AlgorithmAssignmentsResponse;
import com.uavusv.platform.module.algorithm.dto.AlgorithmAssignmentsUpdateRequest;
import com.uavusv.platform.module.algorithm.dto.AlgorithmEventRequest;
import com.uavusv.platform.module.algorithm.dto.AlgorithmEventResponse;
import com.uavusv.platform.module.algorithm.dto.AlgorithmRunResponse;
import com.uavusv.platform.module.algorithm.dto.AlgorithmStartRequest;
import com.uavusv.platform.module.algorithm.dto.AlgorithmStatusUpdateRequest;
import com.uavusv.platform.module.algorithm.dto.AlgorithmStopRequest;
import com.uavusv.platform.module.algorithm.entity.AlgorithmAssignment;
import com.uavusv.platform.module.algorithm.entity.AlgorithmAssignmentRole;
import com.uavusv.platform.module.algorithm.entity.AlgorithmEvent;
import com.uavusv.platform.module.algorithm.entity.AlgorithmEventLevel;
import com.uavusv.platform.module.algorithm.entity.AlgorithmRun;
import com.uavusv.platform.module.algorithm.entity.AlgorithmRunStatus;
import com.uavusv.platform.module.algorithm.entity.AlgorithmType;
import com.uavusv.platform.module.algorithm.repository.AlgorithmAssignmentRepository;
import com.uavusv.platform.module.algorithm.repository.AlgorithmEventRepository;
import com.uavusv.platform.module.algorithm.repository.AlgorithmRunRepository;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.scheduling.annotation.Scheduled;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import java.time.LocalDate;
import java.time.LocalDateTime;
import java.time.format.DateTimeFormatter;
import java.util.EnumSet;
import java.util.List;
import java.util.Map;
import java.util.UUID;

@Service
public class AlgorithmService {

    private static final DateTimeFormatter COMMAND_DATE = DateTimeFormatter.BASIC_ISO_DATE;
    private static final EnumSet<AlgorithmRunStatus> ACTIVE_STATUSES = EnumSet.of(
            AlgorithmRunStatus.PENDING,
            AlgorithmRunStatus.RUNNING
    );

    private final AlgorithmRunRepository runRepository;
    private final AlgorithmAssignmentRepository assignmentRepository;
    private final AlgorithmEventRepository eventRepository;
    private final ObjectMapper objectMapper;
    private final long commandTimeoutSeconds;

    public AlgorithmService(
            AlgorithmRunRepository runRepository,
            AlgorithmAssignmentRepository assignmentRepository,
            AlgorithmEventRepository eventRepository,
            ObjectMapper objectMapper,
            @Value("${app.algorithm.command-timeout-seconds:90}") long commandTimeoutSeconds
    ) {
        this.runRepository = runRepository;
        this.assignmentRepository = assignmentRepository;
        this.eventRepository = eventRepository;
        this.objectMapper = objectMapper;
        this.commandTimeoutSeconds = Math.max(commandTimeoutSeconds, 10);
    }

    @Transactional
    public AlgorithmRunResponse start(AlgorithmStartRequest request) {
        String commandId = nextCommandId();
        AlgorithmRun run = runRepository.save(new AlgorithmRun(
                commandId,
                request.algorithmType(),
                request.targetId(),
                toJson(request),
                toJson(request.parameters() == null ? Map.of() : request.parameters())
        ));
        seedMockAssignments(run, request);
        eventRepository.save(new AlgorithmEvent(
                run.getCommandId(),
                run.getAlgorithmType(),
                AlgorithmEventLevel.INFO,
                "INIT",
                "后端已生成算法 commandId；模拟分配结果已写入，等待外部算法 ACK"
        ));
        return AlgorithmRunResponse.from(run);
    }

    @Transactional
    public List<AlgorithmRunResponse> stop(AlgorithmStopRequest request) {
        String reason = request == null || request.reason() == null || request.reason().isBlank()
                ? "平台请求停止算法"
                : request.reason();
        List<AlgorithmRun> runs;
        if (request != null && request.commandId() != null && !request.commandId().isBlank()) {
            runs = List.of(requireRun(request.commandId()));
        } else {
            runs = runRepository.findTop50ByOrderByStartedAtDesc().stream()
                    .filter(run -> ACTIVE_STATUSES.contains(run.getStatus()))
                    .toList();
        }
        for (AlgorithmRun run : runs) {
            run.stop(reason);
            runRepository.save(run);
            eventRepository.save(new AlgorithmEvent(run.getCommandId(), run.getAlgorithmType(),
                    AlgorithmEventLevel.WARN, "STOPPED", reason));
        }
        return runs.stream().map(AlgorithmRunResponse::from).toList();
    }

    @Transactional(readOnly = true)
    public List<AlgorithmRunResponse> status(String commandId) {
        if (commandId != null && !commandId.isBlank()) {
            return List.of(AlgorithmRunResponse.from(requireRun(commandId)));
        }
        return runRepository.findTop50ByOrderByStartedAtDesc()
                .stream()
                .map(AlgorithmRunResponse::from)
                .toList();
    }

    @Transactional(readOnly = true)
    public AlgorithmAssignmentsResponse assignments(String commandId) {
        String resolvedCommandId = resolveCommandId(commandId);
        AlgorithmRun run = requireRun(resolvedCommandId);
        List<AlgorithmAssignment> assignments = assignmentRepository.findByCommandIdOrderByIdAsc(resolvedCommandId);
        return new AlgorithmAssignmentsResponse(
                resolvedCommandId,
                run.getTargetId(),
                assignments.stream().map(AlgorithmAssignmentItemResponse::from).toList()
        );
    }

    @Transactional(readOnly = true)
    public List<AlgorithmEventResponse> events(String commandId) {
        if (commandId != null && !commandId.isBlank()) {
            return eventRepository.findTop100ByCommandIdOrderByOccurredAtDesc(commandId)
                    .stream()
                    .map(AlgorithmEventResponse::from)
                    .toList();
        }
        return eventRepository.findTop100ByOrderByOccurredAtDesc()
                .stream()
                .map(AlgorithmEventResponse::from)
                .toList();
    }

    @Transactional
    public AlgorithmRunResponse acknowledge(String commandId, AlgorithmAckRequest request) {
        AlgorithmRun run = requireRun(commandId);
        run.acknowledge(Boolean.TRUE.equals(request.success()), request.detail(), request.errorCode());
        run = runRepository.save(run);
        eventRepository.save(new AlgorithmEvent(
                run.getCommandId(),
                run.getAlgorithmType(),
                Boolean.TRUE.equals(request.success()) ? AlgorithmEventLevel.INFO : AlgorithmEventLevel.ERROR,
                run.getStage(),
                run.getMessage()
        ));
        return AlgorithmRunResponse.from(run);
    }

    @Transactional
    public AlgorithmRunResponse updateStatus(String commandId, AlgorithmStatusUpdateRequest request) {
        AlgorithmRun run = requireRun(commandId);
        run.updateStatus(request.status(), request.stage(), request.message(), request.errorMessage());
        run = runRepository.save(run);
        eventRepository.save(new AlgorithmEvent(
                run.getCommandId(),
                run.getAlgorithmType(),
                request.status() == AlgorithmRunStatus.FAILED ? AlgorithmEventLevel.ERROR : AlgorithmEventLevel.INFO,
                run.getStage(),
                run.getMessage()
        ));
        return AlgorithmRunResponse.from(run);
    }

    @Transactional
    public AlgorithmAssignmentsResponse updateAssignments(String commandId, AlgorithmAssignmentsUpdateRequest request) {
        AlgorithmRun run = requireRun(commandId);
        assignmentRepository.deleteByCommandId(commandId);
        List<AlgorithmAssignment> saved = request.assignments().stream()
                .map(item -> new AlgorithmAssignment(
                        commandId,
                        request.targetId() == null || request.targetId().isBlank() ? run.getTargetId() : request.targetId(),
                        item.vehicleId(),
                        normalizeVehicleCode(item.vehicleId(), item.vehicleCode()),
                        item.role(),
                        item.x(),
                        item.y(),
                        item.z(),
                        item.heading(),
                        item.detail()
                ))
                .map(assignmentRepository::save)
                .toList();
        run.updateStatus(AlgorithmRunStatus.RUNNING, "ASSIGNMENT_GENERATED", "外部算法分配结果已更新", null);
        runRepository.save(run);
        eventRepository.save(new AlgorithmEvent(run.getCommandId(), run.getAlgorithmType(),
                AlgorithmEventLevel.INFO, "ASSIGNMENT_GENERATED", "收到外部算法分配结果"));
        return new AlgorithmAssignmentsResponse(commandId, run.getTargetId(),
                saved.stream().map(AlgorithmAssignmentItemResponse::from).toList());
    }

    @Transactional
    public AlgorithmEventResponse appendEvent(AlgorithmEventRequest request) {
        AlgorithmRun run = null;
        if (request.commandId() != null && !request.commandId().isBlank()) {
            run = requireRun(request.commandId());
        }
        AlgorithmEvent event = eventRepository.save(new AlgorithmEvent(
                request.commandId(),
                request.algorithmType() != null ? request.algorithmType() : run == null ? null : run.getAlgorithmType(),
                request.level(),
                request.stage(),
                request.message()
        ));
        return AlgorithmEventResponse.from(event);
    }

    @Scheduled(fixedDelay = 5000)
    @Transactional
    public void expirePendingCommands() {
        LocalDateTime cutoff = LocalDateTime.now().minusSeconds(commandTimeoutSeconds);
        runRepository.findAllByStatusInAndStartedAtBefore(List.of(AlgorithmRunStatus.PENDING), cutoff)
                .forEach(run -> {
                    run.timeout("外部算法未在超时时间内 ACK，保持 TIMEOUT，不伪造执行成功");
                    runRepository.save(run);
                    eventRepository.save(new AlgorithmEvent(run.getCommandId(), run.getAlgorithmType(),
                            AlgorithmEventLevel.ERROR, "TIMEOUT", run.getMessage()));
                });
    }

    private void seedMockAssignments(AlgorithmRun run, AlgorithmStartRequest request) {
        String targetId = request.targetId() == null || request.targetId().isBlank() ? "target_01" : request.targetId();
        List<String> uavIds = emptyToDefault(request.uavIds(), List.of("uav_01", "uav_02", "uav_03"));
        List<String> usvIds = emptyToDefault(request.usvIds(), List.of("usv_01", "usv_02", "usv_03"));
        int index = 0;
        for (String vehicleId : uavIds) {
            assignmentRepository.save(new AlgorithmAssignment(
                    run.getCommandId(), targetId, vehicleId, normalizeVehicleCode(vehicleId, null),
                    run.getAlgorithmType() == AlgorithmType.ESCORT_DEFENSE ? AlgorithmAssignmentRole.ESCORT : AlgorithmAssignmentRole.TRACK,
                    105.0 + index * 12.0, 80.0 + index * 6.0, 25.0, 0.35 + index * 0.2,
                    "模拟 UAV 分配结果，等待真实算法覆盖"));
            index++;
        }
        index = 0;
        for (String vehicleId : usvIds) {
            assignmentRepository.save(new AlgorithmAssignment(
                    run.getCommandId(), targetId, vehicleId, normalizeVehicleCode(vehicleId, null),
                    run.getAlgorithmType() == AlgorithmType.ESCORT_DEFENSE ? AlgorithmAssignmentRole.DEFEND : AlgorithmAssignmentRole.ENCIRCLE,
                    115.0 + index * 14.0, 68.0 - index * 5.0, 0.0, 0.65 + index * 0.15,
                    "模拟 USV 分配结果，等待真实算法覆盖"));
            index++;
        }
    }

    private AlgorithmRun requireRun(String commandId) {
        return runRepository.findByCommandId(commandId)
                .orElseThrow(() -> new BusinessException(ErrorCode.NOT_FOUND, "算法指令不存在"));
    }

    private String resolveCommandId(String commandId) {
        if (commandId != null && !commandId.isBlank()) {
            requireRun(commandId);
            return commandId;
        }
        return runRepository.findTop50ByOrderByStartedAtDesc()
                .stream()
                .findFirst()
                .map(AlgorithmRun::getCommandId)
                .orElseThrow(() -> new BusinessException(ErrorCode.NOT_FOUND, "暂无算法指令"));
    }

    private String nextCommandId() {
        return "alg-" + LocalDate.now().format(COMMAND_DATE) + "-" + UUID.randomUUID().toString().substring(0, 8);
    }

    private String normalizeVehicleCode(String vehicleId, String vehicleCode) {
        if (vehicleCode != null && !vehicleCode.isBlank()) return vehicleCode;
        return vehicleId == null ? "" : vehicleId.replace('_', '-');
    }

    private <T> List<T> emptyToDefault(List<T> values, List<T> defaults) {
        return values == null || values.isEmpty() ? defaults : values;
    }

    private String toJson(Object value) {
        try {
            return objectMapper.writeValueAsString(value);
        } catch (JsonProcessingException exception) {
            throw new IllegalArgumentException("算法请求序列化失败", exception);
        }
    }
}
