package com.uavusv.platform.module.algorithm.service;

import com.fasterxml.jackson.databind.ObjectMapper;
import com.uavusv.platform.common.entity.BaseEntity;
import com.uavusv.platform.common.exception.BusinessException;
import com.uavusv.platform.module.algorithm.dto.AlgorithmStartRequest;
import com.uavusv.platform.module.algorithm.dto.AlgorithmStopRequest;
import com.uavusv.platform.module.algorithm.entity.AlgorithmAssignment;
import com.uavusv.platform.module.algorithm.entity.AlgorithmAssignmentRole;
import com.uavusv.platform.module.algorithm.entity.AlgorithmEvent;
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
import com.uavusv.platform.module.monitoring.entity.RuntimePose;
import com.uavusv.platform.module.monitoring.repository.RuntimeDeviceStatusRepository;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.mockito.ArgumentCaptor;

import java.lang.reflect.Field;
import java.time.Clock;
import java.time.Instant;
import java.time.LocalDateTime;
import java.time.ZoneOffset;
import java.util.List;
import java.util.Map;
import java.util.Optional;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.Mockito.atLeastOnce;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.never;
import static org.mockito.Mockito.times;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

class AlgorithmServiceTest {

    private static final Clock CLOCK = Clock.fixed(Instant.parse("2026-01-01T00:00:00Z"), ZoneOffset.UTC);
    private static final LocalDateTime NOW = LocalDateTime.ofInstant(CLOCK.instant(), CLOCK.getZone());

    private final ObjectMapper objectMapper = new ObjectMapper();

    private AlgorithmRunRepository runRepository;
    private AlgorithmAssignmentRepository assignmentRepository;
    private AlgorithmEventRepository eventRepository;
    private AlgorithmPythonClient pythonClient;
    private DeviceRepository deviceRepository;
    private RuntimeDeviceStatusRepository runtimeStatusRepository;
    private AlgorithmService service;
    private long nextDeviceId;

    @BeforeEach
    void setUp() {
        runRepository = mock(AlgorithmRunRepository.class);
        assignmentRepository = mock(AlgorithmAssignmentRepository.class);
        eventRepository = mock(AlgorithmEventRepository.class);
        pythonClient = mock(AlgorithmPythonClient.class);
        deviceRepository = mock(DeviceRepository.class);
        runtimeStatusRepository = mock(RuntimeDeviceStatusRepository.class);
        service = new AlgorithmService(
                runRepository,
                assignmentRepository,
                eventRepository,
                pythonClient,
                deviceRepository,
                runtimeStatusRepository,
                objectMapper,
                90,
                10,
                CLOCK
        );
        nextDeviceId = 1L;
        when(runRepository.save(any(AlgorithmRun.class))).thenAnswer(invocation -> invocation.getArgument(0));
        when(assignmentRepository.save(any(AlgorithmAssignment.class))).thenAnswer(invocation -> invocation.getArgument(0));
        when(eventRepository.save(any(AlgorithmEvent.class))).thenAnswer(invocation -> invocation.getArgument(0));
    }

    @Test
    void capturePassesTargetPositionToPythonUnchanged() {
        registerDevice("uav_01", "uav-01", DeviceType.UAV, runtimeStatus(1.0, 2.0, 3.0, 0.0, 0.0, 0.0, 1.0, NOW));
        when(pythonClient.runOnce(any())).thenAnswer(invocation -> successResult(invocation.getArgument(0)));

        service.start(captureRequest());

        AlgorithmPythonClient.RunOnceRequest request = capturedPythonRequest();
        assertEquals(10.0, request.targetPosition().x());
        assertEquals(20.0, request.targetPosition().y());
        assertEquals(30.0, request.targetPosition().z());
        assertEquals(1.25, request.targetPosition().heading());
    }

    @Test
    void escortPassesTargetAndThreatPositionsToPythonUnchanged() {
        registerDevice("uav_01", "uav-01", DeviceType.UAV, runtimeStatus(1.0, 2.0, 3.0, 0.0, 0.0, 0.0, 1.0, NOW));
        when(pythonClient.runOnce(any())).thenAnswer(invocation -> successResult(invocation.getArgument(0)));

        service.start(escortRequest());

        AlgorithmPythonClient.RunOnceRequest request = capturedPythonRequest();
        assertEquals(10.0, request.targetPosition().x());
        assertEquals(20.0, request.targetPosition().y());
        assertEquals(30.0, request.targetPosition().z());
        assertEquals(1.25, request.targetPosition().heading());
        assertEquals(40.0, request.threatPosition().x());
        assertEquals(50.0, request.threatPosition().y());
        assertEquals(60.0, request.threatPosition().z());
        assertEquals(2.5, request.threatPosition().heading());
    }

