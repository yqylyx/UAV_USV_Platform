package com.uavusv.platform.module.voicecontrol;

public class VoiceFailure extends RuntimeException {
    public final int status;
    public final String code;

    public VoiceFailure(int status, String code) {
        super(code);
        this.status = status;
        this.code = code;
    }

    public static VoiceFailure bad() {
        return new VoiceFailure(400, "INVALID_REQUEST");
    }

    public static VoiceFailure conflict(String code) {
        return new VoiceFailure(409, code);
    }
}
