package com.uavusv.platform.module.voicecontrol;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.node.ObjectNode;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.boot.context.event.ApplicationReadyEvent;
import org.springframework.context.event.EventListener;
import org.springframework.scheduling.annotation.Scheduled;
import org.springframework.stereotype.Service;

import java.time.Instant;
import java.util.*;
import java.util.concurrent.ConcurrentLinkedQueue;
import java.util.concurrent.atomic.AtomicInteger;

@Service
public class VoiceDispatcher {
    private static final Logger log = LoggerFactory.getLogger(VoiceDispatcher.class);
    private final VoiceStore s;
    private final VoiceJson j;
    private final VoiceTime t;
    private final RuntimeContextRegistry r;
    private final Queue<Pending> pending = new ConcurrentLinkedQueue<>();
    private final AtomicInteger pendingCount = new AtomicInteger();
    private volatile boolean storageHealthy = true;

    private record Pending(
            String ref,
            String generation,
            JsonNode event,
            String operation,
            long receivedNanos,
            String receivedAt) {}

    public VoiceDispatcher(VoiceStore s, VoiceJson j, VoiceTime t, RuntimeContextRegistry r) {
        this.s = s;
        this.j = j;
        this.t = t;
        this.r = r;
    }

    @EventListener(ApplicationReadyEvent.class)
    public void recover() {
        // The platform owns local child pipes; deployment is one backend process per database.
        for (var c : s.locked(() -> s.query("SELECT data_json FROM voice_runtime_context")))
            if (r.channel(c.path("_id").asText()) == null)
                r.ended(c.path("_id").asText(), c.path("runtimeGeneration").asText());
        s.locked(
                () -> {
                    s.jdbc.update(
                            "UPDATE voice_outbox SET status='UNCERTAIN' WHERE status='SENDING'");
                    return null;
                });
    }

    @Scheduled(fixedDelayString = "${app.voicecontrol.poll-ms:200}")
    public synchronized void tick() {
        try {
            Pending item;
            while ((item = pending.peek()) != null) {
                apply(item);
                pending.remove();
                pendingCount.decrementAndGet();
            }
            storageHealthy = true;
            var all =
                    s.locked(
                            () ->
                                    s.query(
                                            "SELECT data_json FROM voice_execution WHERE state IN"
                                                + " ('QUEUED','DISPATCHED','ACCEPTED','EXECUTING','TIMED_OUT')"));
            for (var e : all) {
                String ref = e.path("runtimeRef").asText();
                var ch = r.channel(ref);
                if (ch == null) continue;
                synchronized (ch.lock) {
                    if ("QUEUED".equals(e.path("state").asText()))
                        dispatch(e.path("_id").asText(), ch);
                    else timeoutAndQuery(e.path("_id").asText(), ch);
                }
            }
        } catch (Exception e) {
            storageHealthy = false;
            log.warn(
                    "P0 dispatch suspended; persistence/reconciliation will retry: {}",
                    e.getClass().getSimpleName());
        }
    }

