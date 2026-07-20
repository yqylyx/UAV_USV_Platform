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
import com.uavusv.platform.module.algorithm.integration.AlgorithmPythonClient;
import com.uavusv.platform.module.algorithm.repository.AlgorithmAssignmentRepository;
import com.uavusv.platform.module.algorithm.repository.AlgorithmEventRepository;
import com.uavusv.platform.module.algorithm.repository.AlgorithmRunRepository;
import com.uavusv.platform.module.device.entity.Device;
import com.uavusv.platform.module.device.entity.DeviceStatus;
import com.uavusv.platform.module.device.entity.DeviceType;
import com.uavusv.platform.module.device.repository.DeviceRepository;
import com.uavusv.platform.module.monitoring.entity.RuntimeDeviceStatus;
import com.uavusv.platform.module.monitoring.repository.RuntimeDeviceStatusRepository;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.scheduling.annotation.Scheduled;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import java.time.Clock;
import java.time.LocalDate;
import java.time.LocalDateTime;
import java.time.format.DateTimeFormatter;
import java.util.ArrayList;
import java.util.EnumSet;
import java.util.LinkedHashMap;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Map;
import java.util.Set;
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
    private final AlgorithmPythonClient pythonClient;
    private final DeviceRepository deviceRepository;
    private final RuntimeDeviceStatusRepository runtimeStatusRepository;
    private final ObjectMapper objectMapper;
    private final long commandTimeoutSeconds;
    private final long positionMaxAgeSeconds;
    private final Clock clock;

    @Autowired
    public AlgorithmService(
            AlgorithmRunRepository runRepository,
            AlgorithmAssignmentRepository assignmentRepository,
            AlgorithmEventRepository eventRepository,
            AlgorithmPythonClient pythonClient,
            DeviceRepository deviceRepository,
            RuntimeDeviceStatusRepository runtimeStatusRepository,
            ObjectMapper objectMapper,
            @Value("${app.algorithm.command-timeout-seconds:90}") long commandTimeoutSeconds,
            @Value("${app.algorithm.position-max-age-seconds:10}") long positionMaxAgeSeconds
    ) {
        this(runRepository, assignmentRepository, eventRepository, pythonClient, deviceRepository,
                runtimeStatusRepository, objectMapper, commandTimeoutSeconds, positionMaxAgeSeconds,
                Clock.systemDefaultZone());
    }

    AlgorithmService(
            AlgorithmRunRepository runRepository,
            AlgorithmAssignmentRepository assignmentRepository,
            AlgorithmEventRepository eventRepository,
            AlgorithmPythonClient pythonClient,
            DeviceRepository deviceRepository,
            RuntimeDeviceStatusRepository runtimeStatusRepository,
            ObjectMapper objectMapper,
            long commandTimeoutSeconds,
            long positionMaxAgeSeconds,
            Clock clock
    ) {
        this.runRepository = runRepository;
        this.assignmentRepository = assignmentRepository;
        this.eventRepository = eventRepository;
        this.pythonClient = pythonClient;
        this.deviceRepository = deviceRepository;
        this.runtimeStatusRepository = runtimeStatusRepository;
        this.objectMapper = objectMapper;
        this.commandTimeoutSeconds = Math.max(commandTimeoutSeconds, 10);
        this.positionMaxAgeSeconds = Math.max(positionMaxAgeSeconds, 1);
        this.clock = clock;
    }

    public AlgorithmRunResponse start(AlgorithmStartRequest request) {
        String commandId = nextCommandId();
        AlgorithmRun run = runRepository.save(new AlgorithmRun(
                commandId,
                request.algorithmType(),
                request.targetId(),
                toJson(request),
                toJson(request.parameters() == null ? Map.of() : request.parameters())
        ));
        try {
            LocalDateTime now = LocalDateTime.now(clock);
            ResolvedVehicles vehicles = resolveVehicles(request, now);
            AlgorithmPythonClient.AlgorithmResult result = pythonClient.runOnce(buildPythonRequest(commandId, request, vehicles));
            completeFromPythonResult(run, request, vehicles.vehicleIds(), result);
            return AlgorithmRunResponse.from(runRepository.save(run));
        } catch (AlgorithmPythonClient.AlgorithmPythonClientException exception) {
            String message = "Python run-once 调用失败: " + exception.getMessage();
            failRun(run, message);
            throw new BusinessException(ErrorCode.BAD_REQUEST, message);
        } catch (BusinessException exception) {
            failRun(run, exception.getMessage());
            throw exception;
        } catch (RuntimeException exception) {
            String message = "算法 run-once 执行失败: " + exception.getMessage();
            failRun(run, message);
            throw new BusinessException(ErrorCode.BAD_REQUEST, message);
        }
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
            if (!ACTIVE_STATUSES.contains(run.getStatus())) {
                eventRepository.save(new AlgorithmEvent(run.getCommandId(), run.getAlgorithmType(),
                        AlgorithmEventLevel.WARN, run.getStage(),
                        "同步 run-once 已结束，未执行远程停止；本地状态保持 " + run.getStatus()));
                continue;
            }
            String localReason = "本地停止请求已记录；同步 run-once 无远程中断能力: " + reason;
            run.stop(localReason);
            runRepository.save(run);
            eventRepository.save(new AlgorithmEvent(run.getCommandId(), run.getAlgorithmType(),
                    AlgorithmEventLevel.WARN, "STOPPED", localReason));
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

    private ResolvedVehicles resolveVehicles(AlgorithmStartRequest request, LocalDateTime now) {
        if (request.resolvedPositionSource() == AlgorithmStartRequest.PositionSource.MANUAL) {
            return resolveManualVehicles(request);
        }
        Set<String> vehicleIds = new LinkedHashSet<>();
        Set<String> deviceCodes = new LinkedHashSet<>();
        List<AlgorithmPythonClient.Vehicle> uavs = resolveVehicles(request.uavIds(), DeviceType.UAV, "UAV", now, vehicleIds, deviceCodes);
        List<AlgorithmPythonClient.Vehicle> usvs = resolveVehicles(request.usvIds(), DeviceType.USV, "USV", now, vehicleIds, deviceCodes);
        return new ResolvedVehicles(uavs, usvs, vehicleIds);
    }

    private ResolvedVehicles resolveManualVehicles(AlgorithmStartRequest request) {
        Map<String, AlgorithmStartRequest.ManualVehiclePositionRequest> manualPositions = manualPositionsByVehicleCode(request);
        Set<String> selectedVehicleCodes = new LinkedHashSet<>();
        Set<String> vehicleIds = new LinkedHashSet<>();
        Set<String> deviceCodes = new LinkedHashSet<>();
        List<AlgorithmPythonClient.Vehicle> uavs = resolveManualVehicles(
                request.uavIds(), DeviceType.UAV, "UAV", manualPositions, selectedVehicleCodes, vehicleIds, deviceCodes);
        List<AlgorithmPythonClient.Vehicle> usvs = resolveManualVehicles(
                request.usvIds(), DeviceType.USV, "USV", manualPositions, selectedVehicleCodes, vehicleIds, deviceCodes);
        for (AlgorithmStartRequest.ManualVehiclePositionRequest item : request.manualVehiclePositions()) {
            String vehicleCode = normalizeVehicleCode(item.vehicleId(), null);
            if (!selectedVehicleCodes.contains(vehicleCode)) {
                throw new BusinessException(ErrorCode.BAD_REQUEST, "手动车辆位姿包含未选择设备: " + item.vehicleId());
            }
        }
        return new ResolvedVehicles(uavs, usvs, vehicleIds);
    }

    private Map<String, AlgorithmStartRequest.ManualVehiclePositionRequest> manualPositionsByVehicleCode(
            AlgorithmStartRequest request
    ) {
        if (request.manualVehiclePositions() == null || request.manualVehiclePositions().isEmpty()) {
            throw new BusinessException(ErrorCode.BAD_REQUEST, "MANUAL 模式必须提供手动车辆位姿");
        }
        Map<String, AlgorithmStartRequest.ManualVehiclePositionRequest> positions = new LinkedHashMap<>();
        for (AlgorithmStartRequest.ManualVehiclePositionRequest item : request.manualVehiclePositions()) {
            if (item.vehicleId() == null || item.vehicleId().isBlank()) {
                throw new BusinessException(ErrorCode.BAD_REQUEST, "手动车辆位姿 vehicleId 不能为空");
            }
            if (item.position() == null) {
                throw new BusinessException(ErrorCode.BAD_REQUEST, "手动车辆位姿缺少坐标: " + item.vehicleId());
            }
            String vehicleCode = normalizeVehicleCode(item.vehicleId(), null);
            if (positions.putIfAbsent(vehicleCode, item) != null) {
                throw new BusinessException(ErrorCode.BAD_REQUEST, "手动车辆位姿重复: " + item.vehicleId());
            }
        }
        return positions;
    }

    private List<AlgorithmPythonClient.Vehicle> resolveManualVehicles(
            List<String> requestedVehicleIds,
            DeviceType expectedType,
            String label,
            Map<String, AlgorithmStartRequest.ManualVehiclePositionRequest> manualPositions,
            Set<String> selectedVehicleCodes,
            Set<String> vehicleIds,
            Set<String> deviceCodes
    ) {
        if (requestedVehicleIds == null || requestedVehicleIds.isEmpty()) {
            return List.of();
        }
        List<AlgorithmPythonClient.Vehicle> vehicles = new ArrayList<>();
        for (String vehicleId : requestedVehicleIds) {
            if (vehicleId == null || vehicleId.isBlank()) {
                throw new BusinessException(ErrorCode.BAD_REQUEST, label + " 设备标识不能为空");
            }
            String lookupCode = normalizeVehicleCode(vehicleId, null);
            if (!selectedVehicleCodes.add(lookupCode)) {
                throw new BusinessException(ErrorCode.BAD_REQUEST, "所选设备重复: " + vehicleId);
            }
            if (!vehicleIds.add(vehicleId)) {
                throw new BusinessException(ErrorCode.BAD_REQUEST, "所选设备重复: " + vehicleId);
            }
            AlgorithmStartRequest.ManualVehiclePositionRequest manualPosition = manualPositions.get(lookupCode);
            if (manualPosition == null) {
                throw new BusinessException(ErrorCode.BAD_REQUEST, "缺少手动车辆位姿: " + vehicleId);
            }
            Device device = deviceRepository.findByCode(lookupCode)
                    .orElseThrow(() -> new BusinessException(ErrorCode.BAD_REQUEST, "设备不存在: " + lookupCode));
            if (device.getType() != expectedType) {
                throw new BusinessException(ErrorCode.BAD_REQUEST, "设备类型不匹配: " + device.getCode());
            }
            if (!deviceCodes.add(device.getCode())) {
                throw new BusinessException(ErrorCode.BAD_REQUEST, "设备重复: " + device.getCode());
            }
            vehicles.add(new AlgorithmPythonClient.Vehicle(
                    vehicleId,
                    device.getCode(),
                    toPythonPosition(manualPosition.position())
            ));
        }
        return vehicles;
    }

    private List<AlgorithmPythonClient.Vehicle> resolveVehicles(
            List<String> requestedVehicleIds,
            DeviceType expectedType,
            String label,
            LocalDateTime now,
            Set<String> vehicleIds,
            Set<String> deviceCodes
    ) {
        if (requestedVehicleIds == null || requestedVehicleIds.isEmpty()) {
            return List.of();
        }
        List<AlgorithmPythonClient.Vehicle> vehicles = new ArrayList<>();
        for (String vehicleId : requestedVehicleIds) {
            if (vehicleId == null || vehicleId.isBlank()) {
                throw new BusinessException(ErrorCode.BAD_REQUEST, label + " 设备标识不能为空");
            }
            if (!vehicleIds.add(vehicleId)) {
                throw new BusinessException(ErrorCode.BAD_REQUEST, "设备重复: " + vehicleId);
            }
            String lookupCode = normalizeVehicleCode(vehicleId, null);
            Device device = deviceRepository.findByCode(lookupCode)
                    .orElseThrow(() -> new BusinessException(ErrorCode.BAD_REQUEST, "设备不存在: " + lookupCode));
            if (device.getType() != expectedType) {
                throw new BusinessException(ErrorCode.BAD_REQUEST, "设备类型不匹配: " + device.getCode());
            }
            if (!deviceCodes.add(device.getCode())) {
                throw new BusinessException(ErrorCode.BAD_REQUEST, "设备重复: " + device.getCode());
            }
            RuntimeDeviceStatus status = runtimeStatusRepository.findByDeviceId(device.getId())
                    .orElseThrow(() -> new BusinessException(ErrorCode.BAD_REQUEST, "设备缺少运行状态: " + device.getCode()));
            vehicles.add(new AlgorithmPythonClient.Vehicle(
                    vehicleId,
                    device.getCode(),
                    toPythonPosition(device.getCode(), status, now)
            ));
        }
        return vehicles;
    }

    private AlgorithmPythonClient.Position toPythonPosition(String deviceCode, RuntimeDeviceStatus status, LocalDateTime now) {
        if (status.getStatus() != DeviceStatus.ONLINE) {
            throw new BusinessException(ErrorCode.BAD_REQUEST, "设备当前离线: " + deviceCode);
        }
        if (!isFinite(status.getPositionX()) || !isFinite(status.getPositionY()) || !isFinite(status.getPositionZ())) {
            throw new BusinessException(ErrorCode.BAD_REQUEST, "设备坐标无效: " + deviceCode);
        }
        if (!isFinite(status.getOrientationX()) || !isFinite(status.getOrientationY())
                || !isFinite(status.getOrientationZ()) || !isFinite(status.getOrientationW())) {
            throw new BusinessException(ErrorCode.BAD_REQUEST, "设备姿态四元数无效: " + deviceCode);
        }
        if (status.getLastMessageAt() == null) {
            throw new BusinessException(ErrorCode.BAD_REQUEST, "设备实时数据缺少更新时间: " + deviceCode);
        }
        if (status.getLastMessageAt().isBefore(now.minusSeconds(positionMaxAgeSeconds))) {
            throw new BusinessException(ErrorCode.BAD_REQUEST, "设备实时坐标已过期: " + deviceCode);
        }
        return new AlgorithmPythonClient.Position(
                status.getPositionX(),
                status.getPositionY(),
                status.getPositionZ(),
                headingFromQuaternion(deviceCode, status)
        );
    }

    double headingFromQuaternion(String deviceCode, RuntimeDeviceStatus status) {
        double x = status.getOrientationX();
        double y = status.getOrientationY();
        double z = status.getOrientationZ();
        double w = status.getOrientationW();
        double norm = Math.sqrt(x * x + y * y + z * z + w * w);
        if (!Double.isFinite(norm) || norm == 0.0) {
            throw new BusinessException(ErrorCode.BAD_REQUEST, "设备姿态四元数无效: " + deviceCode);
        }
        x /= norm;
        y /= norm;
        z /= norm;
        w /= norm;
        return Math.atan2(2 * (w * z + x * y), 1 - 2 * (y * y + z * z));
    }

    private AlgorithmPythonClient.RunOnceRequest buildPythonRequest(
            String commandId,
            AlgorithmStartRequest request,
            ResolvedVehicles vehicles
    ) {
        return new AlgorithmPythonClient.RunOnceRequest(
                commandId,
                request.algorithmType().name(),
                request.targetId(),
                toPythonPosition(request.targetPosition()),
                threatTargetId(request.parameters()),
                request.algorithmType() == AlgorithmType.ESCORT_DEFENSE ? toPythonPosition(request.threatPosition()) : null,
                vehicles.uavs(),
                vehicles.usvs(),
                request.parameters() == null ? Map.of() : request.parameters()
        );
    }

    private AlgorithmPythonClient.Position toPythonPosition(AlgorithmStartRequest.PositionRequest position) {
        if (position == null) {
            return null;
        }
        if (!isFinite(position.x()) || !isFinite(position.y()) || !isFinite(position.z()) || !isFinite(position.heading())) {
            throw new BusinessException(ErrorCode.BAD_REQUEST, "请求坐标必须是有限数字");
        }
        return new AlgorithmPythonClient.Position(position.x(), position.y(), position.z(), position.heading());
    }

    private String threatTargetId(Map<String, Object> parameters) {
        if (parameters == null) {
            return null;
        }
        Object value = parameters.get("threatTargetId");
        return value instanceof String text && !text.isBlank() ? text : null;
    }

    private void completeFromPythonResult(
            AlgorithmRun run,
            AlgorithmStartRequest request,
            Set<String> requestedVehicleIds,
            AlgorithmPythonClient.AlgorithmResult result
    ) {
        if (result == null) {
            throw new BusinessException(ErrorCode.BAD_REQUEST, "Python run-once 返回空结果");
        }
        if (!run.getCommandId().equals(result.commandId())) {
            throw new BusinessException(ErrorCode.BAD_REQUEST, "Python run-once commandId 不一致");
        }
        if (isPythonFailedStatus(result.status())) {
            throw new BusinessException(ErrorCode.BAD_REQUEST, pythonFailureMessage(result));
        }
        List<AlgorithmAssignment> assignments = validateAssignments(run, request, requestedVehicleIds, result.assignments());
        List<AlgorithmEvent> events = toEvents(run, result.events());
        assignments.forEach(assignmentRepository::save);
        events.forEach(eventRepository::save);
        run.updateStatus(
                AlgorithmRunStatus.COMPLETED,
                result.stage() == null || result.stage().isBlank() ? "COMPLETED" : result.stage(),
                runMessage(request, result),
                null
        );
    }

    private String runMessage(AlgorithmStartRequest request, AlgorithmPythonClient.AlgorithmResult result) {
        String message = result.message() == null || result.message().isBlank()
                ? "Python run-once 执行完成"
                : result.message();
        if (request.resolvedPositionSource() != AlgorithmStartRequest.PositionSource.MANUAL) {
            return message;
        }
        return "手动初始位姿实验：车辆初始位置来自请求输入，算法结果来自Python服务；" + message;
    }

    private List<AlgorithmAssignment> validateAssignments(
            AlgorithmRun run,
            AlgorithmStartRequest request,
            Set<String> requestedVehicleIds,
            List<AlgorithmPythonClient.Assignment> pythonAssignments
    ) {
        if (pythonAssignments == null || pythonAssignments.isEmpty()) {
            return List.of();
        }
        Set<String> assignedVehicleIds = new LinkedHashSet<>();
        List<AlgorithmAssignment> assignments = new ArrayList<>();
        for (AlgorithmPythonClient.Assignment item : pythonAssignments) {
            if (item.vehicleId() == null || !requestedVehicleIds.contains(item.vehicleId())) {
                throw new BusinessException(ErrorCode.BAD_REQUEST, "Python 返回未知 vehicleId: " + item.vehicleId());
            }
            if (!assignedVehicleIds.add(item.vehicleId())) {
                throw new BusinessException(ErrorCode.BAD_REQUEST, "Python 返回重复 vehicleId: " + item.vehicleId());
            }
            AlgorithmAssignmentRole role = parseAssignmentRole(item.role());
            assignments.add(new AlgorithmAssignment(
                    run.getCommandId(),
                    resultTargetId(request, item),
                    item.vehicleId(),
                    item.vehicleCode(),
                    role,
                    item.x(),
                    item.y(),
                    item.z(),
                    item.heading(),
                    item.detail() == null || item.detail().isNull() ? null : toJson(item.detail())
            ));
        }
        return assignments;
    }

    private String resultTargetId(AlgorithmStartRequest request, AlgorithmPythonClient.Assignment item) {
        return request.targetId();
    }

    private List<AlgorithmEvent> toEvents(AlgorithmRun run, List<AlgorithmPythonClient.AlgorithmEvent> pythonEvents) {
        if (pythonEvents == null || pythonEvents.isEmpty()) {
            return List.of();
        }
        return pythonEvents.stream()
                .map(event -> new AlgorithmEvent(
                        run.getCommandId(),
                        run.getAlgorithmType(),
                        parseEventLevel(event.level()),
                        event.stage(),
                        event.message() == null || event.message().isBlank() ? "Python run-once event" : event.message()
                ))
                .toList();
    }

    private AlgorithmAssignmentRole parseAssignmentRole(String role) {
        try {
            return AlgorithmAssignmentRole.valueOf(role);
        } catch (RuntimeException exception) {
            throw new BusinessException(ErrorCode.BAD_REQUEST, "Python 返回未知 role: " + role);
        }
    }

    private AlgorithmEventLevel parseEventLevel(String level) {
        if (level == null || level.isBlank()) {
            return AlgorithmEventLevel.INFO;
        }
        try {
            return AlgorithmEventLevel.valueOf(level);
        } catch (IllegalArgumentException exception) {
            return AlgorithmEventLevel.INFO;
        }
    }

    private boolean isPythonFailedStatus(String status) {
        return "FAILED".equals(status) || "INVALID_REQUEST".equals(status) || "UNSUPPORTED_CONFIGURATION".equals(status);
    }

    private String pythonFailureMessage(AlgorithmPythonClient.AlgorithmResult result) {
        if (result.error() != null && !result.error().isBlank()) {
            return result.error();
        }
        if (result.message() != null && !result.message().isBlank()) {
            return result.message();
        }
        return "Python run-once 返回失败状态: " + result.status();
    }

    private void failRun(AlgorithmRun run, String message) {
        run.updateStatus(AlgorithmRunStatus.FAILED, "FAILED", message, message);
        runRepository.save(run);
        eventRepository.save(new AlgorithmEvent(run.getCommandId(), run.getAlgorithmType(),
                AlgorithmEventLevel.ERROR, "FAILED", message));
    }

    private boolean isFinite(Double value) {
        return value != null && Double.isFinite(value);
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

    private String toJson(Object value) {
        try {
            return objectMapper.writeValueAsString(value);
        } catch (JsonProcessingException exception) {
            throw new IllegalArgumentException("算法请求序列化失败", exception);
        }
    }

    private record ResolvedVehicles(
            List<AlgorithmPythonClient.Vehicle> uavs,
            List<AlgorithmPythonClient.Vehicle> usvs,
            Set<String> vehicleIds
    ) {
    }
}
