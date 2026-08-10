package com.uavusv.platform.module.gateway.v1;

public record RosGatewayV1ControlAckEvent(
        String commandKey,
        boolean success,
        String detail,
        String errorCode
) {
}
