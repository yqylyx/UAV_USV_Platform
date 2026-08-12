package com.uavusv.platform.module.gateway.v1;

public record RosGatewayV1ControlAckEvent(
        String commandKey,
        String runId,
        String status,
        String detail,
        String errorCode
) {
}
