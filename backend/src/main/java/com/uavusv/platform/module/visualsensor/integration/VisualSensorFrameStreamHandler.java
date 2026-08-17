package com.uavusv.platform.module.visualsensor.integration;

import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.databind.node.ObjectNode;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.stereotype.Component;
import org.springframework.web.socket.CloseStatus;
import org.springframework.web.socket.TextMessage;
import org.springframework.web.socket.WebSocketSession;
import org.springframework.web.socket.handler.TextWebSocketHandler;

import java.time.Clock;
import java.util.Map;
import java.util.Set;
import java.util.concurrent.ConcurrentHashMap;

@Component
public class VisualSensorFrameStreamHandler extends TextWebSocketHandler {

    private static final long MIN_FRAME_INTERVAL_MILLIS = 125;

    private final Set<WebSocketSession> sessions = ConcurrentHashMap.newKeySet();
    private final Map<String, Long> lastSentAtMillis = new ConcurrentHashMap<>();
    private final ObjectMapper objectMapper;
    private final Clock clock;

    @Autowired
    public VisualSensorFrameStreamHandler(ObjectMapper objectMapper) {
        this(objectMapper, Clock.systemUTC());
    }

    VisualSensorFrameStreamHandler(ObjectMapper objectMapper, Clock clock) {
        this.objectMapper = objectMapper;
        this.clock = clock;
    }

    @Override
    public void afterConnectionEstablished(WebSocketSession session) {
        sessions.add(session);
    }

    @Override
    public void afterConnectionClosed(WebSocketSession session, CloseStatus status) {
        sessions.remove(session);
    }

    @Override
    public void handleTransportError(WebSocketSession session, Throwable exception) {
        sessions.remove(session);
    }

    public void publishFrame(
            String cameraId,
            String jpegBase64,
            int width,
            int height,
            long timestampMs,
            String source
    ) {
        if (sessions.isEmpty() || cameraId == null || cameraId.isBlank() || jpegBase64 == null || jpegBase64.isBlank()) {
            return;
        }
        long now = clock.millis();
        Long previous = lastSentAtMillis.get(cameraId);
        if (previous != null && now - previous < MIN_FRAME_INTERVAL_MILLIS) {
            return;
        }
        lastSentAtMillis.put(cameraId, now);
        try {
            ObjectNode frame = objectMapper.createObjectNode();
            frame.put("type", "visualSensorFrame");
            frame.put("cameraId", cameraId);
            frame.put("timestampMs", timestampMs > 0 ? timestampMs : now);
            frame.put("width", width);
            frame.put("height", height);
            frame.put("source", source == null || source.isBlank()
                    ? "ROS Gateway v1 media.camera_jpeg"
                    : source);
            frame.put("jpegBase64", jpegBase64);
            TextMessage message = new TextMessage(objectMapper.writeValueAsString(frame));
            for (WebSocketSession session : sessions) {
                send(session, message);
            }
        } catch (Exception ignored) {
            // Sensor intake must remain best-effort and must not block on browser clients.
        }
    }

    private void send(WebSocketSession session, TextMessage message) {
        if (!session.isOpen()) {
            sessions.remove(session);
            return;
        }
        try {
            synchronized (session) {
                session.sendMessage(message);
            }
        } catch (Exception exception) {
            sessions.remove(session);
        }
    }
}
