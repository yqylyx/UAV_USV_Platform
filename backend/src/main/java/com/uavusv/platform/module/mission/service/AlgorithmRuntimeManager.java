package com.uavusv.platform.module.mission.service;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.uavusv.platform.common.exception.BusinessException;
import com.uavusv.platform.common.exception.ErrorCode;
import com.uavusv.platform.module.mission.dto.response.AlgorithmRuntimeStatusResponse;
import jakarta.annotation.PreDestroy;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Service;

import java.io.BufferedReader;
import java.io.BufferedWriter;
import java.io.IOException;
import java.io.InputStreamReader;
import java.io.OutputStreamWriter;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.ArrayList;
import java.util.ArrayDeque;
import java.util.Base64;
import java.util.Deque;
import java.util.List;
import java.util.Map;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicLong;
import java.util.concurrent.atomic.AtomicReference;

@Service
public class AlgorithmRuntimeManager {
    private final ObjectMapper objectMapper;
    private final String pythonCommand;
    private final Path runnerPath;
    private final Map<Long, RuntimeHandle> handles = new ConcurrentHashMap<>();

    public AlgorithmRuntimeManager(
            ObjectMapper objectMapper,
            @Value("${app.algorithm.python-command:python}") String pythonCommand,
            @Value("${app.algorithm.runner-path:../algorithm-service/runner.py}") String runnerPath
    ) {
        this.objectMapper = objectMapper;
        this.pythonCommand = pythonCommand;
        this.runnerPath = resolveRunnerPath(runnerPath);
    }

    public synchronized AlgorithmRuntimeStatusResponse prepare(Long runId, String algorithmCode, Map<String, Object> config) {
        if ("UNITY_SIMPLE_ENCIRCLEMENT".equals(algorithmCode)) {
            return new AlgorithmRuntimeStatusResponse(runId, algorithmCode, "UNITY_NATIVE", 0, null, null);
        }
        if (!List.of("GB_SFLA_CS", "ESCORT_GUARD").contains(algorithmCode)) {
            throw new BusinessException(ErrorCode.BAD_REQUEST, "不支持的外部算法：" + algorithmCode);
        }
        RuntimeHandle existing = handles.get(runId);
        if (existing != null
                && existing.process.isAlive()
                && algorithmCode.equals(existing.algorithmCode)
                && existing.error.get() == null) {
            return status(runId);
        }
        stopExisting(runId);
        if (!Files.isRegularFile(runnerPath)) {
            throw new BusinessException(ErrorCode.BAD_REQUEST, "算法运行器不存在：" + runnerPath);
        }
        try {
            List<String> command = new ArrayList<>();
            command.add(pythonCommand);
            command.add(runnerPath.toString());
            command.add("--algorithm");
            command.add(algorithmCode);
            command.add("--run-id");
            command.add(String.valueOf(runId));
            command.add("--config-base64");
            command.add(Base64.getEncoder().encodeToString(
                    objectMapper.writeValueAsBytes(config == null ? Map.of() : config)
            ));
            command.add("--fps");
            command.add("10");
            ProcessBuilder builder = new ProcessBuilder(command);
            builder.directory(runnerPath.getParent().toFile());
            builder.environment().put("PYTHONUTF8", "1");
            builder.environment().put("PYTHONUNBUFFERED", "1");
            builder.environment().put("MPLCONFIGDIR", Path.of(System.getProperty("java.io.tmpdir"), "uav-usv-matplotlib").toString());
            Process process = builder.start();
            RuntimeHandle handle = new RuntimeHandle(runId, algorithmCode, process,
                    new BufferedWriter(new OutputStreamWriter(process.getOutputStream(), StandardCharsets.UTF_8)));
            handles.put(runId, handle);
            startReaders(handle);
            if (!handle.ready.await(12, TimeUnit.SECONDS)) {
                stopExisting(runId);
                throw new BusinessException(ErrorCode.BAD_REQUEST, "算法运行器启动超时");
            }
            if (handle.error.get() != null) {
                stopExisting(runId);
                throw new BusinessException(ErrorCode.BAD_REQUEST, "算法运行器启动失败：" + handle.error.get());
            }
            return status(runId);
        } catch (IOException exception) {
            throw new BusinessException(ErrorCode.BAD_REQUEST, "无法启动算法运行器：" + exception.getMessage());
        } catch (InterruptedException exception) {
            Thread.currentThread().interrupt();
            throw new BusinessException(ErrorCode.BAD_REQUEST, "等待算法运行器时被中断");
        }
    }

