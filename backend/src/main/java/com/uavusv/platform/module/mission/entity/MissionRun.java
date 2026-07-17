package com.uavusv.platform.module.mission.entity;

import com.uavusv.platform.common.entity.BaseEntity;
import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.EnumType;
import jakarta.persistence.Enumerated;
import jakarta.persistence.Table;

import java.time.LocalDateTime;
import java.util.UUID;

@Entity
@Table(name = "mission_run")
public class MissionRun extends BaseEntity {

    @Column(name = "mission_id", nullable = false)
    private Long missionId;

    @Column(name = "session_id")
    private Long sessionId;

    @Column(name = "run_key", nullable = false, unique = true, length = 64)
    private String runKey;

    @Column(name = "run_no", nullable = false)
    private Integer runNo;

    @Enumerated(EnumType.STRING)
    @Column(nullable = false, length = 32)
    private MissionRunStatus status;

    @Enumerated(EnumType.STRING)
    @Column(nullable = false, length = 40)
    private MissionStage stage;

    @Column(name = "requested_by", length = 64)
    private String requestedBy;

    @Column(name = "started_at", nullable = false)
    private LocalDateTime startedAt;

    @Column(name = "paused_at")
    private LocalDateTime pausedAt;

    @Column(name = "ended_at")
    private LocalDateTime endedAt;

    @Column(name = "failure_reason", length = 1000)
    private String failureReason;
    @Column(name = "runtime_instance_id", length = 128)
    private String runtimeInstanceId;
    @Column(name = "algorithm_code", length = 64)
    private String algorithmCode;
    @Column(name = "algorithm_version", length = 64)
    private String algorithmVersion;

    protected MissionRun() {
    }

    public MissionRun(Long missionId, Long sessionId, Integer runNo, MissionStage stage, String requestedBy) {
        this(missionId, sessionId, runNo, stage, requestedBy, null, "default", "1.0");
    }

    public MissionRun(
            Long missionId,
            Long sessionId,
            Integer runNo,
            MissionStage stage,
            String requestedBy,
            String runtimeInstanceId,
            String algorithmCode,
            String algorithmVersion
    ) {
        this.missionId = missionId;
        this.sessionId = sessionId;
        this.runKey = UUID.randomUUID().toString();
        this.runNo = runNo;
        this.status = MissionRunStatus.PENDING;
        this.stage = stage;
        this.requestedBy = requestedBy;
        this.runtimeInstanceId = runtimeInstanceId;
        this.algorithmCode = algorithmCode;
        this.algorithmVersion = algorithmVersion;
        this.startedAt = LocalDateTime.now();
    }

    public void activate(MissionStage stage) {
        this.status = MissionRunStatus.RUNNING;
        this.stage = stage;
    }

    public void pause(MissionStage stage) {
        this.status = MissionRunStatus.PAUSED;
        this.stage = stage;
        this.pausedAt = LocalDateTime.now();
    }

    public void resume(MissionStage stage) {
        this.status = MissionRunStatus.RUNNING;
        this.stage = stage;
        this.pausedAt = null;
    }

    public void complete(MissionStage stage) {
        finish(MissionRunStatus.COMPLETED, stage, null);
    }

    public void fail(MissionStage stage, String reason) {
        finish(MissionRunStatus.FAILED, stage, reason);
    }

    public void cancel(MissionStage stage) {
        finish(MissionRunStatus.CANCELLED, stage, null);
    }

    private void finish(MissionRunStatus status, MissionStage stage, String failureReason) {
        this.status = status;
        this.stage = stage;
        this.failureReason = failureReason;
        this.endedAt = LocalDateTime.now();
    }

    public Long getMissionId() { return missionId; }
    public Long getSessionId() { return sessionId; }
    public String getRunKey() { return runKey; }
    public Integer getRunNo() { return runNo; }
    public MissionRunStatus getStatus() { return status; }
    public MissionStage getStage() { return stage; }
    public String getRequestedBy() { return requestedBy; }
    public LocalDateTime getStartedAt() { return startedAt; }
    public LocalDateTime getPausedAt() { return pausedAt; }
    public LocalDateTime getEndedAt() { return endedAt; }
    public String getFailureReason() { return failureReason; }
    public String getRuntimeInstanceId() { return runtimeInstanceId; }
    public String getAlgorithmCode() { return algorithmCode; }
    public String getAlgorithmVersion() { return algorithmVersion; }
}