    private void dispatch(String id, RuntimeContextRegistry.Channel ch) {
        if (!storageHealthy) return;
        ObjectNode command =
                s.locked(
                        () -> {
                            var e = s.get("voice_execution", id);
                            if (!"QUEUED".equals(e.path("state").asText())) return null;
                            var c = s.get("voice_runtime_context", e.path("runtimeRef").asText());
                            try {
                                if (!t.now()
                                        .isBefore(
                                                Instant.parse(e.path("createdAt").asText())
                                                        .plusSeconds(10)))
                                    throw VoiceFailure.conflict("DISPATCH_DEADLINE_EXCEEDED");
                                if (!e.path("runtimeGeneration")
                                        .equals(c.path("runtimeGeneration")))
                                    throw VoiceFailure.conflict("GENERATION_MISMATCH");
                                if (!e.path("_plan")
                                                .path("contextVersion")
                                                .equals(c.path("contextVersion"))
                                        || !e.path("_plan")
                                                .path("stateVersion")
                                                .equals(c.path("stateVersion")))
                                    throw VoiceFailure.conflict("CONTEXT_CHANGED");
                                r.check(
                                        c,
                                        e.path("action").asText(),
                                        !e.path("_manual").asBoolean());
                            } catch (VoiceFailure failure) {
                                e.put("state", "INVALIDATED")
                                        .put("outcome", "REJECTED")
                                        .put("errorCode", failure.code)
                                        .put("updatedAt", t.stamp());
                                s.save("voice_execution", e);
                                s.jdbc.update(
                                        "UPDATE voice_outbox SET status='CANCELLED' WHERE"
                                            + " execution_id=? AND status='READY'",
                                        id);
                                return null;
                            }
                            if (s.jdbc.update(
                                            "UPDATE voice_outbox SET status='SENDING',claimed_at=?"
                                                + " WHERE execution_id=? AND status='READY'",
                                            t.stamp(),
                                            id)
                                    != 1) return null;
                            long sequence = c.path("_nextSequence").asLong() + 1;
                            c.put("_nextSequence", sequence);
                            s.save("voice_runtime_context", c);
                            e.put("_commandSequence", sequence)
                                    .put("_sendStartedAt", t.stamp())
                                    .put("state", "DISPATCHED")
                                    .put("updatedAt", t.stamp());
                            s.save("voice_execution", e);
                            var cmd = j.object();
                            cmd.put("protocolVersion", RuntimeContextRegistry.PROTOCOL)
                                    .put("kind", "COMMAND")
                                    .put("commandId", e.path("commandId").asText());
                            cmd.set("runtimeRef", e.path("runtimeRef"));
                            cmd.set("runtimeGeneration", e.path("runtimeGeneration"));
                            cmd.put("commandSequence", sequence);
                            cmd.set("expectedStateVersion", e.path("_plan").path("stateVersion"));
                            cmd.set("action", e.path("action"));
                            cmd.putObject("parameters");
                            j.validate("Command", cmd);
                            return cmd;
                        });
        if (command == null) return;
        try {
            // At this point SENDING is committed. Failure after this point is ambiguous, never
            // resend.
            ch.sender.accept(command);
        } catch (RuntimeException failure) {
            s.locked(
                    () -> {
                        var e = s.get("voice_execution", id);
                        markTimeout(e, "SEND_UNCERTAIN");
                        s.jdbc.update(
                                "UPDATE voice_outbox SET status='UNCERTAIN' WHERE execution_id=?",
                                id);
                        return null;
                    });
            return;
        }
        s.locked(
                () -> {
                    var e = s.get("voice_execution", id);
                    e.put("_flushedAt", t.stamp());
                    s.save("voice_execution", e);
                    s.jdbc.update("UPDATE voice_outbox SET status='SENT' WHERE execution_id=?", id);
                    return null;
                });
    }

    private void timeoutAndQuery(String id, RuntimeContextRegistry.Channel ch) {
        var query =
                s.locked(
                        () -> {
                            var e = s.get("voice_execution", id);
                            String state = e.path("state").asText();
                            if (Set.of("DISPATCHED", "ACCEPTED", "EXECUTING").contains(state)) {
                                String start =
                                        e.path("_flushedAt")
                                                .asText(e.path("_sendStartedAt").asText());
                                long seconds = state.equals("DISPATCHED") ? 5 : 15;
                                if (!t.now().isBefore(Instant.parse(start).plusSeconds(seconds)))
                                    markTimeout(e, "COMMAND_TIMEOUT");
                            }
                            if (!"TIMED_OUT".equals(e.path("state").asText())
                                    || !ch.alive.getAsBoolean()
                                    || e.path("_queryCount").asInt() >= 3) return null;
                            if (e.has("_lastQueryAt")
                                    && t.now()
                                            .isBefore(
                                                    Instant.parse(e.path("_lastQueryAt").asText())
                                                            .plusSeconds(2))) return null;
                            String qid = VoiceJson.uuid();
                            e.put("_queryId", qid)
                                    .put("_queryCount", e.path("_queryCount").asInt() + 1)
                                    .put("_lastQueryAt", t.stamp());
                            s.save("voice_execution", e);
                            var q = j.object();
                            q.put("kind", "STATUS_QUERY")
                                    .put("protocolVersion", RuntimeContextRegistry.PROTOCOL)
                                    .put("queryId", qid);
                            q.set("commandId", e.path("commandId"));
                            q.set("runtimeRef", e.path("runtimeRef"));
                            q.set("runtimeGeneration", e.path("runtimeGeneration"));
                            return q;
                        });
        if (query != null)
            try {
                ch.sender.accept(query);
            } catch (RuntimeException ex) {
                log.debug("P0 read-only query unavailable");
            }
    }

    private void markTimeout(ObjectNode e, String code) {
        if (Set.of("SUCCEEDED", "REJECTED", "FAILED", "INVALIDATED")
                .contains(e.path("state").asText())) return;
        e.put("state", "TIMED_OUT")
                .put("outcome", "UNKNOWN")
                .put("errorCode", code)
                .put("updatedAt", t.stamp());
        if (e.path("timedOutAt").isNull()) e.put("timedOutAt", t.stamp());
        s.save("voice_execution", e);
    }

    public void receive(String ref, String gen, JsonNode event) {
        accept(new Pending(ref, gen, event.deepCopy(), "EVENT", t.nanos(), t.stamp()));
    }

