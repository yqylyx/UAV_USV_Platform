package com.uavusv.platform.module.gateway.v1;

import org.springframework.stereotype.Component;

import java.util.Map;
import java.util.concurrent.ConcurrentHashMap;

@Component
public class GatewaySequenceGuard {

    private final Map<StreamKey, StreamCursor> cursors = new ConcurrentHashMap<>();

    public SequenceCheckResult inspect(GatewayEnvelope envelope) {
        return inspect(envelope, null);
    }

    public SequenceCheckResult inspect(GatewayEnvelope envelope, String expectedRunId) {
        if (expectedRunId != null
                && envelope.runId() != null
                && !expectedRunId.equals(envelope.runId())) {
            return SequenceCheckResult.oldRun();
        }
        if (envelope.sequence() < 0) {
            return SequenceCheckResult.invalidSequence();
        }

        StreamKey key = new StreamKey(
                taskScoped(envelope.type()) ? normalizeRunId(envelope.runId()) : null,
                envelope.source(), envelope.streamId());
        if (requiresRunId(envelope.type()) && key.runId() == null) {
            return SequenceCheckResult.oldRun();
        }
        StreamCursor previous = cursors.putIfAbsent(key, new StreamCursor(envelope.runId(), envelope.sequence()));
        if (previous == null) {
            return new SequenceCheckResult(SequenceCheckStatus.ACCEPTED);
        }
        if (sameRun(previous.runId(), envelope.runId()) && envelope.sequence() == previous.sequence()) {
            return SequenceCheckResult.duplicate();
        }
        if (sameRun(previous.runId(), envelope.runId()) && envelope.sequence() < previous.sequence()) {
            return SequenceCheckResult.outOfOrder();
        }

        cursors.put(key, new StreamCursor(envelope.runId(), envelope.sequence()));
        return new SequenceCheckResult(SequenceCheckStatus.ACCEPTED);
    }

    public void reset() {
        cursors.clear();
    }

    private boolean sameRun(String left, String right) {
        if (left == null || left.isBlank() || right == null || right.isBlank()) {
            return true;
        }
        return left.equals(right);
    }

    private boolean taskScoped(GatewayMessageType type) {
        return type == GatewayMessageType.TELEMETRY_POSE_BATCH
                || type == GatewayMessageType.MISSION_STATUS
                || type == GatewayMessageType.CONTROL_ACK
                || type == GatewayMessageType.CONTROL_FEEDBACK
                || type == GatewayMessageType.CONTROL_RESULT;
    }

    private boolean requiresRunId(GatewayMessageType type) {
        return type == GatewayMessageType.MISSION_STATUS
                || type == GatewayMessageType.CONTROL_ACK
                || type == GatewayMessageType.CONTROL_FEEDBACK
                || type == GatewayMessageType.CONTROL_RESULT;
    }

    private String normalizeRunId(String runId) {
        return runId == null || runId.isBlank() ? null : runId.trim();
    }

    private record StreamKey(String runId, String source, String streamId) {
    }

    private record StreamCursor(String runId, long sequence) {
    }

    public record SequenceCheckResult(SequenceCheckStatus status) {
        public boolean accepted() {
            return status == SequenceCheckStatus.ACCEPTED;
        }

        public static SequenceCheckResult duplicate() {
            return new SequenceCheckResult(SequenceCheckStatus.DUPLICATE);
        }

        public static SequenceCheckResult outOfOrder() {
            return new SequenceCheckResult(SequenceCheckStatus.OUT_OF_ORDER);
        }

        public static SequenceCheckResult oldRun() {
            return new SequenceCheckResult(SequenceCheckStatus.OLD_RUN);
        }

        public static SequenceCheckResult invalidSequence() {
            return new SequenceCheckResult(SequenceCheckStatus.INVALID_SEQUENCE);
        }
    }

    public enum SequenceCheckStatus {
        ACCEPTED,
        DUPLICATE,
        OUT_OF_ORDER,
        OLD_RUN,
        INVALID_SEQUENCE
    }
}
