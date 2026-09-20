package com.uavusv.platform.module.voicecontrol;

import com.fasterxml.jackson.core.JsonParser;
import com.fasterxml.jackson.databind.*;
import com.fasterxml.jackson.databind.node.*;

import org.springframework.stereotype.Component;

import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.util.*;

@Component
public class VoiceJson {
    public final ObjectMapper mapper =
            new ObjectMapper()
                    .enable(JsonParser.Feature.STRICT_DUPLICATE_DETECTION)
                    .enable(DeserializationFeature.FAIL_ON_TRAILING_TOKENS);
    private final JsonNode definitions;

    public VoiceJson() {
        try (var in = getClass().getResourceAsStream("/voicecontrol/contracts.schema.json")) {
            definitions = mapper.readTree(in).get("definitions");
        } catch (Exception e) {
            throw new IllegalStateException("Missing P0 schema", e);
        }
    }

    public ObjectNode object() {
        return mapper.createObjectNode();
    }

    public ObjectNode read(String s) {
        try {
            var n = mapper.readTree(s);
            if (!(n instanceof ObjectNode o)) throw VoiceFailure.bad();
            return o;
        } catch (Exception e) {
            throw VoiceFailure.bad();
        }
    }

    public void validate(String definition, JsonNode n) {
        if (!matches(definitions.required(definition), n)) throw VoiceFailure.bad();
    }

    // Evaluates the finite draft-07 vocabulary used by the checked-in P0 schema.
    private boolean matches(JsonNode s, JsonNode n) {
        if (n == null) return false;
        if (s.has("$ref"))
            return matches(
                    definitions.required(s.get("$ref").asText().replace("#/definitions/", "")), n);
        if (s.has("anyOf")) {
            boolean ok = false;
            for (var v : s.get("anyOf")) ok |= matches(v, n);
            if (!ok) return false;
        }
        if (s.has("allOf")) for (var v : s.get("allOf")) if (!matches(v, n)) return false;
        if (s.has("if")) {
            String branch = matches(s.get("if"), n) ? "then" : "else";
            if (s.has(branch) && !matches(s.get(branch), n)) return false;
        }
        if (s.has("const") && !s.get("const").equals(n)) return false;
        if (s.has("enum")) {
            boolean ok = false;
            for (var v : s.get("enum")) ok |= v.equals(n);
            if (!ok) return false;
        }
        if (s.has("type")) {
            boolean ok =
                    switch (s.get("type").asText()) {
                        case "object" -> n.isObject();
                        case "array" -> n.isArray();
                        case "string" -> n.isTextual();
                        case "integer" -> n.isIntegralNumber();
                        case "boolean" -> n.isBoolean();
                        case "null" -> n.isNull();
                        default -> false;
                    };
            if (!ok) return false;
        }
        if (n.isObject()) {
            if (s.has("required"))
                for (var k : s.get("required")) if (!n.has(k.asText())) return false;
            JsonNode p = s.path("properties");
            var fields = n.fields();
            while (fields.hasNext()) {
                var f = fields.next();
                if (p.has(f.getKey())) {
                    if (!matches(p.get(f.getKey()), f.getValue())) return false;
                } else if (s.has("additionalProperties")
                        && !s.get("additionalProperties").asBoolean()) return false;
            }
        }
        if (n.isArray()) {
            if (n.size() < s.path("minItems").asInt(0)
                    || n.size() > s.path("maxItems").asInt(Integer.MAX_VALUE)) return false;
            Set<JsonNode> seen = new HashSet<>();
            for (var item : n) {
                if (s.has("items") && !matches(s.get("items"), item)) return false;
                if (s.path("uniqueItems").asBoolean() && !seen.add(item)) return false;
            }
        }
        if (n.isTextual()) {
            String t = n.asText();
            int len = t.codePointCount(0, t.length());
            if (len < s.path("minLength").asInt(0)
                    || len > s.path("maxLength").asInt(Integer.MAX_VALUE)) return false;
            if (s.has("pattern") && !t.matches(s.get("pattern").asText())) return false;
            if ("date-time".equals(s.path("format").asText()))
                try {
                    java.time.OffsetDateTime.parse(t);
                } catch (Exception e) {
                    return false;
                }
        }
        if (n.isNumber()) {
            if (!n.isIntegralNumber() || !n.canConvertToLong()) return false;
            if (s.has("minimum") && n.longValue() < s.get("minimum").longValue()) return false;
            if (s.has("maximum") && n.longValue() > s.get("maximum").longValue()) return false;
        }
        return true;
    }

    public static String uuid() {
        return UUID.randomUUID().toString();
    }

    public static String uuid(String value) {
        if (value == null
                || !value.matches("[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}"))
            throw VoiceFailure.bad();
        return value;
    }

    public String canonical(JsonNode n) {
        if (n.isObject()) {
            var keys = new TreeSet<String>();
            n.fieldNames().forEachRemaining(keys::add);
            var items = new ArrayList<String>();
            for (String k : keys) items.add(quote(k) + ":" + canonical(n.get(k)));
            return "{" + String.join(",", items) + "}";
        }
        if (n.isArray()) {
            var items = new ArrayList<String>();
            for (var v : n) items.add(canonical(v));
            return "[" + String.join(",", items) + "]";
        }
        if (n.isTextual()) return quote(n.asText());
        if (n.isNull() || n.isBoolean() || n.isIntegralNumber()) return n.toString();
        throw VoiceFailure.bad();
    }

    private String quote(String s) {
        StringBuilder b = new StringBuilder("\"");
        for (char c : s.toCharArray())
            switch (c) {
                case '"' -> b.append("\\\"");
                case '\\' -> b.append("\\\\");
                case '\n' -> b.append("\\n");
                case '\r' -> b.append("\\r");
                case '\t' -> b.append("\\t");
                case '\b' -> b.append("\\b");
                case '\f' -> b.append("\\f");
                default -> {
                    if (c < 32 || c >= 127)
                        b.append(String.format(Locale.ROOT, "\\u%04x", (int) c));
                    else b.append(c);
                }
            }
        return b.append('"').toString();
    }

    public String hash(JsonNode n) {
        try {
            return HexFormat.of()
                    .formatHex(
                            MessageDigest.getInstance("SHA-256")
                                    .digest(canonical(n).getBytes(StandardCharsets.UTF_8)));
        } catch (java.security.NoSuchAlgorithmException e) {
            throw new IllegalStateException(e);
        }
    }
}