    public void frame(String ref, String gen, JsonNode frame) {
        accept(new Pending(ref, gen, frame.deepCopy(), "FRAME", t.nanos(), t.stamp()));
    }

    public void ended(String ref, String gen) {
        accept(new Pending(ref, gen, j.object(), "EXIT", t.nanos(), t.stamp()));
    }

    private void accept(Pending item) {
        try {
            apply(item);
        } catch (org.springframework.dao.DataAccessException
                | org.springframework.transaction.TransactionException ex) {
            storageHealthy = false;
            if (pendingCount.incrementAndGet() <= 256) pending.add(item);
            else {
                pendingCount.decrementAndGet();
                var ch = r.channel(item.ref);
                if (ch != null) ch.faulted = true;
                log.error("P0 event buffer exhausted; runtime made read-only for reconciliation");
            }
        }
    }

    private void apply(Pending p) {
        if (p.operation.equals("FRAME")) {
            r.frame(p.ref, p.generation, p.event);
            return;
        }
        if (p.operation.equals("EXIT")) {
            r.ended(p.ref, p.generation);
            return;
        }
        s.locked(
                () -> {
                    var c = s.get("voice_runtime_context", p.ref);
                    if (c == null) return null;
                    var event = p.event;
                    boolean envelopeValid = false;
                    try {
                        String def =
                                switch (event.path("kind").asText()) {
                                    case "RUNTIME_READY" -> "RuntimeReady";
                                    case "HEARTBEAT" -> "Heartbeat";
                                    case "COMMAND_RESULT" -> "CommandResult";
                                    case "STATUS_REPLY" -> "StatusReply";
                                    case "PROTOCOL_ERROR" -> "ProtocolError";
                                    default -> throw VoiceFailure.bad();
                                };
                        j.validate(def, event);
                        if (!p.ref.equals(event.path("runtimeRef").asText())
                                || !p.generation.equals(event.path("runtimeGeneration").asText())
                                || !p.generation.equals(c.path("runtimeGeneration").asText()))
                            throw VoiceFailure.bad();
                        envelopeValid = true;
                        c.put("_protocolViolations", 0);
                        switch (def) {
                            case "RuntimeReady" -> {
                                if (c.path("_ready").asBoolean()) {
                                    if (!c.path("capabilities").equals(event.path("capabilities")))
                                        throw VoiceFailure.bad();
                                    break;
                                }
                                c.put("_ready", true);
                                c.set("capabilities", event.path("capabilities"));
                                r.state(
                                        c,
                                        event.path("state").asText(),
                                        event.path("stateVersion").asLong());
                                RuntimeContextRegistry.bump(c);
                            }
                            case "Heartbeat" -> {
                                long seq = event.path("heartbeatSequence").asLong();
                                if (seq <= c.path("_heartbeatSequence").asLong()) break;
                                if (!"LOST".equals(c.path("state").asText())) {
                                    if (event.path("stateVersion").asLong()
                                            < c.path("stateVersion").asLong()) break;
                                    if (event.path("stateVersion").asLong()
                                                    == c.path("stateVersion").asLong()
                                            && !event.path("runtimeState")
                                                    .asText()
                                                    .equals(c.path("state").asText()))
                                        throw VoiceFailure.bad();
                                    c.put("_heartbeatSequence", seq)
                                            .put("lastHeartbeatReceivedAt", p.receivedAt);
                                    var ch = r.channel(p.ref);
                                    if (ch != null) ch.heartbeatNanos = p.receivedNanos;
                                    r.state(
                                            c,
                                            event.path("runtimeState").asText(),
                                            event.path("stateVersion").asLong());
                                }
                            }
                            case "CommandResult" -> result(c, event);
                            case "StatusReply" -> {
                                var rows =
                                        s.query(
                                                "SELECT data_json FROM voice_execution WHERE"
                                                    + " command_id=?",
                                                event.path("commandId").asText());
                                if (rows.isEmpty()) throw VoiceFailure.bad();
                                var e = rows.get(0);
                                if (!e.path("_queryId").equals(event.path("queryId"))
                                        || !e.path("runtimeRef").equals(event.path("runtimeRef")))
                                    throw VoiceFailure.bad();
                                if (event.path("known").asBoolean()) {
                                    var result = event.path("result");
                                    if (!result.path("commandId").equals(event.path("commandId"))
                                            || !result.path("runtimeRef")
                                                    .equals(event.path("runtimeRef"))
                                            || !result.path("runtimeGeneration")
                                                    .equals(event.path("runtimeGeneration")))
                                        throw VoiceFailure.bad();
                                    result(c, result);
                                }
                            }
                            case "ProtocolError" -> {
                                fault(p.ref, event.path("errorCode").asText());
                            }
                            default -> throw VoiceFailure.bad();
                        }
                        s.save("voice_runtime_context", c);
                    } catch (VoiceFailure e) {
                        if (envelopeValid) fault(p.ref, "INVALID_PROTOCOL_EVENT");
                        else {
                            int violations = c.path("_protocolViolations").asInt() + 1;
                            c.put("_protocolViolations", violations);
                            s.save("voice_runtime_context", c);
                            if (violations >= 3) fault(p.ref, "INVALID_PROTOCOL_ENVELOPE");
                            else s.audit(p.ref, "PROTOCOL_ERROR", "INVALID_PROTOCOL_ENVELOPE", t.stamp());
                        }
                    }
                    return null;
                });
    }

