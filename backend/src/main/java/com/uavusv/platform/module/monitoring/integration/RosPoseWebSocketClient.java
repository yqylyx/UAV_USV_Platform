package com.uavusv.platform.module.monitoring.integration;

import com.fasterxml.jackson.databind.ObjectMapper;
import com.uavusv.platform.module.monitoring.dto.request.RosPoseFrame;
import com.uavusv.platform.module.monitoring.service.RuntimeStateService;
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
public class RosPoseWebSocketClient implements WebSocket.Listener {

    private static final Logger log = LoggerFactory.getLogger(RosPoseWebSocketClient.class);

    private final ObjectMapper objectMapper;
    private final RuntimeStateService runtimeStateService;
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
            @Value("${app.runtime.ros-websocket-url}") String endpoint
    ) {
        this.objectMapper = objectMapper;
        this.runtimeStateService = runtimeStateService;
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
                RosPoseFrame frame = objectMapper.readValue(payload, RosPoseFrame.class);
                if (frame.boat() != null && frame.drone() != null) {
                    runtimeStateService.observeRosFrame(frame);
                }
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
