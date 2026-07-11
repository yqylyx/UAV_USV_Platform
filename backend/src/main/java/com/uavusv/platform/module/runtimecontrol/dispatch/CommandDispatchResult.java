package com.uavusv.platform.module.runtimecontrol.dispatch;

public record CommandDispatchResult(
        boolean accepted,
        boolean acknowledged,
        String detail,
        String errorCode
) {
    public static CommandDispatchResult acknowledged(String detail) {
        return new CommandDispatchResult(true, true, detail, null);
    }

    public static CommandDispatchResult dispatched(String detail) {
        return new CommandDispatchResult(true, false, detail, null);
    }

    public static CommandDispatchResult rejected(String errorCode, String detail) {
        return new CommandDispatchResult(false, false, detail, errorCode);
    }
}
