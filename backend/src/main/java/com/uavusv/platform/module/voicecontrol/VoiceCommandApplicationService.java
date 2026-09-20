package com.uavusv.platform.module.voicecontrol;

import com.fasterxml.jackson.databind.node.ObjectNode;

import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.stereotype.Service;

import java.time.Instant;
import java.util.*;

@Service
public class VoiceCommandApplicationService {
    private final VoiceStore s;
    private final VoiceJson j;
    private final VoiceTime t;
    private final VoiceAccess a;
    private final RuntimeContextRegistry r;
    private final VoiceSettings settings;

    public record Reply(int status, ObjectNode data) {}

    public VoiceCommandApplicationService(
            VoiceStore s,
            VoiceJson j,
            VoiceTime t,
            VoiceAccess a,
            RuntimeContextRegistry r,
            VoiceSettings settings) {
        this.s = s;
        this.j = j;
        this.t = t;
        this.a = a;
        this.r = r;
        this.settings = settings;
    }

    @PreAuthorize("isAuthenticated()")
    public List<ObjectNode> contexts() {
        long u = a.user(false);
        return s.locked(
                () ->
                        s
                                .query(
                                        "SELECT data_json FROM voice_runtime_context WHERE"
                                            + " owner_id=?",
                                        u)
                                .stream()
                                .map(r::view)
                                .toList());
    }

    @PreAuthorize("isAuthenticated()")
    public ObjectNode context(String ref) {
        long u = a.user(false);
        return s.locked(() -> r.view(r.require(ref, u)));
    }

    @PreAuthorize("isAuthenticated()")
    public ObjectNode proposal(String id) {
        long u = a.user(false);
        return s.locked(
                () -> {
                    var p = owned("voice_proposal", id, u);
                    expire(p);
                    return RuntimeContextRegistry.publicView(p);
                });
    }

    @PreAuthorize("isAuthenticated()")
    public ObjectNode execution(String id) {
        long u = a.user(false);
        return s.locked(() -> executionView(owned("voice_execution", id, u)));
    }

    @PreAuthorize("hasRole('ADMIN')")
    public Reply createProposal(String key, ObjectNode body) {
        long u = a.user(true);
        settings.requireEnabled();
        VoiceJson.uuid(key);
        j.validate("ProposalRequest", body);
        return s.locked(
                () -> {
                    settings.requireEnabled();
                    var c = r.require(body.path("runtimeRef").asText(), u);
                    String hash = j.hash(body), old = s.replay(u, "propose", key, hash);
                    if (old != null) {
                        var p = owned("voice_proposal", old, u);
                        expire(p);
                        return new Reply(200, RuntimeContextRegistry.publicView(p));
                    }
                    if (!c.path("runtimeGeneration").equals(body.path("runtimeGeneration")))
                        throw VoiceFailure.conflict("GENERATION_MISMATCH");
                    if (c.path("contextVersion").asLong()
                            != body.path("expectedContextVersion").asLong())
                        throw VoiceFailure.conflict("CONTEXT_CHANGED");
                    String action = body.path("intent").asText().substring(8);
                    r.check(c, action, true);
                    var p = newProposal(c, u, action);
                    s.proposal(p);
                    s.remember(u, "propose", key, hash, p.path("_id").asText());
                    return new Reply(201, RuntimeContextRegistry.publicView(p));
                });
    }

