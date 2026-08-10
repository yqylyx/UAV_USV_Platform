package com.uavusv.platform.module.gateway.v1;

import jakarta.annotation.PreDestroy;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.boot.context.event.ApplicationReadyEvent;
import org.springframework.context.event.EventListener;
import org.springframework.stereotype.Component;

import java.io.ByteArrayOutputStream;
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.WebSocket;
import java.nio.ByteBuffer;
import java.time.Duration;
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.CompletionStage;
import java.util.concurrent.Executors;
import java.util.concurrent.ScheduledExecutorService;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicBoolean;

@Component
@ConditionalOnProperty(
        name = "app.gateway.v1.enabled",
        havingValue = "true"
)
public class RosGatewayV1WebSocketClient implements WebSocket.Listener {

    private static final Logger log = LoggerFactory.getLogger(RosGatewayV1WebSocketClient.class);

    private final GatewayEnvelopeDecoder gatewayEnvelopeDecoder;
    private final GatewayProtobufDecoder gatewayProtobufDecoder;
    private final GatewaySequenceGuard gatewaySequenceGuard;
    private final RealtimeHub realtimeHub;
    private final URI endpoint;
    private final HttpClient httpClient;
    private final ScheduledExecutorService reconnectExecutor;
    private final AtomicBoolean connecting = new AtomicBoolean(false);
    private final AtomicBoolean reconnectScheduled = new AtomicBoolean(false);
    private final StringBuilder messageBuffer = new StringBuilder();
    private final ByteArrayOutputStream binaryMessageBuffer = new ByteArrayOutputStream();
    private volatile WebSocket socket;
    private volatile boolean closing;

    public RosGatewayV1WebSocketClient(
            GatewayEnvelopeDecoder gatewayEnvelopeDecoder,
            GatewayProtobufDecoder gatewayProtobufDecoder,
            GatewaySequenceGuard gatewaySequenceGuard,
            RealtimeHub realtimeHub,
            @Value("${app.gateway.v1.websocket-url:ws://127.0.0.1:8765/uav_usv/v1}") String websocketUrl
    ) {
        this.gatewayEnvelopeDecoder = gatewayEnvelopeDecoder;
        this.gatewayProtobufDecoder = gatewayProtobufDecoder;
        this.gatewaySequenceGuard = gatewaySequenceGuard;
        this.realtimeHub = realtimeHub;
        this.endpoint = URI.create(websocketUrl);
        this.httpClient = HttpClient.newBuilder()
                .connectTimeout(Duration.ofSeconds(3))
                .build();
        this.reconnectExecutor = Executors.newSingleThreadScheduledExecutor(task -> {
            Thread thread = new Thread(task, "ros-gateway-v1-reconnect");
            thread.setDaemon(true);
            return thread;
        });
    }

    @EventListener(ApplicationReadyEvent.class)
    public void connect() {
        if (closing || socket != null || !connecting.compareAndSet(false, true)) {
            return;
        }
        httpClient.newWebSocketBuilder()
                .connectTimeout(Duration.ofSeconds(3))
                .buildAsync(endpoint, this)
                .whenComplete((webSocket, error) -> {
                    connecting.set(false);
                    if (error != null) {
                        log.warn("ROS Gateway v1 connection failed: {}", error.getMessage());
                        scheduleReconnect();
                    }
                });
    }

    public void reconnect() {
        WebSocket current = socket;
        socket = null;
        if (current != null) {
            current.abort();
        }
        scheduleReconnect();
    }

    @Override
    public void onOpen(WebSocket webSocket) {
        socket = webSocket;
        log.info("ROS Gateway v1 connected");
        webSocket.request(1);
    }

    @Override
    public CompletionStage<?> onText(WebSocket webSocket, CharSequence data, boolean last) {
        synchronized (messageBuffer) {
            messageBuffer.append(data);
            if (last) {
                String payload = messageBuffer.toString();
                messageBuffer.setLength(0);
                handleTextPayload(payload);
            }
        }
        webSocket.request(1);
        return CompletableFuture.completedFuture(null);
    }

    @Override
    public CompletionStage<?> onBinary(WebSocket webSocket, ByteBuffer data, boolean last) {
        byte[] chunk = new byte[data.remaining()];
        data.get(chunk);
        synchronized (binaryMessageBuffer) {
            binaryMessageBuffer.writeBytes(chunk);
            if (last) {
                byte[] payload = binaryMessageBuffer.toByteArray();
                binaryMessageBuffer.reset();
                handleBinaryPayload(payload);
            }
        }
        webSocket.request(1);
        return CompletableFuture.completedFuture(null);
    }

    @Override
    public CompletionStage<?> onClose(WebSocket webSocket, int statusCode, String reason) {
        handleDisconnect("connection closed: " + statusCode + " " + reason);
        return CompletableFuture.completedFuture(null);
    }

    @Override
    public void onError(WebSocket webSocket, Throwable error) {
        handleDisconnect("connection error: " + error.getMessage());
    }

    @PreDestroy
    public void close() {
        closing = true;
        WebSocket current = socket;
        socket = null;
        reconnectExecutor.shutdownNow();
        if (current != null) {
            current.sendClose(WebSocket.NORMAL_CLOSURE, "platform stopping");
        }
    }

    private void handleTextPayload(String payload) {
        try {
            GatewayEnvelope envelope = gatewayEnvelopeDecoder.decode(payload);
            log.info("ROS Gateway v1 message type {}", envelope.type().wireName());
            GatewaySequenceGuard.SequenceCheckResult result = gatewaySequenceGuard.inspect(envelope);
            if (result.accepted()) {
                realtimeHub.publish(envelope);
            } else {
                log.warn("ROS Gateway v1 rejected sequence result {}", result.status());
            }
        } catch (IllegalArgumentException exception) {
            log.warn("Ignored invalid ROS Gateway v1 message: {}", exception.getMessage());
        }
    }

    private void handleBinaryPayload(byte[] payload) {
        try {
            GatewayEnvelope envelope = gatewayProtobufDecoder.decode(payload);
            log.info("ROS Gateway v1 binary message type {}", envelope.type().wireName());
            GatewaySequenceGuard.SequenceCheckResult result = gatewaySequenceGuard.inspect(envelope);
            if (result.accepted()) {
                realtimeHub.publish(envelope);
            } else {
                log.warn("ROS Gateway v1 rejected binary sequence result {}", result.status());
            }
        } catch (IllegalArgumentException exception) {
            log.warn("Ignored invalid ROS Gateway v1 binary message: {}", exception.getMessage());
        }
    }

    private void handleDisconnect(String detail) {
        socket = null;
        if (!closing) {
            log.warn("ROS Gateway v1 disconnected: {}", detail);
            scheduleReconnect();
        }
    }

    private void scheduleReconnect() {
        if (closing || !reconnectScheduled.compareAndSet(false, true)) {
            return;
        }
        reconnectExecutor.schedule(() -> {
            reconnectScheduled.set(false);
            connect();
        }, 2, TimeUnit.SECONDS);
    }
}