    @Test
    void mapsFrontendUavIdToDatabaseDeviceCode() {
        registerDevice("uav_01", "uav-01", DeviceType.UAV, runtimeStatus(1.0, 2.0, 3.0, 0.0, 0.0, 0.0, 1.0, NOW));
        when(pythonClient.runOnce(any())).thenAnswer(invocation -> successResult(invocation.getArgument(0)));

        service.start(captureRequest());

        verify(deviceRepository).findByCode("uav-01");
        assertEquals("uav-01", capturedPythonRequest().uavs().get(0).vehicleCode());
    }

    @Test
    void pythonVehicleIdKeepsFrontendOriginalValue() {
        registerDevice("uav_01", "uav-01", DeviceType.UAV, runtimeStatus(1.0, 2.0, 3.0, 0.0, 0.0, 0.0, 1.0, NOW));
        when(pythonClient.runOnce(any())).thenAnswer(invocation -> successResult(invocation.getArgument(0)));

        service.start(captureRequest());

        assertEquals("uav_01", capturedPythonRequest().uavs().get(0).vehicleId());
    }

    @Test
    void runtimePositionIsPassedToPythonUnchanged() {
        registerDevice("uav_01", "uav-01", DeviceType.UAV, runtimeStatus(7.0, 8.0, 9.0, 0.0, 0.0, 0.0, 1.0, NOW));
        when(pythonClient.runOnce(any())).thenAnswer(invocation -> successResult(invocation.getArgument(0)));

        service.start(captureRequest());

        AlgorithmPythonClient.Position position = capturedPythonRequest().uavs().get(0).position();
        assertEquals(7.0, position.x());
        assertEquals(8.0, position.y());
        assertEquals(9.0, position.z());
    }

    @Test
    void unitQuaternionProducesHeadingZero() {
        registerDevice("uav_01", "uav-01", DeviceType.UAV, runtimeStatus(1.0, 2.0, 3.0, 0.0, 0.0, 0.0, 1.0, NOW));
        when(pythonClient.runOnce(any())).thenAnswer(invocation -> successResult(invocation.getArgument(0)));

        service.start(captureRequest());

        assertEquals(0.0, capturedPythonRequest().uavs().get(0).position().heading(), 1e-9);
    }

    @Test
    void ninetyDegreeYawQuaternionProducesPiOverTwoHeading() {
        double half = Math.sqrt(0.5);
        registerDevice("uav_01", "uav-01", DeviceType.UAV, runtimeStatus(1.0, 2.0, 3.0, 0.0, 0.0, half, half, NOW));
        when(pythonClient.runOnce(any())).thenAnswer(invocation -> successResult(invocation.getArgument(0)));

        service.start(captureRequest());

        assertEquals(Math.PI / 2, capturedPythonRequest().uavs().get(0).position().heading(), 1e-9);
    }

    @Test
    void missingDeviceDoesNotCallPython() {
        when(deviceRepository.findByCode("uav-01")).thenReturn(Optional.empty());

        assertThrows(BusinessException.class, () -> service.start(captureRequest()));

        verify(pythonClient, never()).runOnce(any());
    }

    @Test
    void missingRuntimeStatusDoesNotCallPython() {
        Device device = registerDeviceWithoutStatus("uav_01", "uav-01", DeviceType.UAV);
        when(runtimeStatusRepository.findByDeviceId(device.getId())).thenReturn(Optional.empty());

        assertThrows(BusinessException.class, () -> service.start(captureRequest()));

        verify(pythonClient, never()).runOnce(any());
    }

    @Test
    void offlineDeviceDoesNotCallPython() {
        RuntimeDeviceStatus status = runtimeStatus(1.0, 2.0, 3.0, 0.0, 0.0, 0.0, 1.0, NOW);
        status.markOffline("offline");
        registerDevice("uav_01", "uav-01", DeviceType.UAV, status);

        assertThrows(BusinessException.class, () -> service.start(captureRequest()));

        verify(pythonClient, never()).runOnce(any());
    }

