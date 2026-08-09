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

        StreamKey key = new StreamKey(envelope.source(), envelope.streamId());
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

    private record StreamKey(String source, String streamId) {
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
