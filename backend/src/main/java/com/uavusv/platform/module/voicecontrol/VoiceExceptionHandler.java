package com.uavusv.platform.module.voicecontrol;

import com.fasterxml.jackson.databind.node.ObjectNode;

import org.springframework.core.annotation.Order;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.*;

@RestControllerAdvice
@Order(-100)
public class VoiceExceptionHandler {
    private final VoiceJson j;
    private final VoiceTime t;

    public VoiceExceptionHandler(VoiceJson j, VoiceTime t) {
        this.j = j;
        this.t = t;
    }

    @ExceptionHandler(VoiceFailure.class)
    public ResponseEntity<ObjectNode> failure(VoiceFailure e) {
        var n = j.object();
        n.put("code", e.code).put("message", e.code).putNull("data").put("timestamp", t.stamp());
        return ResponseEntity.status(e.status).header("Cache-Control", "no-store").body(n);
    }
}
