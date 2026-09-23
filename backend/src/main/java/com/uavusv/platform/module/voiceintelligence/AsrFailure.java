package com.uavusv.platform.module.voiceintelligence;

public final class AsrFailure extends RuntimeException {
    public final int status;
    public final String code;
    public final Integer retryAfter;
    public final boolean uncertain;

    public AsrFailure(int status, String code) {
        this(status, code, null, false);
    }

    public AsrFailure(int status, String code, Integer retryAfter, boolean uncertain) {
        super(code);
        this.status = status;
        this.code = code;
        this.retryAfter = retryAfter;
        this.uncertain = uncertain;
    }

    public static AsrFailure invalid() {
        return new AsrFailure(400, "VOICE_INVALID_REQUEST");
    }
}
