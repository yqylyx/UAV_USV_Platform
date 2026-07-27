package com.uavusv.platform.module.visualsensor.integration;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.databind.node.ArrayNode;
import com.fasterxml.jackson.databind.node.ObjectNode;
import com.uavusv.platform.module.visualsensor.service.VisualSensorService;
import jakarta.annotation.PostConstruct;
import jakarta.annotation.PreDestroy;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Component;

import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.WebSocket;
import java.time.Duration;
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.CompletionStage;
import java.util.concurrent.Executors;
import java.util.concurrent.ScheduledExecutorService;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicBoolean;

@Component
public class VisualSensorWebSocketClient implements WebSocket.Listener {

    private static final Logger log = LoggerFactory.getLogger(VisualSensorWebSocketClient.class);
    private final ObjectMapper objectMapper;
    private final VisualSensorService visualSensorService;
    private final URI endpoint;
    private final HttpClient httpClient;
    private final ScheduledExecutorService executor;
    private final AtomicBoolean connecting = new AtomicBoolean();
    private final StringBuilder messageBuffer = new StringBuilder();
    private volatile WebSocket socket;
    private volatile boolean shuttingDown;
    private volatile String lastFocusedCamera = "";

    public VisualSensorWebSocketClient(
            ObjectMapper objectMapper,
            VisualSensorService visualSensorService,
            @Value("${app.visual-sensor.websocket-url:ws://127.0.0.1:8766/visual_sensors}") String endpoint
    ) {
        this.objectMapper = objectMapper;
        this.visualSensorService = visualSensorService;
        this.endpoint = URI.create(endpoint);
        this.httpClient = HttpClient.newBuilder().connectTimeout(Duration.ofSeconds(3)).build();
        this.executor = Executors.newSingleThreadScheduledExecutor(runnable -> {
            Thread thread = new Thread(runnable, "visual-sensor-websocket");
            thread.setDaemon(true);
            return thread;
        });
    }

    @PostConstruct
    public void start() {
        executor.schedule(this::connect, 0, TimeUnit.SECONDS);
        executor.scheduleAtFixedRate(this::syncSubscription, 1, 1, TimeUnit.SECONDS);
    }

    private void connect() {
        if (shuttingDown || socket != null || !connecting.compareAndSet(false, true)) {
            return;
        }
        httpClient.newWebSocketBuilder()
                .connectTimeout(Duration.ofSeconds(3))
                .buildAsync(endpoint, this)
                .whenComplete((ignored, error) -> {
                    connecting.set(false);
                    if (error != null) {
                        visualSensorService.observeGateway(false, "无法连接 " + endpoint);
                        executor.schedule(this::connect, 2, TimeUnit.SECONDS);
                    }
                });
    }

    @Override
    public void onOpen(WebSocket webSocket) {
        socket = webSocket;
        visualSensorService.observeGateway(true, "视觉传感器网关在线");
        log.info("Connected to visual sensor WebSocket {}", endpoint);
        sendSubscription(true);
        webSocket.request(1);
    }

    @Override
    public CompletionStage<?> onText(WebSocket webSocket, CharSequence data, boolean last) {
        messageBuffer.append(data);
        if (last) {
            String payload = messageBuffer.toString();
            messageBuffer.setLength(0);
            try {
                JsonNode root = objectMapper.readTree(payload);
                if ("camera_frame".equals(root.path("type").asText())) {
                    visualSensorService.observeFrame(root);
                }
            } catch (Exception exception) {
                log.debug("Ignored invalid visual sensor frame: {}", exception.getMessage());
            }
        }
        webSocket.request(1);
        return CompletableFuture.completedFuture(null);
    }

    @Override
    public CompletionStage<?> onClose(WebSocket webSocket, int statusCode, String reason) {
        disconnect("连接关闭: " + statusCode + " " + reason);
        return CompletableFuture.completedFuture(null);
    }

    @Override
    public void onError(WebSocket webSocket, Throwable error) {
        disconnect("连接异常: " + error.getMessage());
    }

    private void syncSubscription() {
        if (socket == null) {
            connect();
            return;
        }
        String focus = visualSensorService.focusedCameraId();
        if (!focus.equals(lastFocusedCamera)) {
            sendSubscription(false);
        }
    }

    private void sendSubscription(boolean force) {
        WebSocket current = socket;
        if (current == null) {
            return;
        }
        String focus = visualSensorService.focusedCameraId();
        if (!force && focus.equals(lastFocusedCamera)) {
            return;
        }
        ObjectNode frame = objectMapper.createObjectNode();
        frame.put("type", "sensor_subscription");
        frame.put("focused_camera_id", focus);
        frame.put("thumbnail_fps", 2);
        frame.put("focused_fps", 12);
        ArrayNode cameras = frame.putArray("camera_ids");
        visualSensorService.cameraIds().forEach(cameras::add);
        current.sendText(frame.toString(), true);
        lastFocusedCamera = focus;
    }

    private void disconnect(String detail) {
        socket = null;
        lastFocusedCamera = "";
        visualSensorService.observeGateway(false, detail);
        if (!shuttingDown) {
            executor.schedule(this::connect, 2, TimeUnit.SECONDS);
        }
    }

    @PreDestroy
    public void stop() {
        shuttingDown = true;
        WebSocket current = socket;
        socket = null;
        if (current != null) {
            current.sendClose(WebSocket.NORMAL_CLOSURE, "platform stopping");
        }
        executor.shutdownNow();
    }
}
