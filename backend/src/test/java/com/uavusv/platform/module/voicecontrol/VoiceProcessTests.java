package com.uavusv.platform.module.voicecontrol;

import static org.junit.jupiter.api.Assertions.*;
import static org.mockito.Mockito.*;

import com.fasterxml.jackson.databind.ObjectMapper;
import com.uavusv.platform.module.mission.repository.MissionRunRepository;
import com.uavusv.platform.module.mission.service.*;

import org.junit.jupiter.api.Test;
import org.springframework.test.util.ReflectionTestUtils;

import java.nio.file.Path;
import java.time.Duration;
import java.util.Map;
import java.util.concurrent.locks.LockSupport;

class VoiceProcessTests extends VoiceControlTests {
    @Test
    void existingManagerNegotiatesPipesAndSerializesFourManualActions() throws Exception {
        alive.set(false);
        r.ended(ref(), gen());
        var catalog = mock(AlgorithmCatalogService.class);
        var manager =
                new AlgorithmRuntimeManager(
                        new ObjectMapper(),
                        mock(MissionRunRepository.class),
                        catalog,
                        System.getenv().getOrDefault("PYTHON_COMMAND", "python"),
                        Path.of("src/test/resources/voicecontrol/contract_runner.py")
                                .toAbsolutePath()
                                .toString());
        var bridge = new VoiceRuntimeBridge(r, app, worker, j);
        ReflectionTestUtils.setField(manager, "voiceBridge", bridge);
        try {
            var config = Map.<String, Object>of("standaloneVirtualSimulation", true, "dt", 0.1);
            var prepared = manager.prepare(9001L, "GB_SFLA_CS", config);
            assertEquals("PREPARED", prepared.state());
            assertEquals(RuntimeContextRegistry.PROTOCOL, prepared.protocolVersion());
            assertEquals(java.util.List.of("START", "PAUSE", "RESUME", "STOP"), prepared.capabilities());
            var serialized = new ObjectMapper().valueToTree(prepared);
            assertEquals(10, serialized.size());
            assertEquals(9001L, serialized.path("runId").asLong());
            assertNotNull(prepared.latestFrame());
            assertTrue(prepared.latestSequence() >= 1);
            var contexts = app.contexts();
            var run =
                    contexts.stream()
                            .filter(n -> n.path("algorithmRunId").asText().equals("9001"))
                            .findFirst()
                            .orElseThrow();
            String ref = run.path("runtimeRef").asText();
            assertEquals(ref, prepared.runtimeRef());
            assertEquals(run.path("runtimeGeneration").asText(), prepared.runtimeGeneration());
            var repeated = manager.prepare(9001L, "GB_SFLA_CS", config);
            assertEquals(prepared.runtimeRef(), repeated.runtimeRef());
            assertEquals(prepared.runtimeGeneration(), repeated.runtimeGeneration());
            assertEquals(prepared.capabilities(), manager.status(9001L).capabilities());
            assertTimeoutPreemptively(
                    Duration.ofSeconds(5),
                    () -> {
                        while (r.channel(ref).heartbeatNanos == null)
                            LockSupport.parkNanos(1_000_000);
                    });
            int before = count("voice_execution");
            for (String action : new String[] {"START", "PAUSE", "RESUME", "STOP"}) {
                manager.action(9001L, action);
                worker.tick();
                assertTimeoutPreemptively(
                        Duration.ofSeconds(5),
                        () -> {
                            while (s
                                    .locked(
                                            () ->
                                                    s.query(
                                                            "SELECT data_json FROM voice_execution"
                                                                + " WHERE runtime_ref=?",
                                                            ref))
                                    .stream()
                                    .anyMatch(e -> !e.path("state").asText().equals("SUCCEEDED")))
                                LockSupport.parkNanos(1_000_000);
                        });
            }
            assertEquals(before + 4, count("voice_execution"));
            assertEquals(8, count("voice_command_event"));
            var executions =
                    s.locked(
                            () ->
                                    s.query(
                                            "SELECT data_json FROM voice_execution WHERE"
                                                + " runtime_ref=?",
                                            ref));
            assertTrue(
                    executions.stream()
                            .allMatch(e -> e.path("outcome").asText().equals("SUCCESS")));
            VoiceControlTests.login("bob");
            error("RESOURCE_NOT_FOUND", () -> manager.status(9001L));
            error("RUNTIME_BUSY", () -> manager.prepare(9001L, "GB_SFLA_CS", config));
        } finally {
            VoiceControlTests.login("alice");
            manager.close();
        }
    }
    @Test
    void prepareExposesOnlyNegotiatedSubsetAndReplacesIdentityWithNewProcess() throws Exception {
        alive.set(false);
        r.ended(ref(), gen());
        var manager = new AlgorithmRuntimeManager(new ObjectMapper(), mock(MissionRunRepository.class),
                mock(AlgorithmCatalogService.class), System.getenv().getOrDefault("PYTHON_COMMAND", "python"),
                Path.of("src/test/resources/voicecontrol/contract_runner.py").toAbsolutePath().toString());
        ReflectionTestUtils.setField(manager, "voiceBridge", new VoiceRuntimeBridge(r, app, worker, j));
        try {
            var config = Map.<String, Object>of("standaloneVirtualSimulation", true,
                    "testCapabilities", java.util.List.of("START", "STOP"));
            var first = manager.prepare(9002L, "GB_SFLA_CS", config);
            assertEquals(java.util.List.of("START", "STOP"), first.capabilities());
            var second = manager.prepare(9003L, "GB_SFLA_CS", config);
            assertNotEquals(first.runtimeRef(), second.runtimeRef());
            assertNotEquals(first.runtimeGeneration(), second.runtimeGeneration());
            assertEquals(first.capabilities(), second.capabilities());
        } finally { manager.close(); }
    }

    @Test
    void failedStartupDoesNotReturnSuccessfulPrepareMetadata() throws Exception {
        alive.set(false);
        r.ended(ref(), gen());
        var manager = new AlgorithmRuntimeManager(new ObjectMapper(), mock(MissionRunRepository.class),
                mock(AlgorithmCatalogService.class), System.getenv().getOrDefault("PYTHON_COMMAND", "python"),
                Path.of("src/test/resources/voicecontrol/contract_runner.py").toAbsolutePath().toString());
        ReflectionTestUtils.setField(manager, "voiceBridge", new VoiceRuntimeBridge(r, app, worker, j));
        try {
            assertThrows(com.uavusv.platform.common.exception.BusinessException.class,
                    () -> manager.prepare(9004L, "GB_SFLA_CS",
                            Map.of("standaloneVirtualSimulation", true, "testFailBeforeReady", true)));
        } finally { manager.close(); }
    }

    @Test
    void statusSnapshotChecksOwnerAndGenerationAndDoesNotInventNegotiation() {
        var bridge = new VoiceRuntimeBridge(r, app, worker, j);
        var pending = r.register(9005L, "pending");
        var snapshot = bridge.statusSnapshot(pending);
        assertFalse(snapshot.path("_ready").asBoolean());
        assertTrue(snapshot.path("capabilities").isEmpty());
        var stale = pending.deepCopy().put("runtimeGeneration", VoiceJson.uuid());
        error("GENERATION_MISMATCH", () -> bridge.statusSnapshot(stale));
        login("bob");
        error("RESOURCE_NOT_FOUND", () -> bridge.statusSnapshot(pending));
    }

}
