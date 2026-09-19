package com.uavusv.platform.module.voicecontrol;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Component;

@Component
public class VoiceSettings {
    private volatile boolean enabled;

    public VoiceSettings(@Value("${app.voicecontrol.enabled:false}") boolean enabled) {
        this.enabled = enabled;
    }

    public boolean enabled() {
        return enabled;
    }

    // Internal configuration hook, deliberately not exposed as a public HTTP setting.
    public void setEnabled(boolean value) {
        enabled = value;
    }

    public void requireEnabled() {
        if (!enabled) throw new VoiceFailure(503, "VOICE_CONTROL_DISABLED");
    }
}
