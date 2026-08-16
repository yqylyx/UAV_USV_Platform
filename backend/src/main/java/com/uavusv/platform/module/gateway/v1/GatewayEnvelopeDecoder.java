package com.uavusv.platform.module.gateway.v1;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.springframework.stereotype.Component;

import java.time.Instant;

@Component
public class GatewayEnvelopeDecoder {

    private final ObjectMapper objectMapper;

    public GatewayEnvelopeDecoder(ObjectMapper objectMapper) {
        this.objectMapper = objectMapper;
    }

    public GatewayEnvelope decode(String json) {
        try {
            JsonNode root = objectMapper.readTree(json);
            String version = text(root, "version", text(root, "specVersion", "v1"));
            GatewayMessageType type = GatewayMessageType.fromWireName(
                    text(root, "type", text(root, "messageType", null))
            );
            String source = requireText(root, "source");
            String runId = text(root, "runId", text(root, "run_id", null));
            String streamId = text(root, "streamId", text(root, "stream_id", type.wireName()));
            long sequence = root.path("sequence").asLong(-1);
            if (sequence < 0) {
                throw new IllegalArgumentException("Gateway envelope sequence must be non-negative");
            }
            JsonNode payload = root.has("payload") ? root.path("payload") : objectMapper.createObjectNode();
            return new GatewayEnvelope(
                    version,
                    type,
                    source,
                    readTimestamp(root.path("timestamp")),
                    runId,
                    streamId,
                    sequence,
                    payload
            );
        } catch (IllegalArgumentException exception) {
            throw exception;
        } catch (Exception exception) {
            throw new IllegalArgumentException("Invalid gateway envelope JSON", exception);
        }
    }

    private String requireText(JsonNode root, String fieldName) {
        String value = text(root, fieldName, null);
        if (value == null || value.isBlank()) {
            throw new IllegalArgumentException("Gateway envelope missing required field: " + fieldName);
        }
        return value;
    }

    private String text(JsonNode root, String fieldName, String fallback) {
        JsonNode value = root.path(fieldName);
        if (!value.isTextual() || value.asText().isBlank()) {
            return fallback;
        }
        return value.asText();
    }

    private Instant readTimestamp(JsonNode value) {
        if (value == null || value.isMissingNode() || value.isNull()) {
            return Instant.now();
        }
        if (value.isNumber()) {
            return Instant.ofEpochMilli(value.asLong());
        }
        if (value.isObject() && value.has("seconds")) {
            long seconds = value.path("seconds").asLong();
            long nanos = value.path("nanos").asLong(0);
            return Instant.ofEpochSecond(seconds, nanos);
        }
        return Instant.parse(value.asText());
    }
}
