package com.uavusv.platform.module.voicecontrol;

import static org.junit.jupiter.api.Assertions.*;
import org.junit.jupiter.api.Test;
import org.springframework.core.io.ClassPathResource;
import com.fasterxml.jackson.databind.node.ObjectNode;

/** Captured real adapter frame: Python commit 0577987, run 990022. */
class VoiceDeviceMembershipTests extends VoiceControlTests {
    ObjectNode realFrame() throws Exception {
        try (var input = new ClassPathResource("voicecontrol/real-adapter-code-frame.json").getInputStream()) {
            return (ObjectNode) j.mapper.readTree(input);
        }
    }

    @Test
    void codeOnlyRealFrameRejectsActionWithoutEnqueueing() throws Exception {
        var frame = realFrame();
        frame.put("sequence", 2);
        r.frame(ref(), gen(), frame);
        int before = count("voice_execution");
        error("CONTEXT_CHANGED", () -> app.manual(ref(), "PAUSE"));
        assertEquals(before, count("voice_execution"));
        assertTrue(sent.isEmpty());
    }

    @Test
    void canonicalDeviceCodesBecomeTheExactCommandMembership() throws Exception {
        var frame = realFrame();
        frame.put("sequence", 2);
        var expected = new java.util.TreeSet<String>();
        for (var agent : frame.path("agents")) {
            String code = agent.path("code").asText();
            ((ObjectNode) agent).put("deviceCode", code);
            expected.add(code);
        }
        r.frame(ref(), gen(), frame);
        var combined = app.manual(ref(), "PAUSE");
        assertEquals(j.mapper.valueToTree(expected),
                combined.path("proposal").path("plan").path("explicitDeviceCodes"));
        assertEquals(6, expected.size());
    }

    @Test
    void emptySuccessfulReceiptCannotSettleOrAdvanceRuntime() {
        var e = execution(app.manual(ref(), "PAUSE"));
        worker.tick();
        var n = event("COMMAND_RESULT");
        n.set("commandId", e.path("commandId"));
        n.put("eventSequence", 1).put("status", "SUCCEEDED")
                .put("runtimeState", "PAUSED").put("stateVersion", 4)
                .put("lastFrameSequence", 1).putNull("errorCode");
        n.putArray("affectedDeviceCodes");
        worker.receive(ref(), gen(), n);
        assertEquals("DISPATCHED", app.execution(e.path("executionId").asText()).path("state").asText());
        assertEquals("RUNNING", app.context(ref()).path("state").asText());
        assertEquals(0, count("voice_command_event"));
    }
}