    public AlgorithmRuntimeStatusResponse action(Long runId, String action) {
        RuntimeHandle handle = requireHandle(runId);
        String normalized = action.toUpperCase();
        if (!List.of("START", "PAUSE", "RESUME", "CANCEL", "STOP").contains(normalized)) {
            throw new BusinessException(ErrorCode.BAD_REQUEST, "不支持的算法运行指令：" + action);
        }
        send(handle, Map.of("action", normalized));
        if ("CANCEL".equals(normalized)) handle.state.set("CANCELLED");
        if ("STOP".equals(normalized)) handle.state.set("STOPPED");
        return status(runId);
    }

    public AlgorithmRuntimeStatusResponse placeThreat(Long runId, double x, double y) {
        RuntimeHandle handle = requireHandle(runId);
        if (!"ESCORT_GUARD".equals(handle.algorithmCode)) {
            throw new BusinessException(ErrorCode.BAD_REQUEST, "只有护航守卫算法支持动态放置威胁目标");
        }
        send(handle, Map.of("action", "PLACE_THREAT", "x", x, "y", y));
        return status(runId);
    }

    public AlgorithmRuntimeStatusResponse status(Long runId) {
        RuntimeHandle handle = requireHandle(runId);
        return new AlgorithmRuntimeStatusResponse(runId, handle.algorithmCode, handle.state.get(),
                handle.latestSequence.get(), handle.error.get(), handle.latestFrame.get());
    }

    public JsonNode latestFrame(Long runId, long afterSequence) {
        RuntimeHandle handle = requireHandle(runId);
        return handle.latestSequence.get() > afterSequence ? handle.latestFrame.get() : null;
    }

    public List<JsonNode> framesAfter(Long runId, long afterSequence) {
        RuntimeHandle handle = requireHandle(runId);
        List<JsonNode> frames = new ArrayList<>();
        synchronized (handle.frameBuffer) {
            for (JsonNode frame : handle.frameBuffer) {
                if (frame.path("sequence").asLong() > afterSequence) frames.add(frame);
            }
        }
        return frames;
    }

    private void startReaders(RuntimeHandle handle) {
        Thread outputThread = new Thread(() -> {
            try (BufferedReader reader = new BufferedReader(new InputStreamReader(handle.process.getInputStream(), StandardCharsets.UTF_8))) {
                String line;
                while ((line = reader.readLine()) != null) {
                    JsonNode event;
                    try {
                        event = objectMapper.readTree(line);
                    } catch (Exception ignored) {
                        // Vendor algorithms may print diagnostics. Only NDJSON
                        // events belong to the runtime protocol.
                        continue;
                    }
                    String eventType = event.path("event").asText();
                    if ("runtimeReady".equals(eventType)) {
                        handle.state.set(event.path("state").asText("PREPARED"));
                        handle.ready.countDown();
                    } else if ("frame".equals(eventType)) {
                        JsonNode frame = event.path("payload");
                        handle.latestFrame.set(frame);
                        handle.latestSequence.set(frame.path("sequence").asLong());
                        synchronized (handle.frameBuffer) {
                            handle.frameBuffer.addLast(frame);
                            while (handle.frameBuffer.size() > 90) handle.frameBuffer.removeFirst();
                        }
                    } else if ("stateChanged".equals(eventType) || "runtimeStopped".equals(eventType)) {
                        handle.state.set(event.path("state").asText(handle.state.get()));
                    }
                }
                if (handle.ready.getCount() > 0) {
                    handle.stderrDone.await(2, TimeUnit.SECONDS);
                    String detail = handle.lastStderr.get();
                    handle.error.compareAndSet(null, detail == null
                            ? "Algorithm process exited before runtimeReady"
                            : detail);
                    handle.ready.countDown();
                }
            } catch (Exception exception) {
                handle.error.compareAndSet(null, exception.getMessage());
                handle.ready.countDown();
            }
        }, "algorithm-out-" + handle.runId);
        outputThread.setDaemon(true);
        outputThread.start();
        Thread errorThread = new Thread(() -> {
            try (BufferedReader reader = new BufferedReader(new InputStreamReader(handle.process.getErrorStream(), StandardCharsets.UTF_8))) {
                String line;
                String last = null;
                while ((line = reader.readLine()) != null) {
                    last = line;
                    handle.lastStderr.set(line);
                }
                if (handle.process.exitValue() != 0 && last != null) handle.error.compareAndSet(null, last);
            } catch (Exception ignored) {
                // Process shutdown closes the stream normally.
            } finally {
                handle.stderrDone.countDown();
            }
        }, "algorithm-err-" + handle.runId);
        errorThread.setDaemon(true);
        errorThread.start();
    }

