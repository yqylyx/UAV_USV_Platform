package com.uavusv.platform.module.algorithm.entity;

import com.uavusv.platform.common.entity.BaseEntity;
import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.EnumType;
import jakarta.persistence.Enumerated;
import jakarta.persistence.Table;

import java.time.LocalDateTime;

@Entity
@Table(name = "algorithm_run")
public class AlgorithmRun extends BaseEntity {

    @Column(name = "command_id", nullable = false, unique = true, length = 64)
    private String commandId;

    @Enumerated(EnumType.STRING)
    @Column(name = "algorithm_type", nullable = false, length = 32)
    private AlgorithmType algorithmType;

    @Enumerated(EnumType.STRING)
    @Column(nullable = false, length = 32)
    private AlgorithmRunStatus status;

    @Column(name = "target_id", length = 64)
    private String targetId;

    @Column(length = 64)
    private String stage;

    @Column(length = 1000)
    private String message;

    @Column(name = "request_json", columnDefinition = "TEXT")
    private String requestJson;

    @Column(name = "parameter_json", columnDefinition = "TEXT")
    private String parameterJson;

    @Column(name = "started_at", nullable = false)
    private LocalDateTime startedAt;

    @Column(name = "last_ack_at")
    private LocalDateTime lastAckAt;

    @Column(name = "completed_at")
    private LocalDateTime completedAt;

    @Column(name = "error_message", length = 1000)
    private String errorMessage;

    protected AlgorithmRun() {
    }

    public AlgorithmRun(String commandId, AlgorithmType algorithmType, String targetId, String requestJson, String parameterJson) {
        this.commandId = commandId;
        this.algorithmType = algorithmType;
        this.status = AlgorithmRunStatus.PENDING;
        this.targetId = targetId;
        this.stage = "INIT";
        this.message = "已生成算法指令，等待外部算法 ACK；模拟分配结果可用于前端联调";
        this.requestJson = requestJson;
        this.parameterJson = parameterJson;
        this.startedAt = LocalDateTime.now();
    }

    public void acknowledge(boolean success, String detail, String errorCode) {
        this.lastAckAt = LocalDateTime.now();
        if (success) {
            this.status = AlgorithmRunStatus.RUNNING;
            this.stage = this.stage == null ? "INIT" : this.stage;
            this.message = detail == null || detail.isBlank() ? "外部算法已确认运行" : detail;
            this.errorMessage = null;
        } else {
            this.status = AlgorithmRunStatus.FAILED;
            this.stage = "FAILED";
            this.message = detail == null || detail.isBlank() ? "外部算法拒绝指令" : detail;
            this.errorMessage = errorCode == null || errorCode.isBlank() ? this.message : errorCode + ": " + this.message;
            this.completedAt = LocalDateTime.now();
        }
    }

    public void updateStatus(AlgorithmRunStatus status, String stage, String message, String errorMessage) {
        this.status = status;
        if (stage != null && !stage.isBlank()) this.stage = stage;
        if (message != null && !message.isBlank()) this.message = message;
        this.errorMessage = errorMessage;
        this.lastAckAt = LocalDateTime.now();
        if (status == AlgorithmRunStatus.COMPLETED || status == AlgorithmRunStatus.FAILED
                || status == AlgorithmRunStatus.TIMEOUT || status == AlgorithmRunStatus.STOPPED) {
            this.completedAt = LocalDateTime.now();
        }
    }

    public void stop(String message) {
        this.status = AlgorithmRunStatus.STOPPED;
        this.stage = "STOPPED";
        this.message = message;
        this.completedAt = LocalDateTime.now();
    }

    public void timeout(String message) {
        this.status = AlgorithmRunStatus.TIMEOUT;
        this.stage = "TIMEOUT";
        this.message = message;
        this.errorMessage = message;
        this.completedAt = LocalDateTime.now();
    }

    public String getCommandId() { return commandId; }
    public AlgorithmType getAlgorithmType() { return algorithmType; }
    public AlgorithmRunStatus getStatus() { return status; }
    public String getTargetId() { return targetId; }
    public String getStage() { return stage; }
    public String getMessage() { return message; }
    public String getRequestJson() { return requestJson; }
    public String getParameterJson() { return parameterJson; }
    public LocalDateTime getStartedAt() { return startedAt; }
    public LocalDateTime getLastAckAt() { return lastAckAt; }
    public LocalDateTime getCompletedAt() { return completedAt; }
    public String getErrorMessage() { return errorMessage; }
}