    @Test
    void nullCoordinateDoesNotCallPython() {
        RuntimeDeviceStatus status = runtimeStatus(1.0, 2.0, 3.0, 0.0, 0.0, 0.0, 1.0, NOW);
        setField(status, "positionX", null);
        registerDevice("uav_01", "uav-01", DeviceType.UAV, status);

        assertThrows(BusinessException.class, () -> service.start(captureRequest()));

        verify(pythonClient, never()).runOnce(any());
    }

    @Test
    void nonFiniteCoordinateDoesNotCallPython() {
        registerDevice("uav_01", "uav-01", DeviceType.UAV, runtimeStatus(Double.NaN, 2.0, 3.0, 0.0, 0.0, 0.0, 1.0, NOW));

        assertThrows(BusinessException.class, () -> service.start(captureRequest()));

        verify(pythonClient, never()).runOnce(any());
    }

    @Test
    void missingQuaternionDoesNotCallPython() {
        RuntimeDeviceStatus status = runtimeStatus(1.0, 2.0, 3.0, 0.0, 0.0, 0.0, 1.0, NOW);
        setField(status, "orientationW", null);
        registerDevice("uav_01", "uav-01", DeviceType.UAV, status);

        assertThrows(BusinessException.class, () -> service.start(captureRequest()));

        verify(pythonClient, never()).runOnce(any());
    }

    @Test
    void nonFiniteQuaternionDoesNotCallPython() {
        registerDevice("uav_01", "uav-01", DeviceType.UAV, runtimeStatus(1.0, 2.0, 3.0, 0.0, 0.0, Double.POSITIVE_INFINITY, 1.0, NOW));

        assertThrows(BusinessException.class, () -> service.start(captureRequest()));

        verify(pythonClient, never()).runOnce(any());
    }

    @Test
    void zeroNormQuaternionDoesNotCallPython() {
        registerDevice("uav_01", "uav-01", DeviceType.UAV, runtimeStatus(1.0, 2.0, 3.0, 0.0, 0.0, 0.0, 0.0, NOW));

        assertThrows(BusinessException.class, () -> service.start(captureRequest()));

        verify(pythonClient, never()).runOnce(any());
    }

    @Test
    void staleRuntimePositionDoesNotCallPython() {
        registerDevice("uav_01", "uav-01", DeviceType.UAV,
                runtimeStatus(1.0, 2.0, 3.0, 0.0, 0.0, 0.0, 1.0, NOW.minusSeconds(11)));

        assertThrows(BusinessException.class, () -> service.start(captureRequest()));

        verify(pythonClient, never()).runOnce(any());
    }

    @Test
    void duplicateRequestedDeviceDoesNotCallPython() {
        registerDevice("uav_01", "uav-01", DeviceType.UAV, runtimeStatus(1.0, 2.0, 3.0, 0.0, 0.0, 0.0, 1.0, NOW));

        assertThrows(BusinessException.class, () -> service.start(new AlgorithmStartRequest(
                AlgorithmType.CAPTURE,
                "target_01",
                position(10.0, 20.0, 30.0, 1.25),
                null,
                List.of("uav_01", "uav_01"),
                List.of(),
                Map.of()
        )));

        verify(pythonClient, never()).runOnce(any());
    }

    @Test
    void wrongDeviceTypeDoesNotCallPython() {
        registerDevice("uav_01", "uav-01", DeviceType.USV, runtimeStatus(1.0, 2.0, 3.0, 0.0, 0.0, 0.0, 1.0, NOW));

        assertThrows(BusinessException.class, () -> service.start(captureRequest()));

        verify(pythonClient, never()).runOnce(any());
    }

    @Test
    void pythonCommandIdMismatchDoesNotSaveAssignment() {
        registerDevice("uav_01", "uav-01", DeviceType.UAV, runtimeStatus(1.0, 2.0, 3.0, 0.0, 0.0, 0.0, 1.0, NOW));
        when(pythonClient.runOnce(any())).thenAnswer(invocation -> successResultForCommandId("other-command"));

        assertThrows(BusinessException.class, () -> service.start(captureRequest()));

        verify(assignmentRepository, never()).save(any());
        assertEquals(AlgorithmRunStatus.FAILED, lastSavedRun().getStatus());
    }