    @PreAuthorize("hasRole('ADMIN')")
    public Reply confirm(String id, String key, ObjectNode body) {
        long u = a.user(true);
        settings.requireEnabled();
        VoiceJson.uuid(key);
        j.validate("ConfirmRequest", body);
        return s.locked(
                () -> {
                    settings.requireEnabled();
                    var p = owned("voice_proposal", id, u);
                    var c = r.require(p.path("plan").path("runtimeRef").asText(), u);
                    String op = "confirm:" + id, hash = j.hash(body);
                    String replay = s.replay(u, op, key, hash);
                    checkPlan(p, body);
                    if ("CONFIRMED".equals(p.path("status").asText())) {
                        if (replay == null) s.remember(u, op, key, hash, id);
                        return new Reply(200, combined(p));
                    }
                    pending(p);
                    var plan = (ObjectNode) p.path("plan");
                    if (!plan.path("runtimeGeneration").equals(c.path("runtimeGeneration"))) {
                        invalidate(p);
                        throw VoiceFailure.conflict("GENERATION_MISMATCH");
                    }
                    if (plan.path("contextVersion").asLong() != c.path("contextVersion").asLong()
                            || !plan.path("explicitDeviceCodes").equals(c.path("_members"))) {
                        invalidate(p);
                        throw VoiceFailure.conflict("CONTEXT_CHANGED");
                    }
                    r.check(c, plan.path("action").asText(), true);
                    if (s.busy(c.path("_id").asText()))
                        throw VoiceFailure.conflict("EXECUTION_IN_PROGRESS");
                    enqueue(p, c, false);
                    s.remember(u, op, key, hash, id);
                    return new Reply(202, combined(p));
                });
    }

    @PreAuthorize("hasRole('ADMIN')")
    public Reply cancel(String id, String key, ObjectNode body) {
        long u = a.user(true);
        settings.requireEnabled();
        VoiceJson.uuid(key);
        j.validate("CancelRequest", body);
        return s.locked(
                () -> {
                    settings.requireEnabled();
                    var p = owned("voice_proposal", id, u);
                    String op = "cancel:" + id, hash = j.hash(body);
                    String replay = s.replay(u, op, key, hash);
                    checkPlan(p, body);
                    if ("CONFIRMED".equals(p.path("status").asText()))
                        throw VoiceFailure.conflict("ALREADY_CONFIRMED");
                    if ("CANCELLED".equals(p.path("status").asText())) {
                        if (replay == null) s.remember(u, op, key, hash, id);
                        return new Reply(200, RuntimeContextRegistry.publicView(p));
                    }
                    pending(p);
                    p.put("status", "CANCELLED");
                    s.save("voice_proposal", p);
                    s.remember(u, op, key, hash, id);
                    return new Reply(200, RuntimeContextRegistry.publicView(p));
                });
    }

    /**
     * Existing authenticated manual route uses the same queue, without masquerading as a voice
     * confirmation.
     */
    @PreAuthorize("hasRole('ADMIN')")
    public ObjectNode manual(String ref, String action) {
        long u = a.user(true);
        if (!Set.of("START", "PAUSE", "RESUME", "STOP").contains(action))
            throw new VoiceFailure(422, "UNSUPPORTED_CAPABILITY");
        return s.locked(
                () -> {
                    var c = r.require(ref, u);
                    r.check(c, action, false);
                    if (s.busy(ref)) throw VoiceFailure.conflict("EXECUTION_IN_PROGRESS");
                    var p = newProposal(c, u, action);
                    p.put("_source", "MANUAL");
                    s.proposal(p);
                    enqueue(p, c, true);
                    s.audit(ref, "MANUAL_ACTION", action, t.stamp());
                    return combined(p);
                });
    }

    private ObjectNode newProposal(ObjectNode c, long u, String action) {
        var plan = j.object();
        plan.put("runtimeRef", c.path("runtimeRef").asText())
                .put("runtimeGeneration", c.path("runtimeGeneration").asText());
        plan.set("contextVersion", c.path("contextVersion"));
        plan.set("stateVersion", c.path("stateVersion"));
        plan.put("action", action);
        plan.set("explicitDeviceCodes", c.path("_members").deepCopy());
        plan.put("policyVersion", "voice-p0.v1");
        var p = j.object();
        String id = VoiceJson.uuid();
        p.put("_id", id)
                .put("_owner", u)
                .put("proposalId", id)
                .put("status", "AWAITING_CONFIRMATION")
                .put("planVersion", 1)
                .put("planHash", j.hash(plan));
        p.set("plan", plan);
        p.put("requiresConfirmation", true)
                .put("createdAt", t.stamp())
                .put("expiresAt", t.now().plusSeconds(30).toString())
                .putNull("executionId");
        return p;
    }

