package com.uavusv.platform.module.voiceintelligence;

import org.springframework.http.ResponseEntity;

import java.time.Instant;
import java.util.LinkedHashMap;
import java.util.Map;

public final class AsrResponses {
    public record Outcome(int status, Map<String, Object> body, Integer retryAfter) {}

    public static Outcome error(AsrFailure e) {
        return new Outcome(e.status, body(e.code, message(e.code), null), e.retryAfter);
    }

    public static Map<String, Object> body(String code, String message, Object data) {
        var b = new LinkedHashMap<String, Object>();
        b.put("code", code);
        b.put("message", message);
        b.put("data", data);
        b.put("timestamp", Instant.now().toString());
        return b;
    }

    public static ResponseEntity<Map<String, Object>> response(Outcome o) {
        var r = ResponseEntity.status(o.status()).header("Cache-Control", "no-store");
        if (o.retryAfter() != null) r.header("Retry-After", o.retryAfter().toString());
        return r.body(o.body());
    }

    private static String message(String c) {
        return switch (c) {
            case "VOICE_NO_SPEECH" -> "未识别到有效语音，请重新录制";
            case "VOICE_REQUEST_IN_PROGRESS" -> "原请求仍在处理中";
            case "VOICE_TRANSCRIPTION_TIMEOUT" -> "识别等待超时，请联系管理员检查服务";
            case "VOICE_AUDIO_TOO_LONG" -> "录音超过60秒，请缩短后重录";
            case "VOICE_INTELLIGENCE_DISABLED" -> "本地语音识别尚未启用";
            case "VOICE_RATE_LIMITED" -> "识别服务忙，请稍后再试";
            default -> "语音请求未完成，请检查输入或联系管理员";
        };
    }
}