    @Test
    void pythonUnknownVehicleIdDoesNotSaveAssignment() {
        registerDevice("uav_01", "uav-01", DeviceType.UAV, runtimeStatus(1.0, 2.0, 3.0, 0.0, 0.0, 0.0, 1.0, NOW));
        when(pythonClient.runOnce(any())).thenAnswer(invocation -> resultWithAssignments(
                invocation.getArgument(0),
                List.of(assignment("uav_99", "uav-99", "TRACK"))
        ));

        assertThrows(BusinessException.class, () -> service.start(captureRequest()));

        verify(assignmentRepository, never()).save(any());
    }

    @Test
    void pythonDuplicateVehicleIdDoesNotSaveAssignment() {
        registerDevice("uav_01", "uav-01", DeviceType.UAV, runtimeStatus(1.0, 2.0, 3.0, 0.0, 0.0, 0.0, 1.0, NOW));
        when(pythonClient.runOnce(any())).thenAnswer(invocation -> resultWithAssignments(
                invocation.getArgument(0),
                List.of(assignment("uav_01", "uav-01", "TRACK"), assignment("uav_01", "uav-01", "TRACK"))
        ));

        assertThrows(BusinessException.class, () -> service.start(captureRequest()));

        verify(assignmentRepository, never()).save(any());
    }

    @Test
    void pythonUnknownRoleDoesNotUseDefaultRole() {
        registerDevice("uav_01", "uav-01", DeviceType.UAV, runtimeStatus(1.0, 2.0, 3.0, 0.0, 0.0, 0.0, 1.0, NOW));
        when(pythonClient.runOnce(any())).thenAnswer(invocation -> resultWithAssignments(
                invocation.getArgument(0),
                List.of(assignment("uav_01", "uav-01", "UNKNOWN_ROLE"))
        ));

        assertThrows(BusinessException.class, () -> service.start(captureRequest()));

        verify(assignmentRepository, never()).save(any());
    }

    @Test
    void successfulPythonResponseSavesRealAssignments() throws Exception {
        registerDevice("uav_01", "uav-01", DeviceType.UAV, runtimeStatus(1.0, 2.0, 3.0, 0.0, 0.0, 0.0, 1.0, NOW));
        when(pythonClient.runOnce(any())).thenAnswer(invocation -> successResult(invocation.getArgument(0)));

        service.start(captureRequest());

        AlgorithmAssignment assignment = capturedAssignment();
        assertEquals("uav_01", assignment.getVehicleId());
        assertEquals("uav-01", assignment.getVehicleCode());
        assertEquals(AlgorithmAssignmentRole.TRACK, assignment.getRole());
        assertEquals(101.0, assignment.getX());
        assertEquals("python", objectMapper.readTree(assignment.getDetail()).path("source").asText());
        assertNotEquals("STANDBY", assignment.getRole().name());
    }

    @Test
    void successfulRunOnceEndsAsCompleted() {
        registerDevice("uav_01", "uav-01", DeviceType.UAV, runtimeStatus(1.0, 2.0, 3.0, 0.0, 0.0, 0.0, 1.0, NOW));
        when(pythonClient.runOnce(any())).thenAnswer(invocation -> successResult(invocation.getArgument(0)));

        assertEquals(AlgorithmRunStatus.COMPLETED, service.start(captureRequest()).status());
    }

    @Test
    void pythonBusinessRejectionEndsAsFailed() {
        registerDevice("uav_01", "uav-01", DeviceType.UAV, runtimeStatus(1.0, 2.0, 3.0, 0.0, 0.0, 0.0, 1.0, NOW));
        when(pythonClient.runOnce(any())).thenAnswer(invocation -> failedResult(invocation.getArgument(0), "INVALID_REQUEST"));

        assertThrows(BusinessException.class, () -> service.start(captureRequest()));

        assertEquals(AlgorithmRunStatus.FAILED, lastSavedRun().getStatus());
    }

