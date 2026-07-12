package com.uavusv.platform.module.runtimecontrol.event;

public record RosCommandAckReceivedEvent(String commandKey, int status, String message) {
}
