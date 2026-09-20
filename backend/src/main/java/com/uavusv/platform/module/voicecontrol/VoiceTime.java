package com.uavusv.platform.module.voicecontrol;

import org.springframework.stereotype.Component;

import java.time.Instant;
import java.time.temporal.ChronoUnit;

/** Override in deterministic tests; elapsed checks never trust process/browser clocks. */
@Component
public class VoiceTime {
    public Instant now() {
        return Instant.now().truncatedTo(ChronoUnit.MICROS);
    }

    public long nanos() {
        return System.nanoTime();
    }

    public String stamp() {
        return now().toString();
    }
}