    @Test
    void httpClientExceptionEndsAsFailed() {
        registerDevice("uav_01", "uav-01", DeviceType.UAV, runtimeStatus(1.0, 2.0, 3.0, 0.0, 0.0, 0.0, 1.0, NOW));
        when(pythonClient.runOnce(any())).thenThrow(new AlgorithmPythonClient.AlgorithmPythonClientException("connection refused"));

        assertThrows(BusinessException.class, () -> service.start(captureRequest()));

        assertEquals(AlgorithmRunStatus.FAILED, lastSavedRun().getStatus());
    }

    @Test
    void terminalRunStopIsNotOverwrittenAsStopped() {
        AlgorithmRun run = new AlgorithmRun("alg-done", AlgorithmType.CAPTURE, "target_01", "{}", "{}");
        run.updateStatus(AlgorithmRunStatus.COMPLETED, "COMPLETED", "done", null);
        when(runRepository.findByCommandId("alg-done")).thenReturn(Optional.of(run));

        service.stop(new AlgorithmStopRequest("alg-done", "user stop"));

        assertEquals(AlgorithmRunStatus.COMPLETED, run.getStatus());
        verify(runRepository, never()).save(run);
    }

    @Test
    void startPathDoesNotGenerateMockAssignments() {
        registerDevice("uav_01", "uav-01", DeviceType.UAV, runtimeStatus(1.0, 2.0, 3.0, 0.0, 0.0, 0.0, 1.0, NOW));
        when(pythonClient.runOnce(any())).thenAnswer(invocation -> successResult(invocation.getArgument(0)));

        service.start(captureRequest());

        verify(assignmentRepository, times(1)).save(any());
        AlgorithmAssignment assignment = capturedAssignment();
        assertEquals(101.0, assignment.getX());
    }

    @Test
    void pythonEventsAreSavedAndMetricsAreIgnored() {
        registerDevice("uav_01", "uav-01", DeviceType.UAV, runtimeStatus(1.0, 2.0, 3.0, 0.0, 0.0, 0.0, 1.0, NOW));
        when(pythonClient.runOnce(any())).thenAnswer(invocation -> successResult(invocation.getArgument(0)));

        service.start(captureRequest());

        AlgorithmEvent event = capturedEvent();
        assertEquals("python-stage", event.getStage());
        assertEquals("python event", event.getMessage());
    }

    private AlgorithmStartRequest captureRequest() {
        return new AlgorithmStartRequest(
                AlgorithmType.CAPTURE,
                "target_01",
                position(10.0, 20.0, 30.0, 1.25),
                null,
                List.of("uav_01"),
                List.of(),
                Map.of("captureRadius", 60)
        );
    }

    private AlgorithmStartRequest escortRequest() {
        return new AlgorithmStartRequest(
                AlgorithmType.ESCORT_DEFENSE,
                "escort_target_01",
                position(10.0, 20.0, 30.0, 1.25),
                position(40.0, 50.0, 60.0, 2.5),
                List.of("uav_01"),
                List.of(),
                Map.of("threatTargetId", "enemy_01", "threatDirection", "FRONT")
        );
    }

    private AlgorithmStartRequest.PositionRequest position(double x, double y, double z, double heading) {
        return new AlgorithmStartRequest.PositionRequest(x, y, z, heading);
    }

    private Device registerDevice(String vehicleId, String deviceCode, DeviceType type, RuntimeDeviceStatus status) {
        Device device = registerDeviceWithoutStatus(vehicleId, deviceCode, type);
        setField(status, "deviceId", device.getId());
        when(runtimeStatusRepository.findByDeviceId(device.getId())).thenReturn(Optional.of(status));
        return device;
    }

    private Device registerDeviceWithoutStatus(String vehicleId, String deviceCode, DeviceType type) {
        Device device = new Device(deviceCode, deviceCode, type, DeviceStatus.ONLINE, null, null, null, null);
        setId(device, nextDeviceId++);
        when(deviceRepository.findByCode(vehicleId.replace('_', '-'))).thenReturn(Optional.of(device));
        return device;
    }

    private RuntimeDeviceStatus runtimeStatus(
            double x,
            double y,
            double z,
            double qx,
            double qy,
            double qz,
            double qw,
            LocalDateTime observedAt
    ) {
        RuntimeDeviceStatus status = new RuntimeDeviceStatus(0L);
        status.observe("ROS", "sim", observedAt, 1L, "127.0.0.1", 8765,
                new RuntimePose(x, y, z, qx, qy, qz, qw), null);
        return status;
    }