    private void enqueue(ObjectNode p, ObjectNode c, boolean manual) {
        String id = VoiceJson.uuid();
        var e = j.object();
        e.put("_id", id)
                .put("_owner", p.path("_owner").asLong())
                .put("_manual", manual)
                .put("_eventSequence", 0)
                .put("_queryCount", 0);
        e.set("_plan", p.path("plan").deepCopy());
        e.put("executionId", id)
                .put("proposalId", p.path("proposalId").asText())
                .put("commandId", VoiceJson.uuid());
        e.put("runtimeRef", c.path("runtimeRef").asText())
                .put("runtimeGeneration", c.path("runtimeGeneration").asText())
                .put("action", p.path("plan").path("action").asText());
        e.put("state", "QUEUED")
                .put("outcome", "UNKNOWN")
                .putNull("errorCode")
                .putNull("timedOutAt");
        e.put(
                "presentationStatus",
                Set.of("START", "RESUME").contains(e.path("action").asText())
                        ? "PENDING"
                        : "NOT_REQUIRED");
        e.put("createdAt", t.stamp()).put("updatedAt", t.stamp());
        s.execution(e);
        p.put("status", "CONFIRMED").put("executionId", id);
        s.save("voice_proposal", p);
    }

    private ObjectNode combined(ObjectNode p) {
        var result = j.object();
        result.set("proposal", RuntimeContextRegistry.publicView(p));
        result.set(
                "execution",
                executionView(s.get("voice_execution", p.path("executionId").asText())));
        return result;
    }

    private ObjectNode executionView(ObjectNode e) {
        if ("SUCCEEDED".equals(e.path("state").asText())
                && java.util.Set.of("START", "RESUME").contains(e.path("action").asText())
                && "PENDING".equals(e.path("presentationStatus").asText())) {
            String deadline = e.path("_presentationDeadlineAt").asText("");
            // Historical successes have no trustworthy start time: never invent a new window.
            if (deadline.isEmpty() || !t.now().isBefore(java.time.Instant.parse(deadline))) {
                e.put("presentationStatus", "STALE").put("updatedAt", t.stamp());
                s.save("voice_execution", e);
            }
        }
        var v = RuntimeContextRegistry.publicView(e);
        var c = s.get("voice_runtime_context", e.path("runtimeRef").asText());
        if ("REPORTED_APPLIED".equals(v.path("presentationStatus").asText())
                && (!r.freshScene(c) || !e.path("_presentationBinding").equals(c.path("_binding"))))
            v.put("presentationStatus", "STALE");
        return v;
    }

    private ObjectNode owned(String table, String id, long u) {
        VoiceJson.uuid(id);
        var n = s.get(table, id);
        if (n == null || n.path("_owner").asLong() != u)
            throw new VoiceFailure(404, "RESOURCE_NOT_FOUND");
        return n;
    }

    private void checkPlan(ObjectNode p, ObjectNode b) {
        if (b.path("expectedPlanVersion").asInt() != 1
                || !p.path("planHash").equals(b.path("expectedPlanHash")))
            throw VoiceFailure.conflict("PLAN_MISMATCH");
    }

    private void expire(ObjectNode p) {
        if ("AWAITING_CONFIRMATION".equals(p.path("status").asText())
                && !t.now().isBefore(Instant.parse(p.path("expiresAt").asText()))) {
            p.put("status", "EXPIRED");
            s.save("voice_proposal", p);
        }
    }

    private void pending(ObjectNode p) {
        expire(p);
        String status = p.path("status").asText();
        if (!"AWAITING_CONFIRMATION".equals(status))
            throw VoiceFailure.conflict("PROPOSAL_" + status);
    }

    private void invalidate(ObjectNode p) {
        p.put("status", "INVALIDATED");
        s.save("voice_proposal", p);
    }
}
