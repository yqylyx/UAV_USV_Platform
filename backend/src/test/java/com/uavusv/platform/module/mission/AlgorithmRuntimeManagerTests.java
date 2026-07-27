package com.uavusv.platform.module.mission;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.uavusv.platform.module.mission.dto.response.AlgorithmRuntimeStatusResponse;
import com.uavusv.platform.module.mission.service.AlgorithmRuntimeManager;
import org.junit.jupiter.api.Test;

import java.nio.file.Path;
import java.util.Map;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertTrue;

class AlgorithmRuntimeManagerTests {

    @Test
    void shouldRunCaptureAdapterAndExposeAuthoritativeFrame() throws Exception {
        Path runner = Path.of("..", "algorithm-service", "runner.py").toAbsolutePath().normalize();
        AlgorithmRuntimeManager manager = new AlgorithmRuntimeManager(
                new ObjectMapper(),
                "python",
                runner.toString()
        );
        try {
            AlgorithmRuntimeStatusResponse prepared = manager.prepare(
                    91001L,
                    "GB_SFLA_CS",
                    Map.of("seed", 42, "targetBehavior", "STATIC")
            );
            assertEquals("PREPARED", prepared.state());
            manager.action(91001L, "START");

            JsonNode frame = null;
            for (int attempt = 0; attempt < 60 && frame == null; attempt++) {
                Thread.sleep(100);
                frame = manager.latestFrame(91001L, 0);
            }
            assertNotNull(frame);
            assertEquals("GB_SFLA_CS", frame.path("algorithmCode").asText());
            assertEquals(6, frame.path("agents").size());
            assertEquals(2, frame.path("targets").size());
            assertFalse(manager.framesAfter(91001L, 0).isEmpty());
            long observedSequence = frame.path("sequence").asLong();
            assertTrue(manager.framesAfter(91001L, observedSequence).stream()
                    .allMatch(bufferedFrame -> bufferedFrame.path("sequence").asLong() > observedSequence));

            long sequenceBeforeRepeatedPrepare = observedSequence;
            AlgorithmRuntimeStatusResponse repeatedPrepare = manager.prepare(
                    91001L,
                    "GB_SFLA_CS",
                    Map.of("seed", 42, "targetBehavior", "STATIC")
            );
            assertEquals("RUNNING", repeatedPrepare.state());
            assertTrue(repeatedPrepare.latestSequence() >= sequenceBeforeRepeatedPrepare);
        } finally {
            try { manager.action(91001L, "CANCEL"); } catch (RuntimeException ignored) {}
            manager.close();
        }
    }
}
