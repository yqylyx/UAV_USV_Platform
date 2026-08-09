package com.uavusv.platform.module.gateway.v1;

import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.databind.node.ObjectNode;
import org.springframework.stereotype.Component;
import org.springframework.web.socket.TextMessage;
import org.springframework.web.socket.WebSocketSession;
import org.springframework.web.socket.handler.TextWebSocketHandler;

import java.net.URI;
import java.net.URLDecoder;
import java.nio.charset.StandardCharsets;

@Component
public class GatewayV1WebSocketHandler extends TextWebSocketHandler {

    private final GatewayEnvelopeDecoder decoder;
    private final GatewaySequenceGuard sequenceGuard;
    private final RealtimeHub realtimeHub;
    private final ObjectMapper objectMapper;

    public GatewayV1WebSocketHandler(
            GatewayEnvelopeDecoder decoder,
            GatewaySequenceGuard sequenceGuard,
            RealtimeHub realtimeHub,
            ObjectMapper objectMapper
    ) {
        this.decoder = decoder;
        this.sequenceGuard = sequenceGuard;
        this.realtimeHub = realtimeHub;
        this.objectMapper = objectMapper;
    }

    @Override
    protected void handleTextMessage(WebSocketSession session, TextMessage message) throws Exception {
        try {
            GatewayEnvelope envelope = decoder.decode(message.getPayload());
            GatewaySequenceGuard.SequenceCheckResult result = sequenceGuard.inspect(
                    envelope,
                    expectedRunId(session.getUri())
            );
            if (result.accepted()) {
                realtimeHub.publish(envelope);
            }
            session.sendMessage(new TextMessage(ack(envelope, result)));
        } catch (IllegalArgumentException exception) {
            session.sendMessage(new TextMessage(error(exception.getMessage())));
        }
    }

    private String ack(
            GatewayEnvelope envelope,
            GatewaySequenceGuard.SequenceCheckResult result
    ) throws Exception {
        ObjectNode node = objectMapper.createObjectNode();
        node.put("type", "gateway.mock_ack");
        node.put("accepted", result.accepted());
        node.put("status", result.status().name());
        node.put("messageType", envelope.type().wireName());
        node.put("source", envelope.source());
        node.put("streamId", envelope.streamId());
        node.put("sequence", envelope.sequence());
        if (envelope.runId() != null) {
            node.put("runId", envelope.runId());
        }
        return objectMapper.writeValueAsString(node);
    }

    private String error(String detail) throws Exception {
        ObjectNode node = objectMapper.createObjectNode();
        node.put("type", "gateway.mock_ack");
        node.put("accepted", false);
        node.put("status", "INVALID_ENVELOPE");
        node.put("detail", detail);
        return objectMapper.writeValueAsString(node);
    }

    private String expectedRunId(URI uri) {
        if (uri == null || uri.getQuery() == null || uri.getQuery().isBlank()) {
            return null;
        }
        for (String pair : uri.getQuery().split("&")) {
            String[] parts = pair.split("=", 2);
            if (parts.length == 2 && "runId".equals(parts[0])) {
                return URLDecoder.decode(parts[1], StandardCharsets.UTF_8);
            }
        }
        return null;
    }
}
