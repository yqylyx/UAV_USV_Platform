package com.uavusv.platform.module.mission;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.uavusv.platform.common.exception.BusinessException;
import com.uavusv.platform.common.exception.ErrorCode;
import com.uavusv.platform.module.mission.dto.response.AlgorithmRuntimeStatusResponse;
import com.uavusv.platform.module.mission.entity.AlgorithmDefinition;
import com.uavusv.platform.module.mission.entity.MissionRun;
import com.uavusv.platform.module.mission.entity.MissionStage;
import com.uavusv.platform.module.mission.repository.MissionRunRepository;
import com.uavusv.platform.module.mission.service.AlgorithmCatalogService;
import com.uavusv.platform.module.mission.service.AlgorithmRuntimeManager;
import org.junit.jupiter.api.Test;

import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.Map;
import java.util.Optional;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.verifyNoInteractions;
import static org.mockito.Mockito.when;

class AlgorithmRuntimeManagerTests {

    @Test
    void shouldRunCaptureAdapterAndExposeAuthoritativeFrame() throws Exception {
        long runId = 91001L;
        MissionRunRepository runRepository = mock(MissionRunRepository.class);
        AlgorithmCatalogService catalogService = mock(AlgorithmCatalogService.class);
        when(runRepository.findById(runId)).thenReturn(Optional.of(run("GB_SFLA_CS")));
        when(catalogService.requireEnabled("GB_SFLA_CS")).thenReturn(mock(AlgorithmDefinition.class));
        AlgorithmRuntimeManager manager = manager(runRepository, catalogService);
        try {
            AlgorithmRuntimeStatusResponse prepared = manager.prepare(
                    runId,
                    "GB_SFLA_CS",
                    Map.of("seed", 42, "targetBehavior", "STATIC")
            );
            assertEquals("PREPARED", prepared.state());
            manager.action(runId, "START");

            JsonNode frame = null;
            for (int attempt = 0; attempt < 60 && frame == null; attempt++) {
                Thread.sleep(100);
                frame = manager.latestFrame(runId, 0);
            }
            assertNotNull(frame);
            assertEquals("GB_SFLA_CS", frame.path("algorithmCode").asText());
            assertEquals(6, frame.path("agents").size());
            // A 3+3 active-capture run intentionally owns one moving enemy.
            // Additional enemies are introduced only by the adaptive scale thresholds.
            assertEquals(1, frame.path("targets").size());
            assertFalse(manager.framesAfter(runId, 0).isEmpty());
            long observedSequence = frame.path("sequence").asLong();
            assertTrue(manager.framesAfter(runId, observedSequence).stream()
                    .allMatch(bufferedFrame -> bufferedFrame.path("sequence").asLong() > observedSequence));

            long sequenceBeforeRepeatedPrepare = observedSequence;
            AlgorithmRuntimeStatusResponse repeatedPrepare = manager.prepare(
                    runId,
                    "GB_SFLA_CS",
                    Map.of("seed", 42, "targetBehavior", "STATIC")
            );
            assertEquals("RUNNING", repeatedPrepare.state());
            assertTrue(repeatedPrepare.latestSequence() >= sequenceBeforeRepeatedPrepare);
        } finally {
            try { manager.action(runId, "CANCEL"); } catch (RuntimeException ignored) {}
            manager.close();
        }
    }

    @Test
    void shouldRejectUnknownRunBeforeStartingAlgorithm() {
        MissionRunRepository runRepository = mock(MissionRunRepository.class);
        AlgorithmCatalogService catalogService = mock(AlgorithmCatalogService.class);
        when(runRepository.findById(404L)).thenReturn(Optional.empty());
        AlgorithmRuntimeManager manager = manager(runRepository, catalogService);

        BusinessException exception = assertThrows(
                BusinessException.class,
                () -> manager.prepare(404L, "GB_SFLA_CS", Map.of())
        );

        assertEquals(ErrorCode.NOT_FOUND, exception.getErrorCode());
        assertEquals("任务运行批次不存在：404", exception.getMessage());
        verifyNoInteractions(catalogService);
    }

    @Test
    void shouldRejectAlgorithmThatDoesNotMatchRunSnapshot() {
        MissionRunRepository runRepository = mock(MissionRunRepository.class);
        AlgorithmCatalogService catalogService = mock(AlgorithmCatalogService.class);
        when(runRepository.findById(15L)).thenReturn(Optional.of(run("GB_SFLA_CS")));
        AlgorithmRuntimeManager manager = manager(runRepository, catalogService);

        BusinessException exception = assertThrows(
                BusinessException.class,
                () -> manager.prepare(15L, "ESCORT_GUARD", Map.of())
        );

        assertEquals(ErrorCode.BAD_REQUEST, exception.getErrorCode());
        assertEquals(
                "算法代码与任务运行快照不一致：请求=ESCORT_GUARD，运行快照=GB_SFLA_CS",
                exception.getMessage()
        );
        verifyNoInteractions(catalogService);
    }

    @Test
    void shouldRejectDisabledCatalogAlgorithm() {
        MissionRunRepository runRepository = mock(MissionRunRepository.class);
        AlgorithmCatalogService catalogService = mock(AlgorithmCatalogService.class);
        when(runRepository.findById(16L)).thenReturn(Optional.of(run("GB_SFLA_CS")));
        when(catalogService.requireEnabled("GB_SFLA_CS")).thenThrow(
                new BusinessException(ErrorCode.BAD_REQUEST, "所选算法已停用：GB_SFLA_CS")
        );
        AlgorithmRuntimeManager manager = manager(runRepository, catalogService);

        BusinessException exception = assertThrows(
                BusinessException.class,
                () -> manager.prepare(16L, "GB_SFLA_CS", Map.of())
        );

        assertEquals(ErrorCode.BAD_REQUEST, exception.getErrorCode());
        assertEquals("所选算法已停用：GB_SFLA_CS", exception.getMessage());
    }

    private AlgorithmRuntimeManager manager(
            MissionRunRepository runRepository,
            AlgorithmCatalogService catalogService
    ) {
        Path runner = Path.of("..", "algorithm-service", "runner.py").toAbsolutePath().normalize();
        return new AlgorithmRuntimeManager(
                new ObjectMapper(),
                runRepository,
                catalogService,
                resolvePythonExecutable(),
                runner.toString()
        );
    }

    private String resolvePythonExecutable() {
        String configured = System.getenv("ALGORITHM_PYTHON");
        if (configured != null && !configured.isBlank()) {
            return configured;
        }
        String locator = System.getProperty("os.name", "").toLowerCase().contains("win")
                ? "where.exe"
                : "which";
        try {
            Process process = new ProcessBuilder(locator, "python").redirectErrorStream(true).start();
            try (var reader = process.inputReader()) {
                String candidate;
                while ((candidate = reader.readLine()) != null) {
                    Path path = Path.of(candidate.trim());
                    if (Files.isRegularFile(path) && !path.toString().contains("WindowsApps")) {
                        return path.toString();
                    }
                }
            }
        } catch (IOException ignored) {
            // Portable fallback for environments where the locator command is
            // unavailable but python itself is executable from PATH.
        }
        return "python";
    }

    private MissionRun run(String algorithmCode) {
        return new MissionRun(
                1L,
                null,
                1,
                MissionStage.PREPARE,
                "test",
                "mission-unity-test",
                algorithmCode,
                "2026.07.27"
        );
    }
}
