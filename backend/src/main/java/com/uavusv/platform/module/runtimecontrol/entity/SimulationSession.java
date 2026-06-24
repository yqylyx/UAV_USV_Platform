package com.uavusv.platform.module.runtimecontrol.entity;

import com.uavusv.platform.common.entity.BaseEntity;
import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.EnumType;
import jakarta.persistence.Enumerated;
import jakarta.persistence.Table;

import java.time.LocalDateTime;

@Entity
@Table(name = "simulation_session")
public class SimulationSession extends BaseEntity {
    @Column(name = "session_key", nullable = false, unique = true, length = 64)
    private String sessionKey;
    @Enumerated(EnumType.STRING)
    @Column(nullable = false, length = 32)
    private SimulationStatus status;
    @Column(name = "requested_by", length = 64)
    private String requestedBy;
    @Column(name = "ros_managed", nullable = false)
    private boolean rosManaged;
    @Column(name = "unity_managed", nullable = false)
    private boolean unityManaged;
    @Column(name = "ros_process_id")
    private Long rosProcessId;
    @Column(name = "unity_process_id")
    private Long unityProcessId;
    @Column(name = "started_at")
    private LocalDateTime startedAt;
    @Column(name = "stopped_at")
    private LocalDateTime stoppedAt;
    @Column(name = "error_message", length = 1000)
    private String errorMessage;

    protected SimulationSession() {
    }

    public SimulationSession(String sessionKey, String requestedBy) {
        this.sessionKey = sessionKey;
        this.requestedBy = requestedBy;
        this.status = SimulationStatus.STARTING;
        this.startedAt = LocalDateTime.now();
    }

    public void configureOwnership(boolean rosManaged, boolean unityManaged, Long rosProcessId, Long unityProcessId) {
        this.rosManaged = rosManaged;
        this.unityManaged = unityManaged;
        this.rosProcessId = rosProcessId;
        this.unityProcessId = unityProcessId;
    }

    public void updateStatus(SimulationStatus status) {
        this.status = status;
        if (status == SimulationStatus.STOPPED || status == SimulationStatus.FAILED) {
            this.stoppedAt = LocalDateTime.now();
        }
    }

    public void fail(String errorMessage) {
        this.errorMessage = errorMessage;
        updateStatus(SimulationStatus.FAILED);
    }

    public String getSessionKey() { return sessionKey; }
    public SimulationStatus getStatus() { return status; }
    public String getRequestedBy() { return requestedBy; }
    public boolean isRosManaged() { return rosManaged; }
    public boolean isUnityManaged() { return unityManaged; }
    public Long getRosProcessId() { return rosProcessId; }
    public Long getUnityProcessId() { return unityProcessId; }
    public LocalDateTime getStartedAt() { return startedAt; }
    public LocalDateTime getStoppedAt() { return stoppedAt; }
    public String getErrorMessage() { return errorMessage; }
}