    private void send(RuntimeHandle handle, Map<String, Object> payload) {
        if (!handle.process.isAlive()) throw new BusinessException(ErrorCode.BAD_REQUEST, "算法运行器已经停止");
        try {
            synchronized (handle.writer) {
                handle.writer.write(objectMapper.writeValueAsString(payload));
                handle.writer.newLine();
                handle.writer.flush();
            }
        } catch (IOException exception) {
            throw new BusinessException(ErrorCode.BAD_REQUEST, "算法指令发送失败：" + exception.getMessage());
        }
    }

    private RuntimeHandle requireHandle(Long runId) {
        RuntimeHandle handle = handles.get(runId);
        if (handle == null) throw new BusinessException(ErrorCode.NOT_FOUND, "算法运行实例不存在，请重新执行任务");
        return handle;
    }

    private void stopExisting(Long runId) {
        RuntimeHandle previous = handles.remove(runId);
        if (previous == null) return;
        try { previous.writer.close(); } catch (IOException ignored) {}
        previous.process.destroy();
        try {
            if (!previous.process.waitFor(2, TimeUnit.SECONDS)) previous.process.destroyForcibly();
        } catch (InterruptedException exception) {
            Thread.currentThread().interrupt();
            previous.process.destroyForcibly();
        }
    }

    private static Path resolveRunnerPath(String configuredPath) {
        Path configured = Path.of(configuredPath).toAbsolutePath().normalize();
        if (Files.isRegularFile(configured)) return configured;
        Path workingDirectory = Path.of("").toAbsolutePath().normalize();
        List<Path> candidates = List.of(
                workingDirectory.resolve("algorithm-service/runner.py").normalize(),
                workingDirectory.resolve("../algorithm-service/runner.py").normalize(),
                workingDirectory.resolve("../../algorithm-service/runner.py").normalize()
        );
        return candidates.stream().filter(Files::isRegularFile).findFirst().orElse(configured);
    }

    @PreDestroy
    public void close() {
        new ArrayList<>(handles.keySet()).forEach(this::stopExisting);
    }

    private static final class RuntimeHandle {
        final Long runId;
        final String algorithmCode;
        final Process process;
        final BufferedWriter writer;
        final CountDownLatch ready = new CountDownLatch(1);
        final CountDownLatch stderrDone = new CountDownLatch(1);
        final AtomicReference<String> state = new AtomicReference<>("STARTING");
        final AtomicReference<String> error = new AtomicReference<>();
        final AtomicReference<String> lastStderr = new AtomicReference<>();
        final AtomicReference<JsonNode> latestFrame = new AtomicReference<>();
        final AtomicLong latestSequence = new AtomicLong();
        final Deque<JsonNode> frameBuffer = new ArrayDeque<>();

        RuntimeHandle(Long runId, String algorithmCode, Process process, BufferedWriter writer) {
            this.runId = runId;
            this.algorithmCode = algorithmCode;
            this.process = process;
            this.writer = writer;
        }
    }
}