    private AlgorithmPythonClient.AlgorithmResult successResult(AlgorithmPythonClient.RunOnceRequest request) {
        return resultWithAssignments(request, List.of(assignment("uav_01", "uav-01", "TRACK")));
    }

    private AlgorithmPythonClient.AlgorithmResult successResultForCommandId(String commandId) {
        return new AlgorithmPythonClient.AlgorithmResult(
                commandId,
                "CAPTURE",
                "COMPLETED",
                "python-stage",
                "target_01",
                List.of(assignment("uav_01", "uav-01", "TRACK")),
                List.of(new AlgorithmPythonClient.AlgorithmEvent("INFO", "python-stage", "python event", json("{\"detail\":true}"))),
                json("{\"objective\":12.5}"),
                "python done",
                null,
                null
        );
    }

    private AlgorithmPythonClient.AlgorithmResult resultWithAssignments(
            AlgorithmPythonClient.RunOnceRequest request,
            List<AlgorithmPythonClient.Assignment> assignments
    ) {
        return new AlgorithmPythonClient.AlgorithmResult(
                request.commandId(),
                request.algorithmType(),
                "COMPLETED",
                "python-stage",
                request.targetId(),
                assignments,
                List.of(new AlgorithmPythonClient.AlgorithmEvent("INFO", "python-stage", "python event", json("{\"detail\":true}"))),
                json("{\"objective\":12.5}"),
                "python done",
                null,
                null
        );
    }

    private AlgorithmPythonClient.AlgorithmResult failedResult(AlgorithmPythonClient.RunOnceRequest request, String status) {
        return new AlgorithmPythonClient.AlgorithmResult(
                request.commandId(),
                request.algorithmType(),
                status,
                "failed",
                request.targetId(),
                List.of(),
                List.of(),
                null,
                "python rejected",
                "python rejected",
                null
        );
    }

    private AlgorithmPythonClient.Assignment assignment(String vehicleId, String vehicleCode, String role) {
        return new AlgorithmPythonClient.Assignment(
                vehicleId,
                vehicleCode,
                role,
                101.0,
                202.0,
                303.0,
                1.5,
                json("{\"source\":\"python\"}")
        );
    }

    private com.fasterxml.jackson.databind.JsonNode json(String json) {
        try {
            return objectMapper.readTree(json);
        } catch (Exception exception) {
            throw new IllegalStateException(exception);
        }
    }

    private AlgorithmPythonClient.RunOnceRequest capturedPythonRequest() {
        ArgumentCaptor<AlgorithmPythonClient.RunOnceRequest> captor = ArgumentCaptor.forClass(AlgorithmPythonClient.RunOnceRequest.class);
        verify(pythonClient).runOnce(captor.capture());
        return captor.getValue();
    }

    private AlgorithmAssignment capturedAssignment() {
        ArgumentCaptor<AlgorithmAssignment> captor = ArgumentCaptor.forClass(AlgorithmAssignment.class);
        verify(assignmentRepository, atLeastOnce()).save(captor.capture());
        return captor.getValue();
    }

    private AlgorithmEvent capturedEvent() {
        ArgumentCaptor<AlgorithmEvent> captor = ArgumentCaptor.forClass(AlgorithmEvent.class);
        verify(eventRepository, atLeastOnce()).save(captor.capture());
        return captor.getValue();
    }

    private AlgorithmRun lastSavedRun() {
        ArgumentCaptor<AlgorithmRun> captor = ArgumentCaptor.forClass(AlgorithmRun.class);
        verify(runRepository, atLeastOnce()).save(captor.capture());
        List<AlgorithmRun> values = captor.getAllValues();
        return values.get(values.size() - 1);
    }

    private void setId(BaseEntity entity, Long id) {
        setField(entity, "id", id);
    }

    private void setField(Object target, String fieldName, Object value) {
        Class<?> type = target.getClass();
        while (type != null) {
            try {
                Field field = type.getDeclaredField(fieldName);
                field.setAccessible(true);
                field.set(target, value);
                return;
            } catch (NoSuchFieldException ignored) {
                type = type.getSuperclass();
            } catch (IllegalAccessException exception) {
                throw new IllegalStateException(exception);
            }
        }
        throw new IllegalArgumentException("No field " + fieldName + " on " + target.getClass());
    }
}
