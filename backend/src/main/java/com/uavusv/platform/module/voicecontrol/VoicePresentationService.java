package com.uavusv.platform.module.voicecontrol;

import com.fasterxml.jackson.databind.node.ObjectNode;

import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.stereotype.Service;

import java.time.Instant;

/** Authenticated browser evidence, never a source of algorithm success. */
@Service
@PreAuthorize("isAuthenticated()")
public class VoicePresentationService {
    private final VoiceStore s;
    private final VoiceJson j;
    private final VoiceTime t;
    private final VoiceAccess a;
    private final RuntimeContextRegistry r;

    public VoicePresentationService(
            VoiceStore s, VoiceJson j, VoiceTime t, VoiceAccess a, RuntimeContextRegistry r) {
        this.s = s;
        this.j = j;
        this.t = t;
        this.a = a;
        this.r = r;
    }

    public ObjectNode binding(String ref) {
        long u = a.user(false);
        return s.locked(
                () -> {
                    var c = r.require(ref, u);
                    var v = j.object();
                    v.set(
                            "bindingId",
                            c.path("_binding").isMissingNode()
                                    ? j.mapper.nullNode()
                                    : c.path("_binding"));
                    v.set("runtimeGeneration", c.path("runtimeGeneration"));
                    return v;
                });
    }

    public ObjectNode bind(String ref, String key, ObjectNode body) {
        long u = a.user(false);
        VoiceJson.uuid(key);
        j.validate("PresentationBindingRequest", body);
        return s.locked(
                () -> {
                    var c = r.require(ref, u);
                    generation(c, body);
                    String op = "bind:" + ref, hash = j.hash(body);
                    String old = s.replay(u, op, key, hash);
                    if (old != null) {
                        if (!old.equals(c.path("_binding").asText()))
                            throw VoiceFailure.conflict("CONTEXT_CHANGED");
                        return bindingView(c);
                    }
                    String current = c.path("_binding").asText("");
                    if (!current.equals(body.path("expectedBindingId").asText("")))
                        throw VoiceFailure.conflict("CONTEXT_CHANGED");
                    String id = VoiceJson.uuid();
                    c.put("_binding", id).put("_sceneSequence", 0);
                    c.remove("_challenge");
                    var ch = r.channel(ref);
                    if (ch != null) ch.sceneNanos = null;
                    s.save("voice_runtime_context", c);
                    s.remember(u, op, key, hash, id);
                    return bindingView(c);
                });
    }

    public ObjectNode challenge(String ref, String key, ObjectNode body) {
        long u = a.user(false);
        VoiceJson.uuid(key);
        j.validate("PresentationChallengeRequest", body);
        return s.locked(
                () -> {
                    var c = r.require(ref, u);
                    generation(c, body);
                    binding(c, body);
                    String op = "challenge:" + ref, hash = j.hash(body);
                    String old = s.replay(u, op, key, hash);
                    if (old != null) {
                        if (!old.equals(c.path("_challenge").path("requestId").asText()))
                            throw VoiceFailure.conflict("CONTEXT_CHANGED");
                        return ((ObjectNode) c.path("_challenge")).deepCopy();
                    }
                    if ("FRAME_APPLIED".equals(body.path("kind").asText())) {
                        var e = s.get("voice_execution", body.path("executionId").asText());
                        if (e == null
                                || e.path("_owner").asLong() != u
                                || !ref.equals(e.path("runtimeRef").asText()))
                            throw new VoiceFailure(404, "RESOURCE_NOT_FOUND");
                        if (!"SUCCEEDED".equals(e.path("state").asText())
                                || !java.util.Set.of("START", "RESUME")
                                        .contains(e.path("action").asText()))
                            throw VoiceFailure.conflict("INVALID_STATE");
                    }
                    var q = body.deepCopy();
                    q.put("requestId", VoiceJson.uuid())
                            .put("sequence", c.path("_sceneSequence").asLong() + 1)
                            .put("expiresAt", t.now().plusSeconds(5).toString());
                    c.set("_challenge", q);
                    c.put("_challengeUsed", false);
                    s.save("voice_runtime_context", c);
                    s.remember(u, op, key, hash, q.path("requestId").asText());
                    return q;
                });
    }

    public ObjectNode report(String ref, String key, ObjectNode body) {
        long u = a.user(false);
        VoiceJson.uuid(key);
        j.validate("PresentationReportRequest", body);
        return s.locked(
                () -> {
                    var c = r.require(ref, u);
                    generation(c, body);
                    binding(c, body);
                    String op = "report:" + ref, hash = j.hash(body);
                    String old = s.replay(u, op, key, hash);
                    if (old != null)
                        return r.view(c); // Replaying evidence never refreshes its age.
                    var q = c.path("_challenge");
                    if (!q.path("requestId").equals(body.path("requestId"))
                            || q.path("sequence").asLong() != body.path("sequence").asLong()
                            || !q.path("kind").equals(body.path("kind"))
                            || !q.path("executionId").equals(body.path("executionId")))
                        throw VoiceFailure.conflict("CONTEXT_CHANGED");
                    if (c.path("_challengeUsed").asBoolean()
                            || !t.now().isBefore(Instant.parse(q.path("expiresAt").asText())))
                        throw VoiceFailure.conflict("SCENE_NOT_READY");
                    long frame = body.path("frameSequence").asLong();
                    if (frame > c.path("latestFrameSequence").asLong()) throw VoiceFailure.bad();
                    var ch = r.channel(ref);
                    if (ch == null || !ch.alive.getAsBoolean())
                        throw VoiceFailure.conflict("RUNTIME_UNAVAILABLE");
                    if ("FRAME_APPLIED".equals(body.path("kind").asText())) {
                        var e = s.get("voice_execution", body.path("executionId").asText());
                        if (e == null
                                || !"SUCCEEDED".equals(e.path("state").asText())
                                || frame < e.path("_resultFrame").asLong())
                            throw VoiceFailure.conflict("CONTEXT_CHANGED");
                        if (body.path("applied").asBoolean()) {
                            e.put("presentationStatus", "REPORTED_APPLIED");
                            e.set("_presentationBinding", c.path("_binding"));
                            e.put("updatedAt", t.stamp());
                            s.save("voice_execution", e);
                        }
                    }
                    c.put("_challengeUsed", true)
                            .put("_sceneSequence", body.path("sequence").asLong());
                    ch.sceneNanos = body.path("applied").asBoolean() ? t.nanos() : null;
                    s.save("voice_runtime_context", c);
                    s.remember(u, op, key, hash, body.path("requestId").asText());
                    return r.view(c);
                });
    }

    private void generation(ObjectNode c, ObjectNode b) {
        if (!c.path("runtimeGeneration").equals(b.path("runtimeGeneration")))
            throw VoiceFailure.conflict("GENERATION_MISMATCH");
    }

    private void binding(ObjectNode c, ObjectNode b) {
        if (!c.path("_binding").equals(b.path("bindingId")))
            throw VoiceFailure.conflict("CONTEXT_CHANGED");
    }

    private ObjectNode bindingView(ObjectNode c) {
        var v = j.object();
        v.set("bindingId", c.path("_binding"));
        v.set("runtimeGeneration", c.path("runtimeGeneration"));
        return v;
    }
}
