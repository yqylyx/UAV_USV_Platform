package com.uavusv.platform.module.monitoring.integration;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.databind.node.ObjectNode;
import com.uavusv.platform.module.monitoring.dto.request.RosPoseFrame;
import com.uavusv.platform.module.monitoring.service.RuntimeStateService;
import com.uavusv.platform.module.runtimecontrol.dto.RuntimeCommandRequest;
import com.uavusv.platform.module.runtimecontrol.event.RosCommandAckReceivedEvent;
import jakarta.annotation.PostConstruct;
import jakarta.annotation.PreDestroy;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.ApplicationEventPublisher;
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
public class RosPoseWebSocketClient implements WebSocket.Listener {

    private static final Logger log = LoggerFactory.getLogger(RosPoseWebSocketClient.class);

    private final ObjectMapper objectMapper;
    private final RuntimeStateService runtimeStateService;
    private final ApplicationEventPublisher eventPublisher;
    private final URI endpoint;
    private final HttpClient httpClient;
    private final ScheduledExecutorService reconnectExecutor;
    private final AtomicBoolean connecting = new AtomicBoolean(false);
    private final StringBuilder messageBuffer = new StringBuilder();
    private volatile WebSocket socket;
    private volatile boolean shuttingDown;

    public RosPoseWebSocketClient(
            ObjectMapper objectMapper,
            RuntimeStateService runtimeStateService,
            ApplicationEventPublisher eventPublisher,
            @Value("${app.runtime.ros-websocket-url}") String endpoint
    ) {
        this.objectMapper = objectMapper;
        this.runtimeStateService = runtimeStateService;
        this.eventPublisher = eventPublisher;
        this.endpoint = URI.create(endpoint);
        this.httpClient = HttpClient.newBuilder().connectTimeout(Duration.ofSeconds(3)).build();
        this.reconnectExecutor = Executors.newSingleThreadScheduledExecutor(runnable -> {
            Thread thread = new Thread(runnable, "ros-websocket-reconnect");
            thread.setDaemon(true);
            return thread;
        });
    }

    @PostConstruct
    public void start() {
        scheduleConnect(0);
    }

    private void connect() {
        if (shuttingDown || socket != null || !connecting.compareAndSet(false, true)) {
            return;
        }

        httpClient.newWebSocketBuilder()
                .connectTimeout(Duration.ofSeconds(3))
                .buildAsync(endpoint, this)
                .whenComplete((webSocket, error) -> {
                    connecting.set(false);
                    if (error != null) {
                        runtimeStateService.observeRosConnection(false, "无法连接 " + endpoint);
                        log.debug("ROS WebSocket connection failed: {}", error.getMessage());
                        scheduleConnect(2);
                    }
                });
    }

    @Override
    public void onOpen(WebSocket webSocket) {
        socket = webSocket;
        runtimeStateService.observeRosConnection(true, "已连接 " + endpoint);
        log.info("Connected to ROS pose WebSocket {}", endpoint);
        webSocket.request(1);
    }

    @Override
    public CompletionStage<?> onText(WebSocket webSocket, CharSequence data, boolean last) {
        messageBuffer.append(data);
        if (last) {
            String payload = messageBuffer.toString();
            messageBuffer.setLength(0);
            try {
                handleMessage(payload);
            } catch (Exception exception) {
                log.warn("Ignored invalid ROS pose frame: {}", exception.getMessage());
            }
        }
        webSocket.request(1);
        return CompletableFuture.completedFuture(null);
    }

    @Override
    public CompletionStage<?> onClose(WebSocket webSocket, int statusCode, String reason) {
        handleDisconnect("连接关闭: " + statusCode + " " + reason);
        return CompletableFuture.completedFuture(null);
    }

    @Override
    public void onError(WebSocket webSocket, Throwable error) {
        handleDisconnect("连接异常: " + error.getMessage());
    }

    public void sendControlCommand(String commandKey, RuntimeCommandRequest request) {
        WebSocket current = socket;
        if (current == null) {
            throw new IllegalStateException("ROS WebSocket is not connected");
        }
        try {
            ObjectNode frame = objectMapper.createObjectNode();
            frame.put("type", "command");
            frame.put("commandKey", commandKey);
            frame.put("commandType", request.commandType().name());
            if (request.deviceCode() != null && !request.deviceCode().isBlank()) {
                frame.put("deviceCode", request.deviceCode());
            }
            if (request.payload() != null && !request.payload().isBlank()) {
                frame.set("payload", objectMapper.readTree(request.payload()));
            }
            current.sendText(objectMapper.writeValueAsString(frame), true)
                    .get(3, TimeUnit.SECONDS);
        } catch (Exception exception) {
            throw new IllegalStateException("Failed to send command to ROS WebSocket", exception);
        }
    }

    private void handleMessage(String payload) throws Exception {
        JsonNode root = objectMapper.readTree(payload);
        String type = root.path("type").asText("pose_frame");
        if ("command_ack".equals(type)) {
            eventPublisher.publishEvent(new RosCommandAckReceivedEvent(
                    root.path("commandKey").asText(),
                    root.path("status").asInt(),
                    root.path("message").asText(null)
            ));
            return;
        }
        if ("pose_frame".equals(type) || (root.has("boat") && root.has("drone"))) {
            JsonNode frameNode = root.has("frame") ? root.path("frame") : root;
            RosPoseFrame frame = objectMapper.treeToValue(frameNode, RosPoseFrame.class);
            if (frame.boat() != null && frame.drone() != null) {
                runtimeStateService.observeRosFrame(frame);
            }
        }
    }

    private void handleDisconnect(String detail) {
        socket = null;
        runtimeStateService.observeRosConnection(false, detail);
        if (!shuttingDown) {
            log.info("ROS pose WebSocket disconnected, retrying: {}", detail);
            scheduleConnect(2);
        }
    }

    private void scheduleConnect(long delaySeconds) {
        if (!shuttingDown) {
            reconnectExecutor.schedule(this::connect, delaySeconds, TimeUnit.SECONDS);
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
        reconnectExecutor.shutdownNow();
    }
}