    private void fault(String ref, String detail) {
        var ch = r.channel(ref);
        if (ch != null) ch.faulted = true;
        s.audit(ref, "PROTOCOL_ERROR", detail, t.stamp());
    }

    private void result(ObjectNode c, JsonNode event) {
        var rows =
                s.query(
                        "SELECT data_json FROM voice_execution WHERE command_id=?",
                        event.path("commandId").asText());
        if (rows.isEmpty()) throw VoiceFailure.bad();
        var e = rows.get(0);
        if (!e.path("runtimeRef").equals(event.path("runtimeRef"))
                || !e.path("runtimeGeneration").equals(event.path("runtimeGeneration"))
                || !e.has("_sendStartedAt")) throw VoiceFailure.bad();
        long sequence = event.path("eventSequence").asLong();
        String id = e.path("_id").asText(), hash = j.hash(event);
        var existing =
                s.jdbc.queryForList(
                        "SELECT body_hash FROM voice_command_event WHERE execution_id=? AND"
                            + " event_sequence=?",
                        id,
                        sequence);
        if (!existing.isEmpty()) {
            if (!hash.equals(existing.get(0).get("body_hash"))) throw VoiceFailure.bad();
            return;
        }
        String status = event.path("status").asText();
        Set<String> expected = new HashSet<>();
        e.path("_plan").path("explicitDeviceCodes").forEach(x -> expected.add(x.asText()));
        Set<String> actual = new HashSet<>();
        event.path("affectedDeviceCodes").forEach(x -> actual.add(x.asText()));
        if (!expected.containsAll(actual)
                || ("SUCCEEDED".equals(status) && !expected.equals(actual)))
            throw VoiceFailure.bad();
        if ("SUCCEEDED".equals(status)) {
            String target =
                    switch (e.path("action").asText()) {
                        case "START", "RESUME" -> "RUNNING";
                        case "PAUSE" -> "PAUSED";
                        case "STOP" -> "STOPPED";
                        default -> "";
                    };
            if (!target.equals(event.path("runtimeState").asText())
                    || event.path("stateVersion").asLong()
                            != e.path("_plan").path("stateVersion").asLong() + 1)
                throw VoiceFailure.bad();
        }
        String current = e.path("state").asText();
        boolean terminal =
                Set.of("SUCCEEDED", "REJECTED", "FAILED", "INVALIDATED").contains(current);
        if (terminal && sequence > e.path("_eventSequence").asLong()) throw VoiceFailure.bad();
        if ("EXECUTING".equals(current) && "ACCEPTED".equals(status)) throw VoiceFailure.bad();
        s.jdbc.update(
                "INSERT INTO"
                    + " voice_command_event(execution_id,event_sequence,body_hash,data_json,received_at)"
                    + " VALUES (?,?,?,?,?)",
                id,
                sequence,
                hash,
                event.toString(),
                t.stamp());
        if (terminal || sequence <= e.path("_eventSequence").asLong()) return;

        e.put("_eventSequence", sequence);
        if (!"TIMED_OUT".equals(current)
                || Set.of("SUCCEEDED", "REJECTED", "FAILED").contains(status)) {
            e.put("state", status)
                    .put(
                            "outcome",
                            switch (status) {
                                case "SUCCEEDED" -> "SUCCESS";
                                case "REJECTED" -> "REJECTED";
                                case "FAILED" -> "FAILED";
                                default -> "UNKNOWN";
                            });
            e.set("errorCode", event.path("errorCode"));
        }
        e.put("_resultFrame", event.path("lastFrameSequence").asLong()).put("updatedAt", t.stamp());
        s.save("voice_execution", e);
        var ch = r.channel(c.path("_id").asText());
        if (ch != null && !"LOST".equals(c.path("state").asText()))
            r.state(c, event.path("runtimeState").asText(), event.path("stateVersion").asLong());
    }
}
