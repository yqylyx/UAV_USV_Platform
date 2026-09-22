package com.uavusv.platform.module.voicecontrol;

import static org.junit.jupiter.api.Assertions.*;
import static org.mockito.Mockito.*;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.uavusv.platform.module.mission.repository.MissionRunRepository;
import com.uavusv.platform.module.mission.service.*;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.condition.EnabledIfEnvironmentVariable;
import org.springframework.test.util.ReflectionTestUtils;
import java.nio.file.*;
import java.util.*;
import java.util.function.BooleanSupplier;

/** Real Java process manager and Python adapter; fresh H2, no HTTP or Unity simulation. */
@EnabledIfEnvironmentVariable(named = "P0_REAL_RUNNER", matches = ".+")
class VoiceRealRunnerTests extends VoiceControlTests {
    private void until(BooleanSupplier condition, String reason) throws Exception {
        long end = System.nanoTime() + 10_000_000_000L;
        while (!condition.getAsBoolean()) {
            if (System.nanoTime() >= end) fail(reason);
            Thread.sleep(25);
        }
    }

    @Test
    void realRunnerReadyHeartbeatAndFourActions() throws Exception {
        var runner = Path.of(System.getenv("P0_REAL_RUNNER")).toAbsolutePath();
        assertTrue(Files.isRegularFile(runner), "Runner file missing");
        var report = j.object().put("runner", runner.toString()).put("startedAt", java.time.Instant.now().toString());
        var steps = report.putArray("actions");
        var manager = new AlgorithmRuntimeManager(new ObjectMapper(), mock(MissionRunRepository.class),
                mock(AlgorithmCatalogService.class), System.getenv().getOrDefault("PYTHON_COMMAND", "python"), runner.toString());
        ReflectionTestUtils.setField(manager, "voiceBridge", new VoiceRuntimeBridge(r, app, worker, j));
        try {
            var prepared = manager.prepare(990031L, "GB_SFLA_CS",
                    Map.<String, Object>of("standaloneVirtualSimulation", true, "seed", 42));
            report.set("prepare", j.mapper.valueToTree(prepared));
            assertEquals("PREPARED", prepared.state());
            assertEquals(RuntimeContextRegistry.PROTOCOL, prepared.protocolVersion());
            assertEquals(List.of("START", "PAUSE", "RESUME", "STOP"), prepared.capabilities());
            String ref = prepared.runtimeRef();
            String generation = prepared.runtimeGeneration();
            UUID.fromString(ref); UUID.fromString(generation);
            until(() -> r.channel(ref).heartbeatNanos != null, "No real heartbeat received");
            report.set("contextAfterHeartbeat", app.context(ref()));
            var expected = new TreeSet<String>();
            for (var agent : prepared.latestFrame().path("agents")) {
                String code = agent.path("deviceCode").asText();
                assertTrue(code.matches("[A-Za-z0-9_.:-]{1,96}"),
                        "Real adapter frame missing valid deviceCode; legacy code=" + agent.path("code").asText());
                expected.add(code);
            }
            assertFalse(expected.isEmpty(), "Empty authoritative device membership");
            var commandIds = new HashSet<String>();
            int version = 0;
            for (String action : List.of("START", "PAUSE", "RESUME", "STOP")) {
                manager.action(990031L, action);
                var executions = s.locked(() -> s.query(
                        "SELECT data_json FROM voice_execution WHERE runtime_ref=?", ref));
                var e = executions.stream().filter(x -> action.equals(x.path("action").asText())).findFirst().orElseThrow();
                String id = e.path("executionId").asText();
                assertTrue(commandIds.add(e.path("commandId").asText()));
                worker.tick();
                until(() -> "SUCCEEDED".equals(app.execution(id).path("state").asText()),
                        action + " did not reach SUCCEEDED: " + app.execution(id));
                var actual = app.execution(id);
                steps.add(actual);
                assertEquals("SUCCESS", actual.path("outcome").asText());
                assertEquals(generation, actual.path("runtimeGeneration").asText());
                var receipts = s.locked(() -> s.query(
                        "SELECT data_json FROM voice_command_event WHERE execution_id=? ORDER BY event_sequence", id));
                var success = receipts.stream().filter(x -> "SUCCEEDED".equals(x.path("status").asText())).findFirst().orElseThrow();
                assertTrue(receipts.stream().anyMatch(x -> "ACCEPTED".equals(x.path("status").asText())));
                assertEquals(e.path("commandId"), success.path("commandId"));
                assertEquals(ref, success.path("runtimeRef").asText());
                assertEquals(generation, success.path("runtimeGeneration").asText());
                assertEquals(j.mapper.valueToTree(expected), success.path("affectedDeviceCodes"));
                assertEquals(++version, success.path("stateVersion").asInt());
                String target = action.equals("PAUSE") ? "PAUSED" : action.equals("STOP") ? "STOPPED" : "RUNNING";
                assertEquals(target, success.path("runtimeState").asText());
                assertEquals(target, app.context(ref).path("state").asText());
                report.set(action + "Receipts", j.mapper.valueToTree(receipts));
                if (action.equals("PAUSE")) {
                    long previous = s.locked(() -> s.get("voice_runtime_context", ref)).path("_heartbeatSequence").asLong();
                    until(() -> s.locked(() -> s.get("voice_runtime_context", ref)).path("_heartbeatSequence").asLong() > previous,
                            "No heartbeat while paused");
                }
            }
            until(() -> !r.channel(ref).alive.getAsBoolean(), "Runner did not exit after STOP receipt");
            report.put("result", "PASS");
        } catch (Exception | AssertionError failure) {
            report.put("result", "FAIL").put("failure", failure.toString());
            throw failure;
        } finally {
            manager.close();
            var output = Path.of("target/p0-real-runner-report.json");
            Files.createDirectories(output.getParent());
            j.mapper.writerWithDefaultPrettyPrinter().writeValue(output.toFile(), report);
        }
    }
}

